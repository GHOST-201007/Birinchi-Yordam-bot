import subprocess
import sys
import time
import os

def main():
    print("🚀 Production rejimida ishga tushirilmoqda...")
    
    # 1. Web serverni ishga tushirish (app_server.py)
    app_server_path = os.path.join(os.path.dirname(__file__), "app_server.py")
    web_server = subprocess.Popen([sys.executable, app_server_path])
    print("✅ Veb-server 8000-portda ishga tushdi.")
    
    time.sleep(2)
    
    # 2. Telegram botni ishga tushirish (bot.py)
    bot_path = os.path.join(os.path.dirname(__file__), "bot.py")
    bot_process = subprocess.Popen([sys.executable, bot_path])
    print("✅ Telegram bot ishga tushdi.")
    
    try:
        bot_process.wait()
    except KeyboardInterrupt:
        print("To'xtatilmoqda...")
        web_server.terminate()
        bot_process.terminate()

if __name__ == "__main__":
    main()
