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
from app.personality.manager import PersonalityManager
from app.memory.manager import MemoryManager
from app.ai.response_engine import ResponseEngine
from app.utils.helpers import format_number, trunc_text, calculate_uptime


# Global start time for uptime calculation
_start_time = datetime.now(timezone.utc)


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
        self._prompt_edit_state: dict[int, dict] = {}  # owner_id -> {"action": ..., "data": ...}

    # ── Decorator ───────────────────────────────────────

    @staticmethod
    def owner_only(func):
        """Decorator: only allow OWNER_ID."""
        async def wrapper(client: Client, message: Message):
            if message.from_user and message.from_user.id == cfg.OWNER_ID:
                await func(client, message)
            else:
                await message.reply("⛔ Owner only.")
        return wrapper

    # ── Command Handlers ─────────────────────────────────

    @owner_only
    async def cmd_start(self, client: Client, message: Message):
        """Start panel with inline buttons."""
        groups_count = await db_ops.get_group_count()
        users_count = await db_ops.get_user_count()
        today_stats = await db_ops.get_stats()
        mongo_ok = await db_ops.db_ping()
        latency = self.engine.avg_latency

        uptime = calculate_uptime(_start_time)
        status_emoji = "🟢" if mongo_ok else "🔴"
        today_replies = today_stats.get("replies", 0) if today_stats else 0

        text = (
            f"🤖 <b>Persona AI Assistant</b>\n\n"
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
                    InlineKeyboardButton("📊 Statistics", callback_data="panel_stats"),
                    InlineKeyboardButton("🧠 Memory", callback_data="panel_memory"),
                ],
                [
                    InlineKeyboardButton("🎭 Personality", callback_data="panel_personality"),
                    InlineKeyboardButton("⚙️ Settings", callback_data="panel_settings"),
                ],
                [
                    InlineKeyboardButton("📂 Logs", callback_data="panel_logs"),
                    InlineKeyboardButton("🔄 Restart", callback_data="panel_restart"),
                ],
                [
                    InlineKeyboardButton("📤 Backup", callback_data="panel_backup"),
                    InlineKeyboardButton("🗑️ Blacklist", callback_data="panel_blacklist"),
                ],
            ]
        )

        await message.reply_text(text, reply_markup=keyboard)

    @owner_only
    async def cmd_help(self, client: Client, message: Message):
        commands = (
            "📖 <b>Available Commands</b>\n\n"
            "`/start` — Status panel\n"
            "`/ping` — Latency check\n"
            "`/stats` — Today's statistics\n"
            "`/groups` — List groups\n"
            "`/users` — User count\n"
            "`/settings` — View settings\n"
            "`/status` — System status\n"
            "`/personality` — View personality\n"
            "`/setprompt <text>` — Set personality\n"
            "`/memory [chat_id]` — View memory/summary\n"
            "`/summary [chat_id]` — Force generate summary\n"
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

    @owner_only
    async def cmd_ping(self, client: Client, message: Message):
        t0 = time.perf_counter()
        await db_ops.db_ping()
        latency = (time.perf_counter() - t0) * 1000
        await message.reply_text(f"🏓 Pong!\nDB Latency: {latency:.0f} ms\nAI Latency: {self.engine.avg_latency:.0f} ms")

    @owner_only
    async def cmd_stats(self, client: Client, message: Message):
        stats = await db_ops.get_stats()
        if not stats:
            await message.reply_text("No stats for today yet.")
            return

        text = (
            f"📊 <b>Today's Statistics</b>\n\n"
            f"Messages: {format_number(stats.get('messages', 0))}\n"
            f"Replies: {format_number(stats.get('replies', 0))}\n"
            f"API Calls: {format_number(stats.get('api_calls', 0))}\n"
            f"Tokens Used: {format_number(stats.get('tokens_used', 0))}\n"
            f"Summaries: {format_number(stats.get('summaries_generated', 0))}\n"
            f"Errors: {format_number(stats.get('errors', 0))}\n"
            f"Date: {stats.get('date', 'N/A')}\n"
        )
        await message.reply_text(text)

    @owner_only
    async def cmd_groups(self, client: Client, message: Message):
        groups = await db_ops.get_all_groups()
        if not groups:
            await message.reply_text("No groups registered yet.")
            return

        lines = [f"📋 <b>Groups ({len(groups)})</b>\n"]
        for g in groups[:30]:  # limit to 30
            status = "🟢" if g.get("enabled", True) else "🔴"
            title = g.get("title", "Unknown")
            gid = g["group_id"]
            replies = g.get("reply_count", 0)
            lines.append(f"{status} <code>{gid}</code> | {title} | {replies} replies")

        if len(groups) > 30:
            lines.append(f"\n... and {len(groups) - 30} more")

        await message.reply_text("\n".join(lines))

    @owner_only
    async def cmd_users(self, client: Client, message: Message):
        count = await db_ops.get_user_count()
        await message.reply_text(f"👥 Total users stored: {format_number(count)}")

    @owner_only
    async def cmd_settings(self, client: Client, message: Message):
        text = (
            f"⚙️ <b>Current Settings</b>\n\n"
            f"AI Provider: <code>{cfg.AI_PROVIDER}</code>\n"
            f"AI Model: <code>{cfg.AI_MODEL or 'default'}</code>\n"
            f"Fallback: {'Enabled' if cfg.FALLBACK_ENABLED else 'Disabled'}\n"
            f"Fallback Order: {', '.join(cfg.FALLBACK_ORDER)}\n"
            f"Short-term Limit: {cfg.SHORT_TERM_LIMIT}\n"
            f"Summary Trigger: {cfg.SUMMARY_TRIGGER_COUNT} msgs / {cfg.SUMMARY_TRIGGER_MINUTES} min\n"
            f"Reply Cooldown: {cfg.REPLY_COOLDOWN}s\n"
            f"Typing Delay: {cfg.TYPING_DELAY_MIN}-{cfg.TYPING_DELAY_MAX}s\n"
            f"Auto Summary: {'Enabled' if cfg.AUTO_SUMMARY_ENABLED else 'Disabled'}\n"
            f"Whitelist Only: {'Yes' if cfg.WHITELIST_ONLY else 'No'}\n"
            f"Log Level: {cfg.LOG_LEVEL}\n"
        )
        await message.reply_text(text)

    @owner_only
    async def cmd_status(self, client: Client, message: Message):
        mongo_ok = await db_ops.db_ping()
        uptime = calculate_uptime(_start_time)
        text = (
            f"🔋 <b>System Status</b>\n\n"
            f"MongoDB: {'🟢 Connected' if mongo_ok else '🔴 Disconnected'}\n"
            f"AI Provider: {cfg.AI_PROVIDER}\n"
            f"Session: {'🟢 Active' if True else '🔴 Disconnected'}\n"
            f"Uptime: {uptime}\n"
            f"Total API Calls: {format_number(self.engine.call_count)}\n"
            f"Avg AI Latency: {self.engine.avg_latency:.0f} ms\n"
        )
        await message.reply_text(text)

    @owner_only
    async def cmd_personality(self, client: Client, message: Message):
        p = self.personality_mgr.personality
        await message.reply_text(f"🎭 <b>Current Personality</b>\n\n{p}")

    @owner_only
    async def cmd_setprompt(self, client: Client, message: Message):
        new_prompt = message.text.split("/setprompt", 1)[1].strip() if len(message.text.split("/setprompt", 1)) > 1 else ""
        if not new_prompt:
            await message.reply_text("Usage: `/setprompt <your personality text>`")
            return
        await self.personality_mgr.update(new_prompt)
        self.engine.prompt_builder.set_personality(new_prompt)
        await message.reply_text("✅ Personality updated!")
        await db_ops.save_log("INFO", "Personality changed", f"by owner {cfg.OWNER_ID}")

    @owner_only
    async def cmd_memory(self, client: Client, message: Message):
        args = message.text.split()
        chat_id = int(args[1]) if len(args) > 1 else None

        if chat_id:
            summary = await db_ops.get_summary(chat_id)
            memories = await db_ops.get_memories(chat_id)
            msg_count = await db_ops.get_message_count_since(
                chat_id,
                datetime.now(timezone.utc),
            )
            text = f"🧠 <b>Memory for {chat_id}</b>\n\n"
            text += f"Short-term messages: {msg_count}\n\n"
            if summary:
                text += f"<b>Summary:</b>\n{summary}\n\n"
            else:
                text += "<b>Summary:</b> None yet\n\n"
            if memories:
                text += "<b>Key Facts:</b>\n"
                text += "\n".join(f"• {m['key']}: {m['value']}" for m in memories)
            else:
                text += "<b>Key Facts:</b> None yet"
            await message.reply_text(trunc_text(text))
        else:
            groups = await db_ops.get_all_groups()
            text = "🧠 <b>Memory Overview</b>\n\n"
            for g in groups[:15]:
                gid = g["group_id"]
                title = g.get("title", "Unknown")[:20]
                summary = await db_ops.get_summary(gid)
                has_summary = "✅" if summary else "❌"
                text += f"{has_summary} <code>{gid}</code> | {title}\n"
            await message.reply_text(text or "No groups yet.")

    @owner_only
    async def cmd_summary(self, client: Client, message: Message):
        args = message.text.split()
        chat_id = int(args[1]) if len(args) > 1 else None
        if not chat_id:
            await message.reply_text("Usage: `/summary <chat_id>`")
            return
        await message.reply_text(f"⏳ Generating summary for {chat_id}...")
        result = await self.memory_mgr.generate_summary(chat_id)
        if result:
            await message.reply_text(f"✅ Summary generated:\n\n{result}")
        else:
            await message.reply_text("⚠️ Not enough messages to summarize.")

    @owner_only
    async def cmd_logs(self, client: Client, message: Message):
        args = message.text.split()
        limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
        logs = await db_ops.get_recent_logs(limit)
        if not logs:
            await message.reply_text("No logs found.")
            return

        lines = [f"📂 <b>Recent Logs ({len(logs)})</b>\n"]
        for log in logs:
            ts = log.get("created_at", "")
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%H:%M:%S")
            level = log.get("level", "INFO")
            msg = log.get("message", "")
            lines.append(f"[{ts}] {level}: {msg}")

        await message.reply_text(trunc_text("\n".join(lines), 4000))

    @owner_only
    async def cmd_reload(self, client: Client, message: Message):
        self.engine.refresh_providers()
        await self.personality_mgr.load()
        self.engine.prompt_builder.set_personality(self.personality_mgr.personality)
        await message.reply_text("✅ Settings and personality reloaded.")
        await db_ops.save_log("INFO", "Reload", "Settings reloaded by owner")

    @owner_only
    async def cmd_restart(self, client: Client, message: Message):
        await message.reply_text("🔄 Restarting...")
        await db_ops.save_log("INFO", "Restart", "Restart triggered by owner")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @owner_only
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

        await message.reply_document(file, caption="📤 Backup exported.")

    @owner_only
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

        await message.reply_document(file, caption="📤 Full export completed.")

    @owner_only
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
                            # Upsert
                            if "key" in item:
                                await col.update_one({"key": item["key"]}, {"$set": item, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}}, upsert=True)
                            elif "chat_id" in item:
                                await col.update_one({"chat_id": item["chat_id"]}, {"$set": item}, upsert=True)
                            elif "user_id" in item:
                                await col.update_one({"user_id": item["user_id"]}, {"$set": item, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}}, upsert=True)
                            imported += 1

            await message.reply_text(f"✅ Imported {imported} records.")
        except Exception as e:
            await message.reply_text(f"❌ Import failed: {e}")

    @owner_only
    async def cmd_version(self, client: Client, message: Message):
        await message.reply_text("🤖 <b>Persona AI Assistant</b>\nVersion: <code>v1.0</code>")

    @owner_only
    async def cmd_enable(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text("Usage: `/enable <group_id>`")
            return
        try:
            gid = int(args[1])
            await db_ops.set_group_enabled(gid, True)
            await message.reply_text(f"✅ Group {gid} enabled.")
        except ValueError:
            await message.reply_text("Invalid group ID.")

    @owner_only
    async def cmd_disable(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text("Usage: `/disable <group_id>`")
            return
        try:
            gid = int(args[1])
            await db_ops.set_group_enabled(gid, False)
            await message.reply_text(f"🔴 Group {gid} disabled.")
        except ValueError:
            await message.reply_text("Invalid group ID.")

    @owner_only
    async def cmd_blacklist(self, client: Client, message: Message):
        users = await db_ops.get_blacklisted_users()
        if not users:
            await message.reply_text("📋 Blacklist is empty.")
            return
        lines = [f"📋 <b>Blacklist ({len(users)})</b>\n"]
        for u in users:
            lines.append(f"• <code>{u['user_id']}</code>")
        await message.reply_text("\n".join(lines))

    @owner_only
    async def cmd_whitelist(self, client: Client, message: Message):
        users = await db_ops.get_whitelisted_users()
        if not users:
            await message.reply_text("📋 Whitelist is empty.")
            return
        lines = [f"📋 <b>Whitelist ({len(users)})</b>\n"]
        for u in users:
            lines.append(f"• <code>{u['user_id']}</code>")
        await message.reply_text("\n".join(lines))

    # ── Blacklist/Whitelist add/remove ──────────────────

    @owner_only
    async def cmd_blacklist_add(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/bladd <user_id>`")
            return
        uid = int(args[1])
        await db_ops.blacklist_user(uid)
        await message.reply_text(f"⛔ User {uid} blacklisted.")

    @owner_only
    async def cmd_blacklist_rm(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/blrm <user_id>`")
            return
        uid = int(args[1])
        await db_ops.unblacklist_user(uid)
        await message.reply_text(f"✅ User {uid} removed from blacklist.")

    @owner_only
    async def cmd_whitelist_add(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/wladd <user_id>`")
            return
        uid = int(args[1])
        await db_ops.whitelist_user(uid)
        await message.reply_text(f"✅ User {uid} whitelisted.")

    @owner_only
    async def cmd_whitelist_rm(self, client: Client, message: Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            await message.reply_text("Usage: `/wlrm <user_id>`")
            return
        uid = int(args[1])
        await db_ops.unwhitelist_user(uid)
        await message.reply_text(f"✅ User {uid} removed from whitelist.")

    # ── Callback Query Handlers (inline buttons) ────────

    async def on_callback(self, client: Client, callback: CallbackQuery):
        if callback.from_user.id != cfg.OWNER_ID:
            await callback.answer("⛔ Owner only.", show_alert=True)
            return

        data = callback.data
        await callback.answer()

        if data == "panel_stats":
            await self.cmd_stats(client, callback.message)
        elif data == "panel_memory":
            await self.cmd_memory(client, callback.message)
        elif data == "panel_personality":
            await self.cmd_personality(client, callback.message)
        elif data == "panel_settings":
            await self.cmd_settings(client, callback.message)
        elif data == "panel_logs":
            await self.cmd_logs(client, callback.message)
        elif data == "panel_restart":
            await self.cmd_restart(client, callback.message)
        elif data == "panel_backup":
            await self.cmd_backup(client, callback.message)
        elif data == "panel_blacklist":
            await self.cmd_blacklist(client, callback.message)
        else:
            await callback.message.reply_text(f"Unknown panel: {data}")

    # ── Register all handlers ────────────────────────────

    def register_handlers(self, bot_client: Client):
        """Register all owner bot command handlers."""
        bot_client.on_message(filters.command("start") & filters.user(cfg.OWNER_ID))(self.cmd_start)
        bot_client.on_message(filters.command("help") & filters.user(cfg.OWNER_ID))(self.cmd_help)
        bot_client.on_message(filters.command("ping") & filters.user(cfg.OWNER_ID))(self.cmd_ping)
        bot_client.on_message(filters.command("stats") & filters.user(cfg.OWNER_ID))(self.cmd_stats)
        bot_client.on_message(filters.command("groups") & filters.user(cfg.OWNER_ID))(self.cmd_groups)
        bot_client.on_message(filters.command("users") & filters.user(cfg.OWNER_ID))(self.cmd_users)
        bot_client.on_message(filters.command("settings") & filters.user(cfg.OWNER_ID))(self.cmd_settings)
        bot_client.on_message(filters.command("status") & filters.user(cfg.OWNER_ID))(self.cmd_status)
        bot_client.on_message(filters.command("personality") & filters.user(cfg.OWNER_ID))(self.cmd_personality)
        bot_client.on_message(filters.command("setprompt") & filters.user(cfg.OWNER_ID))(self.cmd_setprompt)
        bot_client.on_message(filters.command("memory") & filters.user(cfg.OWNER_ID))(self.cmd_memory)
        bot_client.on_message(filters.command("summary") & filters.user(cfg.OWNER_ID))(self.cmd_summary)
        bot_client.on_message(filters.command("logs") & filters.user(cfg.OWNER_ID))(self.cmd_logs)
        bot_client.on_message(filters.command("reload") & filters.user(cfg.OWNER_ID))(self.cmd_reload)
        bot_client.on_message(filters.command("restart") & filters.user(cfg.OWNER_ID))(self.cmd_restart)
        bot_client.on_message(filters.command("backup") & filters.user(cfg.OWNER_ID))(self.cmd_backup)
        bot_client.on_message(filters.command("export") & filters.user(cfg.OWNER_ID))(self.cmd_export)
        bot_client.on_message(filters.command("import") & filters.user(cfg.OWNER_ID))(self.cmd_import)
        bot_client.on_message(filters.command("version") & filters.user(cfg.OWNER_ID))(self.cmd_version)
        bot_client.on_message(filters.command("enable") & filters.user(cfg.OWNER_ID))(self.cmd_enable)
        bot_client.on_message(filters.command("disable") & filters.user(cfg.OWNER_ID))(self.cmd_disable)
        bot_client.on_message(filters.command("blacklist") & filters.user(cfg.OWNER_ID))(self.cmd_blacklist)
        bot_client.on_message(filters.command("whitelist") & filters.user(cfg.OWNER_ID))(self.cmd_whitelist)
        bot_client.on_message(filters.command("bladd") & filters.user(cfg.OWNER_ID))(self.cmd_blacklist_add)
        bot_client.on_message(filters.command("blrm") & filters.user(cfg.OWNER_ID))(self.cmd_blacklist_rm)
        bot_client.on_message(filters.command("wladd") & filters.user(cfg.OWNER_ID))(self.cmd_whitelist_add)
        bot_client.on_message(filters.command("wlrm") & filters.user(cfg.OWNER_ID))(self.cmd_whitelist_rm)

        # Callback queries (inline buttons)
        bot_client.on_callback_query(self.on_callback)

        logger.info(f"Owner dashboard registered ({25} commands)")
