# G relizi: `review-g-home` → `main`

**Kim uchun:** loyiha egasi (server va GitHub'da qo'lda bajariladigan qadamlar).
**Holat:** `review-g-home` da 0–5-bosqichlar tayyor, testlar yashil. `main` hozir `26150b4` da (G dan oldingi oxirgi commit).
**Eslatma:** `main` ga push = production deploy (GitHub Actions serverni yangilaydi va botni qayta ishga tushiradi).

Tartib: **1 → 2 → 3 → 4**. Muammo bo'lsa — 5 (rollback).

### Nimalar chiqadi (`26150b4..review-g-home`)

| Commit | Nima |
|---|---|
| `7f650f4` | G tokenlari, Nunito (o'zimizda), 4 tabli nav (Yordam, Kasalliklar, Sog'liq, AI) |
| `1ac40af` | Bosh ekran: tana figurasi, holat chiplari, "Bugun" kartalari, Test qatori, tana sheet'i |
| `57ff141` | `/api/ai/chat` + `/api/state` ga `ai_remaining` / `ai_limit` |
| `f69a106` | Bepul foydalanuvchiga jami 1 ta AI savol; limit tugaganda Premium taklifi |
| `44a062c` | Bosh ekranda maneken figurasi + G yorliqlari va strelkalari |
| `dd2f923` | AI rate limit: soniyalik cheklov, 30 s blok, bir vaqtda 1 ta so'rov |
| `448abde` | AI tabida Premium taklif kartasi |
| `d1f106e` | Mavzu tanlash: Avto / Kunduzgi / Tungi |
| `07f2ff3` | AI suhbat tabi |
| `7099a32` | Mavzu almashganda MainButton ranglari |
| `4db1425` | a11y: bosish zonasi ≥ 44×44, prefers-reduced-motion, a11y testlari |
| `70cd0de` | O'lik kod tozalandi (eski Tana tabi, SOS karta, eski modal/baraban) |
| `46cb2e0` | Bot: `premium_upsell` matni (Premium'ga "Bepul limit" yo'q, "cheksiz" yo'q) |
| `ab6e8c2` | Detal / kasallik "AI'dan so'rash" → AI tabi (holat chipi) |
| `ae09271` | `FREE_AI_DAILY_LIMIT` o'qilishi olib tashlandi |
| `1bc74ba` | Beqaror test barqarorlashtirildi |
| (oxirgi) | Shu hujjat |

---

## 1. Server: nginx `/api/` bloki (deploydan OLDIN)

AI javobi 40 soniyagacha kutilishi mumkin (`/api/ai/chat`). nginx standart `proxy_read_timeout` 60 s — chegarada.
`70s` qo'yish tavsiya etiladi.

Blok qaysi faylda ekanini topish:

```bash
sudo grep -rn "location /api/" /etc/nginx/
```

To'liq namuna (mavjud blok bilan solishtiring; asosiysi — `proxy_pass` oxirida `/` YO'Q va `proxy_read_timeout 70s`):

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:10000;          # oxirida "/" YO'Q — URI o'zgarmasdan uzatiladi (/api/state, /api/ai/chat ...)
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 5s;
    proxy_send_timeout 30s;
    proxy_read_timeout 70s;                     # AI javobi (server 40 s kutadi) + zaxira
}
```

- `10000` — botning ichki aiohttp porti (`.env` dagi `PORT`; boshqa bo'lsa o'shani yozing). U faqat `127.0.0.1` da tinglaydi.
- Mini App (`/`) bloki va CSP o'zgarmaydi: `Content-Security-Policy` sarlavhasini `app_server.py` o'zi qo'shadi.

Tekshirish va qayta yuklash:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`nginx -t` xato bersa — `reload` qilinmaydi (`&&`), sayt eski sozlama bilan ishlashda davom etadi.

---

## 2. `review-g-home` → `main` (chiqarish)

Kompyuterda (repo papkasida):

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git log --oneline main..origin/review-g-home      # chiqadigan commitlar ro'yxati — ko'rib chiqing
git merge --ff-only origin/review-g-home
git push origin main                              # = production deploy
```

- `--ff-only` — `main` da G dan keyin boshqa commit bo'lsa, merge to'xtaydi (hech narsa buzilmaydi). Shunda menga ayting.
- Deploy holati: GitHub → Actions. Serverda versiya: `cd /root/Birinchi-Yordam-bot && git log -1 --oneline`.

---

## 3. Deploydan keyingi tekshiruv (serverda, 2–3 daqiqadan so'ng)

```bash
# API yopiq: buzuq init_data -> 403
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://birinchiyordam.duckdns.org/api/state \
     -H 'Content-Type: application/json' -d '{"init_data":"buzuq"}'
# kutiladi: 403

# AI endpointi ham himoyalangan -> 403
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://birinchiyordam.duckdns.org/api/ai/chat \
     -H 'Content-Type: application/json' -d '{"init_data":"buzuq","message":"salom"}'
# kutiladi: 403

# Botning ichki health tekshiruvi (faqat serverning o'zida; tashqaridan ochiq emas)
curl -s http://127.0.0.1:10000/health
# kutiladi: Birinchi Yordam bot is running!

# Mini App ochiladi va CSP sarlavhasi bor
curl -sI https://birinchiyordam.duckdns.org/ | grep -iE "^HTTP|content-security-policy"
# kutiladi: HTTP/... 200 va Content-Security-Policy: default-src 'self'; ...

# Servislar va oxirgi loglar
systemctl status birinchi-yordam-bot birinchi-yordam-app --no-pager
journalctl -u birinchi-yordam-bot -n 50 --no-pager
```

`502` chiqsa — bot ishlamayapti yoki port mos emas (`journalctl -u birinchi-yordam-bot -n 100`).
`404` chiqsa — nginx `/api/` bloki yo'q yoki `proxy_pass` oxirida `/` bor.

---

## 4. Telefonda qo'lda sinov (Telegram, iOS va Android)

Mini App'ni bot menyusidan oching. Har bandni light va dark mavzuda ko'ring.

**Bosh ekran**
- [ ] "Qayeringiz og'riyapti?", maneken, 5 ta yorliq va strelkalar to'g'ri joyda
- [ ] Oldi / Orqa almashadi (Orqa'da "Orqa" va "Bel" yorliqlari)
- [ ] Har bir yorliq (Bosh, Qo'l, Ko'krak, Qorin, Oyoq, Orqa, Bel) va maneken qismi bosilganda sheet ochiladi
- [ ] Sheet: holatlar ro'yxati, "Tezkor" belgisi, pastda "AI'dan so'rash" (Telegram'ning pastki tugmasi)
- [ ] Holat chiplari bosilganda detal ochiladi; "Hammasi" — to'liq ro'yxat va qidiruv
- [ ] Detal: "AI'dan so'rash" → AI tabi "Holat: ..." chipi bilan (xabar o'zi ketmaydi)

**Bonus va baraban (mantiq o'zgarmagan)**
- [ ] Kunlik bonus: "Olish" → ball qo'shiladi, karta "Olindi" bo'ladi
- [ ] Baraban: aylantirish → natija; **X bilan yopib** qayta oching — ball baribir yozilgan
- [ ] Baraban taymeri (kutish holati) to'g'ri

**Premium**
- [ ] Sog'liq → Premium: tarif tanlash → "★ ... — Davom etish" → Telegram to'lov oynasi (`openInvoice`) ochiladi
- [ ] To'lovni bekor qilish — ilova buzilmaydi

**AI tabi**
- [ ] Salom va 4 ta chip; chip bosilsa savol yuboriladi
- [ ] Yozish → "yozmoqda" nuqtalari → javob shu tabda chiqadi; mini app yopilmaydi
- [ ] Javobdagi qalin matn va ro'yxatlar to'g'ri, `**` / `##` belgilari ko'rinmaydi
- [ ] Bosh ekran sheet'idan "AI'dan so'rash" → "Tana qismi: ..." chipi, × bilan olib tashlanadi
- [ ] Bepul hisob: 1 ta savoldan keyin "Bepul savol: 0/1", Premium taklif kartasi, yozish paneli o'chiq
- [ ] Premium hisob: "Bugun: N/15 so'rov" kamayadi
- [ ] Ketma-ket tez bosish → "Juda tez yozyapsiz. N soniyadan so'ng..." va tugma vaqtincha o'chadi
- [ ] **Klaviatura (iOS va Android):** yozish paneli klaviatura ustida ko'rinadi, pastki menyu yashirinadi, yopilganda qaytadi
- [ ] "Yangi suhbat" tarixni tozalaydi

**Umumiy**
- [ ] Sog'liq → Ko'rinish: Avto / Kunduzgi / Tungi; Avto — Telegram mavzusiga ergashadi; qayta ochganda tanlov saqlanadi
- [ ] Telegram sarlavha va fon rangi mavzuga mos
- [ ] Telegram BackButton: detal, sheet, "Hammasi", Premium oynasidan to'g'ri qaytaradi
- [ ] Tebranish (haptic): tugmalar, baraban, bonus
- [ ] Telefon sozlamasida "Harakatni kamaytirish" yoqilsa — animatsiyalar o'chadi, konfetti yo'q

Muammo bo'lsa: skrinshot + qisqa tavsif (qaysi telefon, iOS/Android, light/dark).

---

## 5. Rollback (muammo bo'lsa)

```bash
git checkout main
git pull --ff-only origin main
git revert --no-edit 26150b4..HEAD
git push origin main                              # = deploy (G dan oldingi holat)
```

- `26150b4..HEAD` — G'ning barcha commitlari teskari tartibda bekor qilinadi (tarix saqlanadi, force push yo'q).
- Bazaga migratsiya yo'q (G faqat o'qiydigan `get_ai_quota` qo'shgan) — rollback bazaga tegmaydi.
- nginx `proxy_read_timeout 70s` ni qaytarish shart emas (eski kodga zarari yo'q).

---

## 6. `.env` (serverda)

- Yangi o'zgaruvchi **yo'q**.
- `FREE_AI_DAILY_LIMIT` endi kodning hech qayerida o'qilmaydi (bepul — jami 1 ta savol). Serverdagi `.env` da bo'lsa,
  xohlasangiz o'chirib qo'ying — qolsa ham ta'siri yo'q.
- AI limitlari: `PRO_AI_DAILY_LIMIT` (15), `PLUS_AI_DAILY_LIMIT` (30), `ULTRA_AI_DAILY_LIMIT` (100) — o'zgarmagan.
