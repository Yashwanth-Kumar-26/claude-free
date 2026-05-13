"""Application settings — loaded from .env / environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .backend_ids import REGISTERED_BACKEND_IDS
from .nim_cfg import NimConfig

# ---------------------------------------------------------------------------
# .env resolution
# ---------------------------------------------------------------------------


def _env_paths() -> tuple[Path, ...]:
    paths: list[Path] = [
        Path.home() / ".config" / "claudefree" / ".env",
        Path(".env"),
    ]
    if extra := os.environ.get("CF_ENV_FILE"):
        paths.append(Path(extra))
    return tuple(paths)


def _dotenv_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    try:
        vals = dotenv_values(path)
    except OSError:
        return None
    if key not in vals:
        return None
    return "" if vals[key] is None else vals[key]


def _last_dotenv_value(paths: tuple[Path, ...], key: str) -> str | None:
    result: str | None = None
    for p in paths:
        v = _dotenv_value(p, key)
        if v is not None:
            result = v
    return result


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """All runtime configuration for the claudefree gateway."""

    # ── Fallback / per-tier model ───────────────────────────────────────────
    model: str = "open_router/deepseek/deepseek-chat-v3-0324:free"
    model_opus: str | None = Field(default=None, validation_alias="MODEL_OPUS")
    model_sonnet: str | None = Field(default=None, validation_alias="MODEL_SONNET")
    model_haiku: str | None = Field(default=None, validation_alias="MODEL_HAIKU")

    # ── Backend API keys ────────────────────────────────────────────────────
    nvidia_nim_api_key: str = Field(default="", validation_alias="NVIDIA_NIM_API_KEY")
    open_router_api_key: str = Field(default="", validation_alias="OPEN_ROUTER_API_KEY")
    opencode_api_key: str = Field(default="", validation_alias="OPENCODE_API_KEY")
    # ── Optional per-provider HTTP proxies ──────────────────────────────────
    nvidia_nim_proxy: str = Field(default="", validation_alias="NVIDIA_NIM_PROXY")
    open_router_proxy: str = Field(default="", validation_alias="OPENROUTER_PROXY")
    opencode_proxy: str = Field(default="", validation_alias="OPENCODE_PROXY")
    # ── Rate limiting ───────────────────────────────────────────────────────
    backend_rate_limit: int = Field(default=40, validation_alias="BACKEND_RATE_LIMIT")
    backend_rate_window: int = Field(default=60, validation_alias="BACKEND_RATE_WINDOW")
    backend_max_concurrency: int = Field(
        default=5, validation_alias="BACKEND_MAX_CONCURRENCY"
    )

    # ── HTTP client timeouts ────────────────────────────────────────────────
    http_read_timeout: float = Field(default=120.0, validation_alias="HTTP_READ_TIMEOUT")
    http_write_timeout: float = Field(default=10.0, validation_alias="HTTP_WRITE_TIMEOUT")
    http_connect_timeout: float = Field(
        default=5.0, validation_alias="HTTP_CONNECT_TIMEOUT"
    )

    # ── Thinking / reasoning ────────────────────────────────────────────────
    enable_thinking: bool = Field(default=True, validation_alias="ENABLE_THINKING")

    # ── Request shortcuts (intercept trivial calls locally) ─────────────────
    enable_shortcuts: bool = Field(default=True, validation_alias="ENABLE_SHORTCUTS")

    # ── NIM-specific ────────────────────────────────────────────────────────
    nim: NimConfig = Field(default_factory=NimConfig)

    # ── HTTP server ─────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 16324
    log_file: str = "claudefree.log"
    auth_token: str = Field(default="God", validation_alias="ANTHROPIC_AUTH_TOKEN")

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("model_opus", "model_sonnet", "model_haiku", mode="before")
    @classmethod
    def _coerce_empty_none(cls, v: Any) -> Any:
        return None if v == "" else v

    @field_validator("model", "model_opus", "model_sonnet", "model_haiku")
    @classmethod
    def _validate_model_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if "/" not in v:
            raise ValueError(
                f"Model must be 'backend_id/model_name'. "
                f"Registered backends: {', '.join(REGISTERED_BACKEND_IDS)}"
            )
        prefix = v.split("/", 1)[0]
        if prefix not in REGISTERED_BACKEND_IDS:
            supported = ", ".join(f"'{b}'" for b in REGISTERED_BACKEND_IDS)
            raise ValueError(f"Unknown backend '{prefix}'. Supported: {supported}")
        return v

    @model_validator(mode="after")
    def _prefer_dotenv_auth_token(self) -> Settings:
        """Let the .env auth token override a stale shell variable."""
        override = _last_dotenv_value(tuple(_env_paths()), "ANTHROPIC_AUTH_TOKEN")
        if override is not None:
            self.auth_token = override
        return self

    @model_validator(mode="after")
    def _load_config_json(self) -> Settings:
        """Load model configuration from config.json if it exists."""
        config_path = Path("config.json")
        if config_path.is_file():
            try:
                import json

                with open(config_path) as f:
                    cfg = json.load(f)
                    provider = cfg.get("provider")
                    model_name = cfg.get("model_default")
                    if provider and model_name:
                        self.model = f"{provider}/{model_name}"
            except Exception:
                pass
        return self

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def default_backend_id(self) -> str:
        return self.model.split("/", 1)[0]

    @property
    def default_model_name(self) -> str:
        return self.model.split("/", 1)[1]

    def resolve_model(self, claude_model: str) -> str:
        """Map an incoming Claude model name to our backend/model string."""
        # 1. Direct backend target? (e.g. 'open_router/anthropic/claude...')
        if "/" in claude_model:
            head = claude_model.split("/", 1)[0]
            if head in REGISTERED_BACKEND_IDS:
                return claude_model

        # 2. Tier aliases
        lower = claude_model.lower()
        if "opus" in lower and self.model_opus:
            return self.model_opus
        if "haiku" in lower and self.model_haiku:
            return self.model_haiku
        if "sonnet" in lower and self.model_sonnet:
            return self.model_sonnet

        # 3. Default fallback
        return self.model

    @staticmethod
    def split_backend(model_string: str) -> tuple[str, str]:
        """Return (backend_id, model_name) from a 'backend/model' string."""
        parts = model_string.split("/", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    model_config = SettingsConfigDict(
        env_file=_env_paths(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
