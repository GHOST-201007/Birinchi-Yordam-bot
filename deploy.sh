#!/usr/bin/env bash
# Birinchi Yordam Bot — serverni GitHub'dagi oxirgi kod bilan yangilash.
# Serverda qo'lda:  bash /root/Birinchi-Yordam-bot/deploy.sh
# Servis fayllari (/etc/systemd/system/birinchi-yordam-*.service), .env va *.db ga TEGMAYDI.
set -euo pipefail

APP_DIR="/root/Birinchi-Yordam-bot"
BRANCH="main"
BOT_SERVICE="birinchi-yordam-bot"
APP_SERVICE="birinchi-yordam-app"

cd "$APP_DIR"

echo "==> 1. GitHub'dan kod olinmoqda ($BRANCH)..."
OLD_REV=$(git rev-parse HEAD)
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
NEW_REV=$(git rev-parse HEAD)

if [ "$OLD_REV" = "$NEW_REV" ]; then
  echo "    Yangi o'zgarish yo'q ($NEW_REV). Baribir qayta ishga tushiriladi."
else
  echo "    $OLD_REV -> $NEW_REV"
  git diff --stat "$OLD_REV" "$NEW_REV" | tail -15 | sed 's/^/      /'
fi

echo "==> 2. Kutubxonalar..."
if [ "$OLD_REV" != "$NEW_REV" ] && git diff --name-only "$OLD_REV" "$NEW_REV" | grep -q '^requirements.txt$'; then
  ./venv/bin/pip install -q -r requirements.txt
  echo "    requirements.txt o'zgargan — o'rnatildi."
else
  echo "    O'zgarmagan."
fi

echo "==> 3. Servislar qayta ishga tushirilmoqda..."
systemctl restart "$APP_SERVICE"
systemctl restart "$BOT_SERVICE"
sleep 10

FAIL=0
for s in "$APP_SERVICE" "$BOT_SERVICE"; do
  if systemctl is-active --quiet "$s"; then
    echo "    ✅ $s ishlayapti"
  else
    echo "    ❌ $s ishlamayapti! Loglar:"
    journalctl -u "$s" -n 40 --no-pager
    FAIL=1
  fi
done

echo "--- Bot loglari (oxirgi 15 qator) ---"
journalctl -u "$BOT_SERVICE" -n 15 --no-pager || true

if [ "$FAIL" = "1" ]; then
  exit 1
fi
echo "✅ Deploy tugadi. Versiya: $(git log -1 --format='%h — %s')"
