# handlers.py

from modules.admin import process_admin_commands
from modules.games import process_game
from modules.protection import process_protection

def handle_message(thread, msg):
    text = msg.text or ""

    # حماية
    if process_protection(thread, msg):
        return

    # أوامر الادمن
    if process_admin_commands(thread, msg):
        return

    # الألعاب
    if process_game(thread, msg):
        return