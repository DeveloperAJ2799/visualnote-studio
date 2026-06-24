"""Low-level LLM wrapper for council members.

A thin chat-completions caller that:
- Accepts an explicit `model` id per call (so the council can use different
  free models per member).
- Retries with exponential backoff on transient failures (timeout, 5xx, 429).
- Validates the response is non-empty and, if `json_mode=True`, parses it.
- Logs every call with model, prompt-token estimate, and wall time.

This module deliberately knows nothing about member roles or prompts.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)


# Cheap/fast models we fall back to if a primary free model 5xx's or 429's.
# Order matters: first available wins.
_FALLBACK_CHAIN = [
    "openrouter/free",
    "kilo-auto/free",
]


@dataclass
class CouncilCallResult:
    """The outcome of a single LLM call."""

    text: str
    model: str
    attempts: int
    elapsed_s: float
    fallback_used: bool = False
    error: Optional[str] = None


class CouncilLLMError(RuntimeError):
    """Raised when an LLM call fails after exhausting retries + fallbacks."""


def chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    *,
    json_mode: bool = False,
    temperature: float = 0.4,
    timeout_s: float = 120.0,
    max_retries: int = 3,
    fallback_models: Optional[List[str]] = None,
) -> CouncilCallResult:
    """Call the chat-completions endpoint with retry + fallback.

    Args:
        base_url: e.g. ``https://api.kilo.ai/api/gateway``.
        api_key: Bearer token.
        model: Primary model id (e.g. ``openrouter/free``).
        messages: OpenAI-style ``[{"role": ..., "content": ...}, ...]``.
        json_mode: If True, request ``response_format={"type":"json_object"}``
            and parse the response as JSON.
        temperature: Sampling temperature.
        timeout_s: Per-attempt timeout.
        max_retries: Retries on the primary model before falling back.
        fallback_models: Additional models to try after primary fails.
            Defaults to the module-level ``_FALLBACK_CHAIN``.

    Returns:
        A ``CouncilCallResult`` with the response text and metadata.

    Raises:
        CouncilLLMError: If every model in the chain fails.
    """
    fallbacks = list(fallback_models or _FALLBACK_CHAIN)
    chain: List[str] = [model] + [m for m in fallbacks if m != model]
    last_error: Optional[str] = None
    total_attempts = 0
    start = time.perf_counter()

    for idx, current_model in enumerate(chain):
        is_fallback = idx > 0
        for attempt in range(1, max_retries + 1):
            total_attempts += 1
            attempt_start = time.perf_counter()
            try:
                text = _do_call(
                    base_url=base_url,
                    api_key=api_key,
                    model=current_model,
                    messages=messages,
                    json_mode=json_mode,
                    temperature=temperature,
                    timeout_s=timeout_s,
                )
                elapsed = time.perf_counter() - start
                log.debug(
                    "council llm ok: model=%s attempt=%d elapsed=%.1fs",
                    current_model, attempt, elapsed,
                )
                return CouncilCallResult(
                    text=text,
                    model=current_model,
                    attempts=total_attempts,
                    elapsed_s=elapsed,
                    fallback_used=is_fallback,
                )
            except (_TransientError, httpx.TimeoutException) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                wait = min(2 ** attempt, 8)
                log.warning(
                    "council llm transient (model=%s attempt=%d): %s; retrying in %ds",
                    current_model, attempt, exc, wait,
                )
                if attempt < max_retries:
                    time.sleep(wait)
            except _PermanentError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning(
                    "council llm permanent (model=%s attempt=%d): %s; trying next model",
                    current_model, attempt, exc,
                )
                break  # do not retry this model further
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning(
                    "council llm unexpected (model=%s attempt=%d): %s",
                    current_model, attempt, exc,
                )
                if attempt >= max_retries:
                    break

    raise CouncilLLMError(
        f"All models in chain failed after {total_attempts} attempts. "
        f"Last error: {last_error}"
    )


def _do_call(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    json_mode: bool,
    temperature: float,
    timeout_s: float,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=timeout_s)
    except httpx.TimeoutException as exc:
        raise _TransientError(f"timeout after {timeout_s}s") from exc
    except httpx.HTTPError as exc:
        raise _TransientError(f"http error: {exc}") from exc

    status = resp.status_code
    if status == 429 or 500 <= status < 600:
        raise _TransientError(f"status {status}: {resp.text[:200]}")
    if status >= 400:
        raise _PermanentError(f"status {status}: {resp.text[:200]}")

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise _PermanentError(f"non-JSON response: {resp.text[:200]}") from exc

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise _PermanentError(f"unexpected response shape: {exc}") from exc

    if not isinstance(text, str) or not text.strip():
        raise _PermanentError("empty response content")

    if json_mode:
        parsed = _parse_json_lenient(text)
        return json.dumps(parsed, ensure_ascii=False)

    return text


class _TransientError(Exception):
    """Retryable error (timeout, 429, 5xx, network)."""


class _PermanentError(Exception):
    """Non-retryable error (4xx other than 429, bad shape)."""


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json_lenient(text: str) -> Any:
    """Parse JSON, tolerating stray markdown fences and surrounding prose."""
    cleaned = _JSON_FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                raise CouncilLLMError(
                    f"Failed to parse LLM JSON: {exc}\n--- payload ---\n{cleaned[:1000]}"
                ) from exc
        raise CouncilLLMError(
            f"Failed to parse LLM JSON: no JSON object/array found\n"
            f"--- payload ---\n{cleaned[:1000]}"
        )
