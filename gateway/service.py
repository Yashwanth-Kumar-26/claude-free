"""GatewayService — orchestrates shortcuts, selection, and backend streaming."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from loguru import logger

from backends.hub import BackendHub
from engine.tokens import count_tokens
from settings.env import Settings

from .schemas import MessagesRequest, TokenCountRequest, TokenCountResponse
from .selector import ModelSelector
from .shortcuts import ShortcutHandler
from .stats import get_stats


class GatewayService:
    """
    Central service that processes every Claude API request.

    Flow:
      1. ShortcutHandler → local fast reply if trivial
      2. ModelSelector   → resolve backend + model
      3. BackendHub.get  → fetch adapter
      4. adapter.stream_response → stream Anthropic SSE
    """

    def __init__(
        self,
        settings:  Settings,
        hub:       BackendHub,
        selector:  ModelSelector,
        shortcuts: ShortcutHandler,
    ) -> None:
        self._hub       = hub
        self._selector  = selector
        self._shortcuts = shortcuts

    async def stream(
        self,
        req:        MessagesRequest,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        # 1. shortcut?
        shortcut = self._shortcuts.intercept(req)
        if shortcut is not None:
            for chunk in shortcut:
                yield chunk
            return

        # 2. route
        routed = self._selector.route_messages(req)
        sel    = routed.selection
        backend = self._hub.get(sel.backend_id)

        # 3. token count for input
        try:
            input_tokens = count_tokens(
                req.messages,
                system=req.system,
                tools=req.tools,
            )
        except Exception as exc:
            logger.warning("Token count failed: {}", exc)
            input_tokens = 0

        logger.info(
            "GATEWAY: stream backend={} model={} input_tokens={}",
            sel.backend_id, sel.backend_model, input_tokens,
        )

        # 4. stream
        t0 = time.monotonic()
        output_tokens = 0
        had_error = False
        try:
            async for chunk in backend.stream_response(
                routed.request,
                input_tokens,
                request_id=request_id,
            ):
                # Simple heuristic to extract output token count from stream (usually in message_delta)
                if "output_tokens" in chunk and '"type": "message_delta"' in chunk:
                    try:
                        parts = chunk.split("data: ")
                        if len(parts) > 1:
                            data = json.loads(parts[1])
                            output_tokens = data.get("usage", {}).get("output_tokens", 0)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.debug("Failed to parse output tokens: {}", e)
                yield chunk
        except Exception:
            had_error = True
            raise
        finally:
            duration_ms = (time.monotonic() - t0) * 1000
            get_stats().record_request(
                sel.backend_id,
                input_tokens,
                output_tokens or 1,
                duration_ms,
                is_error=had_error
            )

    def count_tokens(self, req: TokenCountRequest) -> TokenCountResponse:
        n = count_tokens(
            req.messages,
            system=req.system,
            tools=req.tools,
        )
        return TokenCountResponse(input_tokens=n)
