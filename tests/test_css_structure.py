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
        # G palitrasi (docs/MINI_APP_G_TASK.md, 2-bo'lim)
        root = block(self.css, ":root")
        expected = {
            "--bg": "#EEF8F5", "--surface": "#FFFFFF", "--text": "#0F2A2E", "--text-2": "#4F6B6E",
            "--line": "#D7E8E3", "--line-strong": "#BFDDD6", "--primary": "#0E7C72", "--on-primary": "#FFFFFF",
            "--primary-soft": "#DCEFEC", "--body-fill": "#CFEAE4", "--seg-bg": "#DCEDE8",
            "--danger": "#B4231B", "--danger-line": "#D6453D", "--danger-soft": "#FDECEC",
            "--warning": "#9A5700", "--warning-soft": "#FFF1D6", "--info": "#075E94", "--info-soft": "#E1F0FB",
            "--r-sm": "10px", "--r-md": "14px", "--r-lg": "22px", "--r-pill": "999px",
        }
        for name, value in expected.items():
            self.assertEqual(root.get(name), value, name)
        self.assertTrue(root["--font"].startswith('"Nunito"'))
        self.assertIn("-apple-system", root["--font"])                     # tizim shrifti — zaxira

    def test_design_tokens_dark(self):
        dark = block(self.css, "body.dark-mode")
        expected = {"--bg": "#0C1517", "--surface": "#152225", "--text": "#E6F2F0", "--text-2": "#8FA9A9",
                    "--line": "#22393B", "--line-strong": "#2E4A4C", "--primary": "#3DC2B3", "--on-primary": "#06211E",
                    "--primary-soft": "#183A38", "--body-fill": "#1F3A3B", "--seg-bg": "#1A2C2E",
                    "--danger": "#FF8A8A", "--danger-line": "#FF7B7B", "--danger-soft": "#3A1D22",
                    "--warning": "#F5B544", "--warning-soft": "#3B2C10", "--info": "#7CC4F2", "--info-soft": "#12304A"}
        for name, value in expected.items():
            self.assertEqual(dark.get(name), value, name)

    def test_g_palette_not_telegram_theme(self):
        # G ning o'z palitrasi: Telegram mavzu ranglari tokenlarga aralashmaydi
        self.assertNotIn("body.tg-light", self.css)
        self.assertNotIn("--tg-theme", self.css)

    def test_legacy_names_alias_new_tokens_on_body(self):
        # Eski nomlar faqat body da (yagona :root talabi); body.dark-mode tokenlari ularda ham hisoblanadi
        m = re.search(r"^body\s*\{(\s*--bg-color.*?)\}", self.css, re.M | re.S)
        self.assertIsNotNone(m, "eski nomlar body da e'lon qilinishi kerak")
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
