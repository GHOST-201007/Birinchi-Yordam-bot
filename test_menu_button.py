import asyncio
import os
from aiogram import Bot, types
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

async def main():
    if not TOKEN or not ADMIN_ID:
        print("Missing token or admin id")
        return
        
    bot = Bot(token=TOKEN)
    
    # Try with query params
    try:
        url_with_params = "https://example.com?v=1.1.0&score=10"
        await bot.set_chat_menu_button(
            chat_id=ADMIN_ID,
            menu_button=types.MenuButtonWebApp(
                text="Test Menu Button",
                web_app=types.WebAppInfo(url=url_with_params)
            )
        )
        print("Success setting with query params")
    except Exception as e:
        print(f"Failed with query params: {e}")

    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
