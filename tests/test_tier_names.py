"""
test_tier_names.py — tarif NOMLARI almashgan: ichki kod pro = ko'rinadigan "Plus", ichki plus = "Pro", ultra o'zgarmagan.

Narx, muddat, AI limit, ichki kodlar (premium_type, payload, callback_data) o'zgarmaydi — faqat ko'rinadigan matn.
Ko'rinadigan nom BITTA joyda: Python — database.TIER_DISPLAY / TIER_ICON; Mini App — app.js PREMIUM_TIERS
(ikkalasi shu testda solishtiriladi). Haqiqiy Telegram yoki bazaga murojaat qilinmaydi.
"""
import glob
import os
import re
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

# ichki kod -> (ko'rinadigan nom, belgi, muddat kun, narx Stars, AI/kun, payload, callback_data)
EXPECTED = {
    "pro": ("Plus", "⭐", 7, 50, 15, "PRO_7_DAYS", "buy_pro_7"),
    "plus": ("Pro", "💎", 30, 150, 30, "PLUS_30_DAYS", "buy_plus_30"),
    "ultra": ("Ultra", "👑", 30, 300, 100, "ULTRA_30_DAYS", "buy_ultra_30"),
}
ENV = {"PRO_TRIAL_STARS": "50", "PRO_MONTHLY_STARS": "150", "ULTRA_MONTHLY_STARS": "300"}


def read(*parts):
    with open(os.path.join(PROJECT_DIR, *parts), encoding="utf-8") as f:
        return f.read()


class NameConstantsTest(unittest.TestCase):
    def test_display_name_and_icon_per_internal_code(self):
        for tier, (name, icon, *_rest) in EXPECTED.items():
            with self.subTest(tier=tier):
                self.assertEqual(database.TIER_DISPLAY[tier], name)
                self.assertEqual(database.TIER_ICON[tier], icon)
                self.assertEqual(bot.tier_title(tier), f"{icon} Premium {name}")
        self.assertEqual(set(database.TIER_DISPLAY), {"pro", "plus", "ultra"})

    def test_bot_takes_names_from_the_single_database_constant(self):
        self.assertIs(bot.TIER_DISPLAY, database.TIER_DISPLAY)
        self.assertIs(bot.TIER_ICON, database.TIER_ICON)
        self.assertEqual(bot.AI_TIER_NAMES, database.TIER_DISPLAY)

    def test_titles_labels_and_admin_names_are_built_from_it(self):
        self.assertEqual(bot.PREMIUM_TIER_TITLES,
                         {"pro": "⭐ Premium Plus", "plus": "💎 Premium Pro", "ultra": "👑 Premium Ultra"})
        # admin paneli: tarif tugmalari tartibi ⭐ Plus, 💎 Pro, 👑 Ultra
        self.assertEqual([label for _code, _tier, label in bot._pm_tiers()], ["⭐ Plus", "💎 Pro", "👑 Ultra"])
        self.assertEqual(bot.PM_TIER_NAMES, {"free": "Oddiy", "pro": "Plus", "plus": "Pro", "ultra": "Ultra"})

    def test_internal_codes_prices_durations_are_unchanged(self):
        with mock.patch.dict(os.environ, ENV):
            tariffs = bot.get_stars_tariffs()
            for tier, (_name, _icon, days, stars, _ai, payload, _cb) in EXPECTED.items():
                with self.subTest(tier=tier):
                    self.assertEqual(tariffs[payload][:2], (tier, days))
                    self.assertEqual(tariffs[payload][3], stars)
            self.assertEqual(tariffs[bot.DISCOUNT_PAYLOAD][:2], ("plus", 30))
            self.assertEqual(tariffs[bot.DISCOUNT_PAYLOAD][3], 75)
        self.assertEqual(bot.DISCOUNT_PAYLOAD, "PLUS_30_DAYS_DISCOUNT")
        self.assertEqual(bot.API_INVOICE_PLANS, ("buy_pro_7", "buy_plus_30", "buy_ultra_30"))
        self.assertEqual(bot.PREMIUM_TIER_ACTIONS, {t: v[6] for t, v in EXPECTED.items()})
        self.assertEqual(bot.ai_tier_limits(), {t: v[4] for t, v in EXPECTED.items()})
        self.assertEqual(database._ADMIN_TIERS, ("pro", "plus", "ultra"))

    def test_invoice_titles_use_visible_names(self):
        with mock.patch.dict(os.environ, ENV):
            t = bot.get_stars_tariffs()
            self.assertEqual(t["PRO_7_DAYS"][2], "⭐ Premium Plus (7 kun)")
            self.assertEqual(t["PLUS_30_DAYS"][2], "💎 Premium Pro (30 kun)")
            self.assertEqual(t["ULTRA_30_DAYS"][2], "👑 Premium Ultra (30 kun)")
            self.assertEqual(t[bot.DISCOUNT_PAYLOAD][2], "🎁 Premium Pro (30 kun, 50% chegirma)")
            self.assertEqual(bot.LEGACY_STARS_PAYLOADS["stars_premium_1month"][2], "⭐ Premium Plus (30 kun)")


class OfferTextTest(unittest.IsolatedAsyncioTestCase):
    async def offer(self, action, discount=False):
        with mock.patch.dict(os.environ, ENV), \
                mock.patch.object(bot.database, "has_discount", return_value=discount):
            return await bot.build_premium_offer(1, action)

    async def test_offer_titles_and_descriptions(self):
        title, desc, payload, stars = await self.offer("buy_pro_7")
        self.assertEqual((title, payload, stars), ("⭐ Premium Plus — 7 kun", "PRO_7_DAYS", 50))
        self.assertIn("7 kunlik Premium Plus", desc)
        title, desc, payload, stars = await self.offer("buy_plus_30")
        self.assertEqual((title, payload, stars), ("💎 Premium Pro — 30 kun", "PLUS_30_DAYS", 150))
        self.assertIn("30 kunlik Premium Pro", desc)
        title, desc, payload, stars = await self.offer("buy_ultra_30")
        self.assertEqual((title, payload, stars), ("👑 Premium Ultra — 30 kun", "ULTRA_30_DAYS", 300))

    async def test_super_prize_offer_is_premium_pro(self):
        title, desc, payload, stars = await self.offer("buy_plus_30", discount=True)
        self.assertEqual((title, payload, stars), ("🎁 Premium Pro — 30 kun (50% chegirma)", bot.DISCOUNT_PAYLOAD, 75))
        self.assertIn("Premium Pro", desc)
        self.assertNotIn("Premium Plus", title + desc)


class ReplyMenuTest(unittest.TestCase):
    def premium_filter(self):
        handler = next(h for h in bot.dp.message.handlers if h.callback is bot.reply_premium_info)
        return handler.filters[0].callback

    def test_reply_menu_button_per_tier(self):
        from tests.test_premium_visibility import labels, view
        expected = {"pro": "⭐ Premium Plus", "plus": "💎 Premium Pro", "ultra": "👑 Premium Ultra"}
        for tier, text in expected.items():
            with self.subTest(tier=tier):
                markup = bot.get_start_keyboard(view(tier, days=5))
                self.assertEqual([t for t in labels(markup) if "Premium" in t], [text])

    def test_every_menu_text_goes_to_the_premium_handler(self):
        matches = self.premium_filter()
        for text in ("💎 Premium", "⭐ Premium Plus", "💎 Premium Pro", "👑 Premium Ultra"):
            with self.subTest(text=text):
                self.assertTrue(matches(SimpleNamespace(text=text)))

    def test_old_keyboards_still_open_the_premium_page(self):
        """Nomlar almashishidan OLDIN yuborilgan reply klaviatura qurilmada qoladi: eski matn (⭐ Premium Pro /
        💎 Premium Plus) bosilsa ham Premium sahifasi ochiladi — AI savol deb qabul qilinmaydi."""
        matches = self.premium_filter()
        for text in ("⭐ Premium Pro", "💎 Premium Plus"):
            with self.subTest(text=text):
                self.assertTrue(matches(SimpleNamespace(text=text)))
                self.assertNotIn(text, bot.PREMIUM_BUTTON_TEXTS)             # yangi klaviaturada chiqmaydi
                self.assertIn(text, bot.PREMIUM_BUTTON_TEXTS_ROUTED)


class SalesPageTextTest(unittest.IsolatedAsyncioTestCase):
    def free_view(self):
        return database.admin_premium_view(0, None, None)

    async def test_sales_text_and_buttons_use_visible_names(self):
        target = mock.MagicMock()
        target.from_user = SimpleNamespace(id=1)
        target.answer = mock.AsyncMock()
        with mock.patch.dict(os.environ, ENV), \
                mock.patch.object(database, "get_score", return_value=40), \
                mock.patch.object(database, "has_discount", return_value=False), \
                mock.patch.object(bot, "get_web_app_url", mock.AsyncMock(return_value="https://x/app")):
            await bot._show_premium_sales(target, self.free_view())
        text = target.answer.await_args.args[0]
        for part in ("100 Ball → 3 kun Premium Plus", "50 ⭐ → 7 kun Premium Plus",
                     "150 ⭐ → 30 kun Premium Pro", "300 ⭐ → 30 kun Premium Ultra",
                     "PREMIUM PLUS", "PREMIUM PRO", "PREMIUM ULTRA", "Barcha Premium Plus imkoniyatlari"):
            self.assertIn(part, text)
        markup = target.answer.await_args.kwargs["reply_markup"]
        buttons = [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row if b.callback_data]
        self.assertIn(("⭐ 50 Stars → 7 kun Premium Plus", "buy_pro_7"), buttons)
        self.assertIn(("💎 150 Stars → 30 kun Premium Pro", "buy_plus_30"), buttons)
        self.assertIn(("👑 300 Stars → 30 kun Premium Ultra", "buy_ultra_30"), buttons)
        self.assertIn(("🎁 100 ball → 3 kun Plus (Yana 60 ball kerak)", "redeem_points_info"), buttons)

    async def test_redeem_alerts_say_premium_plus(self):
        cb = mock.MagicMock()
        cb.from_user = SimpleNamespace(id=1)
        cb.answer = mock.AsyncMock()
        with mock.patch.object(database, "get_score", return_value=40):
            await bot.process_redeem_points_info(cb)
        self.assertIn("3 kunlik Premium Plus", cb.answer.await_args.args[0])

    async def test_upsell_texts_use_visible_names(self):
        text, _ = bot.premium_upsell_text(False, None)
        for line in ("Plus — kuniga 15 ta", "Pro — kuniga 30 ta", "Ultra — kuniga 100 ta"):
            self.assertIn(line, text)
        text, _ = bot.premium_upsell_text(True, "pro")
        self.assertIn("Premium Plus: kuniga 15", text)
        self.assertIn("Pro — kuniga 30 ta", text)


class NoOldNamesLeftTest(unittest.TestCase):
    """Eski nom–muddat juftliklari ("Premium Pro (7 kun)", "30 kun Premium Plus"...) hech bir matnda qolmasligi kerak.
    Yangi juftliklar: Plus = 1/3/7 kun, Pro = 30 kun."""
    OLD_PAIRS = [
        r"Premium Pro\)?\s*[\(—–-]?\s*(?<!\d)(7|1|3) ?kun",
        r"(?<![\d.])(7|1|3) ?kun(lik)?\s+(Premium\s+)?Pro\b",
        r"Premium Plus\)?\s*[\(—–-]?\s*30 ?kun",
        r"(?<![\d.])30 ?kun(lik)?\s+(Premium\s+)?Plus\b",
    ]
    FILES = ["bot.py", "database.py", "app/app.js", "app/index.html", "docs/DEPLOY.md"] + \
        [os.path.relpath(p, PROJECT_DIR) for p in glob.glob(os.path.join(PROJECT_DIR, "services", "*.py"))]

    def test_no_old_name_duration_pairs_in_bot_and_mini_app_texts(self):
        for rel in self.FILES:
            text = read(*rel.replace("\\", "/").split("/"))
            for pattern in self.OLD_PAIRS:
                for m in re.finditer(pattern, text):
                    line = text.count("\n", 0, m.start()) + 1
                    self.fail(f"{rel}:{line}: eski nom-muddat juftligi: {m.group(0)!r}")

    def test_checker_catches_the_old_pairs(self):
        for old in ("Premium Pro (7 kun)", "Premium Pro — 7 kun", "7 kunlik Premium Pro", "3 kun Premium Pro",
                    "1 kunlik Pro", "Premium Plus (30 kun)", "30 kun Premium Plus", "30 kunlik Plus"):
            with self.subTest(old=old):
                self.assertTrue(any(re.search(p, old) for p in self.OLD_PAIRS), old)
        for new in ("Premium Plus (7 kun)", "30 kun Premium Pro", "7 kunlik Plus", "Premium Pro — 30 kun",
                    "150 ⭐ → 30 kun Premium Pro", "3 kunlik Premium Plus"):
            with self.subTest(new=new):
                self.assertFalse(any(re.search(p, new) for p in self.OLD_PAIRS), new)


class MiniAppNamesTest(unittest.TestCase):
    """Mini App nomlari Python konstantasi bilan bir xil; HTML dagi karta nomlari ham."""

    def test_js_constant_matches_python_constant(self):
        js = read("app", "app.js")
        block = js[js.index("const PREMIUM_TIERS = {"): js.index("};", js.index("const PREMIUM_TIERS = {"))]
        found = dict((m.group(1), (m.group(2), m.group(3)))
                     for m in re.finditer(r"(\w+): \{ name: '(\w+)', icon: '(\w+)'", block))
        self.assertEqual({t: n for t, (n, _i) in found.items()}, database.TIER_DISPLAY)
        self.assertEqual({t: i for t, (_n, i) in found.items()}, {"pro": "star", "plus": "gem", "ultra": "crown"})
        plans = dict(re.findall(r"(\w+): \{ name: '\w+', icon: '\w+', plan: '(\w+)'", block))
        self.assertEqual(plans, bot.PREMIUM_TIER_ACTIONS)

    def test_js_and_python_comment_the_internal_code_mapping(self):
        self.assertIn("ICHKI KOD pro = KO'RINADIGAN", read("app", "app.js"))
        self.assertIn("ICHKI KOD pro = KO'RINADIGAN", read("database.py"))

    def test_html_plan_cards_use_visible_names_and_keep_internal_values(self):
        html_text = read("app", "index.html")
        names = re.findall(r'<span class="plan-name" data-tier="(\w+)">Premium (\w+)', html_text)
        self.assertEqual(len(names), 6)                                   # AI taklif kartasi + Premium oynasi
        for tier, name in names:
            self.assertEqual(name, database.TIER_DISPLAY[tier], tier)
        for plan in bot.PREMIUM_TIER_ACTIONS.values():                     # value (buy_pro_7...) o'zgarmagan
            self.assertEqual(html_text.count(f'value="{plan}"'), 2, plan)
        self.assertIn("1 kunlik Premium Plus va SUPER priz", html_text)

    def test_css_keeps_internal_tier_classes(self):
        css = read("app", "style.css")
        for tier in ("pro", "plus", "ultra"):
            self.assertIn(f"body.tier-{tier}", css)
            self.assertIn(f"--tier-{tier}:", css)


if __name__ == "__main__":
    unittest.main()
