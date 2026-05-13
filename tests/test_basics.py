"""Basic smoke tests for the claudefree gateway."""

from __future__ import annotations

import pytest


def test_backend_ids_sync():
    """BACKEND_DESCRIPTORS and _FACTORIES must have identical keys."""
    from backends.hub import _FACTORIES, BACKEND_DESCRIPTORS
    assert set(BACKEND_DESCRIPTORS.keys()) == set(_FACTORIES.keys())


def test_registered_backend_ids_subset_of_descriptors():
    """Every REGISTERED_BACKEND_ID must appear in BACKEND_DESCRIPTORS."""
    from backends.hub import BACKEND_DESCRIPTORS
    from settings.backend_ids import REGISTERED_BACKEND_IDS
    for bid in REGISTERED_BACKEND_IDS:
        assert bid in BACKEND_DESCRIPTORS, f"Missing descriptor for '{bid}'"


def test_opencode_go_in_registry():
    from backends.hub import BACKEND_DESCRIPTORS
    assert "opencode_go" in BACKEND_DESCRIPTORS


def test_opencode_zen_in_registry():
    from backends.hub import BACKEND_DESCRIPTORS
    assert "opencode_zen" in BACKEND_DESCRIPTORS



def test_settings_model_validation_valid():
    from settings.env import Settings
    s = Settings(
        model="nvidia_nim/test-model",
        _env_file=None,
    )
    assert s.default_backend_id == "nvidia_nim"


def test_settings_model_validation_invalid():
    from pydantic import ValidationError
    with pytest.raises((ValueError, ValidationError)):
        from settings.env import Settings
        Settings(model="unknown_backend/model", _env_file=None)


def test_think_parser_basic():
    from engine.thinking import ChunkKind, ThinkParser
    parser = ThinkParser()
    chunks = list(parser.feed("Hello <think>thinking here</think> world"))
    kinds  = [c.kind for c in chunks]
    assert ChunkKind.TEXT     in kinds
    assert ChunkKind.THINKING in kinds


def test_token_count_basic():
    """Token counter should return a positive value for a simple message."""
    from engine.tokens import count_tokens

    class FakeMsg:
        role    = "user"
        content = "Hello world"

    n = count_tokens([FakeMsg()])
    assert n > 0


def test_shortcut_quota_probe():
    from gateway.schemas import MessageParam, MessagesRequest
    from gateway.shortcuts import maybe_quota_probe

    req = MessagesRequest(
        model="test",
        messages=[MessageParam(role="user", content="hi")],
    )
    result = maybe_quota_probe(req)
    assert result is not None


def test_model_selector_resolve():
    from gateway.selector import ModelSelector
    from settings.env import Settings

    class _FakeSettings:
        def resolve_model(self, m):
            return "opencode_go/anthropic/claude-sonnet-4-5"
        @staticmethod
        def split_backend(s):
            return Settings.split_backend(s)

    sel = ModelSelector(_FakeSettings())
    s   = sel.select("claude-sonnet-4-5")
    assert s.backend_id    == "opencode_go"
    assert s.backend_model == "anthropic/claude-sonnet-4-5"
