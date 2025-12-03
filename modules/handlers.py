# modules/handlers.py

from modules.utils import (
    log,
    is_command,
    extract_username,
    reply_to,
)
from modules.permissions import (
    is_dev,
    is_group_owner,
    is_admin,
    has_bot_admin,
    add_bot_admin,
    remove_bot_admin,
)
from modules.group_actions import (
    kick_user,
    accept_user,
    user_exists_in_group,
)
from modules.state import (
    is_group_active,
    activate_group,
    deactivate_group,
    set_group_owner,
)
from modules.tickets import send_ticket_to_admins


def handle_message(thread, msg):
    text = msg.text or ""
    sender = msg.user_id
    reply_user = msg.reply_user_id

    # === رسائل سجل
    log(f"رسالة جديدة من {sender}: {text}")

    # ===== تجاهل غير المجموعات =====
    if thread.thread_type != "group":
        return

    # ===== التحقق هل البوت مُفعل في هذه المجموعة =====
    group_id = thread.thread_id

    # أمر /تفعيل يعمل فقط من الديف
    if text == "/تفعيل" and is_dev(sender):
        activate_group(group_id)
        reply_to(thread, msg, "تم تفعيل البوت في هذه المجموعة")
        return

    # أمر /غادر يعمل فقط من الديف
    if text == "/غادر" and is_dev(sender):
        deactivate_group(group_id)
        reply_to(thread, msg, "تم تعطيل البوت والمغادرة")
        thread.leave_group()
        return

    # قبل التفعيل: تجاهل
    if not is_group_active(group_id):
        return

    # ===== أمر /تعرف (الديف فقط) =====
    if text.startswith("/تعرف") and is_dev(sender):
        if not reply_user:
            reply_to(thread, msg, "الرجاء الرد على المستخدم المراد")
            return

        set_group_owner(group_id, reply_user)
        reply_to(thread, msg, f"تم التعرف على @{reply_user} كمؤسس للمجموعة")
        return

    # ===== أوامر الادمن والرفع =====
    owner = is_group_owner(group_id, sender)

    # أمر /ادمن
    if text.startswith("/ادمن"):
        if not owner and not is_dev(sender):
            return  # تجاهل بدون رسالة

        target = extract_username(text, reply_user)
        if not target:
            reply_to(thread, msg, "لم أستطع العثور على المستخدم")
            return

        add_bot_admin(group_id, target)
        reply_to(thread, msg, f"@{target} صار له صلاحيات ادمن في القروب")
        return

    # أمر /سحب
    if text.startswith("/سحب"):
        if not owner and not is_dev(sender):
            return

        target = extract_username(text, reply_user)
        if not target:
            reply_to(thread, msg, "لم أستطع العثور على المستخدم")
            return

        remove_bot_admin(group_id, target)
        reply_to(thread, msg, f"@{target} سحبت منه صلاحيات الادمن")
        return

    # ===== أوامر الطرد =====
    if text.startswith("/طرد") or text.startswith("/kik"):

        # فقط للادمن الحقيقيين أو الادمن داخل البوت
        if not is_admin(thread, sender) and not has_bot_admin(group_id, sender) and not owner and not is_dev(sender):
            return

        target = extract_username(text, reply_user)
        if not target:
            reply_to(thread, msg, "لم أستطع العثور على المستخدم")
            return

        # منع طرد الادمن الحقيقيين أو المرفوعين
        if is_admin(thread, target) or has_bot_admin(group_id, target):
            if not owner and not is_dev(sender):
                reply_to(thread, msg, "ما تقدر تطرد ادمن")
                return

        if not user_exists_in_group(thread, target):
            reply_to(thread, msg, f"@{target} ما حصلته")
            return

        kick_user(thread, target)
        reply_to(thread, msg, f"@{target} Kik")
        return

    # ===== أمر القبول =====
    if text.startswith("/قبول"):
        if not is_admin(thread, sender) and not has_bot_admin(group_id, sender) and not owner and not is_dev(sender):
            return

        target = extract_username(text)

        if not target:
            reply_to(thread, msg, "لم أستطع العثور على المستخدم")
            return

        if not accept_user(thread, target):
            reply_to(thread, msg, f"@{target} ما حصلته")
            return

        reply_to(thread, msg, f"@{target} قبلته")
        return

    # ===== نظام التكت =====
    if text.startswith("/تكت"):
        complaint = text.replace("/تكت", "").strip()

        if complaint == "":
            reply_to(thread, msg, "يرجى كتابة التكت بعد الأمر")
            return

        send_ticket_to_admins(thread, sender, complaint)
        reply_to(thread, msg, "رفعت التكت للادمنز")
        return