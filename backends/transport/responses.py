"""OpenAI Responses API transport — for OpenCode Zen endpoint.

POST https://opencode.ai/zen/v1/responses
Authorization: Bearer <api_key>

The Responses API uses a different request/response shape than chat/completions:
  Request: { model, input: [...], stream: true, ... }
  SSE events: response.text.delta, response.done, etc.

This transport converts:
  Anthropic MessagesRequest → Responses API body
  Responses API SSE         → Anthropic SSE
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from loguru import logger

from backends.base import BackendAdapter, BackendConfig
from backends.error_mapping import map_error
from backends.rate_limit import GlobalRateLimiter
from engine import StreamEvent, append_rid, error_message, map_finish_reason
from engine.content import get_attr, get_type


def _convert_messages_to_input(messages: list[Any], system: Any = None) -> list[dict]:
    """Convert Anthropic messages to OpenAI Responses API 'input' format."""
    out: list[dict] = []

    if system:
        if isinstance(system, str):
            out.append({"role": "system", "content": system})
        elif isinstance(system, list):
            parts = [get_attr(b, "text", "") for b in system if get_type(b) == "text"]
            if parts:
                out.append({"role": "system", "content": "\n\n".join(parts)})

    for msg in messages:
        role    = msg.role if hasattr(msg, "role") else msg.get("role", "user")
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")

        if isinstance(content, str):
            out.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Convert complex content to text for Responses API
            parts: list[str] = []
            tool_calls: list[dict] = []
            for blk in content:
                bt = get_type(blk)
                if bt == "text":
                    parts.append(get_attr(blk, "text", ""))
                elif bt == "thinking":
                    th = get_attr(blk, "thinking", "")
                    parts.append(f"<think>\n{th}\n</think>")
                elif bt == "tool_use":
                    inp = get_attr(blk, "input", {})
                    tool_calls.append({
                        "id":   get_attr(blk, "id", ""),
                        "type": "function",
                        "function": {
                            "name":      get_attr(blk, "name", ""),
                            "arguments": json.dumps(inp),
                        },
                    })
                elif bt == "tool_result":
                    rc = get_attr(blk, "content", "")
                    if isinstance(rc, list):
                        rc = "\n".join(
                            i.get("text", str(i)) if isinstance(i, dict) else str(i)
                            for i in rc
                        )
                    out.append({
                        "role": "tool",
                        "tool_call_id": get_attr(blk, "tool_use_id", ""),
                        "content": str(rc),
                    })
            if parts or tool_calls:
                entry: dict = {"role": role, "content": "\n\n".join(parts) or " "}
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                out.append(entry)
        else:
            out.append({"role": role, "content": str(content)})

    return out


class ResponsesTransport(BackendAdapter):
    """
    Adapter for the OpenAI Responses API (POST /v1/responses).

    This is the transport used by the OpenCode Zen endpoint.

    Responses API SSE event types:
      - response.created
      - response.output_item.added
      - response.content_part.added
      - response.text.delta        ← main text streaming event
      - response.text.done
      - response.output_item.done
      - response.done              ← final event with full response
      - error
    """

    def __init__(
        self,
        cfg:          BackendConfig,
        *,
        tag:          str,
        base_url:     str,
        api_key:      str,
    ) -> None:
        super().__init__(cfg)
        self._tag      = tag
        self._base_url = base_url.rstrip("/")
        self._api_key  = api_key
        self._rl       = GlobalRateLimiter.scoped(
            tag.lower(),
            rate_limit=cfg.rate_limit or 40,
            rate_window=cfg.rate_window,
            max_concurrency=cfg.max_concurrency,
        )
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            proxy=cfg.proxy or None,
            timeout=httpx.Timeout(
                cfg.http_read_timeout,
                connect=cfg.http_connect_timeout,
                write=cfg.http_write_timeout,
            ),
        )

    async def cleanup(self) -> None:
        await self._http.aclose()

    # ── request building ──────────────────────────────────────────────────

    def _build_body(self, request: Any) -> dict:
        system  = getattr(request, "system", None)
        msgs    = _convert_messages_to_input(request.messages, system)
        body: dict[str, Any] = {
            "model":  request.model,
            "input":  msgs,
            "stream": True,
        }
        max_tok = getattr(request, "max_tokens", None)
        if max_tok:
            body["max_output_tokens"] = max_tok
        temp = getattr(request, "temperature", None)
        if temp is not None:
            body["temperature"] = temp

        # tool conversion
        tools = getattr(request, "tools", None)
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": getattr(t, "input_schema", {}) or {},
                }
                for t in tools
            ]
        return body

    def _headers(self) -> dict[str, str]:
        key = self._api_key or "placeholder"
        return {
            "Authorization":  f"Bearer {key}",
            "Content-Type":   "application/json",
            "Accept":         "text/event-stream",
        }

    # ── SSE parsing ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_sse(raw: str) -> tuple[str | None, str | None]:
        """Return (event_type, data_json) from a raw SSE event string."""
        etype: str | None = None
        data:  str | None = None
        for line in raw.strip().splitlines():
            if line.startswith("event:"):
                etype = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        return etype, data

    # ── streaming ─────────────────────────────────────────────────────────

    async def stream_response(
        self,
        request:      Any,
        input_tokens: int = 0,
        *,
        request_id:   str | None = None,
    ) -> AsyncIterator[str]:
        tag = self._tag
        rid = f" rid={request_id}" if request_id else ""
        body = self._build_body(request)

        logger.info(
            "{}_ZEN_STREAM:{} model={} msgs={}",
            tag, rid,
            body.get("model"),
            len(body.get("input", [])),
        )

        msg_id = f"msg_{uuid.uuid4()}"
        ev     = StreamEvent(msg_id, request.model, input_tokens)
        yield ev.message_start()

        resp:       httpx.Response | None = None
        finish_reason: str | None         = None
        out_tokens:    int                = 0
        async with self._rl.concurrency_slot():
            try:
                req = self._http.build_request(
                    "POST", "/responses", json=body, headers=self._headers()
                )
                resp = await self._rl.execute_with_retry(self._http.send, req, stream=True)
                resp.raise_for_status()

                raw_buf: list[str] = []
                async for line in resp.aiter_lines():
                    if line:
                        raw_buf.append(line)
                        continue

                    # blank line = end of SSE event
                    if not raw_buf:
                        continue
                    event_str = "\n".join(raw_buf) + "\n\n"
                    raw_buf.clear()

                    etype, data = self._parse_sse(event_str)
                    if not etype or not data:
                        continue

                    # ── event dispatch ────────────────────────────────

                    if etype == "response.text.delta":
                        try:
                            payload = json.loads(data)
                            text    = payload.get("delta", "")
                        except Exception:
                            text = data
                        for e in ev.ensure_text():
                            yield e
                        yield ev.text_delta(text)

                    elif etype == "response.done":
                        try:
                            payload = json.loads(data)
                            resp_obj = payload.get("response", {})
                            finish_reason = resp_obj.get("stop_reason") or "end_turn"
                            usage = resp_obj.get("usage", {})
                            out_tokens = usage.get("output_tokens", ev.estimate_tokens())
                        except Exception:
                            finish_reason = "end_turn"
                            out_tokens    = ev.estimate_tokens()

                    elif etype == "error":
                        try:
                            payload = json.loads(data)
                            err = payload.get("error", {})
                            msg = err.get("message", str(payload))
                        except Exception:
                            msg = data
                        logger.error("{}_ZEN_ERROR:{} {}", tag, rid, msg)
                        for e in ev.close_all():
                            yield e
                        for e in ev.emit_error(append_rid(msg, request_id)):
                            yield e
                # flush remaining raw buf
                if raw_buf:
                    etype, data = self._parse_sse("\n".join(raw_buf))
                    if etype == "response.text.delta" and data:
                        try:
                            text = json.loads(data).get("delta", "")
                        except Exception:
                            text = data
                        for e in ev.ensure_text():
                            yield e
                        yield ev.text_delta(text)

            except Exception as exc:
                logger.error("{}_ZEN_ERROR:{} {}: {}", tag, rid, type(exc).__name__, exc)
                mapped  = map_error(exc, rate_limiter=self._rl)
                base    = error_message(mapped, read_timeout_s=self._cfg.http_read_timeout)
                err_msg = append_rid(base, request_id)
                for e in ev.close_open():
                    yield e
                for e in ev.emit_error(err_msg):
                    yield e
            finally:
                if resp is not None and not resp.is_closed:
                    await resp.aclose()

        for e in ev.close_all():
            yield e
        yield ev.message_delta(
            map_finish_reason(finish_reason),
            out_tokens or ev.estimate_tokens(),
        )
        yield ev.message_stop()
