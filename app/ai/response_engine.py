"""Response Engine — calls AI with fallback, parses and returns clean text.

Supports concurrent requests via asyncio.Semaphore to handle multiple
users chatting at the same time without overwhelming the API.
"""

import asyncio
import time
from loguru import logger
from app.ai.provider import get_ai_provider, get_fallback_chain, AIProvider
from app.ai.prompt_builder import PromptBuilder
from app.database import operations as db_ops
import app.config as cfg

# Limit concurrent AI API calls to avoid rate limits
_api_semaphore = asyncio.Semaphore(5)


class ResponseEngine:
    def __init__(self, prompt_builder: PromptBuilder):
        self.prompt_builder = prompt_builder
        self._provider_chain = get_fallback_chain()
        self._call_count = 0
        self._total_latency = 0.0

    def refresh_providers(self) -> None:
        self._provider_chain = get_fallback_chain()

    async def generate_reply(self, chat_id: int, user_id: int, message_text: str, user_name: str = "User", reply_to_text: str | None = None) -> str:
        """Generate a reply using per-user prompt + AI providers with concurrency control."""
        system_prompt, user_prompt = await self.prompt_builder.build(chat_id, user_id, message_text, user_name, reply_to_text=reply_to_text)

        last_error = None
        async with _api_semaphore:  # throttle concurrent API hits
            for provider in self._provider_chain:
                t0 = time.perf_counter()
                try:
                    reply = await provider.generate(user_prompt, system_prompt)
                    latency = (time.perf_counter() - t0) * 1000
                    self._call_count += 1
                    self._total_latency += latency

                    await db_ops.update_stats(api_calls=1, replies=1, tokens_used=len(user_prompt) + len(reply))
                    logger.info(f"AI reply via {provider.name} ({latency:.0f}ms) for user {user_id}")
                    return reply[:cfg.MAX_REPLY_LENGTH]
                except Exception as e:
                    last_error = e
                    # Check for DEGRADED model error — log at debug level, not warning
                    error_str = str(e)
                    if "DEGRADED" in error_str or "cannot be invoked" in error_str:
                        logger.debug(f"{provider.name} model DEGRADED, trying next...")
                    else:
                        logger.warning(f"{provider.name} failed: {e}  -> trying next provider")

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
