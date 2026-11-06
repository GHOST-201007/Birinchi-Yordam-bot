"""
test_race_conditions.py — P1-2: parallel so'rovlarda bonus aynan 1 marta beriladi,
register_user dublikat xatosi bermaydi.

Haqiqiy baza ishlatilmaydi. FakeDB PostgreSQL xatti-harakatini taqlid qiladi:
  * SELECT hech qanday qulfsiz joriy holatni o'qiydi (barcha oqimlar to'siqda kutib,
    eski holatni bir vaqtda ko'radi — eng yomon holat);
  * UPDATE/INSERT atomik bajariladi va WHERE shartini qayta tekshiradi.
"""
import contextlib
import os
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

USER_ID = 900000401
THREADS = 20


class FakeDB:
    def __init__(self, row=None):
        self.lock = threading.Lock()
        self.rows = {} if row is None else {USER_ID: dict(row)}
        self.barrier = threading.Barrier(THREADS, timeout=5)
        self.score_grants = 0
        self.inserts = 0


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = -1
        self._result = None

    def execute(self, sql, params=()):
        db = self.db
        sql_flat = " ".join(sql.split())
        if sql_flat.startswith("SELECT daily_streak, last_checkin_date"):
            row = db.rows.get(params[0])
            self._result = (row["daily_streak"], row["last_checkin_date"]) if row else None
            db.barrier.wait()
        elif sql_flat.startswith("SELECT last_spin_date, pending_spin_prize"):
            row = db.rows.get(params[0])
            self._result = (row["last_spin_date"], row["pending_spin_prize"]) if row else None
            db.barrier.wait()
        elif sql_flat.startswith("SELECT user_id FROM users"):
            db.barrier.wait()
            self._result = (params[0],) if params[0] in db.rows else None
        elif sql_flat.startswith("INSERT INTO users"):
            db.barrier.wait()
            with db.lock:
                uid = params[0]
                if uid in db.rows:
                    if "ON CONFLICT" not in sql_flat:
                        raise RuntimeError("duplicate key value violates unique constraint")
                    self.rowcount = 0
                else:
                    db.rows[uid] = {"full_name": params[5]}
                    db.inserts += 1
                    self.rowcount = 1
        elif sql_flat.startswith("UPDATE users SET daily_streak"):
            with db.lock:
                uid = params[3]
                row = db.rows[uid]
                if "IS DISTINCT FROM" in sql_flat and row["last_checkin_date"] == params[4]:
                    self.rowcount = 0
                else:
                    row["last_checkin_date"] = params[1]
                    db.score_grants += 1
                    self.rowcount = 1
        elif sql_flat.startswith("UPDATE users SET last_spin_date"):
            with db.lock:
                uid = params[-1]
                row = db.rows[uid]
                if "pending_spin_prize IS NOT NULL" in sql_flat and row["pending_spin_prize"] is None:
                    self.rowcount = 0
                else:
                    row["pending_spin_prize"] = None
                    db.score_grants += 1
                    self.rowcount = 1
        elif sql_flat.startswith("UPDATE users SET full_name"):
            self.rowcount = 1
        else:
            raise AssertionError(f"Kutilmagan SQL: {sql_flat}")

    def fetchone(self):
        return self._result

    def close(self):
        pass


class FakeConn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return FakeCursor(self.db)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class RaceConditionTest(unittest.TestCase):
    def run_parallel(self, db, func):
        @contextlib.contextmanager
        def fake_managed():
            conn = FakeConn(db)
            yield conn, conn.cursor()

        with mock.patch.object(database, "_managed_cursor", fake_managed), \
             mock.patch.object(database, "get_connection", lambda: FakeConn(db)), \
             mock.patch.object(database, "check_and_grant_premium"):
            with ThreadPoolExecutor(max_workers=THREADS) as pool:
                return list(pool.map(lambda _: func(USER_ID), range(THREADS)))

    def test_daily_bonus_granted_once(self):
        db = FakeDB({"daily_streak": 0, "last_checkin_date": None})
        results = self.run_parallel(db, database.check_and_grant_daily_bonus)
        self.assertEqual(db.score_grants, 1)
        self.assertEqual(sum(1 for granted, _, _ in results if granted), 1)

    def test_spin_bonus_granted_once(self):
        db = FakeDB({"last_spin_date": None, "pending_spin_prize": 5})
        results = self.run_parallel(db, database.check_and_grant_spin_bonus)
        self.assertEqual(db.score_grants, 1)
        self.assertEqual(sum(1 for ok, _ in results if ok), 1)

    def test_register_user_parallel_no_duplicate_error(self):
        db = FakeDB()
        self.run_parallel(db, lambda uid: database.register_user(uid, full_name="Ali"))
        self.assertEqual(db.inserts, 1)


if __name__ == "__main__":
    unittest.main()
