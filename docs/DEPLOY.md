# DigitalOcean serverini yangilash (ASOSIY USUL)

## Avtomatik: `git push` → server o'zi yangilanadi
Kompyuterda o'zgarish qilgach:
```
git add .
git commit -m "nima o'zgardi"
git push
```
GitHub Actions serverga SSH orqali ulanadi va `deploy.sh` ni ishga tushiradi
(kod olinadi → kutubxonalar → bot restart → holat tekshiriladi).
Natijani GitHub repodagi **Actions** bo'limida ko'rasiz (yashil ✅ / qizil ❌).

### Bir martalik sozlash
1. **Serverda SSH kalit yaratish** (DigitalOcean konsoli yoki `ssh root@SERVER_IP`):
   ```
   ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
   cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
   cat ~/.ssh/github_deploy        # shu chiqqan matnni to'liq nusxalang
   ```
2. **GitHub → repo → Settings → Secrets and variables → Actions → New repository secret**:
   | Nomi | Qiymati |
   |---|---|
   | `DO_HOST` | Droplet IP manzili (DigitalOcean panelida) |
   | `DO_USER` | `root` |
   | `DO_SSH_KEY` | 1-qadamdagi `github_deploy` fayl matni (BEGIN...END qatorlari bilan) |
3. Agar repo **private** bo'lsa, serverda `git fetch` ishlashi uchun deploy key qo'shing:
   ```
   ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
   cat ~/.ssh/id_ed25519.pub
   ```
   Chiqqanini GitHub → repo → Settings → Deploy keys → Add key ga qo'ying va
   serverda: `cd /root/Birinchi-Yordam-bot && git remote set-url origin git@github.com:GHOST-201007/Birinchi-Yordam-bot.git`
4. Serverda birinchi marta qo'lda: `cd /root/Birinchi-Yordam-bot && git pull && bash deploy.sh`

## Qo'lda (zaxira usul)
```
ssh root@SERVER_IP
bash /root/Birinchi-Yordam-bot/deploy.sh
```

## Foydali buyruqlar (serverda)
| Vazifa | Buyruq |
|---|---|
| Bot holati | `systemctl status birinchi-yordam-bot` |
| Mini App holati | `systemctl status birinchi-yordam-app` |
| Jonli loglar | `journalctl -u birinchi-yordam-bot -f` |
| Restart | `systemctl restart birinchi-yordam-bot birinchi-yordam-app` |
| Serverdagi versiya | `cd /root/Birinchi-Yordam-bot && git log -1 --oneline` |

> `.env` va `*.db` fayllar git'da yo'q — deploy ularga tegmaydi.

### Mini App API (`/api/...`)
Bot jarayonidagi aiohttp serveri (`PORT`, default 10000) **faqat `127.0.0.1`** da tinglaydi: internetdan to'g'ridan-to'g'ri ochiq emas.
Nginx `location /api/` ni `http://127.0.0.1:10000` ga **URI o'zgartirmasdan** uzatadi (`proxy_pass` oxirida `/` yo'q), shuning uchun
endpointlar aynan shu yo'llarda: `POST /api/state`, `POST /api/spin/claim`, `POST /api/bonus/claim`, `POST /api/invoice` (`/health` — ichki tekshiruv).
`/api/invoice` tanasi `{"init_data": ..., "plan": "buy_pro_7"|"buy_plus_30"|"buy_ultra_30"}`: narx va payload faqat serverdan (`build_premium_offer`), javob `{"ok": true, "url": <Stars invoice link>}`; yangi env o'zgaruvchi kerak emas.
Har so'rovda `init_data` (Telegram WebApp imzosi) tekshiriladi; foydalanuvchi uchun daqiqasiga 20 so'rov; tana ≤ 4 KB.
Tekshirish (serverda): `curl -s -X POST https://birinchiyordam.duckdns.org/api/state -H 'Content-Type: application/json' -d '{"init_data":"buzuq"}'` → `403`.
Lokal (`run_dev.py`, cloudflare tunnel) `/api/` proksilanmaydi — Mini App u yerda URL-parametr zaxira yo'lida ishlaydi.

### Admin Premium paneli (`/premium`, faqat `ADMIN_ID`)
`/premium` (admin) → userlar ro'yxati (10 tadan, ◀️ ▶️, 🔍 ID yoki @username bilan qidirish) → user kartasi → **tarif** (Pro/Plus/Ultra) → **muddat** (1/3/7/30/90 kun yoki ♾ muddatsiz) → **rejim** (📣 Xabar bilan / 🤫 Sirli) → sabab (faqat "Xabar bilan") → tasdiqlash. Olib tashlash ham shu rejimlar bilan. Oddiy userlar uchun `/premium` o'zgarmagan.
- Kunlik muddat `grant_premium_days` orqali: faol muddatga qo'shadi, yuqori tarifni saqlaydi (Ultra + 3 kun Pro → Ultra, muddat +3 kun).
- Muddatsiz: `database.set_premium_unlimited` (`premium_expires_at = NULL`); tarif limiti `premium_type` bo'yicha. **Muddatsiz Premiumli userga kunlik muddat berilmaydi** — avval olib tashlash kerak.
- Har bir o'zgarish logda: `journalctl -u birinchi-yordam-bot | grep "ADMIN PREMIUM"` (admin, user, tarif, muddat, rejim). Bazaga tarix yozilmaydi. Yangi env o'zgaruvchi va migratsiya yo'q.
- "Xabar bilan" rejimida user botni bloklagan bo'lsa Premium baribir beriladi/olinadi, adminga ogohlantirish chiqadi.

### Premium ko'rinib turishi (mini app va bot)
Premiumi bor foydalanuvchi buni mini appda ham, botda ham doim ko'radi; bepul foydalanuvchida hech narsa o'zgarmaydi.
- **Holat bitta joydan:** `database.admin_premium_view` / `get_premium_view(user_id)` (muddati o'tgan flag — oddiy, muddatsiz ham to'g'ri; `days_left` = `ceil((tugash - hozir) / 1 kun)`, Toshkent vaqti). Bot ham, API ham shundan foydalanadi.
- **Mini app:** `/api/state` (va ai/pro_day sovrinli `/api/spin/claim`) ga `premium_expires_at` (muddatsizda `null`), `premium_unlimited`, `premium_days_left` qo'shildi. Header belgisi (`Ultra · 5 kun` / `· ♾` / `· bugun`), Sog'liq tabida "Mening Premiumim" kartasi, tugashiga ≤ 2 kun qolganda bosh ekran banneri (yopilgani `premium_expires_at` bo'yicha eslab qolinadi), tarif rangidagi aksent (`body.tier-pro|plus|ultra`).
- **Bot:** reply menyudagi `💎 Premium` tugmasi tarifga mos (`⭐ Premium Pro` / `💎 Premium Plus` / `👑 Premium Ultra`; kun soni yozilmaydi); `/start` salomiga bitta qator; Premiumi borga "Mening obunam" sahifasi (muddatsiz endi sotuv sahifasiga tushmaydi).
- **Tugash eslatmasi:** fon vazifasi (`premium_expiry_loop`, polling va webhook rejimida ham) soatiga bir marta tekshiradi: faol, muddatli Premium va qolgan vaqt ≤ 24 soat bo'lsa bitta xabar (`🔄 Uzaytirish` tugmasi bilan). Takrorlanmasligi uchun **yangi ustun `users.premium_expiry_notified_for TEXT`** — `init_db()` o'zi qo'shadi (`ADD COLUMN IF NOT EXISTS`), qo'lda hech narsa kerak emas. Muddatsiz, bepul va ban qilinganlarga yuborilmaydi; bir tekshiruvda ko'pi bilan 200 ta. Muddati o'tganlar shu vazifada yopiladi (xabarsiz). Yangi env o'zgaruvchi yo'q.
- **Chap pastdagi shaxsiy tugma:** `/start` da Premium faol bo'lsa `👑 Ilova` (faqat joriy `MINI_APP_URL`, query parametrsiz), aks holda eski shaxsiy tugma tozalanadi (mavjud mexanizm saqlangan). Admin Premium bersa — tugma qo'yiladi, olib tashlasa yoki muddat tugasa — Default ga qaytadi. Hammasi fonda, timeout bilan.
  - `MINI_APP_URL` o'zgarsa: Premium userlarning shaxsiy tugmasi bot restartdan keyin ular `/start` bosganda yangilanadi.
  - ⚠️ `scripts/reset_menu_buttons.py` ni qayta ishga tushirsangiz, Premium userlarning `👑 Ilova` tugmasi ham tozalanadi (ular `/start` bossa qaytadi).
- "🔄 Uzaytirish" mavjud xarid tugmalarini ko'rsatadi; mavjud siyosat bo'yicha faol Premiumda joriy tarifga teng yoki past tarif sotib olinmaydi (`check_premium_purchase_eligibility`) — bu o'zgartirilmagan.

### Omad baraboni (8 sovrin)
Sovrinlar **bitta joyda**: `database.SPIN_PRIZES` (kod, ehtimol). Mini App `segments` (app.js) shu kodlar bilan mos bo'lishi shart — `tests/test_spin_prizes.py` tekshiradi.

| Kod (`pending_spin_prize`) | Sovrin | Ehtimol |
|---|---|---|
| 1 / 2 / 3 / 5 | shuncha ball | 35% / 20% / 12% / 5% |
| -2 | 💡 kun maslahati (ball yo'q, `data/spin_tips.json` dan) | 15% |
| -1 | 🤖 +1 bepul AI savol (`users.spin_ai_bonus`) | 10% |
| -3 | ⭐ 1 kunlik Premium Pro (faol Plus/Ultra tarifi pasaymaydi, muddati +1 kun) | 2% |
| 0 | 🏆 SUPER: Premium Plus (30 kun) uchun 50% chegirma | 1% |

- **Migratsiya:** `users.spin_ai_bonus INTEGER DEFAULT 0` — `init_db()` bot ishga tushganda o'zi qo'shadi (`ADD COLUMN IF NOT EXISTS`), qo'lda hech narsa qilinmaydi. `pending_spin_prize` turi o'zgarmagan (INTEGER). Yangi env o'zgaruvchi yo'q.
- **Eski holat:** deploy paytida bazada `pending_spin_prize = 10` turgan bo'lsa u o'zgartirilmay +10 ball beriladi; noma'lum qiymat — +1 ball.
- **`data/spin_tips.json`** (40 ta maslahat) repo bilan keladi. Fayl yo'q/buzuq bo'lsa bitta zaxira maslahat ko'rsatiladi (logda xato).
- **AI kvota tartibi** (bot va mini app umumiy): bepul 1 ta yoki tarif kunlik limiti → u tugagach `spin_ai_bonus`. Xatoda savol o'sha manbaga qaytariladi. Bonus muddatsiz. `ai_remaining` bonusni o'z ichiga oladi, `ai_limit` — faqat tarif limiti, `ai_bonus` alohida.
- **Mini App API:** `/api/state` → `prize` (kod) + `prize_type` (`points|tip|ai|pro_day|super`) + `ai_bonus`; `/api/spin/claim` → `prize`, `prize_type`, `points`, `tip` (ai/pro_day da yana Premium holati va AI hisoblagichi); `/api/ai/chat` → `bonus`.
- **⚠️ Eski kodga qaytarishdan OLDIN** (rollback): eski kod `pending_spin_prize` ning noma'lum qiymatini (-1, -2, -3) 10 ball deb beradi. Avval serverda: `UPDATE users SET pending_spin_prize = NULL WHERE pending_spin_prize < 0;` (ustun `spin_ai_bonus` qolaveradi — zararsiz).

### Telegram webhook (ixtiyoriy — polling o'rniga)
Standart rejim — **polling** (hech narsa o'zgarmaydi). `.env` da quyidagi **ikkalasi** ham berilsa, bot **webhook** rejimida ishlaydi:

| O'zgaruvchi | Misol | Izoh |
|---|---|---|
| `WEBHOOK_BASE_URL` | `https://birinchiyordam.duckdns.org` | `https://` majburiy (Telegram talabi); oxirida `/` shart emas |
| `WEBHOOK_SECRET` | `Zk3...` | 1–256 belgi, **faqat** `A-Z a-z 0-9 _ -`. Yaratish: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |

Faqat bittasi berilsa — polling davom etadi (logda ogohlantirish). `https://` bo'lmasa yoki secret'da ruxsat etilmagan belgi bo'lsa — bot ishga tushmaydi (xato matni logda, secret chiqarilmaydi).

**Qanday ishlaydi.** Route — mavjud aiohttp ilovasida (`127.0.0.1:PORT`, yangi port yo'q): `POST /api/tg/webhook`. Nginx `/api/` ni allaqachon shu portga uzatadi, **nginx o'zgarmaydi**.
Himoya faqat `X-Telegram-Bot-Api-Secret-Token` sarlavhasi (noto'g'ri yoki yo'q bo'lsa `401`); `/api/` rate-limit va `init_data` tekshiruvi bu route'ga qo'llanmaydi.
Ilovaning umumiy tana chegarasi 1 MB (Telegram update uchun); Mini App `/api/*` route'lari o'z chegarasini (4 KB / `/api/ai/chat` 16 KB) o'zi qo'llaydi — amalda o'zgarmagan.
Middleware'lar, dori eslatmalari, engagement scheduler va FSM ikkala rejimda bir xil ishlaydi.

**Yoqish (serverda):**
1. Avval kodni deploy qiling (`.env` hali o'zgarmagan — bot polling'da qayta ishga tushadi).
2. `.env` ga qo'shing: `WEBHOOK_BASE_URL=...` va `WEBHOOK_SECRET=...`
3. `sudo systemctl restart birinchi-yordam-bot`
4. Tekshirish:
   - `journalctl -u birinchi-yordam-bot -n 50 --no-pager` → `Webhook rejimi: webhook o'rnatildi: https://.../api/tg/webhook`
   - `curl -s https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo` → `url` to'g'ri, `last_error_message` yo'q, `pending_update_count` kichik (tokenni chatga/skrinshotga qo'ymang)
   - `curl -i -X POST https://birinchiyordam.duckdns.org/api/tg/webhook -H 'Content-Type: application/json' -d '{}'` → `401` (secret'siz rad etiladi)
   - botga `/start` yuboring.

**Polling'ga qaytarish:**
1. `.env` dan `WEBHOOK_BASE_URL` va `WEBHOOK_SECRET` qatorlarini o'chiring (yoki `#` bilan izohlang).
2. `sudo systemctl restart birinchi-yordam-bot` — polling boshlanishida bot o'zi `delete_webhook(drop_pending_updates=False)` chaqiradi, navbatdagi update'lar yo'qolmaydi.

**Eslatmalar.**
- Webhook rejimida to'xtatish/restartda `delete_webhook` **chaqirilmaydi**: restart paytida Telegram update'larni navbatda ushlab turadi. To'xtatishda (SIGTERM/SIGINT) ishlayotgan update'lar 30 soniyagacha kutiladi; serverdagi unit faylda `TimeoutStopSec` 30 soniyadan kam bo'lmasligi kerak (default 90 s).
- Bitta bot tokeni uchun polling va webhook bir vaqtda bo'lmaydi. Boshqa joyda (masalan, kompyuterda `run_dev.py`) **production tokeni bilan** polling ishga tushsa, u webhook'ni o'chirib yuboradi va server update olmay qoladi. Lokalda faqat alohida TEST bot tokeni ishlating; lokal `.env` ga `WEBHOOK_*` ni qo'ymang.

### Serverdagi tuzilma
- Bot: `birinchi-yordam-bot.service` (venv/bin/python bot.py)
- Mini App: `birinchi-yordam-app.service` (app_server.py, nginx orqali `https://birinchiyordam.duckdns.org`)
- `run_dev.py` (cloudflare tunnel) serverda ISHLATILMAYDI — u `.env` dagi `MINI_APP_URL` ni buzadi.

---

# Birinchi Yordam Bot — Deployment Checklist

## Har yangilashda bajariladigan qadamlar

### 1. Kod yangilash
```
git pull
```
yoki fayllarni serverga nusxalash.

### 2. Dependencies (kutubxonalar)
```
pip install -r requirements.txt
```

### 3. Database (ma'lumotlar bazasi)
Database — **PostgreSQL (Neon)**, ulanish `.env` dagi `DATABASE_URL` orqali.
`init_db()` funksiyasi bot ishga tushganida `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
orqali yangi ustunlarni xavfsiz qo'shadi. Hech qanday qo'shimcha amal talab qilinmaydi.

> Lokal `users.db` / `pending_reconcile.db` fayllari git'da yo'q va ularni o'chirmang.
> `pending_reconcile.db` — DB xatosi tufayli saqlanmagan to'lovlar dalili (`/reconcile` uchun).

### 4. .env fayli tekshiruvi
`.env` faylida quyidagilar to'g'ri ekanligini tekshiring:
```
BOT_TOKEN=...
GEMINI_API_KEY=...
DATABASE_URL=postgresql://...   # Neon
ADMIN_ID=...
ADMIN_USERNAME=...
MINI_APP_URL=...                # serverda doimiy domen; lokalda run_dev.py yangilaydi
PRO_TRIAL_STARS=50              # Pro 7 kun
PRO_MONTHLY_STARS=150           # Plus 30 kun (SUPER PRIZ chegirmasi = yarmi)
ULTRA_MONTHLY_STARS=300         # Ultra 30 kun
PREMIUM_STARS_PRICE=50          # xabarlardagi "... Stars dan boshlab" matni uchun
# Ixtiyoriy: ikkalasi ham bo'lsa webhook rejimi, bo'lmasa polling (batafsil: yuqoridagi "Telegram webhook")
# WEBHOOK_BASE_URL=https://birinchiyordam.duckdns.org
# WEBHOOK_SECRET=...            # faqat A-Z a-z 0-9 _ -
```

### Bir martalik qo'lda bajariladigan buyruqlar (serverda)
| Qachon | Buyruq |
|---|---|
| P0-1 tuzatishi deploy qilingandan keyin (bir marta) | `venv/bin/python scripts/purge_ai_chat_cache.py` |
| Eski trycloudflare shaxsiy menyu tugmalarini o'chirish (bir marta). Avval sinov: | `venv/bin/python scripts/reset_menu_buttons.py --dry-run` |
| ...so'ng haqiqiy ishga tushirish (soniyasiga <= 20 so'rov; trafik kam paytda) | `venv/bin/python scripts/reset_menu_buttons.py` |

---

## Lokal ishga tushirish (faqat kompyuterda, serverda EMAS)

### 5. Eski jarayonlarni to'xtatish
Agar bot allaqachon ishlayotgan bo'lsa:
- Terminaldagi `run_dev.py` jarayonini `Ctrl+C` bilan to'xtating.
- Task Manager dan qolgan python.exe jarayonlarini tekshiring.

### 6. Ishga tushirish
`run_dev.py` botning UMUMIY menyu tugmasini ham trycloudflare manziliga o'zgartiradi, shuning uchun production
`BOT_TOKEN` bilan ishlatilsa hamma foydalanuvchilar uchun Mini App buziladi. Himoya: `RUN_DEV_ALLOWED=1` shell
muhitida berilmasa u hech narsa qilmasdan to'xtaydi (`.env` dagi qiymat hisobga olinmaydi). Faqat alohida TEST bot
tokeni bilan:
```
$env:RUN_DEV_ALLOWED="1"; python run_dev.py      # PowerShell
RUN_DEV_ALLOWED=1 python run_dev.py              # bash
```

Bu quyidagilarni bajaradi:
- Port 8000 da `app_server.py` ni ishga tushiradi (Mini App)
- Cloudflare tunnel orqali yangi URL oladi
- `.env` dagi `MINI_APP_URL` ni yangi URL bilan yangilaydi
- Telegram botni ishga tushiradi

### 7. Tekshirish

#### Telegram komandalar
- Botga `/start` yuboring → klaviatura yangi ko'rinishda kelishi kerak
- Admin sifatida `/stats` yuboring → ishlashi kerak
- Oddiy foydalanuvchi sifatida `/stats` yuboring → "Huquq yo'q" xatosi kelishi kerak

#### Mini App
- Botdagi "Mini Ilova" tugmasini bosing
- Brauzer developer tools (F12) → Network → `index.html` yuklanishini tekshiring
- `style.css` va `app.js` uchun URL da `?v=XXXXXX` qo'shilgan bo'lishi kerak
- Versiya raqami CSS/JS fayli oxirgi o'zgartirish vaqtiga mos bo'lishi kerak

#### Reply Keyboard
- Har qanday tugmani bosing → yangi menyu kelishi kerak
- "🌐 Mening ballarim" tugmasini bosing → ball ko'rsatilishi va menyu yangilanishi kerak

---

## Mini App statik fayllarini yangilash

CSS yoki JS ni o'zgartirgandan keyin:
1. Faylni saqlang
2. Botni qayta ishga tushirmang (zarur emas)
3. Mini Appni yoping va qayta oching

`app_server.py` fayl o'zgartirish vaqtini avtomatik versiya sifatida ishlatadi.
Foydalanuvchi keyingi safar Mini Appni ochganda yangi versiyani yuklab oladi.

### Content-Security-Policy
`app_server.py` har bir javobga `Content-Security-Policy` sarlavhasini qo'shadi (`CSP` o'zgaruvchisi): skriptlar faqat
o'zimizdan va `https://telegram.org` (WebApp SDK), inline style/script yo'q, `/api/` bir xil manbada.
Nginx o'zi alohida CSP qo'shmasligi kerak (ikki siyosat birlashib, qattiqroq bo'lib qoladi).
Yangi tashqi manba (CDN, rasm domeni) qo'shilsa — `CSP` ga ham qo'shing, aks holda brauzer uni bloklaydi.

---

## Telegram komanda menyusini yangilash

Komanda menyusini o'zgartirsangiz (bot.py dagi `set_bot_commands` funksiyasi):
1. Botni qayta ishga tushiring
2. Telegram bot `set_my_commands` ni bot ishga tushganida chaqiradi
3. Foydalanuvchilar yangi komandalarni ko'radi (10-30 daqiqa ichida)

---

## APP_VERSION ni yangilash

`bot.py` dagi `APP_VERSION` qiymatini kattalashtirish kerak bo'lgan hollar:
- Mini App UI da katta o'zgarishlar bo'lganda
- app.js yoki style.css da muhim funksional o'zgarishlar bo'lganda

O'zgartirish uchun `bot.py` dagi shu qatorni toping:
```python
APP_VERSION = "1.1.0"
```
Va versiyani o'zgartiring, masalan `"1.2.0"`.

---

## Nima avtomatik yangilanadi?
| Narsa | Qachon yangilanadi |
|---|---|
| Bot mantiqi (handlers) | Bot qayta ishga tushganda |
| Telegram komanda menyusi | Bot qayta ishga tushganda |
| Reply Keyboard | Foydalanuvchi keyingi xabar yuborganda |
| Mini App HTML | Foydalanuvchi Mini Appni keyingi ochganda |
| Mini App CSS/JS | Foydalanuvchi Mini Appni keyingi ochganda (auto-versiya tufayli) |
| Database yangi ustunlar | Bot qayta ishga tushganda (init_db() chaqiriladi) |

## Nima qayta ishga tushirishni talab qiladi?
| Narsa | Shart |
|---|---|
| bot.py o'zgarishi | Ha, bot restart kerak |
| database.py o'zgarishi | Ha, bot restart kerak |
| .env o'zgarishi | Ha, bot restart kerak |
| app/index.html o'zgarishi | Yo'q, avtomatik (app_server.py tufayli) |
| app/style.css o'zgarishi | Yo'q, avtomatik (auto-versiya tufayli) |
| app/app.js o'zgarishi | Yo'q, avtomatik (auto-versiya tufayli) |
