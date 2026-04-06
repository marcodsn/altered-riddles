"""llm_client.py — Unified LLM client for the Altered Riddles benchmark.

Provides sync, async, and batched call interfaces that work with every
provider registered in `config.py`.  All functions return `LLMResponse`
so callers that only need text can simply use `.text`.

This module is the **single source of truth** for talking to LLMs.
No other script should contain provider-specific API call code.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from scripts.core.config import (
    INITIAL_BACKOFF_S,
    MAX_RETRIES,
    get_base_url,
    get_client_type,
)

logger = logging.getLogger(__name__)


# ── Response container ────────────────────────────────────────────────


@dataclass
class LLMResponse:
    """Carries raw text, optional reasoning trace, and token-usage counters."""

    text: str
    reasoning: str | None = None  # chain-of-thought / thinking trace
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None  # Gemini: thoughts_token_count


# ── Sync helpers (one provider call) ──────────────────────────────────


def _call_gemini_sync(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    from google import genai
    from google.genai import types
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
        # Request thought summaries; harmless on non-thinking models.
        thinking_config=types.ThinkingConfig(include_thoughts=True),
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt_text,
        config=config,
    )

    # Separate thought parts from answer parts.
    thought_parts: list[str] = []
    answer_parts: list[str] = []
    for part in response.candidates[0].content.parts:
        if not part.text:
            continue
        (thought_parts if part.thought else answer_parts).append(part.text)

    text = "\n".join(answer_parts)
    assert text, "Gemini returned an empty response"
    reasoning = "\n".join(thought_parts) or None

    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)
        reasoning_tokens = getattr(
            response.usage_metadata, "thoughts_token_count", None
        )

    return LLMResponse(
        text=text,
        reasoning=reasoning,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _call_openai_compat_sync(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    base_url: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    from openai import OpenAI

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)
    create_kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        # response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_completion_tokens"] = max_output_tokens

    response = client.chat.completions.create(**create_kwargs)
    message = response.choices[0].message
    result = message.content
    assert result is not None, (
        f"OpenAI-compat ({base_url or 'default'}) returned an empty response"
    )

    # `reasoning_content` is a non-standard extension supported by DeepSeek R1,
    # Qwen-thinking, and many other OpenAI-compat providers.  Vanilla OpenAI
    # o-series does NOT expose reasoning via the Chat Completions API (only via
    # the newer Responses API), so this will simply be None for those models.
    reasoning: str | None = getattr(message, "reasoning_content", None)

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
        reasoning=reasoning,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _call_mistral_sync(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    from mistralai.client import Mistral

    client = Mistral(api_key=api_key)
    create_kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        # response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_tokens"] = max_output_tokens

    response = client.chat.complete(**create_kwargs)
    message = response.choices[0].message
    result = message.content
    assert result is not None, "Mistral returned an empty response"

    # Magistral and reasoning_effort-enabled models return thinking_blocks —
    # a list of objects each carrying a `.thinking` string.
    reasoning: str | None = None
    thinking_blocks = getattr(message, "thinking_blocks", None)
    if thinking_blocks:
        reasoning = (
            "\n".join(
                b.thinking for b in thinking_blocks if getattr(b, "thinking", None)
            )
            or None
        )

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
        reasoning=reasoning,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


# ── Public sync entry-point ───────────────────────────────────────────


def call_llm(
    prompt_text: str,
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    """Call an LLM with retries + exponential backoff.  Returns ``LLMResponse``."""
    client_type = get_client_type(provider)
    base_url = get_base_url(provider)
    backoff = INITIAL_BACKOFF_S

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if client_type == "gemini":
                return _call_gemini_sync(
                    prompt_text, model, temperature, api_key, max_output_tokens
                )
            elif client_type == "mistral":
                return _call_mistral_sync(
                    prompt_text, model, temperature, api_key, max_output_tokens
                )
            else:
                return _call_openai_compat_sync(
                    prompt_text,
                    model,
                    temperature,
                    api_key,
                    base_url=base_url,
                    max_output_tokens=max_output_tokens,
                )
        except Exception as exc:
            logger.warning(
                "API call attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
            )
            if attempt == MAX_RETRIES:
                raise
            logger.info("Retrying in %.1f s …", backoff)
            time.sleep(backoff)
            backoff *= 2

    raise RuntimeError("Exhausted retries")  # unreachable but satisfies type checkers


# ── Async helpers (one provider call) ─────────────────────────────────


async def _call_gemini_async(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    from google import genai
    from google.genai import types
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(include_thoughts=True),
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt_text,
        config=config,
    )

    thought_parts: list[str] = []
    answer_parts: list[str] = []
    for part in response.candidates[0].content.parts:
        if not part.text:
            continue
        (thought_parts if part.thought else answer_parts).append(part.text)

    text = "\n".join(answer_parts)
    assert text, "Gemini returned an empty response"
    reasoning = "\n".join(thought_parts) or None

    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)
        reasoning_tokens = getattr(
            response.usage_metadata, "thoughts_token_count", None
        )

    return LLMResponse(
        text=text,
        reasoning=reasoning,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


async def _call_openai_compat_async(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    base_url: str | None = None,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    from openai import AsyncOpenAI

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = AsyncOpenAI(**client_kwargs)
    create_kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        # response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_completion_tokens"] = max_output_tokens

    response = await client.chat.completions.create(**create_kwargs)
    message = response.choices[0].message
    result = message.content
    assert result is not None, (
        f"OpenAI-compat async ({base_url or 'default'}) returned empty"
    )

    reasoning: str | None = getattr(message, "reasoning_content", None)

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
        reasoning=reasoning,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def _call_mistral_async(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    from mistralai.client import Mistral

    client = Mistral(api_key=api_key)
    create_kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        # response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_tokens"] = max_output_tokens

    response = await client.chat.complete_async(**create_kwargs)
    message = response.choices[0].message
    result = message.content
    assert result is not None, "Mistral async returned an empty response"

    reasoning: str | None = None
    thinking_blocks = getattr(message, "thinking_blocks", None)
    if thinking_blocks:
        reasoning = (
            "\n".join(
                b.thinking for b in thinking_blocks if getattr(b, "thinking", None)
            )
            or None
        )

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
        reasoning=reasoning,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


# ── Async single-call dispatcher ─────────────────────────────────────


async def _call_provider_async(
    prompt_text: str,
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    """Single async LLM call dispatched by provider."""
    client_type = get_client_type(provider)
    base_url = get_base_url(provider)

    if client_type == "gemini":
        return await _call_gemini_async(
            prompt_text, model, temperature, api_key, max_output_tokens
        )
    elif client_type == "mistral":
        return await _call_mistral_async(
            prompt_text, model, temperature, api_key, max_output_tokens
        )
    else:
        return await _call_openai_compat_async(
            prompt_text,
            model,
            temperature,
            api_key,
            base_url=base_url,
            max_output_tokens=max_output_tokens,
        )


# ── Batched async dispatch ────────────────────────────────────────────

# (unchanged — _provider_batch_async and call_llm_batched are identical to the
# original; they just call _call_provider_async which now returns the richer
# LLMResponse automatically.)


async def _provider_batch_async(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int = 10,
) -> list[LLMResponse | BaseException]:
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _guarded(idx: int, prompt: str) -> LLMResponse:
        async with semaphore:
            backoff = INITIAL_BACKOFF_S
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    return await _call_provider_async(
                        prompt,
                        provider=provider,
                        model=model,
                        temperature=temperature,
                        api_key=api_key,
                        max_output_tokens=max_output_tokens,
                    )
                except Exception as exc:
                    logger.warning(
                        "Prompt %d async attempt %d/%d failed: %s",
                        idx,
                        attempt,
                        MAX_RETRIES,
                        exc,
                    )
                    if attempt == MAX_RETRIES:
                        raise
                    await asyncio.sleep(backoff)
                    backoff *= 2
            raise RuntimeError("Exhausted retries")

    tasks = [asyncio.create_task(_guarded(i, p)) for i, p in enumerate(prompts)]
    return await asyncio.gather(*tasks, return_exceptions=True)  # type: ignore[return-value]


def call_llm_batched(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int = 10,
) -> list[LLMResponse | BaseException]:
    return asyncio.run(
        _provider_batch_async(
            prompts,
            provider=provider,
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_output_tokens=max_output_tokens,
            max_concurrency=max_concurrency,
        )
    )
