"""
Medicine Database-First Search Service
======================================
AI token sarfini kamaytirish uchun avval lokal bazadan qidirish tizimi.

Qidiruv tartibi:
  USER QUERY → NORMALIZE → CACHE → EXACT → NORMALIZED → SYNONYM/ALIAS →
  ACTIVE INGREDIENT → FUZZY → TOPILSA: LOCAL RESPONSE → TOPILMASA: AI/API → SAVE
"""

import os
import re
import logging
import datetime
import time
from difflib import SequenceMatcher

try:
    import psycopg2
    DB_TYPE = "postgres"
except ImportError:
    import sqlite3
    DB_TYPE = "sqlite"

from dotenv import load_dotenv
load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ═══════════════════════════════════════════════════════════════════
# IN-MEMORY CACHE (TTL bilan)
# ═══════════════════════════════════════════════════════════════════

_cache = {}        # {normalized_query: {"data": ..., "timestamp": ...}}
_CACHE_TTL = 3600  # 1 soat (soniyada)
_MAX_CACHE = 500   # Maksimal cache elementlari


def _cache_get(key: str):
    """Cache'dan qidirish. TTL o'tgan bo'lsa None qaytaradi."""
    entry = _cache.get(key)
    if entry and (time.time() - entry["timestamp"]) < _CACHE_TTL:
        return entry["data"]
    elif entry:
        del _cache[key]
    return None


def _cache_set(key: str, data: dict):
    """Cache'ga saqlash. Agar cache to'lgan bo'lsa, eng eskisini o'chiradi."""
    if len(_cache) >= _MAX_CACHE:
        oldest_key = min(_cache, key=lambda k: _cache[k]["timestamp"])
        del _cache[oldest_key]
    _cache[key] = {"data": data, "timestamp": time.time()}


# ═══════════════════════════════════════════════════════════════════
# DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════════════

def _get_conn():
    if DB_TYPE == "postgres":
        import database
        return database.get_connection()
    else:
        db_path = os.path.join(os.path.dirname(__file__), "medicine_knowledge.db")
        return sqlite3.connect(db_path)


def _placeholder():
    return "%s" if DB_TYPE == "postgres" else "?"


# ═══════════════════════════════════════════════════════════════════
# KIRIL ↔ LOTIN TRANSLITERATSIYA
# ═══════════════════════════════════════════════════════════════════

_LATIN_TO_CYRILLIC = {
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "ҳ", "i": "и", "j": "ж", "k": "к",
    "l": "л", "m": "м", "n": "н", "o": "о", "p": "п",
    "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "x": "х", "y": "й", "z": "з",
    "sh": "ш", "ch": "ч", "ng": "нг", "yo": "ё",
    "ya": "я", "yu": "ю", "oʻ": "ў", "gʻ": "ғ",
    "o'": "ў", "g'": "ғ",
}

_CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sh", "ъ": "", "ь": "", "э": "e",
    "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'",
    "ҳ": "h",
}


def _to_latin(text: str) -> str:
    """Kiril matnni lotin alifbosiga o'girish"""
    result = []
    for ch in text:
        lower = ch.lower()
        if lower in _CYRILLIC_TO_LATIN:
            result.append(_CYRILLIC_TO_LATIN[lower])
        else:
            result.append(lower)
    return "".join(result)


def _to_cyrillic(text: str) -> str:
    """Lotin matnni kiril alifbosiga o'girish"""
    result = []
    i = 0
    lower = text.lower()
    while i < len(lower):
        # 2 harfli kombinatsiyalarni avval tekshiramiz
        if i + 1 < len(lower):
            pair = lower[i:i+2]
            if pair in _LATIN_TO_CYRILLIC:
                result.append(_LATIN_TO_CYRILLIC[pair])
                i += 2
                continue
        ch = lower[i]
        if ch in _LATIN_TO_CYRILLIC:
            result.append(_LATIN_TO_CYRILLIC[ch])
        else:
            result.append(ch)
        i += 1
    return "".join(result)


# ═══════════════════════════════════════════════════════════════════
# NORMALIZATSIYA
# ═══════════════════════════════════════════════════════════════════

# Foydalanuvchi so'rovidan olib tashlanadigan so'zlar
_STOP_WORDS = {
    "nima", "haqida", "dori", "dorisi", "tabletkasi", "tabletka",
    "qanday", "necha", "narxi", "bergin", "aytib", "ber",
    "malumot", "ma'lumot", "maʼlumot", "kerak", "ishlatiladi",
    "nimaga", "foydasi", "zarari", "ta'siri", "taʼsiri",
    "bu", "uchun", "bilan", "va", "yoki", "ham",
    "qaysi", "kasallik", "davolash", "davolaydi",
    "ichish", "qo'llash", "qollash",
}


def normalize_query(text: str) -> str:
    """Foydalanuvchi so'rovini normalizatsiya qilish"""
    text = text.lower().strip()
    # Lotin alifbosiga o'girish (agar kiril bo'lsa)
    if any('\u0400' <= c <= '\u04ff' for c in text):
        text = _to_latin(text)
    # Maxsus belgilarni olib tashlash
    text = re.sub(r'[^\w\s\'-]', '', text)
    # Ortiqcha bo'shliqlarni tozalash
    text = re.sub(r'\s+', ' ', text).strip()
    # Stop so'zlarni olib tashlash
    words = text.split()
    filtered = [w for w in words if w not in _STOP_WORDS]
    return " ".join(filtered) if filtered else " ".join(words)


# ═══════════════════════════════════════════════════════════════════
# DATABASE YARATISH
# ═══════════════════════════════════════════════════════════════════

def init_medicine_db():
    """Dorilar bazasini yaratish (medicines va ai_response_cache jadvallari)"""
    conn = _get_conn()
    c = conn.cursor()
    ph = _placeholder()

    if DB_TYPE == "postgres":
        c.execute('''
            CREATE TABLE IF NOT EXISTS medicines (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                active_ingredient TEXT,
                aliases TEXT,
                description TEXT,
                usage_info TEXT,
                side_effects TEXT,
                warnings TEXT,
                dosage TEXT,
                related_medicines TEXT,
                source TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS ai_response_cache (
                id SERIAL PRIMARY KEY,
                query_normalized TEXT UNIQUE NOT NULL,
                query_original TEXT,
                response_text TEXT NOT NULL,
                response_type TEXT DEFAULT 'general',
                hit_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        # Indekslar
        c.execute("CREATE INDEX IF NOT EXISTS idx_med_normalized ON medicines (normalized_name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_med_active ON medicines (active_ingredient)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cache_query ON ai_response_cache (query_normalized)")
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                active_ingredient TEXT,
                aliases TEXT,
                description TEXT,
                usage_info TEXT,
                side_effects TEXT,
                warnings TEXT,
                dosage TEXT,
                related_medicines TEXT,
                source TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS ai_response_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_normalized TEXT UNIQUE NOT NULL,
                query_original TEXT,
                response_text TEXT NOT NULL,
                response_type TEXT DEFAULT 'general',
                hit_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute("CREATE INDEX IF NOT EXISTS idx_med_normalized ON medicines (normalized_name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_med_active ON medicines (active_ingredient)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cache_query ON ai_response_cache (query_normalized)")

    conn.commit()
    conn.close()
    logging.info("[MEDICINE_DB] Jadvallar yaratildi/tekshirildi.")

    # Boshlang'ich dorilar ro'yxatini qo'shish
    _seed_medicines()


# ═══════════════════════════════════════════════════════════════════
# BOSHLANG'ICH DORILAR MA'LUMOTI
# ═══════════════════════════════════════════════════════════════════

_SEED_MEDICINES = [
    {
        "name": "Paracetamol",
        "normalized_name": "paracetamol",
        "active_ingredient": "paracetamol (acetaminophen)",
        "aliases": "paratsetamol,парацетамол,acetaminophen,asetaminofen,panadol,efferalgan,tylenol,calpol",
        "description": (
            "💊 <b>Paracetamol (Acetaminophen)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Bosh og'rig'i, tish og'rig'i, mushak og'rig'i\n"
            "• Isitma (haroratni) tushirish\n"
            "• Shamollash va gripp belgilarini yengillashtirish\n\n"
            "💡 <b>Qanday ishlaydi:</b>\n"
            "Miyada og'riq va harorat markazlariga ta'sir qilib, og'riqni kamaytiradi va isitmani tushiradi.\n\n"
            "⚠️ <b>Muhim ogohlantirishlar:</b>\n"
            "• Jigar kasalligi bo'lganlarga ehtiyotkorlik bilan\n"
            "• Spirtli ichimliklar bilan birga qabul qilinmasin\n"
            "• Kunlik dozadan (4g) oshirmaslik kerak\n"
            "• Bolalarga yosh va vazniga qarab doza beriladi\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "Dori 3 kundan ko'p yordam bermasa, albatta shifokorga murojaat qiling!"
        ),
        "usage_info": "Kattalar: 500-1000mg har 4-6 soatda. Kunlik max: 4000mg. Bolalar: 10-15mg/kg har 4-6 soatda.",
        "side_effects": "Kamdan-kam: allergik reaktsiya, oshqozon bezovtaligi. Haddan tashqari dozada: jigar shikastlanishi.",
        "warnings": "Jigar kasalligi, alkogol iste'moli, boshqa paracetamol saqlovchi dorilar bilan birga qabul qilmaslik.",
        "dosage": "Kattalar: 500-1000mg, kuniga 3-4 marta. Bolalar: shifokor ko'rsatmasi bilan.",
        "related_medicines": "ibuprofen,aspirin,analgin,nimesulid",
    },
    {
        "name": "Ibuprofen",
        "normalized_name": "ibuprofen",
        "active_ingredient": "ibuprofen",
        "aliases": "ибупрофен,nurofen,brufen,advil,motrin,ibuprom",
        "description": (
            "💊 <b>Ibuprofen</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Yallig'lanishga qarshi (artrit, mushak og'rig'i)\n"
            "• Bosh og'rig'i, tish og'rig'i\n"
            "• Isitma tushirish\n"
            "• Hayz (menstruatsiya) og'rig'i\n\n"
            "💡 <b>Qanday ishlaydi:</b>\n"
            "NSAID guruhi — yallig'lanish, og'riq va isitmaga sabab bo'ladigan prostaglandinlarni kamaytiradi.\n\n"
            "⚠️ <b>Muhim ogohlantirishlar:</b>\n"
            "• Oshqozon yarasi bo'lganlarga qabul qilish mumkin emas\n"
            "• Buyrak muammolari bo'lganlarga ehtiyotkorlik\n"
            "• Homiladorlik (3-trimester) da taqiqlangan\n"
            "• Ovqatdan keyin qabul qilish tavsiya etiladi\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "5 kundan ortiq ishlatilsa, shifokorga murojaat qiling!"
        ),
        "usage_info": "Kattalar: 200-400mg har 4-6 soatda. Kunlik max: 1200mg (retseptsiz). Ovqatdan keyin.",
        "side_effects": "Oshqozon og'rig'i, ko'ngil aynishi, bosh aylanishi. Kamdan-kam: oshqozon qon ketishi.",
        "warnings": "Oshqozon yarasi, buyrak kasalligi, homiladorlik (3-trimester), aspirin allergiyasi.",
        "dosage": "Kattalar: 200-400mg, kuniga 3 marta. Bolalar: shifokor ko'rsatmasi bilan.",
        "related_medicines": "paracetamol,aspirin,nimesulid,diklofenak,ketoprofen",
    },
    {
        "name": "Aspirin",
        "normalized_name": "aspirin",
        "active_ingredient": "acetylsalicylic acid (atsetilsalitsil kislota)",
        "aliases": "аспирин,atsetilsalitsil,acetylsalicylic,atsil",
        "description": (
            "💊 <b>Aspirin (Atsetilsalitsil kislota)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Og'riq qoldirish (bosh, tish, mushak)\n"
            "• Isitma tushirish\n"
            "• Yallig'lanishga qarshi\n"
            "• Qon suyultirish (yurak-qon tomir kasalliklari profilaktikasi)\n\n"
            "⚠️ <b>Muhim ogohlantirishlar:</b>\n"
            "• 16 yoshgacha bolalarga BERISH MUMKIN EMAS (Reye sindromi xavfi)\n"
            "• Oshqozon yarasi bo'lganlarga taqiqlangan\n"
            "• Qon ketish xavfi bo'lganlarda ehtiyotkorlik\n"
            "• Operatsiyadan 1 hafta oldin qabul qilishni to'xtatish kerak\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "Qon suyultirish maqsadida faqat shifokor buyrug'i bilan qabul qiling!"
        ),
        "usage_info": "Og'riqqa: 300-600mg har 4-6 soatda. Qon suyultirish: 75-100mg kuniga 1 marta.",
        "side_effects": "Oshqozon og'rig'i, ko'ngil aynishi, qon ketish xavfi oshishi.",
        "warnings": "16 yoshgacha bolalarga berish mumkin emas. Oshqozon yarasi, qon ketish kasalliklari.",
        "dosage": "Kattalar: 300-600mg har 4-6 soatda. Profilaktika: 75-100mg/kun.",
        "related_medicines": "paracetamol,ibuprofen",
    },
    {
        "name": "Analgin",
        "normalized_name": "analgin",
        "active_ingredient": "metamizol (metamizol natriy)",
        "aliases": "анальгин,metamizol,baralgin,novalgin,dipyrone",
        "description": (
            "💊 <b>Analgin (Metamizol)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Kuchli og'riqlarni qoldirish\n"
            "• Isitma tushirish (boshqa dorilar yordam bermasa)\n"
            "• Kolika (ichak, buyrak, o't toshi og'rig'i)\n\n"
            "⚠️ <b>Muhim ogohlantirishlar:</b>\n"
            "• Ko'p mamlakatlarda taqiqlangan (agranulositoz xavfi)\n"
            "• Uzoq vaqt qabul qilmaslik kerak\n"
            "• Qon kasalliklari bo'lganlarga taqiqlangan\n"
            "• Homiladorlikda (ayniqsa 1 va 3-trimestr) qabul qilmaslik\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "Analgin faqat vaqtincha og'riq qoldiruvchi sifatida, qisqa muddatga ishlatilsin!"
        ),
        "usage_info": "Kattalar: 250-500mg, kuniga 2-3 marta. Max: 3g/kun.",
        "side_effects": "Allergik reaktsiya, qon bosimi tushishi, agranulositoz (kamdan-kam, lekin jiddiy).",
        "warnings": "Qon kasalliklari, homiladorlik, bronxial astma.",
        "dosage": "250-500mg, kuniga 2-3 marta. 5 kundan ortiq ishlatmaslik.",
        "related_medicines": "paracetamol,ibuprofen,ketanov",
    },
    {
        "name": "Amoxicillin",
        "normalized_name": "amoxicillin",
        "active_ingredient": "amoxicillin",
        "aliases": "амоксициллин,amoksitsillin,amoksisillin,flemoxin,augmentin,ospamox,amoxil",
        "description": (
            "💊 <b>Amoxicillin</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Bakterial infektsiyalar: angina, otit, sinusit\n"
            "• Bronxit, pnevmoniya\n"
            "• Siydik yo'llari infektsiyalari\n"
            "• Teri infektsiyalari\n\n"
            "⚠️ <b>Muhim ogohlantirishlar:</b>\n"
            "• FAQAT shifokor buyrug'i bilan qabul qiling!\n"
            "• Antibiotik — virusga (gripp, shamollash) YORDAM BERMAYDI\n"
            "• Kursni to'liq tugatish shart (yarqillab tashlamaslik)\n"
            "• Penitsillin allergiyasi bo'lganlarga berish mumkin emas\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "Antibiotikni FAQAT shifokor tayinlasin. O'zboshimchalik bilan qabul qilish zararli!"
        ),
        "usage_info": "Kattalar: 250-500mg, kuniga 3 marta, 5-10 kun. Bolalar: shifokor buyrug'i bilan.",
        "side_effects": "Diareya, ko'ngil aynishi, teri toshmasi, allergik reaktsiya.",
        "warnings": "Penitsillin allergiyasi, jigar kasalligi. Kursni to'liq tugatish shart!",
        "dosage": "250-500mg har 8 soatda, 7-10 kun davomida.",
        "related_medicines": "azithromycin,cefixime,augmentin",
    },
    {
        "name": "Aktivlangan ko'mir",
        "normalized_name": "aktivlangan ko'mir",
        "active_ingredient": "activated charcoal (faollashtirilgan ko'mir)",
        "aliases": "активированный уголь,aktiv ko'mir,faol ko'mir,ugol,karbon",
        "description": (
            "💊 <b>Aktivlangan ko'mir (Faollashtirilgan ko'mir)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Ovqat zaharlanganda birinchi yordam\n"
            "• Gaz (meteorizm) va qorin shishishida\n"
            "• Diareya (ich ketish) da yordamchi\n\n"
            "💡 <b>Qanday ishlaydi:</b>\n"
            "Oshqozon va ichakdagi zaharli moddalarni o'ziga shimib (adsorbtsiya), ularni organizmdan chiqaradi.\n\n"
            "⚠️ <b>Muhim ogohlantirishlar:</b>\n"
            "• Boshqa dorilar bilan birga qabul qilmaslik (ularning ta'sirini kamaytiradi)\n"
            "• Doimiy qabul qilish vitaminlar so'rilishini buzadi\n"
            "• Qabziyatga olib kelishi mumkin\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "Zaharlanishda shifokorga murojaat qiling. Ko'mir faqat birinchi yordam vositasi!"
        ),
        "usage_info": "Zaharlanishda: 1g/kg (taxminan 1 tabletka/10 kg). Meteorizm: 1-2g kuniga 3-4 marta.",
        "side_effects": "Qabziyat, qora rang najas. Doimiy qabullashda vitamin yetishmovchiligi.",
        "warnings": "Oshqozon-ichak qon ketishi, ichak tutilishida qabul qilmaslik.",
        "dosage": "Zaharlanish: har 10 kg vazniga 1 tabletka. Oddiy: 250-500mg kuniga 3 marta.",
        "related_medicines": "smekta,enterosgel,polysorb",
    },
    {
        "name": "No-shpa",
        "normalized_name": "no-shpa",
        "active_ingredient": "drotaverin (drotaverine)",
        "aliases": "но-шпа,но шпа,noshpa,drotaverin,drotaverine,spazmalgon",
        "description": (
            "💊 <b>No-shpa (Drotaverin)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Oshqozon va ichak spazmlari (og'rig'i)\n"
            "• Hayz (menstruatsiya) og'rig'i\n"
            "• O't yo'llari spazmlari\n"
            "• Siydik yo'llari spazmlari\n"
            "• Bosh og'rig'i (spazmdan kelib chiqqan)\n\n"
            "💡 <b>Qanday ishlaydi:</b>\n"
            "Silliq mushaklarni bo'shashtiradi, spazmni yo'qotadi va og'riqni kamaytiradi.\n\n"
            "⚠️ <b>Muhim ogohlantirishlar:</b>\n"
            "• Past qon bosimi bo'lganlarda ehtiyotkorlik\n"
            "• Jigar va buyrak yetishmovchiligida doza kamaytirish\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "Og'riq 2-3 kundan keyin davom etsa, shifokorga murojaat qiling!"
        ),
        "usage_info": "Kattalar: 40-80mg (1-2 tabletka), kuniga 2-3 marta. Max: 240mg/kun.",
        "side_effects": "Bosh aylanishi, qon bosimi tushishi, ko'ngil aynishi (kamdan-kam).",
        "warnings": "Past qon bosimi, jigar/buyrak yetishmovchiligi.",
        "dosage": "40-80mg, kuniga 2-3 marta.",
        "related_medicines": "spazmalgon,papaverin",
    },
    {
        "name": "Loratadin",
        "normalized_name": "loratadin",
        "active_ingredient": "loratadine",
        "aliases": "лоратадин,claritine,klaritin,loratadine,claritin,loratin",
        "description": (
            "💊 <b>Loratadin (Claritin)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Allergik rinit (burun oqishi, aksirish)\n"
            "• Eshakemi (urtikaria)\n"
            "• Allergik kon'yunktivit (ko'z qichishi)\n"
            "• Teri qichishishi\n\n"
            "💡 <b>Qanday ishlaydi:</b>\n"
            "Antihistamin — allergik reaktsiyaga sabab bo'ladigan gistaminni bloklaydi.\n\n"
            "⚠️ <b>Afzalliklari:</b>\n"
            "• Uyquchanlik bermaydi (2-avlod antihistamin)\n"
            "• Kuniga 1 marta yetarli\n"
            "• Bolalarga 2 yoshdan boshlab berish mumkin\n\n"
            "🩺 <b>Shifokor maslahati:</b>\n"
            "Allergiya uzoq davom etsa, allergolog shifokorga murojaat qiling!"
        ),
        "usage_info": "Kattalar: 10mg kuniga 1 marta. Bolalar (2-12 yosh): 5mg kuniga 1 marta.",
        "side_effects": "Kamdan-kam: bosh og'rig'i, og'iz quruqligi, uyquchanlik.",
        "warnings": "Jigar kasalligi bo'lganlarda doza kamaytirish. Homiladorlikda shifokor maslahati.",
        "dosage": "10mg kuniga 1 marta (kattalar).",
        "related_medicines": "cetrizin,suprastin,diazolin,tavegil",
    },
    {
        "name": "Cetrizin",
        "normalized_name": "cetrizin",
        "active_ingredient": "cetirizine",
        "aliases": "цетиризин,cetirizine,zyrtec,zodak,setrizin,tsetrizin",
        "description": (
            "💊 <b>Cetrizin (Zyrtec/Zodak)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Allergik rinit va aksirish\n"
            "• Eshakemi\n"
            "• Allergik teri qichishishi\n"
            "• Kon'yunktivit\n\n"
            "💡 <b>Xususiyatlari:</b>\n"
            "• 2-avlod antihistamin\n"
            "• Tez ta'sir qiladi (30-60 daqiqada)\n"
            "• 24 soat davom etadi\n\n"
            "⚠️ <b>Ogohlantirishlar:</b>\n"
            "• Buyrak kasalligi bo'lganlarda doza kamaytirish\n"
            "• Ba'zi odamlarda engil uyquchanlik berishi mumkin\n\n"
            "🩺 Allergiya surunkali bo'lsa, shifokorga murojaat qiling!"
        ),
        "usage_info": "Kattalar: 10mg kuniga 1 marta. Bolalar (6-12 yosh): 5mg kuniga 1-2 marta.",
        "side_effects": "Uyquchanlik (kamroq), og'iz quruqligi, bosh og'rig'i.",
        "warnings": "Buyrak yetishmovchiligi. Avtomobil haydashda ehtiyotkorlik.",
        "dosage": "10mg kuniga 1 marta.",
        "related_medicines": "loratadin,suprastin,diazolin",
    },
    {
        "name": "Smekta",
        "normalized_name": "smekta",
        "active_ingredient": "diosmectite (diosmektit)",
        "aliases": "смекта,diosmectite,diosmektit,smecta",
        "description": (
            "💊 <b>Smekta (Diosmektit)</b>\n\n"
            "📌 <b>Nima uchun ishlatiladi:</b>\n"
            "• Diareya (ich ketish) — kattalar va bolalarda\n"
            "• Oshqozon-ichak bezovtaligi\n"
            "• Qorin og'rig'i va shishishi\n"
            "• Reflyuks (ko'krak sohasidagi kuyish)\n\n"
            "💡 <b>Qanday ishlaydi:</b>\n"
            "Ichak shilliq qavatini qoplaydi va himoyalaydi, zaharli moddalarni shimib oladi.\n\n"
            "⚠️ <b>Afzalliklari:</b>\n"
            "• Tabiiy tarkibli (loydan olingan)\n"
            "• Chaqaloqlardan boshlab berish mumkin\n"
            "• Homiladorlikda ham xavfsiz\n\n"
            "🩺 Diareya 3 kundan ko'p davom etsa, shifokorga murojaat qiling!"
        ),
        "usage_info": "Kattalar: 1 paket kuniga 3 marta. Bolalar: 1 paket kuniga 1-2 marta. Suvda eritib ichiladi.",
        "side_effects": "Qabziyat (kamdan-kam).",
        "warnings": "Ichak tutilishida qabul qilmaslik. Boshqa dorilardan 2 soat oldin/keyin qabul qilish.",
        "dosage": "1 paketni 100ml suvda eritib, ovqat orasida ichish.",
        "related_medicines": "aktivlangan ko'mir,enterosgel,polysorb,linex",
    },
]


def _seed_medicines():
    """Boshlang'ich dorilar ma'lumotlarini bazaga qo'shish (agar bo'sh bo'lsa)"""
    conn = _get_conn()
    c = conn.cursor()
    ph = _placeholder()

    c.execute("SELECT COUNT(*) FROM medicines")
    count = c.fetchone()[0]

    if count > 0:
        conn.close()
        return

    logging.info("[MEDICINE_DB] Boshlang'ich dorilar bazaga qo'shilmoqda...")

    for med in _SEED_MEDICINES:
        c.execute(
            f"INSERT INTO medicines (name, normalized_name, active_ingredient, aliases, description, usage_info, side_effects, warnings, dosage, related_medicines, source) "
            f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
            (
                med["name"], med["normalized_name"], med["active_ingredient"],
                med["aliases"], med["description"], med.get("usage_info", ""),
                med.get("side_effects", ""), med.get("warnings", ""),
                med.get("dosage", ""), med.get("related_medicines", ""), "seed"
            )
        )

    conn.commit()
    conn.close()
    logging.info(f"[MEDICINE_DB] {len(_SEED_MEDICINES)} ta dori qo'shildi.")


# ═══════════════════════════════════════════════════════════════════
# QIDIRUV FUNKSIYALARI
# ═══════════════════════════════════════════════════════════════════

def _search_exact(conn, query: str):
    """1-bosqich: Aniq nom bo'yicha qidirish"""
    c = conn.cursor()
    ph = _placeholder()
    c.execute(f"SELECT * FROM medicines WHERE LOWER(name) = {ph}", (query.lower(),))
    return c.fetchone()


def _search_normalized(conn, normalized: str):
    """2-bosqich: Normalizatsiya qilingan nom bo'yicha"""
    c = conn.cursor()
    ph = _placeholder()
    c.execute(f"SELECT * FROM medicines WHERE normalized_name = {ph}", (normalized,))
    return c.fetchone()


def _search_alias(conn, query: str):
    """3-bosqich: Sinonimlar/aliaslar bo'yicha qidirish"""
    c = conn.cursor()
    c.execute("SELECT * FROM medicines WHERE aliases IS NOT NULL")
    rows = c.fetchall()
    query_lower = query.lower()
    for row in rows:
        aliases = row[4]  # aliases ustuni
        if aliases:
            alias_list = [a.strip().lower() for a in aliases.split(",")]
            if query_lower in alias_list:
                return row
    return None


def _search_active_ingredient(conn, query: str):
    """4-bosqich: Faol modda bo'yicha qidirish"""
    c = conn.cursor()
    ph = _placeholder()
    like_query = f"%{query.lower()}%"
    c.execute(f"SELECT * FROM medicines WHERE LOWER(active_ingredient) LIKE {ph}", (like_query,))
    return c.fetchone()


def _search_fuzzy(conn, query: str, threshold: float = 0.55):
    """6-bosqich: O'xshashlik bo'yicha qidirish (fuzzy match)"""
    c = conn.cursor()
    c.execute("SELECT * FROM medicines")
    rows = c.fetchall()

    best_match = None
    best_score = 0

    query_lower = query.lower()

    for row in rows:
        # nom bo'yicha
        score = SequenceMatcher(None, query_lower, row[1].lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = row

        # normalized_name bo'yicha
        score2 = SequenceMatcher(None, query_lower, row[2].lower()).ratio()
        if score2 > best_score:
            best_score = score2
            best_match = row

        # aliases bo'yicha
        if row[4]:
            for alias in row[4].split(","):
                score3 = SequenceMatcher(None, query_lower, alias.strip().lower()).ratio()
                if score3 > best_score:
                    best_score = score3
                    best_match = row

    if best_score >= threshold:
        return best_match
    return None


def _search_ai_cache(conn, normalized: str):
    """AI javoblar cache'idan qidirish"""
    c = conn.cursor()
    ph = _placeholder()
    c.execute(f"SELECT response_text, hit_count FROM ai_response_cache WHERE query_normalized = {ph}", (normalized,))
    row = c.fetchone()
    if row:
        # hit_count oshirish
        c.execute(f"UPDATE ai_response_cache SET hit_count = hit_count + 1, updated_at = {ph} WHERE query_normalized = {ph}",
                  (datetime.datetime.now().isoformat(), normalized))
        conn.commit()
        return row[0]
    return None


def save_ai_response(query_original: str, response_text: str, response_type: str = "general"):
    """AI javobini cache bazasiga saqlash (keyingi so'rovlar uchun)"""
    normalized = normalize_query(query_original)
    conn = _get_conn()
    c = conn.cursor()
    ph = _placeholder()
    now = datetime.datetime.now().isoformat()

    try:
        if DB_TYPE == "postgres":
            c.execute(
                f"INSERT INTO ai_response_cache (query_normalized, query_original, response_text, response_type, created_at, updated_at) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}) "
                f"ON CONFLICT (query_normalized) DO UPDATE SET response_text = {ph}, updated_at = {ph}, hit_count = ai_response_cache.hit_count + 1",
                (normalized, query_original, response_text, response_type, now, now, response_text, now)
            )
        else:
            c.execute(
                f"INSERT OR REPLACE INTO ai_response_cache (query_normalized, query_original, response_text, response_type, created_at, updated_at) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                (normalized, query_original, response_text, response_type, now, now)
            )
        conn.commit()
        logging.info(f"[AI_CACHE] Saqlandi: '{normalized}'")
    except Exception as e:
        logging.error(f"[AI_CACHE] Saqlashda xato: {e}")
    finally:
        conn.close()

    # In-memory cache'ga ham saqlash
    _cache_set(normalized, {
        "found": True,
        "source": "ai_cache",
        "data": response_text
    })


def _format_medicine_response(row) -> str:
    """Database natijasini chiroyli formatda chiqarish"""
    # row: (id, name, normalized_name, active_ingredient, aliases, description,
    #        usage_info, side_effects, warnings, dosage, related_medicines, source, created_at, updated_at)
    description = row[5] if row[5] else ""

    parts = [description]

    if row[6]:  # usage_info
        parts.append(f"\n\n📋 <b>Qo'llash usuli:</b>\n{row[6]}")
    if row[8]:  # dosage
        parts.append(f"\n\n💉 <b>Doza:</b>\n{row[8]}")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
# ASOSIY QIDIRUV FUNKSIYASI
# ═══════════════════════════════════════════════════════════════════

def find_medicine(query: str) -> dict:
    """
    Asosiy qidiruv funksiyasi. Qidiruv tartibi:
    1. Cache (in-memory)
    2. Exact match
    3. Normalized match
    4. Synonym/alias match
    5. Active ingredient match
    6. AI response cache (database)
    7. Fuzzy search
    8. TOPILMASA → {"found": False}

    Returns:
        {
            "found": True/False,
            "source": "cache/database/synonym/ingredient/fuzzy/ai_cache",
            "data": str  # Formatted response text
        }
    """
    if not query or len(query.strip()) < 2:
        return {"found": False, "source": "none", "data": ""}

    normalized = normalize_query(query)
    logging.info(f"[SEARCH] query='{query}' → normalized='{normalized}'")

    # Kiril varianti ham yasaymiz
    cyrillic_query = _to_cyrillic(normalized) if not any('\u0400' <= c <= '\u04ff' for c in query) else query.lower()
    latin_query = _to_latin(normalized) if any('\u0400' <= c <= '\u04ff' for c in query) else normalized

    # 1. In-memory cache
    cached = _cache_get(normalized)
    if cached:
        logging.info(f"[CACHE] HIT: '{normalized}'")
        return cached

    conn = _get_conn()
    result = None

    try:
        # 2. Exact match
        row = _search_exact(conn, query.strip())
        if row:
            logging.info(f"[DATABASE] EXACT HIT: '{query}'")
            result = {"found": True, "source": "database", "data": _format_medicine_response(row)}
            _cache_set(normalized, result)
            return result

        # 3. Normalized match
        for q in [normalized, latin_query, cyrillic_query]:
            row = _search_normalized(conn, q)
            if row:
                logging.info(f"[DATABASE] NORMALIZED HIT: '{q}'")
                result = {"found": True, "source": "database", "data": _format_medicine_response(row)}
                _cache_set(normalized, result)
                return result

        # 4. Synonym/alias match
        for q in [query.strip(), normalized, latin_query, cyrillic_query]:
            row = _search_alias(conn, q)
            if row:
                logging.info(f"[SYNONYM] HIT: '{q}'")
                result = {"found": True, "source": "synonym", "data": _format_medicine_response(row)}
                _cache_set(normalized, result)
                return result

        # 5. Active ingredient match
        for q in [normalized, latin_query]:
            row = _search_active_ingredient(conn, q)
            if row:
                logging.info(f"[INGREDIENT] HIT: '{q}'")
                result = {"found": True, "source": "ingredient", "data": _format_medicine_response(row)}
                _cache_set(normalized, result)
                return result

        # 6. AI cache (database)
        ai_cached = _search_ai_cache(conn, normalized)
        if ai_cached:
            logging.info(f"[AI_CACHE] HIT: '{normalized}'")
            result = {"found": True, "source": "ai_cache", "data": ai_cached}
            _cache_set(normalized, result)
            return result

        # 7. Fuzzy match
        for q in [normalized, latin_query]:
            row = _search_fuzzy(conn, q)
            if row:
                logging.info(f"[FUZZY] HIT: '{q}' → '{row[1]}'")
                result = {"found": True, "source": "fuzzy", "data": _format_medicine_response(row)}
                _cache_set(normalized, result)
                return result

    finally:
        conn.close()

    # 8. TOPILMADI
    logging.info(f"[SEARCH] MISS: '{query}' → AI FALLBACK")
    return {"found": False, "source": "none", "data": ""}


def is_medicine_query(text: str) -> bool:
    """
    Matn dori/kasallik haqidami yoki oddiy savol/suhbatmi tekshiradi.
    Bu funksiya orqali faqat tegishli so'rovlar uchun database qidiruvi amalga oshiriladi.
    """
    if not text:
        return False

    text_lower = text.lower().strip()

    # Dori/tibbiy kalit so'zlar
    medicine_keywords = [
        "dori", "tabletka", "sirop", "tabletkasi", "dorisi",
        "preparat", "vitamin", "antibiotik", "og'riq qoldiruvchi",
        "isitma", "harorat", "allergiya", "qichish",
        "bosh og'ri", "tish og'ri", "oshqozon", "ich ketish",
        "kasallik", "davolash", "ichish kerak", "foydasi",
        "ta'sir", "zarari", "dozasi", "nima uchun",
        # Kiril
        "дори", "таблетка", "касаллик",
    ]

    # Agar matn juda qisqa bo'lsa (1-3 so'z) va dori nomiga o'xshasa
    words = text_lower.split()
    if len(words) <= 3:
        # Birinchi so'z katta harfdan boshlansa — dori nomi bo'lishi mumkin
        normalized = normalize_query(text)
        conn = _get_conn()
        try:
            # Tez tekshiruv — bazadan bor-yo'qligini
            for q in [normalized, text_lower]:
                row = _search_exact(conn, q) or _search_normalized(conn, q) or _search_alias(conn, q)
                if row:
                    return True
        finally:
            conn.close()

    # Kalit so'zlar bilan tekshirish
    for kw in medicine_keywords:
        if kw in text_lower:
            return True

    return False
