from datetime import datetime, timezone, timedelta
import asyncio
from loguru import logger
from app.database import operations as db_ops
from app.ai.provider import get_ai_provider
import app.config as cfg


class MemoryManager:
    """Two-Level Memory Manager — PER USER isolation.

    Each user has their own short-term messages, long-term summary,
    and key-value memories. When User A asks something, only
    User A's conversation history is sent to the AI.
    """

    def __init__(self):
        # Keyed by (chat_id, user_id) tuples
        self._last_summary_time: dict[tuple[int, int], datetime] = {}
        self._message_counter: dict[tuple[int, int], int] = {}

    async def should_summarize(self, chat_id: int, user_id: int) -> bool:
        """Check if summary should be triggered for a specific user in a chat."""
        key = (chat_id, user_id)
        since = datetime.now(timezone.utc) - timedelta(minutes=cfg.SUMMARY_TRIGGER_MINUTES)
        count = await db_ops.get_message_count_since(chat_id, user_id, since)

        triggered = False
        if count >= cfg.SUMMARY_TRIGGER_COUNT:
            triggered = True

        last_time = self._last_summary_time.get(key)
        if last_time and (datetime.now(timezone.utc) - last_time).total_seconds() >= cfg.SUMMARY_TRIGGER_MINUTES * 60:
            if count >= 10:
                triggered = True

        return triggered

    async def generate_summary(self, chat_id: int, user_id: int) -> str | None:
        """Summarize a specific user's old messages, save per-user summary."""
        try:
            messages = await db_ops.get_recent_messages(chat_id, user_id, limit=cfg.SUMMARY_TRIGGER_COUNT + 20)
            if len(messages) < 10:
                return None

            conv_text = "\n".join(
                f"{'Assistant' if m.get('is_bot') else 'User'}: {m['text']}"
                for m in messages
            )

            existing_summary = await db_ops.get_summary(chat_id, user_id)

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
                key = (chat_id, user_id)
                await db_ops.save_summary(chat_id, user_id, new_summary)
                self._last_summary_time[key] = datetime.now(timezone.utc)
                self._message_counter[key] = 0

                # Delete old messages for this user (keep last SHORT_TERM_LIMIT)
                cutoff_msgs = messages[-cfg.SHORT_TERM_LIMIT: 1]
                if cutoff_msgs:
                    before = cutoff_msgs[0].get("created_at", datetime.now(timezone.utc))
                    deleted = await db_ops.delete_old_messages(chat_id, user_id, before)
                    logger.info(f"Summary for user {user_id} in {chat_id}: saved, deleted {deleted} old messages")

                await db_ops.update_stats(summaries_generated=1)
                await db_ops.save_log("INFO", "Summary generated", f"chat_id={chat_id} user_id={user_id}")
                return new_summary

        except Exception as e:
            logger.error(f"Summary generation failed for user {user_id} in {chat_id}: {e}")
            await db_ops.update_stats(errors=1)
        return None

    async def auto_summarize_all(self) -> None:
        """Check all active users in groups and summarize where needed."""
        try:
            user_ids = await db_ops.get_active_user_ids()
            groups = await db_ops.get_all_groups()

            for group in groups:
                gid = group["group_id"]
                for uid in user_ids:
                    if await self.should_summarize(gid, uid):
                        await self.generate_summary(gid, uid)
        except Exception as e:
            logger.error(f"Auto-summarize all failed: {e}")

    def register_message(self, chat_id: int, user_id: int) -> None:
        """Increment message counter for a specific user in a chat."""
        key = (chat_id, user_id)
        self._message_counter[key] = self._message_counter.get(key, 0) + 1
