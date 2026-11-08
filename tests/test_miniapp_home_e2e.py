"""
test_miniapp_home_e2e.py — G bosh ekran (docs/MINI_APP_G_TASK.md, 2-bosqich):
header (bosh harflar, ★ ball, 103 doira), "Qayeringiz og'riyapti?", tana figurasi (2.4 geometriya, Oldi/Orqa),
hudud -> bottom sheet (body_map_data.json), holat chiplari + "Hammasi" sahifasi, "Bugun" kartalari, Test qatori,
Premium qatori Sog'liq tabida. Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase

STATE = {**STATE_OK, "score": 120, "streak": 3, "daily_claimed": False, "prize": 5, "cooldown_seconds": 0,
         "is_premium": False, "premium_type": "free"}
LABEL = "#body-figure .fig-label[data-slot='{}']"


class HomeE2ETest(MiniAppE2EBase):
    def active_section(self, page):
        return page.evaluate("document.querySelector('.tab-content.active').id")

    def ready(self, page):
        page.wait_for_function("bodyMapData !== null")

    # ---- Header ----------------------------------------------------------------------------
    def test_header_initials_score_and_103(self):
        page, _ = self.open_app({"state": (200, STATE)})
        page.wait_for_selector("#global-score:not([hidden])")
        self.assertEqual(page.inner_text("#user-avatar"), "AL")                         # Ali -> bosh harflar
        self.assertEqual(page.evaluate("getComputedStyle(document.getElementById('user-avatar')).width"), "42px")
        self.assertRegex(page.inner_text("#global-score"), r"120\s+ball")
        btn = page.locator(".emergency-btn")
        self.assertEqual(btn.get_attribute("href"), "tel:103")
        self.assertEqual(btn.get_attribute("aria-label"), "103 — tez yordamni chaqirish")
        box = btn.bounding_box()
        self.assertEqual((round(box["width"]), round(box["height"])), (48, 48))
        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, ".emergency-btn"), 4.5)

    def test_old_home_blocks_removed(self):
        page, _ = self.open_app({})
        for sel in (".sos-card", ".quick-actions", ".qa", ".premium-banner"):
            self.assertEqual(page.locator(sel).count(), 0, sel)
        self.assertFalse(page.is_visible("#first-aid-grid"))                            # ro'yxat "Hammasi" sahifasida

    # ---- Sarlavha va tana figurasi ---------------------------------------------------------
    def test_title_and_figure_geometry(self):
        page, _ = self.open_app({})
        self.ready(page)
        page.wait_for_function("document.fonts.status === 'loaded'")                   # Nunito almashguncha joy siljiydi
        self.assertEqual(page.inner_text(".home-h1"), "Qayeringiz og'riyapti?")
        self.assertEqual(page.inner_text(".home-sub"), "Tana qismini bosing")
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.home-h1')).fontSize"), "28px")
        wrap = page.locator("#body-figure").bounding_box()
        self.assertEqual((round(wrap["width"]), round(wrap["height"])), (350, 340))
        self.assertEqual(page.get_attribute("#body-figure svg", "viewBox"), "0 0 350 340")
        expected = {1: ("left", 17), 2: ("left", 128), 3: ("right", 89), 4: ("right", 137), 5: ("right", 253)}
        for slot, (side, top) in expected.items():
            wrap = page.locator("#body-figure").bounding_box()
            box = page.locator(LABEL.format(slot)).bounding_box()
            self.assertEqual((round(box["width"]), round(box["height"])), (76, 36), slot)
            self.assertAlmostEqual(box["y"] - wrap["y"], top, delta=1)
            if side == "left":
                self.assertAlmostEqual(box["x"], wrap["x"], delta=1)
            else:
                self.assertAlmostEqual(box["x"] + box["width"], wrap["x"] + wrap["width"], delta=1)
            hit = page.evaluate(f"(() => {{ const s = getComputedStyle(document.querySelector(\"{LABEL.format(slot)}\"), '::after');"
                                f" return 36 - 2 * parseFloat(s.top); }})()")
            self.assertGreaterEqual(hit, 44)                                             # bosish zonasi >= 44px

    def test_front_back_labels_and_spine(self):
        page, _ = self.open_app({})
        self.ready(page)
        front = page.evaluate("[...document.querySelectorAll('#body-figure .fig-label')].map(b => [b.id, b.textContent])")
        self.assertEqual(front, [["bosh", "Bosh"], ["qol", "Qo'l"], ["kokrak", "Ko'krak"], ["qorin", "Qorin"], ["oyoq", "Oyoq"]])
        spine = "getComputedStyle(document.querySelector('.fig-spine')).display"
        self.assertEqual(page.evaluate(spine), "none")                                  # umurtqa — faqat Orqa
        page.click(".fig-views [data-view='back']")
        back = page.evaluate("[...document.querySelectorAll('#body-figure .fig-label')].map(b => [b.id, b.textContent])")
        self.assertEqual(back, [["bosh", "Bosh"], ["qol", "Qo'l"], ["orqa", "Orqa"], ["bel", "Bel"], ["oyoq", "Oyoq"]])
        self.assertEqual(page.get_attribute("#body-figure", "data-view"), "back")
        self.assertNotEqual(page.evaluate(spine), "none")
        self.assertEqual(page.get_attribute(".fig-views [data-view='back']", "aria-pressed"), "true")

    def test_hotspot_opens_sheet_with_region_conditions(self):
        page, _ = self.open_app({})
        self.ready(page)
        page.click("#kokrak")
        page.wait_for_selector("#body-map-modal:not([hidden])")
        self.assertEqual(page.inner_text("#modal-title"), "Ko'krak")
        names = page.evaluate("[...document.querySelectorAll('#modal-diseases-list .sheet-item-name')].map(e => e.textContent)")
        self.assertEqual(names, page.evaluate("bodyMapData.chest.diseases.map(d => d.name)"))
        self.assertIn("selected", page.get_attribute("#kokrak", "class"))
        self.assertEqual(page.get_attribute("#kokrak", "aria-pressed"), "true")
        self.assertEqual(page.inner_text("#body-map-modal .sheet-disclaimer"), "Bu ma'lumot tashxis emas. Og'ir holatda 103.")
        self.assertEqual(self.tg(page)["mainText"], "AI'dan so'rash")
        # Bir nechta hudud: Bosh = head + neck (takrorsiz)
        page.click("#modal-close")
        page.click("#bosh")
        expected = page.evaluate("[...bodyMapData.head.diseases, ...bodyMapData.neck.diseases].map(d => d.name)")
        names = page.evaluate("[...document.querySelectorAll('#modal-diseases-list .sheet-item-name')].map(e => e.textContent)")
        self.assertEqual(names, expected)
        self.assertEqual(page.get_attribute("#kokrak", "aria-pressed"), "false")

    def test_ai_button_falls_back_to_send_data(self):
        page, _ = self.open_app({})
        self.ready(page)
        page.click("#kokrak")
        page.evaluate("window.__mainCb()")
        page.clock.fast_forward(400)
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot?start=ai_consult_chest"])

    def test_narrow_screen_scales_figure(self):
        page, _ = self.open_app({})
        page.set_viewport_size({"width": 320, "height": 700})
        page.evaluate("window.dispatchEvent(new Event('resize'))")
        outer = page.locator("#body-figure-outer").bounding_box()
        wrap = page.locator("#body-figure").bounding_box()
        self.assertLessEqual(wrap["width"], outer["width"] + 1)
        self.assertAlmostEqual(outer["height"], 340 * wrap["width"] / 350, delta=2)
        self.assertEqual(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), True)  # gorizontal skroll yo'q

    # ---- Holat chiplari va "Hammasi" -------------------------------------------------------
    def test_condition_chips_critical_first_then_all(self):
        page, _ = self.open_app({})
        ids = page.evaluate("[...document.querySelectorAll('#home-chips .home-chip')].map(c => c.dataset.id || c.id)")
        critical = page.evaluate("FIRST_AID_ITEMS.filter(i => i.urgency === 'critical').map(i => i.id)")
        rest = page.evaluate("FIRST_AID_ITEMS.filter(i => i.urgency !== 'critical').map(i => i.id)")
        self.assertEqual(ids, critical + rest + ["home-chip-all"])
        chip = page.locator('#home-chips [data-id="kuyish"]')
        self.assertEqual(chip.inner_text(), "Kuyish")                                    # emoji yo'q
        self.assertEqual(round(chip.bounding_box()["height"]), 42)
        self.assertEqual(page.inner_text("#home-chip-all"), "Hammasi")
        chip.click()
        page.wait_for_function("document.getElementById('overlay-title').textContent.includes('Kuyish')")

    def test_hammasi_page_with_search_and_back(self):
        page, _ = self.open_app({})
        page.click("#home-chip-all")
        self.assertEqual(self.active_section(page), "tab-first-aid-all")
        self.assertTrue(self.tg(page)["backVisible"])
        rows = page.locator("#first-aid-grid .list-row")
        self.assertEqual(rows.count(), 9)
        self.assertEqual(page.locator('#first-aid-grid [data-id="qon_ketishi"] .row-icon--danger').count(), 1)
        page.fill("#first-aid-search", "bogilish")
        visible = page.evaluate("[...document.querySelectorAll('#first-aid-grid .list-row')].filter(r => !r.hidden).map(r => r.dataset.id)")
        self.assertEqual(visible, ["bogilish"])
        page.fill("#first-aid-search", "xyzxyz")
        self.assertTrue(page.is_visible("#first-aid-empty"))
        page.fill("#first-aid-search", "")
        page.click('#first-aid-grid [data-id="kuyish"]')
        page.wait_for_selector("#overlay-details.active")
        page.evaluate("window.__backCb()")
        page.clock.fast_forward(400)
        page.evaluate("window.__backCb()")                                               # "Hammasi" -> bosh ekran
        self.assertEqual(self.active_section(page), "tab-first-aid")
        self.assertFalse(self.tg(page)["backVisible"])

    # ---- "Bugun" kartalari -----------------------------------------------------------------
    def test_today_cards_unclaimed_and_ready(self):
        page, _ = self.open_app({"state": (200, STATE)})
        page.wait_for_function("document.querySelector('#today-bonus-sub').textContent.includes('seriya')")
        self.assertEqual(page.inner_text("#today-bonus-sub"), "3-kun seriya")
        self.assertEqual(page.inner_text("#today-bonus-claim"), "Olish +3")
        self.assertTrue(page.is_enabled("#today-bonus-claim"))
        self.assertEqual(page.inner_text("#btn-open-wheel"), "Aylantirish")
        self.assertEqual(page.inner_text("#today-wheel-sub"), "Tayyor")
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                p2, _ = self.open_app({"state": (200, STATE)}, init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                p2.wait_for_function("document.querySelector('#today-bonus-claim').textContent === 'Olish +3'")
                self.assertGreaterEqual(p2.evaluate(CONTRAST_JS, "#today-bonus-claim"), 4.5)
                self.assertGreaterEqual(p2.evaluate(CONTRAST_JS, "#btn-open-wheel"), 4.5)

    def test_today_cards_claimed_and_wheel_countdown(self):
        page, _ = self.open_app({"state": (200, {**STATE, "daily_claimed": True, "streak": 7,
                                                 "prize": None, "cooldown_seconds": 4783})})
        page.wait_for_function("document.querySelector('#today-bonus-claim').textContent === 'Olindi'")
        self.assertTrue(page.is_disabled("#today-bonus-claim"))
        self.assertEqual(page.locator("#today-bonus-claim svg").count(), 1)               # ✓ ikonka
        self.assertEqual(page.inner_text("#today-bonus-sub"), "7-kun seriya")
        self.assertRegex(page.inner_text("#btn-open-wheel"), r"^01:19:4\d$")              # tabular taymer
        self.assertIn("is-waiting", page.get_attribute("#btn-open-wheel", "class"))
        self.assertEqual(page.inner_text("#today-wheel-sub"), "Keyingisi")
        page.clock.fast_forward(4800_000)
        page.wait_for_function("document.querySelector('#btn-open-wheel').textContent === 'Aylantirish'")

    def test_wheel_card_opens_wheel_sheet(self):
        for sel in ("#btn-open-wheel", "#wheel-promo-card"):
            with self.subTest(sel=sel):
                page, _ = self.open_app({"state": (200, STATE)})
                page.click(sel)
                page.wait_for_function("document.querySelector('#wheel-modal').style.display === 'flex'")

    def test_bonus_card_opens_sheet_and_claims_from_home(self):
        page, calls = self.open_app({"state": (200, STATE), "bonus/claim": (200, {
            "ok": True, "message": "ok", "points": 3, "streak": 3, "score": 123})})
        page.wait_for_function("document.querySelector('#today-bonus-claim').textContent === 'Olish +3'")
        page.click("#today-bonus-claim")                                                  # mavjud api('bonus/claim')
        self.wait_for_call(calls, "bonus/claim")
        page.wait_for_function("document.querySelector('#today-bonus-claim').textContent === 'Olindi'")
        self.assertEqual(page.inner_text("#global-score-val"), "123")
        page.click("#btn-open-daily-bonus")
        page.wait_for_selector("#daily-bonus-modal:not(.hidden)")

    def test_today_card_from_url_when_api_unavailable(self):
        page, _ = self.open_app({}, query="?streak=2&daily_claimed=0&prize=3", init_data="")
        page.wait_for_function("document.querySelector('#today-bonus-sub').textContent.includes('seriya')")
        self.assertEqual(page.inner_text("#today-bonus-claim"), "Olish +2")

    def test_today_card_default_text_without_any_data(self):
        page, _ = self.open_app({}, init_data="")
        self.assertEqual(page.inner_text("#today-bonus-sub"), "Kunlik bonus")
        self.assertEqual(page.inner_text("#btn-open-wheel"), "Aylantirish")

    # ---- Test qatori va Premium -------------------------------------------------------------
    def test_quiz_row_opens_quiz_and_back_returns(self):
        page, _ = self.open_app({})
        page.click("#home-quiz-row")
        self.assertEqual(self.active_section(page), "tab-quiz")
        self.assertTrue(self.tg(page)["backVisible"])
        page.evaluate("window.__backCb()")
        self.assertEqual(self.active_section(page), "tab-first-aid")

    def test_premium_row_in_health_tab_hidden_for_premium(self):
        page, _ = self.open_app({"state": (200, STATE)})
        page.wait_for_selector("#global-score:not([hidden])")
        page.click('nav [data-tab="tab-health"]')
        self.assertTrue(page.is_visible("#btn-open-premium"))
        self.assertIn("Premium", page.inner_text("#btn-open-premium"))
        page.click("#btn-open-premium")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        page2, _ = self.open_app({"state": (200, {**STATE, "is_premium": True, "premium_type": "plus"})})
        page2.wait_for_selector("#hdr-premium:not([hidden])")
        page2.click('nav [data-tab="tab-health"]')
        self.assertFalse(page2.is_visible("#btn-open-premium"))


if __name__ == "__main__":
    unittest.main()
