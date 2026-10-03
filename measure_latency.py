import os
import time
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types
import aiohttp
import sqlite3

load_dotenv()
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def measure_latency():
    print("[PERF] Measuring latency...")
    
    # Measure DB latency (T2-T3)
    t_start_db = time.time()
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    conn.close()
    t_end_db = time.time()
    db_latency = (t_end_db - t_start_db) * 1000

    # Measure Gemini latency (T4-T5)
    t_start_gemini = time.time()
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash",
            contents="Hello! This is a quick latency test. Respond with 'ok'."
        )
    except Exception as e:
        print(f"Gemini API Error: {e}")
    t_end_gemini = time.time()
    gemini_latency = (t_end_gemini - t_start_gemini) * 1000

    # Measure Telegram API latency (T6-T7)
    t_start_telegram = time.time()
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
        async with session.get(url) as resp:
            await resp.json()
    t_end_telegram = time.time()
    telegram_latency = (t_end_telegram - t_start_telegram) * 1000

    print(f"telegram_to_handler = (Network/Webhook dependent)")
    print(f"database = {db_latency:.2f} ms")
    print(f"gemini_request = {gemini_latency:.2f} ms")
    print(f"telegram_send = {telegram_latency:.2f} ms")

asyncio.run(measure_latency())
