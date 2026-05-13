"""Dynamic adapter factory — creates adapters for any provider from models.dev."""

from __future__ import annotations

from typing import Any, ClassVar

from loguru import logger

from backends.base import BackendAdapter, BackendConfig
from backends.opencode.adapters.anthropic_native import AnthropicNativeAdapter
from backends.opencode.adapters.openai_compat import OpenAICompatibleAdapter
from backends.opencode.adapters.responses_api import ResponsesAPIAdapter
from backends.opencode.base_adapter import DynamicAdapterConfig, DynamicBackendAdapter


class DynamicAdapterFactory:
    """Creates dynamic adapters for any provider from models.dev."""

    # Mapping of npm package names to adapter types
    ADAPTER_DETECTION: ClassVar[dict[str, str]] = {
        "@anthropic-ai/sdk": "anthropic_native",
        "@openrouter/ai-sdk-provider": "openai_compat",
        "@azure/openai": "openai_compat",
        "openai": "openai_compat",
        "groq": "openai_compat",
        "mistralai": "openai_compat",
        "cohere": "openai_compat",
        "together": "openai_compat",
    }

    @staticmethod
    def detect_adapter_type(provider_data: dict[str, Any]) -> str:
        """Detect adapter type based on provider metadata.

        Args:
            provider_data: Provider data from models.dev

        Returns:
            Adapter type: 'anthropic_native', 'openai_compat', or 'responses_api'
        """
        npm = provider_data.get("npm", "")

        # Check npm package
        for pkg, adapter_type in DynamicAdapterFactory.ADAPTER_DETECTION.items():
            if pkg in npm.lower():
                logger.debug(
                    "DynamicAdapterFactory: detected {} adapter via npm '{}'",
                    adapter_type,
                    npm,
                )
                return adapter_type

        # Try to detect from API URL patterns
        api_url = provider_data.get("api", "").lower()
        if "anthropic" in api_url:
            return "anthropic_native"
        if "responses" in api_url:
            return "responses_api"

        # Default to OpenAI-compatible (most common)
        logger.debug("DynamicAdapterFactory: defaulting to openai_compat")
        return "openai_compat"

    @staticmethod
    async def create_adapter(
        provider_id: str,
        provider_data: dict[str, Any],
        api_key: str,
        model_id: str,
        **kwargs,
    ) -> DynamicBackendAdapter:
        """Create a dynamic adapter for a provider.

        Args:
            provider_id: Provider ID from models.dev
            provider_data: Provider metadata from models.dev
            api_key: API key for authentication
            model_id: Model ID to use
            **kwargs: Additional options

        Returns:
            DynamicBackendAdapter instance

        Raises:
            ValueError: If provider is not supported or adapter type unknown
        """
        adapter_type = DynamicAdapterFactory.detect_adapter_type(provider_data)
        api_url = provider_data.get("api")
        provider_name = provider_data.get("name", provider_id)

        if not api_url:
            raise ValueError(f"Provider '{provider_id}' missing API URL")

        config = DynamicAdapterConfig(
            provider_id=provider_id,
            provider_name=provider_name,
            api_url=api_url,
            api_key=api_key,
            model_id=model_id,
            **kwargs,
        )

        logger.info(
            "DynamicAdapterFactory: creating {} adapter for {} (model: {})",
            adapter_type,
            provider_id,
            model_id,
        )

        if adapter_type == "anthropic_native":
            return AnthropicNativeAdapter(config)
        elif adapter_type == "openai_compat":
            return OpenAICompatibleAdapter(config)
        elif adapter_type == "responses_api":
            return ResponsesAPIAdapter(config)
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")

    @staticmethod
    def wrap_dynamic_adapter(
        adapter: DynamicBackendAdapter, backend_config: BackendConfig
    ) -> BackendAdapter:
        """Wrap a dynamic adapter to work with the BackendAdapter interface.

        This allows dynamic adapters to be used seamlessly with the rest of claudefree.

        Args:
            adapter: DynamicBackendAdapter instance
            backend_config: BackendConfig for rate limiting, timeouts, etc.

        Returns:
            BackendAdapter-compatible wrapper
        """
        # For now, dynamic adapters are already compatible
        # This method exists for future extensibility (e.g., adding retry logic)
        return adapter
