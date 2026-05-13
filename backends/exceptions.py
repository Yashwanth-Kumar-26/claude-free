"""Unified exception hierarchy for backend adapters."""

from __future__ import annotations

from typing import Any


class BackendError(Exception):
    """Base class for all backend-level errors."""

    def __init__(
        self,
        message:    str,
        status_code: int = 500,
        error_type:  str = "api_error",
        raw:         Any = None,
    ) -> None:
        super().__init__(message)
        self.message     = message
        self.status_code = status_code
        self.error_type  = error_type
        self.raw         = raw

    def to_anthropic(self) -> dict:
        return {
            "type": "error",
            "error": {"type": self.error_type, "message": self.message},
        }


class AuthError(BackendError):
    def __init__(self, msg: str, raw: Any = None) -> None:
        super().__init__(msg, 401, "authentication_error", raw)


class BadRequestError(BackendError):
    def __init__(self, msg: str, raw: Any = None) -> None:
        super().__init__(msg, 400, "invalid_request_error", raw)


class RateLimitError(BackendError):
    def __init__(self, msg: str, raw: Any = None) -> None:
        super().__init__(msg, 429, "rate_limit_error", raw)


class OverloadedError(BackendError):
    def __init__(self, msg: str, raw: Any = None) -> None:
        super().__init__(msg, 529, "overloaded_error", raw)


class UnknownBackendError(ValueError):
    """Raised when a backend_id is not registered in the hub."""
