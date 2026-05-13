"""Adapter for Responses API format.

Handles APIs using the Responses SDK format.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from loguru import logger

from backends.opencode.base_adapter import DynamicAdapterConfig, DynamicBackendAdapter


class ResponsesAPIAdapter(DynamicBackendAdapter):
    """Adapter for Responses API format (alternative streaming format)."""

    def __init__(self, config: DynamicAdapterConfig):
        super().__init__(config)
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def validate_credentials(self) -> bool:
        """
        Validate API key by making a test request.

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
        Create a message using Responses API format.

        Args:
            messages: List of messages
            system: System prompt
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            **kwargs: Additional options

        Yields:
            Anthropic SSE format responses
        """
        try:
            # Responses API typically uses a different request format
            # This is a simplified version - actual implementation depends on provider
            request_body = {
                "model": self.model_id,
                "messages": messages,
                "stream": True,
                "temperature": temperature or 1.0,
            }

            if max_tokens:
                request_body["max_tokens"] = max_tokens

            if system:
                request_body["system"] = system

            request_body.update(kwargs)

            logger.debug(f"Calling {self.provider_id} API with Responses format")

            # Try common endpoint patterns
            endpoint_candidates = [
                "/v1/chat/completions",
                "/api/v1/chat/completions",
                "/completions",
            ]

            last_error = None
            for endpoint in endpoint_candidates:
                try:
                    async with self.client.stream(
                        "POST",
                        endpoint,
                        json=request_body,
                        timeout=300.0,
                    ) as response:
                        if response.status_code == 200:
                            # Successfully found endpoint
                            async for line in response.aiter_lines():
                                if not line or line.startswith(":"):
                                    continue

                                if line.startswith("data: "):
                                    data_str = line[6:]
                                    if data_str == "[DONE]":
                                        break

                                    try:
                                        data = json.loads(data_str)
                                        chunk = self._convert_to_anthropic_chunk(data)
                                        if chunk:
                                            yield chunk
                                    except json.JSONDecodeError:
                                        logger.warning(
                                            f"Failed to parse JSON chunk: {data_str}"
                                        )
                            return

                        elif response.status_code != 404:
                            error_text = await response.aread()
                            last_error = (
                                f"{response.status_code}: {error_text.decode()}"
                            )
                            break

                except httpx.ConnectError:
                    continue

            # If we get here, no endpoint worked
            if last_error:
                raise RuntimeError(f"API error: {last_error}")
            else:
                raise RuntimeError(
                    f"Could not find working endpoint for {self.provider_id}"
                )

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

    def _convert_to_anthropic_chunk(self, data: dict[str, Any]) -> str | None:
        """
        Convert Responses API chunk to Anthropic SSE format.

        This is a generic converter - actual format depends on provider.

        Args:
            data: Response chunk from provider

        Returns:
            Anthropic SSE format chunk or None
        """
        # Handle different possible chunk formats
        if "choices" in data:
            # OpenAI-like format
            choices = data.get("choices", [])
            if choices:
                choice = choices[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")

                if "content" in delta:
                    anthropic_chunk = {
                        "type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": delta["content"]},
                    }
                    return f"event: content_block_delta\ndata: {json.dumps(anthropic_chunk)}\n\n"

                if finish_reason:
                    anthropic_chunk = {
                        "type": "message_delta",
                        "delta": {"stop_reason": finish_reason},
                    }
                    return f"event: message_delta\ndata: {json.dumps(anthropic_chunk)}\n\n"

        elif "text" in data:
            # Simple text format
            anthropic_chunk = {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": data["text"]},
            }
            return f"event: content_block_delta\ndata: {json.dumps(anthropic_chunk)}\n\n"

        return None
