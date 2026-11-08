"""
test_miniapp_detail_e2e.py — redesign 4.4-C: detal sahifa (birinchi yordam va kasallik), tg.MainButton, tg.BackButton.
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import MiniAppE2EBase


class DetailE2ETest(MiniAppE2EBase):
    def open_item(self, page, item_id):
        page.click(f'#first-aid-grid [data-id="{item_id}"]')
        page.wait_for_selector("#overlay-details.active")

    def item(self, page, item_id):
        return page.evaluate(f"FIRST_AID_ITEMS.find(i => i.id === '{item_id}')")

    def test_critical_item_layout_and_103_main_button(self):
        page, _ = self.open_app({})
        self.open_item(page, "qon_ketishi")
        data = self.item(page, "qon_ketishi")
        self.assertEqual(page.inner_text("#overlay-title"), data["title"])           # ma'lumot matni o'zgarmagan
        self.assertEqual(page.inner_text("#overlay-chips .chip"), "Kritik holat")
        self.assertEqual(page.locator("#overlay-chips .chip--danger").count(), 1)
        steps = page.evaluate("[...document.querySelectorAll('.timeline-step .timeline-text')].map(e => e.innerText.trim())")
        self.assertEqual(steps, [s.strip() for s in data["steps"]])
        nums = page.evaluate("[...document.querySelectorAll('.timeline-num')].map(e => e.innerText.trim())")
        self.assertEqual(nums, [str(i + 1) for i in range(len(data["steps"]))])
        self.assertIn("Qilmang!", page.inner_text(".dont-card .dont-title"))
        self.assertIn(data["prohibited"].strip()[:40], page.inner_text(".dont-card p"))
        self.assertIn("Bu ma'lumot tashxis emas. Og'ir holatda 103.", page.inner_text(".detail-disclaimer"))
        tg = self.tg(page)
        self.assertTrue(tg["mainVisible"])
        self.assertEqual(tg["mainText"], "103 ga qo'ng'iroq")
        self.assertEqual(tg["mainParams"]["color"].upper(), "#C9343A")

    def test_non_critical_item_main_button_asks_ai_in_bot(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        self.assertEqual(page.inner_text("#overlay-chips .chip"), "Muhim holat")
        tg = self.tg(page)
        self.assertEqual(tg["mainText"], "AI'dan so'rash")
        page.evaluate("window.__mainCb()")
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot"])
        self.assertEqual(self.tg(page)["closed"], 0)

    def test_back_closes_detail_and_hides_main_button(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        self.assertTrue(self.tg(page)["backVisible"])
        self.assertFalse(page.is_visible("#close-overlay-btn"))                     # Telegram ichida o'z tugmamiz yo'q
        page.evaluate("window.__backCb()")
        page.wait_for_selector("#overlay-details:not(.active)", state="attached")
        tg = self.tg(page)
        self.assertFalse(tg["mainVisible"])
        self.assertFalse(tg["backVisible"])
        self.assertIsNone(page.evaluate("window.__mainCb"))                          # handler ham olib tashlangan

    def test_switching_items_keeps_single_main_button_handler(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        page.evaluate("window.__backCb()")
        page.clock.fast_forward(400)
        self.open_item(page, "qon_ketishi")
        self.assertEqual(self.tg(page)["mainText"], "103 ga qo'ng'iroq")

    def test_call_card_and_symptoms_present_when_data_has_them(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        data = self.item(page, "kuyish")
        self.assertEqual(page.locator(".symptom-tag").count(), len(data["symptoms"]))
        if data.get("whenToCall103"):
            self.assertEqual(page.get_attribute(".call-card .call-btn", "href"), "tel:103")

    def test_browser_fallback_back_button(self):
        page, _ = self.open_app({}, init_script="delete window.Telegram.WebApp.BackButton;")
        self.open_item(page, "kuyish")
        self.assertTrue(page.is_visible("#close-overlay-btn"))
        page.click("#close-overlay-btn")
        page.wait_for_selector("#overlay-details:not(.active)", state="attached")

    def test_disease_detail(self):
        page, _ = self.open_app({})
        page.click('nav [data-tab="tab-diseases"]')
        first = page.evaluate("DISEASES_DATA[0]")
        page.locator("#disease-list-container .disease-item, #disease-list-container .list-row").first.click()
        page.wait_for_selector("#overlay-details.active")
        self.assertEqual(page.inner_text("#overlay-title"), first["name"])
        self.assertEqual(page.inner_text("#overlay-chips .chip"), first["cat"])
        self.assertIn("Kasallik tavsifi", page.inner_text("#overlay-body-content"))
        self.assertIn("Birinchi yordam va chora", page.inner_text("#overlay-body-content"))
        self.assertEqual(self.tg(page)["mainText"], "AI'dan so'rash")


if __name__ == "__main__":
    unittest.main()
