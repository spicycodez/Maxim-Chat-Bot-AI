"""APScheduler-based background jobs.

- Auto-summarize memory periodically
- Cleanup old logs
- Stats aggregation
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from app.memory.manager import MemoryManager
from app.database import operations as db_ops
import app.config as cfg


class AppScheduler:
    def __init__(self, memory_manager: MemoryManager):
        self.scheduler = AsyncIOScheduler()
        self.memory_manager = memory_manager

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

    async def _cleanup_logs(self) -> None:
        """Delete logs older than 30 days."""
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            col = db_ops.get_collection("logs")
            result = await col.delete_many({"created_at": {"$lt": cutoff}})
            logger.info(f"Cleaned up {result.deleted_count} old log entries")
        except Exception as e:
            logger.error(f"Log cleanup failed: {e}")
