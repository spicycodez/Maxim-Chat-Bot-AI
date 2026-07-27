import sys
import asyncio
import time
from datetime import datetime, timezone
from loguru import logger
from pyrogram import Client, filters

import app.config as cfg
from app.database import connect_db, disconnect_db
from app.personality.manager import PersonalityManager
from app.memory.manager import MemoryManager
from app.language.detector import LanguageDetector
from app.ai.prompt_builder import PromptBuilder
from app.ai.response_engine import ResponseEngine
from app.handlers.message_handler import MessageHandler
from app.owner_bot.dashboard import OwnerDashboard
from app.scheduler.scheduler import AppScheduler
from app.database import operations as db_ops


# ── Loguru setup ─────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    level=cfg.LOG_LEVEL,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    ),
)
logger.add(
    "app/logs/bot.log",
    rotation="10 MB",
    retention="7 days",
    level=cfg.LOG_LEVEL,
)


# ── Globals ───────────────────────────────────────────
user_client: Client | None = None
bot_client: Client | None = None
scheduler: AppScheduler | None = None
response_engine: ResponseEngine | None = None
personality_mgr: PersonalityManager | None = None
memory_mgr: MemoryManager | None = None
_start_time = datetime.now(timezone.utc)


async def send_startup_notification(bot: Client) -> None:
    """Send startup notification to the owner."""
    try:
        groups_count = await db_ops.get_group_count()
        users_count = await db_ops.get_user_count()
        mongo_ok = await db_ops.db_ping()
        latency = response_engine.avg_latency if response_engine else 0

        text = (
            f"✅ <b>Persona AI Started</b>\n\n"
            f"Session: {'Connected' if user_client and user_client.is_connected else 'Disconnected'}\n"
            f"Mongo: {'Connected' if mongo_ok else 'Disconnected'}\n"
            f"AI: {cfg.AI_PROVIDER}\n"
            f"Groups: {groups_count}\n"
            f"Latency: {latency:.0f} ms\n"
            f"Version: 1.0\n"
            f"Ready."
        )
        await bot.send_message(cfg.OWNER_ID, text)
        logger.info("Startup notification sent")
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")


async def main():
    global user_client, bot_client, scheduler, response_engine, personality_mgr, memory_mgr

    logger.info("Persona AI Assistant v1.0 starting...")

    # 1. Connect MongoDB
    await connect_db()
    await db_ops.save_log("INFO", "Startup", "Bot starting")

    # 2. Load personality
    personality_mgr = PersonalityManager()
    await personality_mgr.load()

    # 3. Initialize AI components
    prompt_builder = PromptBuilder(personality=personality_mgr.personality)
    response_engine = ResponseEngine(prompt_builder=prompt_builder)

    # 4. Initialize memory
    memory_mgr = MemoryManager()

    # 5. Connect User Session
    user_client = Client(
        "persona_user",
        api_id=cfg.API_ID,
        api_hash=cfg.API_HASH,
        session_string=cfg.SESSION_STRING,
    )
    await user_client.start()
    logger.info("User session connected")

    # 6. Initialize message handler
    msg_handler = MessageHandler(
        client=user_client,
        response_engine=response_engine,
        memory_manager=memory_mgr,
    )

    # Register message handler for groups and private chats
    @user_client.on_message(filters.group | filters.private)
    async def on_message(client, message):
        await msg_handler.handle(message)

    # 7. Connect Owner Bot
    if cfg.BOT_TOKEN:
        bot_client = Client(
            "persona_bot",
            api_id=cfg.API_ID,
            api_hash=cfg.API_HASH,
            bot_token=cfg.BOT_TOKEN,
        )
        await bot_client.start()
        logger.info("Owner bot connected")

        # Register owner dashboard
        dashboard = OwnerDashboard(
            personality_mgr=personality_mgr,
            memory_mgr=memory_mgr,
            response_engine=response_engine,
        )
        dashboard.register_handlers(bot_client)

        # Send startup notification
        await send_startup_notification(bot_client)
    else:
        logger.warning("No BOT_TOKEN set — owner dashboard disabled")

    # 8. Initialize scheduler
    scheduler = AppScheduler(memory_mgr)
    scheduler.start()

    # 9. Ready
    logger.info("Persona AI is ready and listening!")

    # Keep running
    await asyncio.Event().wait()


async def shutdown():
    """Graceful shutdown."""
    logger.info("Shutting down...")
    if scheduler:
        scheduler.stop()
    if bot_client:
        await bot_client.stop()
    if user_client:
        await user_client.stop()
    await disconnect_db()
    await db_ops.save_log("INFO", "Shutdown", "Bot stopped")
    logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        asyncio.run(shutdown())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        asyncio.run(shutdown())
        sys.exit(1)
