# BIRINCHI YORDAM BOT — MASTER AUDIT VA PRE-GIT / PRE-DEPLOY HISOBOTI
**Sana:** 2026-11-02 (Yangilangan yakuniy registr)  
**Holat:** Barcha P0/P1/P2 xatolar tuzatildi, testlar izolyatsiya qilindi, **109 PASS / 0 FAIL / 2 BLOCKED (live API)** tasdiqlandi.  
**Chegara:** Git commit/push va production deploy/restart **QILINMADI** (pre-Git / pre-deploy darajasida to'xtatildi).

---

## 1. Zaxira (Backup) va Izolyatsiya Tasdig'i

| Zaxira paketi / fayl | Holat | Izoh |
|---|---|---|
| `BACKUP_PHASE1_20261101/` | Saqlangan (o'zgarmagan) | Dastlabki Phase 1 zaxira nusxasi (39 ta fayl + `SHA256_MANIFEST.txt`) |
| `BACKUP_PHASE4_PREFIX_20261102/` | Yaratildi | Phase 4 (Master Fix) oldidan olingan to'liq zaxira nusxasi (35 ta fayl) |
| `pending_reconcile.db` | O'zgarmagan (`SHA256: EBB7162EE3FFEC4FDDCD92631FA0D8D2FB4F8B6F20CEE706287D440D703A6589`) | Phase 1 zaxirasi bilan 100% bir xil; testlar vaqtinchalik faylda (`TemporaryDirectory`) ishlaydi |
| `users.db` | O'zgarmagan (`SHA256: D22299A24C2F67ABF1AFD1F4692698C0AD33EBEDED974BDE4CA695021EFECD4B`) | Testlar davomida umuman tegilmadi |

---

## 2. Master Issue Register (P0 / P1 / P2 / P3)

| ID | Daraja | Kategoriya | Fayl va qatorlar | Muammo tavsifi va ildiz sababi | Holat | Tuzatish va test dalili |
|---|---|---|---|---|---|---|
| **ISS-001** (BUG-001) | **P0** | Payment / Stars / Reconciliation | `bot.py:429-450`, `2534-2999`, `database.py:1141-1255` | `process_paid_premium` ichida `record_payment_transaction` + `extend_paid_premium` bitta atomar tranzaksiyada bajarilishi, `validate_payment` orqali Stars (`XTR`) / legacy payload tekshiruvi, DB xatosida `pending_reconcile.db` ga dalil yozish va `/reconcile` komandasida faqat haqiqiy dalil asosida tiklash. | **FIXED** | `test_payment_fixes.py` (28 ta test: atomarlik, dublikat charge_id, noma'lum payload, `/reconcile` tamper-proof) |
| **ISS-002** (BUG-002) | **P1** | Telegram Delivery / Chunking / Refund | `bot.py:137-372`, `785-814`, `2199-2277`, `3148-3195` | Gemini javobida HTML parse xatosi, HTML escape (`&`, `<`, `>`) tufayli 4096 belgidan oshish, `"message is not modified"` xatosida yolg'on refund, timeout/tarmoq uzilishida dublikat xabar yuborish, va keyingi bo'lak (`idx > 0`) xatosida foydalanuvchini ogohlantirmaslik. | **FIXED** | `_build_ai_pieces`, `_send_piece`, `_deliver_ai_response` va `stream_gemini_to_message` fallback; `test_image_handler.py` (`test_e*`, `test_h1`–`test_h4`) |
| **ISS-003** | **P1** | DB Connection / Pool / Cursor Safety | `database.py:36-78`, `82-1536` | `PooledConnectionWrapper.close()` ko'p oqimli (multithreaded) chaqiruvda lock'siz edi; `rollback()` xato berganda yaroqsiz ulanish pool'ga qaytarilardi (`close=True` berilmasdi); 32 ta funksiyada `try/finally` va `c.close()` yo'q edi. | **FIXED** | `PooledConnectionWrapper` `threading.Lock()` va `self._broken` (`putconn(conn, close=True)`) bilan himoyalandi; barcha 32 funksiya `with _managed_cursor() as (conn, c):` ga o'tkazildi. `test_payment_fixes.py` (`test_db_*`, `test_pooled_*`) |
| **ISS-004** | **P1** | Missing DB Function (`receipt_timeout`) | `bot.py:3061`, `database.py:856-858` | `bot.py` `receipt_timeout` vazifasi `database.is_waiting_receipt(uid)` ni chaqirardi, ammo `database.py` da faqat `get_waiting_receipt(uid)` mavjud bo'lib, 5 daqiqadan keyin `AttributeError` yuzaga kelardi. | **FIXED** | `database.py:856-858` da `is_waiting_receipt(user_id) -> bool` qo'shildi. `test_payment_fixes.py:test_is_waiting_receipt_and_managed_cursor_cleanup` |
| **ISS-005** | **P1** | Voice Handler Quota Leak | `bot.py:2118-2277` | `handle_voice` ichida `try_consume_free_ai` / `try_consume_daily_request` `if not gemini_client:` tekshiruvidan OLDIN chaqirilgani sababli AI o'chiq bo'lganda limit bekorga kuyardi; shuningdek `refund_once()` va `_deliver_ai_response` yo'q edi. | **FIXED** | `if not gemini_client:` tekshiruvi limit yechishdan oldinga ko'chirildi; `try/except`, `refund_once()` va `_deliver_ai_response` ulandi. `test_image_handler.py:test_h6_voice_handler_no_quota_leak_when_gemini_unconfigured` |
| **ISS-006** | **P1** | Mini App `initData` UTC Timestamp Bug | `app_server.py:41` | `datetime.datetime.utcnow().timestamp()` Python'da naive datetime ni lokal vaqt mintaqasi (`UTC+5`) sifatida talqin qilib, `now_ts` ni haqiqiy UTC dan 5 soat (18000 s) orqaga surardi. Natijada `auth_ts > now_ts + 60` sharti barcha yangi Telegram WebApp `initData` so'rovlarini xato rad etardi. | **FIXED** | `datetime.datetime.now(datetime.timezone.utc).timestamp()` ga o'zgartirildi. `test_payment_fixes.py:test_app_server_validate_init_data_utc_correctness` |
| **ISS-007** | **P1** | SQLite Connection Leak & Test Isolation | `bot.py:482-575`, `test_payment_fixes.py:228-252` | `with sqlite3.connect(_PENDING_RECONCILE_DB) as conn:` tranzaksiyani yakunlasa ham, SQLite ulanishini (`conn.close()`) yopmasdi; shuningdek `test_payment_fixes.py` haqiqiy `pending_reconcile.db` fayliga yozardi. | **FIXED** | `bot.py` dagi barcha 5 ta reconcile funksiyasida `finally: conn.close()` qo'shildi; `test_payment_fixes.py` da `tempfile.TemporaryDirectory()` orqali `_PENDING_RECONCILE_DB` izolyatsiya qilindi. |
| **ISS-008** | **P2** | Quota Try-Consume DB Error & Double Refund Guard | `bot.py:3085-3115`, `3472-3526`, `4112-4180` | `handle_image`, `handle_voice`, `web_app_data_handler` va `handle_ai_chat` funksiyalarida DB xatosi yoki kutilmagan istisnoda ikki marta refund chaqirilishi yoki foydalanuvchiga xabar bormasligi xavfi bor edi. | **FIXED** | Barcha oqimlarda idempotent `refund_once()` va `try/except` himoyasi o'rnatildi. `test_image_handler.py:test_h5_db_error_during_try_consume_handled_gracefully` |
| **ISS-009** | **P2** | Engagement & Medicine DB Cursor/Connection Cleanup | `services/engagement.py:48-190`, `services/engagement_scheduler.py:12-162`, `medicine_db.py:72-895`, `bot.py:4310-4402` | `engagement.py`, `engagement_scheduler.py`, `medicine_db.py` va `bot.py` (`fallback_text`, `handle_engagement_answer`) da `conn = get_connection()` `try` dan tashqarida ochilib, `cursor.close()` yoki `rollback()` ba'zi chiqish yo'llarida chaqirilmasdi. | **FIXED** | `database._safe_close(c, conn)` / `_safe_rollback(conn)` va `medicine_db._safe_close(c, conn)` barcha funksiyalarga joriy qilindi. |
| **ISS-010** | **P3** | Bot Session Shutdown & Legacy Backup Syntax | `bot.py:4554-4558`, `BY_REPAIR_BACKUP_20261024/bot.py` | `main()` yakunida `bot.session.close()` `finally` blokida yo'q edi (tuzatildi). Eski arxiv papkasi `BY_REPAIR_BACKUP_20261024/bot.py` va `bot_backup_before_image_fix.py` ishlab chiqarishda ishlatilmaydi (qoidaga binoan o'chirilmadi). | **FIXED / DOCUMENTED** | `bot.py` `main()` ga `finally: await bot.session.close()` qo'shildi. |

---

## 3. BGE-M3 Vektor Qidiruvga Tayyorgarlik Rejasi (Faqat Arxitektura Rejasi — Kodga Qo'shilmadi)

1. **Maqsad**: `medicine_db.py` dagi mavjud 7 bosqichli qidiruv (`cache -> exact -> normalized -> alias -> active_ingredient -> ai_cache -> fuzzy`) natija bermaganda, Gemini API'ga murojaat qilishdan oldin `BAAI/bge-m3` ko'p tilli (o'zbek lotin/kiril + rus) embedding modeli yordamida semantik qidiruv bosqichini qo'shish.
2. **Ma'lumotlar bazasi sxemasi (keyingi bosqich uchun)**:
   - PostgreSQL da `pgvector` kengaytmasi (`CREATE EXTENSION IF NOT EXISTS vector;`) va `medicine_embeddings (medicine_id INT REFERENCES medicines(id), embedding vector(1024), model_version TEXT, updated_at TIMESTAMP)` jadvali (`HNSW` indeksi bilan: `USING hnsw (embedding vector_cosine_ops)`).
   - Lokal/fallback rejimda oldindan hisoblangan `.npz` / float32 matritsa orqali cosine similarity tekshiruvi.
3. **Xavfsiz chegara (Threshold)**:
   - Cosine similarity `>= 0.78` bo'lgandagina lokal dori ma'lumoti qaytariladi; `0.65 - 0.78` oralig'ida ehtimoliy nomzodlar sifatida kontekst boyitiladi; `< 0.65` bo'lsa mavjud Gemini AI oqimiga o'tiladi.
   - **Tibbiy xavfsizlik**: Vektor qidiruv faqat tasdiqlangan `medicines` va `FIRST_AID_DATA` yozuvlarini qaytaradi — hech qachon mustaqil doza to'qib chiqarmaydi.
