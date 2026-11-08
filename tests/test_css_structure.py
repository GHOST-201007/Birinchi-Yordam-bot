"""
test_css_structure.py — style.css: bitta :root va bitta body.dark-mode (3-bosqich), 4.2 dizayn tokenlari (redesign).
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
    return dict((k, v.strip()) for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


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

    def test_design_tokens_light(self):
        root = block(self.css, ":root")
        expected = {
            "--bg": "#F2F4F7", "--surface": "#FFFFFF", "--text": "#0F1B2D",
            "--primary": "#0A84C6", "--teal": "#14A39A", "--danger": "#E5484D", "--warning": "#F5A524",
            "--r-sm": "10px", "--r-md": "14px", "--r-lg": "20px", "--r-xl": "28px",
            "--fs-body": "15px", "--fs-title": "17px", "--fs-h2": "22px", "--fs-display": "34px",
        }
        for name, value in expected.items():
            self.assertEqual(root.get(name), value, name)
        for name in ("--text-2", "--separator", "--primary-soft", "--teal-soft", "--danger-soft",
                     "--warning-soft", "--font", "--shadow-card", "--ease", "--s-4", "--fs-caption"):
            self.assertIn(name, root)
        self.assertIn("-apple-system", root["--font"])

    def test_design_tokens_dark(self):
        dark = block(self.css, "body.dark-mode")
        expected = {"--bg": "#0B0F14", "--surface": "#151B23", "--text": "#E8EEF5", "--text-2": "#8592A3",
                     "--primary": "#3FA9E8", "--teal": "#2EC4B6", "--danger": "#FF6B6B", "--shadow-card": "none"}
        for name, value in expected.items():
            self.assertEqual(dark.get(name), value, name)

    def test_telegram_theme_tokens_only_in_tg_light(self):
        tg = block(self.css, "body.tg-light")
        self.assertIn("--tg-theme-secondary-bg-color", tg["--bg"])
        self.assertIn("--tg-theme-bg-color", tg["--surface"])
        self.assertNotIn("--tg-theme", self.css[:self.css.index("body.tg-light")])     # :root fallback qat'iy

    def test_legacy_names_alias_new_tokens_on_root_and_body(self):
        m = re.search(r"^:root, body\s*\{(.*?)\}", self.css, re.M | re.S)
        self.assertIsNotNone(m, "eski nomlar :root VA body da e'lon qilinishi kerak (dark-mode uchun)")
        legacy = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))
        self.assertEqual(legacy["--bg-color"].strip(), "var(--bg)")
        self.assertEqual(legacy["--text-color"].strip(), "var(--text)")
        self.assertEqual(legacy["--color-primary"].strip(), "var(--primary)")
        self.assertEqual(legacy["--accent-red"].strip(), "var(--danger)")

    def test_no_external_fonts_or_icon_fonts(self):
        self.assertNotIn("Outfit", self.css)
        self.assertNotIn("Font Awesome", self.css)


if __name__ == "__main__":
    unittest.main()
