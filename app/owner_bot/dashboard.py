"""
Owner Dashboard Bot - separate Telegram Bot Token for admin control.

All commands are owner-only.
"""

import os
import sys
import time
import json
import io
from datetime import datetime, timezone
from loguru import logger
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

import app.config as cfg
from app.database import operations as db_ops
from app.database import db as db_module
from app.database import get_collection
from app.personality.manager import PersonalityManager
from app.memory.manager import MemoryManager
from app.ai.response_engine import ResponseEngine
from app.utils.helpers import format_number, trunc_text, calculate_uptime


# Global start time for uptime calculation
_start_time = datetime.now(timezone.utc)


def _owner_only(func):
    """Decorator: only allow OWNER_ID. Standalone function, not a staticmethod."""
    async def wrapper(client: Client, message: Message):
        if message.from_user and message.from_user.id == cfg.OWNER_ID:
            return await func(client, message)
        else:
            await message.reply_text("\u26d4 Owner only.")
    return wrapper


class OwnerDashboard:
    def __init__(
        self,
        personality_mgr: PersonalityManager,
        memory_mgr: MemoryManager,
        response_engine: ResponseEngine,
    ):
        self.personality_mgr = personality_mgr
        self.memory_mgr = memory_mgr
        self.engine = response_engine
        self._prompt_edit_state: dict[int, dict] = {}

    # ── Command Handlers ─────────────────────────────────

    async def cmd_start(self, client: Client, message: Message):
        """Start panel with inline buttons."""
        groups_count = await db_ops.get_group_count()
        users_count = await db_ops.get_user_count()
        today_stats = await db_ops.get_stats()
        mongo_ok = await db_ops.db_ping()
        latency = self.engine.avg_latency

        uptime = calculate_uptime(_start_time)
        status_emoji = "\U0001f7e2" if mongo_ok else "\U0001f534"
        today_replies = today_stats.get("replies", 0) if today_stats else 0

        text = (
            f"\U0001f916 <b>Persona AI Assistant</b>\n\n"
            f"Status: {status_emoji} Online\n"
            f"Version: <code>v1.0</code>\n"
            f"Groups: {format_number(groups_count)}\n"
            f"Users Stored: {format_number(users_count)}\n"
            f"Today's Replies: {format_number(today_replies)}\n"
            f"Mongo: {'Connected' if mongo_ok else 'Disconnected'}\n"
            f"AI: {', '.join(self.engine.provider_names)}\n"
            f"Memory: {'Enabled' if cfg.AUTO_SUMMARY_ENABLED else 'Disabled'}\n"
            f"Latency: {latency:.0f} ms\n"
            f"Uptime: {uptime}\n"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("\U0001f4ca Statistics", callback_data="panel_stats"),
                    InlineKeyboardButton("\U0001f9e0 Memory", callback_data="panel_memory"),
                ],
                [
                    InlineKeyboardButton("\U0001f3ad Personality", callback_data="panel_personality"),
                    InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="panel_settings"),
                ],
                [
                    InlineKeyboardButton("\U0001f4c2 Logs", callback_data="panel_logs"),
                    InlineKeyboardButton("\U0001f504 Restart", callback_data="panel_restart"),
                ],
                [
                    InlineKeyboardButton("\U0001f4e4 Backup", callback_data="panel_backup"),
                    InlineKeyboardButton("\U0001f5d1\ufe0f Blacklist", callback_data="panel_blacklist"),
                ],
            ]
        )

        await message.reply_text(text, reply_markup=keyboard)

    async def cmd_help(self, client: Client, message: Message):
        commands = (
            "\U0001f4d6 <b>Available Commands</b>\n\n"
            "`/start` — Status panel\n"
            "`/ping` — Latency check\n"
            "`/stats` — Today's statistics\n"
            "`/groups` — List groups\n"
            "`/users` — User count\n"
            "`/settings` — View settings\n"
            "`/status` — System status\n"
            "`/personality` — View personality\n"
            "`/setprompt <text>` — Set personality\n"
            "`/memory [chat_id] [user_id]` — View per-user memory/summary\n"
            "`/summary <chat_id> <user_id>` — Force generate summary\n"
            "`/logs [N]` — Recent N logs\n"
            "`/reload` — Reload settings\n"
            "`/restart` — Restart the bot\n"
            "`/backup` — Export DB stats as JSON\n"
            "`/export` — Export full backup\n"
            "`/version` — Version info\n"
            "`/enable <chat_id>` — Enable group\n"
            "`/disable <chat_id>` — Disable group\n"
            "`/blacklist` — View blacklist\n"
            "`/whitelist` — View whitelist\n"
        )
        await message.reply_text(commands)

    async def cmd_ping(self, client: Client, message: Message):
        t0 = time.perf_counter()
        await db_ops.db_ping()
        latency = (time.perf_counter() - t0) * 1000
        await message.reply_text(f"\U0001f3d3 Pong!\nDB Latency: {latency:.0f} ms\nAI Latency: {self.engine.avg_latency:.0f} ms")

    async def cmd_stats(self, client: Client, message: Message):
        stats = await db_ops.get_stats()
        if not stats:
            await message.reply_text("No stats for today yet.")
            return

        text = (
            f"\U0001f4ca <b>Today's Statistics</b>\n\n"
            f"Messages: {format_number(stats.get('messages', 0))}\n"
            f"Replies: {format_number(stats.get('replies', 0))}\n"
            f"API Calls: {format_number(stats.get('api_calls', 0))}\n"
            f"Tokens Used: {format_number(stats.get('tokens_used', 0))}\n"
            f"Summaries: {format_number(stats.get('summaries_generated', 0))}\n"
            f"Errors: {format_number(stats.get('errors', 0))}\n"
            f"Date: {stats.get('date', 'N/A')}\n"
        )
        await message.reply_text(text)

    async def cmd_groups(self, client: Client, message: Message):
        groups = await db_ops.get_all_groups()
        if not groups:
            await message.reply_text("No groups registered yet.")
            return

        lines = [f"\U0001f4cb <b>Groups ({len(groups)})</b>\n"]
        for g in groups[:30]:
            status = "\U0001f7e2" if g.get("enabled", True) else "\U0001f534"
            title = g.get("title", "Unknown")
            gid = g["group_id"]
            replies = g.get("reply_count", 0)
            lines.append(f"{status} <code>{gid}</code> | {title} | {replies} replies")

        if len(groups) > 30:
            lines.append(f"\n... and {len(groups) - 30} more")

        await message.reply_text("\n".join(lines))

    async def cmd_users(self, client: Client, message: Message):
        count = await db_ops.get_user_count()
        await message.reply_text(f"\U0001f465 Total users stored: {format_number(count)}")

    async def cmd_settings(self, client: Client, message: Message):
        text = (
            f"\u2699\ufe0f <b>Current Settings</b>\n\n"
            f"AI Provider: <code>{cfg.AI_PROVIDER}</code>\n"
            f"AI Model: <code>{cfg.AI_MODEL or 'default'}</code>\n"
            f"Short-term Limit: {cfg.SHORT_TERM_LIMIT}\n"
            f"Summary Trigger: {cfg.SUMMARY_TRIGGER_COUNT} msgs / {cfg.SUMMARY_TRIGGER_MINUTES} min\n"
            f"Reply Cooldown: {cfg.REPLY_COOLDOWN}s\n"
            f"Typing Delay: {cfg.TYPING_DELAY_MIN}-{cfg.TYPING_DELAY_MAX}s\n"
            f"Auto Summary: {'Enabled' if cfg.AUTO_SUMMARY_ENABLED else 'Disabled'}\n"
            f"Auto Messages: {'Enabled' if cfg.AUTO_MESSAGE_ENABLED else 'Disabled'}\n"
            f"Weekly Cleanup: Enabled (7 days)\n"
            f"Memory Mode: Per-User Isolated\n"
            f"Whitelist Only: {'Yes' if cfg.WHITELIST_ONLY else 'No'}\n"
            f"Log Level: {cfg.LOG_LEVEL}\n"
        )
        await message.reply_text(text)

    async def cmd_status(self, client: Client, message: Message):
        mongo_ok = await db_ops.db_ping()
        uptime = calculate_uptime(_start_time)
        text = (
            f"\U0001f50b <b>System Status</b>\n\n"
            f"MongoDB: {'\U0001f7e2 Connected' if mongo_ok else '\U0001f534 Disconnected'}\n"
            f"AI Provider: {cfg.AI_PROVIDER}\n"
            f"Session: \U0001f7e2 Active\n"
            f"Uptime: {uptime}\n"
            f"Total API Calls: {format_number(self.engine.call_count)}\n"
            f"Avg AI Latency: {self.engine.avg_latency:.0f} ms\n"
        )
        await message.reply_text(text)

    async def cmd_personality(self, client: Client, message: Message):
        p = self.personality_mgr.personality
        await message.reply_text(f"\U0001f3ad <b>Current Personality</b>\n\n{p}")

    async def cmd_setprompt(self, client: Client, message: Message):
        new_prompt = message.text.split("/setprompt", 1)[1].strip() if len(message.text.split("/setprompt", 1)) > 1 else ""
        if not new_prompt:
            await message.reply_text("Usage: `/setprompt <your personality text>`")
            return
        await self.personality_mgr.update(new_prompt)
        self.engine.prompt_builder.set_personality(new_prompt)
        await message.reply_text("\u2705 Personality updated!")
        await db_ops.save_log("INFO", "Personality changed", f"by owner {cfg.OWNER_ID}")

    async def cmd_memory(self, client: Client, message: Message):
        args = message.text.split()
        # /memory <chat_id> <user_id>  OR  /memory <chat_id>  (lists users)
        chat_id = int(args[1]) if len(args) > 1 and args[1].lstrip('-').isdigit() else None
        user_id = int(args[2]) if len(args) > 2 and args[2].lstrip('-').isdigit() else None

        if chat_id and user_id:
            # Show specific user's memory in a chat
            summary = await db_ops.get_summary(chat_id, user_id)
            memories = await db_ops.get_memories(chat_id, user_id)
            msg_count = await db_ops.get_message_count_since(
                chat_id, user_id,
                datetime.now(timezone.utc),
            )
            text = f"\U0001f9e0 <b>Memory for user {user_id} in {chat_id}</b>\n\n"
            text += f"Short-term messages: {msg_count}\n\n"
            if summary:
                text += f"<b>Summary:</b>\n{summary}\n\n"
            else:
                text += "<b>Summary:</b> None yet\n\n"
            if memories:
                text += "<b>Key Facts:</b>\n"
                text += "\n".join(f"\u2022 {m['key']}: {m['value']}" for m in memories)
            else:
                text += "<b>Key Facts:</b> None yet"
            await message.reply_text(trunc_text(text))
        elif chat_id:
            # List all users who have memory in this chat
            col = get_collection("messages")
            pipeline = [
                {"$match": {"chat_id": chat_id}},
                {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            user_stats = await col.aggregate(pipeline).to_list(length=100)
            if not user_stats:
                await message.reply_text(f"No user data for chat {chat_id}.")
                return
            text = f"\U0001f9e0 <b>Users in {chat_id}</b>\n\n"
            for u in user_stats[:30]:
                uid = u["_id"]
                cnt = u["count"]
                summary = await db_ops.get_summary(chat_id, uid)
                has_sum = "\u2705" if summary else "\u274c"
                text += f"{has_sum} <code>{uid}</code> | {cnt} msgs\n"
            text += f"\n\nUse: /memory {chat_id} <user_id>"
            await message.reply_text(trunc_text(text))
        else:
            groups = await db_ops.get_all_groups()
            text = "\U0001f9e0 <b>Memory Overview</b>\n\n"
            for g in groups[:15]:
                gid = g["group_id"]
                title = g.get("title", "Unknown")[:20]
                text += f"\U0001f4c1 <code>{gid}</code> | {title}\n"
            text += "\nUse: /memory <chat_id> to see users"
            await message.reply_text(text or "No groups yet.")

    async def cmd_summary(self, client: Client, message: Message):
        args = message.text.split()
        chat_id = int(args[1]) if len(args) > 1 and args[1].lstrip('-').isdigit() else None
        user_id = int(args[2]) if len(args) > 2 and args[2].lstrip('-').isdigit() else None
        if not chat_id or not user_id:
            await message.reply_text("Usage: `/summary <chat_id> <user_id>`")
            return
        await message.reply_text(f"\u23f3 Generating summary for user {user_id} in {chat_id}...")
        result = await self.memory_mgr.generate_summary(chat_id, user_id)
        if result:
            await message.reply_text(f"\u2705 Summary generated:\n\n{result}")
        else:
            await message.reply_text("\u26a0\ufe0f Not enough messages to summarize.")

    async def cmd_logs(self, client: Client, message: Message):
        args = message.text.split()
        limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
        logs = await db_ops.get_recent_logs(limit)
        if not logs:
            await message.reply_text("No logs found.")
            return

        lines = [f"\U0001f4c2 <b>Recent Logs ({len(logs)})</b>\n"]
        for log in logs:
            ts = log.get("created_at", "")
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%H:%M:%S")
            level = log.get("level", "INFO")
            msg = log.get("message", "")
            lines.append(f"[{ts}] {level}: {msg}")

        await message.reply_text(trunc_text("\n".join(lines), 4000))

    async def cmd_reload(self, client: Client, message: Message):
        self.engine.refresh_providers()
        await self.personality_mgr.load()
        self.engine.prompt_builder.set_personality(self.personality_mgr.personality)
        await message.reply_text("\u2705 Settings and personality reloaded.")
        await db_ops.save_log("INFO", "Reload", "Settings reloaded by owner")

    async def cmd_restart(self, client: Client, message: Message):
        await message.reply_text("\U0001f504 Restarting...")
        await db_ops.save_log("INFO", "Restart", "Restart triggered by owner")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    async def cmd_backup(self, client: Client, message: Message):
        stats = await db_ops.get_all_stats()
        groups = await db_ops.get_all_groups()
        user_count = await db_ops.get_user_count()

        backup = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "v1.0",
            "user_count": user_count,
            "group_count": len(groups),
            "statistics": [{"date": s.get("date"), **{k: v for k, v in s.items() if k != "_id"}} for s in stats],
            "groups": [{"group_id": g.get("group_id"), "title": g.get("title", ""), "replies": g.get("reply_count", 0)} for g in groups],
        }

        data = json.dumps(backup, indent=2, default=str)
        file = io.BytesIO(data.encode())
        file.name = f"persona_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        await message.reply_document(file, caption="\U0001f4e4 Backup exported.")

    async def cmd_export(self, client: Client, message: Message):
        """Export a full database backup including summaries and settings."""
        from app.database import get_collection

        collections_to_export = ["settings", "summaries", "memories", "blacklist", "whitelist"]
        export = {"timestamp": datetime.now(timezone.utc).isoformat(), "version": "v1.0"}

        for col_name in collections_to_export:
            col = get_collection(col_name)
            docs = await col.find({}, {"_id": 0}).to_list(length=10000)
            export[col_name] = docs

        data = json.dumps(export, indent=2, default=str)
        file = io.BytesIO(data.encode())
        file.name = f"persona_full_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        await message.reply_document(file, caption="\U0001f4e4 Full export completed.")

    async def cmd_import(self, client: Client, message: Message):
        """Import settings/summaries/memories from a JSON file."""
        if not message.reply_to_message or not message.reply_to_message.document:
            await message.reply_text("Reply to a JSON file to import.")
            return

        try:
            doc = await message.reply_to_message.download(in_memory=True)
            data = json.loads(doc.getvalue().decode())

            imported = 0
            for col_name in ["settings", "summaries", "memories", "blacklist", "whitelist"]:
                if col_name in data:
                    col = db_ops.get_collection(col_name)
                    for item in data[col_name]:
                        if "key" in item or "chat_id" in item or "user_id" in item:
                            if "key" in item:
                                await col.update_one({"key": item["key"]}, {"$set": item, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}}, upsert=True)
                            elif "chat_id" in item:
                                await col.update_one({"chat_id": item["chat_id"]}, {"$set": item}, upsert=True)
                            elif "user_id" in item:
                                await col.update_one({"user_id": item["user_id"]}, {"$set": item, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}}, upsert=True)
                            imported += 1

            await message.reply_text(f"\u2705 Imported {imported} records.")
        except Exception as e:
            await message.reply_text(f"\u274c Import failed: {e}")

    async def cmd_version(self, client: Client, message: Message):
        await message.reply_text("\U0001f916 <b>Persona AI Assistant</b>\nVersion: <code>v1.0</code>")

    async def cmd_enable(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text("Usage: `/enable <group_id>`")
            return
        try:
            gid = int(args[1])
            await db_ops.set_group_enabled(gid, True)
            await message.reply_text(f"\u2705 Group {gid} enabled.")
        except ValueError:
            await message.reply_text("Invalid group ID.")

    async def cmd_disable(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text("Usage: `/disable <group_id>`")
            return
        try:
            gid = int(args[1])
            await db_ops.set_group_enabled(gid, False)
            await message.reply_text(f"\U0001f534 Group {gid} disabled.")
        except ValueError:
            await message.reply_text("Invalid group ID.")

    async def cmd_blacklist(self, client: Client, message: Message):
        users = await db_ops.get_blacklisted_users()
        if not users:
            await message.reply_text("\U0001f4cb Blacklist is empty.")
            return
        lines = [f"\U0001f4cb <b>Blacklist ({len(users)})</b>\n"]
        for u in users:
            lines.append(f"\u2022 <code>{u['user_id']}</code>")
        await message.reply_text("\n".join(lines))

    async def cmd_whitelist(self, client: Client, message: Message):
        users = await db_ops.get_whitelisted_users()
        if not users:
            await message.reply_text("\U0001f4cb Whitelist is empty.")
            return
        lines = [f"\U0001f4cb <b>Whitelist ({len(users)})</b>\n"]
        for u in users:
            lines.append(f"\u2022 <code>{u['user_id']}</code>")
        await message.reply_text("\n".join(lines))

    async def cmd_blacklist_add(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/bladd <user_id>`")
            return
        uid = int(args[1])
        await db_ops.blacklist_user(uid)
        await message.reply_text(f"\u26d4 User {uid} blacklisted.")

    async def cmd_blacklist_rm(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/blrm <user_id>`")
            return
        uid = int(args[1])
        await db_ops.unblacklist_user(uid)
        await message.reply_text(f"\u2705 User {uid} removed from blacklist.")

    async def cmd_whitelist_add(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/wladd <user_id>`")
            return
        uid = int(args[1])
        await db_ops.whitelist_user(uid)
        await message.reply_text(f"\u2705 User {uid} whitelisted.")

    async def cmd_whitelist_rm(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/wlrm <user_id>`")
            return
        uid = int(args[1])
        await db_ops.unwhitelist_user(uid)
        await message.reply_text(f"\u2705 User {uid} removed from whitelist.")

    # ── Callback Query Handlers (inline buttons) ────────

    async def on_callback(self, client: Client, callback: CallbackQuery):
        if callback.from_user.id != cfg.OWNER_ID:
            await callback.answer("\u26d4 Owner only.", show_alert=True)
            return

        data = callback.data
        await callback.answer()

        handler_map = {
            "panel_stats": self.cmd_stats,
            "panel_memory": self.cmd_memory,
            "panel_personality": self.cmd_personality,
            "panel_settings": self.cmd_settings,
            "panel_logs": self.cmd_logs,
            "panel_restart": self.cmd_restart,
            "panel_backup": self.cmd_backup,
            "panel_blacklist": self.cmd_blacklist,
        }

        handler = handler_map.get(data)
        if handler:
            await handler(client, callback.message)
        else:
            await callback.message.reply_text(f"Unknown panel: {data}")

    # ── Register all handlers ────────────────────────────

    def register_handlers(self, bot_client: Client):
        """Register all owner bot command handlers."""
        commands = [
            ("help", self.cmd_help),
            ("ping", self.cmd_ping),
            ("stats", self.cmd_stats),
            ("groups", self.cmd_groups),
            ("users", self.cmd_users),
            ("settings", self.cmd_settings),
            ("status", self.cmd_status),
            ("personality", self.cmd_personality),
            ("setprompt", self.cmd_setprompt),
            ("memory", self.cmd_memory),
            ("summary", self.cmd_summary),
            ("logs", self.cmd_logs),
            ("reload", self.cmd_reload),
            ("restart", self.cmd_restart),
            ("backup", self.cmd_backup),
            ("export", self.cmd_export),
            ("import", self.cmd_import),
            ("version", self.cmd_version),
            ("enable", self.cmd_enable),
            ("disable", self.cmd_disable),
            ("blacklist", self.cmd_blacklist),
            ("whitelist", self.cmd_whitelist),
            ("bladd", self.cmd_blacklist_add),
            ("blrm", self.cmd_blacklist_rm),
            ("wladd", self.cmd_whitelist_add),
            ("wlrm", self.cmd_whitelist_rm),
        ]

        for cmd_name, handler in commands:
            wrapped = _owner_only(handler)
            bot_client.on_message(filters.command(cmd_name) & filters.user(cfg.OWNER_ID))(wrapped)

        # Public /start for everyone — owner gets dashboard, others get welcome
        @bot_client.on_message(filters.command("start"))
        async def public_start(client, message):
            if message.from_user and message.from_user.id == cfg.OWNER_ID:
                return await self.cmd_start(client, message)

            # Public welcome with optional image + support buttons
            start_text = cfg.START_MESSAGE or (
                f"Hey {message.from_user.first_name or 'there'}! \n\n"
                f"I'm an AI-powered assistant that chats in groups. \n"
                f"Add me to your group and tag me to get started!"
            )
            buttons = []
            if cfg.SUPPORT_GROUP:
                buttons.append([InlineKeyboardButton("Support Group", url=cfg.SUPPORT_GROUP)])
            if cfg.SUPPORT_CHANNEL:
                buttons.append([InlineKeyboardButton("Support Channel", url=cfg.SUPPORT_CHANNEL)])

            if cfg.START_IMAGE_URL and buttons:
                await message.reply_photo(
                    photo=cfg.START_IMAGE_URL,
                    caption=start_text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            elif cfg.START_IMAGE_URL:
                await message.reply_photo(photo=cfg.START_IMAGE_URL, caption=start_text)
            elif buttons:
                await message.reply_text(start_text, reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await message.reply_text(start_text)

        # Catch-all for any other command from non-owners
        @bot_client.on_message(~filters.user(cfg.OWNER_ID) & filters.regex(r"^/"))
        async def cmd_catchall(client, message):
            if message.text and message.text.startswith("/start"):
                return  # handled above
            await message.reply_text("\u26d4 Owner only.")

        # Callback queries (inline buttons)
        bot_client.on_callback_query(self.on_callback)

        logger.info(f"Owner dashboard registered ({len(commands)} commands)")
