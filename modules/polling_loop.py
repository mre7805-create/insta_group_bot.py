# polling_loop.py

import time
from modules.listener import check_inbox
from modules.utils import log
from modules.ig_api import IG

def start_bot():
    log("بدء تشغيل بوت إنستقرام")

    # تسجيل الدخول أو تحميل الجلسة
    if not IG.login():
        log("فشل تسجيل الدخول. أعد المحاولة.")
        return

    log("الجلسة جاهزة. بدء الاستماع...")

    while True:
        try:
            check_inbox()
        except Exception as e:
            log(f"⚠ خطأ في listener: {e}")

        time.sleep(4)  # لا تزيد، لا تنقص

if __name__ == "__main__":
    start_bot()