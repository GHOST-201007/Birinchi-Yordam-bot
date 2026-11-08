"""
test_miniapp_bodymap_e2e.py — tana hududi bottom sheet (body_map_data.json).
G Stage 1: "Tana" tabi olib tashlandi; sheet va a'zo ma'lumoti mantig'i saqlanadi (Stage 2 da bosh ekrandagi
tana figurasidan ochiladi). Bu yerda sheet openBodyMapModal() orqali ochiladi.
MainButton "AI'dan so'rash" — 4-bosqichdan: AI tabini kontekst chipi bilan ochadi (xabar yuborilmaydi).
Eski tg.sendData oqimi — AI tabidagi "Botda davom etish" zaxirasi (test_miniapp_ai_chat_e2e.py).
"""
import json
import unittest

from tests.e2e_base import MiniAppE2EBase


class BodySheetE2ETest(MiniAppE2EBase):
    def open_sheet(self, key="head", **kw):
        page, _ = self.open_app({}, **kw)
        page.wait_for_function("bodyMapData !== null")
        page.emulate_media(reduced_motion="reduce")
        page.evaluate(f"openBodyMapModal('{key}')")
        page.wait_for_selector("#body-map-modal:not([hidden])")
        return page

    def test_tana_tab_and_map_removed(self):
        page, _ = self.open_app({})
        self.assertEqual(page.locator("#tab-body-map").count(), 0)
        self.assertEqual(page.locator('[data-tab="tab-body-map"]').count(), 0)
        self.assertFalse(page.evaluate("typeof renderBodyMap !== 'undefined' || typeof FRONT_BODY_SVG !== 'undefined'"))
        self.assertEqual(page.locator("#body-map-modal").count(), 1)                    # sheet saqlangan

    def test_sheet_is_non_modal_bottom_sheet_above_nav(self):
        page = self.open_sheet()
        sheet = page.locator("#body-map-modal").bounding_box()
        nav = page.locator(".app-nav").bounding_box()
        self.assertAlmostEqual(sheet["y"] + sheet["height"], nav["y"], delta=1)         # pastki menyu ustida
        self.assertLess(sheet["height"], 844 * 0.6)
        self.assertEqual(page.get_attribute("#body-map-modal", "aria-modal"), "false")
        self.assertEqual(page.inner_text("#modal-title"), "Bosh")
        data = page.evaluate("bodyMapData.head.diseases.map(d => d.name)")
        self.assertEqual(page.evaluate("[...document.querySelectorAll('#modal-diseases-list .sheet-item-name')].map(e => e.textContent)"),
                         data)
        urgent = page.evaluate("bodyMapData.head.diseases.filter(d => d.urgent).length")
        self.assertEqual(page.locator("#modal-diseases-list .is-urgent .chip--danger").count(), urgent)

    def test_disease_items_accordion_one_open(self):
        page = self.open_sheet()
        items = page.locator("#modal-diseases-list .sheet-item summary")
        items.nth(0).click()
        self.assertTrue(page.is_visible("#modal-diseases-list .sheet-item:nth-child(1) .sheet-item-desc"))
        items.nth(1).click()
        page.wait_for_function("document.querySelectorAll('#modal-diseases-list details[open]').length === 1")

    def test_main_button_opens_ai_chat_with_context(self):
        page = self.open_sheet("left_knee")
        tg = self.tg(page)
        self.assertTrue(tg["mainVisible"])
        self.assertFalse(page.is_visible("#ai-consult-btn"))                           # Telegram ichida — MainButton
        page.evaluate("window.__mainCb()")
        page.wait_for_selector("#tab-ai.active")
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertEqual(page.inner_text("#ai-context-label"), "Tana qismi: Chap tizza")
        tg = self.tg(page)
        self.assertEqual([json.loads(s) for s in tg["sent"]], [])                       # botga chiqmaydi
        self.assertEqual((tg["links"], tg["closed"], tg["mainVisible"]), ([], 0, False))

    def test_close_by_button_back_escape_and_tab_change(self):
        page = self.open_sheet()
        page.click("#modal-close")
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertFalse(self.tg(page)["mainVisible"])
        self.assertFalse(self.tg(page)["backVisible"])
        page.evaluate("openBodyMapModal('head')")
        self.assertTrue(self.tg(page)["backVisible"])
        page.evaluate("openBodyMapModal('neck')")                                       # stekka ikkinchi marta qo'shilmaydi
        page.evaluate("window.__backCb()")
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertFalse(self.tg(page)["backVisible"])
        page.evaluate("openBodyMapModal('head')")
        page.keyboard.press("Escape")
        self.assertFalse(page.is_visible("#body-map-modal"))
        page.evaluate("openBodyMapModal('head')")
        page.click('nav [data-tab="tab-diseases"]')                                     # boshqa bo'lim — sheet yopiladi
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertFalse(self.tg(page)["mainVisible"])

    def test_browser_fallback_button(self):
        page = self.open_sheet(init_data="")
        self.assertTrue(page.is_visible("#ai-consult-btn"))
        self.assertFalse(self.tg(page)["mainVisible"])


if __name__ == "__main__":
    unittest.main()
