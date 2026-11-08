"""
test_miniapp_wheel_close_claim_e2e.py — tuzatish: aylantirilgandan keyin "Mukofotni olish" bosilmasdan oyna yopilsa
(X yoki Telegram BackButton), sovrin baribir serverdan BIR MARTA olinadi (/api/spin/claim).
Ikki marta yopish / qayta ochish ikki marta bermaydi; SUPER va limit tugagan holatlar; API yo'q bo'lsa — deep link.
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import CLAIM_OK, STATE_OK, MiniAppE2EBase, sequence

SUPER_STATE = {**STATE_OK, "prize": 0}
SUPER_CLAIM = {"ok": True, "message": "SUPER", "score": 7, "is_super": True}
LIMIT_CLAIM = {"ok": False, "message": "Keyingi urinishgacha 23:59:10 vaqt qoldi.", "score": 7}


class WheelCloseClaimE2ETest(MiniAppE2EBase):
    def spun(self, routes, **kw):
        page, calls = self.open_app(routes, **kw)
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)                       # aylanish tugadi, "Mukofotni olish" bosilmaydi
        return page, calls

    def claims(self, calls):
        return [c[0] for c in calls].count("spin/claim")

    def close_x(self, page):
        page.click("#wheel-modal-close")
        page.wait_for_function("document.getElementById('wheel-modal').style.display === 'none'")

    # (a) X bilan yopilganda ball beriladi
    def test_close_with_x_claims_prize(self):
        page, calls = self.spun({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)})
        self.assertEqual(self.claims(calls), 0)
        self.close_x(page)
        self.wait_for_call(calls, "spin/claim")
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '12'")
        page.wait_for_selector("#toast:not([hidden])")
        self.assertEqual(page.inner_text("#toast"), "+5 ball hisobingizga qo'shildi")
        tg = self.tg(page)
        self.assertEqual(tg["links"], [])                # botga chiqilmaydi
        self.assertEqual(tg["closed"], 0)

    def test_close_with_telegram_back_button_claims_prize(self):
        page, calls = self.spun({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)})
        page.evaluate("window.__backCb()")
        self.wait_for_call(calls, "spin/claim")
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '12'")

    # (b) ikki marta yopish / qayta ochish — ikki marta berilmaydi
    def test_close_twice_and_reopen_claims_once(self):
        page, calls = self.spun({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)})
        self.close_x(page)
        self.wait_for_call(calls, "spin/claim")
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '12'")
        self.open_wheel(page)
        page.wait_for_selector("#wheel-countdown-timer")                      # qayta ochilganda — kutish
        self.assertTrue(page.is_disabled("#btn-spin-wheel"))
        self.close_x(page)
        page.click("#btn-open-wheel")
        page.wait_for_function("document.getElementById('wheel-modal').style.display === 'flex'")
        page.evaluate("window.__backCb()")
        page.wait_for_timeout(300)
        self.assertEqual(self.claims(calls), 1)

    def test_button_then_close_claims_once(self):
        page, calls = self.spun({"state": (200, STATE_OK), "spin/claim": (200, CLAIM_OK)})
        self.press_main(page, "#btn-confirm-spin")
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('+5 ball yutdingiz!')")
        self.close_x(page)
        page.wait_for_timeout(300)
        self.assertEqual(self.claims(calls), 1)

    # (c) SUPER sovrin
    def test_super_prize_claimed_on_close(self):
        page, calls = self.spun({"state": (200, SUPER_STATE), "spin/claim": (200, SUPER_CLAIM)})
        self.close_x(page)
        self.wait_for_call(calls, "spin/claim")
        page.wait_for_selector("#toast:not([hidden])")
        self.assertIn("50% chegirma", page.inner_text("#toast"))
        self.assertEqual(self.tg(page)["links"], [])     # Premium avtomatik ochilmaydi
        self.assertEqual(self.tg(page)["invoices"], [])
        self.open_wheel(page)
        page.wait_for_selector("#wheel-countdown-timer")                      # qayta ochilganda — kutish
        self.assertEqual(self.claims(calls), 1)

    # (d) limit tugagan holat
    def test_limit_reached_server_refuses_and_message_shown(self):
        page, calls = self.spun({"state": (200, STATE_OK), "spin/claim": (200, LIMIT_CLAIM)})
        self.close_x(page)
        self.wait_for_call(calls, "spin/claim")
        page.wait_for_selector("#toast:not([hidden])")
        self.assertEqual(page.inner_text("#toast"), LIMIT_CLAIM["message"])
        self.assertEqual(page.inner_text("#global-score-val"), "7")              # ball qo'shilmadi
        self.assertEqual(self.claims(calls), 1)

    def test_cooldown_active_no_spin_no_claim_on_close(self):
        page, calls = self.open_app({"state": (200, {**STATE_OK, "prize": None, "cooldown_seconds": 3600}),
                                     "spin/claim": (200, CLAIM_OK)})
        self.open_wheel(page)
        page.wait_for_selector("#wheel-countdown-timer")
        self.close_x(page)
        page.wait_for_timeout(300)
        self.assertEqual(self.claims(calls), 0)

    # Zaxira yo'llar
    def test_no_api_close_uses_deep_link(self):
        page, calls = self.spun({}, query="?prize=3", init_data="")
        self.close_x(page)
        self.assertEqual(calls, [])
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=spin_3"])

    def test_connection_error_then_close_retries_once(self):
        # 1-urinish uziladi, holat tekshiruvi "hali berilmagan" deydi; yopilganda yana bir urinish — muvaffaqiyatli
        page, calls = self.spun({
            "state": sequence((200, STATE_OK), (200, STATE_OK)),
            "spin/claim": sequence("abort", (200, CLAIM_OK)),
        })
        self.press_main(page, "#btn-confirm-spin")
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Ulanishda xatolik')")
        self.close_x(page)
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '12'")
        self.assertEqual(self.claims(calls), 2)
        self.close_x(page) if page.is_visible("#wheel-modal-close") else None
        page.wait_for_timeout(300)
        self.assertEqual(self.claims(calls), 2)


if __name__ == "__main__":
    unittest.main()
