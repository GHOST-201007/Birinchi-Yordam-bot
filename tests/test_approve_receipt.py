"""Mock tests for database.approve_receipt_and_grant (atomic receipt + premium grant).

No real DB: database.get_connection is replaced by an in-memory fake that models
manual_receipts + users and honours commit/rollback (changes are staged until commit).
"""
import copy
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://stub:stub@127.0.0.1:1/stub")

import database  # noqa: E402


class FakeDB:
    def __init__(self):
        self.committed = {
            "receipts": {"tok1": {"status": "pending", "user_id": 111}},
            "users": {111: {"premium_type": "free", "premium_expires_at": None, "is_premium": 0}},
        }
        self.fail_on = None          # substring of SQL that raises
        self.commit_count = 0
        self.rollback_count = 0
        self.connections_opened = 0
        self.connections_closed = 0
        self.fail_commit = False


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._row = None

    def execute(self, sql, params=()):
        db = self.conn.db
        if db.fail_on and db.fail_on in sql:
            raise RuntimeError("simulated SQL error")
        s = self.conn.staged
        if sql.startswith("SELECT status, user_id FROM manual_receipts"):
            r = s["receipts"].get(params[0])
            self._row = (r["status"], r["user_id"]) if r else None
        elif sql.startswith("UPDATE manual_receipts SET status = 'approved'"):
            s["receipts"][params[0]]["status"] = "approved"
        elif sql.startswith("SELECT premium_expires_at, premium_type FROM users"):
            u = s["users"].get(params[0])
            self._row = (u["premium_expires_at"], u["premium_type"]) if u else None
        elif sql.startswith("UPDATE users SET is_premium = 1"):
            final_type, until, _until2, uid = params
            u = s["users"][uid]
            u.update(premium_type=final_type, premium_expires_at=until, is_premium=1)
        else:
            raise AssertionError("unexpected SQL: " + sql)

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.staged = copy.deepcopy(db.committed)
        db.connections_opened += 1

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        if self.db.fail_commit:
            raise RuntimeError("simulated commit failure")
        self.db.committed = copy.deepcopy(self.staged)
        self.db.commit_count += 1

    def rollback(self):
        self.staged = copy.deepcopy(self.db.committed)
        self.db.rollback_count += 1

    def close(self):
        self.db.connections_closed += 1


class ApproveReceiptTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self._orig = database.get_connection
        database.get_connection = lambda: FakeConn(self.db)

    def tearDown(self):
        database.get_connection = self._orig

    def test_receipt_and_premium_in_single_transaction(self):
        self.assertTrue(database.approve_receipt_and_grant(111, "tok1"))
        self.assertEqual(self.db.connections_opened, 1, "grant must reuse the same connection")
        self.assertEqual(self.db.commit_count, 1, "exactly one commit")
        self.assertEqual(self.db.committed["receipts"]["tok1"]["status"], "approved")
        u = self.db.committed["users"][111]
        self.assertEqual(u["is_premium"], 1)
        self.assertEqual(u["premium_type"], "pro")
        self.assertEqual(self.db.connections_closed, self.db.connections_opened)

    def test_user_id_mismatch_rejected(self):
        self.assertFalse(database.approve_receipt_and_grant(999, "tok1"))
        self.assertEqual(self.db.committed["receipts"]["tok1"]["status"], "pending")
        self.assertEqual(self.db.committed["users"][111]["is_premium"], 0)
        self.assertEqual(self.db.commit_count, 0)
        self.assertEqual(self.db.connections_closed, self.db.connections_opened)

    def test_unknown_token_rejected(self):
        self.assertFalse(database.approve_receipt_and_grant(111, "nope"))
        self.assertEqual(self.db.commit_count, 0)

    def test_sql_error_rolls_back_everything(self):
        self.db.fail_on = "UPDATE users SET is_premium"
        self.assertFalse(database.approve_receipt_and_grant(111, "tok1"))
        self.assertEqual(self.db.committed["receipts"]["tok1"]["status"], "pending")
        self.assertEqual(self.db.committed["users"][111]["is_premium"], 0)
        self.assertGreaterEqual(self.db.rollback_count, 1)
        self.assertEqual(self.db.connections_closed, self.db.connections_opened)

    def test_commit_failure_leaves_no_partial_grant(self):
        self.db.fail_commit = True
        self.assertFalse(database.approve_receipt_and_grant(111, "tok1"))
        self.assertEqual(self.db.committed["receipts"]["tok1"]["status"], "pending")
        self.assertEqual(self.db.committed["users"][111]["is_premium"], 0)

    def test_second_approval_does_not_grant_again(self):
        self.assertTrue(database.approve_receipt_and_grant(111, "tok1"))
        until_first = self.db.committed["users"][111]["premium_expires_at"]
        self.assertFalse(database.approve_receipt_and_grant(111, "tok1"))
        self.assertEqual(self.db.committed["users"][111]["premium_expires_at"], until_first)

    def test_grant_premium_days_default_still_commits_itself(self):
        database.grant_premium_days(111, 3, premium_type="pro")
        self.assertEqual(self.db.commit_count, 1)
        self.assertEqual(self.db.committed["users"][111]["is_premium"], 1)
        self.assertEqual(self.db.connections_closed, self.db.connections_opened)


if __name__ == "__main__":
    unittest.main()
