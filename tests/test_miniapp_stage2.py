"""
test_miniapp_stage2.py — Mini App 2-bosqich: stack trace/alert, mojibake, avatar, ko'p oqimli server, headerlar.

Server faqat 127.0.0.1 da vaqtinchalik portda ishga tushiriladi (tashqi tarmoq yo'q).
"""
import functools
import http.client
import os
import re
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(PROJECT_DIR, "app")
sys.path.insert(0, PROJECT_DIR)

import app_server  # noqa: E402


def read(name):
    with open(os.path.join(APP_DIR, name), encoding="utf-8") as f:
        return f.read()


class StaticChecksTest(unittest.TestCase):
    def setUp(self):
        self.js = read("app.js")

    def test_no_stack_trace_shown_to_user(self):
        for i, line in enumerate(self.js.splitlines(), 1):
            if re.search(r"\.stack\b", line):
                self.assertIn("console.", line, f"app.js:{i} stack trace foydalanuvchiga ko'rinishi mumkin")

    def test_alert_only_inside_notify(self):
        for i, line in enumerate(self.js.splitlines(), 1):
            if re.search(r"(?<![.\w])alert\(", line):
                self.assertIn("tg.showAlert(msg)", line, f"app.js:{i} to'g'ridan-to'g'ri alert()")

    def test_helpers_defined(self):
        self.assertIn("function notify(msg)", self.js)
        self.assertIn("function reportError(where, err)", self.js)

    def test_no_replacement_character(self):
        for name in os.listdir(APP_DIR):
            path = os.path.join(APP_DIR, name)
            if os.path.isfile(path):
                self.assertNotIn("�", read(name), f"{name} da buzilgan belgi (U+FFFD) bor")

    def test_avatar_built_with_dom_not_innerhtml(self):
        self.assertNotIn("avatarEl.innerHTML", self.js)
        self.assertIn("avatarEl.replaceChildren(img)", self.js)
        self.assertIn(".avatar-img", read("style.css"))


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(app_server.MiniAppHandler, directory=APP_DIR)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            resp.read()
            return resp
        finally:
            conn.close()

    def test_server_class_is_threading(self):
        src = open(os.path.join(PROJECT_DIR, "app_server.py"), encoding="utf-8").read()
        self.assertIn("ThreadingHTTPServer((", src)
        self.assertNotRegex(src, r"(?<!Threading)HTTPServer\(\(")

    def test_security_headers_on_all_responses(self):
        for path in ("/", "/style.css", "/app.js"):
            resp = self.get(path)
            self.assertEqual(resp.status, 200, path)
            self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff", path)
            self.assertEqual(resp.getheader("Referrer-Policy"), "strict-origin-when-cross-origin", path)

    def test_index_versions_still_replaced(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/")
        body = conn.getresponse().read().decode("utf-8")
        conn.close()
        self.assertNotIn("__CSS_VERSION__", body)
        self.assertNotIn("__JS_VERSION__", body)

    def test_slow_client_does_not_block_others(self):
        # Ochiq, hech narsa yubormagan ulanish boshqa so'rovni bloklamasligi kerak
        import socket
        stuck = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            resp = self.get("/style.css")
            self.assertEqual(resp.status, 200)
        finally:
            stuck.close()


if __name__ == "__main__":
    unittest.main()
