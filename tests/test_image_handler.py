"""
test_image_handler.py - bot.handle_image uchun mock asosidagi unit testlar.
Haqiqiy Telegram, Gemini API yoki ma'lumotlar bazasiga murojaat qilinmaydi.
"""
import asyncio
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot  # noqa: E402  (polling faqat main() ichida ishga tushadi)

TEST_USER_ID = 900000001  # soxta ID
FAKE_IMAGE = b"\xff\xd8\xff\xe0FAKEJPEG"


def make_response(text):
    return SimpleNamespace(text=text)


class ImageHandlerTestBase(unittest.TestCase):
    def setUp(self):
        # --- Telegram mocklari ---
        self.status_msg = mock.MagicMock()
        self.status_msg.edit_text = mock.AsyncMock()

        self.tg_bot = mock.MagicMock()
        self.tg_bot.get_file = mock.AsyncMock(return_value=SimpleNamespace(file_path="photos/x.jpg"))
        self.tg_bot.download_file = mock.AsyncMock(side_effect=lambda *_a, **_k: io.BytesIO(FAKE_IMAGE))
        self.tg_bot.send_chat_action = mock.AsyncMock()

        self.message = mock.MagicMock()
        self.message.from_user = SimpleNamespace(id=TEST_USER_ID)
        self.message.chat = SimpleNamespace(id=TEST_USER_ID)
        self.message.photo = [SimpleNamespace(file_id="small"), SimpleNamespace(file_id="big")]
        self.message.caption = "Qo'limdagi kuyish"
        self.message.bot = self.tg_bot
        self.message.answer = mock.AsyncMock(return_value=self.status_msg)

        # --- Gemini mocki ---
        self.generate = mock.AsyncMock(return_value=make_response("**Javob** matni"))
        self.gemini = mock.MagicMock()
        self.gemini.aio.models.generate_content = self.generate

        # --- DB mocklari (default: bepul limit sarflanadi) ---
        self.try_free = mock.MagicMock(return_value=True)
        self.try_daily = mock.MagicMock(return_value=False)
        self.refund_free = mock.MagicMock()
        self.refund_daily = mock.MagicMock()
        self.get_profile = mock.MagicMock(return_value=None)
        self.upsell = mock.AsyncMock()

        self.models = ["model-a", "model-b"]
        self._patchers = [
            mock.patch.object(bot, "gemini_client", self.gemini),
            mock.patch.object(bot, "premium_upsell", self.upsell),
            mock.patch.object(bot, "_build_profile_context", return_value=""),
            mock.patch.object(bot.database, "try_consume_free_ai", self.try_free),
            mock.patch.object(bot.database, "try_consume_daily_request", self.try_daily),
            mock.patch.object(bot.database, "refund_free_ai", self.refund_free),
            mock.patch.object(bot.database, "refund_daily_request", self.refund_daily),
            mock.patch.object(bot.database, "get_medical_profile", self.get_profile),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in reversed(self._patchers):
            p.stop()

    def run_handler(self, models=None):
        models = self.models if models is None else models
        with mock.patch.object(bot, "GEMINI_MULTIMODAL_MODELS", models):
            asyncio.run(asyncio.wait_for(bot.handle_image(self.message, mock.MagicMock()), timeout=5))

    def edit_texts(self):
        return [c.args[0] if c.args else c.kwargs.get("text") for c in self.status_msg.edit_text.call_args_list]


class TestImageHandler(ImageHandlerTestBase):
    # A
    def test_a_success(self):
        self.run_handler()
        self.tg_bot.get_file.assert_awaited_once_with("big")
        self.generate.assert_awaited_once()
        kwargs = self.generate.await_args.kwargs
        self.assertEqual(kwargs["model"], "model-a")
        part = kwargs["contents"][0]
        self.assertEqual(part.inline_data.data, FAKE_IMAGE, "Rasm baytlari Gemini'ga uzatilmadi")
        self.assertEqual(part.inline_data.mime_type, "image/jpeg")
        self.assertIn("Qo'limdagi kuyish", kwargs["contents"][1])
        self.status_msg.edit_text.assert_awaited_once()
        self.assertIn("Rasm tahlili natijasi", self.edit_texts()[0])
        self.assertIn("<b>Javob</b>", self.edit_texts()[0])
        self.refund_free.assert_not_called()
        self.refund_daily.assert_not_called()

    # B
    def test_b_all_models_fail(self):
        self.generate.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        self.run_handler()
        self.assertEqual(self.generate.await_count, 2, "Har bir model sinalishi kerak")
        self.refund_free.assert_called_once_with(TEST_USER_ID)
        self.refund_daily.assert_not_called()
        self.assertIn("imkoni bo'lmadi", self.edit_texts()[-1])

    def test_b2_non_retryable_error_stops_and_refunds_once(self):
        self.generate.side_effect = Exception("500 internal")
        self.run_handler()
        self.assertEqual(self.generate.await_count, 1)
        self.refund_free.assert_called_once_with(TEST_USER_ID)

    # C
    def test_c_empty_model_list(self):
        self.run_handler(models=[])
        self.generate.assert_not_awaited()
        self.refund_free.assert_called_once_with(TEST_USER_ID)
        self.assertIn("imkoni bo'lmadi", self.edit_texts()[-1])

    # D
    def test_d_empty_and_none_response(self):
        for empty in ("", None):
            with self.subTest(text=empty):
                self.generate.reset_mock(return_value=True, side_effect=True)
                self.generate.return_value = make_response(empty)
                self.refund_free.reset_mock()
                self.status_msg.edit_text.reset_mock()
                self.run_handler()
                self.assertEqual(self.generate.await_count, 2)
                self.refund_free.assert_called_once_with(TEST_USER_ID)
                self.assertIn("imkoni bo'lmadi", self.edit_texts()[-1])

    # E
    def test_e_edit_text_fails_on_result(self):
        self.status_msg.edit_text.side_effect = [Exception("Bad Request: can't parse entities"), None]
        self.run_handler()
        # BUG-002 tuzatilgach: HTML parse xatosida plain-text fallback ishlaydi, javob yo'qolmaydi
        self.assertEqual(self.generate.await_count, 1)
        self.refund_free.assert_not_called()
        self.assertEqual(self.status_msg.edit_text.await_count, 2)
        self.assertIsNone(self.status_msg.edit_text.call_args_list[-1].kwargs.get("parse_mode"))
        self.assertIn("Rasm tahlili natijasi", self.edit_texts()[-1])
        self.assertIn("Javob", self.edit_texts()[-1])
        self.message.answer.assert_awaited_once()

    def test_e2_edit_text_both_html_and_plain_fail_refunds(self):
        self.status_msg.edit_text.side_effect = [
            Exception("Bad Request: can't parse entities"),
            Exception("Telegram network failure"),
            None,
        ]
        self.run_handler()
        self.assertEqual(self.generate.await_count, 1)
        self.assertEqual(self.refund_free.call_count, 1)
        self.assertEqual(self.status_msg.edit_text.await_count, 3)
        self.assertIn("imkoni bo'lmadi", self.edit_texts()[-1])

    def test_e3_long_response_chunked_safely(self):
        para1 = "Birinchi qism: " + ("A" * 2500)
        para2 = "Ikkinchi qism: " + ("B" * 2500)
        long_text = para1 + "\n\n" + para2
        self.generate.return_value = make_response(long_text)
        self.run_handler()

        self.assertEqual(self.generate.await_count, 1)
        self.refund_free.assert_not_called()
        # Birinchi bo'lak status_msg.edit_text orqali yuboriladi
        self.assertEqual(self.status_msg.edit_text.await_count, 1)
        first_chunk = self.edit_texts()[0]
        self.assertLessEqual(len(first_chunk), 4096)
        self.assertIn("Birinchi qism:", first_chunk)
        # Ikkinchi bo'lak message.answer orqali yuboriladi (1-chaqiruv status_msg edi, 2-chaqiruv 2-bo'lak)
        self.assertEqual(self.message.answer.await_count, 2)
        second_chunk = self.message.answer.call_args_list[1].args[0]
        self.assertLessEqual(len(second_chunk), 4096)
        self.assertIn("Ikkinchi qism:", second_chunk)

    def test_e4_long_response_html_error_fallback_no_duplicate(self):
        long_text = ("Salom tibbiy tahlil. " * 250).strip()  # > 5000 belgi
        self.generate.return_value = make_response(long_text)
        # 1-bo'lakda HTML parse xato beradi, plain-text fallback muvaffaqiyatli o'tadi
        self.status_msg.edit_text.side_effect = [Exception("Bad Request: can't parse entities"), None]
        self.run_handler()

        self.assertEqual(self.generate.await_count, 1)
        self.refund_free.assert_not_called()
        self.assertEqual(self.status_msg.edit_text.await_count, 2)
        self.assertIsNone(self.status_msg.edit_text.call_args_list[-1].kwargs.get("parse_mode"))
        # 2-bo'lak faqat bir marta message.answer orqali yuboriladi (1-si boshlang'ich status_msg)
        self.assertEqual(self.message.answer.await_count, 2)

    def test_e5_chunk_text_helper(self):
        text = ("Qator " + "x" * 100 + "\n") * 60
        chunks = bot.chunk_text(text, max_len=4096)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 4096)
            self.assertGreater(len(c), 0)

    # F
    def test_f_refund_fails_after_gemini_failure(self):
        self.generate.side_effect = Exception("500 internal")
        self.refund_free.side_effect = Exception("DB down")
        self.run_handler()  # istisno tashqariga chiqmasligi kerak
        self.assertEqual(self.refund_free.call_count, 1, "Refund qayta urinilmasligi kerak")
        self.assertIn("qayta ishlashda xatolik", self.edit_texts()[-1])

    def test_f2_refund_fails_after_download_failure(self):
        # Rasm yuklashda xato + refund xatosi: refund outer except ichida, try'siz chaqiriladi
        self.tg_bot.download_file.side_effect = Exception("network")
        self.refund_free.side_effect = Exception("DB down")
        try:
            self.run_handler()
        except Exception as e:
            self.fail(f"Handler istisnoni tashqariga chiqardi: {e!r} "
                      f"(bot.py handle_image: except blokidagi refund_once() himoyalanmagan)")
        self.assertTrue(self.edit_texts(), "Foydalanuvchiga xato xabari yuborilmadi")

    # G
    def test_g1_free_limit_refunds_only_free(self):
        self.generate.side_effect = Exception("500")
        self.run_handler()
        self.refund_free.assert_called_once()
        self.refund_daily.assert_not_called()
        self.try_daily.assert_not_called()

    def test_g2_daily_limit_refunds_only_daily(self):
        self.try_free.return_value = False
        self.try_daily.return_value = True
        self.generate.side_effect = Exception("500")
        self.run_handler()
        self.refund_daily.assert_called_once_with(TEST_USER_ID)
        self.refund_free.assert_not_called()

    def test_g3_no_limit_upsell_no_download(self):
        self.try_free.return_value = False
        self.try_daily.return_value = False
        self.run_handler()
        self.upsell.assert_awaited_once_with(self.message)
        self.tg_bot.get_file.assert_not_awaited()
        self.tg_bot.download_file.assert_not_awaited()
        self.generate.assert_not_awaited()
        self.refund_free.assert_not_called()
        self.refund_daily.assert_not_called()

    def test_h1_html_escape_expansion_stays_under_4096(self):
        # '&' * 2000 HTML escape bo'lganda '&amp;' * 2000 = 10000 belgi bo'ladi;
        # har bir yuborilgan xabar 4096 belgidan oshmasligi shart
        self.generate.return_value = make_response("&" * 2000)
        self.run_handler()
        self.refund_free.assert_not_called()
        for t in self.edit_texts():
            self.assertLessEqual(len(t), 4096)
        for call in self.message.answer.call_args_list:
            sent = call.args[0] if call.args else call.kwargs.get("text", "")
            self.assertLessEqual(len(sent), 4096)

    def test_h2_partial_delivery_later_chunk_fails_no_refund_and_notifies(self):
        long_text = ("Birinchi qism: " + "A" * 2500) + "\n\n" + ("Ikkinchi qism: " + "B" * 2500)
        self.generate.return_value = make_response(long_text)
        # message.answer: 1-chaqiruv status_msg, 2-chaqiruv (2-bo'lak HTML) xato, 3-chaqiruv (2-bo'lak plain) xato, 4-chaqiruv ogohlantirish
        self.message.answer.side_effect = [
            self.status_msg,
            Exception("Bad Request: can't parse entities"),
            Exception("Bad Request: chat write forbidden"),
            mock.MagicMock(),
        ]
        self.run_handler()
        self.refund_free.assert_not_called()
        self.assertEqual(self.status_msg.edit_text.await_count, 1)
        last_answer = self.message.answer.call_args_list[-1].args[0]
        self.assertIn("Javobning davomi", last_answer)

    def test_h3_ambiguous_timeout_error_no_duplicate_and_no_refund(self):
        self.status_msg.edit_text.side_effect = TimeoutError("Request timeout")
        self.run_handler()
        # Noaniq timeout xatosida plain-text qayta yuborilmaydi (dublikat oldini olish) va refund qilinmaydi
        self.assertEqual(self.status_msg.edit_text.await_count, 1)
        self.refund_free.assert_not_called()

    def test_h4_message_not_modified_treated_as_delivered(self):
        self.status_msg.edit_text.side_effect = Exception("Bad Request: message is not modified")
        self.run_handler()
        self.assertEqual(self.status_msg.edit_text.await_count, 1)
        self.refund_free.assert_not_called()

    def test_h5_db_error_during_try_consume_handled_gracefully(self):
        self.try_free.side_effect = RuntimeError("DB connection pool exhausted")
        self.run_handler()
        self.generate.assert_not_awaited()
        self.refund_free.assert_not_called()
        self.message.answer.assert_awaited_once()
        self.assertIn("texnik xatolik", self.message.answer.call_args.args[0])

    def test_h6_voice_handler_no_quota_leak_when_gemini_unconfigured(self):
        self.message.caption = None
        self.message.voice = SimpleNamespace(file_id="voice_123")
        with mock.patch.object(bot, "gemini_client", None):
            asyncio.run(asyncio.wait_for(bot.handle_voice(self.message), timeout=5))
        self.try_free.assert_not_called()
        self.try_daily.assert_not_called()
        self.refund_free.assert_not_called()


if __name__ == "__main__":
    unittest.main()
