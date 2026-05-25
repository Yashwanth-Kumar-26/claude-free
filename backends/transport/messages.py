

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx
from loguru import logger

from backends.base import BackendAdapter, BackendConfig
from backends.error_mapping import map_error
from backends.rate_limit import GlobalRateLimiter
from engine import append_rid, error_message

_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 81920
ChunkMode = Literal["line", "event"]


class MessagesTransport(BackendAdapter):
    """
    Proxy connector for providers that expose a native Anthropic /messages endpoint.

    SSE events are forwarded verbatim (line or grouped-event mode), with optional
    per-stream transformation via _transform_event().
    """

    stream_mode: ChunkMode = "line"

    def __init__(
        self,
        cfg: BackendConfig,
        *,
        tag: str,
        default_base: str,
    ) -> None:
        super().__init__(cfg)
        self._tag = tag
        self._base_url = (cfg.base_url or default_base).rstrip("/")
        self._rl = GlobalRateLimiter.scoped(
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

    # ── override points ──────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _build_body(self, request: Any) -> dict:
        thinking_on = self._thinking_enabled(request)
        body = request.model_dump(exclude_none=True)
        for key in ("extra_body", "original_model", "resolved_provider_model"):
            body.pop(key, None)
        if "thinking" in body:
            cfg = body.pop("thinking")
            if thinking_on and isinstance(cfg, dict):
                payload: dict = {"type": "enabled"}
                if isinstance(cfg.get("budget_tokens"), int):
                    payload["budget_tokens"] = cfg["budget_tokens"]
                body["thinking"] = payload
        body.setdefault("max_tokens", _DEFAULT_MAX_TOKENS)
        return body

    def _new_state(self, request: Any, *, thinking_on: bool) -> Any:
        return None

    def _transform_event(
        self,
        event: str,
        state: Any,
        *,
        thinking_on: bool,
    ) -> str | None:
        return event

    def _format_error(self, base: str, rid: str | None) -> str:
        return append_rid(base, rid)

    def _emit_error(
        self,
        *,
        request: Any,
        input_tokens: int,
        err_msg: str,
        sent: bool,
    ):
        evt = {"type": "error", "error": {"type": "api_error", "message": err_msg}}
        yield f"event: error\ndata: {json.dumps(evt)}\n\n"

    # ── streaming ────────────────────────────────────────────────────────

    async def _send(self, body: dict) -> httpx.Response:
        req = self._http.build_request(
            "POST", "/messages", json=body, headers=self._headers()
        )
        return await self._http.send(req, stream=True)

    async def _raise_status(self, resp: httpx.Response, *, tag: str) -> None:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            body_bytes = await resp.aread() if hasattr(resp, "aread") else b""
            if body_bytes:
                logger.error(
                    "{} HTTP {}: {}",
                    tag,
                    resp.status_code,
                    body_bytes.decode("utf-8", errors="replace"),
                )
            raise

    async def _iter_lines(self, resp: httpx.Response) -> AsyncIterator[str]:
        async for line in resp.aiter_lines():
            yield f"{line}\n" if line else "\n"

    async def _iter_events(self, resp: httpx.Response) -> AsyncIterator[str]:
        buf: list[str] = []
        async for line in resp.aiter_lines():
            if line:
                buf.append(line)
            elif buf:
                # Join buffered lines and yield event (faster than clear())
                yield "\n".join(buf) + "\n\n"
                buf = []  # Faster than buf.clear()
        if buf:
            yield "\n".join(buf) + "\n\n"

    async def _iter_chunks(
        self,
        resp: httpx.Response,
        *,
        state: Any,
        thinking_on: bool,
    ) -> AsyncIterator[str]:
        if self.stream_mode == "line":
            async for chunk in self._iter_lines(resp):
                yield chunk
            return
        async for evt in self._iter_events(resp):
            out = self._transform_event(evt, state, thinking_on=thinking_on)
            if out is not None:
                yield out

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        tag = self._tag
        rid = f" rid={request_id}" if request_id else ""
        thinking_on = self._thinking_enabled(request)
        body = self._build_body(request)

        # Log at debug level to reduce I/O overhead in hot path
        logger.debug(
            "{}_STREAM:{} native Anthropic model={} msgs={} tools={}",
            tag,
            rid,
            body.get("model"),
            len(body.get("messages", [])),
            len(body.get("tools", [])),
        )

        resp: httpx.Response | None = None
        sent = False
        state = self._new_state(request, thinking_on=thinking_on)

        async with self._rl.concurrency_slot():
            try:
                resp = await self._rl.execute_with_retry(self._send, body)
                if resp.status_code != 200:
                    await self._raise_status(resp, tag=tag)

                async for chunk in self._iter_chunks(
                    resp, state=state, thinking_on=thinking_on
                ):
                    sent = True
                    yield chunk

            except Exception as exc:
                logger.error("{}_ERROR:{} {}: {}", tag, rid, type(exc).__name__, exc)
                mapped = map_error(exc, rate_limiter=self._rl)
                base = error_message(mapped, read_timeout_s=self._cfg.http_read_timeout)
                msg = self._format_error(base, request_id)

                if resp is not None and not resp.is_closed:
                    await resp.aclose()

                for evt in self._emit_error(
                    request=request,
                    input_tokens=input_tokens,
                    err_msg=msg,
                    sent=sent,
                ):
                    yield evt
                return
            finally:
                if resp is not None and not resp.is_closed:
                    await resp.aclose()
