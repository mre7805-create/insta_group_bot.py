# modules/ig_api.py
import json, uuid, time, hashlib, random
import requests
from modules.utils import log

class InstagramAPI:
    def __init__(self):
        with open("config.json", "r") as f:
            cfg = json.load(f)

        self.username = cfg["username"]
        self.password = cfg["password"]

        self.device_id = self.generate_device_id()
        self.uuid = str(uuid.uuid4())

        self.session = requests.Session()
        self.base = "https://i.instagram.com/api/v1"

        self.headers = {
            "User-Agent": "Instagram 219.0.0.12.117 Android",
            "X-IG-App-ID": "567067343352427",
            "Connection": "Keep-Alive"
        }

    def generate_device_id(self):
        return "android-" + hashlib.md5(str(time.time()).encode()).hexdigest()[0:16]

    # -------- LOGIN --------
    def login(self):
        log("🔐 تسجيل الدخول...")

        data = {
            "jazoest": "22499",
            "country_codes": "[{\"country_code\":\"1\",\"source\":[\"default\"]}]",
            "phone_id": self.uuid,
            "_uuid": self.uuid,
            "username": self.username,
            "adid": self.uuid,
            "device_id": self.device_id,
            "password": self.password,
            "login_attempt_count": "0"
        }

        response = self.session.post(
            f"{self.base}/accounts/login/",
            data=data,
            headers=self.headers
        )

        if "logged_in_user" in response.text:
            log("✅ تم تسجيل الدخول بنجاح!")
            self.sessionid = response.cookies.get("sessionid")
            self.csrf = response.cookies.get("csrftoken")
            return True

        log("❌ فشل تسجيل الدخول")
        log(response.text)
        return False

    # ---------- GET INBOX ----------
    def get_inbox(self):
        res = self.session.get(
            f"{self.base}/direct_v2/inbox/",
            headers=self.headers
        ).json()
        return res.get("inbox", {}).get("threads", [])

    # ---------- SEND TEXT ----------
    def send_text(self, thread_id, text):
        data = {
            "action": "send_item",
            "thread_ids": f"[\"{thread_id}\"]",
            "text": text
        }

        self.session.post(
            f"{self.base}/direct_v2/threads/broadcast/text/",
            data=data,
            headers=self.headers
        )

    # --------- SEND TO USER (new chat) ---------
    def send_text_user(self, user_id, text):
        data = {
            "recipient_users": f"[[\"{user_id}\"]]",
            "action": "send_item",
            "text": text
        }

        self.session.post(
            f"{self.base}/direct_v2/threads/broadcast/text/",
            data=data,
            headers=self.headers
        )

    # ---------- FETCH THREAD MESSAGES ----------
    def get_thread_messages(self, thread_id):
        res = self.session.get(
            f"{self.base}/direct_v2/threads/{thread_id}/",
            headers=self.headers
        ).json()
        return res.get("thread", {}).get("items", [])

IG = InstagramAPI()