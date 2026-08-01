from typing import Protocol, runtime_checkable
from loguru import logger
import app.config as cfg
from app.ai.openrouter_provider import OpenRouterProvider
from app.ai.tokenrouter_provider import TokenRouterProvider


@runtime_checkable
class AIProvider(Protocol):
    """Protocol every AI provider must implement."""

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...


def get_ai_provider(provider_name: str | None = None, model: str = "") -> AIProvider:
    """Factory: return an AIProvider instance."""
    if not model:
        model = cfg.AI_MODEL or "nvidia/nemotron-3-super-120b-a12b:free"
    logger.info(f"Init AI provider: openrouter model={model}")
    return OpenRouterProvider(api_key=cfg.AI_API_KEY, model=model)


def get_fallback_chain() -> list[AIProvider]:
    """Return provider chain using ALL available API keys.

    Builds a single fallback chain that includes models from:
      1. OpenRouter (if AI_API_KEY is set)
      2. TokenRouter (if TOKENROUTER_API_KEY is set)

    Order: user's preferred model first, then OpenRouter free fallbacks,
    then TokenRouter models. This ensures maximum uptime — if one
    provider hits rate limits or goes down, the other takes over.
    """
    chain: list[AIProvider] = []
    seen_models: set[str] = set()

    def _add(provider: AIProvider) -> None:
        key = f"{provider.name}:{provider.model}"
        if key not in seen_models:
            seen_models.add(key)
            chain.append(provider)

    # ── 1. User's primary model (from AI_MODEL or default OpenRouter) ──
    if cfg.AI_API_KEY:
        user_model = cfg.AI_MODEL or "nvidia/nemotron-3-super-120b-a12b:free"
        _add(OpenRouterProvider(api_key=cfg.AI_API_KEY, model=user_model))

    # ── 2. User's TokenRouter primary model ──
    if cfg.TOKENROUTER_API_KEY:
        tr_model = cfg.TOKENROUTER_MODEL or "gpt-4o-mini"
        _add(TokenRouterProvider(api_key=cfg.TOKENROUTER_API_KEY, model=tr_model))

    # ── 3. OpenRouter free fallbacks (if key available) ──
    if cfg.AI_API_KEY:
        or_fallbacks = [
            "google/gemma-4-31b-it:free",           # 31B, strong general chat
            "inclusionai/ling-3.0-flash:free",      # fast, good general
            "nvidia/nemotron-3-nano-30b-a3b:free",  # 30B, good quality
            "google/gemma-4-26b-a4b-it:free",        # 26B MoE, efficient
            "nvidia/nemotron-nano-9b-v2:free",       # 9B, fast fallback
            "openai/gpt-oss-20b:free",               # OpenAI's open model
        ]
        for m in or_fallbacks:
            _add(OpenRouterProvider(api_key=cfg.AI_API_KEY, model=m))

    # ── 4. TokenRouter fallback models (if key available) ──
    if cfg.TOKENROUTER_API_KEY:
        tr_fallbacks = [
            "gpt-4o-mini",       # fast, cheap, good quality
            "gpt-3.5-turbo",     # reliable fallback
        ]
        for m in tr_fallbacks:
            _add(TokenRouterProvider(api_key=cfg.TOKENROUTER_API_KEY, model=m))

    # Safety: if no keys configured at all, use OpenRouter default
    if not chain:
        logger.warning("No AI API keys configured! Using OpenRouter default (may fail)")
        chain.append(OpenRouterProvider(
            api_key=cfg.AI_API_KEY,
            model="nvidia/nemotron-3-super-120b-a12b:free",
        ))

    logger.info(
        f"Fallback chain ({len(chain)} providers): "
        f"{[p.name + '/' + p.model for p in chain]}"
    )
    return chain
