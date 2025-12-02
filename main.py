# main.py
"""
Instagram UserBot – ملف التشغيل الرئيسي
يشغّل البوت + يربط كل الموديولات + يبدأ مراقبة الرسائل
"""

import time
from modules.ig_client import ig
from modules.handlers import handle_message
from modules.utils import log

def main():
    log("🚀 تشغيل بوت إنستقرام...")

    # تسجيل الدخول + تحميل الجلسة
    ig.login()

    last_checked = time.time()

    while True:
        try:
            # جلب الرسائل الجديدة
            inbox = ig.client.direct_threads()

            for thread in inbox:
                messages = thread.messages

                for msg in messages:
                    if msg.timestamp > last_checked:
                        handle_message(thread, msg)

            last_checked = time.time()

        except Exception as e:
            log(f"⚠️ خطأ في الحلقة الرئيسية: {e}")

        time.sleep(2)  # لا نستهلك السيرفر

if __name__ == "__main__":
    main()