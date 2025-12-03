# modules/listener.py

from modules.ig_api import IG
from modules.admin import ADMIN
from modules.protection import PROTECT   # ← أضفته هنا
from modules.utils import log

LAST_MESSAGES = {}   # لمنع إعادة معالجة نفس الرسالة


def normalize_message(item):
    """
    تحويل أي رسالة/حدث من إنستقرام إلى دكت مفهوم داخل البوت.
    يدعم جميع الأنواع تمامًا مثل ما تظهر للمستخدم:

    ✔ نص
    ✔ طرد عضو
    ✔ إضافة عضو
    ✔ مغادرة
    ✔ تغيير اسم القروب
    ✔ تغيير صورة القروب
    ✔ كل الـ action_log
    ✔ أي item_type مستقبلية (fallback)
    """

    msg_type = item.get("item_type")
    user_id = str(item.get("user_id") or "")

    # ============ 1) نص عادي ============
    if msg_type == "text":
        return {
            "type": "text",
            "text": item.get("text", "").strip(),
            "user_id": user_id,
            "raw": item
        }

    # ============ 2) طرد ============
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

        # مغادرة عضو
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

        # إضافة عضو (من action_log)
        if "added" in action and "to the group" in action:
            return {
                "type": "add_user",
                "actor_id": user_id,
                "raw": item
            }

        # أي شيء آخر
        return {
            "type": "action_log",
            "text": action,
            "raw": item
        }

    # ============ 5) fallback لأي item_type ثاني ============
    return {
        "type": msg_type,
        "raw": item
    }


def process_thread(thread):
    """
    تحليل ثريد واحد وإرسال أحدث حدث لنظام الأدمن + نظام الحماية
    """

    thread_id = thread.get("thread_id")
    users = thread.get("users", [])
    is_group = len(users) > 2  # IG: قروب = 3 أعضاء+

    items = thread.get("items", [])
    if not items:
        return

    last_item = items[0]  # أحدث شيء

    # منع التكرار
    msg_key = f"{thread_id}:{last_item.get('item_id')}"
    if LAST_MESSAGES.get(msg_key):
        return
    LAST_MESSAGES[msg_key] = True

    # تحليل الحدث
    msg = normalize_message(last_item)

    # ====== ✨ إرسال لنظام الحماية ======
    PROTECT.handle_event(
        thread_id=thread_id,
        msg=msg,
        is_group=is_group,
        users=users
    )

    # ====== ✨ إرسال إلى نظام الأدمن ======
    ADMIN.process_command(
        thread_id=thread_id,
        msg=msg,
        is_group=is_group,
        thread_users=users
    )


def check_inbox():
    """
    يجلب كل الثريدات ويرسل آخر حدث من كل واحد
    """

    threads = IG.get_inbox()
    if not threads:
        return

    for th in threads:
        full_items = IG.get_thread_messages(th["thread_id"])
        if full_items:
            th["items"] = full_items[::-1]  # ترتيب من القديم إلى الجديد
            process_thread(th)