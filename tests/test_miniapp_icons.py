"""
test_miniapp_icons.py — redesign 4.3: FontAwesome va Google Fonts CDN yo'q; barcha ikonkalar inline SVG sprite'dan.
Ishlatilgan har bir ikonka sprite'da mavjud bo'lishi shart (aks holda bo'sh joy ko'rinadi).
"""
import os
import re
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(PROJECT_DIR, "app")


def read(name):
    with open(os.path.join(APP, name), encoding="utf-8") as f:
        return f.read()


class IconsTest(unittest.TestCase):
    def setUp(self):
        self.html = read("index.html")
        self.js = read("app.js")
        self.symbols = set(re.findall(r'<symbol id="i-([\w-]+)" viewBox="0 0 24 24">', self.html))

    def test_no_external_cdn(self):
        for needle in ("fontawesome", "font-awesome", "fonts.googleapis", "fonts.gstatic", "cdnjs"):
            self.assertNotIn(needle, self.html.lower(), needle)
        srcs = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https?://[^"]+)"', self.html)
        self.assertEqual(srcs, ["https://telegram.org/js/telegram-web-app.js"])   # yagona tashqi so'rov

    def test_no_fontawesome_classes_left(self):
        self.assertEqual(re.findall(r"fa-solid|fa-regular|class=\"fa-", self.html + self.js), [])

    def test_spec_icon_set_present(self):
        required = {"phone", "siren", "heart-pulse", "stethoscope", "pill", "book", "calculator", "droplet", "flame",
                    "brain", "chart", "user", "chevron-right", "chevron-left", "x", "star", "gift", "crown", "clock",
                    "search", "moon", "sun", "sparkles", "shield-check", "activity"}
        self.assertEqual(required - self.symbols, set())

    def test_every_used_icon_exists_in_sprite(self):
        used = set(re.findall(r'href="#i-([\w-]+)"', self.html))
        used |= set(re.findall(r"svgIcon\('([\w-]+)'", self.js))
        used |= set(re.findall(r"'fa-[\w-]+': '([\w-]+)'", self.js))        # FA_ICON_MAP qiymatlari
        used |= {"activity"}                                              # iconName() zaxirasi
        self.assertTrue(used)
        self.assertEqual(used - self.symbols, set())

    def test_data_icon_names_are_mapped(self):
        data_icons = set(re.findall(r'icon: "(fa-[\w-]+)"', self.js))
        mapped = set(re.findall(r"'(fa-[\w-]+)': '[\w-]+'", self.js))
        self.assertTrue(data_icons)
        self.assertEqual(data_icons - mapped, set())

    def test_icon_only_buttons_have_labels(self):
        btn = re.search(r'<button[^>]*id="theme-toggle-btn"[^>]*>', self.html).group(0)
        self.assertIn("aria-label", btn)


if __name__ == "__main__":
    unittest.main()
