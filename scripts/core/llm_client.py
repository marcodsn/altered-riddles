"""llm_client.py — Unified LLM client for the Altered Riddles benchmark.

Provides sync, async, and batched call interfaces for every provider in config.py.
All functions return LLMResponse.
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
from scripts.core.reasoning import ReasoningPlan

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Raw text, optional reasoning trace, and token-usage counters."""

    text: str
    reasoning: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None


# ── Sync helpers ──────────────────────────────────────────────────────


def _gemini_thinking_config(plan: ReasoningPlan | None):
    from google.genai import types

    if plan is None:
        return types.ThinkingConfig(include_thoughts=True)
    if not plan.enabled:
        return types.ThinkingConfig(include_thoughts=False, thinking_budget=0)
    budget = plan.gemini_thinking_budget
    return types.ThinkingConfig(
        include_thoughts=True,
        thinking_budget=budget if budget is not None else -1,
    )


def _call_gemini_sync(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    reasoning_plan: ReasoningPlan | None = None,
) -> LLMResponse:
    from google import genai
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
        thinking_config=_gemini_thinking_config(reasoning_plan),
    )
    response = client.models.generate_content(model=model, contents=prompt_text, config=config)

    thought_parts, answer_parts = [], []
    for part in response.candidates[0].content.parts:
        if not part.text:
            continue
        (thought_parts if part.thought else answer_parts).append(part.text)

    text = "\n".join(answer_parts)
    assert text, "Gemini returned an empty response"
    reasoning = "\n".join(thought_parts) or None

    input_tokens = output_tokens = reasoning_tokens = None
    if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)
        reasoning_tokens = getattr(response.usage_metadata, "thoughts_token_count", None)

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
    reasoning_plan: ReasoningPlan | None = None,
    is_direct_openai: bool = False,
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
    )
    if max_output_tokens is not None:
        create_kwargs["max_completion_tokens"] = max_output_tokens
    if reasoning_plan is not None:
        if is_direct_openai and reasoning_plan.openai_direct_kwargs:
            create_kwargs.update(reasoning_plan.openai_direct_kwargs)
        elif not is_direct_openai and reasoning_plan.openai_compat_extra:
            create_kwargs["extra_body"] = reasoning_plan.openai_compat_extra

    response = client.chat.completions.create(**create_kwargs)
    message = response.choices[0].message
    result = message.content
    assert result is not None, f"OpenAI-compat ({base_url or 'default'}) returned empty"

    reasoning: str | None = getattr(message, "reasoning_content", None)
    input_tokens = output_tokens = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result, reasoning=reasoning, input_tokens=input_tokens, output_tokens=output_tokens
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
    )
    if max_output_tokens is not None:
        create_kwargs["max_tokens"] = max_output_tokens

    response = client.chat.complete(**create_kwargs)
    message = response.choices[0].message
    result = message.content
    assert result is not None, "Mistral returned an empty response"

    reasoning: str | None = None
    thinking_blocks = getattr(message, "thinking_blocks", None)
    if thinking_blocks:
        reasoning = (
            "\n".join(b.thinking for b in thinking_blocks if getattr(b, "thinking", None)) or None
        )

    input_tokens = output_tokens = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result, reasoning=reasoning, input_tokens=input_tokens, output_tokens=output_tokens
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
    reasoning_plan: ReasoningPlan | None = None,
) -> LLMResponse:
    """Call an LLM with retries + exponential backoff."""
    client_type = get_client_type(provider)
    base_url = get_base_url(provider)
    backoff = INITIAL_BACKOFF_S

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if client_type == "gemini":
                return _call_gemini_sync(
                    prompt_text, model, temperature, api_key, max_output_tokens,
                    reasoning_plan=reasoning_plan,
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
                    reasoning_plan=reasoning_plan,
                    is_direct_openai=(provider == "openai"),
                )
        except Exception as exc:
            logger.warning("Attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(backoff)
            backoff *= 2

    raise RuntimeError("Exhausted retries")


# ── Async helpers ─────────────────────────────────────────────────────


async def _call_gemini_async(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    reasoning_plan: ReasoningPlan | None = None,
) -> LLMResponse:
    from google import genai
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
        thinking_config=_gemini_thinking_config(reasoning_plan),
    )
    response = await client.aio.models.generate_content(
        model=model, contents=prompt_text, config=config
    )

    thought_parts, answer_parts = [], []
    for part in response.candidates[0].content.parts:
        if not part.text:
            continue
        (thought_parts if part.thought else answer_parts).append(part.text)

    text = "\n".join(answer_parts)
    assert text, "Gemini returned an empty response"
    reasoning = "\n".join(thought_parts) or None

    input_tokens = output_tokens = reasoning_tokens = None
    if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)
        reasoning_tokens = getattr(response.usage_metadata, "thoughts_token_count", None)

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
    client: Any | None = None,
    reasoning_plan: ReasoningPlan | None = None,
    is_direct_openai: bool = False,
) -> LLMResponse:
    from openai import AsyncOpenAI

    if client is None:
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = AsyncOpenAI(**client_kwargs)

    create_kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
    )
    if max_output_tokens is not None:
        create_kwargs["max_completion_tokens"] = max_output_tokens
    if reasoning_plan is not None:
        if is_direct_openai and reasoning_plan.openai_direct_kwargs:
            create_kwargs.update(reasoning_plan.openai_direct_kwargs)
        elif not is_direct_openai and reasoning_plan.openai_compat_extra:
            create_kwargs["extra_body"] = reasoning_plan.openai_compat_extra

    response = await client.chat.completions.create(**create_kwargs)
    message = response.choices[0].message
    result = message.content

    # --- DEBUG DUMP ---
    # import json
    # import pathlib
    # import time

    # debug = {
    #     "finish_reason": response.choices[0].finish_reason,
    #     "content": message.content,
    #     "reasoning_content": getattr(message, "reasoning_content", None),
    #     "model": response.model,
    #     "usage": vars(response.usage) if response.usage else None,
    #     "system_fingerprint": getattr(response, "system_fingerprint", None),
    #     "raw_message": str(message),  # full repr in case fields are non-standard
    # }
    # pathlib.Path(f"debug_response_{int(time.time() * 1000)}.json").write_text(
    #     json.dumps(debug, indent=2, default=str), encoding="utf-8"
    # )
    # --- END DEBUG DUMP ---

    assert result is not None, f"OpenAI-compat async ({base_url or 'default'}) returned empty"

    reasoning: str | None = getattr(message, "reasoning_content", None)
    input_tokens = output_tokens = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result, reasoning=reasoning, input_tokens=input_tokens, output_tokens=output_tokens
    )


async def _call_mistral_async(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    client: Any | None = None,
) -> LLMResponse:
    from mistralai.client import Mistral

    if client is None:
        client = Mistral(api_key=api_key)

    create_kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
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
            "\n".join(b.thinking for b in thinking_blocks if getattr(b, "thinking", None)) or None
        )

    input_tokens = output_tokens = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result, reasoning=reasoning, input_tokens=input_tokens, output_tokens=output_tokens
    )


async def _call_provider_async(
    prompt_text: str,
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    client: Any | None = None,
    reasoning_plan: ReasoningPlan | None = None,
) -> LLMResponse:
    client_type = get_client_type(provider)
    base_url = get_base_url(provider)

    if client_type == "gemini":
        return await _call_gemini_async(
            prompt_text, model, temperature, api_key, max_output_tokens,
            reasoning_plan=reasoning_plan,
        )
    elif client_type == "mistral":
        return await _call_mistral_async(
            prompt_text,
            model,
            temperature,
            api_key,
            max_output_tokens,
            client=client,
        )
    else:
        return await _call_openai_compat_async(
            prompt_text,
            model,
            temperature,
            api_key,
            base_url=base_url,
            max_output_tokens=max_output_tokens,
            client=client,
            reasoning_plan=reasoning_plan,
            is_direct_openai=(provider == "openai"),
        )


async def _provider_batch_async(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int = 10,
    reasoning_plan: ReasoningPlan | None = None,
) -> list[LLMResponse | BaseException]:
    semaphore = asyncio.Semaphore(max_concurrency)

    client_type = get_client_type(provider)
    base_url = get_base_url(provider)
    shared_client: Any | None = None

    if client_type == "openai_compat":
        from openai import AsyncOpenAI

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        shared_client = AsyncOpenAI(**client_kwargs)
    elif client_type == "mistral":
        from mistralai.client import Mistral

        shared_client = Mistral(api_key=api_key)

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
                        client=shared_client,
                        reasoning_plan=reasoning_plan,
                    )
                except Exception as exc:
                    logger.warning(
                        "Prompt %d attempt %d/%d failed: %s", idx, attempt, MAX_RETRIES, exc
                    )
                    if attempt == MAX_RETRIES:
                        raise
                    await asyncio.sleep(backoff)
                    backoff *= 2
            raise RuntimeError("Exhausted retries")

    try:
        tasks = [asyncio.create_task(_guarded(i, p)) for i, p in enumerate(prompts)]
        return await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if shared_client is not None:
            if hasattr(shared_client, "aclose"):
                await shared_client.aclose()
            elif hasattr(shared_client, "__aexit__"):
                await shared_client.__aexit__(None, None, None)


def call_llm_batched(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int = 10,
    reasoning_plan: ReasoningPlan | None = None,
) -> list[LLMResponse | BaseException]:
    """Batch-call an LLM with async concurrency. Returns list of results."""
    return asyncio.run(
        _provider_batch_async(
            prompts,
            provider=provider,
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_output_tokens=max_output_tokens,
            max_concurrency=max_concurrency,
            reasoning_plan=reasoning_plan,
        )
    )
