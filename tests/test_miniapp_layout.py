"""
test_miniapp_layout.py — index.html tuzilmasi va asosiy joylashuv.

Sabab: overlay blokini almashtirishda ortiqcha </div> #app-container ni barvaqt yopgan va pastki menyu ekrandan
tashqariga chiqib ketgan (header yashiringan). Bu test shuni qayta bo'lishiga yo'l qo'ymaydi.
"""
import os
import unittest
from html.parser import HTMLParser

from tests.e2e_base import MiniAppE2EBase

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
VOID = {"meta", "link", "input", "br", "img", "hr", "source", "use", "path", "circle", "rect", "polygon", "line"}


class Tree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.parents = {}        # id -> ota id lar ro'yxati
        self.errors = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.parents[a["id"]] = [x[1] for x in self.stack if x[1]]
        if tag not in VOID:
            self.stack.append((tag, a.get("id")))

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.parents[a["id"]] = [x[1] for x in self.stack if x[1]]

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append(f"kutilmagan </{tag}> (stek: {[t for t, _ in self.stack[-3:]]})")
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break
            return
        self.stack.pop()


class HtmlStructureTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(APP, "index.html"), encoding="utf-8") as f:
            self.tree = Tree()
            self.tree.feed(f.read())

    def test_tags_balanced(self):
        self.assertEqual(self.tree.errors, [])
        self.assertEqual([t for t, _ in self.tree.stack], [], "yopilmagan teglar")

    def test_main_parts_inside_app_container(self):
        for el in ("overlay-details", "body-map-modal", "wheel-modal", "first-aid-grid", "disease-list-container"):
            self.assertIn("app-container", self.tree.parents.get(el, []), el)

    def test_nav_inside_app_container(self):
        # nav'da id yo'q — data-tab tugmasi orqali tekshiramiz
        with open(os.path.join(APP, "index.html"), encoding="utf-8") as f:
            html = f.read()
        container = html.index('<div id="app-container">')
        nav = html.index('<nav class="app-nav"')
        self.assertLess(container, nav)


class LayoutE2ETest(MiniAppE2EBase):
    TABS = ["tab-first-aid", "tab-diseases", "tab-health", "tab-body-map"]

    def test_header_and_nav_inside_viewport_on_every_tab(self):
        page, _ = self.open_app({})
        for tab in self.TABS:
            with self.subTest(tab=tab):
                page.click(f'nav [data-tab="{tab}"]')
                header = page.locator(".app-header").bounding_box()
                nav = page.locator(".app-nav").bounding_box()
                self.assertEqual(header["y"], 0)
                self.assertAlmostEqual(nav["y"] + nav["height"], 844, delta=1)
                self.assertEqual(page.evaluate("document.body.scrollTop + document.documentElement.scrollTop"), 0)
                self.assertTrue(page.evaluate("!!document.querySelector('#app-container > .app-nav')"))


if __name__ == "__main__":
    unittest.main()
