"""Thin async wrappers around MongoDB collections used by the assistant."""

import asyncio
from datetime import datetime, timezone
from loguru import logger
from app.database import get_collection


# ═══════════════════════════════════════════════════════════
#  Users
# ═══════════════════════════════════════════════════════════
async def upsert_user(user_id: int, username: str = "", first_name: str = "", last_name: str = "") -> None:
    col = get_collection("users")
    existing = await col.find_one({"user_id": user_id})
    if existing:
        await col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$inc": {"message_count": 1},
            },
        )
    else:
        await col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "updated_at": datetime.now(timezone.utc),
                    "created_at": datetime.now(timezone.utc),
                    "message_count": 1,
                    "reply_count": 0,
                },
            },
            upsert=True,
        )


async def increment_user_replies(user_id: int) -> None:
    col = get_collection("users")
    await col.update_one({"user_id": user_id}, {"$inc": {"reply_count": 1}})


# ═══════════════════════════════════════════════════════════
#  Groups
# ═══════════════════════════════════════════════════════════
async def register_group(group_id: int, title: str = "", username: str = "") -> None:
    col = get_collection("groups")
    await col.update_one(
        {"group_id": group_id},
        {
            "$set": {
                "title": title,
                "username": username,
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc),
                "enabled": True,
                "reply_count": 0,
                "last_reply_at": None,
            },
        },
        upsert=True,
    )


async def is_group_enabled(group_id: int) -> bool:
    col = get_collection("groups")
    doc = await col.find_one({"group_id": group_id}, {"enabled": 1})
    return doc["enabled"] if doc else True


async def set_group_enabled(group_id: int, enabled: bool) -> None:
    col = get_collection("groups")
    await col.update_one({"group_id": group_id}, {"$set": {"enabled": enabled}})


async def get_all_groups() -> list[dict]:
    col = get_collection("groups")
    return await col.find({}).to_list(length=500)


async def increment_group_replies(group_id: int) -> None:
    col = get_collection("groups")
    await col.update_one(
        {"group_id": group_id},
        {
            "$inc": {"reply_count": 1},
            "$set": {"last_reply_at": datetime.now(timezone.utc)},
        },
    )


# ═══════════════════════════════════════════════════════════
#  Messages  (short-term memory)
# ═══════════════════════════════════════════════════════════
async def save_message(
    chat_id: int,
    user_id: int,
    text: str,
    is_bot: bool = False,
    message_id: int = 0,
) -> None:
    col = get_collection("messages")
    await col.insert_one(
        {
            "chat_id": chat_id,
            "user_id": user_id,
            "text": text,
            "is_bot": is_bot,
            "message_id": message_id,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def get_recent_messages(chat_id: int, limit: int = 20) -> list[dict]:
    col = get_collection("messages")
    cursor = col.find(
        {"chat_id": chat_id},
        {"text": 1, "user_id": 1, "is_bot": 1, "created_at": 1},
    ).sort("created_at", 1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_message_count_since(chat_id: int, since: datetime) -> int:
    col = get_collection("messages")
    return await col.count_documents({"chat_id": chat_id, "created_at": {"$gte": since}})


async def delete_old_messages(chat_id: int, before: datetime) -> int:
    col = get_collection("messages")
    result = await col.delete_many({"chat_id": chat_id, "created_at": {"$lt": before}})
    return result.deleted_count


# ═══════════════════════════════════════════════════════════
#  Summaries  (long-term memory)
# ═══════════════════════════════════════════════════════════
async def save_summary(chat_id: int, summary: str) -> None:
    col = get_collection("summaries")
    await col.update_one(
        {"chat_id": chat_id},
        {
            "$set": {"summary": summary, "updated_at": datetime.now(timezone.utc)},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


async def get_summary(chat_id: int) -> str | None:
    col = get_collection("summaries")
    doc = await col.find_one({"chat_id": chat_id}, {"summary": 1})
    return doc["summary"] if doc else None


# ═══════════════════════════════════════════════════════════
#  Memories  (key-value facts extracted from summaries)
# ═══════════════════════════════════════════════════════════
async def save_memory(chat_id: int, key: str, value: str) -> None:
    col = get_collection("memories")
    await col.update_one(
        {"chat_id": chat_id, "key": key},
        {
            "$set": {"value": value, "updated_at": datetime.now(timezone.utc)},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


async def get_memories(chat_id: int) -> list[dict]:
    col = get_collection("memories")
    return await col.find({"chat_id": chat_id}, {"key": 1, "value": 1}).to_list(length=100)


# ═══════════════════════════════════════════════════════════
#  Settings
# ═══════════════════════════════════════════════════════════
async def get_setting(key: str, default=None):
    col = get_collection("settings")
    doc = await col.find_one({"key": key}, {"value": 1})
    return doc["value"] if doc else default


async def set_setting(key: str, value) -> None:
    col = get_collection("settings")
    await col.update_one(
        {"key": key},
        {
            "$set": {"value": value, "updated_at": datetime.now(timezone.utc)},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


# ═══════════════════════════════════════════════════════════
#  Personality
# ═══════════════════════════════════════════════════════════
async def get_personality() -> str:
    col = get_collection("settings")
    doc = await col.find_one({"key": "personality"}, {"value": 1})
    return doc["value"] if doc else ""


async def set_personality(text: str) -> None:
    await set_setting("personality", text)


# ═══════════════════════════════════════════════════════════
#  Statistics
# ═══════════════════════════════════════════════════════════
async def update_stats(**fields) -> None:
    col = get_collection("statistics")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await col.update_one(
        {"date": today},
        {
            "$set": {"date": today},
            "$inc": fields,
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


async def get_stats(date: str | None = None) -> dict | None:
    col = get_collection("statistics")
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return await col.find_one({"date": date})


async def get_all_stats() -> list[dict]:
    col = get_collection("statistics")
    return await col.find({}).sort("date", -1).to_list(length=90)


# ═══════════════════════════════════════════════════════════
#  Logs
# ═══════════════════════════════════════════════════════════
async def save_log(level: str, message: str, details: str = "") -> None:
    col = get_collection("logs")
    await col.insert_one(
        {
            "level": level,
            "message": message,
            "details": details,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def get_recent_logs(limit: int = 50) -> list[dict]:
    col = get_collection("logs")
    return await col.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)


# ═══════════════════════════════════════════════════════════
#  Blacklist / Whitelist
# ═══════════════════════════════════════════════════════════
async def is_blacklisted(user_id: int) -> bool:
    col = get_collection("blacklist")
    return bool(await col.find_one({"user_id": user_id}))


async def blacklist_user(user_id: int) -> None:
    col = get_collection("blacklist")
    await col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def unblacklist_user(user_id: int) -> None:
    col = get_collection("blacklist")
    await col.delete_one({"user_id": user_id})


async def is_whitelisted(user_id: int) -> bool:
    col = get_collection("whitelist")
    return bool(await col.find_one({"user_id": user_id}))


async def whitelist_user(user_id: int) -> None:
    col = get_collection("whitelist")
    await col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def unwhitelist_user(user_id: int) -> None:
    col = get_collection("whitelist")
    await col.delete_one({"user_id": user_id})


async def get_blacklisted_users() -> list[dict]:
    col = get_collection("blacklist")
    return await col.find({}, {"_id": 0}).to_list(length=500)


async def get_whitelisted_users() -> list[dict]:
    col = get_collection("whitelist")
    return await col.find({}, {"_id": 0}).to_list(length=500)


# ═══════════════════════════════════════════════════════════
#  Utility
# ═══════════════════════════════════════════════════════════
async def get_user_count() -> int:
    col = get_collection("users")
    return await col.estimated_document_count()


async def get_group_count() -> int:
    col = get_collection("groups")
    return await col.estimated_document_count()


async def db_ping() -> bool:
    import app.database as db_module
    if db_module.db is None:
        return False
    try:
        await db_module.db.command("ping")
        return True
    except Exception:
        return False
