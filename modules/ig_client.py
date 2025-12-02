# modules/ig_client.py

import json
from instagrapi import Client
from modules.utils import log

class IGClient:
    def __init__(self):
        self.client = Client()

    def login(self):
        log("🔐 تسجيل الدخول إلى إنستقرام...")
        with open("config.json", "r") as f:
            cfg = json.load(f)

        username = cfg["username"]
        password = cfg["password"]

        try:
            self.client.load_settings("session.json")
            self.client.login(username, password)
            log("✅ تسجيل الدخول باستخدام الجلسة")
        except:
            log("⚠️ الجلسة غير صالحة – تسجيل دخول يدوي...")
            self.client.login(username, password)
            self.client.dump_settings("session.json")
            log("✅ تم إنشاء session.json جديدة")

ig = IGClient()