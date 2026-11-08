"""
test_miniapp_home_e2e.py — redesign 4.4-B: bosh ekran (SOS, tezkor harakatlar, "Bugun" kartasi, Premium banner,
guruhlangan birinchi yordam ro'yxati + qidiruv). Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import STATE_OK, MiniAppE2EBase

STATE = {**STATE_OK, "score": 120, "streak": 3, "daily_claimed": False, "prize": 5, "cooldown_seconds": 0,
         "is_premium": False, "premium_type": "free"}


class HomeE2ETest(MiniAppE2EBase):
    def active_section(self, page):
        return page.evaluate("document.querySelector('.tab-content.active').id")

    # ---- SOS ---------------------------------------------------------------------------------
    def test_sos_card_calls_103_and_scrolls_to_guides(self):
        page, _ = self.open_app({})
        self.assertEqual(page.get_attribute(".sos-call", "href"), "tel:103")
        self.assertIn("103", page.inner_text(".sos-call"))
        self.assertEqual(page.evaluate("document.querySelector('.app-content').scrollTop"), 0)
        page.click(".sos-link")
        page.wait_for_function("document.querySelector('.app-content').scrollTop > 0")

    # ---- Tezkor harakatlar ---------------------------------------------------------------
    def test_quick_actions(self):
        page, _ = self.open_app({"state": (200, STATE)})
        labels = page.evaluate("[...document.querySelectorAll('.quick-actions .qa')].map(b => b.innerText.trim())")
        self.assertEqual(labels, ["AI maslahat", "Kalkulyator", "Test", "Baraban"])
        page.click('.qa[data-action="ai"]')
        self.assertEqual(self.active_section(page), "tab-body-map")
        page.click('nav [data-tab="tab-first-aid"]')
        page.click('.qa[data-action="calc"]')
        self.assertEqual(self.active_section(page), "tab-health")

    def test_quiz_opens_from_home_and_back_returns(self):
        page, _ = self.open_app({})
        page.click('.qa[data-action="quiz"]')
        self.assertEqual(self.active_section(page), "tab-quiz")
        self.assertTrue(self.tg(page)["backVisible"])                       # Telegram "Orqaga" ko'rinadi
        page.evaluate("window.__backCb()")
        self.assertEqual(self.active_section(page), "tab-first-aid")
        self.assertFalse(self.tg(page)["backVisible"])

    def test_wheel_uses_wheel_icon_not_refresh(self):
        page, _ = self.open_app({})
        for sel in ("#btn-open-wheel .qa-icon use", "#wheel-promo-card .row-icon use"):
            self.assertEqual(page.get_attribute(sel, "href"), "#i-wheel", sel)

    def test_filled_pill_contrast_is_aa_in_both_themes(self):
        script = r"""(() => {
            const parse = c => c.match(/[\d.]+/g).slice(0, 3).map(Number);
            const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
                                          return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
            const cs = getComputedStyle(document.querySelector('#today-bonus-pill'));
            const a = lum(parse(cs.color)), b = lum(parse(cs.backgroundColor));
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        })()"""
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_app({"state": (200, STATE)},
                                        init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                page.wait_for_function("document.querySelector('#today-bonus-pill').textContent === 'Olish'")
                self.assertGreaterEqual(page.evaluate(script), 4.5)

    def test_wheel_quick_action_opens_wheel(self):
        page, _ = self.open_app({"state": (200, STATE)})
        self.open_wheel(page)                                               # #btn-open-wheel = "Baraban"
        self.assertIn("Baraban", page.inner_text("#btn-open-wheel"))

    # ---- "Bugun" kartasi -----------------------------------------------------------------
    def test_today_card_unclaimed_and_ready(self):
        page, _ = self.open_app({"state": (200, STATE)})
        page.wait_for_function("document.querySelector('#today-bonus-sub').textContent.includes('seriya')")
        self.assertEqual(page.inner_text("#today-bonus-sub"), "3-kun seriya · +3 ball")
        self.assertEqual(page.inner_text("#today-bonus-pill"), "Olish")
        self.assertEqual(page.inner_text("#today-wheel-sub"), "Tayyor — bepul aylantiring")

    def test_today_card_claimed_and_wheel_countdown(self):
        page, _ = self.open_app({"state": (200, {**STATE, "daily_claimed": True, "streak": 7,
                                                 "prize": None, "cooldown_seconds": 3661})})
        page.wait_for_function("document.querySelector('#today-bonus-sub').textContent.startsWith('Olindi')")
        self.assertEqual(page.inner_text("#today-bonus-sub"), "Olindi · 7-kun seriya")
        self.assertEqual(page.inner_text("#today-bonus-pill"), "Olindi")
        self.assertRegex(page.inner_text("#today-wheel-sub"), r"Keyingisi: 01:01:0\d")
        self.assertEqual(page.inner_text("#today-wheel-pill"), "Kutish")
        page.clock.fast_forward(3700_000)                                   # cooldown tugadi
        page.wait_for_function("document.querySelector('#today-wheel-pill').textContent === 'Ochish'")

    def test_today_rows_open_bonus_and_wheel(self):
        page, _ = self.open_app({"state": (200, STATE)})
        page.click("#btn-open-daily-bonus")
        page.wait_for_selector("#daily-bonus-modal:not(.hidden)")
        page.click("#daily-bonus-close")
        page.click("#wheel-promo-card")
        page.wait_for_function("document.querySelector('#wheel-modal').style.display === 'flex'")

    def test_today_rows_keyboard_accessible(self):
        page, _ = self.open_app({"state": (200, STATE)})
        page.focus("#btn-open-daily-bonus")
        page.keyboard.press("Enter")
        page.wait_for_selector("#daily-bonus-modal:not(.hidden)")

    def test_today_card_updates_after_bonus_claim(self):
        page, _ = self.open_app({"state": (200, STATE), "bonus/claim": (200, {
            "ok": True, "message": "ok", "points": 3, "streak": 3, "score": 123})})
        page.wait_for_function("document.querySelector('#today-bonus-pill').textContent === 'Olish'")
        page.click("#btn-open-daily-bonus")
        self.press_main(page, "#btn-claim-daily-bonus")
        page.wait_for_selector("#daily-bonus-result")
        self.assertEqual(page.inner_text("#today-bonus-pill"), "Olindi")

    def test_today_card_from_url_when_api_unavailable(self):
        page, _ = self.open_app({}, query="?streak=2&daily_claimed=0&prize=3", init_data="")
        page.wait_for_function("document.querySelector('#today-bonus-sub').textContent.includes('seriya')")
        self.assertEqual(page.inner_text("#today-bonus-sub"), "2-kun seriya · +2 ball")

    def test_today_card_default_text_without_any_data(self):
        page, _ = self.open_app({}, init_data="")
        self.assertEqual(page.inner_text("#today-bonus-sub"), "Har kuni kirib, ball oling")

    # ---- Premium banner -----------------------------------------------------------------
    def test_premium_banner_hidden_for_premium_users(self):
        page, _ = self.open_app({"state": (200, STATE)})
        page.wait_for_function("document.querySelector('#today-bonus-sub').textContent.includes('seriya')")
        self.assertTrue(page.is_visible("#btn-open-premium"))
        page2, _ = self.open_app({"state": (200, {**STATE, "is_premium": True, "premium_type": "plus"})})
        page2.wait_for_selector("#hdr-premium:not([hidden])")
        self.assertFalse(page2.is_visible("#btn-open-premium"))

    # ---- Ro'yxat ---------------------------------------------------------------------------
    def test_first_aid_list_rows(self):
        page, _ = self.open_app({})
        rows = page.locator("#first-aid-grid .list-row")
        self.assertEqual(rows.count(), 9)
        self.assertEqual(page.inner_text('#first-aid-grid [data-id="kuyish"] .row-title'), "Kuyish")   # emoji qatorda yo'q
        self.assertEqual(page.locator('#first-aid-grid [data-id="qon_ketishi"] .row-icon--danger').count(), 1)
        self.assertEqual(page.locator('#first-aid-grid [data-id="kuyish"] .row-icon--primary').count(), 1)
        for i in range(rows.count()):
            self.assertGreaterEqual(rows.nth(i).bounding_box()["height"], 44)

    def test_search_filters_and_shows_empty_state(self):
        page, _ = self.open_app({})
        page.fill("#first-aid-search", "qon")
        visible = page.evaluate("[...document.querySelectorAll('#first-aid-grid .list-row')].filter(r => !r.hidden).map(r => r.dataset.id)")
        self.assertEqual(visible, ["qon_ketishi"])
        for q in ("bog‘ilish", "bo'g'ilish", "BOGILISH", "bogʻilish"):     # apostrof shakllari va katta harf
            page.fill("#first-aid-search", q)
            visible = page.evaluate("[...document.querySelectorAll('#first-aid-grid .list-row')].filter(r => !r.hidden).map(r => r.dataset.id)")
            self.assertEqual(visible, ["bogilish"], q)
        page.fill("#first-aid-search", "xyzxyz")
        self.assertTrue(page.is_visible("#first-aid-empty"))
        self.assertFalse(page.is_visible("#first-aid-grid"))
        page.fill("#first-aid-search", "")
        self.assertEqual(page.locator("#first-aid-grid .list-row:not([hidden])").count(), 9)

    def test_row_opens_detail(self):
        page, _ = self.open_app({})
        page.click('#first-aid-grid [data-id="kuyish"]')
        page.wait_for_function("document.getElementById('overlay-title').textContent.includes('Kuyish')")


if __name__ == "__main__":
    unittest.main()
