# ---
# Map upstream HTTP / SDK exceptions to BackendError subclasses.
# ---
# HTTP 429          → RateLimitError    (triggers GlobalRateLimiter backoff)
# HTTP 401          → AuthError
# HTTP 503/529      → OverloadedError
# httpx errors      → BackendError
# Other             → pass through unchanged
# ---
# Usage: backend_error = map_error(exc, rate_limiter=limiter)

from __future__ import annotations

import httpx
import openai

from .exceptions import AuthError, BackendError, OverloadedError, RateLimitError
from .rate_limit import GlobalRateLimiter


def map_error(
    exc: Exception,
    *,
    rate_limiter: GlobalRateLimiter | None = None,
) -> BackendError | Exception:
    """Return a BackendError translation of exc, or exc itself if no mapping exists."""
    if isinstance(exc, BackendError):
        return exc

    status = getattr(exc, "status_code", None)

    if isinstance(exc, openai.RateLimitError) or status == 429:
        if rate_limiter:
            rate_limiter.signal_upstream_429()
        return RateLimitError(str(exc) or "Rate limit exceeded.", raw=exc)

    if isinstance(exc, openai.AuthenticationError) or status == 401:
        return AuthError(str(exc) or "Authentication failed.", raw=exc)

    if status in (529, 503):
        return OverloadedError(str(exc) or "Backend overloaded.", raw=exc)

    if isinstance(exc, httpx.HTTPStatusError):
        return BackendError(
            str(exc) or "HTTP error from backend.",
            status_code=exc.response.status_code,
            raw=exc,
        )

    return exc
