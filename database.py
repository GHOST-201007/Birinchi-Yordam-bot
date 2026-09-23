import sqlite3
import datetime

DB_FILE = "users.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.OperationalError:
        pass
    return conn

def init_db():
    """Ma'lumotlar bazasini yaratish"""
    conn = get_connection()
    c = conn.cursor()
    
    # Asosiy users jadvali
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            registered_at TIMESTAMP,
            is_premium INTEGER DEFAULT 0,
            daily_requests INTEGER DEFAULT 0,
            last_request_date DATE,
            medicine_score INTEGER DEFAULT 0,
            premium_until TIMESTAMP
        )
    ''')
    
    # Dori eslatmalari jadvali (Feature 2)
    c.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            medicine_name TEXT,
            times TEXT,
            days TEXT DEFAULT 'daily',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP
        )
    ''')
    
    # Dinamik tarzda yangi ustunlarni qo'shamiz (avvalgi bazalar buzilmasligi uchun)
    new_columns = [
        ("waiting_receipt", "INTEGER DEFAULT 0"),
        # Feature 1: Tibbiy profil
        ("blood_group", "TEXT"),
        ("age", "INTEGER"),
        ("weight", "REAL"),
        ("height", "REAL"),
        ("chronic_diseases", "TEXT"),
        ("allergies", "TEXT"),
        # Feature 6: Premium muddati
        ("premium_expires_at", "TIMESTAMP"),
        # Feature 7: Kunlik tavsiyalar obunasi
        ("daily_tips_subscribed", "INTEGER DEFAULT 0"),
        # Ban tizimi
        ("is_banned", "INTEGER DEFAULT 0"),
        ("banned_until", "TIMESTAMP"),
        # Foydalanuvchi ismi va username
        ("full_name", "TEXT"),
        ("username", "TEXT"),
        # 1 ta bepul AI savol tizimi
        ("free_ai_used", "INTEGER DEFAULT 0"),
        # Dori eslatma ball tizimi
        ("medicine_score", "INTEGER DEFAULT 0"),
        ("premium_until", "TIMESTAMP"),
        # Daily bonus streak system
        ("daily_streak", "INTEGER DEFAULT 0"),
        ("last_checkin_date", "TEXT"),
        # Referral system
        ("referred_by", "INTEGER"),
        # Wheel of fortune
        ("last_spin_date", "TEXT"),
        # Super prize discount
        ("has_discount", "INTEGER DEFAULT 0"),
        # Server-side verification for spin
        ("pending_spin_prize", "INTEGER"),
    ]

    # reminders jadvalidagi yangi ustunlar (avvalgi bazalar uchun)
    reminder_columns = [
        ("days", "TEXT DEFAULT 'daily'"),
    ]
    for col_name, col_type in reminder_columns:
        try:
            c.execute(f"ALTER TABLE reminders ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Ustun allaqachon mavjud
    
    for col_name, col_type in new_columns:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Ustun allaqachon mavjud
        
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────────
# ASOSIY FOYDALANUVCHI FUNKSIYALARI
# ─────────────────────────────────────────────────────────────────

def register_user(user_id, full_name=None, username=None):
    """Foydalanuvchini bazaga qo'shish (agar yo'q bo'lsa), ismini yangilash"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not c.fetchone():
        now = datetime.datetime.now()
        c.execute(
            "INSERT INTO users (user_id, registered_at, is_premium, daily_requests, last_request_date, full_name, username) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, now.isoformat(), 0, 0, now.date().isoformat(), full_name, username)
        )
    else:
        # Ismini yangilaymiz
        if full_name or username:
            c.execute(
                "UPDATE users SET full_name=?, username=? WHERE user_id=?",
                (full_name, username, user_id)
            )
    conn.commit()
    conn.close()

def try_consume_daily_request(user_id) -> bool:
    """
    Foydalanuvchining AI limitsini atomar tarzda tekshiradi va band qiladi.
    Qaytaradi: True (ruxsat), False (limit tugagan).
    """
    register_user(user_id)
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT registered_at, is_premium, premium_expires_at FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return False
        
    registered_at_str, is_premium, premium_expires_at = row
    
    # 1. Premium foydalanuvchilar uchun muddatni tekshirish
    if is_premium:
        if premium_expires_at:
            expires = datetime.datetime.fromisoformat(premium_expires_at)
            if datetime.datetime.now() > expires:
                conn.execute("UPDATE users SET is_premium = 0 WHERE user_id = ?", (user_id,))
                conn.commit()
            else:
                conn.close()
                return True
        else:
            conn.close()
            return True  # Muddatsiz premium
            
    now = datetime.datetime.now()
    registered_at = datetime.datetime.fromisoformat(registered_at_str)
    
    # 2. Birinchi 24 soat mutlaqo bepul
    if (now - registered_at).total_seconds() < 24 * 3600:
        conn.close()
        return True
        
    # 3. Kunlik limitni atomar tekshirish va oshirish
    current_date = now.date().isoformat()
    # Avval kun o'zgargan bo'lsa, nollaymiz
    conn.execute("UPDATE users SET daily_requests = 0, last_request_date = ? WHERE user_id = ? AND last_request_date != ?", (current_date, user_id, current_date))
    
    # Endi atomar ravishda band qilamiz
    cur = conn.execute("UPDATE users SET daily_requests = daily_requests + 1 WHERE user_id = ? AND daily_requests < 5", (user_id,))
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    
    return success

def refund_daily_request(user_id):
    """Xato yuz berganda band qilingan kunlik limitni qaytarish"""
    conn = get_connection()
    conn.execute("UPDATE users SET daily_requests = daily_requests - 1 WHERE user_id = ? AND daily_requests > 0", (user_id,))
    conn.commit()
    conn.close()

def try_consume_free_ai(user_id) -> bool:
    """
    Foydalanuvchining bepul 1 ta AI savolini atomar band qiladi.
    Premium bo'lsa - har doim True.
    """
    register_user(user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT is_premium, premium_expires_at FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    is_premium, premium_expires_at = row
    
    if is_premium:
        if premium_expires_at:
            expires = datetime.datetime.fromisoformat(premium_expires_at)
            if datetime.datetime.now() <= expires:
                conn.close()
                return True
        else:
            conn.close()
            return True
            
    cur = conn.execute("UPDATE users SET free_ai_used = 1 WHERE user_id = ? AND COALESCE(free_ai_used, 0) = 0", (user_id,))
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success

def refund_free_ai(user_id):
    """Xato yuz berganda bepul savolni qaytarish"""
    conn = get_connection()
    conn.execute("UPDATE users SET free_ai_used = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def set_premium(user_id, status: int, months: int = 1):
    """Adminga foydalanuvchini Premium qilish uchun. months - necha oylik."""
    conn = get_connection()
    if status == 1:
        # Agar mavjud premium muddati bor bo'lsa, undan boshlab qo'shamiz
        row = conn.execute(
            "SELECT premium_expires_at FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        now = datetime.datetime.now()
        base = now
        if row and row[0]:
            try:
                existing = datetime.datetime.fromisoformat(row[0])
                if existing > now:
                    base = existing
            except (ValueError, TypeError):
                pass
        expires_at = (base + datetime.timedelta(days=30 * months)).isoformat()
        conn.execute(
            "UPDATE users SET is_premium = ?, premium_expires_at = ?, premium_until = ? WHERE user_id = ?",
            (status, expires_at, expires_at, user_id)
        )
    else:
        conn.execute(
            "UPDATE users SET is_premium = ?, premium_expires_at = NULL, premium_until = NULL WHERE user_id = ?",
            (status, user_id)
        )
    conn.commit()
    conn.close()

# New helper functions for medicine score and premium awarding

def add_score(user_id: int, points: int = 1) -> None:
    """Increase user's medicine_score by points."""
    conn = get_connection()
    conn.execute("UPDATE users SET medicine_score = COALESCE(medicine_score,0) + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()

def get_score(user_id: int) -> int:
    """Return current medicine_score for user."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT medicine_score FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0

def set_premium_until(user_id: int, until: datetime.datetime) -> None:
    """Set premium_until timestamp for user."""
    conn = get_connection()
    conn.execute("UPDATE users SET is_premium = 1, premium_until = ?, premium_expires_at = ? WHERE user_id = ?", (until.isoformat(), until.isoformat(), user_id))
    conn.commit()
    conn.close()

def check_and_grant_premium(user_id: int) -> None:
    """If user reached 100 points, grant 30‑day premium and reset score."""
    score = get_score(user_id)
    if score >= 100:
        until = datetime.datetime.now() + datetime.timedelta(days=30)
        set_premium_until(user_id, until)
        # Reset score after granting premium
        conn = get_connection()
        conn.execute("UPDATE users SET medicine_score = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

def get_premium_info(user_id):
    """Premium holati va muddatini olish. Agar muddat tugagan bo'lsa, avtomatik o'chiradi."""
    register_user(user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT is_premium, premium_expires_at FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return (0, None)
        
    is_premium, premium_expires_at = row
    
    if is_premium and premium_expires_at:
        expires = datetime.datetime.fromisoformat(premium_expires_at)
        if datetime.datetime.now() > expires:
            # Premium muddati tugagan — avtomatik o'chiramiz
            conn2 = get_connection()
            conn2.execute("UPDATE users SET is_premium = 0 WHERE user_id = ?", (user_id,))
            conn2.commit()
            conn2.close()
            return (0, premium_expires_at)
            
    return (is_premium, premium_expires_at)

def set_waiting_receipt(user_id, status: int):
    """Foydalanuvchining to'lov chekini kutish holatini o'zgartirish"""
    register_user(user_id)
    conn = get_connection()
    conn.execute("UPDATE users SET waiting_receipt = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

def get_waiting_receipt(user_id) -> int:
    """Foydalanuvchi to'lov chekini kutish holatini olish"""
    register_user(user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT waiting_receipt FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_all_users():
    """Barcha foydalanuvchilar ro'yxatini olish"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_all_users_info(limit=20):
    """Foydalanuvchilar ro'yxatini id, premium holati, ism va username bilan olish"""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT user_id, is_premium, registered_at, full_name, username FROM users ORDER BY registered_at DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return rows  # [(user_id, is_premium, registered_at, full_name, username), ...]

def get_all_users_info_ban(limit=20):
    """Foydalanuvchilar ro'yxatini id, ban holati, ism va username bilan olish"""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT user_id, is_banned, registered_at, full_name, username FROM users ORDER BY registered_at DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_users_count():
    """Jami foydalanuvchilar soni"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_premium_count():
    """Jami premium foydalanuvchilar soni"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_banned_count():
    """Jami banlangan foydalanuvchilar soni"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


# ─────────────────────────────────────────────────────────────────
# FEATURE 1: TIBBIY PROFIL
# ─────────────────────────────────────────────────────────────────

def save_medical_profile(user_id, blood_group=None, age=None, weight=None, height=None,
                          chronic_diseases=None, allergies=None):
    """Tibbiy profilni saqlash"""
    register_user(user_id)
    conn = get_connection()
    conn.execute(
        """UPDATE users SET blood_group=?, age=?, weight=?, height=?,
           chronic_diseases=?, allergies=? WHERE user_id=?""",
        (blood_group, age, weight, height, chronic_diseases, allergies, user_id)
    )
    conn.commit()
    conn.close()

def get_medical_profile(user_id):
    """Tibbiy profilni olish"""
    register_user(user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT blood_group, age, weight, height, chronic_diseases, allergies FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return row  # (blood_group, age, weight, height, chronic_diseases, allergies)

def update_profile_field(user_id, field: str, value):
    """Tibbiy profilning bitta maydonini yangilash"""
    allowed = ["blood_group", "age", "weight", "height", "chronic_diseases", "allergies"]
    if field not in allowed:
        return
    register_user(user_id)
    conn = get_connection()
    conn.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────────
# FEATURE 2: DORI ESLATMALARI
# ─────────────────────────────────────────────────────────────────

def add_reminder(user_id, medicine_name: str, times: str, days: str = "daily") -> int:
    """
    Yangi dori eslatmasini qo'shish.
    times = '08:00,14:00,20:00' ko'rinishida
    days  = 'daily' (har kuni) yoki 'every_other' (kunora)
    """
    conn = get_connection()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute(
        "INSERT INTO reminders (user_id, medicine_name, times, days, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (user_id, medicine_name, times, days, now)
    )
    reminder_id = c.lastrowid
    conn.commit()
    conn.close()
    return reminder_id


def count_user_active_reminders(user_id: int) -> int:
    """Foydalanuvchining hozirda nechta faol eslatmasi borligini qaytaradi."""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM reminders WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_user_reminders(user_id):
    """Foydalanuvchining barcha faol eslatmalari"""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, medicine_name, times, days FROM reminders WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows  # [(id, name, times, days), ...]

def delete_reminder(reminder_id: int, user_id: int):
    """Eslatmani o'chirish"""
    conn = get_connection()
    conn.execute("UPDATE reminders SET is_active = 0 WHERE id = ? AND user_id = ?", (reminder_id, user_id))
    conn.commit()
    conn.close()

def get_all_active_reminders():
    """Barcha faol eslatmalar (scheduler uchun)"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, user_id, medicine_name, times, days FROM reminders WHERE is_active = 1")
    rows = c.fetchall()
    conn.close()
    return rows  # [(id, user_id, medicine_name, times, days), ...]

# ─────────────────────────────────────────────────────────────────
# FEATURE 7: KUNLIK TAVSIYALAR OBUNASI
# ─────────────────────────────────────────────────────────────────

def set_daily_tips_subscription(user_id, status: int):
    """Kunlik tavsiyalar obunasini yoqish/o'chirish"""
    register_user(user_id)
    conn = get_connection()
    conn.execute("UPDATE users SET daily_tips_subscribed = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()

def get_daily_tips_subscribers():
    """Kunlik tavsiyalarga obuna bo'lgan barcha foydalanuvchilar"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE daily_tips_subscribed = 1")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_daily_tips_status(user_id) -> int:
    """Foydalanuvchining kunlik tavsiyalar obuna holati"""
    register_user(user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT daily_tips_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# ─────────────────────────────────────────────────────────────────
# BAN TIZIMI (ADMIN BUYRUQLARI UCHUN)
# ─────────────────────────────────────────────────────────────────

def ban_user(user_id: int, duration_minutes: int = None):
    """Foydalanuvchini ban qilish. duration_minutes berilsa - vaqtinchalik, aks holda - doimiy."""
    register_user(user_id)
    conn = get_connection()
    if duration_minutes:
        banned_until = (datetime.datetime.now() + datetime.timedelta(minutes=duration_minutes)).isoformat()
        conn.execute(
            "UPDATE users SET is_banned = 1, banned_until = ? WHERE user_id = ?",
            (banned_until, user_id)
        )
    else:
        conn.execute(
            "UPDATE users SET is_banned = 1, banned_until = NULL WHERE user_id = ?",
            (user_id,)
        )
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    """Foydalanuvchini bandan chiqarish."""
    register_user(user_id)
    conn = get_connection()
    conn.execute(
        "UPDATE users SET is_banned = 0, banned_until = NULL WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()

def is_user_banned(user_id: int) -> tuple:
    """
    Foydalanuvchi banlanganligini tekshirish.
    Qaytaradi: (is_banned: bool, message: str)
    """
    register_user(user_id)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT is_banned, banned_until FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return False, ""
        
    is_banned, banned_until_str = row
    if not is_banned:
        return False, ""
        
    if banned_until_str:
        try:
            banned_until = datetime.datetime.fromisoformat(banned_until_str)
            if datetime.datetime.now() > banned_until:
                # Ban muddati tugagan — avtomatik o'chiramiz
                conn2 = get_connection()
                conn2.execute("UPDATE users SET is_banned = 0, banned_until = NULL WHERE user_id = ?", (user_id,))
                conn2.commit()
                conn2.close()
                return False, ""
            else:
                formatted_time = banned_until.strftime("%d.%m.%Y %H:%M")
                return True, f"🚫 Vaqtinchalik ban muddati: {formatted_time} gacha."
        except Exception:
            return True, "🚫 Vaqtinchalik ban faol."
            
    return True, "🚫 Doimiy (muddatsiz) ban faol."


def check_and_grant_daily_bonus(user_id: int) -> tuple:
    """
    Checks if user is eligible for daily check-in bonus.
    Returns (is_granted, points_granted, current_streak)
    """
    # Uzbekistan timezone (UTC+5)
    from datetime import datetime, timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    today_dt = datetime.now(uz_tz).date()
    today_str = today_dt.isoformat()
    yesterday_str = (today_dt - timedelta(days=1)).isoformat()

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT daily_streak, last_checkin_date FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return False, 0, 0

    streak, last_date = row
    if streak is None:
        streak = 0

    if last_date == today_str:
        # Already checked in today
        conn.close()
        return False, 0, streak

    # Determine new streak and points
    if last_date == yesterday_str:
        new_streak = streak + 1
        if new_streak > 7:
            new_streak = 1
    else:
        new_streak = 1

    # Points calculation
    if new_streak == 1:
        points = 1
    elif new_streak == 2:
        points = 2
    elif new_streak == 3:
        points = 3
    elif new_streak == 7:
        points = 20
    else:
        points = 3 # days 4, 5, 6 give +3 points

    # Update database
    c.execute(
        "UPDATE users SET daily_streak = ?, last_checkin_date = ?, medicine_score = COALESCE(medicine_score, 0) + ? WHERE user_id = ?",
        (new_streak, today_str, points, user_id)
    )
    conn.commit()
    conn.close()

    # Also automatically check if user qualifies for Premium upgrade
    check_and_grant_premium(user_id)

    return True, points, new_streak


def handle_referral(new_user_id: int, referrer_id: int) -> tuple:
    """
    Connects a referred user to their referrer.
    Returns (success, points_given, bonus_given)
    """
    if new_user_id == referrer_id:
        return False, 0, False

    conn = get_connection()
    c = conn.cursor()

    # Check if referrer exists
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
    if not c.fetchone():
        conn.close()
        return False, 0, False

    # Check if new_user exists and if they already have a referrer
    c.execute("SELECT registered_at, referred_by FROM users WHERE user_id = ?", (new_user_id,))
    row = c.fetchone()

    is_new = False
    if not row:
        # Not registered yet
        now = datetime.datetime.now()
        c.execute(
            "INSERT INTO users (user_id, registered_at, is_premium, daily_requests, last_request_date, referred_by) VALUES (?, ?, ?, ?, ?, ?)",
            (new_user_id, now.isoformat(), 0, 0, now.date().isoformat(), referrer_id)
        )
        is_new = True
    else:
        reg_time_str, ref_by = row
        if ref_by is None:
            # Check if registered very recently (e.g. within 2 minutes)
            try:
                reg_time = datetime.datetime.fromisoformat(reg_time_str)
                if (datetime.datetime.now() - reg_time).total_seconds() < 120:
                    c.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, new_user_id))
                    is_new = True
            except Exception:
                pass

    if not is_new:
        conn.close()
        return False, 0, False

    # Give referrer +10 points
    c.execute("UPDATE users SET medicine_score = COALESCE(medicine_score, 0) + 10 WHERE user_id = ?", (referrer_id,))
    
    # Check total friends referred by this referrer
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (referrer_id,))
    count = c.fetchone()[0]

    bonus_given = False
    points_given = 10

    if count == 5:
        # Give extra +50 points bonus
        c.execute("UPDATE users SET medicine_score = COALESCE(medicine_score, 0) + 50 WHERE user_id = ?", (referrer_id,))
        points_given += 50
        bonus_given = True

    conn.commit()
    conn.close()

    # Automatically check if referrer qualifies for Premium upgrade
    check_and_grant_premium(referrer_id)

    return True, points_given, bonus_given


def check_and_grant_spin_bonus(user_id: int, points: int) -> tuple:
    """
    Checks if user is eligible for spin bonus.
    If yes, awards points and updates last_spin_date.
    Returns (success, message)
    """
    # Uzbekistan timezone (UTC+5)
    from datetime import datetime, timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    now = datetime.now(uz_tz)
    now_str = now.isoformat()

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT last_spin_date, pending_spin_prize FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return False, "Foydalanuvchi topilmadi!"

    last_spin = row[0]
    pending_prize = row[1]

    if last_spin:
        try:
            # Parse full ISO timestamp
            last_spin_dt = datetime.fromisoformat(last_spin)
            if last_spin_dt.tzinfo is None:
                last_spin_dt = last_spin_dt.replace(tzinfo=uz_tz)
            
            # Check if 24 hours have passed
            diff = now - last_spin_dt
            if diff.total_seconds() < 24 * 3600:
                conn.close()
                remaining_seconds = int(24 * 3600 - diff.total_seconds())
                hours = remaining_seconds // 3600
                minutes = (remaining_seconds % 3600) // 60
                seconds = remaining_seconds % 60
                return False, f"Keyingi urinishgacha {hours:02d}:{minutes:02d}:{seconds:02d} vaqt qoldi. 🕒"
        except ValueError:
            # Fallback to old YYYY-MM-DD format
            if last_spin == now.date().isoformat():
                conn.close()
                return False, "Siz bugun barabanni aylantirib bo'ldingiz! Keyingi urinish ertaga. 🕒"

    if pending_prize is None:
        conn.close()
        return False, "Sizda tasdiqlanmagan yutuq topilmadi yoki u allaqachon hisobingizga qo'shilgan! 🕒"

    points = pending_prize

    if points == 0:
        # Super Prize: discount
        c.execute(
            "UPDATE users SET last_spin_date = ?, has_discount = 1, pending_spin_prize = NULL WHERE user_id = ?",
            (now_str, user_id)
        )
        msg = (
            "🎉 <b>Tabriklaymiz! Omad barabanidan SUPER PRIZ yutib oldingiz!</b> 🏆\n\n"
            "🎁 Siz 1 oylik Premium obunani 30 Stars o'rniga <b>atigi 20 Stars (Telegram yulduzi)</b> evaziga xarid qilish imkoniyatiga ega bo'ldingiz!\n\n"
            "Chegirmali Premium obunani faollashtirish uchun quyidagi buyruqni bosing:\n"
            "➡️ /premium (yoki quyidagi tugmani bosing)"
        )
    else:
        # Standard points
        c.execute(
            "UPDATE users SET last_spin_date = ?, medicine_score = COALESCE(medicine_score, 0) + ?, pending_spin_prize = NULL WHERE user_id = ?",
            (now_str, points, user_id)
        )
        msg = f"Tabriklaymiz! Siz Omad barabanidan <b>+{points} ball</b> yutib oldingiz! 🎉"

    conn.commit()
    conn.close()

    # Automatically check if user qualifies for Premium upgrade
    if points > 0:
        check_and_grant_premium(user_id)

    return True, msg


def has_discount(user_id: int) -> bool:
    """Checks if the user has an active super prize discount"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT has_discount FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        val = bool(row[0]) if row else False
    except Exception:
        val = False
    conn.close()
    return val


def consume_discount(user_id: int) -> None:
    """Consumes the super prize discount"""
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET has_discount = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        import logging
        logging.error(f"Error consuming discount: {e}")
    conn.close()
def get_referral_count(user_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def generate_or_get_spin_prize(user_id: int):
    """
    Spins the wheel on the server side.
    Returns the prize points (0 for super prize) if eligible, or None if cooldown is active.
    """
    import random
    from datetime import datetime, timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    now = datetime.now(uz_tz)

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT last_spin_date, pending_spin_prize FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return None

    last_spin = row[0]
    pending_prize = row[1]

    # Check cooldown
    if last_spin:
        try:
            last_spin_dt = datetime.fromisoformat(last_spin)
            if last_spin_dt.tzinfo is None:
                last_spin_dt = last_spin_dt.replace(tzinfo=uz_tz)
            
            diff = now - last_spin_dt
            if diff.total_seconds() < 24 * 3600:
                conn.close()
                return None  # Cooldown active
        except ValueError:
            if last_spin == now.date().isoformat():
                conn.close()
                return None

    # If we already generated a prize but they haven't claimed it yet
    if pending_prize is not None:
        conn.close()
        return pending_prize

    # Generate new prize
    # Segments based on app.js: 1, 3, 5, 10, 20, 50, Super (0)
    r = random.random()
    if r < 0.40: prize = 1
    elif r < 0.70: prize = 3
    elif r < 0.85: prize = 5
    elif r < 0.95: prize = 10
    elif r < 0.98: prize = 20
    elif r < 0.99: prize = 50
    else: prize = 0

    c.execute("UPDATE users SET pending_spin_prize = ? WHERE user_id = ?", (prize, user_id))
    conn.commit()
    conn.close()
    return prize
def get_daily_bonus_info(user_id: int) -> dict:
    """
    Returns information about the user's daily bonus status:
    - streak: Current active streak
    - is_claimed_today: True if they already claimed today's bonus
    """
    from datetime import datetime, timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    today_dt = datetime.now(uz_tz).date()
    today_str = today_dt.isoformat()
    yesterday_str = (today_dt - timedelta(days=1)).isoformat()

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT daily_streak, last_checkin_date FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"streak": 1, "is_claimed_today": False}

    streak, last_date = row
    if streak is None:
        streak = 0

    is_claimed_today = (last_date == today_str)

    if last_date == yesterday_str or last_date == today_str:
        # Streak is active
        current_streak = streak if last_date == today_str else streak + 1
        if current_streak > 7:
            current_streak = 1
    else:
        # Streak broken or never started
        current_streak = 1
        if last_date == today_str: # Just in case
             current_streak = streak

    return {
        "streak": current_streak,
        "is_claimed_today": is_claimed_today
    }
