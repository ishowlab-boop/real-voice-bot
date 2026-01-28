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
        return dt.strftime("%A, %d %b %Y")
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
    kb.add(types.InlineKeyboardButton("♻️ Reset Voices", callback_data="admin:voices:reset"))
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
        # MENU
        # -----------------------
        if section == "menu":
            return bot.send_message(callback.message.chat.id, "⚙️ Admin Panel", reply_markup=build_admin_menu())

        # -----------------------
        # CREDITS -> ask user id
        # -----------------------
        if section == "credits" and len(parts) == 2:
            admin_steps[uid] = {"action": "credits_pick_user"}
            return bot.send_message(callback.message.chat.id, "Send User ID for credits:")

        # -----------------------
        # VALIDITY -> ask user id
        # -----------------------
        if section == "validity" and len(parts) == 2:
            admin_steps[uid] = {"action": "validity_pick_user"}
            return bot.send_message(callback.message.chat.id, "Send User ID for validity:")

        # -----------------------
        # PREMIUM LIST (pretty start/end)
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
        # VOICES
        # -----------------------
        if section == "voices" and len(parts) == 2:
            models = _get_models_from_db(db)
            return bot.send_message(
                callback.message.chat.id,
                "🎛 Manage Voices\nSelect a voice to change ID:",
                reply_markup=build_voices_keyboard(models),
            )

        if section == "voices" and len(parts) > 2 and parts[2] == "edit":
            idx = int(parts[3])
            models = _get_models_from_db(db)
            if idx < 0 or idx >= len(models):
                return bot.send_message(callback.message.chat.id, "❌ Invalid voice")
            v = models[idx]
            admin_steps[uid] = {"action": "voice_edit_apply", "index": idx}
            return bot.send_message(
                callback.message.chat.id,
                f"🎙 Voice: {v.get('name')}\nCurrent ID:\n{v.get('id')}\n\nSend NEW Voice ID:"
            )

        if section == "voices" and len(parts) > 2 and parts[2] == "add":
            admin_steps[uid] = {"action": "voice_add"}
            return bot.send_message(callback.message.chat.id, "Send: <voice_id> | <voice_name>")

        if section == "voices" and len(parts) > 2 and parts[2] == "reset":
            _set_models_to_db(db, DEFAULT_MODELS)
            db.set_setting("default_voice_id", DEFAULT_MODELS[0]["id"])
            return bot.send_message(callback.message.chat.id, "✅ Voices reset done!")

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
        step = admin_steps.get(uid)
        if not step:
            return

        action = step.get("action")

        try:
            # -------- credits: pick user id -> show add/remove buttons
            if action == "credits_pick_user":
                user_id = parse_int(msg.text)
                db.ensure_user(user_id, None)
                admin_steps.pop(uid, None)

                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("➕ Add Credits", callback_data=f"admin:credits_add:{user_id}"))
                kb.add(types.InlineKeyboardButton("➖ Remove Credits", callback_data=f"admin:credits_remove:{user_id}"))
                kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:menu"))
                return bot.send_message(msg.chat.id, f"User {user_id}\nChoose:", reply_markup=kb)

            # -------- validity: pick user id -> ask days
            if action == "validity_pick_user":
                user_id = parse_int(msg.text)
                db.ensure_user(user_id, None)
                admin_steps[uid] = {"action": "validity_days", "target": user_id}
                return bot.send_message(msg.chat.id, f"User {user_id}\nSend validity days (example: 30):")

            if action == "validity_days":
                days = parse_int(msg.text)
                target = int(step.get("target"))
                admin_steps.pop(uid, None)
                db.ensure_user(target, None)
                db.set_validity(target, days)
                return bot.send_message(msg.chat.id, f"✅ Validity set: {days} days for {target}")

            # -------- voice edit
            if action == "voice_edit_apply":
                new_id = (msg.text or "").strip()
                if len(new_id) < 10:
                    return bot.send_message(msg.chat.id, "❌ Invalid Voice ID")
                idx = int(step.get("index"))
                admin_steps.pop(uid, None)

                models = _get_models_from_db(db)
                if idx < 0 or idx >= len(models):
                    return bot.send_message(msg.chat.id, "❌ Invalid voice index")

                models[idx]["id"] = new_id
                _set_models_to_db(db, models)
                return bot.send_message(msg.chat.id, f"✅ Voice updated:\n{models[idx].get('name')}\n{new_id}")

            # -------- voice add
            if action == "voice_add":
                raw = (msg.text or "").strip()
                if "|" not in raw:
                    return bot.send_message(msg.chat.id, "❌ Use: <voice_id> | <voice_name>")
                vid, vname = [x.strip() for x in raw.split("|", 1)]
                if len(vid) < 10:
                    return bot.send_message(msg.chat.id, "❌ Invalid voice id")
                admin_steps.pop(uid, None)

                models = _get_models_from_db(db)
                models.append({"id": vid, "name": vname or vid})
                _set_models_to_db(db, models)
                return bot.send_message(msg.chat.id, "✅ Voice added successfully!")

        except Exception as e:
            admin_steps.pop(uid, None)
            bot.send_message(msg.chat.id, f"❌ Error: {e}")

    # -----------------------
    # CALLBACKS: credits add/remove amount
    # -----------------------
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin:credits_add:"))
    def credits_add_cb(callback):
        if not ensure_admin(callback.from_user.id):
            return bot.answer_callback_query(callback.id)
        user_id = int(callback.data.split(":")[2])
        admin_steps[callback.from_user.id] = {"action": "credits_add_amount", "target": user_id}
        bot.answer_callback_query(callback.id)
        bot.send_message(callback.message.chat.id, f"Send amount to ADD for {user_id}:")

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin:credits_remove:"))
    def credits_remove_cb(callback):
        if not ensure_admin(callback.from_user.id):
            return bot.answer_callback_query(callback.id)
        user_id = int(callback.data.split(":")[2])
        admin_steps[callback.from_user.id] = {"action": "credits_remove_amount", "target": user_id}
        bot.answer_callback_query(callback.id)
        bot.send_message(callback.message.chat.id, f"Send amount to REMOVE for {user_id}:")

    @bot.message_handler(func=lambda m: m.from_user.id in admin_steps and admin_steps[m.from_user.id].get("action") in ("credits_add_amount", "credits_remove_amount"))
    def credits_amount_handler(msg):
        uid = msg.from_user.id
        step = admin_steps.pop(uid, None)
        if not step:
            return

        try:
            amount = parse_int(msg.text)
            target = int(step.get("target"))
            db.ensure_user(target, None)

            if step.get("action") == "credits_add_amount":
                db.add_credits(target, amount)
                return bot.send_message(msg.chat.id, f"✅ Added {amount} credits to {target}")

            if step.get("action") == "credits_remove_amount":
                db.remove_credits(target, amount)
                return bot.send_message(msg.chat.id, f"✅ Removed {amount} credits from {target}")

        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Error: {e}")
