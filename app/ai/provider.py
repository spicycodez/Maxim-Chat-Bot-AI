from typing import Protocol, runtime_checkable
import httpx
import google.generativeai as genai
from loguru import logger
import app.config as cfg
from app.ai.gemini_provider import GeminiProvider
from app.ai.groq_provider import GroqProvider
from app.ai.openrouter_provider import OpenRouterProvider


@runtime_checkable
class AIProvider(Protocol):
    """Protocol every AI provider must implement."""

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        ...

    @property
    def name(self) -> str:
        ...


def get_ai_provider(provider_name: str | None = None) -> AIProvider:
    """Factory: return an AIProvider instance for the given name."""
    name = (provider_name or cfg.AI_PROVIDER).lower()

    if name == "gemini":
        return GeminiProvider(api_key=cfg.AI_API_KEY, model=cfg.AI_MODEL or "gemini-2.0-flash")
    elif name == "groq":
        return GroqProvider(api_key=cfg.AI_API_KEY, model=cfg.AI_MODEL or "llama-3.3-70b-versatile")
    elif name == "openrouter":
        return OpenRouterProvider(api_key=cfg.AI_API_KEY, model=cfg.AI_MODEL or "google/gemma-4-31b-it:free")
    else:
        raise ValueError(f"Unknown AI provider: {name}")


def get_fallback_chain() -> list[AIProvider]:
    """Return ordered list of fallback providers."""
    chain = [get_ai_provider(cfg.AI_PROVIDER)]
    if cfg.FALLBACK_ENABLED:
        for fb_name in cfg.FALLBACK_ORDER:
            if fb_name != cfg.AI_PROVIDER:
                try:
                    chain.append(get_ai_provider(fb_name))
                except ValueError:
                    logger.warning(f"Fallback provider '{fb_name}' is not configured, skipping.")
    return chain
