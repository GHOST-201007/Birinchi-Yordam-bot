"""
test_miniapp_nav_e2e.py — redesign 4.4-A (header) va 4.4-L (4 tabli navigatsiya), tg.BackButton, Telegram mavzusi.
Asos: tests/e2e_base.py
"""
import unittest

from tests.e2e_base import STATE_OK, MiniAppE2EBase

NAV = [("tab-first-aid", "Yordam"), ("tab-diseases", "Kasalliklar"), ("tab-health", "Sog'liq"), ("tab-ai", "AI")]


class NavE2ETest(MiniAppE2EBase):
    def active_section(self, page):
        return page.evaluate("document.querySelector('.tab-content.active').id")

    def active_nav(self, page):
        return page.evaluate("[...document.querySelectorAll('.nav-btn.active')].map(b => b.dataset.tab)")

    def test_four_tabs_with_labels_and_current_marker(self):
        page, _ = self.open_app({})
        buttons = page.evaluate("[...document.querySelectorAll('nav .nav-btn')].map(b => [b.dataset.tab, b.innerText.trim()])")
        self.assertEqual(buttons, [list(x) for x in NAV])
        for tab, _label in NAV:
            page.click(f'nav [data-tab="{tab}"]')
            self.assertEqual(self.active_section(page), tab)
            self.assertEqual(self.active_nav(page), [tab])
            self.assertEqual(page.get_attribute(f'nav [data-tab="{tab}"]', "aria-current"), "page")

    def test_nav_buttons_are_tap_size(self):
        page, _ = self.open_app({})
        for tab, _ in NAV:
            box = page.locator(f'nav [data-tab="{tab}"]').bounding_box()
            self.assertGreaterEqual(box["height"], 44)
            self.assertGreaterEqual(box["width"], 44)

    def test_history_is_inside_health_via_segmented_control(self):
        page, _ = self.open_app({})
        page.click('nav [data-tab="tab-health"]')
        page.click('#tab-health [data-show-tab="tab-history"]')
        self.assertEqual(self.active_section(page), "tab-history")
        self.assertEqual(self.active_nav(page), ["tab-health"])            # nav'da Sog'liq faol qoladi
        self.assertEqual(page.get_attribute('#tab-history [data-show-tab="tab-history"]', "aria-selected"), "true")
        page.click('#tab-history [data-show-tab="tab-health"]')
        self.assertEqual(self.active_section(page), "tab-health")

    def test_quiz_section_still_reachable_and_maps_to_home(self):
        page, _ = self.open_app({})
        page.evaluate("showTab('tab-quiz')")
        self.assertEqual(self.active_section(page), "tab-quiz")
        self.assertEqual(self.active_nav(page), ["tab-first-aid"])

    # ---- Header ---------------------------------------------------------------------------
    def test_header_shows_name_score_and_103(self):
        page, _ = self.open_app({"state": (200, STATE_OK)})
        page.wait_for_function("document.querySelector('#global-score-val').textContent === '7'")
        self.assertEqual(page.inner_text("#user-name"), "Ali")
        self.assertTrue(page.is_visible("#global-score"))
        self.assertEqual(page.get_attribute(".emergency-btn", "href"), "tel:103")
        self.assertIn("103", page.inner_text(".emergency-btn"))
        self.assertEqual(page.locator("#theme-toggle-btn").count(), 0)     # mavzu Telegram'ga ergashadi
        self.assertFalse(page.is_visible("#hdr-premium"))

    def test_header_premium_badge_from_state(self):
        for tier, name in (("pro", "Premium Pro"), ("plus", "Premium Plus"), ("ultra", "Premium Ultra")):
            with self.subTest(tier=tier):
                page, _ = self.open_app({"state": (200, {**STATE_OK, "is_premium": True, "premium_type": tier})})
                page.wait_for_selector("#hdr-premium:not([hidden])")
                self.assertEqual(page.inner_text("#hdr-premium-name"), name)

    def test_header_without_api_hides_score_and_premium(self):
        page, _ = self.open_app({}, init_data="")
        self.assertFalse(page.is_visible("#global-score"))
        self.assertFalse(page.is_visible("#hdr-premium"))

    # ---- tg.BackButton --------------------------------------------------------------------
    def test_telegram_back_button_follows_navigation_stack(self):
        page, _ = self.open_app({"state": (200, STATE_OK)})
        self.assertFalse(self.tg(page)["backVisible"])
        self.assertFalse(page.is_visible("#header-back-btn"))              # Telegram ichida o'z tugmamiz yo'q
        self.open_wheel(page)
        self.assertTrue(self.tg(page)["backVisible"])
        self.assertFalse(page.is_visible("#header-back-btn"))
        page.evaluate("window.__backCb()")                                  # Telegram "Orqaga"
        page.clock.fast_forward(400)                                        # 300 ms debounce
        page.wait_for_function("document.querySelector('#wheel-modal').style.display === 'none'")
        self.assertFalse(self.tg(page)["backVisible"])

    def test_browser_fallback_back_button_without_telegram_back_button(self):
        # Brauzerda (tg.BackButton yo'q) navigatsiya stekiga mos ravishda o'z tugmamiz ko'rinadi/yashirinadi.
        # (To'liq ekranli oynalar uni yopib turadi — ularning o'z "Yopish" tugmasi bor.)
        page, _ = self.open_app({"state": (200, STATE_OK)}, init_script="delete window.Telegram.WebApp.BackButton;")
        self.assertFalse(page.is_visible("#header-back-btn"))
        self.open_wheel(page)
        self.assertFalse(page.evaluate("document.getElementById('header-back-btn').classList.contains('hidden')"))
        page.click("#wheel-modal-close")
        page.wait_for_function("document.querySelector('#wheel-modal').style.display === 'none'")
        self.assertTrue(page.evaluate("document.getElementById('header-back-btn').classList.contains('hidden')"))
        page.evaluate("AppNavigation.push({type: 't', close: () => AppNavigation.pop()})")
        self.assertTrue(page.is_visible("#header-back-btn"))
        page.click("#header-back-btn")
        self.assertFalse(page.is_visible("#header-back-btn"))

    # ---- Mavzu --------------------------------------------------------------------------
    def test_follows_telegram_color_scheme_and_theme_changed(self):
        page, _ = self.open_app({}, init_script="window.Telegram.WebApp.colorScheme = 'dark';")
        self.assertTrue(page.evaluate("document.body.classList.contains('dark-mode')"))
        page.evaluate("window.Telegram.WebApp.colorScheme = 'light'; window.__tgEvents.themeChanged();")
        self.assertFalse(page.evaluate("document.body.classList.contains('dark-mode')"))
        self.assertTrue(page.evaluate("document.body.classList.contains('tg-light')"))

    def test_old_saved_theme_preference_is_ignored(self):
        page, _ = self.open_app({}, init_script="try { localStorage.setItem('theme', 'dark'); } catch (e) {}")
        self.assertFalse(page.evaluate("document.body.classList.contains('dark-mode')"))

    def test_telegram_header_and_background_colors_follow_tokens(self):
        page, _ = self.open_app({})
        tg = self.tg(page)
        self.assertEqual(tg["headerColors"][-1].upper(), "#FFFFFF")         # --surface
        self.assertEqual(tg["bgColors"][-1].upper(), "#EEF8F5")             # --bg
        page.evaluate("window.Telegram.WebApp.colorScheme = 'dark'; window.__tgEvents.themeChanged();")
        tg = self.tg(page)
        self.assertEqual(tg["headerColors"][-1].upper(), "#152225")
        self.assertEqual(tg["bgColors"][-1].upper(), "#0C1517")


if __name__ == "__main__":
    unittest.main()
