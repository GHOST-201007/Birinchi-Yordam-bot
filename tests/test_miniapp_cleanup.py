"""
test_miniapp_cleanup.py — G 5-bosqich tozalash (statik):
app/ da buzilgan belgi (U+FFFD) yo'q; index.html da inline style / handler yo'q; tokenlar bitta :root va bitta
body.dark-mode blokida; har bir CSS klassi va keyframes ishlatiladi (eski Tana tabi, SOS karta, eski modal/baraban
qoldiqlari yo'q); innerHTML shablonlariga foydalanuvchi / AI matni qo'yilmaydi.
Sprite ikonkalar ro'yxati redesign 4.3 spetsifikatsiyasi bo'yicha (test_miniapp_icons.py) — bu yerda tekshirilmaydi.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")


def read(name):
    with open(os.path.join(APP, name), encoding="utf-8") as f:
        return f.read()


class CleanupStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css, cls.html, cls.js = read("style.css"), read("index.html"), read("app.js")
        cls.text = cls.html + "\n" + cls.js

    def test_no_replacement_character_in_app(self):
        for name in os.listdir(APP):
            if name.endswith((".js", ".css", ".html", ".json")):
                self.assertNotIn("�", read(name), name)

    def test_no_inline_style_or_handlers(self):
        self.assertEqual(self.html.count('style="'), 0)
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", self.html))

    def test_single_token_blocks(self):
        self.assertEqual(len(re.findall(r"^:root\s*\{", self.css, re.M)), 1)
        self.assertEqual(len(re.findall(r"^body\.dark-mode\s*\{", self.css, re.M)), 1)

    def used(self, name):
        if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", self.text):
            return True
        m = re.match(r"(.+?-{1,2})\w+$", name)                  # dinamik: 'base--' + x / `base-${x}`
        return bool(m) and any(m.group(1) + q in self.text for q in ("'", '"', "${"))

    def test_every_css_class_is_used(self):
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        classes = set()
        for sel in re.findall(r"([^{}]+)\{", css):
            if not sel.strip().startswith("@"):
                classes.update(re.findall(r"\.([A-Za-z_][\w-]*)", sel))
        dead = sorted(c for c in classes if not self.used(c))
        self.assertEqual(dead, [])

    def test_every_keyframes_is_used(self):
        for name in re.findall(r"@keyframes ([\w-]+)", self.css):
            self.assertRegex(self.css, r"animation(-name)?:[^;]*\b" + re.escape(name) + r"\b", name)

    def test_legacy_body_map_and_sos_removed(self):
        for legacy in ("human-body-svg", "body-map-card", "body-quick-chips", "scanner-sweep", "section-title",
                       "modal-content", "doctor-modal", "SOS kartasi"):
            self.assertNotIn(legacy, self.css + self.html, legacy)
        self.assertNotIn("function bodyPartName", self.js)

    def test_innerhtml_templates_have_no_user_or_ai_text(self):
        # Har bir `innerHTML = `...`` shablonidagi ${...} ifodalar: foydalanuvchi kiritgan / AI matni yo'q
        deny = re.compile(r"\b(value|query|reply|message|first_name|last_name|username|initData|pending|aiChat|input)\b")
        for m in re.finditer(r"innerHTML\s*=\s*`((?:[^`\\]|\\.)*)`", self.js):
            for expr in re.findall(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", m.group(1)):
                self.assertIsNone(deny.search(expr), f"innerHTML: ${{{expr}}}")


if __name__ == "__main__":
    unittest.main()
