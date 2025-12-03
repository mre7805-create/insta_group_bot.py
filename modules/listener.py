# modules/listener.py

from modules.ig_api import IG
from modules.admin import ADMIN
from modules.utils import log  # حذفنا extract_text لأنه غير مستخدم

LAST_MESSAGES = {}   # لمنع تكرار الرسائل من إنستقرام


def normalize_message(item):
    """
    يحول رسالة إنستقرام إلى دكت نظيف تُستخدم في نظامك
    """
    msg_type = item.get("item_type")
    user_id = str(item.get("user_id"))

    text = ""
    if msg_type == "text":
        text = item.get("text", "")

    return {
        "user_id": user_id,
        "text": text.strip(),
        "type": msg_type
    }


def process_thread(thread):
    """
    معالجة Thread واحد
    """
    thread_id = thread.get("thread_id")
    users = thread.get("users", [])
    is_group = len(users) > 2  # IG group chat logic

    items = thread.get("items", [])
    if not items:
        return

    last_item = items[0]

    # منع إعادة المعالجة
    msg_key = f"{thread_id}:{last_item.get('item_id')}"
    if LAST_MESSAGES.get(msg_key):
        return
    LAST_MESSAGES[msg_key] = True

    msg = normalize_message(last_item)

    # إرسال إلى نظام الأدمن
    ADMIN.process_command(
        thread_id=thread_id,
        msg=msg,
        is_group=is_group,
        thread_users=users
    )


def check_inbox():
    """
    يجلب كل الثريدات ويمررها واحد واحد لـ process_thread()
    """
    threads = IG.get_inbox()
    if not threads:
        return

    for th in threads:
        full = IG.get_thread_messages(th["thread_id"])
        if full:
            th["items"] = full[::-1]  # ترتيب عكسي (من أقدم إلى أحدث)
            process_thread(th)