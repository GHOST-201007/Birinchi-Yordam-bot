"""
reset_menu_buttons.py — BIR MARTALIK skript: barcha foydalanuvchilarning SHAXSIY menyu tugmasini o'chiradi.

Sabab: ilgari update_user_menu_button har /start da chat_id li (shaxsiy) MenuButton o'rnatgan va o'shanda
MINI_APP_URL trycloudflare.com edi. Shaxsiy tugma umumiysidan ustun, shuning uchun ba'zi foydalanuvchilarda mini app
eski manzilga ochiladi. Har bir foydalanuvchi uchun MenuButtonDefault() o'rnatilsa, shaxsiy tugma o'chadi va botning
UMUMIY (to'g'ri) tugmasi ishlaydi.

Ishga tushirish (serverda, loyiha papkasidan):
    venv/bin/python scripts/reset_menu_buttons.py --dry-run     # faqat sanaydi, Telegram'ga so'rov yubormaydi
    venv/bin/python scripts/reset_menu_buttons.py               # haqiqiy ishga tushirish

  * BOT_TOKEN va DATABASE_URL .env dan olinadi va HECH QAYERGA chiqarilmaydi (xato matnlari ham: faqat xato turi).
  * Tezlik: soniyasiga ko'pi bilan 20 ta so'rov; TelegramRetryAfter kelsa hamma so'rovlar kutadi va qayta uriniladi.
  * Botni bloklagan / chat topilmagan foydalanuvchilar o'tkazib yuboriladi.
  * Oxirida: jami / muvaffaqiyatli / o'tkazib yuborilgan soni.
"""
import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from aiogram import Bot, types  # noqa: E402
from aiogram.exceptions import (  # noqa: E402
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

MAX_RPS = 20            # Telegram limiti: soniyasiga ko'pi bilan shuncha so'rov
CONCURRENCY = 10        # bir vaqtdagi so'rovlar (tezlikni baribir yagona RateLimiter cheklaydi)
MAX_RETRIES = 5         # bitta foydalanuvchi uchun RetryAfter / tarmoq xatosidan keyingi qayta urinishlar
PROGRESS_EVERY = 100

R_FORBIDDEN = "botni bloklagan yoki faol emas"
R_NOT_FOUND = "chat topilmadi"
R_BAD_REQUEST = "boshqa BadRequest"
R_RETRY_AFTER = "flood-limit: qayta urinishlar tugadi"
R_NETWORK = "tarmoq/server xatosi: qayta urinishlar tugadi"
R_API = "boshqa Telegram xatosi"
R_UNEXPECTED = "kutilmagan xato"


class FatalError(Exception):
    """Davom etib bo'lmaydigan xato (masalan, BOT_TOKEN yaroqsiz)."""


@dataclass
class Result:
    total: int = 0
    success: int = 0
    skipped: int = 0
    reasons: Counter = field(default_factory=Counter)
    dry_run: bool = False

    @property
    def processed(self) -> int:
        return self.success + self.skipped


class RateLimiter:
    """Barcha so'rovlar uchun YAGONA tezlik cheklovchi: so'rovlar boshlanish vaqti orasida kamida 1/rps soniya.
    Bir nechta ishchi bo'lsa ham soniyasiga rps dan oshmaydi."""

    def __init__(self, rps: float = MAX_RPS, clock=time.monotonic, sleep=asyncio.sleep):
        self.interval = 1.0 / rps
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = asyncio.Lock()

    def block(self, seconds: float) -> None:
        """Barcha so'rovlarni kamida `seconds` soniyaga to'xtatadi (RetryAfter / tarmoq xatosi)."""
        self._next = max(self._next, self._clock() + seconds)

    async def acquire(self) -> None:
        async with self._lock:
            wait = self._next - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._next = max(self._next, self._clock()) + self.interval


async def _reset_one(bot, uid: int, limiter: RateLimiter, max_retries: int):
    """Bitta foydalanuvchi uchun shaxsiy tugmani o'chiradi. (True, None) yoki (False, sabab) qaytaradi.
    Xato MATNLARI qaytarilmaydi: aiohttp xatolari URL (ya'ni BOT_TOKEN) ni o'z ichiga olishi mumkin."""
    last_failure = R_UNEXPECTED
    for attempt in range(max_retries + 1):
        await limiter.acquire()
        try:
            await bot.set_chat_menu_button(chat_id=uid, menu_button=types.MenuButtonDefault())
            return True, None
        except TelegramRetryAfter as exc:
            limiter.block(float(exc.retry_after) + 1.0)        # hamma kutadi, keyin qayta uriniladi
            last_failure = R_RETRY_AFTER
        except TelegramUnauthorizedError as exc:
            raise FatalError("BOT_TOKEN yaroqsiz (Telegram 401)") from None
        except TelegramForbiddenError:
            return False, R_FORBIDDEN
        except TelegramNotFound:
            return False, R_NOT_FOUND
        except TelegramBadRequest as exc:
            text = (getattr(exc, "message", "") or "").lower()
            if "chat not found" in text or "user not found" in text or "peer_id_invalid" in text:
                return False, R_NOT_FOUND
            return False, R_BAD_REQUEST
        except (TelegramNetworkError, TelegramServerError):
            limiter.block(float(attempt + 1))                  # 1, 2, 3... soniya
            last_failure = R_NETWORK
        except TelegramAPIError:
            return False, R_API
        except Exception:
            return False, R_UNEXPECTED
    return False, last_failure


async def reset_menu_buttons(bot, user_ids, result: Result | None = None, *, dry_run: bool = False,
                             max_rps: float = MAX_RPS, concurrency: int = CONCURRENCY,
                             max_retries: int = MAX_RETRIES, clock=time.monotonic, sleep=asyncio.sleep,
                             progress=None) -> Result:
    result = result if result is not None else Result()
    result.total = len(user_ids)
    result.dry_run = dry_run
    if dry_run or not user_ids:
        return result            # dry-run: Telegram'ga HECH QANDAY so'rov yuborilmaydi

    limiter = RateLimiter(max_rps, clock=clock, sleep=sleep)
    queue: asyncio.Queue = asyncio.Queue()
    for uid in user_ids:
        queue.put_nowait(uid)
    stop = asyncio.Event()
    fatal: list = []

    async def worker():
        while not stop.is_set():
            try:
                uid = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                ok, reason = await _reset_one(bot, uid, limiter, max_retries)
            except FatalError as exc:
                fatal.append(exc)
                stop.set()
                return
            if ok:
                result.success += 1
            else:
                result.skipped += 1
                result.reasons[reason] += 1
            if progress and result.processed % PROGRESS_EVERY == 0:
                progress(result.processed, result.total)

    await asyncio.gather(*(worker() for _ in range(max(1, min(concurrency, len(user_ids))))))
    if fatal:
        raise fatal[0]
    return result


def format_summary(result: Result) -> str:
    if result.dry_run:
        eta = int(result.total / MAX_RPS) + 1 if result.total else 0
        return (
            "DRY-RUN: Telegram'ga so'rov yuborilmadi.\n"
            f"Jami foydalanuvchilar: {result.total}\n"
            f"Haqiqiy ishga tushirishda yuboriladigan so'rovlar: {result.total} (taxminan {eta} soniya)"
        )
    lines = [
        f"Jami: {result.total}",
        f"Muvaffaqiyatli: {result.success}",
        f"O'tkazib yuborilgan: {result.skipped}",
    ]
    for reason, count in result.reasons.most_common():
        lines.append(f"  - {reason}: {count}")
    if result.processed < result.total:
        lines.append(f"Qayta ishlanmadi: {result.total - result.processed}")
    return "\n".join(lines)


def _clean_user_ids(raw) -> list:
    ids = set()
    for value in raw or []:
        try:
            uid = int(value)
        except (TypeError, ValueError):
            continue
        if uid > 0:                      # shaxsiy chat ID lari musbat
            ids.add(uid)
    return sorted(ids)


def _default_fetch_user_ids():
    import database                      # DATABASE_URL .env dan o'qiladi (database.py ichida)
    return database.get_all_users()


def main(argv=None, *, env=None, fetch_user_ids=None, bot_factory=None, stdout=None) -> int:
    parser = argparse.ArgumentParser(description="Barcha foydalanuvchilarning shaxsiy menyu tugmasini o'chiradi.")
    parser.add_argument("--dry-run", action="store_true", help="faqat sanaydi, Telegram'ga so'rov yubormaydi")
    args = parser.parse_args(argv)
    out = stdout if stdout is not None else sys.stdout

    def say(text=""):
        print(text, file=out, flush=True)

    if env is None:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_DIR, ".env"))
        env = os.environ

    token = env.get("BOT_TOKEN")
    if not args.dry_run and (not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE"):
        say("XATO: BOT_TOKEN .env da topilmadi.")
        return 2
    if fetch_user_ids is None:
        if not env.get("DATABASE_URL"):
            say("XATO: DATABASE_URL .env da topilmadi.")
            return 2
        fetch_user_ids = _default_fetch_user_ids

    try:
        user_ids = _clean_user_ids(fetch_user_ids())
    except Exception as exc:
        say(f"XATO: foydalanuvchilar ro'yxatini bazadan olib bo'lmadi ({type(exc).__name__}).")   # matn chiqarilmaydi
        return 1
    say(f"Bazadan {len(user_ids)} ta foydalanuvchi olindi." + (" (dry-run)" if args.dry_run else ""))

    result = Result()

    def progress(done, total):
        say(f"  ... {done}/{total}")

    async def run():
        bot = None
        try:
            if not args.dry_run:
                bot = bot_factory(token) if bot_factory else Bot(token=token)
            await reset_menu_buttons(bot, user_ids, result, dry_run=args.dry_run, progress=progress)
        finally:
            if bot is not None:
                try:
                    await bot.session.close()
                except Exception:
                    pass

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        say("\nTo'xtatildi (Ctrl+C).")
        say(format_summary(result))
        return 130
    except FatalError as exc:
        say(f"XATO: {exc}")
        say(format_summary(result))
        return 1

    say(format_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
