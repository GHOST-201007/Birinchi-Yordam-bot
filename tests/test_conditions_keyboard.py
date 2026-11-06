"""
test_conditions_keyboard.py — P1-4: YO'R (reanimatsiya) tugmasi birinchi qatorda va ishlaydi.
"""
import asyncio
import os
import sys
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402
import data  # noqa: E402


class ConditionsKeyboardTest(unittest.TestCase):
    def test_cpr_button_first_row_alone(self):
        rows = bot.get_conditions_keyboard().inline_keyboard
        self.assertEqual(len(rows[0]), 1)
        self.assertEqual(rows[0][0].callback_data, "aid_reanimatsiya")
        self.assertIn("YO'R", rows[0][0].text)

    def test_every_aid_button_has_data(self):
        for row in bot.get_conditions_keyboard().inline_keyboard:
            for button in row:
                if button.callback_data.startswith("aid_"):
                    key = button.callback_data[len("aid_"):]
                    self.assertIn(key, data.FIRST_AID_DATA, button.callback_data)

    def test_cpr_callback_shows_text(self):
        callback = mock.MagicMock()
        callback.data = "aid_reanimatsiya"
        callback.message.edit_text = mock.AsyncMock()
        callback.answer = mock.AsyncMock()
        asyncio.run(bot.process_aid_callback(callback))
        text = callback.message.edit_text.await_args.args[0]
        self.assertIn("reanimatsiya", text)
        self.assertNotIn("Ma'lumot topilmadi", text)


if __name__ == "__main__":
    unittest.main()
