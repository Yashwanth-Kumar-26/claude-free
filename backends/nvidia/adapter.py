"""NVIDIA NIM backend adapter.

NVIDIA NIM (NVIDIA Inference Microservices) exposes an OpenAI-compatible
/v1/chat/completions API with extended thinking support.

This adapter:
  1. Uses ChatCompletionsTransport for streaming
  2. Converts Anthropic format to OpenAI format
  3. Adds model-specific reasoning configurations
  4. Handles extended thinking via reasoning_effort + reasoning_budget
  5. Supports optional chat template configuration

Protocol: OpenAI-compatible /v1/chat/completions
Transport: ChatCompletionsTransport (JSON streaming)
Auth: Bearer token (NVIDIA_NIM_API_KEY)
Base URL: https://integrate.api.nvidia.com/v1 (default)

Extended Thinking:
  - reasoning_effort: "high" (from NimConfig)
  - reasoning_budget: model-specific token budget
  - chat_template_kwargs: optional template configuration
"""

from __future__ import annotations

import json
from typing import Any

import openai
from loguru import logger

from backends.base import BackendConfig
from backends.defaults import NVIDIA_NIM_BASE
from backends.transport.chat_completions import ChatCompletionsTransport
from engine import build_openai_body
from settings.nim_cfg import NimConfig


class NvidiaAdapter(ChatCompletionsTransport):
    """NVIDIA NIM via OpenAI-compatible /chat/completions."""

    def __init__(self, cfg: BackendConfig, *, nim: NimConfig) -> None:
        super().__init__(cfg, tag="NIM", base_url=cfg.base_url or NVIDIA_NIM_BASE, api_key=cfg.api_key)
        self._nim = nim

    def _build_body(self, request: Any) -> dict:
        thinking  = self._thinking_enabled(request)
        body      = build_openai_body(request, reasoning_content=thinking)
        model     = body.get("model", "")
        extra: dict = {}

        if thinking and self._nim.needs_reasoning(model):
            extra["reasoning_effort"] = "high"
            extra["reasoning_budget"] = self._nim.budget_for(model)

        if self._nim.enable_chat_template:
            extra["chat_template_kwargs"] = {"enable_thinking": thinking}

        if extra:
            body["extra_body"] = extra
        return body

    def _retry_body(self, error: Exception, body: dict) -> dict | None:
        if not isinstance(error, openai.BadRequestError):
            return None
        txt = (str(error) + json.dumps(getattr(error, "body", None) or {})).lower()
        if "reasoning_budget" in txt:
            new_body = dict(body)
            new_extra = {k: v for k, v in (body.get("extra_body") or {}).items()
                         if "reasoning" not in k}
            new_body["extra_body"] = new_extra or None
            logger.warning("NIM: retry without reasoning_budget")
            return new_body
        if "chat_template" in txt:
            new_body = dict(body)
            new_extra = {k: v for k, v in (body.get("extra_body") or {}).items()
                         if "chat_template" not in k}
            new_body["extra_body"] = new_extra or None
            logger.warning("NIM: retry without chat_template")
            return new_body
        return None
