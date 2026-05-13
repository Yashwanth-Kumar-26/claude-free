"""User-facing error message helpers."""

from __future__ import annotations

import httpx
import openai


def error_message(exc: Exception, *, read_timeout_s: float | None = None) -> str:
    """Return a readable non-empty message for the user."""
    msg = str(exc).strip()
    if msg:
        return msg

    if isinstance(exc, httpx.ReadTimeout):
        return (
            f"Backend request timed out after {read_timeout_s:g}s."
            if read_timeout_s
            else "Backend request timed out."
        )
    if isinstance(exc, httpx.ConnectTimeout):
        return "Could not connect to backend."
    if isinstance(exc, TimeoutError):
        return (
            f"Request timed out after {read_timeout_s:g}s."
            if read_timeout_s
            else "Request timed out."
        )

    name   = type(exc).__name__
    status = getattr(exc, "status_code", None)

    if isinstance(exc, openai.RateLimitError)     or name == "RateLimitError":
        return "Backend rate limit reached. Please retry shortly."
    if isinstance(exc, openai.AuthenticationError) or name == "AuthenticationError":
        return "Backend authentication failed. Check your API key."
    if isinstance(exc, openai.BadRequestError)     or name == "InvalidRequestError":
        return "Invalid request sent to backend."
    if name == "OverloadedError":
        return "Backend is overloaded. Please retry."
    if name == "APIError":
        if status in (502, 503, 504):
            return "Backend temporarily unavailable. Please retry."
        return "Backend API request failed."
    if name.endswith("BackendError") or name in ("ProviderError", "BackendError"):
        return "Backend request failed."

    return "Backend request failed unexpectedly."


def append_rid(msg: str, request_id: str | None) -> str:
    base = msg.strip() or "Backend request failed unexpectedly."
    return f"{base} (rid={request_id})" if request_id else base
