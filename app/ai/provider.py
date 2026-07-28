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

    Updated July 2026: old models (gemini-2.0-flash-exp, llama-3.1-8b, mistral-7b,
    qwen-2-7b, zephyr-7b) have all been delisted from OpenRouter.
    New fallbacks use models confirmed live as of July 27, 2026.

    If the user set AI_MODEL in .env, that model is tried first.
    If it fails (e.g. DEGRADED/404), we try the remaining free models in order.
    """
    user_model = cfg.AI_MODEL or "nvidia/nemotron-3-super-120b-a12b:free"

    # Live free models as of July 27, 2026 (verified on openrouter.ai/collections/free-models)
    # Ordered: best general chat quality first, then code-specialized, then smaller
    fallback_models = [
        "google/gemma-4-31b-it:free",           # 31B, strong general chat
        "inclusionai/ling-3.0-flash:free",      # fast, good general
        "nvidia/nemotron-3-nano-30b-a3b:free",  # 30B, good quality
        "google/gemma-4-26b-a4b-it:free",        # 26B MoE, efficient
        "nvidia/nemotron-nano-9b-v2:free",       # 9B, fast fallback
        "openai/gpt-oss-20b:free",               # OpenAI's open model
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
