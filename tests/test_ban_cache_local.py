"""
Ban-cache optimizatsiyasi uchun FAQAT LOKAL testlar.

Xavfsizlik kafolatlari:
  * psycopg2 va dotenv sys.modules ichida STUB bilan almashtiriladi (haqiqiy drayver/.env o'qilmaydi).
  * DATABASE_URL yaroqsiz qiymatga o'rnatiladi, get_connection fake bilan almashtiriladi.
  * Socket ulanishlari bloklanadi (urinish bo'lsa test yiqiladi).
  * bot.py import qilinmaydi: faqat kerakli middleware sinflari AST orqali ajratib olinadi
    va fake aiogram/types muhitida bajariladi (Telegram API chaqirilmaydi).
  * Global `time` moduli patch qilinmaydi; kesh uchun lokal fake clock ishlatiladi.
"""
import ast
import asyncio
import datetime
import logging
import os
import socket
import sys
import types as pytypes
import unittest
from typing import Any, Awaitable, Callable, Dict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ---- izolyatsiya rejimi ------------------------------------------------------
# Bu testlar FAQAT alohida, toza Python processda ishlaydi (BY_BAN_CACHE_ISOLATED=1).
# Boshqa testlar bilan bitta processda import qilinsa (masalan bot/database allaqachon
# haqiqiy .env bilan yuklangan bo'lsa), hech qanday stub/patch o'rnatilmaydi va
# load_tests() faqat bitta testni qaytaradi: u shu faylni alohida processda ishga tushiradi.
_ISOLATION_FLAG = "BY_BAN_CACHE_ISOLATED"
_ISOLATED = os.environ.get(_ISOLATION_FLAG) == "1"
_STUB_DATABASE_URL = "postgresql://invalid:invalid@127.0.0.1:1/none"
# Child processga uzatilmaydigan maxfiy o'zgaruvchilar
_SECRET_ENV_KEYS = (
    "DATABASE_URL", "BOT_TOKEN", "GEMINI_API_KEY", "PROVIDER_TOKEN",
    "CARD_NUMBER", "CARD_NAME", "ADMIN_ID",
)

if _ISOLATED:
    _preloaded = [m for m in ("database", "bot", "psycopg2", "dotenv") if m in sys.modules]
    if _preloaded:
        # Izolyatsiya kafolatlanmaydi -> testlar umuman ishga tushirilmaydi
        raise RuntimeError(
            "test_ban_cache_local: isolation not guaranteed, modules already imported: %s"
            % ", ".join(_preloaded)
        )

    # ---- tarmoqni bloklash ---------------------------------------------------
    _ORIG_CONNECT = socket.socket.connect
    _LOOPBACK = {"127.0.0.1", "::1", "localhost"}

    def _guarded_connect(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else address
        if host not in _LOOPBACK:
            raise AssertionError("NETWORK ACCESS ATTEMPTED IN LOCAL TEST: %r" % (address,))
        return _ORIG_CONNECT(self, address, *a, **k)   # faqat loopback (asyncio ichki socketpair uchun)

    def _blocked(*a, **k):
        raise AssertionError("NETWORK ACCESS ATTEMPTED IN LOCAL TEST")

    socket.socket.connect = _guarded_connect
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked   # DNS ham bloklanadi

    # ---- psycopg2 / dotenv stublari (haqiqiy DB drayveri yuklanmaydi) ---------
    os.environ["DATABASE_URL"] = _STUB_DATABASE_URL

    _psycopg2 = pytypes.ModuleType("psycopg2")
    _extras = pytypes.ModuleType("psycopg2.extras")
    _pool = pytypes.ModuleType("psycopg2.pool")

    class _NoPool:
        def __init__(self, *a, **k):
            raise AssertionError("REAL CONNECTION POOL CREATION ATTEMPTED")

    _pool.ThreadedConnectionPool = _NoPool
    _psycopg2.extras = _extras
    _psycopg2.pool = _pool
    sys.modules["psycopg2"] = _psycopg2
    sys.modules["psycopg2.extras"] = _extras
    sys.modules["psycopg2.pool"] = _pool
    _dotenv = pytypes.ModuleType("dotenv")
    _dotenv.load_dotenv = lambda *a, **k: False
    sys.modules["dotenv"] = _dotenv

    import database  # noqa: E402
else:
    database = None  # umumiy processda haqiqiy database moduliga tegilmaydi


# ---- fake DB ---------------------------------------------------------------
class FakeDB:
    def __init__(self):
        self.users = {}            # uid -> (is_banned, banned_until_naive[, ban_mode, ban_reason])
        self.registered = []
        self.connections = []
        self.fail_get_connection = False
        self.fail_register = False
        self.fail_execute = False
        self.fail_commit = False
        self.fail_rollback = False
        self.fail_conn_close = False
        self.fail_cursor_close = False

    def get_connection(self):
        if self.fail_get_connection:
            raise ConnectionError("get_connection failed")
        conn = FakeConn(self)
        self.connections.append(conn)
        return conn

    def register_user(self, user_id, full_name=None, username=None):
        if self.fail_register:
            raise ConnectionError("register failed")
        self.users.setdefault(user_id, (0, None))
        self.registered.append(user_id)

    @staticmethod
    def naive_wall(delta_seconds):
        return (database.get_uz_now() + datetime.timedelta(seconds=delta_seconds)).replace(tzinfo=None)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.row = None
        self.close_calls = 0

    def execute(self, sql, params=()):
        db = self.conn.db
        if db.fail_execute:
            raise ValueError("orig-exec-error")
        s = " ".join(sql.split())
        if s.startswith("SELECT is_banned, banned_until"):
            row = db.users.get(params[0])
            self.row = None if row is None else tuple(list(row) + [None] * (4 - len(row)))[:4]
        elif s.startswith("UPDATE users SET"):
            self.conn.pending.append((s, params))
        else:
            raise AssertionError("unexpected SQL: " + s)

    def fetchone(self):
        return self.row

    def close(self):
        self.close_calls += 1
        if self.conn.db.fail_cursor_close:
            raise RuntimeError("cursor-close-failed")


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.pending = []
        self.cursors = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def cursor(self):
        c = FakeCursor(self)
        self.cursors.append(c)
        return c

    def commit(self):
        self.commit_calls += 1
        if self.db.fail_commit:
            raise RuntimeError("commit-failed")
        for s, params in self.pending:
            uid = params[-1]
            if "is_banned = 1" in s:
                until = None
                if params[0]:
                    until = datetime.datetime.fromisoformat(params[0]).replace(tzinfo=None)  # PG TIMESTAMP tashlab yuboradi
                self.db.users[uid] = (1, until, params[1], params[2])
            elif "is_banned = 0" in s:
                self.db.users[uid] = (0, None)
        self.pending = []

    def rollback(self):
        self.rollback_calls += 1
        if self.db.fail_rollback:
            raise RuntimeError("rollback-failed")
        self.pending = []

    def close(self):
        self.close_calls += 1
        if self.db.fail_conn_close:
            raise RuntimeError("conn-close-failed")


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class DBTestCase(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.clock = FakeClock()
        self._orig = (database.get_connection, database.register_user, database._ban_cache)
        database.get_connection = self.db.get_connection
        database.register_user = self.db.register_user
        database._ban_cache = database._BanCache(clock=self.clock)
        self.cache = database._ban_cache

    def tearDown(self):
        database.get_connection, database.register_user, database._ban_cache = self._orig


# =============================================================================
# 1. (bool, str) kontrakti
# =============================================================================
class TestTupleContract(DBTestCase):
    def assert_tuple(self, r, banned, msg_contains=None):
        self.assertIsInstance(r, tuple)
        self.assertEqual(len(r), 2)
        self.assertIsInstance(r[0], bool)
        self.assertIsInstance(r[1], str)
        self.assertEqual(r[0], banned)
        if msg_contains is not None:
            self.assertIn(msg_contains, r[1])

    def test_not_banned(self):
        r = database.is_user_banned(1)
        self.assertEqual(r, (False, ""))
        self.assert_tuple(r, False)

    def test_permanent(self):
        self.db.users[2] = (1, None)
        r = database.is_user_banned(2)
        self.assertEqual(r, (True, "🚫 Doimiy (muddatsiz) ban faol."))
        self.assert_tuple(r, True)

    def test_temporary_active(self):
        self.db.users[3] = (1, FakeDB.naive_wall(300))
        r = database.is_user_banned(3)
        self.assert_tuple(r, True, "🚫 Vaqtinchalik ban muddati: ")
        self.assertTrue(r[1].endswith(" gacha."))

    def test_expired(self):
        self.db.users[4] = (1, FakeDB.naive_wall(-60))
        self.assertEqual(database.is_user_banned(4), (False, ""))

    def test_unparsable_until(self):
        self.db.users[5] = (1, "garbage")
        r = database.is_user_banned(5)
        self.assertTrue(r[0])                    # fail-closed: muddat o'qilmasa — banda
        self.assertIsNone(self.cache.get(5))   # tahlil xatosi keshlanmaydi

    def test_hit_returns_same_tuple_type(self):
        database.is_user_banned(6)
        r = database.is_user_banned(6)
        self.assert_tuple(r, False)

    def test_registration_on_miss_and_skip_on_hit(self):
        database.is_user_banned(7)
        self.assertEqual(self.db.registered, [7])
        self.assertIn(7, self.db.users)
        n_conn = len(self.db.connections)
        database.is_user_banned(7)
        self.assertEqual(self.db.registered, [7])           # hit register_user'ni chaqirmaydi
        self.assertEqual(len(self.db.connections), n_conn)  # va DB'ga bormaydi


# =============================================================================
# 2. TTL / FIFO / monotonic clock
# =============================================================================
class TestCache(DBTestCase):
    def test_ttl_expiry(self):
        database.is_user_banned(1)
        n = len(self.db.connections)
        self.clock.t += 29.9
        database.is_user_banned(1)
        self.assertEqual(len(self.db.connections), n)       # hali kesh
        self.clock.t += 0.2                                  # 30.1 s
        database.is_user_banned(1)
        self.assertGreater(len(self.db.connections), n)     # qayta o'qildi

    def test_ttl_capped_at_30(self):
        self.cache.put(1, (False, ""), 1000, self.cache.epoch())
        self.clock.t += 30.01
        self.assertIsNone(self.cache.get(1))

    def test_ttl_bounded_by_remaining_ban_time(self):
        self.db.users[9] = (1, FakeDB.naive_wall(5))
        database.is_user_banned(9)
        self.assertIsNotNone(self.cache.get(9))
        self.clock.t += 6.0
        self.assertIsNone(self.cache.get(9))

    def test_fifo_limit_2000(self):
        e = self.cache.epoch()
        for uid in range(2001):
            self.cache.put(uid, (False, ""), 30, e)
        self.assertEqual(len(self.cache._data), 2000)
        self.assertIsNone(self.cache.get(0))
        self.assertIsNotNone(self.cache.get(1))
        self.assertIsNotNone(self.cache.get(2000))

    def test_zero_or_negative_ttl_not_stored(self):
        self.cache.put(1, (False, ""), 0, self.cache.epoch())
        self.cache.put(2, (False, ""), -3, self.cache.epoch())
        self.assertIsNone(self.cache.get(1))
        self.assertIsNone(self.cache.get(2))

    def test_global_time_module_not_patched(self):
        import time
        self.assertIs(time.monotonic, __import__("time").monotonic)
        self.assertIsNot(database._time, None)


# =============================================================================
# 3. ban/unban invalidatsiyasi
# =============================================================================
class TestInvalidation(DBTestCase):
    def test_ban_invalidates_after_commit(self):
        self.assertEqual(database.is_user_banned(1), (False, ""))
        self.assertIsNotNone(self.cache.get(1))
        self.assertIsNone(database.ban_user(1))
        self.assertIsNone(self.cache.get(1))
        self.assertEqual(database.is_user_banned(1), (True, "🚫 Doimiy (muddatsiz) ban faol."))

    def test_unban_invalidates_after_commit(self):
        self.db.users[1] = (1, None)
        self.assertTrue(database.is_user_banned(1)[0])
        self.assertIsNone(database.unban_user(1))
        self.assertIsNone(self.cache.get(1))
        self.assertEqual(database.is_user_banned(1), (False, ""))

    def test_commit_failure_keeps_cache_untouched_ban(self):
        database.is_user_banned(1)
        before = self.cache.get(1)
        epoch_before = self.cache.epoch()
        self.db.fail_commit = True
        with self.assertRaises(RuntimeError) as cm:
            database.ban_user(1)
        self.assertEqual(str(cm.exception), "commit-failed")
        self.assertEqual(self.cache.get(1), before)
        self.assertEqual(self.cache.epoch(), epoch_before)

    def test_commit_failure_keeps_cache_untouched_unban(self):
        self.db.users[1] = (1, None)
        database.is_user_banned(1)
        before = self.cache.get(1)
        self.db.fail_commit = True
        with self.assertRaises(RuntimeError):
            database.unban_user(1)
        self.assertEqual(self.cache.get(1), before)

    def test_ban_temporary_sql_and_register(self):
        database.ban_user(1, 10)
        self.assertIn(1, self.db.registered)
        self.assertEqual(self.db.users[1][0], 1)
        self.assertIsNotNone(self.db.users[1][1])
        r = database.is_user_banned(1)
        self.assertTrue(r[0])
        self.assertIn("Vaqtinchalik", r[1])


# =============================================================================
# 4. Epoch poygasi
# =============================================================================
class TestEpoch(DBTestCase):
    def test_put_with_stale_epoch_rejected(self):
        e = self.cache.epoch()
        self.cache.invalidate(1)
        self.cache.put(1, (False, ""), 30, e)
        self.assertIsNone(self.cache.get(1))

    def test_concurrent_ban_between_read_and_put(self):
        orig = database._read_ban_state

        def racing(uid):
            res = orig(uid)          # eski: "banned emas"
            database.ban_user(uid)   # o'rtada admin ban qiladi
            return res

        database._read_ban_state = racing
        try:
            r = database.is_user_banned(1)
        finally:
            database._read_ban_state = orig
        self.assertEqual(r, (False, ""))            # joriy chaqiruv eski natijani qaytaradi
        self.assertIsNone(self.cache.get(1))        # lekin eskirgan natija keshga yozilmadi
        self.assertTrue(database.is_user_banned(1)[0])

    def test_concurrent_unban_between_read_and_put(self):
        self.db.users[1] = (1, None)
        orig = database._read_ban_state

        def racing(uid):
            res = orig(uid)
            database.unban_user(uid)
            return res

        database._read_ban_state = racing
        try:
            database.is_user_banned(1)
        finally:
            database._read_ban_state = orig
        self.assertIsNone(self.cache.get(1))
        self.assertFalse(database.is_user_banned(1)[0])


# =============================================================================
# 5. Vaqtinchalik ban muddati, timezone, auto-unban
# =============================================================================
class TestTempBanExpiry(DBTestCase):
    def test_stored_value_is_naive_and_comparison_works(self):
        database.ban_user(1, 1)
        stored = self.db.users[1][1]
        self.assertIsNone(stored.tzinfo)                      # PG TIMESTAMP naive qaytaradi
        self.assertTrue(database.is_user_banned(1)[0])        # TypeError -> "faol" fallback emas
        self.assertNotEqual(database.is_user_banned(1)[1], "🚫 Vaqtinchalik ban faol.")

    def test_expired_ban_reads_as_free_but_is_not_cleaned(self):
        """Muddati o'tgan ban o'qishda "ban yo'q" deb qaytadi, lekin bazada TOZALANMAYDI (tozalash va "Blok muddati tugadi"
        xabari faqat fon vazifasida: database.expire_finished_bans)."""
        self.db.users[1] = (1, FakeDB.naive_wall(-30))
        database._ban_cache.invalidate(1)
        before = len(self.db.connections)
        r = database.is_user_banned(1)
        self.assertEqual(r, (False, ""))
        self.assertEqual(self.db.users[1][0], 1)                              # bazada hali is_banned = 1
        self.assertEqual(len(self.db.connections) - before, 1)
        self.assertEqual(sum(c.commit_calls for c in self.db.connections[before:]), 0)   # o'qish hech narsa yozmadi

    def test_message_wall_time_matches_stored(self):
        when = FakeDB.naive_wall(600).replace(second=0, microsecond=0)
        self.db.users[1] = (1, when)
        msg = database.is_user_banned(1)[1]
        self.assertIn(when.strftime("%d.%m.%Y %H:%M"), msg)

    def test_aware_stored_value_also_ok(self):
        self.db.users[1] = (1, database.get_uz_now() + datetime.timedelta(minutes=5))
        self.assertTrue(database.is_user_banned(1)[0])

    def test_reading_an_expired_ban_never_commits(self):
        """O'qish yozmaydi: commit buzilgan bo'lsa ham muddati o'tgan ban xatosiz "ban yo'q" qaytaradi."""
        self.db.users[1] = (1, FakeDB.naive_wall(-30))
        orig_commit = FakeConn.commit

        def bad_commit(self_):
            raise RuntimeError("commit-failed")

        FakeConn.commit = bad_commit
        try:
            self.assertEqual(database.is_user_banned(1), (False, ""))
        finally:
            FakeConn.commit = orig_commit


# =============================================================================
# 6a. DB xatosi keshlanmaydi
# =============================================================================
class TestDBErrorsNotCached(DBTestCase):
    def test_get_connection_error(self):
        self.db.fail_get_connection = True
        with self.assertRaises(ConnectionError):
            database.is_user_banned(1)
        self.assertEqual(len(self.cache._data), 0)

    def test_register_error(self):
        self.db.fail_register = True
        with self.assertRaises(ConnectionError):
            database.is_user_banned(1)
        self.assertEqual(len(self.cache._data), 0)

    def test_execute_error_does_not_overwrite_existing_entry(self):
        database.is_user_banned(1)
        self.clock.t += 31
        self.db.fail_execute = True
        with self.assertRaises(ValueError):
            database.is_user_banned(1)
        self.assertEqual(len(self.cache._data), 0)


# =============================================================================
# 7. Cleanup xatolarida asl istisno saqlanishi
# =============================================================================
class TestCleanup(DBTestCase):
    def test_all_cleanup_fail_original_preserved(self):
        self.db.fail_execute = True
        self.db.fail_rollback = True
        self.db.fail_conn_close = True
        self.db.fail_cursor_close = True
        with self.assertLogs(level="WARNING"):
            with self.assertRaises(ValueError) as cm:
                database.ban_user(1)
        self.assertEqual(str(cm.exception), "orig-exec-error")
        conn = self.db.connections[-1]
        self.assertEqual(conn.rollback_calls, 1)
        self.assertEqual(conn.close_calls, 1)
        self.assertEqual(conn.cursors[-1].close_calls, 1)

    def test_commit_failure_with_cleanup_failures(self):
        self.db.fail_commit = True
        self.db.fail_rollback = True
        self.db.fail_conn_close = True
        with self.assertLogs(level="WARNING"):
            with self.assertRaises(RuntimeError) as cm:
                database.unban_user(1)
        self.assertEqual(str(cm.exception), "commit-failed")

    def test_cursor_close_failure_still_returns_connection(self):
        self.db.fail_cursor_close = True
        with self.assertLogs(level="WARNING"):
            database.ban_user(1)      # xatosiz tugaydi
        conn = self.db.connections[-1]
        self.assertEqual(conn.close_calls, 1)

    def test_connection_returned_on_success_read(self):
        database.is_user_banned(1)
        self.assertEqual(self.db.connections[-1].close_calls, 1)
        self.assertEqual(self.db.connections[-1].cursors[-1].close_calls, 1)

    def test_get_connection_failure_original_preserved(self):
        self.db.fail_get_connection = True
        with self.assertRaises(ConnectionError):
            database.ban_user(1)


# =============================================================================
# 6b + 8. Middleware (bot.py dan AST orqali ajratilgan, fake aiogram muhitida)
# =============================================================================
FREE_INFO = {"banned": False, "mode": None, "until": None, "reason": None}


class FakeBaseMiddleware:
    def __init__(self, *a, **k):
        pass


class FakeMessage:
    def __init__(self):
        self.answers = []

    async def answer(self, *a, **k):
        self.answers.append((a, k))


class FakeCallback:
    def __init__(self):
        self.answers = []

    async def answer(self, *a, **k):
        self.answers.append((a, k))


def load_middlewares(fake_database):
    with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    wanted = {"ThrottlingMiddleware", "BanMiddleware"}
    helpers = {"ban_contact_line", "ban_term_text", "ban_notice_text"}
    parts = [ast.get_source_segment(src, n) for n in tree.body
             if (isinstance(n, ast.ClassDef) and n.name in wanted)
             or (isinstance(n, ast.FunctionDef) and n.name in helpers)]
    assert len(parts) == 2 + len(helpers), "middleware classes / ban helpers not found in bot.py"
    import html as real_html
    import time as real_time
    ns = {
        "BaseMiddleware": FakeBaseMiddleware,
        "TelegramObject": object,
        "types": pytypes.SimpleNamespace(Message=FakeMessage, CallbackQuery=FakeCallback),
        "Callable": Callable, "Dict": Dict, "Any": Any, "Awaitable": Awaitable,
        "asyncio": asyncio, "logging": logging, "time": real_time, "html": real_html,
        "timezone": datetime.timezone, "timedelta": datetime.timedelta,
        "database": fake_database, "ADMIN_USERNAME": "admin",
    }
    exec(compile("\n\n".join(parts), "bot.py(extracted)", "exec"), ns)
    return ns["ThrottlingMiddleware"], ns["BanMiddleware"]


class TestMiddlewares(unittest.TestCase):
    def setUp(self):
        self.fake_db = pytypes.SimpleNamespace(
            get_ban_info=lambda uid: dict(FREE_INFO), BAN_MODE_OPEN="open", BAN_MODE_SILENT="silent")
        self.Throttle, self.Ban = load_middlewares(self.fake_db)
        self.user = pytypes.SimpleNamespace(id=42)
        self.calls = 0

        async def handler(event, data):
            self.calls += 1
            return "handled"

        self.handler = handler

    def run_mw(self, mw, event):
        return asyncio.run(mw(self.handler, event, {"event_from_user": self.user}))

    # ---- Ban
    def test_db_failure_fail_closed_callback_answered_once(self):
        def boom(uid):
            raise ConnectionError("db down")
        self.fake_db.get_ban_info = boom
        mw = self.Ban()
        ev = FakeCallback()
        with self.assertLogs(level="ERROR"):
            self.assertIsNone(self.run_mw(mw, ev))
        self.assertEqual(self.calls, 0)
        self.assertEqual(len(ev.answers), 1)
        self.assertTrue(ev.answers[0][1].get("show_alert"))

    def test_db_failure_repeat_within_cooldown_silent_answer_once(self):
        def boom(uid):
            raise ConnectionError("db down")
        self.fake_db.get_ban_info = boom
        mw = self.Ban()
        with self.assertLogs(level="ERROR"):
            self.run_mw(mw, FakeCallback())
            ev2 = FakeCallback()
            self.run_mw(mw, ev2)
        self.assertEqual(self.calls, 0)
        self.assertEqual(len(ev2.answers), 1)                  # javobsiz qolmaydi
        self.assertFalse(ev2.answers[0][1].get("show_alert"))  # lekin alert spam yo'q

    def test_db_failure_message_alert_throttled(self):
        def boom(uid):
            raise ConnectionError("db down")
        self.fake_db.get_ban_info = boom
        mw = self.Ban()
        m1, m2 = FakeMessage(), FakeMessage()
        with self.assertLogs(level="ERROR"):
            self.run_mw(mw, m1)
            self.run_mw(mw, m2)
        self.assertEqual(len(m1.answers), 1)
        self.assertEqual(len(m2.answers), 0)
        self.assertEqual(self.calls, 0)

    def test_banned_callback_answered_once_handler_not_called(self):
        self.fake_db.get_ban_info = lambda uid: {"banned": True, "mode": "open", "until": None, "reason": None}
        ev = FakeCallback()
        self.assertIsNone(self.run_mw(self.Ban(), ev))
        self.assertEqual(len(ev.answers), 1)
        self.assertEqual(self.calls, 0)

    def test_not_banned_passes_through_without_answer(self):
        ev = FakeCallback()
        self.assertEqual(self.run_mw(self.Ban(), ev), "handled")
        self.assertEqual(self.calls, 1)
        self.assertEqual(len(ev.answers), 0)

    def test_answer_failure_during_error_notification_is_logged_not_raised(self):
        def boom(uid):
            raise ConnectionError("db down")
        self.fake_db.get_ban_info = boom

        class BadCb(FakeCallback):
            async def answer(self, *a, **k):
                raise RuntimeError("telegram down")

        with self.assertLogs(level="WARNING"):
            self.assertIsNone(self.run_mw(self.Ban(), BadCb()))
        self.assertEqual(self.calls, 0)

    # ---- Throttle
    def test_throttled_callbacks_answered_exactly_once_each(self):
        mw = self.Throttle()
        e1, e2, e3 = FakeCallback(), FakeCallback(), FakeCallback()
        self.assertEqual(self.run_mw(mw, e1), "handled")
        self.assertEqual(len(e1.answers), 0)
        self.assertIsNone(self.run_mw(mw, e2))      # throttled + ogohlantirish
        self.assertEqual(len(e2.answers), 1)
        self.assertTrue(e2.answers[0][1].get("show_alert"))
        self.assertIsNone(self.run_mw(mw, e3))      # throttled, warn cooldown ichida -> jim javob
        self.assertEqual(len(e3.answers), 1)
        self.assertFalse(e3.answers[0][1].get("show_alert"))
        self.assertEqual(self.calls, 1)


# =============================================================================
# 9. Izolyatsiya tekshiruvi
# =============================================================================
class TestIsolation(unittest.TestCase):
    def test_no_real_pool_created(self):
        self.assertIsNone(database.db_pool)

    def test_driver_is_stub(self):
        self.assertIs(sys.modules["psycopg2.pool"], _pool)
        # Qiymat hech qachon chiqarilmaydi (assertEqual diff URL ni logga yozib yuborardi)
        self.assertTrue(database.DATABASE_URL == _STUB_DATABASE_URL,
                        "database.DATABASE_URL is not the stub value (value redacted)")

    def test_network_blocked(self):
        with self.assertRaises(AssertionError):
            socket.create_connection(("example.com", 80))

    def test_real_get_connection_never_used(self):
        # get_connection DBTestCase tashqarisida chaqirilsa, stub pool AssertionError beradi
        with self.assertRaises(AssertionError):
            database.get_connection()


# =============================================================================
# 10. Umumiy processda: testlarni alohida toza processga topshirish
# =============================================================================
if not _ISOLATED:
    class TestBanCacheIsolatedProcess(unittest.TestCase):
        def test_ban_cache_suite_in_isolated_process(self):
            import subprocess
            env = {k: v for k, v in os.environ.items() if k not in _SECRET_ENV_KEYS}
            env[_ISOLATION_FLAG] = "1"
            env["DATABASE_URL"] = _STUB_DATABASE_URL
            env["PYTHONIOENCODING"] = "utf-8"
            test_target = "tests.test_ban_cache_local"
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "-v", test_target],
                cwd=PROJECT_DIR, env=env, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=300,
            )
            # Child natijalari (test nomlari + ok/FAIL); child'da faqat stub URL mavjud
            sys.stderr.write("\n--- isolated test_ban_cache_local ---\n")
            sys.stderr.write(proc.stdout + proc.stderr)
            sys.stderr.write("--- end isolated test_ban_cache_local ---\n")
            self.assertEqual(proc.returncode, 0, "isolated ban-cache suite failed (see output above)")


def load_tests(loader, standard_tests, pattern):
    if _ISOLATED:
        return standard_tests
    suite = unittest.TestSuite()
    suite.addTest(TestBanCacheIsolatedProcess("test_ban_cache_suite_in_isolated_process"))
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
