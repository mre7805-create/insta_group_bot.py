# modules/protection.py
"""
نظام الحماية (Protection)
يتوافق مع بنية الرسائل في listener.py و IG في ig_api.py (النسخة البسيطة).
- كشف سرقة الادمن (مقارنة snapshots قبل/بعد)
- محاولة استرجاع الادمن المسحوب (باستخدام حساب مساعد إذا وُجد)
- منع الطرد الجماعي (>=5 طرد في دقيقة)
- تخزين الحالة (owners, snapshots)
ملاحظات تنفيذية:
- listener يمرّر (thread: dict, msg: dict) كما في listener.py
- msg لأنواع:
    - {"type":"remove_user", "actor_id": "...", "target_ids": [...], "raw": ...}
    - {"type":"add_user", "actor_id": "...", "target_ids": [...], "raw": ...}
    - {"type":"action_log", "text": "...", ...}
    - {"type":"text", "text": "...", "user_id": "..."}
- الملف يحاول استخدام helper_session.txt إن وُجد (يحتوي sessionid فقط).
"""

import time
import json
import os
import requests
from modules.utils import log
from modules.ig_api import IG

OWNERS_FILE = "owners.json"
SNAPSHOT_FILE = "admin_snapshots.json"
KICK_LOG = {}  # { kicker_id: [timestamp, ...] }

# Helper: read helper session (optional)
def _load_helper_headers():
    helper_path = "helper_session.txt"
    if not os.path.exists(helper_path):
        return None
    try:
        sid = open(helper_path, "r", encoding="utf8").read().strip()
        if not sid:
            return None
        return {
            "User-Agent": IG.headers.get("User-Agent", "Instagram 290.0.0.0.123 Android"),
            "Cookie": f"sessionid={sid};"
        }
    except Exception as e:
        log(f"protection: failed loading helper session: {e}")
        return None

HELPER_HEADERS = _load_helper_headers()

# ---------------- owners storage ----------------
def load_owners():
    if not os.path.exists(OWNERS_FILE):
        return {"primary": None, "secondary": []}
    try:
        return json.load(open(OWNERS_FILE, "r", encoding="utf8"))
    except Exception:
        return {"primary": None, "secondary": []}

def save_owners(data):
    json.dump(data, open(OWNERS_FILE, "w", encoding="utf8"), indent=2)

def register_owner(user_id):
    data = load_owners()
    if data.get("primary") is None:
        data["primary"] = str(user_id)
    else:
        if str(user_id) not in [str(x) for x in data.get("secondary", [])]:
            data.setdefault("secondary", []).append(str(user_id))
    save_owners(data)
    return True

# ---------------- snapshots helpers ----------------
def _load_snapshots():
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    try:
        return json.load(open(SNAPSHOT_FILE, "r", encoding="utf8"))
    except Exception:
        return {}

def _save_snapshots(snap):
    json.dump(snap, open(SNAPSHOT_FILE, "w", encoding="utf8"), indent=2)

def fetch_thread_admins(thread_id):
    """
    إحضار قائمة الأدمنز الحالية في الثريد (أخذها من thread info)
    تعيد قائمة من user_ids (as strings).
    """
    try:
        url = f"{IG.API_URL}/direct_v2/threads/{thread_id}/"
        r = requests.get(url, headers=IG.headers, timeout=12)
        if r.status_code != 200:
            log(f"protection: failed fetch thread info {thread_id} status={r.status_code}")
            return []
        data = r.json().get("thread", {})
        # عادة توجد users داخل thread
        users = data.get("users", []) or data.get("items", [])
        admins = []
        for u in users:
            # user dict may be nested or flat
            uid = str(u.get("pk") or u.get("id") or u.get("user", {}).get("pk") or "")
            if not uid:
                continue
            # check flags
            if u.get("is_admin") or u.get("is_moderator") or u.get("is_team_admin"):
                admins.append(uid)
                continue
            role = (u.get("role") or u.get("status") or "")
            if isinstance(role, str) and role.lower() in ("admin", "creator", "administrator"):
                admins.append(uid)
                continue
        # dedupe
        return list(dict.fromkeys(admins))
    except Exception as e:
        log(f"protection: fetch_thread_admins error: {e}")
        return []

def _get_saved_admins(thread_id):
    snap = _load_snapshots()
    return snap.get(str(thread_id), [])

def _set_saved_admins(thread_id, admin_list):
    snap = _load_snapshots()
    snap[str(thread_id)] = list(dict.fromkeys([str(x) for x in admin_list]))
    _save_snapshots(snap)

# ---------------- low-level actions ----------------
def _post_remove_user(thread_id, user_id, headers=None):
    """
    محاولة طرد مستخدم من الثريد (remove_user endpoint).
    نستخدم headers الممرّر أو IG.headers افتراضياً.
    """
    try:
        h = headers if headers is not None else IG.headers
        url = f"{IG.API_URL}/direct_v2/threads/{thread_id}/remove_user/"
        data = {"user_id": str(user_id)}
        r = requests.post(url, headers=h, data=data, timeout=12)
        return r.status_code in (200, 201)
    except Exception as e:
        log(f"protection: remove_user error: {e}")
        return False

def _post_add_user(thread_id, user_id, headers=None):
    """
    محاولة إعادة إضافة مستخدم إلى الثريد (add_user endpoint).
    """
    try:
        h = headers if headers is not None else IG.headers
        url = f"{IG.API_URL}/direct_v2/threads/{thread_id}/add_user/"
        data = {"user_ids": f'["{user_id}"]'}
        r = requests.post(url, headers=h, data=data, timeout=12)
        return r.status_code in (200, 201)
    except Exception as e:
        log(f"protection: add_user error: {e}")
        return False

def _send_thread_message(thread_id, text, headers=None):
    try:
        h = headers if headers is not None else IG.headers
        url = f"{IG.API_URL}/direct_v2/threads/broadcast/text/"
        data = {"thread_ids": f'["{thread_id}"]', "text": text}
        r = requests.post(url, headers=h, data=data, timeout=8)
        return r.status_code in (200, 201)
    except Exception as e:
        log(f"protection: send_message error: {e}")
        return False

# ---------------- core detection & handlers ----------------
def detect_admin_change(thread, msg):
    """
    مقارنة snapshot القديم مع الحالة الحالية واكتشاف الادمنز المسحوبين.
    thread -> dict (كما في listener.py): يحتاج thread['thread_id']
    msg -> dict من listener.normalize_message
    """
    thread_id = str(thread.get("thread_id"))
    if not thread_id:
        return

    old_saved = _get_saved_admins(thread_id)
    current = fetch_thread_admins(thread_id)

    # إذا لم يكن لدينا snapshot سابق، خزّنه وارجع
    if not isinstance(old_saved, list) or old_saved == []:
        _set_saved_admins(thread_id, current)
        return

    removed = [a for a in old_saved if a not in current]
    if not removed:
        # حدثت تغييرات غير متعلقة بسحب الأدمن، حدّث snapshot ثم اخرج
        if set(current) != set(old_saved):
            _set_saved_admins(thread_id, current)
        return

    owners = load_owners()
    primary = str(owners.get("primary")) if owners.get("primary") is not None else None
    secondaries = [str(x) for x in owners.get("secondary", [])]

    # نحاول تحديد الفاعل (actor)
    actor = None
    if msg.get("type") == "remove_user":
        actor = str(msg.get("actor_id") or "")
        kicked = [str(x) for x in msg.get("target_ids", [])]
    else:
        # إذا لم يكن remove_user، نحاول سحب من raw event
        raw = msg.get("raw", {}) or {}
        actor = str(raw.get("actor_id") or raw.get("user_id") or "")
        kicked = []

    for lost_admin in removed:
        lost_admin = str(lost_admin)
        # تجاهل لو المفقود فارغ
        if not lost_admin:
            continue

        # حالة: فقدان الأونر الأساسي
        if primary and lost_admin == primary:
            # إذا الفاعل هو هو نفسه الرئيسي -> تجاهل
            if actor == primary:
                continue

            # إذا البوت نفسه اُزيل كأدمن (محفوظ اسمه غير معروف) -> نحاول إعادة رفعه
            # محاولة استخدام HELPER لعمل الاسترجاع وإقصاء المخرب
            # نحدد الرسائل التنبيهية كما طلبت
            try:
                if HELPER_HEADERS:
                    # helper first: يزيل المخرب ثم يرجّع الاونر
                    _post_remove_user(thread_id, actor, headers=HELPER_HEADERS)
                    _post_add_user(thread_id, primary, headers=HELPER_HEADERS)
                    _send_thread_message(thread_id,
                                         f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر",
                                         headers=IG.headers)
                else:
                    # بدون helper: نستخدم البوت بنفسه (قد لا ينجح لو البوت ليس مدرجاً كأدمن)
                    _post_remove_user(thread_id, actor, headers=IG.headers)
                    _post_add_user(thread_id, primary, headers=IG.headers)
                    _send_thread_message(thread_id,
                                         f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر",
                                         headers=IG.headers)
            except Exception as e:
                log(f"protection: failed handling lost primary admin: {e}")
            finally:
                # حدّث snapshot
                new_admins = fetch_thread_admins(thread_id)
                _set_saved_admins(thread_id, new_admins)
            continue

        # حالة: فقدان ادمن المساعد (إذا وُجد helper owner id تخزّن في owners.secondary أو في primary?):
        helper_id = None
        # نفترض أنّك خزّنت id المساعد في owners (مثلاً في secondary أو في ملف خاص) — إن لم يكن موجودًا نتحقّق من HELPER_HEADERS وجودها فقط
        # لا توجد آلية مضمّنة لاكتشاف helper id تلقائياً بدون بيانات إضافية
        if HELPER_HEADERS:
            # تحاول أن تعالج فقدان أي admin عبر helper إذا لم يكن primary
            if lost_admin == str(owners.get("helper_id") or ""):
                # إذا عرفنا helper id وتعطّل → حاول استرجاعه
                try:
                    _post_remove_user(thread_id, actor, headers=IG.headers)
                    _post_add_user(thread_id, lost_admin, headers=HELPER_HEADERS)
                    _send_thread_message(thread_id, f"(@{actor}) شال الادمن من المساعد وسحبت ادمنه ورجعت ادمن اخوي",
                                         headers=IG.headers)
                except Exception as e:
                    log(f"protection: failed restoring helper admin: {e}")
                finally:
                    new_admins = fetch_thread_admins(thread_id)
                    _set_saved_admins(thread_id, new_admins)
                continue

        # حالة: فقدان Owner ثانوي
        if lost_admin in secondaries:
            # لو الفاعل هو primary → مسموح
            if actor == primary:
                # تحديث snapshot فقط
                _set_saved_admins(thread_id, current)
                continue

            # محاولة استعادة باستخدام HELPER إن وُجد
            try:
                if HELPER_HEADERS:
                    _post_remove_user(thread_id, actor, headers=HELPER_HEADERS)
                    _post_add_user(thread_id, lost_admin, headers=HELPER_HEADERS)
                    _send_thread_message(thread_id, f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر",
                                         headers=IG.headers)
                else:
                    # بدون helper: نستخدم البوت
                    _post_remove_user(thread_id, actor, headers=IG.headers)
                    _post_add_user(thread_id, lost_admin, headers=IG.headers)
                    _send_thread_message(thread_id, f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر",
                                         headers=IG.headers)
            except Exception as e:
                log(f"protection: failed restoring secondary owner: {e}")
            finally:
                new_admins = fetch_thread_admins(thread_id)
                _set_saved_admins(thread_id, new_admins)
            continue

        # حالة عامة: فقدان أي ادمن آخر (غير owner)
        # سنعاملها كمحاولة سرقة: نزيل صلاحية الفاعل ونحاول إرجاع الادمن
        try:
            if HELPER_HEADERS:
                _post_remove_user(thread_id, actor, headers=HELPER_HEADERS)
                _post_add_user(thread_id, lost_admin, headers=HELPER_HEADERS)
                _send_thread_message(thread_id, f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر",
                                     headers=IG.headers)
            else:
                _post_remove_user(thread_id, actor, headers=IG.headers)
                _post_add_user(thread_id, lost_admin, headers=IG.headers)
                _send_thread_message(thread_id, f"(@{actor}) شال الادمن من Onwre وسحبت ادمنه ورجعت ادمن الاونر",
                                     headers=IG.headers)
        except Exception as e:
            log(f"protection: failed restoring admin: {e}")
        finally:
            new_admins = fetch_thread_admins(thread_id)
            _set_saved_admins(thread_id, new_admins)

# ---------------- protection mass kick ----------------
def protection_mass_kick(thread, msg):
    """
    كشف الطرد الجماعي: إذا قام أي مستخدم (غير primary) بطرد >=5 أشخاص خلال 60 ثانية
    نفّذ إزالة (kick) لذلك المستخدم.
    msg: النوع remove_user مع actor_id و target_ids
    """
    thread_id = str(thread.get("thread_id"))
    if not thread_id:
        return

    owners = load_owners()
    primary = str(owners.get("primary")) if owners.get("primary") is not None else None

    if msg.get("type") != "remove_user":
        return

    kicker = str(msg.get("actor_id") or "")
    if not kicker:
        return

    # لا نطبق على primary
    if primary and kicker == primary:
        return

    now = int(time.time())
    if kicker not in KICK_LOG:
        KICK_LOG[kicker] = []
    # keep only last 60s
    KICK_LOG[kicker] = [t for t in KICK_LOG[kicker] if now - t < 60]
    # one entry per remove_user event; if event removed many users we still count it as 1 action,
    # but if you prefer counting individuals you can extend by len(target_ids)
    KICK_LOG[kicker].append(now)

    if len(KICK_LOG[kicker]) >= 5:
        # نزيل صلاحياته (نحاول طرده من القروب)
        try:
            # حاول helper أولاً
            if HELPER_HEADERS:
                _post_remove_user(thread_id, kicker, headers=HELPER_HEADERS)
            else:
                _post_remove_user(thread_id, kicker, headers=IG.headers)
            _send_thread_message(thread_id, f"(@{kicker}) طرد اكثر من ٥ اشخاص في دقيقة وسحبت ادمنه", headers=IG.headers)
        except Exception as e:
            log(f"protection: failed mass-kick action: {e}")
        finally:
            # أفرغ السجل لهذا المستخدم
            KICK_LOG[kicker] = []

# ---------------- entry point ----------------
def process_protection(thread, msg):
    """
    يستدعى من listener أو handlers
    thread: dict (as from IG.get_inbox / thread info)
    msg: normalized dict from listener.normalize_message
    """
    # نتأكد أنه ثريد قروب (users len > 2)
    users = thread.get("users", []) or []
    if len(users) <= 2:
        return False

    # 1) حماية من الطرد الجماعي
    if msg.get("type") == "remove_user":
        protection_mass_kick(thread, msg)

    # 2) مقارنة الأدمنز (كشف سرقة)
    # نعمل مقارنة snapshot فقط عندما نرى تغير في الادمنز عبر استدعاء fetch_thread_admins
    try:
        detect_admin_change(thread, msg)
    except Exception as e:
        log(f"protection: detect_admin_change exception: {e}")

    return False