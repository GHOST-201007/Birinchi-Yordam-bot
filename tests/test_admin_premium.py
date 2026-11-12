"""
test_admin_premium.py — admin /premium paneli: ro'yxat, qidiruv, user kartasi, Premium berish/olib tashlash.

DB mantig'i HAQIQIY SQL bilan (tests/sqlite_db.py); Telegram (bot.send_message / get_chat) soxta.
"""
import asyncio
import datetime as dt
import inspect
import os
import sys
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

from aiogram import types  # noqa: E402

import bot as bot_mod  # noqa: E402
import database  # noqa: E402
from tests.sqlite_db import SqliteDB  # noqa: E402

ADMIN = 111_000_111
STRANGER = 222_000_222
EVIL = '<b>x</b><a href="http://e">'
NOW = database.get_uz_now


def parse(value):
    return database._to_uz_datetime(value)


def buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def find(markup, text):
    matches = [b for b in buttons(markup) if b.text == text]
    assert len(matches) == 1, (text, [b.text for b in buttons(markup)])
    return matches[0].callback_data


def texts(markup):
    return [b.text for b in buttons(markup)]


def future(**delta):
    return (NOW() + dt.timedelta(**delta)).isoformat()


class PanelCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SqliteDB()
        self.addCleanup(self.db.close)
        self.fake_bot = mock.MagicMock()
        self.fake_bot.send_message = mock.AsyncMock()
        self.fake_bot.get_chat = mock.AsyncMock()
        self.fake_bot.set_chat_menu_button = mock.AsyncMock()        # B9: shaxsiy menyu tugmasi (fonda)
        patches = [
            self.db.patched(),
            mock.patch.object(bot_mod, "ADMIN_ID", ADMIN),
            mock.patch.object(bot_mod, "bot", self.fake_bot),
            mock.patch.dict(os.environ, {"MINI_APP_URL": "https://app.example/index.html"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        bot_mod._pm_recent.clear()
        bot_mod._menu_premium_done.clear()
        bot_mod._menu_reset_done.clear()
        bot_mod._premium_menu_cache.clear()
        self.msg_seq = 1000
        self.state = mock.MagicMock()
        self.state.set_state = mock.AsyncMock()
        self.state.clear = mock.AsyncMock()

    # ---- yordamchilar ---------------------------------------------------------------------
    def add_user(self, uid, name="Ali", username=None, **cols):
        cols.setdefault("registered_at", "2026-01-01T00:00:00+05:00")
        self.db.add_user(uid, full_name=name, username=username, **cols)

    def row(self, uid):
        return self.db.row(uid)

    def callback(self, data, user_id=ADMIN, message_id=None):
        cb = mock.MagicMock()
        cb.data = data
        cb.from_user.id = user_id
        cb.message.chat.id = user_id
        cb.message.message_id = message_id or self.msg_seq
        cb.message.edit_text = mock.AsyncMock()
        cb.answer = mock.AsyncMock()
        return cb

    async def press(self, data, user_id=ADMIN, message_id=None):
        self.msg_seq += 1
        cb = self.callback(data, user_id, message_id)
        await bot_mod.cb_premium_panel(cb, self.state)
        return cb

    def edited(self, cb):
        cb.message.edit_text.assert_awaited()
        args, kwargs = cb.message.edit_text.await_args
        return args[0], kwargs.get("reply_markup")

    def alert(self, cb):
        cb.answer.assert_awaited()
        return cb.answer.await_args.args[0] if cb.answer.await_args.args else ""

    def confirm_data(self, uid, tier, days, mode="s", reason="-", pg=0):
        code = bot_mod.PM_TIER_CODES[tier]
        return bot_mod._pm_cb("c", uid, pg, code, days, mode, reason)

    async def grant(self, uid, tier, days, mode="s", reason="-"):
        return await self.press(self.confirm_data(uid, tier, days, mode, reason))

    def assert_expires_in(self, uid, days, base=None, tol=120):
        expected = (base or NOW()) + dt.timedelta(days=days)
        actual = parse(self.row(uid)["premium_expires_at"])
        self.assertLess(abs((actual - expected).total_seconds()), tol, (actual, expected))


# ───────────────────────────── xavfsizlik ─────────────────────────────
class AdminGateTest(PanelCase):
    async def test_every_step_rejects_non_admin_and_changes_nothing(self):
        self.add_user(5, name="Vali")
        samples = ["pm:l:0", "pm:s", "pm:u:5:0", "pm:g:5:0", "pm:t:5:0:p", "pm:d:5:0:p:7", "pm:m:5:0:p:7:n",
                   "pm:r:5:0:p:7:n:0", "pm:c:5:0:p:7:n:0", "pm:c:5:0:p:7:s:-", "pm:c:5:0:u:u:s:-", "pm:x:5:0",
                   "pm:y:5:0:n", "pm:z:5:0:s"]
        for data in samples:
            with self.subTest(data=data):
                cb = await self.press(data, user_id=STRANGER)
                cb.answer.assert_awaited_once_with("❌ Siz admin emassiz!", show_alert=True)
                cb.message.edit_text.assert_not_awaited()
        self.assertEqual(self.row(5)["is_premium"], 0)
        self.fake_bot.send_message.assert_not_awaited()
        self.state.set_state.assert_not_awaited()

    async def test_search_input_rejects_non_admin(self):
        self.add_user(5, name="Vali")
        message = mock.MagicMock()
        message.from_user.id = STRANGER
        message.text = "5"
        message.answer = mock.AsyncMock()
        with mock.patch.object(bot_mod.database, "admin_find_user") as find_user:
            await bot_mod.pm_search_input(message, self.state)
        find_user.assert_not_called()
        message.answer.assert_awaited_once_with("❌ Siz admin emassiz!")

    async def test_unset_admin_id_means_nobody_is_admin(self):
        for unset in (0, None, ""):
            with self.subTest(admin_id=unset), mock.patch.object(bot_mod, "ADMIN_ID", unset):
                self.assertFalse(bot_mod._is_admin(0))
                self.assertFalse(bot_mod._is_admin(STRANGER))

    async def test_ordinary_user_still_gets_the_normal_premium_page(self):
        message = mock.MagicMock()
        message.from_user.id = STRANGER
        message.answer = mock.AsyncMock()
        with mock.patch.object(bot_mod, "_show_premium_page", mock.AsyncMock()) as page:
            await bot_mod.cmd_premium(message, self.state)
        page.assert_awaited_once_with(message)
        message.answer.assert_not_awaited()

    async def test_old_callbacks_and_helpers_are_gone(self):
        for name in ("cb_pm_toggle", "cb_pm_refresh", "_build_premium_list_text", "_build_premium_list_keyboard"):
            self.assertFalse(hasattr(bot_mod, name), name)
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("pm_toggle_", src)
        self.assertNotIn("pm_refresh", src)
        cb = await self.press("pm_toggle_5")                    # eski format endi hech qaysi handlerga mos emas
        self.assertFalse(bot_mod.F.data.startswith("pm:") and "pm_toggle_5".startswith("pm:"))
        cb.message.edit_text.assert_not_awaited()

    async def test_malformed_callback_data_is_rejected_without_changes(self):
        self.add_user(5)
        for data in ("pm:", "pm:zz", "pm:l:abc", "pm:u:x:0", "pm:g:5", "pm:t:5:0:q", "pm:d:5:0:p:2", "pm:m:5:0:p:7:x",
                     "pm:r:5:0:p:7:n:9", "pm:r:5:0:p:7:n:x", "pm:c:5:0:p:7:s:3", "pm:c:5:0:p:7:n:-", "pm:c:5:0:p:7:s",
                     "pm:y:5:0:q", "pm:z:5:0", "pm:c:5:0:p:7:s:-:extra"):
            with self.subTest(data=data):
                cb = await self.press(data)
                self.assertIn("Noto'g'ri so'rov", self.alert(cb))
                cb.message.edit_text.assert_not_awaited()
        self.assertEqual(self.row(5)["is_premium"], 0)
        self.fake_bot.send_message.assert_not_awaited()

    async def test_callback_data_never_exceeds_64_bytes(self):
        big = {"user_id": 9_999_999_999_999_999, "full_name": "Ali", "username": "ali", "active": True, "tier": "plus",
               "unlimited": False, "expires": NOW(), "score": 1}
        pg = 99_999
        views = [bot_mod._pm_card_view(big, pg), bot_mod._pm_tier_view(big, pg),
                 bot_mod._pm_days_view(big, pg, "ultra"), bot_mod._pm_mode_view(big, pg, "ultra", "90"),
                 bot_mod._pm_reason_view(big, pg, "ultra", "u"), bot_mod._pm_remove_mode_view(big, pg),
                 bot_mod._pm_remove_confirm_view(big, pg, "n"), bot_mod._pm_result_markup(big["user_id"], pg)]
        for mode, reason in (("n", 4), ("s", bot_mod.PM_NO_REASON)):
            views.append(bot_mod._pm_confirm_view(big, pg, "ultra", "90", mode, reason))
        for item in views:
            markup = item[1] if isinstance(item, tuple) else item
            for b in buttons(markup):
                self.assertLessEqual(len(b.callback_data.encode()), 64, b.callback_data)
                self.assertTrue(b.callback_data.startswith("pm:"))

    async def test_unexpected_error_does_not_leak_details(self):
        with mock.patch.object(bot_mod.database, "admin_users_page", side_effect=RuntimeError("SECRET-DB-DETAIL")):
            cb = await self.press("pm:l:0")
        self.assertIn("Xatolik", self.alert(cb))
        self.assertNotIn("SECRET-DB-DETAIL", self.alert(cb))


# ───────────────────────────── ro'yxat va sahifalash ─────────────────────────────
class ListTest(PanelCase):
    def fill(self, n, premium=None):
        premium = premium or {}
        base = dt.datetime(2026, 5, 1, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=5)))
        for i in range(1, n + 1):
            cols = {"registered_at": (base + dt.timedelta(minutes=i)).isoformat()}
            cols.update(premium.get(i, {}))
            self.add_user(i, name=f"User{i}", **cols)

    async def test_pagination_is_ten_per_page_newest_first(self):
        self.fill(25)
        sizes, first_names = [], []
        for page in (0, 1, 2):
            cb = await self.press(f"pm:l:{page}")
            text, markup = self.edited(cb)
            users = [b for b in buttons(markup) if b.callback_data.startswith("pm:u:")]
            sizes.append(len(users))
            first_names.append(users[0].text)
            self.assertIn(f"Sahifa: <b>{page + 1}/3</b>", text)
        self.assertEqual(sizes, [10, 10, 5])
        self.assertEqual(first_names[0], "👤 User25 — Oddiy")                 # eng yangi birinchi
        self.assertEqual(first_names[2], "👤 User5 — Oddiy")

    async def test_navigation_buttons_only_where_they_make_sense(self):
        self.fill(25)
        expected = {0: ["▶️"], 1: ["◀️", "▶️"], 2: ["◀️"]}
        for page, arrows in expected.items():
            cb = await self.press(f"pm:l:{page}")
            _, markup = self.edited(cb)
            self.assertEqual([t for t in texts(markup) if t in ("◀️", "▶️")], arrows)
            self.assertIn("🔍 Qidirish", texts(markup))
        _, markup = self.edited(await self.press("pm:l:1"))
        self.assertEqual(find(markup, "◀️"), "pm:l:0")
        self.assertEqual(find(markup, "▶️"), "pm:l:2")

    async def test_out_of_range_pages_are_clamped_without_error(self):
        self.fill(25)
        text, _ = self.edited(await self.press("pm:l:99"))
        self.assertIn("Sahifa: <b>3/3</b>", text)
        text, _ = self.edited(await self.press("pm:l:-5"))
        self.assertIn("Sahifa: <b>1/3</b>", text)

    async def test_boundaries_exact_multiples_and_empty_database(self):
        for n, pages in ((10, 1), (11, 2), (20, 2), (0, 1)):
            with self.subTest(users=n):
                self.db.close()
                self.db = SqliteDB()
                self.addCleanup(self.db.close)
                with self.db.patched():
                    self.fill(n)
                    text, markup = bot_mod._pm_list_view(await bot_mod._pm_load_list(0))
                    last_text, _ = bot_mod._pm_list_view(await bot_mod._pm_load_list(pages - 1))
                self.assertIn(f"Sahifa: <b>1/{pages}</b>", text)
                self.assertIn(f"Sahifa: <b>{pages}/{pages}</b>", last_text)
                self.assertEqual(sum(1 for b in buttons(markup) if b.callback_data.startswith("pm:u:")), min(n, 10))

    async def test_header_counts_total_and_only_active_premium_users(self):
        self.fill(6, {
            1: {"is_premium": 1, "premium_type": "pro", "premium_expires_at": future(days=3)},
            2: {"is_premium": 1, "premium_type": "ultra", "premium_expires_at": None},               # muddatsiz
            3: {"is_premium": 1, "premium_type": "plus", "premium_expires_at": future(days=30)},
            4: {"is_premium": 1, "premium_type": "pro", "premium_expires_at": future(days=-2)},     # muddati o'tgan
            5: {"is_premium": 1, "premium_type": "plus", "premium_expires_at": future(days=-1)},    # muddati o'tgan
        })
        text, markup = self.edited(await self.press("pm:l:0"))
        self.assertIn("Jami foydalanuvchilar: <b>6</b>", text)
        self.assertIn("Premium foydalanuvchilar: <b>3</b>", text)
        labels = {b.callback_data.split(":")[2]: b.text for b in buttons(markup) if b.callback_data.startswith("pm:u:")}
        self.assertEqual(labels["1"], "🌟 User1 — Pro")
        self.assertEqual(labels["2"], "🌟 User2 — Ultra ♾")
        self.assertEqual(labels["3"], "🌟 User3 — Plus")
        self.assertEqual(labels["4"], "👤 User4 — Oddiy")                                          # eskirgan flag
        self.assertEqual(labels["6"], "👤 User6 — Oddiy")

    async def test_only_database_users_are_listed(self):
        self.add_user(7, name="Bazada")
        _, markup = self.edited(await self.press("pm:l:0"))
        self.assertEqual([b.callback_data for b in buttons(markup) if b.callback_data.startswith("pm:u:")],
                         ["pm:u:7:0"])

    async def test_cmd_premium_shows_first_page_for_admin(self):
        self.fill(3)
        message = mock.MagicMock()
        message.from_user.id = ADMIN
        message.answer = mock.AsyncMock()
        await bot_mod.cmd_premium(message, self.state)
        text = message.answer.await_args.args[0]
        self.assertIn("Jami foydalanuvchilar: <b>3</b>", text)
        self.assertEqual(message.answer.await_args.kwargs["parse_mode"], "HTML")
        self.state.clear.assert_awaited()

    async def test_name_missing_in_db_is_resolved_from_telegram(self):
        self.add_user(8, name=None, username=None)
        self.fake_bot.get_chat.return_value = mock.MagicMock(first_name="Vali", last_name="Aliyev", username="vali")
        _, markup = self.edited(await self.press("pm:l:0"))
        self.assertEqual(texts(markup)[0], "👤 Vali Aliyev — Oddiy")
        self.assertEqual(self.row(8)["full_name"], "Vali Aliyev")                                  # keyingi safar so'ralmaydi

    async def test_long_names_are_shortened_on_buttons(self):
        self.add_user(9, name="A" * 80)
        _, markup = self.edited(await self.press("pm:l:0"))
        self.assertLessEqual(len(texts(markup)[0]), 40)


# ───────────────────────────── user kartasi ─────────────────────────────
class CardTest(PanelCase):
    async def test_card_for_ordinary_user(self):
        self.add_user(5, name="Vali", username="vali_u", medicine_score=42)
        text, markup = self.edited(await self.press("pm:u:5:0"))
        for part in ("Vali", "@vali_u", "<code>5</code>", "Oddiy", "<b>42</b>"):
            self.assertIn(part, text)
        self.assertEqual(texts(markup), ["🎁 Premium berish", "⬅️ Ro'yxatga"])                  # olib tashlash tugmasi yo'q
        self.assertEqual(find(markup, "⬅️ Ro'yxatga"), "pm:l:0")

    async def test_card_for_premium_user_shows_tier_and_tashkent_expiry(self):
        self.add_user(5, name="Vali", is_premium=1, premium_type="plus",
                      premium_expires_at="2026-12-25T14:30:00+05:00")
        with mock.patch.object(database, "get_uz_now",
                               return_value=dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=5)))):
            text, markup = self.edited(await self.press("pm:u:5:2"))
        self.assertIn("Plus", text)
        self.assertIn("25.12.2026 14:30", text)
        self.assertIn("Toshkent", text)
        self.assertEqual(texts(markup), ["🎁 Premium berish", "❌ Premiumni olib tashlash", "⬅️ Ro'yxatga"])
        self.assertEqual(find(markup, "⬅️ Ro'yxatga"), "pm:l:2")                                # qaytish sahifasi saqlanadi

    async def test_card_for_unlimited_user(self):
        self.add_user(5, is_premium=1, premium_type="ultra", premium_expires_at=None)
        text, markup = self.edited(await self.press("pm:u:5:0"))
        self.assertIn("Muddatsiz", text)
        self.assertIn("Ultra", text)
        self.assertIn("❌ Premiumni olib tashlash", texts(markup))

    async def test_card_for_expired_flag_counts_as_ordinary(self):
        self.add_user(5, is_premium=1, premium_type="pro", premium_expires_at=future(days=-3))
        text, markup = self.edited(await self.press("pm:u:5:0"))
        self.assertIn("Oddiy", text)
        self.assertNotIn("❌ Premiumni olib tashlash", texts(markup))

    async def test_names_and_usernames_are_html_escaped(self):
        self.add_user(5, name=EVIL, username="ali")
        text, _ = self.edited(await self.press("pm:u:5:0"))
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", text)
        self.assertNotIn('<a href="http://e">', text)

    async def test_unknown_user_gives_alert(self):
        cb = await self.press("pm:u:424242:0")
        self.assertIn("topilmadi", self.alert(cb))
        cb.message.edit_text.assert_not_awaited()


# ───────────────────────────── qidiruv ─────────────────────────────
class SearchTest(PanelCase):
    def message(self, text, user_id=ADMIN):
        m = mock.MagicMock()
        m.from_user.id = user_id
        m.text = text
        m.answer = mock.AsyncMock()
        return m

    async def test_search_button_asks_for_id_or_username_and_sets_state(self):
        cb = await self.press("pm:s")
        text, markup = self.edited(cb)
        self.assertIn("ID", text)
        self.assertIn("@username", text)
        self.state.set_state.assert_awaited_once_with(bot_mod.AdminPremiumStates.waiting_search)
        self.assertEqual(find(markup, "⬅️ Ro'yxatga"), "pm:l:0")

    async def test_other_panel_buttons_leave_search_mode(self):
        await self.press("pm:l:0")
        self.state.clear.assert_awaited()
        self.state.set_state.assert_not_awaited()

    async def test_found_by_numeric_id_and_by_username_any_case(self):
        self.add_user(5, name="Vali", username="Vali_Uz")
        for query in ("5", " 5 ", "@Vali_Uz", "@vali_uz", "VALI_UZ", "vali_uz"):
            with self.subTest(query=query):
                m = self.message(query)
                await bot_mod.pm_search_input(m, self.state)
                text = m.answer.await_args.args[0]
                self.assertIn("Vali", text)
                self.assertIn("<code>5</code>", text)
                self.assertEqual(find(m.answer.await_args.kwargs["reply_markup"], "🎁 Premium berish"), "pm:g:5:0")
        self.state.clear.assert_awaited()

    async def test_not_found_message(self):
        self.add_user(5, name="Vali", username="vali")
        for query in ("999", "@nobody", "nobody", "'; DROP TABLE users;--", "x" * 100, "99999999999999999999999"):
            with self.subTest(query=query):
                m = self.message(query)
                await bot_mod.pm_search_input(m, self.state)
                self.assertIn("Topilmadi", m.answer.await_args.args[0])
        self.assertIsNotNone(self.row(5))                                                    # jadval butun

    async def test_db_search_function_directly(self):
        self.add_user(5, name="Vali", username="Vali")
        self.assertEqual(database.admin_find_user("@VALI")["user_id"], 5)
        self.assertEqual(database.admin_find_user("5")["user_id"], 5)
        for bad in ("", "   ", "@", None, "6", "@nobody", "٥"):                            # arab raqami ham ID emas
            self.assertIsNone(database.admin_find_user(bad), bad)


# ───────────────────────────── berish oqimi (tugmalar) ─────────────────────────────
class GrantFlowTest(PanelCase):
    async def test_full_click_through_with_back_buttons_at_every_step(self):
        self.add_user(5, name="Vali", username="vali")
        _, markup = self.edited(await self.press("pm:u:5:3"))
        _, markup = self.edited(await self.press(find(markup, "🎁 Premium berish")))
        # 1) tarif: get_stars_tariffs() dagi turlar bilan bir xil
        self.assertEqual(texts(markup)[:-1], ["⭐ Pro", "💎 Plus", "👑 Ultra"])
        tiers = {entry[0] for entry in bot_mod.get_stars_tariffs().values()}
        self.assertEqual({t for _, t, _ in bot_mod._pm_tiers()}, tiers)
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:u:5:3")
        _, markup = self.edited(await self.press(find(markup, "💎 Plus")))
        # 2) muddat
        self.assertEqual(texts(markup)[:-1], ["1 kun", "3 kun", "7 kun", "30 kun", "90 kun", "♾ Muddatsiz"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:g:5:3")
        _, markup = self.edited(await self.press(find(markup, "30 kun")))
        # 3) rejim
        self.assertEqual(texts(markup)[:-1], ["📣 Xabar bilan", "🤫 Sirli"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:t:5:3:l")
        _, markup = self.edited(await self.press(find(markup, "📣 Xabar bilan")))
        # 4) sabab (faqat Xabar bilan)
        self.assertEqual(texts(markup)[:-1], ["🏆 Konkurs g'olibi", "🎂 Tug'ilgan kun sovg'asi", "🎁 Sovg'a",
                                              "🙏 Faolligingiz uchun", "🛠 Noqulaylik uchun kompensatsiya", "➖ Sababsiz"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:d:5:3:l:30")
        text, markup = self.edited(await self.press(find(markup, "🏆 Konkurs g'olibi")))
        # 5) tasdiqlash: qisqa xulosa
        for part in ("Vali", "<code>5</code>", "Plus", "30 kun", "Xabar bilan", "Konkurs g'olibi"):
            self.assertIn(part, text)
        self.assertEqual(texts(markup), ["✅ Tasdiqlash", "✖️ Bekor qilish", "⬅️ Orqaga"])
        self.assertEqual(find(markup, "✖️ Bekor qilish"), "pm:u:5:3")
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:m:5:3:l:30:n")
        self.assertEqual(self.row(5)["is_premium"], 0)                                      # hali hech narsa berilmagan
        cb = await self.press(find(markup, "✅ Tasdiqlash"))
        self.assertEqual(self.row(5)["premium_type"], "plus")
        self.assert_expires_in(5, 30)
        text, markup = self.edited(cb)
        self.assertIn("Premium berildi", text)
        self.assertEqual(find(markup, "⬅️ Ro'yxatga"), "pm:l:3")

    async def test_secret_mode_skips_reason_step(self):
        self.add_user(5)
        _, markup = self.edited(await self.press("pm:d:5:0:p:7"))
        text, markup = self.edited(await self.press(find(markup, "🤫 Sirli")))
        self.assertIn("Sirli", text)
        self.assertNotIn("Sabab", text)
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:d:5:0:p:7")                         # sabab bosqichi yo'q
        await self.press(find(markup, "✅ Tasdiqlash"))
        self.assertEqual(self.row(5)["premium_type"], "pro")

    async def test_cancel_returns_to_card_without_granting(self):
        self.add_user(5)
        _, markup = self.edited(await self.press("pm:r:5:0:u:90:n:2"))
        text, markup = self.edited(await self.press(find(markup, "✖️ Bekor qilish")))
        self.assertIn("Oddiy", text)
        self.assertEqual(self.row(5)["is_premium"], 0)
        self.fake_bot.send_message.assert_not_awaited()

    async def test_confirm_summary_mentions_kept_higher_tier(self):
        self.add_user(5, is_premium=1, premium_type="ultra", premium_expires_at=future(days=10))
        text, _ = self.edited(await self.press("pm:m:5:0:p:3:s"))
        self.assertIn("Ultra bor: tarif saqlanadi, muddat +3 kun", text)


# ───────────────────────────── berish mantig'i ─────────────────────────────
class GrantLogicTest(PanelCase):
    async def test_every_tier_and_duration_gives_the_right_term(self):
        uid = 10
        for tier in ("pro", "plus", "ultra"):
            for days in (1, 3, 7, 30, 90):
                with self.subTest(tier=tier, days=days):
                    uid += 1
                    self.add_user(uid)
                    cb = await self.grant(uid, tier, str(days))
                    row = self.row(uid)
                    self.assertEqual((row["is_premium"], row["premium_type"]), (1, tier))
                    self.assert_expires_in(uid, days)
                    self.assertEqual(row["premium_until"], row["premium_expires_at"])
                    self.assertIn("Premium berildi", self.edited(cb)[0])

    async def test_active_higher_tier_is_not_downgraded_and_term_is_extended(self):
        expires = NOW() + dt.timedelta(days=10)
        for held, given in (("ultra", "pro"), ("ultra", "plus"), ("plus", "pro")):
            with self.subTest(held=held, given=given):
                uid = 20 + len(held) + len(given)
                self.add_user(uid, is_premium=1, premium_type=held, premium_expires_at=expires.isoformat())
                cb = await self.grant(uid, given, "3")
                row = self.row(uid)
                self.assertEqual(row["premium_type"], held)                                # tarif pasaymadi
                self.assert_expires_in(uid, 3, base=expires, tol=5)                         # faol muddatga +3 kun
                text = self.edited(cb)[0]
                self.assertIn(f"{bot_mod.PM_TIER_NAMES[held]}</b> saqlandi, muddat +3 kun", text)

    async def test_higher_tier_replaces_lower_and_stacks_term(self):
        expires = NOW() + dt.timedelta(days=5)
        self.add_user(30, is_premium=1, premium_type="pro", premium_expires_at=expires.isoformat())
        await self.grant(30, "plus", "7")
        self.assertEqual(self.row(30)["premium_type"], "plus")
        self.assert_expires_in(30, 7, base=expires, tol=5)

    async def test_expired_flag_is_treated_as_free(self):
        self.add_user(31, is_premium=1, premium_type="ultra", premium_expires_at=future(days=-4))
        await self.grant(31, "pro", "1")
        self.assertEqual(self.row(31)["premium_type"], "pro")                              # eski Ultra qaytmaydi
        self.assert_expires_in(31, 1)

    async def test_unlimited_grant_sets_null_expiry_and_chosen_tier(self):
        for tier in ("pro", "plus", "ultra"):
            with self.subTest(tier=tier):
                uid = 40 + len(tier)
                self.add_user(uid)
                cb = await self.grant(uid, tier, "u")
                row = self.row(uid)
                self.assertEqual((row["is_premium"], row["premium_type"]), (1, tier))
                self.assertIsNone(row["premium_expires_at"])
                self.assertIsNone(row["premium_until"])
                self.assertIn("Muddatsiz", self.edited(cb)[0])

    async def test_unlimited_replaces_daily_premium_and_can_switch_tier(self):
        self.add_user(50, is_premium=1, premium_type="ultra", premium_expires_at=future(days=3))
        await self.grant(50, "pro", "u")
        row = self.row(50)
        self.assertEqual((row["premium_type"], row["premium_expires_at"]), ("pro", None))
        await self.grant(50, "ultra", "u")                                                  # muddatsiz -> muddatsiz
        row = self.row(50)
        self.assertEqual((row["is_premium"], row["premium_type"], row["premium_expires_at"]), (1, "ultra", None))

    async def test_daily_grant_to_unlimited_user_is_blocked_everywhere(self):
        self.add_user(60, is_premium=1, premium_type="ultra", premium_expires_at=None)
        before = self.row(60)
        # (a) muddat tanlanganda — rejim bosqichiga o'tkazmaydi
        cb = await self.press("pm:d:60:0:p:7")
        self.assertIn("muddatsiz Premium bor", self.alert(cb))
        self.assertIn("avval olib tashlang", self.alert(cb))
        cb.message.edit_text.assert_not_awaited()
        # (b) to'g'ridan-to'g'ri tasdiqlash (eski tugma / poyga) — bazada baribir bloklanadi
        for mode, reason in (("s", "-"), ("n", "0")):
            cb = await self.press(self.confirm_data(60, "pro", "7", mode, reason))
            self.assertIn("muddatsiz Premium bor", self.alert(cb))
        self.assertEqual(self.row(60), before)                                              # hech narsa o'zgarmadi
        self.fake_bot.send_message.assert_not_awaited()                                       # xabar ham ketmadi
        # bloklangan urinish keyingi (to'g'ri) urinishni to'smaydi
        self.assertEqual(bot_mod._pm_recent, {})

    async def test_database_function_reports_unlimited_block(self):
        self.add_user(61, is_premium=1, premium_type="plus", premium_expires_at=None)
        result = database.admin_grant_premium(61, "pro", 3)
        self.assertEqual((result["ok"], result["error"]), (False, "unlimited_exists"))
        self.assertEqual(self.row(61)["premium_type"], "plus")

    async def test_unlimited_premium_uses_tier_quota_and_info(self):
        self.add_user(62)
        await self.grant(62, "plus", "u")
        with mock.patch.dict(os.environ, {"PLUS_AI_DAILY_LIMIT": "30", "PRO_AI_DAILY_LIMIT": "15",
                                          "ULTRA_AI_DAILY_LIMIT": "100"}):
            self.assertEqual(database.get_premium_info(62), (1, None, "plus"))
            self.assertEqual(database.get_ai_quota(62), (30, 30))                           # premium_type bo'yicha
            self.assertFalse(database.try_consume_free_ai(62))                              # premiumda bepul savol yo'q
            self.assertTrue(database.try_consume_daily_request(62))
            self.assertEqual(database.get_ai_quota(62), (29, 30))
        self.assertEqual(self.row(62)["premium_expires_at"], None)                          # muddatsiz buzilmagan

    async def test_unknown_user_and_bad_arguments(self):
        cb = await self.grant(777, "pro", "7")
        self.assertIn("topilmadi", self.alert(cb))
        with self.assertRaises(ValueError):
            database.admin_grant_premium(1, "free", 3)
        with self.assertRaises(ValueError):
            database.admin_grant_premium(1, "pro", 0)
        with self.assertRaises(ValueError):
            database.set_premium_unlimited(1, "free")

    async def test_double_press_grants_once(self):
        self.add_user(63)
        data = self.confirm_data(63, "pro", "7")
        first = await self.press(data, message_id=5000)
        second = await self.press(data, message_id=5000)                                    # qo'sh bosish
        self.assertIn("Premium berildi", self.edited(first)[0])
        self.assertIn("allaqachon bajarilgan", self.alert(second))
        self.assert_expires_in(63, 7)                                                       # 14 kun emas

    async def test_database_error_is_reported_and_allows_retry(self):
        self.add_user(64)
        data = self.confirm_data(64, "pro", "7")
        with mock.patch.object(bot_mod.database, "admin_grant_premium", side_effect=RuntimeError("DB")):
            cb = await self.press(data, message_id=6000)
        self.assertIn("Bazada xatolik", self.alert(cb))
        cb = await self.press(data, message_id=6000)                                        # qayta urinish bloklanmagan
        self.assertIn("Premium berildi", self.edited(cb)[0])

    async def test_every_change_is_logged(self):
        self.add_user(65)
        with self.assertLogs(level="INFO") as logs:
            await self.grant(65, "ultra", "30", "n", "1")
        line = next(l for l in logs.output if "[ADMIN PREMIUM]" in l)
        for part in (f"admin={ADMIN}", "user=65", "berish", "tarif=ultra", "30 kun", "rejim=n", "Tug'ilgan kun"):
            self.assertIn(part, line)
        self.add_user(66, is_premium=1, premium_type="pro", premium_expires_at=future(days=2))
        with self.assertLogs(level="INFO") as logs:
            await self.press(bot_mod._pm_cb("z", 66, 0, "s"))
        line = next(l for l in logs.output if "[ADMIN PREMIUM]" in l)
        for part in (f"admin={ADMIN}", "user=66", "olib tashlash", "rejim=s"):
            self.assertIn(part, line)


# ───────────────────────────── userga xabarlar ─────────────────────────────
class NotificationTest(PanelCase):
    async def test_notify_mode_sends_one_message_with_reason_and_expiry(self):
        self.add_user(70)
        await self.grant(70, "plus", "30", "n", "0")
        self.fake_bot.send_message.assert_awaited_once()
        args, kwargs = self.fake_bot.send_message.await_args
        self.assertEqual(args[0], 70)
        text = args[1]
        self.assertIn("🎁 Tabriklaymiz! Siz admin tomonidan <b>30 kunlik Premium Plus</b> oldingiz!", text)
        self.assertIn("Sabab: 🏆 Konkurs g'olibi", text)
        self.assertIn("⏳ Tugash sanasi:", text)
        self.assertEqual(kwargs["parse_mode"], "HTML")

    async def test_every_reason_text_goes_to_the_user(self):
        for idx, reason in enumerate(bot_mod.PM_REASONS[:-1]):
            with self.subTest(reason=reason):
                uid = 80 + idx
                self.add_user(uid)
                self.fake_bot.send_message.reset_mock()
                await self.grant(uid, "pro", "7", "n", str(idx))
                self.assertIn(f"Sabab: {reason}", self.fake_bot.send_message.await_args.args[1])

    async def test_no_reason_line_for_sababsiz(self):
        self.add_user(90)
        await self.grant(90, "pro", "7", "n", str(bot_mod.PM_NO_REASON))
        text = self.fake_bot.send_message.await_args.args[1]
        self.assertNotIn("Sabab", text)
        self.assertNotIn("Sababsiz", text)
        self.assertIn("Tabriklaymiz", text)

    async def test_unlimited_message_and_open_app_button(self):
        self.add_user(91)
        await self.grant(91, "ultra", "u", "n", "2")
        args, kwargs = self.fake_bot.send_message.await_args
        self.assertIn("<b>Muddatsiz Premium Ultra</b>", args[1])
        self.assertIn("♾ Muddatsiz", args[1])
        self.assertNotIn("Tugash sanasi", args[1])
        button = buttons(kwargs["reply_markup"])[0]
        self.assertEqual(button.web_app.url, "https://app.example/index.html")                 # mini appni ochish tugmasi
        self.assertIn("Mini Ilova", button.text)

    async def test_open_app_button_is_omitted_without_url(self):
        self.add_user(92)
        with mock.patch.dict(os.environ, {"MINI_APP_URL": ""}), mock.patch.object(bot_mod, "MINI_APP_URL", ""):
            await self.grant(92, "pro", "7", "n", "5")
        self.assertIsNone(self.fake_bot.send_message.await_args.kwargs["reply_markup"])

    async def test_button_does_not_pregenerate_a_wheel_prize_for_the_user(self):
        # get_web_app_url() qabul qiluvchi uchun baraban sovrinini yaratardi — bu yerda ishlatilmaydi
        self.add_user(93)
        with mock.patch.object(bot_mod, "get_web_app_url", mock.AsyncMock()) as builder:
            await self.grant(93, "pro", "7", "n", "5")
        builder.assert_not_awaited()
        self.assertIsNone(self.row(93)["pending_spin_prize"])

    async def test_secret_mode_sends_nothing(self):
        self.add_user(94)
        await self.grant(94, "plus", "30", "s")
        self.fake_bot.send_message.assert_not_awaited()
        self.assertEqual(self.row(94)["premium_type"], "plus")

    async def test_message_says_when_higher_tier_was_kept(self):
        self.add_user(95, is_premium=1, premium_type="ultra", premium_expires_at=future(days=10))
        await self.grant(95, "pro", "3", "n", "2")
        text = self.fake_bot.send_message.await_args.args[1]
        self.assertIn("<b>3 kunlik Premium Pro</b>", text)
        self.assertIn("Joriy tarifingiz: <b>Premium Ultra</b>", text)

    async def test_delivery_failure_still_grants_and_warns_admin(self):
        self.add_user(96)
        self.fake_bot.send_message.side_effect = Exception("Forbidden: bot was blocked by the user")
        cb = await self.grant(96, "plus", "7", "n", "3")
        self.assertEqual(self.row(96)["premium_type"], "plus")                                # Premium baribir berildi
        self.assert_expires_in(96, 7)
        text = self.edited(cb)[0]
        self.assertIn("Premium berildi", text)
        self.assertIn("⚠️ Xabar yetkazilmadi (user botni bloklagan bo'lishi mumkin)", text)

    async def test_no_warning_when_delivered_or_secret(self):
        self.add_user(97)
        self.add_user(98)
        ok = await self.grant(97, "pro", "7", "n", "2")
        secret = await self.grant(98, "pro", "7", "s")
        self.assertNotIn("Xabar yetkazilmadi", self.edited(ok)[0])
        self.assertNotIn("Xabar yetkazilmadi", self.edited(secret)[0])


# ───────────────────────────── olib tashlash ─────────────────────────────
class RemoveTest(PanelCase):
    def premium_user(self, uid, **cols):
        cols.setdefault("is_premium", 1)
        cols.setdefault("premium_type", "plus")
        cols.setdefault("premium_expires_at", future(days=20))
        self.add_user(uid, **cols)

    async def test_remove_flow_asks_mode_then_confirms(self):
        self.premium_user(5, name="Vali")
        _, markup = self.edited(await self.press("pm:x:5:2"))
        self.assertEqual(texts(markup), ["📣 Xabar bilan", "🤫 Sirli", "⬅️ Orqaga"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:u:5:2")
        text, markup = self.edited(await self.press(find(markup, "📣 Xabar bilan")))
        self.assertIn("tasdiqlang", text)
        self.assertEqual(texts(markup), ["✅ Tasdiqlash", "✖️ Bekor qilish", "⬅️ Orqaga"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "pm:x:5:2")
        self.assertEqual(self.row(5)["is_premium"], 1)                                      # tasdiqlanguncha olinmaydi
        self.fake_bot.send_message.assert_not_awaited()

    async def test_remove_works_in_both_modes(self):
        for mode, sends in (("n", 1), ("s", 0)):
            with self.subTest(mode=mode):
                uid = 10 + sends
                self.premium_user(uid)
                self.fake_bot.send_message.reset_mock()
                cb = await self.press(bot_mod._pm_cb("z", uid, 0, mode))
                row = self.row(uid)
                self.assertEqual((row["is_premium"], row["premium_type"]), (0, "free"))
                self.assertIsNone(row["premium_expires_at"])
                self.assertIsNone(row["premium_until"])
                self.assertEqual(self.fake_bot.send_message.await_count, sends)
                self.assertIn("Premium olib tashlandi", self.edited(cb)[0])

    async def test_removal_message_text(self):
        self.premium_user(20)
        await self.press(bot_mod._pm_cb("z", 20, 0, "n"))
        args, _ = self.fake_bot.send_message.await_args
        self.assertEqual(args[0], 20)
        self.assertEqual(args[1], "ℹ️ Sizning Premium obunangiz admin tomonidan bekor qilindi.")

    async def test_unlimited_premium_can_be_removed(self):
        self.premium_user(21, premium_type="ultra", premium_expires_at=None)
        await self.press(bot_mod._pm_cb("z", 21, 0, "s"))
        self.assertEqual(self.row(21)["is_premium"], 0)
        # olib tashlangach kunlik muddat berish mumkin (blok faqat muddatsiz uchun)
        cb = await self.grant(21, "pro", "7")
        self.assertEqual(self.row(21)["premium_type"], "pro")
        self.assertIn("Premium berildi", self.edited(cb)[0])

    async def test_delivery_failure_still_removes_and_warns(self):
        self.premium_user(22)
        self.fake_bot.send_message.side_effect = Exception("Forbidden")
        cb = await self.press(bot_mod._pm_cb("z", 22, 0, "n"))
        self.assertEqual(self.row(22)["is_premium"], 0)
        self.assertIn("⚠️ Xabar yetkazilmadi (user botni bloklagan bo'lishi mumkin)", self.edited(cb)[0])

    async def test_double_press_removes_once_and_sends_once(self):
        self.premium_user(23)
        data = bot_mod._pm_cb("z", 23, 0, "n")
        await self.press(data, message_id=7000)
        second = await self.press(data, message_id=7000)
        self.assertEqual(self.fake_bot.send_message.await_count, 1)
        self.assertIn("allaqachon bajarilgan", self.alert(second))

    async def test_remove_unknown_user(self):
        cb = await self.press(bot_mod._pm_cb("z", 31337, 0, "s"))
        self.assertIn("topilmadi", self.alert(cb))


# ───────────────────────────── B9: shaxsiy menyu tugmasi va reply menyu ─────────────────────────────
class MenuButtonHookTest(PanelCase):
    async def drain(self):
        tasks = list(bot_mod._menu_reset_tasks)
        if tasks:
            await asyncio.wait(tasks, timeout=2)

    def button_of(self, uid):
        calls = [c for c in self.fake_bot.set_chat_menu_button.await_args_list if c.kwargs["chat_id"] == uid]
        self.assertEqual(len(calls), 1, calls)
        return calls[0].kwargs["menu_button"]

    async def test_grant_sets_personal_app_button_in_both_modes(self):
        for uid, mode in ((10, "n"), (11, "s")):
            with self.subTest(mode=mode):
                self.add_user(uid)
                await self.grant(uid, "plus", "30", mode, "0" if mode == "n" else "-")
                await self.drain()
                button = self.button_of(uid)
                self.assertIsInstance(button, types.MenuButtonWebApp)
                self.assertEqual(button.text, "👑 Ilova")
                self.assertEqual(button.web_app.url, "https://app.example/index.html")      # query parametrsiz, joriy MINI_APP_URL
                self.assertNotIn("?", button.web_app.url)
        sent_to = [c.args[0] for c in self.fake_bot.send_message.await_args_list]
        self.assertEqual(sent_to, [10])                                                     # Sirli rejimda xabar yo'q (tugma xabar emas)

    async def test_unlimited_grant_also_sets_the_button(self):
        self.add_user(12)
        await self.grant(12, "ultra", "u")
        await self.drain()
        self.assertIsInstance(self.button_of(12), types.MenuButtonWebApp)

    async def test_remove_returns_default_button_in_both_modes(self):
        for uid, mode in ((20, "n"), (21, "s")):
            with self.subTest(mode=mode):
                self.add_user(uid, is_premium=1, premium_type="plus", premium_expires_at=future(days=10))
                bot_mod._menu_reset_done.add(uid)                                           # "allaqachon tozalangan" belgisi — majburan yuboriladi
                await self.press(bot_mod._pm_cb("z", uid, 0, mode))
                await self.drain()
                self.assertIsInstance(self.button_of(uid), types.MenuButtonDefault)

    async def test_grant_then_remove_round_trip(self):
        self.add_user(30)
        await self.grant(30, "pro", "7")
        await self.drain()
        await self.press(bot_mod._pm_cb("z", 30, 0, "s"))
        await self.drain()
        kinds = [type(c.kwargs["menu_button"]) for c in self.fake_bot.set_chat_menu_button.await_args_list
                 if c.kwargs["chat_id"] == 30]
        self.assertEqual(kinds, [types.MenuButtonWebApp, types.MenuButtonDefault])

    async def test_failed_or_blocked_grant_does_not_touch_the_button(self):
        self.add_user(40, is_premium=1, premium_type="ultra", premium_expires_at=None)     # muddatsiz: kunlik berish bloklanadi
        await self.press(self.confirm_data(40, "pro", "7"))
        await self.grant(777, "pro", "7")                                                   # bazada yo'q
        await self.drain()
        self.fake_bot.set_chat_menu_button.assert_not_awaited()

    async def test_reply_keyboard_cache_follows_admin_actions(self):
        self.add_user(50)
        await self.grant(50, "ultra", "30")
        self.assertEqual(bot_mod.cached_premium_view(50), {"active": True, "tier": "ultra"})
        self.add_user(51, is_premium=1, premium_type="plus", premium_expires_at=future(days=5))
        await self.press(bot_mod._pm_cb("z", 51, 0, "s"))
        self.assertEqual(bot_mod.cached_premium_view(51), {"active": False, "tier": "free"})
        # Ustun tarif saqlansa — yakuniy tarif keshga yoziladi
        self.add_user(52, is_premium=1, premium_type="ultra", premium_expires_at=future(days=10))
        await self.grant(52, "pro", "3")
        self.assertEqual(bot_mod.cached_premium_view(52), {"active": True, "tier": "ultra"})

    async def test_telegram_error_in_button_update_does_not_break_the_admin_flow(self):
        self.add_user(60)
        self.fake_bot.set_chat_menu_button.side_effect = RuntimeError("Telegram ishlamayapti")
        with self.assertLogs(level="WARNING"):
            cb = await self.grant(60, "pro", "7")
            await self.drain()
        self.assertIn("Premium berildi", self.edited(cb)[0])                                # admin ekrani normal
        self.assertEqual(self.row(60)["premium_type"], "pro")

    async def test_button_update_is_not_awaited_inside_the_admin_response(self):
        self.add_user(61)
        gate = asyncio.Event()

        async def blocked(**kwargs):
            await gate.wait()

        self.fake_bot.set_chat_menu_button.side_effect = blocked
        with mock.patch.object(bot_mod, "MENU_RESET_TIMEOUT", 30.0):
            cb = await self.grant(61, "pro", "7")
            self.assertIn("Premium berildi", self.edited(cb)[0])                            # tugma javobni kechiktirmadi
            self.assertTrue(any(not t.done() for t in bot_mod._menu_reset_tasks))
            gate.set()
            await self.drain()


# ───────────────────────────── DB yordamchilari ─────────────────────────────
class DatabaseHelpersTest(PanelCase):
    async def test_premium_view_rules(self):
        view = database.admin_premium_view
        now = NOW()
        self.assertEqual(view(0, "pro", None)["tier"], "free")
        self.assertFalse(view(0, "pro", None)["active"])
        unlimited = view(1, "plus", None)
        self.assertEqual((unlimited["active"], unlimited["unlimited"], unlimited["tier"]), (True, True, "plus"))
        self.assertEqual(view(1, "free", None)["tier"], "ultra")                                # kvota kodi kabi
        self.assertFalse(view(1, "pro", (now - dt.timedelta(minutes=1)).isoformat())["active"])
        active = view(1, "ultra", (now + dt.timedelta(days=1)).isoformat())
        self.assertEqual((active["active"], active["unlimited"], active["tier"]), (True, False, "ultra"))
        self.assertFalse(view(1, "pro", "buzuq-sana")["active"])

    async def test_set_premium_unlimited_returns_false_for_unknown_user(self):
        self.assertFalse(database.set_premium_unlimited(99999, "pro"))
        self.add_user(1)
        self.assertTrue(database.set_premium_unlimited(1, "pro"))

    async def test_sql_is_parametrized_in_new_functions(self):
        for fn in (database.admin_users_page, database.admin_get_user, database.admin_find_user,
                   database.set_premium_unlimited, database.admin_grant_premium):
            src = inspect.getsource(fn)
            self.assertNotIn('f"SELECT', src)
            self.assertNotIn("f'SELECT", src)
            self.assertNotIn('f"UPDATE', src)
            self.assertNotIn(".format(", src)


if __name__ == "__main__":
    unittest.main()
