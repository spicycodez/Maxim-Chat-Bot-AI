"""Personality Manager — loads, caches, and updates the assistant's personality prompt."""

from loguru import logger
from app.database import operations as db_ops


# Default personality if none is stored in MongoDB
DEFAULT_PERSONALITY = """\
You are a friendly Telegram user named Persona.
Talk naturally like a real person, not a bot.
Use Hinglish (Hindi written in English) by default.
Use English only if the user speaks English.
Never repeat yourself.
Avoid unnecessary emojis — use them only when it feels natural.
Keep replies concise unless asked to elaborate.
Stay consistent with previous conversations.
If someone asks your name, say Persona.
Don't act like an AI assistant. You are just another person in the group.
"""


class PersonalityManager:
    def __init__(self):
        self._personality: str = ""

    async def load(self) -> str:
        """Load personality from DB, falling back to default."""
        saved = await db_ops.get_personality()
        self._personality = saved if saved else DEFAULT_PERSONALITY.strip()
        logger.info(f"Personality loaded ({len(self._personality)} chars)")
        return self._personality

    @property
    def personality(self) -> str:
        return self._personality

    async def update(self, new_text: str) -> str:
        """Persist new personality to DB and update cache."""
        self._personality = new_text.strip()
        await db_ops.set_personality(self._personality)
        logger.info("Personality updated")
        return self._personality

    def get_default(self) -> str:
        return DEFAULT_PERSONALITY.strip()
