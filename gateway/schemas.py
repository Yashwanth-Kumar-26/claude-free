"""Anthropic-compatible request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ContentBlock(BaseModel):
    type: str
    text: str | None = None
    thinking: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    tool_use_id: str | None = None
    content: Any = None
    source: Any = None
    data: str | None = None
    media_type: str | None = None
    signature: str | None = None
    encrypted_thinking: str | None = None
    enabled: bool | None = None
    budget_tokens: int | None = None

    model_config = {"extra": "allow"}


class ThinkingConfig(BaseModel):
    type: str = "enabled"
    budget_tokens: int = 10000
    enabled: bool | None = None

    model_config = {"extra": "allow"}


class ToolDefinition(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    cache_control: Any = None

    model_config = {"extra": "allow"}


class MessageParam(BaseModel):
    role: str
    content: str | list[ContentBlock] | Any

    model_config = {"extra": "allow"}


class MessagesRequest(BaseModel):
    model: str
    messages: list[MessageParam]
    system: str | list[ContentBlock] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    stream: bool = True
    thinking: ThinkingConfig | dict[str, Any] | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    # Internal routing fields (added by selector, stripped before sending)
    original_model: str | None   = None
    resolved_provider_model: str | None = None
    extra_body: dict[str, Any] | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class TokenCountRequest(BaseModel):
    model: str
    messages: list[MessageParam]
    system: str | list[ContentBlock] | None = None
    tools: list[ToolDefinition] | None = None
    thinking: ThinkingConfig | dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class TokenCountResponse(BaseModel):
    input_tokens: int


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "claudefree"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo]
