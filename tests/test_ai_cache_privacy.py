"""
test_ai_cache_privacy.py — P0-1: bir foydalanuvchining profilga bog'liq AI javobi
boshqa foydalanuvchiga keshdan ko'rsatilmasligi kerak.

Haqiqiy Telegram, Gemini yoki production bazaga murojaat qilinmaydi:
medicine_db vaqtinchalik SQLite faylga yo'naltiriladi.
"""
import asyncio
import os
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402
import medicine_db  # noqa: E402
import purge_ai_chat_cache  # noqa: E402

USER_A = 900000101
USER_B = 900000102
QUESTION = "Kechasi yo'talim kuchayadi, nima qilsam bo'ladi?"
PRIVATE_ANSWER = "Sizda penitsillinga allergiya va qandli diabet borligi uchun..."


class AiCachePrivacyTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.patches = [
            mock.patch.object(medicine_db, "DB_TYPE", "sqlite"),
            mock.patch.object(medicine_db, "sqlite3", sqlite3, create=True),
            mock.patch.object(medicine_db, "_get_conn", lambda: sqlite3.connect(self.db_path)),
        ]
        for p in self.patches:
            p.start()
        medicine_db._cache.clear()
        medicine_db.init_medicine_db()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        medicine_db._cache.clear()
        os.remove(self.db_path)

    def _make_message(self, user_id, text):
        msg = mock.MagicMock()
        msg.text = text
        msg.from_user = SimpleNamespace(id=user_id)
        msg.chat = SimpleNamespace(id=user_id)
        msg.bot = mock.MagicMock()
        msg.bot.send_chat_action = mock.AsyncMock()
        msg.answer = mock.AsyncMock(return_value=mock.MagicMock())
        msg.reply = mock.AsyncMock()
        return msg

    def _insert_old_cache_row(self, response_type):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO ai_response_cache (query_normalized, query_original, response_text, "
                "response_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (medicine_db.normalize_query(QUESTION), QUESTION, PRIVATE_ANSWER,
                 response_type, "2026-11-01", "2026-11-01"),
            )
            conn.commit()
        finally:
            conn.close()

    def _cache_rows(self):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT response_type FROM ai_response_cache").fetchall()
        finally:
            conn.close()

    def test_user_b_does_not_get_user_a_answer(self):
        """A profil bilan savol beradi → B o'sha savolni yozsa find_medicine found=False."""
        msg_a = self._make_message(USER_A, QUESTION)
        profile = {"allergies": "penitsillin", "chronic_diseases": "qandli diabet"}
        with mock.patch.object(bot.database, "try_consume_free_ai", return_value=True), \
             mock.patch.object(bot.database, "get_medical_profile", return_value=profile), \
             mock.patch.object(bot, "_build_profile_context", return_value="\nProfil: allergiya"), \
             mock.patch.object(bot, "stream_gemini_to_message",
                               new=mock.AsyncMock(return_value=PRIVATE_ANSWER)) as stream:
            asyncio.run(bot.handle_ai_chat(msg_a, mock.MagicMock()))

        stream.assert_awaited_once()  # AI haqiqatan chaqirildi
        self.assertEqual(self._cache_rows(), [])  # hech narsa keshlanmadi

        result_b = medicine_db.find_medicine(QUESTION)
        self.assertFalse(result_b["found"])
        self.assertNotIn(PRIVATE_ANSWER, str(result_b))

    def test_old_ai_chat_rows_are_never_served(self):
        """Bazada eski 'ai_chat' yozuvi qolgan bo'lsa ham u qaytarilmaydi."""
        self._insert_old_cache_row("ai_chat")
        result = medicine_db.find_medicine(QUESTION)
        self.assertFalse(result["found"])

    def test_purge_script_deletes_only_ai_chat(self):
        self._insert_old_cache_row("ai_chat")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO ai_response_cache (query_normalized, query_original, response_text, "
                "response_type, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("boshqa", "boshqa", "umumiy", "general", "2026-11-01", "2026-11-01"),
            )
            conn.commit()
        finally:
            conn.close()

        deleted = purge_ai_chat_cache.purge_ai_chat_cache()
        self.assertEqual(deleted, 1)
        self.assertEqual(self._cache_rows(), [("general",)])

    def test_real_medicine_still_found(self):
        """Tuzatish oddiy dori qidiruvini buzmagan."""
        result = medicine_db.find_medicine("Paratsetamol")
        self.assertTrue(result["found"])


if __name__ == "__main__":
    unittest.main()
