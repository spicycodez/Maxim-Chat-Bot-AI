from typing import Protocol, runtime_checkable
from loguru import logger
import app.config as cfg
from app.ai.openrouter_provider import OpenRouterProvider


@runtime_checkable
class AIProvider(Protocol):
    """Protocol every AI provider must implement."""

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        ...

    @property
    def name(self) -> str:
        ...


def get_ai_provider(provider_name: str | None = None, model: str = "") -> AIProvider:
    """Factory: return an AIProvider instance. Only OpenRouter is used."""
    if not model:
        model = cfg.AI_MODEL or "nvidia/nemotron-3-super-120b-a12b:free"
    logger.info(f"Init AI provider: openrouter model={model}")
    return OpenRouterProvider(api_key=cfg.AI_API_KEY, model=model)


def get_fallback_chain() -> list[AIProvider]:
    """Return provider chain with multiple fallback free models.

    If the user set AI_MODEL in .env, that model is tried first.
    If it fails (e.g. DEGRADED), we try the remaining free models in order.
    """
    user_model = cfg.AI_MODEL or "nvidia/nemotron-3-super-120b-a12b:free"

    # Ordered list of free fallback models (reliable ones first)
    fallback_models = [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "qwen/qwen-2-7b-instruct:free",
        "huggingfaceh4/zephyr-7b-beta:free",
    ]

    # Build chain: user's model first, then fallbacks (skip duplicate)
    chain = []
    seen = set()
    for m in [user_model] + fallback_models:
        if m not in seen:
            seen.add(m)
            chain.append(OpenRouterProvider(api_key=cfg.AI_API_KEY, model=m))

    logger.info(f"Fallback chain: {[p.name + '(' + p._model + ')' for p in chain]}")
    return chain
