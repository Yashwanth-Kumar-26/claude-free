"""OpenAI /chat/completions transport (NIM, OpenCode Go).

This transport layer handles providers that expose an OpenAI-compatible
/v1/chat/completions endpoint with streaming support.

Features:
  1. OpenAI SDK integration via AsyncOpenAI client
  2. JSON streaming response parsing
  3. Extended thinking block extraction & forwarding
  4. Tool call parsing (function calls)
  5. Finish reason mapping (stop_reason → Anthropic format)
  6. Retry logic via _retry_body() for transient errors
  7. Error mapping to BackendError subclasses

Used by:
  - NvidiaAdapter: NVIDIA NIM via integrate.api.nvidia.com

Protocol Details:
  - OpenAI-compatible /v1/chat/completions
  - JSON streaming response
  - Supports extended thinking (reasoning_effort, reasoning_budget)
  - Tool/function call support via tools parameter
  - Finish reasons: stop, length, tool_calls, content_filter
"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx
from loguru import logger
from openai import AsyncOpenAI

from backends.base import BackendAdapter, BackendConfig
from backends.error_mapping import map_error
from backends.rate_limit import GlobalRateLimiter
from engine import (
    ChunkKind,
    StreamEvent,
    ThinkParser,
    ToolParser,
    append_rid,
    error_message,
    map_finish_reason,
)


class ChatCompletionsTransport(BackendAdapter):
    """
    Base adapter for OpenAI /chat/completions endpoints.

    Subclasses must implement _build_body(request) → dict.
    Optionally override _retry_body(error, body) → dict | None.
    """

    def __init__(
        self,
        cfg:           BackendConfig,
        *,
        tag:           str,
        base_url:      str,
        api_key:       str,
    ) -> None:
        super().__init__(cfg)
        self._tag      = tag
        self._base_url = base_url.rstrip("/")
        self._rl       = GlobalRateLimiter.scoped(
            tag.lower(),
            rate_limit=cfg.rate_limit or 40,
            rate_window=cfg.rate_window,
            max_concurrency=cfg.max_concurrency,
        )
        http_client = None
        if cfg.proxy:
            http_client = httpx.AsyncClient(
                proxy=cfg.proxy,
                timeout=httpx.Timeout(
                    cfg.http_read_timeout,
                    connect=cfg.http_connect_timeout,
                    write=cfg.http_write_timeout,
                ),
            )
        self._client = AsyncOpenAI(
            api_key=api_key or "placeholder",
            base_url=self._base_url,
            max_retries=0,
            timeout=httpx.Timeout(
                cfg.http_read_timeout,
                connect=cfg.http_connect_timeout,
                write=cfg.http_write_timeout,
            ),
            http_client=http_client,
        )

    async def cleanup(self) -> None:
        await self._client.aclose()

    @abstractmethod
    def _build_body(self, request: Any) -> dict: ...

    def _retry_body(self, error: Exception, body: dict) -> dict | None:
        return None

    async def _create_stream(self, body: dict) -> tuple[Any, dict]:
        try:
            stream = await self._rl.execute_with_retry(
                self._client.chat.completions.create, **body, stream=True
            )
            return stream, body
        except Exception as err:
            retry = self._retry_body(err, body)
            if retry is None:
                raise
            stream = await self._rl.execute_with_retry(
                self._client.chat.completions.create, **retry, stream=True
            )
            return stream, retry

    def _process_tool_call(self, tc: dict, ev: StreamEvent) -> AsyncIterator[str]:
        raise NotImplementedError  # sync generator — see _yield_tool

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        with logger.contextualize(request_id=request_id):
            async for chunk in self._stream_impl(request, input_tokens, request_id):
                yield chunk

    async def _stream_impl(
        self,
        request:      Any,
        input_tokens: int,
        request_id:   str | None,
    ) -> AsyncIterator[str]:
        rid     = f" rid={request_id}" if request_id else ""
        msg_id  = f"msg_{uuid.uuid4()}"
        ev      = StreamEvent(msg_id, request.model, input_tokens)
        body    = self._build_body(request)

        logger.info(
            "{}_STREAM:{} model={} msgs={} tools={}",
            self._tag, rid,
            body.get("model"),
            len(body.get("messages", [])),
            len(body.get("tools", [])),
        )

        yield ev.message_start()

        think_parser = ThinkParser()
        tool_parser  = ToolParser()
        thinking_on  = self._thinking_enabled(request)
        finish_reason: str | None = None
        usage_info:    Any        = None
        had_error                 = False
        err_msg                   = ""

        async with self._rl.concurrency_slot():
            try:
                stream, body = await self._create_stream(body)
                async for chunk in stream:
                    if getattr(chunk, "usage", None):
                        usage_info = chunk.usage

                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta  = choice.delta
                    if delta is None:
                        continue

                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                    # reasoning_content (extended OpenAI format)
                    reasoning = getattr(delta, "reasoning_content", None)
                    if thinking_on and reasoning:
                        for e in ev.ensure_thinking():
                            yield e
                        yield ev.thinking_delta(reasoning)

                    # text content (possibly containing <think> tags)
                    if delta.content:
                        for part in think_parser.feed(delta.content):
                            if part.kind == ChunkKind.THINKING:
                                if not thinking_on:
                                    continue
                                for e in ev.ensure_thinking():
                                    yield e
                                yield ev.thinking_delta(part.content)
                            else:
                                safe, detected = tool_parser.feed(part.content)
                                if safe:
                                    for e in ev.ensure_text():
                                        yield e
                                    yield ev.text_delta(safe)
                                for tu in detected:
                                    for e in ev.close_open():
                                        yield e
                                    idx = ev.blocks.alloc()
                                    if tu.get("name") == "Task" and isinstance(tu.get("input"), dict):
                                        tu["input"]["run_in_background"] = False
                                    yield ev._block_start(idx, "tool_use",
                                                          id=tu["id"], name=tu["name"])
                                    yield ev._block_delta(idx, "input_json_delta",
                                                          json.dumps(tu["input"]))
                                    yield ev._block_stop(idx)

                    # native tool calls
                    if delta.tool_calls:
                        for e in ev.close_open():
                            yield e
                        for tc in delta.tool_calls:
                            tc_dict = {
                                "index": tc.index,
                                "id":    tc.id,
                                "function": {
                                    "name":      tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for e in self._yield_tool(tc_dict, ev):
                                yield e

            except (asyncio.CancelledError, GeneratorExit):
                raise
            except Exception as exc:
                logger.error("{}_ERROR:{} {}: {}", self._tag, rid, type(exc).__name__, exc)
                mapped  = map_error(exc, rate_limiter=self._rl)
                had_error = True
                base     = error_message(mapped, read_timeout_s=self._cfg.http_read_timeout)
                err_msg  = append_rid(base, request_id)
                for e in ev.close_open():
                    yield e
                for e in ev.emit_error(err_msg):
                    yield e

        # flush
        remaining = think_parser.flush()
        if remaining:
            if remaining.kind == ChunkKind.THINKING and thinking_on:
                for e in ev.ensure_thinking():
                    yield e
                yield ev.thinking_delta(remaining.content)
            elif remaining.kind == ChunkKind.TEXT and remaining.content:
                for e in ev.ensure_text():
                    yield e
                yield ev.text_delta(remaining.content)

        for tu in tool_parser.flush():
            for e in ev.close_open():
                yield e
            idx = ev.blocks.alloc()
            if tu.get("name") == "Task" and isinstance(tu.get("input"), dict):
                tu["input"]["run_in_background"] = False
            yield ev._block_start(idx, "tool_use", id=tu["id"], name=tu["name"])
            yield ev._block_delta(idx, "input_json_delta", json.dumps(tu["input"]))
            yield ev._block_stop(idx)

        if not had_error and ev.blocks.text_idx == -1 and not ev.blocks.tools:
            for e in ev.ensure_text():
                yield e
            yield ev.text_delta(" ")

        # flush buffered Task args
        for tool_idx, out in ev.blocks.flush_task_bufs():
            yield ev.tool_delta(tool_idx, out)

        for e in ev.close_all():
            yield e

        out_tokens = (
            usage_info.completion_tokens
            if usage_info and hasattr(usage_info, "completion_tokens")
            else ev.estimate_tokens()
        )
        yield ev.message_delta(map_finish_reason(finish_reason), out_tokens)
        yield ev.message_stop()

    # ── tool streaming helper ──────────────────────────────────────────────

    def _yield_tool(self, tc: dict, ev: StreamEvent):
        idx     = tc.get("index", 0)
        if idx < 0:
            idx = len(ev.blocks.tools)
        fn      = tc.get("function", {})
        name    = fn.get("name")
        args    = fn.get("arguments", "")

        if name is not None:
            ev.blocks.register_tool_name(idx, name)

        st = ev.blocks.tools.get(idx)
        if (st is None or not st.started) and (name or tc.get("id")):
                tool_id = tc.get("id") or f"tool_{uuid.uuid4()}"
                yield ev.open_tool(idx, tool_id, name or "tool_call")

        if args:
            st = ev.blocks.tools.get(idx)
            if st is None or not st.started:
                tool_id = tc.get("id") or f"tool_{uuid.uuid4()}"
                yield ev.open_tool(idx, tool_id, (st.name if st else None) or "tool_call")
                st = ev.blocks.tools.get(idx)

            cname = st.name if st else ""
            if cname == "Task":
                parsed = ev.blocks.buffer_task_args(idx, args)
                if parsed is not None:
                    yield ev.tool_delta(idx, json.dumps(parsed))
                return
            yield ev.tool_delta(idx, args)
