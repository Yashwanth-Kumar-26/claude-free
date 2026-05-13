"""BackendAdapter base class and BackendConfig.

This module defines the interface that all backend adapters must implement.
Adapters are responsible for:
  1. Converting Anthropic message format to provider format
  2. Streaming responses from external LLM APIs
  3. Handling errors and retries
  4. Managing rate limiting and concurrency
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel


class BackendConfig(BaseModel):
    """Configuration shared by all backend adapters.

    Attributes:
        api_key: Authentication key for the backend provider
        base_url: Optional override for provider's API base URL
        rate_limit: Max requests per rate_window (None = unlimited)
        rate_window: Sliding window in seconds for rate limiting (default: 60s)
        max_concurrency: Max concurrent requests to this backend (default: 5)
        http_read_timeout: HTTP read timeout in seconds (default: 120s)
        http_write_timeout: HTTP write timeout in seconds (default: 10s)
        http_connect_timeout: HTTP connect timeout in seconds (default: 5s)
        enable_thinking: Forward extended thinking blocks to client (default: True)
        proxy: Optional HTTP proxy URL
    """

    api_key:            str
    base_url:           str | None = None
    rate_limit:         int | None = None
    rate_window:        int        = 60
    max_concurrency:    int        = 5
    http_read_timeout:  float      = 120.0
    http_write_timeout: float      = 10.0
    http_connect_timeout: float    = 5.0
    enable_thinking:    bool       = True
    proxy:              str        = ""


class BackendAdapter(ABC):
    """Abstract base for all LLM backend adapters.

    Adapters convert Anthropic message format to provider-specific formats
    and stream responses back as Anthropic-compatible SSE.

    Subclasses must implement:
        stream_response(request, input_tokens, *, request_id) → AsyncIterator[str]
            Stream response from provider as Anthropic SSE events
        cleanup() → None
            Teardown any resources (connections, etc.)

    Example implementations:
        - OpenRouterAdapter: native Anthropic /messages endpoint
        - NvidiaAdapter: OpenAI-compatible /chat/completions
        - DynamicBackendAdapter: factory-created multi-format adapters
    """

    def __init__(self, cfg: BackendConfig) -> None:
        self._cfg = cfg

    # ── helpers ──────────────────────────────────────────────────────────

    def _thinking_enabled(self, request: Any) -> bool:
        """Return True when thinking blocks should be forwarded to the client."""
        thinking = getattr(request, "thinking", None)
        enabled  = True
        if thinking is not None:
            ttype = (
                thinking.get("type")
                if isinstance(thinking, dict)
                else getattr(thinking, "type", None)
            )
            if ttype == "disabled":
                enabled = False
            flag = (
                thinking.get("enabled")
                if isinstance(thinking, dict)
                else getattr(thinking, "enabled", None)
            )
            if flag is not None:
                enabled = bool(flag)
        return self._cfg.enable_thinking and enabled

    # ── abstract API ─────────────────────────────────────────────────────

    @abstractmethod
    async def cleanup(self) -> None:
        """Release HTTP client or other long-lived resources."""

    @abstractmethod
    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield Anthropic SSE events as strings."""
        if False:
            yield ""  # keeps type-checkers happy for async generator
