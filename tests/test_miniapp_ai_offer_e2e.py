"""
test_miniapp_ai_offer_e2e.py — AI tabida Premium taklif kartasi: bepul savol ishlatilgach
(/api/state: ai_remaining = 0, is_premium = false). G uslubi (teal), tarif kartalari, "★ Premium olish" ->
mavjud buyPremium (/api/invoice -> tg.openInvoice; zaxira — deep link).
"""
import re
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")
FREE_USED = {**STATE_OK, "is_premium": False, "premium_type": "free", "ai_remaining": 0, "ai_limit": 1}
INVOICE_OK = (200, {"ok": True, "url": "https://t.me/$invoice-test"})
RADIO = '#ai-premium-offer input[name="ai-offer-plan"][value="{}"]'


class AiOfferE2ETest(MiniAppE2EBase):
    def open_ai(self, state, **kw):
        routes = {"state": (200, state), "invoice": INVOICE_OK}
        routes.update(kw.pop("routes", {}))
        page, calls = self.open_app(routes, **kw)
        page.wait_for_selector("#global-score:not([hidden])")
        page.click('nav [data-tab="tab-ai"]')
        return page, calls

    def test_hidden_while_free_question_available(self):
        page, _ = self.open_ai({**FREE_USED, "ai_remaining": 1})
        self.assertFalse(page.is_visible("#ai-premium-offer"))
        self.assertTrue(page.is_visible("#ai-soon"))

    def test_shown_after_free_question_used(self):
        page, _ = self.open_ai(FREE_USED)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertFalse(page.is_visible("#ai-soon"))
        self.assertEqual(page.inner_text("#ai-offer-title"), "Bepul savolingiz ishlatildi")
        self.assertEqual(page.get_attribute("#ai-premium-offer .ai-offer-badge use", "href"), "#i-crown")
        prices = page.evaluate("[...document.querySelectorAll('#ai-premium-offer .plan-price')].map(e => e.textContent)")
        self.assertEqual(prices, ["★ 50", "★ 150", "★ 300"])
        self.assertTrue(page.is_checked(RADIO.format("buy_plus_30")))
        self.assertEqual(page.inner_text("#ai-offer-buy"), "★ Premium olish")
        self.assertIsNone(EMOJI.search(page.inner_text("#ai-premium-offer").replace("★", "")))   # ★ — narx belgisi
        hero_bg = page.evaluate("getComputedStyle(document.querySelector('.ai-offer-hero')).backgroundColor")
        self.assertEqual(hero_bg, "rgb(14, 124, 114)")                                   # teal (--primary)

    def test_hidden_for_premium_user(self):
        page, _ = self.open_ai({**FREE_USED, "is_premium": True, "premium_type": "pro"})
        page.wait_for_selector("#hdr-premium:not([hidden])")
        self.assertFalse(page.is_visible("#ai-premium-offer"))

    def test_plan_selection_updates_features_and_keyboard(self):
        page, _ = self.open_ai(FREE_USED)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertEqual(page.inner_text("#ai-offer-features li:first-child"), "Kuniga 30 AI so'rov")
        page.focus(RADIO.format("buy_plus_30"))
        page.keyboard.press("ArrowDown")                                                  # radio — klaviatura
        self.assertTrue(page.is_checked(RADIO.format("buy_ultra_30")))
        self.assertEqual(page.inner_text("#ai-offer-features li:first-child"), "Kuniga 100 AI so'rov")

    def test_buy_uses_existing_invoice_flow(self):
        page, calls = self.open_ai(FREE_USED)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        page.click("#ai-premium-offer .plan-card:has(input[value='buy_ultra_30'])")
        page.click("#ai-offer-buy")
        self.wait_for_call(calls, "invoice")
        page.wait_for_function("window.__tg.invoices.length === 1")
        self.assertEqual([c[1]["plan"] for c in calls if c[0] == "invoice"], ["buy_ultra_30"])
        self.assertEqual(self.tg(page)["invoices"], ["https://t.me/$invoice-test"])     # tg.openInvoice
        self.assertEqual(self.tg(page)["links"], [])

    def test_fallback_deep_link_when_invoice_unavailable(self):
        page, _ = self.open_ai(FREE_USED, routes={"invoice": (500, {"ok": False})})
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        page.click("#ai-offer-buy")
        page.wait_for_function("window.__tg.links.length === 1")
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=buy_plus_30"])

    def test_contrast_light_and_dark(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_ai(FREE_USED, init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                page.wait_for_selector("#ai-premium-offer:not([hidden])")
                for sel in ("#ai-offer-title", ".ai-offer-text", "#ai-premium-offer .plan-name", "#ai-premium-offer .plan-days",
                            "#ai-premium-offer .plan-price", "#ai-premium-offer .plan-chip", "#ai-offer-buy",
                            ".ai-offer-note", "#ai-offer-features li span:last-child"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)


if __name__ == "__main__":
    unittest.main()
