"""Request shortcuts — intercept trivial requests locally to save API quota."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator

from loguru import logger

from engine.tokens import count_tokens
from .schemas import MessagesRequest

# ── helpers ──────────────────────────────────────────────────────────────────

def _last_user_text(req: MessagesRequest) -> str:
    for msg in reversed(req.messages):
        if msg.role == "user":
            c = msg.content
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                parts = []
                for blk in c:
                    txt = getattr(blk, "text", None) or (
                        blk.get("text") if isinstance(blk, dict) else None
                    )
                    if txt:
                        parts.append(txt)
                return " ".join(parts)
    return ""


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _simple_stream(model: str, text: str, input_tokens: int = 1) -> Iterator[str]:
    """Emit a minimal complete Anthropic SSE stream for a fixed text reply."""
    msg_id = f"msg_{uuid.uuid4()}"
    yield _sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id, "type": "message", "role": "assistant",
            "content": [], "model": model,
            "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": 1},
        },
    })
    yield _sse("content_block_start", {
        "type": "content_block_start", "index": 0,
        "content_block": {"type": "text", "text": ""},
    })
    yield _sse("ping", {"type": "ping"})
    yield _sse("content_block_delta", {
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "text_delta", "text": text},
    })
    yield _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    output_tokens = count_tokens([{"role": "assistant", "content": text}])
    yield _sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    })
    yield _sse("message_stop", {"type": "message_stop"})


# ── quota probe ───────────────────────────────────────────────────────────────
# Claude Code sends a minimal "Hello" message on startup to probe quota.

_QUOTA_PROBES = frozenset(
    {"hi", "hello", "ping", "test", "yo", "hey", "sup"}
)


def maybe_quota_probe(req: MessagesRequest) -> Iterator[str] | None:
    """Return a shortcut reply for Claude Code startup quota probes."""
    if len(req.messages) > 2:
        return None
    txt = _last_user_text(req).strip().lower()
    if txt in _QUOTA_PROBES or (len(txt) < 10 and not any(c in txt for c in "?!.\n")):
        logger.debug("SHORTCUT: quota probe intercepted")
        return _simple_stream(req.model, "Hello. How can I help?", input_tokens=5)
    return None


# ── title generation ──────────────────────────────────────────────────────────
# Claude Code sends a request to name the conversation after the first message.

_TITLE_PATTERN = re.compile(
    r"(?:generate|create|write|give me|suggest|provide)(?:\s+\w+){0,5}"
    r"\s+(?:a\s+)?(?:short\s+)?(?:title|heading|label)\b|"
    r"(?:name\s+(?:this|the)\s+conversation|conversation\s+name)\b",
    re.IGNORECASE,
)


def maybe_title_gen(req: MessagesRequest) -> Iterator[str] | None:
    txt = _last_user_text(req)
    if _TITLE_PATTERN.search(txt):
        logger.debug("SHORTCUT: title generation intercepted")
        return _simple_stream(req.model, "Conversation", input_tokens=15)
    return None


# ── suggestion mode ───────────────────────────────────────────────────────────
# Claude Code checks if the model supports suggestion mode.

_SUGGESTION_PATTERN = re.compile(
    r"suggestion\s+mode|mode.*suggestion|rewrite.*suggestion|"
    r"can\s+you\s+(?:provide|give|make)\s+(?:a\s+)?suggestion",
    re.IGNORECASE,
)


def maybe_suggestion_mode(req: MessagesRequest) -> Iterator[str] | None:
    txt = _last_user_text(req)
    if _SUGGESTION_PATTERN.search(txt):
        logger.debug("SHORTCUT: suggestion mode intercepted")
        return _simple_stream(req.model, "I can help with suggestions.", input_tokens=10)
    return None


# ── filepath extraction ───────────────────────────────────────────────────────
# Some Claude Code builds probe whether the model can extract file paths.

_FILEPATH_PATTERN = re.compile(
    r"extract(?:ing)?\s+(?:the\s+)?(?:file\s+)?(?:path|paths|filename|filenames)\b",
    re.IGNORECASE,
)


def maybe_filepath_extract(req: MessagesRequest) -> Iterator[str] | None:
    txt = _last_user_text(req)
    if _FILEPATH_PATTERN.search(txt):
        logger.debug("SHORTCUT: filepath extraction intercepted")
        return _simple_stream(req.model, "[]", input_tokens=10)
    return None


# ── prefix detection ──────────────────────────────────────────────────────────
# Claude Code uses a prefix-completion request to detect model type.

_PREFIX_MARKERS = (
    '{"type":"',
    '"human_turn"',
    '"assistant_turn"',
    "Human:",
    "<human>",
)


def maybe_prefix_detect(req: MessagesRequest) -> Iterator[str] | None:
    txt = _last_user_text(req)
    if all(m.lower() not in txt.lower() for m in _PREFIX_MARKERS):
        return None
    logger.debug("SHORTCUT: prefix detection intercepted")
    return _simple_stream(req.model, '{"type":"human_turn"}', input_tokens=5)


# ── composite shortcut handler ────────────────────────────────────────────────

class ShortcutHandler:
    """
    Checks incoming requests against known trivial patterns and returns a fast
    local response when matched, avoiding an upstream round-trip.
    """

    def __init__(self, *, enabled: bool = True) -> None:
        self._checks = (
            [
                maybe_quota_probe,
                maybe_title_gen,
                maybe_suggestion_mode,
                maybe_filepath_extract,
                maybe_prefix_detect,
            ]
            if enabled
            else []
        )

    def intercept(self, req: MessagesRequest) -> Iterator[str] | None:
        for fn in self._checks:
            result = fn(req)
            if result is not None:
                return result
        return None
