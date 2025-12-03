# modules/protection.py
import time
from modules.admin_system import load_admins, save_admins
from modules.utils import log
from modules.ig_api import IG, IG_HELPER

# التخزين الأساسي
OWNERS_FILE = "owners.json"
KICK_LOG = {}

# ===============================================================
#              حماية من السرقة + حماية من الطرد الجماعي
# ===============================================================

def load_owners():
    import json, os
    if not os.path.exists(OWNERS_FILE):
        return {"primary": None, "secondary": []}
    return json.load(open(OWNERS_FILE, "r"))

def save_owners(data):
    import json
    json.dump(data, open(OWNERS_FILE, "w"), indent=2)

# ===============================================================
#                  تسجيل Owner (من ملف الأدمن)
# ===============================================================
def register_owner(user_id):
    data = load_owners()
    if data["primary"] is None:
        data["primary"] = user_id
    else:
        if user_id not in data["secondary"]:
            data["secondary"].append(user_id)
    save_owners(data)
    return True

# ===============================================================
#               check changes in admin list (سرقة)
# ===============================================================
def detect_admin_change(thread, msg, old_admins, new_admins):
    """
    old_admins → قبل الحدث
    new_admins → بعد الحدث
    """
    owners = load_owners()
    primary = owners["primary"]
    secondary = owners["secondary"]

    removed = [a for a in old_admins if a not in new_admins]

    if not removed:
        return

    for lost_admin in removed:
        # ----------------------------
        #      سحب ادمن الأونر الأساسي
        # ----------------------------
        if lost_admin == primary:
            actor = msg.user_id
            if actor == primary:
                continue

            # إذا البوت مرفوع وسحبه أحد
            if lost_admin == IG.username:
                # رجع ادمن البوت بواسطة المساعد
                IG_HELPER.set_admin(thread.thread_id, IG.username)
                IG_HELPER.remove_admin(thread.thread_id, actor)
                thread.send_message(f"(@{actor}) شال الادمن مني وسحبت ادمنه بواسطة المساعد ورجعت ادمني")
                continue

            # اللي حاول يسرق الأونر الأساسي
            # رده طبيعي
            IG_HELPER.remove_admin(thread.thread_id, actor)
            IG_HELPER.set_admin(thread.thread_id, primary)
            thread.send_message(f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر")
            continue

        # ----------------------------
        #      سحب ادمن المساعد
        # ----------------------------
        if lost_admin == IG_HELPER.username:
            actor = msg.user_id
            IG.remove_admin(thread.thread_id, actor)
            IG.set_admin(thread.thread_id, IG_HELPER.username)
            thread.send_message(f"(@{actor}) شال الادمن من المساعد وسحبت ادمنه ورجعت ادمن اخوي")
            continue

        # ----------------------------
        #   سحب ادمن Owner ثانوي
        # ----------------------------
        if lost_admin in secondary:
            actor = msg.user_id

            # إذا اللي سحب هو primary → مسموح ولا يعتبر سرقة
            if actor == primary:
                continue

            # يعتبر محاولة سرقة
            IG_HELPER.remove_admin(thread.thread_id, actor)
            IG_HELPER.set_admin(thread.thread_id, lost_admin)
            thread.send_message(f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر")

# ===============================================================
#                حماية الطرد الجماعي (5 في دقيقة)
# ===============================================================
def protection_mass_kick(thread, msg):
    """
    msg → يحتوي معلومات الطرد
    """
    owners = load_owners()
    primary = owners["primary"]

    kicker = msg.user_id
    target = msg.kicked_user

    if kicker == primary:
        return

    # سجّل عملية الطرد
    now = int(time.time())
    if kicker not in KICK_LOG:
        KICK_LOG[kicker] = []

    KICK_LOG[kicker] = [t for t in KICK_LOG[kicker] if now - t < 60]
    KICK_LOG[kicker].append(now)

    if len(KICK_LOG[kicker]) >= 5:
        IG.remove_admin(thread.thread_id, kicker)
        thread.send_message(f"(@{kicker}) طرد اكثر من ٥ اشخاص في دقيقة وسحبت ادمنه")

# ===============================================================
#                دمج النظامين في نقطة واحدة
# ===============================================================
def process_protection(thread, msg):
    """
    يتم استدعاؤه من handle_message
    """
    if thread.thread_type != "group":
        return False

    # جلب قائمة الادمنز قبل وبعد الحدث
    old_admins = thread.get_admins()
    thread.refresh_state()
    new_admins = thread.get_admins()

    # اكتشاف سرقة
    detect_admin_change(thread, msg, old_admins, new_admins)

    # اكتشاف طرد جماعي
    if msg.action == "kick":
        protection_mass_kick(thread, msg)

    return False