"""Provider selection helpers for AIShoppingService.

Kept separate from agent.py so provider wiring (env/config inspection,
OpenAI SDK construction) can evolve without touching the core service.
Selection order: explicit callable > OpenAI > Featherless > none
(deterministic fallback).
"""

from __future__ import annotations

from typing import Any

OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
FEATHERLESS_DEFAULT_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"


def select_provider(config: Any) -> dict:
    """Inspect config and describe the provider to use.

    Returns {"name": 'openai'|'featherless'|'', "model": str,
             "client_kwargs": dict}. Empty name means: no credentials, the
    service must use its deterministic fallback.
    """
    provider = (getattr(config, "AI_PROVIDER", "") or "").strip().lower()
    model = (getattr(config, "AI_MODEL", "") or "").strip()
    openai_key = getattr(config, "OPENAI_API_KEY", "") or ""
    featherless_key = getattr(config, "FEATHERLESS_API_KEY", "") or ""
    featherless_base = getattr(config, "FEATHERLESS_BASE_URL", "") or FEATHERLESS_BASE_URL

    if provider and provider not in {"openai", "featherless"}:
        raise ValueError("AI_PROVIDER must be 'openai' or 'featherless'.")
    if provider == "openai" and not openai_key:
        raise RuntimeError("AI_PROVIDER=openai requires OPENAI_API_KEY.")
    if provider == "featherless" and not featherless_key:
        raise RuntimeError("AI_PROVIDER=featherless requires FEATHERLESS_API_KEY.")

    if provider == "openai" or (not provider and openai_key):
        return {
            "name": "openai",
            "model": model or OPENAI_DEFAULT_MODEL,
            "client_kwargs": {"api_key": openai_key},
        }
    if provider == "featherless" or (not provider and featherless_key):
        return {
            "name": "featherless",
            "model": model or FEATHERLESS_DEFAULT_MODEL,
            "client_kwargs": {"api_key": featherless_key, "base_url": featherless_base},
        }
    return {"name": "", "model": "", "client_kwargs": {}}


def build_client(client_kwargs: dict) -> Any:
    """Build an OpenAI SDK client (works for Featherless via base_url)."""
    try:
        import openai  # deferred import: only needed in provider-backed mode
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openai SDK required for provider-backed mode") from exc
    return openai.OpenAI(**client_kwargs)


def complete(client: Any, model: str, messages: list[dict]) -> str | None:
    """One JSON-mode chat completion. Returns the raw content string."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return response.choices[0].message.content
