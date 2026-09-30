from aiohttp import web
import asyncio
import os
import logging
import re
import html
import json
from datetime import datetime, time, timedelta
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    LabeledPrice, ContentType, TelegramObject
)
from typing import Callable, Dict, Any, Awaitable
import time

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
            except Exception:
                pass
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
    def __init__(self, cooldown: float = 1.0):
        self.cooldown = cooldown
        self.last_requests = {}
        self.last_warnings = {}
        super().__init__()

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
                        except Exception:
                            pass
                    elif isinstance(event, types.CallbackQuery):
                        try:
                            await event.answer("⚠️ Iltimos, shoshilmang! Biroz kuting. 🕒", show_alert=True)
                        except Exception:
                            pass
                return # Stop processing
                
            self.last_requests[user_id] = now
        return await handler(event, data)

class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            is_banned, ban_msg = await asyncio.to_thread(database.is_user_banned, user.id)
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

# ═══════════════════════════════════════════════════════════════════
# ASOSIY SOZLAMALAR
# ═══════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
load_dotenv()

TOKEN          = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID       = os.getenv("ADMIN_ID", "YOUR_ADMIN_ID")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "YOUR_ADMIN_USERNAME")
CARD_NUMBER         = os.getenv("CARD_NUMBER", "")
CARD_NAME           = os.getenv("CARD_NAME", "")
PROVIDER_TOKEN      = os.getenv("PROVIDER_TOKEN", "")  # Feature 6: To'lov uchun (eski)
MINI_APP_URL        = os.getenv("MINI_APP_URL", "")
PREMIUM_STARS_PRICE = int(os.getenv("PREMIUM_STARS_PRICE", "50"))  # Stars narxi (default: 50 ⭐)

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
if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

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

GEMINI_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]

# Audio va rasm uchun multimodal modellar (gemini-2.5 yaxshi qo'llab-quvvatlaydi)
GEMINI_MULTIMODAL_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]

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
            err = str(e)
            if "429" in err or "404" in err or "RESOURCE_EXHAUSTED" in err or "NOT_FOUND" in err:
                logging.warning(f"{model} ishlamadi, keyingisiga o'tilmoqda...")
                last_error = e
                continue
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
                    try:
                        await sent_msg.edit_text(
                            markdown_to_html(full_text),
                            parse_mode="HTML",
                            reply_markup=reply_markup
                        )
                    except Exception:
                        pass
                    return full_text
                else:
                    logging.warning(f"{model} bo'sh javob qaytardi, keyingisiga o'tilmoqda...")
                    continue

            except Exception as e:
                err = str(e)
                if "429" in err or "404" in err or "RESOURCE_EXHAUSTED" in err or "NOT_FOUND" in err:
                    logging.warning(f"Streaming: {model} ishlamadi, keyingisiga o'tilmoqda...")
                    last_error = e
                    continue
                _handle_gemini_error(e)
                await sent_msg.edit_text(markdown_to_html("🤖 AI xizmati hozircha javob bermayapti. Keyinroq qayta urinib ko'ring."), parse_mode="HTML", reply_markup=reply_markup)
                return None

    logging.warning("Barcha streaming modellari ishlamadi, oddiy javobga o'tilmoqda...")
    fallback_text = await get_gemini_response(prompt)
    if fallback_text is None:
        try:
            await sent_msg.edit_text(markdown_to_html("🤖 AI xizmati hozircha javob bermayapti. Keyinroq qayta urinib ko'ring."), parse_mode="HTML", reply_markup=reply_markup)
        except Exception:
            pass
        return None
    try:
        await sent_msg.edit_text(markdown_to_html(fallback_text), parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        pass
    return fallback_text

async def get_web_app_url(user_id: int, page: str = None) -> str:
    if not MINI_APP_URL:
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
        
    return f"{MINI_APP_URL}?{urllib.parse.urlencode(params)}"

# ═══════════════════════════════════════════════════════════════════
# KLAVIATURALAR (KEYBOARDS)
# ═══════════════════════════════════════════════════════════════════

def get_start_keyboard():
    """Asosiy reply menyu tugmalari"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
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
            ],
        ],
        resize_keyboard=True,
        persistent=True
    )
    return keyboard

def get_conditions_keyboard():
    builder = InlineKeyboardBuilder()
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
    builder.adjust(2, 2, 2, 2, 2, 2, 1)
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
        f"⭐ <b>{PREMIUM_STARS_PRICE} Telegram Stars</b> yoki karta orqali.\n\n"
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
    await state.clear()
    user = message.from_user
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None
    username = user.username or None
    
    # Always register user first to ensure they exist in database
    await asyncio.to_thread(database.register_user, user.id, full_name=full_name, username=username)
    
    args = message.text.split() if message.text else []
    
    # Check for daily bonus claim
    if len(args) > 1 and args[1] == "claim_daily":
        success, points, streak = await asyncio.to_thread(database.check_and_grant_daily_bonus, user.id)
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
        await update_user_menu_button(user.id, message.bot)
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
            await update_user_menu_button(user.id, message.bot)
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
            referral_success = await asyncio.to_thread(database.handle_referral, user.id, referrer_id)
            
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

    web_app_url = await get_web_app_url(user.id)  # Bir marta yuklanadi
    
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

    await update_user_menu_button(user.id, message.bot)

async def update_user_menu_button(user_id: int, current_bot: Bot):
    web_app_url = await get_web_app_url(user_id)
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
    is_premium_user, _ = await asyncio.to_thread(database.get_premium_info, user_id)
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
    # "Batafsil ma'lumot" — FAQAT PREMIUM foydalanuvchilar uchun
    is_premium_user, premium_expires_at = await asyncio.to_thread(database.get_premium_info, user_id)
    import datetime as _dt
    if is_premium_user and premium_expires_at:
        expires = _dt.datetime.fromisoformat(premium_expires_at)
        if _dt.datetime.now() > expires:
            is_premium_user = 0
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
            f"⭐ <b>{PREMIUM_STARS_PRICE} Telegram Stars</b> — oylik Premium.\n\n"
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
        f"🩸 <b>Qon guruhi:</b> {blood_group or '—'}\n"
        f"🎂 <b>Yosh:</b> {age or '—'}\n"
        f"⚖️ <b>Vazn:</b> {f'{weight} kg' if weight else '—'}\n"
        f"📏 <b>Bo'y:</b> {f'{height} sm' if height else '—'}\n"
        f"🏥 <b>Surunkali kasalliklar:</b> {chronic or '—'}\n"
        f"⚠️ <b>Allergiyalar:</b> {allergies or '—'}\n\n"
        "ℹ️ Bu ma'lumotlar AI konsultatsiyada hisobga olinadi va aniqroq maslahat beradi."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Profilni to'ldirish / tahrirlash", callback_data="edit_profile")
    builder.button(text="🗑️ Profilni o'chirish",               callback_data="clear_profile")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

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
    is_prem, _ = await asyncio.to_thread(database.get_premium_info, user_id)
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
            text += f"• <b>{name}</b> — {times_display} ({days_icon})\n"
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
    is_prem, _ = await asyncio.to_thread(database.get_premium_info, user_id)
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
        except:
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
        f"💊 <b>Dori:</b> {medicine_name}\n"
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
    is_prem, _ = await asyncio.to_thread(database.get_premium_info, user_id)
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
            text += f"• <b>{name}</b> — {times.replace(',', ', ')} ({days_icon})\n"
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

    consumed_free = False
    consumed_daily = False
    if await asyncio.to_thread(database.try_consume_free_ai, user_id):
        consumed_free = True
    elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
        consumed_daily = True
    else:
        await premium_upsell(message)
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    if not gemini_client:
        await message.answer(
            "⚠️ Ovozli xabarlarni qayta ishlash uchun AI sozlanmagan.\n"
            "Iltimos, matnli savol yuboring.",
            reply_markup=get_start_keyboard()
        )
        return

    # Ovozli xabarni yuklab olish
    status_msg = await message.answer("🎙️ <b>Ovozli xabar qayta ishlanmoqda...</b>", parse_mode="HTML")
    try:
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

        prompt_parts = [
            {
                "inline_data": {
                    "mime_type": "audio/ogg",
                    "data": audio_b64
                }
            },
            {
                "text": (
                    "Bu audio xabarni o'zbek yoki rus tilida tinglab, "
                    "mazmunini o'zbekcha yozing va unga tibbiy/sog'liq nuqtai nazaridan javob bering. "
                    "Agar savol tibbiyotga oid bo'lmasa, faqat sog'liq mavzusida gapirishingizni ayting."
                )
            }
        ]

        # Gemini API ga yuborish (multimodal modellar bilan)
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
                    if response.text:
                        await status_msg.edit_text(
                            f"🎙️ <b>Ovozli xabaringiz qabul qilindi!</b>\n\n"
                            + markdown_to_html(response.text),
                            parse_mode="HTML"
                        )
                        return
                except Exception as e:
                    err = str(e)
                    logging.warning(f"Voice: {model} xato: {err[:200]}")
                    last_err = err
                    if "429" in err or "404" in err or "NOT_FOUND" in err or "RESOURCE_EXHAUSTED" in err:
                        continue
                    break

        # Fallback: API ovozni qayta ishlay olmasa
        logging.error(f"Voice: barcha modellar ishlamadi. Oxirgi xato: {last_err}")
        if consumed_free:
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            await asyncio.to_thread(database.refund_daily_request, user_id)
        await status_msg.edit_text(
            "⚠️ Ovozli xabarni matnlashtirish vaqtincha ishlamayapti.\n\n"
            "Iltimos, savolingizni <b>matn ko'rinishida</b> yuboring. 📝",
            parse_mode="HTML"
        )


    except Exception as e:
        logging.error(f"Voice handler xatosi: {e}")
        if consumed_free:
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            await asyncio.to_thread(database.refund_daily_request, user_id)
        await status_msg.edit_text(
            "⚠️ Ovozli xabarni qayta ishlashda xatolik yuz berdi.\n"
            "Iltimos, matnli savol yuboring.",
            parse_mode="HTML"
        )

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
        if is_callback:
            try:
                await message_or_cb.message.edit_text(text, parse_mode="HTML")
            except Exception:
                await message_or_cb.message.answer(text, parse_mode="HTML")
            await message_or_cb.answer()
        else:
            await message_or_cb.answer(text, parse_mode="HTML")
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
    await callback.answer(f"⚠️ Sizda {score} ball bor. 3 kunlik Premium Pro uchun yana {needed} ball to'plashingiz kerak!", show_alert=True)

@dp.callback_query(F.data == "redeem_points_premium")
async def process_redeem_points_premium(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    success = await asyncio.to_thread(database.check_and_grant_premium, user_id)
    if success:
        await callback.answer("🎉 100 ball yechildi! 3 kunlik Premium Pro aktivlashtirildi!", show_alert=True)
        await _show_premium_page(callback)
    else:
        score = await asyncio.to_thread(database.get_score, user_id)
        await callback.answer(f"⚠️ Ballaringiz yetarli emas (Hozirda {score} ball bor).", show_alert=True)

@dp.callback_query(F.data.in_(["buy_pro_7", "buy_plus_30", "buy_ultra_30", "pay_stars"]))
async def process_pay_stars_tariff(callback: types.CallbackQuery):
    """Telegram Stars tariflari invoice yuborish"""
    try:
        user_id = callback.from_user.id
        action = callback.data

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
        elif action == "buy_ultra_30":
            title = "👑 Premium Ultra — 30 kun"
            desc = "30 kunlik Premium Ultra obuna: Kuniga 100 AI so'rov (Cheksiz) va prioritet maslahat."
            payload = "ULTRA_30_DAYS"
            stars = int(os.getenv("ULTRA_MONTHLY_STARS", "300"))

        prices = [LabeledPrice(label=title, amount=stars)]
        await callback.message.answer_invoice(
            title=title,
            description=desc,
            payload=payload,
            currency="XTR",
            prices=prices,
            provider_token="",
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Stars invoice yuborishda xatolik: {e}")
        await callback.answer("⚠️ Invoice yuborishda xatolik yuz berdi.", show_alert=True)

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    """To'lovni tasdiqlash (10 soniya ichida javob berish shart)"""
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    """Muvaffaqiyatli to'lov — Stars to'lovi va duplicate protection"""
    user_id = message.from_user.id
    payment = message.successful_payment
    payload = payment.invoice_payload
    charge_id = payment.telegram_payment_charge_id or f"stars_{user_id}_{payment.total_amount}_{datetime.now().timestamp()}"

    product_map = {
        "PRO_7_DAYS": ("pro", 7, "⭐ Premium Pro (7 kun)"),
        "PLUS_30_DAYS": ("plus", 30, "💎 Premium Plus (30 kun)"),
        "ULTRA_30_DAYS": ("ultra", 30, "👑 Premium Ultra (30 kun)"),
        "stars_premium_1month": ("pro", 30, "⭐ Premium Pro (30 kun)"),
    }

    if payload in product_map:
        prem_type, days, product_title = product_map[payload]
        recorded = await asyncio.to_thread(
            database.record_payment_transaction,
            charge_id, user_id, payload, payment.total_amount, prem_type, days
        )

        if not recorded:
            await message.answer("⚠️ Bu to'lov allaqachon qayta ishlangan!", reply_markup=get_start_keyboard())
            return

        until = await asyncio.to_thread(database.grant_premium_days, user_id, days, prem_type)
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
        username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{user_id}"
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

    # Eski UZS to'lovi (agar PROVIDER_TOKEN bo'lsa)
    elif payment.invoice_payload == "premium_1month":
        await asyncio.to_thread(database.set_premium, user_id, 1, months=1)
        amount = payment.total_amount / 100
        await message.answer(
            "🎉 <b>To'lov muvaffaqiyatli amalga oshirildi!</b>\n\n"
            "💎 <b>Premium obunangiz faollashtirildi!</b>\n"
            "📅 Muddati: 1 oy\n\n"
            "Endi AI yordamchisidan cheksiz foydalaning! 🚀",
            parse_mode="HTML",
            reply_markup=get_start_keyboard()
        )
        username = f"@{message.from_user.username}" if message.from_user.username else f"ID:{user_id}"
        try:
            await message.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"💳 <b>Avtomatik to'lov qabul qilindi!</b>\n\n"
                    f"👤 Foydalanuvchi: {username}\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"💰 Summa: {amount:,.0f} UZS\n"
                    f"✅ Premium avtomatik faollashtirildi!"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Adminga to'lov xabari yuborishda xato: {e}")

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
    username = f"@{message.from_user.username}" if message.from_user.username else "Noma'lum"
    photo_id = message.photo[-1].file_id
    admin_keyboard = InlineKeyboardBuilder()
    admin_keyboard.button(text="✅ Tasdiqlash (Premium berish)", callback_data=f"adm_app_{user_id}")
    admin_keyboard.button(text="❌ Rad etish",                    callback_data=f"adm_rej_{user_id}")
    admin_keyboard.adjust(1, 1)
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
    except Exception as e:
        logging.error(f"Adminga chek yuborishda xatolik: {e}")
        await message.answer("⚠️ Texnik xatolik. Iltimos, to'g'ridan-to'g'ri adminga yozing.")

@dp.message(F.photo)
async def handle_general_photo(message: types.Message):
    user_id = message.from_user.id
    
    # Agar rasm ostida buyruq yozilgan bo'lsa (masalan, /broadcast) — o'tkazib yuboramiz

    # Agar rasm ostida buyruq yozilgan bo'lsa (masalan, /broadcast)
    if message.caption and message.caption.strip().startswith('/'):
        return

    consumed_free = False
    consumed_daily = False
    if await asyncio.to_thread(database.try_consume_free_ai, user_id):
        consumed_free = True
    elif await asyncio.to_thread(database.try_consume_daily_request, user_id):
        consumed_daily = True
    else:
        await premium_upsell(message)
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    if not gemini_client:
        await message.answer(
            "⚠️ Rasmlarni tahlil qilish uchun AI sozlanmagan.\n"
            "Iltimos, matnli savol yuboring.",
            reply_markup=get_start_keyboard()
        )
        return

    status_msg = await message.answer("🔍 <b>Rasm tahlil qilinmoqda...</b>", parse_mode="HTML")
    try:
        # Eng yuqori sifatli rasmni yuklab olamiz
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_path = file.file_path

        # Fayl baytlarini yuklab olamiz
        import io
        file_bytes = await message.bot.download_file(file_path)
        photo_data = file_bytes.read()

        # Base64 formatga o'tkazamiz
        import base64
        photo_b64 = base64.b64encode(photo_data).decode("utf-8")

        # Caption (tavsif) yozilgan bo'lsa uni qo'shib yuboramiz
        user_caption = message.caption or "Ushbu rasmdagi tibbiy holat bo'yicha tushuntirish va birinchi yordam choralarini bering."

        # Tibbiy profil ma'lumotlari
        profile = await asyncio.to_thread(database.get_medical_profile, user_id)
        profile_context = _build_profile_context(profile)

        prompt_parts = [
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": photo_b64
                }
            },
            {
                "text": (
                    f"Rasmda tasvirlangan tibbiy holat, jarohat, toshma yoki boshqa tibbiyot/salomatlik bilan "
                    f"bog'liq vaziyatni tahlil qiling. Quyidagi savol yoki topshiriq asosida javob bering:\n"
                    f"\"{user_caption}\"\n\n"
                    f"Siz Birinchi Yordam AI botsiz. Javob o'zbek tilida, professional, samimiy va tushunarli bo'lsin. "
                    f"Kasalni davolashga urinmang, birinchi yordam choralarini ko'rsating va zarur bo'lsa "
                    f"tez yordam (103) yoki shifokorga murojaat qilishni qat'iy eslating.\n"
                    + profile_context
                )
            }
        ]

        # Gemini modellari orqali sinab ko'ramiz (multimodal)
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
                    if response.text:
                        await status_msg.edit_text(
                            f"📸 <b>Rasm tahlili natijasi:</b>\n\n"
                            + markdown_to_html(response.text),
                            parse_mode="HTML"
                        )
                        return
                except Exception as e:
                    err = str(e)
                    logging.warning(f"Rasm: {model} xato: {err[:150]}")
                    last_err = err
                    if "429" in err or "404" in err or "RESOURCE_EXHAUSTED" in err or "NOT_FOUND" in err:
                        logging.warning(f"Rasm tahlilida {model} ishlamadi, keyingisiga o'tish...")
                        continue
                    break

        if consumed_free:
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            await asyncio.to_thread(database.refund_daily_request, user_id)
        await status_msg.edit_text(
            "⚠️ Rasmni tahlil qilish imkoni bo'lmadi.\n"
            "Iltimos, muammoni matn shaklida yozib yuboring. 📝",
            parse_mode="HTML"
        )

    except Exception as e:
        logging.error(f"Rasm tahlili handlerida xatolik: {e}")
        if consumed_free:
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            await asyncio.to_thread(database.refund_daily_request, user_id)
        await status_msg.edit_text(
            "⚠️ Rasmni qayta ishlashda xatolik yuz berdi.\n"
            "Iltimos, matnli savol yuboring.",
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("adm_app_"))
async def process_admin_approve(callback: types.CallbackQuery):
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("Siz admin emassiz!", show_alert=True)
        return
    user_id = int(callback.data.replace("adm_app_", ""))
    await asyncio.to_thread(database.set_premium, user_id, 1)
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
                "To'lovingiz tasdiqlandi va <b>Premium</b> obunangiz faollashtirildi!\n"
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
    user_id = int(callback.data.replace("adm_rej_", ""))
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>To'lov rad etildi.</b>",
        reply_markup=None,
        parse_mode="HTML"
    )
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ <b>To'lovingiz tasdiqlanmadi.</b>\n\n"
                "Chek yoki to'lovda muammo aniqlandi. Ma'lumotlarni tekshirib, qaytadan urinib ko'ring."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Foydalanuvchiga rad xabari yuborib bo'lmadi: {e}")
    await callback.answer("To'lov rad etildi!")

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
            except Exception as e:
                logging.warning(f"Eslatma yuborib bo'lmadi (user: {user_id}): {e}")

async def check_and_send_reminders():
    """Har daqiqa ishlab, dori vaqti kelganini tekshiradi"""
    from datetime import timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    last = datetime.now(uz_tz).replace(second=0, microsecond=0) - timedelta(minutes=1)
    while True:
        now = datetime.now(uz_tz).replace(second=0, microsecond=0)
        while last < now:  # o'tib ketgan daqiqalarni ham qamraydi
            last += timedelta(minutes=1)
            try:
                await _send_due_reminders(last)
            except Exception:
                logging.exception("Eslatma scheduler xatosi: %s", last)
        await asyncio.sleep(60 - datetime.now(uz_tz).second + 0.5)


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
    try:
        data = json.loads(message.web_app_data.data)
        if data.get("action") == "ai_consult":
            body_part_title = data.get("title", "noma'lum a'zo")
            user_id = message.from_user.id
            
            await message.answer(
                f"🤖 <b>AI Konsultatsiya ({body_part_title}):</b>\n\n"
                f"Siz <b>{body_part_title}</b> sohasidagi muammoni tanladingiz.\n"
                f"Tahlil qilinmoqda, iltimos kuting... ⏳",
                parse_mode="HTML"
            )
            
            prompt = (
                f"Foydalanuvchi inson tanasidagi '{body_part_title}' sohasida og'riq yoki bezovtalik borligini bildirdi. "
                f"Ushbu tana a'zosi bo'yicha eng ko'p uchraydigan kasalliklar, ularning kelib chiqish sabablari va "
                f"uy sharoitida birinchi yordam hamda shifokorga qachon murojaat qilish kerakligi haqida atroflicha, "
                f"chiroyli va tushunarli o'zbek tilida maslahat ber."
            )
            
            ai_response = await get_gemini_response(prompt)
            if ai_response is None:
                ai_response = "🤖 AI xizmati hozircha javob bermayapti. Keyinroq qayta urinib ko'ring."
            await message.answer(ai_response, parse_mode="HTML")
    except Exception as e:
        logging.error(f"web_app_data xatolik: {e}")
        await message.answer("⚠️ Ma'lumotlarni qayta ishlashda xatolik yuz berdi.")

# ═══════════════════════════════════════════════════════════════════
# KUNLIK TAVSIYA SCHEDULER (har kuni 08:00 da)
# ═══════════════════════════════════════════════════════════════════

async def daily_tips_scheduler():
    """Har kuni 08:00 da kunlik maslahatlarni yuboradi"""
    from datetime import timezone, timedelta
    uz_tz = timezone(timedelta(hours=5))
    while True:
        now = datetime.now(uz_tz)
        # Keyingi 08:00 ni hisoblash
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logging.info(f"Keyingi kunlik maslahat {wait_seconds/3600:.1f} soatdan keyin yuboriladi.")
        await asyncio.sleep(wait_seconds)
        await send_daily_tips()

# ═══════════════════════════════════════════════════════════════════
# ADMIN BUYRUQLARI
# ═══════════════════════════════════════════════════════════════════


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
        name_str = full_name or "Noma'lum"
        uname_str = f" (@{username})" if username else ""
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
        name_str = full_name or "Noma'lum"
        uname_str = f" (@{username})" if username else ""
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
    # 1 ta bepul savol tizimi yoki kunlik limit tekshiruvi
    consumed_free = False
    consumed_daily = False
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
            f"⭐ <b>{PREMIUM_STARS_PRICE} Telegram Stars</b> — 1 oylik.",
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
        if consumed_free:
            await asyncio.to_thread(database.refund_free_ai, user_id)
        if consumed_daily:
            await asyncio.to_thread(database.refund_daily_request, user_id)
    elif result:
        # AI javobini cache'ga saqlash (keyingi so'rovlar uchun)
        try:
            await asyncio.to_thread(medicine_db.save_ai_response, message.text, result, "ai_chat")
        except Exception as e:
            logging.warning(f"AI javobini cache'ga saqlashda xato: {e}")

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
    is_prem, expires = await asyncio.to_thread(database.get_premium_info, user_id)
    
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
    logging.info("message_type=text")
    # Tizimdagi komandalarga yoki menyularga tushmagan har qanday oddiy matnni AI ga yo'naltiramiz
    await state.set_state(AiChatStates.chatting)
    await handle_ai_chat(message, state)

@dp.message()
async def fallback_all(message: types.Message):
    msg_type = message.content_type
    logging.info(f"message_type={msg_type}")
    await message.reply("ℹ️ Bu turdagi xabar qabul qilindi, lekin hozircha uni qayta ishlash imkonim yo'q.")

async def health_check(request):
    return web.Response(text="Birinchi Yordam bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"🌐 Web server started on port {port}")

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
    asyncio.create_task(check_and_send_reminders())  # Feature 2: Dori eslatmalari
    asyncio.create_task(daily_tips_scheduler())       # Feature 7: Kunlik maslahatlar
    asyncio.create_task(start_web_server())           # Render web server

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

