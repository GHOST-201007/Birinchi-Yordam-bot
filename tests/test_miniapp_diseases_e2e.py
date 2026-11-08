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

    # ---- 10/10: indeks, chiplar, kategoriya nuqtasi, highlight, bo'sh holat, animatsiya, klaviatura -----------------
    def test_az_index_jumps_to_letter_group(self):
        page = self.open_tab()
        letters = page.evaluate("[...document.querySelectorAll('#disease-az button')].map(b => b.textContent)")
        headers = page.evaluate("[...document.querySelectorAll('#disease-list-container .letter-header')].map(h => h.textContent)")
        self.assertEqual(letters, headers)
        self.assertTrue(page.is_visible("#disease-az"))
        self.assertEqual(page.get_attribute('#disease-az [data-letter="K"]', "aria-label"), "K harfiga o'tish")
        page.click('#disease-az [data-letter="K"]')
        header = page.locator('#disease-list-container .letter-header[data-letter="K"]').bounding_box()
        tools = page.locator("#tab-diseases .sticky-tools").bounding_box()
        self.assertAlmostEqual(header["y"], tools["y"] + tools["height"], delta=12)   # sarlavha sticky panel ostida

    def test_az_index_keyboard_moves_focus_to_group(self):
        page = self.open_tab()
        page.focus('#disease-az [data-letter="S"]')
        page.keyboard.press("Enter")
        self.assertTrue(page.evaluate("""document.activeElement === document.querySelector(
            '#disease-list-container .letter-header[data-letter="S"]').nextElementSibling.querySelector('.list-row')"""))

    def test_az_index_hidden_when_search_or_chip_active(self):
        page = self.open_tab()
        page.fill("#disease-search-input", "gri")
        self.assertFalse(page.is_visible("#disease-az"))
        page.click("#search-clear-btn")
        self.assertTrue(page.is_visible("#disease-az"))
        page.click('#disease-cats [data-cat="Yurak"]')
        self.assertFalse(page.is_visible("#disease-az"))

    def test_chip_row_fade_and_active_chip_scrolls_into_view(self):
        page = self.open_tab()
        mask = page.evaluate("getComputedStyle(document.getElementById('disease-cats')).webkitMaskImage")
        self.assertIn("gradient", mask)
        page.evaluate("document.querySelector('#disease-cats .cat-chip:last-child').click()")
        page.wait_for_function("""(() => { const b = document.getElementById('disease-cats').getBoundingClientRect();
            const c = document.querySelector('#disease-cats .cat-chip:last-child').getBoundingClientRect();
            return c.left >= b.left - 1 && c.right <= b.right + 1; })()""", timeout=3000)   # silliq skroll tugaguncha
        page.wait_for_function("document.getElementById('disease-cats').classList.contains('at-end')", timeout=3000)

    def test_chips_keyboard_arrows(self):
        page = self.open_tab()
        page.focus('#disease-cats [data-cat="all"]')
        page.keyboard.press("ArrowRight")
        second = page.evaluate("document.querySelectorAll('#disease-cats .cat-chip')[1].getAttribute('data-cat')")
        self.assertEqual(page.get_attribute(f'#disease-cats [data-cat="{second}"]', "aria-selected"), "true")
        self.assertEqual(page.evaluate("document.activeElement.getAttribute('data-cat')"), second)
        self.assertEqual(page.evaluate(
            "[...document.querySelectorAll('#disease-cats .cat-chip')].filter(c => c.tabIndex === 0).length"), 1)
        page.keyboard.press("Home")
        self.assertEqual(page.get_attribute('#disease-cats [data-cat="all"]', "aria-selected"), "true")

    def test_rows_show_colored_category_dot(self):
        page = self.open_tab()
        self.assertEqual(page.evaluate("DISEASES_DATA.filter(d => !CAT_HUE[d.cat]).length"), 0)   # har kategoriyaga rang
        row = page.locator(ROWS).first
        self.assertEqual(row.locator(".row-sub .cat-dot").count(), 1)
        self.assertEqual(row.locator(".cat-dot").get_attribute("aria-hidden"), "true")
        hues = page.evaluate(
            f"new Set([...document.querySelectorAll('{ROWS} .cat-dot')].map(d => getComputedStyle(d).backgroundColor)).size")
        self.assertGreaterEqual(hues, 6)

    def test_search_highlight_count_and_flat_list(self):
        page = self.open_tab()
        page.fill("#disease-search-input", "gripp")
        marks = page.evaluate(f"[...document.querySelectorAll('{ROWS} mark')].map(m => m.textContent)")
        self.assertTrue(marks)
        self.assertTrue(all(m.lower() == "gripp" for m in marks))
        n = len(self.names(page))
        self.assertEqual(page.inner_text("#disease-count"), f"{n} ta natija")
        self.assertEqual(page.get_attribute("#disease-count", "role"), "status")
        self.assertEqual(page.locator("#disease-list-container .letter-header").count(), 0)   # filtrda harflarsiz
        page.fill("#disease-search-input", "ogrig")                         # apostroflarsiz: "og'rig'i"
        self.assertTrue(self.names(page))
        self.assertTrue(all(m.lower().replace("'", "") == "ogrig" for m in
                            page.evaluate(f"[...document.querySelectorAll('{ROWS} mark')].map(m => m.textContent)")))
        page.click("#search-clear-btn")
        self.assertFalse(page.is_visible("#disease-count"))

    def test_highlight_never_injects_html(self):
        page = self.open_tab()
        page.evaluate("""DISEASES_DATA.push({ name: '<img src=x onerror="window.__xss=1">Zzz', cat: 'Umumiy',
                                              desc: '', symptoms: [], firstAid: '' }); applyDiseaseFilter()""")
        page.fill("#disease-search-input", "zzz")
        self.assertEqual(page.locator(f"{ROWS} img").count(), 0)
        self.assertIn("<img", self.names(page)[0])
        self.assertIsNone(page.evaluate("window.__xss"))

    def test_empty_state_offers_ai(self):
        page = self.open_tab()
        page.fill("#disease-search-input", "xyzxyz")
        self.assertTrue(page.is_visible("#disease-empty .empty-icon svg"))
        self.assertEqual(page.inner_text("#disease-empty .empty-title"), "Topilmadi")
        self.assertFalse(page.is_visible("#disease-count"))
        page.click("#disease-ask-ai")
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot"])

    def test_entry_animation_respects_reduced_motion(self):
        page = self.open_tab()
        page.click('#disease-cats [data-cat="Yurak"]')
        self.assertEqual(page.evaluate(
            "getComputedStyle(document.querySelector('#disease-list-container .inset-group')).animationName"), "row-in")
        page.emulate_media(reduced_motion="reduce")
        page.click('#disease-cats [data-cat="Travma"]')
        self.assertFalse(page.evaluate(
            "document.getElementById('disease-list-container').classList.contains('animate-in')"))
        self.assertEqual(page.evaluate(
            "getComputedStyle(document.querySelector('#disease-list-container .list-row')).transitionDuration"), "0s")

    # ---- Kasalliklar (2): tartib, alomatlar bo'yicha qidiruv, sticky harflar ----------------------------------------
    def test_search_order_prefix_then_mid_word_alphabetical_inside(self):
        page = self.open_tab()
        page.fill("#disease-search-input", "gri")
        names = self.names(page)
        self.assertEqual(names[:2], ["Gribok", "Gripp"])                    # so'z boshidan — birinchi
        self.assertTrue(all("og'rig'i" in n for n in names[2:]), names)      # so'z o'rtasidan — keyin
        ranks = page.evaluate("""(q) => [...document.querySelectorAll('#disease-list-container .list-row .row-title')]
            .map(e => diseaseMatchRank(DISEASES_DATA.find(d => d.name === e.textContent), q))""", "gri")
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(page.locator(f"{ROWS} .row-match").count(), 0)      # tavsifdagi "og'riq" hisoblanmaydi
        expected = page.evaluate("""(n) => n.map(x => DISEASES_DATA.find(d => d.name === x)).sort(compareDiseaseNames).map(d => d.name)""",
                                 names[2:])
        self.assertEqual(names[2:], expected)                               # daraja ichida alifbo

    def test_symptom_search_shows_matching_fragment(self):
        page = self.open_tab()
        page.fill("#disease-search-input", "harorat")
        names = self.names(page)
        self.assertIn("Gripp", names)
        self.assertTrue(all("harorat" not in n.lower() for n in names))
        rows = page.locator(ROWS)
        for i in range(rows.count()):
            self.assertEqual(rows.nth(i).locator(".row-match mark").inner_text().lower(), "harorat")
        self.assertEqual(page.inner_text("#disease-count"), f"{len(names)} ta natija")

    def test_short_query_does_not_search_description(self):
        page = self.open_tab()
        page.fill("#disease-search-input", "yu")
        self.assertEqual(page.locator(f"{ROWS} .row-match").count(), 0)

    def test_regex_special_characters_are_safe(self):
        page = self.open_tab()
        for q in ("(((", "a+b?", "[xq", "\\\\"):
            page.fill("#disease-search-input", q)                            # sahifada xato bo'lmasligi (base tekshiradi)
            self.assertTrue(page.is_visible("#disease-empty"), q)

    def test_letter_headers_stick_under_search_panel(self):
        page = self.open_tab()
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.letter-header')).position"), "sticky")
        page.evaluate("document.querySelector('.app-content').scrollTop = 1400")
        page.wait_for_timeout(100)
        tools = page.locator("#tab-diseases .sticky-tools").bounding_box()
        tops = page.evaluate("[...document.querySelectorAll('#disease-list-container .letter-header')].map(h => h.getBoundingClientRect().top)")
        bottom = tools["y"] + tools["height"]
        self.assertTrue(any(abs(t - bottom) < 2 for t in tops), (bottom, tops[:6]))  # bitta harf panel ostida qotgan


if __name__ == "__main__":
    unittest.main()
