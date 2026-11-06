"""
test_wipe_medical_data.py — P2-8: barcha tibbiy ma'lumotlarni to'liq o'chirish (tasdiqlash bilan).

Haqiqiy baza yoki Telegram ishlatilmaydi.
"""
import asyncio
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402
import database  # noqa: E402

USER_ID = 900000801


class RecordingCursor:
    def __init__(self):
        self.executed = []
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.executed.append((" ".join(sql.split()), params))
        self.rowcount = 2


class WipeDatabaseTest(unittest.TestCase):
    def test_wipes_all_medical_tables_in_one_transaction(self):
        cursor = RecordingCursor()
        conn = mock.MagicMock()

        @contextlib.contextmanager
        def fake_managed():
            yield conn, cursor

        with mock.patch.object(database, "_managed_cursor", fake_managed):
            result = database.wipe_user_medical_data(USER_ID)

        sqls = [s for s, _ in cursor.executed]
        self.assertTrue(any(s.startswith("UPDATE users SET blood_group = NULL") and "allergies = NULL" in s for s in sqls))
        for table in ("reminders", "engagement_logs", "user_interests"):
            self.assertIn(f"DELETE FROM {table} WHERE user_id = %s", sqls)
        # Hisob/premium/to'lovlarga tegilmaydi
        self.assertFalse(any("payment_transactions" in s or "DELETE FROM users" in s for s in sqls))
        self.assertTrue(all(p == (USER_ID,) for _, p in cursor.executed))
        conn.commit.assert_called_once()
        self.assertEqual(result, {"reminders": 2, "engagement_logs": 2, "user_interests": 2})


class WipeHandlersTest(unittest.TestCase):
    def make_callback(self, data):
        cb = mock.MagicMock()
        cb.data = data
        cb.from_user = SimpleNamespace(id=USER_ID)
        cb.answer = mock.AsyncMock()
        cb.message.answer = mock.AsyncMock()
        cb.message.edit_text = mock.AsyncMock()
        return cb

    def test_profile_menu_has_wipe_button(self):
        msg = mock.MagicMock()
        msg.from_user = SimpleNamespace(id=USER_ID)
        msg.answer = mock.AsyncMock()
        with mock.patch.object(bot.database, "get_medical_profile", return_value=None):
            asyncio.run(bot.medical_profile_menu(msg))
        markup = msg.answer.await_args.kwargs["reply_markup"]
        datas = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn("wipe_medical", datas)

    def test_ask_does_not_delete(self):
        cb = self.make_callback("wipe_medical")
        with mock.patch.object(bot.database, "wipe_user_medical_data") as wipe:
            asyncio.run(bot.wipe_medical_ask(cb))
        wipe.assert_not_called()
        markup = cb.message.answer.await_args.kwargs["reply_markup"]
        datas = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertEqual(datas, ["wipe_medical_yes", "wipe_medical_no"])

    def test_confirm_deletes(self):
        cb = self.make_callback("wipe_medical_yes")
        with mock.patch.object(bot.database, "wipe_user_medical_data", return_value={}) as wipe:
            asyncio.run(bot.wipe_medical_confirm(cb))
        wipe.assert_called_once_with(USER_ID)
        self.assertIn("o'chirildi", cb.message.edit_text.await_args.args[0])

    def test_cancel_does_not_delete(self):
        cb = self.make_callback("wipe_medical_no")
        with mock.patch.object(bot.database, "wipe_user_medical_data") as wipe:
            asyncio.run(bot.wipe_medical_cancel(cb))
        wipe.assert_not_called()

    def test_db_error_reported(self):
        cb = self.make_callback("wipe_medical_yes")
        with mock.patch.object(bot.database, "wipe_user_medical_data", side_effect=RuntimeError("db")):
            asyncio.run(bot.wipe_medical_confirm(cb))
        self.assertIn("xatolik", cb.message.edit_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
