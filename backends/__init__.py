"""Backends package — LLM adapters for claudefree."""
from .base import BackendAdapter, BackendConfig
from .exceptions import BackendError, UnknownBackendError
from .hub import BackendHub, get_hub

__all__ = [
    "BackendAdapter",
    "BackendConfig",
    "BackendError",
    "BackendHub",
    "UnknownBackendError",
    "get_hub",
]
