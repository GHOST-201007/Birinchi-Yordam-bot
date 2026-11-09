"""
test_miniapp_scrollbar_az_e2e.py — scrollbar (yupqa, mavzuga mos; faqat sichqoncha/trackpad) va Kasalliklar
A–Z alifbo paneli: pill ko'rinish, ro'yxatni yopmaydi, header / pastki nav bilan to'qnashmaydi, kichik ekranda
oraliq kichrayadi, faol harf, bosilganda silliq (reduced-motion — darhol), sudrab o'tish. Asos: tests/e2e_base.py
"""
import os
import re
import unittest

from tests.e2e_base import CONTRAST_JS, MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTN = '#disease-az [data-letter="{}"]'
HEADER_AT_TOP = """(l) => { const h = document.querySelector(`#disease-list-container .letter-header[data-letter="${l}"]`);
    const t = document.querySelector('#tab-diseases .sticky-tools');
    return Math.abs(h.getBoundingClientRect().top - t.getBoundingClientRect().bottom) <= 12; }"""
SPY = """() => { const c = document.querySelector('.app-content'); window.__scrollTo = []; const orig = c.scrollTo.bind(c);
    c.scrollTo = (o) => { window.__scrollTo.push(o && o.behavior); return orig(o); }; }"""


def box(page, sel):
    return page.evaluate(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); "
                         "return {left: r.left, top: r.top, right: r.right, bottom: r.bottom, h: r.height}; })()")


class ScrollbarStaticTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "app", "style.css"), encoding="utf-8") as f:
            self.css = f.read()

    def test_thin_theme_scrollbar_only_for_fine_pointer(self):
        m = re.search(r"@media \(hover: hover\) and \(pointer: fine\) \{(.*?)\n\}", self.css, re.S)
        self.assertIsNotNone(m, "scrollbar faqat sichqoncha/trackpad uchun (telefonda o'zgarmaydi)")
        block = re.sub(r"\s+", " ", m.group(1))
        self.assertIn("scrollbar-width: thin; scrollbar-color: var(--line-strong) transparent;", block)
        self.assertIn("::-webkit-scrollbar { width: 6px; height: 6px; }", block)
        self.assertIn("::-webkit-scrollbar-thumb { border-radius: 3px; background: var(--line-strong); }", block)
        self.assertIn("::-webkit-scrollbar-thumb:hover { background: var(--primary); }", block)
        self.assertIn("background: transparent", block)

    def test_chip_rows_hide_scrollbar(self):
        self.assertIn(".chip-scroll, .az-index { scrollbar-width: none; }", self.css)
        self.assertIn(".chip-scroll::-webkit-scrollbar, .az-index::-webkit-scrollbar { display: none; }", self.css)


class ScrollbarAzE2ETest(MiniAppE2EBase):
    def open_tab(self, size=None, scheme="light", reduced=False):
        page, _ = self.open_app({}, init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
        if size:
            page.set_viewport_size({"width": size[0], "height": size[1]})
        if reduced:
            page.emulate_media(reduced_motion="reduce")
        page.click('nav [data-tab="tab-diseases"]')
        page.wait_for_selector("#disease-az:not([hidden])")
        page.wait_for_function("document.getElementById('tab-diseases').getAnimations().length === 0")
        return page

    def test_scrollbar_rules_parsed_by_browser(self):
        page, _ = self.open_app({})
        found = page.evaluate("""[...document.styleSheets].some(s => { try { return [...s.cssRules].some(r =>
            r.media && r.media.mediaText.includes('pointer: fine') && r.cssText.includes('::-webkit-scrollbar-thumb:hover')); }
            catch (e) { return false; } })""")
        self.assertTrue(found)

    def test_panel_pill_look_in_both_themes(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page = self.open_tab(scheme=scheme)
                s = page.evaluate("""(() => { const n = getComputedStyle(document.getElementById('disease-az'));
                    const b = getComputedStyle(document.querySelector('#disease-az button'));
                    return [n.borderTopWidth, n.borderTopStyle, parseFloat(n.borderTopLeftRadius) >= 14, n.backgroundColor,
                            b.fontSize, b.fontWeight]; })()""")
                self.assertEqual(s[:3], ["1px", "solid", True])
                self.assertRegex(s[3], r"0\.8\d?\)$")                                   # shaffof --surface
                self.assertEqual(s[4:], ["11px", "800"])
                self.assertEqual(page.get_attribute("#disease-az", "aria-label"), "Alifbo bo'yicha o'tish")
                self.assertEqual(page.get_attribute(BTN.format("A"), "aria-label"), "A harfiga o'tish")
                for sel in (BTN.format("B"), "#disease-az .is-active"):                 # oddiy va faol harf
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
                active = page.evaluate("getComputedStyle(document.querySelector('#disease-az .is-active')).backgroundColor")
                self.assertEqual(active, "rgb(14, 124, 114)" if scheme == "light" else "rgb(61, 194, 179)")   # --primary

    def test_only_letters_present_in_list(self):
        page = self.open_tab()
        letters = page.evaluate("[...document.querySelectorAll('#disease-az button')].map(b => b.dataset.letter)")
        headers = page.evaluate("[...document.querySelectorAll('#disease-list-container .letter-header')].map(h => h.dataset.letter)")
        self.assertEqual(letters, headers)
        self.assertNotIn("F", letters)                                                  # ro'yxatda F yo'q — panelda ham yo'q

    def test_panel_does_not_cover_list_header_or_nav(self):
        for size in ((360, 740), (390, 844), (430, 932), (360, 568)):
            with self.subTest(size=size):
                page = self.open_tab(size)
                az, tools, nav = box(page, "#disease-az"), box(page, "#tab-diseases .sticky-tools"), box(page, ".app-nav")
                row = box(page, "#disease-list-container .list-row")
                self.assertGreaterEqual(az["top"], tools["bottom"])                    # qidiruv paneli / header ostida
                self.assertLessEqual(az["bottom"], nav["top"] - 4)                      # pastki nav ustida
                self.assertLessEqual(row["right"], az["left"] - 2)                      # ro'yxat panel ostida qolmaydi
                self.assertLessEqual(az["right"], size[0])
                heights = page.evaluate("[...document.querySelectorAll('#disease-az button')].map(b => Math.round(b.getBoundingClientRect().height))")
                self.assertEqual(len(set(heights)), 1)                                  # oraliq teng
                last = page.evaluate("document.querySelector('#disease-az button:last-child').getBoundingClientRect().bottom")
                self.assertLessEqual(last, az["bottom"])                                # hamma harf sig'adi
                if size[1] < 600:
                    self.assertLess(heights[0], 18)                                     # kichik ekranda oraliq kichraydi

    def test_active_letter_follows_scroll(self):
        page = self.open_tab()
        self.assertEqual(page.get_attribute(BTN.format("A"), "aria-current"), "true")
        page.evaluate("""() => { const c = document.querySelector('.app-content');
            const h = document.querySelector('#disease-list-container .letter-header[data-letter="K"]');
            const t = document.querySelector('#tab-diseases .sticky-tools');            // skrollda panel tepaga yopishadi
            c.scrollTop += h.getBoundingClientRect().top - (c.getBoundingClientRect().top + t.offsetHeight) + 20; }""")
        page.wait_for_function("document.querySelector('#disease-az .is-active').dataset.letter === 'K'")
        self.assertEqual(page.evaluate("[...document.querySelectorAll('#disease-az [aria-current]')].map(b => b.dataset.letter)"), ["K"])

    def test_tap_scrolls_smoothly(self):
        page = self.open_tab()
        page.evaluate(SPY)
        page.click(BTN.format("M"))
        self.assertEqual(page.evaluate("window.__scrollTo"), ["smooth"])
        self.assertEqual(page.get_attribute(BTN.format("M"), "aria-current"), "true")
        page.wait_for_function(HEADER_AT_TOP, arg="M")
        self.assertEqual(page.get_attribute(BTN.format("M"), "aria-current"), "true")   # o'tish davomida o'zgarmadi

    def test_tap_with_reduced_motion_is_instant(self):
        page = self.open_tab(reduced=True)
        page.evaluate(SPY)
        page.click(BTN.format("S"))
        self.assertTrue(page.evaluate(HEADER_AT_TOP, "S"))                               # darhol
        self.assertNotIn("smooth", page.evaluate("window.__scrollTo"))

    def test_drag_scrub_jumps_letter_by_letter(self):
        page = self.open_tab()
        page.evaluate(SPY)
        a, g = box(page, BTN.format("A")), box(page, BTN.format("G"))
        page.mouse.move((a["left"] + a["right"]) / 2, (a["top"] + a["bottom"]) / 2)
        page.mouse.down()
        page.mouse.move((g["left"] + g["right"]) / 2, (g["top"] + g["bottom"]) / 2, steps=8)
        self.assertTrue(page.evaluate(HEADER_AT_TOP, "G"))                               # sudrashda darhol
        self.assertEqual(page.get_attribute(BTN.format("G"), "aria-current"), "true")
        page.mouse.up()
        self.assertNotIn("smooth", page.evaluate("window.__scrollTo"))                  # qo'yib yuborganda qayta o'tmaydi

    def test_last_letter_stays_active_at_list_end(self):
        page = self.open_tab(reduced=True)
        last = page.evaluate("document.querySelector('#disease-az button:last-child').dataset.letter")
        page.click(BTN.format(last))
        page.wait_for_timeout(150)
        self.assertEqual(page.evaluate("document.querySelector('#disease-az .is-active').dataset.letter"), last)


if __name__ == "__main__":
    unittest.main()
