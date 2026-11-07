"""
test_miniapp_bonus_e2e.py — 5-qadam: umumiy /api/state, header ball, kunlik bonus /api/bonus/claim orqali (Playwright).
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import INIT_DATA, STATE_OK, MiniAppE2EBase, sequence

BONUS_STATE = {"ok": True, "score": 7, "streak": 3, "daily_claimed": False, "prize": 5, "cooldown_seconds": 0}
BONUS_OK = {"ok": True, "message": "Bugungi bonus olindi!", "points": 3, "streak": 3, "score": 10}


class StateAndBonusE2ETest(MiniAppE2EBase):
    def open_bonus(self, page):
        page.click("#btn-open-daily-bonus")
        page.wait_for_selector("#daily-bonus-modal:not(.hidden)")

    def state_calls(self, calls):
        return [c for c in calls if c[0] == "state"]

    def timer_seconds(self, page):
        h, m, sec = (int(x) for x in page.inner_text("#wheel-countdown-timer").split(":"))
        return h * 3600 + m * 60 + sec

    # ---- ochilganda holat serverdan -------------------------------------------
    def test_menu_button_open_fills_header_and_bonus_from_state(self):
        # Menyu tugmasidan ochilganda URL'da hech narsa yo'q
        page, calls = self.open_app({"state": (200, BONUS_STATE)}, query="")
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.assertTrue(page.is_visible("#global-score"))              # URL'da ball bo'lmasa ham header'da ko'rinadi
        self.open_bonus(page)
        self.assertEqual(page.inner_text("#daily-bonus-current-score"), "7")
        cards = page.locator("#daily-bonus-grid .daily-bonus-card")
        self.assertEqual(cards.count(), 7)
        self.assertEqual(page.locator("#daily-bonus-grid .daily-bonus-card.claimed").count(), 2)   # 1- va 2-kun
        self.assertIn("active", cards.nth(2).get_attribute("class"))                                # 3-kun — bugungi
        self.assertEqual(len(self.state_calls(calls)), 1)

    def test_daily_claimed_state_disables_button(self):
        page, calls = self.open_app({"state": (200, {**BONUS_STATE, "daily_claimed": True})})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_bonus(page)
        self.assertIn("bugungi bonus olindi", page.inner_text("#btn-claim-daily-bonus").lower())
        self.assertEqual(page.locator("#daily-bonus-grid .daily-bonus-card.claimed").count(), 3)
        page.click("#btn-claim-daily-bonus")
        self.assertEqual([c[0] for c in calls], ["state"])

    # ---- bitta umumiy state so'rovi ---------------------------------------------
    def test_wheel_and_bonus_share_one_state_request_until_60s(self):
        page, calls = self.open_app({"state": (200, BONUS_STATE)})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_bonus(page)
        page.click("#daily-bonus-close")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.assertEqual(len(self.state_calls(calls)), 1)            # header + bonus + baraban = 1 ta so'rov

        page.click("#wheel-modal-close")
        page.clock.fast_forward(61_000)                              # kesh 60 soniyadan eski bo'ldi
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.assertEqual(len(self.state_calls(calls)), 2)

    def test_wheel_cooldown_from_cache_decreases_with_time(self):
        page, calls = self.open_app({"state": (200, {**BONUS_STATE, "prize": None, "cooldown_seconds": 3600})})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        page.clock.fast_forward(30_000)                              # 30 soniya o'tdi, kesh hali yangi
        self.open_wheel(page)
        page.wait_for_selector("#wheel-countdown-timer")
        self.assertIn(self.timer_seconds(page), range(3568, 3571))     # 3600 - 30 soniya (+-1 soniya)
        self.assertEqual(len(self.state_calls(calls)), 1)

    # ---- bonusni mini app ichida olish -------------------------------------------
    def test_claim_bonus_via_api_stays_in_app(self):
        page, calls = self.open_app({"state": (200, BONUS_STATE), "bonus/claim": (200, BONUS_OK)})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_bonus(page)
        page.click("#btn-claim-daily-bonus")
        page.wait_for_selector("#daily-bonus-result")
        self.assertEqual(page.inner_text("#daily-bonus-result"), "+3 ball, 3-kun")
        self.assertEqual(page.inner_text("#global-score-val"), "10")
        self.assertEqual(page.inner_text("#daily-bonus-current-score"), "10")
        self.assertIn("bugungi bonus olindi", page.inner_text("#btn-claim-daily-bonus").lower())   # "Olindi" holati
        self.assertEqual([c[0] for c in calls], ["state", "bonus/claim"])
        for _, body in calls:
            self.assertEqual(body, {"init_data": INIT_DATA})
        tg = self.tg(page)
        self.assertEqual(tg["closed"], 0)
        self.assertEqual(tg["links"], [])

    def test_claim_bonus_updates_cache_so_reopen_needs_no_request(self):
        page, calls = self.open_app({"state": (200, BONUS_STATE), "bonus/claim": (200, BONUS_OK)})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_bonus(page)
        page.click("#btn-claim-daily-bonus")
        page.wait_for_selector("#daily-bonus-result")
        page.click("#daily-bonus-close")
        self.open_bonus(page)
        self.assertIn("bugungi bonus olindi", page.inner_text("#btn-claim-daily-bonus").lower())
        self.assertEqual(len(self.state_calls(calls)), 1)

    def test_double_click_sends_single_claim(self):
        page, calls = self.open_app({"state": (200, BONUS_STATE), "bonus/claim": (200, BONUS_OK)})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_bonus(page)
        page.dblclick("#btn-claim-daily-bonus")
        page.wait_for_selector("#daily-bonus-result")
        self.assertEqual([c[0] for c in calls].count("bonus/claim"), 1)

    def test_claim_not_ok_shows_message_and_refreshes_state(self):
        page, calls = self.open_app({
            "state": (200, BONUS_STATE),
            "bonus/claim": (200, {"ok": False, "message": "Siz bugungi bonusni olib bo'lgansiz.",
                                  "points": 0, "streak": 3, "score": 7}),
        })
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_bonus(page)
        page.click("#btn-claim-daily-bonus")
        page.wait_for_function("window.__tg.alerts.length === 1")
        self.assertEqual(self.tg(page)["alerts"], ["Siz bugungi bonusni olib bo'lgansiz."])
        page.wait_for_function("document.querySelectorAll('#daily-bonus-grid .daily-bonus-card.claimed').length >= 2")
        self.assertEqual([c[0] for c in calls], ["state", "bonus/claim", "state"])

    # ---- ZAXIRA yo'l --------------------------------------------------------------
    def test_fallback_when_state_fails_uses_url_params_and_deep_link(self):
        page, calls = self.open_app({"state": (500, {"ok": False, "error": "server_error"})},
                                    query="?streak=2&daily_claimed=0&score=4")
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '4'")
        self.open_bonus(page)
        self.assertEqual(page.inner_text("#daily-bonus-current-score"), "4")
        self.assertIn("active", page.locator("#daily-bonus-grid .daily-bonus-card").nth(1).get_attribute("class"))
        page.click("#btn-claim-daily-bonus")
        tg = self.tg(page)
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot?start=claim_daily"])
        self.assertEqual(tg["closed"], 1)
        self.assertNotIn("bonus/claim", [c[0] for c in calls])

    def test_fallback_without_init_data_makes_no_api_calls(self):
        page, calls = self.open_app({}, query="?streak=1&daily_claimed=0&score=0", init_data="")
        self.open_bonus(page)
        page.click("#btn-claim-daily-bonus")
        self.assertEqual(calls, [])
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=claim_daily"])

    def test_claim_network_failure_and_state_unavailable_falls_back_to_deep_link(self):
        # claim ham, qayta so'ralgan state ham olinmasa — ESKI deep link zaxira yo'li
        page, calls = self.open_app({"state": sequence((200, BONUS_STATE), "abort"), "bonus/claim": "abort"})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_bonus(page)
        page.click("#btn-claim-daily-bonus")
        page.wait_for_function("window.__tg.links.length === 1")
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=claim_daily"])
        self.assertEqual(self.tg(page)["closed"], 1)

    def test_spin_claim_updates_shared_cache_score(self):
        page, calls = self.open_app({
            "state": (200, STATE_OK),
            "spin/claim": (200, {"ok": True, "message": "ok", "score": 12, "is_super": False}),
        })
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '12'")
        self.open_bonus_after_wheel(page)
        self.assertEqual(page.inner_text("#daily-bonus-current-score"), "12")
        self.assertEqual(len(self.state_calls(calls)), 1)

    def open_bonus_after_wheel(self, page):
        page.click("#wheel-modal-close")
        self.open_bonus(page)


if __name__ == "__main__":
    unittest.main()
