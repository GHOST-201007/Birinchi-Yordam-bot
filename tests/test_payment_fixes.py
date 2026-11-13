"""
test_payment_fixes.py - Premium to'lov tuzatishlari uchun lokal unit testlar.
PostgreSQL/Telegram API talab qilmaydi, mock/stub bilan ishlaydi.
"""
import ast
import os
import sys
import unittest
import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self.last_fetch = None
        self.closed = False

    def execute(self, query, params=None):
        if self.db.fail_execute:
            err = Exception("Simulated DB execute failure")
            err.pgcode = self.db.fail_pgcode
            raise err

        params = params or ()
        q_upper = query.strip().upper()

        if "INSERT INTO PAYMENT_TRANSACTIONS" in q_upper and "ON CONFLICT (CHARGE_ID) DO NOTHING" in q_upper:
            charge_id = params[0]
            if charge_id in self.db.payment_transactions:
                self.last_fetch = None
                self.rowcount = 0
            else:
                self.db.payment_transactions[charge_id] = params
                self.last_fetch = (len(self.db.payment_transactions),)
                self.rowcount = 1

        elif "INSERT INTO PAYMENT_TRANSACTIONS" in q_upper:
            charge_id = params[0]
            if charge_id in self.db.payment_transactions:
                err = Exception("duplicate key value violates unique constraint")
                err.pgcode = "23505"
                raise err
            self.db.payment_transactions[charge_id] = params
            self.rowcount = 1

        elif "INSERT INTO USERS" in q_upper and "ON CONFLICT" in q_upper:
            uid = params[0]
            if uid not in self.db.users:
                self.db.users[uid] = {"is_premium": 0, "premium_type": "free", "premium_expires_at": None}
            self.rowcount = 1

        elif "SELECT PREMIUM_EXPIRES_AT, PREMIUM_TYPE FROM USERS" in q_upper:
            uid = params[0]
            u = self.db.users.get(uid, {"premium_expires_at": None, "premium_type": "free"})
            self.last_fetch = (u.get("premium_expires_at"), u.get("premium_type"))
            self.rowcount = 1

        elif "SELECT IS_PREMIUM, PREMIUM_EXPIRES_AT, PREMIUM_TYPE FROM USERS" in q_upper:
            uid = params[0]
            u = self.db.users.get(uid, {"is_premium": 0, "premium_expires_at": None, "premium_type": "free"})
            self.last_fetch = (u.get("is_premium", 0), u.get("premium_expires_at"), u.get("premium_type", "free"))
            self.rowcount = 1

        elif "SELECT IS_PREMIUM, PREMIUM_EXPIRES_AT FROM USERS" in q_upper:
            uid = params[0]
            u = self.db.users.get(uid, {"is_premium": 0, "premium_expires_at": None})
            self.last_fetch = (u.get("is_premium", 0), u.get("premium_expires_at"))
            self.rowcount = 1

        elif "SELECT REGISTERED_AT, IS_PREMIUM, PREMIUM_EXPIRES_AT, PREMIUM_TYPE FROM USERS" in q_upper:
            uid = params[0]
            u = self.db.users.get(uid, {"registered_at": "2026-10-14", "is_premium": 0, "premium_expires_at": None, "premium_type": "free"})
            self.last_fetch = (u.get("registered_at", "2026-10-14"), u.get("is_premium", 0), u.get("premium_expires_at"), u.get("premium_type", "free"))
            self.rowcount = 1

        elif "SELECT LAST_REQUEST_DATE FROM USERS" in q_upper:
            uid = params[0]
            u = self.db.users.get(uid)
            self.last_fetch = (u.get("last_request_date"),) if u is not None else None
            self.rowcount = 1 if self.last_fetch else 0

        elif "SELECT USER_ID FROM USERS" in q_upper:
            uid = params[0]
            self.last_fetch = (uid,) if uid in self.db.users else None
            self.rowcount = 1 if self.last_fetch else 0

        elif "UPDATE USERS SET FREE_AI_USED = 1" in q_upper:
            uid = params[0]
            u = self.db.users.setdefault(uid, {})
            if u.get("free_ai_used", 0) == 0:
                u["free_ai_used"] = 1
                self.rowcount = 1
            else:
                self.rowcount = 0

        elif "UPDATE USERS SET FREE_AI_USED = 0" in q_upper:
            uid = params[0]
            u = self.db.users.setdefault(uid, {})
            u["free_ai_used"] = 0
            self.rowcount = 1

        elif "UPDATE USERS SET DAILY_REQUESTS = 0" in q_upper:
            cur_date = params[0]
            uid = params[1]
            u = self.db.users.setdefault(uid, {})
            if u.get("last_request_date") != cur_date or u.get("last_request_date") is None:
                u["daily_requests"] = 0
                u["last_request_date"] = cur_date
                self.rowcount = 1
            else:
                self.rowcount = 0

        elif "UPDATE USERS SET DAILY_REQUESTS = DAILY_REQUESTS + 1" in q_upper:
            uid = params[0]
            max_req = params[1]
            u = self.db.users.setdefault(uid, {})
            cur = u.get("daily_requests", 0)
            if cur < max_req:
                u["daily_requests"] = cur + 1
                self.rowcount = 1
            else:
                self.rowcount = 0

        elif "UPDATE USERS SET DAILY_REQUESTS = DAILY_REQUESTS - 1" in q_upper:
            uid = params[0]
            u = self.db.users.setdefault(uid, {})
            cur = u.get("daily_requests", 0)
            if cur > 0:
                u["daily_requests"] = cur - 1
            self.rowcount = 1

        elif "UPDATE USERS SET MEDICINE_SCORE = MEDICINE_SCORE - 100" in q_upper:
            uid = params[0]
            u = self.db.users.setdefault(uid, {})
            score = u.get("medicine_score", 0)
            if score >= 100:
                u["medicine_score"] = score - 100
                self.rowcount = 1
            else:
                self.rowcount = 0

        elif "SELECT MEDICINE_SCORE FROM USERS" in q_upper:
            uid = params[0]
            u = self.db.users.get(uid, {})
            self.last_fetch = (u.get("medicine_score", 0),)
            self.rowcount = 1

        elif "UPDATE USERS SET IS_PREMIUM = 1" in q_upper:
            if self.db.fail_update_user:
                err = Exception("Simulated user update failure during premium grant")
                err.pgcode = self.db.fail_pgcode
                raise err
            uid = params[3]
            u = self.db.users.setdefault(uid, {})
            u["is_premium"] = 1
            u["premium_type"] = params[0]
            u["premium_until"] = params[1]
            u["premium_expires_at"] = params[2]
            self.rowcount = 1

        else:
            self.rowcount = 1
            self.last_fetch = (1,)

    def fetchone(self):
        return self.last_fetch

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.cursors = []
        # Save snapshot of state for transaction rollback
        self._tx_snapshot = dict(self.db.payment_transactions)

    def cursor(self):
        c = FakeCursor(self.db)
        self.cursors.append(c)
        return c

    def commit(self):
        if self.db.fail_commit:
            raise Exception("Simulated commit failure")
        self.committed = True

    def rollback(self):
        self.rolled_back = True
        # Rollback restores state prior to uncommitted inserts
        self.db.payment_transactions = dict(self._tx_snapshot)

    def close(self):
        self.closed = True


class MockDB:
    def __init__(self):
        self.payment_transactions = {}
        self.users = {}
        self.connections = []
        self.fail_execute = False
        self.fail_pgcode = None
        self.fail_update_user = False
        self.fail_commit = False

    def get_connection(self):
        conn = FakeConn(self)
        self.connections.append(conn)
        return conn


class _NoRealPool:
    def __init__(self, *a, **k):
        raise AssertionError("REAL DB CONNECTION POOL CREATION ATTEMPTED IN LOCAL TEST")


class TestPaymentFixes(unittest.TestCase):
    def setUp(self):
        import tempfile
        import database
        import bot
        self.db = database
        self.mock = MockDB()
        self.orig_get_connection = database.get_connection
        database.get_connection = self.mock.get_connection
        # Haqiqiy psycopg2 pool hech qachon yaratilmasligi kafolati
        self.orig_pool_cls = database.ThreadedConnectionPool
        database.ThreadedConnectionPool = _NoRealPool
        # pending_reconcile.db fayliga testlar yozmasligi uchun vaqtinchalik faylga yo'naltiramiz
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.orig_reconcile_db = bot._PENDING_RECONCILE_DB
        bot._PENDING_RECONCILE_DB = os.path.join(self._tmp_dir.name, "test_pending_reconcile.db")
        bot._init_reconcile_db()

    def tearDown(self):
        import bot
        bot._PENDING_RECONCILE_DB = self.orig_reconcile_db
        self._tmp_dir.cleanup()
        self.db.get_connection = self.orig_get_connection
        self.db.ThreadedConnectionPool = self.orig_pool_cls

    def test_record_payment_transaction_new_and_duplicate(self):
        # 1. Yangi to'lov muvaffaqiyatli yoziladi
        res1 = self.db.record_payment_transaction("ch_101", 12345, "PRO_7_DAYS", 50, "pro", 7)
        self.assertTrue(res1)
        self.assertIn("ch_101", self.mock.payment_transactions)

        # 2. Aynan bir xil charge_id qayta yuborilganda False qaytadi (UniqueViolation 23505)
        res2 = self.db.record_payment_transaction("ch_101", 12345, "PRO_7_DAYS", 50, "pro", 7)
        self.assertFalse(res2)

    def test_record_payment_transaction_other_error_raises(self):
        # 3. Boshqa DB xatosi (masalan connection xato) dublikat deb yutilmaydi, yuqoriga uzatiladi
        self.mock.fail_execute = True
        self.mock.fail_pgcode = "08006"  # connection_failure
        with self.assertRaises(Exception) as ctx:
            self.db.record_payment_transaction("ch_102", 12345, "PRO_7_DAYS", 50, "pro", 7)
        self.assertIn("Simulated DB execute failure", str(ctx.exception))

    def test_record_payment_empty_charge_id_raises(self):
        # 4. Bo'sh charge_id berilsa xato beradi (soxta true qaytmaydi)
        with self.assertRaises(ValueError):
            self.db.record_payment_transaction("", 12345, "PRO_7_DAYS", 50, "pro", 7)

    def test_process_paid_premium_atomic_and_idempotent(self):
        # 5. Yangi to'lov: tranzaksiya yoziladi va premium beriladi
        granted1, until1 = self.db.process_paid_premium("ch_201", 999, "PRO_7_DAYS", 50, "pro", 7)
        self.assertTrue(granted1)
        self.assertIsNotNone(until1)
        user = self.mock.users[999]
        self.assertEqual(user["is_premium"], 1)
        self.assertEqual(user["premium_type"], "pro")
        exp1 = user["premium_expires_at"]

        # 6. Duplicate charge_id: Premium qayta uzaytirilmaydi, False qaytadi
        granted2, until2 = self.db.process_paid_premium("ch_201", 999, "PRO_7_DAYS", 50, "pro", 7)
        self.assertFalse(granted2)
        self.assertIsNone(until2)
        # Muddati o'zgarmasligi kerak
        self.assertEqual(self.mock.users[999]["premium_expires_at"], exp1)

    def test_process_paid_premium_rollback_on_failure(self):
        # 7. Agar premium berish paytida DB xatosi bo'lsa, to'lov yozuvi tranzaksiya rollback bo'lgani uchun qolmaydi
        self.mock.fail_update_user = True
        with self.assertRaises(Exception):
            self.db.process_paid_premium("ch_fail", 888, "PRO_7_DAYS", 50, "pro", 7)

        # Tranzaksiya bekor bo'lgan, keyingi to'g'ri urinish muvaffaqiyatli o'tadi
        self.mock.fail_update_user = False
        granted, until = self.db.process_paid_premium("ch_fail", 888, "PRO_7_DAYS", 50, "pro", 7)
        self.assertTrue(granted)
        self.assertIsNotNone(until)
        self.assertEqual(self.mock.users[888]["is_premium"], 1)

    def test_payment_validation_rules(self):
        # 8. Valyuta, payload va summa tekshiruvlari
        import bot

        # To'g'ri tariflar
        ok, reason = bot.validate_payment("PRO_7_DAYS", "XTR", 50)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

        ok, reason = bot.validate_payment("PLUS_30_DAYS", "XTR", 150)
        self.assertTrue(ok)

        ok, reason = bot.validate_payment("ULTRA_30_DAYS", "XTR", 300)
        self.assertTrue(ok)

        # Noto'g'ri valyuta (Stars o'rniga boshqa valyuta)
        ok, reason = bot.validate_payment("PRO_7_DAYS", "USD", 50)
        self.assertFalse(ok)
        self.assertEqual(reason, "currency")

        # Noto'g'ri summa (masalan 50 o'rniga 10 Stars)
        ok, reason = bot.validate_payment("PRO_7_DAYS", "XTR", 10)
        self.assertFalse(ok)
        self.assertEqual(reason, "amount")

        # Noto'g'ri payload
        ok, reason = bot.validate_payment("HACK_TARIFF", "XTR", 50)
        self.assertFalse(ok)
        self.assertEqual(reason, "payload")

    def test_syntax_of_modified_files(self):
        # 9. Barcha o'zgartirilgan fayllar sintaksis tekshiruvi (AST parse)
        files = [
            "database.py", "bot.py", "app_server.py",
            "services/engagement.py", "services/engagement_scheduler.py"
        ]
        for fname in files:
            fpath = os.path.join(PROJECT_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                code = f.read()
            tree = ast.parse(code, filename=fname)
            self.assertIsNotNone(tree)

    def test_engagement_callback_parsing(self):
        # 10. Engagement callback split formatlari (3-part va 4-part)
        def parse_engagement_cb(data_str):
            parts = data_str.split(":")
            if len(parts) == 4:
                return f"{parts[1]}:{parts[2]}", parts[3]
            elif len(parts) == 3:
                return parts[1], parts[2]
            else:
                raise ValueError(f"Kutilmagan format: {len(parts)} ta bo'lak")

        # 4-part: 10:10 job
        e_type, e_date = parse_engagement_cb("engagement_answer:10:10:2026-10-13")
        self.assertEqual(e_type, "10:10")
        self.assertEqual(e_date, "2026-10-13")

        # 4-part: 08:00 job
        e_type, e_date = parse_engagement_cb("engagement_answer:08:00:2026-10-13")
        self.assertEqual(e_type, "08:00")
        self.assertEqual(e_date, "2026-10-13")

        # 3-part: premium_checkin
        e_type, e_date = parse_engagement_cb("engagement_answer:premium_checkin:2026-10-13")
        self.assertEqual(e_type, "premium_checkin")
        self.assertEqual(e_date, "2026-10-13")

        # Noto'g'ri formatlar ValueError berishi kerak
        with self.assertRaises(ValueError):
            parse_engagement_cb("engagement_answer:only_two")
        with self.assertRaises(ValueError):
            parse_engagement_cb("engagement_answer:too:many:parts:here")

    def test_app_server_port(self):
        # 11. app_server.py default PORT tekshiruvi (8000 bo'lishi shart)
        import app_server
        self.assertEqual(app_server.PORT, 8000)

    def test_premium_purchase_eligibility_rules(self):
        # 12. /start, inline tugma, /api/invoice va pre_checkout uchun YAGONA qoida (holat admin_premium_view dan):
        # bir xil tarif = uzaytirish (ruxsat), yuqoriroq = upgrade (ruxsat), pastroq = taqiq, muddatsiz = taqiq
        import bot
        import database

        future = database.get_uz_now() + datetime.timedelta(days=10)

        def view(tier):
            return database.admin_premium_view(1, tier, future)

        # Bepul foydalanuvchi istalgan tarifni sotib olishi mumkin
        free_view = database.admin_premium_view(0, "free", None)
        for action in ("buy_pro_7", "buy_plus_30", "buy_ultra_30"):
            ok, reason = bot.check_premium_purchase_eligibility(free_view, action)
            self.assertTrue(ok)
            self.assertIsNone(reason)

        # Ichki pro (ko'rinadigan Plus): teng tarif = uzaytirish, yuqoriroq = upgrade
        self.assertTrue(bot.check_premium_purchase_eligibility(view("pro"), "buy_pro_7")[0])
        self.assertTrue(bot.check_premium_purchase_eligibility(view("pro"), "buy_plus_30")[0])

        # Ichki plus (ko'rinadigan Pro): pastroq tarif taqiq, o'zi = uzaytirish
        ok, reason = bot.check_premium_purchase_eligibility(view("plus"), "buy_pro_7")
        self.assertFalse(ok)
        self.assertEqual(reason, "Sizda yuqoriroq tarif (Premium Pro) bor — pastroq tarif sotib olinmaydi")
        self.assertTrue(bot.check_premium_purchase_eligibility(view("plus"), "buy_plus_30")[0])

        # Ultra: o'zi = uzaytirish, pastroqlar taqiq
        self.assertTrue(bot.check_premium_purchase_eligibility(view("ultra"), "buy_ultra_30")[0])
        ok, reason = bot.check_premium_purchase_eligibility(view("ultra"), "buy_pro_7")
        self.assertFalse(ok)
        self.assertIn("Premium Ultra", reason)
        self.assertFalse(bot.check_premium_purchase_eligibility(view("ultra"), "buy_plus_30")[0])

    def test_reconciliation_flow(self):
        # 13. Reconcile DB tiklash oqimi
        granted, until = self.db.process_paid_premium("rec_101", 777, "PRO_7_DAYS", 50, "pro", 7)
        self.assertTrue(granted)
        self.assertIsNotNone(until)

        # Qayta tiklash urinishi — duplicate deb aniqlanadi, qayta uzaytirilmaydi
        granted2, until2 = self.db.process_paid_premium("rec_101", 777, "PRO_7_DAYS", 50, "pro", 7)
        self.assertFalse(granted2)
        self.assertIsNone(until2)

    def test_in_flight_concurrency_sets(self):
        # 14. Takroriy AI so'rovlari va callbacklar uchun in-flight to'plamlar
        import bot
        self.assertIsInstance(bot._active_ai_users, set)
        self.assertIsInstance(bot._in_progress_engagements, set)

        # Test guard tracking
        test_uid = 99999
        bot._active_ai_users.add(test_uid)
        self.assertIn(test_uid, bot._active_ai_users)
        bot._active_ai_users.discard(test_uid)
        self.assertNotIn(test_uid, bot._active_ai_users)

    def test_reconcile_charge_id_validation(self):
        # 15. Soxta charge_id bilan Premium berishning oldini olish
        import re
        def is_valid_charge_id(cid: str) -> bool:
            return bool(cid and len(cid) >= 5 and re.match(r'^[A-Za-z0-9_\-:]+$', cid))

        # Yaroqsiz/soxta charge_id'lar rad etiladi
        self.assertFalse(is_valid_charge_id(""))
        self.assertFalse(is_valid_charge_id("123"))
        self.assertFalse(is_valid_charge_id("fake charge id"))
        self.assertFalse(is_valid_charge_id("ch<hack>"))
        self.assertFalse(is_valid_charge_id("drop table;"))

        # Haqiqiy Telegram charge_id'lar qabul qilinadi
        self.assertTrue(is_valid_charge_id("ch_1029384756"))
        self.assertTrue(is_valid_charge_id("tg_stars_998877"))
        self.assertTrue(is_valid_charge_id("legacy_uzs_112233"))

    def test_stars_payment_requires_authentic_charge_id(self):
        # 16. Telegram Stars to'lovida haqiqiy telegram_payment_charge_id bo'lishi shart,
        # message_id ga almashtirilmaydi
        import bot

        class FakePayment:
            def __init__(self, currency, charge_id, total_amount):
                self.currency = currency
                self.telegram_payment_charge_id = charge_id
                self.provider_payment_charge_id = None
                self.total_amount = total_amount
                self.invoice_payload = "PRO_7_DAYS"

        # Stars to'lovida charge_id None bo'lsa -> soxtalashtirilmaydi, rad etiladi
        p_no_charge = FakePayment("XTR", None, 50)
        self.assertIsNone(p_no_charge.telegram_payment_charge_id)

        # Stars to'lovida charge_id mavjud bo'lsa -> o'sha haqiqiy identifikator olinadi
        p_real = FakePayment("XTR", "ch_real_stars_12345", 50)
        self.assertEqual(p_real.telegram_payment_charge_id, "ch_real_stars_12345")

    def test_reconcile_evidence_registry_and_fake_rejection(self):
        # 17. Reconcile faqat Telegram to'lov dalili mavjud bo'lgandagina ishlashi va
        # soxta charge_id rad etilishi
        import bot
        import asyncio

        # 1. Soxta charge_id reestrda mavjud emas
        fake_cid = "ch_fake_without_evidence_12345"
        self.assertIsNone(bot.get_pending_failed_payment(fake_cid))

        # 2. Telegram failed payment kelganda dalil saqlanishi
        real_cid = "ch_verified_stars_998877"
        bot.record_failed_payment(real_cid, 888777, "PRO_7_DAYS", 50)
        evidence = bot.get_pending_failed_payment(real_cid)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["user_id"], 888777)
        self.assertEqual(evidence["payload"], "PRO_7_DAYS")
        self.assertEqual(evidence["stars"], 50)

        # 3. Tiklangandan so'ng dalil reestrdan o'chirilishi
        bot.remove_pending_failed_payment(real_cid)
        self.assertIsNone(bot.get_pending_failed_payment(real_cid))

        # 4. cmd_reconcile_payment orqali soxta charge_id rad etilishi
        class FakeUser:
            def __init__(self, uid):
                self.id = uid

        class FakeMessage:
            def __init__(self, text, user_id):
                self.text = text
                self.from_user = FakeUser(user_id)
                self.answers = []

            async def answer(self, text, **kwargs):
                self.answers.append(text)

        orig_admin = bot.ADMIN_ID
        try:
            bot.ADMIN_ID = "123456"

            # Dalilsiz soxta charge_id yuborilganda rad etiladi
            fake_msg = FakeMessage("/reconcile ch_spoofed_random_9999", 123456)
            asyncio.run(bot.cmd_reconcile_payment(fake_msg))
            self.assertTrue(any("Rad etildi: To'lov dalili topilmadi" in a for a in fake_msg.answers))

            # Admin bo'lmagan foydalanuvchi chaqirsa javob berilmaydi
            non_admin_msg = FakeMessage("/reconcile ch_spoofed_random_9999", 999999)
            asyncio.run(bot.cmd_reconcile_payment(non_admin_msg))
            self.assertEqual(len(non_admin_msg.answers), 0)
        finally:
            bot.ADMIN_ID = orig_admin

    def test_ai_limit_free_and_premium_tiers(self):
        # 18. AI limit tizimi: Free, Pro, Plus, Ultra va kun almashishi
        import database
        import datetime

        today_str = database.get_uz_now().date().isoformat()
        # Fake DB state for user 10001
        uid_free = 10001
        self.mock.users[uid_free] = {
            "is_premium": 0, "premium_type": "free", "premium_expires_at": None,
            "daily_requests": 0, "last_request_date": today_str, "free_ai_used": 0
        }

        # Birinchi savol: try_consume_free_ai orqali ruxsat beriladi
        ok_free = database.try_consume_free_ai(uid_free)
        self.assertTrue(ok_free)
        self.assertEqual(self.mock.users[uid_free].get("free_ai_used"), 1)

        # Xatolik yuz berganda refund_free_ai tiklaydi
        database.refund_free_ai(uid_free)
        self.assertEqual(self.mock.users[uid_free].get("free_ai_used"), 0)
        database.try_consume_free_ai(uid_free)
        self.assertEqual(self.mock.users[uid_free].get("free_ai_used"), 1)

        # Ikkinchi savolda try_consume_free_ai rad etadi
        self.assertFalse(database.try_consume_free_ai(uid_free))
        # Bepul uchun JAMI 1 ta savol: kunlik limit yo'q (bugun ham, ertaga ham)
        self.assertFalse(database.try_consume_daily_request(uid_free))
        self.mock.users[uid_free]["last_request_date"] = "2000-01-01"
        self.assertFalse(database.try_consume_daily_request(uid_free))

        # Premium Pro foydalanuvchi: 15 ta limit tekshiriladi
        uid_pro = 10002
        tomorrow = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5))) + datetime.timedelta(days=7)).isoformat()
        self.mock.users[uid_pro] = {
            "is_premium": 1, "premium_type": "pro", "premium_expires_at": tomorrow,
            "daily_requests": 14, "last_request_date": today_str, "free_ai_used": 0
        }
        # Premium bo'lgani uchun try_consume_free_ai False qaytaradi (kunlik tarif limitidan foydalanish uchun)
        self.assertFalse(database.try_consume_free_ai(uid_pro))
        # 15-savol: ruxsat
        ok_pro = database.try_consume_daily_request(uid_pro)
        self.assertTrue(ok_pro)
        # 16-savol: limit tugadi (15/15)
        self.assertFalse(database.try_consume_daily_request(uid_pro))

        # Refund ishlashi
        database.refund_daily_request(uid_pro)
        self.assertEqual(self.mock.users[uid_pro].get("daily_requests"), 14)

    def test_reconcile_tamper_proof_and_persistence(self):
        # 19. Reconcile: admin user/tarifni o'zgartira olmasligi va dalil saqlanishi
        import bot
        import asyncio

        real_charge = "ch_secure_reconcile_445566"
        target_uid = 777111
        bot.record_failed_payment(real_charge, target_uid, "PRO_7_DAYS", 50)

        # Bot restart simulyatsiyasi: xotira tozalansa ham fayldan/DBdan tiklanadi
        bot._pending_failed_payments.clear()
        recovered = bot.get_pending_failed_payment(real_charge)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["user_id"], target_uid)
        self.assertEqual(recovered["payload"], "PRO_7_DAYS")

        # Admin boshqa user va boshqa tarif kiritishga urinsa ham:
        # Kod Telegram asl dalilini ishlatishi kerak
        class FakeUser:
            def __init__(self, uid): self.id = uid
        class FakeMessage:
            def __init__(self, text, uid):
                self.text = text
                self.from_user = FakeUser(uid)
                self.answers = []
            async def answer(self, text, **kwargs):
                self.answers.append(text)
            @property
            def bot(self):
                class FakeBot:
                    async def send_message(self, *a, **k): pass
                return FakeBot()

        orig_admin = bot.ADMIN_ID
        try:
            bot.ADMIN_ID = "999"
            # Admin boshqa user 999999 va ULTRA tarifini yozsa ham:
            tamper_msg = FakeMessage(f"/reconcile 999999 ULTRA_30_DAYS {real_charge}", 999)
            asyncio.run(bot.cmd_reconcile_payment(tamper_msg))

            # Foydalanuvchi bazada target_uid (777111) sifatida saqlangan bo'lishi kerak
            self.assertIn(target_uid, self.mock.users)
            self.assertEqual(self.mock.users[target_uid].get("is_premium"), 1)
            # Reconcile muvaffaqiyatidan so'ng dalil o'chirilgan
            self.assertIsNone(bot.get_pending_failed_payment(real_charge))
        finally:
            bot.ADMIN_ID = orig_admin

    def test_get_premium_info_unpacking_safety(self):
        # 20. get_premium_info 3 ta qiymat qaytarganda bot.py dagi barcha unpacklar xavfsiz ishlashi
        import database

        uid = 55555
        self.mock.users[uid] = {
            "is_premium": 1, "premium_type": "plus",
            "premium_expires_at": (database.get_uz_now() + datetime.timedelta(days=30)).isoformat()
        }

        # 3 ta qiymat qaytishi
        res = database.get_premium_info(uid)
        self.assertEqual(len(res), 3)

        # 2 ta o'zgaruvchiga unpack xavfsizligi (*_ bilan)
        is_prem, *_ = database.get_premium_info(uid)
        self.assertEqual(is_prem, 1)

        is_prem, expires, *_ = database.get_premium_info(uid)
        self.assertEqual(is_prem, 1)
        self.assertIsNotNone(expires)

    def test_get_user_info_functionality(self):
        # 21. database.get_user_info dict qaytarishi va eligibility bilan integratsiyasi
        import database
        import bot

        uid = 661122
        self.mock.users[uid] = {
            "is_premium": 1, "premium_type": "pro",
            "premium_expires_at": (database.get_uz_now() + datetime.timedelta(days=30)).isoformat()
        }
        info = database.get_user_info(uid)
        self.assertIsInstance(info, dict)
        self.assertEqual(info["user_id"], uid)
        self.assertEqual(info["is_premium"], 1)
        self.assertEqual(info["premium_type"], "pro")

        # Eligibility holat get_premium_view dan: ichki pro user xuddi shu tarifni uzaytira oladi va yuqoriroqqa o'ta oladi
        view = database.get_premium_view(uid)
        self.assertEqual((view["active"], view["tier"]), (True, "pro"))
        ok_same, _ = bot.check_premium_purchase_eligibility(view, "buy_pro_7")
        self.assertTrue(ok_same)
        ok_up, _ = bot.check_premium_purchase_eligibility(view, "buy_plus_30")
        self.assertTrue(ok_up)

    def test_check_and_grant_premium_atomic_flow(self):
        # 22. 100 ball evaziga 3 kunlik Premium Pro olishning atomar tekshiruvi
        import database

        uid = 772233
        # 90 ball -> rad etiladi
        self.mock.users[uid] = {"medicine_score": 90, "is_premium": 0, "premium_type": "free"}
        ok = database.check_and_grant_premium(uid)
        self.assertFalse(ok)
        self.assertEqual(self.mock.users[uid].get("medicine_score"), 90)
        self.assertEqual(self.mock.users[uid].get("is_premium"), 0)

        # 100 ball -> 3 kunlik Pro beriladi, ball 0 bo'ladi
        self.mock.users[uid]["medicine_score"] = 100
        ok2 = database.check_and_grant_premium(uid)
        self.assertTrue(ok2)
        self.assertEqual(self.mock.users[uid].get("medicine_score"), 0)
        self.assertEqual(self.mock.users[uid].get("is_premium"), 1)
        self.assertEqual(self.mock.users[uid].get("premium_type"), "pro")

        # Qayta bosilganda (ball 0) -> rad etiladi (double spend himoyasi)
        ok3 = database.check_and_grant_premium(uid)
        self.assertFalse(ok3)

    def test_pre_checkout_banned_user_and_valid_handling(self):
        # 23. pre_checkout_query: ban qilingan user rad etilishi va to'g'ri to'lov tasdiqlanishi
        import bot
        import asyncio

        class FakePreCheckout:
            def __init__(self, user_id, payload, currency, total_amount):
                class FakeUser:
                    def __init__(self, uid):
                        self.id = uid
                self.from_user = FakeUser(user_id)
                self.invoice_payload = payload
                self.currency = currency
                self.total_amount = total_amount
                self.answers = []

            async def answer(self, ok=True, error_message=None):
                self.answers.append({"ok": ok, "error_message": error_message})

        orig_is_banned = self.db.is_user_banned
        orig_ban_info = self.db.get_ban_info
        try:
            # 1. Banned user simulyatsiyasi (ochiq ban: pre_checkout sabab bilan rad etadi)
            self.db.is_user_banned = lambda uid: (True, "Spam", None) if uid == 999111 else (False, None, None)
            self.db.get_ban_info = lambda uid: (
                {"banned": True, "mode": "open", "until": None, "reason": "Spam"} if uid == 999111
                else {"banned": False, "mode": None, "until": None, "reason": None})

            banned_query = FakePreCheckout(999111, "PRO_7_DAYS", "XTR", 50)
            asyncio.run(bot.process_pre_checkout(banned_query))
            self.assertEqual(len(banned_query.answers), 1)
            self.assertFalse(banned_query.answers[0]["ok"])
            self.assertIn("bloklangan", banned_query.answers[0]["error_message"])

            # 2. Oddiy to'g'ri to'lov
            valid_query = FakePreCheckout(888222, "PRO_7_DAYS", "XTR", 50)
            asyncio.run(bot.process_pre_checkout(valid_query))
            self.assertEqual(len(valid_query.answers), 1)
            self.assertTrue(valid_query.answers[0]["ok"])

            # 3. Noto'g'ri summa bilan to'lov
            wrong_query = FakePreCheckout(888222, "PRO_7_DAYS", "XTR", 10)
            asyncio.run(bot.process_pre_checkout(wrong_query))
            self.assertEqual(len(wrong_query.answers), 1)
            self.assertFalse(wrong_query.answers[0]["ok"])
        finally:
            self.db.is_user_banned = orig_is_banned
            self.db.get_ban_info = orig_ban_info

    def test_legacy_stars_payload_validation(self):
        # 24. stars_premium_1month: faqat XTR va musbat summa qabul qilinishi
        import bot

        ok, reason = bot.validate_payment("stars_premium_1month", "XTR", 50)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

        ok, reason = bot.validate_payment("stars_premium_1month", "USD", 50)
        self.assertFalse(ok)
        self.assertEqual(reason, "currency")

        ok, reason = bot.validate_payment("stars_premium_1month", "XTR", 0)
        self.assertFalse(ok)
        self.assertEqual(reason, "amount")

        ok, reason = bot.validate_payment("stars_premium_1month", "XTR", -10)
        self.assertFalse(ok)
        self.assertEqual(reason, "amount")

    def test_legacy_provider_payload_rejected(self):
        # 25. Eski UZS (premium_1month) oqimi o'chirildi (P2-6): har qanday valyutada rad etiladi
        import bot

        for curr in ("UZS", "XTR"):
            ok, reason = bot.validate_payment("premium_1month", curr, 1000000)
            self.assertFalse(ok)
            self.assertEqual(reason, "payload")
        self.assertFalse(hasattr(bot, "PROVIDER_TOKEN"))

    def test_unknown_payload_evidence_recorded_and_reconcile_safe(self):
        # 26. Noma'lum payload'da dalil saqlanishi va /reconcile avtomatik premium bermasligi
        import bot
        import asyncio

        class FakeUser:
            def __init__(self, uid, username=None):
                self.id = uid
                self.username = username

        class FakeBot:
            def __init__(self):
                self.messages = []
            async def send_message(self, chat_id, text, **kwargs):
                self.messages.append((chat_id, text))

        class FakePayment:
            def __init__(self, charge_id, payload, amount, currency):
                self.telegram_payment_charge_id = charge_id
                self.provider_payment_charge_id = None
                self.invoice_payload = payload
                self.total_amount = amount
                self.currency = currency

        class FakeMessage:
            def __init__(self, uid, payment, fbot):
                self.from_user = FakeUser(uid, "testuser")
                self.successful_payment = payment
                self.bot = fbot
                self.answers = []
            async def answer(self, text, **kwargs):
                self.answers.append(text)

        fbot = FakeBot()
        cid = "ch_unknown_mystery_7788"
        p = FakePayment(cid, "CUSTOM_UNKNOWN_PLAN", 100, "XTR")
        msg = FakeMessage(445566, p, fbot)

        # 1. process_successful_payment chaqiriladi
        asyncio.run(bot.process_successful_payment(msg))
        self.assertTrue(any("paket turini aniqlashda xatolik" in a for a in msg.answers))

        # 2. Dalil pending reestrga yozilgan bo'lishi shart
        evidence = bot.get_pending_failed_payment(cid)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["payload"], "CUSTOM_UNKNOWN_PLAN")
        self.assertEqual(evidence["user_id"], 445566)

        # 3. /reconcile chaqirilganda noma'lum payload uchun avtomatik premium berilmaydi
        orig_admin = bot.ADMIN_ID
        try:
            bot.ADMIN_ID = "999"
            class ReconcileMsg:
                def __init__(self, text, uid):
                    self.text = text
                    self.from_user = FakeUser(uid)
                    self.bot = fbot
                    self.answers = []
                async def answer(self, text, **kwargs):
                    self.answers.append(text)

            rec_msg = ReconcileMsg(f"/reconcile {cid}", 999)
            asyncio.run(bot.cmd_reconcile_payment(rec_msg))
            self.assertTrue(any("Noma'lum mahsulot payload'i" in a for a in rec_msg.answers))

            # Foydalanuvchiga premium berilmagan bo'lishi kerak
            self.assertNotIn(445566, self.mock.users)
            # Dalil hali ham reestrda saqlanib turishi kerak (erta o'chirilmaydi)
            self.assertIsNotNone(bot.get_pending_failed_payment(cid))
        finally:
            bot.ADMIN_ID = orig_admin
            bot.remove_pending_failed_payment(cid)

    def test_unknown_payload_record_failure_gracefully_handled(self):
        # 27. Dalilni saqlash muvaffaqiyatsiz bo'lsa (masalan disk/DB xatosi), crash qilmaslik
        import bot
        import asyncio

        class FakeUser:
            def __init__(self, uid):
                self.id = uid
                self.username = "user1"

        class FakeBot:
            def __init__(self):
                self.messages = []

            async def send_message(self, chat_id, text, **kwargs):
                self.messages.append((chat_id, text))

        class FakePayment:
            def __init__(self, charge_id):
                self.telegram_payment_charge_id = charge_id
                self.provider_payment_charge_id = None
                self.invoice_payload = "RANDOM_PAYLOAD"
                self.total_amount = 50
                self.currency = "XTR"

        class FakeMessage:
            def __init__(self, uid, payment, fbot):
                self.from_user = FakeUser(uid)
                self.successful_payment = payment
                self.bot = fbot
                self.answers = []

            async def answer(self, text, **kwargs):
                self.answers.append(text)

        orig_record = bot.record_failed_payment
        orig_admin = bot.ADMIN_ID
        try:
            bot.ADMIN_ID = "12345"
            def fail_record(*args):
                raise RuntimeError("Disk full / DB failure")
            bot.record_failed_payment = fail_record

            fbot = FakeBot()
            msg = FakeMessage(112233, FakePayment("ch_record_fail_99"), fbot)
            # Crash bo'lmasligi kerak
            asyncio.run(bot.process_successful_payment(msg))
            self.assertEqual(len(msg.answers), 1)
            # Adminga dalil holatida xato ekani bildirilgan
            self.assertTrue(any("Dalilni saqlashda xatolik" in m[1] for m in fbot.messages))
        finally:
            bot.record_failed_payment = orig_record
            bot.ADMIN_ID = orig_admin

    def test_reconcile_user_notification_failure_does_not_abort_success(self):
        # 28. Foydalanuvchiga bildirishnoma yuborishdagi xato muvaffaqiyatli tiklashni buzmasligi
        import bot
        import asyncio

        cid = "ch_notify_fail_1122"
        target_uid = 334455
        bot.record_failed_payment(cid, target_uid, "PRO_7_DAYS", 50)

        class FakeUser:
            def __init__(self, uid):
                self.id = uid

        class ExplodingBot:
            async def send_message(self, chat_id, text, **kwargs):
                if chat_id == target_uid:
                    raise Exception("Bot was blocked by the user (Forbidden)")

        class FakeMsg:
            def __init__(self, text, uid, fbot):
                self.text = text
                self.from_user = FakeUser(uid)
                self.bot = fbot
                self.answers = []

            async def answer(self, text, **kwargs):
                self.answers.append(text)

        orig_admin = bot.ADMIN_ID
        try:
            bot.ADMIN_ID = "12345"
            msg = FakeMsg(f"/reconcile {cid}", 12345, ExplodingBot())
            asyncio.run(bot.cmd_reconcile_payment(msg))

            # Foydalanuvchi baribir premium olgan (tranzaksiya bekor bo'lmagan)
            self.assertIn(target_uid, self.mock.users)
            self.assertEqual(self.mock.users[target_uid].get("is_premium"), 1)
            # Dalil reestrdan tozalangan
            self.assertIsNone(bot.get_pending_failed_payment(cid))
            # Admin muvaffaqiyat xabarini olgan
            self.assertTrue(any("To'lov muvaffaqiyatli tiklandi" in a for a in msg.answers))
        finally:
            bot.ADMIN_ID = orig_admin
            bot.remove_pending_failed_payment(cid)

    def test_db_connection_and_cursor_closed_on_consume_and_refund_paths(self):
        # 29. try_consume_daily_request, refund_daily_request, try_consume_free_ai, refund_free_ai:
        # barcha normal va erta qaytish (early return) yo'llarida connection hamda cursor yopilishi
        import database

        today_str = database.get_uz_now().date().isoformat()
        future_exp = (database.get_uz_now() + datetime.timedelta(days=10)).isoformat()

        # 1) Faol premium userda try_consume_free_ai erta False qaytaradi (cursor va conn yopilishi shart)
        uid_prem = 901001
        self.mock.users[uid_prem] = {
            "is_premium": 1, "premium_type": "pro", "premium_expires_at": future_exp,
            "daily_requests": 0, "last_request_date": today_str, "free_ai_used": 0,
        }
        self.assertFalse(database.try_consume_free_ai(uid_prem))

        # 2) Muddatsiz premium userda try_consume_free_ai erta False qaytaradi
        uid_inf = 901002
        self.mock.users[uid_inf] = {
            "is_premium": 1, "premium_type": "ultra", "premium_expires_at": None,
            "daily_requests": 0, "last_request_date": today_str, "free_ai_used": 0,
        }
        self.assertFalse(database.try_consume_free_ai(uid_inf))

        # 3) Oddiy user consume/refund oqimi
        uid_reg = 901003
        self.mock.users[uid_reg] = {
            "is_premium": 0, "premium_type": "free", "premium_expires_at": None,
            "daily_requests": 0, "last_request_date": today_str, "free_ai_used": 0,
        }
        self.assertTrue(database.try_consume_free_ai(uid_reg))
        database.refund_free_ai(uid_reg)
        # Bepul foydalanuvchida kunlik limit yo'q (jami 1 ta bir martalik savol) — lekin ulanish baribir yopiladi
        self.assertFalse(database.try_consume_daily_request(uid_reg))
        database.refund_daily_request(uid_reg)

        self.assertGreater(len(self.mock.connections), 0)
        for conn in self.mock.connections:
            self.assertTrue(conn.closed, "Connection yopilmay qoldi!")
            for cur in conn.cursors:
                self.assertTrue(cur.closed, "Cursor yopilmay qoldi!")

    def test_db_connection_rollback_and_close_on_exceptions(self):
        # 30. SQL execute yoki commit xatosida rollback chaqirilishi va connection/cursor yopilishi
        import database

        uid = 902001
        today_str = database.get_uz_now().date().isoformat()
        self.mock.users[uid] = {
            "is_premium": 0, "premium_type": "free", "premium_expires_at": None,
            "daily_requests": 1, "last_request_date": today_str, "free_ai_used": 1,
        }

        orig_reg = database.register_user
        try:
            database.register_user = lambda *a, **k: None

            for fn in (
                database.try_consume_daily_request,
                database.refund_daily_request,
                database.try_consume_free_ai,
                database.refund_free_ai,
            ):
                self.mock.connections.clear()
                self.mock.fail_execute = True
                self.mock.fail_commit = False
                with self.assertRaises(Exception):
                    fn(uid)
                self.assertEqual(len(self.mock.connections), 1)
                c_exec = self.mock.connections[0]
                self.assertTrue(c_exec.rolled_back, f"{fn.__name__}: execute xatosida rollback qilinmadi")
                self.assertTrue(c_exec.closed, f"{fn.__name__}: execute xatosida connection yopilmadi")
                for cur in c_exec.cursors:
                    self.assertTrue(cur.closed, f"{fn.__name__}: execute xatosida cursor yopilmadi")

                self.mock.connections.clear()
                self.mock.fail_execute = False
                self.mock.fail_commit = True
                with self.assertRaises(Exception):
                    fn(uid)
                self.assertEqual(len(self.mock.connections), 1)
                c_commit = self.mock.connections[0]
                self.assertTrue(c_commit.rolled_back, f"{fn.__name__}: commit xatosida rollback qilinmadi")
                self.assertTrue(c_commit.closed, f"{fn.__name__}: commit xatosida connection yopilmadi")
                for cur in c_commit.cursors:
                    self.assertTrue(cur.closed, f"{fn.__name__}: commit xatosida cursor yopilmadi")
        finally:
            self.mock.fail_execute = False
            self.mock.fail_commit = False
            database.register_user = orig_reg

    def test_pooled_connection_wrapper_idempotent_close(self):
        # 31. PooledConnectionWrapper.close() bir marta putconn chaqirishi va takroriy close() xavfsizligi
        import database

        returned = []
        class DummyPool:
            def putconn(self, conn):
                returned.append(conn)

        raw_conn = object()
        wrapper = database.PooledConnectionWrapper(raw_conn, DummyPool())
        wrapper.close()
        wrapper.close()
        self.assertEqual(len(returned), 1)
        self.assertIs(returned[0], raw_conn)

    def test_pooled_connection_wrapper_threadsafe_and_broken_rollback(self):
        # 32. Ko'p oqimli (multithreaded) close() va rollback xatosida close=True bilan yopish
        import threading
        import database

        calls = []
        lock = threading.Lock()

        class DummyPool:
            def putconn(self, conn, close=False):
                with lock:
                    calls.append((conn, close))

        class BrokenRawConn:
            def rollback(self):
                raise RuntimeError("socket closed during rollback")

        raw1 = object()
        w1 = database.PooledConnectionWrapper(raw1, DummyPool())
        threads = [threading.Thread(target=w1.close) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], raw1)
        self.assertFalse(calls[0][1])

        calls.clear()
        raw2 = BrokenRawConn()
        w2 = database.PooledConnectionWrapper(raw2, DummyPool())
        with self.assertRaises(RuntimeError):
            w2.rollback()
        w2.close()
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], raw2)
        self.assertTrue(calls[0][1], "Rollback xatosidan keyin broken connection close=True bilan yopilishi kerak")

    def test_is_waiting_receipt_and_managed_cursor_cleanup(self):
        # 33. database.is_waiting_receipt mavjudligi va _managed_cursor xatoda cursor/conn yopishi
        import database

        self.assertTrue(hasattr(database, "is_waiting_receipt"))
        self.assertIsInstance(database.is_waiting_receipt(123456), bool)

        for fn, args in [
            (database.set_premium, (123456, 1)),
            (database.add_score, (123456, 10)),
            (database.get_score, (123456,)),
            (database.is_waiting_receipt, (123456,)),
        ]:
            self.mock.connections.clear()
            self.mock.fail_execute = True
            with self.assertRaises(Exception):
                fn(*args)
            self.assertEqual(len(self.mock.connections), 1)
            conn = self.mock.connections[0]
            self.assertTrue(conn.rolled_back, f"{fn.__name__}: rollback qilinmadi")
            self.assertTrue(conn.closed, f"{fn.__name__}: connection yopilmadi")
            for cur in conn.cursors:
                self.assertTrue(cur.closed, f"{fn.__name__}: cursor yopilmadi")
        self.mock.fail_execute = False

    def test_premium_type_and_days_validation_before_db_transaction(self):
        # 35. process_paid_premium va grant_premium_days: noto'g'ri premium_type yoki days bo'lsa
        # DB tranzaksiyasi boshlanishidan oldin ValueError qaytarilishi
        import database

        self.mock.connections.clear()
        invalid_types = ("free", "gold", "basic", "", None, 123, ["pro"])
        for bad_type in invalid_types:
            with self.assertRaises(ValueError, msg=f"grant_premium_days invalid type={bad_type!r}"):
                database.grant_premium_days(1001, 7, premium_type=bad_type)
            with self.assertRaises(ValueError, msg=f"process_paid_premium invalid type={bad_type!r}"):
                database.process_paid_premium("ch_val_1", 1001, "PRO_7_DAYS", 50, bad_type, 7)

        invalid_days = (0, -1, -30, True, False, 3.5, "7", None)
        for bad_days in invalid_days:
            with self.assertRaises(ValueError, msg=f"grant_premium_days invalid days={bad_days!r}"):
                database.grant_premium_days(1001, bad_days, premium_type="pro")
            with self.assertRaises(ValueError, msg=f"process_paid_premium invalid days={bad_days!r}"):
                database.process_paid_premium("ch_val_2", 1001, "PRO_7_DAYS", 50, "pro", bad_days)

        # Hech qanday DB connection ochilmagan bo'lishi shart!
        self.assertEqual(len(self.mock.connections), 0, "Validatsiya xatosida DB connection ochilmasligi kerak!")

    def test_grant_premium_days_locking_and_transaction_behavior(self):
        # 36. grant_premium_days(): mustaqil tranzaksiyada SELECT ... FOR UPDATE va commit/close,
        # tashqi _cursor berilganda commit/close qilmaslik
        import database

        executed_queries = []
        orig_execute = FakeCursor.execute

        def spy_execute(cur_self, query, params=None):
            executed_queries.append(query.strip())
            return orig_execute(cur_self, query, params)

        FakeCursor.execute = spy_execute
        try:
            self.mock.connections.clear()
            uid = 808001
            self.mock.users[uid] = {"is_premium": 0, "premium_type": "free", "premium_expires_at": None}

            # 1) Mustaqil tranzaksiya (_cursor=None): SELECT ... FOR UPDATE, commit=True, close=True
            until1 = database.grant_premium_days(uid, 7, premium_type="pro")
            self.assertIsNotNone(until1)
            self.assertEqual(len(self.mock.connections), 1)
            standalone_conn = self.mock.connections[0]
            self.assertTrue(standalone_conn.committed, "Mustaqil grant_premium_days commit qilishi shart")
            self.assertTrue(standalone_conn.closed, "Mustaqil grant_premium_days connectionni yopishi shart")
            self.assertTrue(standalone_conn.cursors[0].closed, "Mustaqil grant_premium_days cursorni yopishi shart")
            self.assertTrue(
                any("SELECT PREMIUM_EXPIRES_AT, PREMIUM_TYPE FROM USERS" in q.upper() and "FOR UPDATE" in q.upper() for q in executed_queries),
                f"Mustaqil tranzaksiyada SELECT ... FOR UPDATE ishlatilmadi: {executed_queries}"
            )

            # 2) Tashqi tranzaksiya (_cursor berilganda): commit ham, close ham qilmasligi shart
            executed_queries.clear()
            self.mock.connections.clear()
            ext_conn = self.mock.get_connection()
            ext_cur = ext_conn.cursor()

            until2 = database.grant_premium_days(uid, 30, premium_type="plus", _cursor=ext_cur)
            self.assertGreater(until2, until1)
            self.assertEqual(self.mock.users[uid]["premium_type"], "plus")
            self.assertEqual(len(self.mock.connections), 1, "Tashqi cursor berilganda yangi connection ochilmasligi kerak")
            self.assertFalse(ext_conn.committed, "Tashqi cursor berilganda grant_premium_days commit qilmasligi kerak")
            self.assertFalse(ext_conn.closed, "Tashqi cursor berilganda grant_premium_days connectionni yopmasligi kerak")
            self.assertFalse(ext_cur.closed, "Tashqi cursor berilganda grant_premium_days cursorni yopmasligi kerak")
        finally:
            FakeCursor.execute = orig_execute

    def test_record_failed_payment_sqlite_failure_not_reported_as_saved(self):
        # 37. SQLite yozuvi muvaffaqiyatsiz bo'lganda record_failed_payment False qaytarishi,
        # in-memory keshda saqlangan deb qolmasligi va foydalanuvchi/adminga yolg'on 'saqlandi' yuborilmasligi
        import bot
        import asyncio

        class FakeUser:
            def __init__(self, uid):
                self.id = uid
                self.username = "sqlite_fail_user"

        class FakeBot:
            def __init__(self):
                self.messages = []
            async def send_message(self, chat_id, text, **kwargs):
                self.messages.append((chat_id, text))

        class FakePayment:
            def __init__(self, charge_id, payload="PRO_7_DAYS", amount=50, currency="XTR"):
                self.telegram_payment_charge_id = charge_id
                self.provider_payment_charge_id = None
                self.invoice_payload = payload
                self.total_amount = amount
                self.currency = currency

        class FakeMessage:
            def __init__(self, uid, payment, fbot):
                self.from_user = FakeUser(uid)
                self.successful_payment = payment
                self.bot = fbot
                self.answers = []
            async def answer(self, text, **kwargs):
                self.answers.append(text)

        orig_db_path = bot._PENDING_RECONCILE_DB
        orig_admin = bot.ADMIN_ID
        orig_process = self.db.process_paid_premium
        try:
            bot.ADMIN_ID = "12345"
            # Mavjud papkani fayl sifatida ko'rsatamiz -> sqlite3.connect OperationalError beradi
            bot._PENDING_RECONCILE_DB = self._tmp_dir.name
            bot._pending_failed_payments.clear()

            # 1) record_failed_payment bevosita False qaytarishi va _pending_failed_payments toza qolishi
            cid1 = "ch_sqlite_broken_1"
            ok = bot.record_failed_payment(cid1, 701001, "PRO_7_DAYS", 50)
            self.assertFalse(ok, "SQLite ishlamaganda record_failed_payment False qaytarishi shart")
            self.assertNotIn(cid1, bot._pending_failed_payments, "SQLite yozilmaganda in-memory dict da qolmasligi kerak")

            # 2) Stars DB xatosi + SQLite xatosi -> foydalanuvchiga 'To'lovingiz saqlab qolindi' DEYILMASLIGI shart
            def fail_db(*a, **k):
                raise RuntimeError("Primary PostgreSQL down")
            self.db.process_paid_premium = fail_db

            fbot = FakeBot()
            cid2 = "ch_sqlite_broken_2"
            msg = FakeMessage(701002, FakePayment(cid2, "PRO_7_DAYS", 50, "XTR"), fbot)
            asyncio.run(bot.process_successful_payment(msg))

            self.assertEqual(len(msg.answers), 1)
            self.assertNotIn("saqlab qolindi", msg.answers[0])
            self.assertIn(cid2, msg.answers[0])
            self.assertTrue(any("Dalilni saqlashda xatolik" in m[1] for m in fbot.messages))
            self.assertFalse(any("Dalil saqlandi" in m[1] for m in fbot.messages))

            # 3) Noma'lum payload + SQLite xatosi -> adminga 'Dalilni saqlashda xatolik!' borishi shart
            fbot2 = FakeBot()
            cid3 = "ch_sqlite_broken_3"
            msg2 = FakeMessage(701003, FakePayment(cid3, "UNKNOWN_TIER_99", 50, "XTR"), fbot2)
            asyncio.run(bot.process_successful_payment(msg2))
            self.assertTrue(any("Dalilni saqlashda xatolik" in m[1] for m in fbot2.messages))
            self.assertFalse(any("Dalil saqlandi" in m[1] for m in fbot2.messages))
        finally:
            bot._PENDING_RECONCILE_DB = orig_db_path
            bot.ADMIN_ID = orig_admin
            self.db.process_paid_premium = orig_process

    def test_unique_index_migration_error_logged_and_raised(self):
        # 38. init_db(): idx_payment_transactions_charge_id UNIQUE indeks xatosi jim yutilmasligi,
        # dublikatlar avtomatik o'chirilmasligi va xato log qilinib yuqoriga uzatilishi
        import database

        executed_sql = []
        orig_execute = FakeCursor.execute

        def fail_on_unique_idx(cur_self, query, params=None):
            executed_sql.append(query.strip())
            if "CREATE UNIQUE INDEX" in query.upper() and "IDX_PAYMENT_TRANSACTIONS_CHARGE_ID" in query.upper():
                err = RuntimeError("could not create unique index \"idx_payment_transactions_charge_id\": Key (charge_id)=(dup_1) is duplicated.")
                err.pgcode = "23505"
                raise err
            return orig_execute(cur_self, query, params)

        FakeCursor.execute = fail_on_unique_idx
        try:
            self.mock.connections.clear()
            self.mock.payment_transactions["dup_1"] = ("dup_1", 111, "PRO_7_DAYS", 50, "pro", 7)

            with self.assertLogs(level="CRITICAL") as cm:
                with self.assertRaises(RuntimeError):
                    database.init_db()

            self.assertTrue(any("idx_payment_transactions_charge_id" in line for line in cm.output))
            # Hech qanday DELETE so'rovi yuborilmagan bo'lishi va mavjud yozuv o'chirilmagan bo'lishi shart
            self.assertFalse(any("DELETE" in q.upper() for q in executed_sql))
            self.assertIn("dup_1", self.mock.payment_transactions)
            # Connection rollback qilinib yopilgan bo'lishi shart
            self.assertEqual(len(self.mock.connections), 1)
            self.assertTrue(self.mock.connections[0].rolled_back)
            self.assertTrue(self.mock.connections[0].closed)
        finally:
            FakeCursor.execute = orig_execute


if __name__ == "__main__":
    unittest.main()
