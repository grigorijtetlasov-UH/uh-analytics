"""
Одноразовий скрипт для отримання Google Ads Refresh Token.

ЯК ЗАПУСТИТИ:
  1) Заповни CLIENT_ID і CLIENT_SECRET (отримаєш їх у Google Cloud Console)
  2) python get_gads_refresh_token.py
  3) Браузер відкриється — авторизуйся через Google аккаунт що має доступ до Google Ads
  4) Дозволь застосунку доступ до Ads
  5) Скопіюй refresh_token який виведе скрипт у консоль
  6) Збережи його в env: GADS_REFRESH_TOKEN=...

ОДНОРАЗОВО — refresh_token не протухає (роками жиє якщо не відкличеш).
"""
import urllib.parse
import webbrowser
import http.server
import socketserver
import requests
import json
import threading
import sys

# ─── ЗАМІНИ НА СВОЇ ─────────────────────────────────────────────
CLIENT_ID     = ""   # ← з Google Cloud Console (OAuth Client ID)
CLIENT_SECRET = ""   # ← з Google Cloud Console (OAuth Client Secret)
# ────────────────────────────────────────────────────────────────

REDIRECT_URI = "http://localhost:8765/callback"
SCOPE        = "https://www.googleapis.com/auth/adwords"
PORT         = 8765

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ Заповни CLIENT_ID і CLIENT_SECRET у скрипті перед запуском.")
    print("   Отримати їх: Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
    sys.exit(1)

# Збираємо authorization URL
auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    + urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",   # обовʼязково consent — щоб отримати refresh_token
    })
)

print("\n" + "=" * 70)
print("  Google Ads OAuth — отримання refresh_token")
print("=" * 70)
print(f"\n📂 Зараз відкрию браузер. Авторизуйся через акаунт у якого є доступ до Google Ads.")
print(f"   Якщо браузер не відкрився — скопіюй URL вручну:\n   {auth_url}\n")

received_code = {"value": None}

class CallbackHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/callback"):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            code = params.get("code", [None])[0]
            if code:
                received_code["value"] = code
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("""
                <html><body style='font-family:sans-serif;padding:40px;text-align:center'>
                  <h1>✅ Авторизація успішна</h1>
                  <p>Можеш закрити це вікно і повернутися в термінал.</p>
                </body></html>
                """.encode("utf-8"))
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code received")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # тиша


def run_server():
    with socketserver.TCPServer(("localhost", PORT), CallbackHandler) as httpd:
        while received_code["value"] is None:
            httpd.handle_request()


# Запускаємо сервер у фоні і відкриваємо браузер
threading.Thread(target=run_server, daemon=True).start()
webbrowser.open(auth_url)

print("⏳ Чекаю на авторизацію в браузері...\n")
import time
for _ in range(300):  # макс 5 хв
    if received_code["value"]:
        break
    time.sleep(1)

if not received_code["value"]:
    print("❌ Таймаут. Запусти скрипт знову.")
    sys.exit(1)

code = received_code["value"]
print(f"✅ Отримано authorization code")

# Обмінюємо code на refresh_token
print("⏳ Обмінюю code на refresh_token...")
token_resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code":          code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }
)

if token_resp.status_code != 200:
    print(f"❌ Помилка обміну: {token_resp.status_code}")
    print(token_resp.text)
    sys.exit(1)

data = token_resp.json()
refresh_token = data.get("refresh_token")
access_token  = data.get("access_token")

if not refresh_token:
    print("❌ refresh_token не повернувся. Можливо ти вже авторизовував цей застосунок раніше.")
    print("   Зайди https://myaccount.google.com/permissions, відклич доступ застосунку, і спробуй знову.")
    sys.exit(1)

print("\n" + "=" * 70)
print("  ✅ ГОТОВО")
print("=" * 70)
print(f"\nДодай у env (або у GitHub Secrets):\n")
print(f"  GADS_REFRESH_TOKEN={refresh_token}")
print(f"\n(access_token: {access_token[:20]}... — це короткоживуча штука, не зберігай)")
print()
