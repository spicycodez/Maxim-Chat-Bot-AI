"""Builds the final prompt sent to the AI provider.

Order:
  1. System Prompt (personality)
  2. Long-term summary
  3. Recent conversation (short-term memory)
  4. Current message
"""

from loguru import logger
from app.database import operations as db_ops
import app.config as cfg


class PromptBuilder:
    def __init__(self, personality: str = ""):
        self._personality = personality

    async def build(self, chat_id: int, current_message: str, user_name: str = "User") -> tuple[str, str]:
        """Return (system_prompt, user_prompt)."""
        # 1. Personality as system prompt
        system_prompt = self._personality or "You are a helpful Telegram assistant. Be concise and natural."

        # 2. Long-term summary
        summary = await db_ops.get_summary(chat_id)
        memories = await db_ops.get_memories(chat_id)

        # 3. Recent conversation
        recent = await db_ops.get_recent_messages(chat_id, limit=cfg.SHORT_TERM_LIMIT)

        # 4. Assemble user prompt
        parts = []

        if summary:
            parts.append(f"[Conversation Summary]\n{summary}")

        if memories:
            mem_lines = "\n".join(f"- {m['key']}: {m['value']}" for m in memories)
            parts.append(f"[Known Facts]\n{mem_lines}")

        if recent:
            conv_lines = []
            for msg in recent:
                role = "Assistant" if msg.get("is_bot") else str(msg.get("user_id", "User"))
                conv_lines.append(f"{role}: {msg['text']}")
            parts.append("[Recent Conversation]\n" + "\n".join(conv_lines))

        parts.append(f"{user_name}: {current_message}")

        user_prompt = "\n\n".join(parts)
        return system_prompt, user_prompt

    def set_personality(self, text: str) -> None:
        self._personality = text
