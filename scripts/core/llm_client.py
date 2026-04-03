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
from dataclasses import dataclass
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
    """Carries raw text and optional token-usage counters from an LLM call."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


# ── Sync helpers (one provider call) ──────────────────────────────────


def _call_gemini_sync(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    from google import genai
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt_text,
        config=config,
    )
    assert response.text is not None, "Gemini returned an empty response"

    input_tokens: int | None = None
    output_tokens: int | None = None
    if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

    return LLMResponse(
        text=response.text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
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
        response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_completion_tokens"] = max_output_tokens

    response = client.chat.completions.create(**create_kwargs)
    result = response.choices[0].message.content
    assert result is not None, (
        f"OpenAI-compat ({base_url or 'default'}) returned an empty response"
    )

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
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
        response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_tokens"] = max_output_tokens

    response = client.chat.complete(**create_kwargs)
    result = response.choices[0].message.content
    assert result is not None, "Mistral returned an empty response"

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
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
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt_text,
        config=config,
    )
    assert response.text is not None, "Gemini returned an empty response"

    input_tokens: int | None = None
    output_tokens: int | None = None
    if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

    return LLMResponse(
        text=response.text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
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
        response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_completion_tokens"] = max_output_tokens

    response = await client.chat.completions.create(**create_kwargs)
    result = response.choices[0].message.content
    assert result is not None, (
        f"OpenAI-compat async ({base_url or 'default'}) returned empty"
    )

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
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
        response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        create_kwargs["max_tokens"] = max_output_tokens

    response = await client.chat.complete_async(**create_kwargs)
    result = response.choices[0].message.content
    assert result is not None, "Mistral async returned an empty response"

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
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
    """Send *prompts* concurrently (capped at *max_concurrency*).

    Returns one ``LLMResponse`` (or exception) per prompt, preserving
    order.  Each slot independently retries with exponential backoff so a
    single flaky request never stalls the rest of the batch.
    """
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
    """Synchronous entry-point for batched inference on any provider.

    Runs all prompts through a single ``asyncio`` event loop, returning
    results in the same order.  Exceptions are returned as values so the
    caller can handle them per-prompt without aborting the batch.
    """
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
