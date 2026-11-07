"""
test_css_structure.py — Mini App 3-bosqich: style.css da bitta :root va bitta body.dark-mode bloki.
Birlashtirishda qiymatlar o'zgarmagani (keyingi blok yutgan) asosiy o'zgaruvchilar bo'yicha tekshiriladi.
"""
import os
import re
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def css_text():
    with open(os.path.join(PROJECT_DIR, "app", "style.css"), encoding="utf-8") as f:
        return f.read()


def block(css, header):
    m = re.search(r"^" + re.escape(header) + r"\s*\{(.*?)\}", css, re.M | re.S)
    assert m, header
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


class CssStructureTest(unittest.TestCase):
    def setUp(self):
        self.css = css_text()

    def test_single_root_and_dark_block(self):
        self.assertEqual(len(re.findall(r"^:root\s*\{", self.css, re.M)), 1)
        self.assertEqual(len(re.findall(r"^body\.dark-mode\s*\{", self.css, re.M)), 1)

    def test_symptom_tag_not_duplicated(self):
        self.assertEqual(len(re.findall(r"^\.symptom-tag\s*\{", self.css, re.M)), 1)
        self.assertEqual(len(re.findall(r"^body\.dark-mode \.symptom-tag\s*\{", self.css, re.M)), 1)

    def test_braces_balanced(self):
        self.assertEqual(self.css.count("{"), self.css.count("}"))

    def test_light_values_from_later_block_win(self):
        root = block(self.css, ":root")
        self.assertEqual(root["--bg-color"], "#f0fbf9")
        self.assertEqual(root["--color-primary"], "#159b8a")
        self.assertEqual(root["--card-shadow"], "0 8px 24px rgba(21, 155, 138, 0.08)")
        # faqat birinchi blokda bo'lgan o'zgaruvchilar saqlangan
        for name in ("--space-1", "--radius-md", "--accent-red", "--color-error"):
            self.assertIn(name, root)

    def test_dark_values_merged(self):
        dark = block(self.css, "body.dark-mode")
        self.assertEqual(dark["--bg-color"], "#0b1816")
        self.assertEqual(dark["--button-color"], "#1eb5a2")
        self.assertEqual(dark["--card-shadow"], "0 8px 24px rgba(0, 0, 0, 0.4)")
        # birinchi blokdagi, ikkinchisida qayta yozilmagan qiymat saqlangan
        self.assertEqual(dark["--link-color"], "#4da6ff")
        self.assertEqual(dark["--accent-red-bg"], "rgba(255, 59, 48, 0.15)")


if __name__ == "__main__":
    unittest.main()
