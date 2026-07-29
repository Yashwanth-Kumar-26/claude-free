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


def test_shortcut_title_gen():
    from gateway.schemas import MessageParam, MessagesRequest
    from gateway.shortcuts import maybe_title_gen

    # Valid title gen prompts
    req1 = MessagesRequest(
        model="test",
        messages=[MessageParam(role="user", content="generate a short title for this conversation")],
    )
    assert maybe_title_gen(req1) is not None

    req2 = MessagesRequest(
        model="test",
        messages=[MessageParam(role="user", content="suggest a title")],
    )
    assert maybe_title_gen(req2) is not None

    req3 = MessagesRequest(
        model="test",
        messages=[MessageParam(role="user", content="name this conversation")],
    )
    assert maybe_title_gen(req3) is not None

    # Invalid title gen prompts (should not be matched)
    req4 = MessagesRequest(
        model="test",
        messages=[MessageParam(role="user", content="Create a new folder name it Logic and Move make PDF for exam reference")],
    )
    assert maybe_title_gen(req4) is None

    req5 = MessagesRequest(
        model="test",
        messages=[MessageParam(role="user", content="write a function named get_user")],
    )
    assert maybe_title_gen(req5) is None


def test_shortcut_suggestion_mode_requires_probe_shape():
    from gateway.schemas import MessageParam, MessagesRequest
    from gateway.shortcuts import maybe_suggestion_mode

    # Probe-like request should be intercepted
    req_probe = MessagesRequest(
        model="test",
        max_tokens=16,
        messages=[MessageParam(role="user", content="does this model support suggestion mode?")],
    )
    assert maybe_suggestion_mode(req_probe) is not None

    # Normal user prompt should not be intercepted
    req_user = MessagesRequest(
        model="test",
        max_tokens=1024,
        messages=[MessageParam(role="user", content="Can you provide a suggestion to optimize this function?")],
    )
    assert maybe_suggestion_mode(req_user) is None


def test_shortcut_prefix_detect_requires_probe_shape():
    from gateway.schemas import MessageParam, MessagesRequest
    from gateway.shortcuts import maybe_prefix_detect

    # Probe-like request should be intercepted
    req_probe = MessagesRequest(
        model="test",
        max_tokens=16,
        messages=[
            MessageParam(
                role="user",
                content='Complete this prefix: {"type":"human_turn"}',
            )
        ],
    )
    assert maybe_prefix_detect(req_probe) is not None

    # Normal request with JSON snippets should not be intercepted
    req_user = MessagesRequest(
        model="test",
        max_tokens=1024,
        messages=[
            MessageParam(
                role="user",
                content='Please explain this JSON schema {"type":"object","properties":{"name":{"type":"string"}}}',
            )
        ],
    )
    assert maybe_prefix_detect(req_user) is None


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


@pytest.mark.asyncio
async def test_cancelled_client_does_not_start_backend_stream():
    """A disconnected Claude Code client must not dispatch a stale prompt."""
    from types import SimpleNamespace

    from gateway.router import create_message
    from gateway.schemas import MessageParam, MessagesRequest

    class Service:
        called = False

        async def stream(self, body, *, request_id=None):
            self.called = True
            yield "data: unexpected\n\n"

    service = Service()

    class Request:
        def __init__(self):
            self.headers = {"authorization": "Bearer test-key-1"}
            self.app = SimpleNamespace(state=SimpleNamespace(service=service))

        async def is_disconnected(self):
            return True

    response = await create_message(
        MessagesRequest(model="test", messages=[MessageParam(role="user", content="old prompt")]),
        Request(),
    )
    assert [chunk async for chunk in response.body_iterator] == []
    assert service.called is False


@pytest.mark.asyncio
async def test_client_disconnect_closes_active_backend_stream():
    """Esc during streaming closes the upstream generator before it can continue."""
    from types import SimpleNamespace

    from gateway.router import create_message
    from gateway.schemas import MessageParam, MessagesRequest

    class Request:
        def __init__(self):
            self.headers = {"authorization": "Bearer test-key-2"}
            self.disconnected = False

        async def is_disconnected(self):
            return self.disconnected

    request = Request()
    closed = False

    class Service:
        async def stream(self, body, *, request_id=None):
            nonlocal closed
            try:
                request.disconnected = True
                yield "data: old prompt response\n\n"
                yield "data: must not be read\n\n"
            finally:
                closed = True

    request.app = SimpleNamespace(state=SimpleNamespace(service=Service()))
    response = await create_message(
        MessagesRequest(model="test", messages=[MessageParam(role="user", content="old prompt")]),
        request,
    )
    assert [chunk async for chunk in response.body_iterator] == []
    assert closed is True
