import psycopg2
import psycopg2.extras
import datetime
import html
import json
import os
import logging
import math
import random
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

POOL_MIN_CONN = 2
POOL_MAX_CONN = 10


def get_connection():
    """PostgreSQL bazaga ulanish. Pooling orqali ishlaydi."""
    global db_pool
    if db_pool is None:
        # Server 512 MB RAM, Neon bepul tarif ulanish limitlari — kichik pool (P2-1)
        db_pool = ThreadedConnectionPool(minconn=POOL_MIN_CONN, maxconn=POOL_MAX_CONN, dsn=DATABASE_URL)
    
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
                ban_mode TEXT,
                ban_reason TEXT,
                banned_at TIMESTAMP,
                full_name TEXT,
                username TEXT,
                free_ai_used INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_checkin_date TEXT,
                referred_by BIGINT,
                last_spin_date TEXT,
                has_discount INTEGER DEFAULT 0,
                discount_expires_at TIMESTAMP,
                pending_spin_prize INTEGER,
                spin_ai_bonus INTEGER DEFAULT 0,
                premium_expiry_notified_for TEXT
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

        # Migratsiya: Omad barabanidan yutilgan bonus AI savollar (muddatsiz, ishlatilguncha saqlanadi)
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS spin_ai_bonus INTEGER DEFAULT 0")

        # Migratsiya: tugashidan oldingi eslatma qaysi premium_expires_at uchun yuborilgani (takrorlanmasligi uchun)
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_expiry_notified_for TEXT")

        # Migratsiya: SUPER PRIZ chegirmasi endi 24 soat amal qiladi (discount_expires_at). Muddatsiz saqlangan eski
        # chegirmalarga (has_discount = 1, muddat yo'q) deploy paytidan boshlab 24 soat beriladi — bir marta (idempotent).
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS discount_expires_at TIMESTAMP")
        migrate_discount_expiry(c)

        # Migratsiya: ban rejimi ('open' — ochiq, 'silent' — sirli), sabab (sirlida — admin izohi) va qo'yilgan vaqt.
        # Eski banlar (is_banned = 1, ban_mode IS NULL) OCHIQ ban hisoblanadi.
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_mode TEXT")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at TIMESTAMP")

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
        # SELECT -> INSERT o'rniga atomik INSERT: parallel /start da dublikat xatosi bo'lmaydi (P1-2)
        now = get_uz_now()
        c.execute(
            "INSERT INTO users (user_id, registered_at, is_premium, daily_requests, last_request_date, full_name, username) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
            (user_id, now.isoformat(), 0, 0, now.date().isoformat(), full_name, username)
        )
        if c.rowcount == 0:
            # Mavjud foydalanuvchi — ismini yangilaymiz
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
    Premium foydalanuvchining kunlik AI limitini atomar tarzda tekshiradi va band qiladi.
    Limitlar: PRO = 15, PLUS = 30, ULTRA = 100 (env: *_AI_DAILY_LIMIT).
    Bepul foydalanuvchida kunlik limit YO'Q: unga jami 1 ta bir martalik savol try_consume_free_ai() orqali beriladi.
    Qaytaradi: True (ruxsat), False (limit tugagan yoki bepul foydalanuvchi).
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

        # Limitni aniqlaymiz: ULTRA (100), PLUS (30), PRO (15). Bepul — 0 (faqat bir martalik bepul savol)
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
            max_requests = 0

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

def _ai_quota_parts(user_id) -> tuple:
    """(oddiy_qolgan, limit, bonus). FAQAT o'qiydi — hech narsa yozmaydi.
    Oddiy kvota qoidasi try_consume_free_ai + try_consume_daily_request bilan bir xil:
      * premium: kunlik tarif limiti PRO / PLUS / ULTRA_AI_DAILY_LIMIT, daily_requests faqat bugungi kun uchun;
      * bepul (yoki muddati o'tgan premium): jami 1 ta bir martalik savol — 1/1, ishlatilgach 0/1.
    bonus — Omad barabanidan yutilgan savollar (spin_ai_bonus), tarif limitiga KIRMAYDI."""
    tier_limits = {
        "pro": int(os.environ.get("PRO_AI_DAILY_LIMIT", "15")),
        "plus": int(os.environ.get("PLUS_AI_DAILY_LIMIT", "30")),
        "ultra": int(os.environ.get("ULTRA_AI_DAILY_LIMIT", "100")),
    }
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT is_premium, premium_expires_at, premium_type, daily_requests, last_request_date, free_ai_used, "
            "spin_ai_bonus FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    if not row:
        return 1, 1, 0                                   # yangi foydalanuvchi: bitta bepul savol

    is_premium, expires_at, premium_type, daily_requests, last_request_date, free_ai_used, bonus = row
    bonus = max(0, int(bonus or 0))
    active = bool(is_premium)
    if active and expires_at:
        active = get_uz_now() <= _to_uz_datetime(expires_at)
    if not active:
        return (0 if free_ai_used else 1), 1, bonus      # bepul: jami 1 ta (bir martalik)

    tier = premium_type if premium_type in tier_limits else "ultra"   # muddatsiz premium — ultra (try_consume_daily_request kabi)
    tier_limit = tier_limits[tier]
    today = get_uz_now().date().isoformat()
    used = int(daily_requests or 0) if last_request_date == today else 0
    return max(0, tier_limit - used), tier_limit, bonus


def get_ai_quota(user_id) -> tuple:
    """AI kvotasi: (qolgan, limit). Bot va mini app bitta kvotani ulashadi.
    `qolgan` oddiy kvota qoldig'iga barabandan yutilgan bonusni ham QO'SHADI; `limit` esa faqat tarif limiti
    (bonus unga kirmaydi — mini app limit<=1 ni "bepul" deb biladi)."""
    base, limit, bonus = _ai_quota_parts(user_id)
    return base + bonus, limit


def get_ai_quota_detail(user_id) -> tuple:
    """(qolgan, limit, bonus) — get_ai_quota + bonus alohida (mini app yorlig'i "... + N bonus" uchun).
    `qolgan` bonusni o'z ichiga oladi: oddiy qoldiq = qolgan - bonus."""
    base, limit, bonus = _ai_quota_parts(user_id)
    return base + bonus, limit, bonus


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


def try_consume_spin_ai_bonus(user_id) -> bool:
    """Barabandan yutilgan bonus AI savolni atomar sarflaydi (spin_ai_bonus - 1, nolga yetganda False).
    Chaqirish tartibi: avval oddiy kvota (try_consume_free_ai / try_consume_daily_request), u tugagach shu."""
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE users SET spin_ai_bonus = spin_ai_bonus - 1 WHERE user_id = %s AND spin_ai_bonus > 0",
                  (user_id,))
        success = c.rowcount > 0
        conn.commit()
    return success


def refund_spin_ai_bonus(user_id):
    """AI xato qilganda bonus savolni qaytarish (faqat u bonusdan olingan bo'lsa chaqiriladi)."""
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE users SET spin_ai_bonus = COALESCE(spin_ai_bonus, 0) + 1 WHERE user_id = %s", (user_id,))
        conn.commit()

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

# ═══════════════════════════════════════════════════════════════════
# ADMIN PREMIUM PANELI (bot.py: /premium) — ro'yxat, qidiruv, berish, muddatsiz
# ═══════════════════════════════════════════════════════════════════
ADMIN_PAGE_SIZE = 10
_ADMIN_TIERS = ("pro", "plus", "ultra")

# ── Ko'rinadigan tarif nomlari: BITTA joyda (bot.py ham shundan oladi) ─────────────────────────────────────────
# ⚠️ ICHKI KOD pro = KO'RINADIGAN "Plus" (eng arzon: 7 kun, 50 ⭐, 15 AI/kun); ichki plus = ko'rinadigan "Pro"
# (30 kun, 150 ⭐, 30 AI/kun). Ultra o'zgarmagan. Pastdan yuqoriga: Plus → Pro → Ultra.
# Bazadagi premium_type (pro/plus/ultra), invoice payloadlari (PRO_7_DAYS, PLUS_30_DAYS, PLUS_30_DAYS_DISCOUNT),
# callback_data (buy_pro_7, buy_plus_30...), env nomlari, tier_rank va CSS klasslari (tier-pro, tier-plus) ICHKI kod
# bo'yicha QOLADI: o'zgaradigan faqat foydalanuvchi va admin ko'radigan matn. JS dagi PREMIUM_TIERS (app.js) bilan bir xil.
TIER_DISPLAY = {"pro": "Plus", "plus": "Pro", "ultra": "Ultra"}
TIER_ICON = {"pro": "⭐", "plus": "💎", "ultra": "👑"}


def premium_days_left(expires, now=None) -> int:
    """Qolgan kun: ceil((tugash - hozir) / 1 kun). Vaqt Toshkent (UTC+5) bo'yicha (aware datetime'lar farqi). Tugagan -> 0."""
    now = now or get_uz_now()
    return max(0, math.ceil((expires - now).total_seconds() / 86400))


def admin_premium_view(is_premium, premium_type, expires_at, now=None) -> dict:
    """Foydalanuvchining HAQIQIY Premium holati — bot, API va admin paneli uchun YAGONA manba:
    {"active", "tier" ('free'|'pro'|'plus'|'ultra'), "unlimited", "expires" (datetime | None),
     "days_left" (int | None — muddatsiz/oddiyda None), "ends_today" (24 soatdan kam qolgan)}.
    Kvota kodi (get_ai_quota / try_consume_daily_request) bilan bir xil qoida: muddatsiz premium (is_premium=1,
    muddat bo'sh) premium_type bo'yicha hisoblanadi (noma'lum tur -> ultra); muddati o'tgan premium — oddiy."""
    free = {"active": False, "tier": "free", "unlimited": False, "expires": None, "days_left": None,
            "ends_today": False}
    if not is_premium:
        return free
    tier = premium_type if premium_type in _ADMIN_TIERS else "ultra"
    if not expires_at:
        return {"active": True, "tier": tier, "unlimited": True, "expires": None, "days_left": None,
                "ends_today": False}
    try:
        expires = _to_uz_datetime(expires_at)
    except (ValueError, TypeError):
        return free
    now = now or get_uz_now()
    if expires <= now:
        return free
    return {"active": True, "tier": tier, "unlimited": False, "expires": expires,
            "days_left": premium_days_left(expires, now), "ends_today": (expires - now).total_seconds() < 86400}


def get_premium_view(user_id: int) -> dict:
    """admin_premium_view foydalanuvchi uchun (faqat o'qiydi: register_user ham, muddati o'tgan flagni tozalash ham yo'q).
    Foydalanuvchi bazada bo'lmasa — oddiy."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT is_premium, premium_expires_at, premium_type FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    if not row:
        return admin_premium_view(0, None, None)
    is_premium, expires_at, premium_type = row
    return admin_premium_view(is_premium, premium_type, expires_at)


_ADMIN_USER_COLUMNS = (
    "user_id, is_premium, premium_type, premium_expires_at, full_name, username, COALESCE(medicine_score, 0), "
    "is_banned, banned_until, ban_mode, ban_reason, banned_at"
)


def _admin_user_record(row) -> dict:
    """Admin panellari (Premium va Ban) uchun yozuv: Premium holati (admin_premium_view) + ban holati ("ban":
    get_ban_info bilan BIR XIL qoida, qo'shimcha "banned_at")."""
    (user_id, is_premium, premium_type, expires_at, full_name, username, score,
     is_banned, banned_until, ban_mode, ban_reason, banned_at) = row
    record = {"user_id": user_id, "full_name": full_name, "username": username, "score": int(score or 0)}
    record.update(admin_premium_view(is_premium, premium_type, expires_at))
    ban, _ttl = _ban_view(is_banned, banned_until, ban_mode, ban_reason)
    try:
        ban["banned_at"] = _to_uz_datetime(banned_at) if (ban["banned"] and banned_at) else None
    except (ValueError, TypeError):
        ban["banned_at"] = None
    record["ban"] = ban
    return record


def admin_users_page(page: int = 0, page_size: int = ADMIN_PAGE_SIZE, banned_only: bool = False) -> dict:
    """Bazadagi foydalanuvchilar (yangi ro'yxatdan o'tganlar birinchi), sahifalab. banned_only=True — faqat HOZIR banda
    bo'lganlar (muddati o'tgan, lekin hali tozalanmagan ban hisobga olinmaydi). Natija: {"users", "page", "pages",
    "total" (jami foydalanuvchilar), "premium_count", "banned_count", "listed" (ro'yxatdagi jami)}.
    Sahifa chegaradan chiqsa — chegaraga keltiriladi."""
    now_param = not_banned_params()
    with _managed_cursor() as (conn, c):
        c.execute("SELECT COUNT(*) FROM users")
        total = int(c.fetchone()[0] or 0)
        c.execute("SELECT is_premium, premium_type, premium_expires_at FROM users WHERE is_premium = 1")
        premium_count = sum(1 for r in c.fetchall() if admin_premium_view(r[0], r[1], r[2])["active"])
        c.execute("SELECT COUNT(*) FROM users WHERE " + BANNED_SQL, now_param)
        banned_count = int(c.fetchone()[0] or 0)
        listed = banned_count if banned_only else total
        pages = max(1, -(-listed // page_size))
        page = min(max(int(page), 0), pages - 1)
        if banned_only:
            c.execute(
                "SELECT " + _ADMIN_USER_COLUMNS + " FROM users WHERE " + BANNED_SQL +
                " ORDER BY banned_at DESC NULLS LAST, user_id DESC LIMIT %s OFFSET %s",
                (*now_param, page_size, page * page_size)
            )
        else:
            c.execute(
                "SELECT " + _ADMIN_USER_COLUMNS + " FROM users "
                "ORDER BY registered_at DESC NULLS LAST, user_id DESC LIMIT %s OFFSET %s",
                (page_size, page * page_size)
            )
        users = [_admin_user_record(r) for r in c.fetchall()]
    return {"users": users, "page": page, "pages": pages, "total": total, "premium_count": premium_count,
            "banned_count": banned_count, "listed": listed}


def admin_get_user(user_id: int):
    """Bitta foydalanuvchi yozuvi (dict) yoki None."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT " + _ADMIN_USER_COLUMNS + " FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    return _admin_user_record(row) if row else None


def admin_find_user(query: str):
    """Qidiruv: raqamli ID yoki @username (kichik/katta harf farqsiz). Faqat bazadagi foydalanuvchilar. Topilmasa None."""
    q = (query or "").strip()
    if q.startswith("@"):
        q = q[1:].strip()
    if not q or len(q) > 64:
        return None
    with _managed_cursor() as (conn, c):
        if q.isascii() and q.isdigit():
            if int(q) > 2 ** 63 - 1:                      # BIGINT dan katta ID bazada bo'lishi mumkin emas
                return None
            c.execute("SELECT " + _ADMIN_USER_COLUMNS + " FROM users WHERE user_id = %s", (int(q),))
        else:
            c.execute("SELECT " + _ADMIN_USER_COLUMNS + " FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1", (q,))
        row = c.fetchone()
    return _admin_user_record(row) if row else None


def _like_pattern(text: str) -> str:
    """LIKE uchun qidiruv matni: foiz, pastki chiziq va teskari chiziq belgilari oddiy harf sifatida (ESCAPE)."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def admin_search_users(query: str, limit: int = 10) -> list:
    """Admin qidiruvi: ID, @username yoki ISM bo'yicha (kichik/katta harf farqsiz). ID va @username — admin_find_user
    (Premium panelidagi qidiruv) bilan BIR XIL; "@" siz matn bo'lsa avval aniq username, keyin ism/username bo'laklari.
    Natija — dict'lar ro'yxati (ko'pi bilan `limit` ta, yangi ro'yxatdan o'tganlar birinchi); topilmasa []."""
    q = (query or "").strip()
    if not q or len(q) > 64:
        return []
    if q.startswith("@") or (q.isascii() and q.isdigit()):
        user = admin_find_user(q)
        return [user] if user else []
    found = []
    exact = admin_find_user(q)                                  # "ali" — aniq username bo'lishi mumkin
    if exact:
        found.append(exact)
    pattern = _like_pattern(q.lower())
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT " + _ADMIN_USER_COLUMNS + " FROM users "
            "WHERE LOWER(full_name) LIKE %s ESCAPE '\\' OR LOWER(username) LIKE %s ESCAPE '\\' "
            "ORDER BY registered_at DESC NULLS LAST, user_id DESC LIMIT %s",
            (pattern, pattern, int(limit))
        )
        rows = c.fetchall()
    seen = {u["user_id"] for u in found}
    for row in rows:
        record = _admin_user_record(row)
        if record["user_id"] not in seen:
            seen.add(record["user_id"])
            found.append(record)
    return found[:limit]


def set_premium_unlimited(user_id: int, tier: str, _cursor=None) -> bool:
    """Muddatsiz Premium: is_premium=1, premium_type=tier, premium_expires_at=NULL, premium_until=NULL.
    Kvota kodi muddatsizni premium_type bo'yicha hisoblaydi (tarif limiti). _cursor berilsa — chaqiruvchining
    tranzaksiyasida (commit/close bu yerda emas). True — foydalanuvchi topildi va yangilandi."""
    if tier not in _ADMIN_TIERS:
        raise ValueError(f"Noto'g'ri premium_type: {tier!r}. Faqat {_ADMIN_TIERS} qabul qilinadi.")
    sql = ("UPDATE users SET is_premium = 1, premium_type = %s, premium_expires_at = NULL, premium_until = NULL "
           "WHERE user_id = %s")
    if _cursor is not None:
        _cursor.execute(sql, (tier, user_id))
        return _cursor.rowcount > 0
    with _managed_cursor() as (conn, c):
        c.execute(sql, (tier, user_id))
        updated = c.rowcount > 0
        conn.commit()
    return updated


def admin_grant_premium(user_id: int, tier: str, days) -> dict:
    """Admin Premium beradi — BITTA tranzaksiyada. days=None — muddatsiz.
    * Kunlik muddat: grant_premium_days (faol muddatga qo'shadi, yuqori tarifni saqlaydi: Ultra + 3 kun (ichki pro) ->
      Ultra saqlanadi, muddat +3 kun).
    * Userda muddatsiz Premium bo'lsa kunlik muddat BERILMAYDI (grant_premium_days uni kunlikka almashtirib yuborardi):
      error="unlimited_exists". Muddatsiz -> muddatsiz (tarifni almashtirish) mumkin.
    Natija: {"ok", "error" (None | "not_found" | "unlimited_exists"), "tier" (yakuniy), "previous_tier", "expires",
    "unlimited", "kept_higher" (yakuniy tarif so'ralganidan yuqori)}."""
    if tier not in _ADMIN_TIERS:
        raise ValueError(f"Noto'g'ri premium_type: {tier!r}. Faqat {_ADMIN_TIERS} qabul qilinadi.")
    if days is not None:
        _validate_premium_grant_args(tier, days)
    result = {"ok": False, "error": None, "tier": None, "previous_tier": "free", "expires": None,
              "unlimited": days is None, "kept_higher": False}
    with _managed_cursor() as (conn, c):
        c.execute("SELECT is_premium, premium_type, premium_expires_at FROM users WHERE user_id = %s FOR UPDATE",
                  (user_id,))
        row = c.fetchone()
        if not row:
            result["error"] = "not_found"
            return result
        before = admin_premium_view(row[0], row[1], row[2])
        result["previous_tier"] = before["tier"] if before["active"] else "free"

        if days is None:
            set_premium_unlimited(user_id, tier, _cursor=c)
            conn.commit()
            result.update(ok=True, tier=tier)
            return result

        if before["unlimited"]:
            result["error"] = "unlimited_exists"
            return result
        until = grant_premium_days(user_id, days, tier, _cursor=c)
        c.execute("SELECT premium_type FROM users WHERE user_id = %s", (user_id,))
        final_tier = c.fetchone()[0] or tier
        conn.commit()
        result.update(ok=True, tier=final_tier, expires=until, unlimited=False, kept_higher=final_tier != tier)
    return result


# ── Tugashidan oldingi eslatma va muddati o'tgan Premiumni yopish (bot.py: premium_expiry_loop) ──
PREMIUM_EXPIRY_BATCH = 200
PREMIUM_EXPIRY_WINDOW_SECONDS = 24 * 3600


def premium_expiry_candidates(now=None, limit: int = PREMIUM_EXPIRY_BATCH) -> dict:
    """Muddatli Premiumlar (is_premium=1, muddat bor) ichidan:
      * "notify"  — hali faol, qolgan vaqt <= 24 soat va BU muddat uchun eslatma yuborilmagan (ban holatini
        chaqiruvchi is_user_banned bilan tekshiradi: vaqtinchalik ban muddati ham hisobga olinadi);
      * "expired" — muddati o'tgan (flag hali 1).
    Muddatsiz va oddiy foydalanuvchilar umuman kirmaydi. Har ro'yxat ko'pi bilan `limit` ta.
    Elementlar: dict(user_id, tier, expires (datetime), expires_raw (bazadagi qiymat), full_name)."""
    now = now or get_uz_now()
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT user_id, premium_type, premium_expires_at, full_name, premium_expiry_notified_for "
            "FROM users WHERE is_premium = 1 AND premium_expires_at IS NOT NULL"
        )
        rows = c.fetchall()
    notify, expired = [], []
    for user_id, premium_type, expires_raw, full_name, notified_for in rows:
        view = admin_premium_view(1, premium_type, expires_raw, now)
        if view["unlimited"]:
            continue
        if not view["active"]:
            try:
                expires = _to_uz_datetime(expires_raw)
            except (ValueError, TypeError):
                continue
            if len(expired) < limit:
                expired.append({"user_id": user_id, "tier": premium_type if premium_type in _ADMIN_TIERS else "pro",
                                "expires": expires, "expires_raw": expires_raw, "full_name": full_name})
            continue
        if len(notify) >= limit:
            continue
        if (view["expires"] - now).total_seconds() > PREMIUM_EXPIRY_WINDOW_SECONDS:
            continue
        if notified_for == view["expires"].isoformat():
            continue
        notify.append({"user_id": user_id, "tier": view["tier"], "expires": view["expires"],
                       "expires_raw": expires_raw, "full_name": full_name})
    return {"notify": notify, "expired": expired}


def claim_premium_expiry_notice(user_id: int, expires_iso: str) -> bool:
    """Eslatmani ATOMAR belgilaydi: faqat shu muddat uchun hali belgilanmagan bo'lsa True (bir nechta jarayon bo'lsa ham
    xabar bitta ketadi). Muddat uzaytirilsa qiymat o'zgaradi va eslatma yana ishlaydi."""
    with _managed_cursor() as (conn, c):
        c.execute(
            "UPDATE users SET premium_expiry_notified_for = %s WHERE user_id = %s "
            "AND premium_expiry_notified_for IS DISTINCT FROM %s",
            (expires_iso, user_id, expires_iso)
        )
        claimed = c.rowcount == 1
        conn.commit()
    return claimed


def close_expired_premium(user_id: int, expires_raw) -> bool:
    """Muddati o'tgan Premium flagini yopadi (get_premium_info dagi kabi), lekin faqat muddat hamon o'sha qiymat bo'lsa
    (parallel uzaytirishni buzmaydi). True — yopildi."""
    with _managed_cursor() as (conn, c):
        c.execute(
            "UPDATE users SET is_premium = 0, premium_type = 'free' "
            "WHERE user_id = %s AND is_premium = 1 AND premium_expires_at = %s",
            (user_id, expires_raw)
        )
        closed = c.rowcount == 1
        conn.commit()
    return closed


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
                         premium_type: str, days: int, consume_discount: bool = False):
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
        if consume_discount:
            # SUPER PRIZ chegirmasi premium bilan bir tranzaksiyada sarflanadi (P1-5)
            c.execute("UPDATE users SET has_discount = 0, discount_expires_at = NULL WHERE user_id = %s", (user_id,))
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
    """If user has at least 100 points, grant 3-day premium (ichki pro) and subtract 100 score atomically.
    False — ball yetarli emas YOKI muddatsiz Premium bor: muddatsiz (is_premium=1, muddat bo'sh) Premiumga 3 kunlik muddat
    qo'shib bo'lmaydi (u muddatsizni buzib yuborardi), ballar ham yechilmaydi. Tekshiruv ballni yechish bilan BIR
    tranzaksiyada, qator qulflangan holda (kunlik bonus / referal / baraban avto-berishi ham shu funksiyadan o'tadi)."""
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
        c.execute("SELECT is_premium, premium_expires_at, premium_type FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
        row = c.fetchone()
        if row and row[0] and not row[1]:
            conn.rollback()                    # muddatsiz Premium: ball yechilmaydi, Premium o'zgarmaydi
            return False
        base = now
        current_type = "free"
        if row and row[1]:
            try:
                existing = _to_uz_datetime(row[1])
                if existing > now:
                    base = existing
                    current_type = row[2] or "pro"
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
    """BARCHA foydalanuvchilar (banlangan ham) — ma'muriy skriptlar uchun (masalan scripts/reset_menu_buttons.py).
    Xabar yuborish uchun BUNI ishlatmang: get_active_user_ids() / get_broadcast_targets()."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT user_id FROM users")
        rows = c.fetchall()
    return [r[0] for r in rows]


def get_active_user_ids() -> list:
    """HOZIR banda bo'lmagan barcha foydalanuvchilar (ommaviy va rejali yuborishlar uchun). Muddati o'tgan, lekin hali
    fon vazifasi tozalamagan ban hisobga olinmaydi (NOT_BANNED_SQL)."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT user_id FROM users WHERE " + NOT_BANNED_SQL, not_banned_params())
        rows = c.fetchall()
    return [r[0] for r in rows]


def get_broadcast_targets() -> dict:
    """Admin /broadcast uchun: {"users": [banda bo'lmaganlar], "banned": o'tkazib yuboriladigan banlanganlar soni}."""
    now_param = not_banned_params()
    with _managed_cursor() as (conn, c):
        c.execute("SELECT user_id FROM users WHERE " + NOT_BANNED_SQL, now_param)
        users = [r[0] for r in c.fetchall()]
        c.execute("SELECT COUNT(*) FROM users WHERE " + BANNED_SQL, now_param)
        banned = int(c.fetchone()[0] or 0)
    return {"users": users, "banned": banned}


def get_premium_checkin_targets() -> list:
    """Premium check-in (20:30) uchun: banda bo'lmagan Premium foydalanuvchilar [(user_id, premium_expires_at, premium_type)]."""
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT user_id, premium_expires_at, premium_type FROM users WHERE " + NOT_BANNED_SQL + " AND is_premium = 1",
            not_banned_params()
        )
        rows = c.fetchall()
    return rows

def get_all_users_info(limit=20):
    """Foydalanuvchilar ro'yxatini id, premium holati, ism va username bilan olish"""
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT user_id, is_premium, registered_at, full_name, username FROM users ORDER BY registered_at DESC LIMIT %s",
            (limit,)
        )
        rows = c.fetchall()
    return rows  # [(user_id, is_premium, registered_at, full_name, username), ...]

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
    """HOZIR banda bo'lgan foydalanuvchilar soni (muddati o'tgan ban hisobga olinmaydi)"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT COUNT(*) FROM users WHERE " + BANNED_SQL, not_banned_params())
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

def wipe_user_medical_data(user_id: int) -> dict:
    """Foydalanuvchining BARCHA tibbiy ma'lumotlarini bitta tranzaksiyada o'chiradi (P2-8):
    profil maydonlari, dori eslatmalari, engagement javoblari, qiziqishlar.
    Hisob, ballar, premium va to'lov yozuvlari saqlanib qoladi.
    Qaytaradi: o'chirilgan qatorlar soni {"reminders": n, "engagement_logs": n, "user_interests": n}."""
    deleted = {}
    with _managed_cursor() as (conn, c):
        c.execute(
            """UPDATE users SET blood_group = NULL, age = NULL, weight = NULL, height = NULL,
               chronic_diseases = NULL, allergies = NULL WHERE user_id = %s""",
            (user_id,)
        )
        c.execute("DELETE FROM reminders WHERE user_id = %s", (user_id,))
        deleted["reminders"] = c.rowcount
        c.execute("DELETE FROM engagement_logs WHERE user_id = %s", (user_id,))
        deleted["engagement_logs"] = c.rowcount
        c.execute("DELETE FROM user_interests WHERE user_id = %s", (user_id,))
        deleted["user_interests"] = c.rowcount
        conn.commit()
    logging.info("wipe_user_medical_data: user=%s deleted=%s", user_id, deleted)
    return deleted


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
    """Faol eslatmalar (scheduler uchun). Banlangan foydalanuvchilarning eslatmalari qaytarilmaydi (ularga hech qanday
    avtomatik xabar bormaydi); muddati o'tgan ban hisobga olinmaydi."""
    with _managed_cursor() as (conn, c):
        c.execute(
            "SELECT id, user_id, medicine_name, times, days FROM reminders WHERE is_active = 1 "
            "AND user_id NOT IN (SELECT user_id FROM users WHERE " + BANNED_SQL + ")",
            not_banned_params()
        )
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
    """Kunlik tavsiyalarga obuna bo'lgan foydalanuvchilar (banda bo'lmaganlar: NOT_BANNED_SQL)"""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT user_id FROM users WHERE daily_tips_subscribed = 1 AND " + NOT_BANNED_SQL, not_banned_params())
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


# ═══════════════════════════════════════════════════════════════════
# BAN TIZIMI: 📣 ochiq (userga xabar, mini app "Siz bloklangansiz") va 🤫 sirli (bot butunlay jim, mini app oddiy xato).
# Yagona o'qish joyi — get_ban_info; is_user_banned unga tayanadi. Muddati o'tgan ban o'qishda "ban yo'q" hisoblanadi,
# lekin bazaga YOZILMAYDI: tozalash va "Blok muddati tugadi" xabari faqat fon vazifasida (expire_finished_bans).
# ═══════════════════════════════════════════════════════════════════
BAN_MODE_OPEN = "open"
BAN_MODE_SILENT = "silent"
BAN_MODES = (BAN_MODE_OPEN, BAN_MODE_SILENT)
BAN_REASON_MAX = 200

# YAGONA SQL shartlari ("hozir banda emas" / "hozir banda"). Parametr — Toshkent devor soati (not_banned_params()).
# Barcha ommaviy yuborishlar shundan foydalanadi: oddiy `is_banned = 0` muddati o'tgan, lekin hali tozalanmagan
# userlarni noto'g'ri chiqarib tashlardi.
NOT_BANNED_SQL = "(COALESCE(is_banned, 0) = 0 OR (banned_until IS NOT NULL AND banned_until <= %s))"
BANNED_SQL = "(COALESCE(is_banned, 0) = 1 AND (banned_until IS NULL OR banned_until > %s))"


def _wall_iso(value=None) -> str:
    """Toshkent devor soati (zonasiz) ISO matni — TIMESTAMP ustunlari (banned_until, banned_at) shu ko'rinishda saqlanadi
    va solishtiriladi (PostgreSQL TIMESTAMP zona qismini baribir tashlab yuboradi)."""
    value = value or get_uz_now()
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone(datetime.timedelta(hours=5)))
    return value.replace(tzinfo=None).isoformat()


def not_banned_params(now=None) -> tuple:
    """NOT_BANNED_SQL / BANNED_SQL uchun parametrlar (bitta: hozirgi Toshkent devor soati)."""
    return (_wall_iso(now),)


class _BanCache:
    MAX_ENTRIES = 2000
    MAX_TTL = 30.0

    def __init__(self, clock=_time.monotonic):
        self._clock = clock          # testlarda lokal soat beriladi
        self._lock = threading.Lock()
        self._data = OrderedDict()   # user_id -> (expires_at, ban_info)
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


def _clean_ban_reason(reason):
    """Sabab / admin izohi: bo'sh -> None, ortiqcha bo'shliqlar olinadi, BAN_REASON_MAX belgigacha."""
    if reason is None:
        return None
    text = " ".join(str(reason).split())
    return text[:BAN_REASON_MAX] or None


def ban_user(user_id: int, duration_minutes: int = None, mode: str = BAN_MODE_OPEN, reason: str = None):
    """Foydalanuvchini ban qilish (faqat admin chaqiradi). duration_minutes berilsa — vaqtinchalik, aks holda — muddatsiz.
    mode: 'open' (📣 userga xabar boradi, bot va mini app "bloklangansiz" deydi) yoki 'silent' (🤫 hech narsa sezdirilmaydi).
    reason: ochiqda userga ko'rsatiladigan sabab; sirlida — faqat admin uchun izoh (userga ko'rsatilmaydi).
    Mavjud banni qayta qo'ysa — yangi muddat / rejim / sabab bilan almashtiriladi."""
    if mode not in BAN_MODES:
        raise ValueError(f"Noto'g'ri ban rejimi: {mode!r}. Faqat {BAN_MODES} qabul qilinadi.")
    if duration_minutes is not None and (isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int)
                                         or duration_minutes < 0):
        raise ValueError(f"duration_minutes manfiy bo'lmagan butun son yoki None bo'lishi shart: {duration_minutes!r}")
    reason = _clean_ban_reason(reason)
    register_user(user_id)
    now = get_uz_now()
    until = _wall_iso(now + datetime.timedelta(minutes=duration_minutes)) if duration_minutes else None
    with _managed_cursor() as (conn, c):
        c.execute(
            "UPDATE users SET is_banned = 1, banned_until = %s, ban_mode = %s, ban_reason = %s, banned_at = %s "
            "WHERE user_id = %s",
            (until, mode, reason, _wall_iso(now), user_id)
        )
        conn.commit()
        _ban_cache.invalidate(user_id)   # faqat muvaffaqiyatli commitdan keyin


def unban_user(user_id: int):
    """Foydalanuvchini bandan chiqarish. Premium, ballar va boshqa ma'lumotlarga TEGILMAYDI."""
    register_user(user_id)
    with _managed_cursor() as (conn, c):
        c.execute(
            "UPDATE users SET is_banned = 0, banned_until = NULL WHERE user_id = %s",
            (user_id,)
        )
        conn.commit()
        _ban_cache.invalidate(user_id)   # faqat muvaffaqiyatli commitdan keyin


def change_ban_duration(user_id: int, duration_minutes: int = None) -> bool:
    """HOZIR faol banning muddatini o'zgartiradi (rejim, sabab va qo'yilgan vaqt saqlanadi). duration_minutes=None —
    muddatsiz. True — o'zgardi; user banda emas (yoki muddati o'tgan) bo'lsa False."""
    if duration_minutes is not None and (isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int)
                                         or duration_minutes <= 0):
        raise ValueError(f"duration_minutes musbat butun son yoki None bo'lishi shart: {duration_minutes!r}")
    until = _wall_iso(get_uz_now() + datetime.timedelta(minutes=duration_minutes)) if duration_minutes else None
    with _managed_cursor() as (conn, c):
        c.execute("UPDATE users SET banned_until = %s WHERE user_id = %s AND " + BANNED_SQL,
                  (until, user_id, *not_banned_params()))
        changed = c.rowcount == 1
        conn.commit()
        _ban_cache.invalidate(user_id)
    return changed


def expire_finished_bans(now=None) -> list:
    """FON VAZIFASI: muddati o'tgan banlarni ATOMAR tozalaydi (bitta UPDATE ... RETURNING: parallel chaqiruvda har user
    faqat bitta chaqiruvga tushadi, shuning uchun xabar ikki marta ketmaydi). Qaytaradi: [(user_id, ban_mode)], ban_mode —
    'open' yoki 'silent' (NULL — eski ban — 'open'). ban_mode / ban_reason / banned_at tarix sifatida qoladi."""
    with _managed_cursor() as (conn, c):
        c.execute(
            "UPDATE users SET is_banned = 0, banned_until = NULL "
            "WHERE COALESCE(is_banned, 0) = 1 AND banned_until IS NOT NULL AND banned_until <= %s "
            "RETURNING user_id, ban_mode",
            not_banned_params(now)
        )
        rows = c.fetchall()
        conn.commit()
    for user_id, _mode in rows:
        _ban_cache.invalidate(user_id)
    return [(user_id, mode if mode in BAN_MODES else BAN_MODE_OPEN) for user_id, mode in rows]


def _ban_view(is_banned, banned_until, ban_mode, ban_reason, now=None):
    """Bazadagi ustunlardan ban holati: (info, ttl_sekund yoki None). info = {"banned", "mode", "until" (aware datetime |
    None — muddatsiz), "reason"}. Muddati o'tgan ban — "ban yo'q" (bazaga yozilmaydi). ban_mode NULL (eski ban) — 'open'.
    Muddat o'qilmasa — fail-closed: banda, lekin keshlanmaydi (ttl=None)."""
    free = {"banned": False, "mode": None, "until": None, "reason": None}
    if not is_banned:
        return free, _BanCache.MAX_TTL
    mode = ban_mode if ban_mode in BAN_MODES else BAN_MODE_OPEN
    reason = (ban_reason or None)
    if not banned_until:
        return {"banned": True, "mode": mode, "until": None, "reason": reason}, _BanCache.MAX_TTL
    try:
        # Bazadagi TIMESTAMP (zonasiz) qiymati Toshkent (UTC+5) devor soati; _to_uz_datetime shuni aware qiladi.
        until = _to_uz_datetime(banned_until)
        now = now or get_uz_now()
    except Exception:
        return {"banned": True, "mode": mode, "until": None, "reason": reason}, None
    if until <= now:
        return free, _BanCache.MAX_TTL
    return ({"banned": True, "mode": mode, "until": until, "reason": reason},
            min(_BanCache.MAX_TTL, (until - now).total_seconds()))


def _read_ban_state(user_id: int):
    """Qaytaradi: (ban_info, ttl_sekund yoki None). ttl=None - keshlanmaydi. FAQAT o'qiydi (hech narsa yozmaydi)."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT is_banned, banned_until, ban_mode, ban_reason FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    if not row:
        return {"banned": False, "mode": None, "until": None, "reason": None}, None
    return _ban_view(*row)


def get_ban_info(user_id: int) -> dict:
    """YAGONA ban o'qish funksiyasi (middleware, API, fon vazifalari, is_user_banned): {"banned": bool, "mode": None |
    'open' | 'silent', "until": aware datetime | None (muddatsiz), "reason": str | None}. Keshlanadi (<= 30 s, ban
    muddatidan oshmaydi); ban_user / unban_user keshni darhol bekor qiladi."""
    hit = _ban_cache.get(user_id)
    if hit is not None:
        # Yozuv faqat register_user() va DB o'qish muvaffaqiyatli bo'lgandan keyin yaratiladi.
        return dict(hit)

    epoch = _ban_cache.epoch()   # o'qishdan OLDIN olinadi (poyga himoyasi)
    register_user(user_id)
    info, ttl = _read_ban_state(user_id)
    if ttl:
        _ban_cache.put(user_id, info, ttl, epoch)   # DB xatosida bu yerga yetib kelinmaydi
    return dict(info)


def ban_message_text(info: dict) -> str:
    """is_user_banned uchun qisqa matn (eski chaqiruvchilar bilan mos)."""
    if not info["banned"]:
        return ""
    if info["until"]:
        return f"🚫 Vaqtinchalik ban muddati: {info['until'].strftime('%d.%m.%Y %H:%M')} gacha."
    return "🚫 Doimiy (muddatsiz) ban faol."


def is_user_banned(user_id: int) -> tuple:
    """
    Foydalanuvchi banlanganligini tekshirish (eski chaqiruvchilar uchun; mantiq get_ban_info da).
    Qaytaradi: (is_banned: bool, message: str)
    """
    info = get_ban_info(user_id)
    return info["banned"], ban_message_text(info)


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

        # Shartli UPDATE: parallel so'rovlardan faqat bittasi bonus oladi (P1-2)
        c.execute(
            "UPDATE users SET daily_streak = %s, last_checkin_date = %s, medicine_score = COALESCE(medicine_score, 0) + %s "
            "WHERE user_id = %s AND last_checkin_date IS DISTINCT FROM %s",
            (new_streak, today_str, points, user_id, today_str)
        )
        if c.rowcount == 0:
            conn.rollback()
            return False, 0, streak
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


# ═══════════════════════════════════════════════════════════════════
# OMAD BARABANI — sovrinlar jadvali (BITTA joyda)
# Kod = users.pending_spin_prize (INTEGER). app/app.js dagi `segments` AYNAN shu kodlar bilan mos bo'lishi shart
# (tests/test_spin_prizes.py ikkalasini solishtiradi). Ehtimollar yig'indisi 1.0.
#    1, 2, 3, 5  — shuncha ball
#   -2           — kun maslahati (ball yo'q)
#   -1           — +1 bepul AI savol (spin_ai_bonus)
#   -3           — 1 kunlik Premium Plus (ichki kod: pro — TIER_DISPLAY)
#    0           — SUPER: Premium Pro (30 kun; ichki kod: plus) uchun 50% chegirma
# ═══════════════════════════════════════════════════════════════════
SPIN_PRIZES = [
    (1, 0.35),
    (2, 0.20),
    (3, 0.12),
    (5, 0.05),
    (-2, 0.15),
    (-1, 0.10),
    (-3, 0.02),
    (0, 0.01),
]
SPIN_PRIZE_CODES = tuple(code for code, _ in SPIN_PRIZES)
SPIN_LEGACY_POINTS = 10          # eski baraban (1, 3, 5, 10, SUPER): bazada qolgan pending=10 o'zgartirilmasdan +10 ball beriladi
SPIN_TIPS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spin_tips.json")
_SPIN_TIP_FALLBACK = "Muhim raqamlar: 101 — yong'in, 102 — militsiya, 103 — tez yordam, 104 — gaz xizmati."
_spin_tips_cache = None


def normalize_spin_prize(code):
    """Bazadagi pending kodini haqiqiy sovrin kodiga keltiradi: jadvaldagi kodlar va eski 10 o'zgarmaydi,
    boshqa noma'lum qiymat -> 1 (+1 ball). None -> None."""
    if code is None:
        return None
    if code in SPIN_PRIZE_CODES or code == SPIN_LEGACY_POINTS:
        return code
    return 1


def spin_prize_type(code):
    """Frontend uchun sovrin turi: points / tip / ai / pro_day / super (None -> None)."""
    code = normalize_spin_prize(code)
    if code is None:
        return None
    return {0: "super", -1: "ai", -2: "tip", -3: "pro_day"}.get(code, "points")


def pick_spin_prize(rnd=None) -> int:
    """SPIN_PRIZES bo'yicha tasodifiy kod. rnd (0 <= rnd < 1) testlar uchun; berilmasa random.random()."""
    r = random.random() if rnd is None else rnd
    acc = 0.0
    for code, probability in SPIN_PRIZES:
        acc += probability
        if r < acc:
            return code
    return SPIN_PRIZES[-1][0]             # suzuvchi nuqta xatosi: oxirgi bo'lak


def load_spin_tips() -> list:
    """data/spin_tips.json dagi maslahatlar (bir marta o'qiladi). Fayl yo'q / buzuq bo'lsa — bitta zaxira maslahat."""
    global _spin_tips_cache
    if _spin_tips_cache is None:
        tips = []
        try:
            with open(SPIN_TIPS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                tips = [t.strip() for t in data if isinstance(t, str) and t.strip()]
        except (OSError, ValueError):
            logging.exception("spin_tips.json o'qilmadi: %s", SPIN_TIPS_PATH)
        _spin_tips_cache = tips or [_SPIN_TIP_FALLBACK]
    return _spin_tips_cache


def pick_spin_tip() -> str:
    return random.choice(load_spin_tips())


def _spin_result(ok, message, code=None, prize_type=None, points=0, tip=None) -> dict:
    return {"ok": ok, "message": message, "code": code, "prize_type": prize_type, "points": points, "tip": tip}


_SPIN_NO_PRIZE_MSG = "Sizda tasdiqlanmagan yutuq topilmadi yoki u allaqachon hisobingizga qo'shilgan! 🕒"
_PREMIUM_RANK = {"free": 0, "pro": 1, "plus": 2, "ultra": 3}


def _grant_spin_pro_day(c, user_id: int) -> str:
    """1 kunlik Premium (ichki kod pro, ko'rinadigan nom TIER_DISPLAY["pro"]) sovrini — claim tranzaksiyasi
    ICHIDA (commit/rollback chaqiruvchida). grant_premium_days faol muddatga qo'shadi va yuqori tarifni
    (ichki plus / ultra) saqlaydi, shuning uchun tarif pasaymaydi. Muddatsiz premium (is_premium=1, muddat NULL)
    uchun grant_premium_days "free" deb hisoblab, uni 1 kunlik tarif bilan ALMASHTIRIB yuborardi — bunday
    foydalanuvchiga tegilmaydi.
    Foydalanuvchiga ko'rsatiladigan HTML xabarni qaytaradi."""
    c.execute("SELECT is_premium, premium_expires_at, premium_type FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()
    is_premium, expires_at, premium_type = row if row else (0, None, None)

    if is_premium and not expires_at:
        return (f"⭐ Sizda muddatsiz Premium bor — 1 kunlik {TIER_DISPLAY['pro']} sovg'asi tarifingizni "
                "o'zgartirmadi, u saqlanib qoldi.")

    previous = "free"
    if expires_at:
        try:
            if _to_uz_datetime(expires_at) > get_uz_now():
                previous = premium_type if premium_type in _PREMIUM_RANK else "pro"
        except (ValueError, TypeError):
            previous = "free"

    grant_premium_days(user_id, 1, "pro", _cursor=c)

    if previous == "free":
        return (f"⭐ Tabriklaymiz! Siz Omad barabanidan <b>1 kunlik Premium {TIER_DISPLAY['pro']}</b> yutib oldingiz — "
                "u hozir faollashdi! 🎉")
    if previous == "pro":
        return f"⭐ Tabriklaymiz! Premium {TIER_DISPLAY['pro']} muddatingiz <b>1 kunga uzaytirildi</b>! 🎉"
    return (f"⭐ Tabriklaymiz! Premium {TIER_DISPLAY[previous]} muddatingiz <b>1 kunga uzaytirildi</b>. "
            "Tarifingiz o'zgarmadi. 🎉")


def claim_spin_prize(user_id: int) -> dict:
    """
    Barabandan yutilgan sovrinni hisobga qo'shadi. Sovrin FAQAT serverdagi pending_spin_prize dan olinadi
    (mijoz yuborgan hech narsa hisobga olinmaydi). Hamma tur uchun shartli
    `UPDATE ... WHERE pending_spin_prize IS NOT NULL` + rowcount tekshiruvi: parallel so'rovlarda ham sovrin
    aynan bir marta beriladi (P1-2). 1 kunlik Premium sovrini ham xuddi shu tranzaksiyada.

    Qaytaradi (dict): ok, message (bot uchun HTML), code (sovrin kodi), prize_type (points / tip / ai / pro_day / super),
    points (berilgan ball, ball bo'lmagan turlarda 0), tip (maslahat matni, faqat tip turida).
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
            return _spin_result(False, "Foydalanuvchi topilmadi!")

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
                    return _spin_result(False, f"Keyingi urinishgacha {hours:02d}:{minutes:02d}:{seconds:02d} vaqt qoldi. 🕒")
            except ValueError:
                # Fallback to old YYYY-MM-DD format
                if last_spin == now.date().isoformat():
                    return _spin_result(False, "Siz bugun barabanni aylantirib bo'ldingiz! Keyingi urinish ertaga. 🕒")

        if pending_prize is None:
            return _spin_result(False, _SPIN_NO_PRIZE_MSG)

        # Eski holat: pending=10 o'zgarmaydi (+10 ball); noma'lum qiymat -> +1 ball
        code = normalize_spin_prize(pending_prize)
        prize_type = spin_prize_type(code)
        points = code if prize_type == "points" else 0
        tip = pick_spin_tip() if prize_type == "tip" else None

        if prize_type == "super":
            # Super Prize: ichki plus (ko'rinadigan Pro) 30 kun uchun 50% chegirma, DISCOUNT_HOURS (24 soat) amal qiladi.
            # Chegirma allaqachon bor bo'lsa — muddat yangi 24 soatga suriladi. Narx — yagona plus_discount_price().
            plus_price_now = plus_price()
            discount_price = plus_discount_price(plus_price_now)
            discount_until = now + timedelta(hours=DISCOUNT_HOURS)
            sql = ("UPDATE users SET last_spin_date = %s, has_discount = 1, discount_expires_at = %s, "
                   "pending_spin_prize = NULL WHERE user_id = %s AND pending_spin_prize IS NOT NULL")
            params = (now_str, discount_until.isoformat(), user_id)
            msg = (
                "🎉 <b>Tabriklaymiz! Omad barabanidan SUPER PRIZ yutib oldingiz!</b> 🏆\n\n"
                f"🎁 Siz 30 kunlik <b>Premium {TIER_DISPLAY['plus']}</b> obunani {plus_price_now} Stars o'rniga "
                f"<b>atigi {discount_price} Stars</b> (50% chegirma) evaziga xarid qilish imkoniyatiga ega bo'ldingiz!\n\n"
                f"⏳ Taklif {DISCOUNT_HOURS} soat amal qiladi: {discount_until:%d.%m.%Y %H:%M} gacha.\n"
                "Chegirma bir martalik. Faollashtirish uchun:\n"
                "➡️ /premium (yoki quyidagi tugmani bosing)"
            )
        elif prize_type == "ai":
            sql = ("UPDATE users SET last_spin_date = %s, spin_ai_bonus = COALESCE(spin_ai_bonus, 0) + 1, "
                   "pending_spin_prize = NULL WHERE user_id = %s AND pending_spin_prize IS NOT NULL")
            params = (now_str, user_id)
            msg = (
                "🤖 Tabriklaymiz! Omad barabanidan <b>+1 bepul AI savol</b> yutib oldingiz!\n\n"
                "Uni AI tabida yoki botdagi AI suhbatda ishlatishingiz mumkin. Bonus savol muddatsiz saqlanadi."
            )
        elif prize_type == "tip":
            sql = ("UPDATE users SET last_spin_date = %s, pending_spin_prize = NULL "
                   "WHERE user_id = %s AND pending_spin_prize IS NOT NULL")
            params = (now_str, user_id)
            msg = f"💡 <b>Kun maslahati</b>\n\n{html.escape(tip, quote=False)}"
        elif prize_type == "pro_day":
            sql = ("UPDATE users SET last_spin_date = %s, pending_spin_prize = NULL "
                   "WHERE user_id = %s AND pending_spin_prize IS NOT NULL")
            params = (now_str, user_id)
            msg = None                          # premium holatiga qarab _grant_spin_pro_day beradi
        else:
            # Standard points
            sql = ("UPDATE users SET last_spin_date = %s, medicine_score = COALESCE(medicine_score, 0) + %s, "
                   "pending_spin_prize = NULL WHERE user_id = %s AND pending_spin_prize IS NOT NULL")
            params = (now_str, points, user_id)
            msg = f"Tabriklaymiz! Siz Omad barabanidan <b>+{points} ball</b> yutib oldingiz! 🎉"

        c.execute(sql, params)
        # Shartli UPDATE: yutuq parallel so'rovlarda faqat bir marta beriladi (P1-2). 1 kunlik Premium faqat shundan KEYIN.
        if c.rowcount == 0:
            conn.rollback()
            return _spin_result(False, _SPIN_NO_PRIZE_MSG)

        if prize_type == "pro_day":
            msg = _grant_spin_pro_day(c, user_id)
        conn.commit()

    # Automatically check if user qualifies for Premium upgrade
    if points > 0:
        check_and_grant_premium(user_id)

    result = _spin_result(True, msg, code, prize_type, points, tip)
    if prize_type == "super":
        # Yangi chegirma (qo'shimcha so'rovsiz): bot yutgan zahoti invoice tugmasini, Mini App taklif kartasini shundan chizadi
        result["discount"] = _discount_view(1, discount_until, now)
    return result


def check_and_grant_spin_bonus(user_id: int, client_points: int = 0) -> tuple:
    """
    Eski interfeys: (success, message). Hamma ish claim_spin_prize() da; mijoz bergan client_points e'tiborga olinmaydi.
    Mini App uchun to'liq natija (sovrin turi, ball, maslahat) — claim_spin_prize().
    """
    result = claim_spin_prize(user_id)
    return result["ok"], result["message"]


# ═══════════════════════════════════════════════════════════════════
# SUPER PRIZ CHEGIRMASI: Pro (ichki plus, 30 kun) -50%, DISCOUNT_HOURS (24 soat) amal qiladi, bir martalik.
# Yagona manba — get_discount_info; has_discount unga tayanadi. Muddati o'tgan chegirma o'qishda "faol emas"
# (bazaga yozilmaydi). Narx FAQAT plus_price() / plus_discount_price() dan (ikkinchi formula yo'q).
# ═══════════════════════════════════════════════════════════════════
DISCOUNT_HOURS = 24


def plus_price() -> int:
    """Ichki plus (ko'rinadigan Pro) 30 kunlik oddiy narxi (Stars). env: PRO_MONTHLY_STARS (standart 150)."""
    return int(os.getenv("PRO_MONTHLY_STARS", "150"))


def plus_discount_price(price: int = None) -> int:
    """Chegirmali narx: oddiy narxning 50% i (yuqoriga yaxlitlanadi, kamida 1 Stars). YAGONA formula: bot.py ham,
    to'lov tekshiruvi ham, SUPER PRIZ xabari ham, API ham shuni ishlatadi."""
    price = plus_price() if price is None else price
    return max(1, (price + 1) // 2)


def migrate_discount_expiry(c, now=None) -> int:
    """Bir martalik migratsiya (init_db ichida, idempotent): has_discount = 1 va muddat yo'q bo'lgan userlarga shu
    paytdan 24 soat beriladi. Ikkinchi marta ishlaganda hech narsani o'zgartirmaydi (muddat allaqachon qo'yilgan).
    Qaytaradi: o'zgargan qatorlar soni."""
    until = ((now or get_uz_now()) + datetime.timedelta(hours=DISCOUNT_HOURS)).isoformat()
    c.execute("UPDATE users SET discount_expires_at = %s WHERE has_discount = 1 AND discount_expires_at IS NULL", (until,))
    count = c.rowcount
    return count if isinstance(count, int) and count > 0 else 0


def _discount_view(has_flag, expires_raw, now=None) -> dict:
    """Bazadagi ustunlardan chegirma holati. active = has_discount = 1 VA discount_expires_at > hozir.
    {"active", "expires_at" (aware datetime | None — faqat faol bo'lsa), "seconds_left" (int), "price", "old_price"}."""
    old_price = plus_price()
    info = {"active": False, "expires_at": None, "seconds_left": 0, "price": plus_discount_price(old_price),
            "old_price": old_price}
    if not has_flag or not expires_raw:
        return info
    try:
        expires = _to_uz_datetime(expires_raw)
    except (ValueError, TypeError):
        return info
    now = now or get_uz_now()
    if expires <= now:
        return info
    info.update(active=True, expires_at=expires, seconds_left=int((expires - now).total_seconds()))
    return info


def get_discount_info(user_id: int, now=None) -> dict:
    """SUPER PRIZ chegirmasi holati — YAGONA o'qish funksiyasi: {"active", "expires_at", "seconds_left", "price",
    "old_price"}. Muddati o'tgan chegirma "active": False (bazaga yozilmaydi). Foydalanuvchi yo'q — faol emas."""
    with _managed_cursor() as (conn, c):
        c.execute("SELECT has_discount, discount_expires_at FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    if not row:
        return _discount_view(0, None, now)
    return _discount_view(row[0], row[1], now)


def has_discount(user_id: int) -> bool:
    """Foydalanuvchida FAOL (muddati o'tmagan) SUPER PRIZ chegirmasi bormi (get_discount_info ga tayanadi)."""
    try:
        return bool(get_discount_info(user_id)["active"])
    except Exception:
        logging.error("has_discount: chegirma holatini o'qib bo'lmadi (user=%s)", user_id, exc_info=True)
        return False


def consume_discount(user_id: int) -> None:
    """Consumes the super prize discount"""
    with _managed_cursor() as (conn, c):
        try:
            c.execute("UPDATE users SET has_discount = 0, discount_expires_at = NULL WHERE user_id = %s", (user_id,))
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
    Returns the prize CODE (SPIN_PRIZES: 1, 2, 3, 5 ball; -2 maslahat; -1 AI savol; -3 1 kunlik Premium; 0 SUPER)
    if eligible, or None if cooldown is active / user not found.
    """
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
            return normalize_spin_prize(pending_prize)

        # Generate new prize: SPIN_PRIZES jadvali bo'yicha (app.js segments bilan bir xil kodlar)
        prize = pick_spin_prize()

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
