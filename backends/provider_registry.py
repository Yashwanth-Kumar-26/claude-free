"""Provider registry — fetches and caches provider data from models.dev."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


class ProviderRegistry:
    """Manages provider data fetching and caching from models.dev."""

    MODELS_DEV_API = "https://models.dev/api.json"
    DEFAULT_CACHE_TTL = 3600  # 1 hour in seconds
    DEFAULT_CACHE_DIR = Path.home() / ".cache" / "claudefree"

    def __init__(
        self, cache_dir: Path | None = None, cache_ttl: int = DEFAULT_CACHE_TTL
    ):
        """Initialize provider registry.

        Args:
            cache_dir: Directory to cache provider data. Defaults to ~/.cache/claudefree
            cache_ttl: Cache time-to-live in seconds. Defaults to 3600 (1 hour)
        """
        self.cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self.cache_ttl = cache_ttl
        self.cache_file = self.cache_dir / "providers.json"
        self._providers: dict[str, Any] | None = None
        self._cache_timestamp: datetime | None = None

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _is_cache_valid(self) -> bool:
        """Check if cached providers are still valid."""
        if not self._cache_timestamp:
            return False
        elapsed = (datetime.now() - self._cache_timestamp).total_seconds()
        return elapsed < self.cache_ttl

    async def fetch_providers(self, force_refresh: bool = False) -> dict[str, Any]:
        """Fetch providers from models.dev API or cache.

        Args:
            force_refresh: Force refresh from API, ignoring cache

        Returns:
            Dictionary of providers with their metadata
        """
        # Return cached if valid
        if self._providers and self._is_cache_valid() and not force_refresh:
            logger.debug("ProviderRegistry: using cached providers")
            return self._providers

        # Try to load from cache file
        if not force_refresh and self.cache_file.exists():
            try:
                logger.debug("ProviderRegistry: loading providers from cache file")
                with open(self.cache_file) as f:
                    data = json.load(f)
                    self._providers = data
                    self._cache_timestamp = datetime.now()
                    return self._providers
            except Exception as e:
                logger.warning("ProviderRegistry: failed to load cache: {}", e)

        # Fetch from API
        try:
            logger.info("ProviderRegistry: fetching providers from {}", self.MODELS_DEV_API)
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(self.MODELS_DEV_API)
                response.raise_for_status()
                self._providers = response.json()
                self._cache_timestamp = datetime.now()

                # Save to cache
                self._ensure_cache_dir()
                with open(self.cache_file, "w") as f:
                    json.dump(self._providers, f)
                    logger.debug("ProviderRegistry: saved providers to cache")

                return self._providers
        except Exception as e:
            logger.error("ProviderRegistry: failed to fetch providers: {}", e)
            raise

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        """Get provider data by ID (must call fetch_providers first).

        Args:
            provider_id: Provider ID to look up

        Returns:
            Provider data dict or None if not found
        """
        if not self._providers:
            logger.warning(
                "ProviderRegistry: providers not loaded, call fetch_providers first"
            )
            return None
        return self._providers.get(provider_id)

    def list_provider_ids(self) -> list[str]:
        """List all available provider IDs (must call fetch_providers first).

        Returns:
            List of provider IDs
        """
        if not self._providers:
            logger.warning(
                "ProviderRegistry: providers not loaded, call fetch_providers first"
            )
            return []
        return list(self._providers.keys())

    def get_provider_models(self, provider_id: str) -> dict[str, Any]:
        """Get models for a provider.

        Args:
            provider_id: Provider ID

        Returns:
            Dictionary of models with their metadata
        """
        provider = self.get_provider(provider_id)
        if not provider:
            return {}
        return provider.get("models", {})

    def get_provider_api_url(self, provider_id: str) -> str | None:
        """Get API URL for a provider.

        Args:
            provider_id: Provider ID

        Returns:
            API URL or None if not found
        """
        provider = self.get_provider(provider_id)
        if not provider:
            return None
        return provider.get("api")

    def get_provider_env_vars(self, provider_id: str) -> list[str]:
        """Get required environment variables for a provider.

        Args:
            provider_id: Provider ID

        Returns:
            List of environment variable names
        """
        provider = self.get_provider(provider_id)
        if not provider:
            return []
        return provider.get("env", [])

    def clear_cache(self) -> None:
        """Clear in-memory and on-disk cache."""
        self._providers = None
        self._cache_timestamp = None
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                logger.debug("ProviderRegistry: cleared cache file")
            except Exception as e:
                logger.warning("ProviderRegistry: failed to delete cache file: {}", e)


# Global registry instance
_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Get or create the global provider registry.

    Returns:
        ProviderRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
