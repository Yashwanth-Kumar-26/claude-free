"""Canonical list of registered backend IDs.

Must stay in sync with backends/hub.py BACKEND_DESCRIPTORS.
"""

from __future__ import annotations

REGISTERED_BACKEND_IDS: tuple[str, ...] = (
    "nvidia_nim",
    "open_router",
    "opencode_go",   # OpenCode Go — OpenAI chat/completions
    "opencode_zen",  # OpenCode Zen — OpenAI Responses API
)
