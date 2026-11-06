import random
import datetime
import database
import logging

QUESTION_BANK = [
    {"category": "hydration", "question": "Ertalab bir stakan iliq suv ichish tanani uyg'otadi. Kun davomida yetarli suv ichishni unutmang! 💧"},
    {"category": "sleep", "question": "Kecha yaxshi dam oldingizmi? Bugun tetik va quvvatli bo'lish uchun qanday rejangiz bor? 😴"},
    {"category": "physical_activity", "question": "Bugun 10-15 daqiqa piyoda yurish yoki yengil badantarbiya qilishga vaqt ajratasizmi? 🏃‍♂️"},
    {"category": "stress_management", "question": "Kun davomida xotirjamlikni saqlash muhim. Charchoq paydo bo'lsa, qisqa tanaffus qilib chuqur nafas oling. 🧘"},
    {"category": "healthy_habits", "question": "Sog'lom turmush tarzi kichik odatlardan boshlanadi. Bugun qaysi foydali odatni sinab ko'rmoqchisiz? 🍏"},
    {"category": "nutrition", "question": "Bugungi taomnomangizga ko'proq meva, sabzavot yoki yangi ko'katlar qo'shishni rejalashtirdingizmi? 🥗"},
    {"category": "motivation", "question": "Bugungi yangi kuningiz samarali va xayrli o'tishini tilaymiz! Bugungi asosiy maqsadingiz nima? 🎯"},
    {"category": "self_care", "question": "Ish va tashvishlar orasida o'zingizga ham ozgina vaqt ajratishni unutmang. Bugun o'zingizni qanday xursand qilasiz? ☕"},
    {"category": "mindfulness", "question": "Kuningizni yengil tabassum va yaxshi niyat bilan boshlang. O'zingizni qanday his qilyapsiz? ✨"}
]


# Additional premium check‑in prompts – short, friendly and varied
PREMIUM_CHECKIN_QUESTIONS = [
    "🌆 Kuningiz qanday o'tdi? Bugun o'zingizni qanday his qilyapsiz?",
    "💎 Bugungi kayfiyatingiz va umumiy holatingiz qanday? Qandaydir bezovtalik yoki charchoq bormi?",
    "✨ Bugungi kuningiz samarali bo'ldimi? O'zingizga vaqt ajrata oldingizmi?",
    "🌟 Oqshomingiz xayrli o'tsin! Ertangi kun uchun qanday rejalaringiz bor?",
    "🔹 Bugun salomatligingiz va salomatlik rejalaringiz uchun nimalar qila oldingiz?",
]

def pick_premium_checkin_question():
    """Return a random premium check‑in message.
    Keeps messages short, personal and varied.
    """
    return random.choice(PREMIUM_CHECKIN_QUESTIONS)

# Morning greeting variations for daily engagement
MORNING_GREETINGS = [
    "☀️ <b>Xayrli tong!</b>",
    "🌅 <b>Salom, yangi kun!</b>",
    "👋 <b>Yaxshi tong, do‘stim!</b>",
    "🌞 <b>Kun yorqin bo‘lsin!</b>",
]

def pick_morning_greeting():
    """Return a random short morning greeting.
    Used to prepend daily engagement questions.
    """
    return random.choice(MORNING_GREETINGS)

def log_engagement_event(user_id, event_type, event_date, question, category=None):
    """Event yuborilganda log ga yozish"""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        now = database.get_uz_now()
        c.execute('''
            INSERT INTO engagement_logs 
            (user_id, event_type, event_date, question, category, sent_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, event_type, event_date) DO NOTHING
        ''', (user_id, event_type, event_date, question, category, now))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        database._safe_rollback(conn)
        import logging
        logging.error(f"Error logging engagement: {e}")
        return False
    finally:
        database._safe_close(c, conn)

def prepare_premium_checkin(user_id, event_date, question, category="premium"):
    """Bugungi Premium Check-in qaydini tayyorlaydi; yuborilmagan bo'lsa savolni qaytaradi."""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO engagement_logs
                (user_id, event_type, event_date, question, category, sent_at)
            VALUES (%s, 'premium_checkin', %s, %s, %s, NULL)
            ON CONFLICT (user_id, event_type, event_date) DO NOTHING
        """, (user_id, event_date, question, category))
        conn.commit()

        c.execute("""
            SELECT sent_at, question
            FROM engagement_logs
            WHERE user_id = %s
              AND event_type = 'premium_checkin'
              AND event_date = %s
        """, (user_id, event_date))
        row = c.fetchone()

        if not row or row[0] is not None:
            return None

        return row[1]
    except Exception:
        database._safe_rollback(conn)
        raise
    finally:
        database._safe_close(c, conn)


def mark_premium_checkin_sent(user_id, event_date):
    """Faqat Telegram xabari muvaffaqiyatli yuborilgandan keyin chaqiriladi."""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            UPDATE engagement_logs
            SET sent_at = %s
            WHERE user_id = %s
              AND event_type = 'premium_checkin'
              AND event_date = %s
              AND sent_at IS NULL
        """, (database.get_uz_now(), user_id, event_date))
        conn.commit()
        return c.rowcount > 0
    except Exception:
        database._safe_rollback(conn)
        raise
    finally:
        database._safe_close(c, conn)


def update_engagement_answer(user_id, event_type, event_date, answer_text, bot_reply=None):
    """User javob berganida saqlash"""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        now = database.get_uz_now()
        c.execute('''
            UPDATE engagement_logs
            SET answered_at = %s, answer_text = %s, bot_reply = %s
            WHERE user_id = %s AND event_type = %s AND event_date = %s
        ''', (now, answer_text, bot_reply, user_id, event_type, event_date))
        conn.commit()
    except Exception as e:
        database._safe_rollback(conn)
        import logging
        logging.error(f"Error updating engagement answer: {e}")
    finally:
        database._safe_close(c, conn)

def set_engagement_message_id(user_id, event_type, event_date, message_id):
    """Yuborilgan engagement xabarining Telegram message_id sini saqlash."""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute('''
            UPDATE engagement_logs
            SET message_id = %s
            WHERE user_id = %s AND event_type = %s AND event_date = %s
        ''', (message_id, user_id, event_type, event_date))
        conn.commit()
    except Exception:
        database._safe_rollback(conn)
        logging.exception("Error saving engagement message_id")
    finally:
        database._safe_close(c, conn)


def find_unanswered_by_reply(user_id, message_id):
    """User reply qilgan bot xabari javob berilmagan engagement xabarimi?
    Topilsa (event_type, event_date), aks holda None qaytaradi."""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT event_type, event_date
            FROM engagement_logs
            WHERE user_id = %s AND message_id = %s AND answered_at IS NULL
            LIMIT 1
        ''', (user_id, message_id))
        row = c.fetchone()
        return (row[0], row[1]) if row else None
    finally:
        database._safe_close(c, conn)


def get_today_engagement(user_id, event_type, event_date):
    """Bugungi muayyan event logging ini olish"""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT id, question, answered_at, answer_text, bot_reply
            FROM engagement_logs
            WHERE user_id = %s AND event_type = %s AND event_date = %s
        ''', (user_id, event_type, event_date))
        return c.fetchone()
    finally:
        database._safe_close(c, conn)

def pick_morning_question(user_id):
    """User uchun 08:00 savolini tanlash (duplicate oldini oladi)"""
    conn = None
    c = None
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT question FROM engagement_logs 
            WHERE user_id = %s AND event_type = '08:00'
            ORDER BY sent_at DESC LIMIT 5
        ''', (user_id,))
        recent_questions = [row[0] for row in c.fetchall()]
        
        available = [q for q in QUESTION_BANK if q["question"] not in recent_questions]
        if not available:
            available = QUESTION_BANK
            
        # interests bo'yicha weighting qilinishi mumkin, hozircha random
        return random.choice(available)
    finally:
        database._safe_close(c, conn)

async def generate_1010_followup(user_answer, ai_generate_func):
    """10:10 uchun AI orqali follow-up generatsiya qilish"""
    prompt = (
        f"Foydalanuvchi ertalabki sog'lom odat so'roviga shunday javob berdi: '{user_answer}'. "
        f"Uning javobini hisobga olgan holda, unga dalda beruvchi yoki qiziqarli qo'shimcha bitta savol ber. "
        f"Juda qisqa (1-2 gap), samimiy va do'stona bo'lsin."
    )
    try:
        return await ai_generate_func(prompt)
    except Exception as e:
        logging.exception("Error generating 10:10 follow-up")
        return "Ajoyib tanlov! Bugungi kuningiz samarali va yoqimli o'tishini tilayman. O'zingizni asrang!"

async def generate_premium_reply(user_answer, ai_generate_func):
    """Premium userlarning holati bo'yicha javobga supportive AI reply"""
    prompt = (
        f"Foydalanuvchi bugungi kungi holati/kayfiyati haqida shunday dedi: '{user_answer}'. "
        f"Unga qisqa (1-3 gap), muloyim va qo'llab-quvvatlovchi javob yoz. "
        f"Agar u charchagan bo'lsa dalda ber, xursand bo'lsa tabriklab qo'y. Shifokor yoki psixolog rolini o'ynama."
    )
    fallback = "Rahmat, ulashganingiz uchun. O'zingizga qarab yuring, siz biz uchun qadrlisiz! ❤️"
    try:
        # AI ishlamasa get_gemini_response None qaytaradi — bo'sh xabar yuborilmasin
        return await ai_generate_func(prompt) or fallback
    except Exception as e:
        logging.exception("Error generating premium reply")
        return fallback
