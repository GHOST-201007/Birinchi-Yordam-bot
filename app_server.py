"""
app_server.py - Mini App uchun maxsus HTTP server.
"""
import os
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
PORT = int(os.environ.get("PORT", 8000))

def get_file_version(filepath):
    try:
        mtime = os.path.getmtime(filepath)
        return str(int(mtime))[-6:]
    except OSError:
        return "1"

# Content-Security-Policy: faqat kerakli manbalar.
# - script: o'zimiz + Telegram WebApp SDK (telegram.org); inline script va eval yo'q
# - style: faqat style.css (inline style atributlari yo'q; JS dagi element.style — CSSOM, ruxsat etilgan)
# - img: o'zimiz, data: (SVG/canvas), Telegram profil rasmi (t.me)
# - connect: o'zimiz (/api/..., body_map_data.json)
# - frame-ancestors: Telegram Web (web.telegram.org va boshqa *.telegram.org) iframe'da ochadi
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://telegram.org",
    "style-src 'self'",
    "img-src 'self' data: https://t.me https://*.telegram.org",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org",
])


class MiniAppHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", ""):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        elif "?v=" in self.path:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "public, max-age=300")
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", ""):
            self._serve_index_with_versions()
        else:
            super().do_GET()

    def _serve_index_with_versions(self):
        index_path = os.path.join(APP_DIR, "index.html")
        css_path = os.path.join(APP_DIR, "style.css")
        js_path = os.path.join(APP_DIR, "app.js")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            css_version = get_file_version(css_path)
            js_version = get_file_version(js_path)
            content = content.replace("__CSS_VERSION__", css_version)
            content = content.replace("__JS_VERSION__", js_version)
            encoded = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except Exception as e:
            self.send_error(500, f"index.html yuklashda xato: {e}")

    def log_message(self, format, *args):
        if args and len(args) >= 2 and str(args[1]) == "200":
            return
        super().log_message(format, *args)

if __name__ == "__main__":
    os.chdir(APP_DIR)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), MiniAppHandler)
    print(f"Mini App server ishga tushdi: http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
