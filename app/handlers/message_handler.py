import random
import re
import asyncio
import time
from datetime import datetime, timezone, timedelta
from loguru import logger
from pyrogram import Client, filters
from pyrogram.types import Message

from app.database import operations as db_ops
from app.language.detector import LanguageDetector
from app.ai.response_engine import ResponseEngine
from app.memory.manager import MemoryManager
import app.config as cfg


class MessageHandler:
    """Processes incoming Telegram messages, decides whether to reply, and generates responses."""

    def __init__(
        self,
        client: Client,
        response_engine: ResponseEngine,
        memory_manager: MemoryManager,
    ):
        self.client = client
        self.engine = response_engine
        self.memory = memory_manager
        self.detector = LanguageDetector()
        self._cooldowns: dict[int, float] = {}  # group_id -> last reply timestamp
        self._my_user_id: int = 0
        self._my_username: str = ""
        self._my_first_name: str = ""

    def _ensure_me(self) -> None:
        """Cache self info on first use."""
        if not self._my_user_id and self.client.me:
            self._my_user_id = self.client.me.id
            self._my_username = (self.client.me.username or "").lower()
            self._my_first_name = (self.client.me.first_name or "").lower()

    # ── Filter checks ───────────────────────────────────

    async def should_process(self, message: Message) -> bool:
        """Return True if the message passes all filter checks."""
        # Ignore empty messages
        if not message.text or not message.text.strip():
            return False

        # Ignore bots
        if message.from_user and message.from_user.is_bot:
            return False

        # Ignore commands (messages starting with /)
        if message.text.startswith("/"):
            return False

        # Ignore forwarded messages
        if message.forward_date:
            return False

        # Ignore channel posts
        if message.sender_chat:
            return False

        # Ignore deleted / service messages
        if message.empty:
            return False

        user_id = message.from_user.id if message.from_user else 0

        # Check blacklist
        if await db_ops.is_blacklisted(user_id):
            return False

        # Check whitelist-only mode
        if cfg.WHITELIST_ONLY and not await db_ops.is_whitelisted(user_id):
            return False

        # Check if user is in config blacklist
        if user_id in cfg.BLACKLISTED_USERS:
            return False

        # Check group enabled
        chat_id = message.chat.id
        if message.chat.type in ("group", "supergroup"):
            if not await db_ops.is_group_enabled(chat_id):
                return False

        # Ignore very short messages (< 2 chars)
        if len(message.text.strip()) < 2:
            return False

        return True

    def _is_mentioned(self, message: Message) -> bool:
        """Check if the assistant is mentioned via @mention, text mention, or reply."""
        self._ensure_me()

        # 1. Check Telegram entities (actual @mentions and text_mentions)
        if message.entities:
            for ent in message.entities:
                # @username mention
                if ent.type == "mention":
                    mentioned_text = message.text[ent.offset:ent.offset + ent.length].lower()
                    mentioned_text = mentioned_text.lstrip("@")
                    if mentioned_text == self._my_username:
                        logger.debug(f"Mentioned via @username: {mentioned_text}")
                        return True

                # Text mention (when user is mentioned without @, e.g. in name)
                if ent.type == "text_mention":
                    if ent.user and ent.user.id == self._my_user_id:
                        logger.debug("Mentioned via text_mention entity")
                        return True

        # 2. Check if replying to our message
        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == self._my_user_id:
                logger.debug("Mentioned via reply")
                return True

        # 3. Text-based fallback: check if username/first_name appears in text
        text = (message.text or "").lower()
        if self._my_username and self._my_username in text:
            logger.debug(f"Mentioned via text: @{self._my_username}")
            return True
        if self._my_first_name and self._my_first_name in text:
            logger.debug(f"Mentioned via text: {self._my_first_name}")
            return True

        return False

    def _should_reply(self, message: Message) -> bool:
        """Determine if the message warrants a reply."""
        # In private chats, always reply
        if message.chat.type == "private":
            return True

        # In groups: always reply if mentioned (@tag, reply, name)
        if self._is_mentioned(message):
            return True

        # For group chats, probabilistic response for non-directed messages
        if message.chat.type in ("group", "supergroup"):
            return random.random() < 0.15

        return False

    async def _check_cooldown(self, chat_id: int) -> bool:
        """Return True if we're still in cooldown for this group."""
        now = time.time()
        last = self._cooldowns.get(chat_id, 0)
        if now - last < cfg.REPLY_COOLDOWN:
            return True
        return False

    async def _set_cooldown(self, chat_id: int) -> None:
        self._cooldowns[chat_id] = time.time()

    # ── Main handler ─────────────────────────────────────

    async def handle(self, message: Message) -> None:
        """Main entry point for processing a message."""
        try:
            self._ensure_me()

            if not await self.should_process(message):
                return

            if not self._should_reply(message):
                return

            chat_id = message.chat.id

            # Cooldown check (groups only) — skip if mentioned
            is_mentioned = self._is_mentioned(message)
            if message.chat.type in ("group", "supergroup") and not is_mentioned:
                if await self._check_cooldown(chat_id):
                    return

            user_id = message.from_user.id if message.from_user else 0
            user_name = (
                message.from_user.first_name or "User"
                if message.from_user
                else "User"
            )
            text = message.text.strip()

            # Detect language (for logging / future use)
            lang = self.detector.detect(text)
            logger.debug(f"Detected language: {lang} for: {text[:50]}")

            # Register user & group in DB
            await db_ops.upsert_user(
                user_id=user_id,
                username=message.from_user.username or "",
                first_name=message.from_user.first_name or "",
                last_name=message.from_user.last_name or "",
            )
            if message.chat.type in ("group", "supergroup"):
                await db_ops.register_group(
                    group_id=chat_id,
                    title=message.chat.title or "",
                    username=message.chat.username or "",
                )

            # Save message to DB (short-term memory)
            await db_ops.save_message(
                chat_id=chat_id,
                user_id=user_id,
                text=text,
                is_bot=False,
                message_id=message.id,
            )
            self.memory.register_message(chat_id)

            # Check if summary is needed
            if await self.memory.should_summarize(chat_id):
                asyncio.create_task(self.memory.generate_summary(chat_id))

            # Generate reply
            reply_text = await self.engine.generate_reply(chat_id, text, user_name)

            if not reply_text:
                return

            # Typing simulation
            delay = random.uniform(cfg.TYPING_DELAY_MIN, cfg.TYPING_DELAY_MAX)
            await asyncio.sleep(delay)

            # Send reply
            await message.reply_text(reply_text)

            # Save assistant's reply to DB
            await db_ops.save_message(
                chat_id=chat_id,
                user_id=self._my_user_id,
                text=reply_text,
                is_bot=True,
            )

            # Update stats
            await db_ops.increment_user_replies(user_id)
            if message.chat.type in ("group", "supergroup"):
                await db_ops.increment_group_replies(chat_id)
                await self._set_cooldown(chat_id)

            logger.info(f"Replied to {user_name} in {chat_id}")

        except Exception as e:
            logger.error(f"MessageHandler error: {e}")
            await db_ops.update_stats(errors=1)
            await db_ops.save_log("ERROR", "MessageHandler", str(e)[:500])
