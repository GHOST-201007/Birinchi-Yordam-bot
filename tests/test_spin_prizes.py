"""
test_spin_prizes.py — Omad baraboni: 8 bo'lakli yangi sovrinlar jadvali.

  1, 2, 3, 5 ball | -2 kun maslahati | -1 +1 bepul AI savol | -3 1 kunlik Premium Pro | 0 SUPER (Plus uchun 50%)

DB mantig'i HAQIQIY SQL bilan (tests/sqlite_db.py: atomar shartli UPDATE, rowcount, rollback, parallel oqimlar);
Telegram, Gemini va PostgreSQL ishlatilmaydi.
"""
import datetime as dt
import math
import os
import random
import re
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import database  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402

UID = 900000701
THREADS = 20
UZ = dt.timezone(dt.timedelta(hours=5))
EXPECTED_TABLE = {1: 0.35, 2: 0.20, 3: 0.12, 5: 0.05, -2: 0.15, -1: 0.10, -3: 0.02, 0: 0.01}


def now():
    return database.get_uz_now()


def parse(value):
    return database._to_uz_datetime(value)


# ───────────────────────────── jadval (DB'siz) ─────────────────────────────
class PrizeTableTest(unittest.TestCase):
    def test_probabilities_sum_to_one(self):
        self.assertTrue(math.isclose(sum(p for _, p in database.SPIN_PRIZES), 1.0, abs_tol=1e-9))

    def test_table_is_exactly_the_specified_one(self):
        self.assertEqual(len(database.SPIN_PRIZES), 8)
        self.assertEqual(len({code for code, _ in database.SPIN_PRIZES}), 8)              # kodlar takrorlanmaydi
        self.assertEqual(dict(database.SPIN_PRIZES), EXPECTED_TABLE)

    def test_expected_points_drop_to_about_1_4_per_day(self):
        expected = sum(code * p for code, p in database.SPIN_PRIZES if code > 0)
        self.assertAlmostEqual(expected, 1.36, places=2)                                  # ~3.5 dan ~1.4 ga

    def test_legacy_10_points_is_gone_from_the_table(self):
        self.assertNotIn(10, [code for code, _ in database.SPIN_PRIZES])

    def test_pick_follows_cumulative_boundaries(self):
        pick = database.pick_spin_prize
        # Chegaralar (kumulyativ): .35 | .55 | .67 | .72 | .87 | .97 | .99 — har birining ikki tomoni (aniq chegara emas:
        # suzuvchi nuqtada 0.35+0.20+0.12+0.05 aniq 0.72 bo'lmasligi mumkin)
        cases = [(0.0, 1), (0.3499, 1), (0.3501, 2), (0.5499, 2), (0.5501, 3), (0.6699, 3), (0.6701, 5),
                 (0.7199, 5), (0.7201, -2), (0.8699, -2), (0.8701, -1), (0.9699, -1), (0.9701, -3),
                 (0.9899, -3), (0.9901, 0), (0.99999999, 0)]
        for r, code in cases:
            with self.subTest(r=r):
                self.assertEqual(pick(r), code)

    def test_pick_uses_random_when_no_value_given(self):
        with mock.patch.object(database.random, "random", return_value=0.995):
            self.assertEqual(database.pick_spin_prize(), 0)

    def test_pick_distribution_matches_table(self):
        rng = random.Random(20261111)
        n = 100_000
        counts = {code: 0 for code, _ in database.SPIN_PRIZES}
        for _ in range(n):
            counts[database.pick_spin_prize(rng.random())] += 1
        for code, p in database.SPIN_PRIZES:
            self.assertAlmostEqual(counts[code] / n, p, delta=0.006, msg=f"kod {code}")

    def test_prize_types(self):
        types = {1: "points", 2: "points", 3: "points", 5: "points",
                 -2: "tip", -1: "ai", -3: "pro_day", 0: "super", 10: "points"}
        for code, kind in types.items():
            self.assertEqual(database.spin_prize_type(code), kind, code)
        self.assertIsNone(database.spin_prize_type(None))

    def test_normalize_keeps_known_and_legacy_10_and_maps_unknown_to_one_point(self):
        for code in (*EXPECTED_TABLE, 10):
            self.assertEqual(database.normalize_spin_prize(code), code)
        for unknown in (4, 7, 20, 50, 99, -4, -9, 1000):
            self.assertEqual(database.normalize_spin_prize(unknown), 1, unknown)
        self.assertIsNone(database.normalize_spin_prize(None))

    def test_app_js_segments_use_exactly_the_server_codes(self):
        with open(os.path.join(PROJECT_DIR, "app", "app.js"), encoding="utf-8") as f:
            js = f.read()
        start = js.index("const segments = [")
        block = js[start: js.index("];", start)]
        codes = [int(x) for x in re.findall(r"code: (-?\d+)", block)]
        self.assertEqual(len(codes), 8)
        self.assertEqual(sorted(codes), sorted(database.SPIN_PRIZE_CODES))
        self.assertEqual(sorted(codes), sorted(EXPECTED_TABLE))


class TipsTest(unittest.TestCase):
    def setUp(self):
        database._spin_tips_cache = None
        self.addCleanup(setattr, database, "_spin_tips_cache", None)

    def test_file_has_40_unique_non_empty_strings(self):
        tips = database.load_spin_tips()
        self.assertEqual(len(tips), 40)
        self.assertEqual(len(set(tips)), 40)
        self.assertTrue(all(isinstance(t, str) and t.strip() for t in tips))
        self.assertLessEqual(max(len(t) for t in tips), 300)               # xabarga va kartaga sig'adi

    def test_file_is_plain_json_array_of_strings(self):
        import json
        with open(database.SPIN_TIPS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, list)
        self.assertEqual(data[0], "Kuyganda joyni 10–20 daqiqa salqin oqar suv ostida tuting. "
                                  "Muz, yog' yoki tish pastasi surtmang.")
        self.assertEqual(data[-1], "Muhim raqamlar: 101 — yong'in, 102 — militsiya, 103 — tez yordam, 104 — gaz xizmati.")
        self.assertIn("Zaharlanganda shifokor aytmaguncha qustirishga urinmang.", data)

    def test_pick_returns_a_tip_from_the_file(self):
        tips = set(database.load_spin_tips())
        for _ in range(50):
            self.assertIn(database.pick_spin_tip(), tips)

    def test_missing_or_broken_file_falls_back_to_one_safe_tip(self):
        with mock.patch.object(database, "SPIN_TIPS_PATH", os.path.join(PROJECT_DIR, "data", "yoq.json")):
            tips = database.load_spin_tips()
        self.assertEqual(len(tips), 1)
        self.assertIn("103", tips[0])

    def test_data_directory_does_not_shadow_data_module(self):
        # data/ papkasi (spin_tips.json) yonidagi data.py modulini yashirmasligi kerak
        import data
        self.assertTrue(hasattr(data, "FIRST_AID_DATA"))
        self.assertTrue(data.__file__.endswith("data.py"))


# ───────────────────────────── DB (SQLite) ─────────────────────────────
class DbTestCase(unittest.TestCase):
    def setUp(self):
        self.reset()

    def reset(self):
        """Toza baza (subTest'lar orasida ham ishlatiladi)."""
        if getattr(self, "_patcher", None):
            self._patcher.stop()
            self.db.close()
        self.db = SqliteDB()
        self._patcher = self.db.patched()
        self._patcher.start()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        if self._patcher:
            self._patcher.stop()
            self._patcher = None
            self.db.close()

    def user(self, **cols):
        self.db.add_user(UID, **cols)
        return self.db.row(UID)

    def row(self):
        return self.db.row(UID)


class ClaimPrizeTest(DbTestCase):
    def test_every_points_code_adds_exactly_that_many_points(self):
        for code in (1, 2, 3, 5):
            with self.subTest(code=code):
                self.reset()
                self.user(pending_spin_prize=code, medicine_score=10)
                r = database.claim_spin_prize(UID)
                self.assertTrue(r["ok"])
                self.assertEqual((r["code"], r["prize_type"], r["points"], r["tip"]), (code, "points", code, None))
                self.assertIn(f"+{code} ball", r["message"])
                row = self.row()
                self.assertEqual(row["medicine_score"], 10 + code)
                self.assertIsNone(row["pending_spin_prize"])
                self.assertIsNotNone(row["last_spin_date"])                 # cooldown boshlandi
                self.assertEqual((row["spin_ai_bonus"], row["has_discount"], row["is_premium"]), (0, 0, 0))

    def test_tip_gives_no_points_and_returns_a_tip_from_the_file(self):
        self.user(pending_spin_prize=-2, medicine_score=10)
        r = database.claim_spin_prize(UID)
        self.assertTrue(r["ok"])
        self.assertEqual((r["code"], r["prize_type"], r["points"]), (-2, "tip", 0))
        self.assertIn(r["tip"], database.load_spin_tips())
        self.assertIn(r["tip"], r["message"])
        self.assertIn("Kun maslahati", r["message"])
        row = self.row()
        self.assertEqual(row["medicine_score"], 10)                          # ball yo'q
        self.assertIsNone(row["pending_spin_prize"])
        self.assertIsNotNone(row["last_spin_date"])                          # cooldown boshlandi
        self.assertEqual((row["spin_ai_bonus"], row["has_discount"], row["is_premium"]), (0, 0, 0))

    def test_tip_text_is_html_escaped_in_message_but_raw_in_field(self):
        database._spin_tips_cache = ["A & B <b>x</b>"]
        self.addCleanup(setattr, database, "_spin_tips_cache", None)
        self.user(pending_spin_prize=-2)
        r = database.claim_spin_prize(UID)
        self.assertEqual(r["tip"], "A & B <b>x</b>")
        self.assertIn("A &amp; B &lt;b&gt;x&lt;/b&gt;", r["message"])

    def test_ai_prize_adds_one_bonus_question(self):
        self.user(pending_spin_prize=-1, medicine_score=10, spin_ai_bonus=2)
        r = database.claim_spin_prize(UID)
        self.assertTrue(r["ok"])
        self.assertEqual((r["code"], r["prize_type"], r["points"], r["tip"]), (-1, "ai", 0, None))
        row = self.row()
        self.assertEqual(row["spin_ai_bonus"], 3)
        self.assertEqual(row["medicine_score"], 10)
        self.assertIsNone(row["pending_spin_prize"])

    def test_ai_prize_works_when_bonus_column_is_null(self):
        self.user(pending_spin_prize=-1, spin_ai_bonus=None)
        self.assertTrue(database.claim_spin_prize(UID)["ok"])
        self.assertEqual(self.row()["spin_ai_bonus"], 1)

    def test_super_prize_sets_discount_and_keeps_message(self):
        self.user(pending_spin_prize=0, medicine_score=10)
        with mock.patch.dict(os.environ, {"PRO_MONTHLY_STARS": "150"}):
            r = database.claim_spin_prize(UID)
        self.assertTrue(r["ok"])
        self.assertEqual((r["code"], r["prize_type"], r["points"]), (0, "super", 0))
        self.assertIn("75 Stars", r["message"])
        row = self.row()
        self.assertEqual((row["has_discount"], row["medicine_score"]), (1, 10))

    def test_legacy_pending_10_is_given_as_10_points_unchanged(self):
        self.user(pending_spin_prize=10, medicine_score=0)
        self.assertEqual(database.generate_or_get_spin_prize(UID), 10)        # foydalanuvchi ko'rgan qiymat o'zgarmaydi
        self.assertEqual(self.row()["pending_spin_prize"], 10)
        r = database.claim_spin_prize(UID)
        self.assertTrue(r["ok"])
        self.assertEqual((r["code"], r["prize_type"], r["points"]), (10, "points", 10))
        self.assertEqual(self.row()["medicine_score"], 10)

    def test_unknown_pending_values_become_one_point(self):
        for unknown in (7, 20, 50, -9):
            with self.subTest(pending=unknown):
                self.reset()
                self.user(pending_spin_prize=unknown, medicine_score=0)
                r = database.claim_spin_prize(UID)
                self.assertTrue(r["ok"])
                self.assertEqual((r["prize_type"], r["points"]), ("points", 1))
                self.assertEqual(self.row()["medicine_score"], 1)

    def test_ten_point_cap_rule_is_gone(self):
        # eski qoida: 10 dan boshqa katta qiymat 10 ga tushirilardi; endi noma'lum qiymat +1
        self.user(pending_spin_prize=20, medicine_score=0)
        self.assertEqual(database.claim_spin_prize(UID)["points"], 1)

    def test_client_points_are_ignored_by_legacy_wrapper(self):
        self.user(pending_spin_prize=3, medicine_score=0)
        ok, message = database.check_and_grant_spin_bonus(UID, 5000)
        self.assertTrue(ok)
        self.assertIn("+3 ball", message)
        self.assertEqual(self.row()["medicine_score"], 3)

    def test_second_claim_gives_nothing_for_every_prize_type(self):
        for code in EXPECTED_TABLE:
            with self.subTest(code=code):
                self.reset()
                self.user(pending_spin_prize=code, medicine_score=0)
                first = database.claim_spin_prize(UID)
                after_first = self.row()
                second = database.claim_spin_prize(UID)
                self.assertTrue(first["ok"])
                self.assertFalse(second["ok"])
                self.assertEqual((second["code"], second["prize_type"], second["points"], second["tip"]),
                                 (None, None, 0, None))
                self.assertEqual(self.row(), after_first)                    # ikkinchi marta hech narsa o'zgarmadi

    def test_cooldown_blocks_claim_and_keeps_pending(self):
        recent = (now() - dt.timedelta(hours=1)).isoformat()
        self.user(pending_spin_prize=5, last_spin_date=recent, medicine_score=0)
        r = database.claim_spin_prize(UID)
        self.assertFalse(r["ok"])
        self.assertIn("Keyingi urinishgacha", r["message"])
        row = self.row()
        self.assertEqual((row["pending_spin_prize"], row["medicine_score"]), (5, 0))

    def test_no_pending_prize_and_unknown_user(self):
        self.user(pending_spin_prize=None)
        r = database.claim_spin_prize(UID)
        self.assertFalse(r["ok"])
        self.assertIn("tasdiqlanmagan yutuq", r["message"])
        r = database.claim_spin_prize(UID + 1)
        self.assertFalse(r["ok"])
        self.assertIn("topilmadi", r["message"])

    def test_old_cooldown_over_allows_claim(self):
        old = (now() - dt.timedelta(hours=25)).isoformat()
        self.user(pending_spin_prize=2, last_spin_date=old, medicine_score=0)
        self.assertTrue(database.claim_spin_prize(UID)["ok"])

    def test_premium_for_100_points_is_checked_only_for_point_prizes(self):
        for code, calls in ((2, 1), (-2, 0), (-1, 0), (0, 0), (-3, 0)):
            with self.subTest(code=code):
                self.reset()
                self.user(pending_spin_prize=code, medicine_score=150)
                with mock.patch.object(database, "check_and_grant_premium") as check:
                    database.claim_spin_prize(UID)
                self.assertEqual(check.call_count, calls)

    def test_hundred_points_still_unlock_three_days_pro(self):
        self.user(pending_spin_prize=2, medicine_score=99)
        database.claim_spin_prize(UID)
        row = self.row()
        self.assertEqual(row["medicine_score"], 1)                           # 99 + 2 - 100
        self.assertEqual((row["is_premium"], row["premium_type"]), (1, "pro"))
        self.assertAlmostEqual((parse(row["premium_expires_at"]) - now()).total_seconds(), 3 * 86400, delta=60)


class ParallelClaimTest(DbTestCase):
    def run_parallel(self, func):
        barrier = threading.Barrier(THREADS, timeout=10)

        def worker(_):
            barrier.wait()
            return func()

        with ThreadPoolExecutor(max_workers=THREADS) as pool:
            return list(pool.map(worker, range(THREADS)))

    def test_twenty_parallel_claims_give_one_prize_of_every_type(self):
        for code in EXPECTED_TABLE:
            with self.subTest(code=code):
                self.reset()
                self.user(pending_spin_prize=code, medicine_score=0)
                results = self.run_parallel(lambda: database.claim_spin_prize(UID))
                self.assertEqual(sum(1 for r in results if r["ok"]), 1)
                row = self.row()
                self.assertEqual(row["medicine_score"], code if code > 0 else 0)
                self.assertEqual(row["spin_ai_bonus"], 1 if code == -1 else 0)
                self.assertEqual(row["has_discount"], 1 if code == 0 else 0)
                if code == -3:
                    # 1 kun, 20 kun emas
                    self.assertAlmostEqual((parse(row["premium_expires_at"]) - now()).total_seconds(), 86400, delta=60)
                else:
                    self.assertEqual(row["is_premium"], 0)


class ProDayTest(DbTestCase):
    def claim(self):
        r = database.claim_spin_prize(UID)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["code"], r["prize_type"], r["points"], r["tip"]), (-3, "pro_day", 0, None))
        return r

    def test_free_user_gets_one_day_of_pro(self):
        self.user(pending_spin_prize=-3, medicine_score=7)
        r = self.claim()
        self.assertIn("1 kunlik Premium Pro", r["message"])
        row = self.row()
        self.assertEqual((row["is_premium"], row["premium_type"]), (1, "pro"))
        self.assertAlmostEqual((parse(row["premium_expires_at"]) - now()).total_seconds(), 86400, delta=60)
        self.assertEqual(row["medicine_score"], 7)                           # ball yo'q
        self.assertIsNone(row["pending_spin_prize"])

    def test_active_plus_or_ultra_keeps_tier_and_extends_by_one_day(self):
        for tier in ("plus", "ultra"):
            with self.subTest(tier=tier):
                self.reset()
                expires = now() + dt.timedelta(days=10)
                self.user(pending_spin_prize=-3, is_premium=1, premium_type=tier,
                          premium_expires_at=expires.isoformat(), premium_until=expires.isoformat())
                r = self.claim()
                self.assertIn(tier.capitalize(), r["message"])
                self.assertIn("o'zgarmadi", r["message"])
                row = self.row()
                self.assertEqual((row["is_premium"], row["premium_type"]), (1, tier))        # Pro ga TUSHMADI
                self.assertAlmostEqual((parse(row["premium_expires_at"]) - expires).total_seconds(), 86400, delta=2)

    def test_active_pro_extends_by_one_day(self):
        expires = now() + dt.timedelta(days=3)
        self.user(pending_spin_prize=-3, is_premium=1, premium_type="pro", premium_expires_at=expires.isoformat())
        r = self.claim()
        self.assertIn("1 kunga uzaytirildi", r["message"])
        row = self.row()
        self.assertEqual(row["premium_type"], "pro")
        self.assertAlmostEqual((parse(row["premium_expires_at"]) - expires).total_seconds(), 86400, delta=2)

    def test_expired_plus_does_not_keep_old_tier(self):
        expired = now() - dt.timedelta(days=2)
        self.user(pending_spin_prize=-3, is_premium=1, premium_type="plus", premium_expires_at=expired.isoformat())
        self.claim()
        row = self.row()
        self.assertEqual((row["is_premium"], row["premium_type"]), (1, "pro"))
        self.assertAlmostEqual((parse(row["premium_expires_at"]) - now()).total_seconds(), 86400, delta=60)

    def test_unlimited_premium_is_left_untouched(self):
        # muddatsiz premium (admin bergan): grant_premium_days uni 1 kunlik Pro bilan almashtirib yuborardi
        self.user(pending_spin_prize=-3, is_premium=1, premium_type="ultra", premium_expires_at=None)
        r = self.claim()
        self.assertIn("muddatsiz", r["message"])
        row = self.row()
        self.assertEqual((row["is_premium"], row["premium_type"], row["premium_expires_at"]), (1, "ultra", None))
        self.assertIsNone(row["pending_spin_prize"])                          # sovrin baribir sarflandi, cooldown boshlandi
        self.assertIsNotNone(row["last_spin_date"])

    def test_grant_runs_inside_the_claim_transaction(self):
        self.user(pending_spin_prize=-3)
        with mock.patch.object(database, "grant_premium_days", wraps=database.grant_premium_days) as grant:
            self.claim()
        grant.assert_called_once()
        self.assertEqual(grant.call_args.args, (UID, 1, "pro"))
        self.assertIsNotNone(grant.call_args.kwargs.get("_cursor"))           # alohida ulanish/commit emas

    def test_failure_rolls_back_everything_so_prize_is_not_lost(self):
        self.user(pending_spin_prize=-3, medicine_score=4)
        with mock.patch.object(database, "grant_premium_days", side_effect=RuntimeError("DB xatosi")):
            with self.assertRaises(RuntimeError):
                database.claim_spin_prize(UID)
        row = self.row()
        self.assertEqual(row["pending_spin_prize"], -3)                      # sovrin yo'qolmadi
        self.assertIsNone(row["last_spin_date"])                             # cooldown boshlanmadi
        self.assertEqual((row["is_premium"], row["medicine_score"]), (0, 4))
        self.claim()                                                         # qayta urinish muvaffaqiyatli
        self.assertEqual(self.row()["premium_type"], "pro")


class AiBonusDbTest(DbTestCase):
    def test_consume_decrements_until_zero_and_never_goes_negative(self):
        self.user(spin_ai_bonus=2)
        self.assertTrue(database.try_consume_spin_ai_bonus(UID))
        self.assertTrue(database.try_consume_spin_ai_bonus(UID))
        self.assertFalse(database.try_consume_spin_ai_bonus(UID))
        self.assertFalse(database.try_consume_spin_ai_bonus(UID))
        self.assertEqual(self.row()["spin_ai_bonus"], 0)

    def test_consume_without_bonus_or_user_or_null(self):
        self.user(spin_ai_bonus=None)
        self.assertFalse(database.try_consume_spin_ai_bonus(UID))
        self.assertFalse(database.try_consume_spin_ai_bonus(UID + 1))

    def test_refund_returns_the_question(self):
        self.user(spin_ai_bonus=1)
        self.assertTrue(database.try_consume_spin_ai_bonus(UID))
        database.refund_spin_ai_bonus(UID)
        self.assertEqual(self.row()["spin_ai_bonus"], 1)
        self.assertTrue(database.try_consume_spin_ai_bonus(UID))             # qaytarilgan savol yana ishlatiladi

    def test_refund_on_null_column_gives_one(self):
        self.user(spin_ai_bonus=None)
        database.refund_spin_ai_bonus(UID)
        self.assertEqual(self.row()["spin_ai_bonus"], 1)

    def test_parallel_consumption_never_goes_negative(self):
        self.user(spin_ai_bonus=5)
        barrier = threading.Barrier(30, timeout=10)

        def worker(_):
            barrier.wait()
            return database.try_consume_spin_ai_bonus(UID)

        with ThreadPoolExecutor(max_workers=30) as pool:
            results = list(pool.map(worker, range(30)))
        self.assertEqual(sum(results), 5)                                    # aynan 5 ta muvaffaqiyat
        self.assertEqual(self.row()["spin_ai_bonus"], 0)                     # manfiyga tushmadi

    def test_bonus_does_not_expire_with_premium_or_new_day(self):
        self.user(spin_ai_bonus=3, is_premium=1, premium_type="pro",
                  premium_expires_at=(now() - dt.timedelta(days=1)).isoformat(),
                  daily_requests=15, last_request_date="2020-01-01")
        self.assertTrue(database.try_consume_spin_ai_bonus(UID))
        self.assertEqual(self.row()["spin_ai_bonus"], 2)

    def test_quota_adds_bonus_to_remaining_but_not_to_limit(self):
        self.user(free_ai_used=1, spin_ai_bonus=2)                           # bepul savol ishlatilgan, 2 ta bonus
        self.assertEqual(database.get_ai_quota(UID), (2, 1))
        self.assertEqual(database.get_ai_quota_detail(UID), (2, 1, 2))

    def test_quota_for_premium_with_bonus(self):
        today = now().date().isoformat()
        expires = (now() + dt.timedelta(days=5)).isoformat()
        self.user(is_premium=1, premium_type="pro", premium_expires_at=expires, daily_requests=3,
                  last_request_date=today, spin_ai_bonus=2)
        with mock.patch.dict(os.environ, {"PRO_AI_DAILY_LIMIT": "15"}):
            self.assertEqual(database.get_ai_quota_detail(UID), (14, 15, 2))

    def test_consumption_order_is_regular_quota_first_then_bonus(self):
        # bot va mini app zanjiri: try_consume_free_ai -> try_consume_daily_request -> try_consume_spin_ai_bonus
        self.user(spin_ai_bonus=2)

        def consume():
            if database.try_consume_free_ai(UID):
                return "free"
            if database.try_consume_daily_request(UID):
                return "daily"
            if database.try_consume_spin_ai_bonus(UID):
                return "bonus"
            return None

        self.assertEqual([consume() for _ in range(4)], ["free", "bonus", "bonus", None])
        self.assertEqual(self.row()["free_ai_used"], 1)

    def test_premium_uses_daily_quota_before_bonus(self):
        expires = (now() + dt.timedelta(days=5)).isoformat()
        self.user(is_premium=1, premium_type="pro", premium_expires_at=expires, daily_requests=14,
                  last_request_date=now().date().isoformat(), spin_ai_bonus=1)
        with mock.patch.dict(os.environ, {"PRO_AI_DAILY_LIMIT": "15"}):
            self.assertFalse(database.try_consume_free_ai(UID))               # premiumda bepul savol yo'q
            self.assertTrue(database.try_consume_daily_request(UID))          # 15-savol kunlik kvotadan
            self.assertFalse(database.try_consume_daily_request(UID))         # kunlik tugadi
            self.assertTrue(database.try_consume_spin_ai_bonus(UID))          # endi bonusdan
        row = self.row()
        self.assertEqual((row["daily_requests"], row["spin_ai_bonus"]), (15, 0))


class GeneratePrizeTest(DbTestCase):
    def test_new_prize_comes_from_the_table(self):
        for code in EXPECTED_TABLE:
            with self.subTest(code=code):
                self.reset()
                self.user()
                with mock.patch.object(database, "pick_spin_prize", return_value=code):
                    self.assertEqual(database.generate_or_get_spin_prize(UID), code)
                self.assertEqual(self.row()["pending_spin_prize"], code)

    def test_real_random_draw_stays_inside_table(self):
        self.user()
        self.assertIn(database.generate_or_get_spin_prize(UID), EXPECTED_TABLE)

    def test_random_value_maps_through_spin_prizes(self):
        self.user()
        with mock.patch.object(database.random, "random", return_value=0.995):
            self.assertEqual(database.generate_or_get_spin_prize(UID), 0)    # SUPER

    def test_pending_prize_is_returned_and_not_regenerated(self):
        self.user(pending_spin_prize=-1)
        with mock.patch.object(database, "pick_spin_prize", return_value=5) as pick:
            self.assertEqual(database.generate_or_get_spin_prize(UID), -1)
        pick.assert_not_called()
        self.assertEqual(self.row()["pending_spin_prize"], -1)

    def test_unknown_pending_is_reported_as_one_point_like_claim_will_give(self):
        self.user(pending_spin_prize=20)
        self.assertEqual(database.generate_or_get_spin_prize(UID), 1)

    def test_cooldown_and_unknown_user_return_none(self):
        recent = (now() - dt.timedelta(hours=2)).isoformat()
        self.user(last_spin_date=recent)
        self.assertIsNone(database.generate_or_get_spin_prize(UID))
        self.assertIsNone(self.row()["pending_spin_prize"])                  # cooldownda yangi sovrin yaratilmaydi
        self.assertIsNone(database.generate_or_get_spin_prize(UID + 1))


class MigrationTest(unittest.TestCase):
    def test_init_db_adds_spin_ai_bonus_column_in_existing_style(self):
        cursor = mock.MagicMock()
        executed = []
        cursor.execute.side_effect = lambda sql, params=(): executed.append(" ".join(sql.split()))
        cm = mock.MagicMock()
        cm.__enter__.return_value = (mock.MagicMock(), cursor)
        with mock.patch.object(database, "_managed_cursor", return_value=cm):
            database.init_db()
        self.assertIn("ALTER TABLE users ADD COLUMN IF NOT EXISTS spin_ai_bonus INTEGER DEFAULT 0", executed)
        create_users = next(q for q in executed if q.startswith("CREATE TABLE IF NOT EXISTS users"))
        self.assertIn("spin_ai_bonus INTEGER DEFAULT 0", create_users)
        self.assertIn("pending_spin_prize INTEGER", create_users)             # turi o'zgarmagan


# ───────────────────────────── bot: kvota zanjiri ─────────────────────────────
class BotQuotaChainSourceTest(unittest.TestCase):
    def test_every_consume_site_also_tries_bonus_and_refunds_it(self):
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            src = f.read()
        free = src.count("database.try_consume_free_ai")
        self.assertGreaterEqual(free, 7)                                       # 6 bot joyi + API
        self.assertEqual(src.count("database.try_consume_spin_ai_bonus"), free)
        self.assertEqual(src.count("database.refund_spin_ai_bonus"), src.count("database.refund_free_ai"))
        self.assertEqual(src.count("database.refund_spin_ai_bonus"), src.count("database.refund_daily_request"))

    def test_bonus_is_always_tried_after_free_and_daily(self):
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            src = f.read()
        for m in re.finditer(r"database\.try_consume_free_ai", src):
            window = src[m.start(): m.start() + 700]
            self.assertLess(window.index("try_consume_daily_request"), window.index("try_consume_spin_ai_bonus"))


class BotBonusFlowTest(unittest.IsolatedAsyncioTestCase):
    """Kasallik callback'i (bot): oddiy kvota tugagach bonus sarflanadi, AI xato qilsa bonusga qaytariladi."""

    def setUp(self):
        import bot
        self.bot = bot
        self.m = {
            "free": mock.MagicMock(return_value=False), "daily": mock.MagicMock(return_value=False),
            "bonus": mock.MagicMock(return_value=True),
            "refund_free": mock.MagicMock(), "refund_daily": mock.MagicMock(), "refund_bonus": mock.MagicMock(),
        }
        db = bot.database
        self.upsell = mock.AsyncMock()
        self.stream = mock.AsyncMock(return_value="javob")
        patches = [
            mock.patch.object(db, "try_consume_free_ai", self.m["free"]),
            mock.patch.object(db, "try_consume_daily_request", self.m["daily"]),
            mock.patch.object(db, "try_consume_spin_ai_bonus", self.m["bonus"]),
            mock.patch.object(db, "refund_free_ai", self.m["refund_free"]),
            mock.patch.object(db, "refund_daily_request", self.m["refund_daily"]),
            mock.patch.object(db, "refund_spin_ai_bonus", self.m["refund_bonus"]),
            mock.patch.object(db, "get_premium_info", return_value=(False, None, "free")),
            mock.patch.object(db, "get_medical_profile", return_value=None),
            mock.patch.object(bot, "premium_upsell", self.upsell),
            mock.patch.object(bot, "stream_gemini_to_message", self.stream),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def callback(self):
        cb = mock.MagicMock()
        cb.data = "dis_1_0"
        cb.from_user.id = 424242
        cb.answer = mock.AsyncMock()
        cb.message.bot.send_chat_action = mock.AsyncMock()
        return cb

    async def test_bonus_used_when_regular_quota_is_exhausted(self):
        await self.bot.process_disease_callback(self.callback())
        self.m["bonus"].assert_called_once_with(424242)
        self.upsell.assert_not_awaited()
        self.stream.assert_awaited_once()
        for name in ("refund_free", "refund_daily", "refund_bonus"):
            self.m[name].assert_not_called()                                  # muvaffaqiyat: kvota yeyilgan

    async def test_ai_failure_refunds_the_bonus_not_other_sources(self):
        self.stream.return_value = None
        await self.bot.process_disease_callback(self.callback())
        self.m["refund_bonus"].assert_called_once_with(424242)
        self.m["refund_free"].assert_not_called()
        self.m["refund_daily"].assert_not_called()

    async def test_bonus_is_not_touched_while_regular_quota_remains(self):
        for source, refund in (("free", "refund_free"), ("daily", "refund_daily")):
            with self.subTest(source=source):
                for m in self.m.values():
                    m.reset_mock()
                self.m["free"].return_value = source == "free"
                self.m["daily"].return_value = source == "daily"
                self.stream.return_value = None
                await self.bot.process_disease_callback(self.callback())
                self.m["bonus"].assert_not_called()
                self.m[refund].assert_called_once_with(424242)               # qaysi manbadan olingan bo'lsa, o'shanga
                self.m["refund_bonus"].assert_not_called()

    async def test_all_sources_exhausted_shows_premium_offer(self):
        self.m["bonus"].return_value = False
        cb = self.callback()
        await self.bot.process_disease_callback(cb)
        self.upsell.assert_awaited_once_with(cb)
        self.stream.assert_not_awaited()


class DeepLinkTest(unittest.IsolatedAsyncioTestCase):
    """/start spin_... : parametrdan qat'i nazar sovrin faqat serverdagi pending_spin_prize dan olinadi."""

    async def run_start(self, param, result):
        import bot
        message = mock.MagicMock()
        message.text = f"/start {param}"
        message.from_user.id = 424242
        message.from_user.first_name = "Ali"
        message.from_user.last_name = None
        message.from_user.username = "ali"
        message.answer = mock.AsyncMock()
        state = mock.MagicMock()
        state.clear = mock.AsyncMock()
        db = bot.database
        with mock.patch.object(db, "claim_spin_prize", return_value=result) as claim, \
                mock.patch.object(db, "register_user"), \
                mock.patch.object(db, "get_premium_view", return_value=db.admin_premium_view(0, None, None)), \
                mock.patch.object(bot, "schedule_personal_menu_sync"):
            await bot.cmd_start(message, state)
        return claim, message

    async def test_param_is_ignored_and_message_comes_from_server_result(self):
        for param in ("spin_5", "spin_super", "spin_tip", "spin_ai", "spin_proday", "spin_-2", "spin_abc"):
            with self.subTest(param=param):
                result = {"ok": True, "message": "Natija xabari", "code": -2, "prize_type": "tip",
                          "points": 0, "tip": "x"}
                claim, message = await self.run_start(param, result)
                claim.assert_called_once_with(424242)                         # faqat user_id, parametr uzatilmaydi
                self.assertEqual(message.answer.await_args.args[0], "Natija xabari")

    async def test_super_prize_offers_premium_button_other_types_do_not(self):
        for kind, expect_premium in (("super", True), ("tip", False), ("ai", False), ("pro_day", False), ("points", False)):
            with self.subTest(kind=kind):
                result = {"ok": True, "message": "m", "code": 0, "prize_type": kind, "points": 0, "tip": None}
                _, message = await self.run_start("spin_x", result)
                markup = message.answer.await_args.kwargs["reply_markup"]
                texts = [b.text for row in getattr(markup, "inline_keyboard", []) for b in row]
                self.assertEqual(any("Premium xarid qilish" in t for t in texts), expect_premium)


if __name__ == "__main__":
    unittest.main()
