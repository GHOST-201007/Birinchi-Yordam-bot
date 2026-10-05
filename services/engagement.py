import random
import datetime
import database

QUESTION_BANK = [
    {"category": "hydration", "question": "Bugun qancha suv ichishni rejalashtirgansiz? O'zingizni yaxshi his qilish uchun kichik bir stakan ko'proq ichishga nima deysiz?"},
    {"category": "sleep", "question": "Kechasi yaxshi dam ola oldingizmi? Bugun energiya bilan to'la bo'lish uchun qanday kichik odat sizga yordam beradi?"},
    {"category": "physical_activity", "question": "Bugun jismoniy faollik uchun atigi 10 daqiqa ajrata olsangiz, qaysi mashqni tanlagan bo'lardingiz?"},
    {"category": "stress_management", "question": "Hozirgi paytda sizni charchatayotgan narsalar bormi? Bugun 5 daqiqa o'zingiz yoqtirgan ishni qilish imkoni bormi?"},
    {"category": "healthy_habits", "question": "Bugun sog'ligingiz uchun foydali bo'lgan qanday bitta kichik tanlov qila olasiz?"},
    {"category": "nutrition", "question": "Bugungi tushlik yoki kechki ovqatda qanday foydali mahsulot qo'shmoqchisiz?"},
    {"category": "motivation", "question": "O'z sog'ligingizni yaxshilash yo'lida sizga eng ko'p nima turtki beradi?"},
    {"category": "self_care", "question": "Bugun faqat o'zingiz uchun qiladigan bitta yoqimli ish nima bo'lishi mumkin?"}
]

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
    except:
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
    except:
        return "Rahmat, ulashganingiz uchun. O'zingizga qarab yuring, siz biz uchun qadrlisiz! ❤️"
