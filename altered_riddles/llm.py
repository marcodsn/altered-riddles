"""altered_riddles.llm — one small OpenAI-compatible client for v2.

Every reply carries the token counts the provider reported, including
reasoning tokens, so a run can check that thinking was actually on or off
(the D6 guardrail). Thinking is switched per model family with the request
parameters that were verified to work on Jalapeno Cloud on 2026-09-04; see
PLAN.md section 5 for the table.

Usage:
    from altered_riddles.llm import Client
    client = Client("jalapeno")
    reply = await client.chat("DeepSeek-V4-Flash-0731", [{"role": "user", "content": "..."}],
                              max_tokens=16, thinking=False)
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, RateLimitError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

PROVIDERS: dict[str, dict[str, Any]] = {
    # Jalapeno Cloud (beta): DeepSeek / GLM / Kimi / Qwen / Hy. The paid budget.
    "jalapeno": {"base_url": "https://api.jalapeno-cloud.ai/v1", "env_key": "JALAPENO_API_KEY"},
    # Nous Portal: the `:free` models cost nothing and are rate-limited.
    "nous": {"base_url": "https://inference-api.nousresearch.com/v1", "env_key": "NOUS_API_KEY"},
    # A local vLLM / llama.cpp server. Base URL from LOCAL_BASE_URL.
    "local": {"base_url": os.environ.get("LOCAL_BASE_URL", "http://localhost:8000/v1"), "env_key": None},
}

# Reasons a call is retried: transient by nature, or the provider's own
# "we encountered some issues, please try again" 400.
_TRANSIENT_MARKERS = ("try again", "overloaded", "timeout", "temporarily", "502", "503", "504")


def thinking_extra(model: str, on: bool | None) -> dict[str, Any]:
    """Request parameters that switch thinking on or off for `model`.

    `None` means "provider default, send nothing". Families whose thinking
    cannot be switched on the route (Hy on Jalapeno, instruct-only Qwen) get
    nothing too; the caller must read `Reply.reasoning_tokens` to know what
    actually happened.
    """
    if on is None:
        return {}
    m = model.lower()
    if "deepseek" in m:
        if on:
            return {"reasoning": {"enabled": True}}
        return {"chat_template_kwargs": {"enable_thinking": False}}
    if "glm" in m or "kimi" in m or "moonshot" in m:
        return {"thinking": {"type": "enabled" if on else "disabled"}}
    if "qwen" in m:
        if "instruct" in m:
            return {}
        return {"chat_template_kwargs": {"enable_thinking": bool(on)}}
    if m.startswith("hy") or "hunyuan" in m:
        return {}
    # OpenRouter-style block, the convention on Nous and most aggregators.
    return {"reasoning": {"enabled": bool(on)}}


def switchable(model: str) -> bool:
    """True if `thinking_extra` knows a switch for this model family."""
    return bool(thinking_extra(model, False)) or bool(thinking_extra(model, True))


@dataclass
class Reply:
    model: str
    text: str
    reasoning: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    finish_reason: str | None
    latency_s: float
    attempts: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "text": self.text,
            "reasoning": self.reasoning,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "finish_reason": self.finish_reason,
            "latency_s": round(self.latency_s, 3),
            "attempts": self.attempts,
            "error": self.error,
        }


def _usage_field(usage: Any, *path: str) -> int | None:
    node = usage
    for key in path:
        if node is None:
            return None
        node = getattr(node, key, None) if not isinstance(node, dict) else node.get(key)
    return node if isinstance(node, int) else None


class Client:
    def __init__(self, provider: str, *, concurrency: int = 8, timeout: float = 180.0, retries: int = 5):
        if provider not in PROVIDERS:
            raise SystemExit(f"Unknown provider {provider!r}; known: {', '.join(PROVIDERS)}")
        cfg = PROVIDERS[provider]
        key = os.environ.get(cfg["env_key"], "") if cfg["env_key"] else "local"
        if not key:
            raise SystemExit(f"Missing {cfg['env_key']} in .env for provider {provider!r}")
        self.provider = provider
        self._client = AsyncOpenAI(base_url=cfg["base_url"], api_key=key, timeout=timeout, max_retries=0)
        self._sem = asyncio.Semaphore(concurrency)
        self.retries = retries

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float | None = None,
        thinking: bool | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> Reply:
        body: dict[str, Any] = dict(thinking_extra(model, thinking))
        if extra_body:
            body.update(extra_body)
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if body:
            kwargs["extra_body"] = body

        t0 = time.monotonic()
        last_err = "no attempts"
        for attempt in range(1, self.retries + 1):
            async with self._sem:
                try:
                    resp = await self._client.chat.completions.create(**kwargs)
                    choice = resp.choices[0] if resp.choices else None
                    msg = choice.message if choice is not None else None
                    if msg is None:
                        raise APIError("empty choices", request=None, body=None)  # type: ignore[arg-type]
                    text = msg.content or ""
                    reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
                    if reasoning is None and hasattr(msg, "model_extra") and msg.model_extra:
                        reasoning = msg.model_extra.get("reasoning_content") or msg.model_extra.get("reasoning")
                    usage = resp.usage
                    rt = _usage_field(usage, "completion_tokens_details", "reasoning_tokens")
                    if rt is None:
                        rt = _usage_field(usage, "reasoning_tokens")
                    return Reply(
                        model=model,
                        text=text,
                        reasoning=reasoning if isinstance(reasoning, str) else None,
                        prompt_tokens=_usage_field(usage, "prompt_tokens"),
                        completion_tokens=_usage_field(usage, "completion_tokens"),
                        reasoning_tokens=rt,
                        finish_reason=getattr(choice, "finish_reason", None),
                        latency_s=time.monotonic() - t0,
                        attempts=attempt,
                    )
                except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                    last_err = f"{type(e).__name__}: {e}"
                except APIError as e:
                    last_err = f"{type(e).__name__}: {e}"
                    status = getattr(e, "status_code", None)
                    transient = (status is not None and status >= 500) or any(
                        marker in str(e).lower() for marker in _TRANSIENT_MARKERS
                    )
                    if not transient:
                        break
                except Exception as e:  # noqa: BLE001 — record, then retry
                    last_err = f"{type(e).__name__}: {e}"
            await asyncio.sleep(min(60.0, (2 ** attempt) + random.uniform(0, 1)))
        return Reply(
            model=model, text="", reasoning=None, prompt_tokens=None, completion_tokens=None,
            reasoning_tokens=None, finish_reason=None, latency_s=time.monotonic() - t0,
            attempts=self.retries, error=last_err[:500],
        )


async def gather_limited(coros, *, progress_every: int = 0, label: str = "") -> list:
    """Run coroutines concurrently (the Client's semaphore bounds concurrency)
    and return results in order. Prints progress to stderr if asked."""
    import sys

    results = [None] * len(coros)
    done = 0

    async def run(i, c):
        nonlocal done
        results[i] = await c
        done += 1
        if progress_every and done % progress_every == 0:
            print(f"  {label}{done}/{len(coros)}", file=sys.stderr, flush=True)

    await asyncio.gather(*(run(i, c) for i, c in enumerate(coros)))
    return results
