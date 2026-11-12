"""
test_miniapp_wheel_prizes_e2e.py — Omad baraboni: 8 bo'lak va yangi sovrin turlari (brauzerda, Playwright).

  1, 2, 3, 5 ball | -2 kun maslahati | -1 +1 bepul AI savol | -3 1 kunlik Premium Pro | 0 SUPER
Har tur uchun: bo'lak (kod bo'yicha), tasdiqlash kartasi, natija kartasi, konfetti, yopilganda claim, qayta tiklash,
zaxira deep link; AI tabidagi "+ N bonus" hisoblagichi. Asos: tests/e2e_base.py
"""
import datetime as dt
import os
import re

from tests.e2e_base import INIT_DATA, STATE_OK, MiniAppE2EBase, sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")
ORDER = [1, 2, 3, 5, -2, -1, -3, 0]                      # app.js segments tartibi (soat strelkasi bo'yicha)
TYPE = {1: "points", 2: "points", 3: "points", 5: "points", -2: "tip", -1: "ai", -3: "pro_day", 0: "super", 10: "points"}
TIP = "Kuyganda joyni 10–20 daqiqa salqin oqar suv ostida tuting. Muz, yog' yoki tish pastasi surtmang."


def state(prize, **kw):
    return {**STATE_OK, "prize": prize, "prize_type": TYPE.get(prize), **kw}


def claim(prize, **kw):
    base = {"ok": True, "message": "server xabari", "score": 7, "is_super": prize == 0, "prize": prize,
            "prize_type": TYPE[prize], "points": prize if prize > 0 else 0, "tip": None}
    return (200, {**base, **kw})


CLAIM_TIP = claim(-2, message="💡 Kun maslahati\n\n" + TIP, tip=TIP)
CLAIM_AI = claim(-1, message="🤖 +1 bepul AI savol yutdingiz!", is_premium=False, premium_type="free",
                 ai_remaining=2, ai_limit=1, ai_bonus=2)
PRO_EXPIRES = (dt.datetime.now(dt.timezone(dt.timedelta(hours=5))) + dt.timedelta(hours=23)).isoformat()
CLAIM_PRO = claim(-3, message="⭐ Tabriklaymiz! Siz Omad barabanidan 1 kunlik Premium Pro yutib oldingiz — u hozir faollashdi! 🎉",
                  is_premium=True, premium_type="pro", premium_expires_at=PRO_EXPIRES, premium_unlimited=False,
                  premium_days_left=1, ai_remaining=15, ai_limit=15, ai_bonus=0)
CLAIM_SUPER = claim(0, message="SUPER PRIZ")
CLAIMS = {-2: CLAIM_TIP, -1: CLAIM_AI, -3: CLAIM_PRO, 0: CLAIM_SUPER}


class WheelPrizesE2ETest(MiniAppE2EBase):
    # ---- yordamchilar ---------------------------------------------------------------------
    def open_ready(self, prize, claim_response=None, **kw):
        routes = {"state": (200, state(prize)), "spin/claim": claim_response or CLAIMS.get(prize) or claim(prize)}
        routes.update(kw.pop("routes", {}))
        page, calls = self.open_app(routes, **kw)
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        return page, calls

    def landed_index(self, page):
        transform = page.evaluate("document.getElementById('wheel-canvas').style.transform")
        deg = float(re.search(r"rotate\(([-\d.]+)deg\)", transform).group(1))
        return int(((270 - deg) % 360) // 45)

    def title(self, page):
        return page.inner_text("#wheel-result-msg .result-title")

    def desc(self, page):
        return page.inner_text("#wheel-result-msg .result-desc")

    def icon_href(self, page):
        return page.get_attribute("#wheel-result-msg .result-icon use", "href")

    def close_x(self, page):
        page.click("#wheel-modal-close")
        page.wait_for_function("document.getElementById('wheel-modal').style.display === 'none'")

    # ---- 8 bo'lak -------------------------------------------------------------------------
    def test_every_prize_stops_on_its_own_segment(self):
        for prize in ORDER:
            with self.subTest(prize=prize):
                page, _ = self.open_ready(prize)
                self.spin_and_finish(page)
                self.assertEqual(self.landed_index(page), ORDER.index(prize))

    def test_all_eight_segments_draw_a_glyph_and_a_label(self):
        page, _ = self.open_ready(5)
        result = page.evaluate("""() => {
            const c = document.getElementById('wheel-canvas'), ctx = c.getContext('2d');
            const r = c.width / 2, arc = Math.PI * 2 / 8, out = [];
            for (let i = 0; i < 8; i++) {
                const th = (i + 0.5) * arc, cos = Math.cos(th), sin = Math.sin(th);
                const pt = (px, py) => [Math.round(r + px * cos - py * sin), Math.round(r + px * sin + py * cos)];
                const [bx, by] = pt(r * 0.93, 0);
                const bg = ctx.getImageData(bx, by, 1, 1).data;
                let glyph = 0, label = 0;
                for (let px = 105; px <= 285; px += 2) {
                    for (let py = -50; py <= 54; py += 2) {
                        const [x, y] = pt(px, py), d = ctx.getImageData(x, y, 1, 1).data;
                        const diff = Math.abs(d[0] - bg[0]) + Math.abs(d[1] - bg[1]) + Math.abs(d[2] - bg[2]);
                        if (diff > 120) { if (py < 12) glyph++; else label++; }
                    }
                }
                out.push([glyph, label]);
            }
            return out;
        }""")
        self.assertEqual(len(result), 8)
        for i, (glyph, label) in enumerate(result):
            self.assertGreater(glyph, 40, f"{i}-bo'lak: belgi/ikonka chizilmagan")
            self.assertGreater(label, 40, f"{i}-bo'lak: yozuv chizilmagan")

    def test_wheel_icon_symbols_are_path_only_for_canvas(self):
        with open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8") as f:
            html = f.read()
        for name in ("lightbulb", "bot", "star"):
            symbol = re.search(rf'<symbol id="i-{name}"[^>]*>(.*?)</symbol>', html, re.S).group(1)
            self.assertTrue(symbol.strip().startswith("<path"), name)
            self.assertEqual(re.findall(r"<(?!path\b)(\w+)", symbol), [], f"{name}: faqat <path> (canvas Path2D)")
        self.assertIn("kun maslahati", html)                                  # canvas aria-label yangi sovrinlarni aytadi
        self.assertIn("bepul AI savol", html)

    def test_legacy_pending_10_points_still_works_without_a_segment(self):
        page, calls = self.open_ready(10, claim_response=claim(10, score=17))
        self.spin_and_finish(page)
        self.assertEqual(self.landed_index(page), ORDER.index(5))             # eng katta ball bo'lagida to'xtaydi
        self.assertEqual(self.title(page), "+10 ball yutdingiz!")             # karta serverdagi qiymat bo'yicha

    def test_unknown_negative_code_is_blocked_with_error_card(self):
        page, calls = self.open_ready(-9, claim_response=(200, {"ok": False}))
        page.click("#btn-spin-wheel")
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Texnik xatolik')")
        self.assertEqual([c[0] for c in calls], ["state"])

    # ---- tasdiqlash kartasi (aylanishdan keyin, claim'dan oldin) ----------------------------------
    def test_confirm_card_per_prize_type(self):
        expected = {
            5: ("+5 ball yutdingiz!", "Ballarni hisobingizga", "#i-sparkles"),
            2: ("+2 ball yutdingiz!", "Ballarni hisobingizga", "#i-sparkles"),
            -2: ("Kun maslahati", "maslahatni ochish", "#i-lightbulb"),
            -1: ("+1 bepul AI savol", "AI tabida ishlatishingiz mumkin", "#i-bot"),
            -3: ("1 kunlik Premium Pro yutdingiz!", "Faollashtirish", "#i-star"),
            0: ("SUPER PRIZ!", "50% chegirma", "#i-crown"),
        }
        for prize, (title, desc, icon) in expected.items():
            with self.subTest(prize=prize):
                page, calls = self.open_ready(prize)
                self.spin_and_finish(page)
                self.assertEqual(self.title(page), title)
                self.assertIn(desc, self.desc(page))
                self.assertEqual(self.icon_href(page), icon)
                self.assertEqual(page.locator("#wheel-result-msg .result-icon svg").count(), 1)
                self.assertEqual(page.inner_text("#btn-confirm-spin"), "Mukofotni olish")
                self.assertIsNone(EMOJI.search(self.card_text(page)))          # kartada emoji yo'q (SVG ikonka)
                self.assertEqual([c[0] for c in calls], ["state"])             # tasdiqlanguncha hech narsa berilmaydi

    def test_premium_style_icon_for_super_and_pro_day_only(self):
        for prize, accent in ((5, False), (-2, False), (-1, False), (-3, True), (0, True)):
            with self.subTest(prize=prize):
                page, _ = self.open_ready(prize)
                self.spin_and_finish(page)
                self.assertEqual(page.locator("#wheel-result-msg .result-icon--super").count(), 1 if accent else 0)

    # ---- natija kartasi (claim'dan keyin) ---------------------------------------------------------
    def test_tip_card_shows_tip_text_and_no_points(self):
        page, calls = self.open_ready(-2)
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Kun maslahati')")
        self.assertEqual(self.desc(page), TIP)
        self.assertEqual(page.inner_text("#global-score-val"), "7")             # ball o'zgarmadi
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])
        self.assertEqual(calls[1][1], {"init_data": INIT_DATA})                 # tanada boshqa hech narsa yo'q
        self.assertEqual(self.icon_href(page), "#i-lightbulb")
        self.assertEqual(self.tg(page)["links"], [])

    def test_tip_text_is_never_interpreted_as_html(self):
        evil = "<img src=x onerror=\"window.__xss=1\"><b>qalin</b>"
        page, _ = self.open_ready(-2, claim_response=claim(-2, tip=evil, message="Kun maslahati " + evil))
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Kun maslahati')")
        self.assertEqual(self.desc(page), evil)                                 # matn sifatida
        self.assertEqual(page.locator("#wheel-result-msg img").count(), 0)
        self.assertEqual(page.locator("#wheel-result-msg b").count(), 0)
        self.assertIsNone(page.evaluate("window.__xss"))

    def test_ai_card_and_ai_tab_counter(self):
        page, calls = self.open_ready(-1)
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('+1 bepul AI savol')")
        self.assertEqual(self.desc(page), "AI tabida ishlatishingiz mumkin")
        self.assertEqual(self.icon_href(page), "#i-bot")
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])        # hisoblagich uchun qo'shimcha /api/state yo'q
        self.close_x(page)
        page.click('nav [data-tab="tab-ai"]')
        page.wait_for_selector("#tab-ai.active")
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 0/1 + 2 bonus")
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])

    def test_pro_day_card_and_header_badge(self):
        page, calls = self.open_ready(-3)
        self.assertFalse(page.is_visible("#hdr-premium"))
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('1 kunlik Premium Pro faollashdi!')")
        self.assertIn("1 kunlik Premium Pro", self.desc(page))                  # server xabari (oddiy matn)
        self.assertEqual(self.icon_href(page), "#i-star")
        page.wait_for_function("document.getElementById('hdr-premium-name').textContent === 'Pro · bugun'")
        self.assertTrue(page.is_visible("#hdr-premium"))
        self.assertEqual([c[0] for c in calls], ["state", "spin/claim"])

    def test_super_card_unchanged(self):
        page, _ = self.open_ready(0)
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-desc:has-text('50% chegirma faollashtirildi')")
        self.assertEqual(self.title(page), "SUPER PRIZ!")
        self.assertEqual(page.inner_text("#wheel-result-msg .result-confirm-btn"), "Premium olish")

    def test_claim_refused_title_depends_on_prize_type(self):
        refused = (200, {"ok": False, "message": "Allaqachon olingan", "score": 7, "prize": None, "prize_type": None,
                         "points": 0, "tip": None})
        for prize, title in ((5, "Ball qo'shilmadi"), (-2, "Sovrin qo'shilmadi"), (-1, "Sovrin qo'shilmadi"),
                             (-3, "Sovrin qo'shilmadi")):
            with self.subTest(prize=prize):
                page, _ = self.open_ready(prize, claim_response=refused)
                self.spin_and_confirm(page)
                page.wait_for_selector(f"#wheel-result-msg .result-title:has-text(\"{title}\")")
                self.assertIn("Allaqachon olingan", self.desc(page))

    # ---- oyna yopilganda sovrin yo'qolmaydi -------------------------------------------------------
    def test_closing_without_confirming_claims_every_prize_type_once(self):
        toasts = {
            -2: "Kun maslahati: " + TIP,
            -1: "+1 bepul AI savol hisobingizga qo'shildi",
            -3: "1 kunlik Premium Pro faollashdi",
            0: "SUPER PRIZ: Premium Plus uchun 50% chegirma faollashtirildi",
            5: "+5 ball hisobingizga qo'shildi",
        }
        for prize, toast in toasts.items():
            with self.subTest(prize=prize):
                claim_response = (200, {**CLAIMS[prize][1], "score": 12}) if prize in CLAIMS else claim(5, score=12)
                page, calls = self.open_ready(prize, claim_response=claim_response)
                self.spin_and_finish(page)                                      # "Mukofotni olish" bosilmaydi
                self.close_x(page)
                self.wait_for_call(calls, "spin/claim")
                page.wait_for_selector("#toast:not([hidden])")
                self.assertEqual(page.inner_text("#toast"), toast)
                page.wait_for_timeout(300)
                self.assertEqual([c[0] for c in calls].count("spin/claim"), 1)
                self.assertEqual(self.tg(page)["links"], [])

    # ---- javob yo'qolsa: holatni qayta so'rab, tur bo'yicha karta ----------------------------------
    def test_lost_claim_response_recovers_card_for_each_type(self):
        after = {**STATE_OK, "prize": None, "prize_type": None, "cooldown_seconds": 86000}
        expected = {
            -2: ("Kun maslahati", "matnni ko'rsatib bo'lmadi"),
            -1: ("+1 bepul AI savol", "AI tabida ishlatishingiz mumkin"),
            -3: ("1 kunlik Premium Pro faollashdi!", ""),
            0: ("SUPER PRIZ!", "50% chegirma faollashtirildi"),
            5: ("Ball hisobingizga qo'shilgan", ""),
        }
        for prize, (title, desc) in expected.items():
            with self.subTest(prize=prize):
                page, calls = self.open_ready(prize, routes={
                    "state": sequence((200, state(prize)), (200, after)), "spin/claim": "abort"})
                self.spin_and_confirm(page)
                page.wait_for_selector(f"#wheel-result-msg .result-title:has-text(\"{title}\")")
                self.assertIn(desc, self.card_text(page))
                self.assertEqual(self.tg(page)["links"], [])                    # server bergan: deep link yo'q
                self.assertEqual([c[0] for c in calls], ["state", "spin/claim", "state"])

    def test_connection_error_then_close_retries_new_prize_once(self):
        page, calls = self.open_ready(-1, routes={
            "state": sequence((200, state(-1)), (200, state(-1))), "spin/claim": sequence("abort", CLAIM_AI)})
        self.spin_and_confirm(page)
        page.wait_for_selector("#wheel-result-msg .result-title:has-text('Ulanishda xatolik')")
        self.assertIn("Sovrin hali qo'shilmadi", self.desc(page))
        self.close_x(page)
        page.wait_for_function("[...document.querySelectorAll('#toast')].some(t => !t.hidden)")
        self.assertEqual([c[0] for c in calls].count("spin/claim"), 2)

    # ---- zaxira: API yo'q -> botga deep link ---------------------------------------------------------
    def test_fallback_deep_link_names_per_prize_type(self):
        expected = {0: "spin_super", -1: "spin_ai", -2: "spin_tip", -3: "spin_proday", 2: "spin_2", 5: "spin_5"}
        for prize, start in expected.items():
            with self.subTest(prize=prize):
                page, calls = self.open_app({}, query=f"?prize={prize}", init_data="")
                self.open_wheel(page)
                page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
                self.spin_and_finish(page)
                self.assertEqual(self.landed_index(page), ORDER.index(prize))
                self.press_main(page, "#btn-confirm-spin")
                self.assertEqual(calls, [])
                self.assertEqual(self.tg(page)["links"], [f"https://t.me/Birinchiyordam1Bot?start={start}"])
                self.assertEqual(self.tg(page)["closed"], 1)

    # ---- xavfsizlik / dizayn qoidalari ---------------------------------------------------------------
    def test_reduced_motion_still_shows_new_prize_cards(self):
        page, _ = self.open_ready(-2)
        page.emulate_media(reduced_motion="reduce")
        page.click("#btn-spin-wheel")
        self.assertIn("600ms", page.evaluate("document.getElementById('wheel-canvas').style.transition"))
        page.clock.fast_forward(800)
        page.wait_for_selector("#btn-confirm-spin", state="attached")
        self.assertEqual(self.title(page), "Kun maslahati")

    def test_dark_theme_draws_wheel_without_errors(self):
        page, _ = self.open_app({"state": (200, state(-3)), "spin/claim": CLAIM_PRO},
                                init_script="window.Telegram.WebApp.colorScheme = 'dark';")
        self.open_wheel(page)
        page.wait_for_function("!document.querySelector('#btn-spin-wheel').disabled")
        self.spin_and_finish(page)
        self.assertEqual(self.landed_index(page), ORDER.index(-3))


class AiTabBonusCounterE2ETest(MiniAppE2EBase):
    """AI tabi sarlavhasi: remaining bonusni o'z ichiga oladi, "+ N bonus" alohida; limit<=1 hamon "bepul"."""

    def open_ai(self, ai_state, chat=None):
        page, calls = self.open_app({"state": (200, {**STATE_OK, **ai_state}),
                                     "ai/chat": chat or (200, {"ok": True, "reply": "Salom", "remaining": 1,
                                                               "limit": 1, "bonus": 1})})
        page.wait_for_selector("#global-score:not([hidden])")
        page.click('nav [data-tab="tab-ai"]')
        page.wait_for_selector("#tab-ai.active")
        return page, calls

    def test_free_user_label_with_bonus(self):
        page, _ = self.open_ai({"is_premium": False, "premium_type": "free", "ai_remaining": 3, "ai_limit": 1, "ai_bonus": 2})
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 1/1 + 2 bonus")

    def test_free_question_used_but_bonus_left_no_premium_offer(self):
        page, _ = self.open_ai({"is_premium": False, "premium_type": "free", "ai_remaining": 2, "ai_limit": 1, "ai_bonus": 2})
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 0/1 + 2 bonus")
        self.assertTrue(page.is_hidden("#ai-premium-offer"))                    # savol berish mumkin: taklif kartasi yo'q
        self.assertFalse(page.is_disabled("#ai-input"))

    def test_premium_label_with_bonus(self):
        page, _ = self.open_ai({"is_premium": True, "premium_type": "pro", "ai_remaining": 14, "ai_limit": 15, "ai_bonus": 2})
        self.assertEqual(page.inner_text("#ai-quota"), "Bugun: 12/15 so'rov + 2 bonus")

    def test_state_without_bonus_field_looks_as_before(self):
        page, _ = self.open_ai({"is_premium": False, "premium_type": "free", "ai_remaining": 1, "ai_limit": 1})
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 1/1")
        page, _ = self.open_ai({"is_premium": True, "premium_type": "pro", "ai_remaining": 12, "ai_limit": 15, "ai_bonus": 0})
        self.assertEqual(page.inner_text("#ai-quota"), "Bugun: 12/15 so'rov")

    def test_reply_updates_label_and_last_bonus_shows_offer_when_everything_is_spent(self):
        page, _ = self.open_ai({"is_premium": False, "premium_type": "free", "ai_remaining": 1, "ai_limit": 1, "ai_bonus": 1},
                               chat=(200, {"ok": True, "reply": "Salom", "remaining": 0, "limit": 1, "bonus": 0}))
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 0/1 + 1 bonus")
        page.fill("#ai-input", "Kuyib qoldim")
        page.click("#ai-send")
        page.wait_for_function("document.getElementById('ai-quota').textContent === 'Bepul savol: 0/1'")
        page.wait_for_function("!document.getElementById('ai-premium-offer').hidden")     # hammasi tugadi: Premium taklifi

    def test_reply_with_remaining_bonus_keeps_chat_open(self):
        page, _ = self.open_ai({"is_premium": False, "premium_type": "free", "ai_remaining": 3, "ai_limit": 1, "ai_bonus": 2},
                               chat=(200, {"ok": True, "reply": "Salom", "remaining": 2, "limit": 1, "bonus": 2}))
        page.fill("#ai-input", "Kuyib qoldim")
        page.click("#ai-send")
        page.wait_for_function("document.getElementById('ai-quota').textContent === 'Bepul savol: 0/1 + 2 bonus'")
        self.assertTrue(page.is_hidden("#ai-premium-offer"))
