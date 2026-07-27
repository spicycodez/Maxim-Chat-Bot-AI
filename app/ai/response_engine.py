"""Response Engine — calls AI with fallback, parses and returns clean text."""

import time
from loguru import logger
from app.ai.provider import get_ai_provider, get_fallback_chain, AIProvider
from app.ai.prompt_builder import PromptBuilder
from app.database import operations as db_ops
import app.config as cfg


class ResponseEngine:
    def __init__(self, prompt_builder: PromptBuilder):
        self.prompt_builder = prompt_builder
        self._provider_chain = get_fallback_chain()
        self._call_count = 0
        self._total_latency = 0.0

    def refresh_providers(self) -> None:
        self._provider_chain = get_fallback_chain()

    async def generate_reply(self, chat_id: int, message_text: str, user_name: str = "User") -> str:
        """Generate a reply using the prompt builder + AI providers with fallback."""
        system_prompt, user_prompt = await self.prompt_builder.build(chat_id, message_text, user_name)

        last_error = None
        for provider in self._provider_chain:
            t0 = time.perf_counter()
            try:
                reply = await provider.generate(user_prompt, system_prompt)
                latency = (time.perf_counter() - t0) * 1000
                self._call_count += 1
                self._total_latency += latency

                # Track stats
                await db_ops.update_stats(api_calls=1, replies=1, tokens_used=len(user_prompt) + len(reply))
                logger.info(f"AI reply via {provider.name} ({latency:.0f}ms)")
                return reply[:cfg.MAX_REPLY_LENGTH]
            except Exception as e:
                last_error = e
                logger.warning(f"{provider.name} failed: {e}  →  trying next provider")

        # All providers failed
        await db_ops.update_stats(errors=1)
        logger.error(f"All AI providers failed. Last error: {last_error}")
        return ""

    @property
    def avg_latency(self) -> float:
        if self._call_count == 0:
            return 0.0
        return self._total_latency / self._call_count

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._provider_chain]
