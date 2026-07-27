"""Two-Level Memory Manager.

Short-Term: Last N messages stored in MongoDB, included in every prompt.
Long-Term: Summaries generated every N messages or M minutes.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from loguru import logger
from app.database import operations as db_ops
from app.ai.provider import get_ai_provider
import app.config as cfg


class MemoryManager:
    def __init__(self):
        self._last_summary_time: dict[int, datetime] = {}
        self._message_counter: dict[int, int] = {}

    async def should_summarize(self, chat_id: int) -> bool:
        """Check if summary should be triggered for a chat."""
        since = datetime.now(timezone.utc) - timedelta(minutes=cfg.SUMMARY_TRIGGER_MINUTES)
        count = await db_ops.get_message_count_since(chat_id, since)

        triggered = False
        if count >= cfg.SUMMARY_TRIGGER_COUNT:
            triggered = True

        last_time = self._last_summary_time.get(chat_id)
        if last_time and (datetime.now(timezone.utc) - last_time).total_seconds() >= cfg.SUMMARY_TRIGGER_MINUTES * 60:
            if count >= 10:  # at least 10 messages before time-based trigger
                triggered = True

        return triggered

    async def generate_summary(self, chat_id: int) -> str | None:
        """Summarize old messages, save summary, delete old messages."""
        try:
            # Fetch messages to summarize
            messages = await db_ops.get_recent_messages(chat_id, limit=cfg.SUMMARY_TRIGGER_COUNT + 20)
            if len(messages) < 10:
                return None

            # Build text for summarization
            conv_text = "\n".join(
                f"{'Assistant' if m.get('is_bot') else 'User'}: {m['text']}"
                for m in messages
            )

            # Get existing summary for context
            existing_summary = await db_ops.get_summary(chat_id)

            summary_prompt = (
                "You are a conversation summarizer. Extract key facts, preferences, "
                "and important context from this conversation. "
                "Output a concise bulleted summary. "
                "Each line should be a single fact or preference.\n\n"
            )
            if existing_summary:
                summary_prompt += f"[Previous Summary]\n{existing_summary}\n\n"
            summary_prompt += f"[New Messages]\n{conv_text}"

            provider = get_ai_provider()
            new_summary = await provider.generate(summary_prompt, system_prompt="")
            new_summary = new_summary.strip()

            if new_summary:
                await db_ops.save_summary(chat_id, new_summary)
                self._last_summary_time[chat_id] = datetime.now(timezone.utc)
                self._message_counter[chat_id] = 0

                # Delete old messages (keep last SHORT_TERM_LIMIT)
                cutoff = messages[-cfg.SHORT_TERM_LIMIT : 1]
                if cutoff:
                    before = cutoff[0].get("created_at", datetime.now(timezone.utc))
                    deleted = await db_ops.delete_old_messages(chat_id, before)
                    logger.info(f"Summary for {chat_id}: saved, deleted {deleted} old messages")

                await db_ops.update_stats(summaries_generated=1)
                await db_ops.save_log("INFO", "Summary generated", f"chat_id={chat_id}")
                return new_summary

        except Exception as e:
            logger.error(f"Summary generation failed for {chat_id}: {e}")
            await db_ops.update_stats(errors=1)
        return None

    async def auto_summarize_all(self) -> None:
        """Check all groups and summarize where needed. Called by scheduler."""
        groups = await db_ops.get_all_groups()
        for group in groups:
            gid = group["group_id"]
            if await self.should_summarize(gid):
                await self.generate_summary(gid)

    def register_message(self, chat_id: int) -> None:
        """Increment message counter for a chat."""
        self._message_counter[chat_id] = self._message_counter.get(chat_id, 0) + 1
