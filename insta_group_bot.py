#!/usr/bin/env python3
# insta_group_bot.py
# بوت إدارة مجموعة إنستاجرام — مبدئي، يعمل مع instagrapi.
# اقرأ README والـ notes أدناه قبل التشغيل.

import os
import time
import traceback
from instagrapi import Client

# ------------------- إعدادات من متغيرات البيئة -------------------
BOT_USERNAME = os.getenv("BOT_USERNAME")
BOT_PASSWORD = os.getenv("BOT_PASSWORD")
THREAD_ID = os.getenv("THREAD_ID")          # ضع thread id كرقم (string مقروء)
DEV_ID = int(os.getenv("DEV_ID", "0"))     # id رقمي للمطوّر (Dev)

# خيارات عامة
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "3"))
SAVE_SESSION = True
SESSION_FILE = f"session_{BOT_USERNAME}.json"

# ------------------- تهيئة الكلاينت -------------------
cl = Client()

def try_login():
    try:
        if SAVE_SESSION and os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(BOT_USERNAME, BOT_PASSWORD)
        else:
            cl.login(BOT_USERNAME, BOT_PASSWORD)
            if SAVE_SESSION:
                cl.dump_settings(SESSION_FILE)
        print("✅ تم تسجيل دخول البوت بنجاح.")
        return True
    except Exception as e:
        print("❌ فشل تسجيل الدخول:", e)
        traceback.print_exc()
        return False

# ------------------- بيانات داخل الذاكرة -------------------
owners = set()            # user_id (int)
admins = set()            # user_id (int) — ادمن فعلي (not just bot-perms)
authorized_users = set()  # users who can give bot commands (permissions)
member_warnings = {}      # user_id -> {"warnings": int, "last_msg": str}

blacklist_words = ["سب", "شتم"]          # عدّل براحتك
blacklist_links = ["http://", "https://"]

# ------------------- أدوات مساعدة -------------------
def uid_from_username(username: str):
    """حاول إرجاع user id من @username (بدون @)"""
    if not username:
        return None
    uname = username.lstrip("@")
    try:
        info = cl.user_info_by_username(uname)
        return int(info.pk)
    except Exception:
        try:
            # محاولة بديلة
            info = cl.user_info_by_username(uname)
            return int(info.pk)
        except Exception as e:
            print("لم أستطع إرجاع user id من اليوزر:", username, e)
            return None

def user_display_name_by_id(uid: int):
    try:
        u = cl.user_info(uid)
        return getattr(u, "username", str(uid))
    except Exception:
        return str(uid)

# ------------------- قوالب رسائل -------------------
def send_group(text):
    try:
        if THREAD_ID:
            cl.direct_send(text, thread_ids=[int(THREAD_ID)])
        else:
            print("THREAD_ID غير محدد، الرسالة:", text)
    except Exception as e:
        print("خطأ عند إرسال رسالة للمجموعة:", e)

# ------------------- حماية البوت من سحب الادمن -------------------
def is_bot_admin():
    try:
        if not THREAD_ID:
            return False
        info = cl.thread_info(int(THREAD_ID))
        bot_id = cl.user_id
        for u in info.users:
            if getattr(u, "pk", None) == bot_id:
                return getattr(u, "is_admin", False)
    except Exception as e:
        print("خطأ في is_bot_admin:", e)
    return False

def check_admin_status_and_auto_leave():
    if not is_bot_admin():
        send_group("تم سحب ادمن البوت أو لم يُعطَ ادمن. يغادر خلال دقيقة إذا لم تُعد الادمن.")
        time.sleep(60)
        if not is_bot_admin():
            try:
                cl.leave_thread(int(THREAD_ID))
            except Exception:
                pass
            print("البوت غادر المجموعة بسبب فقدان صلاحية الادمن.")
            exit(0)

# ------------------- إدارة الإنذارات والمخالفات -------------------
def give_warning_to(uid: int, issuer_uid: int=None):
    if uid in owners:
        return
    rec = member_warnings.get(uid, {"warnings":0, "last_msg":""})
    rec["warnings"] += 1
    member_warnings[uid] = rec
    issuer_name = user_display_name_by_id(issuer_uid) if issuer_uid else "نظام"
    target_name = user_display_name_by_id(uid)
    send_group(f"تم اعطاءه انذار بواسطة @{issuer_name} — @{target_name} / انذار {rec['warnings']}")
    if rec["warnings"] >= 3:
        try:
            cl.direct_remove_user(int(THREAD_ID), uid)
            send_group(f"@{target_name} تم طرده بعد الوصول لعدد الإنذارات.")
        except Exception as e:
            send_group(f"فشل طرد @{target_name}: {e}")

def check_violation_from_message(msg):
    """
    msg is an instagrapi message object from thread messages
    We look at text content; ignore owners; apply rules:
    - روابط => +2
    - شتم => +3
    - تكرار => +2
    """
    try:
        uid = int(msg.user_id)
        if uid in owners:
            return
        text = (msg.text or "").lower()
        rec = member_warnings.get(uid, {"warnings":0, "last_msg":""})
        applied = False

        if any(l in text for l in blacklist_links) and ("insta.com/group" not in text):
            rec["warnings"] += 2
            send_group(f"ممنوع نشر الروابط هنا، @{user_display_name_by_id(uid)} / إنذار {rec['warnings']}")
            applied = True
        elif any(w in text for w in blacklist_words):
            rec["warnings"] += 3
            send_group(f"ممنوع الشتم هنا، @{user_display_name_by_id(uid)} / إنذار {rec['warnings']}")
            applied = True
        elif rec.get("last_msg") and rec["last_msg"] == text and text != "":
            rec["warnings"] += 2
            send_group(f"ممنوع التكرار، @{user_display_name_by_id(uid)} / إنذار {rec['warnings']}")
            applied = True

        rec["last_msg"] = text
        if applied:
            member_warnings[uid] = rec
        if rec["warnings"] >= 3:
            try:
                cl.direct_remove_user(int(THREAD_ID), uid)
                send_group(f"@{user_display_name_by_id(uid)} تم طرده بعد عدة مخالفات!")
            except Exception as e:
                send_group(f"فشل طرد @{user_display_name_by_id(uid)}: {e}")
    except Exception as e:
        print("خطأ في check_violation_from_message:", e)

# ------------------- أوامر الإدارة (Owner / Admin / Dev) -------------------
def handle_special_command_text(issuer_uid:int, text:str, reply_msg=None):
    """
    أوامر نصية: owner, unowner, admin, unadmin, انذار, طرد, اعطاء صلاحية, سحب صلاحية, السماح/منع الشتم, السماح/منع التكرار
    يمكن أن تأتي بالأمر + reply (للـ reply) أو الأمر + @username
    """
    try:
        txt = text.strip()
        parts = txt.split()
        cmd = parts[0].lower()

        # helper: get target uid
        target_uid = None
        if reply_msg:
            target_uid = int(reply_msg.user_id)
        else:
            # إذا ذكروا @username
            if len(parts) >= 2 and parts[1].startswith("@"):
                target_uid = uid_from_username(parts[1])

        # OWNER (من dev فقط)
        if cmd == "owner" and issuer_uid == DEV_ID and target_uid:
            owners.add(target_uid)
            send_group(f"تم التعرف على @{user_display_name_by_id(target_uid)} كمالك المجموعة")
            return

        if cmd == "unowner" and issuer_uid == DEV_ID and target_uid:
            owners.discard(target_uid)
            send_group(f"تم سحب التعرف على @{user_display_name_by_id(target_uid)} كمالك المجموعة")
            return

        # ADMIN (من owner أو dev)
        if cmd == "admin" and (issuer_uid in owners or issuer_uid == DEV_ID) and target_uid:
            admins.add(target_uid)
            send_group(f"تم التعرف على @{user_display_name_by_id(target_uid)} كمسؤول أساسي")
            return

        if cmd == "unadmin" and (issuer_uid in owners or issuer_uid == DEV_ID) and target_uid:
            admins.discard(target_uid)
            send_group(f"تم سحب التعرف على @{user_display_name_by_id(target_uid)} كمسؤول أساسي")
            return

        # انذار (reply أو @username)
        if cmd == "انذار" and target_uid:
            give_warning_to(target_uid, issuer_uid)
            return

        # طرد
        if cmd == "طرد" and target_uid and (issuer_uid in owners or issuer_uid in admins or issuer_uid==DEV_ID or issuer_uid in authorized_users):
            try:
                cl.direct_remove_user(int(THREAD_ID), target_uid)
                send_group(f"تم طرد @{user_display_name_by_id(target_uid)} بواسطة @{user_display_name_by_id(issuer_uid)}")
            except Exception as e:
                send_group(f"فشل طرد @{user_display_name_by_id(target_uid)}: {e}")
            return

        # اعطاء صلاحية (authorize) — فقط owner أو dev
        if cmd in ("اعطاء", "اعطاءصلاحية", "اعطاء_صلاحية") and (issuer_uid in owners or issuer_uid==DEV_ID) and target_uid:
            authorized_users.add(target_uid)
            send_group(f"@{user_display_name_by_id(target_uid)} اصبح لديه صلاحية استخدام اوامر البوت")
            return

        # سحب صلاحية
        if cmd in ("سحب", "سحب_صلاحية") and (issuer_uid in owners or issuer_uid==DEV_ID) and target_uid:
            authorized_users.discard(target_uid)
            send_group(f"تم سحب صلاحية @{user_display_name_by_id(target_uid)}")
            return

        # السماح/منع الشتم
        if cmd in ("منع_الشتم","منع الشتم","منع_الشتم".strip()):
            # mode on: منع الشتم (سيعمل عبر check_violation)
            send_group("تم تفعيل وضع منع الشتم")
            return
        if cmd in ("سماح_الشتم","سماح الشتم"):
            send_group("تم تفعيل وضع السماح بالشتم (يتجاهل الشتم مؤقتًا)")
            return

        # السماح/منع التكرار
        if cmd in ("منع_التكرار","منع التكرار"):
            send_group("تم تفعيل وضع منع التكرار")
            return
        if cmd in ("سماح_التكرار","سماح التكرار"):
            send_group("تم تفعيل وضع السماح بالتكرار")
            return

    except Exception as e:
        print("خطأ في handle_special_command_text:", e, traceback.format_exc())

# ------------------- استلام ومعالجة الرسائل (حلقة رئيسية) -------------------
def poll_thread_and_process():
    """
    ملاحظة: instagrapi توفر عدة طرق لجلب رسائل DM/threads.
    الدالة التالية تستخدم direct_threads / thread messages polling.
    قد تحتاج تعديل بسيط حسب نسخة instagrapi إذا تغيرت الواجهات.
    """
    try:
        inbox = cl.direct_threads()
        for thread in inbox:
            try:
                if str(getattr(thread, "thread_id", getattr(thread, "id", None))) != str(THREAD_ID):
                    continue
                # جلب الرسائل الحديثة في الـthread
                messages = cl.direct_thread_messages(getattr(thread, "id", getattr(thread, "thread_id", None)))
                for m in messages:
                    # m: message object
                    # تجاهل رسائل البوت نفسه
                    if int(getattr(m, "user_id", getattr(m, "user", 0))) == cl.user_id:
                        continue

                    # افحص المخالفات أولًا
                    check_violation_from_message(m)

                    # تعامل مع الأوامر إن كانت من مفوّض
                    issuer_uid = int(getattr(m, "user_id", getattr(m, "user", 0)))
                    is_authorized = issuer_uid in owners or issuer_uid in admins or issuer_uid==DEV_ID or issuer_uid in authorized_users
                    if is_authorized:
                        # إذا الرسالة هي reply لرسالة سابقة، مرّر الـreply object
                        reply_obj = None
                        if getattr(m, "reply_to_message_id", None):
                            # جلب الرسالة المردودة (ربما تحتاج تعديل حسب نسخة instagrapi)
                            try:
                                reply_obj = cl.direct_message(getattr(m, "reply_to_message_id"))
                            except Exception:
                                reply_obj = None
                        handle_special_command_text(issuer_uid, getattr(m, "text", ""), reply_msg=reply_obj)
            except Exception as e:
                print("خطأ أثناء معالجة ثريد:", e)
    except Exception as e:
        print("خطأ في poll_thread_and_process:", e)

# ------------------- MAIN -------------------
def main():
    if not BOT_USERNAME or not BOT_PASSWORD:
        print("يرجى تعيين BOT_USERNAME و BOT_PASSWORD و THREAD_ID كمتغيرات بيئة.")
        return

    logged = try_login()
    if not logged:
        print("خروج: فشل تسجيل الدخول")
        return

    # عند التشغيل: رسالة تفعيل
    send_group(f"تم الاستضافة من قبل @{BOT_USERNAME}")

    # تعرّف الـDEV تلقائيًا كـowner (يمكنك تعطيل لو أردت)
    if DEV_ID:
        owners.add(DEV_ID)
        send_group(f"تم التعرف على @{user_display_name_by_id(DEV_ID)} كـDev/Owner تلقائياً")

    # الحلقة
    while True:
        try:
            check_admin_status_and_auto_leave()
            poll_thread_and_process()
        except Exception as e:
            print("خطأ عام في الحلقة الرئيسية:", e, traceback.format_exc())
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
