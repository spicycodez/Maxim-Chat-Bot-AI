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


def get_ai_provider(provider_name: str | None = None) -> AIProvider:
    """Factory: return an AIProvider instance. Only OpenRouter is used."""
    model = cfg.AI_MODEL or "nvidia/nemotron-3-super-120b-a12b:free"
    logger.info(f"Init AI provider: openrouter model={model}")
    return OpenRouterProvider(api_key=cfg.AI_API_KEY, model=model)


def get_fallback_chain() -> list[AIProvider]:
    """Return provider chain. OpenRouter only — no fallback."""
    return [get_ai_provider()]
