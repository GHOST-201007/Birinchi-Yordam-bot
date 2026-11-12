"""
test_miniapp_ai_offer_e2e.py — AI tabida Premium taklif kartasi: bepul savol ishlatilgach
(/api/state: ai_remaining = 0, is_premium = false). G uslubi (teal). Karta o'zining tarif kartalarini ko'rsatmaydi:
"★ Premium tariflari" BITTA Premium oynasini (#premium-modal: tariflar + 100 ball) ochadi; to'lov o'sha oynada
mavjud buyPremium oqimi bilan (/api/invoice -> tg.openInvoice; zaxira — deep link).
"""
import re
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")
FREE_USED = {**STATE_OK, "is_premium": False, "premium_type": "free", "ai_remaining": 0, "ai_limit": 1}
INVOICE_OK = (200, {"ok": True, "url": "https://t.me/$invoice-test"})
RADIO = '#premium-modal input[name="premium-plan"][value="{}"]'


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
        self.assertTrue(page.is_enabled("#ai-input"))                                    # suhbat ochiq

    def test_shown_after_free_question_used(self):
        page, _ = self.open_ai(FREE_USED)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertTrue(page.is_disabled("#ai-input"))                                   # yozish paneli o'chiq
        self.assertTrue(page.is_disabled("#ai-send"))
        self.assertEqual(page.inner_text("#ai-offer-title"), "Bepul savolingiz ishlatildi")
        self.assertEqual(page.get_attribute("#ai-premium-offer .ai-offer-badge use", "href"), "#i-crown")
        self.assertEqual(page.inner_text("#ai-offer-buy"), "★ Premium tariflari")
        self.assertEqual(page.inner_text(".ai-offer-note"), "To'lov — Telegram Stars orqali yoki 100 ball evaziga")
        self.assertIsNone(EMOJI.search(page.inner_text("#ai-premium-offer").replace("★", "")))   # ★ — narx belgisi
        hero_bg = page.evaluate("getComputedStyle(document.querySelector('.ai-offer-hero')).backgroundColor")
        self.assertEqual(hero_bg, "rgb(14, 124, 114)")                                   # teal (--primary)

    def test_card_has_no_plans_of_its_own(self):
        """Premium uchun BITTA oyna: karta ichida tarif kartalari / radio / imkoniyatlar ro'yxati yo'q."""
        page, _ = self.open_ai(FREE_USED)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertEqual(page.locator("#ai-premium-offer .plan-card").count(), 0)
        self.assertEqual(page.locator("#ai-premium-offer input[type=radio]").count(), 0)
        self.assertEqual(page.locator("#premium-modal").count(), 1)

    def test_hidden_for_premium_user(self):
        page, _ = self.open_ai({**FREE_USED, "is_premium": True, "premium_type": "pro"})
        page.wait_for_selector("#hdr-premium:not([hidden])")
        self.assertFalse(page.is_visible("#ai-premium-offer"))

    def test_button_opens_the_single_premium_sheet(self):
        page, _ = self.open_ai(FREE_USED)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertTrue(page.is_hidden("#premium-modal"))
        page.click("#ai-offer-buy")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        plans = page.evaluate("""() => [...document.querySelectorAll('#premium-modal .plan-card')]
            .filter(c => c.offsetParent !== null).map(c => c.querySelector('input').value)""")
        self.assertEqual(plans, ["buy_pro_7", "buy_plus_30", "buy_ultra_30"])
        self.assertTrue(page.is_visible("#pm-points"))                                   # 100 ball bo'limi ham shu oynada
        self.assertEqual(self.tg(page)["mainText"], "★ 150 — Davom etish")

    def test_buy_uses_existing_invoice_flow_from_the_sheet(self):
        page, calls = self.open_ai(FREE_USED)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        page.click("#ai-offer-buy")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        page.click("#premium-modal .plan-card:has(input[value='buy_ultra_30'])")
        self.assertTrue(page.is_checked(RADIO.format("buy_ultra_30")))
        page.evaluate("window.__mainCb()")                                               # MainButton
        self.wait_for_call(calls, "invoice")
        page.wait_for_function("window.__tg.invoices.length === 1")
        self.assertEqual([c[1]["plan"] for c in calls if c[0] == "invoice"], ["buy_ultra_30"])
        self.assertEqual(self.tg(page)["invoices"], ["https://t.me/$invoice-test"])     # tg.openInvoice
        self.assertEqual(self.tg(page)["links"], [])

    def test_fallback_deep_link_when_invoice_unavailable(self):
        page, _ = self.open_ai(FREE_USED, routes={"invoice": (500, {"ok": False})})
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        page.click("#ai-offer-buy")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        page.evaluate("window.__mainCb()")
        page.wait_for_function("window.__tg.links.length === 1")
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=buy_plus_30"])

    def test_contrast_light_and_dark(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_ai(FREE_USED, init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                page.wait_for_selector("#ai-premium-offer:not([hidden])")
                for sel in ("#ai-offer-title", ".ai-offer-text", "#ai-offer-buy", ".ai-offer-note"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)


if __name__ == "__main__":
    unittest.main()
