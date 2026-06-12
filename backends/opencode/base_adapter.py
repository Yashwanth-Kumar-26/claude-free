"""Base adapter class for all dynamic providers."""

from __future__ import annotations

import json
import uuid
from abc import abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from loguru import logger

from backends.base import BackendAdapter, BackendConfig


class DynamicAdapterConfig:
    """Configuration for a dynamic adapter."""

    def __init__(
        self,
        provider_id: str,
        provider_name: str,
        api_url: str,
        api_key: str,
        model_id: str,
        **kwargs,
    ):
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.api_url = api_url
        self.api_key = api_key
        self.model_id = model_id
        self.extra = kwargs


class DynamicBackendAdapter(BackendAdapter):
    """Abstract base class for dynamic backend adapters."""

    def __init__(self, config: DynamicAdapterConfig):
        # Initialize BackendAdapter with a dummy config or extract relevant bits
        # Actually BackendAdapter needs BackendConfig
        dummy_cfg = BackendConfig(api_key=config.api_key)
        super().__init__(dummy_cfg)
        self.config = config
        self.provider_id = config.provider_id
        self.provider_name = config.provider_name
        self.api_url = config.api_url
        self.api_key = config.api_key
        self.model_id = config.model_id

    @abstractmethod
    async def create_message(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        input_tokens: int = 0,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Create a message and stream the response.

        Args:
            messages: List of message dicts with role/content
            system: System prompt
            max_tokens: Max tokens in response
            temperature: Temperature for generation
            **kwargs: Additional provider-specific options

        Yields:
            Streamed response chunks (in Anthropic SSE format)
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate that the API key works.

        Returns:
            True if credentials are valid
        """
        pass

    async def get_model_info(self) -> dict[str, Any]:
        """
        Get info about the model.

        Returns:
            Dictionary with model metadata
        """
        return {
            "id": self.model_id,
            "provider": self.provider_id,
            "provider_name": self.provider_name,
        }

    async def cleanup(self) -> None:
        """Clean up resources used by the adapter."""
        pass

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Implementation of the BackendAdapter interface.
        Delegates to create_message.
        """
        # Convert Pydantic request to compatible parameters
        messages = []
        for m in request.messages:
            msg = {"role": m.role}
            if isinstance(m.content, str):
                msg["content"] = m.content
            elif isinstance(m.content, list):
                msg["content"] = [b.model_dump() if hasattr(b, "model_dump") else b for b in m.content]
            else:
                msg["content"] = m.content
            messages.append(msg)

        system_str = None
        if request.system:
            if isinstance(request.system, str):
                system_str = request.system
            elif isinstance(request.system, list):
                # Concatenate text from content blocks
                parts = []
                for b in request.system:
                    if hasattr(b, "text") and b.text:
                        parts.append(b.text)
                    elif isinstance(b, dict) and b.get("text"):
                        parts.append(b["text"])
                system_str = "\n".join(parts)

        # Extract tools if present
        tools = None
        if hasattr(request, "tools") and request.tools:
            tools = [
                t.model_dump() if hasattr(t, "model_dump") else t
                for t in request.tools
            ]

        first = True
        wrapped = False
        had_delta = False
        block_stopped = False
        upstream_stop_reason = "end_turn"

        async for chunk in self.create_message(
            messages=messages,
            system=system_str,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            tools=tools,
            input_tokens=input_tokens,
            model=request.model,
        ):
            if first:
                first = False
                if '"type": "message_start"' not in chunk:
                    # Need wrapping to be Anthropic-compatible
                    wrapped = True
                    msg_id = f"msg_dyn_{uuid.uuid4()}"
                    yield f'event: message_start\ndata: {{"type": "message_start", "message": {{"id": "{msg_id}", "type": "message", "role": "assistant", "model": "{self.model_id}", "content": [], "stop_reason": null, "stop_sequence": null, "usage": {{"input_tokens": {input_tokens}, "output_tokens": 1}}}}}}\n\n'
                    yield 'event: content_block_start\ndata: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}\n\n'

            if wrapped and '"type": "message_delta"' in chunk:
                # content_block_stop MUST come before message_delta (Anthropic protocol)
                if not block_stopped:
                    block_stopped = True
                    yield 'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 0}\n\n'
                if had_delta:
                    # Suppress duplicate message_delta (OpenRouter sends usage in a 2nd one)
                    continue
                had_delta = True
                # Extract stop_reason from upstream
                try:
                    parts = chunk.split("data: ", 1)
                    if len(parts) < 2:
                        logger.debug("Chunk missing 'data: ' separator: {}", chunk[:100])
                    else:
                        data_str = parts[1].strip()
                        stop_reason = json.loads(data_str).get("delta", {}).get("stop_reason")
                        if stop_reason:
                            upstream_stop_reason = stop_reason
                except json.JSONDecodeError as e:
                    logger.debug("Failed to parse JSON in chunk: {}", e)
                except Exception as e:
                    logger.debug("Unexpected error parsing chunk: {}: {}", type(e).__name__, e)

            yield chunk

        if wrapped:
            # Emit content_block_stop if upstream never sent message_delta
            if not block_stopped:
                yield 'event: content_block_stop\ndata: {"type": "content_block_stop", "index": 0}\n\n'
            if not had_delta:
                yield f'event: message_delta\ndata: {{"type": "message_delta", "delta": {{"stop_reason": "{upstream_stop_reason}", "stop_sequence": null}}, "usage": {{"output_tokens": 1}}}}\n\n'
            yield 'event: message_stop\ndata: {"type": "message_stop"}\n\n'

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider={self.provider_id}, model={self.model_id})"
