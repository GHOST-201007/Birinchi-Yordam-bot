"""
test_miniapp_ai_chat_e2e.py — G 4-bosqich: AI tabi = mini app ichida suhbat (/api/ai/chat).
Salom + tezkor chiplar, yuborish va javob (xavfsiz render, innerHTML yo'q), tarix (oxirgi 6, xotirada),
limit (bepul — Premium taklif kartasi, yozish o'chiq; Premium — limit vaqti), "juda tez" (retry_after / inflight),
xatolar (band / tarmoq / forbidden), tana sheet'idan kontekst chipi, klaviatura, kontrast, CSP.
Asos: tests/e2e_base.py
"""
import os
import re
import unittest

os.environ.setdefault("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890")   # bot import (kalit qoidasi testi)
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_key")

from tests.e2e_base import CONTRAST_JS, STATE_OK, MiniAppE2EBase, sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREE = {**STATE_OK, "is_premium": False, "premium_type": "free", "ai_remaining": 1, "ai_limit": 1}
PREMIUM = {**STATE_OK, "is_premium": True, "premium_type": "pro", "ai_remaining": 12, "ai_limit": 15}
GREETING = "Salom! Nima bo'ldi? Holatni yozing, men birinchi yordam bo'yicha maslahat beraman."
DISCLAIMER = "Bu tashxis emas. Hayot xavf ostida bo'lsa — 103."
REPLIES = "#ai-thread .ai-msg--ai:not(.ai-greeting):not(.ai-typing)"
LAST_BUBBLE = f"{REPLIES}:last-child .ai-bubble"


def ok(reply="Sovuq suv bilan 10–20 daqiqa sovuting.", remaining=11, limit=15):
    return (200, {"ok": True, "reply": reply, "remaining": remaining, "limit": limit})


def error(status, code, **extra):
    return (status, {"ok": False, "error": code, "message": "server matni", **extra})


class AiChatE2ETest(MiniAppE2EBase):
    # ---- yordamchilar ---------------------------------------------------------------------
    def open_ai(self, state=FREE, chat=None, **kw):
        routes = {"state": (200, state) if state else "abort", "ai/chat": chat or ok()}
        routes.update(kw.pop("routes", {}))
        page, calls = self.open_app(routes, **kw)
        if state and kw.get("init_data", None) != "":
            page.wait_for_selector("#global-score:not([hidden])")
        page.click('nav [data-tab="tab-ai"]')
        page.wait_for_selector("#tab-ai.active")
        if not kw.get("enforce_csp"):                    # tab ochilish animatsiyasi (fadeIn) tugashi — o'lchamlar uchun
            page.wait_for_function("document.getElementById('tab-ai').getAnimations().length === 0")
        return page, calls

    def send(self, page, text):
        page.fill("#ai-input", text)
        page.click("#ai-send")

    def wait_replies(self, page, n=1):
        page.wait_for_function(f"document.querySelectorAll('{REPLIES}').length >= {n}")

    def chat_calls(self, calls):
        return [c[1] for c in calls if c[0] == "ai/chat"]

    def last_text(self, page):
        return page.inner_text(LAST_BUBBLE)

    def ready_body(self, page):
        page.wait_for_function("bodyMapData !== null")

    # ---- 1. Salom, chiplar, sarlavha ------------------------------------------------------
    def test_greeting_chips_header_and_no_api_call(self):
        page, calls = self.open_ai(FREE)
        self.assertEqual(page.inner_text(".ai-greeting .ai-bubble"), GREETING)
        chips = page.evaluate("[...document.querySelectorAll('#ai-quick .ai-chip')].map(b => b.textContent)")
        self.assertEqual(chips, ["Qon ketishi", "Kuyish", "Bo'g'ilish", "Yurak xuruji"])
        self.assertEqual(page.inner_text(".ai-disclaimer"), DISCLAIMER)
        self.assertEqual(page.inner_text(".ai-head-title"), "AI maslahat")
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 1/1")             # bepul: jami 1 ta
        self.assertEqual(page.get_attribute(".ai-head-badge use", "href"), "#i-sparkles")
        self.assertEqual(page.locator("#tab-ai a[href='tel:103']").count(), 0)          # AI tabida alohida 103 yo'q
        self.assertEqual(page.get_attribute("#ai-thread", "role"), "log")
        self.assertEqual(page.get_attribute("#ai-input", "maxlength"), "1000")
        self.assertTrue(page.is_disabled("#ai-send"))                                    # bo'sh matn
        self.assertTrue(page.is_disabled("#ai-new-chat"))
        self.assertNotIn("Tez orada", page.inner_text("#tab-ai"))
        self.assertEqual(page.locator("#ai-soon").count(), 0)
        self.assertFalse(self.tg(page)["mainVisible"])                                   # MainButton bu tabda yo'q
        self.assertEqual(self.chat_calls(calls), [])                                     # salom statik

    def test_premium_counter_format(self):
        page, _ = self.open_ai(PREMIUM)
        self.assertEqual(page.inner_text("#ai-quota"), "Bugun: 12/15 so'rov")

    def test_counter_kind_follows_server_limit(self):
        # Holat eskirgan (Premium botda olingan): server limiti 15 -> "Bugun", "Bepul savol" emas
        page, _ = self.open_ai(FREE, ok(remaining=14, limit=15))
        self.send(page, "Savol")
        self.wait_replies(page)
        self.assertEqual(page.inner_text("#ai-quota"), "Bugun: 14/15 so'rov")
        self.assertFalse(page.is_visible("#ai-premium-offer"))

    def test_stale_free_state_premium_limit_reached_no_free_offer(self):
        page, _ = self.open_ai(FREE, error(429, "limit", remaining=0, limit=15, offer="premium"))
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertIn("Bugungi limit tugadi", self.last_text(page))
        self.assertFalse(page.is_visible("#ai-premium-offer"))                           # bepul taklifi emas
        self.assertTrue(page.is_enabled("#ai-input"))

    def test_stale_premium_state_free_limit_shows_offer(self):
        page, _ = self.open_ai(PREMIUM, error(429, "limit", remaining=0, limit=1, offer="premium"))
        self.send(page, "Savol")
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertTrue(page.is_disabled("#ai-input"))

    def test_quick_chip_sends_its_text(self):
        page, calls = self.open_ai(FREE, ok(remaining=0, limit=1))
        page.click('#ai-quick [data-topic="kuyish"]')
        self.wait_replies(page)
        body = self.chat_calls(calls)[0]
        self.assertEqual((body["message"], body["history"]), ("Kuyish", []))
        self.assertNotIn("context", body)
        self.assertFalse(page.is_visible("#ai-quick"))                                   # suhbat boshlandi

    # ---- 2. Yuborish va javob --------------------------------------------------------------
    def test_send_shows_bubble_typing_and_blocks_double_send(self):
        page, calls = self.open_ai(PREMIUM, "hang")
        self.send(page, "Kuyib qoldim")
        self.assertEqual(page.inner_text("#ai-thread .ai-msg--user .ai-bubble"), "Kuyib qoldim")   # darhol
        self.assertTrue(page.is_visible(".ai-typing"))
        self.assertEqual(page.input_value("#ai-input"), "")
        self.wait_for_call(calls, "ai/chat")
        page.fill("#ai-input", "yana")
        self.assertTrue(page.is_disabled("#ai-send"))                                    # javob kelguncha o'chiq
        page.press("#ai-input", "Control+Enter")
        page.wait_for_timeout(200)
        self.assertEqual(len(self.chat_calls(calls)), 1)                                 # ikki marta ketmaydi
        self.assertTrue(page.is_disabled("#ai-new-chat"))
        self.assertTrue(page.is_disabled('#ai-quick [data-topic="kuyish"]'))
        page.clock.fast_forward(45_001)                                                  # AbortController 45 s
        page.wait_for_selector(".ai-msg--notice")
        self.assertIn("Aloqa yo'q", self.last_text(page))
        self.assertEqual(page.locator(".ai-typing").count(), 0)
        self.assertTrue(page.is_enabled("#ai-send"))

    def test_reply_rendered_safely_without_raw_markdown(self):
        reply = ("## Birinchi yordam\n**Muhim:** joyni sovuting.\n\n- Sovuq suv 10–20 daqiqa\n* Muz qo'ymang\n"
                 "1. Bir\n2. Ikki\n\n<img src=x onerror=\"window.__xss=1\"> va <b>x</b> *yulduz*")
        page, _ = self.open_ai(PREMIUM, ok(reply))
        self.send(page, "Kuyish")
        self.wait_replies(page)
        text = self.last_text(page)
        self.assertNotIn("**", text)
        self.assertNotIn("#", text)
        self.assertNotRegex(text, r"(?m)^\s*[*-]\s")                                     # xom ro'yxat belgisi yo'q
        self.assertNotIn("*", text)
        q = lambda sel: page.evaluate(f"[...document.querySelectorAll('{LAST_BUBBLE} {sel}')].map(e => e.textContent)")
        self.assertEqual(q(".ai-h"), ["Birinchi yordam"])
        self.assertEqual(q("strong"), ["Muhim:"])
        self.assertEqual(q("ul li"), ["Sovuq suv 10–20 daqiqa", "Muz qo'ymang"])
        self.assertEqual(q("ol li"), ["Bir", "Ikki"])
        self.assertEqual(page.locator(f"{LAST_BUBBLE} img, {LAST_BUBBLE} b, {LAST_BUBBLE} script").count(), 0)
        self.assertIn('<img src=x onerror="window.__xss=1">', text)                       # matn sifatida
        self.assertIsNone(page.evaluate("window.__xss"))
        self.assertEqual(page.inner_text("#ai-quota"), "Bugun: 11/15 so'rov")             # remaining dan

    def test_user_text_is_plain_text(self):
        page, _ = self.open_ai(PREMIUM)
        self.send(page, "<b>qalin</b> **emas**")
        self.wait_replies(page)
        self.assertEqual(page.inner_text("#ai-thread .ai-msg--user .ai-bubble"), "<b>qalin</b> **emas**")
        self.assertEqual(page.locator("#ai-thread .ai-msg--user b").count(), 0)

    def test_ctrl_enter_sends_enter_adds_newline_and_autosize(self):
        page, calls = self.open_ai(PREMIUM)
        page.fill("#ai-input", "Bir")
        one = page.evaluate("document.getElementById('ai-input').offsetHeight")
        page.press("#ai-input", "Enter")
        self.assertEqual(page.input_value("#ai-input"), "Bir\n")
        self.assertEqual(self.chat_calls(calls), [])
        self.assertGreater(page.evaluate("document.getElementById('ai-input').offsetHeight"), one)   # 2 qator
        page.fill("#ai-input", "1\n2\n3\n4\n5\n6")
        tall = page.evaluate("document.getElementById('ai-input').offsetHeight")
        self.assertEqual(one, 47)
        self.assertEqual(tall, 113)                                                       # ko'pi bilan 4 qator
        page.press("#ai-input", "Control+Enter")
        self.wait_replies(page)
        self.assertEqual(self.chat_calls(calls)[0]["message"], "1\n2\n3\n4\n5\n6")
        self.assertEqual(page.evaluate("document.getElementById('ai-input').offsetHeight"), 47)

    def test_history_last_six_in_memory_and_truncated(self):
        page, calls = self.open_ai(PREMIUM, ok("a" * 3000))
        for i in range(4):
            self.send(page, f"Savol {i}")
            self.wait_replies(page, i + 1)
        bodies = self.chat_calls(calls)
        self.assertEqual([len(b["history"]) for b in bodies], [0, 2, 4, 6])
        last = bodies[-1]["history"]
        self.assertEqual([h["role"] for h in last], ["user", "ai"] * 3)
        self.assertEqual([h["text"] for h in last if h["role"] == "user"], ["Savol 0", "Savol 1", "Savol 2"])
        self.assertTrue(all(len(h["text"]) <= 1000 for h in last))                       # server chegarasi
        self.assertEqual(len(last[1]["text"]), 1000)
        self.assertEqual(page.evaluate("localStorage.length"), 0)                         # tarix saqlanmaydi

    def test_new_chat_clears_history(self):
        page, calls = self.open_ai(PREMIUM)
        self.send(page, "Birinchi")
        self.wait_replies(page)
        self.assertTrue(page.is_enabled("#ai-new-chat"))
        page.click("#ai-new-chat")
        self.assertEqual(page.locator("#ai-thread .ai-msg").count(), 1)                  # faqat salom
        self.assertTrue(page.is_visible("#ai-quick"))
        self.assertTrue(page.is_disabled("#ai-new-chat"))
        self.send(page, "Ikkinchi")
        self.wait_replies(page)
        self.assertEqual(self.chat_calls(calls)[-1]["history"], [])

    # ---- 3. Limit ----------------------------------------------------------------------------
    def test_free_limit_shows_existing_offer_and_locks_composer(self):
        page, _ = self.open_ai(FREE, error(429, "limit", remaining=0, limit=1, offer="premium"))
        self.send(page, "Savol")
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertTrue(page.evaluate("!!document.querySelector('#ai-log #ai-premium-offer')"))   # suhbat ichida
        self.assertEqual(page.inner_text("#ai-offer-title"), "Bepul savolingiz ishlatildi")
        self.assertTrue(page.is_disabled("#ai-input"))
        self.assertTrue(page.is_disabled("#ai-send"))
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 0/1")
        self.assertEqual(page.locator(".ai-msg--notice").count(), 0)                     # alohida pufak yo'q

    def test_free_answer_with_zero_remaining_then_offer(self):
        page, _ = self.open_ai(FREE, ok(remaining=0, limit=1))
        self.send(page, "Savol")
        self.wait_replies(page)
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertIn("Sovuq suv", self.last_text(page))                                # javob ko'rinadi
        self.assertTrue(page.is_disabled("#ai-input"))
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 0/1")

    def test_used_free_question_locks_on_open(self):
        page, calls = self.open_ai({**FREE, "ai_remaining": 0})
        page.wait_for_selector("#ai-premium-offer:not([hidden])")
        self.assertTrue(page.is_disabled("#ai-input"))
        self.assertEqual(page.get_attribute("#ai-input", "placeholder"), "Bepul savolingiz ishlatildi")
        self.assertTrue(page.is_disabled('#ai-quick [data-topic="kuyish"]'))
        self.assertEqual(page.inner_text("#ai-quota"), "Bepul savol: 0/1")
        self.assertEqual(self.chat_calls(calls), [])

    def test_premium_limit_says_reset_time_and_opens_premium(self):
        page, _ = self.open_ai(PREMIUM, error(429, "limit", remaining=0, limit=15, offer="premium"))
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        text = self.last_text(page)
        self.assertIn("Bugungi limit tugadi", text)
        self.assertIn("ertaga soat 00:00", text)
        self.assertFalse(page.is_visible("#ai-premium-offer"))
        self.assertTrue(page.is_enabled("#ai-input"))
        self.assertEqual(page.inner_text("#ai-quota"), "Bugun: 0/15 so'rov")
        page.click('[data-ai-action="premium"]')
        page.wait_for_selector("#premium-modal:not(.hidden)")

    def test_ultra_limit_has_no_premium_button(self):
        page, _ = self.open_ai({**PREMIUM, "premium_type": "ultra"}, error(429, "limit", remaining=0, limit=100, offer=None))
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertIn("Bugungi limit tugadi", self.last_text(page))
        self.assertEqual(page.locator('[data-ai-action="premium"]').count(), 0)

    # ---- 4. Juda tez yozish (rate / inflight) ----------------------------------------------------
    def test_rate_limit_message_and_send_disabled_until_retry_after(self):
        page, calls = self.open_ai(PREMIUM, sequence(error(429, "busy", reason="rate", retry_after=5), ok()))
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertEqual(page.inner_text(".ai-msg--notice .ai-notice-text"),
                         "Juda tez yozyapsiz. 5 soniyadan so'ng qayta urinib ko'ring.")
        page.fill("#ai-input", "yana")
        self.assertTrue(page.is_disabled("#ai-send"))
        self.assertTrue(page.is_disabled('[data-ai-action="retry"]'))
        page.clock.fast_forward(4000)
        self.assertTrue(page.is_disabled("#ai-send"))                                    # hali 5 s o'tmadi
        page.clock.fast_forward(1100)
        self.assertTrue(page.is_enabled("#ai-send"))
        page.click('[data-ai-action="retry"]')                                           # o'sha xabar qayta
        self.wait_replies(page)
        self.assertEqual([b["message"] for b in self.chat_calls(calls)], ["Savol", "Savol"])
        self.assertEqual(page.locator("#ai-thread .ai-msg--user").count(), 1)
        self.assertEqual(page.locator(".ai-msg--notice").count(), 0)

    def test_inflight_shows_same_message(self):
        page, _ = self.open_ai(PREMIUM, (409, {"ok": False, "error": "busy", "reason": "inflight", "message": "x"}))
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertEqual(page.inner_text(".ai-msg--notice .ai-notice-text"),
                         "Juda tez yozyapsiz. 5 soniyadan so'ng qayta urinib ko'ring.")
        page.fill("#ai-input", "yana")
        self.assertTrue(page.is_disabled("#ai-send"))
        page.clock.fast_forward(5100)
        self.assertTrue(page.is_enabled("#ai-send"))

    # ---- 5. Xatolar --------------------------------------------------------------------------
    def test_busy_error_has_retry_that_resends(self):
        page, calls = self.open_ai(PREMIUM, sequence(error(503, "busy"), ok("Mana javob")))
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertEqual(page.inner_text(".ai-msg--notice .ai-notice-text"), "Hozir band, qayta urinib ko'ring.")
        page.click('[data-ai-action="retry"]')
        page.wait_for_function("document.querySelectorAll('.ai-msg--notice').length === 0 && "
                               f"document.querySelectorAll('{REPLIES}').length === 1")
        self.assertEqual(self.last_text(page), "Mana javob")
        self.assertEqual(len(self.chat_calls(calls)), 2)
        self.assertEqual(self.chat_calls(calls)[1]["history"], [])                       # xato tarixga kirmaydi

    def test_server_error_message(self):
        page, _ = self.open_ai(PREMIUM, error(500, "server"))
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertEqual(page.inner_text(".ai-msg--notice .ai-notice-text"), "Xatolik yuz berdi. Qayta urinib ko'ring.")
        self.assertEqual(page.locator('[data-ai-action="retry"]').count(), 1)

    def test_network_error_offers_bot_fallback_old_send_data_path(self):
        page, _ = self.open_ai(PREMIUM, "abort")
        self.send(page, "Bolam zaharlandi")
        page.wait_for_selector(".ai-msg--notice")
        self.assertEqual(page.inner_text(".ai-msg--notice .ai-notice-text"),
                         "Aloqa yo'q. Internetni tekshirib, qayta urinib ko'ring.")
        self.assertEqual(page.locator('[data-ai-action="retry"]').count(), 1)
        page.click('[data-ai-action="bot"]')
        tg = self.tg(page)
        self.assertEqual(tg["sent"], ['{"action":"ai_consult","title":"Bolam zaharlandi"}'])
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot"])
        self.assertEqual(tg["closed"], 1)

    def test_api_without_error_code_treated_as_network(self):
        page, _ = self.open_ai(PREMIUM, (502, {"ok": False}))                            # nginx / noma'lum javob
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertIn("Aloqa yo'q", self.last_text(page))
        self.assertEqual(page.locator('[data-ai-action="bot"]').count(), 1)

    def test_forbidden_outside_telegram_and_403(self):
        page, calls = self.open_ai(None, init_data="")
        self.send(page, "Savol")
        page.wait_for_selector(".ai-msg--notice")
        self.assertEqual(page.inner_text(".ai-msg--notice .ai-notice-text"), "Mini appni Telegram ichida oching.")
        self.assertEqual(self.chat_calls(calls), [])
        self.assertEqual(page.locator(".ai-msg--notice button").count(), 0)
        page2, _ = self.open_ai(PREMIUM, error(403, "forbidden"))
        self.send(page2, "Savol")
        page2.wait_for_selector(".ai-msg--notice")
        self.assertEqual(page2.inner_text(".ai-msg--notice .ai-notice-text"), "Mini appni Telegram ichida oching.")

    # ---- 6. Tana sheet'idan kontekst chipi -------------------------------------------------------
    def test_body_sheet_opens_ai_tab_with_context_chip_without_sending(self):
        page, calls = self.open_app({"state": (200, PREMIUM), "ai/chat": ok()})
        self.ready_body(page)
        page.click("#kokrak")
        page.wait_for_selector("#body-map-modal:not([hidden])")
        self.assertEqual(self.tg(page)["mainText"], "AI'dan so'rash")
        page.evaluate("window.__mainCb()")
        page.wait_for_selector("#tab-ai.active")
        self.assertEqual(page.get_attribute('nav [data-tab="tab-ai"]', "aria-current"), "page")
        self.assertFalse(page.is_visible("#body-map-modal"))
        self.assertEqual(page.inner_text("#ai-context-label"), "Tana qismi: Ko'krak")
        self.assertEqual(page.evaluate("document.activeElement.id"), "ai-input")
        tg = self.tg(page)
        self.assertEqual((tg["sent"], tg["links"], tg["closed"]), ([], [], 0))           # botga chiqmaydi
        self.assertFalse(tg["mainVisible"])
        self.assertFalse(tg["backVisible"])
        self.assertEqual(self.chat_calls(calls), [])                                     # avtomatik yuborilmaydi
        self.send(page, "Og'riyapti")
        self.wait_replies(page)
        self.assertEqual(self.chat_calls(calls)[0]["context"], {"type": "body_part", "key": "kokrak"})
        self.assertFalse(page.is_visible("#ai-context"))                                 # birinchi yuborishda
        self.send(page, "Yana")
        self.wait_replies(page, 2)
        self.assertNotIn("context", self.chat_calls(calls)[1])

    def test_context_chip_can_be_removed(self):
        page, calls = self.open_app({"state": (200, PREMIUM), "ai/chat": ok()})
        self.ready_body(page)
        page.evaluate("openBodyMapModal('left_knee')")
        page.evaluate("window.__mainCb()")
        page.wait_for_selector("#tab-ai.active")
        self.assertEqual(page.inner_text("#ai-context-label"), "Tana qismi: Chap tizza")
        page.click("#ai-context-clear")
        self.assertFalse(page.is_visible("#ai-context"))
        self.send(page, "Savol")
        self.wait_replies(page)
        self.assertNotIn("context", self.chat_calls(calls)[0])

    def test_context_bot_fallback_keeps_old_body_part_link(self):
        page, calls = self.open_app({"state": (200, PREMIUM), "ai/chat": "abort"})
        self.ready_body(page)
        page.evaluate("openBodyMapModal('left_knee')")
        page.evaluate("window.__mainCb()")
        page.wait_for_selector("#tab-ai.active")
        self.send(page, "Tizzam og'riyapti")
        page.wait_for_selector('[data-ai-action="bot"]')
        self.assertEqual(self.chat_calls(calls)[0]["context"], {"type": "body_part", "key": "knee"})
        page.click('[data-ai-action="bot"]')
        tg = self.tg(page)
        self.assertEqual(tg["sent"], ['{"action":"ai_consult","title":"Tizza"}'])
        self.assertEqual(tg["links"], ["https://t.me/Birinchiyordam1Bot?start=ai_consult_left_knee"])
        self.assertEqual(tg["closed"], 1)

    # ---- 6b. Detal / kasallik "AI'dan so'rash" (holat konteksti) -----------------------------------------
    def test_first_aid_detail_opens_ai_with_condition_chip(self):
        page, calls = self.open_app({"state": (200, PREMIUM), "ai/chat": ok()})
        page.click('#home-chips [data-id="kuyish"]')
        page.wait_for_selector("#overlay-details.active")
        self.assertEqual(self.tg(page)["mainText"], "AI'dan so'rash")
        page.evaluate("window.__mainCb()")
        page.wait_for_selector("#tab-ai.active")
        self.assertFalse(page.evaluate("document.getElementById('overlay-details').classList.contains('active')"))
        self.assertEqual(page.inner_text("#ai-context-label"), "Holat: Kuyish")
        self.assertEqual(page.evaluate("document.activeElement.id"), "ai-input")
        tg = self.tg(page)
        self.assertEqual((tg["links"], tg["sent"], tg["mainVisible"], tg["backVisible"]), ([], [], False, False))
        self.assertEqual(self.chat_calls(calls), [])                                     # avtomatik yuborilmaydi
        self.send(page, "Nima qilay?")
        self.wait_replies(page)
        self.assertEqual(self.chat_calls(calls)[0]["context"], {"type": "condition", "key": "kuyish"})

    def test_critical_detail_secondary_ai_button(self):
        page, _ = self.open_app({"state": (200, PREMIUM), "ai/chat": ok()})
        page.click('#home-chips [data-id="qon_ketishi"]')
        page.wait_for_selector("#overlay-details.active")
        self.assertEqual(self.tg(page)["mainText"], "103 ga qo'ng'iroq")                # MainButton — 103
        page.evaluate("document.getElementById('overlay-details').scrollTop = 99999")
        page.click("#detail-ai-btn")
        page.wait_for_selector("#tab-ai.active")
        self.assertEqual(page.inner_text("#ai-context-label"), "Holat: Qon ketishi")

    def test_disease_detail_opens_ai_with_disease_key(self):
        page, calls = self.open_app({"state": (200, PREMIUM), "ai/chat": ok()})
        page.click('nav [data-tab="tab-diseases"]')
        page.fill("#disease-search-input", "gripp")
        page.locator("#disease-list-container .list-row", has_text="Gripp").first.click()
        page.wait_for_selector("#overlay-details.active")
        page.evaluate("window.__mainCb()")
        page.wait_for_selector("#tab-ai.active")
        self.assertEqual(page.inner_text("#ai-context-label"), "Kasallik: Gripp")
        self.assertEqual(self.chat_calls(calls), [])
        self.send(page, "Isitmam bor")
        self.wait_replies(page)
        self.assertEqual(self.chat_calls(calls)[0]["context"], {"type": "condition", "key": "gripp"})

    def test_disease_keys_match_server_rule(self):
        import bot                                                                      # noqa: E402 (env — test_free_ai_limit)
        page, _ = self.open_app({})
        pairs = page.evaluate("DISEASES_DATA.map(d => [d.name, aiDiseaseKey(d.name)])")
        self.assertGreater(len(pairs), 100)
        for name, key in pairs:
            self.assertEqual(key, bot.ai_disease_key(name), name)
        labels = bot.AI_CONTEXT_LABELS["condition"]
        known = [n for n, k in pairs if k in labels]
        self.assertGreaterEqual(len(known), 100)                                        # serverdagi 100 tasi ruxsat etilgan

    # ---- 7. Joylashuv, klaviatura ----------------------------------------------------------------
    def test_composer_pinned_above_nav_messages_scroll(self):
        page, _ = self.open_ai(PREMIUM, ok("Uzun javob\n" * 60))
        self.send(page, "Savol")
        self.wait_replies(page)
        composer = page.locator("#ai-composer").bounding_box()
        nav = page.locator(".app-nav").bounding_box()
        self.assertAlmostEqual(composer["y"] + composer["height"], nav["y"], delta=1)
        self.assertEqual(page.evaluate("document.querySelector('.app-content').scrollTop"), 0)
        self.assertGreater(page.evaluate("(() => { const l = document.getElementById('ai-log'); "
                                         "return l.scrollHeight - l.clientHeight; })()"), 0)
        self.assertEqual(page.locator(".app-header").bounding_box()["y"], 0)

    def test_keyboard_hides_nav_and_keeps_composer_visible(self):
        page, _ = self.open_ai(PREMIUM)
        page.focus("#ai-input")
        page.set_viewport_size({"width": 390, "height": 480})                            # klaviatura ochildi
        page.wait_for_function("document.body.classList.contains('kb-open')")
        self.assertFalse(page.is_visible(".app-nav"))
        box = page.locator("#ai-composer").bounding_box()
        self.assertLessEqual(box["y"] + box["height"], 481)
        page.evaluate("document.activeElement.blur()")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_function("!document.body.classList.contains('kb-open')")
        self.assertTrue(page.is_visible(".app-nav"))
        self.assertEqual(page.evaluate("document.getElementById('app-container').style.height"), "")

    def test_keyboard_state_not_used_on_other_tabs(self):
        page, _ = self.open_ai(PREMIUM)
        page.click('nav [data-tab="tab-health"]')
        self.assertFalse(page.evaluate("document.body.classList.contains('ai-tab-on')"))
        page.set_viewport_size({"width": 390, "height": 480})
        self.assertTrue(page.is_visible(".app-nav"))

    # ---- 8. Mavzu (kontrast), CSP, innerHTML yo'q ---------------------------------------------------
    def test_contrast_light_and_dark(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, _ = self.open_ai(PREMIUM, error(503, "busy"),
                                       init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                page.evaluate("aiSetContext({ type: 'body_part', key: 'kokrak', label: \"Ko'krak\" })")
                for sel in (".ai-greeting .ai-bubble p", ".ai-chip span", ".ai-disclaimer span", "#ai-quota",
                            ".ai-head-title", "#ai-context-label"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
                self.send(page, "Savol")
                page.wait_for_selector(".ai-msg--notice")
                for sel in (".ai-msg--user .ai-user-text", ".ai-notice-text", '[data-ai-action="retry"] span'):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
                page.evaluate("aiAddReply('Oddiy **javob** matni')")
                for sel in (f"{LAST_BUBBLE} p", f"{LAST_BUBBLE} strong"):
                    self.assertGreaterEqual(page.evaluate(CONTRAST_JS, sel), 4.5, sel)
                bg = page.evaluate("getComputedStyle(document.querySelector('.ai-msg--user .ai-bubble')).backgroundColor")
                # --primary: PREMIUM (Pro) holatida aksent tarif rangida (A4: body.tier-pro), bepulda sukut teal (pastdagi test)
                self.assertEqual(bg, "rgb(0, 113, 127)" if scheme == "light" else "rgb(77, 208, 225)")

    def test_user_bubble_uses_default_primary_for_free_user_and_tier_accent_for_premium(self):
        default = {"light": "rgb(14, 124, 114)", "dark": "rgb(61, 194, 179)"}
        pro = {"light": "rgb(0, 113, 127)", "dark": "rgb(77, 208, 225)"}
        for scheme in ("light", "dark"):
            for st, expected in ((FREE, default), (PREMIUM, pro)):
                with self.subTest(scheme=scheme, premium=st["is_premium"]):
                    page, _ = self.open_ai(st, error(503, "busy"),
                                           init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                    self.send(page, "Savol")
                    page.wait_for_selector(".ai-msg--user .ai-bubble")
                    page.wait_for_function("document.getAnimations().length === 0")
                    bg = page.evaluate("getComputedStyle(document.querySelector('.ai-msg--user .ai-bubble')).backgroundColor")
                    self.assertEqual(bg, expected[scheme])

    def test_bubble_shapes(self):
        page, _ = self.open_ai(PREMIUM)
        self.send(page, "Savol")
        self.wait_replies(page)
        radius = lambda sel: page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).borderRadius")
        self.assertEqual(radius(LAST_BUBBLE), "6px 20px 20px")
        self.assertEqual(radius(".ai-msg--user .ai-bubble"), "20px 20px 6px")

    def test_typing_dots_static_with_reduced_motion(self):
        page, _ = self.open_ai(PREMIUM, "hang")
        page.emulate_media(reduced_motion="reduce")
        self.send(page, "Savol")
        self.assertEqual(page.locator(".ai-typing .ai-dot").count(), 3)
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.ai-dot')).animationName"), "none")

    def test_works_under_csp(self):
        page, _ = self.open_ai(PREMIUM, ok("**Qalin** matn\n- ro'yxat"), enforce_csp=True)
        page.fill("#ai-input", "Savol")
        page.click("#ai-send")
        page.wait_for_selector(f"{REPLIES} .ai-bubble strong")
        self.assertEqual(page.inner_text(f"{REPLIES} .ai-bubble li"), "ro'yxat")


class AiChatStaticTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "app", "app.js"), encoding="utf-8") as f:
            self.js = f.read()

    def section(self, start, end):
        a = self.js.index(start)
        return self.js[a:self.js.index(end, a)]

    def test_ai_chat_code_has_no_innerhtml(self):
        chat = self.section("// AI SUHBAT TABI (G 4-bosqich)", "// ═══ /AI SUHBAT TABI ═══")
        self.assertEqual(chat.count("innerHTML"), 0)
        self.assertEqual(chat.count("insertAdjacentHTML") + chat.count("outerHTML"), 0)
        self.assertIn("textContent", chat)
        bridge = self.section("function openAiChatFromBodySheet()", "function markSelectedBodyPart()")
        self.assertEqual(bridge.count("innerHTML"), 0)

    def test_old_send_data_path_kept_as_fallback(self):
        self.assertIn('tg.sendData(JSON.stringify({ action: "ai_consult", title: title }))', self.js)
        self.assertRegex(self.js, r"api\('ai/chat', body, \{ timeoutMs: AI_TIMEOUT_MS, withStatus: true \}\)")

    def test_no_inline_styles_or_scripts_in_html(self):
        with open(os.path.join(ROOT, "app", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertNotRegex(html, r"\sstyle=")
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)[^>]*>")
        self.assertIn('<symbol id="i-send"', html)
        self.assertIsNone(re.search("[\U0001F300-\U0001FAFF]", html[html.index('id="tab-ai"'):html.index("</main>")]))


if __name__ == "__main__":
    unittest.main()
