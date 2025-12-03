# modules/ig_api.py
"""
IG API Wrapper
نظام بسيط وموحد للتعامل مع إنستقرام:
- تسجيل الدخول بالجلسة
- جلب الإنبوكس
- جلب رسائل الثريد
- إرسال رسائل
- إرسال صور
- قراءة كل الأحداث كما يراها المستخدم العادي
"""

import requests
import json
import time


class IG:
    sessionid = None
    headers = {}
    client = None

    API_URL = "https://i.instagram.com/api/v1"

    @staticmethod
    def login():
        """
        تحميل الجلسة sessionid من session.txt
        """
        try:
            with open("session.txt", "r") as f:
                IG.sessionid = f.read().strip()
        except:
            raise Exception("❌ ملف session.txt غير موجود – ضع داخله sessionid فقط")

        IG.headers = {
            "User-Agent": "Instagram 290.0.0.0.123 Android",
            "Cookie": f"sessionid={IG.sessionid};"
        }

        print("✅ تسجيل الدخول عبر sessionid...")

    # ================================
    # جلب الإنبوكس كامل
    # ================================
    @staticmethod
    def get_inbox():
        url = f"{IG.API_URL}/direct_v2/inbox/?persistentBadging=true"
        r = requests.get(url, headers=IG.headers)
        if r.status_code != 200:
            print("⚠️ فشل في جلب الإنبوكس")
            return []

        data = r.json()
        return data.get("inbox", {}).get("threads", [])

    # ================================
    # جلب رسائل ثريد معين
    # ================================
    @staticmethod
    def get_thread_messages(thread_id):
        url = f"{IG.API_URL}/direct_v2/threads/{thread_id}/"
        r = requests.get(url, headers=IG.headers)
        if r.status_code != 200:
            print("⚠️ فشل في جلب رسائل الثريد")
            return []

        data = r.json()
        return data.get("thread", {}).get("items", [])

    # ================================
    # إرسال رسالة نصية
    # ================================
    @staticmethod
    def send_message(thread_id, text):
        url = f"{IG.API_URL}/direct_v2/threads/broadcast/text/"
        data = {
            "thread_ids": f"[\"{thread_id}\"]",
            "text": text
        }
        r = requests.post(url, headers=IG.headers, data=data)
        return r.status_code == 200

    # ================================
    # إرسال صورة
    # ================================
    @staticmethod
    def send_photo(thread_id, path):
        url = f"{IG.API_URL}/direct_v2/threads/broadcast/configure_photo/"
        files = {"photo": open(path, "rb")}
        data = {
            "thread_ids": f"[\"{thread_id}\"]"
        }
        r = requests.post(url, headers=IG.headers, files=files, data=data)
        return r.status_code == 200

    # ================================
    # إرسال منشن (@user)
    # ================================
    @staticmethod
    def mention(thread_id, username, text=""):
        new_text = f"@{username} {text}".strip()
        return IG.send_message(thread_id, new_text)

    # ================================
    # إرسال رد (reply)
    # ================================
    @staticmethod
    def reply(thread_id, item_id, text):
        """
        reply على رسالة، مثل المستخدم نفسه
        """
        url = f"{IG.API_URL}/direct_v2/threads/broadcast/text/"
        data = {
            "thread_ids": f"[\"{thread_id}\"]",
            "text": text,
            "reply_type": "reply",
            "replied_to_item_id": item_id
        }
        r = requests.post(url, headers=IG.headers, data=data)
        return r.status_code == 200