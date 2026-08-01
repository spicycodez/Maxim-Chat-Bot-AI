import pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from loguru import logger
import app.config as cfg

_client: AsyncIOMotorClient | None = None
db = None


async def connect_db() -> None:
    """Connect to MongoDB Atlas and return the database handle."""
    global _client, db
    try:
        _client = AsyncIOMotorClient(
            cfg.MONGO_URL,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        db = _client[cfg.DB_NAME]
        # Verify connection
        await db.command("ping")
        logger.success("MongoDB connected")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise


async def disconnect_db() -> None:
    """Gracefully close the MongoDB connection."""
    global _client, db
    if _client:
        _client.close()
        _client = None
        db = None
        logger.info("MongoDB disconnected")


def get_collection(name: str):
    """Return a Motor collection handle."""
    if db is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return db[name]
