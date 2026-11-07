"""
test_miniapp_wheel_e2e.py — Mini App baraboni /api/ orqali aylantirish (4-qadam), brauzerda (Playwright).
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import CLAIM_OK, INIT_DATA, STATE_OK, MiniAppE2EBase


class WheelApiE2ETest(MiniAppE2EBase):
    # ---- API orqali oqim ------------------------------------------------------
    def test_spin_claim_via_api_no_bot_redirect(self):
        page, calls = self.open_app({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)})
        self.open_wheel(page)
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.assertFalse(page.is_disabled("#btn-spin-wheel"))
        self.spin_and_finish(page)
        self.assertEqual([c[0] for c in calls], ["state"])           # tugma bosilguncha ball qo'shilmaydi
        page.click("#btn-confirm-spin")
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '12'")

        self.assertIn("+5 ball hisobingizga qo'shildi", self.card_text(page))
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])
        for _, body in calls:
            self.assertEqual(body, {"init_data": INIT_DATA})        # tanada boshqa hech narsa yo'q
        tg = self.tg(page)
        self.assertEqual(tg["closed"], 0)                           # tg.close() chaqirilmaydi
        self.assertEqual(tg["links"], [])                           # botga chiqilmaydi

    def test_menu_button_open_without_url_params_works(self):
        # Menyu tugmasidan ochilganda URL'da hech narsa yo'q (prize/score yo'q) — API yetarli
        page, _ = self.open_app({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)}, query="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-desc:has-text('hisobingizga qo')")
        self.assertNotIn("Bot orqali kiring", self.card_text(page))

    def test_super_prize_offers_discount_button(self):
        page, _ = self.open_app({
            "state": (200, {**STATE_OK, "prize": 0}),
            "spin/claim": (200, {"ok": True, "message": "SUPER", "score": 7, "is_super": True}),
        })
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-desc:has-text('50% chegirma faollashtirildi')")
        self.assertEqual(self.tg(page)["closed"], 0)
        self.assertEqual(self.tg(page)["links"], [])
        page.click("#wheel-result-msg .result-confirm-btn")            # "Premium olish"
        tg = self.tg(page)
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot?start=buy_plus_30"])
        self.assertEqual(tg["closed"], 0)

    def test_cooldown_from_server_blocks_spin_and_shows_timer(self):
        page, calls = self.open_app({"state": (200, {**STATE_OK, "prize": None, "cooldown_seconds": 3600})})
        self.open_wheel(page)
        page.wait_for_selector("#wheel-countdown-timer")
        h, m, sec = (int(x) for x in page.inner_text("#wheel-countdown-timer").split(":"))
        self.assertIn(h * 3600 + m * 60 + sec, range(3597, 3601))      # server: 3600 s (ilova ochilganidan beri ~1 s o'tgan bo'lishi mumkin)
        self.assertTrue(page.is_disabled("#btn-spin-wheel"))
        self.assertEqual(page.inner_text("#btn-spin-wheel .wheel-center-text"), "KUTISH")
        self.assertEqual([c[0] for c in calls], ["state"])

    def test_claim_not_ok_shows_server_message_and_updates_score(self):
        page, _ = self.open_app({
            "state": (200, STATE_OK),
            "spin/claim": (200, {"ok": False, "message": "Allaqachon olingan", "score": 9, "is_super": False}),
        })
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Ball qo')")
        self.assertIn("Allaqachon olingan", self.card_text(page))
        self.assertEqual(page.inner_text("#global-score-val"), "9")

    def test_server_message_is_not_interpreted_as_html(self):
        evil = "<img src=x onerror=\"window.__xss=1\"><b>qalin</b>"
        page, _ = self.open_app({
            "state": (200, STATE_OK),
            "spin/claim": (200, {"ok": False, "message": evil, "score": 1, "is_super": False}),
        })
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Ball qo')")
        self.assertIn("<b>qalin</b>", self.card_text(page))             # matn sifatida ko'rinadi
        self.assertEqual(page.locator("#wheel-result-msg img").count(), 0)
        self.assertIsNone(page.evaluate("window.__xss"))

    # ---- ZAXIRA yo'l (eski URL-parametr + deep link mantig'i) --------------------
    def test_fallback_when_state_api_fails_uses_url_prize_and_deep_link(self):
        page, calls = self.open_app({"state": (500, {"ok": False, "error": "server_error"})},
                                    query="?prize=5&score=3")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.assertEqual(page.inner_text("#global-score-val"), "3")     # URL'dagi ball
        self.spin_and_finish(page)
        self.assertEqual({c[0] for c in calls}, {"state"})               # claim chaqirilmadi (state xatoda qayta uriniladi)
        page.click("#btn-confirm-spin")
        tg = self.tg(page)
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot?start=spin_5"])
        self.assertEqual(tg["closed"], 1)

    def test_fallback_when_no_init_data_makes_no_api_calls(self):
        page, calls = self.open_app({}, query="?prize=3", init_data="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)
        page.click("#btn-confirm-spin")
        self.assertEqual(calls, [])
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=spin_3"])

    def test_fallback_without_url_prize_asks_to_use_bot(self):
        page, _ = self.open_app({"state": "abort"}, query="")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        page.click("#btn-spin-wheel")
        page.wait_for_selector("#btn-open-bot-wheel")
        self.assertIn("Bot orqali kiring", self.card_text(page))

    def test_claim_network_failure_falls_back_to_deep_link(self):
        page, calls = self.open_app({"state": (200, STATE_OK), "spin/claim": "abort"})
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_function("window.__tg.links.length === 1")
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=spin_5"])
        self.assertEqual(self.tg(page)["closed"], 1)


if __name__ == "__main__":
    unittest.main()
