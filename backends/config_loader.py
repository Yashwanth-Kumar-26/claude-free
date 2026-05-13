"""Configuration loader — loads config.json and .env files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger


class ConfigLoader:
    """Loads configuration from config.json and .env files."""

    def __init__(self, config_dir: Path | None = None):
        """Initialize config loader.

        Args:
            config_dir: Directory containing config.json.
                       Defaults to current working directory or CLAUDEFREE_CONFIG_DIR env var.
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Check env var first
            env_config_dir = os.getenv("CLAUDEFREE_CONFIG_DIR")
            if env_config_dir:
                self.config_dir = Path(env_config_dir)
            else:
                # Default to current working directory
                self.config_dir = Path.cwd()

        self.config_file = self.config_dir / "config.json"
        self._config: dict[str, Any] | None = None

    def load_config(self) -> dict[str, Any]:
        """Load configuration from config.json.

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If config.json not found
            json.JSONDecodeError: If config.json is invalid JSON
        """
        if self._config:
            return self._config

        if not self.config_file.exists():
            raise FileNotFoundError(
                f"config.json not found at {self.config_file}. "
                f"Run 'setup.sh' to create configuration."
            )

        try:
            logger.info("ConfigLoader: loading config from {}", self.config_file)
            with open(self.config_file) as f:
                self._config = json.load(f)
            logger.debug(
                "ConfigLoader: loaded config with keys: {}", list(self._config.keys())
            )
            return self._config
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Invalid JSON in {self.config_file}: {e.msg}", e.doc, e.pos
            ) from e
        except Exception as e:
            logger.error("ConfigLoader: failed to load config: {}", e)
            raise

    def get_provider(self) -> str:
        """Get selected provider ID from config.

        Returns:
            Provider ID
        """
        config = self.load_config()
        provider = config.get("provider")
        if not provider:
            raise ValueError("config.json missing 'provider' field")
        return provider

    def get_model(self, tier: str = "default") -> str:
        """Get model ID for a tier.

        Args:
            tier: Model tier ('default', 'opus', 'sonnet', 'haiku')

        Returns:
            Model ID
        """
        config = self.load_config()
        tier_lower = tier.lower()
        model_key = f"model_{tier_lower}"

        model = config.get(model_key)
        if not model:
            raise ValueError(f"config.json missing '{model_key}' field")

        # Handle "SAME_AS_DEFAULT" - resolve to actual model
        if model == "[SAME_AS_DEFAULT]":
            default_model = config.get("model_default")
            if not default_model:
                raise ValueError("config.json missing 'model_default' field")
            return default_model

        return model

    def get_all_models(self) -> dict[str, str]:
        """Get all model mappings.

        Returns:
            Dictionary with keys: default, opus, sonnet, haiku
        """
        config = self.load_config()

        default_model = config.get("model_default")
        if not default_model:
            raise ValueError("config.json missing 'model_default' field")

        # Resolve all [SAME_AS_DEFAULT] to actual default model
        return {
            "default": default_model,
            "opus": config.get("model_opus", default_model)
            if config.get("model_opus") != "[SAME_AS_DEFAULT]"
            else default_model,
            "sonnet": config.get("model_sonnet", default_model)
            if config.get("model_sonnet") != "[SAME_AS_DEFAULT]"
            else default_model,
            "haiku": config.get("model_haiku", default_model)
            if config.get("model_haiku") != "[SAME_AS_DEFAULT]"
            else default_model,
        }

    def load_env_file(self, env_file: Path | None = None) -> dict[str, str]:
        """Load environment variables from .env file.

        Args:
            env_file: Path to .env file. Defaults to .env in config_dir.

        Returns:
            Dictionary of environment variables
        """
        if not env_file:
            env_file = self.config_dir / ".env"

        if not env_file.exists():
            logger.warning("ConfigLoader: .env file not found at {}", env_file)
            return {}

        env_vars = {}
        try:
            logger.debug("ConfigLoader: loading .env from {}", env_file)
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue
                    # Parse KEY=VALUE
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip().upper()
                        value = value.strip().strip("\"'")
                        env_vars[key] = value

            logger.debug("ConfigLoader: loaded {} env vars from .env", len(env_vars))
            return env_vars
        except Exception as e:
            logger.error("ConfigLoader: failed to load .env: {}", e)
            raise

    def get_api_key(
        self, provider_id: str, env_vars: dict[str, str] | None = None
    ) -> str:
        """Get API key for a provider from environment variables.

        Args:
            provider_id: Provider ID (e.g., 'openrouter', 'anthropic')
            env_vars: Environment variables dict. If not provided, loads from .env.

        Returns:
            API key

        Raises:
            ValueError: If API key not found
        """
        if env_vars is None:
            env_vars = self.load_env_file()

        # Try common API key environment variable patterns
        api_key_names = [
            f"{provider_id.upper()}_API_KEY",
            f"{provider_id.upper()}_KEY",
            f"PROVIDER_{provider_id.upper()}_KEY",
        ]

        for key_name in api_key_names:
            if key_name in env_vars:
                api_key = env_vars[key_name]
                if api_key:
                    logger.debug(
                        "ConfigLoader: found API key for {} via {}", provider_id, key_name
                    )
                    return api_key

        raise ValueError(
            f"API key not found for provider '{provider_id}'. "
            f"Expected one of: {', '.join(api_key_names)}"
        )


# Global loader instance
_loader: ConfigLoader | None = None


def get_loader(config_dir: Path | None = None) -> ConfigLoader:
    """Get or create the global config loader.

    Args:
        config_dir: Configuration directory (optional)

    Returns:
        ConfigLoader instance
    """
    global _loader
    if _loader is None:
        _loader = ConfigLoader(config_dir)
    return _loader
