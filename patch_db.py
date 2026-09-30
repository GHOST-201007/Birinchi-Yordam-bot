import re
import os

def patch_env():
    with open(".env", "r", encoding="utf-8") as f:
        content = f.read()
    
    if "PRO_TRIAL_STARS" not in content:
        content += """
# Premium Configuration
PRO_TRIAL_STARS=50
PRO_TRIAL_DAYS=3

PRO_MONTHLY_STARS=150
PRO_MONTHLY_DAYS=30

ULTRA_MONTHLY_STARS=300
ULTRA_MONTHLY_DAYS=30

FREE_AI_DAILY_LIMIT=2
PRO_AI_DAILY_LIMIT=10
ULTRA_AI_DAILY_LIMIT=100

PREMIUM_REWARD_POINTS=100
PREMIUM_REWARD_DAYS=3
"""
        with open(".env", "w", encoding="utf-8") as f:
            f.write(content)
        print(".env updated.")

def patch_database():
    with open("database.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Add premium_type column to init_db
    content = content.replace(
        "is_premium INTEGER DEFAULT 0,",
        "is_premium INTEGER DEFAULT 0,\n            premium_type TEXT DEFAULT 'free',"
    )

    # Change limits based on premium type
    # find try_consume_daily_request
    old_func = """    c.execute("SELECT registered_at, is_premium, premium_expires_at FROM users WHERE user_id = %s", (user_id,))"""
    new_func = """    c.execute("SELECT registered_at, is_premium, premium_expires_at, premium_type FROM users WHERE user_id = %s", (user_id,))"""
    content = content.replace(old_func, new_func)

    old_row = """    registered_at_str, is_premium, premium_expires_at = row"""
    new_row = """    registered_at_str, is_premium, premium_expires_at, premium_type = row
    
    if not premium_type:
        premium_type = 'free'
"""
    content = content.replace(old_row, new_row)
    
    # replace limit hardcode
    old_limit = """    c.execute("UPDATE users SET daily_requests = daily_requests + 1 WHERE user_id = %s AND daily_requests < 5", (user_id,))"""
    new_limit = """    
    import os
    limit = int(os.environ.get("FREE_AI_DAILY_LIMIT", "2"))
    if premium_type == 'pro':
        limit = int(os.environ.get("PRO_AI_DAILY_LIMIT", "10"))
    elif premium_type == 'ultra':
        limit = int(os.environ.get("ULTRA_AI_DAILY_LIMIT", "100"))
        
    c.execute("UPDATE users SET daily_requests = daily_requests + 1 WHERE user_id = %s AND daily_requests < %s", (user_id, limit))"""
    content = content.replace(old_limit, new_limit)

    with open("database.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("database.py patched.")

if __name__ == "__main__":
    patch_env()
    patch_database()
