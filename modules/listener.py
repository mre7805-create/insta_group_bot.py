# modules/listener.py

from modules.ig_api import IG
from modules.admin import ADMIN
from modules.utils import log

LAST_MESSAGES = {}   # لمنع تكرار الرسائل


def normalize_message(item):
    """
    تحويل أي رسالة/حدث من إنستقرام إلى دكت مفهوم داخل البوت
    يدعم:
    - نص
    - طرد
    - إضافة عضو
    - مغادرة عضو
    - تغيير اسم القروب
    - تغيير صورة القروب
    - action_log
    - كل item_type أخرى
    """

    msg_type = item.get("item_type")
    user_id = str(item.get("user_id") or "")  # قد يكون فارغ عند بعض الأحداث

    # ============ 1) رسائل نصية ============
    if msg_type == "text":
        return {
            "type": "text",
            "text": item.get("text", "").strip(),
            "user_id": user_id,
            "raw": item
        }

    # ============ 2) طرد عضو ============
    if msg_type == "remove_user":
        return {
            "type": "remove_user",
            "actor_id": str(item.get("actor_id") or ""),
            "target_ids": [str(u) for u in item.get("users", [])],
            "raw": item
        }

    # ============ 3) إضافة عضو ============
    if msg_type == "add_user":
        return {
            "type": "add_user",
            "actor_id": str(item.get("actor_id") or ""),
            "target_ids": [str(u) for u in item.get("users", [])],
            "raw": item
        }

    # ============ 4) أحداث action_log ============
    if msg_type == "action_log":
        action = item.get("action_log", {}).get("description", "").lower()

        # غادر القروب
        if "left the group" in action:
            return {
                "type": "left_group",
                "actor_id": user_id,
                "raw": item
            }

        # تغيير اسم القروب
        if "changed the group name to" in action:
            new_name = action.replace("changed the group name to", "").strip(" '")
            return {
                "type": "group_name_changed",
                "actor_id": user_id,
                "new_name": new_name,
                "raw": item
            }

        # تغيير صورة القروب
        if "changed the group photo" in action:
            return {
                "type": "group_photo_changed",
                "actor_id": user_id,
                "raw": item
            }

        # إضافة عضو من خلال action_log
        if "added" in action and "to the group" in action:
            return {
                "type": "add_user",
                "actor_id": user_id,
                "raw": item
            }

        # أي action آخر
        return {
            "type": "action_log",
            "text": action,
            "raw": item
        }

    # ============ 5) fallback ============
    return {
        "type": msg_type,
        "raw": item
    }


def process_thread(thread):
    thread_id = thread.get("thread_id")
    users = thread.get("users", [])
    is_group = len(users) > 2  # IG يعتبر 3+ = قروب

    items = thread.get("items", [])
    if not items:
        return

    last_item = items[0]  # أحدث رسالة/حدث

    # منع التكرار
    msg_key = f"{thread_id}:{last_item.get('item_id')}"
    if LAST_MESSAGES.get(msg_key):
        return
    LAST_MESSAGES[msg_key] = True

    msg = normalize_message(last_item)

    # إرسال الحدث لنظام الأدمن
    ADMIN.process_command(
        thread_id=thread_id,
        msg=msg,
        is_group=is_group,
        thread_users=users
    )


def check_inbox():
    threads = IG.get_inbox()
    if not threads:
        return

    for th in threads:
        full = IG.get_thread_messages(th["thread_id"])
        if full:
            th["items"] = full[::-1]  # ترتيب من الأقدم للأحدث
            process_thread(th)