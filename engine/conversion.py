"""Anthropic ↔ OpenAI message format converters."""

from __future__ import annotations

import json
from typing import Any

from .content import get_attr, get_type


def _schema(tool: Any) -> dict:
    s = getattr(tool, "input_schema", None)
    return s if isinstance(s, dict) else {"type": "object", "properties": {}}


class MessageConverter:
    """Convert Anthropic messages/tools to OpenAI-compatible format."""

    # ── messages ──────────────────────────────────────────────────────────

    @staticmethod
    def to_openai(
        messages: list[Any],
        *,
        include_thinking: bool = True,
        reasoning_content: bool = False,
    ) -> list[dict[str, Any]]:
        out: list[dict] = []
        for msg in messages:
            role    = msg.role if hasattr(msg, "role") else msg.get("role", "user")
            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            if isinstance(content, str):
                out.append({"role": role, "content": content})
            elif isinstance(content, list):
                if role == "assistant":
                    out.extend(MessageConverter._assistant(
                        content,
                        include_thinking=include_thinking,
                        reasoning_content=reasoning_content,
                    ))
                else:
                    out.extend(MessageConverter._user(content))
            else:
                out.append({"role": role, "content": str(content)})
        return out

    @staticmethod
    def _assistant(
        blocks: list[Any],
        *,
        include_thinking: bool,
        reasoning_content: bool,
    ) -> list[dict]:
        text_parts:   list[str] = []
        think_parts:  list[str] = []
        tool_calls:   list[dict] = []

        for blk in blocks:
            bt = get_type(blk)
            if bt == "text":
                text_parts.append(get_attr(blk, "text", ""))
            elif bt == "thinking" and include_thinking:
                th = get_attr(blk, "thinking", "")
                text_parts.append(f"<think>\n{th}\n</think>")
                if reasoning_content:
                    think_parts.append(th)
            elif bt == "tool_use":
                inp = get_attr(blk, "input", {})
                tool_calls.append({
                    "id": get_attr(blk, "id"),
                    "type": "function",
                    "function": {
                        "name": get_attr(blk, "name"),
                        "arguments": json.dumps(inp) if isinstance(inp, dict) else str(inp),
                    },
                })

        text = "\n\n".join(text_parts) or (" " if not tool_calls else "")
        msg: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content and think_parts:
            msg["reasoning_content"] = "\n".join(think_parts)
        return [msg]

    @staticmethod
    def _user(blocks: list[Any]) -> list[dict]:
        out:   list[dict] = []
        texts: list[str]  = []

        def flush() -> None:
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
                texts.clear()

        for blk in blocks:
            bt = get_type(blk)
            if bt == "text":
                texts.append(get_attr(blk, "text", ""))
            elif bt == "tool_result":
                flush()
                rc = get_attr(blk, "content", "")
                if isinstance(rc, list):
                    rc = "\n".join(
                        i.get("text", str(i)) if isinstance(i, dict) else str(i)
                        for i in rc
                    )
                out.append({
                    "role": "tool",
                    "tool_call_id": get_attr(blk, "tool_use_id"),
                    "content": str(rc) if rc else "",
                })
        flush()
        return out

    # ── tools ─────────────────────────────────────────────────────────────

    @staticmethod
    def tools_to_openai(tools: list[Any]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name":        tool.name,
                    "description": tool.description or "",
                    "parameters":  _schema(tool),
                },
            }
            for tool in tools
        ]

    @staticmethod
    def tool_choice_to_openai(tc: Any) -> Any:
        if not isinstance(tc, dict):
            return tc
        t = tc.get("type")
        if t == "tool":
            name = tc.get("name")
            return {"type": "function", "function": {"name": name}} if name else tc
        if t == "any":
            return "required"
        if t in {"auto", "none", "required"}:
            return t
        return tc

    @staticmethod
    def system_to_openai(system: Any) -> dict | None:
        if isinstance(system, str):
            return {"role": "system", "content": system}
        if isinstance(system, list):
            parts = [get_attr(b, "text", "") for b in system if get_type(b) == "text"]
            if parts:
                return {"role": "system", "content": "\n\n".join(parts).strip()}
        return None


# ── convenience function ────────────────────────────────────────────────────

def build_openai_body(
    req: Any,
    *,
    default_max_tokens: int | None = None,
    include_thinking: bool = True,
    reasoning_content: bool = False,
) -> dict[str, Any]:
    """Build an OpenAI-format request body from an Anthropic MessagesRequest."""
    msgs = MessageConverter.to_openai(
        req.messages,
        include_thinking=include_thinking,
        reasoning_content=reasoning_content,
    )
    system = getattr(req, "system", None)
    if system:
        sys_msg = MessageConverter.system_to_openai(system)
        if sys_msg:
            msgs.insert(0, sys_msg)

    body: dict[str, Any] = {"model": req.model, "messages": msgs}

    max_tok = getattr(req, "max_tokens", None) or default_max_tokens
    if max_tok:
        body["max_tokens"] = max_tok

    for field in ("temperature", "top_p"):
        val = getattr(req, field, None)
        if val is not None:
            body[field] = val

    stops = getattr(req, "stop_sequences", None)
    if stops:
        body["stop"] = stops

    tools = getattr(req, "tools", None)
    if tools:
        body["tools"] = MessageConverter.tools_to_openai(tools)
        tc = getattr(req, "tool_choice", None)
        if tc:
            body["tool_choice"] = MessageConverter.tool_choice_to_openai(tc)

    return body
