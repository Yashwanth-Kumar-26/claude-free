"""Model selector — maps incoming Claude model names to backend/model pairs."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from settings.env import Settings

from .schemas import MessagesRequest, TokenCountRequest


@dataclass(frozen=True, slots=True)
class Selection:
    original_model:  str
    backend_id:      str
    backend_model:   str
    backend_ref:     str   # full "backend_id/model_name"


@dataclass(frozen=True, slots=True)
class RoutedRequest:
    request:   MessagesRequest
    selection: Selection


@dataclass(frozen=True, slots=True)
class RoutedTokenCount:
    request:   TokenCountRequest
    selection: Selection


class ModelSelector:
    """Resolve incoming Claude model identifiers to concrete backends."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def select(self, claude_model: str) -> Selection:
        if not claude_model or not isinstance(claude_model, str):
            raise ValueError(f"Invalid model name: {claude_model!r}. Model name must be a non-empty string.")
        ref        = self._s.resolve_model(claude_model)
        backend_id, backend_model = Settings.split_backend(ref)
        if backend_model != claude_model:
            logger.debug("MODEL SELECT: '{}' → '{}'", claude_model, backend_model)
        return Selection(
            original_model  = claude_model,
            backend_id      = backend_id,
            backend_model   = backend_model,
            backend_ref     = ref,
        )

    def route_messages(self, req: MessagesRequest) -> RoutedRequest:
        sel    = self.select(req.model)
        routed = req.model_copy(deep=True)
        routed.model                  = sel.backend_model
        routed.original_model         = sel.original_model
        routed.resolved_provider_model = sel.backend_ref
        return RoutedRequest(request=routed, selection=sel)

    def route_token_count(self, req: TokenCountRequest) -> RoutedTokenCount:
        sel    = self.select(req.model)
        routed = req.model_copy(update={"model": sel.backend_model}, deep=True)
        return RoutedTokenCount(request=routed, selection=sel)
