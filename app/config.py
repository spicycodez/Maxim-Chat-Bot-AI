"""
Configuration Loader — reads .env and exposes typed settings.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root (one level above app/)
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")

# ── Telegram ──────────────────────────────────────────────
API_ID: int = int(os.getenv("API_ID", "0"))
API_HASH: str = os.getenv("API_HASH", "")
SESSION_STRING: str = os.getenv("SESSION_STRING", "")
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))

# ── MongoDB ───────────────────────────────────────────────
MONGO_URL: str = os.getenv("MONGO_URL", "")
DB_NAME: str = os.getenv("DB_NAME", "persona_ai")

# ── AI Provider ───────────────────────────────────────────
AI_PROVIDER: str = os.getenv("AI_PROVIDER", "openrouter").lower()  # openrouter only
AI_API_KEY: str = os.getenv("AI_API_KEY", "")
AI_MODEL: str = os.getenv("AI_MODEL", "")  # leave empty for provider default

# ── Memory ────────────────────────────────────────────────
SHORT_TERM_LIMIT: int = int(os.getenv("SHORT_TERM_LIMIT", "20"))
SUMMARY_TRIGGER_COUNT: int = int(os.getenv("SUMMARY_TRIGGER_COUNT", "100"))
SUMMARY_TRIGGER_MINUTES: int = int(os.getenv("SUMMARY_TRIGGER_MINUTES", "60"))

# ── Reply Settings ───────────────────────────────────────
REPLY_COOLDOWN: int = int(os.getenv("REPLY_COOLDOWN", "10"))  # seconds per group
TYPING_DELAY_MIN: float = float(os.getenv("TYPING_DELAY_MIN", "0.3"))
TYPING_DELAY_MAX: float = float(os.getenv("TYPING_DELAY_MAX", "1.5"))
MAX_REPLY_LENGTH: int = int(os.getenv("MAX_REPLY_LENGTH", "4096"))

# ── Scheduler ─────────────────────────────────────────────
AUTO_SUMMARY_ENABLED: bool = os.getenv("AUTO_SUMMARY_ENABLED", "true").lower() in ("true", "1", "yes")
AUTO_SUMMARY_INTERVAL: int = int(os.getenv("AUTO_SUMMARY_INTERVAL", "30"))  # minutes

# ── Auto Messages (proactive group messaging) ──────────
AUTO_MESSAGE_ENABLED: bool = os.getenv("AUTO_MESSAGE_ENABLED", "true").lower() in ("true", "1", "yes")
AUTO_MESSAGE_INTERVAL: int = int(os.getenv("AUTO_MESSAGE_INTERVAL", "30"))  # minutes

# ── Bot Start Page ─────────────────────────────────────
START_IMAGE_URL: str = os.getenv("START_IMAGE_URL", "")  # optional image for /start
START_MESSAGE: str = os.getenv("START_MESSAGE", "")  # optional custom text (uses default if empty)
SUPPORT_GROUP: str = os.getenv("SUPPORT_GROUP", "")  # e.g. https://t.me/your_group
SUPPORT_CHANNEL: str = os.getenv("SUPPORT_CHANNEL", "")  # e.g. https://t.me/your_channel

# ── Misc ──────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
BLACKLISTED_USERS: list[int] = [
    int(x) for x in os.getenv("BLACKLISTED_USERS", "").split(",") if x.strip().isdigit()
]
WHITELIST_ONLY: bool = os.getenv("WHITELIST_ONLY", "false").lower() in ("true", "1", "yes")
