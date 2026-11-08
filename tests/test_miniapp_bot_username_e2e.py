"""
test_miniapp_bot_username_e2e.py — 4: bot username app.js da BITTA konstantada (BOT_USERNAME); barcha deep linklar
undan quriladi va oldingidek aynan shu havolalarni ochadi (mantiq o'zgarmagan).
Asos: tests/e2e_base.py
"""
import os
import re
import unittest

from tests.e2e_base import MiniAppE2EBase

APP_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "app.js")
BOT = "Birinchiyordam1Bot"


class BotUsernameConstantStaticTest(unittest.TestCase):
    def setUp(self):
        with open(APP_JS, encoding="utf-8") as f:
            self.js = f.read()

    def test_literal_only_in_constant(self):
        self.assertEqual(self.js.count(BOT), 1, "bot username faqat BOT_USERNAME konstantasida bo'lishi kerak")
        self.assertRegex(self.js, r'const BOT_USERNAME = "' + BOT + r'";')

    def test_every_t_me_link_uses_the_constant(self):
        for m in re.finditer(r"t\.me/", self.js):
            line = self.js[self.js.rfind("\n", 0, m.start()) + 1: self.js.find("\n", m.end())]
            self.assertTrue("botUsername" in line or "BOT_USERNAME" in line, f"qattiq yozilgan havola: {line.strip()}")

    def test_local_aliases_point_to_constant(self):
        # Mahalliy nusxalar bo'lsa — faqat konstantaga ishora qiladi (redesign'da ular BOT_USERNAME bilan almashtirilgan)
        aliases = re.findall(r"(?:const|var) botUsername = ([^;]+);", self.js)
        self.assertTrue(set(aliases) <= {"BOT_USERNAME"}, aliases)


class BotUsernameLinksE2ETest(MiniAppE2EBase):
    def test_buy_premium_helper_link(self):
        page, _ = self.open_app({}, query="", init_data="")
        page.evaluate("buyPremium('buy_plus_30')")
        self.assertEqual(self.tg(page)["links"], [f"https://t.me/{BOT}?start=buy_plus_30"])

    def test_open_bot_wheel_button_link(self):
        page, _ = self.open_app({"state": "abort"}, query="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        page.click("#btn-spin-wheel")
        page.click("#btn-open-bot-wheel")
        tg = self.tg(page)
        self.assertEqual(tg["links"], [f"https://t.me/{BOT}?start=wheel"])
        self.assertEqual(tg["closed"], 1)

    def test_body_map_ai_consult_link(self):
        page, _ = self.open_app({}, query="", init_data="")
        page.click('[data-tab="tab-body-map"]')
        page.evaluate("openBodyMapModal('head')")
        page.wait_for_selector("#body-map-modal:not([hidden])")
        page.click("#ai-consult-btn")
        page.clock.fast_forward(400)
        page.wait_for_function("window.__tg.links.length === 1")
        tg = self.tg(page)
        self.assertEqual(tg["links"], [f"https://t.me/{BOT}?start=ai_consult_head"])
        self.assertEqual(tg["closed"], 1)


if __name__ == "__main__":
    unittest.main()
