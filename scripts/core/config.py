"""config.py — Shared configuration for the Altered Riddles benchmark."""

from __future__ import annotations

# Provider registry. Each key is the name passed to --provider.
# client_type: "gemini" | "openai_compat" | "mistral"
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
    "hf": {
        "default_model": "zai-org/GLM-5:fireworks-ai",
        "env_key": "HF_API_KEY",
        "base_url": "https://router.huggingface.co/v1",
        "client_type": "openai_compat",
    },
    "together": {
        "default_model": "zai-org/GLM-5",
        "env_key": "TOGETHER_API_KEY",
        "client_type": "openai_compat",
        "base_url": "https://api.together.xyz/v1",
    },
    "nous": {
        "default_model": "xiaomi/mimo-v2-pro",
        "env_key": "NOUS_API_KEY",
        "client_type": "openai_compat",
        "base_url": "https://inference-api.nousresearch.com/v1",
    },
}

# Retry / batching defaults
MAX_RETRIES: int = 3
INITIAL_BACKOFF_S: float = 2.0
DEFAULT_BATCH_SIZE: int = 10

# Default paths
DEFAULT_SOURCE = "data/riddles_source.csv"
DEFAULT_SANITY_RESULTS = "data/sanity/results.json"
DEFAULT_RAW = "data/generated/raw.jsonl"
DEFAULT_VALIDATED = "data/generated/validated.jsonl"
DEFAULT_REJECTED = "data/generated/rejected.jsonl"
DEFAULT_HUMAN_REJECTED = "data/generated/human_rejected.jsonl"
DEFAULT_POOL = "data/pool.jsonl"
DEFAULT_BENCHMARK = "data/benchmark.jsonl"
DEFAULT_BENCHMARK_FIXED = "data/benchmark_fixed.jsonl"
DEFAULT_MODEL_OUTPUTS = "data/model_outputs"
DEFAULT_RESULTS = "results"


def provider_names() -> list[str]:
    return sorted(PROVIDERS)


def resolve_provider(provider: str, model: str | None = None) -> tuple[str, str]:
    """Return (resolved_model, api_key) for a provider."""
    import os

    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise SystemExit(
            f"Unknown provider '{provider}'. Registered: {', '.join(provider_names())}"
        )
    resolved_model = model or cfg["default_model"]

    override = cfg.get("api_key_override")
    if override:
        api_key = override
    elif cfg.get("env_key"):
        api_key = os.environ.get(cfg["env_key"], "")
        if not api_key:
            raise SystemExit(f"Missing {cfg['env_key']} for provider '{provider}'.")
    else:
        api_key = "none"

    return resolved_model, api_key


def get_base_url(provider: str) -> str | None:
    return PROVIDERS.get(provider, {}).get("base_url")


def get_client_type(provider: str) -> str:
    return PROVIDERS.get(provider, {}).get("client_type", "openai_compat")
