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


_FACTORIES: dict[str, Callable[[Settings], BackendAdapter]] = {
    "nvidia_nim": _build_nvidia,
    "open_router": _build_openrouter,
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

        Args:
            backend_id: Backend ID

        Returns:
            BackendAdapter instance

        Raises:
            UnknownBackendError: If backend not found
        """
        # Try hardcoded backends first
        if backend_id in _FACTORIES:
            if backend_id not in self._cache:
                logger.info("BackendHub: instantiating hardcoded adapter '{}'", backend_id)
                self._cache[backend_id] = _FACTORIES[backend_id](self._settings)
            return self._cache[backend_id]

        # Try dynamic backends
        if backend_id in self._cache:
            return self._cache[backend_id]

        if backend_id in BACKEND_DESCRIPTORS and backend_id not in _FACTORIES:
            # It's in descriptors but not in cache/factories — might be a dynamic
            # backend that failed to load or hasn't been loaded yet.
                logger.warning(
                    "BackendHub: dynamic backend '{}' is not instantiated. "
                    "Did dynamic loading fail?",
                    backend_id,
                )

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
