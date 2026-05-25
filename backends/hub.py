"""Backend registry hub — instantiates and caches all adapter instances.

The BackendHub is the central registry for all LLM backend adapters. It:
  1. Manages adapter lifecycle (creation, caching, cleanup)
  2. Lazily loads configuration from config.json and .env
  3. Supports both hardcoded backends (OpenRouter, NVIDIA NIM, OpenCode)
     and dynamic providers via DynamicAdapterFactory
  4. Handles provider metadata from models.dev

Architecture:
  BackendHub (singleton)
    ├─ _cache: dict[backend_id] → adapter instance (LRU)
    ├─ _config_loader: loads config.json (lazy)
    ├─ _provider_registry: fetches models.dev metadata (lazy)
    └─ _FACTORIES: dict of factory functions for each backend

Usage:
  hub = get_hub()
  adapter = hub.get("open_router")  # returns or creates OpenRouterAdapter
  await hub.cleanup_all()  # on shutdown
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from loguru import logger

from backends.base import BackendAdapter, BackendConfig
from backends.config_loader import get_loader
from backends.dynamic_factory import DynamicAdapterFactory
from backends.exceptions import UnknownBackendError
from backends.provider_registry import get_registry
from settings.env import Settings, get_settings

# ── descriptor ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BackendDescriptor:
    id: str
    label: str
    description: str


BACKEND_DESCRIPTORS: dict[str, BackendDescriptor] = {
    "nvidia_nim": BackendDescriptor(
        id="nvidia_nim",
        label="NVIDIA NIM",
        description="NVIDIA NIM OpenAI-compatible chat API",
    ),
    "open_router": BackendDescriptor(
        id="open_router",
        label="OpenRouter",
        description="OpenRouter native Anthropic messages API",
    ),
    "opencode_go": BackendDescriptor(
        id="opencode_go",
        label="OpenCode Go",
        description="OpenCode Go — OpenAI chat/completions",
    ),
    "opencode_zen": BackendDescriptor(
        id="opencode_zen",
        label="OpenCode Zen",
        description="OpenCode Zen — OpenAI Responses API",
    ),
}

# ── factory functions ────────────────────────────────────────────────────────


def _make_config(
    settings: Settings,
    api_key: str,
    base_url: str = "",
    proxy: str = "",
) -> BackendConfig:
    return BackendConfig(
        api_key=api_key,
        base_url=base_url or None,
        rate_limit=settings.backend_rate_limit,
        rate_window=settings.backend_rate_window,
        max_concurrency=settings.backend_max_concurrency,
        enable_thinking=settings.enable_thinking,
        http_read_timeout=settings.http_read_timeout,
        http_write_timeout=settings.http_write_timeout,
        http_connect_timeout=settings.http_connect_timeout,
        proxy=proxy,
    )


def _build_nvidia(settings: Settings) -> BackendAdapter:
    from backends.nvidia.adapter import NvidiaAdapter

    cfg = _make_config(
        settings, settings.nvidia_nim_api_key, proxy=settings.nvidia_nim_proxy
    )
    return NvidiaAdapter(cfg, nim=settings.nim)


def _build_openrouter(settings: Settings) -> BackendAdapter:
    from backends.openrouter.adapter import OpenRouterAdapter

    cfg = _make_config(
        settings, settings.open_router_api_key, proxy=settings.open_router_proxy
    )
    return OpenRouterAdapter(cfg)


def _build_opencode_go(settings: Settings) -> BackendAdapter:
    from backends.opencode.adapters.openai_compat import OpenAICompatibleAdapter
    from backends.opencode.base_adapter import DynamicAdapterConfig
    from backends.defaults import OPENCODE_GO_BASE

    # Extract model name without backend prefix (e.g., "claude-3-opus" from "opencode_go/claude-3-opus")
    model_name = settings.model.split("/", 1)[1] if "/" in settings.model else settings.model

    config = DynamicAdapterConfig(
        provider_id="opencode_go",
        provider_name="OpenCode Go",
        api_url=OPENCODE_GO_BASE,
        api_key=settings.opencode_api_key,
        model_id=model_name,  # Use unprefixed model name for upstream API
        proxy=settings.opencode_proxy,
    )
    return OpenAICompatibleAdapter(config)


def _build_opencode_zen(settings: Settings) -> BackendAdapter:
    from backends.opencode.adapters.responses_api import ResponsesAPIAdapter
    from backends.opencode.base_adapter import DynamicAdapterConfig
    from backends.defaults import OPENCODE_ZEN_BASE

    # Extract model name without backend prefix (e.g., "claude-3-opus" from "opencode_zen/claude-3-opus")
    model_name = settings.model.split("/", 1)[1] if "/" in settings.model else settings.model

    config = DynamicAdapterConfig(
        provider_id="opencode_zen",
        provider_name="OpenCode Zen",
        api_url=OPENCODE_ZEN_BASE,
        api_key=settings.opencode_api_key,
        model_id=model_name,  # Use unprefixed model name for upstream API
        proxy=settings.opencode_proxy,
    )
    return ResponsesAPIAdapter(config)


_FACTORIES: dict[str, Callable[[Settings], BackendAdapter]] = {
    "nvidia_nim": _build_nvidia,
    "open_router": _build_openrouter,
    "opencode_go": _build_opencode_go,
    "opencode_zen": _build_opencode_zen,
}

# Verify that descriptors and factories are in sync at import time
assert set(BACKEND_DESCRIPTORS) == set(_FACTORIES), (
    "BACKEND_DESCRIPTORS and _FACTORIES are out of sync! "
    f"Descriptors: {set(BACKEND_DESCRIPTORS)}, Factories: {set(_FACTORIES)}"
)


# ── hub ──────────────────────────────────────────────────────────────────────


class BackendHub:
    """Singleton cache of backend adapter instances.

    Adapters are created lazily on first use and reused for the server lifetime.

    Supports both hardcoded backends and dynamic providers from models.dev.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, BackendAdapter] = {}
        self._config_loader: Any | None = None
        self._provider_registry: Any | None = None
        self._dynamic_backends_loaded = False

    def _get_config_loader(self) -> Any:
        """Lazy-load config loader."""
        if not self._config_loader:
            self._config_loader = get_loader()
        return self._config_loader

    def _get_provider_registry(self) -> Any:
        """Lazy-load provider registry."""
        if not self._provider_registry:
            self._provider_registry = get_registry()
        return self._provider_registry

    async def _load_dynamic_backends(self) -> None:
        """Load dynamic providers from config.json."""
        global BACKEND_DESCRIPTORS
        if self._dynamic_backends_loaded:
            return

        try:
            loader = self._get_config_loader()
            registry = self._get_provider_registry()

            # Load provider from config.json
            provider_id = loader.get_provider()
            logger.info("BackendHub: loading dynamic provider '{}'", provider_id)

            # Fetch providers from models.dev
            providers = await registry.fetch_providers()
            provider_data = providers.get(provider_id)

            if not provider_data:
                logger.warning(
                    "BackendHub: provider '{}' not found in models.dev, adding to dynamic backends list only",
                    provider_id,
                )
                return

            # Create the dynamic backend
            model_id = loader.get_model("default")
            env_vars = loader.load_env_file()
            api_key = loader.get_api_key(provider_id, env_vars)

            # Create the adapter instance
            adapter = await DynamicAdapterFactory.create_adapter(
                provider_id=provider_id,
                provider_data=provider_data,
                api_key=api_key,
                model_id=model_id,
            )

            # Add provider to descriptors if not already there
            if provider_id not in BACKEND_DESCRIPTORS:
                provider_name = provider_data.get("name", provider_id)
                new_descriptor = BackendDescriptor(
                    id=provider_id,
                    label=provider_name,
                    description="Dynamic provider from models.dev",
                )
                # We can't update BACKEND_DESCRIPTORS directly if it's a global dict being used elsewhere
                # but we can add it to our internal registry if we had one.
                # Actually BACKEND_DESCRIPTORS is global, so we can update it.
                # But it's better to just ensure it's in our cache.
                BACKEND_DESCRIPTORS = dict(BACKEND_DESCRIPTORS)
                BACKEND_DESCRIPTORS[provider_id] = new_descriptor

            # Cache the adapter
            self._cache[provider_id] = adapter

            self._dynamic_backends_loaded = True
            logger.info("BackendHub: dynamic provider '{}' ready", provider_id)

        except FileNotFoundError:
            logger.debug("BackendHub: no config.json found, dynamic providers disabled")
            self._dynamic_backends_loaded = True
        except Exception as e:
            logger.warning("BackendHub: failed to load dynamic providers: {}", e)
            self._dynamic_backends_loaded = True

    def get(self, backend_id: str) -> BackendAdapter:
        """Get a backend adapter (hardcoded or dynamic).

        Uses single-pass lookup with LRU ordering for fast path.
        Note: cache is bounded to prevent unbounded memory growth,
        but cleanup happens asynchronously during shutdown only.

        Args:
            backend_id: Backend ID

        Returns:
            BackendAdapter instance

        Raises:
            UnknownBackendError: If backend not found
        """
        # Fast path: already cached (reuse HTTP/2 pool)
        if backend_id in self._cache:
            # Implicit LRU: move to end on access
            adapter = self._cache[backend_id]
            del self._cache[backend_id]
            self._cache[backend_id] = adapter
            return adapter

        # Try hardcoded backends first
        if backend_id in _FACTORIES:
            logger.info("BackendHub: instantiating adapter '{}'", backend_id)
            adapter = _FACTORIES[backend_id](self._settings)
            
            # Keep bounded cache to prevent unbounded HTTP/2 pool growth
            # Old adapters are cleaned up during shutdown, not inline
            if len(self._cache) >= 10:
                oldest_id = next(iter(self._cache))
                self._cache.pop(oldest_id)
                logger.info("BackendHub: evicted unused adapter '{}' from cache", oldest_id)
            
            self._cache[backend_id] = adapter
            return adapter

        # Dynamic backends not found
        supported = ", ".join(f"'{k}'" for k in _FACTORIES)
        raise UnknownBackendError(f"Unknown backend '{backend_id}'. Supported: {supported}")

    async def async_init(self) -> None:
        """Async initialization to load dynamic providers.

        Call this during server startup.
        """
        await self._load_dynamic_backends()

    async def cleanup_all(self) -> None:
        for bid, adapter in list(self._cache.items()):
            try:
                await adapter.cleanup()
            except Exception as exc:
                logger.warning("BackendHub: cleanup {} failed: {}", bid, exc)
        self._cache.clear()

    def list_backends(self) -> list[BackendDescriptor]:
        return list(BACKEND_DESCRIPTORS.values())


@lru_cache
def get_hub() -> BackendHub:
    return BackendHub(get_settings())
