from typing import Dict
import re
import telebot
from telebot import types
from config import DB_PATH


def parse_int(text: str) -> int:
    nums = re.findall(r"\d+", text or "")
    if not nums:
        raise ValueError("No number found")
    return int(nums[0])


def build_admin_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Manage Credits", callback_data="admin:credits"))
    kb.add(types.InlineKeyboardButton("Manage Validity", callback_data="admin:validity"))
    kb.add(types.InlineKeyboardButton("List Users", callback_data="admin:list_users"))
    kb.add(types.InlineKeyboardButton("List Premium Users", callback_data="admin:list_premium"))
    kb.add(types.InlineKeyboardButton("Broadcast", callback_data="admin:broadcast"))
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
        # CREDITS (LIST or USER ID)
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
            admin_steps[uid] = {"action": "credits_pick_user"}
            return bot.send_message(callback.message.chat.id, "Send target User ID (numeric):")

        if section == "credits" and len(parts) > 2 and parts[2] == "user":
            user_id = int(parts[3])
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Add Credits", callback_data=f"admin:credits:add:{user_id}"))
            kb.add(types.InlineKeyboardButton("Remove Credits", callback_data=f"admin:credits:remove:{user_id}"))
            kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:credits"))
            return bot.send_message(callback.message.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

        if section == "credits" and len(parts) > 2 and parts[2] in ("add", "remove"):
            admin_steps[uid] = {"action": parts[2], "target": int(parts[3])}
            return bot.send_message(callback.message.chat.id, "Send credit amount:")

        # -----------------------
        # VALIDITY (LIST or USER ID)
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
            admin_steps[uid] = {"action": "validity_pick_user"}
            return bot.send_message(callback.message.chat.id, "Send target User ID (numeric):")

        if section == "validity" and len(parts) > 2 and parts[2] == "user":
            user_id = int(parts[3])
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("Set Validity", callback_data=f"admin:validity:set:{user_id}"))
            kb.add(types.InlineKeyboardButton("Remove Validity", callback_data=f"admin:validity:remove:{user_id}"))
            kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:validity"))
            return bot.send_message(callback.message.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

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
            admin_steps[uid] = {"action": "broadcast"}
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
            # ✅ manual: user id for credits
            if action == "credits_pick_user":
                user_id = parse_int(msg.text)
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("Add Credits", callback_data=f"admin:credits:add:{user_id}"))
                kb.add(types.InlineKeyboardButton("Remove Credits", callback_data=f"admin:credits:remove:{user_id}"))
                kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:credits"))
                return bot.send_message(msg.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

            # ✅ manual: user id for validity
            if action == "validity_pick_user":
                user_id = parse_int(msg.text)
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("Set Validity", callback_data=f"admin:validity:set:{user_id}"))
                kb.add(types.InlineKeyboardButton("Remove Validity", callback_data=f"admin:validity:remove:{user_id}"))
                kb.add(types.InlineKeyboardButton("⬅ Back", callback_data="admin:validity"))
                return bot.send_message(msg.chat.id, f"User {user_id}\nChoose action:", reply_markup=kb)

            # ✅ add credits
            if action == "add":
                amount = parse_int(msg.text)
                db.ensure_user(target, None)
                db.add_credits(target, amount)
                return bot.send_message(msg.chat.id, f"✔ Added {amount} credits to {target}")

            # ✅ remove credits
            if action == "remove":
                amount = parse_int(msg.text)
                db.ensure_user(target, None)
                db.remove_credits(target, amount)
                return bot.send_message(msg.chat.id, f"✔ Removed {amount} credits from {target}")

            # ✅ set validity
            if action == "set_validity":
                days = parse_int(msg.text)
                db.ensure_user(target, None)
                db.set_validity(target, days)
                return bot.send_message(msg.chat.id, f"✔ Validity set for {target}")

            # ✅ broadcast
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

                return bot.send_message(msg.chat.id, f"📣 Broadcast finished.\n✅ Sent: {sent}\n❌ Failed: {failed}")

        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Error: {e}")
