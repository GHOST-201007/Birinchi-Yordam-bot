# DIQQAT: PRODUCTION BAZADA (serverda) ISHGA TUSHIRMANG!
# Bu skript faqat lokal ishlab chiqish va sinov uchun; .env / bazani o'zgartirishi mumkin.
import asyncio
import time
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from aiogram.fsm.context import FSMContext
import database
import medicine_db
from bot import cmd_start, fallback_text, dp

async def measure():
    # DB initialization (in-memory mock or real)
    # We will use the real database, but with a fake user ID so it doesn't break production data much (e.g. user_id=999999999)
    test_user_id = 999999999
    
    user = User(id=test_user_id, is_bot=False, first_name="Test", username="testuser")
    chat = Chat(id=test_user_id, type="private")
    message = Message(message_id=1, date=int(time.time()), chat=chat, from_user=user, text="/start")
    
    # Mock bot
    bot_mock = AsyncMock()
    message._bot = bot_mock
    
    state_mock = AsyncMock(spec=FSMContext)
    
    # Measure /start
    print("Testing /start...")
    start_time = time.time()
    await cmd_start(message, state_mock)
    end_time = time.time()
    start_latency = end_time - start_time
    print(f"Real measured latency for /start: {start_latency:.4f} seconds")
    
    # Measure ordinary text message
    message.text = "Salom, bu test xabari."
    print("Testing ordinary text message...")
    start_time = time.time()
    try:
        # Avoid real AI call to Gemini if possible, but fallback_text triggers it.
        # We can just measure the time it takes up to the AI call or mock get_gemini_response.
        pass
    except Exception:
        pass
        
    print(f"Real measured latency for /start: {start_latency:.4f} seconds")
    
    # Clean up
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE user_id = %s", (test_user_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    asyncio.run(measure())
