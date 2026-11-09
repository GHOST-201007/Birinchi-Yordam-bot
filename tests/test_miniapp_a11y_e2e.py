"""
test_miniapp_a11y_e2e.py — G 5-bosqich (a11y): bosiladigan elementlarning HAQIQIY bosish zonasi >= 44x44
(::after kengaytmasi bilan, elementFromPoint orqali o'lchanadi), ikonka-tugmalarda nom (aria-label),
matn kontrasti >= 4.5:1 (light + dark), prefers-reduced-motion. Asos: tests/e2e_base.py

Istisno: Kasalliklar A–Z indeksi (#disease-az) — surib tanlanadigan panel (iOS kontaktlaridagi kabi); 22 harfni
44px dan joylab bo'lmaydi. Xuddi shu vazifa ro'yxat va qidiruv orqali ham bajariladi.
"""
import unittest

from tests.e2e_base import STATE_OK, MiniAppE2EBase

STATE = {**STATE_OK, "is_premium": False, "premium_type": "free", "ai_remaining": 1, "ai_limit": 1}

# Ko'rinadigan bosiladigan elementlar: nomi, haqiqiy bosish zonasi (markazdan +-21.5px nuqtalar shu elementga tushadimi)
TARGETS_JS = r"""() => {
  const out = [];
  const vis = el => {
    if (el.closest('[hidden], .hidden')) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
    }
    return true;
  };
  const desc = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '.' + [...el.classList].join('.'))
                     + ' "' + (el.textContent || '').trim().slice(0, 20) + '"';
  const name = el => {
    const lb = el.getAttribute('aria-labelledby');
    const byId = lb ? lb.split(/\s+/).map(id => (document.getElementById(id) || {}).textContent || '').join(' ') : '';
    const lab = el.labels && el.labels.length ? el.labels[0].textContent : '';
    return (el.getAttribute('aria-label') || byId || el.textContent || el.getAttribute('title') || lab || '').trim();
  };
  const SEL = 'button, a[href], [role=button], [role=radio], summary, input:not([type=hidden]), textarea, select';
  const seen = new Set();
  document.querySelectorAll(SEL).forEach(el => {
    if (!vis(el) || el.closest('#disease-az')) return;
    const target = (el.tagName === 'INPUT' && /radio|checkbox/.test(el.type)) ? (el.closest('label') || el) : el;
    if (seen.has(target)) return;
    seen.add(target);
    if (!name(el)) out.push(['noname', desc(el)]);
    try { target.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) { /* yo'q */ }
    const r = target.getBoundingClientRect();
    if (r.width >= 43.5 && r.height >= 43.5) return;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const inside = (x, y) => { const h = document.elementFromPoint(x, y); return !!h && (h === target || target.contains(h)); };
    if (!inside(cx, cy)) return;                       // boshqa qatlam ostida (masalan nav) — bu ekranda baholanmaydi
    const pts = [];
    if (r.height < 43.5) pts.push([cx, cy - 21.5], [cx, cy + 21.5]);
    if (r.width < 43.5) pts.push([cx - 21.5, cy], [cx + 21.5, cy]);
    if (pts.some(([x, y]) => !inside(x, y))) out.push(['small', desc(target), Math.round(r.width) + 'x' + Math.round(r.height)]);
  });
  return out;
}"""

# Bevosita matnli ko'rinadigan elementlar: kontrast >= 4.5 (o'chirilgan elementlar WCAG bo'yicha istisno)
CONTRAST_ALL_JS = r"""() => {
  const out = [];
  const parse = c => (c.match(/[\d.]+/g) || [0, 0, 0]).map(Number);
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
                                return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const vis = el => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || el.closest('[hidden], .hidden')) return false;
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
    }
    return true;
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const done = new Set();
  while (walker.nextNode()) {
    const el = walker.currentNode.parentElement;
    if (!walker.currentNode.textContent.trim() || !el || done.has(el)) continue;
    done.add(el);
    if (!vis(el) || el.closest('.sr-only, svg, [aria-hidden="true"], :disabled, [aria-disabled="true"]')) continue;
    let bg = null;
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== 'none') { bg = 'img'; break; }
      const c = parse(s.backgroundColor);
      if (c.length < 4 || c[3] > 0.99) { bg = c; break; }
    }
    if (bg === 'img') continue;
    bg = bg || [255, 255, 255];
    const a = lum(parse(getComputedStyle(el).color)), b = lum(bg);
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    if (ratio < 4.5) out.push([el.tagName.toLowerCase() + (el.id ? '#' + el.id : '.' + el.className), el.textContent.trim().slice(0, 30), +ratio.toFixed(2)]);
  }
  return out;
}"""


def home(page):
    page.wait_for_function("bodyMapData !== null")


def home_back(page):
    home(page)
    page.click(".fig-views [data-view='back']")


def first_aid_all(page):
    page.click("#home-chip-all")


def diseases(page):
    page.click('nav [data-tab="tab-diseases"]')


def diseases_search(page):
    diseases(page)
    page.fill("#disease-search-input", "gri")


def health(page):
    page.click('nav [data-tab="tab-health"]')


def history(page):
    health(page)
    page.click('[data-show-tab="tab-history"]')


def ai_chat(page):
    page.click('nav [data-tab="tab-ai"]')
    page.evaluate("aiSetContext({ type: 'body_part', key: 'kokrak', label: \"Ko'krak\" });"
                  "aiAddUser('Savol');"
                  "aiAddNotice('Aloqa yo\\'q', [aiRetryAction(), { id: 'bot', label: 'Botda davom etish', onClick() {} }]);")


def body_sheet(page):
    home(page)
    page.click("#kokrak")
    page.wait_for_selector("#body-map-modal:not([hidden])")


def detail(page):
    page.click('#home-chips [data-id="kuyish"]')
    page.wait_for_selector("#overlay-details.active")


def wheel(page):
    page.click("#btn-open-wheel")
    page.wait_for_selector("#wheel-modal:not(.hidden)")


def bonus(page):
    page.click("#btn-open-daily-bonus")
    page.wait_for_selector("#daily-bonus-modal:not(.hidden)")


def premium(page):
    health(page)
    page.click("#btn-open-premium")
    page.wait_for_selector("#premium-modal:not(.hidden)")


# (nomi, amal, brauzerda — Telegram tashqarisi: o'z "Orqaga" va sahifadagi tugmalar ko'rinadi)
SCREENS = [("home", home, False), ("home-back", home_back, False), ("hammasi", first_aid_all, False),
           ("diseases", diseases, False), ("diseases-search", diseases_search, False), ("health", health, False),
           ("history", history, False), ("ai", ai_chat, False), ("sheet", body_sheet, False),
           ("sheet-browser", body_sheet, True), ("detail", detail, False), ("detail-browser", detail, True),
           ("wheel", wheel, False), ("bonus", bonus, False), ("premium", premium, False)]


class A11yE2ETest(MiniAppE2EBase):
    def open(self, action, scheme="light", browser=False):
        kw = {"init_data": ""} if browser else {}
        page, _ = self.open_app({"state": (200, STATE)}, init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';",
                                **kw)
        page.emulate_media(reduced_motion="reduce")
        if not browser:
            page.wait_for_selector("#global-score:not([hidden])")
        action(page)
        # Mavzu qo'llanganda rang o'tishi (0.3 s) va ochilish animatsiyalari tugashi — ranglar yakuniy holatda o'lchanadi
        page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || "
                               "a.effect.getComputedTiming().endTime === Infinity)")
        return page

    def test_touch_targets_44_and_icon_buttons_named(self):
        for name, action, browser in SCREENS:
            with self.subTest(screen=name):
                page = self.open(action, browser=browser)
                self.assertEqual(page.evaluate(TARGETS_JS), [], name)

    def test_text_contrast_both_themes(self):
        for scheme in ("light", "dark"):
            for name, action, browser in SCREENS:
                with self.subTest(screen=name, scheme=scheme):
                    page = self.open(action, scheme, browser=browser)
                    self.assertEqual(page.evaluate(CONTRAST_ALL_JS), [], f"{name} / {scheme}")

    def test_aria_states(self):
        page = self.open(home)
        self.assertEqual(page.get_attribute('nav [data-tab="tab-first-aid"]', "aria-current"), "page")
        self.assertEqual(page.evaluate("[...document.querySelectorAll('.fig-views [data-view]')].map(b => b.getAttribute('aria-pressed'))"),
                         ["true", "false"])
        page.click(".fig-views [data-view='back']")
        self.assertEqual(page.evaluate("[...document.querySelectorAll('.fig-views [data-view]')].map(b => b.getAttribute('aria-pressed'))"),
                         ["false", "true"])
        page.click('nav [data-tab="tab-ai"]')
        self.assertEqual(page.get_attribute('nav [data-tab="tab-ai"]', "aria-current"), "page")
        self.assertIsNone(page.get_attribute('nav [data-tab="tab-first-aid"]', "aria-current"))
        self.assertEqual((page.get_attribute("#ai-thread", "role"), page.get_attribute("#ai-thread", "aria-live")), ("log", "polite"))

    def test_reduced_motion_stops_transitions_and_confetti(self):
        page = self.open(home)
        page.click('nav [data-tab="tab-health"]')
        duration = page.evaluate("parseFloat(getComputedStyle(document.getElementById('tab-health')).animationDuration)")
        self.assertLess(duration, 0.01)                                          # tab o'tishi (fadeIn) yo'q
        page.evaluate("fireConfetti()")
        self.assertEqual(page.evaluate("document.getElementById('wheel-confetti-canvas').width"), 300)   # chizilmadi
        self.assertEqual(page.evaluate("getComputedStyle(document.getElementById('wheel-canvas')).transitionDuration"), "0s")
        # baraban o'zi qisqa aylanadi (600 ms, inline) — umumiy qoida uni o'chirmaydi (test_miniapp_wheel_redesign_e2e)
        page.evaluate("document.getElementById('wheel-canvas').style.transition = 'transform 600ms linear'")
        self.assertEqual(page.evaluate("getComputedStyle(document.getElementById('wheel-canvas')).transitionDuration"), "0.6s")

    def test_confetti_runs_without_reduced_motion(self):
        page, _ = self.open_app({})
        page.evaluate("fireConfetti()")
        self.assertEqual(page.evaluate("document.getElementById('wheel-confetti-canvas').width"), 390)


if __name__ == "__main__":
    unittest.main()
