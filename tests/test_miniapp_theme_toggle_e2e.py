"""
test_miniapp_theme_toggle_e2e.py — headerdagi rejim tugmasi (ism yonida): Avto -> Kunduzgi -> Tungi -> Avto.
Mavjud mavzu mantig'i (localStorage, tg.colorScheme, themeChanged, MainButton ranglari) o'zgarmagan — tugma
setThemePref() ni chaqiradi. Sog'liq tabidagi "Ko'rinish" bilan ikki tomonlama sinxron. Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import STATE_OK, MiniAppE2EBase

STATE = {**STATE_OK, "score": 120, "is_premium": True, "premium_type": "plus"}
TOGGLE = "#theme-toggle"
SPY_HAPTIC = ("window.__sel = 0; const hf = window.Telegram.WebApp.HapticFeedback;"
              "hf.selectionChanged = () => { window.__sel++; };")


def scheme(name):
    return f"window.Telegram.WebApp.colorScheme = '{name}';"


class ThemeToggleE2ETest(MiniAppE2EBase):
    def open(self, init_script="", state=STATE):
        page, _ = self.open_app({"state": (200, state)}, init_script=scheme("light") + init_script)
        page.wait_for_selector("#global-score:not([hidden])")
        return page

    def toggle_state(self, page):
        return page.evaluate("""(() => { const b = document.getElementById('theme-toggle');
            return [b.getAttribute('aria-label'), b.querySelector('use').getAttribute('href'),
                    (() => { try { return localStorage.getItem('theme_mode'); } catch (e) { return null; } })(),
                    document.body.classList.contains('dark-mode')]; })()""")

    def test_button_in_header_between_name_and_103(self):
        page = self.open()
        self.assertEqual(page.locator(TOGGLE).count(), 1)
        order = page.evaluate("[...document.querySelector('.app-header').children].filter(e => !e.classList.contains('hidden'))"
                              ".map(e => e.id || e.className)")
        self.assertEqual(order[-3:], ["user-info-container", "theme-toggle", "emergency-btn"])
        s = page.evaluate("""(() => { const c = getComputedStyle(document.getElementById('theme-toggle'));
            return [c.width, c.height, c.borderTopWidth, c.borderTopStyle, c.borderTopLeftRadius, c.backgroundColor]; })()""")
        self.assertEqual(s, ["40px", "40px", "1px", "solid", "50%", "rgb(255, 255, 255)"])          # --surface
        self.assertEqual(self.toggle_state(page)[:2], ["Rejim: Avto. Almashtirish uchun bosing", "#i-monitor"])
        self.assertEqual(page.get_attribute(TOGGLE, "type"), "button")
        self.assertEqual(page.evaluate("document.querySelectorAll('#i-monitor, #i-sun, #i-moon').length"), 3)

    def test_three_clicks_cycle_auto_light_dark_auto(self):
        page = self.open(SPY_HAPTIC)
        page.click(TOGGLE)
        self.assertEqual(self.toggle_state(page), ["Rejim: Kunduzgi. Almashtirish uchun bosing", "#i-sun", "light", False])
        self.assertEqual(page.inner_text("#toast"), "Rejim: Kunduzgi")
        self.assertEqual((page.get_attribute("#toast", "role"), page.get_attribute("#toast", "aria-live")), ("status", "polite"))
        page.click(TOGGLE)
        self.assertEqual(self.toggle_state(page), ["Rejim: Tungi. Almashtirish uchun bosing", "#i-moon", "dark", True])
        self.assertEqual(page.inner_text("#toast"), "Rejim: Tungi")
        self.assertEqual(self.tg(page)["headerColors"][-1].upper(), "#152225")                      # --surface (dark)
        page.evaluate(scheme("dark"))
        page.click(TOGGLE)
        self.assertEqual(self.toggle_state(page), ["Rejim: Avto. Almashtirish uchun bosing", "#i-monitor", "auto", True])
        self.assertEqual(page.inner_text("#toast"), "Rejim: Avto")
        self.assertEqual(page.evaluate("window.__sel"), 3)                                         # har bosishda haptic

    def test_auto_still_follows_telegram_theme_changed(self):
        page = self.open()
        page.click(TOGGLE)                                                                         # Kunduzgi (qo'lda)
        page.evaluate(scheme("dark") + "window.__tgEvents.themeChanged();")
        self.assertFalse(page.evaluate("document.body.classList.contains('dark-mode')"))           # qo'lda — e'tiborsiz
        page.click(TOGGLE)
        page.click(TOGGLE)                                                                         # Avto
        page.evaluate(scheme("light") + "window.__tgEvents.themeChanged();")
        self.assertFalse(page.evaluate("document.body.classList.contains('dark-mode')"))
        page.evaluate(scheme("dark") + "window.__tgEvents.themeChanged();")
        self.assertTrue(page.evaluate("document.body.classList.contains('dark-mode')"))

    def test_synced_with_health_picker_both_ways(self):
        page = self.open()
        page.click(TOGGLE)                                                                         # header -> Kunduzgi
        page.click('nav [data-tab="tab-health"]')
        checked = "[...document.querySelectorAll('.theme-seg [role=radio]')].filter(b => b.getAttribute('aria-checked') === 'true').map(b => b.dataset.themeMode)"
        self.assertEqual(page.evaluate(checked), ["light"])
        page.click('.theme-seg [data-theme-mode="dark"]')                                         # Sog'liq -> Tungi
        self.assertEqual(self.toggle_state(page)[:3], ["Rejim: Tungi. Almashtirish uchun bosing", "#i-moon", "dark"])

    def test_saved_mode_shown_on_load(self):
        page = self.open("try { localStorage.setItem('theme_mode', 'dark'); } catch (e) {}")
        self.assertEqual(self.toggle_state(page)[:2], ["Rejim: Tungi. Almashtirish uchun bosing", "#i-moon"])

    def test_hit_area_44(self):
        page = self.open()
        ok = page.evaluate("""(() => { const b = document.getElementById('theme-toggle'); const r = b.getBoundingClientRect();
            const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
            return [[0, -21.5], [0, 21.5], [-21.5, 0], [21.5, 0]].every(([dx, dy]) => {
                const h = document.elementFromPoint(cx + dx, cy + dy); return h === b || b.contains(h); }); })()""")
        self.assertTrue(ok)

    def test_fits_narrow_and_wide_with_long_name(self):
        long_name = ("const u = window.Telegram.WebApp.initDataUnsafe.user;"
                     "u.first_name = 'Abdurahmonbek'; u.last_name = 'Muhammadaminov-Xudoyberdiyev';")
        for width in (360, 430):
            with self.subTest(width=width):
                page = self.open(long_name)
                page.set_viewport_size({"width": width, "height": 740})
                b = page.evaluate("""(() => { const r = s => document.querySelector(s).getBoundingClientRect();
                    const n = document.getElementById('user-name');
                    return { info: r('#user-info-container').right, meta: r('.hdr-meta').right, tl: r('#theme-toggle').left,
                             tr: r('#theme-toggle').right, tw: r('#theme-toggle').width, el: r('.emergency-btn').left,
                             er: r('.emergency-btn').right, ew: r('.emergency-btn').width,
                             ellipsis: n.scrollWidth > n.clientWidth, overflow: document.documentElement.scrollWidth }; })()""")
                self.assertLessEqual(b["info"], b["tl"])                                           # ism tugmaga kirmaydi
                self.assertLessEqual(b["meta"], b["tl"])
                self.assertLessEqual(b["tr"], b["el"])                                             # 103 bilan to'qnashmaydi
                self.assertLessEqual(b["er"], width)
                self.assertEqual((b["tw"], b["ew"]), (40, 48))                                     # tugmalar siqilmaydi
                self.assertTrue(b["ellipsis"])                                                     # uzun ism qisqaradi
                self.assertLessEqual(b["overflow"], width)

    def test_no_duplicates_on_other_tabs(self):
        page = self.open()
        visible = """(sel) => [...document.querySelectorAll(sel)].filter(e => e.getClientRects().length
                        && getComputedStyle(e).visibility !== 'hidden').length"""
        for tab in ("tab-first-aid", "tab-diseases", "tab-health", "tab-ai"):
            with self.subTest(tab=tab):
                page.click(f'nav [data-tab="{tab}"]')
                self.assertEqual(page.evaluate(visible, ".theme-toggle, [aria-label^='Rejim:']"), 1)
                self.assertEqual(page.evaluate(visible, "a[href='tel:103']"), 1)
                self.assertTrue(page.evaluate("document.getElementById('theme-toggle').closest('.app-header') !== null"))

    def test_reduced_motion_no_animation(self):
        page = self.open()
        page.emulate_media(reduced_motion="reduce")
        page.click(TOGGLE)
        dur = page.evaluate("""[document.getElementById('theme-toggle'), document.getElementById('toast')]
            .map(e => parseFloat(getComputedStyle(e).animationDuration) + parseFloat(getComputedStyle(e).transitionDuration))""")
        self.assertEqual(dur, [0, 0])


if __name__ == "__main__":
    unittest.main()
