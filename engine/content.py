"""Attribute helpers for Anthropic content blocks (dict or Pydantic)."""

from typing import Any


def get_attr(block: Any, key: str, default: Any = None) -> Any:
    """Fetch a field from a dict-like block or Pydantic object."""
    if hasattr(block, key):
        return getattr(block, key)
    if isinstance(block, dict):
        return block.get(key, default)
    return default


def get_type(block: Any) -> str | None:
    """Return the 'type' field of a content block."""
    return get_attr(block, "type")


def extract_text(content: Any) -> str:
    """Concatenate all text fields from a content block or string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            txt = get_attr(block, "text", "")
            if isinstance(txt, str) and txt:
                parts.append(txt)
        return "".join(parts)
    return ""
