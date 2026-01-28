from typing import Dict
import json
import telebot
from telebot import types
from config import DB_PATH, DEFAULT_MODELS


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


def build_user_list_keyboard(users, prefix: str):
    kb = types.InlineKeyboardMarkup()
    for u in users:
        label = f"{u['id']} @{u.get('username') or 'unknown'}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"{prefix}:{u['id']}"))
    kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:menu"))
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
                return out or DEFAULT_MODELS
        except Exception:
            pass
    return DEFAULT_MODELS


def _set_models_to_db(db, models):
    db.set_setting("models_json", json.dumps(models, ensure_ascii=False))


def _voices_text(models):
    lines = ["🎛️ Voices list:"]
    for i, m in enumerate(models, start=1):
        lines.append(f"{i}) {m.get('name')}  |  {m.get('id')}")
    return "\n".join(lines)


def register_admin_handlers(bot: telebot.TeleBot, db):
    admin_steps: Dict[int, Dict] = {}

    def ensure_admin(uid: int):
        return db.is_admin(uid)

    @bot.message_handler(commands=["admin"])
    def admin_cmd(message):
        if not ensure_admin(message.from_user.id):
            return
        bot.send_message(message.chat.id, "⚙️ Admin Panel", reply_markup=build_admin_menu())

    @bot.callback_query_handler(func=lambda c: c.data.startswith("admin:"))
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
            return bot.edit_message_reply_markup(
                callback.message.chat.id,
                callback.message.message_id,
                build_admin_menu()
            )

        # -----------------------
        # DEFAULT VOICE ID
        # -----------------------
        if section == "default_voice":
            admin_steps[uid] = {"action": "set_default_voice", "target": 0}
            return bot.send_message(callback.message.chat.id, "Send new Default Voice ID:")

        # -----------------------
        # VOICES MANAGEMENT
        # -----------------------
        if section == "voices":
            models = _get_models_from_db(db)
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("➕ Add Voice", callback_data="admin:voices:add"))
            kb.add(types.InlineKeyboardButton("✏️ Edit Voice (by number)", callback_data="admin:voices:edit"))
            kb.add(types.InlineKeyboardButton("🗑 Remove Voice (by number)", callback_data="admin:voices:remove"))
            kb.add(types.InlineKeyboardButton("♻️ Reset to Config Voices", callback_data="admin:voices:reset"))
            kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:menu"))
            return bot.send_message(callback.message.chat.id, _voices_text(models), reply_markup=kb)

        if section == "voices" and len(parts) > 2 and parts[2] == "add":
            admin_steps[uid] = {"action": "voice_add", "target": 0}
            return bot.send_message(
                callback.message.chat.id,
                "Send voice as:\n<voice_id> | <voice_name>\n\nExample:\nabc123... | Marie"
            )

        if section == "voices" and len(parts) > 2 and parts[2] == "edit":
            models = _get_models_from_db(db)
            admin_steps[uid] = {"action": "voice_edit_pick", "count": len(models)}
            return bot.send_message(
                callback.message.chat.id,
                _voices_text(models) + "\n\nSend voice number to edit (e.g., 1):"
            )

        if section == "voices" and len(parts) > 2 and parts[2] == "remove":
            models = _get_models_from_db(db)
            admin_steps[uid] = {"action": "voice_remove", "count": len(models)}
            return bot.send_message(
                callback.message.chat.id,
                _voices_text(models) + "\n\nSend voice number to remove (e.g., 2):"
            )

        if section == "voices" and len(parts) > 2 and parts[2] == "reset":
            _set_models_to_db(db, DEFAULT_MODELS)
            db.set_setting("default_voice_id", DEFAULT_MODELS[0]["id"])
            return bot.send_message(callback.message.chat.id, "✅ Voices reset to config defaults.")

        # -----------------------
        # CREDITS MENU (LIST or MANUAL USER ID)
        # -----------------------
        if section == "credits" and len(parts) == 2:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Select User From List", callback_data="admin:credits:list"))
            kb.add(types.InlineKeyboardButton("Enter User ID", callback_data="admin:credits:manual"))
            kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:menu"))
            return bot.send_message(callback.message.chat.id, "Credits: choose method", reply_markup=kb)

        if section == "credits" and len(parts) > 2 and parts[2] == "list":
            users = db.list_users(limit=200)
            kb = build_user_list_keyboard(users, "admin:credits:user")
            return bot.send_message(callback.message.chat.id, "Select a user:", reply_markup=kb)

        if section == "credits" and len(parts) > 2 and parts[2] == "manual":
            admin_steps[uid] = {"action": "credits_pick_user", "target": 0}
            return bot.send_message(callback.message.chat.id, "Send target User ID (numeric):")

        # -----------------------
        # VALIDITY MENU (LIST or MANUAL USER ID)
        # -----------------------
        if section == "validity" and len(parts) == 2:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Select User From List", callback_data="admin:validity:list"))
            kb.add(types.InlineKeyboardButton("Enter User ID", callback_data="admin:validity:manual"))
            kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:menu"))
            return bot.send_message(callback.message.chat.id, "Validity: choose method", reply_markup=kb)

        if section == "validity" and len(parts) > 2 and parts[2] == "list":
            users = db.list_users(limit=200)
            kb = build_user_list_keyboard(users, "admin:validity:user")
            return bot.send_message(callback.message.chat.id, "Select a user:", reply_markup=kb)

        if section == "validity" and len(parts) > 2 and parts[2] == "manual":
            admin_steps[uid] = {"action": "validity_pick_user", "target": 0}
            return bot.send_message(callback.message.chat.id, "Send target User ID (numeric):")

        # -----------------------
        # SELECTED USER FOR CREDITS (from list or manual)
        # -----------------------
        if section == "credits" and len(parts) > 2 and parts[2] == "user":
            user_id = int(parts[3])
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Add Credits", callback_data=f"admin:credits:add:{user_id}"))
            kb.add(types.InlineKeyboardButton("Remove Credits", callback_data=f"admin:credits:remove:{user_id}"))
            kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:credits"))
            return bot.send_message(callback.message.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

        # -----------------------
        # SELECTED USER FOR VALIDITY (from list or manual)
        # -----------------------
        if section == "validity" and len(parts) > 2 and parts[2] == "user":
            user_id = int(parts[3])
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Set Validity", callback_data=f"admin:validity:set:{user_id}"))
            kb.add(types.InlineKeyboardButton("Remove Validity", callback_data=f"admin:validity:remove:{user_id}"))
            kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:validity"))
            return bot.send_message(callback.message.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

        # -----------------------
        # CREDIT AMOUNT INPUT
        # -----------------------
        if section == "credits" and len(parts) > 2 and parts[2] in ("add", "remove"):
            admin_steps[uid] = {"action": parts[2], "target": int(parts[3])}
            return bot.send_message(callback.message.chat.id, "Send credit amount:")

        # -----------------------
        # VALIDITY INPUT
        # -----------------------
        if section == "validity" and len(parts) > 2 and parts[2] == "set":
            admin_steps[uid] = {"action": "set_validity", "target": int(parts[3])}
            return bot.send_message(callback.message.chat.id, "Send number of days:")

        if section == "validity" and len(parts) > 2 and parts[2] == "remove":
            target = int(parts[3])
            db.ensure_user(target, None)
            db.remove_validity(target)
            return bot.send_message(callback.message.chat.id, f"✔ Removed validity for {target}")

        # -----------------------
        # LIST USERS
        # -----------------------
        if section == "list_users":
            users = db.list_users()
            text = "\n".join([f"{u['id']} @{u.get('username')} | credits={u.get('credits')}" for u in users])
            return bot.send_message(callback.message.chat.id, text or "No users")

        # -----------------------
        # LIST PREMIUM
        # -----------------------
        if section == "list_premium":
            users = db.list_premium_users()
            text = "\n".join([f"{u['id']} credits={u.get('credits')} exp={u.get('validity_expire_at')}" for u in users])
            return bot.send_message(callback.message.chat.id, text or "No premium users")

        # -----------------------
        # BROADCAST
        # -----------------------
        if section == "broadcast":
            admin_steps[uid] = {"action": "broadcast", "target": 0}
            return bot.send_message(callback.message.chat.id, "Send broadcast message:")

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
        target = step.get("target", 0)

        try:
            # ---- manual pick credits user id ----
            if action == "credits_pick_user":
                user_id = int((msg.text or "").strip())
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("Add Credits", callback_data=f"admin:credits:add:{user_id}"))
                kb.add(types.InlineKeyboardButton("Remove Credits", callback_data=f"admin:credits:remove:{user_id}"))
                kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:credits"))
                return bot.send_message(msg.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

            # ---- manual pick validity user id ----
            if action == "validity_pick_user":
                user_id = int((msg.text or "").strip())
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("Set Validity", callback_data=f"admin:validity:set:{user_id}"))
                kb.add(types.InlineKeyboardButton("Remove Validity", callback_data=f"admin:validity:remove:{user_id}"))
                kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:validity"))
                return bot.send_message(msg.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

            # ---- credits add/remove ----
            if action == "add":
                amount = int(msg.text)
                db.ensure_user(target, None)
                db.add_credits(target, amount)
                return bot.send_message(msg.chat.id, f"✔ Added {amount} credits to {target}")

            if action == "remove":
                amount = int(msg.text)
                db.ensure_user(target, None)
                db.remove_credits(target, amount)
                return bot.send_message(msg.chat.id, f"✔ Removed {amount} credits from {target}")

            # ---- validity set ----
            if action == "set_validity":
                days = int(msg.text)
                db.ensure_user(target, None)
                db.set_validity(target, days)
                return bot.send_message(msg.chat.id, f"✔ Validity set for {target}")

            # ---- default voice ----
            if action == "set_default_voice":
                voice_id = (msg.text or "").strip()
                if len(voice_id) < 10:
                    return bot.send_message(msg.chat.id, "❌ Invalid Voice ID")
                db.set_setting("default_voice_id", voice_id)
                return bot.send_message(msg.chat.id, f"✅ Default voice updated:\n{voice_id}")

            # ---- voices manage ----
            if action == "voice_add":
                raw = (msg.text or "").strip()
                if "|" not in raw:
                    return bot.send_message(msg.chat.id, "❌ Format wrong. Use: <voice_id> | <voice_name>")
                vid, vname = [x.strip() for x in raw.split("|", 1)]
                if len(vid) < 10:
                    return bot.send_message(msg.chat.id, "❌ Invalid voice id")
                models = _get_models_from_db(db)
                models.append({"id": vid, "name": vname or vid})
                _set_models_to_db(db, models)
                return bot.send_message(msg.chat.id, "✅ Voice added. Open Manage Voices to verify.")

            if action == "voice_edit_pick":
                n = int((msg.text or "0").strip())
                count = int(step.get("count") or 0)
                if n < 1 or n > count:
                    return bot.send_message(msg.chat.id, "❌ Invalid number")
                admin_steps[uid] = {"action": "voice_edit_apply", "index": n - 1}
                return bot.send_message(
                    msg.chat.id,
                    "Send new value as:\n<voice_id> | <voice_name>\n\nExample:\nabc123... | NewName"
                )

            if action == "voice_edit_apply":
                raw = (msg.text or "").strip()
                if "|" not in raw:
                    return bot.send_message(msg.chat.id, "❌ Format wrong. Use: <voice_id> | <voice_name>")
                vid, vname = [x.strip() for x in raw.split("|", 1)]
                if len(vid) < 10:
                    return bot.send_message(msg.chat.id, "❌ Invalid voice id")

                models = _get_models_from_db(db)
                idx = int(step.get("index"))
                if idx < 0 or idx >= len(models):
                    return bot.send_message(msg.chat.id, "❌ Invalid index")

                models[idx] = {"id": vid, "name": vname or vid}
                _set_models_to_db(db, models)

                if not db.get_setting("default_voice_id", ""):
                    db.set_setting("default_voice_id", models[0]["id"])

                return bot.send_message(msg.chat.id, "✅ Voice updated. Open Manage Voices to verify.")

            if action == "voice_remove":
                n = int((msg.text or "0").strip())
                count = int(step.get("count") or 0)
                if n < 1 or n > count:
                    return bot.send_message(msg.chat.id, "❌ Invalid number")

                models = _get_models_from_db(db)
                removed = models.pop(n - 1)
                _set_models_to_db(db, models if models else DEFAULT_MODELS)

                default_vid = db.get_setting("default_voice_id", DEFAULT_MODELS[0]["id"])
                if removed.get("id") == default_vid:
                    new_default = (models[0]["id"] if models else DEFAULT_MODELS[0]["id"])
                    db.set_setting("default_voice_id", new_default)

                return bot.send_message(msg.chat.id, "✅ Voice removed. Open Manage Voices to verify.")

            # ---- broadcast ----
            if action == "broadcast":
                import time

                users = db.list_users(limit=100000)
                sent = 0
                failed = 0

                for u in users:
                    uid2 = u.get("id")
                    if not uid2:
                        continue
                    try:
                        bot.send_message(uid2, msg.text)
                        sent += 1
                        time.sleep(0.05)
                    except Exception:
                        failed += 1
                        time.sleep(0.2)

                return bot.send_message(
                    msg.chat.id,
                    f"📣 Broadcast finished.\n✅ Sent: {sent}\n❌ Failed: {failed}"
                )

        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Error: {e}")
