"""
test_miniapp_invoice_e2e.py — buyPremium(plan): Mini App ichida Stars invoice (/api/invoice -> tg.openInvoice),
holatlar (paid / cancelled / failed / pending), not_eligible va deep link ZAXIRA yo'li (Playwright).
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import INIT_DATA, STATE_OK, MiniAppE2EBase, sequence

INVOICE_URL = "https://t.me/$AAH-test-invoice"
INVOICE_OK = (200, {"ok": True, "url": INVOICE_URL})
DEEP = "https://t.me/Birinchiyordam1Bot?start="
PAID_TEXT = "To'lov qabul qilindi! Premium bir necha soniyada faollashadi."


class InvoiceE2ETest(MiniAppE2EBase):
    def buy(self, page, plan="buy_plus_30"):
        # Strelkali funksiya Promise qaytarmaydi: page.evaluate async buyPremium tugashini KUTMAYDI (real bosish kabi)
        page.evaluate(f"() => {{ buyPremium('{plan}'); }}")

    def count(self, calls, name):
        return sum(1 for c in calls if c[0] == name)

    def wait_invoice(self, page, n=1):
        page.wait_for_function(f"window.__tg.invoices.length === {n}")

    # ---- asosiy yo'l ---------------------------------------------------------------
    def test_invoice_opens_in_app_without_bot_redirect(self):
        page, calls = self.open_app({"invoice": INVOICE_OK, "state": (200, STATE_OK)})
        self.buy(page, "buy_plus_30")
        self.wait_invoice(page)
        tg = self.tg(page)
        self.assertEqual(tg["invoices"], [INVOICE_URL])
        self.assertEqual(tg["links"], [])                       # botga otilmadi
        self.assertEqual(tg["closed"], 0)                       # tg.close() YO'Q
        invoice_calls = [c for c in calls if c[0] == "invoice"]
        self.assertEqual(invoice_calls, [("invoice", {"init_data": INIT_DATA, "plan": "buy_plus_30"})])

    def test_all_plans_are_sent_as_is(self):
        page, calls = self.open_app({"invoice": INVOICE_OK})
        for i, plan in enumerate(("buy_pro_7", "buy_plus_30", "buy_ultra_30"), 1):
            self.buy(page, plan)
            self.wait_invoice(page, i)
            page.evaluate("window.__invoiceCb('cancelled')")       # keyingi bosish uchun bayroq bo'shaydi
        self.assertEqual([c[1]["plan"] for c in calls if c[0] == "invoice"],
                         ["buy_pro_7", "buy_plus_30", "buy_ultra_30"])

    def test_real_premium_modal_button_uses_invoice(self):
        page, calls = self.open_app({"invoice": INVOICE_OK})
        page.click('nav [data-tab="tab-health"]')
        page.click("#btn-open-premium")
        page.click("#premium-modal .plan-card:has(input[value='buy_plus_30'])")     # tarif kartasi
        self.press_main(page, "#premium-continue")                                   # "★ 150 — Davom etish"
        self.wait_invoice(page)
        self.assertEqual([c[1]["plan"] for c in calls if c[0] == "invoice"], ["buy_plus_30"])
        self.assertEqual(self.tg(page)["links"], [])

    # ---- tg.openInvoice natijalari ---------------------------------------------------
    def test_paid_shows_message_and_refreshes_state(self):
        page, calls = self.open_app({"invoice": INVOICE_OK, "state": (200, STATE_OK)})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.assertEqual(self.count(calls, "state"), 1)
        self.buy(page)
        self.wait_invoice(page)
        page.evaluate("window.__invoiceCb('paid')")
        self.assertEqual(self.tg(page)["alerts"], [PAID_TEXT])
        self.assertEqual(self.tg(page)["closed"], 0)
        page.evaluate("getAppState(60000)")                        # kesh bekor qilingan: qayta so'raladi
        self.assertEqual(self.count(calls, "state"), 2)

    def test_cancelled_is_silent(self):
        page, calls = self.open_app({"invoice": INVOICE_OK, "state": (200, STATE_OK)})
        self.buy(page)
        self.wait_invoice(page)
        page.evaluate("window.__invoiceCb('cancelled')")
        tg = self.tg(page)
        self.assertEqual((tg["alerts"], tg["links"], tg["closed"]), ([], [], 0))
        page.evaluate("getAppState(60000)")
        self.assertEqual(self.count(calls, "state"), 1)            # holat bekor qilinmagan

    def test_failed_and_pending_messages(self):
        page, _ = self.open_app({"invoice": INVOICE_OK})
        for i, (status, text) in enumerate((("failed", "To'lov amalga oshmadi. Qayta urinib ko'ring."),
                                            ("pending", "To'lov tekshirilmoqda...")), 1):
            self.buy(page)
            self.wait_invoice(page, i)
            page.evaluate(f"window.__invoiceCb('{status}')")
            self.assertEqual(self.tg(page)["alerts"][-1], text)
        self.assertEqual(self.tg(page)["links"], [])

    # ---- huquq yo'q ----------------------------------------------------------------------
    def test_not_eligible_shows_server_message_no_invoice_no_deep_link(self):
        msg = "Siz allaqachon Premium Plus foydalanuvchisiz! Joriy tarifingiz sotib olmoqchi bo'lgan tarifdan yuqoriroq yoki teng."
        page, calls = self.open_app({"invoice": (200, {"ok": False, "error": "not_eligible", "message": msg})})
        self.buy(page, "buy_pro_7")
        page.wait_for_function("window.__tg.alerts.length === 1")
        tg = self.tg(page)
        self.assertEqual(tg["alerts"], [msg])
        self.assertEqual((tg["invoices"], tg["links"], tg["closed"]), ([], [], 0))
        # bayroq bo'shagan: qayta bosish mumkin
        self.buy(page, "buy_pro_7")
        page.wait_for_function("window.__tg.alerts.length === 2")
        self.assertEqual(self.count(calls, "invoice"), 2)

    # ---- ZAXIRA: deep link (o'zgarishsiz) ---------------------------------------------
    def assert_deep_link_fallback(self, page, plan="buy_plus_30"):
        page.wait_for_function("window.__tg.links.length === 1")
        tg = self.tg(page)
        self.assertEqual(tg["links"], [DEEP + plan])
        self.assertEqual(tg["invoices"], [])
        self.assertEqual(tg["closed"], 0)

    def test_fallback_on_http_errors(self):
        for status in (500, 502, 403, 429, 404, 400):
            with self.subTest(status=status):
                page, calls = self.open_app({"invoice": (status, {"ok": False, "error": "x"})})
                self.buy(page)
                self.assert_deep_link_fallback(page)
                self.assertEqual(self.count(calls, "invoice"), 1)

    def test_fallback_on_network_error(self):
        page, _ = self.open_app({"invoice": "abort"})
        self.buy(page)
        self.assert_deep_link_fallback(page)

    def test_fallback_on_timeout(self):
        page, calls = self.open_app({"invoice": "hang"})
        self.buy(page)
        self.wait_for_call(calls, "invoice")
        page.clock.fast_forward(9000)                              # 8 s timeout
        self.assert_deep_link_fallback(page)

    def test_fallback_on_unexpected_ok_false_or_missing_url(self):
        for spec in ((200, {"ok": False, "error": "server_error"}), (200, {"ok": True}), (200, {"ok": True, "url": ""}),
                     (200, {"unexpected": 1})):
            with self.subTest(spec=spec):
                page, _ = self.open_app({"invoice": spec})
                self.buy(page)
                self.assert_deep_link_fallback(page)

    def test_fallback_without_init_data_makes_no_api_call(self):
        page, calls = self.open_app({"invoice": INVOICE_OK}, init_data="")
        self.buy(page)
        self.assert_deep_link_fallback(page)
        self.assertEqual(self.count(calls, "invoice"), 0)

    def test_fallback_when_open_invoice_missing_makes_no_api_call(self):
        page, calls = self.open_app({"invoice": INVOICE_OK}, init_script="delete window.Telegram.WebApp.openInvoice;")
        self.buy(page)
        self.assert_deep_link_fallback(page)
        self.assertEqual(self.count(calls, "invoice"), 0)

    def test_fallback_when_open_invoice_throws(self):
        page, _ = self.open_app({"invoice": INVOICE_OK},
                                init_script="window.Telegram.WebApp.openInvoice = () => { throw new Error('boom'); };")
        self.buy(page)
        self.assert_deep_link_fallback(page)

    def test_fallback_for_each_plan_uses_same_plan_in_link(self):
        for plan in ("buy_pro_7", "buy_ultra_30"):
            with self.subTest(plan=plan):
                page, _ = self.open_app({"invoice": (500, {"ok": False})})
                self.buy(page, plan)
                self.assert_deep_link_fallback(page, plan)

    # ---- qayta bosish ---------------------------------------------------------------------
    def test_double_press_sends_single_request_until_response(self):
        page, calls = self.open_app({"invoice": sequence("hang", INVOICE_OK)})
        self.buy(page)
        self.wait_for_call(calls, "invoice")
        self.buy(page)                                             # javob kelguncha: e'tiborga olinmaydi
        self.buy(page)
        self.assertEqual(self.count(calls, "invoice"), 1)
        page.clock.fast_forward(9000)                              # timeout -> zaxira, bayroq bo'shaydi
        self.assert_deep_link_fallback(page)
        self.buy(page)                                             # endi yana mumkin
        self.wait_invoice(page)
        self.assertEqual(self.count(calls, "invoice"), 2)

    def test_cannot_press_again_while_invoice_is_open(self):
        page, calls = self.open_app({"invoice": INVOICE_OK})
        self.buy(page)
        self.wait_invoice(page)
        self.buy(page)                                             # invoice ochiq: yangi so'rov yo'q
        self.assertEqual(self.count(calls, "invoice"), 1)
        page.evaluate("window.__invoiceCb('cancelled')")
        self.buy(page)
        self.wait_invoice(page, 2)
        self.assertEqual(self.count(calls, "invoice"), 2)

    # ---- SUPER PRIZ kartasi -----------------------------------------------------------------
    def test_super_prize_premium_button_uses_invoice_for_plus(self):
        page, calls = self.open_app({
            "state": (200, {**STATE_OK, "prize": 0}),
            "spin/claim": (200, {"ok": True, "message": "SUPER", "score": 7, "is_super": True}),
            "invoice": INVOICE_OK,
        })
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-desc:has-text('50% chegirma faollashtirildi')")
        self.press_main(page, "#wheel-result-msg .result-confirm-btn")   # "Premium olish"
        self.wait_invoice(page)
        tg = self.tg(page)
        self.assertEqual(tg["invoices"], [INVOICE_URL])
        self.assertEqual((tg["links"], tg["closed"]), ([], 0))
        self.assertEqual([c[1] for c in calls if c[0] == "invoice"], [{"init_data": INIT_DATA, "plan": "buy_plus_30"}])


if __name__ == "__main__":
    unittest.main()
