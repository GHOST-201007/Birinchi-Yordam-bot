from aiohttp import web
import asyncio
import os
import logging
import re
import html
import json
import hashlib
import hmac
import urllib.parse
import math
from datetime import datetime, time as dtime, timedelta, timezone  # dtime: pastdagi `import time` moduli bilan to'qnashmasin (P2-2)
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    LabeledPrice, ContentType, TelegramObject
)
from typing import Callable, Dict, Any, Awaitable
import time
import uuid

class KeepTyping:
    def __init__(self, bot: Bot, chat_id: int, action: str = "typing", interval: float = 4.0):
        self.bot = bot
        self.chat_id = chat_id
        self.action = action
        self.interval = interval
        self.task = None

    async def _loop(self):
        while True:
            try:
                await self.bot.send_chat_action(chat_id=self.chat_id, action=self.action)
            except Exception as e:
                logging.exception("Failed to send chat action in KeepTyping loop")
            await asyncio.sleep(self.interval)

    async def __aenter__(self):
        self.task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

class ThrottlingMiddleware(BaseMiddleware):
    # Lug'atlar cheksiz o'smasligi uchun: har CLEANUP_EVERY ta yozuvdan keyin
    # STALE_AFTER soniyadan eski yozuvlar o'chiriladi (P2-9)
    CLEANUP_EVERY = 1000
    STALE_AFTER = 60.0

    def __init__(self, cooldown: float = 1.0):
        self.cooldown = cooldown
        self.last_requests = {}
        self.last_warnings = {}
        self._writes_since_cleanup = 0
        super().__init__()

    def _maybe_cleanup(self, now: float) -> None:
        self._writes_since_cleanup += 1
        if self._writes_since_cleanup < self.CLEANUP_EVERY:
            return
        self._writes_since_cleanup = 0
        cutoff = now - self.STALE_AFTER
        for store in (self.last_requests, self.last_warnings):
            for uid in [uid for uid, ts in store.items() if ts < cutoff]:
                del store[uid]

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            user_id = user.id
            now = time.time()
            last_time = self.last_requests.get(user_id, 0)
            
            if now - last_time < self.cooldown:
                # Limit exceeded
                last_warn = self.last_warnings.get(user_id, 0)
                if now - last_warn > 3.0:
                    self.last_warnings[user_id] = now
                    if isinstance(event, types.Message):
                        try:
                            await event.answer(
                                "⚠️ <b>Iltimos, shoshilmang!</b> Bot faoliyatini himoya qilish uchun so'rovlar oralig'i kamida 1 soniya bo'lishi kerak. 🕒",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logging.exception("Failed to send throttling warning message for Message")
                    elif isinstance(event, types.CallbackQuery):
                        try:
                            await event.answer("⚠️ Iltimos, shoshilmang! Biroz kuting. 🕒", show_alert=True)
                        except Exception as e:
                            logging.exception("Failed to send throttling warning message for CallbackQuery")
                elif isinstance(event, types.CallbackQuery):
                    # Ogohlantirish cooldown'da ham spinner qotib qolmasligi uchun jim javob beramiz
                    try:
                        await event.answer()
                    except Exception:
                        logging.warning("Failed to answer throttled CallbackQuery", exc_info=True)
                return # Stop processing
                
            self.last_requests[user_id] = now
            self._maybe_cleanup(now)
        return await handler(event, data)

class BanMiddleware(BaseMiddleware):
    ERROR_ALERT_COOLDOWN = 30.0
    ERROR_MAP_MAX = 2000

    def __init__(self):
        self._last_error_alert = {}
        super().__init__()

    async def _notify_db_error(self, event: TelegramObject, user_id: int):
        """DB xatosida: CallbackQuery doim javob oladi; alert/xabar faqat cooldown o'tganda."""
        now = time.monotonic()
        last = self._last_error_alert.get(user_id)
        allow_alert = last is None or now - last >= self.ERROR_ALERT_COOLDOWN
        if allow_alert:
            if len(self._last_error_alert) >= self.ERROR_MAP_MAX:
                self._last_error_alert.clear()
            self._last_error_alert[user_id] = now
        text = "⚠️ Vaqtinchalik texnik xatolik. Iltimos, birozdan so'ng qayta urinib ko'ring."
        try:
            if isinstance(event, types.CallbackQuery):
                if allow_alert:
                    await event.answer(text, show_alert=True)
                else:
                    await event.answer()
            elif isinstance(event, types.Message) and allow_alert:
                await event.answer(text)
        except Exception:
            logging.warning("Failed to notify user about ban-check DB error", exc_info=True)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            try:
                is_banned, ban_msg = await asyncio.to_thread(database.is_user_banned, user.id)
            except Exception:
                logging.exception("Ban check failed for user %s; blocking update (fail-closed)", user.id)
                await self._notify_db_error(event, user.id)
                return  # handler chaqirilmaydi
            if is_banned:
                contact_info = f"Murojaat uchun: @{ADMIN_USERNAME}" if (ADMIN_USERNAME and ADMIN_USERNAME != "YOUR_ADMIN_USERNAME") else "Murojaat uchun administratorga yozing."
                if isinstance(event, types.Message):
                    await event.answer(
                        f"❌ <b>Siz botdan foydalanishdan chetlashtirilgansiz (Banned)!</b>\n\n"
                        f"{ban_msg}\n\n"
                        f"⚠️ {contact_info}",
                        parse_mode="HTML"
                    )
                elif isinstance(event, types.CallbackQuery):
                    await event.answer(
                        f"Siz bloklangansiz.\n{ban_msg}",
                        show_alert=True
                    )
                return
        return await handler(event, data)

class AnswerCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        result = await handler(event, data)
        if isinstance(event, types.CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        return result

class FsmResetMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, types.Message) and event.text:
            skip_texts = [
                "📋 Holatlar ro'yxati", "🚨 Favqulodda raqamlar",
                "📚 Kasalliklar", "💬 AI Konsultatsiya", "💬 AI Konsultatsiya (Chat)",
                "🏥 Yaqin kasalxona", "💎 Premium",
                "👤 Tibbiy Profilim", "💊 Dori Eslatmalari",
                "⚖️ Sog'liq Kalkulyatori", "🔔 Kunlik Maslahatlar",
                "👥 Do'stlarni taklif qilish", "🌐 Mening ballarim",
                "📣 Reklama"
            ]
            if event.text in skip_texts or event.text.startswith('/'):
                state = data.get("state")
                if state:
                    await state.clear()
        return await handler(event, data)

    # DailyBonusMiddleware has been removed
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

# Ma'lumotlarni import qilamiz
from data import FIRST_AID_DATA, DISEASES
import database
import medicine_db

# ═══════════════════════════════════════════════════════════════════
# MARKDOWN → HTML CONVERTER
# ═══════════════════════════════════════════════════════════════════

def markdown_to_html(text: str) -> str:
    """Markdown formatidagi matnni Telegram HTML formatiga xavfsiz o'tkazish"""
    if not text:
        return ""
    text = html.escape(text)
    code_blocks = []
    def save_code_block(match):
        code = match.group(1)
        code_blocks.append(code)
        return f"___CODE_BLOCK_{len(code_blocks)-1}___"
    text = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\n?(.*?)\n?```', save_code_block, text, flags=re.DOTALL)
    inline_codes = []
    def save_inline_code(match):
        code = match.group(1)
        inline_codes.append(code)
        return f"___INLINE_CODE_{len(inline_codes)-1}___"
    text = re.sub(r'`(.*?)`', save_inline_code, text)
    text = re.sub(r'^#{1,6}\s+(.*?)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
    text = re.sub(r'\*(?!\s)([^\*]+?)(?<!\s)\*', r'<i>\1</i>', text)
    text = re.sub(r'(^|\s)_(?!\s)([^_]+?)(?<!\s)_(?=$|\s|[.,!?;:])', r'\1<i>\2</i>', text)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    for i, code in enumerate(inline_codes):
        text = text.replace(f"___INLINE_CODE_{i}___", f"<code>{code}</code>")
    for i, code in enumerate(code_blocks):
        text = text.replace(f"___CODE_BLOCK_{i}___", f"<pre>{code}</pre>")
    return text


TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def chunk_text(text: str, max_len: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Uzun matnni Telegram limiti (4096 belgi) bo'yicha xavfsiz bo'laklarga ajratadi."""
    if max_len <= 0:
        raise ValueError("max_len musbat bo'lishi kerak")
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > max_len:
        window = remaining[:max_len]
        split_idx = window.rfind("\n\n")
        sep_len = 2
        if split_idx <= 0:
            split_idx = window.rfind("\n")
            sep_len = 1
        if split_idx <= 0:
            split_idx = window.rfind(" ")
            sep_len = 1
        if split_idx <= 0:
            split_idx = max_len
            sep_len = 0

        chunks.append(remaining[:split_idx])
        remaining = remaining[split_idx + sep_len:]

    if remaining:
        chunks.append(remaining)
    return chunks


def _is_not_modified_error(exc: Exception) -> bool:
    """Telegram 'message is not modified': matn allaqachon ko'rinib turibdi (yetkazilgan hisoblanadi)."""
    return "message is not modified" in str(exc).lower()


def _is_ambiguous_send_error(exc: Exception) -> bool:
    """Telegram xabarni qabul qilgan-qilmaganini bilib bo'lmaydigan xatolar (timeout/tarmoq/5xx).
    Bunday holatda qayta yuborilmaydi (dublikat xavfi)."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    try:
        from aiogram.exceptions import TelegramNetworkError, TelegramServerError
        if isinstance(exc, (TelegramNetworkError, TelegramServerError)):
            return True
    except Exception:
        pass
    low = str(exc).lower()
    return "timed out" in low or "timeout" in low


async def _send_piece(send_fn, html_text, plain_text) -> str:
    """Bitta xabar bo'lagini yuboradi: avval HTML (agar berilgan bo'lsa), aniq rad etilsa plain-text.
    Qaytaradi: 'ok' | 'ambiguous'. Ikkala urinish ham aniq rad etilsa, oxirgi istisnoni ko'taradi."""
    if html_text is not None:
        try:
            await send_fn(html_text, parse_mode="HTML")
            return "ok"
        except Exception as e:
            if _is_not_modified_error(e):
                return "ok"
            if _is_ambiguous_send_error(e):
                logging.warning(f"Yuborish natijasi noaniq (HTML), qayta yuborilmaydi: {e}")
                return "ambiguous"
            logging.warning(f"HTML yuborish rad etildi, plain-text fallback: {e}")
    try:
        await send_fn(plain_text, parse_mode=None)
        return "ok"
    except Exception as e:
        if _is_not_modified_error(e):
            return "ok"
        if _is_ambiguous_send_error(e):
            logging.warning(f"Yuborish natijasi noaniq (plain), qayta yuborilmaydi: {e}")
            return "ambiguous"
        raise


def _build_ai_pieces(ai_text: str, html_prefix: str, plain_prefix: str):
    """AI matnini (html, plain) juftliklariga ajratadi; har bir yuboriladigan matn <= 4096.
    html=None bo'lsa, bo'lak faqat plain-text sifatida yuboriladi."""
    limit = TELEGRAM_MAX_MESSAGE_LENGTH
    full_html = html_prefix + markdown_to_html(ai_text)
    full_plain = plain_prefix + ai_text
    if len(full_html) <= limit:
        return [(full_html, full_plain if len(full_plain) <= limit else None)]
    # Matn HTML ga o'tgach (escape: & < > kengayadi) limitdan oshadi -> HTML uzunligi tekshirilgan holda bo'laklaymiz
    for size in (4000, 2000, 1000, 500):
        raw_chunks = chunk_text(ai_text, max_len=size)
        pieces = []
        for idx, raw in enumerate(raw_chunks):
            h = (html_prefix if idx == 0 else "") + markdown_to_html(raw)
            p = (plain_prefix if idx == 0 else "") + raw
            pieces.append((h, p))
        if all(len(h) <= limit for h, _ in pieces):
            return pieces
    pieces = []
    for idx, raw in enumerate(chunk_text(ai_text, max_len=limit - len(plain_prefix))):
        pieces.append((None, (plain_prefix if idx == 0 else "") + raw))
    return pieces


async def _deliver_ai_response(message, status_msg, ai_text: str, html_prefix: str, plain_prefix: str) -> str:
    """Tayyor AI javobini Telegram'ga yetkazadi (1-bo'lak status_msg.edit_text, qolganlari message.answer).
    Qaytaradi:
      'delivered' - hammasi yuborildi (yoki 'message is not modified' - allaqachon ko'rinib turibdi);
      'ambiguous' - birinchi yuborish natijasi noaniq (timeout); qayta yuborilmaydi;
      'partial'   - kamida bitta bo'lak yuborilgan, keyingisi muvaffaqiyatsiz; foydalanuvchiga ogohlantirish;
      'failed'    - hech narsa yetkazilmagan (aniq rad etilgan).
    Kvota siyosati: faqat 'failed' holatida chaqiruvchi limitni qaytaradi; 'delivered', 'ambiguous' va
    'partial' holatlarida foydalanuvchi javobni (qisman) olgan bo'lishi mumkin, shuning uchun refund qilinmaydi."""
    pieces = _build_ai_pieces(ai_text, html_prefix, plain_prefix)
    sent = 0
    for idx, (h, p) in enumerate(pieces):
        send_fn = status_msg.edit_text if idx == 0 else message.answer
        try:
            result = await _send_piece(send_fn, h, p)
        except Exception as e:
            logging.warning(f"Telegram yuborish xatosi (bo'lak #{idx}): {e}")
            result = "failed"
        if result == "ok":
            sent += 1
            continue
        if idx == 0:
            return "ambiguous" if result == "ambiguous" else "failed"
        try:
            await message.answer("⚠️ Javobning davomi yuborilmadi. Savolingizni qisqaroq qilib qayta yuborib ko'ring.")
        except Exception as notice_err:
            logging.warning(f"Qisman yuborish ogohlantirishi yuborilmadi: {notice_err}")
        return "partial"
    return "delivered"

# ═══════════════════════════════════════════════════════════════════
# ASOSIY SOZLAMALAR
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
load_dotenv()

TOKEN          = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
logging.info(f"GEMINI_API_KEY configured: {'YES' if GEMINI_API_KEY else 'NO'}")
logging.info(f"GEMINI_API_KEY placeholder: {'YES' if GEMINI_API_KEY == 'YOUR_GEMINI_API_KEY_HERE' else 'NO'}")
# Safely parse ADMIN_ID – abort on non‑numeric values, warn on zero/negative IDs
def _parse_admin_id(value: str) -> int:
    try:
        admin_id = int(value)
        logging.info(f"ADMIN_ID set to {admin_id}")
    except ValueError:
        import sys
        logging.error("ADMIN_ID must be a numeric integer; aborting startup.")
        sys.exit(1)
    if admin_id <= 0:
        logging.warning(f"ADMIN_ID set to {admin_id}; admin‑only commands will be disabled.")
    return admin_id

ADMIN_ID = _parse_admin_id(os.getenv("ADMIN_ID", "0"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "YOUR_ADMIN_USERNAME")
CARD_NUMBER = os.getenv("CARD_NUMBER", "")
CARD_NAME = os.getenv("CARD_NAME", "")
MINI_APP_URL        = os.getenv("MINI_APP_URL", "")
PREMIUM_STARS_PRICE = int(os.getenv("PREMIUM_STARS_PRICE", "50"))  # Stars narxi (default: 50 ⭐)

STARS_CURRENCY = "XTR"
STARS_PROVIDER_TOKEN = ""  # Telegram Stars uchun provider_token doim bo'sh bo'lishi shart

INIT_DATA_MAX_AGE = 24 * 3600   # auth_date shundan eski bo'lmasligi kerak
INIT_DATA_FUTURE_SKEW = 60      # soat farqi uchun yo'l qo'yiladigan "kelajak" (soniya)


def parse_init_data(init_data, bot_token: str | None = None, now: float | None = None) -> dict | None:
    """Telegram WebApp initData ni tekshiradi (Mini App /api/ endpointlari uchun).

    Muvaffaqiyatli bo'lsa tekshirilgan foydalanuvchi dict'ini ({"id": ..., "first_name": ...}),
    aks holda None qaytaradi. Hech qachon istisno ko'tarmaydi va init_data ni loglamaydi
    (ichida foydalanuvchi ma'lumoti va hash bor).

    Tekshiruvlar:
      * HMAC-SHA256, secret_key = HMAC("WebAppData", BOT_TOKEN), hmac.compare_digest bilan;
      * auth_date kelajakda emas (+60 s) va 24 soatdan eski emas;
      * user — JSON, ichida musbat butun son `id`.
    user_id FAQAT shu funksiya qaytargan qiymatdan olinadi.
    """
    try:
        token = TOKEN if bot_token is None else bot_token
        if not token or not isinstance(init_data, str) or not init_data:
            return None

        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = {}
        for key, value in pairs:
            if key in fields:        # takroriy kalit — shubhali
                return None
            fields[key] = value

        received_hash = fields.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
        expected = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected.encode("ascii"), received_hash.encode("utf-8")):
            return None

        auth_ts = int(fields.get("auth_date", ""))
        current = time.time() if now is None else now
        if auth_ts > current + INIT_DATA_FUTURE_SKEW:
            return None
        if current - auth_ts > INIT_DATA_MAX_AGE:
            return None

        user = json.loads(fields.get("user", ""))
        if not isinstance(user, dict):
            return None
        uid = user.get("id")
        if isinstance(uid, bool) or not isinstance(uid, int) or uid <= 0:
            return None
        return user
    except Exception:
        return None


def get_stars_tariffs() -> dict:
    """Stars tariflari: payload -> (premium_type, days, title, stars_price).
    Narxlar avvalgidek env'dan chaqiruv paytida o'qiladi (PRO_TRIAL_STARS, PRO_MONTHLY_STARS, ULTRA_MONTHLY_STARS)."""
    plus_price = int(os.getenv("PRO_MONTHLY_STARS", "150"))
    return {
        "PRO_7_DAYS": ("pro", 7, "⭐ Premium Pro (7 kun)", int(os.getenv("PRO_TRIAL_STARS", "50"))),
        "PLUS_30_DAYS": ("plus", 30, "💎 Premium Plus (30 kun)", plus_price),
        "ULTRA_30_DAYS": ("ultra", 30, "👑 Premium Ultra (30 kun)", int(os.getenv("ULTRA_MONTHLY_STARS", "300"))),
        # Omad barabani SUPER PRIZ: Plus 30 kun 50% chegirma bilan (bir martalik, has_discount=1 bo'lsa)
        DISCOUNT_PAYLOAD: ("plus", 30, "🎁 Premium Plus (30 kun, 50% chegirma)", plus_discount_price(plus_price)),
    }


DISCOUNT_PAYLOAD = "PLUS_30_DAYS_DISCOUNT"


def plus_discount_price(plus_price: int | None = None) -> int:
    """Plus 30 kun narxining 50% i (yuqoriga yaxlitlanadi, kamida 1 Stars)."""
    if plus_price is None:
        plus_price = int(os.getenv("PRO_MONTHLY_STARS", "150"))
    return max(1, (plus_price + 1) // 2)


def discount_plus_offer() -> tuple:
    """SUPER PRIZ chegirmali Premium Plus (30 kun) taklifi: (title, desc, payload, stars).
    Inline tugma (buy_plus_30_discount) ham, ?start=buy_plus_30 deep link ham SHU funksiyadan foydalanadi."""
    return (
        "🎁 Premium Plus — 30 kun (50% chegirma)",
        "Omad barabani SUPER PRIZ: 30 kunlik Premium Plus obuna yarim narxda.",
        DISCOUNT_PAYLOAD,
        plus_discount_price(),
    )


# Eski payload: hech qayerda yaratilmaydi, lekin ilgari yuborilgan invoice'lar uchun saqlanadi.
# Git tarixidan (all_git_history_utf8.txt):
# 1) stars_premium_1month: currency="XTR", narxi dinamik (chegirma bilan 20 XTR yoki PREMIUM_STARS_PRICE env, default 50 XTR)
#    bo'lgani uchun yagona statik narxni taxmin qilmasdan XTR valyuta va musbat butun summa tekshiriladi.
LEGACY_STARS_PAYLOADS = {"stars_premium_1month": ("pro", 30, "⭐ Premium Pro (30 kun)")}

def validate_payment(payload: str, currency: str, total_amount: int):
    """To'lov parametrlarini tekshiradi. Returns (ok: bool, reason: str)."""
    tariffs = get_stars_tariffs()
    if payload in tariffs:
        if currency != STARS_CURRENCY:
            return False, "currency"
        if isinstance(total_amount, bool) or not isinstance(total_amount, int) or total_amount != tariffs[payload][3]:
            return False, "amount"
        return True, ""
    if payload in LEGACY_STARS_PAYLOADS:
        if currency != STARS_CURRENCY:
            return False, "currency"
        if isinstance(total_amount, bool) or not isinstance(total_amount, int) or total_amount <= 0:
            return False, "amount"
        return True, ""
    return False, "payload"


def check_premium_purchase_eligibility(user_info: dict, action: str) -> tuple[bool, str | None]:
    """
    Foydalanuvchining tarif xarid qilish huquqini tekshiradi (/start va inline tugmalar uchun bir xil).
    Mavjud mahsulot siyosati bo'yicha: agar foydalanuvchida faol premium bo'lsa va
    joriy tarifi sotib olinayotgan tarifdan yuqoriroq yoki teng bo'lsa (current_rank >= buying_rank),
    xarid to'xtatiladi. Faqat yuqoriroq tarifga upgrade qilishga ruxsat etiladi.
    """
    current_type = user_info.get("premium_type", "free") if user_info else "free"
    is_premium = user_info.get("is_premium", 0) if user_info else 0
    tier_rank = {"free": 0, "pro": 1, "plus": 2, "ultra": 3}
    buying_tier = {
        "buy_pro_7": "pro", "buy_plus_30": "plus", "buy_plus_30_discount": "plus",
        "buy_ultra_30": "ultra", "pay_stars": "pro",
    }.get(action, "pro")
    current_rank = tier_rank.get(current_type, 0) if is_premium else 0
    buying_rank = tier_rank.get(buying_tier, 1)

    if is_premium and current_rank >= buying_rank:
        tier_names = {"pro": "Premium Pro", "plus": "Premium Plus", "ultra": "Premium Ultra"}
        return False, tier_names.get(current_type, "Premium")
    return True, None


# Parallel/takroriy AI va engagement so'rovlarini to'xtatuvchi in-flight to'plamlar
_active_ai_users = set()
_in_progress_engagements = set()

# DB xatosi tufayli saqlanmay qolgan, ammo Telegram tomonidan tasdiqlangan haqiqiy to'lovlar
_pending_failed_payments: dict = {}
_PENDING_RECONCILE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending_reconcile.db")


def _init_reconcile_db(raise_on_error: bool = False) -> bool:
    conn = None
    try:
        import sqlite3
        conn = sqlite3.connect(_PENDING_RECONCILE_DB, timeout=10.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_reconciliations (
                charge_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                payload TEXT NOT NULL,
                stars INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Pending reconcile DB yaratishda xato: {e}")
        if raise_on_error:
            raise
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def record_failed_payment(charge_id: str, user_id: int, payload: str, stars: int) -> bool:
    """Faqat Telegram tomonidan yuborilgan haqiqiy to'lov DB ga yozilmay qolganda chaqiriladi.
    Returns True FAQAT persistent SQLite yozuvi muvaffaqiyatli yakunlanganda; aks holda False."""
    now_str = datetime.now().isoformat()
    conn = None
    try:
        import sqlite3
        _init_reconcile_db(raise_on_error=True)
        conn = sqlite3.connect(_PENDING_RECONCILE_DB, timeout=10.0)
        conn.execute("""
            INSERT OR REPLACE INTO pending_reconciliations
            (charge_id, user_id, payload, stars, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (charge_id, user_id, payload, stars, now_str))
        conn.commit()
        _pending_failed_payments[charge_id] = {
            "user_id": user_id,
            "payload": payload,
            "stars": stars,
            "created_at": now_str
        }
        return True
    except Exception as e:
        _pending_failed_payments.pop(charge_id, None)
        logging.critical(f"Pending reconcile DB ga yozishda xato (charge_id={charge_id}): {e}", exc_info=True)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_pending_failed_payment(charge_id: str) -> dict | None:
    if charge_id in _pending_failed_payments:
        return _pending_failed_payments[charge_id]
    conn = None
    cur = None
    try:
        import sqlite3
        _init_reconcile_db()
        conn = sqlite3.connect(_PENDING_RECONCILE_DB, timeout=10.0)
        cur = conn.cursor()
        cur.execute("SELECT user_id, payload, stars, created_at FROM pending_reconciliations WHERE charge_id = ?", (charge_id,))
        row = cur.fetchone()
        if row:
            res = {"user_id": row[0], "payload": row[1], "stars": row[2], "created_at": row[3]}
            _pending_failed_payments[charge_id] = res
            return res
    except Exception as e:
        logging.warning(f"Pending reconcile DB dan o'qishda xato: {e}")
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return None


def remove_pending_failed_payment(charge_id: str):
    _pending_failed_payments.pop(charge_id, None)
    conn = None
    try:
        import sqlite3
        _init_reconcile_db()
        conn = sqlite3.connect(_PENDING_RECONCILE_DB, timeout=10.0)
        conn.execute("DELETE FROM pending_reconciliations WHERE charge_id = ?", (charge_id,))
        conn.commit()
    except Exception as e:
        logging.warning(f"Pending reconcile DB dan o'chirishda xato: {e}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_all_pending_failed_payments() -> list:
    items = []
    conn = None
    cur = None
    try:
        import sqlite3
        _init_reconcile_db()
        conn = sqlite3.connect(_PENDING_RECONCILE_DB, timeout=10.0)
        cur = conn.cursor()
        cur.execute("SELECT charge_id, user_id, payload, stars, created_at FROM pending_reconciliations ORDER BY created_at DESC")
        for row in cur.fetchall():
            items.append({
                "charge_id": row[0],
                "user_id": row[1],
                "payload": row[2],
                "stars": row[3],
                "created_at": row[4]
            })
    except Exception as e:
        logging.warning(f"Pending reconcile DB ro'yxatini olishda xato: {e}")
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    if not items and _pending_failed_payments:
        for cid, data in _pending_failed_payments.items():
            items.append({"charge_id": cid, **data})
    return items




# ═══════════════════════════════════════════════════════════════
# ILOVA VERSIYASI
# Muhim yangilashlar bo'lganda shu raqamni oshiring.
# Bu versiya Mini App URL parametri sifatida ishlatiladi.
# ═══════════════════════════════════════════════════════════════
APP_VERSION = "1.1.0"

# ═══════════════════════════════════════════════════════════════
# AI TA'MIR REJIMI
# AI ni vaqtincha o'chirish uchun: AI_MAINTENANCE = True
# AI ni yoqish uchun: AI_MAINTENANCE = False
# ═══════════════════════════════════════════════════════════════
AI_MAINTENANCE = os.getenv("AI_MAINTENANCE", "false").lower() == "true"

AI_MAINTENANCE_MSG = (
    "⚙️ <b>AI xizmati vaqtincha to'xtatildi.</b>\n\n"
    "Texnik yangilanish davom etmoqda... 🔄\n\n"
    "⏳ Tez orada yana ishga tushadi. Sabr qilganingiz uchun rahmat!"
)


if not TOKEN or TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    raise ValueError("Iltimos, .env fayliga haqiqiy BOT_TOKEN ni kiriting!")

# Gemini AI sozlamalari
gemini_client = None
gemini_client_initialized = False
if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=genai_types.HttpOptions(
                retry_options=genai_types.HttpRetryOptions(attempts=1)
            ),
        )
        gemini_client_initialized = True
    except Exception as e:
        logging.error(f"Gemini client initialization failure: {e}")
        try:
            gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            gemini_client_initialized = True
        except Exception as e2:
            logging.error(f"Fallback Gemini client init failed: {e2}")
            gemini_client = None
logging.info(f"Gemini client initialized: {'YES' if gemini_client_initialized else 'NO'}")

bot = Bot(token=TOKEN)
dp  = Dispatcher(storage=MemoryStorage())  # FSM uchun MemoryStorage

# ═══════════════════════════════════════════════════════════════════
# FSM STATES (Feature 1: Tibbiy profil, Feature 2: Eslatma)
# ═══════════════════════════════════════════════════════════════════

class MedicalProfileStates(StatesGroup):
    blood_group       = State()
    age               = State()
    weight            = State()
    height            = State()
    chronic_diseases  = State()
    allergies         = State()

class ReminderStates(StatesGroup):
    medicine_name = State()
    times         = State()
    days          = State()  # 'daily' yoki 'every_other'

class BmiStates(StatesGroup):
    weight = State()
    height = State()

class WaterStates(StatesGroup):
    weight = State()

class AiChatStates(StatesGroup):
    chatting = State()

class PaymentStates(StatesGroup):
    waiting_for_receipt = State()

class BroadcastStates(StatesGroup):
    waiting_for_content = State()
    waiting_for_confirmation = State()

# ═══════════════════════════════════════════════════════════════════
# GEMINI AI
# ═══════════════════════════════════════════════════════════════════

GEMINI_SYSTEM_INSTRUCTION = (
    "Siz o'zbek tilida gaplashadigan Birinchi Yordam va Salomatlik bo'yicha aqlli sun'iy intellekt yordamchisiz. "
    "Foydalanuvchilarga favqulodda vaziyatlarda birinchi yordam ko'rsatish, salomatlik, foydali ovqatlar, vitaminlar "
    "va shifobaxsh mashqlar haqida batafsil va to'g'ri maslahatlar bering. "
    "QAT'IY QOIDA: Dori nomi va dozasini mutlaqo tavsiya qilmang! Foydalanuvchini farmatsevt yoki shifokorga yo'naltiring. "
    "Agar savol tibbiyot yoki salomatlikka aloqador bo'lmasa, muloyimlik bilan faqat salomatlik va birinchi yordamga oid savollarga javob berishingizni ayting. "
    "Har doim javoblaringiz oxirida, zarur bo'lsa, shifokor bilan maslahatlashishni va jiddiy holatlarda 103 ga qo'ng'iroq qilishni eslatib o'ting."
)

# Real API testi (2026-10-03): gemini-3.5-flash birinchi so'rovdayoq 4/4 muvaffaqiyatli (~4-5s);
# gemini-3.8-flash / 3.7-flash -> 503 UNAVAILABLE; gemini-2.5-flash -> 404 (yangi userlar uchun yopilgan).
GEMINI_PRIMARY_MODEL = "gemini-3.5-flash"
GEMINI_FALLBACK_MODEL = "gemini-3.8-flash"   # faqat vaqtinchalik xatoda (429/5xx/timeout)

# Maksimum 2 ta model: asosiy + bitta fallback. Doimiy xatoda (404 va h.k.) fallback ishlatilmaydi.
GEMINI_MODELS = [GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL]

def _is_temporary_gemini_error(e: Exception) -> bool:
    """Faqat haqiqiy vaqtinchalik xatolar (fallback modelga o'tishga arziydi)."""
    err = str(e)
    markers = ("429", "500", "502", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE",
               "DEADLINE_EXCEEDED", "INTERNAL", "timed out", "Timeout", "timeout")
    return any(m in err for m in markers)

# Audio va rasm uchun multimodal modellar.
# Ishlaydigan model birinchi turadi: oldin 3.8 (503) -> 2.5 (404) -> 3.7 (503) ketma-ket
# sinalib, har rasm/ovozda bir necha soniya behuda ketardi (yoki 503 da umuman to'xtardi).
GEMINI_MULTIMODAL_MODELS = [GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL]

async def _try_generate(prompt: str, model: str) -> str:
    response = await gemini_client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=GEMINI_SYSTEM_INSTRUCTION,
            temperature=0.7,
        )
    )
    return response.text

async def get_gemini_response(prompt: str):
    if AI_MAINTENANCE:
        return None
    if not gemini_client:
        return None
    last_error = None
    for model in GEMINI_MODELS:
        try:
            logging.info(f"Model sinashda: {model}")
            return await _try_generate(prompt, model)
        except Exception as e:
            if _is_temporary_gemini_error(e):
                logging.warning(f"{model} vaqtinchalik xato, fallback: {str(e)[:120]}")
                last_error = e
                continue
            # Doimiy xato (404/400/401/403...) — boshqa modellarga so'rov yuborilmaydi
            _handle_gemini_error(e)
            return None
    _handle_gemini_error(last_error or Exception("Hech bir model ishlamadi"))
    return None

def _handle_gemini_error(e: Exception):
    error_msg = str(e)
    logging.error(f"Gemini API xatoligi: {error_msg[:300]}")

async def stream_gemini_to_message(
    prompt: str,
    message: types.Message,
    placeholder_text: str = "⏳ Javob tayyorlanmoqda...",
    reply_markup=None
):
    if AI_MAINTENANCE:
        await message.edit_text(markdown_to_html(AI_MAINTENANCE_MSG), parse_mode="HTML", reply_markup=reply_markup)
        return None
    if not gemini_client:
        error_text = "⚠️ Sun'iy intellekt hozir sozlanmagan.\nIltimos, administratorga murojaat qiling."
        await message.edit_text(markdown_to_html(error_text), parse_mode="HTML", reply_markup=reply_markup)
        return None

    try:
        sent_msg = await message.edit_text(placeholder_text, parse_mode="HTML")
    except Exception:
        sent_msg = message

    last_error = None
    async with KeepTyping(message.bot, message.chat.id):
        for model in GEMINI_MODELS:
            full_text = ""
            last_edit_time = asyncio.get_event_loop().time()
            edit_interval = 3.0
            min_chars_before_edit = 80
            chars_since_last_edit = 0

            try:
                stream = await gemini_client.aio.models.generate_content_stream(
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=GEMINI_SYSTEM_INSTRUCTION,
                        temperature=0.7,
                    )
                )
                async for chunk in stream:
                    if chunk.text:
                        full_text += chunk.text
                        chars_since_last_edit += len(chunk.text)
                        now = asyncio.get_event_loop().time()
                        if now - last_edit_time >= edit_interval and chars_since_last_edit >= min_chars_before_edit:
                            try:
                                await sent_msg.edit_text(markdown_to_html(full_text) + " ✍️", parse_mode="HTML")
                                last_edit_time = now
                                chars_since_last_edit = 0
                            except Exception:
                                pass

                if full_text:
                    html_full = markdown_to_html(full_text)
                    if len(html_full) <= 4096:
                        try:
                            await sent_msg.edit_text(
                                html_full,
                                parse_mode="HTML",
                                reply_markup=reply_markup
                            )
                            return full_text
                        except Exception as edit_err:
                            if _is_not_modified_error(edit_err):
                                return full_text
                    # HTML parse xatosi yoki >4096 belgilik javob uchun plain-text fallback
                    plain_chunks = _split_message(full_text, 4096) or [full_text[:4096]]
                    try:
                        await sent_msg.edit_text(
                            plain_chunks[0],
                            parse_mode=None,
                            reply_markup=reply_markup if len(plain_chunks) == 1 else None
                        )
                    except Exception:
                        pass
                    for extra_idx, extra_chunk in enumerate(plain_chunks[1:], start=1):
                        try:
                            is_last = (extra_idx == len(plain_chunks) - 1)
                            await message.answer(
                                extra_chunk,
                                parse_mode=None,
                                reply_markup=reply_markup if is_last else None
                            )
                        except Exception:
                            break
                    return full_text
                else:
                    logging.warning(f"{model} bo'sh javob qaytardi, keyingisiga o'tilmoqda...")
                    continue

            except Exception as e:
                if _is_temporary_gemini_error(e) and not full_text:
                    logging.warning(f"Streaming: {model} vaqtinchalik xato, fallback: {str(e)[:120]}")
                    last_error = e
                    continue
                # Doimiy xato (404 va h.k.) yoki oqim o'rtasida uzilish — boshqa modelga so'rov yuborilmaydi
                _handle_gemini_error(e)
                await sent_msg.edit_text(markdown_to_html("🤖 AI xizmati hozircha javob bermayapti. Keyinroq qayta urinib ko'ring."), parse_mode="HTML", reply_markup=reply_markup)
                return None

    # Asosiy va fallback model ikkalasi ham vaqtinchalik xato berdi — qo'shimcha so'rovlar yuborilmaydi
    if last_error is not None:
        _handle_gemini_error(last_error)
    logging.warning("Streaming: asosiy va fallback model javob bermadi.")
    try:
        await sent_msg.edit_text(markdown_to_html("🤖 AI xizmati hozircha javob bermayapti. Keyinroq qayta urinib ko'ring."), parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        pass
    return None

async def get_web_app_url(user_id: int, page: str = None) -> str:
    base_url = os.getenv("MINI_APP_URL", MINI_APP_URL)
    if not base_url:
        return ""
    
    import urllib.parse
    
    # Fetch score asynchronously
    score = await asyncio.to_thread(database.get_score, user_id)
    
    params = {
        "v": APP_VERSION,
        "score": score
    }
    if page:
        params["page"] = page
        
    prize = await asyncio.to_thread(database.generate_or_get_spin_prize, user_id)
    if prize is not None:
        params["prize"] = prize
        
    bonus_info = await asyncio.to_thread(database.get_daily_bonus_info, user_id)
    params["streak"] = bonus_info["streak"]
    params["daily_claimed"] = "1" if bonus_info["is_claimed_today"] else "0"
        
    return f"{base_url}?{urllib.parse.urlencode(params)}"

# ═══════════════════════════════════════════════════════════════════
# KLAVIATURALAR (KEYBOARDS)
# ═══════════════════════════════════════════════════════════════════

def get_start_keyboard():
    """Asosiy reply menyu tugmalari"""
    kb_rows = [
        [
            KeyboardButton(text="📋 Holatlar ro'yxati"),
            KeyboardButton(text="📚 Kasalliklar")
        ],
        [
            KeyboardButton(text="💬 AI Konsultatsiya (Chat)"),
            KeyboardButton(text="🚨 Favqulodda raqamlar")
        ],
        [
            KeyboardButton(text="🏥 Yaqin kasalxona"),
            KeyboardButton(text="💊 Dori Eslatmalari")
        ],
        [
            KeyboardButton(text="👤 Tibbiy Profilim"),
            KeyboardButton(text="🔔 Kunlik Maslahatlar")
        ],
        [
            KeyboardButton(text="💎 Premium"),
            KeyboardButton(text="👥 Do'stlarni taklif qilish")
        ],
        [
            KeyboardButton(text="🌐 Mening ballarim"),
            KeyboardButton(text="📣 Reklama")
        ]
    ]

    keyboard = ReplyKeyboardMarkup(
        keyboard=kb_rows,
        resize_keyboard=True,
        persistent=True
    )
    return keyboard

def get_conditions_keyboard():
    builder = InlineKeyboardBuilder()
    # Eng muhim holat — birinchi qatorda, alohida (P1-4)
    builder.button(text="🫀 YO'R (reanimatsiya)", callback_data="aid_reanimatsiya")
    builder.button(text="🔥 Kuyish",              callback_data="aid_kuyish")
    builder.button(text="🩸 Qon ketishi",         callback_data="aid_qon_ketishi")
    builder.button(text="🦴 Suyak sinishi",       callback_data="aid_sinish")
    builder.button(text="🫣 Bo'g'ilish",          callback_data="aid_bogilish")
    builder.button(text="💔 Yurak xuruji",        callback_data="aid_yurak_xuruji")
    builder.button(text="😵 Hushidan ketish",     callback_data="aid_hushdan_ketish")
    builder.button(text="💀 Zaharlanish",         callback_data="aid_zaharlanish")
    builder.button(text="☀️ Issiqlik urishi",    callback_data="aid_issiqlik_urishi")
    builder.button(text="⚡ Talvasa (epilepsiya)", callback_data="aid_talvasa")
    builder.button(text="⚡ Elektr toki urishi",  callback_data="aid_elektr_toki")
    builder.button(text="🤧 Kuchli allergiya",    callback_data="aid_allergiya")
    builder.button(text="🧠 Insult belgilari",    callback_data="aid_insult")
    builder.button(text="⬅️ Bosh menyuga qaytish", callback_data="back_to_main")
    builder.adjust(1, 2, 2, 2, 2, 2, 2, 1)
    return builder.as_markup()

def get_back_to_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Bosh menyuga qaytish", callback_data="back_to_main")
    return builder.as_markup()

def get_location_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📍 Joylashuvni yuborish", request_location=True)
    builder.button(text="❌ Bekor qilish")
    builder.adjust(1, 1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def get_diseases_keyboard(page: int = 1):
    builder = InlineKeyboardBuilder()
    page_index = page - 1
    if 0 <= page_index < len(DISEASES):
        page_diseases = DISEASES[page_index]
        for idx, disease in enumerate(page_diseases):
            builder.button(text=disease, callback_data=f"dis_{page}_{idx}")
    if page > 1:
        builder.button(text="⬅️", callback_data=f"page_{page-1}")
    builder.button(text=f"{page}/10", callback_data="page_noop")
    if page < 10:
        builder.button(text="➡️", callback_data=f"page_{page+1}")
    builder.button(text="⬅️ Bosh menyuga qaytish", callback_data="back_to_main")
    layout = [2, 2, 2, 2, 2]
    layout.append(3 if page > 1 and page < 10 else 2)
    layout.append(1)
    builder.adjust(*layout)
    return builder.as_markup()

def get_premium_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="💎 Premium", callback_data="buy_premium")
    return builder.as_markup()

# ═══════════════════════════════════════════════════════════════════
# PREMIUM UPSELL
# ═══════════════════════════════════════════════════════════════════

async def premium_upsell(event):
    text = (
        "🛑 <b>Bepul AI so'rovlar limiti tugadi!</b>\n\n"
        "AI bilan cheksiz ishlash uchun <b>Premium</b> xarid qiling.\n\n"
        "🎁 <b>Bepul Premium olish yo'li:</b>\n"
        "• 🔥 Har kuni botga kirib, kunlik bonus to'plang (1, 2, 3... ball)!\n"
        "• 👥 Do'stingizni taklif qiling: <b>+10 ball</b> (5 ta do'st uchun: <b>🎁 +50 ball</b>!)\n"
        "• 🎓 <b>100 ball</b> to'planganda bepul <b>Premium</b> faollashadi!\n\n"
        f"⭐ <b>{PREMIUM_STARS_PRICE} Telegram Stars</b> dan boshlab yoki karta orqali.\n\n"
        "Quyidagi tugmani bosing:"
    )
    if isinstance(event, types.Message):
        await event.answer(text, reply_markup=get_premium_keyboard(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=get_premium_keyboard(), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# START VA MENYU
# ═══════════════════════════════════════════════════════════════════

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """/start yuborilganda"""
    start_ts = time.time()
    logging.info(f"START received at {start_ts:.3f}")
    await state.clear()
    user = message.from_user
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None
    username = user.username or None
    
    # Always register user first to ensure they exist in database
    await asyncio.to_thread(database.register_user, user.id, full_name=full_name, username=username)
    db_reg_ts = time.time()
    logging.info(f"DB register_user: {(db_reg_ts - start_ts) * 1000:.1f} ms")
    
    args = message.text.split() if message.text else []
    
    # Check for daily bonus claim
    if len(args) > 1 and args[1] == "claim_daily":
        daily_start = time.time()
        success, points, streak = await asyncio.to_thread(database.check_and_grant_daily_bonus, user.id)
        daily_end = time.time()
        logging.info(f"Daily bonus check: {(daily_end - daily_start) * 1000:.1f} ms")
        if success:
            streak_stars = "⭐" * min(streak, 7)
            bonus_msg = (
                f"✅ <b>Bugungi bonus olindi!</b>\n\n"
                f"Sizga <b>+{points} ball</b> berildi!\n"
                f"🔥 <b>Ketma-ket kirish:</b> {streak}-kun {streak_stars}\n\n"
                f"⏰ Ertaga yana kiring."
            )
        else:
            bonus_msg = "✅ Siz bugungi bonusni olib bo'lgansiz!\n⏰ Ertaga yana kiring."
        await message.answer(bonus_msg, parse_mode="HTML", reply_markup=get_start_keyboard())
        # await update_user_menu_button(user.id, message.bot)  # removed to set menu button only at startup
        total_ts = time.time()
        logging.info(f"TOTAL /start (daily bonus path): {(total_ts - start_ts) * 1000:.1f} ms")
        return

    # Deep link orqali premium xarid tugmasi bosilganda
    if len(args) > 1 and args[1] in ("buy_pro_7", "buy_plus_30", "buy_ultra_30"):
        premium_start = time.time()
        logging.info(f"Premium check start: {premium_start - start_ts:.3f}s")
        action = args[1]
        try:
            user_info = await asyncio.to_thread(database.get_user_info, user.id)
            eligible, current_tier_name = check_premium_purchase_eligibility(user_info, action)

            if not eligible:
                await message.answer(
                    f"ℹ️ <b>Siz allaqachon {current_tier_name} foydalanuvchisiz!</b>\n\n"
                    f"Joriy tarifingiz sotib olmoqchi bo'lgan tarifdan yuqoriroq yoki teng. "
                    f"Pastroq tarifga o'tish mumkin emas.",
                    parse_mode="HTML",
                    reply_markup=get_start_keyboard()
                )
                return
            if action == "buy_pro_7":
                title = "⭐ Premium Pro — 7 kun"
                desc = "7 kunlik Premium Pro obuna: Kuniga 15 AI so'rov, ovozli maslahat va tibbiy profil."
                payload = "PRO_7_DAYS"
                stars = int(os.getenv("PRO_TRIAL_STARS", "50"))
            elif action == "buy_plus_30" and await asyncio.to_thread(database.has_discount, user.id):
                # SUPER PRIZ yutgan foydalanuvchi mini appdan shu havola orqali kelsa ham chegirma hisobga olinadi
                title, desc, payload, stars = discount_plus_offer()
            elif action == "buy_plus_30":
                title = "💎 Premium Plus — 30 kun"
                desc = "30 kunlik Premium Plus obuna: Kuniga 30 AI so'rov va barcha Premium imkoniyatlar."
                payload = "PLUS_30_DAYS"
                stars = int(os.getenv("PRO_MONTHLY_STARS", "150"))
            elif action == "buy_ultra_30":
                title = "👑 Premium Ultra — 30 kun"
                desc = "30 kunlik Premium Ultra obuna: Kuniga 100 AI so'rov (Cheksiz) va prioritet maslahat."
                payload = "ULTRA_30_DAYS"
                stars = int(os.getenv("ULTRA_MONTHLY_STARS", "300"))
            else:
                return

            if stars <= 0:
                raise ValueError("Stars price must be greater than zero")

            await message.answer(
                f"💎 <b>{title}</b>\n\n{desc}\n\n"
                f"💰 Narxi: <b>{stars} Telegram Stars</b>\n\n"
                f"To'lov uchun quyidagi invoice ga bosing:",
                parse_mode="HTML",
                reply_markup=get_start_keyboard()
            )
            await message.answer_invoice(
                title=title,
                description=desc,
                payload=payload,
                currency=STARS_CURRENCY,
                prices=[LabeledPrice(label=title, amount=stars)],
                provider_token=STARS_PROVIDER_TOKEN,
            )
        except Exception as e:
            logging.error(f"Deep link invoice xato: {e}", exc_info=True)
            await message.answer("⚠️ Invoice yuborishda xatolik. Iltimos /premium buyrug'ini ishlating.", parse_mode="HTML")
        # await update_user_menu_button(user.id, message.bot)  # removed
        return

    # Web App yoki menyudan to'g'ridan-to'g'ri Omad Barabani ochilganda
    if len(args) > 1 and args[1] in ("wheel", "baraban"):
        web_app_url = await get_web_app_url(user.id, page="wheel")
        builder = InlineKeyboardBuilder()
        builder.button(text="🎡 Omad barabanini ochish", web_app=types.WebAppInfo(url=web_app_url))
        builder.adjust(1)
        await message.answer(
            "🎡 <b>Omad Barabani!</b>\n\n"
            "Har kuni 1 marta barabanni bepul aylantirib ball yoki Premium yuting!\n"
            "Aylantirish uchun quyidagi tugmani bosing:",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        return

    # Check for spin bonus parameter from Wheel of Fortune Web App
    if len(args) > 1 and args[1].startswith("spin_"):
        try:
            param = args[1].split("_")[1]
            if param == "super":
                success, msg = await asyncio.to_thread(database.check_and_grant_spin_bonus, user.id, 0)  # 0 represents super prize
            else:
                pts = int(param)
                success, msg = await asyncio.to_thread(database.check_and_grant_spin_bonus, user.id, pts)
                
            reply_markup = get_start_keyboard()
            if param == "super":
                builder = InlineKeyboardBuilder()
                builder.button(text="💎 Premium xarid qilish", callback_data="buy_premium")
                builder.adjust(1)
                reply_markup = builder.as_markup()

            await message.answer(msg, parse_mode="HTML", reply_markup=reply_markup)
            # await update_user_menu_button(user.id, message.bot)  # removed
            return
        except Exception as e:
            logging.error(f"Error handling spin parameter: {e}")
            await message.answer("⚠️ Omad barabani bonusini tasdiqlashda xatolik yuz berdi.", reply_markup=get_start_keyboard())
            return

    # Check if referral argument exists
    if len(args) > 1:
        param = args[1]
        referrer_id_str = param.replace("ref_", "")
        if referrer_id_str.isdigit():
            referrer_id = int(referrer_id_str)
            # This handles referred_by connection
            # handle_referral (success, points, bonus) tuple qaytaradi — tuple har doim
            # "rost", shuning uchun faqat birinchi elementni tekshiramiz
            referral_success, _, _ = await asyncio.to_thread(database.handle_referral, user.id, referrer_id)

            # Notify the referrer only if referral was successful
            if referral_success:
                try:
                    referrer_score = await asyncio.to_thread(database.get_score, referrer_id)
                    ref_count = await asyncio.to_thread(database.get_referral_count, referrer_id)
                    
                    # Check if this registration triggered a 5th referral bonus
                    bonus_info = ""
                    if ref_count == 5:
                        bonus_info = f"\n\n🎁 <b>Qo'shimcha bonus:</b> Siz 5 ta do'st taklif qilganingiz uchun yana <b>+50 ball</b> berildi!"

                    friend_name = html.escape(full_name or "Do'stingiz")
                    ref_notification = (
                        f"👥 <b>Do'stingiz taklifingizni qabul qildi!</b>\n\n"
                        f"Foydalanuvchi <b>{friend_name}</b> botimizdan foydalanishni boshladi.\n"
                        f"💰 Sizga <b>+10 ball</b> berildi!\n"
                        f"📊 Taklif qilingan do'stlar: <b>{ref_count}</b> ta{bonus_info}\n"
                        f"🏆 Umumiy ballaringiz: <b>{referrer_score}</b> ball"
                    )
                    await message.bot.send_message(chat_id=referrer_id, text=ref_notification, parse_mode="HTML")
                except Exception as e:
                    logging.warning(f"Failed to notify referrer {referrer_id}: {e}")
    
    # Deep link orqali Web App dan kiritilgan bo'lsa
    if message.text and "ai_consult_" in message.text:
        body_part_key = message.text.split("ai_consult_")[-1].strip()
        # Tarjima qismi
        translations = {
            "head": "Bosh", "neck": "Bo'yin", "shoulder": "Yelka", "chest": "Ko'krak",
            "arm": "Qo'l", "abdomen": "Qorin", "hand": "Kaft/Barmoq", "hip": "Chanoq",
            "thigh": "Son", "knee": "Tizza", "shin": "Boldir", "foot": "Oyoq panjasi",
            "back": "Bel/Orqa", "left_shoulder": "Chap yelka", "right_shoulder": "O'ng yelka",
            "left_arm": "Chap qo'l", "right_arm": "O'ng qo'l", "left_leg": "Chap oyoq",
            "right_leg": "O'ng oyoq"
        }
        if body_part_key not in translations:
            await message.answer("⚠️ Noto'g'ri tana a'zosi tanlandi.")
            return
            
        body_part_title = translations[body_part_key]
        user_id = message.from_user.id
        
        consumed_free = False
        consumed_daily = False
        if await asyncio.to_thread(database.try_consume_free_ai, user_id):
            consumed_free = True
        elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
            consumed_daily = True
        else:
            await message.answer(
                "🚫 <b>Sizning AI so'rovlar limitingiz tugagan!</b>\n\n"
                "Iltimos, ertaga urining yoki <b>Premium</b> oling.",
                parse_mode="HTML"
            )
            return
            
        await message.answer(
            f"🤖 <b>AI Konsultatsiya ({body_part_title}):</b>\n\n"
            f"Siz <b>{body_part_title}</b> sohasidagi muammoni tanladingiz.\n"
            f"Tahlil qilinmoqda, iltimos kuting... ⏳",
            parse_mode="HTML",
            reply_markup=get_start_keyboard()
        )
        
        prompt = (
            f"Foydalanuvchi inson tanasidagi '{body_part_title}' sohasida og'riq yoki bezovtalik borligini bildirdi. "
            f"Ushbu tana a'zosi bo'yicha eng ko'p uchraydigan kasalliklar, ularning kelib chiqish sabablari va "
            f"uy sharoitida birinchi yordam hamda shifokorga qachon murojaat qilish kerakligi haqida atroflicha, "
            f"chiroyli va tushunarli o'zbek tilida maslahat ber."
        )
        
        ai_response = await get_gemini_response(prompt)
        if ai_response is None:
            if consumed_free:
                await asyncio.to_thread(database.refund_free_ai, user_id)
            if consumed_daily:
                await asyncio.to_thread(database.refund_daily_request, user_id)
            ai_response = "🤖 AI xizmati hozircha javob bermayapti. Keyinroq qayta urinib ko'ring."
            
        await message.answer(ai_response, parse_mode="HTML")
        return

    # (web_app_url yuklash olib tashlandi, keraksiz DB query tejaldı)
    
    start_text = (
        "🚑 <b>Assalomu alaykum!</b>\n\n"
        "Sog'lig'ingiz uchun foydali yordamchi botga xush kelibsiz! ❤️\n\n"
        "<b>Bot orqali:</b>\n"
        "📋 Holatlar ro'yxati\n"
        "📚 Kasalliklar haqida ma'lumot\n"
        "💬 AI Konsultatsiya\n"
        "🏥 Eng yaqin kasalxonani topish\n"
        "🚨 Favqulodda raqamlar\n"
        "💊 Dori eslatmalari\n"
        "👤 Tibbiy profil\n"
        "🔔 Kunlik maslahatlar\n"
        "🎁 Kunlik bonuslar\n"
        "💎 Premium imkoniyatlar\n\n"
        "va boshqa funksiyalardan foydalanishingiz mumkin.\n\n"
        "📌 <b>Asosiy buyruqlar:</b>\n"
        "/start — Botni ishga tushirish\n"
        "/menu — Bosh menyu\n"
        "/help — Yordam\n"
        "/contacts — Tezkor telefon raqamlari\n"
        "/premium — 💎 Premium imkoniyatlari\n"
        "/reklama — 📣 Reklama bo'yicha murojaat\n\n"
        "💎 <b>PREMIUM</b>\n\n"
        "Botdagi qo'shimcha imkoniyatlardan foydalaning.\n\n"
        "🎁 <b>Eng qiziq joyi:</b>\n"
        "Tekin Premium olish imkoniyati mavjud!\n\n"
        "👇 Quyidagi menyudan xizmatni tanlang:"
    )

    # Bitta xabar: start matni + ReplyKeyboardMarkup (menyu avtomatik ochiladi)
    await message.answer(
        start_text,
        reply_markup=get_start_keyboard(),
        parse_mode="HTML"
    )
    
# await update_user_menu_button(user.id, message.bot)  # removed; now set at startup
    after_menu_ts = time.time()
    logging.info(f"Menu button update latency: {(after_menu_ts - start_ts) * 1000:.1f} ms")
    logging.info(f"TOTAL /start latency: {(after_menu_ts - start_ts) * 1000:.1f} ms")

async def update_user_menu_button(user_id: int, current_bot: Bot):
    # Telegram API requires MenuButton WebAppInfo URL to have NO query params
    web_app_url = os.getenv("MINI_APP_URL", MINI_APP_URL)
    if web_app_url:
        try:
            await current_bot.set_chat_menu_button(
                chat_id=user_id,
                menu_button=types.MenuButtonWebApp(
                    text="🚑 Mini Ilova",
                    web_app=types.WebAppInfo(url=web_app_url)
                )
            )
        except Exception as e:
            logging.error(f"Failed to update chat menu button for user {user_id}: {e}")
    else:
        try:
            await current_bot.set_chat_menu_button(
                chat_id=user_id,
                menu_button=types.MenuButtonDefault()
            )
        except Exception:
            pass

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyu:", reply_markup=get_start_keyboard())

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "ℹ️ <b>Bot imkoniyatlari:</b>\n\n"
        "📋 <b>Holatlar ro'yxati</b> — 12 ta birinchi yordam holati\n"
        "📚 <b>Kasalliklar</b> — 100+ kasallik haqida AI ma'lumot\n"
        "💬 <b>AI Konsultatsiya</b> — Gemini AI bilan suhbat\n"
        "🏥 <b>Kasalxona</b> — Yaqin shifoxona va dorixonalar\n"
        "💎 <b>Premium</b> — Cheksiz AI so'rovlari\n"
        "👤 <b>Tibbiy Profil</b> — Sizning shaxsiy tibbiy ma'lumotlaringiz\n"
        "💊 <b>Dori Eslatmalari</b> — Dorilarni vaqtida ichish uchun budilnik\n"
        "⚖️ <b>Sog'liq Kalkulyatori</b> — BMI va suv balansi\n"
        "🔔 <b>Kunlik Maslahatlar</b> — Har kuni sog'liq bo'yicha tavsiya\n"
        "/reklama — 📣 Reklama bo'yicha murojaat qilish\n\n"
        "📞 <b>Favqulodda:</b> 103 (Tez yordam) | 101 (Yong'in) | 102 (Militsiya)"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_start_keyboard())

@dp.message(Command("contacts"))
async def cmd_contacts(message: types.Message):
    await message.answer(
        markdown_to_html(
            "🚨 **Favqulodda tezkor yordam telefon raqamlari:**\n\n"
            "🚑 **Tez tibbiy yordam:** 103\n🚒 **Yong'in xavfsizligi:** 101\n"
            "👮 **Militsiya:** 102\n👨‍🚒 **Favqulodda vaziyatlar (FVV):** 1050\n\n"
            "Tezkor raqamlarga qo'ng'iroq qilish bepul va 24/7 ishlaydi."
        ),
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════════════════════════════
# REKLAMA
# ═══════════════════════════════════════════════════════════════════

def get_reklama_keyboard():
    """Reklama bo'yicha kanal havolasi bilan inline tugma"""
    builder = InlineKeyboardBuilder()
    # Kanal sahifasiga to'g'ridan-to'g'ri havola — foydalanuvchi kanalga o'tib,
    # "Xabar yozish" (Message) tugmasi orqali kanal chatiga yozadi.
    builder.button(
        text="📩 Reklama bo'yicha yozish",
        url="https://t.me/birinchi1_yordam"
    )
    builder.adjust(1)
    return builder.as_markup()

async def send_reklama_message(message: types.Message):
    """Reklama xabarini yuborish"""
    text = (
        "📣 <b>REKLAMA BERISH</b>\n\n"
        "Botimiz yoki kanalimizda reklama joylashtirishni xohlaysizmi?\n\n"
        "📌 Reklama shartlari va narxi individual kelishiladi.\n\n"
        "💬 Reklama bo'yicha murojaat qilish uchun kanalimizga o'ting "
        "va kanal chatiga xabar qoldiring.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 <b>Reklama uchun quyidagilarni yuboring:</b>\n\n"
        "• Reklama matni\n"
        "• Rasm/video (agar bo'lsa)\n"
        "• Reklama qilinadigan loyiha yoki mahsulot\n"
        "• Qancha muddatga joylashtirishni xohlashingiz\n"
        "• Bog'lanish uchun username yoki link\n\n"
        "Bu ma'lumotlar reklama bo'yicha kelishuvni osonlashtiradi.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ Kanalimizga o'ting.\n"
        "2️⃣ <b>\"Xabar yozish\"</b> tugmasini bosing.\n"
        "3️⃣ Reklama haqida ma'lumot yuboring.\n"
        "4️⃣ Reklama turi va narxini admin bilan kelishing.\n\n"
        "💰 <b>Narx:</b> individual kelishiladi.\n\n"
        "👇 Quyidagi tugmani bosing:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_reklama_keyboard())

@dp.message(Command("reklama"))
async def cmd_reklama(message: types.Message):
    """/reklama buyrug'i — reklama bo'yicha ma'lumot"""
    await send_reklama_message(message)

@dp.message(F.text == "📣 Reklama")
async def btn_reklama(message: types.Message):
    """📣 Reklama tugmasi — reklama bo'yicha ma'lumot"""
    await send_reklama_message(message)

@dp.message(F.text == "👥 Do'stlarni taklif qilish")
async def show_referral_menu(message: types.Message):
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    
    # Generate referral link
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    # Get user referral count and score
    ref_count = await asyncio.to_thread(database.get_referral_count, user_id)
    
    score = await asyncio.to_thread(database.get_score, user_id)
    
    # Share text
    share_text = (
        "Sog'liq va birinchi yordam botidan bepul foydalaning! "
        "AI shifokor bilan cheksiz suhbat, kasalliklar tahlili va boshqa ko'plab foydali narsalar bor. "
        "Botga kirish uchun quyidagi havolani bosing 👇"
    )
    
    # Encode for url
    import urllib.parse
    share_url_encoded = urllib.parse.quote(ref_link)
    share_text_encoded = urllib.parse.quote(share_text)
    
    share_link = f"https://t.me/share/url?url={share_url_encoded}&text={share_text_encoded}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Do'stlarga yuborish", url=share_link)
    builder.adjust(1)
    
    # Message text
    text = (
        "👥 <b>Do'stlarni taklif qilish</b>\n\n"
        "Botimizni do'stlaringizga tavsiya qiling va bepul Premium obunani qo'lga kiriting!\n\n"
        "💰 <b>Qoidalar:</b>\n"
        "• Har bir taklif qilingan do'stingiz uchun: <b>+10 ball</b>\n"
        "• Har 5 ta taklif qilingan do'st uchun qo'shimcha bonus: <b>🎁 +50 ball</b>\n\n"
        "📊 <b>Sizning ko'rsatkichlaringiz:</b>\n"
        f"• Taklif qilingan do'stlar: <b>{ref_count}</b> ta\n"
        f"• Sizning joriy ballaringiz: <b>{score}</b> ball\n\n"
        f"🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "💡 Havolani nusxalab do'stlaringizga yuboring yoki quyidagi <b>Do'stlarga yuborish</b> tugmasini bosing!"
    )
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

async def send_free_premium_info(user_id: int, user: types.User, chat_id: int, bot: Bot):
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None
    await asyncio.to_thread(database.register_user, user_id, full_name=full_name, username=user.username)
    
    score = await asyncio.to_thread(database.get_score, user_id)
    web_app_url = await get_web_app_url(user_id, page="wheel")
    
    builder = InlineKeyboardBuilder()
    if web_app_url:
        builder.button(
            text="🎡 Omad barabani",
            web_app=types.WebAppInfo(url=web_app_url)
        )
    builder.button(text="👥 Do'stlarni taklif qilish", callback_data="show_ref_from_cmd")
    builder.adjust(1)

    text = (
        "💎 <b>Bepul Premium olish tizimi</b>\n\n"
        "Siz botdagi faolligingiz orqali bepul Premium obunani qo'lga kiritishingiz mumkin! Buning uchun <b>100 ball</b> to'plashingiz kifoya.\n\n"
        "💰 <b>Ball to'plash yo'llari:</b>\n"
        "1. 🔥 <b>Kunlik bonus:</b> Har kuni botga kirib, ballarni to'plang (1, 2, 3... ball va 7-kuni 🎁 +20 ball!).\n"
        "2. 👥 <b>Do'stlarni taklif qilish:</b> Har bir taklif qilgan do'stingiz uchun <b>+10 ball</b>, har 5 ta do'st uchun esa qo'shimcha <b>🎁 +50 ball</b> beriladi!\n"
        "3. 🎡 <b>Omad barabani:</b> Har kuni 1 marta barabanni bepul aylantirib ball yutib oling!\n\n"
        f"🏆 <b>Sizning joriy ballaringiz:</b> <b>{score}</b> ball\n\n"
        "Omad barabanini aylantirish yoki do'stlarni taklif qilish uchun quyidagi tugmalardan foydalaning 👇"
    )
    await bot.send_message(chat_id, text, reply_markup=builder.as_markup(), parse_mode="HTML")


# /free_premium komandasi o'chirildi — uning o'rniga /premium ichiga birlashtirildi

@dp.callback_query(F.data == "free_premium_info")
async def cb_free_premium_info(callback: types.CallbackQuery):
    # Eski tugma bosgan bo'lsa ham Premium sahifasiga yo'naltiramiz
    await _show_premium_page(callback)

@dp.callback_query(F.data == "show_ref_from_cmd")
async def process_show_ref_from_cmd(callback: types.CallbackQuery):
    await callback.answer()
    user = callback.from_user
    bot_info = await callback.message.bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    
    ref_count = await asyncio.to_thread(database.get_referral_count, user.id)
    
    score = await asyncio.to_thread(database.get_score, user.id)
    
    import urllib.parse
    share_text = (
        "Sog'liq va birinchi yordam botidan bepul foydalaning! "
        "AI shifokor bilan cheksiz suhbat, kasalliklar tahlili va boshqa ko'plab foydali narsalar bor. "
        "Botga kirish uchun quyidagi havolani bosing 👇"
    )
    share_url_encoded = urllib.parse.quote(ref_link)
    share_text_encoded = urllib.parse.quote(share_text)
    share_link = f"https://t.me/share/url?url={share_url_encoded}&text={share_text_encoded}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Do'stlarga yuborish", url=share_link)
    builder.adjust(1)
    
    text = (
        "👥 <b>Do'stlarni taklif qilish</b>\n\n"
        "Botimizni do'stlaringizga tavsiya qiling va bepul Premium obunani qo'lga kiriting!\n\n"
        "💰 <b>Qoidalar:</b>\n"
        "• Har bir taklif qilingan do'stingiz uchun: <b>+10 ball</b>\n"
        "• Har 5 ta taklif qilingan do'st uchun qo'shimcha bonus: <b>🎁 +50 ball</b>\n\n"
        "📊 <b>Sizning ko'rsatkichlaringiz:</b>\n"
        f"• Taklif qilingan do'stlar: <b>{ref_count}</b> ta\n"
        f"• Sizning joriy ballaringiz: <b>{score}</b> ball\n\n"
        f"🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "💡 Havolani nusxalab do'stlaringizga yuboring yoki quyidagi <b>Do'stlarga yuborish</b> tugmasini bosing!"
    )
    await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════
# REPLY KEYBOARD HANDLERLARI
# ═══════════════════════════════════════════════════════════════════

@dp.message(F.text == "📋 Holatlar ro'yxati")
async def reply_conditions(message: types.Message):
    await message.answer("Quyidagi holatlardan birini tanlang:", reply_markup=get_conditions_keyboard())

@dp.message(F.text == "📚 Kasalliklar")
async def reply_diseases_list(message: types.Message):
    await message.answer("Kasallikni tanlang (sahifa 1/10):", reply_markup=get_diseases_keyboard(1))

@dp.message(F.text == "💬 AI Konsultatsiya (Chat)")
async def reply_diseases_ai(message: types.Message, state: FSMContext):
    await state.set_state(AiChatStates.chatting)
    text = (
        "🤖 **Sun'iy Intellekt (Gemini AI) Yordami (Chat rejimida):**\n\n"
        "Menga istalgan kasallik, simptom, dorilar, foydali ovqatlar yoki jismoniy mashqlar haqida yozing.\n\n"
        "**Masalan yozib ko'ring:**\n"
        "• *Bosh og'rig'ini qoldirish uchun nima qilish kerak?*\n"
        "• *Sog'lom ovqatlanish qoidalari qanday?*\n"
        "• *Bel og'rig'iga qanday mashqlar foydali?*\n\n"
        "⚠️ Chatdan chiqish uchun boshqa biror menyu tugmasini bosing yoki /cancel deb yozing."
    )
    await message.answer(markdown_to_html(text), reply_markup=get_start_keyboard(), parse_mode="HTML")

@dp.message(F.text == "❌ Bekor qilish")
@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    await state.clear()
    
    # Broadcast bekor qilinganda maxsus xabar
    if current_state in [BroadcastStates.waiting_for_content.state, BroadcastStates.waiting_for_confirmation.state]:
        await message.answer("✅ Xabar yuborish bekor qilindi.")
    else:
        await message.answer("Amal bekor qilindi. Bosh menyudasiz.", reply_markup=get_start_keyboard())

@dp.message(F.text == "🏥 Yaqin kasalxona")
async def reply_hospital(message: types.Message):
    await message.answer(
        markdown_to_html(
            "🏥 **Eng yaqin kasalxona va dorixonani topish:**\n\n"
            "Iltimos, joylashuvingizni yuboring — men sizga eng yaqin shifoxonalar **va dorixonalarni** haritada ko'rsataman:"
        ),
        reply_markup=get_location_keyboard(),
        parse_mode="HTML"
    )

@dp.message(F.text == "💎 Premium")
async def reply_premium_info(message: types.Message):
    await _show_premium_page(message)

@dp.message(F.text == "🚨 Favqulodda raqamlar")
async def reply_contacts(message: types.Message):
    text = (
        "🚨 **Favqulodda tezkor yordam telefon raqamlari:**\n\n"
        "🚑 **Tez tibbiy yordam:** 103\n🚒 **Yong'in xavfsizligi:** 101\n"
        "👮 **Militsiya:** 102\n👨‍🚒 **Favqulodda vaziyatlar (FVV):** 1050\n\n"
        "Tezkor raqamlarga qo'ng'iroq qilish bepul va 24/7 ishlaydi."
    )
    await message.answer(markdown_to_html(text), reply_markup=get_start_keyboard(), parse_mode="HTML")

# ─── Yaqin kasalxona + dorixona (Feature 4) ───────────────────────

@dp.message(F.location)
async def handle_location(message: types.Message):
    """Foydalanuvchi joylashuvini qabul qilib — kasalxona VA dorixona haritasini ko'rsatish"""
    lat = message.location.latitude
    lon = message.location.longitude

    hospitals_google  = f"https://www.google.com/maps/search/hospital/@{lat},{lon},14z"
    hospitals_yandex  = f"https://yandex.com/maps/?ll={lon}%2C{lat}&mode=search&text=hospital&z=14"
    pharmacy_google   = f"https://www.google.com/maps/search/pharmacy/@{lat},{lon},15z"
    pharmacy_yandex   = f"https://yandex.com/maps/?ll={lon}%2C{lat}&mode=search&text=dorixona&z=15"

    text = (
        "📍 **Joylashuvingiz qabul qilindi!**\n\n"
        "🏥 **Eng yaqin shifoxonalar:**\n"
        f"🌐 [Google Maps orqali ko'rish]({hospitals_google})\n"
        f"🗺️ [Yandex Maps orqali ko'rish]({hospitals_yandex})\n\n"
        "💊 **Eng yaqin dorixonalar:**\n"
        f"🌐 [Google Maps orqali ko'rish]({pharmacy_google})\n"
        f"🗺️ [Yandex Maps orqali ko'rish]({pharmacy_yandex})\n\n"
        "ℹ️ Haritada sizga eng yaqin nuqtalar ko'rsatiladi."
    )
    await message.answer(
        markdown_to_html(text),
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    # Asosiy menyuni qaytarish
    await message.answer("Bosh menyu:", reply_markup=get_start_keyboard())

# ═══════════════════════════════════════════════════════════════════
# INLINE CALLBACK HANDLERLARI (asosiy)
# ═══════════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        markdown_to_html(FIRST_AID_DATA["start"] + "\n\nKerakli bo'limni tanlang yoki savolingizni to'g'ridan-to'g'ri yozing:"),
        parse_mode="HTML"
    )
    await callback.message.answer("Bosh menyu:", reply_markup=get_start_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "main_conditions")
async def main_conditions(callback: types.CallbackQuery):
    await callback.message.edit_text("Quyidagi holatlardan birini tanlang:", reply_markup=get_conditions_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "main_contacts")
async def main_contacts(callback: types.CallbackQuery):
    text = (
        "🚨 **Favqulodda tezkor yordam telefon raqamlari:**\n\n"
        "🚑 **Tez tibbiy yordam:** 103\n🚒 **Yong'in xavfsizligi:** 101\n"
        "👮 **Militsiya:** 102\n👨‍🚒 **Favqulodda vaziyatlar (FVV):** 1050\n\n"
        "Tezkor raqamlarga qo'ng'iroq qilish bepul va 24/7 ishlaydi."
    )
    await callback.message.edit_text(markdown_to_html(text), reply_markup=get_back_to_main_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("aid_"))
async def process_aid_callback(callback: types.CallbackQuery):
    action_key = callback.data.replace("aid_", "")
    text = FIRST_AID_DATA.get(action_key, "Ma'lumot topilmadi.")
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Holatlar ro'yxatiga qaytish", callback_data="main_conditions")
    await callback.message.edit_text(markdown_to_html(text), reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("page_"))
async def process_page_callback(callback: types.CallbackQuery):
    if callback.data == "page_noop":
        await callback.answer()
        return
    page = int(callback.data.replace("page_", ""))
    await callback.message.edit_text(f"Kasallikni tanlang (sahifa {page}/10):", reply_markup=get_diseases_keyboard(page))
    await callback.answer()

@dp.callback_query(F.data.startswith("dis_"))
async def process_disease_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    # Kasalliklar ro'yxatidan qisqa ma'lumot — BEPUL (Premium talab emas)
    _, page_str, index_str = callback.data.split("_")
    page, index = int(page_str), int(index_str)
    disease_name = DISEASES[page - 1][index]
    
    consumed_free = False
    consumed_daily = False
    if await asyncio.to_thread(database.try_consume_free_ai, user_id):
        consumed_free = True
    elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
        consumed_daily = True
    else:
        await callback.message.edit_text(
            "🚫 <b>Sizning AI so'rovlar limitingiz tugagan!</b>\n\n"
            "Iltimos, ertaga urining yoki <b>Premium</b> oling.",
            parse_mode="HTML"
        )
        return
        
    await callback.message.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")

    # Premium foydalanuvchilar uchun batafsil tugmasi ko'rinadi
    is_premium_user, *_ = await asyncio.to_thread(database.get_premium_info, user_id)
    builder = InlineKeyboardBuilder()
    if is_premium_user:
        builder.button(text="🔍 Batafsil ma'lumot (AI)", callback_data=f"det_{page}_{index}")
    else:
        builder.button(text="🔍 Batafsil ma'lumot (💎 Premium)", callback_data=f"det_{page}_{index}")
    builder.button(text="⬅️ Ro'yxatga qaytish", callback_data=f"page_{page}")
    builder.adjust(1, 1)

    # Tibbiy profilni AI ga qo'shish
    profile = await asyncio.to_thread(database.get_medical_profile, user_id)
    profile_context = _build_profile_context(profile)

    prompt = (
        f"Menga '{disease_name}' kasalligi haqida faqat o'zbek tilida juda qisqa va aniq ma'lumot beruvchi matn yozib ber.\n"
        f"Javob aynan quyidagi qat'iy formatda (emojilar bilan) bo'lishi shart:\n\n"
        f"🩺 **{disease_name}**\n\n"
        f"📌 **Yuqish yo'li:** [Qisqacha]\n"
        f"🛠️ **Yechim:** [1-2 ta birinchi yordam]\n"
        f"🍏 **Parhez:** [Nimalarni yeyish kerak]\n"
        + profile_context
    )
    result = await stream_gemini_to_message(
        prompt=prompt,
        message=callback.message,
        placeholder_text=f"⏳ <b>{disease_name}</b> haqida ma'lumot yuklanmoqda...",
        reply_markup=builder.as_markup()
    )
    if result is None:
        if consumed_free:
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            await asyncio.to_thread(database.refund_daily_request, user_id)

@dp.callback_query(F.data.startswith("det_"))
async def process_disease_detail_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    # "Batafsil ma'lumot" — FAQAT PREMIUM foydalanuvchilar uchun (get_premium_info muddatni tekshiradi)
    is_premium_user, *_ = await asyncio.to_thread(database.get_premium_info, user_id)
    if not is_premium_user:
        text = (
            "🔒 <b>Bu bo'lim faqat Premium foydalanuvchilar uchun!</b>\n\n"
            "📚 <b>Batafsil ma'lumot (AI)</b> — kasallik haqida to'liq:\n"
            "• Sabablari va tarqalish yo'llari\n"
            "• Barcha simptomlar\n"
            "• Davolash va dorilar\n"
            "• Parhez va profilaktika\n\n"
            "🎁 <b>Bepul Premium olish yo'li:</b>\n"
            "• 🔥 Har kuni botga kirib, kunlik bonus to'plang (1, 2, 3... ball)!\n"
            "• 👥 Do'stingizni taklif qiling: <b>+10 ball</b> (5 ta do'st uchun: <b>🎁 +50 ball</b>!)\n"
            "• 🎓 <b>100 ball</b> to'planganda bepul <b>Premium</b> faollashadi!\n\n"
            f"⭐ <b>{PREMIUM_STARS_PRICE} Telegram Stars</b> (7 kunlik Pro) dan boshlab.\n\n"
            "Quyidagi tugmani bosing:"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="💎 Premium", callback_data="buy_premium")
        builder.button(text="⬅️ Ro'yxatga qaytish", callback_data=f"page_{callback.data.split('_')[1]}")
        builder.adjust(1)
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        return
    _, page_str, index_str = callback.data.split("_")
    page, index = int(page_str), int(index_str)
    disease_name = DISEASES[page - 1][index]
    await callback.message.bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Kasallik sahifasiga qaytish", callback_data=f"dis_{page}_{index}")
    builder.button(text="📋 Kasalliklar ro'yxatiga qaytish", callback_data=f"page_{page}")
    builder.adjust(1, 1)

    profile = await asyncio.to_thread(database.get_medical_profile, user_id)
    profile_context = _build_profile_context(profile)

    prompt = (
        f"Menga '{disease_name}' kasalligi haqida juda batafsil, ilmiy va tushunarli tibbiy ma'lumot tayyorlab ber.\n"
        f"Javob o'zbek tilida bo'lsin. Quyidagi bo'limlarni o'z ichiga olsin:\n\n"
        f"🩺 **{disease_name} haqida batafsil ma'lumot**\n\n"
        f"❓ **Kasallik nima va u qanday paydo bo'ladi?**\n"
        f"📌 **Yuqish va tarqalish yo'llari:**\n"
        f"⚠️ **Asosiy simptomlar va belgilari:**\n"
        f"🛠️ **Birinchi yordam va davolash yechimlari:**\n"
        f"🍏 **Tavsiya etiladigan parhez:**\n"
        f"🛡️ **Profilaktika (oldini olish):**\n\n"
        f"Matn oxirida shifokor bilan maslahatlashishni va 103 eslatib o'ting.\n"
        + profile_context
    )
    await stream_gemini_to_message(
        prompt=prompt,
        message=callback.message,
        placeholder_text=f"⏳ <b>{disease_name}</b> haqida to'liq ma'lumot tayyorlanmoqda...",
        reply_markup=builder.as_markup()
    )



# ═══════════════════════════════════════════════════════════════════
# FEATURE 1: 👤 TIBBIY PROFIL
# ═══════════════════════════════════════════════════════════════════

@dp.message(F.text == "👤 Tibbiy Profilim")
async def medical_profile_menu(message: types.Message):
    user_id = message.from_user.id
    profile = await asyncio.to_thread(database.get_medical_profile, user_id)
    blood_group, age, weight, height, chronic, allergies = profile if profile else (None,)*6

    text = (
        "👤 <b>Sizning Tibbiy Profilingiz</b>\n\n"
        f"🩸 <b>Qon guruhi:</b> {html.escape(blood_group or '—')}\n"
        f"🎂 <b>Yosh:</b> {age or '—'}\n"
        f"⚖️ <b>Vazn:</b> {f'{weight} kg' if weight else '—'}\n"
        f"📏 <b>Bo'y:</b> {f'{height} sm' if height else '—'}\n"
        f"🏥 <b>Surunkali kasalliklar:</b> {html.escape(chronic or '—')}\n"
        f"⚠️ <b>Allergiyalar:</b> {html.escape(allergies or '—')}\n\n"
        "ℹ️ Bu ma'lumotlar AI konsultatsiyada hisobga olinadi va aniqroq maslahat beradi."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Profilni to'ldirish / tahrirlash", callback_data="edit_profile")
    builder.button(text="🗑️ Profilni o'chirish",               callback_data="clear_profile")
    builder.button(text="🧹 Barcha tibbiy ma'lumotlarimni o'chirish", callback_data="wipe_medical")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ─── Barcha tibbiy ma'lumotlarni to'liq o'chirish (P2-8) ─────────────────────
WIPE_CONFIRM_TEXT = (
    "⚠️ <b>Barcha tibbiy ma'lumotlaringiz o'chiriladi:</b>\n\n"
    "• Tibbiy profil (qon guruhi, yosh, vazn, bo'y, kasalliklar, allergiyalar)\n"
    "• Barcha dori eslatmalari\n"
    "• Kunlik savollarga bergan javoblaringiz\n\n"
    "Hisobingiz, ballaringiz va Premium obunangiz saqlanib qoladi.\n"
    "<b>Bu amalni qaytarib bo'lmaydi.</b> Davom etasizmi?"
)


def _wipe_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, hammasini o'chirish", callback_data="wipe_medical_yes")
    builder.button(text="❌ Bekor qilish", callback_data="wipe_medical_no")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: types.Message):
    await message.answer(WIPE_CONFIRM_TEXT, reply_markup=_wipe_confirm_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "wipe_medical")
async def wipe_medical_ask(callback: types.CallbackQuery):
    await callback.message.answer(WIPE_CONFIRM_TEXT, reply_markup=_wipe_confirm_keyboard(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "wipe_medical_yes")
async def wipe_medical_confirm(callback: types.CallbackQuery):
    try:
        await asyncio.to_thread(database.wipe_user_medical_data, callback.from_user.id)
    except Exception:
        logging.exception("wipe_user_medical_data xatosi: user=%s", callback.from_user.id)
        await callback.message.edit_text("⚠️ O'chirishda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")
        await callback.answer()
        return
    await callback.message.edit_text(
        "✅ <b>Barcha tibbiy ma'lumotlaringiz o'chirildi.</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "wipe_medical_no")
async def wipe_medical_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("❎ Bekor qilindi. Ma'lumotlaringiz o'zgarmadi.")
    await callback.answer()

@dp.callback_query(F.data == "edit_profile")
async def edit_profile_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(MedicalProfileStates.blood_group)
    builder = InlineKeyboardBuilder()
    for bg in ["I (O+)", "I (O-)", "II (A+)", "II (A-)", "III (B+)", "III (B-)", "IV (AB+)", "IV (AB-)"]:
        builder.button(text=bg, callback_data=f"bg_{bg}")
    builder.button(text="O'tkazib yuborish ➡️", callback_data="bg_skip")
    builder.adjust(2, 2, 2, 2, 1)
    try:
        await callback.message.edit_text(
            "🩸 <b>1/6 — Qon guruhingizni tanlang:</b>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except Exception:
        pass

@dp.callback_query(MedicalProfileStates.blood_group, F.data.startswith("bg_"))
async def profile_blood_group(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    value = callback.data.replace("bg_", "")
    if value != "skip":
        await state.update_data(blood_group=value)
    await state.set_state(MedicalProfileStates.age)
    try:
        await callback.message.edit_text(
            "🎂 <b>2/6 — Yoshingizni kiriting</b> (masalan: 25):\n\n"
            "Yoki /skip yuboring.",
            parse_mode="HTML"
        )
    except Exception:
        pass

@dp.message(MedicalProfileStates.age)
async def profile_age(message: types.Message, state: FSMContext):
    if message.text and message.text.strip() != "/skip":
        try:
            age = int(message.text.strip())
            if 1 <= age <= 120:
                await state.update_data(age=age)
            else:
                await message.answer("⚠️ Yosh 1 dan 120 gacha bo'lishi kerak. Qaytadan kiriting:")
                return
        except ValueError:
            await message.answer("⚠️ Faqat raqam kiriting (masalan: 25):")
            return
    await state.set_state(MedicalProfileStates.weight)
    await message.answer("⚖️ <b>3/6 — Vazningizni kiriting (kg):</b> masalan: 70\n\nYoki /skip yuboring.", parse_mode="HTML")

@dp.message(MedicalProfileStates.weight)
async def profile_weight(message: types.Message, state: FSMContext):
    if message.text and message.text.strip() != "/skip":
        try:
            weight = float(message.text.strip().replace(",", "."))
            if 20 <= weight <= 300:
                await state.update_data(weight=weight)
            else:
                await message.answer("⚠️ Vazn 20 dan 300 gacha bo'lishi kerak:")
                return
        except ValueError:
            await message.answer("⚠️ Faqat raqam kiriting (masalan: 70):")
            return
    await state.set_state(MedicalProfileStates.height)
    await message.answer("📏 <b>4/6 — Bo'yingizni kiriting (sm):</b> masalan: 175\n\nYoki /skip yuboring.", parse_mode="HTML")

@dp.message(MedicalProfileStates.height)
async def profile_height(message: types.Message, state: FSMContext):
    if message.text and message.text.strip() != "/skip":
        try:
            height = float(message.text.strip().replace(",", "."))
            if 50 <= height <= 250:
                await state.update_data(height=height)
            else:
                await message.answer("⚠️ Bo'y 50 dan 250 gacha bo'lishi kerak:")
                return
        except ValueError:
            await message.answer("⚠️ Faqat raqam kiriting (masalan: 175):")
            return
    await state.set_state(MedicalProfileStates.chronic_diseases)
    await message.answer(
        "🏥 <b>5/6 — Surunkali kasalliklaringiz</b> (vergul bilan yozing):\n"
        "Masalan: <i>Diabet, Gipertenziya</i>\n\n"
        "Agar yo'q bo'lsa /skip yuboring.",
        parse_mode="HTML"
    )

@dp.message(MedicalProfileStates.chronic_diseases)
async def profile_chronic(message: types.Message, state: FSMContext):
    if message.text and message.text.strip() != "/skip":
        await state.update_data(chronic_diseases=message.text.strip())
    await state.set_state(MedicalProfileStates.allergies)
    await message.answer(
        "⚠️ <b>6/6 — Dorilarga allergiyalaringiz:</b>\n"
        "Masalan: <i>Aspirin, Penitsullin</i>\n\n"
        "Agar yo'q bo'lsa /skip yuboring.",
        parse_mode="HTML"
    )

@dp.message(MedicalProfileStates.allergies)
async def profile_allergies(message: types.Message, state: FSMContext):
    if message.text and message.text.strip() != "/skip":
        await state.update_data(allergies=message.text.strip())

    data = await state.get_data()
    await state.clear()

    await asyncio.to_thread(database.save_medical_profile, 
        user_id=message.from_user.id,
        blood_group=data.get("blood_group"),
        age=data.get("age"),
        weight=data.get("weight"),
        height=data.get("height"),
        chronic_diseases=data.get("chronic_diseases"),
        allergies=data.get("allergies"),
    )
    await message.answer(
        "✅ <b>Tibbiy profilingiz saqlandi!</b>\n\n"
        "Endi AI konsultatsiyada sizning ma'lumotlaringiz hisobga olinadi va aniqroq maslahat beriladi. 🎯",
        parse_mode="HTML",
        reply_markup=get_start_keyboard()
    )

@dp.callback_query(F.data == "clear_profile")
async def clear_profile(callback: types.CallbackQuery):
    await asyncio.to_thread(database.save_medical_profile, callback.from_user.id)  # Hammasini None qiladi
    await callback.message.edit_text(
        "🗑️ Tibbiy profilingiz tozalandi.",
        parse_mode="HTML"
    )
    await callback.answer("Profil tozalandi!")

# ═══════════════════════════════════════════════════════════════════
# FEATURE 2: 💊 DORI ESLATMALARI
# ═══════════════════════════════════════════════════════════════════

@dp.message(F.text == "💊 Dori Eslatmalari")
async def reminder_menu(message: types.Message):
    user_id = message.from_user.id
    reminders = await asyncio.to_thread(database.get_user_reminders, user_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yangi eslatma qo'shish", callback_data="add_reminder")

    # Limit hisoblash
    is_prem, *_ = await asyncio.to_thread(database.get_premium_info, user_id)
    current_count = await asyncio.to_thread(database.count_user_active_reminders, user_id)
    limit = 7 if is_prem else 3

    text = "💊 <b>Dori Eslatmalari</b>\n\n"
    if is_prem:
        slot_line = f"🌟 <b>Premium:</b> {current_count}/{limit} eslatma faol\n\n"
    else:
        slot_line = f"📊 <b>Eslatmalar:</b> {current_count}/{limit} (Oddiy)\n\n"

    if reminders:
        text += slot_line
        text += "📋 <b>Faol eslatmalaringiz:</b>\n\n"
        for rem_id, name, times, days in reminders:
            times_display = times.replace(",", ", ")
            days_icon = "🗓 Har kuni" if days == "daily" else "📆 Kunora"
            text += f"• <b>{html.escape(name)}</b> — {times_display} ({days_icon})\n"
            builder.button(text=f"🗑️ {name} o'chirish", callback_data=f"del_rem_{rem_id}")
    else:
        text += slot_line
        text += "Hozircha hech qanday eslatma yo'q.\nQuyidagi tugmadan yangi eslatma qo'shishingiz mumkin:"

    # Explain points and premium
    score = await asyncio.to_thread(database.get_score, user_id)
    text += (
        f"\n\n🏆 <b>Sizning ballaringiz:</b> {score} ball\n"
        f"💡 <b>Eslatma:</b> Har kuni botga kirib, kunlik bonus ballarni to'plang va bepul Premium obunani qo'lga kiriting!"
    )

    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "add_reminder")
async def add_reminder_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    is_prem, *_ = await asyncio.to_thread(database.get_premium_info, user_id)
    current_count = await asyncio.to_thread(database.count_user_active_reminders, user_id)
    limit = 7 if is_prem else 3

    if current_count >= limit:
        if is_prem:
            msg = (
                f"🌟 <b>Premium limitga yetdingiz!</b>\n\n"
                f"Sizda hozir <b>{current_count}/{limit}</b> ta faol eslatma bor.\n"
                f"Premium foydalanuvchilar uchun maksimal limit — <b>7 ta</b>.\n\n"
                f"Yangi eslatma qo'shish uchun eskisini o'chiring."
            )
        else:
            msg = (
                f"⚠️ <b>Kunlik limitga yetdingiz!</b>\n\n"
                f"Sizda hozir <b>{current_count}/{limit}</b> ta faol eslatma bor.\n"
                f"Oddiy foydalanuvchilar uchun maksimal limit — <b>3 ta</b>.\n\n"
                f"💎 <b>Premium</b> olsangiz — <b>7 tagacha</b> eslatma qo'sha olasiz!"
            )
            builder_lim = InlineKeyboardBuilder()
            builder_lim.button(text="💎 Premium", callback_data="show_premium")
            await callback.message.edit_text(msg, reply_markup=builder_lim.as_markup(), parse_mode="HTML")
            await callback.answer()
            return
        await callback.message.edit_text(msg, parse_mode="HTML")
        await callback.answer()
        return

    await state.set_state(ReminderStates.medicine_name)
    await callback.message.edit_text(
        "💊 <b>Yangi dori eslatmasi</b>\n\n"
        "<b>1/3</b> — Dori nomini kiriting:\n"
        "Masalan: <i>Paracetamol</i>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(ReminderStates.medicine_name)
async def reminder_medicine_name(message: types.Message, state: FSMContext):
    if not message.text:
        return await message.answer("⚠️ Iltimos, dori nomini matn ko'rinishida kiriting!")
    name = message.text.strip()
    if len(name) > 50:
        return await message.answer("⚠️ Dori nomi juda uzun! Maksimal 50 ta belgi qabul qilinadi.")
    await state.update_data(medicine_name=name)
    await state.set_state(ReminderStates.times)
    await message.answer(
        "⏰ <b>2/3 — Ichish vaqtlarini kiriting</b>\n\n"
        "Vaqtlarni vergul bilan ajrating:\n"
        "Masalan: <code>08:00,14:00,20:00</code>\n\n"
        "Yoki bitta vaqt: <code>09:00</code>",
        parse_mode="HTML"
    )

@dp.message(ReminderStates.times)
async def reminder_times(message: types.Message, state: FSMContext):
    if not message.text:
        return await message.answer("⚠️ Iltimos, vaqtlarni matn ko'rinishida kiriting!")
    raw = message.text.strip()
    # Vaqtlarni tekshirish
    times_list = [t.strip() for t in raw.split(",")]
    if len(times_list) > 10:
        return await message.answer("⚠️ Bitta eslatmada maksimal 10 ta vaqt kiritish mumkin!")
    valid_times = []
    for t in times_list:
        try:
            h, m = t.split(":")
            if 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
                valid_times.append(f"{int(h):02d}:{int(m):02d}")
            else:
                raise ValueError
        except Exception as e:
            logging.exception("Invalid time format for reminder")
            await message.answer(
                f"⚠️ <code>{t}</code> noto'g'ri vaqt formati!\n"
                "Iltimos <code>HH:MM</code> ko'rinishida kiriting (masalan: 08:00,14:00):",
                parse_mode="HTML"
            )
            return

    await state.update_data(times_str=",".join(valid_times))
    await state.set_state(ReminderStates.days)

    # Kun tanlash klaviaturasi
    builder = InlineKeyboardBuilder()
    builder.button(text="🗓 Har kuni", callback_data="rem_days_daily")
    builder.button(text="📆 Kunora", callback_data="rem_days_every_other")
    builder.adjust(2)
    await message.answer(
        "📅 <b>3/3 — Qaysi kunlari eslatish kerak?</b>\n\n"
        "🗓 <b>Har kuni</b> — Har kuni belgilangan vaqtda eslatadi\n"
        "📆 <b>Kunora</b> — Bir kun eslatadi, bir kun dam oladi",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("rem_days_"), ReminderStates.days)
async def reminder_days_chosen(callback: types.CallbackQuery, state: FSMContext):
    """Foydalanuvchi kun turini tanladi — eslatmani bazaga saqlaymiz"""
    days = "daily" if callback.data == "rem_days_daily" else "every_other"
    days_text = "🗓 Har kuni" if days == "daily" else "📆 Kunora"

    data = await state.get_data()
    await state.clear()

    medicine_name = data["medicine_name"]
    times_str = data["times_str"]
    await asyncio.to_thread(database.add_reminder, callback.from_user.id, medicine_name, times_str, days)

    await callback.message.edit_text(
        f"✅ <b>Eslatma qo'shildi!</b>\n\n"
        f"💊 <b>Dori:</b> {html.escape(medicine_name)}\n"
        f"⏰ <b>Vaqtlar:</b> {times_str.replace(',', ', ')}\n"
        f"📅 <b>Kunlar:</b> {days_text}\n\n"
        f"Bot belgilangan vaqtlarda sizga eslatma yuboradi! 🔔",
        parse_mode="HTML"
    )
    await callback.answer("✅ Eslatma saqlandi!")


@dp.callback_query(F.data.startswith("del_rem_"))
async def delete_reminder_handler(callback: types.CallbackQuery):
    rem_id = int(callback.data.replace("del_rem_", ""))
    await asyncio.to_thread(database.delete_reminder, rem_id, callback.from_user.id)
    await callback.answer("✅ Eslatma o'chirildi!", show_alert=True)
    # Ro'yxatni yangilash
    await reminder_menu_refresh(callback.message, callback.from_user.id)

async def reminder_menu_refresh(message: types.Message, user_id: int):
    reminders = await asyncio.to_thread(database.get_user_reminders, user_id)
    is_prem, *_ = await asyncio.to_thread(database.get_premium_info, user_id)
    current_count = len(reminders)
    limit = 7 if is_prem else 3

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yangi eslatma qo'shish", callback_data="add_reminder")

    if is_prem:
        slot_line = f"🌟 <b>Premium:</b> {current_count}/{limit} eslatma faol\n\n"
    else:
        slot_line = f"📊 <b>Eslatmalar:</b> {current_count}/{limit} (Oddiy)\n\n"

    text = "💊 <b>Dori Eslatmalari</b>\n\n"
    if reminders:
        text += slot_line
        text += "📋 <b>Faol eslatmalaringiz:</b>\n\n"
        for rem_id, name, times, days in reminders:
            days_icon = "🗓 Har kuni" if days == "daily" else "📆 Kunora"
            text += f"• <b>{html.escape(name)}</b> — {times.replace(',', ', ')} ({days_icon})\n"
            builder.button(text=f"🗑️ {name} o'chirish", callback_data=f"del_rem_{rem_id}")
    else:
        text += slot_line
        text += "Barcha eslatmalar o'chirildi."

    # Explain points and premium
    score = await asyncio.to_thread(database.get_score, user_id)
    text += (
        f"\n\n🏆 <b>Sizning ballaringiz:</b> {score} ball\n"
        f"💡 <b>Eslatma:</b> Har kuni botga kirib, kunlik bonus ballarni to'plang va bepul Premium obunani qo'lga kiriting!"
    )

    builder.adjust(1)
    try:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════
# FEATURE 3: 🎙️ OVOZLI XABARLAR
# ═══════════════════════════════════════════════════════════════════

@dp.message(F.voice)
async def handle_voice(message: types.Message):
    """Ovozli xabarlarni Gemini AI orqali matnlashtirish va javob berish"""
    user_id = message.from_user.id
    
    # Agar ovozli xabarda buyruq bo'lsa (masalan captionda) — o'tkazib yuboramiz
    if message.caption and message.caption.strip().startswith('/'):
        return

    # AI sozlanmagan bo'lsa limit umuman band qilinmaydi (avval limit sarflanib, qaytarilmay qolardi)
    if not gemini_client:
        await message.answer(
            "⚠️ Ovozli xabarlarni qayta ishlash uchun AI sozlanmagan.\n"
            "Iltimos, matnli savol yuboring.",
            reply_markup=get_start_keyboard()
        )
        return

    consumed_free = False
    consumed_daily = False
    try:
        if await asyncio.to_thread(database.try_consume_free_ai, user_id):
            consumed_free = True
        elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
            consumed_daily = True
        else:
            await premium_upsell(message)
            return
    except Exception:
        logging.exception("Ovoz: limitni band qilishda DB xatosi (user=%s)", user_id)
        try:
            await message.answer("⚠️ Vaqtinchalik texnik xatolik. Iltimos, birozdan so'ng qayta urinib ko'ring.")
        except Exception:
            logging.warning("DB xatosi haqida foydalanuvchiga xabar yuborib bo'lmadi", exc_info=True)
        return

    async def refund_once():
        # Faqat sarflangan limit va faqat bir marta qaytariladi (qayta chaqirilsa ham ikki marta emas)
        nonlocal consumed_free, consumed_daily
        if consumed_free:
            consumed_free = False
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            consumed_daily = False
            await asyncio.to_thread(database.refund_daily_request, user_id)

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # Ovozli xabarni yuklab olish
    status_msg = None
    try:
        status_msg = await message.answer("🎙️ <b>Ovozli xabar qayta ishlanmoqda...</b>", parse_mode="HTML")
        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_path = file.file_path

        # Faylni yuklab olish
        import io
        file_bytes = await message.bot.download_file(file_path)
        audio_data = file_bytes.read()

        # Gemini ga audio yuborish (base64)
        import base64
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        # Gemini API ga yuborish (multimodal modellar bilan)
        # google-genai SDK requires types.Part.from_bytes()
        prompt_parts = [
            genai_types.Part.from_bytes(data=audio_data, mime_type="audio/ogg"),
            (
                "Bu audio xabarni o'zbek yoki rus tilida tinglab, "
                "mazmunini o'zbekcha yozing va unga tibbiy/sog'liq nuqtai nazaridan javob bering. "
                "Agar savol tibbiyotga oid bo'lmasa, faqat sog'liq mavzusida gapirishingizni ayting."
            )
        ]

        ai_text = None
        last_err = None
        async with KeepTyping(message.bot, message.chat.id, action="typing"):
            for model in GEMINI_MULTIMODAL_MODELS:
                try:
                    response = await gemini_client.aio.models.generate_content(
                        model=model,
                        contents=prompt_parts,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=GEMINI_SYSTEM_INSTRUCTION,
                            temperature=0.7,
                        )
                    )
                    if response and response.text:
                        ai_text = response.text
                        break
                except Exception as e:
                    err = str(e)
                    logging.warning(f"Voice: {model} xato: {err[:200]}")
                    last_err = err
                    if _is_temporary_gemini_error(e) or "404" in err or "NOT_FOUND" in err:
                        continue
                    break

        if not ai_text or not ai_text.strip():
            # Fallback: API ovozni qayta ishlay olmasa
            logging.error(f"Voice: barcha modellar ishlamadi. Oxirgi xato: {last_err}")
            await refund_once()
            await status_msg.edit_text(
                "⚠️ Ovozli xabarni matnlashtirish vaqtincha ishlamayapti.\n\n"
                "Iltimos, savolingizni <b>matn ko'rinishida</b> yuboring. 📝",
                parse_mode="HTML"
            )
            return

        state_str = await _deliver_ai_response(
            message, status_msg, ai_text,
            header_html="🎙️ <b>Ovozli xabaringiz qabul qilindi!</b>\n\n",
            header_plain="🎙️ Ovozli xabaringiz qabul qilindi!\n\n",
        )
        if state_str == "failed":
            await refund_once()
            try:
                await status_msg.edit_text(
                    "⚠️ Ovozli xabarni qayta ishlashda xatolik yuz berdi.\n"
                    "Iltimos, matnli savol yuboring.",
                    parse_mode="HTML"
                )
            except Exception as ex:
                logging.error(f"Ovoz xato xabarini yuborib bo'lmadi: {ex}")
        elif state_str == "partial":
            try:
                await message.answer(
                    "⚠️ Javobning davomi texnik xato tufayli yuborilmadi. Savolni qisqaroq qilib qayta yuboring."
                )
            except Exception:
                logging.warning("Qisman javob ogohlantirishini yuborib bo'lmadi", exc_info=True)
        # state_str in ("delivered", "partial", "ambiguous") -> limit qaytarilmaydi

    except Exception as e:
        logging.error(f"Voice handler xatosi: {e}")
        await refund_once()
        err_text = (
            "⚠️ Ovozli xabarni qayta ishlashda xatolik yuz berdi.\n"
            "Iltimos, matnli savol yuboring."
        )
        try:
            if status_msg:
                await status_msg.edit_text(err_text, parse_mode="HTML")
            else:
                await message.answer(err_text, parse_mode="HTML")
        except Exception as ex:
            logging.error(f"Ovoz xato xabarini yuborib bo'lmadi: {ex}")

# ═══════════════════════════════════════════════════════════════════
# FEATURE 5: ⚖️ SOG'LIQ KALKULYATORI (BMI + Suv balansi)
# ═══════════════════════════════════════════════════════════════════

@dp.message(F.text == "⚖️ Sog'liq Kalkulyatori")
async def health_calculator_menu(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="⚖️ BMI (Tana Vazni Indeksi)", callback_data="calc_bmi")
    builder.button(text="💧 Suv balansi kalkulyatori",  callback_data="calc_water")
    builder.adjust(1)
    await message.answer(
        "⚖️ <b>Sog'liq Kalkulyatorlari</b>\n\n"
        "Quyidagi kalkulyatorlardan birini tanlang:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "calc_bmi")
async def calc_bmi_start(callback: types.CallbackQuery, state: FSMContext):
    # Profilda ma'lumot bo'lsa, undan foydalanamiz
    profile = await asyncio.to_thread(database.get_medical_profile, callback.from_user.id)
    if profile and profile[2] and profile[3]:
        weight, height = profile[2], profile[3]
        result = _calculate_bmi(weight, height)
        await callback.message.edit_text(result, parse_mode="HTML")
        await callback.answer()
        return

    await state.set_state(BmiStates.weight)
    await callback.message.edit_text(
        "⚖️ <b>BMI Kalkulyatori</b>\n\n"
        "<b>1/2</b> — Vazningizni kiriting (kg):\n"
        "Masalan: <code>70</code>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(BmiStates.weight)
async def bmi_weight(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text.strip().replace(",", "."))
        if not (20 <= weight <= 300):
            raise ValueError
        await state.update_data(weight=weight)
        await state.set_state(BmiStates.height)
        await message.answer(
            "📏 <b>2/2</b> — Bo'yingizni kiriting (sm):\n"
            "Masalan: <code>175</code>",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("⚠️ 20 dan 300 gacha bo'lgan raqam kiriting:")

@dp.message(BmiStates.height)
async def bmi_height(message: types.Message, state: FSMContext):
    try:
        height = float(message.text.strip().replace(",", "."))
        if not (50 <= height <= 250):
            raise ValueError
        data = await state.get_data()
        await state.clear()
        result = _calculate_bmi(data["weight"], height)
        await message.answer(result, parse_mode="HTML", reply_markup=get_start_keyboard())
    except ValueError:
        await message.answer("⚠️ 50 dan 250 gacha bo'lgan raqam kiriting (sm):")

def _calculate_bmi(weight: float, height: float) -> str:
    height_m = height / 100
    bmi = weight / (height_m ** 2)
    if bmi < 18.5:
        category = "🔵 <b>Tana og'irligi yetarli emas (kam vazn)</b>"
        advice = "Ko'proq kaloriyali va oqsilli ovqatlar iste'mol qiling. Shifokor bilan maslahatlashing."
    elif bmi < 25:
        category = "🟢 <b>Normal vazn (sog'lom)</b>"
        advice = "Ajoyib! Sog'lom hayot tarzini davom ettiring."
    elif bmi < 30:
        category = "🟡 <b>Ortiqcha vazn (pre-obesitas)</b>"
        advice = "Jismoniy faollikni oshiring va ratsionni nazorat qiling."
    elif bmi < 35:
        category = "🟠 <b>1-darajali semizlik</b>"
        advice = "Shifokor yoki dietolog bilan maslahatlashing."
    else:
        category = "🔴 <b>2-darajali va yuqori semizlik</b>"
        advice = "Zudlik bilan shifokor bilan maslahatlashing!"

    return (
        f"⚖️ <b>BMI Hisob natijasi</b>\n\n"
        f"📊 <b>Vazn:</b> {weight} kg\n"
        f"📏 <b>Bo'y:</b> {height} sm\n"
        f"🧮 <b>BMI:</b> {bmi:.1f}\n\n"
        f"{category}\n\n"
        f"💡 <b>Maslahat:</b> {advice}"
    )

@dp.callback_query(F.data == "calc_water")
async def calc_water_start(callback: types.CallbackQuery, state: FSMContext):
    profile = await asyncio.to_thread(database.get_medical_profile, callback.from_user.id)
    if profile and profile[2]:
        weight = profile[2]
        result = _calculate_water(weight)
        await callback.message.edit_text(result, parse_mode="HTML")
        await callback.answer()
        return

    await state.set_state(WaterStates.weight)
    await callback.message.edit_text(
        "💧 <b>Suv Balansi Kalkulyatori</b>\n\n"
        "Vazningizni kiriting (kg):\n"
        "Masalan: <code>70</code>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(WaterStates.weight)
async def water_weight(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text.strip().replace(",", "."))
        if not (20 <= weight <= 300):
            raise ValueError
        await state.clear()
        result = _calculate_water(weight)
        await message.answer(result, parse_mode="HTML", reply_markup=get_start_keyboard())
    except ValueError:
        await message.answer("⚠️ To'g'ri raqam kiriting (masalan: 70):")

def _calculate_water(weight: float) -> str:
    daily_ml = weight * 35
    glasses  = daily_ml / 250
    sport_ml = daily_ml + 500
    summer_ml = daily_ml + 300
    return (
        f"💧 <b>Kunlik Suv Balansi</b>\n\n"
        f"⚖️ <b>Vazniga qarab ({weight} kg):</b>\n\n"
        f"🥛 Kunlik minimum: <b>{daily_ml:.0f} ml</b> (~{glasses:.0f} ta stakan)\n"
        f"🏃 Sport qilganda: <b>{sport_ml:.0f} ml</b>\n"
        f"☀️ Issiq havoda: <b>{summer_ml:.0f} ml</b>\n\n"
        f"💡 <b>Maslahat:</b>\n"
        f"• Ertalab uyg'onganingizda 1-2 stakan suv iching\n"
        f"• Ovqatdan 30 daqiqa oldin suv iching\n"
        f"• Siydik rangi och sariq bo'lishi — me'yor belgisi"
    )

# ═══════════════════════════════════════════════════════════════════
# FEATURE 6: ⭐ TELEGRAM STARS TO'LOV TIZIMI
# ═══════════════════════════════════════════════════════════════════

async def _show_premium_page(message_or_cb):
    """Premium sahifasini ko'rsatish — to'liq FINAL pricing matrix bo'yicha"""
    is_callback = isinstance(message_or_cb, types.CallbackQuery)
    user_id = message_or_cb.from_user.id

    is_prem, expires, prem_type = await asyncio.to_thread(database.get_premium_info, user_id)
    if is_prem and expires:
        try:
            exp_dt = datetime.fromisoformat(expires)
            exp_str = exp_dt.strftime("%d.%m.%Y")
        except Exception:
            exp_str = str(expires)

        tier_title = "⭐ Premium Pro"
        if prem_type == "plus":
            tier_title = "💎 Premium Plus"
        elif prem_type == "ultra":
            tier_title = "👑 Premium Ultra"

        text = (
            f"💎 <b>Sizda faol obuna mavjud!</b>\n\n"
            f"🏷️ Tarif: <b>{tier_title}</b>\n"
            f"📅 Amal qilish muddati: <b>{exp_str}</b> gacha\n\n"
            f"✅ Barcha imkoniyatlardan unumli foydalaning!"
        )
        # SUPER PRIZ chegirmasi bor va Plus ga o'tish mumkin bo'lsa — tugmani ko'rsatamiz
        markup = None
        if prem_type not in ("plus", "ultra") and await asyncio.to_thread(database.has_discount, user_id):
            text += f"\n\n🎁 <b>Sizda SUPER PRIZ chegirmasi bor:</b> 30 kun Premium Plus — {plus_discount_price()} Stars"
            builder = InlineKeyboardBuilder()
            builder.button(text=f"🎁 {plus_discount_price()} Stars → 30 kun Premium Plus (-50%)",
                           callback_data="buy_plus_30_discount")
            markup = builder.as_markup()
        if is_callback:
            try:
                await message_or_cb.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            except Exception:
                await message_or_cb.message.answer(text, parse_mode="HTML", reply_markup=markup)
            await message_or_cb.answer()
        else:
            await message_or_cb.answer(text, parse_mode="HTML", reply_markup=markup)
        return

    score = await asyncio.to_thread(database.get_score, user_id)

    text = (
        "💎 <b>PREMIUM OBS TARIFLARI</b>\n\n"
        "O'zingizga mos tarifni tanlang va barcha tibbiy imkoniyatlarga ega bo'ling:\n\n"
        "🎁 <b>BEPUL REWARD</b>\n"
        "• <b>100 Ball → 3 kun Premium Pro</b>\n"
        "  <i>Botda to'plagan ballaringiz evaziga!</i>\n\n"
        "⭐ <b>PREMIUM PRO</b>\n"
        "• <b>50 ⭐ → 7 kun Premium Pro</b>\n"
        "  • Kuniga 15 ta AI konsultatsiya\n"
        "  • Ovozli xabar bilan muloqot\n"
        "  • Shaxsiy tibbiy profil tahlili\n\n"
        "💎 <b>PREMIUM PLUS</b>\n"
        "• <b>150 ⭐ → 30 kun Premium Plus</b>\n"
        "  • Kuniga 30 ta AI konsultatsiya\n"
        "  • Barcha Premium Pro imkoniyatlari\n\n"
        "👑 <b>PREMIUM ULTRA</b>\n"
        "• <b>300 ⭐ → 30 kun Premium Ultra</b>\n"
        "  • 100 AI so‘rov/kun + kengaytirilgan AI imkoniyatlari\n"
        "  • Prioritet AI javobi va barcha Ultra imkoniyatlar\n\n"
        f"🏆 <b>Sizning ballaringiz:</b> <b>{score}</b> ball\n\n"
        "👇 Sotib olish yoki almashtirish uchun tugmani bosing:"
    )

    web_app_url = await get_web_app_url(user_id, page="wheel")
    builder = InlineKeyboardBuilder()

    if await asyncio.to_thread(database.has_discount, user_id):
        text = (
            f"🎁 <b>Sizda SUPER PRIZ chegirmasi bor!</b> 30 kun Premium Plus — "
            f"<s>{get_stars_tariffs()['PLUS_30_DAYS'][3]}</s> <b>{plus_discount_price()} Stars</b> (bir martalik)\n\n" + text
        )
        builder.button(text=f"🎁 {plus_discount_price()} Stars → 30 kun Premium Plus (-50%)",
                       callback_data="buy_plus_30_discount")

    if score >= 100:
        builder.button(text="🎁 100 ball → 3 kun Premium Pro", callback_data="redeem_points_premium")
    else:
        builder.button(text=f"🎁 100 ball → 3 kun Pro (Yana {100 - score} ball kerak)", callback_data="redeem_points_info")

    builder.button(text="⭐ 50 Stars → 7 kun Premium Pro", callback_data="buy_pro_7")
    builder.button(text="💎 150 Stars → 30 kun Premium Plus", callback_data="buy_plus_30")
    builder.button(text="👑 300 Stars → 30 kun Premium Ultra", callback_data="buy_ultra_30")

    if web_app_url:
        builder.button(text="🎡 Omad barabani", web_app=types.WebAppInfo(url=web_app_url))
    builder.button(text="👥 Do'stlarni taklif qilish", callback_data="show_ref_from_cmd")
    builder.adjust(1)

    if is_callback:
        try:
            await message_or_cb.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            await message_or_cb.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await message_or_cb.answer()
    else:
        await message_or_cb.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.in_(["buy_premium", "show_premium"]))
async def process_buy_premium(callback: types.CallbackQuery):
    await _show_premium_page(callback)

@dp.callback_query(F.data == "redeem_points_info")
async def process_redeem_points_info(callback: types.CallbackQuery):
    score = await asyncio.to_thread(database.get_score, callback.from_user.id)
    needed = max(0, 100 - score)
    logging.info(f"User {callback.from_user.id} requested redeem points info: score={score}, needed={needed}")
    await callback.answer(f"⚠️ Sizda {score} ball bor. 3 kunlik Premium Pro uchun yana {needed} ball to'plashingiz kerak!", show_alert=True)

@dp.callback_query(F.data == "redeem_points_premium")
async def process_redeem_points_premium(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    success = await asyncio.to_thread(database.check_and_grant_premium, user_id)
    if success:
        logging.info(f"User {user_id} successfully redeemed 100 points for Premium Pro.")
        await callback.answer("🎉 100 ball yechildi! 3 kunlik Premium Pro aktivlashtirildi!", show_alert=True)
        await _show_premium_page(callback)
    else:
        score = await asyncio.to_thread(database.get_score, user_id)
        logging.info(f"User {user_id} failed redeem: score={score}")
        await callback.answer(f"⚠️ Ballaringiz yetarli emas (Hozirda {score} ball bor).", show_alert=True)

@dp.callback_query(F.data.in_(["buy_pro_7", "buy_plus_30", "buy_plus_30_discount", "buy_ultra_30", "pay_stars"]))
async def process_pay_stars_tariff(callback: types.CallbackQuery):
    """Telegram Stars tariflari invoice yuborish"""
    try:
        user_id = callback.from_user.id
        action = callback.data

        user_info = await asyncio.to_thread(database.get_user_info, user_id)
        eligible, current_tier_name = check_premium_purchase_eligibility(user_info, action)
        if not eligible:
            await callback.answer(
                f"ℹ️ Siz allaqachon {current_tier_name} foydalanuvchisiz! Joriy tarifingiz sotib olmoqchi bo'lgan tarifdan yuqoriroq yoki teng.",
                show_alert=True
            )
            return

        if action in ("buy_pro_7", "pay_stars"):
            title = "⭐ Premium Pro — 7 kun"
            desc = "7 kunlik Premium Pro obuna: Kuniga 15 AI so'rov, ovozli maslahat va tibbiy profil."
            payload = "PRO_7_DAYS"
            stars = int(os.getenv("PRO_TRIAL_STARS", "50"))
        elif action == "buy_plus_30":
            title = "💎 Premium Plus — 30 kun"
            desc = "30 kunlik Premium Plus obuna: Kuniga 30 AI so'rov va barcha Premium imkoniyatlar."
            payload = "PLUS_30_DAYS"
            stars = int(os.getenv("PRO_MONTHLY_STARS", "150"))
        elif action == "buy_plus_30_discount":
            if not await asyncio.to_thread(database.has_discount, user_id):
                await callback.answer("ℹ️ Sizda faol chegirma yo'q.", show_alert=True)
                return
            title, desc, payload, stars = discount_plus_offer()
        elif action == "buy_ultra_30":
            title = "👑 Premium Ultra — 30 kun"
            desc = "30 kunlik Premium Ultra obuna: Kuniga 100 AI so'rov (Cheksiz) va prioritet maslahat."
            payload = "ULTRA_30_DAYS"
            stars = int(os.getenv("ULTRA_MONTHLY_STARS", "300"))
        else:
            await callback.answer("⚠️ Noto'g'ri tarif tanlandi.", show_alert=True)
            return

        # Validate stars amount
        if stars <= 0:
            raise ValueError("Stars price must be greater than zero")

        prices = [LabeledPrice(label=title, amount=stars)]
        await callback.message.answer_invoice(
            title=title,
            description=desc,
            payload=payload,
            currency=STARS_CURRENCY,
            prices=prices,
            provider_token=STARS_PROVIDER_TOKEN,
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Stars invoice generation error: {e}", exc_info=True)
        await callback.answer("⚠️ Invoice yaratishda xatolik yuz berdi. Administrator bilan bog'laning.", show_alert=True)

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    """To'lovni tasdiqlash (10 soniya ichida javob berish shart)"""
    try:
        user_id = pre_checkout_query.from_user.id
        is_banned, *_ = await asyncio.to_thread(database.is_user_banned, user_id)
        if is_banned:
            logging.warning(f"Pre-checkout rad etildi (bloklangan user): user={user_id}")
            await pre_checkout_query.answer(
                ok=False,
                error_message="Hisobingiz bloklanganligi sababli to'lov qabul qilinmaydi."
            )
            return

        ok, reason = validate_payment(
            pre_checkout_query.invoice_payload,
            pre_checkout_query.currency,
            pre_checkout_query.total_amount
        )
        if not ok:
            logging.warning(
                f"Pre-checkout rad etildi: user={user_id}, "
                f"payload={pre_checkout_query.invoice_payload}, currency={pre_checkout_query.currency}, "
                f"amount={pre_checkout_query.total_amount}, reason={reason}"
            )
            await pre_checkout_query.answer(
                ok=False,
                error_message="To'lov ma'lumotlarida xatolik aniqlandi. Iltimos, /premium orqali qaytadan urinib ko'ring."
            )
            return

        if pre_checkout_query.invoice_payload == DISCOUNT_PAYLOAD:
            if not await asyncio.to_thread(database.has_discount, user_id):
                logging.warning(f"Pre-checkout rad etildi (chegirma yo'q yoki ishlatilgan): user={user_id}")
                await pre_checkout_query.answer(
                    ok=False,
                    error_message="Chegirma allaqachon ishlatilgan. /premium orqali oddiy tarifni tanlang."
                )
                return

        await pre_checkout_query.answer(ok=True)
    except Exception as e:
        logging.error(f"Pre-checkout ishlovida kutilmagan xatolik: {e}", exc_info=True)
        try:
            await pre_checkout_query.answer(
                ok=False,
                error_message="To'lovni tasdiqlashda vaqtinchalik xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
            )
        except Exception:
            pass

@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    """Muvaffaqiyatli to'lov — Stars to'lovi va duplicate protection (bitta atomar DB tranzaksiya)"""
    user_id = message.from_user.id
    payment = message.successful_payment
    payload = payment.invoice_payload

    # XAVFSIZLIK: Telegram Stars to'lovlarida haqiqiy telegram_payment_charge_id bo'lishi shart.
    # Soxta yoki message_id asosidagi soxta charge_id ga ruxsat berilmaydi.
    if payment.currency == STARS_CURRENCY:
        charge_id = payment.telegram_payment_charge_id
    else:
        charge_id = payment.provider_payment_charge_id or payment.telegram_payment_charge_id

    if not charge_id:
        logging.error(f"To'lovda haqiqiy charge_id topilmadi: user={user_id}, currency={payment.currency}")
        await message.answer("⚠️ To'lov tranzaksiya identifikatori topilmadi. Administrator bilan bog'laning.")
        return

    username = f"@{html.escape(message.from_user.username)}" if message.from_user.username else f"ID:{user_id}"

    ok, reason = validate_payment(payload, payment.currency, payment.total_amount)
    if not ok:
        if reason == "payload":
            logging.critical(
                f"UNKNOWN PAYLOAD on successful payment: user={user_id}, payload={payload}, "
                f"currency={payment.currency}, amount={payment.total_amount}, charge_id={charge_id}"
            )
            saved = False
            try:
                saved = bool(record_failed_payment(charge_id, user_id, str(payload), payment.total_amount))
            except Exception as rec_err:
                logging.critical(f"Failed to record evidence for unknown payload charge_id={charge_id}: {rec_err}", exc_info=True)
                saved = False

            await message.answer(
                "⚠️ To'lov qabul qilindi, lekin paket turini aniqlashda xatolik yuz berdi.\n"
                "Mablag'ingiz yo'qolmaydi! Administratorga xabar berildi va Premium tez orada qo'lda faollashtiriladi.",
                reply_markup=get_start_keyboard()
            )
            try:
                safe_payload = html.escape(str(payload)[:100])
                safe_charge_id = html.escape(str(charge_id)[:100])
                status_note = "✅ Dalil saqlandi" if saved else "❌ DIQQAT: Dalilni saqlashda xatolik!"
                await message.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🚨 <b>DIQQAT: Noma'lum to'lov payload'i!</b>\n\n"
                        f"👤 Foydalanuvchi: {username}\n"
                        f"🆔 User ID: <code>{user_id}</code>\n"
                        f"📦 Payload: <code>{safe_payload}</code>\n"
                        f"💰 Summa: {payment.total_amount} {payment.currency}\n"
                        f"🆔 Charge ID: <code>{safe_charge_id}</code>\n"
                        f"📌 Dalil holati: {status_note}\n\n"
                        f"Iltimos, tekshirib foydalanuvchiga Premium qo'lda berilsin!"
                    ),
                    parse_mode="HTML"
                )
            except Exception as admin_err:
                logging.error(f"Adminga noma'lum to'lov xabari yuborishda xato: {admin_err}")
            return

        logging.error(
            f"Successful payment validation failed: user={user_id}, payload={payload}, "
            f"currency={payment.currency}, amount={payment.total_amount}, reason={reason}"
        )
        await message.answer("⚠️ To'lov parametrlarida nomuvofiqlik aniqlandi. Administrator bilan bog'laning.")
        try:
            safe_payload = html.escape(str(payload)[:100])
            safe_charge_id = html.escape(str(charge_id)[:100])
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⚠️ <b>To'lov validatsiyasi muvaffaqiyatsiz bo'ldi!</b>\n\n"
                    f"👤 Foydalanuvchi: {username}\n"
                    f"🆔 User ID: <code>{user_id}</code>\n"
                    f"📦 Payload: <code>{safe_payload}</code>\n"
                    f"💰 Summa: {payment.total_amount} {payment.currency}\n"
                    f"🆔 Charge ID: <code>{safe_charge_id}</code>\n"
                    f"❌ Sabab: {html.escape(reason)}"
                ),
                parse_mode="HTML"
            )
        except Exception as admin_err:
            logging.error(f"Adminga validatsiya xatosi xabarini yuborishda xato: {admin_err}")
        return

    tariffs = get_stars_tariffs()
    product_map = {k: (v[0], v[1], v[2]) for k, v in tariffs.items()}
    product_map.update(LEGACY_STARS_PAYLOADS)

    if payload in product_map:
        if payload in LEGACY_STARS_PAYLOADS:
            logging.warning(
                f"Legacy Stars payment processed: user={user_id}, payload={payload}, "
                f"stars={payment.total_amount}, charge_id={charge_id}"
            )
        prem_type, days, product_title = product_map[payload]
        try:
            granted, until = await asyncio.to_thread(
                database.process_paid_premium,
                charge_id, user_id, payload, payment.total_amount, prem_type, days,
                payload == DISCOUNT_PAYLOAD,  # chegirma shu tranzaksiyada sarflanadi
            )
        except Exception as e:
            logging.error(f"process_paid_premium DB error for user {user_id}, charge_id {charge_id}: {e}", exc_info=True)
            # Haqiqiy Telegram to'lov dalilini reestrga saqlash
            saved = False
            try:
                saved = bool(record_failed_payment(charge_id, user_id, payload, payment.total_amount))
            except Exception as rec_err:
                logging.critical(f"Failed to record evidence for Stars DB error charge_id={charge_id}: {rec_err}", exc_info=True)
                saved = False
            if saved:
                await message.answer(
                    "⚠️ To'lov qabul qilindi, ammo tizimda vaqtinchalik xatolik yuz berdi.\n"
                    "To'lovingiz saqlab qolindi. Iltimos, administrator bilan bog'laning yoki birozdan so'ng /start bosing.",
                    reply_markup=get_start_keyboard()
                )
            else:
                await message.answer(
                    f"⚠️ To'lov qabul qilindi, ammo tizimda vaqtinchalik xatolik yuz berdi.\n"
                    f"Iltimos, to'lov identifikatoringizni administratorga yuboring: {charge_id}",
                    reply_markup=get_start_keyboard()
                )
            try:
                safe_charge_id = html.escape(str(charge_id)[:100])
                status_note = "✅ Dalil saqlandi" if saved else "❌ DIQQAT: Dalilni saqlashda xatolik!"
                reconcile_hint = (
                    f"🔧 Tiklash uchun: <code>/reconcile {safe_charge_id}</code>"
                    if saved else
                    "⚠️ Dalil SQLite bazasiga yozilmadi — foydalanuvchiga Premium qo'lda berilsin!"
                )
                await message.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"🚨 <b>To'lov DB xatosi (Premium berilmadi)!</b>\n\n"
                        f"👤 Foydalanuvchi: {username}\n"
                        f"🆔 User ID: <code>{user_id}</code>\n"
                        f"📦 Mahsulot: {product_title}\n"
                        f"💰 Summa: {payment.total_amount} {payment.currency}\n"
                        f"🆔 Charge ID: <code>{safe_charge_id}</code>\n"
                        f"📌 Dalil holati: {status_note}\n"
                        f"{reconcile_hint}"
                    ),
                    parse_mode="HTML"
                )
            except Exception as admin_err:
                logging.error(f"Adminga DB to'lov xatosi xabarini yuborishda xato: {admin_err}")
            return

        if not granted:
            await message.answer("⚠️ Bu to'lov allaqachon qayta ishlangan!", reply_markup=get_start_keyboard())
            return

        exp_str = until.strftime("%d.%m.%Y")

        await message.answer(
            f"🎉 <b>To'lov muvaffaqiyatli qabul qilindi!</b>\n\n"
            f"📦 Mahsulot: <b>{product_title}</b>\n"
            f"⭐ Sarflandi: <b>{payment.total_amount} Stars</b>\n"
            f"📅 Amal qilish muddati: <b>{exp_str}</b> gacha\n\n"
            f"Barcha imkoniyatlar faollashtirildi! 🚀",
            parse_mode="HTML",
            reply_markup=get_start_keyboard()
        )

        # Adminga bildirishnoma
        try:
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⭐ <b>Yangi Stars To'lovi!</b>\n\n"
                    f"👤 Foydalanuvchi: {username}\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"📦 Mahsulot: {product_title}\n"
                    f"⭐ Stars: {payment.total_amount}\n"
                    f"🆔 Charge ID: <code>{charge_id}</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Adminga Stars to'lov xabari yuborishda xato: {e}")

    else:
        # Noma'lum payload kelganda: foydalanuvchi to'lovi yo'qolmasligi uchun dalilni saqlash va adminga xabar berish
        logging.critical(
            f"UNKNOWN PAYLOAD on successful payment: user={user_id}, payload={payload}, "
            f"currency={payment.currency}, amount={payment.total_amount}, charge_id={charge_id}"
        )
        saved = False
        try:
            saved = bool(record_failed_payment(charge_id, user_id, str(payload), payment.total_amount))
        except Exception as rec_err:
            logging.critical(f"Failed to record evidence for unknown payload charge_id={charge_id}: {rec_err}", exc_info=True)
            saved = False

        await message.answer(
            "⚠️ To'lov qabul qilindi, lekin paket turini aniqlashda xatolik yuz berdi.\n"
            "Mablag'ingiz yo'qolmaydi! Administratorga xabar berildi va Premium tez orada qo'lda faollashtiriladi.",
            reply_markup=get_start_keyboard()
        )
        try:
            safe_payload = html.escape(str(payload)[:100])
            safe_charge_id = html.escape(str(charge_id)[:100])
            status_note = "✅ Dalil saqlandi" if saved else "❌ DIQQAT: Dalilni saqlashda xatolik!"
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚨 <b>DIQQAT: Noma'lum to'lov payload'i!</b>\n\n"
                    f"👤 Foydalanuvchi: {username}\n"
                    f"🆔 User ID: <code>{user_id}</code>\n"
                    f"📦 Payload: <code>{safe_payload}</code>\n"
                    f"💰 Summa: {payment.total_amount} {payment.currency}\n"
                    f"🆔 Charge ID: <code>{safe_charge_id}</code>\n"
                    f"📌 Dalil holati: {status_note}\n\n"
                    f"Iltimos, tekshirib foydalanuvchiga Premium qo'lda berilsin!"
                ),
                parse_mode="HTML"
            )
        except Exception as admin_err:
            logging.error(f"Adminga noma'lum to'lov xabari yuborishda xato: {admin_err}")


@dp.message(Command("reconcile"))
async def cmd_reconcile_payment(message: types.Message):
    """Admin uchun to'lovni xavfsiz tiklash (reconciliation) komandasi.
    Faqat Telegram tomonidan yuborilgan va muvaffaqiyatsiz bo'lgan to'lov dalili mavjud bo'lsagina ishlaydi.
    Format: /reconcile <charge_id> yoki ro'yxat uchun: /reconcile
    """
    # XAVFSIZLIK: Faqat haqiqiy raqamli ADMIN_ID ga ruxsat beriladi
    if not ADMIN_ID or not str(ADMIN_ID).isdigit() or int(message.from_user.id) != int(ADMIN_ID):
        return

    parts = message.text.split()
    # 1. Argument berilmagan bo'lsa: kutilayotgan tasdiqlangan to'lovlar ro'yxatini ko'rsatish
    if len(parts) == 1:
        pending = get_all_pending_failed_payments()
        if not pending:
            await message.answer("✅ Hozirda tiklanishi kutilayotgan tasdiqlangan to'lov dalillari mavjud emas.")
            return
        msg = "📋 <b>Tiklanishi kutilayotgan tasdiqlangan to'lovlar:</b>\n\n"
        for p in pending:
            msg += (
                f"• Charge ID: <code>{html.escape(str(p['charge_id']))}</code>\n"
                f"  User: <code>{p['user_id']}</code> | Paket: <code>{html.escape(str(p['payload']))}</code> | ⭐ {p.get('stars', 0)}\n"
                f"  Vaqt: {str(p.get('created_at', ''))[:19]}\n"
                f"  Tiklash: <code>/reconcile {html.escape(str(p['charge_id']))}</code>\n\n"
            )
        await message.answer(msg, parse_mode="HTML")
        return

    # 2. Argumentlar: /reconcile <charge_id> YOKI /reconcile <user_id> <payload> <charge_id>
    if len(parts) == 2:
        charge_id = parts[1].strip()
    elif len(parts) >= 4:
        charge_id = parts[3].strip()
    else:
        await message.answer(
            "⚠️ Format: <code>/reconcile &lt;charge_id&gt;</code>\n"
            "Yoki ro'yxatni ko'rish uchun: <code>/reconcile</code>",
            parse_mode="HTML"
        )
        return

    # Format tekshiruvi
    if len(charge_id) < 5 or not re.match(r'^[A-Za-z0-9_\-:]+$', charge_id):
        await message.answer("❌ Noto'g'ri charge_id formati! Haqiqiy Telegram charge_id kiritilishi shart.")
        return

    # XAVFSIZLIK: Telegram tomonidan yuborilgan to'lov dalilini tekshirish
    evidence = get_pending_failed_payment(charge_id)
    if not evidence:
        await message.answer(
            f"❌ <b>Rad etildi: To'lov dalili topilmadi!</b>\n\n"
            f"Ushbu charge_id (<code>{html.escape(charge_id)}</code>) bo'yicha Telegram tomonidan tasdiqlangan to'lov mavjud emas.\n"
            f"Xavfsizlik qoidalariga muvofiq, dalilsiz soxta ID bilan Premium berish qat'iyan taqiqlangan.",
            parse_mode="HTML"
        )
        return

    # Barcha parametrlar Telegram bergan asl dalildan olinadi (soxtalashtirish imkonsiz)
    target_uid = evidence["user_id"]
    payload = evidence["payload"]
    stars = evidence.get("stars", 0)

    try:
        tariffs = get_stars_tariffs()
        product_map = {k: (v[0], v[1], v[2], v[3]) for k, v in tariffs.items()}
        product_map.update(LEGACY_STARS_PAYLOADS)

        if payload in product_map:
            mapping = product_map[payload]
            prem_type = mapping[0]
            days = mapping[1]
            product_title = mapping[2]
            if len(mapping) > 3:
                stars = mapping[3]
        else:
            await message.answer(
                f"❌ <b>Tiklab bo'lmadi: Noma'lum mahsulot payload'i ({html.escape(str(payload))})!</b>\n\n"
                f"Ushbu to'lov uchun avtomatik Premium berish taqiqlangan. "
                f"Iltimos, tekshirib foydalanuvchiga Premiumni /set_premium orqali qo'lda bering.",
                parse_mode="HTML"
            )
            return

        granted, until = await asyncio.to_thread(
            database.process_paid_premium,
            charge_id, target_uid, payload, stars, prem_type, days,
            payload == DISCOUNT_PAYLOAD,
        )
        if not granted:
            remove_pending_failed_payment(charge_id)
            await message.answer(f"⚠️ Ushbu charge_id (<code>{html.escape(charge_id)}</code>) allaqachon bazaga yozilgan va hisoblangan!", parse_mode="HTML")
            return

        # Muvaffaqiyatli saqlandi — dalilni reestrdan o'chiramiz
        remove_pending_failed_payment(charge_id)

        exp_str = until.strftime("%d.%m.%Y")
        await message.answer(
            f"✅ <b>To'lov muvaffaqiyatli tiklandi va hisoblandi!</b>\n\n"
            f"👤 User: <code>{target_uid}</code>\n"
            f"📦 Mahsulot: {product_title}\n"
            f"📅 Yangi muddat: <b>{exp_str}</b> gacha\n"
            f"🆔 Charge ID: <code>{html.escape(charge_id)}</code>",
            parse_mode="HTML"
        )
        try:
            await message.bot.send_message(
                chat_id=target_uid,
                text=(
                    f"🎉 <b>To'lovingiz tasdiqlandi va Premium faollashtirildi!</b>\n\n"
                    f"📦 Mahsulot: <b>{product_title}</b>\n"
                    f"📅 Amal qilish muddati: <b>{exp_str}</b> gacha\n\n"
                    f"Keltirilgan noqulaylik uchun uzr so'raymiz."
                ),
                parse_mode="HTML"
            )
        except Exception as u_err:
            logging.warning(f"Reconcile foydalanuvchiga xabar yuborishda xato: {u_err}")
    except Exception as e:
        logging.error(f"Reconcile error: {e}", exc_info=True)
        await message.answer(f"❌ Xatolik yuz berdi: {html.escape(str(e))}", parse_mode="HTML")


# ─── Manual to'lov (karta cheki yuborish) ─────────────────────────


@dp.callback_query(F.data == "send_receipt")
async def process_send_receipt(callback: types.CallbackQuery, state: FSMContext):
    if not CARD_NUMBER:
        await callback.message.answer("⚠️ Karta orqali to'lov hozircha ishlamayapti. Iltimos, admin bilan bog'laning.")
        await callback.answer()
        return
        
    await state.set_state(PaymentStates.waiting_for_receipt)
    await asyncio.to_thread(database.set_waiting_receipt, callback.from_user.id, 1)
    await callback.message.edit_text(
        f"💳 <b>Karta orqali to'lov:</b>\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"👤 {CARD_NAME}\n\n"
        f"💰 Miqdor: <b>10,000 so'm</b> (1 oylik Premium)\n\n"
        f"To'lovdan so'ng <b>chek skrinshotini</b> shu yerga yuboring 👇",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(PaymentStates.waiting_for_receipt, F.photo)
async def handle_receipt_photo(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await asyncio.to_thread(database.set_waiting_receipt, user_id, 0)
    username = f"@{html.escape(message.from_user.username)}" if message.from_user.username else "Noma'lum"
    photo_id = message.photo[-1].file_id
    # Generate a unique token for this receipt
    token = uuid.uuid4().hex
    receipt_created = await asyncio.to_thread(database.create_manual_receipt, user_id, token)
    admin_keyboard = InlineKeyboardBuilder()
    if receipt_created:
        admin_keyboard.button(text="✅ Tasdiqlash (Premium berish)", callback_data=f"adm_app_{user_id}_{token}")
        admin_keyboard.button(text="❌ Rad etish",                    callback_data=f"adm_rej_{user_id}_{token}")
        admin_keyboard.adjust(1, 1)
    else:
        logging.warning(f"Failed to create manual receipt for user {user_id}, token {token}")
    try:
        await message.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=(
                f"🔔 <b>Yangi karta to'lov so'rovi!</b>\n\n"
                f"👤 <b>Foydalanuvchi:</b> {username}\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                "Premium faollashtirish yoki rad etish uchun tugmani bosing:"
            ),
            reply_markup=admin_keyboard.as_markup(),
            parse_mode="HTML"
        )
        await message.answer(
            "✅ <b>To'lov cheki qabul qilindi!</b>\n\n"
            "Admin tekshirib, sizga xabar yuboradi. Iltimos kuting...",
            parse_mode="HTML"
        )
        # Schedule a timeout reminder if admin does not respond within 5 min
        async def receipt_timeout(uid: int, chat_id: int):
            await asyncio.sleep(300)  # 5 minutes
            waiting = await asyncio.to_thread(database.is_waiting_receipt, uid)
            if waiting:
                try:
                    await bot.send_message(chat_id, f"⚠️ {username}, karta to'lovingiz hali admin tomonidan tasdiqlanmagan. Iltimos admin bilan bog'laning.")
                except Exception as ex:
                    logging.error(f"Failed to send receipt timeout message to user {uid}: {ex}")
        asyncio.create_task(receipt_timeout(user_id, message.chat.id))
    except Exception as e:
        logging.error(f"Adminga chek yuborishda xatolik: {e}")
        await message.answer("⚠️ Texnik xatolik. Iltimos, to'g'ridan-to'g'ri adminga yozing.")

@dp.message(F.photo)
async def handle_image(message: types.Message, state: FSMContext):
    """Tibbiy rasmni Gemini multimodal modellari orqali tahlil qilish."""
    user_id = message.from_user.id

    if not gemini_client:
        await message.answer(
            "⚠️ Rasmlarni tahlil qilish uchun AI sozlanmagan.\n"
            "Iltimos, matnli savol yuboring.",
            reply_markup=get_start_keyboard()
        )
        return

    consumed_free = False
    consumed_daily = False
    try:
        if await asyncio.to_thread(database.try_consume_free_ai, user_id):
            consumed_free = True
        elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
            consumed_daily = True
        else:
            await premium_upsell(message)
            return
    except Exception:
        logging.exception("Rasm: limitni band qilishda DB xatosi (user=%s)", user_id)
        try:
            await message.answer("⚠️ Vaqtinchalik texnik xatolik. Iltimos, birozdan so'ng qayta urinib ko'ring.")
        except Exception:
            logging.warning("DB xatosi haqida foydalanuvchiga xabar yuborib bo'lmadi", exc_info=True)
        return

    async def refund_once():
        # Faqat sarflangan limitni va faqat bir marta qaytaramiz
        nonlocal consumed_free, consumed_daily
        if consumed_free:
            consumed_free = False
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            consumed_daily = False
            await asyncio.to_thread(database.refund_daily_request, user_id)

    status_msg = None
    try:
        status_msg = await message.answer("🔍 <b>Rasm tahlil qilinmoqda...</b>", parse_mode="HTML")

        # Eng yuqori sifatli rasmni yuklab olamiz
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        photo_data = file_bytes.read()

        user_caption = message.caption or "Ushbu rasmdagi tibbiy holat bo'yicha tushuntirish va birinchi yordam choralarini bering."

        profile = await asyncio.to_thread(database.get_medical_profile, user_id)
        profile_context = _build_profile_context(profile)

        # google-genai SDK: rasm baytlari Part.from_bytes() orqali uzatiladi
        prompt_parts = [
            genai_types.Part.from_bytes(data=photo_data, mime_type="image/jpeg"),
            (
                "Rasmda tasvirlangan tibbiy holat, jarohat, toshma yoki boshqa tibbiyot/salomatlik bilan "
                "bog'liq vaziyatni tahlil qiling. Quyidagi savol yoki topshiriq asosida javob bering:\n"
                f"\"{user_caption}\"\n\n"
                "Siz Birinchi Yordam AI botsiz. Javob o'zbek tilida, professional, samimiy va tushunarli bo'lsin. "
                "Kasalni davolashga urinmang, birinchi yordam choralarini ko'rsating va zarur bo'lsa "
                "tez yordam (103) yoki shifokorga murojaat qilishni qat'iy eslating.\n"
                + profile_context
            )
        ]

        ai_text = None
        last_err = None
        async with KeepTyping(message.bot, message.chat.id, action="typing"):
            for model in GEMINI_MULTIMODAL_MODELS:
                try:
                    response = await gemini_client.aio.models.generate_content(
                        model=model,
                        contents=prompt_parts,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=GEMINI_SYSTEM_INSTRUCTION,
                            temperature=0.7,
                        )
                    )
                    if response and response.text:
                        ai_text = response.text
                        break

                except Exception as e:
                    err = str(e)
                    logging.warning(f"Rasm: {model} xato: {err[:150]}")
                    last_err = err
                    if _is_temporary_gemini_error(e) or "404" in err or "NOT_FOUND" in err:
                        logging.warning(f"Rasm tahlilida {model} ishlamadi, keyingisiga o'tish...")
                        continue
                    break

        if ai_text:
            delivery = await _deliver_ai_response(
                message, status_msg, ai_text,
                "📸 <b>Rasm tahlili natijasi:</b>\n\n",
                "📸 Rasm tahlili natijasi:\n\n",
            )
            if delivery == "failed":
                # Hech narsa yetkazilmadi: limit bir marta qaytariladi va foydalanuvchiga xabar beriladi
                try:
                    await refund_once()
                except Exception as refund_err:
                    logging.exception("Refund failed after Telegram delivery failure: %s", refund_err)
                err_text = (
                    "⚠️ Rasmni tahlil qilish imkoni bo'lmadi.\n"
                    "Iltimos, muammoni matn shaklida yozib yuboring. 📝"
                )
                try:
                    await status_msg.edit_text(err_text, parse_mode="HTML")
                except Exception as ex2:
                    logging.error(f"Failed to send fallback response: {ex2}")
                    try:
                        await message.answer(err_text, parse_mode="HTML")
                    except Exception as ex3:
                        logging.error(f"Failed to send fallback via answer: {ex3}")
            return

        logging.error(f"Rasm: barcha modellar ishlamadi. Oxirgi xato: {last_err}")
        try:
            await refund_once()
        except Exception as refund_err:
            logging.exception("Refund failed during error handling: %s", refund_err)
        await status_msg.edit_text(
            "⚠️ Rasmni tahlil qilish imkoni bo'lmadi.\n"
            "qayta ishlashda xatolik.",
            parse_mode="HTML"
        )

    except Exception as e:
        logging.error(f"Rasm tahlili handlerida xatolik: {e}")
        try:
            await refund_once()
        except Exception as refund_err:
            logging.exception("Refund failed during outer exception handling: %s", refund_err)
        error_text = (
            "⚠️ Rasmni qayta ishlashda xatolik yuz berdi.\n"
            "Iltimos, matnli savol yuboring."
        )
        try:
            if status_msg:
                await status_msg.edit_text(error_text, parse_mode="HTML")
            else:
                await message.answer(error_text, parse_mode="HTML")
        except Exception as ex:
            logging.error(f"Rasm xato xabarini yuborib bo'lmadi: {ex}")

@dp.callback_query(F.data.startswith("adm_app_"))
async def process_admin_approve(callback: types.CallbackQuery):
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("Siz admin emassiz!", show_alert=True)
        return
    # Parse user_id and token from callback data
    parts = callback.data.split('_')
    if len(parts) < 4:
        await callback.answer("Noto'g'ri callback format.", show_alert=True)
        return
    user_id = int(parts[2])
    token = parts[3]
    # Attempt atomic approval
    success = await asyncio.to_thread(database.approve_receipt_and_grant, user_id, token)
    if not success:
        # Either receipt already processed, mismatch, or DB error
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>Receipt allaqachon tasdiqlangan yoki noto'g'ri.</b>",
            reply_markup=None,
            parse_mode="HTML"
        )
        await callback.answer("⚠️ Premium berilmadi.", show_alert=True)
        return
    # Approval succeeded – update admin message and inform user
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ <b>Tasdiqlandi! Premium berildi.</b>",
        reply_markup=None,
        parse_mode="HTML"
    )
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 <b>Tabriklaymiz!</b>\n\n"
                "Administrator sizga <b>1 oy Premium</b> taqdim etdi.\n"
                "Endi AI yordamchisidan mutlaqo cheksiz foydalanishingiz mumkin. 🚀"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Foydalanuvchiga Premium xabari yuborib bo'lmadi: {e}")
    await callback.answer("Premium berildi!")

@dp.callback_query(F.data.startswith("adm_rej_"))
async def process_admin_reject(callback: types.CallbackQuery):
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("Siz admin emassiz!", show_alert=True)
        return
    # Parse user_id and token from callback data
    parts = callback.data.split('_')
    if len(parts) < 4:
        await callback.answer("Noto'g'ri callback format.", show_alert=True)
        return
    user_id = int(parts[2])
    token = parts[3]
    # Attempt atomic reject
    success = await asyncio.to_thread(database.reject_receipt, user_id, token)
    if not success:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>Receipt allaqachon ishlangan yoki noto'g'ri.</b>",
            reply_markup=None,
            parse_mode="HTML"
        )
        await callback.answer("⚠️ Rad etish muvaffaqiyatsiz.", show_alert=True)
        return
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>To'lov rad etildi.</b>",
        reply_markup=None,
        parse_mode="HTML"
    )
    await callback.answer("Receipt rad etildi.")

# ═══════════════════════════════════════════════════════════════════
# FEATURE 7: 🔔 KUNLIK SOG'LIQ MASLAHATLARI
# ═══════════════════════════════════════════════════════════════════

@dp.message(F.text == "🔔 Kunlik Maslahatlar")
async def daily_tips_menu(message: types.Message):
    user_id = message.from_user.id
    status = await asyncio.to_thread(database.get_daily_tips_status, user_id)
    builder = InlineKeyboardBuilder()
    if status == 1:
        builder.button(text="🔕 Obunani bekor qilish", callback_data="tips_unsubscribe")
        text = (
            "🔔 <b>Kunlik Sog'liq Maslahatlari</b>\n\n"
            "✅ Siz obuna bo'lgansiz!\n\n"
            "Har kuni ertalab soat <b>08:00</b> da sog'lik bo'yicha yangi maslahat olasiz. 🌅"
        )
    else:
        builder.button(text="🔔 Obuna bo'lish (bepul)", callback_data="tips_subscribe")
        text = (
            "🔔 <b>Kunlik Sog'liq Maslahatlari</b>\n\n"
            "Har kuni ertalab <b>08:00</b> da:\n"
            "• 🍎 Foydali ovqatlanish maslahatlari\n"
            "• 🏃 Kun uchun jismoniy mashqlar\n"
            "• 💊 Vitaminlar va sog'liq sirlari\n"
            "• 🧘 Stress va ruhiy salomatlik\n\n"
            "Obuna <b>mutlaqo bepul!</b>"
        )
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "tips_subscribe")
async def tips_subscribe(callback: types.CallbackQuery):
    await asyncio.to_thread(database.set_daily_tips_subscription, callback.from_user.id, 1)
    await callback.message.edit_text(
        "✅ <b>Obuna bo'ldingiz!</b>\n\n"
        "Har kuni soat 08:00 da sog'liq bo'yicha yangi maslahat olasiz. 🌅\n\n"
        "Birinchi maslahat ertaga keladi!",
        parse_mode="HTML"
    )
    await callback.answer("✅ Obuna faollashtirildi!")

@dp.callback_query(F.data == "tips_unsubscribe")
async def tips_unsubscribe(callback: types.CallbackQuery):
    await asyncio.to_thread(database.set_daily_tips_subscription, callback.from_user.id, 0)
    await callback.message.edit_text(
        "🔕 <b>Obuna bekor qilindi.</b>\n\n"
        "Istalgan vaqt qaytadan obuna bo'lishingiz mumkin.",
        parse_mode="HTML"
    )
    await callback.answer("Obuna bekor qilindi!")

async def send_daily_tips():
    """Har kuni ertalab 08:00 da barcha obunachilarga maslahat yuborish"""
    topics = [
        "bugungi kun uchun sabzavot va mevalar haqida eng foydali dietologik maslahat",
        "ertalabki jismoniy mashqlar va ularning foydasi haqida qisqa maslahat",
        "vitaminlar va minerallar: qaysi birlarini qabul qilish kerak va nima uchun",
        "stress va ruhiy salomatlikni yaxshilash uchun 3 ta amaliy tavsiya",
        "uyqu sifatini yaxshilash va salomatlikka ta'siri haqida maslahat",
        "suv ichish odati va organizmga foydasi haqida qiziqarli ma'lumot",
        "immunitetni mustahkamlash uchun tabiiy yo'llar va ovqatlar",
    ]

    import random
    topic = random.choice(topics)
    prompt = (
        f"O'zbek tilida qisqa, iliq va motivatsion sog'liq maslahati yoz ({topic} haqida). "
        f"Matn 200-300 so'zdan oshmaydi. Emoji bilan bezat. "
        f"Boshida 🌅 Bugungi Sog'liq Maslahati sarlavhasini yoz."
    )

    tip_text = await get_gemini_response(prompt)
    if tip_text is None:
        logging.error("AI error received, skipping daily tips broadcast.")
        return
    subscribers = await asyncio.to_thread(database.get_daily_tips_subscribers)

    logging.info(f"Kunlik maslahat {len(subscribers)} ta obunachiga yuborilmoqda...")
    sent, failed = 0, 0
    for user_id in subscribers:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=markdown_to_html(tip_text),
                parse_mode="HTML"
            )
            sent += 1
            await asyncio.sleep(0.05)  # Flood limit oldini olish
        except Exception as e:
            logging.warning(f"Foydalanuvchi {user_id} ga maslahat yuborib bo'lmadi: {e}")
            failed += 1
    logging.info(f"Kunlik maslahat: {sent} muvaffaqiyatli, {failed} muvaffaqiyatsiz.")

# ═══════════════════════════════════════════════════════════════════
# FEATURE 2: DORI ESLATMASI SCHEDULER
# ═══════════════════════════════════════════════════════════════════

async def _send_due_reminders(now_dt):
    now_time = now_dt.strftime("%H:%M")
    day_of_year = now_dt.timetuple().tm_yday
    reminders = await asyncio.to_thread(database.get_all_active_reminders)
    for rem_id, user_id, medicine_name, times_str, days in reminders:
        if days == "every_other" and day_of_year % 2 == 0:
            continue
        times_list = [t.strip() for t in times_str.split(",")]
        if now_time in times_list:
            logging.info(f"[SCHEDULER] Reminder matched: user_id={user_id} time={now_time}")
            try:
                sent_ts = int(now_dt.timestamp())
                builder = InlineKeyboardBuilder()
                builder.button(text="✅ Ichdim", callback_data=f"med_taken_{rem_id}_{sent_ts}")
                builder.button(text="❌ Ichmadim", callback_data=f"med_missed_{rem_id}_{sent_ts}")
                builder.adjust(2)
                
                safe_med_name = html.escape(medicine_name)
                
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"💊 <b>Dori ichish vaqti!</b>\n\n"
                        f"🕐 Vaqt: <b>{now_time}</b>\n"
                        f"💊 Dori: <b>{safe_med_name}</b>\n\n"
                        f"Dorini ichdingizmi? 👇"
                    ),
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
                await asyncio.sleep(0.05)
                logging.info(f"[SCHEDULER] Reminder sent successfully: user_id={user_id}")
            except Exception as e:
                logging.warning(f"[SCHEDULER] Reminder send failed: user_id={user_id} error={e}")

async def check_and_send_reminders():
    """Har daqiqa ishlab, dori vaqti kelganini tekshiradi"""
    logging.info("[SCHEDULER] check_and_send_reminders started")
    from datetime import timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    last = datetime.now(uz_tz).replace(second=0, microsecond=0) - timedelta(minutes=1)
    while True:
        try:
            now = datetime.now(uz_tz).replace(second=0, microsecond=0)
            while last < now:  # o'tib ketgan daqiqalarni ham qamraydi
                last += timedelta(minutes=1)
                try:
                    await _send_due_reminders(last)
                except Exception as e:
                    logging.exception(f"[SCHEDULER] ERROR in check_and_send_reminders (inner): {e}")
            await asyncio.sleep(60 - datetime.now(uz_tz).second + 0.5)
        except Exception as e:
            logging.exception(f"[SCHEDULER] ERROR in check_and_send_reminders (outer loop): {e}")
            await asyncio.sleep(60)
    logging.info("[SCHEDULER] check_and_send_reminders stopped")


@dp.callback_query(F.data.startswith("med_taken_"))
async def medicine_taken_handler(callback: types.CallbackQuery):
    """Foydalanuvchi dorini ichganini tasdiqladi"""
    await callback.message.edit_text(
        f"✅ <b>Dorini ichganingiz tasdiqlandi!</b>\n\n"
        f"Sog'lig'ingizga e'tiborli bo'lganingiz uchun rahmat! Dorilarni o'z vaqtida ichish juda muhim. 🌸",
        parse_mode="HTML"
    )
    await callback.answer("Tasdiqlandi!")


@dp.callback_query(F.data.startswith("med_missed_"))
async def medicine_missed_handler(callback: types.CallbackQuery):
    """Foydalanuvchi dorini ichmaganini bildirdi"""
    await callback.message.edit_text(
        f"⚠️ <b>Dorini ichishni unutmang!</b>\n\n"
        f"Sog'lig'ingiz uchun dorilarni o'z vaqtida ichish juda muhim. Keyingi safar e'tiborliroq bo'ling! 🩺",
        parse_mode="HTML"
    )
    await callback.answer("Keyingi safar ichishni unutmang!")



@dp.message(F.web_app_data)
async def web_app_data_handler(message: types.Message):
    """Mini App'dan kelgan ma'lumotlarni qayta ishlash"""
    consumed_free = False
    consumed_daily = False
    user_id = message.from_user.id if message.from_user else None

    async def refund_once():
        nonlocal consumed_free, consumed_daily
        if not user_id:
            return
        if consumed_free:
            consumed_free = False
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            consumed_daily = False
            await asyncio.to_thread(database.refund_daily_request, user_id)

    try:
        data = json.loads(message.web_app_data.data)
        if data.get("action") == "ai_consult":
            user_id = message.from_user.id
            
            if await asyncio.to_thread(database.try_consume_free_ai, user_id):
                consumed_free = True
            elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
                consumed_daily = True
            else:
                await premium_upsell(message)
                return
                
            raw_title = str(data.get("title", "noma'lum a'zo"))
            safe_title = html.escape(raw_title[:100])
            
            placeholder = await message.answer(
                f"🤖 <b>AI Konsultatsiya ({safe_title}):</b>\n\n"
                f"Tahlil qilinmoqda, iltimos kuting... ⏳",
                parse_mode="HTML"
            )
            
            prompt = (
                f"Foydalanuvchi inson tanasidagi '{safe_title}' sohasida og'riq yoki bezovtalik borligini bildirdi. "
                f"Ushbu tana a'zosi bo'yicha eng ko'p uchraydigan kasalliklar, ularning kelib chiqish sabablari va "
                f"uy sharoitida birinchi yordam hamda shifokorga qachon murojaat qilish kerakligi haqida atroflicha, "
                f"chiroyli va tushunarli o'zbek tilida maslahat ber."
            )
            
            result = await stream_gemini_to_message(prompt=prompt, message=placeholder)
            if result is None:
                await refund_once()

    except Exception as e:
        logging.error(f"web_app_data xatolik: {e}")
        await refund_once()
        await message.answer("⚠️ Ma'lumotlarni qayta ishlashda xatolik yuz berdi.")

# ═══════════════════════════════════════════════════════════════════
# KUNLIK TAVSIYA SCHEDULER (har kuni 08:00 da)
# ═══════════════════════════════════════════════════════════════════

async def daily_tips_scheduler():
    """Har kuni 08:00 da kunlik maslahatlarni yuboradi"""
    logging.info("[SCHEDULER] daily_tips_scheduler started")
    from datetime import timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    while True:
        try:
            now = datetime.now(uz_tz)
            # Keyingi 08:00 ni hisoblash
            target = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logging.info(f"[SCHEDULER] Keyingi kunlik maslahat {wait_seconds/3600:.1f} soatdan keyin yuboriladi.")
            await asyncio.sleep(wait_seconds)
            logging.info(f"[SCHEDULER] daily_tips_scheduler job triggered at {datetime.now(uz_tz)}")
            await send_daily_tips()
        except Exception as e:
            logging.exception(f"[SCHEDULER] ERROR in daily_tips_scheduler: {e}")
            await asyncio.sleep(3600)
    logging.info("[SCHEDULER] daily_tips_scheduler stopped")

# ═══════════════════════════════════════════════════════════════════
# ADMIN BUYRUQLARI
# ═══════════════════════════════════════════════════════════════════

@dp.message(Command("test_scheduler"))
async def cmd_test_scheduler(message: types.Message):
    """Admin uchun scheduler mexanizmlarini test qilish"""
    if str(message.from_user.id) != str(ADMIN_ID):
        return await message.answer("Buning uchun huquqingiz yo'q.")
    
    await message.answer("🔄 <b>Scheduler test boshlandi...</b>", parse_mode="HTML")
    
    try:
        from datetime import timezone, timedelta
        uz_tz = timezone(timedelta(hours=5))
        now_dt = datetime.now(uz_tz).replace(second=0, microsecond=0)
        
        logging.info("[SCHEDULER TEST] Reminder test boshlandi")
        await _send_due_reminders(now_dt)
        
        await message.answer("✅ <b>Test yakunlandi:</b> `_send_due_reminders` joriy vaqt uchun ishlab chiqildi.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ <b>Test xatosi:</b> {e}", parse_mode="HTML")
        logging.exception(f"[SCHEDULER TEST] ERROR: {e}")

def _build_premium_list_keyboard(users_info):
    """Premium boshqaruv uchun keyboard quradi"""
    builder = InlineKeyboardBuilder()
    for row in users_info:
        user_id, is_premium = row[0], row[1]
        full_name = row[3] if len(row) > 3 else None
        username = row[4] if len(row) > 4 else None
        display = full_name or f"ID:{user_id}"
        status_icon = "🌟" if is_premium else "👤"
        action = "❌ Olib tashlash" if is_premium else "🌟 Premium berish"
        builder.button(
            text=f"{status_icon} {display} — {action}",
            callback_data=f"pm_toggle_{user_id}"
        )
    builder.button(text="🔄 Yangilash", callback_data="pm_refresh")
    builder.adjust(1)
    return builder.as_markup()


def _build_premium_list_text(users_info, total, premium_count):
    """Premium ro'yxat matni"""
    text = (
        f"💎 <b>Premium Boshqaruvi</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"🌟 Premium foydalanuvchilar: <b>{premium_count}</b>\n\n"
        f"<b>So'nggi {len(users_info)} ta foydalanuvchi:</b>\n"
        "─────────────────\n"
    )
    for row in users_info:
        user_id, is_premium = row[0], row[1]
        full_name = row[3] if len(row) > 3 else None
        username = row[4] if len(row) > 4 else None
        icon = "🌟" if is_premium else "👤"
        name_str = html.escape(full_name or "Noma'lum")
        uname_str = f" (@{html.escape(username)})" if username else ""
        prem_str = "Premium" if is_premium else "Oddiy"
        text += f"{icon} <b>{name_str}</b>{uname_str}\n"
        text += f"   🆔 <code>{user_id}</code>  |  {prem_str}\n\n"
    text += "Tugma bosib premium berishingiz yoki olib tashlashingiz mumkin 👇"
    return text


async def _resolve_users_info(users_info):
    """Foydalanuvchilar ismlari va usernamelarini Telegram'dan yuklab yangilaydi (agar yo'q bo'lsa)"""
    resolved = []
    for row in users_info:
        user_id, is_premium, reg_at = row[0], row[1], row[2]
        full_name = row[3] if len(row) > 3 else None
        username = row[4] if len(row) > 4 else None
        
        if not full_name:
            try:
                chat = await bot.get_chat(user_id)
                full_name = f"{chat.first_name or ''} {chat.last_name or ''}".strip() or f"User {user_id}"
                username = chat.username
                await asyncio.to_thread(database.register_user, user_id, full_name=full_name, username=username)
            except Exception:
                full_name = f"User {user_id}"
                
        resolved.append((user_id, is_premium, reg_at, full_name, username))
    return resolved


@dp.message(Command("premium"))
async def cmd_premium(message: types.Message):
    """Admin uchun interaktiv Premium boshqaruvi"""
    if str(message.from_user.id) != str(ADMIN_ID):
        # Oddiy foydalanuvchilar uchun Premium sahifasini ko'rsatish
        return await _show_premium_page(message)
    raw_users = await asyncio.to_thread(database.get_all_users_info, limit=15)
    users_info = await _resolve_users_info(raw_users)
    total = await asyncio.to_thread(database.get_users_count)
    premium_count = await asyncio.to_thread(database.get_premium_count)
    text = _build_premium_list_text(users_info, total, premium_count)
    markup = _build_premium_list_keyboard(users_info)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@dp.callback_query(F.data == "pm_refresh")
async def cb_pm_refresh(callback: types.CallbackQuery):
    """Premium ro'yxatini yangilash"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    raw_users = await asyncio.to_thread(database.get_all_users_info, limit=15)
    users_info = await _resolve_users_info(raw_users)
    total = await asyncio.to_thread(database.get_users_count)
    premium_count = await asyncio.to_thread(database.get_premium_count)
    text = _build_premium_list_text(users_info, total, premium_count)
    markup = _build_premium_list_keyboard(users_info)
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("🔄 Yangilandi!")


@dp.callback_query(F.data.startswith("pm_toggle_"))
async def cb_pm_toggle(callback: types.CallbackQuery):
    """Foydalanuvchining premium holatini o'zgartirish"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    try:
        target_id = int(callback.data.replace("pm_toggle_", ""))
        # Hozirgi holatni aniq bilish
        raw_all = await asyncio.to_thread(database.get_all_users_info, limit=100)
        current_status = 0
        for row in raw_all:
            uid = row[0]
            is_prem = row[1]
            if uid == target_id:
                current_status = is_prem
                break
        new_status = 0 if current_status else 1
        await asyncio.to_thread(database.set_premium, target_id, new_status)
        action_text = "🌟 Premium berildi!" if new_status else "❌ Premium olib tashlandi!"
        await callback.answer(f"{action_text} (ID: {target_id})", show_alert=True)
        # Ro'yxatni yangilash
        raw_users = await asyncio.to_thread(database.get_all_users_info, limit=15)
        users_info = await _resolve_users_info(raw_users)
        total = await asyncio.to_thread(database.get_users_count)
        premium_count = await asyncio.to_thread(database.get_premium_count)
        text = _build_premium_list_text(users_info, total, premium_count)
        markup = _build_premium_list_keyboard(users_info)
        try:
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
    except Exception as e:
        await callback.answer(f"Xatolik: {e}", show_alert=True)


def _build_ban_list_keyboard(users_info):
    """Ban boshqaruv uchun keyboard quradi"""
    builder = InlineKeyboardBuilder()
    for row in users_info:
        user_id, is_banned = row[0], row[1]
        full_name = row[3] if len(row) > 3 else None
        display = full_name or f"ID:{user_id}"
        status_icon = "🚫" if is_banned else "👤"
        action = "✅ Unban" if is_banned else "🚫 Ban qilish"
        builder.button(
            text=f"{status_icon} {display} — {action}",
            callback_data=f"ban_toggle_{user_id}"
        )
    builder.button(text="🔄 Yangilash", callback_data="ban_refresh")
    builder.adjust(1)
    return builder.as_markup()


def _build_ban_list_text(users_info, total, banned_count):
    """Ban ro'yxat matni"""
    text = (
        f"🚫 <b>Ban Boshqaruvi</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"🚫 Bloklanganlar: <b>{banned_count}</b>\n\n"
        f"<b>So'nggi {len(users_info)} ta foydalanuvchi:</b>\n"
        "─────────────────\n"
    )
    for row in users_info:
        user_id, is_banned = row[0], row[1]
        full_name = row[3] if len(row) > 3 else None
        username = row[4] if len(row) > 4 else None
        icon = "🚫" if is_banned else "👤"
        name_str = html.escape(full_name or "Noma'lum")
        uname_str = f" (@{html.escape(username)})" if username else ""
        ban_str = "Bloklangan" if is_banned else "Faol"
        text += f"{icon} <b>{name_str}</b>{uname_str}\n"
        text += f"   🆔 <code>{user_id}</code>  |  {ban_str}\n\n"
    text += "Tugma bosib foydalanuvchini ban qilishingiz yoki bandan chiqarishingiz mumkin 👇"
    return text


@dp.callback_query(F.data == "ban_refresh")
async def cb_ban_refresh(callback: types.CallbackQuery):
    """Ban ro'yxatini yangilash"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    raw_users = await asyncio.to_thread(database.get_all_users_info_ban, limit=15)
    users_info = await _resolve_users_info(raw_users)
    total = await asyncio.to_thread(database.get_users_count)
    banned_count = await asyncio.to_thread(database.get_banned_count)
    text = _build_ban_list_text(users_info, total, banned_count)
    markup = _build_ban_list_keyboard(users_info)
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("🔄 Yangilandi!")


@dp.callback_query(F.data.startswith("ban_toggle_"))
async def cb_ban_toggle(callback: types.CallbackQuery):
    """Foydalanuvchini ban qilish yoki bandan chiqarish"""
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    try:
        target_id = int(callback.data.replace("ban_toggle_", ""))
        if str(target_id) == str(ADMIN_ID):
            await callback.answer("❌ O'zingizni ban qila olmaysiz!", show_alert=True)
            return
            
        # Get current status
        raw_all = await asyncio.to_thread(database.get_all_users_info_ban, limit=100)
        current_status = 0
        for row in raw_all:
            uid = row[0]
            is_banned = row[1]
            if uid == target_id:
                current_status = is_banned
                break
                
        if current_status:
            await asyncio.to_thread(database.unban_user, target_id)
            action_text = "✅ Bandan chiqarildi!"
        else:
            await asyncio.to_thread(database.ban_user, target_id)
            action_text = "🚫 Doimiy ban qilindi!"
            
        await callback.answer(f"{action_text} (ID: {target_id})", show_alert=True)
        
        # Refresh ro'yxat
        raw_users = await asyncio.to_thread(database.get_all_users_info_ban, limit=15)
        users_info = await _resolve_users_info(raw_users)
        total = await asyncio.to_thread(database.get_users_count)
        banned_count = await asyncio.to_thread(database.get_banned_count)
        text = _build_ban_list_text(users_info, total, banned_count)
        markup = _build_ban_list_keyboard(users_info)
        try:
            await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
    except Exception as e:
        await callback.answer(f"Xatolik: {e}", show_alert=True)


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Admin uchun statistika: /stats"""
    if str(message.from_user.id) != str(ADMIN_ID):
        return await message.answer("❌ Sizda bu buyruqdan foydalanish huquqi yo'q.")
    total = await asyncio.to_thread(database.get_users_count)
    premium = await asyncio.to_thread(database.get_premium_count)
    subscribers = len(await asyncio.to_thread(database.get_daily_tips_subscribers))
    reminders_count = len(await asyncio.to_thread(database.get_all_active_reminders))
    await message.answer(
        f"📊 <b>Bot Statistikasi</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"💎 Premium foydalanuvchilar: <b>{premium}</b>\n"
        f"🔔 Kunlik maslahat obunachilari: <b>{subscribers}</b>\n"
        f"💊 Faol dori eslatmalari: <b>{reminders_count}</b>",
        parse_mode="HTML"
    )


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    """Barcha foydalanuvchilarga xabar yuborish (Yangi FSM usuli)"""
    if str(message.from_user.id) != str(ADMIN_ID):
        return await message.answer("❌ Sizda bu buyruqdan foydalanish huquqi yo'q.")
    
    reply = message.reply_to_message
    
    if reply:
        # Method 2: Reply qilingan xabarni tarqatish
        await state.set_state(BroadcastStates.waiting_for_confirmation)
        await state.update_data(broadcast_msg_id=reply.message_id)
        users_count = await asyncio.to_thread(database.get_users_count)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Yuborish", callback_data="broadcast_confirm")
        kb.button(text="❌ Bekor qilish", callback_data="broadcast_cancel")
        kb.adjust(2)
        
        await message.answer(
            f"📢 <b>Xabar tayyor.</b>\n\n👥 Qabul qiluvchilar: {users_count} ta\n\nYuborishni tasdiqlaysizmi?",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        # Method 3: Tezkor matnli xabar
        await state.set_state(BroadcastStates.waiting_for_confirmation)
        await state.update_data(broadcast_text=parts[1])
        users_count = await asyncio.to_thread(database.get_users_count)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Yuborish", callback_data="broadcast_confirm")
        kb.button(text="❌ Bekor qilish", callback_data="broadcast_cancel")
        kb.adjust(2)
        
        await message.answer(
            f"📢 <b>Xabar tayyor.</b>\n\n📝 Turi: Matn\n👥 Qabul qiluvchilar: {users_count} ta\n\nYuborishni tasdiqlaysizmi?",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        return

    # Method 1: Kontent kutish
    await state.set_state(BroadcastStates.waiting_for_content)
    await message.answer(
        "📢 <b>Broadcast</b>\n\n"
        "Xabarni yuboring.\n"
        "Matn, rasm, video, ovozli xabar yoki fayl yuborishingiz mumkin.\n\n"
        "❌ Bekor qilish: /cancel",
        parse_mode="HTML"
    )

@dp.message(StateFilter(BroadcastStates.waiting_for_content))
async def process_broadcast_content(message: types.Message, state: FSMContext):
    """Admin yuborgan kontentni qabul qilib, tasdiqlashni so'raydi."""
    if str(message.from_user.id) != str(ADMIN_ID):
        return
        
    await state.set_state(BroadcastStates.waiting_for_confirmation)
    await state.update_data(broadcast_msg_id=message.message_id)
    
    users_count = await asyncio.to_thread(database.get_users_count)
    
    # Aniqlash (faqat ko'rsatish uchun)
    msg_type = "Matn"
    if message.photo: msg_type = "Rasm"
    elif message.video: msg_type = "Video"
    elif message.audio: msg_type = "Audio"
    elif message.voice: msg_type = "Ovozli xabar"
    elif message.document: msg_type = "Fayl"
    elif message.animation: msg_type = "GIF/Animatsiya"
    elif message.sticker: msg_type = "Stiker"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Yuborish", callback_data="broadcast_confirm")
    kb.button(text="❌ Bekor qilish", callback_data="broadcast_cancel")
    kb.adjust(2)
    
    await message.answer(
        f"📢 <b>Broadcast tayyor</b>\n\n"
        f"📝 Turi: {msg_type}\n"
        f"👥 Qabul qiluvchilar: {users_count} ta\n\n"
        f"Yuborishni tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data.in_(["broadcast_confirm", "broadcast_cancel"]), StateFilter(BroadcastStates.waiting_for_confirmation))
async def process_broadcast_confirmation(callback: types.CallbackQuery, state: FSMContext):
    """Tasdiqlash yoki bekor qilishni qayta ishlaydi."""
    if str(callback.from_user.id) != str(ADMIN_ID):
        return await callback.answer("Ruxsat yo'q", show_alert=True)
        
    if callback.data == "broadcast_cancel":
        await state.clear()
        await callback.message.edit_text("❌ Broadcast bekor qilindi.")
        return

    # Tasdiqlandi
    data = await state.get_data()
    msg_id = data.get("broadcast_msg_id")
    text_content = data.get("broadcast_text")
    
    await state.clear()  # Adminga boshqa ishlarni qilishga ruxsat beramiz
    
    users = await asyncio.to_thread(database.get_all_users)
    total = len(users)
    
    progress_msg = await callback.message.edit_text(f"📤 Xabar yuborilmoqda...\n\n👥 Jami: {total}")
    
    sent, failed = 0, 0
    
    for i, user_id in enumerate(users):
        try:
            if msg_id:
                # Xabarni barcha formatlari bilan to'liq nusxalab yuboramiz
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=callback.message.chat.id,
                    message_id=msg_id
                )
            elif text_content:
                # HTML parse xatolaridan himoya qilamiz
                try:
                    await bot.send_message(chat_id=user_id, text=text_content, parse_mode="HTML")
                except Exception:
                    await bot.send_message(chat_id=user_id, text=text_content, parse_mode=None)
            sent += 1
        except Exception:
            failed += 1
            
        await asyncio.sleep(0.05) # Rate limitdan saqlanish
        
        # Har 100 ta xabarda progressni yangilash (Telegram API ni zo'riqtirmaslik uchun)
        if (i + 1) % 100 == 0:
            try:
                await progress_msg.edit_text(
                    f"📤 Xabar yuborilmoqda...\n\n"
                    f"✅ Yuborildi: {sent}\n"
                    f"❌ Xato: {failed}\n"
                    f"👥 Jami: {total}"
                )
            except Exception:
                pass # EditMessage too often xatosini o'tkazib yuborish
                
    # Yakuniy hisobot
    await progress_msg.edit_text(
        f"📢 <b>Broadcast tugadi!</b>\n\n"
        f"👥 Jami: {total}\n"
        f"✅ Muvaffaqiyatli: {sent}\n"
        f"❌ Xatolik (Bloklaganlar/O'chirilganlar): {failed}",
        parse_mode="HTML"
    )

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    """Adminga foydalanuvchini ban qilish: /ban yoki /ban <user_id> [minutes]"""
    if str(message.from_user.id) != str(ADMIN_ID):
        return await message.answer("❌ Sizda bu buyruqdan foydalanish huquqi yo'q.")
    parts = message.text.split()
    if len(parts) < 2:
        # Interactive Mode
        raw_users = await asyncio.to_thread(database.get_all_users_info_ban, limit=15)
        users_info = await _resolve_users_info(raw_users)
        total = await asyncio.to_thread(database.get_users_count)
        banned_count = await asyncio.to_thread(database.get_banned_count)
        text = _build_ban_list_text(users_info, total, banned_count)
        markup = _build_ban_list_keyboard(users_info)
        await message.answer(text, reply_markup=markup, parse_mode="HTML")
        return
        
    try:
        user_id = int(parts[1])
        minutes = int(parts[2]) if len(parts) >= 3 else None
        
        if str(user_id) == str(ADMIN_ID):
            await message.answer("❌ O'zingizni ban qila olmaysiz!")
            return
            
        await asyncio.to_thread(database.ban_user, user_id, minutes)
        if minutes:
            await message.answer(f"✅ Foydalanuvchi {user_id} {minutes} daqiqaga vaqtinchalik ban qilindi.")
        else:
            await message.answer(f"✅ Foydalanuvchi {user_id} doimiy ban qilindi.")
    except ValueError:
        await message.answer("❌ Xatolik: user_id va daqiqalar soni butun son bo'lishi kerak!")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    """Adminga foydalanuvchini bandan chiqarish: /unban <user_id>"""
    if str(message.from_user.id) != str(ADMIN_ID):
        return await message.answer("❌ Sizda bu buyruqdan foydalanish huquqi yo'q.")
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "Foydalanish: /unban <code>&lt;user_id&gt;</code>\n\n"
            "Masalan: <code>/unban 12345678</code>",
            parse_mode="HTML"
        )
        return
    try:
        user_id = int(parts[1])
        await asyncio.to_thread(database.unban_user, user_id)
        await message.answer(f"✅ Foydalanuvchi {user_id} bandan chiqarildi.")
    except ValueError:
        await message.answer("❌ Xatolik: user_id butun son bo'lishi kerak!")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

# ═══════════════════════════════════════════════════════════════════
# AI CHAT (matnli savol)
# ═══════════════════════════════════════════════════════════════════

@dp.message(AiChatStates.chatting, F.text)
async def handle_ai_chat(message: types.Message, state: FSMContext):
    """Foydalanuvchining matnli savollariga avval DATABASE, keyin AI orqali javob"""
    
    # Reply tugmalarni tekshirish (ehtiyot chorasi sifatida qoldiramiz)
    skip_texts = [
        "📋 Holatlar ro'yxati", "🚨 Favqulodda raqamlar",
        "📚 Kasalliklar", "💬 AI Konsultatsiya (Chat)",
        "🏥 Yaqin kasalxona", "💎 Premium",
        "👤 Tibbiy Profilim", "💊 Dori Eslatmalari",
        "⚖️ Sog'liq Kalkulyatori", "🔔 Kunlik Maslahatlar",
        "👥 Do'stlarni taklif qilish", "🌐 Mening ballarim",
        "📣 Reklama"
    ]
    if message.text in skip_texts:
        return

    user_id = message.from_user.id

    # ═══ DATABASE-FIRST: Avval lokal bazadan qidiramiz ═══
    search_result = await asyncio.to_thread(medicine_db.find_medicine, message.text)
    if search_result["found"]:
        logging.info(f"[TOKEN_SAVED] user={user_id} source={search_result['source']} query='{message.text}'")
        await message.answer(
            search_result["data"],
            parse_mode="HTML",
        )
        return  # AI CHAQIRILMADI — token tejaldi! ✅

    # ═══ DATABASE'da topilmadi — AI ga o'tamiz ═══
    if user_id in _active_ai_users:
        await message.reply("⏳ Oldingi savolingizga javob tayyorlanmoqda, iltimos kuting...")
        return
    _active_ai_users.add(user_id)
    consumed_free = False
    consumed_daily = False

    async def refund_once():
        nonlocal consumed_free, consumed_daily
        if consumed_free:
            consumed_free = False
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            consumed_daily = False
            await asyncio.to_thread(database.refund_daily_request, user_id)

    try:
        # 1 ta bepul savol tizimi yoki kunlik limit tekshiruvi
        if await asyncio.to_thread(database.try_consume_free_ai, user_id):
            consumed_free = True
        elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
            consumed_daily = True
        else:
            # Bepul limit tugagan — premium talab qilamiz
            builder = InlineKeyboardBuilder()
            builder.button(text="💎 Premium", callback_data="buy_premium")
            builder.adjust(1)
            await message.answer(
                "🔒 <b>Bepul AI savollar limiti tugadi!</b>\n\n"
                "AI bilan cheksiz suhbat qurish uchun <b>Premium</b> xarid qiling!\n\n"
                "🚀 <b>Premium afzalliklari:</b>\n"
                "• ♾️ Cheksiz AI so'rovlari\n"
                "• 🎙️ Ovozli konsultatsiya\n"
                "• 📚 Kasalliklar batafsil tahlili\n"
                "• 🩺 Shaxsiy tibbiy maslahat\n\n"
                "🎁 <b>Bepul Premium olish yo'li:</b>\n"
                "• 🔥 Har kuni botga kirib, kunlik bonus to'plang (1, 2, 3... ball)!\n"
                "• 👥 Do'stingizni taklif qiling: <b>+10 ball</b> (5 ta do'st uchun: <b>🎁 +50 ball</b>!)\n"
                "• 🎓 <b>100 ball</b> to'planganda bepul <b>Premium</b> faollashadi!\n\n"
                f"⭐ <b>{PREMIUM_STARS_PRICE} Telegram Stars</b> (7 kunlik Pro) dan boshlab.",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
            return

        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        placeholder = await message.answer("⏳ <b>Javob tayyorlanmoqda...</b>", parse_mode="HTML")

        # Tibbiy profilni qo'shish
        profile = await asyncio.to_thread(database.get_medical_profile, user_id)
        profile_context = _build_profile_context(profile)
        full_prompt = message.text + profile_context

        logging.info(f"[AI_FALLBACK] user={user_id} query='{message.text}'")
        result = await stream_gemini_to_message(
            prompt=full_prompt,
            message=placeholder,
            placeholder_text="⏳ <b>Javob tayyorlanmoqda...</b>"
        )
        if result is None:
            await refund_once()
        # DIQQAT: AI javobi keshlanmaydi — u foydalanuvchining tibbiy profiliga
        # bog'liq, umumiy keshga yozilsa boshqa foydalanuvchiga ko'rinib qoladi (P0-1).
    except Exception as e:
        logging.error(f"handle_ai_chat xatolik: {e}", exc_info=True)
        await refund_once()
        try:
            await message.answer("⚠️ AI xizmatida vaqtinchalik xatolik yuz berdi. Iltimos, birozdan so'ng qayta urinib ko'ring.")
        except Exception:
            pass
    finally:
        _active_ai_users.discard(user_id)

def _build_profile_context(profile) -> str:
    """Tibbiy profildan AI uchun kontekst yaratish"""
    if not profile:
        return ""
    blood_group, age, weight, height, chronic, allergies = profile
    parts = []
    if blood_group:
        parts.append(f"Qon guruhi: {blood_group}")
    if age:
        parts.append(f"Yoshi: {age}")
    if weight:
        parts.append(f"Vazni: {weight} kg")
    if height:
        parts.append(f"Bo'yi: {height} sm")
    if chronic:
        parts.append(f"Surunkali kasalliklar: {chronic}")
    if allergies:
        parts.append(f"Dorilarga allergiyalar: {allergies}")
    if not parts:
        return ""
    return "\n\n[Foydalanuvchi tibbiy ma'lumotlari (javobda hisobga oling): " + "; ".join(parts) + "]"

# ═══════════════════════════════════════════════════════════════════
# ERROR HANDLER
# ═══════════════════════════════════════════════════════════════════

@dp.errors()
async def error_handler(event: types.ErrorEvent):
    logging.exception(f"Xatolik yuz berdi: {event.exception}")

# ═══════════════════════════════════════════════════════════════════
# BOT BUYRUQLARI RO'YXATI
# ═══════════════════════════════════════════════════════════════════

async def set_bot_commands(bot_instance: Bot):
    # ═══ FOYDALANUVCHI KOMANDALARI ═══
    user_commands = [
        types.BotCommand(command="start",        description="Botni ishga tushirish"),
        types.BotCommand(command="menu",         description="Bosh menyu"),
        types.BotCommand(command="help",         description="Yordam va yo'riqnoma"),
        types.BotCommand(command="contacts",     description="Tezkor telefon raqamlari"),
        types.BotCommand(command="premium",      description="💎 Premium — to'lash va tekin olish"),
        types.BotCommand(command="reklama",      description="📣 Reklama bo'yicha murojaat"),
    ]
    await bot_instance.set_my_commands(user_commands)

    # ═══ ADMIN KOMANDALARI (user + admin) ═══
    if ADMIN_ID and str(ADMIN_ID).isdigit():
        admin_only_commands = [
            types.BotCommand(command="stats",     description="📊 Bot statistikasi"),
            types.BotCommand(command="broadcast", description="📢 Ommaviy xabar yuborish"),
            types.BotCommand(command="ban",       description="🚫 Foydalanuvchini ban qilish"),
            types.BotCommand(command="unban",     description="✅ Foydalanuvchini unban qilish"),
        ]
        admin_commands = user_commands + admin_only_commands
        try:
            await bot_instance.set_my_commands(
                commands=admin_commands,
                scope=types.BotCommandScopeChat(chat_id=int(ADMIN_ID))
            )
        except Exception as e:
            logging.error(f"Admin komandalarini o'rnatishda xatolik: {e}")

    # Chap burchakdagi ko'k "Menyu" tugmasini "Mini Ilova" tugmasiga almashtiramiz
    if MINI_APP_URL:
        try:
            await bot_instance.set_chat_menu_button(
                menu_button=types.MenuButtonWebApp(
                    text="🚑 Mini Ilova",
                    web_app=types.WebAppInfo(url=MINI_APP_URL)
                )
            )
            logging.info("Bosh menyu tugmasi Mini Ilova-ga muvaffaqiyatli almashtirildi.")
        except Exception as e:
            logging.error(f"Menu tugmasini Mini Ilovaga almashtirishda xato: {e}")
    else:
        try:
            await bot_instance.set_chat_menu_button(
                menu_button=types.MenuButtonDefault()
            )
            logging.info("Bosh menyu tugmasi standart holatga qaytarildi.")
        except Exception as e:
            pass

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

@dp.message(Command("ballarim"))
@dp.message(F.text.in_(["🌐 Mening ballarim", "Mening ballarim", "mening ballarim"]))
async def cmd_ballarim(message: types.Message):
    """Mening ballarim komandasi"""
    user_id = message.from_user.id
    score = await asyncio.to_thread(database.get_score, user_id)
    is_prem, expires, *_ = await asyncio.to_thread(database.get_premium_info, user_id)
    
    msg = f"🏆 <b>Sizning ballaringiz:</b> {score} ball\n"
    if is_prem:
        msg += f"\n💎 Sizda <b>Premium</b> holati faol!\n📅 Amal qilish muddati: {expires}"
    else:
        msg += f"\n💡 Yana {max(0, 100 - score)} ball yig'sangiz, Premium avtomatik faollashadi!"
        
    await message.answer(msg, parse_mode="HTML", reply_markup=get_start_keyboard())

# ==============================================================================
# BARCHA QOLGAN XABARLAR UCHUN FALLBACK HANDLERLAR
# Qoidalarga asosan eng pastga qo'yildi ki, asosiy handlerlarga xalaqit qilmasin
# ==============================================================================

@dp.message(F.audio)
async def fallback_audio(message: types.Message):
    logging.info("message_type=audio")
    await message.reply("🎵 Audio qabul qilindi. Agar savolingiz bo'lsa, uni matn shaklida yoki ovozli xabar (voice) tarzida yuboring.")

@dp.message(F.video)
async def fallback_video(message: types.Message):
    logging.info("message_type=video")
    await message.reply("🎬 Video qabul qilindi. Qo'shimcha ma'lumot yoki savolingizni yuboring.")

@dp.message(F.video_note)
async def fallback_video_note(message: types.Message):
    logging.info("message_type=video_note")
    await message.reply("📹 Video xabar qabul qilindi. Qo'shimcha ma'lumot yoki savolingizni yuboring.")

@dp.message(F.document)
async def fallback_document(message: types.Message):
    logging.info("message_type=document")
    await message.reply("📄 Fayl qabul qilindi. Fayl bilan bog'liq savolingizni yozing.")

@dp.message(F.contact)
async def fallback_contact(message: types.Message):
    logging.info("message_type=contact")
    await message.reply("📞 Kontakt qabul qilindi.")

# F.location handler yuqorida (handle_location) allaqachon aniqlangan — bu yerda takrorlanmaydi

@dp.message(F.text)
async def fallback_text(message: types.Message, state: FSMContext):
    # Skip if already in AI chat state to avoid duplicate handling
    current_state = await state.get_state()
    if current_state == AiChatStates.chatting.state:
        return
    logging.info("message_type=text")
    user_id = message.from_user.id
    
    # Engagement javobi: matn FAQAT bot yuborgan engagement xabariga reply bo'lsa
    # javob deb qabul qilinadi. Aks holda (masalan "bolam zaharlandi") — AI ga (P0-2).
    from services import engagement

    unanswered = None
    reply_to = message.reply_to_message
    if reply_to is not None and reply_to.from_user is not None and reply_to.from_user.is_bot:
        try:
            unanswered = await asyncio.to_thread(
                engagement.find_unanswered_by_reply, user_id, reply_to.message_id
            )
        except Exception as e:
            logging.error(f"Error checking engagement log: {e}")
            unanswered = None

    if unanswered:
        event_type, event_date = unanswered
        await asyncio.to_thread(
            engagement.update_engagement_answer, user_id, event_type, event_date, message.text
        )

        if event_type == 'premium_checkin':
            reply = await engagement.generate_premium_reply(message.text, get_gemini_response)
            await asyncio.to_thread(
                engagement.update_engagement_answer,
                user_id, event_type, event_date, message.text, reply,
            )
            await message.reply(markdown_to_html(reply), parse_mode="HTML")
            return
        elif event_type == '10:10':
            await message.reply("Fikringiz uchun rahmat! 😊 O'zingizni asrang.", parse_mode="HTML")
            return
        elif event_type == '08:00':
            await message.reply("Ajoyib! Javobingiz qabul qilindi. 👍", parse_mode="HTML")
            return

    # Tizimdagi komandalarga yoki menyularga tushmagan har qanday oddiy matnni AI ga yo'naltiramiz
    await state.set_state(AiChatStates.chatting)
    await handle_ai_chat(message, state)

# =============================================================================
# Engagement answer button handler ("Javobini olish")
# =============================================================================
@dp.callback_query(F.data.startswith("engagement_answer"))
async def handle_engagement_answer(callback: types.CallbackQuery):
    """Process the 'Javobini olish' button for engagement questions.
    Expected callback_data format: engagement_answer:<event_type>:<event_date>
    """
    try:
        parts = callback.data.split(":")
        # callback_data formati: engagement_answer:<event_type>:<event_date>
        # Agar event_type '10:10' yoki '08:00' bo'lsa, parts 4 ta bo'ladi: ['engagement_answer', '10', '10', '2026-10-13']
        # Agar event_type 'premium_checkin' bo'lsa, parts 3 ta bo'ladi: ['engagement_answer', 'premium_checkin', '2026-10-13']
        if len(parts) == 4:
            event_type = f"{parts[1]}:{parts[2]}"
            event_date = parts[3]
        elif len(parts) == 3:
            event_type = parts[1]
            event_date = parts[2]
        else:
            raise ValueError(f"Kutilmagan format: {len(parts)} ta bo'lak")
    except Exception as e:
        logging.error(f"Invalid engagement_answer callback data '{callback.data}': {e}")
        await callback.answer("Noto'g'ri ma'lumot.", show_alert=True)
        return

    user_id = callback.from_user.id
    ekey = (user_id, event_type, event_date)
    if ekey in _in_progress_engagements:
        await callback.answer("⏳ Javob tayyorlanmoqda, iltimos kuting...", show_alert=False)
        return
    _in_progress_engagements.add(ekey)
    try:
        # Retrieve the original question and any existing answer/bot_reply
        conn = None
        c = None
        try:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute(
                """
                SELECT question, answer_text, bot_reply FROM engagement_logs
                WHERE user_id = %s AND event_type = %s AND event_date = %s
                ORDER BY sent_at DESC LIMIT 1
                """,
                (user_id, event_type, event_date),
            )
            row = c.fetchone()
        except Exception as e:
            logging.error(f"Error fetching engagement log for answer: {e}")
            row = None
        finally:
            database._safe_close(c, conn)

        question = row[0] if row else ""
        user_answer = row[1] if row else None
        existing_bot_reply = row[2] if row else None

        # If a bot reply was already sent, avoid duplicate sending
        if existing_bot_reply:
            await callback.message.reply(existing_bot_reply, parse_mode="HTML")
            await callback.answer()
            return

        # Generate AI reply based on the event type
        answer = None
        if event_type == "10:10" and user_answer:
            # Follow‑up based on user's morning answer
            answer = await engagement.generate_1010_followup(user_answer, get_gemini_response)
        elif event_type == "premium_checkin":
            # Premium check‑in specific reply
            answer = await engagement.generate_premium_reply(question, get_gemini_response)
        else:
            # Generic answer: ask Gemini to generate a short helpful response to the question
            prompt = (
                f"Foydalanuvchi quyidagi savolni berdi: '{question}'. "
                "Javobini qisqa (1‑2 gap), samimiy, foydali shaklda yoz. "
                "Shifokor yoki farmatsevt rolini o'ynama."
            )
            async with KeepTyping(callback.bot, callback.message.chat.id):
                answer = await get_gemini_response(prompt)
            if not answer:
                answer = "⚠️ AI hozir mavjud emas, keyinroq qayta urinib ko'ring."

        # Record bot reply in DB (no user answer text stored)
        try:
            engagement.update_engagement_answer(user_id, event_type, event_date, "", bot_reply=answer)
        except Exception as e:
            logging.error(f"Failed to update engagement answer in DB: {e}")

        await callback.message.reply(answer, parse_mode="HTML")
        await callback.answer()
    finally:
        _in_progress_engagements.discard(ekey)


@dp.message()
async def fallback_all(message: types.Message):
    # Ignore text messages – they are handled by fallback_text / AI handlers.
    if message.content_type == "text":
        # No processing needed for plain text messages
        return

    msg_type = message.content_type
    logging.info(f"message_type={msg_type}")
    await message.reply("ℹ️ Bu turdagi xabar qabul qilindi, lekin hozircha uni qayta ishlash imkonim yo'q.")
    return

async def health_check(request):
    return web.Response(text="Birinchi Yordam bot is running!")

# ═══════════════════════════════════════════════════════════════════
# MINI APP API (/api/...) — initData bilan himoyalangan
# Nginx `location /api/` ni URI o'zgartirmasdan 127.0.0.1:PORT ga uzatadi,
# shuning uchun route'lar aynan /api/... prefiksi bilan ro'yxatdan o'tadi.
# ═══════════════════════════════════════════════════════════════════
WEB_BIND_HOST = "127.0.0.1"      # internetga ochiq emas; faqat nginx (localhost) orqali
API_MAX_BODY = 4096              # so'rov tanasi hajmi (bayt)
API_RATE_LIMIT = 20              # bitta foydalanuvchi uchun
API_RATE_WINDOW = 60.0           # soniya
SPIN_COOLDOWN_SECONDS = 24 * 3600


class ApiRateLimiter:
    """Foydalanuvchi bo'yicha sirpanuvchi oyna (in-memory). Event loop ichida chaqiriladi."""
    CLEANUP_EVERY = 500

    def __init__(self, limit: int = API_RATE_LIMIT, window: float = API_RATE_WINDOW):
        self.limit = limit
        self.window = window
        self._hits: dict = {}
        self._calls = 0

    def allow(self, user_id: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        cutoff = now - self.window
        self._calls += 1
        if self._calls >= self.CLEANUP_EVERY:      # lug'at cheksiz o'smasligi uchun
            self._calls = 0
            for uid in [u for u, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
                del self._hits[uid]
        hits = [t for t in self._hits.get(user_id, ()) if t > cutoff]
        if len(hits) >= self.limit:
            self._hits[user_id] = hits
            return False
        hits.append(now)
        self._hits[user_id] = hits
        return True


api_rate_limiter = ApiRateLimiter()


def _api_json(data: dict, status: int = 200, headers: dict | None = None) -> web.Response:
    return web.json_response(data, status=status, headers={"Cache-Control": "no-store", **(headers or {})})


def _api_error(status: int, code: str, headers: dict | None = None) -> web.Response:
    """Xato javobida stack trace yoki DB xabari QAYTARILMAYDI — faqat qisqa kod."""
    return _api_json({"ok": False, "error": code}, status, headers)


def _plain_text(message: str) -> str:
    """Bot uchun yozilgan HTML xabarni oddiy matnga aylantiradi (frontendda XSS bo'lmasligi uchun)."""
    return html.unescape(re.sub(r"<[^>]+>", "", message or "")).strip()


def _read_spin_state(user_id: int):
    """(last_spin_date, pending_spin_prize) — mavjud ustunlardan o'qiydi, hech narsa generatsiya qilmaydi."""
    with database._managed_cursor() as (conn, c):
        c.execute("SELECT last_spin_date, pending_spin_prize FROM users WHERE user_id = %s", (user_id,))
        row = c.fetchone()
    return (row[0], row[1]) if row else (None, None)


def _spin_cooldown_seconds(last_spin, now: datetime | None = None) -> int:
    """Keyingi aylantirishgacha qolgan soniyalar (0 — kutish yo'q).
    database.check_and_grant_spin_bonus / generate_or_get_spin_prize dagi qoida bilan bir xil."""
    if not last_spin:
        return 0
    uz_tz = timezone(timedelta(hours=5))
    now = now or database.get_uz_now()
    try:
        last_dt = datetime.fromisoformat(str(last_spin))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=uz_tz)
        return max(0, math.ceil(SPIN_COOLDOWN_SECONDS - (now - last_dt).total_seconds()))
    except ValueError:
        # Eski YYYY-MM-DD formati: shu kun ichida bloklangan, ertaga 00:00 gacha
        if str(last_spin) == now.date().isoformat():
            midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            return max(1, math.ceil((midnight - now).total_seconds()))
        return 0


async def _api_authenticate(request: web.Request):
    """So'rovni tekshiradi. (user_id, None) yoki (None, xato javobi) qaytaradi.
    user_id FAQAT tekshirilgan initData ichidagi user.id dan olinadi, tanadagi boshqa maydonlar e'tiborga olinmaydi.
    Tekshiruvdan o'tmasa hech qanday DB chaqiruvi qilinmaydi."""
    if request.content_type != "application/json":
        return None, _api_error(415, "unsupported_media_type")
    if request.content_length is not None and request.content_length > API_MAX_BODY:
        return None, _api_error(413, "payload_too_large")
    try:
        raw = await request.read()          # Application(client_max_size=API_MAX_BODY) chegarani qo'llaydi
    except web.HTTPRequestEntityTooLarge:
        return None, _api_error(413, "payload_too_large")
    except Exception:
        return None, _api_error(400, "bad_request")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None, _api_error(400, "bad_request")
    if not isinstance(payload, dict) or not isinstance(payload.get("init_data"), str):
        return None, _api_error(400, "bad_request")

    user = parse_init_data(payload["init_data"])
    if user is None:
        return None, _api_error(403, "forbidden")
    user_id = user["id"]
    if not api_rate_limiter.allow(user_id):
        return None, _api_error(429, "rate_limited", {"Retry-After": str(int(API_RATE_WINDOW))})
    return user_id, None


async def _api_handle(request: web.Request, name: str, action) -> web.Response:
    user_id, error = await _api_authenticate(request)
    if error is not None:
        return error
    try:
        banned, *_ = await asyncio.to_thread(database.is_user_banned, user_id)
        if banned:
            return _api_error(403, "banned")
        return _api_json(await action(user_id))
    except Exception:
        # init_data va so'rov tanasi loglanmaydi
        logging.exception("API %s xatosi (user=%s)", name, user_id)
        return _api_error(500, "server_error")


async def _api_state_action(user_id: int) -> dict:
    score = await asyncio.to_thread(database.get_score, user_id)
    bonus = await asyncio.to_thread(database.get_daily_bonus_info, user_id)
    prize = await asyncio.to_thread(database.generate_or_get_spin_prize, user_id)
    cooldown = 0
    if prize is None:
        last_spin, _ = await asyncio.to_thread(_read_spin_state, user_id)
        cooldown = _spin_cooldown_seconds(last_spin)
    return {
        "ok": True,
        "score": score,
        "streak": bonus["streak"],
        "daily_claimed": bool(bonus["is_claimed_today"]),
        "prize": prize,                 # None -> null (kutish yoki foydalanuvchi yo'q); 0 -> SUPER PRIZ
        "cooldown_seconds": cooldown,
    }


async def _api_spin_claim_action(user_id: int) -> dict:
    _, pending = await asyncio.to_thread(_read_spin_state, user_id)    # faqat o'qiydi, yangi yutuq yaratmaydi
    ok, message = await asyncio.to_thread(database.check_and_grant_spin_bonus, user_id, 0)
    score = await asyncio.to_thread(database.get_score, user_id)
    return {"ok": bool(ok), "message": _plain_text(message), "score": score,
            "is_super": bool(ok and pending == 0)}


async def _api_bonus_claim_action(user_id: int) -> dict:
    granted, points, streak = await asyncio.to_thread(database.check_and_grant_daily_bonus, user_id)
    score = await asyncio.to_thread(database.get_score, user_id)
    if granted:
        message = f"Bugungi bonus olindi! +{points} ball. Ketma-ket kirish: {streak}-kun."
    elif streak:
        message = "Siz bugungi bonusni olib bo'lgansiz. Ertaga yana kiring."
    else:
        message = "Bonusni olib bo'lmadi."
    return {"ok": bool(granted), "message": message, "points": points, "streak": streak, "score": score}


async def api_state(request: web.Request) -> web.Response:
    return await _api_handle(request, "state", _api_state_action)


async def api_spin_claim(request: web.Request) -> web.Response:
    return await _api_handle(request, "spin/claim", _api_spin_claim_action)


async def api_bonus_claim(request: web.Request) -> web.Response:
    return await _api_handle(request, "bonus/claim", _api_bonus_claim_action)


def create_web_app() -> web.Application:
    app = web.Application(client_max_size=API_MAX_BODY)
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    # Faqat POST: boshqa metodlarga aiohttp o'zi 405 qaytaradi
    app.router.add_post("/api/state", api_state)
    app.router.add_post("/api/spin/claim", api_spin_claim)
    app.router.add_post("/api/bonus/claim", api_bonus_claim)
    return app


async def start_web_server():
    app = create_web_app()

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, WEB_BIND_HOST, port)
    await site.start()

    print(f"🌐 Web server started on {WEB_BIND_HOST}:{port}")

async def main():
    await asyncio.to_thread(database.init_db)
    await asyncio.to_thread(medicine_db.init_medicine_db)
    
    # Diagnostic: list available models to debug 404 NOT FOUND
    if gemini_client:
        try:
            print("🔍 Qaysi Gemini modellari mavjudligini tekshirmoqdamiz...")
            for m in gemini_client.models.list():
                # supported_actions might be a list or similar, we check if generateContent is supported
                actions = getattr(m, 'supported_actions', [])
                if any("generateContent" in str(a) for a in actions):
                    print(f"  - Model: {m.name}")
        except Exception as e:
            print(f"❌ Modellarni yuklashda xatolik: {e}")
            
    # Middleware-larni ro'yxatdan o'tkazish
    dp.message.outer_middleware(ThrottlingMiddleware())
    dp.callback_query.outer_middleware(ThrottlingMiddleware())
    dp.message.outer_middleware(BanMiddleware())
    dp.callback_query.outer_middleware(BanMiddleware())
    dp.callback_query.outer_middleware(AnswerCallbackMiddleware())
    dp.message.outer_middleware(FsmResetMiddleware())
    # dp.message.outer_middleware(DailyBonusMiddleware())
    
    await set_bot_commands(bot)
    print("✅ Bot ishga tushdi!")
    print("📊 Barcha 8 ta funksiya faol:")
    print("  1. 👤 Tibbiy Profil")
    print("  2. 💊 Dori Eslatmalari")
    print("  3. 🎙️ Ovozli Xabarlar")
    print("  4. 🗺️ Kasalxona + Dorixona")
    print("  5. ⚖️ Sog'liq Kalkulyatorlari")
    print("  6. 💳 Avtomatik To'lov")
    print("  7. 🔔 Kunlik Maslahatlar")
    print("  8. 💊 Dori Database-First Search (AI token tejash)")

    # Background tasklar ishga tushiramiz
    global background_tasks
    background_tasks = set()
    
    task1 = asyncio.create_task(check_and_send_reminders())  # Feature 2: Dori eslatmalari
    background_tasks.add(task1)
    task1.add_done_callback(background_tasks.discard)
    
    # Yangi Daily Engagement tizimi
    from services import engagement_scheduler
    engagement_scheduler.start_scheduler(bot, get_gemini_response)
    
    task3 = asyncio.create_task(start_web_server())           # Render web server
    background_tasks.add(task3)
    task3.add_done_callback(background_tasks.discard)

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    except Exception as e:
        if "conflict" in str(e).lower():
            logging.critical(
                "❌ TELEGRAM CONFLICT ERROR: Boshqa bot instansiyasi bir vaqtda 'getUpdates' (polling) qilmoqda! "
                "Iltimos, VPS dagi systemd xizmatini (birinchiyordam.service) yoki boshqa ishlayotgan bot jarayonini to'xtating.",
                exc_info=True
            )
        else:
            logging.critical(f"Bot polling xatosi: {e}", exc_info=True)
        raise
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())

