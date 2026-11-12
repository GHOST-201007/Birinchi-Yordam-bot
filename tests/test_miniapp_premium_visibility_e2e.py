"""
test_miniapp_premium_visibility_e2e.py — Premium ko'rinib turishi (Mini App, brauzerda / Playwright):
  A1 header belgisi (tarif rangi, "Ultra · 5 kun" / "♾" / "bugun"),
  A2 "Mening Premiumim" kartasi (Sog'liq tabi, qolgan kunlar chizig'i, AI limit, Uzaytirish),
  A3 tugash banneri (2 kun yoki kam; yopilishi shu premium_expires_at uchun saqlanadi),
  A4 tarif rangidagi aksent (body.tier-*, faqat --primary/--on-primary/--primary-soft; MainButton ham).
Bepul foydalanuvchida hech biri ko'rinmaydi. Asos: tests/e2e_base.py
"""
import datetime as dt
import math
import os
import re
import unittest

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase, sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UZ = dt.timezone(dt.timedelta(hours=5))
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")

# Tarif tokenlari (style.css: :root va body.dark-mode). Har juftlik kontrasti >= 4.5:1
TOKENS = {
    "pro": {"light": ("#00717F", "#FFFFFF", "#D3EEF2"), "dark": ("#4DD0E1", "#04232A", "#123A40"),
            "icon": "#i-star", "name": "Pro"},
    "plus": {"light": ("#6A3DB8", "#FFFFFF", "#E7DDF7"), "dark": ("#B79CFF", "#170C3A", "#2B2352"),
             "icon": "#i-gem", "name": "Plus"},
    "ultra": {"light": ("#8A5A00", "#FFFFFF", "#FBECC9"), "dark": ("#F5B544", "#231600", "#3B2C10"),
              "icon": "#i-crown", "name": "Ultra"},
}
DEFAULT_PRIMARY = {"light": "#0E7C72", "dark": "#3DC2B3"}
SURFACE = {"light": "#FFFFFF", "dark": "#152225"}
BG = {"light": "#EEF8F5", "dark": "#0C1517"}
TEXT = {"light": "#0F2A2E", "dark": "#E6F2F0"}
EXPIRES_FIXED = "2026-12-15T18:00:00+05:00"


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return "rgb({}, {}, {})".format(*(int(h[i:i + 2], 16) for i in (0, 2, 4)))


def lum(hex_color):
    c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def state(tier=None, days=None, hours=None, unlimited=False, ai=(12, 30, 0), expires=None, **extra):
    """/api/state javobi. Argumentsiz — bepul foydalanuvchi."""
    if tier is None:
        return {**STATE_OK, "is_premium": False, "premium_type": "free", "premium_expires_at": None,
                "premium_unlimited": False, "premium_days_left": None, "ai_remaining": 1, "ai_limit": 1,
                "ai_bonus": 0, **extra}
    if unlimited:
        expires_iso, left = None, None
    else:
        delta = dt.timedelta(days=days) if days is not None else dt.timedelta(hours=hours)
        expires_iso = expires or (dt.datetime.now(UZ) + delta).isoformat(timespec="seconds")
        left = math.ceil(delta / dt.timedelta(days=1))
    remaining, limit, bonus = ai
    return {**STATE_OK, "is_premium": True, "premium_type": tier, "premium_expires_at": expires_iso,
            "premium_unlimited": unlimited, "premium_days_left": left, "ai_remaining": remaining,
            "ai_limit": limit, "ai_bonus": bonus, **extra}


def assert_tap_target(test, box, label=""):
    """>= 44 x 44 px (sub-piksel yaxlitlashga 0.1 px bag'ishlanadi)."""
    test.assertGreaterEqual(box["height"], 43.9, label)
    test.assertGreaterEqual(box["width"], 43.9, label)


def scheme_script(scheme):
    return f"window.Telegram.WebApp.colorScheme = '{scheme}';"


class PremiumE2EBase(MiniAppE2EBase):
    def open_state(self, st, scheme="light", init_script="", **kw):
        page, calls = self.open_app({"state": (200, st)}, init_script=scheme_script(scheme) + init_script, **kw)
        page.wait_for_selector("#global-score:not([hidden])")
        return page, calls

    def open_health(self, st, **kw):
        page, calls = self.open_state(st, **kw)
        page.click('nav [data-tab="tab-health"]')
        page.wait_for_selector("#tab-health.active")
        return page, calls

    def patch(self, page, **fields):
        page.evaluate("(p) => patchAppState(p)", fields)

    def body_classes(self, page):
        return page.evaluate("[...document.body.classList].filter(c => c.startsWith('tier-'))")

    def var(self, page, name):
        return page.evaluate("(n) => getComputedStyle(document.body).getPropertyValue(n).trim()", name)


# ───────────────────────────── CSS (brauzersiz) ─────────────────────────────
class PremiumCssStaticTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "app", "style.css"), encoding="utf-8") as f:
            self.css = f.read()

    def block(self, start_re):
        m = re.search(start_re, self.css, re.M)
        return self.css[m.start(): self.css.index("\n}", m.start())]

    def test_tier_tokens_match_the_documented_palette_in_both_themes(self):
        for theme, start in (("light", r"^:root\s*\{"), ("dark", r"^body\.dark-mode\s*\{")):
            block = self.block(start)
            for tier, t in TOKENS.items():
                primary, on, soft = t[theme]
                m = re.search(rf"--tier-{tier}:\s*(#[0-9A-Fa-f]{{6}});\s*--tier-{tier}-on:\s*(#[0-9A-Fa-f]{{6}});\s*"
                              rf"--tier-{tier}-soft:\s*(#[0-9A-Fa-f]{{6}});", block)
                self.assertIsNotNone(m, (theme, tier))
                self.assertEqual(tuple(x.upper() for x in m.groups()), (primary, on, soft))

    def test_every_pair_has_contrast_at_least_4_5_in_light_and_dark(self):
        for theme in ("light", "dark"):
            for tier, t in TOKENS.items():
                primary, on, soft = t[theme]
                pairs = {"primary/surface": (primary, SURFACE[theme]), "primary/bg": (primary, BG[theme]),
                         "on/primary": (on, primary), "primary/soft": (primary, soft), "text/soft": (TEXT[theme], soft)}
                for name, (a, b) in pairs.items():
                    self.assertGreaterEqual(ratio(a, b), 4.5, (theme, tier, name, a, b))

    def test_tier_classes_only_change_the_accent_and_come_after_dark_mode(self):
        for tier in TOKENS:
            m = re.search(rf"^body\.tier-{tier}\s*\{{([^}}]*)\}}", self.css, re.M)
            self.assertIsNotNone(m, tier)
            props = sorted(p.split(":")[0].strip() for p in m.group(1).split(";") if p.strip())
            self.assertEqual(props, ["--on-primary", "--primary", "--primary-soft"])    # fon/matn ranglari o'zgarmaydi
            self.assertGreater(m.start(), re.search(r"^body\.dark-mode\s*\{", self.css, re.M).start())

    def test_progress_bar_respects_reduced_motion(self):
        m = re.search(r"@media \(prefers-reduced-motion: reduce\) \{\s*\.mp-bar-fill \{ transition: none; \}", self.css)
        self.assertIsNotNone(m)


# ───────────────────────────── A1: header ─────────────────────────────
class HeaderBadgeE2ETest(PremiumE2EBase):
    def test_badge_text_icon_and_color_per_tier(self):
        for tier, t in TOKENS.items():
            with self.subTest(tier=tier):
                page, _ = self.open_state(state(tier, days=5))
                page.wait_for_selector("#hdr-premium:not([hidden])")
                self.assertEqual(page.inner_text("#hdr-premium-name"), f"{t['name']} · 5 kun")
                self.assertIn(f"hdr-premium--{tier}", page.get_attribute("#hdr-premium", "class"))
                self.assertEqual(page.get_attribute("#hdr-premium use", "href"), t["icon"])       # sprite ikonka
                primary, _on, soft = t["light"]
                colors = page.evaluate("""() => { const cs = getComputedStyle(document.getElementById('hdr-premium'));
                                                  return [cs.color, cs.backgroundColor]; }""")
                self.assertEqual(colors, [rgb(primary), rgb(soft)])

    def test_texts_for_unlimited_last_day_and_unknown_term(self):
        cases = [
            (state("ultra", unlimited=True), "Ultra · ♾"),
            (state("ultra", hours=3), "Ultra · bugun"),
            (state("ultra", hours=25), "Ultra · 2 kun"),
            (state("plus", days=1), "Plus · bugun"),                                      # 1 kun = 24 soatdan oshmagan
            ({**STATE_OK, "is_premium": True, "premium_type": "ultra"}, "Ultra"),         # eski server: muddat maydonlari yo'q
        ]
        for st, expected in cases:
            with self.subTest(expected=expected):
                page, _ = self.open_state(st)
                page.wait_for_selector("#hdr-premium:not([hidden])")
                self.assertEqual(page.inner_text("#hdr-premium-name"), expected)

    def test_contrast_and_tokens_in_light_and_dark(self):
        for scheme in ("light", "dark"):
            for tier, t in TOKENS.items():
                with self.subTest(scheme=scheme, tier=tier):
                    page, _ = self.open_state(state(tier, days=5), scheme=scheme)
                    page.wait_for_selector("#hdr-premium:not([hidden])")
                    primary, _on, soft = t[scheme]
                    colors = page.evaluate("""() => { const cs = getComputedStyle(document.getElementById('hdr-premium'));
                                                      return [cs.color, cs.backgroundColor]; }""")
                    self.assertEqual(colors, [rgb(primary), rgb(soft)])
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#hdr-premium"), 4.5)

    def test_no_emoji_in_badge_only_the_infinity_sign(self):
        page, _ = self.open_state(state("ultra", unlimited=True))
        page.wait_for_selector("#hdr-premium:not([hidden])")
        self.assertIsNone(EMOJI.search(page.inner_text("#hdr-premium").replace("♾", "")))

    def test_free_user_sees_no_badge(self):
        page, _ = self.open_state(state())
        self.assertFalse(page.is_visible("#hdr-premium"))
        self.assertEqual(page.evaluate("document.getElementById('hdr-premium').hidden"), True)


# ───────────────────────────── A2: "Mening Premiumim" kartasi ─────────────────────────────
class MyPremiumCardE2ETest(PremiumE2EBase):
    def test_card_content_for_dated_premium(self):
        st = state("ultra", days=12, ai=(14, 30, 2))
        page, _ = self.open_health(st)
        self.assertTrue(page.is_visible("#my-premium"))
        self.assertEqual(page.evaluate("document.getElementById('tab-health').firstElementChild.id"), "my-premium")   # eng tepada
        self.assertIn("Mening Premiumim", page.inner_text("#my-premium"))
        self.assertEqual(page.inner_text("#mp-tier"), "Premium Ultra")
        y, m, d = st["premium_expires_at"][:10].split("-")
        self.assertEqual(page.inner_text("#mp-until"), f"{d}.{m}.{y}")
        self.assertEqual(page.get_attribute("#my-premium .mp-badge use", "href"), "#i-crown")
        bar = page.locator("#mp-bar")
        self.assertEqual(bar.get_attribute("role"), "progressbar")
        self.assertEqual((bar.get_attribute("aria-valuemin"), bar.get_attribute("aria-valuemax"),
                          bar.get_attribute("aria-valuenow")), ("0", "30", "12"))
        self.assertEqual(page.evaluate("document.getElementById('mp-bar').style.getPropertyValue('--mp-pct')"), "40")
        self.assertEqual(page.inner_text("#mp-left"), "12 kun qoldi")
        self.assertEqual(page.inner_text("#mp-ai"), "Bugungi AI limit: 12/30 + 2 bonus")             # 14 - 2 bonus = 12
        self.assertTrue(page.is_visible("#mp-extend"))
        self.assertEqual(page.inner_text("#mp-extend"), "Uzaytirish")
        self.assertFalse(page.is_visible("#btn-open-premium"))                                          # sotuv qatori o'rniga

    def test_bar_full_length_rules(self):
        page, _ = self.open_health(state("plus", days=12))
        cases = [(1, "7"), (5, "7"), (7, "7"), (8, "30"), (12, "30"), (30, "30"), (31, "90"), (60, "90"), (90, "90"),
                 (120, "90")]
        for days, full in cases:
            with self.subTest(days=days):
                self.patch(page, premium_days_left=days, premium_unlimited=False,
                           premium_expires_at=(dt.datetime.now(UZ) + dt.timedelta(days=days)).isoformat(timespec="seconds"))
                bar = page.locator("#mp-bar")
                self.assertEqual(bar.get_attribute("aria-valuemax"), full)
                self.assertEqual(bar.get_attribute("aria-valuenow"), str(min(days, int(full))))
                self.assertEqual(page.inner_text("#mp-left"), "Bugun tugaydi" if days == 1 else f"{days} kun qoldi")

    def test_unlimited_has_no_bar_and_no_extend_button(self):
        page, _ = self.open_health(state("pro", unlimited=True))
        self.assertTrue(page.is_visible("#my-premium"))
        self.assertEqual(page.inner_text("#mp-until"), "Muddatsiz")
        self.assertEqual(page.inner_text("#mp-left"), "Muddatsiz")
        self.assertFalse(page.is_visible("#mp-bar"))
        self.assertFalse(page.is_visible("#mp-extend"))
        self.assertEqual(page.inner_text("#mp-tier"), "Premium Pro")

    def test_last_day(self):
        page, _ = self.open_health(state("ultra", hours=3))
        self.assertEqual(page.inner_text("#mp-left"), "Bugun tugaydi")
        bar = page.locator("#mp-bar")
        self.assertEqual((bar.get_attribute("aria-valuenow"), bar.get_attribute("aria-valuemax")), ("1", "7"))
        self.assertTrue(page.is_visible("#mp-extend"))

    def test_extend_button_opens_the_existing_premium_modal(self):
        page, _ = self.open_health(state("plus", days=4))
        page.click("#mp-extend")
        page.wait_for_selector("#premium-modal:not(.hidden)")
        self.assertTrue(page.is_visible("#premium-modal"))

    def test_ai_line_without_bonus_and_without_quota_fields(self):
        page, _ = self.open_health(state("pro", days=9, ai=(12, 15, 0)))
        self.assertEqual(page.inner_text("#mp-ai"), "Bugungi AI limit: 12/15")
        self.patch(page, ai_remaining=None, ai_limit=None)
        self.assertFalse(page.is_visible("#mp-ai"))

    def test_free_user_has_no_card_and_keeps_the_upsell_row(self):
        page, _ = self.open_health(state())
        self.assertFalse(page.is_visible("#my-premium"))
        self.assertTrue(page.is_visible("#btn-open-premium"))

    def test_card_disappears_when_premium_ends(self):
        page, _ = self.open_health(state("ultra", days=3))
        self.assertTrue(page.is_visible("#my-premium"))
        self.patch(page, is_premium=False, premium_type="free", premium_expires_at=None, premium_unlimited=False,
                   premium_days_left=None)
        self.assertFalse(page.is_visible("#my-premium"))
        self.assertTrue(page.is_visible("#btn-open-premium"))

    def test_text_set_with_textcontent_not_html(self):
        page, _ = self.open_health(state("ultra", days=3, ai=(5, 30, 0)))
        self.assertEqual(page.locator("#my-premium img, #my-premium script").count(), 0)
        with open(os.path.join(ROOT, "app", "app.js"), encoding="utf-8") as f:
            js = f.read()
        block = js[js.index("function renderPremiumCard"): js.index("// A3: bosh ekran tepasida")]
        self.assertNotIn("innerHTML", block)

    def test_tap_target_contrast_and_reduced_motion(self):
        for scheme in ("light", "dark"):
            for tier, t in TOKENS.items():
                with self.subTest(scheme=scheme, tier=tier):
                    page, _ = self.open_health(state(tier, days=9), scheme=scheme)
                    box = page.locator("#mp-extend").bounding_box()
                    self.assertGreaterEqual(box["height"], 43.9)
                    for sel in ("#mp-extend", "#mp-until", "#mp-tier", "#mp-left", "#mp-ai", ".mp-kicker"):
                        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, (scheme, tier, sel))
        page, _ = self.open_health(state("ultra", days=9))
        page.emulate_media(reduced_motion="reduce")
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.mp-bar-fill')).transitionDuration"), "0s")

    def test_card_under_enforced_csp_has_no_violations(self):
        page, _ = self.open_app({"state": (200, state("ultra", days=2))}, init_script=scheme_script("light"),
                                enforce_csp=True)
        page.wait_for_selector("#global-score:not([hidden])")
        page.click('nav [data-tab="tab-health"]')
        page.wait_for_selector("#my-premium:not([hidden])")
        self.assertEqual(page.inner_text("#mp-left"), "2 kun qoldi")                  # --mp-pct (CSSOM) CSP'ni buzmaydi


# ───────────────────────────── A3: tugash banneri ─────────────────────────────
class ExpiryBannerE2ETest(PremiumE2EBase):
    def test_shown_for_two_days_or_less_only(self):
        cases = [
            (state("ultra", days=2), "Premiumingiz 2 kundan keyin tugaydi"),
            (state("pro", days=1), "Premiumingiz bugun tugaydi"),
            (state("plus", hours=3), "Premiumingiz bugun tugaydi"),
        ]
        for st, text in cases:
            with self.subTest(text=text):
                page, _ = self.open_state(st)
                page.wait_for_selector("#prem-banner:not([hidden])")
                self.assertEqual(page.inner_text("#prem-banner-text"), text)
                self.assertEqual(page.inner_text("#prem-banner-extend"), "Uzaytirish")
                self.assertEqual(page.evaluate("document.getElementById('tab-first-aid').firstElementChild.id"),
                                 "prem-banner")                                               # bosh ekranning tepasida
        for st in (state("ultra", days=3), state("ultra", days=30), state("ultra", unlimited=True), state()):
            with self.subTest(hidden=st["premium_days_left"]):
                page, _ = self.open_state(st)
                self.assertTrue(page.evaluate("document.getElementById('prem-banner').hidden"))

    def test_banner_is_only_on_the_home_screen(self):
        page, _ = self.open_state(state("ultra", days=2))
        page.wait_for_selector("#prem-banner:not([hidden])")
        page.click('nav [data-tab="tab-health"]')
        self.assertFalse(page.is_visible("#prem-banner"))

    def test_extend_opens_premium_modal(self):
        page, _ = self.open_state(state("ultra", days=2))
        page.click("#prem-banner-extend")
        page.wait_for_selector("#premium-modal:not(.hidden)")

    def test_close_is_remembered_for_this_expiry_value_only(self):
        st = state("ultra", days=2, expires=EXPIRES_FIXED)
        page, _ = self.open_state(st)
        page.wait_for_selector("#prem-banner:not([hidden])")
        page.click("#prem-banner-close")
        self.assertTrue(page.evaluate("document.getElementById('prem-banner').hidden"))
        self.assertEqual(page.evaluate("localStorage.getItem('premium_banner_dismissed')"), EXPIRES_FIXED)
        # Yangi holat shu muddat bilan — banner qaytmaydi
        self.patch(page, premium_days_left=2)
        self.assertTrue(page.evaluate("document.getElementById('prem-banner').hidden"))
        # Muddat uzaytirildi (yangi premium_expires_at) va yana <= 2 kun qoldi — banner yana chiqadi
        self.patch(page, premium_expires_at="2026-12-17T18:00:00+05:00", premium_days_left=2)
        self.assertFalse(page.evaluate("document.getElementById('prem-banner').hidden"))

    def test_remembered_value_survives_reload_and_other_value_does_not_hide(self):
        st = state("ultra", days=2, expires=EXPIRES_FIXED)
        remembered = f"localStorage.setItem('premium_banner_dismissed', '{EXPIRES_FIXED}');"
        page, _ = self.open_state(st, init_script=remembered)
        self.assertTrue(page.evaluate("document.getElementById('prem-banner').hidden"))
        other = "localStorage.setItem('premium_banner_dismissed', '2026-01-01T00:00:00+05:00');"
        page, _ = self.open_state(st, init_script=other)
        page.wait_for_selector("#prem-banner:not([hidden])")

    def test_storage_failure_does_not_break_the_banner(self):
        broken = "Object.defineProperty(window, 'localStorage', { get() { throw new Error('storage blocked'); } });"
        page, _ = self.open_state(state("ultra", days=2), init_script=broken)
        page.wait_for_selector("#prem-banner:not([hidden])")                  # eslab qolinmaydi, lekin ishlaydi
        page.click("#prem-banner-close")
        self.assertTrue(page.evaluate("document.getElementById('prem-banner').hidden"))     # sahifa xatosi yo'q (cleanup tekshiradi)

    def test_tap_targets_contrast_and_icon(self):
        for scheme in ("light", "dark"):
            for tier in TOKENS:
                with self.subTest(scheme=scheme, tier=tier):
                    page, _ = self.open_state(state(tier, days=2), scheme=scheme)
                    page.wait_for_selector("#prem-banner:not([hidden])")
                    for sel in ("#prem-banner-extend", "#prem-banner-close"):
                        assert_tap_target(self, page.locator(sel).bounding_box(), sel)
                    for sel in ("#prem-banner-text", "#prem-banner-extend"):
                        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, (scheme, tier, sel))
        self.assertEqual(page.get_attribute("#prem-banner > .icon use", "href"), "#i-clock")             # emoji emas, sprite
        self.assertEqual(page.get_attribute("#prem-banner-close", "aria-label"), "Yopish")
        self.assertIsNone(EMOJI.search(page.inner_text("#prem-banner")))


# ───────────────────────────── A4: tarif rangidagi aksent ─────────────────────────────
class TierAccentE2ETest(PremiumE2EBase):
    def test_body_class_and_accent_tokens_per_tier_and_theme(self):
        for scheme in ("light", "dark"):
            for tier, t in TOKENS.items():
                with self.subTest(scheme=scheme, tier=tier):
                    page, _ = self.open_state(state(tier, days=9), scheme=scheme)
                    page.wait_for_selector("#hdr-premium:not([hidden])")
                    self.assertEqual(self.body_classes(page), [f"tier-{tier}"])
                    primary, on, soft = t[scheme]
                    self.assertEqual(self.var(page, "--primary").upper(), primary)
                    self.assertEqual(self.var(page, "--on-primary").upper(), on)
                    self.assertEqual(self.var(page, "--primary-soft").upper(), soft)

    def test_free_user_keeps_green_teal(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_state(state(), scheme=scheme)
                self.assertEqual(self.body_classes(page), [])
                self.assertEqual(self.var(page, "--primary").upper(), DEFAULT_PRIMARY[scheme])

    def test_only_the_accent_changes_not_background_or_text(self):
        for scheme in ("light", "dark"):
            for tier in TOKENS:
                with self.subTest(scheme=scheme, tier=tier):
                    js = """() => { const cs = getComputedStyle(document.body);
                        return ['--bg', '--surface', '--text', '--text-2', '--line', '--danger', '--warning'].map(n => cs.getPropertyValue(n).trim())
                            .concat([cs.backgroundColor, cs.color]); }"""
                    free_page, _ = self.open_state(state(), scheme=scheme)
                    prem_page, _ = self.open_state(state(tier, days=9), scheme=scheme)
                    prem_page.wait_for_selector("#hdr-premium:not([hidden])")
                    for pg in (free_page, prem_page):                       # rang o'tish (transition) animatsiyalari tugasin
                        pg.wait_for_function("document.getAnimations().length === 0")
                    self.assertEqual(prem_page.evaluate(js), free_page.evaluate(js))
                    self.assertNotEqual(self.var(prem_page, "--primary"), self.var(free_page, "--primary"))

    def test_class_follows_state_changes(self):
        page, _ = self.open_state(state("pro", days=9))
        self.assertEqual(self.body_classes(page), ["tier-pro"])
        self.patch(page, premium_type="plus")
        self.assertEqual(self.body_classes(page), ["tier-plus"])                         # almashadi, to'planmaydi
        self.patch(page, is_premium=False, premium_type="free", premium_expires_at=None, premium_unlimited=False,
                   premium_days_left=None)
        self.assertEqual(self.body_classes(page), [])                                    # Premium tugadi: klass olib tashlanadi
        self.assertEqual(self.var(page, "--primary").upper(), DEFAULT_PRIMARY["light"])

    def test_new_api_state_after_removal_drops_the_class(self):
        page, calls = self.open_app({"state": sequence((200, state("ultra", days=9)), (200, state()))},
                                    init_script=scheme_script("light"))
        page.wait_for_selector("#hdr-premium:not([hidden])")
        self.assertEqual(self.body_classes(page), ["tier-ultra"])
        page.evaluate("() => { invalidateAppState(); return getAppState(0); }")           # yangi /api/state (admin olib tashladi)
        page.wait_for_function("document.querySelector('#hdr-premium').hidden === true")
        self.assertEqual(self.body_classes(page), [])
        self.assertEqual([c[0] for c in calls].count("state"), 2)

    def test_telegram_main_button_uses_the_tier_colors(self):
        for scheme in ("light", "dark"):
            for tier, t in TOKENS.items():
                with self.subTest(scheme=scheme, tier=tier):
                    page, _ = self.open_app({"state": (200, state(tier, days=9)),
                                             "spin/claim": (200, {"ok": True, "message": "x", "score": 7})},
                                            init_script=scheme_script(scheme))
                    page.wait_for_selector("#hdr-premium:not([hidden])")
                    self.open_wheel(page)
                    page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
                    self.spin_and_finish(page)                                           # "Mukofotni olish" — MainButton qo'yiladi
                    params = self.tg(page)["mainParams"]
                    primary, on, _soft = t[scheme]
                    self.assertEqual((params["color"].upper(), params["text_color"].upper()), (primary, on))

    def test_free_main_button_keeps_the_default_color(self):
        page, _ = self.open_app({"state": (200, state()), "spin/claim": (200, {"ok": True, "message": "x", "score": 7})},
                                init_script=scheme_script("light"))
        page.wait_for_selector("#global-score:not([hidden])")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)
        self.assertEqual(self.tg(page)["mainParams"]["color"].upper(), DEFAULT_PRIMARY["light"])

    def test_main_button_color_updates_when_the_tier_changes_while_it_is_shown(self):
        page, _ = self.open_app({"state": (200, state("pro", days=9)),
                                 "spin/claim": (200, {"ok": True, "message": "x", "score": 7})},
                                init_script=scheme_script("light"))
        page.wait_for_selector("#hdr-premium:not([hidden])")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)
        self.assertEqual(self.tg(page)["mainParams"]["color"].upper(), TOKENS["pro"]["light"][0])
        self.patch(page, premium_type="ultra")
        self.assertEqual(self.tg(page)["mainParams"]["color"].upper(), TOKENS["ultra"]["light"][0])

    def test_primary_buttons_keep_contrast_with_tier_accent(self):
        for scheme in ("light", "dark"):
            for tier in TOKENS:
                with self.subTest(scheme=scheme, tier=tier):
                    page, _ = self.open_state(state(tier, days=2), scheme=scheme)
                    page.wait_for_selector("#prem-banner:not([hidden])")
                    page.click('nav [data-tab="tab-health"]')
                    for sel in ("#mp-extend", "#prem-banner-extend"):
                        self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, (scheme, tier, sel))


if __name__ == "__main__":
    unittest.main()
