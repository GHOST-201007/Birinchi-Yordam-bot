"""
test_ban_panel.py — admin /ban paneli (Premium paneli uslubida): ro'yxat, qidiruv, user kartasi, ban (muddat -> rejim -> sabab ->
tasdiq), unban (📣 / 🤫), muddatni o'zgartirish, matnli /ban va /unban, Premium paneli bilan hamkorlik.

DB mantig'i HAQIQIY SQL bilan (tests/sqlite_db.py); Telegram soxta.
"""
import datetime as dt
import html
import os
import sys
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

import bot as bot_mod  # noqa: E402
import database  # noqa: E402
from tests.test_admin_premium import ADMIN, STRANGER, EVIL, PanelCase, buttons, find, texts  # noqa: E402

LIFTED = "✅ Siz blokdan chiqarildingiz. Botdan yana foydalanishingiz mumkin."


class FakeState:
    """FSM: ma'lumot va holat saqlanadi (clear — ikkalasini ham tozalaydi, set_state(None) — faqat holatni)."""

    def __init__(self):
        self.data = {}
        self.current = None

    async def set_state(self, state):
        self.current = state

    async def clear(self):
        self.data, self.current = {}, None

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)
        return dict(self.data)


def future_wall(**delta):
    return (database.get_uz_now() + dt.timedelta(**delta)).replace(tzinfo=None).isoformat()


class BanPanelCase(PanelCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.state = FakeState()
        patcher = mock.patch.object(bot_mod, "ADMIN_USERNAME", "adminbot")
        patcher.start()
        self.addCleanup(patcher.stop)
        bot_mod._ban_cache_reset = None
        patcher = mock.patch.object(database, "_ban_cache", database._BanCache())
        patcher.start()
        self.addCleanup(patcher.stop)

    # ---- yordamchilar ----
    async def bn(self, *parts, user_id=ADMIN, message_id=None):
        self.msg_seq += 1
        cb = self.callback(bot_mod._bn_cb(*parts), user_id, message_id)
        await bot_mod.cb_ban_panel(cb, self.state)
        return cb

    async def bn_raw(self, data, user_id=ADMIN):
        self.msg_seq += 1
        cb = self.callback(data, user_id)
        await bot_mod.cb_ban_panel(cb, self.state)
        return cb

    def message(self, text, user_id=ADMIN):
        message = mock.MagicMock()
        message.from_user.id = user_id
        message.text = text
        message.answer = mock.AsyncMock()
        return message

    def sent(self):
        return [(c.args[0], c.args[1]) for c in self.fake_bot.send_message.await_args_list]

    def info(self, uid):
        return database.get_ban_info(uid)

    async def do_ban(self, uid, dur="7", mode="n", rs="5", ctx="a0"):
        return await self.bn("c", uid, ctx, dur, mode, rs)


# ───────────────────────────── xavfsizlik ─────────────────────────────
class GateTest(BanPanelCase):
    async def test_every_step_rejects_non_admin_and_changes_nothing(self):
        self.add_user(5, name="Vali")
        samples = ["bn:l:a0", "bn:l:b0", "bn:s", "bn:u:5:a0", "bn:g:5:a0", "bn:d:5:a0:7", "bn:m:5:a0:7:n", "bn:m:5:a0:7:s",
                   "bn:r:5:a0:7:0", "bn:w:5:a0:7:n", "bn:c:5:a0:7:n:5", "bn:c:5:a0:7:s:-", "bn:x:5:a0", "bn:y:5:a0:n",
                   "bn:z:5:a0:n", "bn:e:5:a0", "bn:f:5:a0:7", "bn:h:5:a0:7"]
        for data in samples:
            with self.subTest(data=data):
                cb = await self.bn_raw(data, user_id=STRANGER)
                cb.answer.assert_awaited_once_with("❌ Siz admin emassiz!", show_alert=True)
                cb.message.edit_text.assert_not_awaited()
        self.assertEqual(self.row(5)["is_banned"], 0)
        self.fake_bot.send_message.assert_not_awaited()

    async def test_text_inputs_reject_non_admin(self):
        self.add_user(5, name="Vali")
        for handler in (bot_mod.bn_search_input, bot_mod.bn_text_input):
            message = self.message("5", user_id=STRANGER)
            await handler(message, self.state)
            message.answer.assert_awaited_once_with("❌ Siz admin emassiz!")
        self.assertEqual(self.row(5)["is_banned"], 0)

    async def test_text_commands_reject_non_admin(self):
        self.add_user(5, name="Vali")
        for handler, text in ((bot_mod.cmd_ban, "/ban 5 10"), (bot_mod.cmd_unban, "/unban 5")):
            message = self.message(text, user_id=STRANGER)
            if handler is bot_mod.cmd_ban:
                await handler(message, self.state)
            else:
                await handler(message)
            message.answer.assert_awaited_once()
            self.assertIn("huquqi yo'q", message.answer.await_args.args[0])
        self.assertEqual(self.row(5)["is_banned"], 0)
        self.fake_bot.send_message.assert_not_awaited()

    async def test_malformed_callbacks_are_rejected_without_changes(self):
        self.add_user(5)
        for data in ("bn:", "bn:zz", "bn:l:x", "bn:l:a", "bn:u:5", "bn:u:x:a0", "bn:u:5:z1", "bn:d:5:a0:9", "bn:m:5:a0:7:x",
                     "bn:r:5:a0:7:9", "bn:r:5:a0:7:4", "bn:r:5:a0:7:x", "bn:c:5:a0:7:n:9", "bn:c:5:a0:7:s:3",
                     "bn:c:5:a0:7:n", "bn:c:5:a0:7:n:5:extra", "bn:y:5:a0:q", "bn:f:5:a0:9"):
            with self.subTest(data=data):
                cb = await self.bn_raw(data)
                self.assertIn("Noto'g'ri so'rov", self.alert(cb))
                cb.message.edit_text.assert_not_awaited()
        self.assertEqual(self.row(5)["is_banned"], 0)
        self.fake_bot.send_message.assert_not_awaited()

    async def test_callback_data_never_exceeds_64_bytes(self):
        big_ban = {"banned": True, "mode": "open", "until": database.get_uz_now(), "reason": "x", "banned_at": None}
        big = {"user_id": 9_999_999_999_999_999, "full_name": "Ali", "username": "ali", "active": True, "tier": "plus",
               "unlimited": False, "expires": database.get_uz_now(), "score": 1, "ban": big_ban}
        free = dict(big, ban={"banned": False, "mode": None, "until": None, "reason": None, "banned_at": None})
        ctx = "b99999"
        views = [bot_mod._bn_card_view(big, ctx), bot_mod._bn_card_view(free, ctx), bot_mod._bn_duration_view(free, ctx),
                 bot_mod._bn_mode_view(free, ctx, "u"), bot_mod._bn_reason_view(free, ctx, "u"),
                 bot_mod._bn_confirm_view(free, ctx, "u", "n", "4", "x"), bot_mod._bn_confirm_view(free, ctx, "u", "s", "t", "x"),
                 bot_mod._bn_text_prompt_view(free, ctx, "u", "s"), bot_mod._bn_edit_duration_view(big, ctx),
                 bot_mod._bn_edit_confirm_view(big, ctx, "30"), bot_mod._bn_unban_mode_view(big, ctx),
                 bot_mod._bn_unban_confirm_view(big, ctx, "n"), (None, bot_mod._bn_result_markup(big["user_id"], ctx)),
                 bot_mod._bn_list_view({"users": [big], "page": 99999, "pages": 100000, "total": 1, "banned_count": 1,
                                        "listed": 1}, True),
                 bot_mod._bn_search_view([big], "x")]
        for _text, markup in views:
            for button in buttons(markup):
                self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64, button.callback_data)
                self.assertTrue(button.callback_data.startswith("bn:"))


# ───────────────────────────── ro'yxat, qidiruv, karta ─────────────────────────────
class ListSearchCardTest(BanPanelCase):
    def fill(self):
        self.add_user(1, name="Erkin", username="erkin_u")
        self.add_user(2, name="Ochiq", is_banned=1, ban_mode="open", ban_reason="Spam")
        self.add_user(3, name="Sirli", username="sirli_u", is_banned=1, ban_mode="silent", banned_until=future_wall(days=2))
        self.add_user(4, name="Eski", is_banned=1)                                         # ban_mode NULL = ochiq
        self.add_user(5, name="Tugagan", is_banned=1, ban_mode="open", banned_until=future_wall(minutes=-4))

    async def test_ban_command_opens_the_list_with_markers_and_counts(self):
        self.fill()
        message = self.message("/ban")
        await bot_mod.cmd_ban(message, self.state)
        text = message.answer.await_args.args[0]
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertIn("Ban Boshqaruvi", text)
        self.assertIn("Jami foydalanuvchilar: <b>5</b>", text)
        self.assertIn("Banlanganlar: <b>3</b>", text)                                      # muddati o'tgani hisobga olinmaydi
        labels = {b.callback_data.split(":")[2]: b.text for b in buttons(markup) if b.callback_data.startswith("bn:u:")}
        self.assertEqual(labels["1"], "👤 Erkin — Faol")
        self.assertEqual(labels["2"], "🚫 Ochiq — Ochiq ban")
        self.assertEqual(labels["3"], "🤫 Sirli — Sirli ban")
        self.assertEqual(labels["4"], "🚫 Eski — Ochiq ban")
        self.assertEqual(labels["5"], "👤 Tugagan — Faol")
        self.assertIn("🚫 Banlanganlar", texts(markup))
        self.assertIn("🔍 Qidirish", texts(markup))

    async def test_banned_only_filter(self):
        self.fill()
        text, markup = bot_mod._bn_list_view(await bot_mod._pm_load_list(0, True), True)
        ids = sorted(int(b.callback_data.split(":")[2]) for b in buttons(markup) if b.callback_data.startswith("bn:u:"))
        self.assertEqual(ids, [2, 3, 4])
        self.assertIn("faqat banlanganlar", text)
        self.assertIn("👥 Hammasi", texts(markup))
        cb = await self.bn("l", "b0")
        edited_text, edited_markup = self.edited(cb)
        self.assertEqual(sorted(int(b.callback_data.split(":")[2]) for b in buttons(edited_markup)
                                if b.callback_data.startswith("bn:u:")), [2, 3, 4])

    async def test_banned_only_filter_without_bans(self):
        self.add_user(1)
        cb = await self.bn("l", "b0")
        text, markup = self.edited(cb)
        self.assertIn("Banlanganlar yo'q.", text)
        self.assertEqual([b for b in buttons(markup) if b.callback_data.startswith("bn:u:")], [])

    async def test_pagination_keeps_the_filter(self):
        for uid in range(1, 26):
            self.add_user(uid, name=f"U{uid}", is_banned=1, ban_mode="open")
        cb = await self.bn("l", "b1")
        text, markup = self.edited(cb)
        self.assertIn("Sahifa: <b>2/3</b>", text)
        self.assertEqual(find(markup, "◀️"), "bn:l:b0")
        self.assertEqual(find(markup, "▶️"), "bn:l:b2")

    async def test_search_by_id_username_and_name(self):
        self.fill()
        for query, expected in (("1", 1), ("@erkin_u", 1), ("SIRLI_U", 3), ("erkin", 1), ("irli", 3)):
            with self.subTest(query=query):
                message = self.message(query)
                await bot_mod.bn_search_input(message, self.state)
                text = message.answer.await_args.args[0]
                self.assertIn(f"<code>{expected}</code>", text)
                self.assertIn("🚫 Ban:", text) if expected == 3 else self.assertIn("Ban: <b>Yo'q</b>", text)

    async def test_search_with_several_matches_shows_a_result_list(self):
        self.add_user(10, name="Ali Valiyev")
        self.add_user(11, name="Alisher")
        self.add_user(12, name="Boshqa")
        message = self.message("ali")
        await bot_mod.bn_search_input(message, self.state)
        markup = message.answer.await_args.kwargs["reply_markup"]
        ids = sorted(int(b.callback_data.split(":")[2]) for b in buttons(markup) if b.callback_data.startswith("bn:u:"))
        self.assertEqual(ids, [10, 11])
        self.assertTrue(all(b.callback_data.endswith(":q") for b in buttons(markup) if b.callback_data.startswith("bn:u:")))
        self.assertIn("2 ta foydalanuvchi", message.answer.await_args.args[0])

    async def test_search_treats_wildcards_literally_and_reports_not_found(self):
        self.add_user(10, name="Ali")
        for query in ("%", "_", "zzz"):
            message = self.message(query)
            await bot_mod.bn_search_input(message, self.state)
            self.assertIn("Topilmadi", message.answer.await_args.args[0])

    async def test_search_prompt_sets_the_waiting_state(self):
        cb = await self.bn("s")
        self.assertIs(self.state.current, bot_mod.AdminBanStates.waiting_search)
        self.assertIn("ismini", self.edited(cb)[0])

    async def test_card_of_a_free_user(self):
        self.add_user(7, name="Vali", username="vali")
        cb = await self.bn("u", 7, "a0")
        text, markup = self.edited(cb)
        for part in ("Vali", "<code>7</code>", "@vali", "Premium:", "Oddiy", "Ban: <b>Yo'q</b>"):
            self.assertIn(part, text)
        self.assertEqual(texts(markup), ["🚫 Ban qilish", "⬅️ Ro'yxatga"])

    async def test_card_of_an_open_ban_shows_mode_time_term_and_reason(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open", ban_reason="Spam", banned_until=future_wall(days=3),
                      banned_at=future_wall(hours=-1))
        cb = await self.bn("u", 7, "a0")
        text, markup = self.edited(cb)
        for part in ("Ban: <b>📣 Ochiq</b>", "Qo'yilgan:", "Muddat: <b>", "gacha", "Sabab: Spam"):
            self.assertIn(part, text)
        self.assertEqual(texts(markup), ["✅ Unban", "✏️ Muddatni o'zgartirish", "⬅️ Ro'yxatga"])

    async def test_card_of_a_silent_ban_marks_the_note_as_admin_only(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="silent", ban_reason="shubhali")
        text, _ = self.edited(await self.bn("u", 7, "a0"))
        self.assertIn("Ban: <b>🤫 Sirli</b>", text)
        self.assertIn("Izoh (faqat admin ko'radi): shubhali", text)
        self.assertIn("♾ Muddatsiz", text)

    async def test_card_shows_premium_state(self):
        self.add_user(7, name="Vali", is_premium=1, premium_type="ultra",
                      premium_expires_at=(database.get_uz_now() + dt.timedelta(days=9)).isoformat())
        text, _ = self.edited(await self.bn("u", 7, "a0"))
        self.assertIn("Ultra", text)
        self.assertIn("Premium tugashi", text)

    async def test_unknown_user_is_reported(self):
        cb = await self.bn("u", 999, "a0")
        self.assertIn("topilmadi", self.alert(cb))

    async def test_names_and_reasons_are_escaped(self):
        self.add_user(7, name=EVIL, username="u7", is_banned=1, ban_mode="open", ban_reason=EVIL)
        text, _ = self.edited(await self.bn("u", 7, "a0"))
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", text)
        self.assertNotIn('<a href="http://e">', text)


# ───────────────────────────── ban qilish oqimi ─────────────────────────────
class BanFlowTest(BanPanelCase):
    async def test_steps_show_the_documented_buttons(self):
        self.add_user(7, name="Vali")
        text, markup = self.edited(await self.bn("g", 7, "a0"))
        self.assertEqual(texts(markup), ["1 soat", "1 kun", "7 kun", "30 kun", "♾ Muddatsiz", "⬅️ Orqaga"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "bn:u:7:a0")
        text, markup = self.edited(await self.bn("d", 7, "a0", "7"))
        self.assertEqual(texts(markup), ["📣 Xabar bilan", "🤫 Sirli", "⬅️ Orqaga"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "bn:g:7:a0")
        text, markup = self.edited(await self.bn("m", 7, "a0", "7", "n"))
        self.assertEqual(texts(markup), ["Spam", "Haqorat", "Qoidabuzarlik", "Reklama", "✍️ Boshqa (yozaman)", "Sababsiz",
                                         "⬅️ Orqaga"])
        self.assertEqual(find(markup, "⬅️ Orqaga"), "bn:d:7:a0:7")

    async def test_silent_mode_asks_for_no_reason(self):
        self.add_user(7, name="Vali")
        text, markup = self.edited(await self.bn("m", 7, "a0", "7", "s"))
        self.assertIn("Ban — tasdiqlang", text)                                            # sabab bosqichi yo'q
        self.assertEqual(texts(markup), ["✅ Tasdiqlash", "❌ Bekor", "✍️ Izoh qo'shish", "⬅️ Orqaga"])
        self.assertNotIn("Spam", texts(markup))

    async def test_confirmation_states_exactly_what_will_happen(self):
        self.add_user(7, name="Vali")
        text, _ = self.edited(await self.bn("m", 7, "a0", "7", "s"))
        self.assertIn("User 7 kunga sirli ban qilinadi, unga xabar bormaydi.", text)
        text, _ = self.edited(await self.bn("r", 7, "a0", "u", 0))
        self.assertIn("User muddatsiz ochiq ban qilinadi: unga xabar boradi", text)
        self.assertIn("Sabab: Spam", text)
        text, _ = self.edited(await self.bn("m", 7, "a0", "h", "s"))
        self.assertIn("User 1 soatga sirli ban qilinadi, unga xabar bormaydi.", text)

    async def test_cancel_and_back_do_not_ban(self):
        self.add_user(7, name="Vali")
        text, markup = self.edited(await self.bn("r", 7, "a0", "7", 0))
        self.assertEqual(find(markup, "❌ Bekor"), "bn:u:7:a0")
        self.assertEqual(find(markup, "⬅️ Orqaga"), "bn:m:7:a0:7:n")
        await self.bn("u", 7, "a0")
        self.assertEqual(self.row(7)["is_banned"], 0)

    async def test_open_ban_full_flow_notifies_the_user_with_term_and_reason(self):
        self.add_user(7, name="Vali")
        cb = await self.do_ban(7, "7", "n", "0")                                            # 7 kun, ochiq, Spam
        info = self.info(7)
        self.assertEqual((info["banned"], info["mode"], info["reason"]), (True, "open", "Spam"))
        self.assertAlmostEqual((info["until"] - database.get_uz_now()).total_seconds(), 7 * 86400, delta=120)
        sent = self.sent()
        self.assertEqual(len(sent), 1)
        uid, text = sent[0]
        self.assertEqual(uid, 7)
        self.assertIn("Siz botdan foydalanishdan chetlashtirildingiz.", text)
        self.assertIn("⏳ Muddat:", text)
        self.assertIn("gacha", text)
        self.assertIn("📝 Sabab: Spam", text)
        self.assertIn("Murojaat uchun: @adminbot", text)
        result_text, _ = self.edited(cb)
        self.assertIn("Ban qo'yildi", result_text)
        self.assertNotIn("yetkazilmadi", result_text)

    async def test_open_ban_without_reason_and_permanent(self):
        self.add_user(7, name="Vali")
        await self.do_ban(7, "u", "n", "5")
        info = self.info(7)
        self.assertEqual((info["mode"], info["until"], info["reason"]), ("open", None, None))
        text = self.sent()[0][1]
        self.assertIn("♾ muddatsiz", text)
        self.assertNotIn("Sabab", text)

    async def test_every_preset_reason_is_saved(self):
        for idx, reason in enumerate(("Spam", "Haqorat", "Qoidabuzarlik", "Reklama")):
            uid = 30 + idx
            self.add_user(uid)
            await self.do_ban(uid, "1", "n", str(idx))
            self.assertEqual(self.info(uid)["reason"], reason)

    async def test_silent_ban_sends_nothing_to_the_user(self):
        self.add_user(7, name="Vali")
        cb = await self.do_ban(7, "30", "s", "-")
        info = self.info(7)
        self.assertEqual((info["banned"], info["mode"], info["reason"]), (True, "silent", None))
        self.assertAlmostEqual((info["until"] - database.get_uz_now()).total_seconds(), 30 * 86400, delta=120)
        self.fake_bot.send_message.assert_not_awaited()
        self.assertIn("Ban qo'yildi", self.edited(cb)[0])

    async def test_silent_ban_with_an_admin_note(self):
        self.add_user(7, name="Vali")
        await self.bn("w", 7, "a0", "7", "s")
        self.assertIs(self.state.current, bot_mod.AdminBanStates.waiting_text)
        message = self.message("  reklama  botlari   bilan bog'liq ")
        await bot_mod.bn_text_input(message, self.state)
        text = message.answer.await_args.args[0]
        self.assertIn("Izoh (faqat admin ko'radi): " + html.escape("reklama botlari bilan bog'liq"), text)
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(find(markup, "✅ Tasdiqlash"), "bn:c:7:a0:7:s:t")
        await self.bn("c", 7, "a0", "7", "s", "t")
        info = self.info(7)
        self.assertEqual((info["mode"], info["reason"]), ("silent", "reklama botlari bilan bog'liq"))
        self.fake_bot.send_message.assert_not_awaited()                                    # izoh userga ko'rsatilmaydi
        self.assertIsNone(self.state.current)
        self.assertEqual(self.state.data, {})

    async def test_open_ban_with_a_typed_reason(self):
        self.add_user(7, name="Vali")
        await self.bn("w", 7, "a0", "30", "n")
        message = self.message("Boshqa foydalanuvchilarni haqorat qildi")
        await bot_mod.bn_text_input(message, self.state)
        self.assertEqual(find(message.answer.await_args.kwargs["reply_markup"], "✅ Tasdiqlash"), "bn:c:7:a0:30:n:4")
        await self.bn("c", 7, "a0", "30", "n", "4")
        self.assertEqual(self.info(7)["reason"], "Boshqa foydalanuvchilarni haqorat qildi")
        self.assertIn("📝 Sabab: Boshqa foydalanuvchilarni haqorat qildi", self.sent()[0][1])

    async def test_typed_reason_is_html_escaped_in_the_user_message(self):
        self.add_user(7, name="Vali")
        await self.bn("w", 7, "a0", "1", "n")
        await bot_mod.bn_text_input(self.message(EVIL), self.state)
        await self.bn("c", 7, "a0", "1", "n", "4")
        text = self.sent()[0][1]
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", text)
        self.assertNotIn('<a href="http://e">', text)

    async def test_typed_text_validation(self):
        self.add_user(7, name="Vali")
        await self.bn("w", 7, "a0", "7", "n")
        message = self.message("   ")
        await bot_mod.bn_text_input(message, self.state)
        self.assertIn("bo'sh", message.answer.await_args.args[0])
        message = self.message("x" * (database.BAN_REASON_MAX + 1))
        await bot_mod.bn_text_input(message, self.state)
        self.assertIn("juda uzun", message.answer.await_args.args[0])
        self.assertNotIn("text", self.state.data)
        self.assertIs(self.state.current, bot_mod.AdminBanStates.waiting_text)            # kutish davom etadi

    async def test_confirm_without_the_typed_text_is_refused(self):
        self.add_user(7, name="Vali")
        cb = await self.bn("c", 7, "a0", "7", "n", "4")                                     # matn FSM da yo'q
        self.assertIn("matn topilmadi", self.alert(cb))
        self.assertEqual(self.row(7)["is_banned"], 0)
        await self.state.update_data(uid=999, dur="7", mode="n", text="boshqa user uchun")
        cb = await self.bn("c", 7, "a0", "7", "n", "4")                                     # boshqa user uchun yozilgan matn
        self.assertIn("matn topilmadi", self.alert(cb))
        self.assertEqual(self.row(7)["is_banned"], 0)

    async def test_ban_replaces_the_search_state_and_cancels_pending_text(self):
        self.add_user(7, name="Vali")
        await self.bn("s")
        await self.bn("u", 7, "a0")                                                          # boshqa amal — kutish bekor
        self.assertIsNone(self.state.current)

    async def test_banning_an_already_banned_user_is_refused_in_the_panel(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open")
        cb = await self.bn("g", 7, "a0")
        self.assertIn("allaqachon banda", self.alert(cb))

    async def test_admin_cannot_ban_themselves(self):
        self.add_user(ADMIN, name="Admin")
        cb = await self.bn("g", ADMIN, "a0")
        self.assertIn("O'zingizni ban qila olmaysiz", self.alert(cb))
        cb = await self.do_ban(ADMIN, "u", "s", "-")                                        # tugmani qo'lda yuborsa ham
        self.assertIn("O'zingizni ban qila olmaysiz", self.alert(cb))
        self.assertEqual(self.row(ADMIN)["is_banned"], 0)

    async def test_delivery_failure_still_bans_and_warns_the_admin(self):
        self.add_user(7, name="Vali")
        self.fake_bot.send_message = mock.AsyncMock(side_effect=RuntimeError("Forbidden: bot was blocked by the user"))
        with self.assertLogs(level="WARNING"):
            cb = await self.do_ban(7, "7", "n", "0")
        self.assertTrue(self.info(7)["banned"])
        self.assertIn("⚠️ Xabar yetkazilmadi", self.edited(cb)[0])

    async def test_double_click_bans_and_notifies_once(self):
        self.add_user(7, name="Vali")
        first = await self.bn("c", 7, "a0", "7", "n", "0", message_id=4242)
        second = await self.bn("c", 7, "a0", "7", "n", "0", message_id=4242)
        self.assertEqual(len(self.sent()), 1)
        self.assertIn("allaqachon bajarilgan", self.alert(second))

    async def test_user_not_in_database_cannot_be_banned_from_the_panel(self):
        cb = await self.bn("g", 999, "a0")
        self.assertIn("topilmadi", self.alert(cb))


# ───────────────────────────── unban va muddatni o'zgartirish ─────────────────────────────
class UnbanTest(BanPanelCase):
    async def test_unban_with_a_message(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open", ban_reason="Spam", medicine_score=40)
        text, markup = self.edited(await self.bn("x", 7, "a0"))
        self.assertEqual(texts(markup), ["📣 Xabar bilan", "🤫 Xabarsiz", "⬅️ Orqaga"])
        text, markup = self.edited(await self.bn("y", 7, "a0", "n"))
        self.assertIn("unga xabar boradi", text)
        cb = await self.bn("z", 7, "a0", "n")
        self.assertFalse(self.info(7)["banned"])
        self.assertEqual(self.sent(), [(7, LIFTED)])
        self.assertEqual(self.row(7)["medicine_score"], 40)
        self.assertIn("Bandan chiqarildi", self.edited(cb)[0])

    async def test_unban_without_a_message(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="silent")
        text, _ = self.edited(await self.bn("y", 7, "a0", "s"))
        self.assertIn("unga xabar bormaydi", text)
        await self.bn("z", 7, "a0", "s")
        self.assertFalse(self.info(7)["banned"])
        self.fake_bot.send_message.assert_not_awaited()

    async def test_both_modes_can_be_unbanned_either_way(self):
        for mode in ("open", "silent"):
            for notify in ("n", "s"):
                with self.subTest(ban=mode, unban=notify):
                    uid = 100 + (mode == "silent") * 10 + (notify == "s")
                    self.add_user(uid, is_banned=1, ban_mode=mode)
                    self.fake_bot.send_message.reset_mock()
                    await self.bn("z", uid, "a0", notify)
                    self.assertFalse(self.info(uid)["banned"])
                    self.assertEqual(self.fake_bot.send_message.await_count, 1 if notify == "n" else 0)

    async def test_unban_of_a_user_who_is_not_banned_is_refused(self):
        self.add_user(7, name="Vali")
        for action, extra in (("x", ()), ("z", ("n",))):
            cb = await self.bn(action, 7, "a0", *extra)
            self.assertIn("banda emas", self.alert(cb))
        self.fake_bot.send_message.assert_not_awaited()

    async def test_unban_delivery_failure_is_reported(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open")
        self.fake_bot.send_message = mock.AsyncMock(side_effect=RuntimeError("blocked"))
        with self.assertLogs(level="WARNING"):
            cb = await self.bn("z", 7, "a0", "n")
        self.assertFalse(self.info(7)["banned"])
        self.assertIn("⚠️ Xabar yetkazilmadi", self.edited(cb)[0])

    async def test_unban_keeps_premium(self):
        premium_until = (database.get_uz_now() + dt.timedelta(days=15)).isoformat()
        self.add_user(7, is_banned=1, ban_mode="open", is_premium=1, premium_type="plus", premium_expires_at=premium_until)
        await self.bn("z", 7, "a0", "s")
        row = self.row(7)
        self.assertEqual((row["premium_type"], row["premium_expires_at"]), ("plus", premium_until))


class ChangeDurationTest(BanPanelCase):
    async def test_change_an_open_ban_notifies_the_user_with_the_new_term(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open", ban_reason="Spam", banned_until=future_wall(hours=1))
        text, markup = self.edited(await self.bn("e", 7, "a0"))
        self.assertEqual(texts(markup), ["1 soat", "1 kun", "7 kun", "30 kun", "♾ Muddatsiz", "⬅️ Orqaga"])
        text, _ = self.edited(await self.bn("f", 7, "a0", "30"))
        self.assertIn("rejim", text.lower())
        self.assertIn("ban xabari yuboriladi", text)
        cb = await self.bn("h", 7, "a0", "30")
        info = self.info(7)
        self.assertEqual((info["mode"], info["reason"]), ("open", "Spam"))                  # rejim va sabab saqlanadi
        self.assertAlmostEqual((info["until"] - database.get_uz_now()).total_seconds(), 30 * 86400, delta=120)
        self.assertEqual(len(self.sent()), 1)
        self.assertIn("Siz botdan foydalanishdan chetlashtirildingiz.", self.sent()[0][1])
        self.assertIn("Ban muddati o'zgartirildi", self.edited(cb)[0])

    async def test_change_a_silent_ban_is_invisible_to_the_user(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="silent", banned_until=future_wall(hours=1))
        text, _ = self.edited(await self.bn("f", 7, "a0", "u"))
        self.assertIn("User hech narsa sezmaydi", text)
        await self.bn("h", 7, "a0", "u")
        info = self.info(7)
        self.assertEqual((info["mode"], info["until"]), ("silent", None))
        self.fake_bot.send_message.assert_not_awaited()

    async def test_change_is_refused_for_a_user_who_is_not_banned(self):
        self.add_user(7, name="Vali")
        for action, extra in (("e", ()), ("f", ("7",)), ("h", ("7",))):
            cb = await self.bn(action, 7, "a0", *extra)
            self.assertIn("banda emas", self.alert(cb))
        self.assertEqual(self.row(7)["is_banned"], 0)

    async def test_change_is_refused_for_an_expired_ban(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open", banned_until=future_wall(minutes=-3))
        cb = await self.bn("h", 7, "a0", "7")
        self.assertIn("banda emas", self.alert(cb))
        self.assertFalse(self.info(7)["banned"])


# ───────────────────────────── matnli /ban va /unban ─────────────────────────────
class TextCommandsTest(BanPanelCase):
    async def ban_cmd(self, text, user_id=ADMIN):
        message = self.message(text, user_id)
        await bot_mod.cmd_ban(message, self.state)
        return message

    async def unban_cmd(self, text):
        message = self.message(text)
        await bot_mod.cmd_unban(message)
        return message

    async def test_ban_with_minutes_is_an_open_ban_without_reason(self):
        self.add_user(7, name="Vali")
        message = await self.ban_cmd("/ban 7 90")
        info = self.info(7)
        self.assertEqual((info["mode"], info["reason"]), ("open", None))
        self.assertAlmostEqual((info["until"] - database.get_uz_now()).total_seconds(), 90 * 60, delta=60)
        reply = message.answer.await_args.args[0]
        self.assertIn("Foydalanuvchi 7 90 daqiqaga vaqtinchalik 📣 ochiq ban qilindi.", reply)
        self.assertIn("Userga xabar yuborildi", reply)
        self.assertEqual([uid for uid, _ in self.sent()], [7])
        self.assertIn("Siz botdan foydalanishdan chetlashtirildingiz.", self.sent()[0][1])

    async def test_ban_without_minutes_is_permanent(self):
        self.add_user(7, name="Vali")
        message = await self.ban_cmd("/ban 7")
        self.assertIsNone(self.info(7)["until"])
        self.assertIn("muddatsiz 📣 ochiq ban qilindi", message.answer.await_args.args[0])
        self.assertIn("♾ muddatsiz", self.sent()[0][1])

    async def test_ban_of_a_user_who_never_started_the_bot_still_works(self):
        message = await self.ban_cmd("/ban 888 5")
        self.assertTrue(self.info(888)["banned"])
        self.assertIn("888", message.answer.await_args.args[0])

    async def test_ban_command_validation(self):
        self.add_user(7)
        for text, part in (("/ban abc", "butun son"), ("/ban 7 xx", "butun son"), ("/ban 7 0", "musbat"),
                           ("/ban 7 -5", "musbat")):
            with self.subTest(text=text):
                message = await self.ban_cmd(text)
                self.assertIn(part, message.answer.await_args.args[0])
                self.assertEqual(self.row(7)["is_banned"], 0)
        self.fake_bot.send_message.assert_not_awaited()

    async def test_admin_cannot_ban_themselves_by_command(self):
        self.add_user(ADMIN)
        message = await self.ban_cmd(f"/ban {ADMIN} 10")
        self.assertIn("O'zingizni ban qila olmaysiz", message.answer.await_args.args[0])
        self.assertEqual(self.row(ADMIN)["is_banned"], 0)

    async def test_ban_command_reports_a_failed_delivery(self):
        self.add_user(7)
        self.fake_bot.send_message = mock.AsyncMock(side_effect=RuntimeError("blocked"))
        with self.assertLogs(level="WARNING"):
            message = await self.ban_cmd("/ban 7 10")
        self.assertTrue(self.info(7)["banned"])
        self.assertIn("⚠️ Xabar yetkazilmadi", message.answer.await_args.args[0])

    async def test_plain_ban_command_opens_the_panel(self):
        self.add_user(7)
        message = await self.ban_cmd("/ban")
        self.assertIn("Ban Boshqaruvi", message.answer.await_args.args[0])

    async def test_unban_command_unbans_with_a_message(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="silent")
        message = await self.unban_cmd("/unban 7")
        self.assertFalse(self.info(7)["banned"])
        self.assertEqual(self.sent(), [(7, LIFTED)])                                         # unban ham 📣
        reply = message.answer.await_args.args[0]
        self.assertIn("Foydalanuvchi 7 bandan chiqarildi", reply)
        self.assertIn("Userga xabar yuborildi", reply)

    async def test_unban_command_for_a_user_who_is_not_banned(self):
        self.add_user(7)
        message = await self.unban_cmd("/unban 7")
        self.assertIn("banda emas", message.answer.await_args.args[0])
        self.fake_bot.send_message.assert_not_awaited()

    async def test_unban_command_usage_and_validation(self):
        message = await self.unban_cmd("/unban")
        self.assertIn("Foydalanish", message.answer.await_args.args[0])
        message = await self.unban_cmd("/unban xx")
        self.assertIn("butun son", message.answer.await_args.args[0])


# ───────────────────────────── Premium paneli bilan hamkorlik ─────────────────────────────
class PremiumPanelInteractionTest(BanPanelCase):
    async def pm(self, *parts):
        self.msg_seq += 1
        cb = self.callback(bot_mod._pm_cb(*parts))
        await bot_mod.cb_premium_panel(cb, self.state)
        return cb

    async def test_premium_card_shows_the_ban_state(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="silent", ban_reason="izoh", banned_until=future_wall(days=2))
        text, _ = self.edited(await self.pm("u", 7, 0))
        self.assertIn("Ban: <b>🤫 Sirli</b>", text)
        self.assertIn("Izoh (faqat admin ko'radi): izoh", text)
        self.add_user(8, name="Boshqa")
        text, _ = self.edited(await self.pm("u", 8, 0))
        self.assertNotIn("Ban:", text)                                                       # banda bo'lmasa qator yo'q

    async def test_grant_with_a_message_to_a_banned_user_sends_nothing_and_warns(self):
        for uid, mode in ((7, "open"), (8, "silent")):
            self.add_user(uid, name="Vali", is_banned=1, ban_mode=mode)
            self.fake_bot.send_message.reset_mock()
            cb = await self.pm("c", uid, 0, "p", "7", "n", 0)                                 # 📣 rejimi
            self.fake_bot.send_message.assert_not_awaited()
            self.assertEqual(self.row(uid)["is_premium"], 1)                                  # Premium baribir berilgan
            self.assertIn("ℹ️ User banlangan — xabar yuborilmadi", self.edited(cb)[0])

    async def test_remove_with_a_message_from_a_banned_user_sends_nothing_and_warns(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open", is_premium=1, premium_type="pro",
                      premium_expires_at=(database.get_uz_now() + dt.timedelta(days=5)).isoformat())
        cb = await self.pm("z", 7, 0, "n")
        self.fake_bot.send_message.assert_not_awaited()
        self.assertEqual(self.row(7)["is_premium"], 0)
        self.assertIn("ℹ️ User banlangan — xabar yuborilmadi", self.edited(cb)[0])

    async def test_secret_mode_for_a_banned_user_has_no_warning(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open")
        cb = await self.pm("c", 7, 0, "p", "7", "s", "-")
        self.assertNotIn("banlangan", self.edited(cb)[0])
        self.fake_bot.send_message.assert_not_awaited()

    async def test_users_who_are_not_banned_are_still_notified(self):
        self.add_user(7, name="Vali")
        cb = await self.pm("c", 7, 0, "p", "7", "n", 0)
        self.assertEqual(len(self.sent()), 1)
        self.assertNotIn("banlangan", self.edited(cb)[0])

    async def test_expired_uncleaned_ban_does_not_block_the_notification(self):
        self.add_user(7, name="Vali", is_banned=1, ban_mode="open", banned_until=future_wall(minutes=-2))
        await self.pm("c", 7, 0, "p", "7", "n", 0)
        self.assertEqual(len(self.sent()), 1)


class OldPanelRemovedTest(unittest.TestCase):
    def test_old_toggle_and_helpers_are_gone(self):
        with open(os.path.join(PROJECT_DIR, "bot.py"), encoding="utf-8") as f:
            src = f.read()
        for needle in ("ban_toggle_", "cb_ban_toggle", "ban_refresh", "_build_ban_list_keyboard", "_build_ban_list_text",
                       "get_all_users_info_ban"):
            self.assertNotIn(needle, src, needle)
        self.assertFalse(hasattr(database, "get_all_users_info_ban"))

    def test_panel_reuses_the_premium_panel_helpers(self):
        import inspect
        for fn in (bot_mod._bn_card_view, bot_mod._bn_list_view, bot_mod._bn_duration_view):
            self.assertIn("_pm_", inspect.getsource(fn))
        src = inspect.getsource(bot_mod._bn_dispatch)
        for helper in ("_pm_load_list", "_pm_load_user", "_pm_edit"):
            self.assertIn(helper, src)
        self.assertEqual(bot_mod._pm_cb("u", 1), "pm:u:1")                                  # Premium paneli o'zgarmagan


if __name__ == "__main__":
    unittest.main()
