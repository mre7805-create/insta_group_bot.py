# main.py
"""
Instagram UserBot – ملف التشغيل الرئيسي
يشغّل البوت + يربط كل الموديولات + يبدأ مراقبة الرسائل
"""

import time
from modules.listener import check_inbox
from modules.ig_api import IG
from modules.utils import log

def main():
    log("🚀 تشغيل بوت إنستقرام...")

    # تسجيل الدخول + تحميل الجلسة
    IG.login()

    while True:
        try:
            # فحص كل الرسائل والأنشطة
            check_inbox()

        except Exception as e:
            log(f"⚠️ خطأ في الحلقة الرئيسية: {e}")

        time.sleep(2)  # لا نستهلك الجهاز

if __name__ == "__main__":
    main()