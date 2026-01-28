from typing import Dict
import json
import re
from datetime import datetime
import telebot
from telebot import types
from config import DB_PATH, DEFAULT_MODELS


def parse_int(text: str) -> int:
    nums = re.findall(r"\d+", text or "")
    if not nums:
        raise ValueError("No number found")
    return int(nums[0])


def pretty_date(iso: str) -> str:
    if not iso:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%A, %d %b %Y")  # Wednesday, 28 Jan 2026
    except Exception:
        return iso


def build_admin_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Manage Credits", callback_data="admin:credits"))
    kb.add(types.InlineKeyboardButton("Manage Validity", callback_data="admin:validity"))
    kb.add(types.InlineKeyboardButton("List Users", callback_data="admin:list_users"))
    kb.add(types.InlineKeyboardButton("List Premium Users", callback_data="admin:list_premium"))
    kb.add(types.InlineKeyboardButton("Broadcast", callback_data="admin:broadcast"))
    kb.add(types.InlineKeyboardButton("Set Default Voice ID", callback_data="admin:default_voice"))
    kb.add(types.InlineKeyboardButton("Manage Voices", callback_data="admin:voices"))
    kb.add(types.InlineKeyboardButton("Download Data", callback_data="admin:download"))
    kb.add(types.InlineKeyboardButton("Manage Admins", callback_data="admin:admins"))
    return kb


def _get_models_from_db(db):
    raw = db.get_setting("models_json", "")
    if raw:
        try:
            models = json.loads(raw)
            if isinstance(models, list) and models:
                out = []
                for m in models:
                    if isinstance(m, dict) and m.get("id"):
                        out.append({"id": str(m["id"]), "name": str(m.get("name") or m["id"])})
                if out:
                    return out
        except Exception:
            pass
    return DEFAULT_MODELS


def _set_models_to_db(db, models):
    db.set_setting("models_json", json.dumps(models, ensure_ascii=False))


def build_voices_keyboard(models):
    kb = types.InlineKeyboardMarkup()
    for idx, m in enumerate(models):
        name = m.get("name") or "Voice"
        kb.add(types.InlineKeyboardButton(f"🎙 {name}", callback_data=f"admin:voices:edit:{idx}"))
    kb.add(types.InlineKeyboardButton("➕ Add Voice", callback_data="admin:voices:add"))
    kb.add(types.InlineKeyboardButton("♻️ Reset to Config Voices", callback_data="admin:voices:reset"))
    kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:menu"))
    return kb


def register_admin_handlers(bot: telebot.TeleBot, db):
    admin_steps: Dict[int, Dict] = {}

    def ensure_admin(uid: int):
        return db.is_admin(uid)

    @bot.message_handler(commands=["admin"])
    def admin_cmd(message):
        if not ensure_admin(message.from_user.id):
            return
        bot.send_message(message.chat.id, "⚙️ Admin Panel", reply_markup=build_admin_menu())

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin:"))
    def cb(callback):
        uid = callback.from_user.id
        if not ensure_admin(uid):
            return bot.answer_callback_query(callback.id)

        bot.answer_callback_query(callback.id)
        parts = callback.data.split(":")
        section = parts[1]

        # -----------------------
        # MAIN MENU
        # -----------------------
        if section == "menu":
            return bot.send_message(callback.message.chat.id, "⚙️ Admin Panel", reply_markup=build_admin_menu())

        # -----------------------
        # CREDITS (User ID)
        # -----------------------
        if section == "credits" and len(parts) == 2:
            admin_steps[uid] = {"action": "credits_pick_user"}
            return bot.send_message(callback.message.chat.id, "Send target User ID:")

        # -----------------------
        # VALIDITY (User ID)
        # -----------------------
        if section == "validity" and len(parts) == 2:
            admin_steps[uid] = {"action": "validity_pick_user"}
            return bot.send_message(callback.message.chat.id, "Send target User ID:")

        # -----------------------
        # LIST USERS
        # -----------------------
        if section == "list_users":
            users = db.list_users()
            text = "\n".join([f"{u['id']} @{u.get('username')} | credits={u.get('credits')}" for u in users])
            return bot.send_message(callback.message.chat.id, text or "No users")

        # -----------------------
        # LIST PREMIUM (Start/End pretty)
        # -----------------------
        if section == "list_premium":
            users = db.list_premium_users()
            lines = []
            for u in users:
                lines.append(
                    f"👤 User: {u['id']}\n"
                    f"💳 Credits: {u.get('credits') or 0}\n"
                    f"✅ Start: {pretty_date(u.get('validity_start_at'))}\n"
                    f"⏳ End: {pretty_date(u.get('validity_expire_at'))}\n"
                    f"----------------------"
                )
            return bot.send_message(callback.message.chat.id, "\n".join(lines) or "No premium users")

        # -----------------------
        # BROADCAST
        # -----------------------
        if section == "broadcast":
            admin_steps[uid] = {"action": "broadcast"}
            return bot.send_message(callback.message.chat.id, "Send broadcast message:")

        # -----------------------
        # DEFAULT VOICE ID
        # -----------------------
        if section == "default_voice":
            admin_steps[uid] = {"action": "set_default_voice"}
            return bot.send_message(callback.message.chat.id, "Send new Default Voice ID:")

        # -----------------------
        # VOICES PANEL (click -> change id)
        # -----------------------
        if section == "voices" and len(parts) == 2:
            models = _get_models_from_db(db)
            current_default = db.get_setting("default_voice_id", DEFAULT_MODELS[0]["id"])
            text = (
                f"🎛️ Default Voice Settings\n\n"
                f"Current default voice id:\n{current_default}\n\n"
                f"Select a voice to change ID:"
            )
            return bot.send_message(callback.message.chat.id, text, reply_markup=build_voices_keyboard(models))

        if section == "voices" and len(parts) > 2 and parts[2] == "edit":
            idx = int(parts[3])
            models = _get_models_from_db(db)
            if idx < 0 or idx >= len(models):
                return bot.send_message(callback.message.chat.id, "❌ Invalid voice")

            v = models[idx]
            admin_steps[uid] = {"action": "voice_edit_apply", "index": idx}
            return bot.send_message(
                callback.message.chat.id,
                f"🎙 Voice: {v.get('name')}\n"
                f"Current voice id:\n{v.get('id')}\n\n"
                f"Send new Voice ID:"
            )

        if section == "voices" and len(parts) > 2 and parts[2] == "add":
            admin_steps[uid] = {"action": "voice_add"}
            return bot.send_message(callback.message.chat.id, "Send voice as:\n<voice_id> | <voice_name>")

        if section == "voices" and len(parts) > 2 and parts[2] == "reset":
            _set_models_to_db(db, DEFAULT_MODELS)
            db.set_setting("default_voice_id", DEFAULT_MODELS[0]["id"])
            return bot.send_message(callback.message.chat.id, "✅ Voices reset to config defaults.")

        # -----------------------
        # DOWNLOAD DB
        # -----------------------
        if section == "download":
            try:
                with open(DB_PATH, "rb") as f:
                    return bot.send_document(callback.message.chat.id, f)
            except Exception:
                return bot.send_message(callback.message.chat.id, "DB not found!")

    # -----------------------
    # STEP HANDLER
    # -----------------------
    @bot.message_handler(func=lambda m: m.from_user.id in admin_steps)
    def step_handler(msg):
        uid = msg.from_user.id
        step = admin_steps.pop(uid, None)
        if not step:
            return

        action = step.get("action")

        try:
            # -------- Credits flow --------
            if action == "credits_pick_user":
                user_id = parse_int(msg.text)
                admin_steps[uid] = {"action": "credits_pick_amount", "target": user_id}
                return bot.send_message(msg.chat.id, f"User {user_id}\nSend credits amount (e.g. 50):")

            if action == "credits_pick_amount":
                amount = parse_int(msg.text)
                target = int(step.get("target"))
                db.ensure_user(target, None)
                db.add_credits(target, amount)
                return bot.send_message(msg.chat.id, f"✅ Added {amount} credits to {target}")

            # -------- Validity flow --------
            if action == "validity_pick_user":
                user_id = parse_int(msg.text)
                admin_steps[uid] = {"action": "validity_pick_days", "target": user_id}
                return bot.send_message(msg.chat.id, f"User {user_id}\nSend validity days (e.g. 30):")

            if action == "validity_pick_days":
                days = parse_int(msg.text)
                target = int(step.get("target"))
                db.ensure_user(target, None)
                db.set_validity(target, days)
                u = db.get_user(target) or {}
                return bot.send_message(
                    msg.chat.id,
                    f"✅ Validity set for {target}\n"
                    f"Start: {pretty_date(u.get('validity_start_at'))}\n"
                    f"End: {pretty_date(u.get('validity_expire_at'))}"
                )

            # -------- Default voice --------
            if action == "set_default_voice":
                voice_id = (msg.text or "").strip()
                if len(voice_id) < 10:
                    return bot.send_message(msg.chat.id, "❌ Invalid Voice ID")
                db.set_setting("default_voice_id", voice_id)
                return bot.send_message(msg.chat.id, f"✅ Default voice updated:\n{voice_id}")

            # -------- Add voice --------
            if action == "voice_add":
                raw = (msg.text or "").strip()
                if "|" not in raw:
                    return bot.send
