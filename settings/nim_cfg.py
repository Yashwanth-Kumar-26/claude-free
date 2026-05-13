"""NIM-specific configuration (chat template selection, reasoning budget)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NimChatTemplateConfig:
    """Per-model chat-template override sent in extra_body."""

    template: str | None = None


# Models that require extended reasoning budget
_REASONING_MODELS: frozenset[str] = frozenset(
    {
        "moonshotai/kimi-k2.5",
        "minimaxai/minimax-m2.5",
        "z-ai/glm5",
        "z-ai/glm4.7",
        "qwen/qwen3.5-397b-a17b",
    }
)

# Baseline reasoning budget per model (tokens)
_DEFAULT_BUDGETS: dict[str, int] = {
    "moonshotai/kimi-k2.5": 10000,
    "minimaxai/minimax-m2.5": 8000,
    "z-ai/glm5": 8000,
    "z-ai/glm4.7": 6000,
    "qwen/qwen3.5-397b-a17b": 12000,
}


@dataclass
class NimConfig:
    """Runtime NIM settings derived from env."""

    reasoning_budget: int = field(default=8000)
    enable_chat_template: bool = field(default=True)

    def budget_for(self, model: str) -> int:
        """Return reasoning budget for a specific model name."""
        for key, budget in _DEFAULT_BUDGETS.items():
            if key in model:
                return budget
        return self.reasoning_budget

    def needs_reasoning(self, model: str) -> bool:
        return any(m in model for m in _REASONING_MODELS)
