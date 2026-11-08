"""
test_miniapp_quiz_e2e.py — redesign 4.4-F: Test.
Ingichka progress + "3 / 10", to'liq kenglikdagi variant kartalari (to'g'ri — teal + ✓, noto'g'ri — danger + ✕, haptic),
natija — SVG doira progress "80 / 100". Savol/ball/saqlash mantig'i o'zgarmagan. Asos: tests/e2e_base.py
"""
import re
import unittest

from tests.e2e_base import CONTRAST_JS, MiniAppE2EBase

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")
OPTS = "#quiz-options-container .quiz-option-btn"


class QuizE2ETest(MiniAppE2EBase):
    def open_quiz(self, **kw):
        page, _ = self.open_app({}, **kw)
        page.click('#home-quiz-row')
        return page

    def start(self, page):
        page.click("#btn-start-quiz")
        page.wait_for_selector("#quiz-question-screen.active")

    def answer(self, page, correct):
        idx = page.evaluate("QUIZ_QUESTIONS[quizState.current].answer")
        if not correct:
            idx = 0 if idx != 0 else 1
        page.locator(OPTS).nth(idx).click()
        return idx

    def test_start_screen_svg_icons_no_emoji_and_button_contrast(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page = self.open_quiz(init_script=f"window.Telegram.WebApp.colorScheme = '{scheme}';")
                self.assertIsNone(EMOJI.search(page.inner_text("#tab-quiz")))
                self.assertEqual(page.get_attribute("#tab-quiz .screen-title use", "href"), "#i-brain")
                self.assertEqual(page.inner_text("#btn-start-quiz"), "Boshlash")
                self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#btn-start-quiz"), 4.5)   # dark kontrast tuzatildi
                self.start(page)
                self.answer(page, False)
                page.clock.fast_forward(10_000)
                for _ in range(9):
                    self.answer(page, True)
                    page.clock.fast_forward(1000)
                page.wait_for_selector("#quiz-result-screen.active")
                self.assertGreaterEqual(page.evaluate(CONTRAST_JS, "#btn-retry-quiz"), 4.5)

    def test_progress_line_and_counter(self):
        page = self.open_quiz()
        self.start(page)
        self.assertEqual(page.inner_text("#quiz-q-num"), "1 / 10")
        self.assertEqual(page.evaluate("document.getElementById('quiz-progress-fill').style.width"), "10%")
        self.assertEqual(page.get_attribute("#quiz-progress", "aria-valuenow"), "1")
        self.answer(page, True)
        page.clock.fast_forward(1000)
        self.assertEqual(page.inner_text("#quiz-q-num"), "2 / 10")
        self.assertEqual(page.get_attribute("#quiz-progress", "aria-valuenow"), "2")
        self.assertEqual(page.inner_text("#quiz-score-live"), "10 ball")

    def test_options_are_full_width_cards_with_letters(self):
        page = self.open_quiz()
        self.start(page)
        container = page.locator("#quiz-options-container").bounding_box()
        opts = page.locator(OPTS)
        self.assertGreaterEqual(opts.count(), 2)
        for i in range(opts.count()):
            box = opts.nth(i).bounding_box()
            self.assertAlmostEqual(box["width"], container["width"], delta=1)
            self.assertGreaterEqual(box["height"], 44)
        letters = page.evaluate(f"[...document.querySelectorAll('{OPTS} .quiz-opt-letter')].map(e => e.textContent)")
        self.assertEqual(letters, list("ABCD")[:opts.count()])
        texts = page.evaluate(f"[...document.querySelectorAll('{OPTS} .quiz-opt-text')].map(e => e.textContent)")
        self.assertEqual(texts, page.evaluate("QUIZ_QUESTIONS[0].options"))

    def test_correct_answer_teal_check_and_haptic(self):
        page = self.open_quiz()
        self.start(page)
        idx = self.answer(page, True)
        btn = page.locator(OPTS).nth(idx)
        self.assertIn("correct", btn.get_attribute("class"))
        primary = page.evaluate("getComputedStyle(document.body).getPropertyValue('--primary').trim()")
        self.assertEqual(primary.upper(), "#0E7C72")                                # G: to'g'ri javob — --primary (teal)
        page.wait_for_function(f"getComputedStyle(document.querySelectorAll('{OPTS}')[{idx}]).borderTopColor === 'rgb(14, 124, 114)'",
                               timeout=2000)                                        # transition tugashi
        self.assertTrue(btn.locator(".quiz-opt-ok").is_visible())
        self.assertEqual(self.tg(page)["haptics"], ["success"])
        self.assertEqual(page.inner_text("#quiz-feedback"), "To'g'ri!")
        self.assertTrue(all(page.locator(OPTS).nth(i).is_disabled() for i in range(page.locator(OPTS).count())))

    def test_wrong_answer_danger_x_and_shows_correct(self):
        page = self.open_quiz()
        self.start(page)
        correct = page.evaluate("QUIZ_QUESTIONS[quizState.current].answer")
        idx = self.answer(page, False)
        wrong = page.locator(OPTS).nth(idx)
        self.assertIn("wrong", wrong.get_attribute("class"))
        self.assertTrue(wrong.locator(".quiz-opt-bad").is_visible())
        page.wait_for_function(f"getComputedStyle(document.querySelectorAll('{OPTS}')[{idx}]).borderTopColor === 'rgb(180, 35, 27)'",
                               timeout=2000)                                        # transition tugashi
        self.assertIn("correct", page.locator(OPTS).nth(correct).get_attribute("class"))
        self.assertEqual(self.tg(page)["haptics"], ["error"])
        self.assertIn("Noto'g'ri", page.inner_text("#quiz-feedback"))
        self.assertEqual(page.inner_text("#quiz-score-live"), "0 ball")

    def test_result_ring_and_stats_saved(self):
        page = self.open_quiz()
        self.start(page)
        for i in range(10):
            self.answer(page, i >= 2)                                                  # 8 ta to'g'ri -> 80
            page.clock.fast_forward(1000)
        page.wait_for_selector("#quiz-result-screen.active")
        self.assertEqual(page.inner_text("#quiz-final-score-num"), "80")
        self.assertEqual(page.inner_text("#tab-quiz .ring-center small"), "/ 100")
        self.assertEqual(page.get_attribute("#quiz-ring-fill", "stroke-dasharray"), "80 100")
        self.assertEqual(page.get_attribute("#quiz-ring", "aria-label"), "100 dan 80 ball")
        self.assertIn("quiz-ring--good", page.get_attribute("#quiz-ring", "class"))
        self.assertEqual(page.inner_text("#quiz-result-title"), "Barakallo!")
        self.assertEqual(page.evaluate("SafeStorage.getItem('quiz_best')"), "80")
        self.assertEqual(page.evaluate("SafeStorage.getItem('quiz_attempts')"), "1")
        page.click("#btn-retry-quiz")
        self.assertEqual(page.inner_text("#quiz-q-num"), "1 / 10")

    def test_low_score_ring_tier(self):
        page = self.open_quiz()
        self.start(page)
        for _ in range(10):
            self.answer(page, False)
            page.clock.fast_forward(1000)
        page.wait_for_selector("#quiz-result-screen.active")
        self.assertEqual(page.get_attribute("#quiz-ring-fill", "stroke-dasharray"), "0 100")
        self.assertIn("quiz-ring--low", page.get_attribute("#quiz-ring", "class"))
        self.assertEqual(page.inner_text("#quiz-result-title"), "Ko'proq o'qing!")

    def test_keyboard_answer(self):
        page = self.open_quiz()
        self.start(page)
        idx = page.evaluate("QUIZ_QUESTIONS[quizState.current].answer")
        page.locator(OPTS).nth(idx).focus()
        page.keyboard.press("Enter")
        self.assertIn("correct", page.locator(OPTS).nth(idx).get_attribute("class"))


if __name__ == "__main__":
    unittest.main()
