import psycopg2
import psycopg2.extras
import datetime
import os
import logging
import threading
import time as _time
from collections import OrderedDict
from contextlib import contextmanager
from dotenv import load_dotenv
from psycopg2.pool import ThreadedConnectionPool

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_uz_now():
    from datetime import timezone, timedelta
    return datetime.datetime.now(timezone(timedelta(hours=5)))


def _to_uz_datetime(value):
    """Bazadan kelgan vaqtni Toshkent timezone'iga moslaydi."""
    if not isinstance(value, datetime.datetime):
        value = datetime.datetime.fromisoformat(str(value))

    uz_tz = datetime.timezone(datetime.timedelta(hours=5))

    if value.tzinfo is None:
        return value.replace(tzinfo=uz_tz)

    return value.astimezone(uz_tz)

# Pool initializatsiyasi
db_pool = None

class PooledConnectionWrapper:
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._lock = threading.Lock()
        self._broken = False
        
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)
        
    def commit(self):
        self._conn.commit()
        
    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            # Rollback bajarilmadi -> ulanish holati noaniq; poolga qaytarilmaydi, yopiladi
            self._broken = True
            raise
        
    def close(self):
        # Bir martalik, thread-safe ajratib olish: ulanish poolga faqat bir marta qaytadi
        with self._lock:
            conn = self._conn
            self._conn = None
            broken = self._broken
        if conn is None:
            return
        try:
            if broken:
                self._pool.putconn(conn, close=True)
            else:
                self._pool.putconn(conn)
        except Exception:
            logging.error("Ulanishni poolga qaytarishda xato; ulanish yopiladi", exc_info=True)
            try:
                self._pool.putconn(conn, close=True)
            except Exception:
                logging.error("Ulanishni yopib tashlashda xato", exc_info=True)
            raise
            
    def __getattr__(self, name):
        return getattr(self._conn, name)

def get_connection():
    """PostgreSQL bazaga ulanish. Pooling orqali ishlaydi."""
    global db_pool
    if db_pool is None:
        db_pool = ThreadedConnectionPool(minconn=1, maxconn=50, dsn=DATABASE_URL)
    
    conn = db_pool.getconn()
    conn.autocommit = False
    return PooledConnectionWrapper(conn, db_pool)

def init_db():
    """Ma'lumotlar bazasini yaratish"""
    with _managed_cursor() as (conn, c):

        # Manual receipt table – stores a unique token per admin‑approved receipt
        c.execute('''
            CREATE TABLE IF NOT EXISTS manual_receipts (
                receipt_token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMPTZ
            )
        ''')


        # Asosiy users jadvali
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                registered_at TIMESTAMP,
                is_premium INTEGER DEFAULT 0,
                premium_type TEXT DEFAULT 'free',
                daily_requests INTEGER DEFAULT 0,
                last_request_date TEXT,
                medicine_score INTEGER DEFAULT 0,
                premium_until TIMESTAMP,
                waiting_receipt INTEGER DEFAULT 0,
                blood_group TEXT,
                age INTEGER,
                weight REAL,
                height REAL,
                chronic_diseases TEXT,
                allergies TEXT,
                premium_expires_at TIMESTAMP,
                daily_tips_subscribed INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                banned_until TIMESTAMP,
                full_name TEXT,
                username TEXT,
                free_ai_used INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_checkin_date TEXT,
                referred_by BIGINT,
                last_spin_date TEXT,
                has_discount INTEGER DEFAULT 0,
                pending_spin_prize INTEGER
            )
        ''')

        # To'lovlar tarixi va qayta ishlov berishdan himoya jadvali
        c.execute('''
            CREATE TABLE IF NOT EXISTS payment_transactions (
                id SERIAL PRIMARY KEY,
                charge_id TEXT UNIQUE,
                user_id BIGINT,
                product_id TEXT,
                stars_amount INTEGER,
                premium_type TEXT,
                duration_days INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration for existing DBs lacking premium_type column
        try:
            c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_type TEXT DEFAULT 'free'")
        except Exception:
            pass

        # Migration for existing DBs lacking unique constraint on charge_id.
        # Eski jadvaldagi dublikatlar avtomatik o'chirilmaydi; indeks yaratish xatosi jim yutilmaydi.
        try:
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_transactions_charge_id ON payment_transactions (charge_id)")
        except Exception as e:
            logging.critical(
                f"CRITICAL MIGRATION ERROR: idx_payment_transactions_charge_id UNIQUE indeksini yaratib bo'lmadi: {e}. "
                "Ehtimol payment_transactions jadvalida dublikat charge_id yozuvlari mavjud. "
                "Xavfsizlik uchun dublikatlar avtomatik o'chirilmaydi — jadvalni qo'lda tekshiring!"
            )
            raise

        # Dori eslatmalari jadvali (Feature 2)
        c.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                medicine_name TEXT,
                times TEXT,
                days TEXT DEFAULT 'daily',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP
            )
        ''')

        # Daily Engagement jadvallari
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_interests (
                user_id BIGINT,
                interest TEXT,
                weight INTEGER DEFAULT 1,
                updated_at TIMESTAMP,
                PRIMARY KEY (user_id, interest)
            )
        ''')
    
        c.execute('''
            CREATE TABLE IF NOT EXISTS engagement_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                event_type TEXT, -- '08:00', '10:10', 'premium_checkin'
                event_date TEXT, -- 'YYYY-MM-DD'
                question TEXT,
                category TEXT,
                sent_at TIMESTAMP,
                answered_at TIMESTAMP,
                answer_text TEXT,
                bot_reply TEXT,
                UNIQUE (user_id, event_type, event_date)
            )
        ''')
        # Migratsiya: engagement xabarining Telegram message_id si (P0-2 —
        # javob faqat shu xabarga reply bo'lsa qabul qilinadi)
        c.execute("ALTER TABLE engagement_logs ADD COLUMN IF NOT EXISTS message_id BIGINT")

        conn.commit()


# ─────────────────────────────────────────────────────────────────
# ASOSIY FOYDALANUVCHI FUNKSIYALARI
# ─────────────────────────────────────────────────────────────────

def register_user(user_id, full_name=None, username=None):
    """Foydalanuvchini bazaga qo'shish (agar yo'q bo'lsa), ismini yangilash"""
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        if not c.fetchone():
            now = get_uz_now()
            c.execute(
                "INSERT INTO users (user_id, registered_at, is_premium, daily_requests, last_request_date, full_name, username) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, now.isoformat(), 0, 0, now.date().isoformat(), full_name, username)
            )
        else:
            # Ismini yangilaymiz
            if full_name or username:
                c.execute(
                    "UPDATE users SET full_name=%s, username=%s WHERE user_id=%s",
                    (full_name, username, user_id)
                )
        conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        _safe_close(c, conn)

# ---------------------------------------------------------------------------
# Manual receipt helpers – token based admin approval
# ---------------------------------------------------------------------------
import uuid

def create_manual_receipt(user_id: int, token: str) -> bool:
    """Insert a pending receipt row. Returns True only if the row was created.
    Uses the primary‑key on receipt_token to guarantee uniqueness."""
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO manual_receipts (receipt_token, user_id) VALUES (%s, %s)",
            (token, user_id)
        )
        conn.commit()
        success = True
    except Exception as e:
        # Duplicate token or other DB error – treat as failure
        logging.warning(f"Failed to create manual receipt for token {token}: {e}")
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        success = False
    finally:
        _safe_close(c, conn)
    return success



def reject_receipt(user_id: int, token: str) -> bool:
    """Atomically reject a pending receipt. No premium changes are made."""
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "SELECT status, user_id FROM manual_receipts WHERE receipt_token = %s FOR UPDATE",
            (token,)
        )
        rec = c.fetchone()
        if not rec or rec[0] != 'pending' or rec[1] != user_id:
            conn.rollback()
            return False

        c.execute(
            "UPDATE manual_receipts SET status = 'rejected' WHERE receipt_token = %s",
            (token,)
        )
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"reject_receipt error for token {token}: {e}")
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        _safe_close(c, conn)

def approve_receipt_and_grant(user_id: int, token: str) -> bool:
    """Atomically approve a pending manual receipt and grant premium.
    Returns True on success, False if receipt not pending or DB error.
    """
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        # Lock the receipt row
        c.execute("SELECT status, user_id FROM manual_receipts WHERE receipt_token = %s FOR UPDATE", (token,))
        row = c.fetchone()
        if not row or row[0] != 'pending' or row[1] != user_id:
            conn.rollback()
            return False
        # Mark as approved
        c.execute("UPDATE manual_receipts SET status = 'approved' WHERE receipt_token = %s", (token,))
        # Grant premium – 30 days of 'pro' tier, SAME transaction (shared cursor)
        grant_premium_days(user_id, 30, premium_type='pro', _cursor=c)
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"approve_receipt_and_grant error for token {token}: {e}", exc_info=True)
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    finally:
        _safe_close(c, conn)



def try_consume_daily_request(user_id) -> bool:
    """
    Foydalanuvchining AI limitsini atomar tarzda tekshiradi va band qiladi.
    Limitlar: FREE = 5, PRO = 15, ULTRA = 100
    Qaytaradi: True (ruxsat), False (limit tugagan).
    """
    register_user(user_id)

    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT registered_at, is_premium, premium_expires_at, premium_type FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()

        if not row:
            return False

        registered_at_str, is_premium, premium_expires_at, premium_type = row
        if not premium_type:
            premium_type = "free"

        # 1. Premium foydalanuvchilar uchun muddatni tekshirish
        if is_premium:
            if premium_expires_at:
                expires = _to_uz_datetime(premium_expires_at)
                if get_uz_now() > expires:
                    c.execute("UPDATE users SET is_premium = 0, premium_type = 'free' WHERE user_id = %s", (user_id,))
                    conn.commit()
                    is_premium = 0
                    premium_type = "free"
            else:
                # Muddatsiz premium (masalan admin berganda) -> Ultra deb hisoblaymiz
                premium_type = premium_type if premium_type != "free" else "ultra"

        now = get_uz_now()
        registered_at = _to_uz_datetime(registered_at_str)

        # 2. (O'chirildi) Avvalgi cheksiz 24-soat bepul mantiq kreditni tugatardi.
        # Endi faqat 1 ta bepul AI try_consume_free_ai() orqali beriladi.

        # Limitni aniqlaymiz: ULTRA (100), PLUS (30), PRO (15), FREE (1)
        free_limit = int(os.environ.get("FREE_AI_DAILY_LIMIT", "1"))
        pro_limit = int(os.environ.get("PRO_AI_DAILY_LIMIT", "15"))
        plus_limit = int(os.environ.get("PLUS_AI_DAILY_LIMIT", "30"))
        ultra_limit = int(os.environ.get("ULTRA_AI_DAILY_LIMIT", "100"))

        if premium_type == "ultra":
            max_requests = ultra_limit
        elif premium_type == "plus":
            max_requests = plus_limit
        elif premium_type == "pro":
            max_requests = pro_limit
        else:
            max_requests = free_limit

        # 3. Kunlik limitni atomar tekshirish va oshirish
        current_date = now.date().isoformat()
        # Avval kun o'zgargan bo'lsa, nollaymiz
        c.execute("UPDATE users SET daily_requests = 0, last_request_date = %s WHERE user_id = %s AND (last_request_date != %s OR last_request_date IS NULL)", (current_date, user_id, current_date))

        # Endi atomar ravishda band qilamiz
        c.execute("UPDATE users SET daily_requests = daily_requests + 1 WHERE user_id = %s AND daily_requests < %s", (user_id, max_requests))
        success = c.rowcount > 0
        conn.commit()

        return success
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        _safe_close(c, conn)

def refund_daily_request(user_id):
    """Xato yuz berganda band qilingan kunlik limitni qaytarish
    Refund is applied only if the request was made today.
    """
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        # Verify the request was recorded for today
        c.execute("SELECT last_request_date FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
        today_str = get_uz_now().date().isoformat()
        if row and row[0] == today_str:
            c.execute("UPDATE users SET daily_requests = daily_requests - 1 WHERE user_id = %s AND daily_requests > 0", (user_id,))
            conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        # Always close safely
        _safe_close(c, conn)

def try_consume_free_ai(user_id) -> bool:
    """
    Foydalanuvchining bepul 1 ta AI savolini atomar band qiladi.
    Faol Premium foydalanuvchilar o'zlarining kunlik tarif limitidan
    (try_consume_daily_request) foydalanishi uchun bu yerda False qaytariladi.
    """
    register_user(user_id)
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT is_premium, premium_expires_at FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
        if not row:
            return False
        is_premium, premium_expires_at = row

        if is_premium:
            if premium_expires_at:
                expires = _to_uz_datetime(premium_expires_at)
                if get_uz_now() <= expires:
                    return False
            else:
                return False

        c.execute("UPDATE users SET free_ai_used = 1 WHERE user_id = %s AND COALESCE(free_ai_used, 0) = 0", (user_id,))
        success = c.rowcount > 0
        conn.commit()
        return success
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        _safe_close(c, conn)

def refund_free_ai(user_id):
    """Xato yuz berganda bepul savolni qaytarish"""
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET free_ai_used = 0 WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        _safe_close(c, conn)

def set_premium(user_id, status: int, months: int = 1):
    """Adminga foydalanuvchini Premium qilish uchun. months - necha oylik."""
    with _managed_cursor() as (conn, c):
        if status == 1:
            # Agar mavjud premium muddati bor bo'lsa, undan boshlab qo'shamiz
            c.execute(
                "SELECT premium_expires_at FROM users WHERE user_id = %s", (user_id,)
            )
            row = c.fetchone()
            now = get_uz_now()
            base = now
            if row and row[0]:
                try:
                    existing = _to_uz_datetime(row[0])
                    if existing > now:
                        base = existing
                except (ValueError, TypeError):
                    pass
            expires_at = (base + datetime.timedelta(days=30 * months)).isoformat()
            c.execute(
                "UPDATE users SET is_premium = %s, premium_type = 'pro', premium_expires_at = %s, premium_until = %s WHERE user_id = %s",
                (status, expires_at, expires_at, user_id)
            )
        else:
            c.execute(
                "UPDATE users SET is_premium = %s, premium_type = 'free', premium_expires_at = NULL, premium_until = NULL WHERE user_id = %s",
                (status, user_id)
            )
        conn.commit()

# New helper functions for medicine score and premium awarding

def add_score(user_id: int, points: int = 1) -> None:
    """Increase user's medicine_score by points."""
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE users SET medicine_score = COALESCE(medicine_score,0) + %s WHERE user_id = %s", (points, user_id))
        conn.commit()

def get_score(user_id: int) -> int:
    """Return current medicine_score for user."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT medicine_score FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    return row[0] if row and row[0] is not None else 0

def set_premium_until(user_id: int, until: datetime.datetime, premium_type: str = "pro") -> None:
    """Set premium_until timestamp and premium_type for user."""
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE users SET is_premium = 1, premium_type = %s, premium_until = %s, premium_expires_at = %s WHERE user_id = %s", (premium_type, until.isoformat(), until.isoformat(), user_id))
        conn.commit()

_VALID_PREMIUM_TYPES = ("pro", "plus", "ultra")


def _validate_premium_grant_args(premium_type: str, days: int) -> None:
    """Premium berish parametrlarini DB tranzaksiyasi boshlanishidan oldin tekshiradi."""
    if not isinstance(premium_type, str) or premium_type not in _VALID_PREMIUM_TYPES:
        raise ValueError(
            f"Noto'g'ri premium_type: {premium_type!r}. Faqat {_VALID_PREMIUM_TYPES} qabul qilinadi."
        )
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError(f"days musbat butun son bo'lishi shart, kelgan qiymat: {days!r}")


def grant_premium_days(user_id: int, days: int, premium_type: str = "pro", _cursor=None) -> datetime.datetime:
    """Grant additional premium days to user, stacking if already active with higher/equal tier.
    If _cursor is given, the grant runs inside the caller's transaction (no commit/close here)."""
    _validate_premium_grant_args(premium_type, days)
    conn = None
    c = None
    shared = _cursor is not None
    try:
        if shared:
            c = _cursor
            c.execute("SELECT premium_expires_at, premium_type FROM users WHERE user_id = %s", (user_id,))
        else:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT premium_expires_at, premium_type FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
        row = c.fetchone()
        now = get_uz_now()
        base = now
        current_type = "free"

        if row and row[0]:
            try:
                existing = _to_uz_datetime(row[0])
                if existing > now:
                    base = existing
                    current_type = row[1] or "pro"
            except (ValueError, TypeError):
                pass

        # Tier ranking: ultra (3) > plus (2) > pro (1) > free (0)
        tier_ranks = {"free": 0, "pro": 1, "plus": 2, "ultra": 3}
        new_rank = tier_ranks.get(premium_type, 1)
        cur_rank = tier_ranks.get(current_type, 0)

        final_type = premium_type if new_rank >= cur_rank else current_type
        until = base + datetime.timedelta(days=days)

        c.execute(
            "UPDATE users SET is_premium = 1, premium_type = %s, premium_until = %s, premium_expires_at = %s WHERE user_id = %s",
            (final_type, until.isoformat(), until.isoformat(), user_id)
        )
        if not shared:
            conn.commit()
        return until
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if not shared:
            _safe_close(c, conn)

_PG_UNIQUE_VIOLATION = "23505"  # PostgreSQL SQLSTATE: unique_violation


def _is_unique_violation(exc: Exception) -> bool:
    """psycopg2 UniqueViolation (SQLSTATE 23505) ekanini aniqlaydi.
    psycopg2.errors import qilinmaydi — pgcode orqali tekshiriladi (stub testlar bilan ham mos)."""
    return getattr(exc, "pgcode", None) == _PG_UNIQUE_VIOLATION


def _safe_close(c, conn) -> None:
    try:
        if c is not None:
            c.close()
    except Exception:
        logging.warning("Cursor yopishda xato", exc_info=True)
    try:
        if conn is not None:
            conn.close()
    except Exception:
        logging.warning("Ulanishni yopishda xato", exc_info=True)


def record_payment_transaction(charge_id: str, user_id: int, product_id: str, stars_amount: int, premium_type: str, duration_days: int) -> bool:
    """
    To'lov yozuvini saqlaydi.
    Returns True — yozildi; False — FAQAT charge_id unique constraint buzilganda (takroriy to'lov).
    Boshqa DB xatolari rollback qilinib yuqoriga uzatiladi (dublikat deb yutilmaydi).
    Bo'sh charge_id -> ValueError (avval True qaytarilardi va dublikat himoyasi chetlab o'tilardi;
    hozirgi yagona chaqiruvchi — legacy oqim — har doim bo'sh bo'lmagan ID beradi).
    """
    if not charge_id:
        raise ValueError("charge_id bo'sh bo'lishi mumkin emas")
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO payment_transactions (charge_id, user_id, product_id, stars_amount, premium_type, duration_days) VALUES (%s, %s, %s, %s, %s, %s)",
            (charge_id, user_id, product_id, stars_amount, premium_type, duration_days)
        )
        conn.commit()
        return True
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                logging.warning("Rollback xatosi", exc_info=True)
        if _is_unique_violation(e):
            logging.warning(f"Duplicate payment attempt for charge_id {charge_id}")
            return False
        logging.error(f"Payment record DB error for charge_id {charge_id}: {e}")
        raise
    finally:
        _safe_close(c, conn)


def process_paid_premium(charge_id: str, user_id: int, product_id: str, stars_amount: int,
                         premium_type: str, days: int):
    """
    To'lov yozuvi va Premium berishni BITTA tranzaksiyada bajaradi (idempotent).
    Returns (True, until)  — yangi to'lov, Premium berildi va commit qilindi.
            (False, None)  — charge_id allaqachon mavjud (Premium qayta uzaytirilmaydi).
    Har qanday xatoda butun tranzaksiya rollback qilinadi va xato yuqoriga uzatiladi,
    shuning uchun to'lov yozuvi Premiumsiz qolib ketmaydi va qayta urinish xavfsiz.
    Muddat hisoblash grant_premium_days() bilan bir xil qoidada (stacking + tier).
    """
    if not charge_id:
        raise ValueError("charge_id bo'sh bo'lishi mumkin emas")
    _validate_premium_grant_args(premium_type, days)
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        # Parallel bir xil charge_id: ikkinchi INSERT birinchisi tugaguncha kutadi, keyin DO NOTHING.
        c.execute(
            "INSERT INTO payment_transactions (charge_id, user_id, product_id, stars_amount, premium_type, duration_days) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (charge_id) DO NOTHING RETURNING id",
            (charge_id, user_id, product_id, stars_amount, premium_type, days)
        )
        if c.fetchone() is None:
            conn.rollback()
            return False, None

        now = get_uz_now()
        # Foydalanuvchi qatori bo'lmasa yaratamiz (to'lov Premiumsiz qolmasligi uchun)
        c.execute(
            "INSERT INTO users (user_id, registered_at) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
            (user_id, now.isoformat())
        )
        c.execute("SELECT premium_expires_at, premium_type FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
        row = c.fetchone()
        base = now
        current_type = "free"
        if row and row[0]:
            try:
                existing = _to_uz_datetime(row[0])
                if existing > now:
                    base = existing
                    current_type = row[1] or "pro"
            except (ValueError, TypeError):
                pass

        tier_ranks = {"free": 0, "pro": 1, "plus": 2, "ultra": 3}
        final_type = premium_type if tier_ranks.get(premium_type, 1) >= tier_ranks.get(current_type, 0) else current_type
        until = base + datetime.timedelta(days=days)

        c.execute(
            "UPDATE users SET is_premium = 1, premium_type = %s, premium_until = %s, premium_expires_at = %s WHERE user_id = %s",
            (final_type, until.isoformat(), until.isoformat(), user_id)
        )
        if c.rowcount != 1:
            raise RuntimeError(f"Premium UPDATE kutilmagan rowcount={c.rowcount} user_id={user_id}")
        conn.commit()
        return True, until
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                logging.warning("Rollback xatosi", exc_info=True)
        raise
    finally:
        _safe_close(c, conn)

def check_and_grant_premium(user_id: int) -> bool:
    """If user has at least 100 points, grant 3-day premium and subtract 100 score atomically."""
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET medicine_score = medicine_score - 100 WHERE user_id = %s AND COALESCE(medicine_score, 0) >= 100",
            (user_id,)
        )
        if c.rowcount != 1:
            conn.rollback()
            return False

        now = get_uz_now()
        c.execute("SELECT premium_expires_at, premium_type FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
        row = c.fetchone()
        base = now
        current_type = "free"
        if row and row[0]:
            try:
                existing = _to_uz_datetime(row[0])
                if existing > now:
                    base = existing
                    current_type = row[1] or "pro"
            except (ValueError, TypeError):
                pass

        tier_ranks = {"free": 0, "pro": 1, "plus": 2, "ultra": 3}
        final_type = "pro" if tier_ranks.get("pro", 1) >= tier_ranks.get(current_type, 0) else current_type
        until = base + datetime.timedelta(days=3)

        c.execute(
            "UPDATE users SET is_premium = 1, premium_type = %s, premium_until = %s, premium_expires_at = %s WHERE user_id = %s",
            (final_type, until.isoformat(), until.isoformat(), user_id)
        )
        conn.commit()
        return True
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        _safe_close(c, conn)

def get_premium_info(user_id):
    """Premium holati, muddati va turini olish. Agar muddat tugagan bo'lsa, avtomatik o'chiradi."""
    register_user(user_id)
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT is_premium, premium_expires_at, premium_type FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    finally:
        _safe_close(c, conn)

    if not row:
        return (0, None, "free")

    is_premium, premium_expires_at, premium_type = row
    if not premium_type:
        premium_type = "free"

    if is_premium and premium_expires_at:
        expires = _to_uz_datetime(premium_expires_at)
        if get_uz_now() > expires:
            # Premium muddati tugagan — avtomatik o'chiramiz
            conn2 = None
            c2 = None
            try:
                conn2 = get_connection()
                c2 = conn2.cursor()
                c2.execute("UPDATE users SET is_premium = 0, premium_type = 'free' WHERE user_id = %s", (user_id,))
                conn2.commit()
            except Exception:
                if conn2 is not None:
                    try:
                        conn2.rollback()
                    except Exception:
                        pass
                logging.warning(f"Premium muddatini yangilashda DB xatosi: user_id={user_id}", exc_info=True)
            finally:
                _safe_close(c2, conn2)
            return (0, str(premium_expires_at), "free")

    return (is_premium, str(premium_expires_at) if premium_expires_at else None, premium_type if is_premium else "free")

def get_user_info(user_id: int) -> dict:
    """Foydalanuvchi ma'lumotlarini (premium holati, turi va muddati) lug'at shaklida qaytaradi."""
    is_premium, expires, premium_type = get_premium_info(user_id)
    return {
        "user_id": user_id,
        "is_premium": is_premium,
        "premium_type": premium_type,
        "premium_expires_at": expires,
    }

def set_waiting_receipt(user_id, status: int):
    """Foydalanuvchining to'lov chekini kutish holatini o'zgartirish"""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE users SET waiting_receipt = %s WHERE user_id = %s", (status, user_id))
        conn.commit()

def get_waiting_receipt(user_id) -> int:
    """Foydalanuvchi to'lov chekini kutish holatini olish"""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute("SELECT waiting_receipt FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    return row[0] if row else 0

def is_waiting_receipt(user_id) -> bool:
    """bot.py (receipt_timeout) chaqiradigan yordamchi: foydalanuvchi chek kutish holatidami."""
    return bool(get_waiting_receipt(user_id))

def get_all_users():
    """Barcha foydalanuvchilar ro'yxatini olish"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT user_id FROM users")
        rows = c.fetchall()
    return [r[0] for r in rows]

def get_all_users_info(limit=20):
    """Foydalanuvchilar ro'yxatini id, premium holati, ism va username bilan olish"""
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT user_id, is_premium, registered_at, full_name, username FROM users ORDER BY registered_at DESC LIMIT %s",
            (limit,)
        )
        rows = c.fetchall()
    return rows  # [(user_id, is_premium, registered_at, full_name, username), ...]

def get_all_users_info_ban(limit=20):
    """Foydalanuvchilar ro'yxatini id, ban holati, ism va username bilan olish"""
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT user_id, is_banned, registered_at, full_name, username FROM users ORDER BY registered_at DESC LIMIT %s",
            (limit,)
        )
        rows = c.fetchall()
    return rows


def get_users_count():
    """Jami foydalanuvchilar soni"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT COUNT(*) FROM users")
        row = c.fetchone()
    return row[0] if row else 0

def get_premium_count():
    """Jami premium foydalanuvchilar soni"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
        row = c.fetchone()
    return row[0] if row else 0

def get_banned_count():
    """Jami banlangan foydalanuvchilar soni"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        row = c.fetchone()
    return row[0] if row else 0


# ─────────────────────────────────────────────────────────────────
# FEATURE 1: TIBBIY PROFIL
# ─────────────────────────────────────────────────────────────────

def save_medical_profile(user_id, blood_group=None, age=None, weight=None, height=None,
                          chronic_diseases=None, allergies=None):
    """Tibbiy profilni saqlash"""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute(
            """UPDATE users SET blood_group=%s, age=%s, weight=%s, height=%s,
               chronic_diseases=%s, allergies=%s WHERE user_id=%s""",
            (blood_group, age, weight, height, chronic_diseases, allergies, user_id)
        )
        conn.commit()

def get_medical_profile(user_id):
    """Tibbiy profilni olish"""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT blood_group, age, weight, height, chronic_diseases, allergies FROM users WHERE user_id = %s",
            (user_id,)
        )
        row = c.fetchone()
    return row  # (blood_group, age, weight, height, chronic_diseases, allergies)

def update_profile_field(user_id, field: str, value):
    """Tibbiy profilning bitta maydonini yangilash"""
    allowed = ["blood_group", "age", "weight", "height", "chronic_diseases", "allergies"]
    if field not in allowed:
        return
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute(f"UPDATE users SET {field} = %s WHERE user_id = %s", (value, user_id))
        conn.commit()

# ─────────────────────────────────────────────────────────────────
# FEATURE 2: DORI ESLATMALARI
# ─────────────────────────────────────────────────────────────────

def add_reminder(user_id, medicine_name: str, times: str, days: str = "daily") -> int:
    """
    Yangi dori eslatmasini qo'shish.
    times = '08:00,14:00,20:00' ko'rinishida
    days  = 'daily' (har kuni) yoki 'every_other' (kunora)
    """
    with _managed_cursor() as (conn, c):
        now = get_uz_now().isoformat()
        c.execute(
            "INSERT INTO reminders (user_id, medicine_name, times, days, is_active, created_at) VALUES (%s, %s, %s, %s, 1, %s) RETURNING id",
            (user_id, medicine_name, times, days, now)
        )
        reminder_id = c.fetchone()[0]
        conn.commit()
    return reminder_id


def count_user_active_reminders(user_id: int) -> int:
    """Foydalanuvchining hozirda nechta faol eslatmasi borligini qaytaradi."""
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT COUNT(*) FROM reminders WHERE user_id = %s AND is_active = 1",
            (user_id,)
        )
        row = c.fetchone()
    return row[0] if row else 0

def get_user_reminders(user_id):
    """Foydalanuvchining barcha faol eslatmalari"""
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT id, medicine_name, times, days FROM reminders WHERE user_id = %s AND is_active = 1",
            (user_id,)
        )
        rows = c.fetchall()
    return rows  # [(id, name, times, days), ...]

def delete_reminder(reminder_id: int, user_id: int):
    """Eslatmani o'chirish"""
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE reminders SET is_active = 0 WHERE id = %s AND user_id = %s", (reminder_id, user_id))
        conn.commit()

def get_all_active_reminders():
    """Barcha faol eslatmalar (scheduler uchun)"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT id, user_id, medicine_name, times, days FROM reminders WHERE is_active = 1")
        rows = c.fetchall()
    return rows  # [(id, user_id, medicine_name, times, days), ...]

# ─────────────────────────────────────────────────────────────────
# FEATURE 7: KUNLIK TAVSIYALAR OBUNASI
# ─────────────────────────────────────────────────────────────────

def set_daily_tips_subscription(user_id, status: int):
    """Kunlik tavsiyalar obunasini yoqish/o'chirish"""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE users SET daily_tips_subscribed = %s WHERE user_id = %s", (status, user_id))
        conn.commit()

def get_daily_tips_subscribers():
    """Kunlik tavsiyalarga obuna bo'lgan barcha foydalanuvchilar"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT user_id FROM users WHERE daily_tips_subscribed = 1")
        rows = c.fetchall()
    return [r[0] for r in rows]

def get_daily_tips_status(user_id) -> int:
    """Foydalanuvchining kunlik tavsiyalar obuna holati"""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute("SELECT daily_tips_subscribed FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    return row[0] if row else 0

# ─────────────────────────────────────────────────────────────────
# BAN TIZIMI (ADMIN BUYRUQLARI UCHUN)
# ─────────────────────────────────────────────────────────────────

# --- Xavfsiz tozalash yordamchilari (asl istisnoni hech qachon almashtirmaydi) ---

def _safe_close_cursor(c):
    if c is None:
        return
    try:
        c.close()
    except Exception:
        logging.warning("cursor close failed", exc_info=True)


def _safe_rollback(conn):
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:
        logging.warning("rollback failed", exc_info=True)


def _safe_release(conn):
    """Connection'ni mavjud wrapper.close() orqali poolga qaytaradi (pool.putconn bevosita chaqirilmaydi)."""
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        logging.warning("connection return failed", exc_info=True)


@contextmanager
def _managed_cursor():
    """(conn, cursor) beradi. Xatoda rollback urinadi, har doim cursor yopiladi va connection qaytariladi."""
    conn = None
    c = None
    try:
        conn = get_connection()
        c = conn.cursor()
        yield conn, c
    except BaseException:
        _safe_rollback(conn)
        raise
    finally:
        _safe_close_cursor(c)
        _safe_release(conn)


# --- Ban keshi: thread-safe, FIFO, maks 2000 yozuv, maks 30 s TTL, monotonic soat ---

class _BanCache:
    MAX_ENTRIES = 2000
    MAX_TTL = 30.0

    def __init__(self, clock=_time.monotonic):
        self._clock = clock          # testlarda lokal soat beriladi
        self._lock = threading.Lock()
        self._data = OrderedDict()   # user_id -> (expires_at, (bool, str))
        self._epoch = 0

    def get(self, user_id):
        with self._lock:
            entry = self._data.get(user_id)
            if entry is None:
                return None
            if entry[0] <= self._clock():
                del self._data[user_id]
                return None
            return entry[1]

    def epoch(self):
        with self._lock:
            return self._epoch

    def put(self, user_id, result, ttl, epoch):
        """Faqat o'qish boshlanganidan beri invalidatsiya bo'lmagan bo'lsa yozadi."""
        ttl = min(float(ttl), self.MAX_TTL)
        if ttl <= 0:
            return
        with self._lock:
            if epoch != self._epoch:
                return
            self._data.pop(user_id, None)
            self._data[user_id] = (self._clock() + ttl, result)
            while len(self._data) > self.MAX_ENTRIES:
                self._data.popitem(last=False)   # FIFO

    def invalidate(self, user_id):
        with self._lock:
            self._epoch += 1
            self._data.pop(user_id, None)


_ban_cache = _BanCache()


def ban_user(user_id: int, duration_minutes: int = None):
    """Foydalanuvchini ban qilish. duration_minutes berilsa - vaqtinchalik, aks holda - doimiy."""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        if duration_minutes:
            banned_until = (get_uz_now() + datetime.timedelta(minutes=duration_minutes)).isoformat()
            c.execute(
                "UPDATE users SET is_banned = 1, banned_until = %s WHERE user_id = %s",
                (banned_until, user_id)
            )
        else:
            c.execute(
                "UPDATE users SET is_banned = 1, banned_until = NULL WHERE user_id = %s",
                (user_id,)
            )
        conn.commit()
        _ban_cache.invalidate(user_id)   # faqat muvaffaqiyatli commitdan keyin

def unban_user(user_id: int):
    """Foydalanuvchini bandan chiqarish."""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute(
            "UPDATE users SET is_banned = 0, banned_until = NULL WHERE user_id = %s",
            (user_id,)
        )
        conn.commit()
        _ban_cache.invalidate(user_id)   # faqat muvaffaqiyatli commitdan keyin

def is_user_banned(user_id: int) -> tuple:
    """
    Foydalanuvchi banlanganligini tekshirish.
    Qaytaradi: (is_banned: bool, message: str)
    """
    hit = _ban_cache.get(user_id)
    if hit is not None:
        # Yozuv faqat register_user() va DB o'qish muvaffaqiyatli bo'lgandan keyin yaratiladi.
        return hit

    epoch = _ban_cache.epoch()   # o'qishdan OLDIN olinadi (poyga himoyasi)
    register_user(user_id)
    result, ttl = _read_ban_state(user_id)
    if ttl:
        _ban_cache.put(user_id, result, ttl, epoch)   # DB xatosida bu yerga yetib kelinmaydi
    return result


def _read_ban_state(user_id: int):
    """Qaytaradi: ((is_banned, message), ttl_sekund yoki None). ttl=None - keshlanmaydi."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT is_banned, banned_until FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()

        if not row:
            return (False, ""), None

        is_banned, banned_until_val = row
        if not is_banned:
            return (False, ""), _BanCache.MAX_TTL

        if banned_until_val:
            # Bazadagi TIMESTAMP (zonasiz) qiymati Toshkent (UTC+5) devor soati; _to_uz_datetime shuni aware qiladi.
            try:
                banned_until = _to_uz_datetime(banned_until_val)
                now = get_uz_now()
                expired = now > banned_until
            except Exception:
                return (True, "🚫 Vaqtinchalik ban faol."), None   # tahlil xatosi keshlanmaydi

            if expired:
                # Ban muddati tugagan — avtomatik o'chiramiz (shu connection'da)
                c.execute("UPDATE users SET is_banned = 0, banned_until = NULL WHERE user_id = %s", (user_id,))
                conn.commit()
                return (False, ""), _BanCache.MAX_TTL

            formatted_time = banned_until.strftime("%d.%m.%Y %H:%M")
            remaining = (banned_until - now).total_seconds()
            return (True, f"🚫 Vaqtinchalik ban muddati: {formatted_time} gacha."), min(_BanCache.MAX_TTL, remaining)

        return (True, "🚫 Doimiy (muddatsiz) ban faol."), _BanCache.MAX_TTL


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

    with _managed_cursor() as (conn, c):
        c.execute("SELECT daily_streak, last_checkin_date FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()

        if not row:
            return False, 0, 0

        streak, last_date = row
        if streak is None:
            streak = 0

        if last_date == today_str:
            # Already checked in today
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
            "UPDATE users SET daily_streak = %s, last_checkin_date = %s, medicine_score = COALESCE(medicine_score, 0) + %s WHERE user_id = %s",
            (new_streak, today_str, points, user_id)
        )
        conn.commit()

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

    with _managed_cursor() as (conn, c):

        # Check if referrer exists
        c.execute("SELECT user_id FROM users WHERE user_id = %s", (referrer_id,))
        if not c.fetchone():
            return False, 0, False

        # Check if new_user exists and if they already have a referrer
        c.execute("SELECT registered_at, referred_by FROM users WHERE user_id = %s", (new_user_id,))
        row = c.fetchone()

        is_new = False
        if not row:
            # Not registered yet
            now = get_uz_now()
            c.execute(
                "INSERT INTO users (user_id, registered_at, is_premium, daily_requests, last_request_date, referred_by) VALUES (%s, %s, %s, %s, %s, %s)",
                (new_user_id, now.isoformat(), 0, 0, now.date().isoformat(), referrer_id)
            )
            is_new = True
        else:
            reg_time_val, ref_by = row
            if ref_by is None:
                # Check if registered very recently (e.g. within 2 minutes)
                # Bazadagi zonasiz vaqt Toshkent zonasiga keltiriladi (aks holda
                # zonali get_uz_now() dan ayirish TypeError beradi — P0-3)
                try:
                    reg_time = _to_uz_datetime(reg_time_val)
                except (TypeError, ValueError):
                    logging.exception(
                        "handle_referral: registered_at o'qilmadi (user=%s, value=%r)",
                        new_user_id, reg_time_val,
                    )
                    reg_time = None
                if reg_time is not None and (get_uz_now() - reg_time).total_seconds() < 120:
                    c.execute("UPDATE users SET referred_by = %s WHERE user_id = %s", (referrer_id, new_user_id))
                    is_new = True

        if not is_new:
            return False, 0, False

        # Give referrer +10 points
        c.execute("UPDATE users SET medicine_score = COALESCE(medicine_score, 0) + 10 WHERE user_id = %s", (referrer_id,))

        # Check total friends referred by this referrer
        c.execute("SELECT COUNT(*) FROM users WHERE referred_by = %s", (referrer_id,))
        count = c.fetchone()[0]

        bonus_given = False
        points_given = 10

        if count == 5:
            # Give extra +50 points bonus
            c.execute("UPDATE users SET medicine_score = COALESCE(medicine_score, 0) + 50 WHERE user_id = %s", (referrer_id,))
            points_given += 50
            bonus_given = True

        conn.commit()

    # Automatically check if referrer qualifies for Premium upgrade
    check_and_grant_premium(referrer_id)

    return True, points_given, bonus_given


def check_and_grant_spin_bonus(user_id: int, client_points: int = 0) -> tuple:
    """
    Checks if user is eligible for spin bonus.
    Reward is strictly taken from server-side pending_spin_prize (ignoring client_points).
    If yes, awards points and updates last_spin_date.
    Returns (success, message)
    """
    # Uzbekistan timezone (UTC+5)
    from datetime import datetime, timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    now = datetime.now(uz_tz)
    now_str = now.isoformat()

    with _managed_cursor() as (conn, c):
        c.execute("SELECT last_spin_date, pending_spin_prize FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()

        if not row:
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
                    remaining_seconds = int(24 * 3600 - diff.total_seconds())
                    hours = remaining_seconds // 3600
                    minutes = (remaining_seconds % 3600) // 60
                    seconds = remaining_seconds % 60
                    return False, f"Keyingi urinishgacha {hours:02d}:{minutes:02d}:{seconds:02d} vaqt qoldi. 🕒"
            except ValueError:
                # Fallback to old YYYY-MM-DD format
                if last_spin == now.date().isoformat():
                    return False, "Siz bugun barabanni aylantirib bo'ldingiz! Keyingi urinish ertaga. 🕒"

        if pending_prize is None:
            return False, "Sizda tasdiqlanmagan yutuq topilmadi yoki u allaqachon hisobingizga qo'shilgan! 🕒"

        # Safe legacy handling: if old DB state has pending_prize > 10 (e.g., 20 or 50), cap to max valid reward (10)
        if pending_prize not in (0, 1, 3, 5, 10):
            pending_prize = 10

        points = pending_prize

        if points == 0:
            # Super Prize: discount
            c.execute(
                "UPDATE users SET last_spin_date = %s, has_discount = 1, pending_spin_prize = NULL WHERE user_id = %s",
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
                "UPDATE users SET last_spin_date = %s, medicine_score = COALESCE(medicine_score, 0) + %s, pending_spin_prize = NULL WHERE user_id = %s",
                (now_str, points, user_id)
            )
            msg = f"Tabriklaymiz! Siz Omad barabanidan <b>+{points} ball</b> yutib oldingiz! 🎉"

        conn.commit()

    # Automatically check if user qualifies for Premium upgrade
    if points > 0:
        check_and_grant_premium(user_id)

    return True, msg


def has_discount(user_id: int) -> bool:
    """Checks if the user has an active super prize discount"""
    with _managed_cursor() as (conn, c):
        try:
            c.execute("SELECT has_discount FROM users WHERE user_id = %s", (user_id,))
            row = c.fetchone()
            val = bool(row[0]) if row else False
        except Exception:
            val = False
    return val


def consume_discount(user_id: int) -> None:
    """Consumes the super prize discount"""
    with _managed_cursor() as (conn, c):
        try:
            c.execute("UPDATE users SET has_discount = 0 WHERE user_id = %s", (user_id,))
            conn.commit()
        except Exception as e:
            logging.error(f"Error consuming discount: {e}")

def get_referral_count(user_id: int) -> int:
    with _managed_cursor() as (conn, c):
        c.execute('SELECT COUNT(*) FROM users WHERE referred_by = %s', (user_id,))
        count = c.fetchone()[0]
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

    with _managed_cursor() as (conn, c):
        c.execute("SELECT last_spin_date, pending_spin_prize FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()

        if not row:
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
                    return None  # Cooldown active
            except ValueError:
                if last_spin == now.date().isoformat():
                    return None

        # If we already generated a prize but they haven't claimed it yet
        if pending_prize is not None:
            return pending_prize

        # Generate new prize
        # MUHIM: Qiymatlar aynan app.js segments bilan mos bo'lishi kerak!
        # Frontend segments: 1, 3, 5, 10, 0 (SUPER)
        # 20 va 50 frontend'da yo'q — ularni generatsiya qilish MUMKIN EMAS
        r = random.random()
        if r < 0.40:    prize = 1    # 40% ehtimol
        elif r < 0.65:  prize = 3    # 25% ehtimol
        elif r < 0.83:  prize = 5    # 18% ehtimol
        elif r < 0.97:  prize = 10   # 14% ehtimol
        else:           prize = 0    #  3% ehtimol (SUPER PRIZ)
        # Jami: 1,3,5,10,SUPER — barcha qiymatlar frontend segments da mavjud

        c.execute("UPDATE users SET pending_spin_prize = %s WHERE user_id = %s", (prize, user_id))
        conn.commit()
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

    with _managed_cursor() as (conn, c):
        c.execute("SELECT daily_streak, last_checkin_date FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()

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
