#!/usr/bin/env python3
"""
main.py - نقطة الدخول لبوت الإنستقرام المتعدد الوظائف
تفصيل:
- يحمّل الإعدادات من config.ini أو المتغيرات البيئية
- يحمّل الموديولات من modules/
- يشتغل بالـ polling أو webhook حسب config
"""

import os
import logging
from configparser import ConfigParser

from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ChatMemberHandler

# نحمّل الموديولات (سكلتون) - هذه الملفات ستحتوي الوظائف الفعلية
from modules import protection, games, ig_integration, utils, storage

# ---------- إعداد اللوق ----------
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- تحميل الإعداد ----------
cfg = ConfigParser()
cfg_path = os.environ.get("CONFIG_PATH", "config.ini")
if os.path.exists(cfg_path):
    cfg.read(cfg_path)
else:
    cfg.read("config.ini.example")
    logger.warning("لم يتم العثور على config.ini، يتم استخدام config.ini.example (قم بنسخ المثال وتعديله).")

BOT_TOKEN = os.environ.get("BOT_TOKEN") or cfg.get("bot", "token", fallback=None)
OWNER_ID = int(os.environ.get("OWNER_ID") or cfg.get("bot", "owner_id", fallback="0"))
USE_WEBHOOK = cfg.getboolean("server", "use_webhook", fallback=False)
WEBHOOK_URL = cfg.get("server", "webhook_url", fallback=None)
PORT = int(os.environ.get("PORT") or cfg.get("server", "port", fallback=8443))

if not BOT_TOKEN:
    logger.error("لم يتم تعيين BOT_TOKEN في البيئات أو config.ini. أوقف التنفيذ.")
    raise SystemExit("BOT_TOKEN required")

# ---------- تهيئة التخزين المحلي ----------
db = storage.SQLiteStorage("bot_data.db")  # واجهة بسيطة؛ أنشئ ملف storage.py لاحقاً
# مثال: db.get_protected_admins(chat_id) ، db.add_game_session(...)

# ---------- وظائف مساعدة للتسجيل الديناميكي للـ handlers ----------
def register_core_handlers(dp):
    # أوامر أساسية
    dp.add_handler(CommandHandler("start", utils.cmd_start))
    dp.add_handler(CommandHandler("help", utils.cmd_help))

    # ألعاب
    dp.add_handler(CommandHandler("game_start", games.cmd_start_game))
    dp.add_handler(CommandHandler("game_join", games.cmd_join_game))
    dp.add_handler(CommandHandler("game_score", games.cmd_score))

    # حماية - مراقبة تغيّر أعضاء (لمراقبة طرد/تخفيض صلاحية)
    dp.add_handler(ChatMemberHandler(protection.chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    # رسالة افتراضية
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, utils.echo_or_game_input))

# ---------- main ----------
def main():
    logger.info("Starting bot...")
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # تمرير الواجهات لموديولات منفصلة
    protection.init(db, bot_token=BOT_TOKEN, owner_id=OWNER_ID)
    games.init(db, owner_id=OWNER_ID)
    ig_integration.init(config=cfg)  # واجهة موضعية للتكامل مع إنستا

    # تسجيل الhandlers
    register_core_handlers(dp)

    # تشغيل
    if USE_WEBHOOK and WEBHOOK_URL:
        # مثال بسيط على start_webhook (يمكن ضبط SSL إلخ عند الحاجة)
        updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN)
        updater.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")
        logger.info(f"Webhook set to {WEBHOOK_URL}/{BOT_TOKEN}")
    else:
        updater.start_polling()
        logger.info("Bot started with polling.")

    updater.idle()

if __name__ == "__main__":
    main()