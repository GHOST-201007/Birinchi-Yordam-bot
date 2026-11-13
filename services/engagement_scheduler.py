import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database
from services import engagement
from aiogram.utils.keyboard import InlineKeyboardBuilder

def start_scheduler(bot, get_gemini_response):
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    premium_checkin_lock = asyncio.Lock()

    async def run_0800_engagement():
        logging.info("[ENGAGEMENT] 08:00 job started")
        conn = None
        c = None
        try:
            # Banda bo'lmagan barcha userlar. YAGONA shart: database.NOT_BANNED_SQL (ikkala ban rejimi chiqarib tashlanadi;
            # muddati o'tgan, lekin hali tozalanmagan ban esa hisobga olinmaydi)
            users = [(uid,) for uid in await asyncio.to_thread(database.get_active_user_ids)]
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
                        sent_msg = await bot.send_message(
                            chat_id=user_id,
                            text=f"{engagement.pick_morning_greeting()}\n\n{q_item['question']}",
                            parse_mode="HTML"
                        )
                        await asyncio.to_thread(
                            engagement.set_engagement_message_id,
                            user_id, '08:00', event_date, sent_msg.message_id,
                        )
                        sent += 1
                        await asyncio.sleep(0.05) # Rate limit protection
                    except Exception as e:
                        failed += 1
                        logging.warning(f"[ENGAGEMENT] 08:00 User {user_id} error: {e}")
            logging.info(f"[ENGAGEMENT] 08:00 sent: {sent}, failed: {failed}")
        finally:
            database._safe_close(c, conn)

    async def run_1010_engagement():
        logging.info("[ENGAGEMENT] 10:10 job started")
        conn = None
        c = None
        try:
            users = [(uid,) for uid in await asyncio.to_thread(database.get_active_user_ids)]   # banda bo'lmaganlar
            event_date = database.get_uz_now().strftime("%Y-%m-%d")
            
            for row in users:
                user_id = row[0]
                
                # Ertalabki engagement history
                morning_log = engagement.get_today_engagement(user_id, '08:00', event_date)
                
                msg_text = None
                category = "followup"
                
                # Determine message text based on previous morning engagement
                if morning_log and morning_log[3]:  # answer_text exists
                    # User answered the 08:00 question, generate AI follow‑up
                    msg_text = await engagement.generate_1010_followup(morning_log[3], get_gemini_response)
                    category = "followup"
                else:
                    # No answer yet – send a new morning‑style question
                    q_item = engagement.pick_morning_question(user_id)
                    msg_text = f"🌞 <b>Kuningiz qanday o'tyapti?</b>\n\n{q_item['question']}"
                    category = q_item["category"]
                
                # Add inline button for AI answer retrieval
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                builder = InlineKeyboardBuilder()
                # Callback data includes event type and date for safe identification
                builder.button(text="🤖 Javob olish", callback_data=f"engagement_answer:10:10:{event_date}")
                reply_markup = builder.as_markup()
                
                is_new = engagement.log_engagement_event(
                    user_id, '10:10', event_date, msg_text, category
                )
                
                if is_new:
                    try:
                        sent_msg = await bot.send_message(
                            chat_id=user_id,
                            text=msg_text,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                        await asyncio.to_thread(
                            engagement.set_engagement_message_id,
                            user_id, '10:10', event_date, sent_msg.message_id,
                        )
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
        finally:
            database._safe_close(c, conn)

    async def run_premium_checkin():
        async with premium_checkin_lock:
            logging.info("[ENGAGEMENT] Premium check-in started")
            conn = None
            c = None
            try:
                users = await asyncio.to_thread(database.get_premium_checkin_targets)      # banda bo'lmagan Premiumlar
                now = database.get_uz_now()
                event_date = now.strftime("%Y-%m-%d")
                logging.info(
                    f"[ENGAGEMENT] Premium check-in target users: {len(users)}"
                )

                for row in users:
                    user_id = row[0]
                    exp = row[1]
                    ptype = row[2]
                    if ptype == "free":
                        continue
                    if exp:
                        try:
                            if database._to_uz_datetime(exp) <= now:
                                continue
                        except Exception:
                            pass

                    question = engagement.pick_premium_checkin_question()

                    try:
                        pending_question = engagement.prepare_premium_checkin(
                            user_id, event_date, question, "premium"
                        )
                        if pending_question is None:
                            continue

                        sent_msg = await bot.send_message(
                            chat_id=user_id,
                            text=f"💎 <b>Premium Check-in</b>\n\n{pending_question}",
                            parse_mode="HTML",
                        )
                        engagement.mark_premium_checkin_sent(user_id, event_date)
                        await asyncio.to_thread(
                            engagement.set_engagement_message_id,
                            user_id, 'premium_checkin', event_date, sent_msg.message_id,
                        )
                        await asyncio.sleep(0.05)
                    except Exception:
                        logging.exception(
                            "[ENGAGEMENT] Premium check-in failed for user %s",
                            user_id,
                        )
            finally:
                database._safe_close(c, conn)

    # Schedule the jobs
    scheduler.add_job(run_0800_engagement, 'cron', hour=8, minute=0)
    # 10:10 job runs only on even calendar days
    scheduler.add_job(run_1010_engagement, 'cron', hour=10, minute=10, day='2-30/2')
    scheduler.add_job(run_premium_checkin, 'cron', hour=20, minute=30)
    
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
            
        # Premium Check-in: faqat bugun 20:30 dan keyin, yarim tungacha.
        if (
            (now.hour == 20 and now.minute >= 30)
            or 21 <= now.hour <= 23
        ):
            logging.info(
                "[ENGAGEMENT] Restart recovery: today's Premium Check-in"
            )
            await run_premium_checkin()

    scheduler.start()
    asyncio.create_task(run_missed_jobs())
    return scheduler
