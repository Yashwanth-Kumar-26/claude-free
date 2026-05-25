"""Adapter for Anthropic-native API.

Handles direct Anthropic API calls.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from loguru import logger

from backends.opencode.base_adapter import DynamicAdapterConfig, DynamicBackendAdapter


class AnthropicNativeAdapter(DynamicBackendAdapter):
    """Adapter for Anthropic-native API (direct Anthropic calls)."""

    ANTHROPIC_API_VERSION = "2023-06-01"

    def __init__(self, config: DynamicAdapterConfig):
        super().__init__(config)
        base_url = self.api_url or "https://api.anthropic.com"
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
        )

    async def validate_credentials(self) -> bool:
        """
        Validate API key by checking Anthropic models endpoint.

        Returns:
            True if API key is valid
        """
        try:
            response = await self.client.get(
                "/models",
                timeout=10.0,
            )
            return response.status_code != 401
        except Exception as e:
            logger.warning(f"Credential validation failed: {e}")
            return False

    async def create_message(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Create a message using Anthropic API (already in Anthropic format).

        Args:
            messages: List of messages already in Anthropic format
            system: System prompt
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            **kwargs: Additional options

        Yields:
            Anthropic SSE format responses
        """
        try:
            # Build request body for Anthropic API
            request_body = {
                "model": self.model_id,
                "messages": messages,
                "stream": True,
                "max_tokens": max_tokens or 4096,
            }

            if system:
                request_body["system"] = system

            if temperature is not None:
                request_body["temperature"] = temperature

            # Add any additional options
            request_body.update(kwargs)

            logger.debug(f"Calling Anthropic API with model {request_body.get('model') or self.model_id}")

            # Call Anthropic API
            async with self.client.stream(
                "POST",
                "/messages",
                json=request_body,
                timeout=300.0,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(
                        f"Anthropic API error {response.status_code}: {error_text.decode()}"
                    )

                # Stream response - Anthropic already uses SSE format
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue

                    # Anthropic returns SSE format directly
                    if line.startswith("data: "):
                        yield line + "\n\n"

        except Exception as e:
            logger.error(f"Error in create_message: {e}")
            error_response = {
                "type": "message_stop",
                "message": {
                    "type": "message",
                    "id": "error",
                    "content": [{"type": "text", "text": f"Error: {e!s}"}],
                    "stop_reason": "end_turn",
                },
            }
            yield f"data: {json.dumps(error_response)}\n\n"
