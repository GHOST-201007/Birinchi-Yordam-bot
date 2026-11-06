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
Database SQLite. `init_db()` funksiyasi bot ishga tushganida `ALTER TABLE ADD COLUMN`
orqali yangi ustunlarni xavfsiz qo'shadi. Hech qanday qo'shimcha amal talab qilinmaydi.

> DIQQAT: `users.db` faylini o'chirmang. Barcha foydalanuvchi ma'lumotlari shu yerda.

### 4. .env fayli tekshiruvi
`.env` faylida quyidagilar to'g'ri ekanligini tekshiring:
```
BOT_TOKEN=...
GEMINI_API_KEY=...
ADMIN_ID=...
ADMIN_USERNAME=...
MINI_APP_URL=...  # run_dev.py avtomatik yangilaydi
PREMIUM_STARS_PRICE=50
```

### 5. Eski jarayonlarni to'xtatish
Agar bot allaqachon ishlayotgan bo'lsa:
- Terminaldagi `run_dev.py` jarayonini `Ctrl+C` bilan to'xtating.
- Task Manager dan qolgan python.exe jarayonlarini tekshiring.

### 6. Ishga tushirish
```
python run_dev.py
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
