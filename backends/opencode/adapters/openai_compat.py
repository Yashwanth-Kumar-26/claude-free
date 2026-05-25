"""Adapter for OpenAI-compatible APIs.

Converts Anthropic protocol to OpenAI format and back.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from loguru import logger

from backends.opencode.base_adapter import DynamicAdapterConfig, DynamicBackendAdapter


class OpenAICompatibleAdapter(DynamicBackendAdapter):
    """Adapter for OpenAI-compatible APIs (most common format)."""

    def __init__(self, config: DynamicAdapterConfig):
        super().__init__(config)
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.client.aclose()
        await super().cleanup()

    async def validate_credentials(self) -> bool:
        """
        Validate API key by making a test request.

        Returns:
            True if API key is valid
        """
        try:
            # Try a minimal request to models endpoint (if available)
            # or just verify the auth header works
            response = await self.client.get(
                "/models",
                timeout=10.0,
            )
            # Any 2xx or 4xx (not auth error) response means credentials exist
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
        tools: list[dict[str, Any]] | None = None,
        input_tokens: int = 0,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Create a message using OpenAI-compatible API.

        Converts from Anthropic protocol, calls OpenAI API, converts response back.

        Args:
            messages: List of messages in Anthropic format
            system: System prompt
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            tools: Anthropic-format tool definitions
            **kwargs: Additional options

        Yields:
            Anthropic SSE format responses
        """
        try:
            # Convert Anthropic messages to OpenAI format
            openai_messages = self._convert_to_openai_messages(messages, system)

            # DeepSeek thinking mode requires reasoning_content on all assistant messages
            if self.model_id and "deepseek" in self.model_id.lower():
                for msg in openai_messages:
                    if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                        msg["reasoning_content"] = " "

            # Prepare request body
            request_body = {
                "model": self.model_id,
                "messages": openai_messages,
                "stream": True,
                "temperature": temperature or 1.0,
            }

            if max_tokens:
                request_body["max_tokens"] = max_tokens

            # Convert Anthropic tools → OpenAI function definitions
            if tools:
                request_body["tools"] = self._convert_tools_to_openai(tools)
                request_body["tool_choice"] = "auto"

            # Add any additional options
            request_body.update(kwargs)

            logger.debug(f"Calling {self.provider_id} API with model {request_body.get('model') or self.model_id}")

            # Call OpenAI-compatible endpoint
            async with self.client.stream(
                "POST",
                "/chat/completions",
                json=request_body,
                timeout=300.0,  # 5 minute timeout for long generations
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(
                        f"API error {response.status_code}: {error_text.decode()}"
                    )

                from engine.sse_builder import SSEBuilder
                from engine.tools import ToolParser

                msg_id = f"msg_dyn_{uuid.uuid4().hex[:8]}"
                sse = SSEBuilder(msg_id, self.model_id, input_tokens=input_tokens)
                heuristic_parser = ToolParser()

                yield sse.message_start()

                final_stop_reason = None

                # Stream response line by line
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if not choices:
                                continue

                            delta = choices[0].get("delta", {})
                            finish_reason = choices[0].get("finish_reason")
                            if finish_reason:
                                final_stop_reason = finish_reason

                            # Handle reasoning content (thinking mode for DeepSeek etc.)
                            reasoning = delta.get("reasoning_content")
                            if reasoning is not None:
                                for event in sse.ensure_thinking_block():
                                    yield event
                                if reasoning:
                                    yield sse.emit_thinking_delta(reasoning)

                            # Handle text content
                            content = delta.get("content", "")
                            if content:
                                filtered_text, detected_tools = heuristic_parser.feed(content)
                                if filtered_text:
                                    for event in sse.ensure_text_block():
                                        yield event
                                    yield sse.emit_text_delta(filtered_text)

                                for tool_use in detected_tools:
                                    for event in sse.close_content_blocks():
                                        yield event
                                    block_idx = sse.blocks.allocate_index()
                                    yield sse.content_block_start(
                                        block_idx, "tool_use",
                                        id=tool_use["id"], name=tool_use["name"]
                                    )
                                    yield sse.content_block_delta(
                                        block_idx, "input_json_delta",
                                        json.dumps(tool_use.get("input", {}))
                                    )
                                    yield sse.content_block_stop(block_idx)

                            # Handle native tool calls
                            tool_calls = delta.get("tool_calls", [])
                            if tool_calls:
                                for event in sse.close_content_blocks():
                                    yield event
                                for tc in tool_calls:
                                    tc_index = tc.get("index", 0)
                                    fn = tc.get("function", {})

                                    if tc.get("id") and fn.get("name"):
                                        yield sse.start_tool_block(tc_index, tc["id"], fn["name"])

                                    args_chunk = fn.get("arguments", "")
                                    if args_chunk:
                                        state = sse.blocks.tool_states.get(tc_index)
                                        if not state or not state.started:
                                            tool_id = tc.get("id", f"tool_{uuid.uuid4().hex[:8]}")
                                            name = state.name if state else "tool"
                                            yield sse.start_tool_block(tc_index, tool_id, name)

                                        yield sse.emit_tool_delta(tc_index, args_chunk)

                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse JSON chunk: {data_str}")

                # Flush final buffers
                for tool_use in heuristic_parser.flush():
                    for event in sse.close_content_blocks():
                        yield event
                    block_idx = sse.blocks.allocate_index()
                    yield sse.content_block_start(
                        block_idx, "tool_use",
                        id=tool_use["id"], name=tool_use["name"]
                    )
                    yield sse.content_block_delta(
                        block_idx, "input_json_delta",
                        json.dumps(tool_use.get("input", {}))
                    )
                    yield sse.content_block_stop(block_idx)

                for event in sse.close_all_blocks():
                    yield event

                stop_reason_mapped = self._convert_stop_reason(final_stop_reason) if final_stop_reason else "end_turn"
                yield sse.message_delta(stop_reason_mapped, sse.estimate_output_tokens())
                yield sse.message_stop()

        except Exception as e:
            logger.error(f"Error in create_message: {e}")
            # Ensure we wrap error if needed, but since we already might have sent message_start,
            # this error handling could break the streaming protocol, but it's okay for hard errors.
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

    def _convert_to_openai_messages(
        self, messages: list[dict[str, Any]], system: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Convert Anthropic messages to OpenAI format.

        Args:
            messages: Anthropic format messages
            system: System prompt

        Returns:
            OpenAI format messages
        """
        openai_messages = []

        # Add system message if provided
        if system:
            openai_messages.append({"role": "system", "content": system})

        # Convert messages
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content")

            if isinstance(content, list):
                text_parts: list[dict] = []
                reasoning_parts: list[str] = []
                tool_calls: list[dict] = []
                tool_results: list[dict] = []

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")

                    if btype == "text":
                        text_parts.append({"type": "text", "text": block.get("text", "")})

                    elif btype == "thinking":
                        reasoning_parts.append(block.get("thinking", ""))

                    elif btype == "image":
                        text_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": block.get("source", {}).get("url", "")},
                            }
                        )

                    elif btype == "tool_use":
                        # Anthropic tool_use → OpenAI tool_calls on assistant message
                        tool_calls.append(
                            {
                                "id": block.get("id", f"call_{block.get('name', '')}"),
                                "type": "function",
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": json.dumps(block.get("input", {})),
                                },
                            }
                        )

                    elif btype == "tool_result":
                        # Anthropic tool_result → OpenAI tool role message
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            result_text = " ".join(
                                b.get("text", "") for b in result_content if isinstance(b, dict)
                            )
                        else:
                            result_text = str(result_content)
                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": block.get("tool_use_id", ""),
                                "content": result_text,
                            }
                        )

                # assistant message with optional tool_calls
                if role == "assistant":
                    asst_msg: dict[str, Any] = {"role": "assistant"}
                    if text_parts:
                        asst_msg["content"] = text_parts if len(text_parts) > 1 else text_parts[0]["text"]
                    else:
                        asst_msg["content"] = None
                    if reasoning_parts:
                        asst_msg["reasoning_content"] = "".join(reasoning_parts)
                    if tool_calls:
                        asst_msg["tool_calls"] = tool_calls
                    openai_messages.append(asst_msg)
                elif tool_results:
                    # user message carrying tool results
                    openai_messages.extend(tool_results)
                else:
                    if text_parts:
                        openai_messages.append({"role": role, "content": text_parts})
            else:
                # Simple text content
                openai_messages.append({"role": role, "content": content})

        return openai_messages

    def _convert_tools_to_openai(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Anthropic tool definitions to OpenAI function definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for tool in tools
        ]

    def _convert_stop_reason(self, openai_reason: str) -> str:
        """Convert OpenAI stop reason to Anthropic format."""
        mapping = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
            "function_call": "tool_use",
        }
        return mapping.get(openai_reason, openai_reason)
