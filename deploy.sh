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
  systemctl enable "$SERVICE" >/dev/null 2>&1 || true
  echo "    Servis fayli yangilandi."
else
  echo "    O'zgarmagan."
fi

echo "==> 4. Bot qayta ishga tushirilmoqda..."
systemctl restart "$SERVICE"
sleep 8

if systemctl is-active --quiet "$SERVICE"; then
  echo "✅ Bot ishlayapti! Versiya: $(git log -1 --format='%h — %s')"
else
  echo "❌ Bot ishga tushmadi! Oxirgi loglar:"
  journalctl -u "$SERVICE" -n 40 --no-pager
  exit 1
fi

echo "--- Oxirgi loglar ---"
journalctl -u "$SERVICE" -n 15 --no-pager
