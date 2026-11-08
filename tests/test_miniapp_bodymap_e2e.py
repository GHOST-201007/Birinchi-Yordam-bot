"""
test_miniapp_bodymap_e2e.py — redesign 4.4-H: Tana xaritasi.
Toza siluet ("SCAN 3D"/lazer/HUD yo'q), tanlangan a'zo --primary, Oldi/Orqa segmented,
pastdan chiquvchi bottom sheet (modal emas), MainButton "AI konsultant" — tg.sendData oqimi o'zgarmagan.
Asos: tests/e2e_base.py
"""
import json
import re
import unittest

from tests.e2e_base import MiniAppE2EBase

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")
PART = '#body-map-container .body-part[data-part="{}"]'


class BodyMapE2ETest(MiniAppE2EBase):
    def open_tab(self, **kw):
        page, _ = self.open_app({}, **kw)
        page.click('nav [data-tab="tab-body-map"]')
        page.wait_for_selector(PART.format("head"))
        return page

    def test_clean_silhouette_no_scanner_hud_no_emoji(self):
        page = self.open_tab()
        for sel in (".scanner-laser", ".scanner-hud-tag", ".scanner-grid-bg", ".part-pin", ".part-label",
                    "#body-map-container [onclick]", "#body-map-container [style]", "#body-map-container defs"):
            self.assertEqual(page.locator(sel).count(), 0, sel)
        self.assertNotIn("SCAN", page.inner_text("#tab-body-map"))
        self.assertIsNone(EMOJI.search(page.inner_text("#tab-body-map")))

    def test_parts_are_accessible_buttons(self):
        page = self.open_tab()
        head = page.locator(PART.format("head"))
        self.assertEqual(head.get_attribute("role"), "button")
        self.assertEqual(head.get_attribute("tabindex"), "0")
        self.assertEqual(head.get_attribute("aria-label"), "Bosh")
        self.assertEqual(page.get_attribute(PART.format("left_knee"), "aria-label"), "Chap tizza")
        page.focus(PART.format("chest"))
        page.keyboard.press("Enter")
        self.assertTrue(page.is_visible("#body-map-modal"))
        self.assertEqual(page.inner_text("#modal-title"), "Ko'krak")

    def test_selected_part_filled_primary_others_outline(self):
        page = self.open_tab()
        page.click(PART.format("head"))
        page.wait_for_function(f"getComputedStyle(document.querySelector('{PART.format('head')} .part-shape')).fill === 'rgb(10, 132, 198)'",
                               timeout=2000)                                           # --primary (transition tugagach)
        self.assertEqual(page.get_attribute(PART.format("head"), "aria-pressed"), "true")
        other = page.evaluate(f"getComputedStyle(document.querySelector('{PART.format('neck')} .part-shape')).fill")
        self.assertNotEqual(other, "rgb(10, 132, 198)")
        page.click(PART.format("neck"))                                                 # boshqa a'zo — tanlov ko'chadi
        self.assertEqual(page.get_attribute(PART.format("head"), "aria-pressed"), "false")
        self.assertEqual(page.inner_text("#modal-title"), "Bo'yin")

    def test_front_back_segmented(self):
        page = self.open_tab()
        self.assertEqual(page.get_attribute('[data-view="front"]', "aria-selected"), "true")
        page.click('[data-view="back"]')
        self.assertEqual(page.get_attribute('[data-view="back"]', "aria-selected"), "true")
        self.assertEqual(page.locator(PART.format("back")).count(), 1)
        self.assertEqual(page.locator(PART.format("chest")).count(), 0)

    def test_sheet_is_non_modal_bottom_sheet_with_content(self):
        page = self.open_tab()
        page.emulate_media(reduced_motion="reduce")                                    # kirish animatsiyasisiz o'lchash
        page.click(PART.format("head"))
        sheet = page.locator("#body-map-modal").bounding_box()
        nav = page.locator(".app-nav").bounding_box()
        self.assertAlmostEqual(sheet["y"] + sheet["height"], nav["y"], delta=1)         # pastki menyu ustida
        self.assertLess(sheet["height"], 844 * 0.6)
        self.assertEqual(page.get_attribute("#body-map-modal", "aria-modal"), "false")
        self.assertTrue(page.is_visible(PART.format("head")))                          # xarita ko'rinib turadi
        data = page.evaluate("bodyMapData.head.diseases.map(d => d.name)")
        self.assertEqual(page.evaluate("[...document.querySelectorAll('#modal-diseases-list .sheet-item-name')].map(e => e.textContent)"),
                         data)
        self.assertIn("aniq tashxis emas", page.inner_text("#body-map-modal .sheet-disclaimer"))
        urgent = page.evaluate("bodyMapData.head.diseases.filter(d => d.urgent).length")
        self.assertEqual(page.locator("#modal-diseases-list .is-urgent .chip--danger").count(), urgent)

    def test_disease_items_accordion_one_open(self):
        page = self.open_tab()
        page.click(PART.format("head"))
        items = page.locator("#modal-diseases-list .sheet-item summary")
        items.nth(0).click()
        self.assertTrue(page.is_visible("#modal-diseases-list .sheet-item:nth-child(1) .sheet-item-desc"))
        items.nth(1).click()
        page.wait_for_function("document.querySelectorAll('#modal-diseases-list details[open]').length === 1")
        self.assertEqual(self.tg(page)["impacts"].count("light") >= 2, True)

    def test_main_button_ai_consult_flow_unchanged(self):
        page = self.open_tab()
        page.click(PART.format("left_knee"))
        tg = self.tg(page)
        self.assertTrue(tg["mainVisible"])
        self.assertEqual(tg["mainText"], "AI konsultant")
        self.assertFalse(page.is_visible("#ai-consult-btn"))                           # Telegram ichida — MainButton
        page.evaluate("window.__mainCb()")
        page.clock.fast_forward(400)
        sent = self.tg(page)["sent"]
        self.assertEqual([json.loads(s) for s in sent], [{"action": "ai_consult", "title": "Tizza"}])
        tg = self.tg(page)
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot?start=ai_consult_left_knee"])
        self.assertEqual(tg["closed"], 1)

    def test_close_by_button_back_button_escape_and_tab_change(self):
        page = self.open_tab()
        page.click(PART.format("head"))
        page.click("#modal-close")
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertFalse(self.tg(page)["mainVisible"])
        self.assertFalse(self.tg(page)["backVisible"])
        page.click(PART.format("head"))
        self.assertTrue(self.tg(page)["backVisible"])
        page.click(PART.format("neck"))                                                 # stekka ikkinchi marta qo'shilmaydi
        page.evaluate("window.__backCb()")
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertFalse(self.tg(page)["backVisible"])
        page.click(PART.format("head"))
        page.keyboard.press("Escape")
        self.assertFalse(page.is_visible("#body-map-modal"))
        page.click(PART.format("head"))
        page.click('nav [data-tab="tab-first-aid"]')
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertFalse(self.tg(page)["mainVisible"])
        self.assertEqual(page.evaluate("document.querySelectorAll('#body-map-container .body-part.selected').length"), 0)

    def test_quick_chips_text_only_open_sheet(self):
        page = self.open_tab()
        chips = page.evaluate("[...document.querySelectorAll('#body-quick-chips .cat-chip')].map(c => c.textContent)")
        self.assertIn("Bosh", chips)
        page.click('#body-quick-chips [data-part="foot"]')
        self.assertTrue(page.is_visible("#body-map-modal"))
        self.assertEqual(page.inner_text("#modal-title"), page.evaluate("bodyPartName('foot')"))

    def test_browser_fallback_button(self):
        page = self.open_tab(init_data="")
        page.click(PART.format("head"))
        self.assertTrue(page.is_visible("#ai-consult-btn"))
        self.assertEqual(page.inner_text("#ai-consult-btn"), "AI konsultant")
        self.assertFalse(self.tg(page)["mainVisible"])


if __name__ == "__main__":
    unittest.main()
