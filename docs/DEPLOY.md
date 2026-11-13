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
endpointlar aynan shu yo'llarda: `POST /api/state`, `POST /api/spin/claim`, `POST /api/bonus/claim`, `POST /api/points/redeem`, `POST /api/invoice`, `POST /api/ai/chat` (`/health` — ichki tekshiruv).
`/api/invoice` tanasi `{"init_data": ..., "plan": "buy_pro_7"|"buy_plus_30"|"buy_ultra_30"}`: narx va payload faqat serverdan (`build_premium_offer`), javob `{"ok": true, "url": <Stars invoice link>}`; yangi env o'zgaruvchi kerak emas.
Har so'rovda `init_data` (Telegram WebApp imzosi) tekshiriladi; foydalanuvchi uchun daqiqasiga 20 so'rov; tana ≤ 4 KB.
Tekshirish (serverda): `curl -s -X POST https://birinchiyordam.duckdns.org/api/state -H 'Content-Type: application/json' -d '{"init_data":"buzuq"}'` → `403`.
Lokal (`run_dev.py`, cloudflare tunnel) `/api/` proksilanmaydi — Mini App u yerda URL-parametr zaxira yo'lida ishlaydi.

### Admin Premium paneli (`/premium`, faqat `ADMIN_ID`)
`/premium` (admin) → userlar ro'yxati (10 tadan, ◀️ ▶️, 🔍 ID yoki @username bilan qidirish) → user kartasi → **tarif** (⭐ Plus / 💎 Pro / 👑 Ultra) → **muddat** (1/3/7/30/90 kun yoki ♾ muddatsiz) → **rejim** (📣 Xabar bilan / 🤫 Sirli) → sabab (faqat "Xabar bilan") → tasdiqlash. Olib tashlash ham shu rejimlar bilan. Oddiy userlar uchun `/premium` o'zgarmagan.
- Kunlik muddat `grant_premium_days` orqali: faol muddatga qo'shadi, yuqori tarifni saqlaydi (Ultra + 3 kun Plus → Ultra, muddat +3 kun).
- Muddatsiz: `database.set_premium_unlimited` (`premium_expires_at = NULL`); tarif limiti `premium_type` bo'yicha. **Muddatsiz Premiumli userga kunlik muddat berilmaydi** — avval olib tashlash kerak.
- Har bir o'zgarish logda: `journalctl -u birinchi-yordam-bot | grep "ADMIN PREMIUM"` (admin, user, tarif, muddat, rejim). Bazaga tarix yozilmaydi. Yangi env o'zgaruvchi va migratsiya yo'q.
- "Xabar bilan" rejimida user botni bloklagan bo'lsa Premium baribir beriladi/olinadi, adminga ogohlantirish chiqadi.

### Premium ko'rinib turishi (mini app va bot)
Premiumi bor foydalanuvchi buni mini appda ham, botda ham doim ko'radi; bepul foydalanuvchida hech narsa o'zgarmaydi.
- **Holat bitta joydan:** `database.admin_premium_view` / `get_premium_view(user_id)` (muddati o'tgan flag — oddiy, muddatsiz ham to'g'ri; `days_left` = `ceil((tugash - hozir) / 1 kun)`, Toshkent vaqti). Bot ham, API ham shundan foydalanadi.
- **Mini app:** `/api/state` (va ai/pro_day sovrinli `/api/spin/claim`) ga `premium_expires_at` (muddatsizda `null`), `premium_unlimited`, `premium_days_left` qo'shildi. Header belgisi (`Ultra · 5 kun` / `· ♾` / `· bugun`), Sog'liq tabida "Mening Premiumim" kartasi, tugashiga ≤ 2 kun qolganda bosh ekran banneri (yopilgani `premium_expires_at` bo'yicha eslab qolinadi), tarif rangidagi aksent (`body.tier-pro|plus|ultra`).
- **Bot:** reply menyudagi `💎 Premium` tugmasi tarifga mos (`⭐ Premium Plus` / `💎 Premium Pro` / `👑 Premium Ultra`; kun soni yozilmaydi); `/start` salomiga bitta qator; Premiumi borga "Mening obunam" sahifasi (muddatsiz endi sotuv sahifasiga tushmaydi).
- **Tugash eslatmasi:** fon vazifasi (`premium_expiry_loop`, polling va webhook rejimida ham) soatiga bir marta tekshiradi: faol, muddatli Premium va qolgan vaqt ≤ 24 soat bo'lsa bitta xabar (`🔄 Uzaytirish` tugmasi bilan). Takrorlanmasligi uchun **yangi ustun `users.premium_expiry_notified_for TEXT`** — `init_db()` o'zi qo'shadi (`ADD COLUMN IF NOT EXISTS`), qo'lda hech narsa kerak emas. Muddatsiz, bepul va ban qilinganlarga yuborilmaydi; bir tekshiruvda ko'pi bilan 200 ta. Muddati o'tganlar shu vazifada yopiladi (xabarsiz). Yangi env o'zgaruvchi yo'q.
- **Chap pastdagi shaxsiy tugma:** `/start` da Premium faol bo'lsa `👑 Ilova` (faqat joriy `MINI_APP_URL`, query parametrsiz), aks holda eski shaxsiy tugma tozalanadi (mavjud mexanizm saqlangan). Admin Premium bersa — tugma qo'yiladi, olib tashlasa yoki muddat tugasa — Default ga qaytadi. Hammasi fonda, timeout bilan.
  - `MINI_APP_URL` o'zgarsa: Premium userlarning shaxsiy tugmasi bot restartdan keyin ular `/start` bosganda yangilanadi.
  - ⚠️ `scripts/reset_menu_buttons.py` ni qayta ishga tushirsangiz, Premium userlarning `👑 Ilova` tugmasi ham tozalanadi (ular `/start` bossa qaytadi).
- "🔄 Uzaytirish" FAQAT sotib olish mumkin bo'lgan tariflarni ko'rsatadi (qoida: pastdagi "Tarif nomlari va uzaytirish").

### Tarif nomlari va uzaytirish
**Ko'rinadigan nomlar** (narx, muddat, AI limit, tartib o'zgarmagan; pastdan yuqoriga: Plus → Pro → Ultra):

| Ichki kod (`premium_type`, payload, `callback_data`) | Muddat | Narx (env) | AI/kun | Ko'rinadigan nom |
|---|---|---|---|---|
| `pro` (`PRO_7_DAYS`, `buy_pro_7`) | 7 kun | 50 ⭐ (`PRO_TRIAL_STARS`) | 15 | ⭐ Premium **Plus** |
| `plus` (`PLUS_30_DAYS`, `buy_plus_30`) | 30 kun | 150 ⭐ (`PRO_MONTHLY_STARS`) | 30 | 💎 Premium **Pro** |
| `ultra` (`ULTRA_30_DAYS`, `buy_ultra_30`) | 30 kun | 300 ⭐ (`ULTRA_MONTHLY_STARS`) | 100 | 👑 Premium Ultra |

- ⚠️ **Ichki kod ≠ ko'rinadigan nom.** Bazadagi `premium_type`, payloadlar, `callback_data`, env nomlari, `tier_rank` va CSS klasslari (`tier-pro`, `tier-plus`) o'zgarmagan, **migratsiya yo'q**. Faqat foydalanuvchi va admin ko'radigan matn almashgan. Kodni o'qiyotganda: `pro` = "Plus" (eng arzon), `plus` = "Pro".
- **Nom bitta joyda:** Python — `database.TIER_DISPLAY` / `TIER_ICON` (`bot.py` shundan oladi, matnlar `tier_title()` orqali); Mini App — `app.js` dagi `PREMIUM_TIERS`. `tests/test_tier_names.py` ikkalasi mos ekanini va bot hamda Mini App matnlarida eski nom–muddat juftliklari (masalan, 7 kunlik tarif eski nomi bilan) qolmaganini tekshiradi.
- **Rang va ikonka darajaga bog'liq:** eng arzon — teal ⭐, o'rta — binafsha 💎, eng yuqori — oltin 👑.
- Baraban: "1 kunlik Premium **Plus**" (ichki `pro`); SUPER sovrin — Premium **Pro** (30 kun, ichki `plus`) uchun 50% chegirma. 100 ball → Premium **Plus** (ichki `pro`, 3 kun; takliflarda muddat yozilmaydi — pastdagi "Premium kartasi va 100 ball").

**Bir xil tarifni qayta sotib olish = uzaytirish.** Qoida YAGONA (`bot.premium_purchase_decision` / `check_premium_purchase_eligibility`), holat `database.get_premium_view` dan (muddati o'tgan flag bloklamaydi). Bot tugmalari, `?start=buy_*` deep link, Mini App `/api/invoice` va `pre_checkout_query` hammasi shundan foydalanadi:
- Joriy tarif bilan **bir xil** tarif — ruxsat: tugash sanasi + tarif muddati (Plus +7 kun, Pro/Ultra +30 kun). "2 oy" kabi yangi variantlar yo'q.
- **Yuqoriroq** tarif — ruxsat (hozirgidek); **pastroq** — taqiq: "Sizda yuqoriroq tarif (Premium Ultra) bor — pastroq tarif sotib olinmaydi".
- **Muddatsiz** Premium — taqiq ("Sizda muddatsiz Premium bor"): unga muddat qo'shib bo'lmaydi. Shu sababli muddatsiz userga "100 ball → Premium" ham berilmaydi.
- SUPER PRIZ chegirmasi (`PLUS_30_DAYS_DISCOUNT`): faol `plus` (Pro) userga uzaytirish sifatida ishlaydi, `ultra` userga taqiq.
- Tugmalar: "Mening obunam", sotuv/uzaytirish sahifasi, Mini App Premium oynasi (Telegram'da `⭐ 300 — Uzaytirish`) faqat sotib olish mumkin bo'lgan tariflarni ko'rsatadi; joriy tarif tugmasi `🔄 Premium Ultra — yana 30 kun (300 ⭐)`.
- Uzaytirilganda to'lov tasdig'i: "✅ Premium Ultra 30 kunga uzaytirildi — yangi tugash sanasi: 11.01.2027".
- `database.process_paid_premium` / `grant_premium_days` faol muddatga qo'shadi va yuqori tarifni saqlaydi (testlar bilan tasdiqlangan). Eslatma: ular muddatsiz Premiumni muddatli qilib yuboradi — shuning uchun xarid qoidasi muddatsizni oldindan rad etadi.

**To'lovdan keyin menyu darhol yangilanadi:** `successful_payment` (va 100 ball → Premium) javobiga `get_start_keyboard(<yangi holat>)` qo'shiladi (pastdagi tugma darhol `👑 Premium Ultra` kabi bo'ladi), menyu keshi yangilanadi va shaxsiy `👑 Ilova` tugmasi fonda qo'yiladi (`refresh_premium_menu`). Baraban 1 kunlik sovrini `/start spin_*` yo'lida shunday, Mini App yo'lida (`/api/spin/claim`) bot xabar yubormaydi — kesh va shaxsiy tugma yangilanadi. To'lov mantig'i (summa, payload, takroriy to'lov himoyasi, reconcile) o'zgarmagan. Yangi env o'zgaruvchi va migratsiya yo'q.

### Premium kartasi va 100 ball
- **Bosh ekran:** "Bugun" bo'limida Bonus va Baraban ostida uchinchi karta — **Premium** (2+1 joylashuv, 360 px da sig'adi). Bepul: `Premium / Tariflar va bonuslar / Ochish`; Premium: tarif nomi, `5 kun qoldi` (muddatsizda `♾`), `Uzaytirish` (muddatsizda `Ko'rish`), rangi tarifga ergashadi. Bosilsa BITTA Premium oynasi (`#premium-modal`) ochiladi: Sog'liq tabidagi `btn-open-premium` qatori ham, AI limit tugagandagi taklif (`★ Premium tariflari`) ham shu oynani ochadi — AI taklifining o'z tarif kartalari yo'q.
- **Oyna:** tariflar (pastroqlari yashirin, joriy tarif "yana N kun"), so'ng **"100 ball → Premium Plus"** bo'limi: progress (`13 / 100 ball`), 100 va undan ko'p bo'lsa `Almashtirish`, aks holda `Yana 87 ball kerak`. Muddatsiz Premiumda bu bo'lim va tariflar yo'q ("Sizda muddatsiz Premium bor").
- **Takliflarda muddat yozilmaydi** (bot va Mini App: "100 ball → Premium Plus"); muddat faqat olingandan KEYIN: `100 ball yechildi! Premium Plus faollashdi — tugash: 15.11.2026`. Mantiq o'zgarmagan: ichki `pro`, 3 kun. `tests/test_points_redeem.py` takliflarda "kun" so'zi yo'qligini tekshiradi.
- **`POST /api/points/redeem`** (`init_data` HMAC, boshqa endpointlar kabi): tanada faqat `init_data`; javob `{"ok", "reason" (null | not_enough | unlimited | busy | banned), "message", "score", "cost": 100}` + `_premium_quota_fields` (yangi Premium holati va AI hisoblagichi). Mantiq botdagi tugma bilan BITTA: `bot.redeem_points_for_premium` (ban, muddatsiz Premium, yetarli ball; ballni yechish va Premium berish `database.check_and_grant_premium` ichida bir tranzaksiyada; bir foydalanuvchining parallel so'rovlari bitta ishlaydi). Muvaffaqiyatdan keyin menyu keshi va shaxsiy "👑 Ilova" tugmasi yangilanadi.
- `database.check_and_grant_premium` endi **muddatsiz Premiumni ham himoyalaydi** (ball yechilmaydi, Premium o'zgarmaydi) — kunlik bonus, referal va baraban avto-berishi ham shu funksiyadan o'tadi. Yangi env o'zgaruvchi va migratsiya yo'q.

### Ban tizimi: 📣 ochiq va 🤫 sirli ban (`/ban`, faqat `ADMIN_ID`)
Ban faqat adminda; ikki xil:

| | 📣 Ochiq ban | 🤫 Sirli ban |
|---|---|---|
| Ban qo'yilganda userga xabar | ✅ muddat + sabab + murojaat | ❌ hech narsa |
| Userning xabari / tugmasi | har safar `🚫 Siz bloklangansiz. 20.11.2026 14:00 gacha. Sabab: ...` (callback — alert) | **bot butunlay jim** (`message.answer` ham, `callback.answer()` ham yo'q) |
| Mini app | 403 `{"error":"banned","until","reason","contact"}` → "Siz bloklangansiz" ekrani | oddiy `500 {"error":"server_error"}` → "Xatolik yuz berdi" ekrani (ban haqida hech narsa yo'q) |
| To'lov (`pre_checkout`) | rad: sabab bilan | rad: umumiy "Xatolik yuz berdi" |
| Avtomatik / ommaviy xabarlar | ❌ | ❌ |
| Muddat tugaganda | `✅ Blok muddati tugadi` xabari | xabarsiz |
| Unban | admin tanlaydi: 📣 xabar bilan / 🤫 xabarsiz | admin tanlaydi |

- **Baza:** `users` ga `ban_mode` (`'open'` / `'silent'`), `ban_reason`, `banned_at` — `init_db()` o'zi qo'shadi (`ADD COLUMN IF NOT EXISTS`), qo'lda hech narsa kerak emas. Eski banlar (`is_banned = 1`, `ban_mode IS NULL`) **ochiq** ban hisoblanadi. Sirli banda `ban_reason` — faqat admin izohi (userga ko'rsatilmaydi). Yangi env o'zgaruvchi yo'q.
- **Yagona o'qish joyi:** `database.get_ban_info(user_id)` → `{"banned", "mode", "until", "reason"}` (keshlanadi, `ban_user` / `unban_user` keshni bekor qiladi). `is_user_banned` unga tayanadi. Muddati o'tgan ban o'qishda "ban yo'q" hisoblanadi, lekin bazaga **yozilmaydi**: tozalash va "Blok muddati tugadi" xabari faqat fon vazifasida.
- **Yagona SQL sharti:** `database.NOT_BANNED_SQL` / `BANNED_SQL` (+ `not_banned_params()`): "hozir banda emas" = `is_banned = 0 OR banned_until <= hozir`. Hamma ommaviy yuborishlar shuni ishlatadi (`get_active_user_ids`, `get_broadcast_targets`, `get_daily_tips_subscribers`, `get_premium_checkin_targets`, `get_all_active_reminders`): muddati o'tgan, lekin hali tozalanmagan user ham qo'shiladi. `get_all_users()` — BARCHA userlar (faqat ma'muriy skriptlar uchun, xabar yuborishga ishlatmang).
- **Middleware tartibi** (`bot.setup_middlewares`): **Ban → Throttling → AnswerCallback → FsmReset**. Ban birinchi, shuning uchun banlangan user "sekinroq" ogohlantirishi yoki AnswerCallback orqali bot tirikligini sezmaydi. Istisno: Telegram allaqachon yechgan `successful_payment` xabari ban middleware'dan o'tkaziladi (pul yo'qolmasin; ban to'lovdan keyin qo'yilgan bo'lishi mumkin).
- **Admin paneli `/ban`** (Premium paneli uslubida, `bn:` callbacklari): ro'yxat (🚫 ochiq, 🤫 sirli, 👤 oddiy; `🚫 Banlanganlar` filtri) yoki qidiruv (ID, @username, ism) → user kartasi → `🚫 Ban qilish` → muddat (1 soat / 1 kun / 7 kun / 30 kun / ♾) → rejim (📣 / 🤫) → sabab (faqat 📣: Spam, Haqorat, Qoidabuzarlik, Reklama, ✍️ Boshqa (yozaman), Sababsiz; 🤫 da ixtiyoriy admin izohi) → tasdiq ("User 7 kunga sirli ban qilinadi, unga xabar bormaydi"). Bandagi userda `✅ Unban` (📣 / 🤫) va `✏️ Muddatni o'zgartirish` (rejim va sabab saqlanadi; ochiq banda userga yangi muddat bilan ban xabari yuboriladi). Admin o'zini ban qila olmaydi. Matnli `/ban <id> [daqiqa]` va `/unban <id>` ishlaydi: ular 📣 ochiq, sababsiz (unban ham 📣). Eski `ban_toggle_` (bitta bosishda doimiy ban) olib tashlandi. Premium paneli kartasida ban holati ko'rinadi; banlangan userga Premium berilsa/olinsa userga xabar yuborilmaydi va admin `ℹ️ User banlangan — xabar yuborilmadi` ogohlantirishini oladi.
- **Fon vazifasi** (`ban_expiry_loop`, har 2 daqiqada, polling va webhook rejimida ham): muddati o'tgan banlarni **atomar** tozalaydi (`UPDATE ... RETURNING user_id, ban_mode`: parallel chaqiruvda ham xabar bir marta ketadi); ochiq edi → `✅ Blok muddati tugadi`, sirli → xabarsiz. Premium muddati va ballar o'zgarmaydi (banlangan userning Premiumi to'xtamaydi).
- **Avtomatik xabarlar:** 08:00 / 10:10 / 20:30 (Premium check-in), kunlik maslahatlar, dori eslatmalari, Premium tugash eslatmasi, `/broadcast` (hisobotda `🚫 Banlangan (o'tkazib yuborildi): N`), referal xabari va admin tasdiqlagandan keyingi xabarlar (karta cheki / reconcile) banlangan userga yuborilmaydi.
- **Mini app:** `app.js` `api()` javobini tekshiradi: `403 banned` → to'liq ekranli `#ban-screen` (qolgan hamma narsa `inert`, MainButton / BackButton / botga zaxira havolalari o'chadi); ilova ochilishida `/api/state` `server_error` (5xx) qaytarsa → `#error-screen` ("Xatolik yuz berdi. Keyinroq urinib ko'ring." + "Qayta urinish" + 103). Ekran ban uchun alohida emas, hamma server xatolari uchun. JSON'siz 502 / tarmoq uzilishi esa oldingi zaxira rejimida qoladi.

### Omad baraboni (8 sovrin)
Sovrinlar **bitta joyda**: `database.SPIN_PRIZES` (kod, ehtimol). Mini App `segments` (app.js) shu kodlar bilan mos bo'lishi shart — `tests/test_spin_prizes.py` tekshiradi.

| Kod (`pending_spin_prize`) | Sovrin | Ehtimol |
|---|---|---|
| 1 / 2 / 3 / 5 | shuncha ball | 35% / 20% / 12% / 5% |
| -2 | 💡 kun maslahati (ball yo'q, `data/spin_tips.json` dan) | 15% |
| -1 | 🤖 +1 bepul AI savol (`users.spin_ai_bonus`) | 10% |
| -3 | ⭐ 1 kunlik Premium Plus (ichki `pro`; faol Pro/Ultra tarifi pasaymaydi, muddati +1 kun) | 2% |
| 0 | 🏆 SUPER: Premium Pro (30 kun, ichki `plus`) uchun 50% chegirma, **24 soat amal qiladi** (pastda: "SUPER PRIZ: 24 soatlik −50% Pro taklifi") | 1% |

- **Migratsiya:** `users.spin_ai_bonus INTEGER DEFAULT 0` — `init_db()` bot ishga tushganda o'zi qo'shadi (`ADD COLUMN IF NOT EXISTS`), qo'lda hech narsa qilinmaydi. `pending_spin_prize` turi o'zgarmagan (INTEGER). Yangi env o'zgaruvchi yo'q.
- **Eski holat:** deploy paytida bazada `pending_spin_prize = 10` turgan bo'lsa u o'zgartirilmay +10 ball beriladi; noma'lum qiymat — +1 ball.
- **`data/spin_tips.json`** (40 ta maslahat) repo bilan keladi. Fayl yo'q/buzuq bo'lsa bitta zaxira maslahat ko'rsatiladi (logda xato).
- **AI kvota tartibi** (bot va mini app umumiy): bepul 1 ta yoki tarif kunlik limiti → u tugagach `spin_ai_bonus`. Xatoda savol o'sha manbaga qaytariladi. Bonus muddatsiz. `ai_remaining` bonusni o'z ichiga oladi, `ai_limit` — faqat tarif limiti, `ai_bonus` alohida.
- **Mini App API:** `/api/state` → `prize` (kod) + `prize_type` (`points|tip|ai|pro_day|super`) + `ai_bonus`; `/api/spin/claim` → `prize`, `prize_type`, `points`, `tip` (ai/pro_day da yana Premium holati va AI hisoblagichi); `/api/ai/chat` → `bonus`.
- **⚠️ Eski kodga qaytarishdan OLDIN** (rollback): eski kod `pending_spin_prize` ning noma'lum qiymatini (-1, -2, -3) 10 ball deb beradi. Avval serverda: `UPDATE users SET pending_spin_prize = NULL WHERE pending_spin_prize < 0;` (ustun `spin_ai_bonus` qolaveradi — zararsiz).

### SUPER PRIZ: 24 soatlik −50% Pro taklifi
Baraban SUPER sovrini (1%) endi **24 soat** amal qiladigan taklif beradi: ko'rinadigan **Pro** (ichki `plus`, 30 kun) — `150⭐` o'rniga `75⭐`. Narx va muddat qoidasi **bitta joyda**: `database.plus_price()` / `plus_discount_price()` (`PRO_MONTHLY_STARS` yarmi, yuqoriga yaxlitlanadi) va `database.DISCOUNT_HOURS = 24`; muddat o'qish — faqat `database.get_discount_info(user_id)`.

- **Migratsiya (yangi ustun):** `users.discount_expires_at TIMESTAMP` — `init_db()` bot ishga tushganda o'zi qo'shadi (`ADD COLUMN IF NOT EXISTS`), qo'lda hech narsa qilinmaydi. Shu yerning o'zida **bir martalik, idempotent** yangilash ishlaydi: `has_discount = 1` va muddati yo'q (eski, muddatsiz) chegirmalarga **deploy paytidan boshlab 24 soat** beriladi. Qayta ishga tushirilganda hech narsa o'zgarmaydi (`... AND discount_expires_at IS NULL`). Yangi env o'zgaruvchi yo'q.
- **Qoidalar:** chegirma faol = `has_discount = 1` VA `discount_expires_at > hozir`. Muddati o'tgani o'qishda "faol emas" bo'ladi (bazaga yozilmaydi, flag `1` bo'lib qolaveradi — zararsiz). Qayta SUPER yutilsa muddat yangi 24 soatga suriladi. Chegirma **faqat muvaffaqiyatli to'lovdan keyin** sarflanadi (`process_paid_premium`, premium berish bilan bir tranzaksiyada: `has_discount = 0`, `discount_expires_at = NULL`). Ultra yoki muddatsiz Premiumi borga taklif ko'rsatilmaydi (`premium_purchase_decision` qoidasi o'zgarmagan).
- **To'lov xavfsizligi:** faol chegirmada invoice `75⭐` (`DISCOUNT_PAYLOAD`), muddat o'tgach `150⭐`. Muddati o'tgan (yoki ishlatilgan) chegirmali invoice `pre_checkout` da rad etiladi: `⏳ Chegirma muddati tugagan. Pro tarifini oddiy narxda olishingiz mumkin.` `validate_payment` faqat `75` (chegirma payload'i) va `150` ni qabul qiladi.
- **Bot:** yutgan zahoti xabar `🏆 SUPER PRIZ! 💎 Pro (30 kun) — 50% chegirma / ~~150⭐~~ → 75⭐ / ⏳ Taklif 24 soat amal qiladi: DD.MM.YYYY HH:MM gacha` + invoice tugmasi `💎 Pro — 75⭐ (−50%)`. 24 soat ichida Pro sotiladigan **hamma joyda** faqat chegirmali tugma, chizilgan eski narx va `⏳ 5 soat 12 daqiqa qoldi`: `/premium` sotuv sahifasi va `🔄 Uzaytirish`, "Mening obunam", AI limit tugagandagi taklif (`premium_upsell`), `/start buy_plus_30` deep link, `/start spin_*`. Muddat o'tgach hammasi oddiy `150⭐` tugmasiga qaytadi. Qolgan vaqt formati bitta: `bot.format_discount_left` (`23 soat 40 daqiqa`, `5 soat`, `40 daqiqa`).
- **Mini App API:** `/api/state` va `_premium_quota_fields` (shu bilan `/api/points/redeem`) javobiga `"discount": {"active", "price", "old_price", "expires_at" (ISO, Toshkent vaqti | null), "seconds_left"}` qo'shildi (faol bo'lmasa ham maydon bor, `active: false`); `/api/spin/claim` da SUPER bo'lsa ham (qo'shimcha so'rovsiz). `seconds_left` — qurilma soatidan mustaqil hisob uchun.
- **Mini App:** yutgan zahoti Pro taklif kartasi (nom + ikonka, chizilgan `★ 150`, katta `★ 75`, `−50%`, qolgan vaqt, `Sotib olish` → mavjud `buyPremium('buy_plus_30')`); 24 soat davomida Premium oynasidagi Pro kartasi, bosh ekrandagi Premium kartasi (`−50% · 5 soat qoldi`) va AI limit taklifi. Taymer 0 ga yetsa sahifani yangilamasdan oddiy narx qaytadi; Pro to'langach darhol yo'qoladi. Server yagona hakam: invoice narxini `/api/invoice` o'zi belgilaydi.
- **Server `.env`:** yangi o'zgaruvchi yo'q (`PRO_MONTHLY_STARS` oldingidek). Deploydan keyin qo'lda hech narsa kerak emas.
- **⚠️ Eski kodga qaytarishdan OLDIN** (rollback): eski kod `has_discount = 1` ni muddatsiz deb biladi. Qaytarishdan oldin muddati o'tgan chegirmalarni tozalash ma'qul: `UPDATE users SET has_discount = 0 WHERE has_discount = 1 AND discount_expires_at <= NOW();` (`discount_expires_at` ustuni qolaveradi — zararsiz).

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
PRO_TRIAL_STARS=50              # Plus 7 kun (ichki kod: pro)
PRO_MONTHLY_STARS=150           # Pro 30 kun (ichki kod: plus; SUPER PRIZ chegirmasi = yarmi)
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
