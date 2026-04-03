"""config.py — Shared configuration for the Altered Riddles benchmark.

Central registry for LLM providers, generator models, default paths,
and retry settings.  Every LLM-enabled script imports from here instead
of defining its own constants.

To add a new provider
─────────────────────
1. Add an entry to `PROVIDERS` below.
2. Set the corresponding env-var in your `.env` (if applicable).
3. That's it — every script picks it up automatically.
"""

from __future__ import annotations

# ── Provider registry ─────────────────────────────────────────────────
#
# Each key is the name you pass to `--provider`.
#
#   default_model    – used when `--model` is omitted
#   env_key          – environment variable that holds the API key
#                      (None → no key needed, e.g. local servers)
#   client_type      – "gemini" | "openai_compat"
#   base_url         – (optional) override for OpenAI-compatible endpoints
#   api_key_override – (optional) hardcoded key (e.g. "local")
#
# Any OpenAI-compatible provider (Together, Groq, Fireworks, …) can be
# added with client_type="openai_compat" and the right base_url.
# ──────────────────────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    "gemini": {
        "default_model": "gemma-4-31b-it",
        "env_key": "GEMINI_API_KEY",
        "client_type": "gemini",
    },
    "openai": {
        "default_model": "gpt-5.4",
        "env_key": "OPENAI_API_KEY",
        "client_type": "openai_compat",
    },
    "local": {
        "default_model": "qwen3.5-27b",
        "env_key": None,
        "client_type": "openai_compat",
        "base_url": "http://10.8.0.5:8083/v1",
        "api_key_override": "local",
    },
    "mistral": {
        "default_model": "mistral-small-2603",
        "env_key": "MISTRAL_API_KEY",
        "client_type": "mistral",
    },
    # ── Examples — uncomment / adapt as needed ────────────────────────
    # "together": {
    #     "default_model": "meta-llama/Llama-3-70b-chat-hf",
    #     "env_key": "TOGETHER_API_KEY",
    #     "client_type": "openai_compat",
    #     "base_url": "https://api.together.xyz/v1",
    # },
    # "groq": {
    #     "default_model": "llama3-70b-8192",
    #     "env_key": "GROQ_API_KEY",
    #     "client_type": "openai_compat",
    #     "base_url": "https://api.groq.com/openai/v1",
    # },
}

# ── Generator models ──────────────────────────────────────────────────
# Used by ``generate_all.py`` to create riddles from multiple families.
# Mixing families maximises stylistic diversity and equalises any single
# model's reasoning-style bias in the benchmark.

GENERATOR_MODELS: list[dict[str, str]] = [
    # {"provider": "gemini", "model": "gemma-4-31b-it"},
    # {"provider": "openai", "model": "gpt-5.4"},
    {"provider": "local", "model": "qwen3.5-27b"},
    {"provider": "mistral", "model": "mistral-small-2603"},
]

# ── Retry / batching defaults ─────────────────────────────────────────

MAX_RETRIES: int = 3
INITIAL_BACKOFF_S: float = 2.0
DEFAULT_BATCH_SIZE: int = 10

# ── Default paths ─────────────────────────────────────────────────────

DEFAULT_BENCHMARK = "data/benchmark.jsonl"
DEFAULT_POOL = "data/pool.jsonl"
DEFAULT_SOURCE = "data/riddles_source.txt"
DEFAULT_MODEL_OUTPUTS = "data/model_outputs"
DEFAULT_RESULTS = "results"
DEFAULT_GENERATED = "data/generated"
VERSION_FILE = "data/VERSION"

# ── Helpers ───────────────────────────────────────────────────────────


def provider_names() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(PROVIDERS)


def resolve_provider(
    provider: str,
    model: str | None = None,
) -> tuple[str, str]:
    """Return `(resolved_model, api_key)` for *provider*.

    Reads the API key from the environment (via `os.environ`).
    Raises `SystemExit` if a required key is missing.
    """
    import os

    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise SystemExit(
            f"Unknown provider '{provider}'. "
            f"Registered providers: {', '.join(provider_names())}"
        )

    resolved_model = model or cfg["default_model"]

    # API key
    override = cfg.get("api_key_override")
    if override:
        api_key = override
    elif cfg.get("env_key"):
        api_key = os.environ.get(cfg["env_key"], "")
        if not api_key:
            raise SystemExit(
                f"Missing {cfg['env_key']} environment variable for provider "
                f"'{provider}'. Set it in .env or your shell."
            )
    else:
        api_key = "none"

    return resolved_model, api_key


def get_base_url(provider: str) -> str | None:
    """Return the base URL override for *provider*, or ``None``."""
    cfg = PROVIDERS.get(provider, {})
    return cfg.get("base_url")


def get_client_type(provider: str) -> str:
    """Return "gemini", "openai_compat", or "mistral" for *provider*."""
    cfg = PROVIDERS.get(provider, {})
    return cfg.get("client_type", "openai_compat")


def get_benchmark_version() -> str:
    """Read the benchmark version from `data/VERSION`.

    Falls back to the current UTC year-month in `YYMM` format if the
    file does not exist.
    """
    from datetime import datetime, timezone
    from pathlib import Path

    vf = Path(VERSION_FILE)
    if vf.exists():
        return vf.read_text().strip()

    return datetime.now(timezone.utc).strftime("%y%m")
