"""
test_miniapp_diseases_e2e.py — redesign 4.4-D: sticky qidiruv, kategoriya chiplari, alifbo bo'yicha guruhlangan ro'yxat.
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import MiniAppE2EBase

ROWS = "#disease-list-container .list-row"


class DiseasesE2ETest(MiniAppE2EBase):
    def open_tab(self):
        page, _ = self.open_app({})
        page.click('nav [data-tab="tab-diseases"]')
        return page

    def names(self, page):
        return page.evaluate(f"[...document.querySelectorAll('{ROWS} .row-title')].map(e => e.textContent)")

    def test_all_diseases_listed_once(self):
        page = self.open_tab()
        total = page.evaluate("DISEASES_DATA.length")
        self.assertGreaterEqual(total, 100)
        self.assertEqual(sorted(self.names(page)), sorted(page.evaluate("DISEASES_DATA.map(d => d.name)")))

    def test_grouped_by_first_letter_with_headers(self):
        page = self.open_tab()
        groups = page.evaluate("""[...document.querySelectorAll('#disease-list-container .letter-header')].map(h =>
            [h.textContent, [...h.nextElementSibling.querySelectorAll('.row-title')].map(e => e.textContent)])""")
        self.assertGreater(len(groups), 10)
        for letter, names in groups:
            self.assertTrue(names)
            for n in names:
                self.assertEqual(n.lstrip("(«\"").upper()[0], letter, n)
        letters = [g[0] for g in groups]
        self.assertEqual(letters[0], "A")
        self.assertEqual(len(letters), len(set(letters)))

    def test_category_chips_filter(self):
        page = self.open_tab()
        chips = page.locator("#disease-cats .cat-chip")
        self.assertEqual(chips.first.inner_text(), "Hammasi")
        self.assertEqual(chips.first.get_attribute("aria-selected"), "true")
        page.click('#disease-cats [data-cat="Yurak"]')
        expected = sorted(page.evaluate("DISEASES_DATA.filter(d => d.cat === 'Yurak').map(d => d.name)"))
        self.assertEqual(sorted(self.names(page)), expected)
        self.assertEqual(page.get_attribute('#disease-cats [data-cat="Yurak"]', "aria-selected"), "true")
        self.assertEqual(chips.first.get_attribute("aria-selected"), "false")
        page.click('#disease-cats [data-cat="all"]')
        self.assertEqual(len(self.names(page)), page.evaluate("DISEASES_DATA.length"))

    def test_search_combines_with_category_and_ignores_apostrophes(self):
        page = self.open_tab()
        page.fill("#disease-search-input", "koz")                         # "Ko'z" kategoriyasi
        names = self.names(page)
        self.assertTrue(names)
        self.assertTrue(page.evaluate("""(n) => n.every(x => {
            const d = DISEASES_DATA.find(i => i.name === x); return (d.name + ' ' + d.cat).toLowerCase().replace(/['ʻʼ‘’`´]/g, '').includes('koz'); })""", names))
        page.click('#disease-cats [data-cat="Travma"]')
        self.assertTrue(all(page.evaluate("(n) => DISEASES_DATA.find(i => i.name === n).cat", n) == "Travma"
                            for n in self.names(page)))

    def test_clear_button_and_empty_state(self):
        page = self.open_tab()
        self.assertFalse(page.is_visible("#search-clear-btn"))
        page.fill("#disease-search-input", "xyzxyz")
        self.assertTrue(page.is_visible("#search-clear-btn"))
        self.assertTrue(page.is_visible("#disease-empty"))
        self.assertEqual(self.names(page), [])
        page.click("#search-clear-btn")
        self.assertFalse(page.is_visible("#disease-empty"))
        self.assertEqual(page.input_value("#disease-search-input"), "")
        self.assertEqual(len(self.names(page)), page.evaluate("DISEASES_DATA.length"))

    def test_search_stays_on_top_while_scrolling(self):
        page = self.open_tab()
        page.evaluate("document.querySelector('.app-content').scrollTop = 2500")
        page.wait_for_timeout(100)
        box = page.locator("#disease-search-input").bounding_box()
        header = page.locator(".app-header").bounding_box()
        self.assertLess(box["y"], header["y"] + header["height"] + 40)      # sticky: header ostida qoladi

    def test_rows_are_tap_size_and_open_detail(self):
        page = self.open_tab()
        self.assertGreaterEqual(page.locator(ROWS).first.bounding_box()["height"], 44)
        name = self.names(page)[0]
        page.locator(ROWS).first.click()
        page.wait_for_selector("#overlay-details.active")
        self.assertEqual(page.inner_text("#overlay-title"), name)


if __name__ == "__main__":
    unittest.main()
