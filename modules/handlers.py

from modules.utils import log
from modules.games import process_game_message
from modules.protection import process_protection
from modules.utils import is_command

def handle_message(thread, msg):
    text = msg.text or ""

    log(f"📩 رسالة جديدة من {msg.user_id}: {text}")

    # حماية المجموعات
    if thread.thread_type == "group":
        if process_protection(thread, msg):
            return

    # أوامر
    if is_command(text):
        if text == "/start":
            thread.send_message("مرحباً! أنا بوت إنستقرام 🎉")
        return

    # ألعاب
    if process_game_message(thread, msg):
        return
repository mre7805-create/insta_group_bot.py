# modules/handlers.py

from modules.utils import log
from modules.games import process_game_message
from modules.protection import process_protection
from modules.utils import is_command

def handle_message(thread, msg):
    text = msg.text or ""

    log(f"📩 رسالة جديدة من {msg.user_id}: {text}")

    # حماية المجموعات
    if thread.thread_type == "group":
        if process_protection(thread, msg):
            return

    # أوامر
    if is_command(text):
        if text == "/start":
            thread.send_message("مرحباً! أنا بوت إنستقرام 🎉")
        return

    # ألعاب
    if process_game_message(thread, msg):
        return