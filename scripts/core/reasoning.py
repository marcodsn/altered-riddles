"""reasoning.py — Reasoning-mode dispatch for the benchmark.

Maps (provider, model, reasoning_enabled, effort) to the API-specific
parameters each backend expects. Provider-neutral on the outside; the
per-backend call sites in llm_client.py ask for the piece they need.
"""

from __future__ import annotations

from dataclasses import dataclass, field

EFFORTS: tuple[str, ...] = ("minimal", "low", "medium", "high", "xhigh")
DEFAULT_EFFORT = "high"

# effort → max_tokens (used for Anthropic/Gemini via OpenRouter-style APIs
# and for Gemini native thinking_budget when positive).
_EFFORT_TO_TOKENS: dict[str, int] = {
    "minimal": 1024,
    "low": 4096,
    "medium": 8192,
    "high": 16384,
    "xhigh": 32768,
}

# effort → verbosity label for models using adaptive-only thinking.
# "minimal" has no direct verbosity equivalent, so it falls back to "low".
_EFFORT_TO_VERBOSITY: dict[str, str] = {
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
}


def _is_adaptive_only(model: str) -> bool:
    """Return True for models that use adaptive thinking exclusively.

    Claude 4.7 Opus ignores reasoning.max_tokens / reasoning.effort and
    requires verbosity to control response effort instead.
    """
    m = model.lower()
    # Match both raw and OpenRouter-prefixed forms:
    #   "claude-4.7-opus", "anthropic/claude-4.7-opus", etc.
    return "4.7" in m and "opus" in m


@dataclass
class ReasoningPlan:
    enabled: bool
    effort: str | None = None
    # For Gemini native SDK: -1 = dynamic, 0 = off, >0 = fixed budget.
    gemini_thinking_budget: int | None = None
    # For OpenAI-compat `extra_body` (merged into create() call).
    openai_compat_extra: dict = field(default_factory=dict)
    # For direct openai provider: kwargs passed to chat.completions.create.
    openai_direct_kwargs: dict = field(default_factory=dict)

    @property
    def tag(self) -> str:
        """Filename suffix fragment, e.g. '_reasoning-high' or ''."""
        if not self.enabled:
            return ""
        return f"_reasoning-{self.effort or DEFAULT_EFFORT}"


def _model_family(model: str) -> str:
    m = model.lower()
    if m.startswith("anthropic/") or m.startswith("claude"):
        return "anthropic"
    if m.startswith("google/") or m.startswith("gemini") or m.startswith("gemma"):
        return "google"
    if (
        m.startswith("openai/")
        or m.startswith("gpt")
        or m.startswith("o1")
        or m.startswith("o3")
    ):
        return "openai"
    if m.startswith("qwen/") or m.startswith("qwen") or m.startswith("alibaba/"):
        return "qwen"
    return "other"


def build_plan(
    *,
    provider: str,
    model: str,
    reasoning: bool,
    effort: str | None = None,
) -> ReasoningPlan:
    """Build a provider-appropriate reasoning plan.

    `reasoning=False` disables thinking via each backend's preferred knob.
    `reasoning=True` enables it at the given effort (default 'high').
    """
    if effort is not None and effort not in EFFORTS:
        raise ValueError(f"Unknown reasoning effort: {effort!r}. Valid: {EFFORTS}")

    eff = effort or DEFAULT_EFFORT
    family = _model_family(model)

    # Gemini native SDK
    if provider == "gemini":
        if not reasoning:
            return ReasoningPlan(enabled=False, gemini_thinking_budget=0)
        budget = -1 if eff == "xhigh" else _EFFORT_TO_TOKENS[eff]
        return ReasoningPlan(enabled=True, effort=eff, gemini_thinking_budget=budget)

    # Direct OpenAI (chat.completions)
    if provider == "openai":
        if not reasoning:
            # Chat completions doesn't accept effort="none"; omit param and
            # additionally request minimal reasoning where available.
            return ReasoningPlan(
                enabled=False, openai_direct_kwargs={"reasoning_effort": "minimal"}
            )
        eff_mapped = "high" if eff == "xhigh" else eff  # 'xhigh' unsupported here
        return ReasoningPlan(
            enabled=True,
            effort=eff,
            openai_direct_kwargs={"reasoning_effort": eff_mapped},
        )

    # Local: reasoning is toggled via the model tag (e.g. `:reasoning`).
    # We don't inject API params; record the flag only.
    if provider == "local":
        return ReasoningPlan(enabled=reasoning, effort=eff if reasoning else None)

    # Mistral: no supported reasoning control; pass through.
    if provider == "mistral":
        return ReasoningPlan(enabled=reasoning, effort=eff if reasoning else None)

    # OpenAI-compatible aggregators (nous, together, hf): use OpenRouter-style
    # `reasoning` block in extra_body, routed by model family.
    reasoning_block: dict
    extra: dict

    if family == "anthropic":
        if _is_adaptive_only(model):
            # Claude 4.7 Opus: adaptive thinking only — reasoning.max_tokens
            # and reasoning.effort are ignored. Use verbosity to set effort,
            # and only pass reasoning.enabled to toggle thinking on/off.
            if not reasoning:
                extra = {"reasoning": {"enabled": False}}
            else:
                extra = {
                    "reasoning": {"enabled": True},
                    "verbosity": _EFFORT_TO_VERBOSITY[eff],
                }
        else:
            # Older Anthropic models (4.5 and below): budget-based thinking.
            if not reasoning:
                extra = {
                    "reasoning": {"enabled": False, "max_tokens": 1, "exclude": False}
                }
            else:
                extra = {
                    "reasoning": {
                        "enabled": True,
                        "max_tokens": _EFFORT_TO_TOKENS[eff],
                        "exclude": False,
                    }
                }

        return ReasoningPlan(
            enabled=reasoning,
            effort=eff if reasoning else None,
            openai_compat_extra=extra,
        )

    elif family == "google":
        if not reasoning:
            reasoning_block = {"enabled": False, "max_tokens": 1, "exclude": False}
        else:
            reasoning_block = {
                "enabled": True,
                "max_tokens": _EFFORT_TO_TOKENS[eff],
                "exclude": False,
            }
    elif family == "openai":
        if not reasoning:
            reasoning_block = {"enabled": False, "effort": "none", "exclude": False}
        else:
            eff_mapped = "high" if eff == "xhigh" else eff
            reasoning_block = {"enabled": True, "effort": eff_mapped, "exclude": False}
    elif family == "qwen":
        if not reasoning:
            reasoning_block = {"enabled": False, "exclude": False}
        else:
            eff_mapped = "high" if eff == "xhigh" else eff
            reasoning_block = {"enabled": True, "effort": eff_mapped, "exclude": False}
    else:
        reasoning_block = {"enabled": bool(reasoning), "exclude": False}

    return ReasoningPlan(
        enabled=reasoning,
        effort=eff if reasoning else None,
        openai_compat_extra={"reasoning": reasoning_block},
    )
