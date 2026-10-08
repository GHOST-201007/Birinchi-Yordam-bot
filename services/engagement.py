import random
import datetime
import database
import logging

QUESTION_BANK = [
    {"category": "hydration", "question": "Suv ichish sizga energiya beradi. Bugun qancha ichishni rejalashtiryapsiz?"},
    {"category": "sleep", "question": "Kechagi damni qoniqtirdimi? Bugun quvvatni oshirish uchun biror kichik odatingiz bormi?"},
    {"category": "physical_activity", "question": "Bugun 10 daqiqalik jismoniy harakatni rejalashtiryapsiz. Qaysi mashqni tanlaysiz?"},
    {"category": "stress_management", "question": "Bugun asabiylashtirgan narsa bormi? Uni 5 daqiqada qanday kamaytirardingiz?"},
    {"category": "healthy_habits", "question": "Sog‘lig‘ingiz uchun kichik bir o‘zgarish qilishni xohlaysizmi? Bugun nimalarni sinab ko‘rmoqchisiz?"},
    {"category": "nutrition", "question": "Tushlik yoki kechki ovqatga qanday foydali qo‘shimchalar qo‘shasiz?"},
    {"category": "motivation", "question": "Bugun sizni ilhomlantirgan narsa nima?"},
    {"category": "self_care", "question": "O‘zingizga bir payt ajratib, nima qilishni xohlaysiz?"},
    {"category": "mindfulness", "question": "Bugun bir necha daqiqa nafas olishga e’tibor qaratdingizmi? Qanday his qildingiz?"}
]


# Additional premium check‑in prompts – short, friendly and varied
PREMIUM_CHECKIN_QUESTIONS = [
    "🌆 Kuningiz yaxshi o'tdimi? Bugun qanday his qilyapsiz?",
    "💎 Sizning bugungi kayfiyatingiz qanday? Qanday yangiliklar bo‘ldi?",
    "✨ Sizni bugun nima ilhomlantirdi? Qisqacha ayting!",
    "🌟 Sizni qoniqtirgan biror narsa bo‘ldimi? Qisqa fikr bildiring.",
    "🔹 Bugun o'zingizga qanday g'amxo'rlik qildingiz?",
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
    conn = database.get_connection()
    c = conn.cursor()
    try:
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
        conn.rollback()
        import logging
        logging.error(f"Error logging engagement: {e}")
        return False
    finally:
        conn.close()

def update_engagement_answer(user_id, event_type, event_date, answer_text, bot_reply=None):
    """User javob berganida saqlash"""
    conn = database.get_connection()
    c = conn.cursor()
    try:
        now = database.get_uz_now()
        c.execute('''
            UPDATE engagement_logs
            SET answered_at = %s, answer_text = %s, bot_reply = %s
            WHERE user_id = %s AND event_type = %s AND event_date = %s
        ''', (now, answer_text, bot_reply, user_id, event_type, event_date))
        conn.commit()
    except Exception as e:
        conn.rollback()
        import logging
        logging.error(f"Error updating engagement answer: {e}")
    finally:
        conn.close()

def get_today_engagement(user_id, event_type, event_date):
    """Bugungi muayyan event logging ini olish"""
    conn = database.get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            SELECT id, question, answered_at, answer_text, bot_reply
            FROM engagement_logs
            WHERE user_id = %s AND event_type = %s AND event_date = %s
        ''', (user_id, event_type, event_date))
        return c.fetchone()
    finally:
        conn.close()

def pick_morning_question(user_id):
    """User uchun 08:00 savolini tanlash (duplicate oldini oladi)"""
    conn = database.get_connection()
    c = conn.cursor()
    try:
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
        conn.close()

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
    try:
        return await ai_generate_func(prompt)
    except Exception as e:
        logging.exception("Error generating premium reply")
        return "Rahmat, ulashganingiz uchun. O'zingizga qarab yuring, siz biz uchun qadrlisiz! ❤️"
