"""OpenRouter adapter — native Anthropic /messages with SSE filtering.

OpenRouter exposes the native Anthropic /v1/messages API endpoint.
This adapter:
  1. Uses MessagesTransport for streaming
  2. Filters SSE events (remaps block indices when thinking is disabled)
  3. Normalizes event-based SSE to line-based format per-stream
  4. Handles extended thinking block filtering

Protocol: Native Anthropic /v1/messages (SSE)
Transport: MessagesTransport (line-based SSE)
Auth: Bearer token (OPENROUTER_API_KEY)
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from backends.base import BackendConfig
from backends.defaults import OPENROUTER_BASE
from backends.transport.messages import ChunkMode, MessagesTransport
from engine.sse import StreamEvent

_ANTHROPIC_VERSION = "2023-06-01"


@dataclass
class _FilterState:
    """Track block index remapping while filtering thinking blocks."""

    next_idx:         int           = 0
    idx_map:          dict[int,int] = field(default_factory=dict)
    dropped:          set[int]      = field(default_factory=set)
    open_types:       dict[int,str] = field(default_factory=dict)
    closed:           set[int]      = field(default_factory=set)
    msg_stopped:      bool          = False


class OpenRouterAdapter(MessagesTransport):
    """OpenRouter — native Anthropic endpoint with per-stream SSE normalisation."""

    stream_mode: ChunkMode = "event"

    def __init__(self, cfg: BackendConfig) -> None:
        super().__init__(cfg, tag="OPENROUTER", default_base=OPENROUTER_BASE)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept":            "text/event-stream",
            "Authorization":     f"Bearer {self._cfg.api_key}",
            "Content-Type":      "application/json",
            "anthropic-version": _ANTHROPIC_VERSION,
        }

    def _new_state(self, request: Any, *, thinking_on: bool) -> Any:
        return _FilterState()

    # ── SSE helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _fmt(ename: str | None, data: str) -> str:
        lines: list[str] = []
        if ename:
            lines.append(f"event: {ename}")
        lines.extend(f"data: {line}" for line in data.splitlines())
        return "\n".join(lines) + "\n\n"

    @staticmethod
    def _parse(evt: str) -> tuple[str | None, str]:
        ename: str | None = None
        dlines: list[str] = []
        for line in evt.strip().splitlines():
            if line.startswith("event:"):
                ename = line[6:].strip()
            elif line.startswith("data:"):
                dlines.append(line[5:].lstrip())
        return ename, "\n".join(dlines)

    @staticmethod
    def _is_done(ename: str | None, data: str) -> bool:
        return (ename is None or ename in {"data", "done"}) and data.strip().upper() == "[DONE]"

    @staticmethod
    def _should_drop(btype: Any, *, thinking_on: bool) -> bool:
        if not isinstance(btype, str):
            return False
        if btype.startswith("redacted_thinking"):
            return True
        return (not thinking_on) and "thinking" in btype

    def _remap(self, payload: dict, state: _FilterState, *, create: bool) -> int | None:
        up = payload.get("index")
        if not isinstance(up, int):
            return None
        if up in state.dropped:
            return None
        mapped = state.idx_map.get(up)
        if mapped is None and create:
            mapped = state.next_idx
            state.idx_map[up] = mapped
            state.next_idx   += 1
        return mapped

    def _close_open_before(self, state: _FilterState, skip: int) -> str:
        evts: list[str] = []
        for oi in list(state.open_types):
            if oi == skip:
                continue
            mi = state.idx_map.get(oi)
            if mi is None:
                continue
            evts.append(self._fmt("content_block_stop",
                                  json.dumps({"type": "content_block_stop", "index": mi})))
            state.closed.add(oi)
            state.open_types.pop(oi, None)
        return "".join(evts)

    def _transform_payload(self, evt: str, state: _FilterState, *, thinking_on: bool) -> str | None:
        ename, data = self._parse(evt)
        if not ename or not data:
            return evt
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return evt

        if ename == "content_block_start":
            block = payload.get("content_block")
            if not isinstance(block, dict):
                return evt
            btype = block.get("type")
            up_idx = payload.get("index")
            if self._should_drop(btype, thinking_on=thinking_on):
                if isinstance(up_idx, int):
                    state.dropped.add(up_idx)
                return None
            mapped = self._remap(payload, state, create=True)
            if mapped is not None:
                payload["index"] = mapped
                if isinstance(up_idx, int) and isinstance(btype, str):
                    prefix = self._close_open_before(state, up_idx)
                    state.open_types[up_idx] = btype
                    return prefix + self._fmt(ename, json.dumps(payload))
                return self._fmt(ename, json.dumps(payload))
            return None if not thinking_on else evt

        if ename == "content_block_delta":
            delta = payload.get("delta")
            if not isinstance(delta, dict):
                return evt
            if self._should_drop(delta.get("type"), thinking_on=thinking_on):
                return None
            mapped = self._remap(payload, state, create=False)
            if mapped is not None:
                payload["index"] = mapped
                return self._fmt(ename, json.dumps(payload))
            if payload.get("index") in state.dropped:
                return None
            return None if not thinking_on else evt

        if ename == "content_block_stop":
            up_idx = payload.get("index")
            if isinstance(up_idx, int) and up_idx in state.closed:
                state.closed.discard(up_idx)
                return None
            mapped = self._remap(payload, state, create=False)
            if mapped is not None:
                payload["index"] = mapped
                if isinstance(up_idx, int):
                    state.open_types.pop(up_idx, None)
                return self._fmt(ename, json.dumps(payload))
            if payload.get("index") in state.dropped:
                return None

        return evt

    def _transform_event(self, evt: str, state: Any, *, thinking_on: bool) -> str | None:
        if not isinstance(state, _FilterState):
            return evt
        ename, data = self._parse(evt)
        if state.msg_stopped or self._is_done(ename, data):
            return None
        if ename == "message_stop":
            state.msg_stopped = True
        return self._transform_payload(evt, state, thinking_on=thinking_on)

    def _emit_error(self, *, request: Any, input_tokens: int, err_msg: str, sent: bool) -> Iterator[str]:
        ev = StreamEvent(f"msg_{uuid.uuid4()}", request.model, input_tokens)
        if not sent:
            yield ev.message_start()
        yield from ev.emit_error(err_msg)
        yield ev.message_delta("end_turn", 1)
        yield ev.message_stop()
