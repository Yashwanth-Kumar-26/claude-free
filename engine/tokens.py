"""Token estimation for Anthropic-compatible requests."""

from __future__ import annotations

import json
from typing import Any

import tiktoken
from loguru import logger

from .content import get_attr

_ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(
    messages: list[Any],
    system:   str | list | None = None,
    tools:    list | None       = None,
) -> int:
    """Approximate token count for a messages request."""
    total = 0

    if system:
        if isinstance(system, str):
            total += len(_ENC.encode(system))
        elif isinstance(system, list):
            for blk in system:
                txt = get_attr(blk, "text", "")
                if txt:
                    total += len(_ENC.encode(str(txt)))
        total += 4

    for msg in messages:
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        if isinstance(content, str):
            total += len(_ENC.encode(content))
        elif isinstance(content, list):
            for blk in content:
                btype = get_attr(blk, "type")
                if btype == "text":
                    total += len(_ENC.encode(str(get_attr(blk, "text", ""))))
                elif btype == "thinking":
                    total += len(_ENC.encode(str(get_attr(blk, "thinking", ""))))
                elif btype == "tool_use":
                    total += len(_ENC.encode(str(get_attr(blk, "name", ""))))
                    total += len(_ENC.encode(json.dumps(get_attr(blk, "input", {}))))
                    total += 15
                elif btype == "image":
                    src = get_attr(blk, "source")
                    if isinstance(src, dict):
                        data = src.get("data") or src.get("base64") or ""
                        total += max(85, len(data) // 3000) if data else 765
                    else:
                        total += 765
                elif btype == "tool_result":
                    rc = get_attr(blk, "content", "")
                    total += len(_ENC.encode(rc if isinstance(rc, str) else json.dumps(rc)))
                    total += 8
                else:
                    try:
                        total += len(_ENC.encode(json.dumps(blk)))
                    except (TypeError, ValueError):
                        total += len(_ENC.encode(str(blk)))
                    logger.debug("count_tokens: unknown block type {!r}", btype)

    total += len(messages) * 4

    if tools:
        for tool in tools:
            name   = str(getattr(tool, "name", "") or "")
            desc   = str(getattr(tool, "description", "") or "")
            schema = getattr(tool, "input_schema", {}) or {}
            total += len(_ENC.encode(name + desc + json.dumps(schema)))
            total += 5

    return max(1, total)
