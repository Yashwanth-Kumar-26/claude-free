"""SSE event builder — emits Anthropic-format streaming events."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field

from loguru import logger

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENC = None

# ── finish-reason mapping ────────────────────────────────────────────────────

_FINISH_MAP = {
    "stop":           "end_turn",
    "length":         "max_tokens",
    "tool_calls":     "tool_use",
    "content_filter": "end_turn",
}


def map_finish_reason(reason: str | None) -> str:
    return _FINISH_MAP.get(reason or "", "end_turn") if reason else "end_turn"


# ── tool call state ──────────────────────────────────────────────────────────

@dataclass
class ToolState:
    block_index:       int
    tool_id:           str
    name:              str
    chunks:            list[str] = field(default_factory=list)
    started:           bool      = False
    task_buf:          str       = ""
    task_emitted:      bool      = False


# ── block manager ────────────────────────────────────────────────────────────

@dataclass
class BlockManager:
    """Track active content block indices during a stream."""

    _next:          int = 0
    thinking_idx:   int = -1
    text_idx:       int = -1
    thinking_open:  bool = False
    text_open:      bool = False
    tools:          dict[int, ToolState] = field(default_factory=dict)

    def alloc(self) -> int:
        idx = self._next
        self._next += 1
        return idx

    def register_tool_name(self, idx: int, name: str) -> None:
        if idx not in self.tools:
            self.tools[idx] = ToolState(block_index=-1, tool_id="", name=name)
            return
        st = self.tools[idx]
        prev = st.name
        if not prev or name.startswith(prev):
            st.name = name
        elif not prev.startswith(name):
            st.name = prev + name

    def buffer_task_args(self, idx: int, args: str) -> dict | None:
        st = self.tools.get(idx)
        if not st or st.task_emitted:
            return None
        st.task_buf += args
        try:
            parsed = json.loads(st.task_buf)
        except Exception:
            return None
        if parsed.get("run_in_background") is not False:
            parsed["run_in_background"] = False
        st.task_emitted = True
        st.task_buf = ""
        return parsed

    def flush_task_bufs(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for idx, st in list(self.tools.items()):
            if not st.task_buf or st.task_emitted:
                continue
            result = "{}"
            try:
                parsed = json.loads(st.task_buf)
                if parsed.get("run_in_background") is not False:
                    parsed["run_in_background"] = False
                result = json.dumps(parsed)
            except Exception as exc:
                logger.warning("Task args flush invalid JSON idx={} err={}", idx, exc)
            st.task_emitted = True
            st.task_buf = ""
            out.append((idx, result))
        return out


# ── SSE event stream ─────────────────────────────────────────────────────────

class StreamEvent:
    """
    Stateful builder for an Anthropic SSE message stream.

    Usage::

        ev = StreamEvent(msg_id, model, input_tokens)
        yield ev.message_start()
        for text in ...:
            for e in ev.ensure_text(): yield e
            yield ev.text_delta(text)
        yield from ev.close_all()
        yield ev.message_delta(stop_reason, output_tokens)
        yield ev.message_stop()
    """

    def __init__(self, msg_id: str, model: str, input_tokens: int = 0) -> None:
        self.msg_id       = msg_id
        self.model        = model
        self.input_tokens = input_tokens
        self.blocks       = BlockManager()
        self._texts:      list[str] = []
        self._reasoning:  list[str] = []

    # ── internal ──────────────────────────────────────────────────────────

    def _evt(self, kind: str, data: dict) -> str:
        line = f"event: {kind}\ndata: {json.dumps(data)}\n\n"
        logger.debug("SSE {} | {}", kind, line.strip())
        return line

    def _block_start(self, idx: int, btype: str, **kw: object) -> str:
        cb: dict = {"type": btype}
        if btype == "thinking":
            cb["thinking"] = kw.get("thinking", "")
        elif btype == "text":
            cb["text"] = kw.get("text", "")
        elif btype == "tool_use":
            cb.update(id=kw.get("id", ""), name=kw.get("name", ""), input={})
        return self._evt("content_block_start",
                         {"type": "content_block_start", "index": idx, "content_block": cb})

    def _block_delta(self, idx: int, dtype: str, payload: str) -> str:
        delta: dict = {"type": dtype}
        if dtype == "thinking_delta":
            delta["thinking"] = payload
        elif dtype == "text_delta":
            delta["text"] = payload
        elif dtype == "input_json_delta":
            delta["partial_json"] = payload
        return self._evt("content_block_delta",
                         {"type": "content_block_delta", "index": idx, "delta": delta})

    def _block_stop(self, idx: int) -> str:
        return self._evt("content_block_stop",
                         {"type": "content_block_stop", "index": idx})

    # ── public API ────────────────────────────────────────────────────────

    def message_start(self) -> str:
        return self._evt("message_start", {
            "type": "message_start",
            "message": {
                "id": self.msg_id, "type": "message", "role": "assistant",
                "content": [], "model": self.model,
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": self.input_tokens, "output_tokens": 1},
            },
        })

    def message_delta(self, stop_reason: str, output_tokens: int) -> str:
        return self._evt("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"input_tokens": self.input_tokens, "output_tokens": output_tokens},
        })

    def message_stop(self) -> str:
        return self._evt("message_stop", {"type": "message_stop"})

    # thinking
    def ensure_thinking(self) -> Iterator[str]:
        if self.blocks.text_open:
            self.blocks.text_open = False
            yield self._block_stop(self.blocks.text_idx)
        if not self.blocks.thinking_open:
            self.blocks.thinking_idx = self.blocks.alloc()
            self.blocks.thinking_open = True
            yield self._block_start(self.blocks.thinking_idx, "thinking")

    def thinking_delta(self, content: str) -> str:
        self._reasoning.append(content)
        return self._block_delta(self.blocks.thinking_idx, "thinking_delta", content)

    # text
    def ensure_text(self) -> Iterator[str]:
        if self.blocks.thinking_open:
            self.blocks.thinking_open = False
            yield self._block_stop(self.blocks.thinking_idx)
        if not self.blocks.text_open:
            self.blocks.text_idx = self.blocks.alloc()
            self.blocks.text_open = True
            yield self._block_start(self.blocks.text_idx, "text")

    def text_delta(self, content: str) -> str:
        self._texts.append(content)
        return self._block_delta(self.blocks.text_idx, "text_delta", content)

    # tool
    def open_tool(self, tool_idx: int, tool_id: str, name: str) -> str:
        blk = self.blocks.alloc()
        if tool_idx in self.blocks.tools:
            st = self.blocks.tools[tool_idx]
            st.block_index = blk
            st.tool_id     = tool_id
            st.started     = True
        else:
            self.blocks.tools[tool_idx] = ToolState(
                block_index=blk, tool_id=tool_id, name=name, started=True)
        return self._block_start(blk, "tool_use", id=tool_id, name=name)

    def tool_delta(self, tool_idx: int, partial: str) -> str:
        st = self.blocks.tools[tool_idx]
        st.chunks.append(partial)
        return self._block_delta(st.block_index, "input_json_delta", partial)

    def close_tool(self, tool_idx: int) -> str:
        return self._block_stop(self.blocks.tools[tool_idx].block_index)

    # close helpers
    def close_open(self) -> Iterator[str]:
        """Close thinking + text blocks (before tool_use)."""
        if self.blocks.thinking_open:
            self.blocks.thinking_open = False
            yield self._block_stop(self.blocks.thinking_idx)
        if self.blocks.text_open:
            self.blocks.text_open = False
            yield self._block_stop(self.blocks.text_idx)

    def close_all(self) -> Iterator[str]:
        """Close every open block (end of stream)."""
        yield from self.close_open()
        for _idx, st in list(self.blocks.tools.items()):
            if st.started:
                yield self._block_stop(st.block_index)

    def emit_error(self, msg: str) -> Iterator[str]:
        idx = self.blocks.alloc()
        yield self._block_start(idx, "text")
        yield self._block_delta(idx, "text_delta", msg)
        yield self._block_stop(idx)

    # token estimation
    def estimate_tokens(self) -> int:
        full_text      = "".join(self._texts)
        full_reasoning = "".join(self._reasoning)
        if _ENC:
            tt = len(_ENC.encode(full_text))
            rt = len(_ENC.encode(full_reasoning))
            tool_t = 0
            n_tools = 0
            for st in self.blocks.tools.values():
                tool_t += len(_ENC.encode(st.name))
                tool_t += len(_ENC.encode("".join(st.chunks))) + 15
                if st.started:
                    n_tools += 1
            blk_count = (
                (1 if full_text else 0)
                + (1 if full_reasoning else 0)
                + n_tools
            )
            return tt + rt + tool_t + blk_count * 4
        tt = len(full_text) // 4
        rt = len(full_reasoning) // 4
        tool_t = sum(1 for st in self.blocks.tools.values() if st.started) * 50
        return tt + rt + tool_t
