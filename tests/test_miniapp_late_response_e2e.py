"""
test_miniapp_late_response_e2e.py — 3a: claim javobi kechiksa/yo'qolsa (timeout, tarmoq xatosi, 5xx) foydalanuvchi
darhol botga otilmaydi: avval holat qayta so'raladi. Server ballni allaqachon bergan bo'lsa — "hisobga qo'shilgan"
ko'rsatiladi (deep link YO'Q); holat ham olinmasa — eski deep link zaxira yo'li.

Sekin server taqlidi: claim so'rovi javobsiz osilib turadi, sahifaning 8 s timeout taymeri (soat) oldinga suriladi.
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import MiniAppE2EBase, STATE_OK, sequence

BONUS_STATE = {"ok": True, "score": 7, "streak": 3, "daily_claimed": False, "prize": 5, "cooldown_seconds": 0}
STATE_SPIN_GRANTED = {"ok": True, "score": 12, "streak": 1, "daily_claimed": False, "prize": None,
                      "cooldown_seconds": 86400}
STATE_BONUS_GRANTED = {"ok": True, "score": 10, "streak": 3, "daily_claimed": True, "prize": 5, "cooldown_seconds": 0}
CLAIM_OK = {"ok": True, "message": "Tabriklaymiz! +5 ball", "score": 12, "is_super": False}
DEEP_SPIN_5 = "https://t.me/Birinchiyordam1Bot?start=spin_5"
DEEP_BONUS = "https://t.me/Birinchiyordam1Bot?start=claim_daily"


class LateSpinClaimE2ETest(MiniAppE2EBase):
    def start_spin_claim(self, routes):
        page, calls = self.open_app(routes)
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)
        self.press_main(page, "#btn-confirm-spin")
        self.wait_for_call(calls, "spin/claim")
        return page, calls

    def test_timeout_but_server_already_granted_no_deep_link(self):
        # Server ballni berdi, lekin javob 8 s ichida yetib kelmadi
        page, calls = self.start_spin_claim({
            "state": sequence((200, STATE_OK), (200, STATE_SPIN_GRANTED)),
            "spin/claim": "hang",
        })
        page.clock.fast_forward(9000)                      # 8 s timeout
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('hisobingizga qo')")
        self.assertIn("+5 ball hisobingizga qo'shildi", self.card_text(page))     # farq: 12 - 7
        self.assertEqual(page.inner_text("#global-score-val"), "12")
        tg = self.tg(page)
        self.assertEqual(tg["links"], [])                  # botga otilmadi
        self.assertEqual(tg["closed"], 0)
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim", "state"])

    def test_timeout_super_prize_already_granted_shows_premium_button(self):
        page, _ = self.start_spin_claim({
            "state": sequence((200, {**STATE_OK, "prize": 0}), (200, {**STATE_SPIN_GRANTED, "prize": None})),
            "spin/claim": "hang",
        })
        page.clock.fast_forward(9000)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('SUPER PRIZ!')")
        self.assertIn("50% chegirma faollashtirildi", self.card_text(page))
        self.assertEqual(self.tg(page)["links"], [])
        self.assertEqual(self.tg(page)["closed"], 0)

    def test_5xx_claim_but_server_already_granted_no_deep_link(self):
        page, calls = self.start_spin_claim({
            "state": sequence((200, STATE_OK), (200, STATE_SPIN_GRANTED)),
            "spin/claim": (502, {"ok": False, "error": "server_error"}),
        })
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('hisobingizga qo')")
        self.assertEqual(self.tg(page)["links"], [])

    def test_timeout_and_state_unavailable_falls_back_to_deep_link(self):
        page, calls = self.start_spin_claim({
            "state": sequence((200, STATE_OK), "abort"),
            "spin/claim": "hang",
        })
        page.clock.fast_forward(9000)
        page.wait_for_function("window.__tg.links.length === 1")
        tg = self.tg(page)
        self.assertEqual(tg["links"], [DEEP_SPIN_5])
        self.assertEqual(tg["closed"], 1)

    def test_timeout_and_server_has_not_granted_offers_retry(self):
        page, calls = self.start_spin_claim({
            "state": sequence((200, STATE_OK), (200, STATE_OK)),      # qayta so'ralganda hali pending
            "spin/claim": sequence("hang", (200, CLAIM_OK)),
        })
        page.clock.fast_forward(9000)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Ulanishda xatolik')")
        self.assertEqual(self.tg(page)["links"], [])                  # botga otilmadi
        self.press_main(page, "#wheel-result-msg .result-confirm-btn")           # "Qayta urinish"
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('+5 ball yutdingiz!')")
        self.assertEqual(page.inner_text("#global-score-val"), "12")
        self.assertEqual(self.tg(page)["links"], [])


class LateBonusClaimE2ETest(MiniAppE2EBase):
    def start_bonus_claim(self, routes):
        page, calls = self.open_app(routes)
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        page.click("#btn-open-daily-bonus")
        page.wait_for_selector("#daily-bonus-modal:not(.hidden)")
        self.press_main(page, "#btn-claim-daily-bonus")
        self.wait_for_call(calls, "bonus/claim")
        return page, calls

    def test_timeout_but_server_already_granted_no_deep_link(self):
        page, calls = self.start_bonus_claim({
            "state": sequence((200, BONUS_STATE), (200, STATE_BONUS_GRANTED)),
            "bonus/claim": "hang",
        })
        self.assertIn("kutilmoqda", page.inner_text("#btn-claim-daily-bonus").lower())    # kutish ko'rsatkichi
        page.clock.fast_forward(9000)
        page.wait_for_selector("#daily-bonus-result")
        self.assertEqual(page.inner_text("#daily-bonus-result"), "+3 ball hisobingizga qo'shilgan")   # farq: 10 - 7
        self.assertEqual(page.inner_text("#global-score-val"), "10")
        self.assertIn("bugungi bonus olindi", page.inner_text("#btn-claim-daily-bonus").lower())
        tg = self.tg(page)
        self.assertEqual(tg["links"], [])
        self.assertEqual(tg["closed"], 0)
        self.assertEqual([c[0] for c in calls], ["state", "bonus/claim", "state"])

    def test_timeout_and_state_unavailable_falls_back_to_deep_link(self):
        page, _ = self.start_bonus_claim({
            "state": sequence((200, BONUS_STATE), "abort"),
            "bonus/claim": "hang",
        })
        page.clock.fast_forward(9000)
        page.wait_for_function("window.__tg.links.length === 1")
        tg = self.tg(page)
        self.assertEqual(tg["links"], [DEEP_BONUS])
        self.assertEqual(tg["closed"], 1)

    def test_timeout_and_server_has_not_granted_allows_retry(self):
        page, calls = self.start_bonus_claim({
            "state": sequence((200, BONUS_STATE), (200, BONUS_STATE)),    # qayta so'ralganda hali olinmagan
            "bonus/claim": sequence("hang", (200, {"ok": True, "message": "ok", "points": 3, "streak": 3, "score": 10})),
        })
        page.clock.fast_forward(9000)
        page.wait_for_function("window.__tg.alerts.length === 1")
        self.assertIn("Ulanishda xatolik", self.tg(page)["alerts"][0])
        self.assertEqual(self.tg(page)["links"], [])
        self.assertNotIn("kutilmoqda", page.inner_text("#btn-claim-daily-bonus").lower())      # tugma qayta faol
        self.press_main(page, "#btn-claim-daily-bonus")
        page.wait_for_selector("#daily-bonus-result:has-text('+3 ball, 3-kun')")
        self.assertEqual(self.tg(page)["links"], [])


if __name__ == "__main__":
    unittest.main()
