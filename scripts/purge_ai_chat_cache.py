"""
purge_ai_chat_cache.py — ai_response_cache dan 'ai_chat' yozuvlarini o'chiradi (P0-1).

Bu yozuvlar foydalanuvchilarning tibbiy profili asosida yozilgan AI javoblari
bo'lib, boshqa foydalanuvchilarga ko'rsatilmasligi kerak.

Serverda bir marta ishga tushiring (loyiha papkasidan):
    venv/bin/python scripts/purge_ai_chat_cache.py

.env dagi DATABASE_URL ishlatiladi (PostgreSQL), psycopg2 bo'lmasa — lokal SQLite.
"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import medicine_db  # noqa: E402


def purge_ai_chat_cache() -> int:
    """'ai_chat' turidagi barcha kesh yozuvlarini o'chiradi va o'chirilganlar sonini qaytaradi."""
    ph = medicine_db._placeholder()
    conn = None
    c = None
    try:
        conn = medicine_db._get_conn()
        c = conn.cursor()
        c.execute(f"DELETE FROM ai_response_cache WHERE response_type = {ph}", ("ai_chat",))
        deleted = c.rowcount
        conn.commit()
        return deleted
    except Exception:
        medicine_db._safe_rollback(conn)
        raise
    finally:
        medicine_db._safe_close(c, conn)


if __name__ == "__main__":
    print(f"Baza turi: {medicine_db.DB_TYPE}")
    count = purge_ai_chat_cache()
    print(f"✅ O'chirildi: {count} ta 'ai_chat' yozuvi")
