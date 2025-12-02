# modules/ig_api.py
import json
import uuid
import time
import hashlib
import random
import os
import requests
from requests.exceptions import RequestException
from modules.utils import log

SESSION_FILE = "session_cookies.json"

class InstagramAPI:
    def __init__(self, cfg_path="config.json"):
        # تحميل إعدادات بسيطة (username/password)
        if not os.path.exists(cfg_path):
            raise FileNotFoundError(f"config file not found: {cfg_path}")
        with open(cfg_path, "r", encoding="utf8") as f:
            cfg = json.load(f)

        self.username = cfg.get("username")
        self.password = cfg.get("password")
        self.session_file = cfg.get("session_file", SESSION_FILE)

        self.device_id = self.generate_device_id()
        self.uuid = str(uuid.uuid4())

        self.session = requests.Session()
        self.base = "https://i.instagram.com/api/v1"

        # رؤوس افتراضية قابلة للتحديث لاحقاً
        self.headers = {
            "User-Agent": "Instagram 219.0.0.12.117 Android",
            "X-IG-App-ID": "567067343352427",
            "Connection": "keep-alive",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # سيتحدّث بعد تسجيل الدخول
        self.sessionid = None
        self.csrf = None

        # حاول تحميل الجلسة إن وجدت
        try:
            self.load_session()
        except Exception:
            pass

    def generate_device_id(self):
        return "android-" + hashlib.md5(str(time.time()).encode()).hexdigest()[0:16]

    # ---------------- helpers ----------------
    def _save_cookies(self):
        try:
            data = requests.utils.dict_from_cookiejar(self.session.cookies)
            payload = {
                "cookies": data,
                "device_id": self.device_id,
                "uuid": self.uuid,
                "saved_at": int(time.time())
            }
            with open(self.session_file, "w", encoding="utf8") as f:
                json.dump(payload, f)
            log(f"💾 session saved -> {self.session_file}")
        except Exception as e:
            log(f"⚠️ failed to save session: {e}")

    def load_session(self):
        if not os.path.exists(self.session_file):
            raise FileNotFoundError("session file not found")
        with open(self.session_file, "r", encoding="utf8") as f:
            payload = json.load(f)
        cookies = payload.get("cookies", {})
        jar = requests.utils.cookiejar_from_dict(cookies)
        self.session.cookies = jar
        # تحديث القيم الأساسية إن وجدت
        self.sessionid = cookies.get("sessionid") or self.session.cookies.get("sessionid")
        self.csrf = cookies.get("csrftoken") or self.session.cookies.get("csrftoken")
        if self.csrf:
            self.headers["X-CSRFToken"] = self.csrf
        log("♻️ session loaded from file")
        return True

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base}/{endpoint.lstrip('/')}"
        max_retries = kwargs.pop("retries", 3)
        backoff = 1.0
        for attempt in range(max_retries):
            try:
                if method.lower() == "get":
                    res = self.session.get(url, headers=self.headers, timeout=15, **kwargs)
                else:
                    res = self.session.post(url, headers=self.headers, timeout=15, **kwargs)

                # تعامُل أساسي مع الأكواد غير 200
                if res.status_code in (200, 201):
                    try:
                        return res.json()
                    except ValueError:
                        # ليس JSON، أرجع النص الخام
                        return {"raw_text": res.text}
                elif res.status_code == 429:
                    # rate limited: ننتظر أكثر
                    log("🛑 rate limited (429). waiting...")
                    time.sleep(5 * (attempt + 1))
                else:
                    log(f"⚠️ unexpected status {res.status_code} for {url} -> {res.text[:200]}")
                    # محاولة إعادة المحاولة مع زيادة الانتظار
                    time.sleep(backoff)
                    backoff *= 2
            except RequestException as e:
                log(f"⚠️ request exception: {e} (attempt {attempt+1}/{max_retries})")
                time.sleep(backoff)
                backoff *= 2
        # إذا انتهت المحاولات
        raise ConnectionError(f"Failed to request {url} after {max_retries} attempts")

    # -------- LOGIN --------
    def login(self, force=False):
        """
        تسجيل الدخول: يحاول أولاً استخدام الجلسة المُخزنة ما لم يُطلب force=True
        بعد نجاح الدخول يتم حفظ الجلسة (cookies)
        """
        if not force:
            # حاول استخدام الجلسة المحفوظة
            try:
                if self.load_session():
                    log("▶️ Using existing session (no login).")
                    return True
            except Exception:
                pass

        log("🔐 تسجيل الدخول (new)...")
        # ملاحظة: بعض الحقول هنا قد تُغيّر مع تحديث الإنستقرام، لكن هذا قالب عملي
        ts = int(time.time())
        enc_password = f"#PWD_INSTAGRAM_BROWSER:0:{ts}:{self.password}"
        data = {
            "jazoest": "22499",
            "country_codes": '[{"country_code":"1","source":["default"]}]',
            "phone_id": self.uuid,
            "_uuid": self.uuid,
            "username": self.username,
            "adid": self.uuid,
            "device_id": self.device_id,
            "enc_password": enc_password,
            "login_attempt_count": "0"
        }

        # يمكن استخدام signed body هنا لو رغبت (تحسين لاحق)
        try:
            res = self.session.post(f"{self.base}/accounts/login/", data=data, headers=self.headers, timeout=20)
        except RequestException as e:
            log(f"❌ login request failed: {e}")
            return False

        text = res.text or ""
        if "logged_in_user" in text or res.status_code in (200,201):
            log("✅ تم تسجيل الدخول بنجاح!")
            # تحديث القيم من الكوكيز
            self.sessionid = self.session.cookies.get("sessionid")
            self.csrf = self.session.cookies.get("csrftoken")
            if self.csrf:
                self.headers["X-CSRFToken"] = self.csrf
            self._save_cookies()
            return True
        else:
            log("❌ فشل تسجيل الدخول")
            # طباعة جزء من الاستجابة للمساعدة في التشخيص (غير كامل لتجنب تسريب)
            log(text[:800])
            return False

    # ---------- GET INBOX ----------
    def get_inbox(self):
        try:
            res = self._request("get", "direct_v2/inbox/")
            # بنرجع قائمة threads كما في ملفك الأصلي
            return res.get("inbox", {}).get("threads", []) if isinstance(res, dict) else []
        except Exception as e:
            log(f"⚠️ get_inbox failed: {e}")
            return []

    # ---------- SEND TEXT (broadcast to thread ids) ----------
    def send_text(self, thread_id, text):
        data = {
            "action": "send_item",
            "thread_ids": f'["{thread_id}"]',
            "text": text
        }
        try:
            return self._request("post", "direct_v2/threads/broadcast/text/", data=data)
        except Exception as e:
            log(f"⚠️ send_text failed: {e}")
            return None

    # --------- SEND TO USER (new chat) ---------
    def send_text_user(self, user_id, text):
        data = {
            "recipient_users": f'[[\"{user_id}\"]]',
            "action": "send_item",
            "text": text
        }
        try:
            return self._request("post", "direct_v2/threads/broadcast/text/", data=data)
        except Exception as e:
            log(f"⚠️ send_text_user failed: {e}")
            return None

    # ---------- FETCH THREAD MESSAGES ----------
    def get_thread_messages(self, thread_id):
        try:
            res = self._request("get", f"direct_v2/threads/{thread_id}/")
            return res.get("thread", {}).get("items", []) if isinstance(res, dict) else []
        except Exception as e:
            log(f"⚠️ get_thread_messages failed: {e}")
            return []

IG = InstagramAPI()