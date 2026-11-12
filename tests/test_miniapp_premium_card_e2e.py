"""
test_miniapp_premium_card_e2e.py — Mini App (brauzerda / Playwright): bosh ekrandagi "Bugun" bo'limida Premium kartasi
va BITTA Premium oynasi (tariflar + "100 ball -> Premium Plus").

  * karta: bepul — "Premium / Tariflar va bonuslar / Ochish"; Premium — tarif nomi, "5 kun qoldi" (muddatsizda "♾"),
    "Uzaytirish" ("Ko'rish"); rangi tarifga ergashadi; 360 px da 2+1 joylashuv, matn kesilmaydi, tugma >= 44 px;
  * karta bosilsa Premium oynasi (sheet) ochiladi — btn-open-premium va AI limit taklifi ochadigan o'sha oyna;
  * 100 ball bo'limi: progress (role=progressbar), "Almashtirish" / "Yana N ball kerak", muddatsizda yo'q, muddat yozilmaydi;
  * "Almashtirish" -> POST /api/points/redeem -> header, karta, ball va tariflar yangilanadi; qo'sh bosish — bitta so'rov.
Asos: tests/e2e_base.py, tests/test_miniapp_premium_visibility_e2e.py
"""
import os
import re
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase, sequence
from tests.test_miniapp_premium_visibility_e2e import (DEFAULT_PRIMARY, TOKENS, PremiumE2EBase, rgb, scheme_script,
                                                       state)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREE = state()


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def redeemed(ok=True, score=20, message="100 ball yechildi! Premium Plus faollashdi — tugash: 15.11.2026", **kw):
    """/api/points/redeem javobi: yangi holat (state() bilan bir xil maydonlar) + ok / reason / message / cost."""
    base = state("pro", days=3, score=score) if ok else state(score=score)
    base.pop("daily_claimed", None)
    return {**base, "ok": ok, "reason": None if ok else "not_enough", "message": message, "cost": 100, **kw}


class CardBase(PremiumE2EBase):
    def open_with(self, st, routes=None, scheme="light", width=None):
        all_routes = {"state": (200, st), **(routes or {})}
        page, calls = self.open_app(all_routes, init_script=scheme_script(scheme))
        if width:
            page.set_viewport_size({"width": width, "height": 800})
        page.wait_for_selector("#global-score:not([hidden])")
        return page, calls

    def open_sheet(self, page):
        page.click("#today-premium-btn")
        page.wait_for_selector("#premium-modal:not(.hidden)")

    def visible_plans(self, page):
        return page.evaluate("""() => [...document.querySelectorAll('#premium-modal .plan-card')]
            .filter(c => c.offsetParent !== null)
            .map(c => ({ plan: c.querySelector('input').value, days: c.querySelector('.plan-days').textContent }))""")

    def card_texts(self, page):
        return (page.inner_text("#today-premium-title"), page.inner_text("#today-premium-sub"),
                page.inner_text("#today-premium-btn"))


# ───────────────────────────── karta ─────────────────────────────
class CardE2ETest(CardBase):
    def test_free_user_card(self):
        page, _ = self.open_with(FREE)
        self.assertEqual(self.card_texts(page), ("Premium", "Tariflar va bonuslar", "Ochish"))
        self.assertEqual(page.get_attribute("#today-premium .today-icon use", "href"), "#i-crown")     # sprite, emoji emas
        structure = page.evaluate("""() => { const cards = [...document.querySelectorAll('.today-grid > .today-card')];
            return { count: cards.length,
                     third: cards[2] && cards[2].id,
                     main: !!document.querySelector('#today-premium > button.today-main'),
                     btn: !!document.querySelector('#today-premium > button.today-btn') }; }""")
        self.assertEqual(structure, {"count": 3, "third": "today-premium", "main": True, "btn": True})   # Bonus, Baraban, Premium
        self.assertEqual(page.inner_text(".today-grid > .today-card:nth-child(1) .today-title"), "Bonus")
        self.assertEqual(page.inner_text(".today-grid > .today-card:nth-child(2) .today-title"), "Baraban")
        self.assertIsNone(re.search("[\U0001F300-\U0001FAFF☀-➿]", page.inner_text("#today-premium")))

    def test_premium_card_per_state(self):
        cases = [
            (state("ultra", days=5), ("Ultra", "5 kun qoldi", "Uzaytirish")),
            (state("pro", days=2), ("Plus", "2 kun qoldi", "Uzaytirish")),                # ichki pro = ko'rinadigan Plus
            (state("plus", days=30), ("Pro", "30 kun qoldi", "Uzaytirish")),
            (state("ultra", unlimited=True), ("Ultra", "♾", "Ko'rish")),
            (state("ultra", hours=3), ("Ultra", "Bugun tugaydi", "Uzaytirish")),
            ({**STATE_OK, "is_premium": True, "premium_type": "ultra"}, ("Ultra", "Faol", "Uzaytirish")),   # eski server
        ]
        for st, expected in cases:
            with self.subTest(expected=expected):
                page, _ = self.open_with(st)
                self.assertEqual(self.card_texts(page), expected)

    def test_color_follows_the_tier(self):
        page, _ = self.open_with(FREE)
        self.assertEqual(page.evaluate("getComputedStyle(document.getElementById('today-premium-btn')).backgroundColor"),
                         rgb(DEFAULT_PRIMARY["light"]))
        for tier, t in TOKENS.items():
            with self.subTest(tier=tier):
                page, _ = self.open_with(state(tier, days=5))
                primary, on, soft = t["light"]
                colors = page.evaluate("""() => { const b = getComputedStyle(document.getElementById('today-premium-btn'));
                    const i = getComputedStyle(document.querySelector('#today-premium .today-icon'));
                    return [b.backgroundColor, b.color, i.backgroundColor, i.color]; }""")
                self.assertEqual(colors, [rgb(primary), rgb(on), rgb(soft), rgb(primary)])

    def test_card_updates_when_state_changes(self):
        page, _ = self.open_with(FREE)
        self.patch(page, **{k: v for k, v in state("ultra", days=5).items() if k.startswith("premium") or k == "is_premium"})
        self.assertEqual(self.card_texts(page), ("Ultra", "5 kun qoldi", "Uzaytirish"))
        self.patch(page, is_premium=False, premium_type="free", premium_expires_at=None, premium_days_left=None)
        self.assertEqual(self.card_texts(page), ("Premium", "Tariflar va bonuslar", "Ochish"))

    def test_card_and_button_open_the_sheet_and_back_closes_it(self):
        page, _ = self.open_with(FREE)
        self.assertTrue(page.is_hidden("#premium-modal"))
        for target in ("#today-premium-card", "#today-premium-btn"):
            with self.subTest(target=target):
                page.click(target)
                page.wait_for_selector("#premium-modal:not(.hidden)")
                self.assertTrue(self.tg(page)["backVisible"])
                page.evaluate("window.__backCb()")                                  # Telegram BackButton
                page.wait_for_selector("#premium-modal.hidden", state="attached")
                self.assertFalse(self.tg(page)["mainVisible"])
                page.wait_for_timeout(350)                                          # AppNavigation.back: 300 ms debounce

    def test_sheet_closes_with_x_and_overlay(self):
        page, _ = self.open_with(FREE)
        self.open_sheet(page)
        page.click("#premium-modal-close")
        page.wait_for_selector("#premium-modal.hidden", state="attached")
        page.wait_for_timeout(350)                                                  # AppNavigation.back: 300 ms debounce
        self.open_sheet(page)
        page.mouse.click(195, 30)                                                   # sheet'dan tashqari (qorong'i fon)
        page.wait_for_selector("#premium-modal.hidden", state="attached")

    def test_sheet_tariffs_follow_the_state(self):
        page, _ = self.open_with(FREE)
        self.open_sheet(page)
        self.assertEqual([p["plan"] for p in self.visible_plans(page)], ["buy_pro_7", "buy_plus_30", "buy_ultra_30"])
        page, _ = self.open_with(state("ultra", days=5))
        self.open_sheet(page)
        self.assertEqual(self.visible_plans(page), [{"plan": "buy_ultra_30", "days": "yana 30 kun"}])
        self.assertEqual(page.inner_text("#premium-title"), "Premiumni uzaytirish")

    def test_one_premium_sheet_for_card_row_ai_offer_and_banner(self):
        """Premium uchun BITTA oyna: karta, Sog'liq qatori (btn-open-premium) va AI limit taklifi shuni ochadi."""
        st = {**FREE, "ai_remaining": 0, "ai_limit": 1}
        page, _ = self.open_with(st)
        self.assertEqual(page.evaluate("document.querySelectorAll('.premium-sheet').length"), 1)
        self.assertEqual(page.evaluate("document.querySelectorAll('#premium-modal').length"), 1)
        openers = {
            "row": lambda: (page.click('nav [data-tab="tab-health"]'), page.click("#btn-open-premium")),
            "ai": lambda: (page.click('nav [data-tab="tab-ai"]'), page.wait_for_selector("#ai-premium-offer:not([hidden])"),
                           page.click("#ai-offer-buy")),
            "card": lambda: (page.click('nav [data-tab="tab-first-aid"]'), page.click("#today-premium-btn")),
        }
        for name, opener in openers.items():
            with self.subTest(opener=name):
                opener()
                page.wait_for_selector("#premium-modal:not(.hidden)")
                self.assertEqual([p["plan"] for p in self.visible_plans(page)], ["buy_pro_7", "buy_plus_30", "buy_ultra_30"])
                self.assertTrue(page.is_visible("#pm-points"))
                page.click("#premium-modal-close")
                page.wait_for_selector("#premium-modal.hidden", state="attached")
                page.wait_for_timeout(350)                                          # AppNavigation.back: 300 ms debounce


# ───────────────────────────── 360 px ─────────────────────────────
class CardLayoutE2ETest(CardBase):
    def test_three_cards_fit_at_360px(self):
        for st in (FREE, state("ultra", days=5), state("plus", unlimited=True)):
            with self.subTest(premium=st["is_premium"], unlimited=st["premium_unlimited"]):
                page, _ = self.open_with(st, width=360)
                page.locator("#today-premium").scroll_into_view_if_needed()
                geo = page.evaluate("""() => {
                    const r = (el) => { const b = el.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; };
                    const cards = [...document.querySelectorAll('.today-grid > .today-card')].map(r);
                    const grid = r(document.querySelector('.today-grid'));
                    const clipped = ['#today-premium-title', '#today-premium-sub', '#today-premium-btn',
                                     '.today-grid > .today-card:nth-child(1) .today-title',
                                     '.today-grid > .today-card:nth-child(2) .today-btn']
                        .filter((s) => { const e = document.querySelector(s); return e.scrollWidth > e.clientWidth + 1; });
                    return { cards, grid, clipped, btn: r(document.getElementById('today-premium-btn')),
                             main: r(document.getElementById('today-premium-card')),
                             overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
                }""")
                self.assertEqual(len(geo["cards"]), 3)
                bonus, wheel, premium = geo["cards"]
                self.assertAlmostEqual(bonus["t"], wheel["t"], delta=1)                 # 2 + 1: yuqorida yonma-yon
                self.assertLessEqual(bonus["r"], wheel["l"] + 0.5)
                self.assertGreater(premium["t"], bonus["b"])                            # Premium — pastda, to'liq kenglikda
                self.assertAlmostEqual(premium["w"], geo["grid"]["w"], delta=1)
                for card in geo["cards"]:
                    self.assertGreaterEqual(card["l"], 0)
                    self.assertLessEqual(card["r"], 360)
                self.assertLessEqual(geo["overflow"], 0)                                # gorizontal skroll yo'q
                self.assertEqual(geo["clipped"], [])                                    # matn kesilmagan
                self.assertGreaterEqual(geo["btn"]["h"], 43.9)                          # tugma >= 44 x 44
                self.assertGreaterEqual(geo["btn"]["w"], 43.9)
                self.assertGreaterEqual(geo["main"]["h"], 43.9)
                self.assertLessEqual(geo["btn"]["r"], premium["r"])

    def test_sheet_sections_fit_at_360px(self):
        for st in ({**FREE, "score": 13}, {**FREE, "score": 130}, state("ultra", days=5, score=40)):
            with self.subTest(score=st["score"], premium=st["is_premium"]):
                page, _ = self.open_with(st, width=360)
                self.open_sheet(page)
                geo = page.evaluate("""() => {
                    const sheet = document.querySelector('#premium-modal .pm-sheet').getBoundingClientRect();
                    const out = [...document.querySelectorAll('#pm-points, #pm-points *')]
                        .filter((e) => e.offsetParent !== null)
                        .filter((e) => { const b = e.getBoundingClientRect(); return b.right > sheet.right + 0.5 || b.left < sheet.left - 0.5; })
                        .map((e) => e.id || e.className);
                    const clipped = [...document.querySelectorAll('#pm-points p, #pm-points h3, #pm-points button')]
                        .filter((e) => e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1).map((e) => e.id);
                    return { out, clipped, over: document.querySelector('#premium-modal .pm-sheet').scrollWidth - sheet.width };
                }""")
                self.assertEqual((geo["out"], geo["clipped"]), ([], []))
                self.assertLessEqual(geo["over"], 1)
                if st["score"] >= 100:
                    box = page.locator("#pm-points-redeem").bounding_box()
                    self.assertGreaterEqual(box["height"], 43.9)
                    self.assertGreaterEqual(box["width"], 43.9)


# ───────────────────────────── 100 ball bo'limi ─────────────────────────────
class PointsSectionE2ETest(CardBase):
    def section(self, page):
        return page.evaluate("""() => { const box = document.getElementById('pm-points');
            const bar = document.getElementById('pm-points-bar');
            const vis = (id) => { const e = document.getElementById(id); return e.offsetParent !== null; };
            return { shown: box.offsetParent !== null,
                     title: document.getElementById('pm-points-title').textContent,
                     role: bar.getAttribute('role'), now: bar.getAttribute('aria-valuenow'),
                     max: bar.getAttribute('aria-valuemax'), min: bar.getAttribute('aria-valuemin'),
                     text: bar.getAttribute('aria-valuetext'), pct: bar.style.getPropertyValue('--pm-pct'),
                     count: document.getElementById('pm-points-count').textContent,
                     hint: vis('pm-points-hint') ? document.getElementById('pm-points-hint').textContent : null,
                     how: vis('pm-points-how') ? document.getElementById('pm-points-how').textContent : null,
                     button: vis('pm-points-redeem') ? document.getElementById('pm-points-redeem').textContent : null,
                     all: box.innerText }; }""")

    def test_not_enough_points(self):
        page, _ = self.open_with({**FREE, "score": 13})
        self.open_sheet(page)
        sec = self.section(page)
        self.assertEqual((sec["shown"], sec["title"]), (True, "100 ball → Premium Plus"))
        self.assertEqual((sec["role"], sec["min"], sec["max"], sec["now"]), ("progressbar", "0", "100", "13"))
        self.assertEqual((sec["text"], sec["pct"], sec["count"]), ("13 / 100 ball", "13", "13 / 100 ball"))
        self.assertEqual(sec["hint"], "Yana 87 ball kerak")
        self.assertEqual(sec["how"], "Baraban, kunlik bonus va test orqali ball yig'ing")
        self.assertIsNone(sec["button"])                                              # Almashtirish yo'q
        self.assertNotRegex(sec["title"] + sec["hint"], r"\bkun")                     # taklifda muddat yo'q

    def test_enough_points(self):
        for score in (100, 120):
            with self.subTest(score=score):
                page, _ = self.open_with({**FREE, "score": score})
                self.open_sheet(page)
                sec = self.section(page)
                self.assertEqual((sec["now"], sec["pct"], sec["count"]), ("100", "100", f"{score} / 100 ball"))
                self.assertEqual(sec["button"], "Almashtirish")
                self.assertIsNone(sec["hint"])
                self.assertIsNone(sec["how"])

    def test_premium_user_still_sees_the_section(self):
        page, _ = self.open_with(state("ultra", days=5, score=40))
        self.open_sheet(page)
        sec = self.section(page)
        self.assertEqual((sec["shown"], sec["hint"]), (True, "Yana 60 ball kerak"))

    def test_hidden_for_unlimited_premium(self):
        page, _ = self.open_with(state("ultra", unlimited=True, score=150))
        self.open_sheet(page)
        self.assertFalse(self.section(page)["shown"])
        self.assertTrue(page.is_visible("#pm-unlimited"))                              # sotib olinadigan narsa yo'q
        self.assertEqual(self.visible_plans(page), [])
        self.assertTrue(page.is_hidden("#premium-continue"))
        self.assertFalse(self.tg(page)["mainVisible"])

    def test_hidden_when_score_is_unknown(self):
        st = {k: v for k, v in FREE.items() if k != "score"}
        page, _ = self.open_app({"state": (200, st)}, init_script=scheme_script("light"))
        page.wait_for_selector("#hdr-premium", state="attached")
        page.click('nav [data-tab="tab-health"]')
        page.click("#btn-open-premium")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        self.assertFalse(self.section(page)["shown"])

    def test_no_duration_words_anywhere_in_the_section(self):
        for score in (13, 130):
            page, _ = self.open_with({**FREE, "score": score})
            self.open_sheet(page)
            text = self.section(page)["all"]
            # "kunlik bonus" — ball yig'ish yo'li (taklif muddati emas); "3 kun" / "N kunlik Premium" yo'q
            self.assertNotRegex(text.replace("kunlik bonus", ""), r"\bkun", text)


class RedeemFlowE2ETest(CardBase):
    def calls_to(self, calls, name):
        return [c for c in calls if c[0] == name]

    def test_redeem_updates_header_card_points_and_tariffs(self):
        page, calls = self.open_with({**FREE, "score": 120}, routes={"points/redeem": (200, redeemed())})
        self.assertEqual(page.inner_text("#global-score-val"), "120")
        self.open_sheet(page)
        page.click("#pm-points-redeem")
        self.wait_for_call(calls, "points/redeem")
        page.wait_for_function("document.getElementById('hdr-premium-name').textContent === 'Plus · 3 kun'")
        self.assertEqual(self.card_texts(page), ("Plus", "3 kun qoldi", "Uzaytirish"))
        self.assertEqual(page.inner_text("#global-score-val"), "20")
        self.assertEqual(page.inner_text("#pm-points-count"), "20 / 100 ball")
        self.assertEqual(page.inner_text("#pm-points-hint"), "Yana 80 ball kerak")
        self.assertTrue(page.is_hidden("#pm-points-redeem"))
        self.assertEqual(page.inner_text("#pm-points-msg"),
                         "100 ball yechildi! Premium Plus faollashdi — tugash: 15.11.2026")
        self.assertEqual(self.body_classes(page), ["tier-pro"])
        self.assertEqual(page.inner_text("#premium-title"), "Premiumni uzaytirish")
        self.assertEqual([p["plan"] for p in self.visible_plans(page)], ["buy_pro_7", "buy_plus_30", "buy_ultra_30"])
        self.assertEqual(self.visible_plans(page)[0]["days"], "yana 7 kun")             # yangi tarif = uzaytirish
        self.assertEqual(self.tg(page)["mainText"], "★ 150 — Davom etish")               # tanlov o'zgarmaydi (yuqoriroq tarif)
        # so'rov tanasi: faqat init_data (summa / tarif serverda)
        self.assertEqual([list(c[1]) for c in self.calls_to(calls, "points/redeem")], [["init_data"]])
        self.assertEqual(self.tg(page)["haptics"][-1], "success")

    def test_double_click_sends_one_request(self):
        page, calls = self.open_with({**FREE, "score": 120}, routes={"points/redeem": (200, redeemed())})
        self.open_sheet(page)
        # tugmani ketma-ket bosish (tugma birinchi bosishdayoq o'chadi) va funksiyani to'g'ridan-to'g'ri qayta chaqirish
        # (himoya: pointsRedeeming) — ikkalasida ham bitta so'rov
        page.evaluate("""() => { const b = document.getElementById('pm-points-redeem'); b.click(); b.click(); b.click();
                                 redeemPoints(); redeemPoints(); }""")
        self.wait_for_call(calls, "points/redeem")
        page.wait_for_function("document.getElementById('hdr-premium-name').textContent === 'Plus · 3 kun'")
        page.wait_for_timeout(300)
        self.assertEqual(len(self.calls_to(calls, "points/redeem")), 1)

    def test_button_is_disabled_while_waiting_for_the_answer(self):
        page, calls = self.open_with({**FREE, "score": 120}, routes={"points/redeem": "hang"})
        self.open_sheet(page)
        page.click("#pm-points-redeem")
        self.wait_for_call(calls, "points/redeem")
        self.assertTrue(page.is_disabled("#pm-points-redeem"))

    def test_server_refusal_shows_the_message_and_syncs_the_score(self):
        refused = redeemed(ok=False, score=60, message="Ballaringiz yetarli emas (hozirda 60 ball bor).")
        page, calls = self.open_with({**FREE, "score": 120}, routes={"points/redeem": (200, refused)})
        self.open_sheet(page)
        page.click("#pm-points-redeem")
        self.wait_for_call(calls, "points/redeem")
        page.wait_for_function("document.getElementById('pm-points-msg').textContent !== ''")
        self.assertEqual(page.inner_text("#pm-points-msg"), "Ballaringiz yetarli emas (hozirda 60 ball bor).")
        self.assertIn("is-error", page.get_attribute("#pm-points-msg", "class"))
        self.assertEqual(page.inner_text("#global-score-val"), "60")
        self.assertEqual(page.inner_text("#pm-points-hint"), "Yana 40 ball kerak")
        self.assertEqual(self.card_texts(page)[0], "Premium")                           # Premium berilmadi
        self.assertEqual(self.tg(page)["haptics"][-1], "error")

    def test_unlimited_refusal_hides_the_section_after_state_update(self):
        refused = {**state("ultra", unlimited=True, score=150), "ok": False, "reason": "unlimited", "cost": 100,
                   "message": "Sizda muddatsiz Premium bor — ball almashtirish shart emas."}
        refused.pop("daily_claimed", None)
        page, calls = self.open_with({**FREE, "score": 150}, routes={"points/redeem": (200, refused)})
        self.open_sheet(page)
        page.click("#pm-points-redeem")
        self.wait_for_call(calls, "points/redeem")
        page.wait_for_selector("#pm-points", state="hidden")
        self.assertEqual(self.card_texts(page), ("Ultra", "♾", "Ko'rish"))

    def test_lost_answer_recovers_the_state(self):
        """Javob kelmadi (tarmoq): server ballni yechgan bo'lishi mumkin — holat qayta so'raladi, ball va karta yangilanadi."""
        after = state("pro", days=3, score=20)
        page, calls = self.open_with(
            {**FREE, "score": 120},
            routes={"state": sequence((200, {**FREE, "score": 120}), (200, after)), "points/redeem": "abort"})
        self.open_sheet(page)
        page.click("#pm-points-redeem")
        page.wait_for_function("document.getElementById('today-premium-title').textContent === 'Plus'")
        self.assertEqual(page.inner_text("#global-score-val"), "20")
        self.assertIn("Aloqa uzildi", page.inner_text("#pm-points-msg"))
        self.assertEqual(len(self.calls_to(calls, "state")), 2)
        self.assertEqual(len(self.calls_to(calls, "points/redeem")), 1)


# ───────────────────────────── kontrast, harakat, xavfsizlik ─────────────────────────────
class PremiumCardQualityE2ETest(CardBase):
    def test_contrast_light_and_dark(self):
        states = {"free": {**FREE, "score": 40}, "ultra": state("ultra", days=5, score=40)}
        for scheme in ("light", "dark"):
            for name, st in states.items():
                with self.subTest(scheme=scheme, state=name):
                    page, _ = self.open_with(st, scheme=scheme)
                    for sel in ("#today-premium-title", "#today-premium-sub", "#today-premium-btn"):
                        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
                    self.open_sheet(page)
                    page.wait_for_timeout(350)                                         # sheet animatsiyasi
                    for sel in ("#pm-points-title", "#pm-points-count", "#pm-points-hint", "#pm-points-how"):
                        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, (scheme, name, sel))

    def test_contrast_of_redeem_button_and_messages(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, calls = self.open_with(
                    {**FREE, "score": 130}, scheme=scheme,
                    routes={"points/redeem": (200, redeemed(ok=False, score=60, message="Ballaringiz yetarli emas."))})
                self.open_sheet(page)
                page.wait_for_timeout(350)
                self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#pm-points-redeem"), 4.5)
                page.click("#pm-points-redeem")
                page.wait_for_function("document.getElementById('pm-points-msg').textContent !== ''")
                self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#pm-points-msg"), 4.5)

    def test_unlimited_note_contrast(self):
        for scheme in ("light", "dark"):
            page, _ = self.open_with(state("ultra", unlimited=True, score=10), scheme=scheme)
            self.open_sheet(page)
            page.wait_for_timeout(350)
            self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#pm-unlimited"), 4.5, scheme)

    def test_progress_fill_has_no_transition_with_reduced_motion(self):
        page, _ = self.open_with({**FREE, "score": 50})
        page.emulate_media(reduced_motion="reduce")
        self.open_sheet(page)
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.pm-points-fill')).transitionDuration"), "0s")


class PremiumCardStaticTest(unittest.TestCase):
    def test_new_functions_never_use_innerhtml(self):
        js = read("app", "app.js")
        for name in ("renderTodayPremium", "renderPremiumPoints", "redeemPoints", "setPointsMessage", "renderPremiumPlans"):
            start = js.index(f"function {name}(") if f"function {name}(" in js else js.index(f"async function {name}(")
            end = js.index("\n}\n", start)
            self.assertNotIn("innerHTML", js[start:end], name)

    def test_markup_has_no_inline_styles_or_handlers(self):
        html = read("app", "index.html")
        block = html[html.index('id="today-premium"'): html.index('</div>', html.index('id="today-premium-btn"'))]
        block += html[html.index('id="pm-points"'): html.index("</section>", html.index('id="pm-points"'))]
        self.assertNotRegex(block, r"\sstyle=")
        self.assertNotRegex(block, r"\son[a-z]+=")

    def test_progress_bar_is_an_accessible_progressbar(self):
        html = read("app", "index.html")
        self.assertRegex(html, r'id="pm-points-bar" role="progressbar" aria-labelledby="pm-points-title" '
                               r'aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"')

    def test_reduced_motion_rule_exists_for_the_new_bar(self):
        css = read("app", "style.css")
        self.assertRegex(css, r"@media \(prefers-reduced-motion: reduce\) \{\s*\.pm-points-fill \{ transition: none; \}")

    def test_card_reuses_the_existing_today_classes(self):
        html = read("app", "index.html")
        start = html.index('<div class="today-card today-card--wide" id="today-premium">')
        card = html[start: html.index("</div>", start)]
        for cls in ("today-card", "today-main", "today-icon", "today-title", "today-sub", "today-btn"):
            self.assertIn(cls, card)
        self.assertIn('href="#i-crown"', card)

    def test_tier_name_for_redeem_comes_from_the_single_constant(self):
        js = read("app", "app.js")
        self.assertIn("premiumTierTitle('pro')", js[js.index("function renderPremiumPoints("):])


if __name__ == "__main__":
    unittest.main()
