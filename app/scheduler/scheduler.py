"""APScheduler-based background jobs.

- Auto-summarize memory periodically
- Cleanup old logs
- Proactive auto-messages in groups
"""

import random
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from app.memory.manager import MemoryManager
from app.database import operations as db_ops
import app.config as cfg


# Time-aware proactive message pools (Hinglish-friendly)
_MESSAGES = {
    "morning": [
        "Good morning everyone! Rise and grind ",
        "Morning guys! Kaise ho sab?",
        "Suprabhat! Aaj ka din acha hone wala hai ",
        "Good morning! Chai peelo aur fresh feel karo ",
        "Morning! Aaj kya plans hai sabke?",
        "Subah ho gayi, uth jao sab! Good morning ",
        "Alarma band karo aur utho! Good morning everyone ",
        "Early bird catches the worm, good morning! ",
    ],
    "afternoon": [
        "Hey everyone, khaana kha liya?",
        "Afternoon guys! Boring din chal raha hai kya?",
        "Lunch time! Kya kha rahe ho sab?",
        "Hey! Koi baat karo na, group mein itna sannata ",
        "Arre yaar, din nikal raha hai aur koi baat hi nahi kar raha ",
        "Kya haal hai dosto? Afternoon vibes ",
        "Bhai log, koi interesting topic discuss karo na ",
        "Hey guys! Anyone online?",
    ],
    "evening": [
        "Evening everyone! Kaam khatam hua sabka?",
        "Shaam ho gayi! Chai time ",
        "Hey guys, kaise gaya aaj ka din?",
        "Evening vibes! Kya scene hai aaj?",
        "Chai peeni hai kisi ko? Evening dosto! ",
        "Waah, din kaise beet gaya! Evening everyone ",
        "Arre evening ho gayi, sab kaam chhod do ab ",
        "Hey! Aaj kya khaane mein bana rahe ho?",
    ],
    "night": [
        "Good night guys! Sweet dreams ",
        "Nighty night everyone! Kal milte hai ",
        "So jaao sab! Good night ",
        "Late ho raha hai, so jaao dosto! Good night ",
        "Okay good night everyone! Take care ",
        "Raat ho gayi hai, phone chhod do aur so jaao ",
        "Bye guys, good night! Kal baat karenge ",
        "Sleep well everyone! Good night ",
    ],
    "general": [
        "Koi hai yahan? Bore ho raha hu ",
        "Hey guys! Kya chal raha hai?",
        "Arre koi toh baat karo ",
        "Interesting fact: Ek din mein 86,400 seconds hote hai! Use them wisely ",
        "Mujhe lagta hai aaj kuch acha hone wala hai ",
        "Guys, koi movie suggest karo na ",
        "Has anyone watched any good series recently?",
        "Bhai log, aaj ka mood kaisa hai?",
        "Just dropping by to say hi! Kaise ho sab?",
        "Kya baat hai, itna quiet kyun hai group?",
        "Yaar, life mein sab kuch transient hai, enjoy the moment ",
        "Music sun rahe ho koi? Bolo na kya sun rahe ho ",
        "Random thought: Agar time travel hota toh kya karte?",
        "Hello hello! Koi alive hai yahan?",
    ],
}


def _get_time_slot() -> str:
    """Return 'morning', 'afternoon', 'evening', 'night' based on IST."""
    hour = datetime.now(timezone(timedelta(hours=5, minutes=30))).hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


def _pick_message() -> str:
    """Pick a random message appropriate for the current time of day."""
    slot = _get_time_slot()
    # 70% chance to pick time-appropriate, 30% general
    pool = _MESSAGES[slot] if random.random() < 0.7 else _MESSAGES["general"]
    return random.choice(pool)


class AppScheduler:
    def __init__(self, memory_manager: MemoryManager, user_client=None):
        self.scheduler = AsyncIOScheduler()
        self.memory_manager = memory_manager
        self.user_client = user_client

    def start(self) -> None:
        """Register and start all background jobs."""
        if cfg.AUTO_SUMMARY_ENABLED:
            self.scheduler.add_job(
                self._auto_summarize,
                trigger=IntervalTrigger(minutes=cfg.AUTO_SUMMARY_INTERVAL),
                id="auto_summary",
                name="Auto Summarize Memory",
                replace_existing=True,
            )
            logger.info(f"Auto-summary scheduled every {cfg.AUTO_SUMMARY_INTERVAL} min")

        if cfg.AUTO_MESSAGE_ENABLED:
            self.scheduler.add_job(
                self._auto_send_group_messages,
                trigger=IntervalTrigger(minutes=cfg.AUTO_MESSAGE_INTERVAL),
                id="auto_messages",
                name="Auto Group Messages",
                replace_existing=True,
            )
            logger.info(f"Auto-messages scheduled every {cfg.AUTO_MESSAGE_INTERVAL} min")

        # Clean old logs every 24h
        self.scheduler.add_job(
            self._cleanup_logs,
            trigger=IntervalTrigger(hours=24),
            id="cleanup_logs",
            name="Cleanup Old Logs",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def _auto_summarize(self) -> None:
        """Run auto-summary on all active groups."""
        try:
            logger.debug("Running auto-summary...")
            await self.memory_manager.auto_summarize_all()
        except Exception as e:
            logger.error(f"Auto-summary job failed: {e}")
            await db_ops.save_log("ERROR", "Scheduler", f"Auto-summary failed: {e}")

    async def _auto_send_group_messages(self) -> None:
        """Send proactive messages to all enabled groups."""
        if not self.user_client:
            logger.warning("Auto-messages skipped: no user client")
            return

        try:
            groups = await db_ops.get_all_groups()
            enabled_groups = [g for g in groups if g.get("enabled", True)]

            if not enabled_groups:
                logger.debug("Auto-messages: no enabled groups")
                return

            # Pick one random message for this round (same msg to all groups to avoid spam)
            message = _pick_message()
            slot = _get_time_slot()
            sent = 0

            for group in enabled_groups:
                group_id = group["group_id"]
                try:
                    await self.user_client.send_message(
                        chat_id=group_id,
                        text=message,
                    )
                    sent += 1
                    logger.info(f"Auto-message sent to {group.get('title', group_id)} ({slot})")
                except Exception as e:
                    logger.warning(f"Auto-message failed for {group_id}: {e}")

            await db_ops.update_stats(auto_messages=sent)
            logger.info(f"Auto-messages sent to {sent}/{len(enabled_groups)} groups")

        except Exception as e:
            logger.error(f"Auto-messages job failed: {e}")
            await db_ops.save_log("ERROR", "Scheduler", f"Auto-messages failed: {e}")

    async def _cleanup_logs(self) -> None:
        """Delete logs older than 30 days."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            col = db_ops.get_collection("logs")
            result = await col.delete_many({"created_at": {"$lt": cutoff}})
            logger.info(f"Cleaned up {result.deleted_count} old log entries")
        except Exception as e:
            logger.error(f"Log cleanup failed: {e}")
