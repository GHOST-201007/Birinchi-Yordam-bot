"""
test_miniapp_super_discount_e2e.py — SUPER PRIZ: 24 soatlik −50% Pro taklifi (Mini App, brauzerda / Playwright).

  * yutgan zahoti taklif kartasi: Pro nomi + ikonka, chizilgan 150, katta 75, −50%, qolgan vaqt, "Sotib olish"
  * 24 soat davomida: Premium oynasidagi Pro kartasi, bosh ekrandagi Premium kartasi ("−50% · 5 soat qoldi"),
    AI limit taklifi — hammasida chegirmali narx va qolgan vaqt (oddiy narx yashirin)
  * taymer 0 ga yetsa sahifani yangilamasdan oddiy narx qaytadi; to'lovdan keyin darhol yo'qoladi
  * Ultra / muddatsiz Premiumda taklif yo'q; qurilma soati noto'g'ri bo'lsa ham qolgan vaqt serverdan
  * 360 px, light/dark kontrast >= 4.5:1, prefers-reduced-motion, innerHTML / inline style / inline handler yo'q
Asos: tests/e2e_base.py (soat Playwright page.clock bilan boshqariladi)
"""
import datetime as dt
import os
import re
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK
from tests.test_miniapp_premium_visibility_e2e import PremiumE2EBase, state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UZ = dt.timezone(dt.timedelta(hours=5))
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")
HOUR = 3600 * 1000
OFF = {"active": False, "price": 75, "old_price": 150, "expires_at": None, "seconds_left": 0}
INVOICE_OK = (200, {"ok": True, "url": "https://t.me/$invoice-test"})
RADIO = '#premium-modal input[name="premium-plan"][value="{}"]'


def disc(hours=24, minutes=0, offset_hours=0):
    """/api/state `discount` maydoni (faol). seconds_left — server hisobi; expires_at — Toshkent vaqti (ko'rsatish uchun emas)."""
    seconds = hours * 3600 + minutes * 60
    expires = dt.datetime.now(UZ) + dt.timedelta(seconds=seconds, hours=offset_hours)
    return {"active": True, "price": 75, "old_price": 150, "expires_at": expires.isoformat(timespec="seconds"),
            "seconds_left": seconds}


def super_state(**kw):
    return {**STATE_OK, "prize": 0, "prize_type": "super", "is_premium": False, "premium_type": "free",
            "premium_expires_at": None, "premium_unlimited": False, "premium_days_left": None,
            "ai_remaining": 1, "ai_limit": 1, "ai_bonus": 0, "discount": OFF, **kw}


def super_claim(discount, **kw):
    return (200, {"ok": True, "message": "SUPER", "score": 7, "is_super": True, "prize": 0, "prize_type": "super",
                  "points": 0, "tip": None, "discount": discount, **kw})


# ═══════════════════════════ Statik tekshiruvlar (brauzersiz) ═══════════════════════════
def function_source(js, name):
    """`function name(` dan o'sha funksiyaning yopilishigacha (indent bo'yicha)."""
    m = re.search(rf"^([ \t]*)(?:async )?function {name}\(", js, re.M)
    assert m, name
    indent = m.group(1)
    end = js.index(f"\n{indent}}}\n", m.end())
    return js[m.start(): end + len(indent) + 2]


class SuperDiscountStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "app", "app.js"), encoding="utf-8") as f:
            cls.js = f.read()
        with open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8") as f:
            cls.html = f.read()
        with open(os.path.join(ROOT, "app", "style.css"), encoding="utf-8") as f:
            cls.css = f.read()

    FUNCTIONS = ("formatDiscountLeft", "discountInfo", "discountOffer", "buildDealBlock", "refreshDiscountTexts",
                 "stopDiscountTimer", "expireDiscountLocally", "discountTick", "syncDiscountUi", "renderPlanDiscount",
                 "renderAiDeal", "renderSuperPrizeCard", "superCardModeNow")

    def test_no_innerhtml_in_the_discount_code(self):
        for name in self.FUNCTIONS:
            with self.subTest(function=name):
                self.assertNotIn("innerHTML", function_source(self.js, name))
                self.assertNotIn("insertAdjacentHTML", function_source(self.js, name))
                self.assertNotIn("outerHTML", function_source(self.js, name))

    def test_no_inline_style_or_handlers_in_the_discount_code(self):
        for name in self.FUNCTIONS:
            with self.subTest(function=name):
                src = function_source(self.js, name)
                self.assertNotIn(".style.", src)
                self.assertNotIn("setAttribute('style'", src)
                self.assertNotIn("setAttribute('on", src)
                self.assertNotIn(".onclick", src)

    def test_new_markup_has_no_inline_style_or_handlers(self):
        for marker in ('class="plan-deal"', 'id="ai-offer-deal"'):
            start = self.html.index(marker)
            snippet = self.html[start: start + 420]
            self.assertNotRegex(snippet, r"\sstyle=")
            self.assertNotRegex(snippet, r"\son[a-z]+=")

    def test_icons_come_from_the_sprite_not_emoji(self):
        start = self.js.index("SUPER PRIZ CHEGIRMASI: Pro (ichki plus")
        block = self.js[start: self.js.index("// Hamma \"qolgan vaqt\" joylari")]
        strings = "".join(re.findall(r"'[^'\n]*'|\"[^\"\n]*\"", block))
        self.assertIsNone(EMOJI.search(strings.replace("★", "")))
        self.assertIn("aiIcon(PREMIUM_TIERS.plus.icon)", block)
        self.assertIn("aiIcon('clock')", block)
        for sprite in ("i-gem", "i-clock"):
            self.assertIn(f'id="{sprite}"', self.html)

    def test_css_block_has_no_emoji_and_uses_tokens_only(self):
        block = self.css[self.css.index("SUPER PRIZ CHEGIRMASI (24 soat"):]
        self.assertIsNone(EMOJI.search(block))
        self.assertNotRegex(block, r"(?<![\w-])#[0-9A-Fa-f]{6}\b")                # rang kodlari yo'q: faqat tokenlar
        self.assertNotIn("animation", block)                     # taymer faqat matn: animatsiya yo'q
        self.assertNotIn("transition", block)

    def test_one_price_formula_on_the_client(self):
        """Mijoz narxni o'zi hisoblamaydi: faqat serverdan (discount.price / old_price)."""
        for name in ("discountInfo", "discountOffer", "buildDealBlock", "renderPlanDiscount"):
            src = function_source(self.js, name)
            self.assertNotRegex(src, r"\b150\b|\b75\b|/ ?2\b|\* ?0\.5")


# ═══════════════════════════ Yutgan zahoti: taklif kartasi ═══════════════════════════
class SuperOfferCardE2ETest(PremiumE2EBase):
    def open_win(self, claim=None, st=None, **kw):
        routes = {"state": (200, st or super_state()), "spin/claim": claim or super_claim(disc(24)),
                  "invoice": INVOICE_OK}
        routes.update(kw.pop("routes", {}))
        page, calls = self.open_app(routes, **kw)
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .deal")
        return page, calls

    def test_offer_card_shows_name_old_new_price_badge_and_time(self):
        page, calls = self.open_win()
        card = "#wheel-result-msg"
        self.assertEqual(page.inner_text(f"{card} .result-title"), "SUPER PRIZ!")
        self.assertEqual(page.inner_text(f"{card} .deal-name"), "Premium Pro — 30 kun")
        self.assertEqual(page.inner_text(f"{card} .deal-old"), "★ 150")
        self.assertEqual(page.inner_text(f"{card} .deal-new"), "★ 75")
        self.assertEqual(page.inner_text(f"{card} .deal-badge"), "−50%")
        self.assertEqual(page.inner_text(f"{card} .deal-left"), "24 soat qoldi")
        self.assertEqual(page.inner_text(f"{card} .result-confirm-btn"), "Sotib olish")
        self.assertEqual(page.get_attribute(f"{card} .deal-head use", "href"), "#i-gem")           # PREMIUM_TIERS.plus.icon
        self.assertEqual(page.get_attribute(f"{card} .deal-left use", "href"), "#i-clock")
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.deal-old')).textDecorationLine"),
                         "line-through")
        self.assertIsNone(EMOJI.search(page.inner_text(f"{card} .deal").replace("★", "")))
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])                              # qo'shimcha so'rov yo'q

    def test_old_price_is_announced_to_screen_readers(self):
        page, _ = self.open_win()
        text = page.evaluate("document.querySelector('#wheel-result-msg .deal-prices').textContent")
        self.assertIn("Eski narx: ★ 150", text)
        self.assertIn("Yangi narx: ★ 75", text)

    def test_buy_button_opens_the_discounted_invoice_flow(self):
        page, calls = self.open_win()
        self.press_main(page, "#btn-super-buy")
        page.wait_for_function("window.__tg.invoices.length === 1")
        self.assertEqual([c[1]["plan"] for c in calls if c[0] == "invoice"], ["buy_plus_30"])
        self.assertEqual(self.tg(page)["invoices"], ["https://t.me/$invoice-test"])

    def test_time_left_is_updated_every_minute(self):
        page, _ = self.open_win()
        page.clock.fast_forward(HOUR)
        page.wait_for_function("document.querySelector('#wheel-result-msg .deal-left').textContent === '23 soat qoldi'")
        page.clock.fast_forward(20 * 60 * 1000)
        page.wait_for_function("document.querySelector('#wheel-result-msg .deal-left').textContent === '22 soat 40 daqiqa qoldi'")

    def test_card_reverts_when_the_timer_reaches_zero(self):
        page, _ = self.open_win(claim=super_claim(disc(0, 30)))
        self.assertEqual(page.inner_text("#wheel-result-msg .deal-left"), "30 daqiqa qoldi")
        page.clock.fast_forward(31 * 60 * 1000)
        page.wait_for_selector("#wheel-result-msg .deal", state="detached")
        self.assertIn("muddati tugadi", page.inner_text("#wheel-result-msg .result-desc"))
        self.assertEqual(page.locator("#wheel-result-msg .result-confirm-btn").count(), 0)       # sotib olish tugmasi yo'q
        self.assertEqual(page.locator("#wheel-result-msg .deal-new").count(), 0)

    def test_winning_again_resets_the_timer_to_a_fresh_24_hours(self):
        page, _ = self.open_win(st=super_state(discount=disc(2)), claim=super_claim(disc(24)))
        self.assertEqual(page.inner_text("#wheel-result-msg .deal-left"), "24 soat qoldi")

    def test_card_is_unchanged_for_an_old_server_without_the_discount_field(self):
        legacy = (200, {"ok": True, "message": "SUPER", "score": 7, "is_super": True, "prize": 0,
                        "prize_type": "super", "points": 0, "tip": None})
        state_no_discount = {k: v for k, v in super_state().items() if k != "discount"}
        routes = {"state": (200, state_no_discount), "spin/claim": legacy}
        page, _ = self.open_app(routes)
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-desc:has-text('50% chegirma faollashtirildi')")
        self.assertEqual(page.locator("#wheel-result-msg .deal").count(), 0)
        self.assertEqual(page.inner_text("#wheel-result-msg .result-confirm-btn"), "Premium olish")

    def test_ultra_winner_gets_no_discount_block(self):
        page, _ = self.open_app({"state": (200, super_state(is_premium=True, premium_type="ultra", premium_days_left=9,
                                                            premium_expires_at=disc(9 * 24)["expires_at"])),
                                 "spin/claim": super_claim(disc(24), is_premium=True, premium_type="ultra",
                                                           premium_days_left=9,
                                                           premium_expires_at=disc(9 * 24)["expires_at"])})
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('SUPER PRIZ!')")
        self.assertEqual(page.locator("#wheel-result-msg .deal").count(), 0)


# ═══════════════════════════ 24 soat davomida: hamma joyda ═══════════════════════════
class DiscountEverywhereE2ETest(PremiumE2EBase):
    def open_with(self, routes, scheme="light", **kw):
        page, calls = self.open_app(routes, init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';", **kw)
        page.wait_for_selector("#global-score:not([hidden])")
        return page, calls

    def open_sheet(self, page):
        page.evaluate("openPremiumModalFromUi()")
        page.wait_for_selector("#premium-modal:not(.hidden)")

    def plans(self, page):
        return page.evaluate("""() => [...document.querySelectorAll('#premium-modal .plan-card')]
            .filter(c => c.offsetParent !== null)
            .map(c => ({ plan: c.querySelector('input').value, price: c.querySelector('.plan-price').textContent,
                         deal: !!c.querySelector('.plan-deal') && !c.querySelector('.plan-deal').hidden }))""")

    # ---- Premium oynasi ----
    def test_sheet_pro_card_shows_the_discounted_price_and_time(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(5, 12)))})
        self.open_sheet(page)
        self.assertEqual(self.plans(page), [
            {"plan": "buy_pro_7", "price": "★ 50", "deal": False},
            {"plan": "buy_plus_30", "price": "★ 75", "deal": True},
            {"plan": "buy_ultra_30", "price": "★ 300", "deal": False}])
        card = '#premium-modal .plan-card:has(input[value="buy_plus_30"])'
        self.assertEqual(page.inner_text(f"{card} .plan-old"), "★ 150")
        self.assertEqual(page.inner_text(f"{card} .plan-off"), "−50%")
        self.assertEqual(page.inner_text(f"{card} .plan-left"), "5 soat 12 daqiqa qoldi")
        self.assertEqual(page.evaluate(f"getComputedStyle(document.querySelector('{card} .plan-old')).textDecorationLine"),
                         "line-through")
        self.assertEqual(self.tg(page)["mainText"], "★ 75 — Davom etish")           # asosiy tugma ham chegirmali narx bilan

    def test_sheet_buys_with_the_pro_plan_and_the_server_applies_the_price(self):
        page, calls = self.open_with({"state": (200, state(discount=disc(5))), "invoice": INVOICE_OK})
        self.open_sheet(page)
        self.press_main(page, "#premium-continue")
        page.wait_for_function("window.__tg.invoices.length === 1")
        self.assertEqual([c[1]["plan"] for c in calls if c[0] == "invoice"], ["buy_plus_30"])

    def test_sheet_time_left_counts_down(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(5, 12)))})
        self.open_sheet(page)
        page.clock.fast_forward(HOUR)
        page.wait_for_function("document.querySelector('#premium-modal .plan-left').textContent === '4 soat 12 daqiqa qoldi'")

    def test_sheet_returns_to_the_normal_price_when_the_timer_ends(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(0, 45)))})
        self.open_sheet(page)
        self.assertEqual(self.tg(page)["mainText"], "★ 75 — Davom etish")
        page.clock.fast_forward(46 * 60 * 1000)                                      # sahifa yangilanmaydi
        page.wait_for_function("document.querySelector('#premium-modal .plan-card:has(input[value=\"buy_plus_30\"]) .plan-price').textContent === '★ 150'")
        self.assertEqual(self.plans(page)[1], {"plan": "buy_plus_30", "price": "★ 150", "deal": False})
        self.assertEqual(self.tg(page)["mainText"], "★ 150 — Davom etish")
        self.assertEqual(page.get_attribute(RADIO.format("buy_plus_30"), "data-price"), "150")
        self.assertTrue(page.is_hidden("#premium-modal .plan-deal"))

    def test_sheet_without_a_discount_is_unchanged(self):
        for discount in (OFF, None):
            with self.subTest(discount=discount):
                st = state() if discount is None else state(discount=discount)
                page, _ = self.open_with({"state": (200, st)})
                self.open_sheet(page)
                self.assertEqual([p["price"] for p in self.plans(page)], ["★ 50", "★ 150", "★ 300"])
                self.assertFalse(any(p["deal"] for p in self.plans(page)))
                self.assertTrue(page.is_hidden("#premium-modal .plan-deal"))              # ko'zga ko'rinmaydi (hidden CSS bilan ham)

    def test_active_pro_extends_with_the_discount_and_lower_tier_stays_hidden(self):
        page, _ = self.open_with({"state": (200, state("plus", days=5, discount=disc(5)))})
        self.open_sheet(page)
        plans = {p["plan"]: p for p in self.plans(page)}
        self.assertEqual(set(plans), {"buy_plus_30", "buy_ultra_30"})
        self.assertEqual(plans["buy_plus_30"], {"plan": "buy_plus_30", "price": "★ 75", "deal": True})
        self.assertEqual(page.inner_text('#premium-modal .plan-card:has(input[value="buy_plus_30"]) .plan-days'),
                         "yana 30 kun")

    def test_ultra_and_unlimited_have_no_discount_anywhere(self):
        for st in (state("ultra", days=5, discount=disc(5)), state("plus", unlimited=True, discount=disc(5)),
                   state("ultra", unlimited=True, discount=disc(5))):
            with self.subTest(tier=st["premium_type"], unlimited=st["premium_unlimited"]):
                page, _ = self.open_with({"state": (200, st)})
                self.assertNotIn("−50%", page.inner_text("#today-premium-sub"))
                self.assertEqual(page.locator("[data-discount-left]").count(), 0)
                self.assertEqual(page.evaluate("discountOffer(AppState.data)"), None)

    # ---- bosh ekran kartasi ----
    def test_home_card_shows_the_discount_and_time(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(5, 12)))})
        self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 5 soat 12 daqiqa qoldi")
        self.assertEqual(page.inner_text("#today-premium-title"), "Premium")
        self.assertEqual(page.inner_text("#today-premium-btn"), "Ochish")
        self.assertIn("−50%", page.get_attribute("#today-premium-card", "aria-label"))
        self.assertIn("5 soat 12 daqiqa qoldi", page.get_attribute("#today-premium-card", "aria-label"))
        page.clock.fast_forward(12 * 60 * 1000)
        page.wait_for_function("document.querySelector('#today-premium-sub').textContent === '−50% · 5 soat qoldi'")

    def test_home_card_for_a_premium_user_keeps_the_extend_button(self):
        page, _ = self.open_with({"state": (200, state("pro", days=3, discount=disc(5)))})
        self.assertEqual(page.inner_text("#today-premium-title"), "Plus")
        self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 5 soat qoldi")
        self.assertEqual(page.inner_text("#today-premium-btn"), "Uzaytirish")

    def test_home_card_returns_to_normal_when_the_timer_ends(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(0, 20)))})
        self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 20 daqiqa qoldi")
        page.clock.fast_forward(21 * 60 * 1000)
        page.wait_for_function("document.querySelector('#today-premium-sub').textContent === 'Tariflar va bonuslar'")
        self.assertEqual(page.get_attribute("#today-premium-card", "aria-label"), "Premium: tariflar va bonuslar")
        self.assertEqual(page.locator("[data-discount-left]").count(), 0)

    def test_home_card_after_expiry_for_a_premium_user_shows_days_again(self):
        page, _ = self.open_with({"state": (200, state("pro", days=3, discount=disc(0, 10)))})
        page.clock.fast_forward(11 * 60 * 1000)
        page.wait_for_function("document.querySelector('#today-premium-sub').textContent === '3 kun qoldi'")

    # ---- AI limit taklifi ----
    def open_ai_limit(self, discount, **kw):
        st = state(discount=discount, **kw)
        st["ai_remaining"], st["ai_limit"] = 0, 1
        page, calls = self.open_with({"state": (200, st), "invoice": INVOICE_OK})
        page.click('nav [data-tab="tab-ai"]')
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        return page, calls

    def test_ai_limit_offer_shows_the_deal_block_with_a_live_timer(self):
        page, _ = self.open_ai_limit(disc(5, 12))
        page.wait_for_selector("#ai-offer-deal:not([hidden])")
        self.assertEqual(page.inner_text("#ai-offer-deal .deal-old"), "★ 150")
        self.assertEqual(page.inner_text("#ai-offer-deal .deal-new"), "★ 75")
        self.assertEqual(page.inner_text("#ai-offer-deal .deal-badge"), "−50%")
        self.assertEqual(page.inner_text("#ai-offer-deal .deal-left"), "5 soat 12 daqiqa qoldi")
        page.clock.fast_forward(12 * 60 * 1000)
        page.wait_for_function("document.querySelector('#ai-offer-deal .deal-left').textContent === '5 soat qoldi'")
        self.assertEqual(page.inner_text("#ai-offer-buy"), "★ Premium tariflari")        # tugma o'sha oynani ochadi

    def test_ai_limit_offer_deal_disappears_when_the_timer_ends(self):
        page, _ = self.open_ai_limit(disc(0, 15))
        page.wait_for_selector("#ai-offer-deal:not([hidden])")
        page.clock.fast_forward(16 * 60 * 1000)
        page.wait_for_selector("#ai-offer-deal", state="hidden")
        self.assertEqual(page.locator("#ai-offer-deal .deal").count(), 0)
        self.assertTrue(page.is_visible("#ai-premium-offer"))                           # oddiy taklif qoladi

    def test_ai_limit_offer_without_a_discount_has_no_deal_block(self):
        page, _ = self.open_ai_limit(OFF)
        self.assertFalse(page.is_visible("#ai-offer-deal"))

    def test_ai_limit_button_opens_the_sheet_with_the_discounted_pro_card(self):
        page, _ = self.open_ai_limit(disc(5))
        page.click("#ai-offer-buy")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        self.assertEqual(self.plans(page)[1]["price"], "★ 75")

    # ---- to'lovdan keyin ----
    def test_discount_disappears_right_after_the_pro_payment(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(5))), "invoice": INVOICE_OK})
        self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 5 soat qoldi")
        self.open_sheet(page)
        self.press_main(page, "#premium-continue")
        page.wait_for_function("window.__tg.invoices.length === 1")
        page.evaluate("window.__invoiceCb('paid')")
        page.wait_for_function("document.querySelector('#today-premium-sub').textContent === 'Tariflar va bonuslar'")
        self.assertEqual(self.plans(page)[1], {"plan": "buy_plus_30", "price": "★ 150", "deal": False})
        self.assertEqual(page.locator("[data-discount-left]").count(), 0)

    def test_cancelled_or_failed_payment_keeps_the_discount(self):
        for status in ("cancelled", "failed", "pending"):
            with self.subTest(status=status):
                page, _ = self.open_with({"state": (200, state(discount=disc(5))), "invoice": INVOICE_OK})
                self.open_sheet(page)
                self.press_main(page, "#premium-continue")
                page.wait_for_function("window.__tg.invoices.length === 1")
                page.evaluate(f"window.__invoiceCb('{status}')")
                page.wait_for_timeout(100)
                self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 5 soat qoldi")

    def test_paying_another_tier_keeps_the_discount(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(5))), "invoice": INVOICE_OK})
        self.open_sheet(page)
        page.click('#premium-modal .plan-card:has(input[value="buy_ultra_30"])')
        self.press_main(page, "#premium-continue")
        page.wait_for_function("window.__tg.invoices.length === 1")
        page.evaluate("window.__invoiceCb('paid')")
        page.wait_for_timeout(100)
        self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 5 soat qoldi")

    # ---- server yagona manba ----
    def test_remaining_time_comes_from_the_server_not_the_device_clock(self):
        wrong = {**disc(1), "expires_at": "2020-01-01T00:00:00+05:00"}         # qurilma soatiga qarab "allaqachon o'tgan"
        page, _ = self.open_with({"state": (200, state(discount=wrong))})
        self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 1 soat qoldi")

    def test_inactive_or_zero_seconds_means_no_offer(self):
        for discount in (OFF, {**disc(1), "active": False}, {**disc(1), "seconds_left": 0}, {**disc(1), "seconds_left": None}):
            with self.subTest(discount=discount):
                page, _ = self.open_with({"state": (200, state(discount=discount))})
                self.assertEqual(page.inner_text("#today-premium-sub"), "Tariflar va bonuslar")

    def test_state_refresh_with_the_same_deadline_does_not_restart_the_timer(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(5)))})
        page.clock.fast_forward(HOUR)
        page.wait_for_function("document.querySelector('#today-premium-sub').textContent === '−50% · 4 soat qoldi'")
        page.evaluate("patchAppState({ score: 9 })")                              # holat qayta chizildi, muddat o'sha
        self.assertEqual(page.inner_text("#today-premium-sub"), "−50% · 4 soat qoldi")

    # ---- 360 px ----
    def test_everything_fits_at_360px(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(23, 59)))})
        page.set_viewport_size({"width": 360, "height": 740})
        self.open_sheet(page)
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 360)
        for sel in ("#premium-modal .plan-card:has(input[value='buy_plus_30'])", "#premium-modal .plan-deal"):
            box = page.locator(sel).bounding_box()
            self.assertGreaterEqual(box["x"], 0, sel)
            self.assertLessEqual(box["x"] + box["width"], 360.5, sel)
        clipped = page.evaluate("""() => ['.plan-old', '.plan-off', '.plan-left', '.plan-price'].map(s => {
            const el = document.querySelector('#premium-modal ' + s); return el.scrollWidth > el.clientWidth + 1; })""")
        self.assertEqual(clipped, [False] * 4)
        page.evaluate("AppNavigation.back()")

    def test_offer_card_and_ai_block_fit_at_360px(self):
        page, _ = self.open_ai_limit(disc(23, 59))
        page.set_viewport_size({"width": 360, "height": 740})
        page.wait_for_selector("#ai-offer-deal:not([hidden])")
        box = page.locator("#ai-offer-deal .deal").bounding_box()
        self.assertGreaterEqual(box["x"], 0)
        self.assertLessEqual(box["x"] + box["width"], 360.5)
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 360)

    # ---- prefers-reduced-motion ----
    def test_timer_works_with_reduced_motion_and_has_no_animation(self):
        page, _ = self.open_with({"state": (200, state(discount=disc(5, 12)))})
        page.emulate_media(reduced_motion="reduce")
        self.open_sheet(page)
        page.clock.fast_forward(HOUR)
        page.wait_for_function("document.querySelector('#premium-modal .plan-left').textContent === '4 soat 12 daqiqa qoldi'")
        names = page.evaluate("""() => ['.plan-deal', '.plan-old', '.plan-off', '.plan-left'].map(s =>
            getComputedStyle(document.querySelector('#premium-modal ' + s)).animationName)""")
        self.assertEqual(names, ["none"] * 4)

    # ---- kontrast ----
    def test_contrast_is_at_least_4_5_in_light_and_dark(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                st = state(discount=disc(5, 12))
                st["ai_remaining"], st["ai_limit"] = 0, 1
                page, _ = self.open_with({"state": (200, st)}, scheme=scheme)
                page.click('nav [data-tab="tab-ai"]')
                page.wait_for_selector("#ai-offer-deal:not([hidden])")
                for sel in ("#ai-offer-deal .deal-name", "#ai-offer-deal .deal-old", "#ai-offer-deal .deal-new",
                            "#ai-offer-deal .deal-badge", "#ai-offer-deal .deal-left"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, (scheme, sel))
                page.click("#ai-offer-buy")
                page.wait_for_selector("#premium-modal:not(.hidden)")
                for plan in ("buy_plus_30",):                       # tanlangan (primary-soft fon) va tanlanmagan holat
                    for sel in ("plan-old", "plan-off", "plan-left", "plan-days", "plan-price"):
                        css = f'#premium-modal .plan-card:has(input[value="{plan}"]) .{sel}'
                        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, css), 4.5, (scheme, "tanlangan", sel))
                page.click('#premium-modal .plan-card:has(input[value="buy_ultra_30"])')
                for sel in ("plan-old", "plan-off", "plan-left"):
                    css = f'#premium-modal .plan-card:has(input[value="buy_plus_30"]) .{sel}'
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, css), 4.5, (scheme, "tanlanmagan", sel))

    def test_contrast_of_the_offer_card_after_winning(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_app({"state": (200, super_state()), "spin/claim": super_claim(disc(24))},
                                        init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                self.open_wheel(page)
                page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
                self.spin_and_confirm(page)
                page.wait_for_selector("#wheel-result-msg .deal")
                for sel in ("#wheel-result-msg .deal-name", "#wheel-result-msg .deal-old", "#wheel-result-msg .deal-new",
                            "#wheel-result-msg .deal-badge", "#wheel-result-msg .deal-left",
                            "#wheel-result-msg .result-title", "#wheel-result-msg .result-desc"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, (scheme, sel))


if __name__ == "__main__":
    unittest.main()
