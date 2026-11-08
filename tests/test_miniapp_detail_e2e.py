"""
test_miniapp_detail_e2e.py — redesign 4.4-C: detal sahifa (birinchi yordam va kasallik), tg.MainButton, tg.BackButton.
Asos: tests/e2e_base.py
"""
import re
import unittest

from tests.e2e_base import MiniAppE2EBase

# Overlay ichidagi har bir ko'rinadigan matn: kontrast (yarim shaffof fonlar qatlamlab hisoblanadi) va o'lcham
TEXT_AUDIT_JS = r"""(sel) => {
    const parse = c => { const m = c.match(/[\d.]+/g).map(Number); return [m[0], m[1], m[2], m.length > 3 ? m[3] : 1]; };
    const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
                                  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
    const bgOf = (el) => {
        const layers = [];
        for (let e = el; e; e = e.parentElement) {
            const c = parse(getComputedStyle(e).backgroundColor);
            if (c[3] > 0) layers.push(c);
            if (c[3] >= 0.99) break;
        }
        let base = [255, 255, 255];
        if (layers.length && layers[layers.length - 1][3] >= 0.99) base = layers.pop().slice(0, 3);
        for (let i = layers.length - 1; i >= 0; i--) { const l = layers[i]; base = base.map((v, k) => l[k] * l[3] + v * (1 - l[3])); }
        return base;
    };
    const out = [];
    document.querySelector(sel).querySelectorAll('*').forEach(el => {
        if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) return;
        for (let e = el; e; e = e.parentElement) {
            const cs = getComputedStyle(e);
            if (parseFloat(cs.opacity) === 0 || cs.visibility === 'hidden') return;
        }
        const cs = getComputedStyle(el);
        const a = lum(parse(cs.color)), b = lum(bgOf(el));
        const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        const size = parseFloat(cs.fontSize);
        if (ratio < 4.5 || size < 16) out.push([el.textContent.trim().slice(0, 40), +ratio.toFixed(2), size]);
    });
    return out;
}"""


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
        self.assertIn(data["prohibited"].strip()[:40], page.inner_text(".dont-card .dont-list"))
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

    def test_main_button_fallback_outside_telegram(self):
        # initData bo'sh (brauzer): MainButton ishlatilmaydi, sahifada oddiy tugma bor va ishlaydi
        page, _ = self.open_app({}, init_data="")
        self.open_item(page, "qon_ketishi")
        self.assertFalse(self.tg(page)["mainVisible"])
        self.assertTrue(page.is_visible("#detail-main-fallback"))
        self.assertEqual(page.inner_text("#detail-main-fallback"), "103 ga qo'ng'iroq")
        page.click("#close-overlay-btn") if page.is_visible("#close-overlay-btn") else page.evaluate("closeDetail()")
        page.wait_for_selector("#overlay-details:not(.active)", state="attached")
        page.clock.fast_forward(400)
        self.open_item(page, "kuyish")
        self.assertEqual(page.inner_text("#detail-main-fallback"), "AI'dan so'rash")
        page.click("#detail-main-fallback")
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot"])

    def test_inside_telegram_fallback_hidden_and_bottom_padding(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        self.assertFalse(page.is_visible("#detail-main-fallback"))
        self.assertTrue(page.evaluate("document.body.classList.contains('tg-main-on')"))
        pad = page.evaluate("parseFloat(getComputedStyle(document.querySelector('.overlay-inner')).paddingBottom)")
        self.assertGreaterEqual(pad, 100)                                           # MainButton kontentni yopmaydi
        page.evaluate("window.__backCb()")
        page.wait_for_selector("#overlay-details:not(.active)", state="attached")
        self.assertFalse(page.evaluate("document.body.classList.contains('tg-main-on')"))

    # ---- Detal 10/10 -------------------------------------------------------------------------------------------
    def test_sticky_bar_becomes_compact_on_scroll(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        self.assertFalse(page.evaluate("document.getElementById('detail-bar').classList.contains('compact')"))
        self.assertEqual(page.inner_text("#detail-bar-name"), page.inner_text("#overlay-title"))
        self.assertEqual(page.locator("#detail-bar-chip .chip").count(), 1)
        page.evaluate("const o = document.getElementById('overlay-details'); o.scrollTop = 600; o.dispatchEvent(new Event('scroll'))")
        page.wait_for_function("document.getElementById('detail-bar').classList.contains('compact')")
        self.assertAlmostEqual(page.locator("#detail-bar").bounding_box()["y"], 0, delta=1)   # sticky: tepada qoladi
        page.wait_for_function("getComputedStyle(document.querySelector('.detail-bar-title')).opacity === '1'")
        page.evaluate("const o = document.getElementById('overlay-details'); o.scrollTop = 0; o.dispatchEvent(new Event('scroll'))")
        page.wait_for_function("!document.getElementById('detail-bar').classList.contains('compact')")

    def test_back_arrow_only_when_telegram_back_button_unavailable(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        self.assertFalse(page.is_visible("#close-overlay-btn"))
        # Telegram tashqarisi: telegram-web-app.js BackButton obyektini yaratadi, lekin initData bo'sh — o'z tugmamiz kerak
        page, _ = self.open_app({}, init_data="")
        self.open_item(page, "kuyish")
        self.assertTrue(page.is_visible("#close-overlay-btn"))
        self.assertEqual(page.get_attribute("#close-overlay-btn", "aria-label"), "Orqaga")
        self.assertFalse(self.tg(page)["backVisible"])
        page.click("#close-overlay-btn")
        page.wait_for_selector("#overlay-details:not(.active)", state="attached")

    def test_top_block_103_for_critical_safety_row_otherwise(self):
        page, _ = self.open_app({})
        self.open_item(page, "qon_ketishi")
        first = page.evaluate("document.querySelector('#overlay-body-content').firstElementChild.className")
        self.assertIn("call-card--top", first)
        self.assertEqual(page.locator("#overlay-body-content .call-card").count(), 1)
        self.assertEqual(page.locator("#overlay-body-content .safety-row").count(), 0)
        page.evaluate("window.__backCb()")
        page.clock.fast_forward(400)
        self.open_item(page, "kuyish")
        first = page.evaluate("document.querySelector('#overlay-body-content').firstElementChild")
        self.assertIn("safety-row", page.evaluate("document.querySelector('#overlay-body-content').firstElementChild.className"))
        self.assertIn("Avval xavfsizlikni tekshiring", page.inner_text(".safety-row"))
        self.assertEqual(page.get_attribute(".safety-row", "role"), "note")
        self.assertEqual(page.locator("#overlay-body-content .call-card--top").count(), 0)
        self.assertEqual(page.locator("#overlay-body-content .call-card").count(), 1)  # pastda qoladi

    def test_steps_can_be_checked_with_progress_not_persisted(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")
        n = len(self.item(page, "kuyish")["steps"])
        storage_before = page.evaluate("JSON.stringify(Object.keys(localStorage))")
        self.assertEqual(page.inner_text("#steps-progress-count"), f"0/{n}")
        btns = page.locator("#overlay-body-content .timeline-btn")
        self.assertEqual(btns.first.get_attribute("role"), "checkbox")
        btns.nth(0).click()
        btns.nth(1).click()
        self.assertEqual(btns.nth(0).get_attribute("aria-checked"), "true")
        self.assertEqual(page.inner_text("#steps-progress-count"), f"2/{n}")
        self.assertEqual(page.evaluate("document.getElementById('steps-bar-fill').style.width"), f"{round(2 / n * 100)}%")
        self.assertTrue(page.is_visible(".timeline-step.done .timeline-check"))
        btns.nth(0).click()
        self.assertEqual(page.inner_text("#steps-progress-count"), f"1/{n}")
        page.evaluate("window.__backCb()")
        page.clock.fast_forward(400)
        self.open_item(page, "kuyish")
        self.assertEqual(page.inner_text("#steps-progress-count"), f"0/{n}")         # saqlanmaydi
        self.assertEqual(page.evaluate("JSON.stringify(Object.keys(localStorage))"), storage_before)

    def test_keyboard_space_checks_step_and_escape_closes_with_focus_return(self):
        page, _ = self.open_app({})
        page.focus('#first-aid-grid [data-id="kuyish"]')
        page.keyboard.press("Enter")
        page.wait_for_selector("#overlay-details.active")
        self.assertEqual(page.evaluate("document.activeElement.id"), "overlay-title")  # fokus detalga o'tdi
        page.focus("#overlay-body-content .timeline-btn")
        page.keyboard.press("Space")
        self.assertEqual(page.get_attribute("#overlay-body-content .timeline-btn", "aria-checked"), "true")
        page.keyboard.press("Escape")
        page.wait_for_selector("#overlay-details:not(.active)", state="attached")
        self.assertEqual(page.evaluate("document.activeElement.getAttribute('data-id')"), "kuyish")

    def test_dont_block_icon_and_x_rows_keep_text(self):
        page, _ = self.open_app({})
        self.open_item(page, "qon_ketishi")
        data = self.item(page, "qon_ketishi")
        self.assertEqual(page.get_attribute(".dont-title use", "href"), "#i-ban")
        rows = page.evaluate("[...document.querySelectorAll('.dont-list li')].map(li => li.innerText.trim())")
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(page.locator(".dont-list li .dont-x svg").count(), len(rows))
        norm = lambda t: re.sub(r"\s+", " ", t).strip()
        self.assertEqual(norm(" ".join(rows)), norm(data["prohibited"]))             # matn o'zgarmagan, faqat bo'lingan
        self.assertTrue(all(r.endswith("!") or "!" in r for r in rows))

    def test_share_copies_plain_text_and_shows_toast(self):
        page, _ = self.open_app({}, init_script="""Object.defineProperty(navigator, 'clipboard', { value: {
            writeText: (t) => { window.__copied = t; return Promise.resolve(); } } });""")
        self.open_item(page, "kuyish")
        page.click("#detail-share-btn")
        page.wait_for_function("window.__copied")
        text = page.evaluate("window.__copied")
        self.assertIn("Kuyish", text)
        self.assertIn("1. ", text)
        self.assertIn("✕ ", text)
        self.assertIn("103", text)
        self.assertIn("https://t.me/Birinchiyordam1Bot", text)
        self.assertNotIn("<", text)
        self.assertTrue(page.is_visible("#toast"))
        self.assertIn("nusxalandi", page.inner_text("#toast"))
        page.clock.fast_forward(2500)
        self.assertFalse(page.is_visible("#toast"))

    def test_secondary_ai_button_only_when_main_is_103(self):
        page, _ = self.open_app({})
        self.open_item(page, "kuyish")                                               # MainButton = AI
        self.assertFalse(page.is_visible("#detail-ai-btn"))
        self.assertTrue(page.is_visible("#detail-share-btn"))
        page.evaluate("window.__backCb()")
        page.clock.fast_forward(400)
        self.open_item(page, "qon_ketishi")                                          # MainButton = 103
        page.evaluate("document.getElementById('overlay-details').scrollTop = 99999")
        self.assertTrue(page.is_visible("#detail-ai-btn"))
        page.click("#detail-ai-btn")
        self.assertEqual(self.tg(page)["links"], ["https://t.me/Birinchiyordam1Bot"])

    def test_text_contrast_aa_and_min_16px_in_both_themes(self):
        for scheme in ("light", "dark"):
            for item_id in ("kuyish", "qon_ketishi"):
                with self.subTest(scheme=scheme, item=item_id):
                    page, _ = self.open_app({}, init_data="",
                                            init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                    self.open_item(page, item_id)
                    page.locator("#overlay-body-content .timeline-btn").first.click()   # "done" holati ham tekshiriladi
                    page.wait_for_function("getComputedStyle(document.getElementById('overlay-details')).opacity === '1'")
                    self.assertEqual(page.evaluate(TEXT_AUDIT_JS, "#overlay-details"), [])
                    # Tekshiruvning o'zi ishlashini tasdiqlash: ataylab yomon matn qo'shamiz
                    page.evaluate("""document.getElementById('overlay-body-content').insertAdjacentHTML('beforeend',
                        '<p id="bad" style="color:#B0B0B0;font-size:12px">past kontrast</p>')""")
                    self.assertEqual(len(page.evaluate(TEXT_AUDIT_JS, "#overlay-details")), 1)

    def test_disease_detail_has_share_and_no_safety_row(self):
        page, _ = self.open_app({}, init_script="""Object.defineProperty(navigator, 'clipboard', { value: {
            writeText: (t) => { window.__copied = t; return Promise.resolve(); } } });""")
        page.click('nav [data-tab="tab-diseases"]')
        page.locator("#disease-list-container .list-row").first.click()
        page.wait_for_selector("#overlay-details.active")
        self.assertEqual(page.locator("#overlay-body-content .safety-row").count(), 0)
        self.assertFalse(page.is_visible("#detail-ai-btn"))
        page.click("#detail-share-btn")
        page.wait_for_function("window.__copied")
        self.assertIn(page.inner_text("#overlay-title"), page.evaluate("window.__copied"))
        page.wait_for_function("getComputedStyle(document.getElementById('overlay-details')).opacity === '1'")
        self.assertEqual(page.evaluate(TEXT_AUDIT_JS, "#overlay-details"), [])

    def test_disease_detail(self):
        page, _ = self.open_app({})
        page.click('nav [data-tab="tab-diseases"]')
        row = page.locator("#disease-list-container .list-row").first             # ro'yxat alifbo tartibida
        name = row.locator(".row-title").inner_text()
        first = page.evaluate("(n) => DISEASES_DATA.find(d => d.name === n)", name)
        row.click()
        page.wait_for_selector("#overlay-details.active")
        self.assertEqual(page.inner_text("#overlay-title"), first["name"])
        self.assertEqual(page.inner_text("#overlay-chips .chip"), first["cat"])
        self.assertIn("Kasallik tavsifi", page.inner_text("#overlay-body-content"))
        self.assertIn("Birinchi yordam va chora", page.inner_text("#overlay-body-content"))
        self.assertEqual(self.tg(page)["mainText"], "AI'dan so'rash")


if __name__ == "__main__":
    unittest.main()
