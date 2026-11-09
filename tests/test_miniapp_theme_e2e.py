"""
test_miniapp_theme_e2e.py — mavzu qo'lda tanlash: Avto (Telegram) / Kunduzgi / Tungi (Sog'liq tabida "Ko'rinish").
localStorage (try/catch), CloudStorage ishlatilmaydi; saqlangan mavzu birinchi chizishdan oldin (app.js boshida).
"""
import os
import unittest

from tests.e2e_base import CONTRAST_JS, MiniAppE2EBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEG = ".theme-seg"
BTN = '.theme-seg [data-theme-mode="{}"]'
DARK = "document.body.classList.contains('dark-mode')"


def scheme(name):
    return f"window.Telegram.WebApp.colorScheme = '{name}';"


def saved(value):
    return f"try {{ localStorage.setItem('theme_mode', '{value}'); }} catch (e) {{}}"


class ThemePickerE2ETest(MiniAppE2EBase):
    def open_health(self, init_script=""):
        page, _ = self.open_app({}, init_script=init_script)
        page.click('nav [data-tab="tab-health"]')
        return page

    def checked(self, page):
        return page.evaluate("[...document.querySelectorAll('.theme-seg [role=radio]')].filter(b => b.getAttribute('aria-checked') === 'true').map(b => b.dataset.themeMode)")

    def test_radiogroup_markup_and_default_auto(self):
        page = self.open_health(scheme("light"))
        self.assertEqual(page.get_attribute(SEG, "role"), "radiogroup")
        self.assertEqual(page.inner_text("#theme-row-label"), "Ko'rinish")
        labels = page.evaluate("[...document.querySelectorAll('.theme-seg [role=radio]')].map(b => b.textContent)")
        self.assertEqual(labels, ["Avto", "Kunduzgi", "Tungi"])
        self.assertEqual(self.checked(page), ["auto"])
        self.assertFalse(page.evaluate(DARK))

    def test_auto_follows_telegram_and_theme_changed(self):
        page = self.open_health(scheme("dark"))
        self.assertTrue(page.evaluate(DARK))
        page.evaluate("window.Telegram.WebApp.colorScheme = 'light'; window.__tgEvents.themeChanged();")
        self.assertFalse(page.evaluate(DARK))

    def test_manual_dark_ignores_theme_changed_and_sets_telegram_colors(self):
        page = self.open_health(scheme("light"))
        page.click(BTN.format("dark"))
        self.assertTrue(page.evaluate(DARK))
        self.assertEqual(self.checked(page), ["dark"])
        self.assertEqual(page.evaluate("localStorage.getItem('theme_mode')"), "dark")
        tg = self.tg(page)
        self.assertEqual(tg["headerColors"][-1].upper(), "#152225")             # --surface (dark)
        self.assertEqual(tg["bgColors"][-1].upper(), "#0C1517")                 # --bg (dark)
        page.evaluate("window.Telegram.WebApp.colorScheme = 'light'; window.__tgEvents.themeChanged();")
        self.assertTrue(page.evaluate(DARK))                                    # qo'lda — e'tiborsiz

    def test_manual_light_over_dark_telegram_then_back_to_auto(self):
        page = self.open_health(scheme("dark"))
        page.click(BTN.format("light"))
        self.assertFalse(page.evaluate(DARK))
        tg = self.tg(page)
        self.assertEqual(tg["headerColors"][-1].upper(), "#FFFFFF")
        self.assertEqual(tg["bgColors"][-1].upper(), "#EEF8F5")
        page.click(BTN.format("auto"))
        self.assertTrue(page.evaluate(DARK))                                    # yana Telegram (dark)
        self.assertEqual(page.evaluate("localStorage.getItem('theme_mode')"), "auto")

    def test_saved_theme_applied_before_first_paint(self):
        # DOMContentLoaded'dagi birinchi tinglovchi (init script) — app.js ning DOMContentLoaded kodidan oldin ishlaydi.
        # Mavzu shu paytdayoq qo'llangan bo'lishi kerak (miltillamaydi)
        boot = ("document.addEventListener('DOMContentLoaded', () => { window.__bootDark = "
                "document.body.classList.contains('dark-mode'); }, { once: true });")
        page = self.open_health(scheme("light") + saved("dark") + boot)
        self.assertTrue(page.evaluate("window.__bootDark"))
        self.assertEqual(self.checked(page), ["dark"])
        page2 = self.open_health(scheme("dark") + saved("light") + boot)
        self.assertFalse(page2.evaluate("window.__bootDark"))

    def test_boot_code_is_at_top_of_app_js(self):
        with open(os.path.join(ROOT, "app", "app.js"), encoding="utf-8") as f:
            head = f.read(3000)
        self.assertIn("(function bootTheme()", head)
        with open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>")             # inline script yo'q (CSP)

    def test_no_cloud_storage_for_theme(self):
        spy = ("const cs = window.Telegram.WebApp.CloudStorage; window.__cloud = []; const orig = cs.setItem;"
               "cs.setItem = (k, v, cb) => { window.__cloud.push(k); return orig(k, v, cb); };")
        page = self.open_health(scheme("light") + spy)
        page.click(BTN.format("dark"))
        self.assertNotIn("theme_mode", page.evaluate("window.__cloud"))

    def test_local_storage_errors_are_silent(self):
        broken = ("Storage.prototype.getItem = () => { throw new Error('blocked'); };"
                  "Storage.prototype.setItem = () => { throw new Error('blocked'); };")
        page = self.open_health(scheme("light") + broken)                       # sahifa xatosi bo'lmasligi shart
        self.assertEqual(self.checked(page), ["auto"])
        page.click(BTN.format("dark"))
        self.assertTrue(page.evaluate(DARK))                                    # joriy oynada ishlaydi
        self.assertEqual(self.checked(page), ["dark"])

    def test_invalid_saved_value_falls_back_to_auto(self):
        page = self.open_health(scheme("dark") + saved("purple"))
        self.assertEqual(self.checked(page), ["auto"])
        self.assertTrue(page.evaluate(DARK))

    def test_keyboard_arrows_home_end(self):
        page = self.open_health(scheme("light"))
        page.focus(BTN.format("auto"))
        page.keyboard.press("ArrowRight")
        self.assertEqual(self.checked(page), ["light"])
        self.assertEqual(page.evaluate("document.activeElement.dataset.themeMode"), "light")
        page.keyboard.press("End")
        self.assertEqual(self.checked(page), ["dark"])
        self.assertTrue(page.evaluate(DARK))
        page.keyboard.press("ArrowRight")                                        # aylanma: oxiridan boshiga
        self.assertEqual(self.checked(page), ["auto"])
        self.assertEqual(page.evaluate("[...document.querySelectorAll('.theme-seg [role=radio]')].filter(b => b.tabIndex === 0).length"), 1)

    def test_visible_main_button_recolored_on_theme_switch(self):
        # Sog'liq tabida "Hisoblash" MainButton ko'rinib turadi — mavzu almashsa uning rangi ham almashadi
        page = self.open_health(scheme("light"))
        self.assertEqual((self.tg(page)["mainVisible"], self.tg(page)["mainText"]), (True, "Hisoblash"))
        page.click(BTN.format("dark"))
        p = self.tg(page)["mainParams"]
        self.assertEqual((p["color"].upper(), p["text_color"].upper()), ("#8FA9A9", "#06211E"))   # nofaol (--text-2)
        page.evaluate("MainButtonCtl.setActive(true)")
        page.click(BTN.format("light"))
        p = self.tg(page)["mainParams"]
        self.assertEqual((p["color"].upper(), p["text_color"].upper()), ("#0E7C72", "#FFFFFF"))   # faol (--primary)
        page.evaluate("window.Telegram.WebApp.colorScheme = 'dark';")
        page.click(BTN.format("auto"))                                          # Avto -> Telegram (dark)
        p = self.tg(page)["mainParams"]
        self.assertEqual((p["color"].upper(), p["text_color"].upper()), ("#3DC2B3", "#06211E"))

    def test_contrast_both_themes(self):
        for mode in ("light", "dark"):
            with self.subTest(mode=mode):
                page = self.open_health(scheme("light") + saved(mode))
                for sel in ("#theme-row-label", BTN.format(mode), BTN.format("auto")):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)


if __name__ == "__main__":
    unittest.main()
