# modules/admin.py
import json
import os
import time
from typing import Optional

from modules.ig_api import IG     # يفترض أن IG هو مثيل InstagramAPI في ig_api.py
from modules.utils import log

STATE_FILE = "admin_state.json"

# --- تنسيق حالة التخزين ---
# {
#   "<thread_id>": {
#       "activated": true/false,
#       "owner": {"user_id": "123", "username": "name"},
#       "bot_admins": ["111","222"],
#       "dev_activated_by": "dev_user_id"
#   },
#   ...
# }
# config.json يجب أن يحتوي على مفتاح "dev_ids": [12345, ...]
# (برمجياً نقرأه داخل init)

class AdminSystem:
    def __init__(self, config_path="config.json"):
        self.state = {}
        self.config_path = config_path
        self.dev_ids = []
        self._load_config()
        self._load_state()

    def _load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf8") as f:
                cfg = json.load(f)
            self.dev_ids = [str(x) for x in cfg.get("dev_ids", [])]
        except Exception:
            self.dev_ids = []
        log(f"admin: dev_ids = {self.dev_ids}")

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf8") as f:
                    self.state = json.load(f)
            except Exception:
                self.state = {}
        else:
            self.state = {}

    def _save_state(self):
        with open(STATE_FILE, "w", encoding="utf8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    # ---------- helpers ----------
    def _ensure_thread(self, thread_id):
        if thread_id not in self.state:
            self.state[thread_id] = {
                "activated": False,
                "owner": None,
                "bot_admins": [],
                "dev_activated_by": None
            }

    def is_dev(self, user_id: str) -> bool:
        return str(user_id) in self.dev_ids

    def is_activated(self, thread_id: str) -> bool:
        self._ensure_thread(thread_id)
        return self.state[thread_id]["activated"]

    def get_owner(self, thread_id: str) -> Optional[dict]:
        self._ensure_thread(thread_id)
        return self.state[thread_id]["owner"]

    def is_bot_admin(self, thread_id: str, user_id: str) -> bool:
        self._ensure_thread(thread_id)
        return str(user_id) in [str(x) for x in self.state[thread_id]["bot_admins"]]

    def add_bot_admin(self, thread_id: str, user_id: str):
        self._ensure_thread(thread_id)
        uid = str(user_id)
        if uid not in self.state[thread_id]["bot_admins"]:
            self.state[thread_id]["bot_admins"].append(uid)
            self._save_state()

    def remove_bot_admin(self, thread_id: str, user_id: str):
        self._ensure_thread(thread_id)
        uid = str(user_id)
        if uid in self.state[thread_id]["bot_admins"]:
            self.state[thread_id]["bot_admins"].remove(uid)
            self._save_state()

    # ---------- low-level IG helpers ----------
    def _thread_info(self, thread_id: str) -> dict:
        """إحضار معلومات الثريد (المستخدمين والصلاحيات) - ترجع dict أو {}"""
        try:
            r = IG.session.get(f"{IG.base}/direct_v2/threads/{thread_id}/", headers=IG.headers, timeout=15)
            return r.json().get("thread", {}) if r.status_code in (200,201) else {}
        except Exception as e:
            log(f"admin._thread_info error: {e}")
            return {}

    def _user_is_real_admin(self, thread_id: str, user_id: str) -> bool:
        """
        يفحص قائمة المستخدمين في الثريد إن كان لديهم علامة أدمين حقيقية
        (يعتمد على وجود حقل في رد الإنستا 'is_admin' أو 'is_moderator' أو status)
        """
        info = self._thread_info(thread_id)
        users = info.get("users") or info.get("items") or []
        for u in users:
            # بنحاول استخراج id و flags بعدة مفاتيح محتملة
            uid = str(u.get("pk") or u.get("id") or u.get("user_id") or u.get("user", {}).get("pk"))
            if uid == str(user_id):
                # تحقق من مفاتيح مختلفة بحسب رد الإنستا
                if u.get("is_admin") or u.get("is_moderator") or u.get("is_team_admin"):
                    return True
                # بعض الردود تضع role أو permissions
                role = u.get("role") or u.get("status")
                if isinstance(role, str) and role.lower() in ("admin", "creator", "administrator"):
                    return True
        return False

    def _resolve_target_from_reply_or_username(self, thread_id: str, msg: dict) -> Optional[dict]:
        """
        msg expects:
          - 'reply_to_user_id' (optional)
          - 'reply_to_username' (optional)
          - 'text' (the command text, may contain @username)
        Returns: {'user_id':..., 'username':...} or None
        """
        # 1) reply-based
        rid = msg.get("reply_to_user_id")
        rusername = msg.get("reply_to_username")
        if rid:
            return {"user_id": str(rid), "username": rusername or ""}

        # 2) @username in text
        text = msg.get("text","").strip()
        parts = text.split()
        for p in parts:
            if p.startswith("@") and len(p) > 1:
                uname = p[1:]
                # try find username in thread participants
                info = self._thread_info(thread_id)
                for u in info.get("users", []) + info.get("items", []):
                    uname_field = u.get("username") or u.get("user", {}).get("username")
                    if uname_field and uname_field.lower() == uname.lower():
                        uid = str(u.get("pk") or u.get("id") or u.get("user", {}).get("pk"))
                        return {"user_id": uid, "username": uname_field}
                # if not found in thread, still return username (best effort)
                return {"user_id": None, "username": uname}
        return None

    def _send_reply(self, thread_id: str, reply_to_message_id: Optional[str], text: str):
        """
        يرسل رد في الثريد كـ reply إن أمكن
        يستخدم endpoint البسيط broadcast/text مع حقل reply_to_message_id إن وُجد
        """
        data = {
            "action": "send_item",
            "thread_ids": f'["{thread_id}"]',
            "text": text
        }
        if reply_to_message_id:
            data["reply_to_message_id"] = str(reply_to_message_id)
        try:
            IG.session.post(f"{IG.base}/direct_v2/threads/broadcast/text/", data=data, headers=IG.headers, timeout=15)
        except Exception as e:
            log(f"admin._send_reply error: {e}")

    # ---------- commands ----------
    def cmd_activate(self, thread_id: str, msg: dict):
        """/تفعيل — only Devs"""
        user = str(msg.get("user_id"))
        if not self.is_dev(user):
            return  # تجاهل بصمت

        self._ensure_thread(thread_id)
        self.state[thread_id]["activated"] = True
        self.state[thread_id]["dev_activated_by"] = user
        self._save_state()

        # رد ريبلاي على طلب التفعيل
        self._send_reply(thread_id, msg.get("message_id"), "تم التفعيل")

    def cmd_leave(self, thread_id: str, msg: dict):
        """/غادر — only Devs -> البوت يغادر الثريد"""
        user = str(msg.get("user_id"))
        if not self.is_dev(user):
            return

        # محاولة مغادرة الثريد
        try:
            IG.session.post(f"{IG.base}/direct_v2/threads/{thread_id}/leave/", headers=IG.headers, timeout=15)
        except Exception as e:
            log(f"admin.leave error: {e}")
        # لا نرد بعد المغادرة (قد لا نستطيع)، لكن نرد قبل المغادرة اذا أردت.
        # هنا نرسل رد قبل المغادرة:
        self._send_reply(thread_id, msg.get("message_id"), "تم المغادرة")
        # ثم نقوم بالفعل بالمغادرة اثناء تنفيذ الطلب - بعض الأحيان البوت لن يستطيع الرد بعد leave

    def cmd_recognize_owner(self, thread_id: str, msg: dict):
        """/تعرف — فقط Dev يعرّف مؤسس المجموعة عبر الريبلاي على رسالة المؤسس"""
        caller = str(msg.get("user_id"))
        if not self.is_dev(caller):
            return

        target = self._resolve_target_from_reply_or_username(thread_id, msg)
        if not target or not target.get("user_id"):
            # إن لم نتمكن من العثور على user_id نرد فشل صغير
            # لكن الطلب قال تجاهل الحالات غير المخولة بصمت؛ هنا dev طلب صراحة، نرد إن لم نجده
            self._send_reply(thread_id, msg.get("message_id"), "لم أجد المستخدم لتعيينه مؤسساً")
            return

        self._ensure_thread(thread_id)
        self.state[thread_id]["owner"] = {"user_id": str(target["user_id"]), "username": target.get("username") or ""}
        self._save_state()

        username_to_show = target.get("username") or ("@" + str(target["user_id"]))
        # الرد المطلوب نصاً
        self._send_reply(thread_id, msg.get("message_id"),
                         f"تم التعرف على @{username_to_show} كمؤسس للمجموعة له كامل الصلاحيات وحماية من السرقة")

    def cmd_give_admin(self, thread_id: str, msg: dict):
        """/ادمن — فقط owner المعرف يمكنه منح صلاحية بوت-أدمن"""
        caller = str(msg.get("user_id"))
        owner = self.get_owner(thread_id)
        if not owner or str(owner.get("user_id")) != caller:
            return  # تجاهل بصمت

        target = self._resolve_target_from_reply_or_username(thread_id, msg)
        if not target or not target.get("user_id"):
            self._send_reply(thread_id, msg.get("message_id"), "المستخدم المراد رفعه ما حصلته")
            return

        targ_id = str(target["user_id"])
        targ_username = target.get("username") or targ_id

        # لا نسمح لمنح صلاحية لأحد إذا كان فعلاً أدمن حقيقي لا يحتاج
        if self._user_is_real_admin(thread_id, targ_id):
            # لا نغير حالة الأدمن الحقيقي
            self._send_reply(thread_id, msg.get("message_id"), "المستخدم هدفه أدمن حقيقي ولا يمكن منحه صلاحية البوت")
            return

        self.add_bot_admin(thread_id, targ_id)
        # رد بالصيغة المحددة
        self._send_reply(thread_id, msg.get("message_id"),
                         f"({('@' + targ_username) if targ_username else targ_id}) صار له صلاحيات ادمن في القروب")

    def cmd_remove_admin(self, thread_id: str, msg: dict):
        """/سحب — فقط owner يمكنه سحب صلاحية بوت-ادمن"""
        caller = str(msg.get("user_id"))
        owner = self.get_owner(thread_id)
        if not owner or str(owner.get("user_id")) != caller:
            return

        target = self._resolve_target_from_reply_or_username(thread_id, msg)
        if not target or not target.get("user_id"):
            self._send_reply(thread_id, msg.get("message_id"), "المستخدم المراد سحبه ما حصلته")
            return

        targ_id = str(target["user_id"])
        targ_username = target.get("username") or targ_id

        # لا نسمح بسحب ادمن حقيقي
        if self._user_is_real_admin(thread_id, targ_id):
            self._send_reply(thread_id, msg.get("message_id"), "ما عندك صلاحية سحب ادمن\nفقط ل (Dev - Owner)")
            return

        self.remove_bot_admin(thread_id, targ_id)
        self._send_reply(thread_id, msg.get("message_id"),
                         f"({('@' + targ_username) if targ_username else targ_id}) سحبت منه صلاحيات الادمن")

    def _can_execute_admin_action(self, thread_id: str, caller_id: str) -> bool:
        """الادمن الحقيقي أو ادمن مرفوع داخل البوت"""
        # مؤسس المجموعة (owner) لا يعتبر ضمن "ادمن حقيقي" هنا لكنه يملك صلاحيات كاملة بالفعل
        if self.get_owner(thread_id) and str(self.get_owner(thread_id).get("user_id")) == str(caller_id):
            return True
        if self.is_bot_admin(thread_id, caller_id):
            return True
        # تحقق من القائمين كـ admins حقيقيين في الثريد
        if self._user_is_real_admin(thread_id, caller_id):
            return True
        return False

    def cmd_kick(self, thread_id: str, msg: dict):
        """/طرد or /kik — يمكن تنفيذه من قبل الادمن الحقيقي أو الادمن المرفوع داخل البوت"""
        caller = str(msg.get("user_id"))
        if not self._can_execute_admin_action(thread_id, caller):
            return  # تجاهل بصمت

        target = self._resolve_target_from_reply_or_username(thread_id, msg)
        if not target or not target.get("user_id"):
            self._send_reply(thread_id, msg.get("message_id"), "المستخدم المراد طرده ما حصلته")
            return

        targ_id = str(target["user_id"])
        targ_username = target.get("username") or targ_id

        # لا يمكن طرد أدمن حقيقي
        if self._user_is_real_admin(thread_id, targ_id):
            self._send_reply(thread_id, msg.get("message_id"), "ما تقدر تطرد ادمن")
            return

        # نفّذ الطرد عبر endpoint مناسب
        try:
            resp = IG.session.post(f"{IG.base}/direct_v2/threads/{thread_id}/remove_user/",
                                   data={"user_id": targ_id}, headers=IG.headers, timeout=15)
        except Exception as e:
            log(f"admin.kick error: {e}")
            resp = None

        # تحقق فعلي إن المستخدم غادر الثريد
        info = self._thread_info(thread_id)
        present = False
        for u in info.get("users", []):
            uid = str(u.get("pk") or u.get("id") or u.get("user", {}).get("pk"))
            if uid == targ_id:
                present = True
                break

        if not present:
            # نجاح الطرد
            self._send_reply(thread_id, msg.get("message_id"), f"({('@' + targ_username) if targ_username else targ_id}) Kik")
            # اذا كان هذا المستخدم مرفوع كـ bot-admin نزيله من قائمتنا
            self.remove_bot_admin(thread_id, targ_id)
        else:
            self._send_reply(thread_id, msg.get("message_id"), f"{('@' + targ_username) if targ_username else targ_id} ما حصلته")

    def cmd_accept(self, thread_id: str, msg: dict):
        """/قبول @usr — قبول طلب الانضمام (اضافة المستخدم الى القروب)"""
        caller = str(msg.get("user_id"))
        if not self._can_execute_admin_action(thread_id, caller):
            return  # تجاهل بصمت

        target = self._resolve_target_from_reply_or_username(thread_id, msg)
        if not target or not target.get("user_id"):
            self._send_reply(thread_id, msg.get("message_id"), "المستخدم المراد قبوله ما حصلته")
            return

        targ_id = str(target["user_id"])
        targ_username = target.get("username") or targ_id

        # محاولة الاضافة عبر endpoint مناسب
        try:
            resp = IG.session.post(f"{IG.base}/direct_v2/threads/{thread_id}/add_user/",
                                   data={"user_ids": f'["{targ_id}"]'}, headers=IG.headers, timeout=15)
        except Exception as e:
            log(f"admin.accept error: {e}")
            resp = None

        # تحقق إن المستخدم أصبح موجوداً
        info = self._thread_info(thread_id)
        present = False
        for u in info.get("users", []):
            uid = str(u.get("pk") or u.get("id") or u.get("user", {}).get("pk"))
            if uid == targ_id:
                present = True
                break

        if present:
            self._send_reply(thread_id, msg.get("message_id"), f"({('@' + targ_username) if targ_username else targ_id}) قبلته")
        else:
            self._send_reply(thread_id, msg.get("message_id"), f"{('@' + targ_username) if targ_username else targ_id} ما حصلته")

    def cmd_ticket(self, thread_id: str, msg: dict):
        """
        /تكت + الشكوى
        يرسل للادمنز في الخاص (البوت-ادمنز + الأدمن الحقيقي)
        """
        caller_id = str(msg.get("user_id"))
        caller_username = msg.get("username") or str(caller_id)
        text = msg.get("text", "").strip()
        # استخراج نص التكت بعد الأمر
        parts = text.split(maxsplit=1)
        ticket_text = parts[1].strip() if len(parts) > 1 else ""

        # بناء رسالة التكت المطلوبة
        ticket_msg = f"({('@' + caller_username) if caller_username else caller_id}) رفع تكت\n#التكت\n{ticket_text}"

        # جمع قائمة مستلمي التكت:
        recipients = set()

        # 1) bot-admins المرفوعين في الثريد
        self._ensure_thread(thread_id)
        for aid in self.state[thread_id]["bot_admins"]:
            recipients.add(str(aid))

        # 2) الأدمن الحقيقيون من thread info
        info = self._thread_info(thread_id)
        for u in info.get("users", []):
            uid = str(u.get("pk") or u.get("id") or u.get("user", {}).get("pk"))
            if u.get("is_admin") or u.get("is_moderator") or (str(uid) == str(self.state[thread_id].get("owner", {}).get("user_id"))):
                recipients.add(uid)

        # إرسال الرسالة لكل واحد يحاول و يتجاهل الفاشلين بصمت
        for rid in recipients:
            try:
                # محاولة إرسال رسالة خاصة للمستخدم (new thread)
                IG.session.post(f"{IG.base}/direct_v2/threads/broadcast/text/",
                                data={"recipient_users": f'[[\"{rid}\"]]', "action": "send_item", "text": ticket_msg},
                                headers=IG.headers, timeout=10)
            except Exception:
                # تجاهل الفشل بدون رد
                continue

        # رد المؤكد للطالب (ريبلاي)
        self._send_reply(thread_id, msg.get("message_id"), "رفعت التكت للادمنز")

    # ---------- entry point ----------
    def process_command(self, thread_id: str, msg: dict):
        """
        msg should include:
          - text
          - user_id
          - username (optional)
          - reply_to_user_id (optional)
          - reply_to_username (optional)
          - message_id (the message item id) - used for reply
        """
        text = (msg.get("text") or "").strip()
        if not text:
            return

        # الأوامر المدعومة:
        # /تفعيل  /غادر  /تعرف  /ادمن  /سحب  /طرد  /kik  /قبول  /تكت
        cmd = text.split()[0]

        if cmd == "/تفعيل":
            self.cmd_activate(thread_id, msg)
            return
        if cmd == "/غادر":
            self.cmd_leave(thread_id, msg)
            return
        if cmd == "/تعرف":
            self.cmd_recognize_owner(thread_id, msg)
            return
        if cmd == "/ادمن":
            self.cmd_give_admin(thread_id, msg)
            return
        if cmd == "/سحب":
            self.cmd_remove_admin(thread_id, msg)
            return
        if cmd in ("/طرد", "/kik"):
            self.cmd_kick(thread_id, msg)
            return
        if cmd == "/قبول":
            self.cmd_accept(thread_id, msg)
            return
        if cmd.startswith("/تكت"):
            self.cmd_ticket(thread_id, msg)
            return

# إنشاء وحدة admin واحدة تستخدم في باقي الموديولات
ADMIN = AdminSystem()