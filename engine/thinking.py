"""Streaming <think>…</think> tag parser."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto


class ChunkKind(Enum):
    TEXT     = auto()
    THINKING = auto()


@dataclass
class Chunk:
    kind:    ChunkKind
    content: str


class ThinkParser:
    """
    Feed streaming text through this parser to extract <think>…</think> blocks.

    Any text outside the tags is yielded as TEXT chunks; content inside is
    THINKING chunks.  Handles partial tags split across multiple feed() calls.
    """

    _OPEN  = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._buf:      str  = ""
        self._thinking: bool = False

    @property
    def in_thinking(self) -> bool:
        return self._thinking

    def feed(self, text: str) -> Iterator[Chunk]:
        self._buf += text
        while self._buf:
            prev = len(self._buf)
            chunk = self._step_outside() if not self._thinking else self._step_inside()
            if chunk:
                yield chunk
            elif len(self._buf) == prev:
                break

    def _step_outside(self) -> Chunk | None:
        open_pos  = self._buf.find(self._OPEN)
        close_pos = self._buf.find(self._CLOSE)

        # Orphan close tag
        if close_pos != -1 and (open_pos == -1 or close_pos < open_pos):
            before = self._buf[:close_pos]
            self._buf = self._buf[close_pos + len(self._CLOSE):]
            return Chunk(ChunkKind.TEXT, before) if before else None

        if open_pos == -1:
            # Guard partial tags
            bracket = self._buf.rfind("<")
            if bracket != -1:
                tail = self._buf[bracket:]
                if (
                    len(tail) < len(self._OPEN)  and self._OPEN.startswith(tail)
                ) or (
                    len(tail) < len(self._CLOSE) and self._CLOSE.startswith(tail)
                ):
                    safe, self._buf = self._buf[:bracket], self._buf[bracket:]
                    return Chunk(ChunkKind.TEXT, safe) if safe else None

            out, self._buf = self._buf, ""
            return Chunk(ChunkKind.TEXT, out) if out else None

        before = self._buf[:open_pos]
        self._buf     = self._buf[open_pos + len(self._OPEN):]
        self._thinking = True
        return Chunk(ChunkKind.TEXT, before) if before else None

    def _step_inside(self) -> Chunk | None:
        end = self._buf.find(self._CLOSE)
        if end == -1:
            bracket = self._buf.rfind("<")
            if bracket != -1 and self._CLOSE.startswith(self._buf[bracket:]):
                out, self._buf = self._buf[:bracket], self._buf[bracket:]
                return Chunk(ChunkKind.THINKING, out) if out else None
            out, self._buf = self._buf, ""
            return Chunk(ChunkKind.THINKING, out) if out else None

        content       = self._buf[:end]
        self._buf     = self._buf[end + len(self._CLOSE):]
        self._thinking = False
        return Chunk(ChunkKind.THINKING, content) if content else None

    def flush(self) -> Chunk | None:
        if self._buf:
            kind = ChunkKind.THINKING if self._thinking else ChunkKind.TEXT
            out, self._buf = self._buf, ""
            return Chunk(kind, out)
        return None
