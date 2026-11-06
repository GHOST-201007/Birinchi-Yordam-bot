"""
app_server.py - Mini App uchun maxsus HTTP server.
"""
import os
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Added for Mini App initData validation
import urllib.parse
import hmac
import hashlib
import datetime

def validate_init_data(init_data: str) -> bool:
    """Validate Telegram WebApp initData string.
    Returns True if data is authentic and not expired (24‑hour window).
    """
    try:
        params = urllib.parse.parse_qs(init_data, keep_blank_values=True)
        hash_vals = params.pop('hash', None)
        if not hash_vals:
            return False
        received_hash = hash_vals[0]
        sorted_items = sorted((k, v[0]) for k, v in params.items())
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_items)
        bot_token = os.getenv('BOT_TOKEN')
        if not bot_token:
            return False
        # Generate secret key as per Telegram Web Apps spec
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(hmac_hash, received_hash):
            return False
        auth_date_str = params.get('auth_date', [None])[0]
        if not auth_date_str:
            return False
        try:
            auth_ts = int(auth_date_str)
        except ValueError:
            return False
        now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        # Reject if auth_date is in the future beyond a small clock‑skew (60 s)
        if auth_ts > now_ts + 60:
            return False
        # Reject if auth_date is older than 24 h plus a small skew
        if now_ts - auth_ts > 86400 + 60:
            return False
        return True
    except Exception:
        return False

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
PORT = int(os.environ.get("PORT", 8000))

def get_file_version(filepath):
    try:
        mtime = os.path.getmtime(filepath)
        return str(int(mtime))[-6:]
    except OSError:
        return "1"

class MiniAppHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
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
    server = HTTPServer(("127.0.0.1", PORT), MiniAppHandler)
    print(f"Mini App server ishga tushdi: http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
