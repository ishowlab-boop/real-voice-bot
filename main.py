import logging
import os
import threading
import time
import telebot
from telebot.types import BotCommand
from config import TELEGRAM_BOT_TOKEN, DB_PATH, VOICES_DIR, ADMIN_IDS, USE_WEBHOOK, WEBHOOK_BASE_URL, PORT
from db import Database
from admin_panel import register_admin_handlers
from user_panel import register_user_handlers
from scheduler import start_expiry_cleanup_thread


def set_commands(bot: telebot.TeleBot):
    commands = [
        BotCommand("start", "Start"),
        BotCommand("admin", "Admin panel"),
    ]
    try:
        bot.set_my_commands(commands)
    except Exception:
        pass


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        telebot.logger.setLevel(logging.DEBUG)
    except Exception:
        pass
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    os.makedirs(VOICES_DIR, exist_ok=True)
    db = Database(DB_PATH)
    for aid in ADMIN_IDS:
        db.add_admin(aid)
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="HTML")
    register_admin_handlers(bot, db)
    register_user_handlers(bot, db)
    set_commands(bot)
    start_expiry_cleanup_thread(db, bot)
    # Decide between webhook mode (Railway) and local polling
    if USE_WEBHOOK and WEBHOOK_BASE_URL:
        # Lazy import Flask only when needed
        try:
            from flask import Flask, request
        except Exception as e:
            logging.error(f"Flask not installed; falling back to polling: {e}")
            try:
                bot.remove_webhook()
            except Exception:
                pass
            try:
                me = bot.get_me()
                print(f"Bot started, polling as @{me.username}")
                for aid in ADMIN_IDS[:1]:
                    try:
                        bot.send_message(aid, f"Bot @{me.username} is online and polling.")
                    except Exception:
                        pass
            except Exception:
                print("Bot started, polling...")
            bot.infinity_polling(skip_pending=True, allowed_updates=['message','callback_query'])
            return

        app = Flask(__name__)

        @app.get("/health")
        def health():
            return "OK", 200

        @app.post(f"/{TELEGRAM_BOT_TOKEN}")
        def telegram_webhook():
            try:
                json_str = request.get_data().decode("utf-8")
                update = telebot.types.Update.de_json(json_str)
                bot.process_new_updates([update])
            except Exception as e:
                logging.exception(f"Webhook processing error: {e}")
                return "ERROR", 500
            return "OK", 200

        # Set webhook to Railway public URL with simple retries to avoid 429
        webhook_url = WEBHOOK_BASE_URL.rstrip("/") + f"/{TELEGRAM_BOT_TOKEN}"

        def set_webhook_with_retry(b: telebot.TeleBot, url: str, retries: int = 3):
            for attempt in range(retries):
                try:
                    b.set_webhook(url=url)
                    return
                except Exception as e:
                    # Remove existing webhook and retry with small backoff
                    try:
                        b.remove_webhook()
                    except Exception:
                        pass
                    time.sleep(1 + attempt)
            # Final attempt
            b.set_webhook(url=url)

        set_webhook_with_retry(bot, webhook_url)

        try:
            me = bot.get_me()
            print(f"Bot started, webhook as @{me.username} -> {webhook_url}")
            for aid in ADMIN_IDS[:1]:
                try:
                    bot.send_message(aid, f"Bot @{me.username} is online (webhook) at {webhook_url}.")
                except Exception:
                    pass
        except Exception:
            print("Bot started in webhook mode.")

        # Start Flask server on Railway-provided PORT
        app.run(host="0.0.0.0", port=PORT)
    else:
        # Local/dev: polling mode
        try:
            bot.remove_webhook()
        except Exception:
            pass
        try:
            me = bot.get_me()
            print(f"Bot started, polling as @{me.username}")
            # Notify first admin the bot is online
            for aid in ADMIN_IDS[:1]:
                try:
                    bot.send_message(aid, f"Bot @{me.username} is online and polling.")
                except Exception:
                    pass
        except Exception:
            print("Bot started, polling...")
        bot.infinity_polling(skip_pending=True, allowed_updates=['message','callback_query'])


if __name__ == "__main__":
    main()