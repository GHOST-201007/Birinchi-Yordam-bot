#!/usr/bin/env bash
# Birinchi Yordam Bot — serverni GitHub'dagi oxirgi kod bilan yangilash.
# Serverda ishga tushirish:  bash /root/Birinchi-Yordam-bot/deploy.sh
set -euo pipefail

APP_DIR="/root/Birinchi-Yordam-bot"
SERVICE="birinchiyordam"
BRANCH="main"

cd "$APP_DIR"

echo "==> 1. GitHub'dan kod olinmoqda ($BRANCH)..."
OLD_REV=$(git rev-parse HEAD)
git fetch origin "$BRANCH"
# .env va *.db .gitignore'da, shuning uchun ular o'zgarmaydi
git reset --hard "origin/$BRANCH"
NEW_REV=$(git rev-parse HEAD)

if [ "$OLD_REV" = "$NEW_REV" ]; then
  echo "    Yangi o'zgarish yo'q ($NEW_REV). Baribir qayta ishga tushiriladi."
else
  echo "    O'zgargan fayllar:"
  git diff --stat "$OLD_REV" "$NEW_REV" | sed 's/^/      /'
fi

echo "==> 2. Kutubxonalar tekshirilmoqda..."
if [ ! -d venv ]; then
  python3 -m venv venv
fi
if [ "$OLD_REV" != "$NEW_REV" ] && git diff --name-only "$OLD_REV" "$NEW_REV" | grep -q '^requirements.txt$'; then
  ./venv/bin/pip install -q -r requirements.txt
  echo "    requirements.txt o'zgargan — o'rnatildi."
else
  ./venv/bin/pip install -q -r requirements.txt >/dev/null
  echo "    OK."
fi

echo "==> 3. Systemd servis fayli tekshirilmoqda..."
if ! cmp -s birinchiyordam.service "/etc/systemd/system/$SERVICE.service"; then
  cp birinchiyordam.service "/etc/systemd/system/$SERVICE.service"
  systemctl daemon-reload
  echo "    Servis fayli yangilandi."
else
  echo "    O'zgarmagan."
fi
# Server qayta yoqilganda bot o'zi ishga tushishi uchun
systemctl enable "$SERVICE" >/dev/null 2>&1 || true

# Qo'lda ishga tushirilgan eski nusxalar bo'lsa to'xtatamiz (aks holda Telegram "Conflict" xatosi beradi)
systemctl stop "$SERVICE" 2>/dev/null || true
pkill -f "$APP_DIR/.*(run_dev|run_prod|bot|app_server)\.py" 2>/dev/null || true
pkill -f "(run_dev|run_prod|bot|app_server)\.py" 2>/dev/null || true
pkill -f "cloudflared tunnel --url http://127.0.0.1:8000" 2>/dev/null || true
sleep 2

echo "==> 4. Bot qayta ishga tushirilmoqda..."
systemctl restart "$SERVICE"
sleep 20

if systemctl is-active --quiet "$SERVICE"; then
  echo "✅ Bot ishlayapti! Versiya: $(git log -1 --format='%h — %s')"
else
  echo "❌ Bot ishga tushmadi! Oxirgi loglar:"
  journalctl -u "$SERVICE" -n 40 --no-pager
  exit 1
fi

echo "--- Oxirgi loglar ---"
journalctl -u "$SERVICE" -n 15 --no-pager
