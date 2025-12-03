# modules/games.py
"""
نظام الألعاب – إنستقرام
- لعبة التكرار
- لعبة المقال
- نظام أسرع إجابة + الوقت المستغرق + حساب كلمات بالدقيقة
الأوامر:
  تكرار
  مقال
  انهاء
  نقاطي
"""

import time
import random
from modules.ig_api import IG

# ================================
#     التخزين الأساسي
# ================================
ACTIVE_GAME = None          # "repeat" | "article" | None
CURRENT_ANSWER = None
WINNERS_LOCK = False
SCORES = {}
GAME_START_TIME = 0         # لحساب سرعة الرد
FIRST_WINNER = None

# ================================
#  200 كلمة للتكرار (عشوائية)
# ================================
WORDS = [
    "انا","سلام","ورد","بيت","سماء","بحر","قلب","نعم","لا","تمام",
    "صحيح","خطأ","محبة","فرح","لعب","سرعة","وقت","ليل","نهار","طريق",
    "هدف","قهوة","شاي","كتاب","قلم","مطر","غيمة","نهر","جبل","وردة",
    "عمل","بيت","سفر","راحة","نسيان","ذكرى","اسم","لون","كلمة","حرف",
    "حياة","العاب","شمس","قمر","لحن","وتر","خط","ورق","باب","صوت",
    "حلم","سر","وهم","صداقة","وحدة","نفس","روح","جسد","ليل","نهار",
    "طفل","كبير","صغير","هوا","ماء","نار","تراب","طرق","ضحك","بسمة",
    "ورد","قمر","سكون","ركض","مشى","لمس","شم","طعم","عين","اذن",
    "سرير","كرسي","طاولة","جدار","مدينة","شارع","ضوء","ظل","قوة","ضعف",
    "سرعة","مشاعر","صدق","كذب","حب","كره","حديقة","سوق","هواء","برد",
    "حر","سهل","صعب","فكرة","هدف","نقطة","خطوة","جمال","هدوء","حماس",
    "ركن","زاوية","باب","نافذة","رؤية","نظر","حركة","ثبات","خبر","خبرة",
    "غريب","قريب","بعيد","ماضي","مستقبل","لحظة","دقيقة","ساعة","ثانية","حدث",
    "زمان","مكان","قيمة","نور","ظلام","وعد","أمل","حزن","فرح","عقل",
    "منطق","مهارة","ذكاء","سرعة","تحدي","قدرة","كتابة","قراءة","معلومة","قصة",
    "حديث","سؤال","جواب","مسافة","موج","ريح","نجمة","سماء","غيمة","نور",
    "ظل","قمر","شمس","اشراق","ليل","نهار","مفتاح","باب","حقل","جبل",
    "سهل","وادي","غابة","شجرة","ورق","نبتة","حجر","نهر","صوت","صدى"
]

# ================================
#   200 مقال (جمل جاهزة)
# ================================
ARTICLES = [
    "الحياة لا تمنح الدروس مجانًا بل تمنحها لمن يستحق الفهم.",
    "كن لطيفًا فكل شخص يقاتل معركته الخاصة دون أن يُظهرها.",
    "الكلمة الطيبة صدقة تنبت في قلب من يسمعها.",
    "الهدوء مساحة آمنة لا يفهمها إلا من جرب الضوضاء.",
    "الوقت يمضي سواء استغللته أم ضيعته فلا تكن عابرًا بلا أثر.",
    "القوة ليست في الصوت العالي بل في النفس الطويل.",
    "الأحلام تكبر بصمت وتتحقق عندما لا نتوقع.",
    "الأصدقاء الحقيقيون قلة لكن وجودهم يعادل حياة.",
    "السعادة قرار وراحة البال إنجاز.",
    "النجاح يبدأ بخطوة لا بثقة كاملة.",
] * 20  # = 200 مقال عشوائي


# ================================
#     لعبة التكرار
# ================================
def generate_repeat_game():
    count1 = random.randint(2, 5)
    count2 = random.randint(3, 7)

    w1 = random.choice(WORDS)
    w2 = random.choice(WORDS)

    question = f"{w1} ({count1})   {w2} ({count2})"
    answer = (" ".join([w1] * count1)) + " " + (" ".join([w2] * count2))

    return question, answer.strip()


# ================================
#     لعبة المقال
# ================================
def generate_article_game():
    text = random.choice(ARTICLES)
    return text, text


# ================================
#     بدء الألعاب
# ================================
def start_repeat(thread_id):
    global ACTIVE_GAME, CURRENT_ANSWER, WINNERS_LOCK, GAME_START_TIME, FIRST_WINNER

    question, answer = generate_repeat_game()
    ACTIVE_GAME = "repeat"
    CURRENT_ANSWER = answer
    WINNERS_LOCK = False
    FIRST_WINNER = None
    GAME_START_TIME = time.time()

    IG.send_message(thread_id, f"لعبة التكرار بدأت.\nاكتب الإجابة:\n{question}")


def start_article(thread_id):
    global ACTIVE_GAME, CURRENT_ANSWER, WINNERS_LOCK, GAME_START_TIME, FIRST_WINNER

    question, answer = generate_article_game()
    ACTIVE_GAME = "article"
    CURRENT_ANSWER = answer
    WINNERS_LOCK = False
    FIRST_WINNER = None
    GAME_START_TIME = time.time()

    IG.send_message(thread_id, f"لعبة المقال بدأت.\nاكتب النص التالي:\n{question}")


# ================================
#     إنهاء اللعبة
# ================================
def end_game(thread_id):
    global ACTIVE_GAME, CURRENT_ANSWER, WINNERS_LOCK, FIRST_WINNER
    ACTIVE_GAME = None
    CURRENT_ANSWER = None
    WINNERS_LOCK = False
    FIRST_WINNER = None

    IG.send_message(thread_id, "تم إنهاء اللعبة.")


# ================================
#     نقاطي
# ================================
def send_points(thread_id, user_id):
    pts = SCORES.get(user_id, 0)
    IG.send_message(thread_id, f"نقاطك: {pts}")


# ================================
#     فحص الإجابة
# ================================
def check_answer(thread_id, user_id, text):
    global ACTIVE_GAME, CURRENT_ANSWER, WINNERS_LOCK, FIRST_WINNER

    if not ACTIVE_GAME:
        return

    if WINNERS_LOCK:
        return

    if text.strip() == CURRENT_ANSWER:
        WINNERS_LOCK = True
        FIRST_WINNER = user_id

        # وقت الاستجابة
        now = time.time()
        taken = round(now - GAME_START_TIME, 2)

        # حساب الكلمات بالدقيقة
        words = len(text.split())
        wpm = round((words / taken) * 60, 1) if taken > 0 else 0

        # زيادة نقاطه
        SCORES[user_id] = SCORES.get(user_id, 0) + 1

        IG.send_message(
            thread_id,
            f"الأول: <@{user_id}>\nالوقت المستغرق: {taken} ثانية\nسرعتك: {wpm} كلمة في الدقيقة"
        )

        ACTIVE_GAME = None
        CURRENT_ANSWER = None


# ================================
#     نقطة الدخول من listener
# ================================
def process_game(thread_id, msg):
    if msg["type"] != "text":
        return

    text = msg["text"].strip()
    user = msg["user_id"]

    if text == "تكرار":
        start_repeat(thread_id)
        return

    if text == "مقال":
        start_article(thread_id)
        return

    if text == "انهاء":
        end_game(thread_id)
        return

    if text == "نقاطي":
        send_points(thread_id, user)
        return

    if ACTIVE_GAME:
        check_answer(thread_id, user, text)