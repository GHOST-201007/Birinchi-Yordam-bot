"""
test_miniapp_tier_names_e2e.py — Mini App (brauzerda / Playwright): tarif NOMLARI va "Uzaytirish" ro'yxati.

Ichki kod pro = ko'rinadigan "Plus", plus = "Pro", ultra = "Ultra" (app.js PREMIUM_TIERS — Python'dagi
database.TIER_DISPLAY bilan bir xil; tests/test_tier_names.py solishtiradi). Narx / muddat / value'lar o'zgarmagan.
"Uzaytirish" oynasi faqat sotib olish MUMKIN bo'lgan tariflarni ko'rsatadi: joriy tarif (yana N kun) va undan yuqorilari;
muddatsiz Premiumda "Uzaytirish" yo'q. Asos: tests/e2e_base.py
"""
import database
from tests.e2e_base import STATE_OK
from tests.test_miniapp_premium_visibility_e2e import PremiumE2EBase, state

CARD = "#premium-modal .plan-card:has(input[value='{}'])"
PLAN_BY_TIER = {"pro": "buy_pro_7", "plus": "buy_plus_30", "ultra": "buy_ultra_30"}
NAME = {tier: f"Premium {name}" for tier, name in database.TIER_DISPLAY.items()}


class TierNamesE2ETest(PremiumE2EBase):
    def visible_plans(self, page):
        return page.evaluate("""() => [...document.querySelectorAll('#premium-modal .plan-card')]
            .filter(c => c.offsetParent !== null)
            .map(c => ({ plan: c.querySelector('input').value,
                         name: c.querySelector('.plan-name').childNodes[0].textContent,
                         days: c.querySelector('.plan-days').textContent,
                         price: c.querySelector('.plan-price').textContent,
                         checked: c.querySelector('input').checked }))""")

    def open_modal(self, page):
        page.evaluate("openPremiumModalFromUi()")
        page.wait_for_selector("#premium-modal:not(.hidden)")

    # ---- bepul foydalanuvchi: uchala tarif, yangi nomlar --------------------------------------
    def test_free_user_sees_three_plans_with_new_names(self):
        page, _ = self.open_state(state())
        self.open_modal(page)
        plans = self.visible_plans(page)
        self.assertEqual([(p["plan"], p["name"], p["days"], p["price"]) for p in plans], [
            ("buy_pro_7", "Premium Plus", "7 kun", "★ 50"),
            ("buy_plus_30", "Premium Pro", "30 kun", "★ 150"),
            ("buy_ultra_30", "Premium Ultra", "30 kun", "★ 300"),
        ])
        self.assertEqual([p["name"] for p in plans], [NAME["pro"], NAME["plus"], NAME["ultra"]])   # Python bilan bir xil
        self.assertEqual([p["plan"] for p in plans if p["checked"]], ["buy_plus_30"])             # standart: o'rtacha tarif
        self.assertEqual(page.inner_text("#premium-title"), "Premium")
        self.assertEqual(self.tg(page)["mainText"], "★ 150 — Davom etish")

    def test_data_tier_attributes_keep_internal_codes(self):
        page, _ = self.open_state(state())
        tiers = page.evaluate("""() => [...document.querySelectorAll('.plan-name[data-tier]')]
            .map(e => [e.dataset.tier, e.closest('.plan-card').querySelector('input').value])""")
        self.assertEqual(sorted(set(map(tuple, tiers))),
                         sorted((tier, plan) for tier, plan in PLAN_BY_TIER.items()))

    def test_ai_offer_card_uses_new_names(self):
        page, _ = self.open_state(state())
        names = page.evaluate("""() => [...document.querySelectorAll('#ai-premium-offer .plan-name')]
            .map(e => e.childNodes[0].textContent)""")
        self.assertEqual(names, ["Premium Plus", "Premium Pro", "Premium Ultra"])

    def test_header_card_and_color_follow_the_tier_not_the_name(self):
        for tier, name in database.TIER_DISPLAY.items():
            with self.subTest(tier=tier):
                page, _ = self.open_health(state(tier, days=5))
                self.assertEqual(page.inner_text("#hdr-premium-name"), f"{name} · 5 kun")
                self.assertEqual(page.inner_text("#mp-tier"), f"Premium {name}")
                self.assertEqual(self.body_classes(page), [f"tier-{tier}"])               # CSS klass ichki kod bo'yicha

    # ---- "Uzaytirish" ro'yxati ------------------------------------------------------------------
    def test_ultra_extension_list_has_only_ultra(self):
        page, _ = self.open_health(state("ultra", days=5))
        page.click("#mp-extend")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        plans = self.visible_plans(page)
        self.assertEqual([(p["plan"], p["name"], p["days"], p["price"], p["checked"]) for p in plans],
                         [("buy_ultra_30", "Premium Ultra", "yana 30 kun", "★ 300", True)])
        self.assertEqual(page.inner_text("#premium-title"), "Premiumni uzaytirish")
        self.assertEqual(self.tg(page)["mainText"], "★ 300 — Uzaytirish")
        for hidden in ("buy_pro_7", "buy_plus_30"):
            self.assertFalse(page.is_visible(CARD.format(hidden)), hidden)

    def test_pro_extension_list_is_pro_and_ultra(self):
        page, _ = self.open_health(state("plus", days=4))
        page.click("#mp-extend")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        plans = self.visible_plans(page)
        self.assertEqual([(p["plan"], p["name"], p["days"], p["checked"]) for p in plans], [
            ("buy_plus_30", "Premium Pro", "yana 30 kun", True),
            ("buy_ultra_30", "Premium Ultra", "30 kun", False),
        ])
        self.assertFalse(page.is_visible(CARD.format("buy_pro_7")))                       # pastroq tarif ko'rinmaydi
        self.assertEqual(self.tg(page)["mainText"], "★ 150 — Uzaytirish")
        page.click(CARD.format("buy_ultra_30"))                                             # yuqoriroqqa o'tish — oddiy xarid
        self.assertEqual(self.tg(page)["mainText"], "★ 300 — Davom etish")

    def test_plus_extension_list_has_all_three_with_its_own_marked(self):
        page, _ = self.open_health(state("pro", days=2))
        page.click("#mp-extend")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        plans = self.visible_plans(page)
        self.assertEqual([(p["plan"], p["days"], p["checked"]) for p in plans], [
            ("buy_pro_7", "yana 7 kun", True), ("buy_plus_30", "30 kun", False), ("buy_ultra_30", "30 kun", False)])
        self.assertEqual(self.tg(page)["mainText"], "★ 50 — Uzaytirish")

    def test_extension_main_button_buys_the_current_tier(self):
        page, _ = self.open_health(state("ultra", days=5))
        page.evaluate("() => { window.__bought = []; window.buyPremium = (p) => window.__bought.push(p); }")
        page.click("#mp-extend")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        page.evaluate("window.__mainCb()")
        self.assertEqual(page.evaluate("window.__bought"), ["buy_ultra_30"])

    def test_banner_extend_opens_the_same_filtered_list(self):
        page, _ = self.open_state(state("ultra", hours=20))
        page.wait_for_selector("#prem-banner:not([hidden])")
        page.click("#prem-banner-extend")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        self.assertEqual([p["plan"] for p in self.visible_plans(page)], ["buy_ultra_30"])

    def test_unlimited_has_no_extend_button_and_no_purchasable_plans(self):
        page, _ = self.open_health(state("ultra", unlimited=True))
        self.assertFalse(page.is_visible("#mp-extend"))
        self.open_modal(page)                                                              # zaxira yo'l: kod orqali ochilsa ham
        self.assertEqual(self.visible_plans(page), [])

    def test_list_follows_state_changes(self):
        """To'lovdan keyin yangi holat kelsa (patchAppState) oyna ro'yxati yangilanadi; muddati o'tsa — hammasi qaytadi."""
        page, _ = self.open_health(state("plus", days=4))
        self.patch(page, premium_type="ultra")
        self.assertEqual([p["plan"] for p in self.visible_plans_when_open(page)], ["buy_ultra_30"])
        self.patch(page, is_premium=False, premium_type="free", premium_expires_at=None, premium_days_left=None)
        self.assertEqual([p["plan"] for p in self.visible_plans_when_open(page)],
                         ["buy_pro_7", "buy_plus_30", "buy_ultra_30"])
        self.assertEqual(page.inner_text("#premium-title"), "Premium")

    def visible_plans_when_open(self, page):
        page.evaluate("document.getElementById('premium-modal').classList.remove('hidden')")
        return self.visible_plans(page)

    def test_state_without_premium_fields_keeps_old_behaviour(self):
        page, _ = self.open_state({**STATE_OK, "is_premium": False})
        self.open_modal(page)
        self.assertEqual(len(self.visible_plans(page)), 3)


if __name__ == "__main__":
    import unittest
    unittest.main()
