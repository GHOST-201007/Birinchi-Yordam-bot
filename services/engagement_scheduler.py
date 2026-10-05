import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database
from services import engagement

def start_scheduler(bot, get_gemini_response):
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

    async def run_0800_engagement():
        logging.info("[ENGAGEMENT] 08:00 job started")
        conn = database.get_connection()
        c = conn.cursor()
        try:
            # Barcha obuna bo'lgan yoki oddiy userlarni olish (masalan, ban bo'lmaganlar)
            c.execute("SELECT user_id FROM users WHERE is_banned = 0")
            users = c.fetchall()
            logging.info(f"[ENGAGEMENT] 08:00 target users: {len(users)}")
            
            event_date = database.get_uz_now().strftime("%Y-%m-%d")
            sent = 0
            failed = 0
            
            for row in users:
                user_id = row[0]
                q_item = engagement.pick_morning_question(user_id)
                
                # Check agar bugun allaqachon yuborilgan bo'lsa (Duplicate prevention)
                is_new = engagement.log_engagement_event(
                    user_id, '08:00', event_date, q_item['question'], q_item['category']
                )
                
                if is_new:
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"☀️ <b>Xayrli tong!</b>\n\n{q_item['question']}",
                            parse_mode="HTML"
                        )
                        sent += 1
                        await asyncio.sleep(0.05) # Rate limit protection
                    except Exception as e:
                        failed += 1
                        logging.warning(f"[ENGAGEMENT] 08:00 User {user_id} error: {e}")
            logging.info(f"[ENGAGEMENT] 08:00 sent: {sent}, failed: {failed}")
        finally:
            conn.close()

    async def run_1010_engagement():
        logging.info("[ENGAGEMENT] 10:10 job started")
        conn = database.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT user_id FROM users WHERE is_banned = 0")
            users = c.fetchall()
            event_date = database.get_uz_now().strftime("%Y-%m-%d")
            
            for row in users:
                user_id = row[0]
                
                # Ertalabki engagement history
                morning_log = engagement.get_today_engagement(user_id, '08:00', event_date)
                
                msg_text = None
                category = "followup"
                
                if morning_log and morning_log[3]: # answer_text
                    # User answered! AI follow up
                    msg_text = await engagement.generate_1010_followup(morning_log[3], get_gemini_response)
                else:
                    # User didn't answer, pick a new different question
                    q_item = engagement.pick_morning_question(user_id)
                    msg_text = f"🌞 <b>Kuningiz qanday o'tyapti?</b>\n\n{q_item['question']}"
                    category = q_item['category']
                
                is_new = engagement.log_engagement_event(
                    user_id, '10:10', event_date, msg_text, category
                )
                
                if is_new:
                    try:
                        await bot.send_message(chat_id=user_id, text=msg_text, parse_mode="HTML")
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
        finally:
            conn.close()

    async def run_premium_checkin():
        logging.info("[ENGAGEMENT] Premium check-in started")
        conn = database.get_connection()
        c = conn.cursor()
        try:
            # Faqat activ premiumlar
            c.execute("SELECT user_id FROM users WHERE is_banned = 0 AND is_premium = 1 AND premium_type != 'free'")
            users = c.fetchall()
            event_date = database.get_uz_now().strftime("%Y-%m-%d")
            
            question = "🌆 Kuningiz yaxshi o'tdimi? Bugun o'zingizni qanday his qilyapsiz?"
            
            for row in users:
                user_id = row[0]
                is_new = engagement.log_engagement_event(
                    user_id, 'premium_checkin', event_date, question, "premium"
                )
                
                if is_new:
                    try:
                        await bot.send_message(chat_id=user_id, text=f"💎 <b>Premium Check-in</b>\n\n{question}", parse_mode="HTML")
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
        finally:
            conn.close()

    # Schedule the jobs
    scheduler.add_job(run_0800_engagement, 'cron', hour=8, minute=0)
    scheduler.add_job(run_1010_engagement, 'cron', hour=10, minute=10)
    scheduler.add_job(run_premium_checkin, 'cron', hour=18, minute=0)
    
    # Check for missed jobs (e.g. restart happened at 08:05)
    async def run_missed_jobs():
        now = database.get_uz_now()
        
        # Agar hozir 08:00 dan 09:59 gacha bo'lsa, 08:00 jobni ishga tushiramiz (DB o'zi duplikatlarni to'xtatadi)
        if now.hour >= 8 and now.hour < 10:
            logging.info("[ENGAGEMENT] Restart in 08:xx window. Running 08:00 job.")
            await run_0800_engagement()
            
        # Agar 10:10 dan 11:59 gacha bo'lsa, 10:10 job
        if (now.hour == 10 and now.minute >= 10) or (now.hour == 11):
            logging.info("[ENGAGEMENT] Restart in 10:xx window. Running 10:10 job.")
            await run_1010_engagement()
            
        # Agar 18:00 dan 20:59 gacha bo'lsa, premium checkin
        if now.hour >= 18 and now.hour < 21:
            logging.info("[ENGAGEMENT] Restart in 18:xx window. Running premium_checkin job.")
            await run_premium_checkin()

    scheduler.start()
    asyncio.create_task(run_missed_jobs())
    return scheduler
