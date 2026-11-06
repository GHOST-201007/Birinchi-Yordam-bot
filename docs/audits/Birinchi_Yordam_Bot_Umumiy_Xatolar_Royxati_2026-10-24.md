# Birinchi Yordam Bot --- Umumiy Xatolar va Ishlar Ro'yxati

**Hujjat sanasi:** 2026-10-24\
**Loyiha:** `C:\Users\User\Desktop\Birinchi yordam-bot`\
**Production papka:** `/root/Birinchi-Yordam-bot`\
**Maqsad:** barcha ma'lum muammolarni bir joyga jamlash, shu fayl
asosida birma-bir audit va tuzatish.

> **Muhim:** bu hujjat --- mavjud suhbatlar va audit natijalaridan
> yig'ilgan master ro'yxat. Undagi barcha bandlar hozirgi kodda albatta
> xato bor degani emas. "Tasdiqlangan" bandlar yaqinda test yoki audit
> bilan aniqlangan. "Qayta tekshirish kerak" bandlar oldingi auditlarda
> qayd etilgan, lekin hozirgi nusxada qayta tasdiqlanmagan. Avval audit,
> keyin tuzatish; hech qachon tekshirmasdan deploy qilinmasin.

## Status belgilari

-   **FIXED AND TESTED** --- tuzatilib, tegishli testdan o'tgan.
-   **FIXED BUT NOT TESTED** --- kodda tuzatish bor, lekin yetarli test
    yo'q.
-   **PARTIALLY FIXED** --- qisman hal qilingan yoki ayrim yo'llari
    xavfli.
-   **NOT FIXED** --- xato tasdiqlangan, tuzatish hali bajarilmagan.
-   **NEEDS AUDIT** --- oldingi auditda ko'tarilgan; hozirgi kodda
    bor-yo'qligini tekshirish kerak.
-   **BLOCKED** --- kerakli ma'lumot yoki xavfsiz test muhiti yo'q.

------------------------------------------------------------------------

# 1. Hozirgi holat va tasdiqlangan testlar

## 1.1 Oxirgi ma'lum test natijalari

  ------------------------------------------------------------------------------------------------------------------
  Tekshiruv                                                                      Oxirgi natija Holat
  --------------------------------------------------------------- ---------------------------- ---------------------
  `python -m py_compile .\bot.py .\database.py .\app_server.py`                    Exit code 0 **FIXED AND TESTED**
                                                                                               --- sintaksis xatosi
                                                                                               hozirgi lokal nusxada
                                                                                               yo'q

  `python -m unittest test_payment_fixes`                               26 passed, exit code 0 **FIXED AND TESTED**
                                                                                               --- mock/unit
                                                                                               testlar, production
                                                                                               integratsiyasi emas

  `python -I .\test_ban_cache_local.py`                                 45 passed, exit code 0 **FIXED AND TESTED**
                                                                                               --- lokal testlar

  `python -m unittest test_image_handler -v`                             11 test: 10 passed, 1 **NOT FIXED** ---
                                                                           failed; exit code 1 bitta haqiqiy xato
                                                                                               aniqlandi

  Jami muvaffaqiyatli eski testlar                                                          71 26 payment + 45
                                                                                               ban-cache

  Rasm handler testlari                                                                  10/11 1 test
                                                                                               muvaffaqiyatsiz
  ------------------------------------------------------------------------------------------------------------------

**Izoh:** testlar mock asosida ishlaydi. Bu haqiqiy Telegram, Gemini,
PostgreSQL yoki production to'lov oqimi to'liq tekshirildi degani emas.

## 1.2 Tasdiqlangan joriy muammolar

### BUG-001 --- Rasm yuklanishi va refund xatosi birga yuz bersa, foydalanuvchiga javob yuborilmaydi

-   **Daraja:** MEDIUM
-   **Holat:** NOT FIXED (oxirgi xabar bo'yicha)
-   **Dalil:** `test_image_handler.py` dagi
    `test_f2_refund_fails_after_download_failure` yiqilgan.
-   **Sabab:** rasmni yuklash yoki qayta ishlash xatosidan keyin
    `refund_once()` ham xato bersa, istisno tashqariga chiqib ketadi;
    foydalanuvchiga xato xabari yuborilmaydi.
-   **Keyingi ish:** refund xatosini alohida ushlash va loglash;
    foydalanuvchiga xabar yuborishga urinish davom etsin. Refund
    muvaffaqiyatsiz bo'lsa, limit qaytarildi deb hisoblanmasin.
-   **Test:** mavjud yiqilgan test tuzatilgan kodda o'tishi kerak;
    testni o'zgartirib xatoni yashirmaslik.

### BUG-002 --- Gemini tayyor javobi Telegram xatosi sabab yo'qolishi mumkin

-   **Daraja:** MEDIUM
-   **Holat:** NOT FIXED (oxirgi xabar bo'yicha)
-   **Dalil:** `bot.py` taxminan 2955--2968-qatorlar; aniq qatorlar kod
    o'zgarsa qayta tekshiriladi.
-   **Sabab:** Gemini javobini yuborishdagi `edit_text()` xatosi model
    chaqiruvi bilan bir `try` ichida; Telegram javobni rad etsa, javob
    yuborish xatosi Gemini model xatosi sifatida talqin qilinishi
    mumkin.
-   **Ehtimoliy sabablar:** HTML rad etilishi yoki matn Telegram limiti
    (odatda 4096 belgi)dan uzun bo'lishi.
-   **Keyingi ish:** model chaqiruvini natijani Telegram'ga yuborishdan
    ajratish; HTML xavfsiz fallback va uzun matnni teglarni buzmasdan
    boshqarish; takroriy javob yubormaslik.
-   **Test:** Telegram `edit_text()` xato berishi, HTML fallback, uzun
    matn va dublikat xabar holatlari uchun testlar.

### BUG-003 --- Rasm handleri hali haqiqiy Telegram + Gemini bilan sinovdan o'tmagan

-   **Daraja:** MEDIUM
-   **Holat:** FIXED BUT NOT TESTED / BLOCKED
-   **Dalil:** mock testlar mavjud; real integratsion test bajarilmagan.
-   **Xavf:** rasm bytes, MIME turi, Gemini model nomlari, Telegram
    xabari va limit/refund oqimi real muhitda hali tasdiqlanmagan.
-   **Keyingi ish:** lokal mock testlar o'tgach, xavfsiz test akkaunti
    va nazorat qilinadigan muhitda integratsion sinov. Ishlab turgan
    botda yoki haqiqiy foydalanuvchilar bilan sinov o'tkazmaslik.

### BUG-004 --- Refund funksiyalarida yarim tun chegarasi bo'yicha limit hisobida xato ehtimoli

-   **Daraja:** LOW
-   **Holat:** NEEDS AUDIT
-   **Dalil:** oldingi auditda `refund_daily_request` sana
    tekshirmasligi qayd etilgan.
-   **Xavf:** so'rov bir kunda boshlanib, refund keyingi kuni bajarilsa,
    yangi kun hisobidan kamaytirishi mumkin.
-   **Keyingi ish:** `database.py` dagi kunlik limit/refund
    tranzaksiyalarini ko'rib chiqish va sana o'zgarishi testi qo'shish.

### BUG-005 --- DB refund funksiyalarida ulanish yopilishi kafolatlanmagan bo'lishi mumkin

-   **Daraja:** LOW
-   **Holat:** NEEDS AUDIT
-   **Dalil:** oldingi auditda refund funksiyalarida `try/finally`
    yo'qligi qayd etilgan.
-   **Xavf:** SQL xatosida DB connection/pool resursi ushlab qolinish
    ehtimoli.
-   **Keyingi ish:** amaldagi connection olish/bo'shatish usulini
    tekshirish; boshqa DB funksiyalarining loyihaviy patterniga mos
    minimal tuzatish va test.

------------------------------------------------------------------------

# 2. To'lovlar va Premium --- to'liq audit talab qilinadigan ro'yxat

> Quyidagi bandlar oldingi auditlarda ko'tarilgan. Kod holati o'zgargan
> bo'lishi mumkin; tuzatishdan oldin joriy lokal kod va testlar bilan
> qayta tasdiqlash shart.

### PAY-001 --- `approve_receipt_and_grant` funksiyasi mavjudligi va ishlatilishi

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi dalil:** `bot.py` ichida `approve_receipt_and_grant`
    chaqirilishi qayd etilgan, ammo `database.py` da mavjudligi
    tasdiqlanmagan.
-   **Tekshiruv:** funksiya ta'rifi, importi, callback yo'li va testlari
    borligini tekshirish.
-   **Talab:** admin to'lovni tasdiqlaganda Premium berish va chek
    holatini yangilash atomik bo'lsin; bitta qadam muvaffaqiyatsiz
    bo'lsa, qisman o'zgarish qolmasin.

### PAY-002 --- Manual receipt / chek tasdiqlash oqimi

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi auditda qayd etilgan xavflar:**
    -   callback faqat `adm_app_<user_id>` / `adm_rej_<user_id>`
        shaklida bo'lishi;
    -   chek uchun noyob token yoki receipt ID bilan egalik tekshiruvi
        yo'qligi;
    -   admin tasdiqlash jarayonida Premium muddati ustma-ust qo'shilib
        ketishi;
    -   chek holati, Premium berish va audit izi bitta DB
        tranzaksiyasida bo'lmasligi mumkin.
-   **Tekshiruv:** joriy callback formatlari, receipt identifikatori,
    admin vakolati, foydalanuvchi/chek mosligi, takroriy approve/reject,
    DB transaction va rollback.
-   **Talab:** chekni faqat tegishli receipt ID va ruxsatli admin
    tasdiqlay olsin; takroriy callback Premium'ni ikki marta bermasin.

### PAY-003 --- Telegram Stars to'lov oqimi to'liq integratsion sinovdan o'tmagan

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi ma'lumot:** `XTR` valyutasi va bo'sh provider token
    ishlatilishi qayd etilgan; mock testlar mavjud, ammo haqiqiy to'lov
    sinovi bu bilan tasdiqlanmaydi.
-   **Tekshiruv:** invoice yaratish, `pre_checkout_query`,
    `successful_payment`, valyuta, summa, payload, Premium
    aktivatsiyasi, bekor qilish va xato holatlari.
-   **Talab:** to'lov Telegram tasdiqlagan qiymatlar asosida
    tekshirilsin; narx yoki Premium muddati foydalanuvchi yuborgan
    payload'dan ko'r-ko'rona olinmasin.

### PAY-004 --- Stars narxi va plan qiymatlarini tekshirish

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** invoice'dagi narx, `total_amount`,
    `currency == "XTR"`, payload va tanlangan tarif bir-biriga mosligini
    tekshirish.
-   **Xavf:** invoice narxi va handler tekshirayotgan narx bir-biridan
    farq qilishi yoki eski tarif qiymati qolishi mumkin.

### PAY-005 --- Takroriy to'lov / idempotency

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT (mock testlar bor)
-   **Oldingi audit:** `process_paid_premium()` atomik/idempotent,
    rollback va row locking ishlatishi haqida ijobiy audit qaydi mavjud;
    buni joriy kodda qayta tasdiqlash kerak.
-   **Tekshiruv:** `telegram_payment_charge_id` yoki boshqa noyob charge
    ID uchun DB unique constraint, takroriy webhook/callback va
    concurrent so'rovlar.
-   **Talab:** bir charge ID bilan Premium faqat bir marta berilsin.

### PAY-006 --- To'lov payload'i noma'lum bo'lsa, admin ogohlantirishi va xavfsiz qayta tiklash

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi audit:** unknown payload uchun xavfsiz log/test
    ssenariylari bor; admin alert va qayta tiklash oqimi to'liq emasligi
    qayd etilgan.
-   **Tekshiruv:** noma'lum payload foydalanuvchiga Premium bermasin;
    shaxsiy yoki maxfiy to'lov ma'lumoti logga chiqarilmasin; admin
    uchun xavfsiz alert va reconciliation yozuvi bo'lsin.

### PAY-007 --- Legacy payload mosligi

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** `premium_1month` kabi eski payload formatlari
    borligi aytilgan.
-   **Tekshiruv:** faqat kerakli eski formatlar qo'llab-quvvatlansin;
    noma'lum payload'lar yangi tarif sifatida talqin qilinmasin.

### PAY-008 --- Reconciliation / pending payment qayta tiklash

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** `_PENDING_RECONCILE_DB`,
    `pending_reconciliations`, `/reconcile` va `_init_reconcile_db`
    haqida kod mavjudligi qayd etilgan; init chaqirilishi va doimiy
    saqlash kafolati noaniq.
-   **Tekshiruv:** DB jadvali yaratilishi, startup'da init chaqirilishi,
    restart'dan keyin yozuvlar saqlanishi, admin reconcile huquqi, xato
    paytida takroriy grant bo'lmasligi.
-   **Talab:** process memory'dagi ma'lumotning o'zi yagona dalil
    bo'lmasin; qayta tiklash idempotent bo'lsin.

### PAY-009 --- `pending_reconcile.db` xavfsizligi

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** fayl joylashuvi, ruxsatlari, backup, bir vaqtda
    yozish, restart/recovery va maxfiy ma'lumotlar.
-   **Eslatma:** bu fayl borligi yoki hozir production'da ishlatilishi
    tasdiqlanmagan.

### PAY-010 --- Admin ID va admin callback tekshiruvlari

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** `ADMIN_ID=0` default xavfi va admin-ID tekshiruvi
    yetarli emasligi qayd etilgan.
-   **Tekshiruv:** startup'da `ADMIN_ID` mavjud va haqiqiy musbat ID
    ekanini tekshirish; barcha admin buyruq/callback'larda server-side
    authorization.
-   **Talab:** noto'g'ri konfiguratsiya paytida bot admin funksiyalarini
    ochiq qoldirmasin.

### PAY-011 --- To'lov xatosidan keyingi recovery

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** DB uzilishi, Telegram notification yuborilmasligi,
    duplicate charge, process restart, unknown payload va admin
    reconciliation.
-   **Talab:** Premium berilgan bo'lsa-yu, xabar yuborilmasa, holatni
    aniqlash mumkin bo'lsin; xabar yuborish xatosi Premium grantni ikki
    marta bajartirmasin.

### PAY-012 --- Premium muddati ustma-ust qo'shilishi (`/start`, admin grant, points reward)

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** `/start` yoki admin grant takrorlanishi Premium
    muddatini noto'g'ri qo'shishi mumkinligi ko'tarilgan.
-   **Tekshiruv:** tarif muddati, mavjud `premium_until`,
    upgrade/downgrade va takroriy admin callback.
-   **Talab:** muddat qoidalari hujjatlashtirilsin va test bilan
    mustahkamlansin.

### PAY-013 --- Premium rejalari va limitlarining mosligi

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi ma'lumot (qayta tekshirish kerak):**
    -   Pro: 50 Stars / 7 kun / kuniga 15 AI so'rovi;
    -   Plus/Max: 150 Stars / 30 kun / kuniga 30 AI so'rovi;
    -   Ultra: 300 Stars / 30 kun / kuniga 100 AI so'rovi;
    -   ball orqali Premium: 100 ball / 3 kun, `premium_type='pro'`.
-   **Tekshiruv:** UI, invoice, DB va backend'dagi qiymatlar bir xilmi;
    admin grant xabari muddati bilan real muddat mosmi.

------------------------------------------------------------------------

# 3. Telegram bot va AI handlerlar

### BOT-001 --- Ovozli xabar handleri to'liq audit qilinmagan

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** audio download, STT/transcription, Gemini chaqiruvi,
    bo'sh transcription, timeout, model fallback, typing action, limit
    sarflash/refund, dublikat javob.
-   **Oldingi kodda ko'rilgan nuqta:** `audio_b64` hisoblanib
    ishlatilmayotgani qayd etilgan; bu ortiqcha kodmi yoki keyingi oqim
    uchun kerakmi --- tekshirish kerak.
-   **Talab:** mock testlar; haqiqiy API sinovi alohida nazoratli
    bosqichda.

### BOT-002 --- Takroriy AI javoblari

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** duplicate AI replies muammosi ilgari fallback text
    handler/state check orqali tuzatilgan.
-   **Tekshiruv:** bir xabar bir necha handler tomonidan
    ishlanmayaptimi; audio, rasm va matn handlerlari bir-birini
    takrorlamaydimi.
-   **Talab:** bir incoming update uchun ko'pi bilan bitta yakuniy
    javob; testlar bilan isbotlash.

### BOT-003 --- Gemini model fallback va rate limit

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** 429/RESOURCE_EXHAUSTED, 404/NOT_FOUND, 5xx, timeout,
    bo'sh model ro'yxati, noto'g'ri konfiguratsiya.
-   **Eslatma:** rasm handlerida `"429"` xatosi bo'lsa keyingi modelga
    o'tish mavjudligi qayd etilgan; bu Gemini rate-limit bo'lsa keraksiz
    qo'shimcha so'rovlar keltirishi mumkin. Qayta urinish siyosati aniq
    bo'lsin.

### BOT-004 --- `markdown_to_html` va Telegram xabar uzunligi

-   **Daraja:** MEDIUM
-   **Holat:** PARTIALLY FIXED / NOT FIXED
-   **Dalil:** rasm javobini yuborishda noto'g'ri HTML yoki 4096
    belgidan uzun matn xatoga olib kelishi mumkin.
-   **Tekshiruv:** ichma-ich/bir-birini kesib o'tuvchi Markdown
    belgilari, HTML escape, teglar muvozanati, xabar uzunligi.
-   **Talab:** Telegram uchun xavfsiz formatlash/fallback; teglarni
    buzib kesmaslik.

### BOT-005 --- FSM holatida rasm handleri ishlashi

-   **Daraja:** LOW
-   **Holat:** NEEDS AUDIT
-   **Dalil:** `handle_image(message, state)` ichida `state`
    ishlatilmasligi qayd etilgan.
-   **Xavf:** foydalanuvchi boshqa FSM jarayonida bo'lsa ham rasm
    tahliliga ketishi mumkin.
-   **Tekshiruv:** chek kutilayotgan holat va boshqa state'larda handler
    tartibi/filterlar kutilganidek ishlashini tekshirish.

### BOT-006 --- Rasm handlerining MIME turi

-   **Daraja:** LOW
-   **Holat:** PARTIALLY FIXED
-   **Dalil:** `Part.from_bytes(..., mime_type="image/jpeg")`
    ishlatiladi.
-   **Izoh:** Telegram `photo` odatda JPEG; hozircha past xavf. Fayl
    turi o'zgarsa yoki document orqali rasm yuborish qo'llansa, MIME
    aniqlash kerak bo'lishi mumkin.

### BOT-007 --- Tibbiy xavfsizlik va 103 tavsiyasi

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** rasm/audio/matn AI javoblarida shoshilinch xavf
    bo'lsa tez yordam 103 yoki shifokor tavsiyasi; tashxisni qat'iy
    tasdiqlamaslik; birinchi yordam bilan cheklanish.
-   **Talab:** prompt va UI matnlarini tekshirish; noaniq tibbiy holatda
    xavfsiz ogohlantirish.

### BOT-008 --- Gemini konfiguratsiyasi va maxfiy kalitlar

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi test logida:** Gemini konfiguratsiyasi borligi qayd
    etilgan; bu production kalitining to'g'ri va xavfsiz ekanini
    isbotlamaydi.
-   **Tekshiruv:** env validation, placeholder kalitni rad etish,
    kalitni logga chiqarmaslik, model nomlari va API xatosi.
-   **Talab:** kalitlarni chat, hisobot yoki Git'ga chiqarib
    yubormaslik.

------------------------------------------------------------------------

# 4. PostgreSQL va ma'lumotlar bazasi

### DB-001 --- `approve_receipt_and_grant` va boshqa DB API'lar

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** `bot.py` chaqiradigan barcha `database.*` funksiyalar
    haqiqatan mavjudmi, imzolari mosmi va import/runtime testlari bormi.

### DB-002 --- To'lovlar uchun atomik transaction

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** receipt status, charge ID, Premium grant, points va
    log bir nechta qadam bo'lsa, transaction/rollback ishlashi.
-   **Talab:** qisman commit yoki takroriy grant bo'lmasin.

### DB-003 --- PostgreSQL duplicate charge ID constraint

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** PostgreSQL'da duplicate `charge_id` bo'yicha
    tekshiruv pending bo'lgan.
-   **Tekshiruv:** unique constraint haqiqatan mavjudligi, eski
    duplicate yozuvlar va concurrency holati.

### DB-004 --- Connection pool resurslari

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Kontekst:** `ThreadedConnectionPool(maxconn=50)` ishlatilishi qayd
    etilgan.
-   **Tekshiruv:** har bir yo'lda connection qaytarilishi, xatoda
    yopilishi, pool exhausted bo'lishi, timeout va retry.

### DB-005 --- `is_user_banned()` va ban-cache

-   **Daraja:** LOW
-   **Holat:** FIXED AND TESTED (lokal testlar)
-   **Dalil:** `test_ban_cache_local.py` 45/45 o'tgan; thread-safe FIFO
    max 2000 / TTL max 30s cache haqida oldingi audit mavjud.
-   **Tekshiruv:** production'da ban/unban cache invalidation va DB
    bilan moslik; lokal test production integratsiyasini tasdiqlamaydi.

### DB-006 --- Refund DB funksiyalarining xatoga chidamliligi

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** SQL exception, rollback, connection release,
    idempotency, kun o'zgarishi va limitning manfiy bo'lib ketmasligi.

------------------------------------------------------------------------

# 5. Mini App / Web / UX

### WEB-001 --- Telegram Mini App `initData` tekshiruvi

-   **Daraja:** CRITICAL/HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi qaydlar bir-biriga zid bo'lishi mumkin:** avval `initData`
    security validation commit'i qayd etilgan, boshqa auditda esa
    verification to'liq tasdiqlanmagan.
-   **Tekshiruv:** server-side Telegram HMAC verification, `auth_date`
    eskirganini tekshirish, `user.id` ni faqat ishonchli tekshirilgan
    initData'dan olish, soxta client payload'ni rad etish.
-   **Talab:** amaldagi implementatsiyani va testlarini ko'rmasdan
    "xavfsiz" deb belgilamaslik.

### WEB-002 --- Mini App Premium sotib olish

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** plan ko'rsatish, Stars invoice, Telegram'dan qaytish,
    loading/error state, Premium aktivatsiyasi, takroriy to'lov, bekor
    qilish va backend bilan moslik.
-   **Talab:** narx UI va serverda mos; frontend hech qachon o'zi
    Premium grant qilmasin.

### WEB-003 --- 103 tez yordam tugmasi

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi so'rov:** Mini App'da 103 tugmasi ko'rinishi va ishlashi
    muammo sifatida ko'tarilgan.
-   **Tekshiruv:** tugma ko'rinishi, bosilgandagi action, mobil qurilma,
    telefon qo'ng'irog'i havolasi, matn va favqulodda vaziyatdagi
    foydalanish.

### WEB-004 --- Omad Barabani / roulette

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** g'ildirak eventlari/animatsiyasi va natija
    saqlanishi ishlamasligi mumkinligi ko'tarilgan.
-   **Tekshiruv:** click handler, animation completion, natijani
    serverda tekshirish, takroriy spin/ball abuse va mobil UX.

### WEB-005 --- Mini App barcha tugmalari va API'lari

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** Tibbiy Profil, Dori Eslatmalari, Ovozli Xabarlar,
    Kasalxona+Dorixona, Sog'liq Kalkulyatorlari, Daily tips, Premium,
    loading/error, API auth, offline/network failure.
-   **Talab:** tugmalarni birma-bir ro'yxatga olib, funksional smoke
    test.

### WEB-006 --- XSS, CSP va frontend xavfsizligi

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** CSP yetishmasligi va frontend xavfsizlikni audit
    qilish zarurati ko'tarilgan.
-   **Tekshiruv:** foydalanuvchi ma'lumotlari DOM'ga qanday qo'shiladi,
    `innerHTML`, CSP header, CORS, input validation, API auth, secrets.
-   **Talab:** faqat topilgan real xavflarni minimal o'zgarish bilan
    tuzatish.

### WEB-007 --- Mini App mobil dizayn va scroll

-   **Daraja:** LOW/MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** mobil ekran, safe area, scroll, klaviatura ochilishi,
    modal va tugmalar, kichik ekranlarda overflow.
-   **Talab:** real ekran o'lchamlarida sinov va regressiya tekshiruvi.

### WEB-008 --- Cache busting va Mini App URL

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi holat:** `.env` da
    `MINI_APP_URL=https://birinchiyordam.duckdns.org` ishlatilgani va
    `app_server.py` da no-cache/cache-bust mexanizmi borligi qayd
    etilgan.
-   **Tekshiruv:** bot menyusidagi URL, TLS, DNS, index.js/css
    yangilanishi, eski Cloudflare URL qolmaganligi.
-   **Eslatma:** joriy server holati qayta tekshirilmagan.

------------------------------------------------------------------------

# 6. Engagement, reminder va scheduler

### ENG-001 --- Premium Check-in takroriy yuborilishi

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** `engagement_logs` da unique
    `(user_id,event_type,event_date)` va `sent_at` bor; bu duplicate DB
    row'ni cheklaydi, lekin Telegram'ga ikki marta yuborilmasligini
    to'liq kafolatlamaydi.
-   **Tekshiruv:** parallel scheduler, restart, send
    muvaffaqiyatsizligi, lock, sent_at faqat muvaffaqiyatdan keyin
    yozilishi.
-   **Vaqt:** oldin 20:30 Asia/Tashkent deb belgilangan; hozirgi
    scheduler sozlamasini tekshirish kerak.

### ENG-002 --- "Javobini olish" callback

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi muammo:** Mini App/Daily Engagement callback
    `engagement_answer:10:10:{event_date}` ishlamayotgani qayd etilgan.
-   **Tekshiruv:** callback data generator/handler mosligi, event_date
    parsing, user ownership, eski tugma va xato javobi.

### ENG-003 --- Reminder va vaqt zonasi

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** Asia/Tashkent, DST/UTC konvertatsiyasi, kun
    almashishi, reminder qayta yuborilishi, foydalanuvchi vaqtini
    saqlash va scheduler restart recovery.

### ENG-004 --- Scheduler xatolari va retry

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** DB xatosi, Telegram 429, foydalanuvchi botni
    bloklashi, restart, duplicate job va loglar.

------------------------------------------------------------------------

# 7. Server, deployment va muhit

### OPS-001 --- Lokal kod, GitHub va production farqi

-   **Daraja:** HIGH
-   **Holat:** BLOCKED / NEEDS AUDIT
-   **Kontekst:** loyiha papkasida `.git` yo'q; `git rev-parse` ota
    `C:\Users\User` repo'ni ko'rsatgan. GitHub-check nusxasi va
    backup'lar mavjud bo'lishi mumkin.
-   **Talab:** lokal loyiha, `Birinchi-Yordam-bot_GITHUB_CHECK`, backup
    va production `/root/Birinchi-Yordam-bot` ni alohida solishtirish.
    Ota papkadagi Git repo'siga tasodifan tegmaslik.
-   **Qat'iy qoida:** user aniq ruxsat bermaguncha
    commit/push/deploy/restart yo'q.

### OPS-002 --- Zaxira fayllar va nusxalar

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Ma'lum backup nomlari:** `bot_backup_before_fix_20261024.py`,
    `bot_backup_before_image_fix.py`; eski
    `Birinchi yordam-bot_BACKUP_20261018` papkasi ham borligi qayd
    etilgan.
-   **Tekshiruv:** mavjudligini, hash'ini, qaysi versiyaga tegishli
    ekanini tekshirish. Backup'ni avtomatik ravishda hozirgi "to'g'ri"
    kod deb qabul qilmaslik. Ustiga yozmaslik.

### OPS-003 --- Python versiyasi, venv va requirements

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** `requirements.txt` da `aiogram==3.0.0b5` kabi eski
    pin bo'lishi mumkin; venv Python311 yo'li yo'q bo'lishi mumkinligi
    aytilgan.
-   **Tekshiruv:** hozirgi Python versiyasi, venv interpreter,
    o'rnatilgan package versiyalari, `requirements.txt` va real kod
    mosligi.
-   **Talab:** paketlarni audit tugamasdan yangilamaslik.

### OPS-004 --- Systemd xizmatlari va Telegram polling conflict

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Oldingi holatlar:** `birinchi-yordam-bot.service` va
    `birinchi-yordam-app.service` faol bo'lgan; oldin
    `TelegramConflictError: terminated by other getUpdates request`
    kuzatilgan, keyin bitta bot jarayoni borligi qayd etilgan.
-   **Tekshiruv:** joriy processlar, systemd unit'lar, boshqa
    server/provider'da polling bor-yo'qligi, loglar.
-   **Talab:** tekshirmasdan restart yoki service disable qilmaslik.

### OPS-005 --- Server resurslari

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi konfiguratsiya:** DigitalOcean Ubuntu 24.04.5, 512 MB RAM
    / 10 GB disk.
-   **Tekshiruv:** RAM, disk, log hajmi, DB pool, restart/oom, disk
    to'lishi va backup joyi.

### OPS-006 --- Portlar va servislarning sog'ligi

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** `app_server.py` localhost:8080; bot health port
    10000; oldin port 8000 bo'yicha fix qayd etilgan.
-   **Tekshiruv:** real port binding, systemd unit va health endpoint
    mosligi.

### OPS-007 --- GitHub va secret hygiene

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** `.env`, tokenlar, DB URL, pending DB, backup fayllar
    va loglar Git'ga ketmaganmi; `.gitignore` to'g'ri ishlaydimi.
-   **Talab:** secret qiymatlarini hisobotga chiqarmaslik.

------------------------------------------------------------------------

# 8. Admin va umumiy xavfsizlik

### SEC-001 --- Admin buyruqlariga ruxsat nazorati

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** approve/reject, Premium grant, reconcile, ban/unban
    va admin komandalarining har biri server-side admin ID tekshiruviga
    egami.

### SEC-002 --- Callback data tekshiruvi

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** noto'g'ri/uzun callback, manfiy ID, user ownership,
    stale callback, takroriy callback, unknown callback.

### SEC-003 --- Admin rate limiting / abuse

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi qayd:** admin rate limits auditda ko'tarilgan.
-   **Tekshiruv:** bruteforce/ko'p callback, flood, admin endpoint
    abuse.

### SEC-004 --- Error loglarda maxfiy ma'lumot

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** payment payload, user medical profile, API key, raw
    initData, personal data logga yozilmayaptimi.
-   **Talab:** xatoni tashxislash uchun yetarli metadata, lekin maxfiy
    qiymatlar redacted.

### SEC-005 --- Env konfiguratsiyasi

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** `ADMIN_ID`, `DATABASE_URL`, Gemini key, bot token,
    `MINI_APP_URL`, payment config. Majburiy qiymatlar yo'q yoki
    noto'g'ri bo'lsa, bot xavfsiz xato bilan to'xtasin.
-   **Oldingi qayd:** `ADMIN_ID=0` default xavfi bo'lishi mumkin.

------------------------------------------------------------------------

# 9. Testlar va avtomatlashtirish

### TEST-001 --- `test_image_handler.py` 11/11 o'tishi

-   **Daraja:** HIGH
-   **Holat:** NOT FIXED (oxirgi test natijasi)
-   **Dalil:** 10 passed, 1 failed ---
    `test_f2_refund_fails_after_download_failure`.
-   **Talab:** testni zaiflashtirmasdan production handlerdagi xatoni
    tuzatish va qayta test qilish.

### TEST-002 --- D2: Telegram send failure testlari

-   **Daraja:** MEDIUM
-   **Holat:** PARTIALLY TESTED
-   **Tekshiruv:** `edit_text` xatosi, HTML fallback, 4096 belgidan uzun
    javob, bir javobdan ortiq yuborilmasligi.

### TEST-003 --- Refund/limit boundary testlari

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** refund xatosi, yarim tun, limit 0, parallel request,
    Premium expired, DB connection error.

### TEST-004 --- Payment integration testlari

-   **Daraja:** HIGH
-   **Holat:** BLOCKED / NEEDS AUDIT
-   **Sabab:** 26 ta test o'tishi mock asosidagi test ekanini bildiradi;
    haqiqiy Telegram Stars to'lovi va production PostgreSQL bilan
    integratsiya isbotlanmagan.
-   **Talab:** Telegram test muhitida va alohida DB'da xavfsiz
    integration test.

### TEST-005 --- CI / regression suite

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** testlarni bitta hujjatlashtirilgan buyruq bilan ishga
    tushirish, exit code, CI mavjudligi, test data izolatsiyasi.

### TEST-006 --- Coverage va testlar ro'yxati

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** payment, manual receipt, image, audio, Mini App API,
    reminders, scheduler, database transaction va auth test bilan qamrab
    olinganmi.

------------------------------------------------------------------------

# 10. Funksional talablar va mahsulot

### FEAT-001 --- PDF yaratish funksiyasi

-   **Daraja:** LOW/MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Oldingi audit:** PDF generator topilmagani qayd etilgan.
-   **Tekshiruv:** loyiha talabi hali dolzarbmi; mavjud PDF eksport kodi
    va kutubxona bormi. Yo'q bo'lsa, alohida feature sifatida
    rejalashtirish.

### FEAT-002 --- Tibbiy profil

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** saqlash/o'qish, foydalanuvchi ID ownership, profil
    bo'sh bo'lishi, AI context, maxfiylik.

### FEAT-003 --- Dori eslatmalari

-   **Daraja:** MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** vaqt zonasi, takroriy yuborish, o'chirish/tahrirlash,
    scheduler restart, foydalanuvchi botni bloklashi.

### FEAT-004 --- Kunlik maslahatlar va engagement

-   **Daraja:** LOW/MEDIUM
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** takrorlanmaslik, til/vaqt, "Javobini olish" callback,
    Premium CTA spam bo'lmasligi.

### FEAT-005 --- Bepul AI limiti va Premium kvotalari

-   **Daraja:** HIGH
-   **Holat:** NEEDS AUDIT
-   **Tekshiruv:** birinchi bepul savol/kun, Premium daily quota,
    parallel request, muvaffaqiyatsiz AI chaqiruvi uchun refund, kun
    almashishi, foydalanuvchi plan'i tugashi.

------------------------------------------------------------------------

# 11. Ishlash tartibi --- bitta-bittadan bajarish

**Muhim tartib:** hamma narsani birdan o'zgartirmaslik. Har bosqichda
audit → kichik patch → tegishli test → regression suite → natijani
jadvalga yozish.

1.  **Bosqich 1 --- Lokal nusxani himoyalash:** joriy fayllar, backup va
    SHA-256 hash'larini qayd etish. Git ota papkasiga tegmaslik.
2.  **Bosqich 2 --- D2/D3 image handler fix:** `bot.py` ni minimal
    o'zgartirish; `test_image_handler.py` dagi 11 testni o'zgartirmasdan
    11/11 ga yetkazish; kerak bo'lsa yangi test qo'shish.
3.  **Bosqich 3 --- Regression:** payment 26/26, ban-cache 45/45,
    py_compile; barcha exit code'lar 0.
4.  **Bosqich 4 --- DB API audit:** `bot.py` ishlatadigan DB
    funksiyalari, jumladan `approve_receipt_and_grant` mavjudligi va
    imzolari.
5.  **Bosqich 5 --- Payment security:** manual receipt, Stars
    validation, charge ID idempotency, unknown payload, reconciliation,
    admin auth.
6.  **Bosqich 6 --- Mini App security:** `initData` HMAC/auth_date, API
    ownership, CSP/XSS, Premium flow.
7.  **Bosqich 7 --- Audio/AI + limits:** handler fallback, refund,
    duplicate reply, API failure.
8.  **Bosqich 8 --- Scheduler/reminders/engagement:** timezone, parallel
    sends, restart recovery, callback.
9.  **Bosqich 9 --- UI/functionality:** 103, roulette, buttons, mobile
    layout, PDF talabini aniqlash.
10. **Bosqich 10 --- Lokal vs GitHub vs production diff:** faqat user
    ruxsati bilan deploy rejasini tayyorlash; deploy alohida tasdiq
    talab qiladi.

------------------------------------------------------------------------

# 12. Har bir tuzatishdan keyingi majburiy checklist

-   [ ] Muammo real kodda tasdiqlandi.
-   [ ] Fayl va qator raqami qayd etildi.
-   [ ] Minimal patch tayyorlandi.
-   [ ] Oldingi testlar o'zgartirib zaiflashtirilmadi.
-   [ ] Yangi regression test qo'shildi.
-   [ ] Tegishli testlar o'tdi.
-   [ ] `py_compile` o'tdi.
-   [ ] `git diff --check` faqat to'g'ri repo'da tekshirildi.
-   [ ] Maxfiy ma'lumotlar log yoki diff'da yo'q.
-   [ ] Lokal, GitHub va production holatlari aralashtirilmadi.
-   [ ] Commit/push/deploy/restart uchun alohida ruxsat olindi.
-   [ ] Ishlar jadvalidagi status dalil bilan yangilandi.

## Yakuniy qoida

**Bu faylni master checklist sifatida ishlat.** Har bir bandni avval
hozirgi kodda tasdiqla, keyin alohida tuzat. Eski audit qaydlari
avtomatik ravishda hozirgi kodning holati deb qabul qilinmasin. Test
o'tishi production integratsiyasini to'liq isbotlamaydi. Hech qachon
deploy'ni avtomatik bajarma.
