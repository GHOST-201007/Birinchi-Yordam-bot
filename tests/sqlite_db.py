"""
sqlite_db.py — database.py funksiyalarini HAQIQIY SQL semantikasi bilan sinash uchun kichik test bazasi.

PostgreSQL emas, SQLite: atomar shartli UPDATE (WHERE ...), rowcount, rollback va parallel yozuvchilar
(har oqim o'z ulanishi bilan, yozuvlar fayl qulfi orqali ketma-ket) haqiqiy bajariladi — regex bilan
soxtalashtirilgan kursordan farqli o'laroq. database.py ning SQL'i quyidagicha moslanadi:
  `%s` -> `?`, `FOR UPDATE` olib tashlanadi (yozuvchilar baribir ketma-ket), `IS DISTINCT FROM` -> `IS NOT`.

Ishlatish:
    db = SqliteDB(); self.addCleanup(db.close)
    db.add_user(1, medicine_score=5)
    with db.patched():
        database.some_function(1)
    db.row(1)["medicine_score"]
"""
import os
import re
import sqlite3
import tempfile
from unittest import mock

import database

USERS_DDL = """
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    registered_at TEXT,
    is_premium INTEGER DEFAULT 0,
    premium_type TEXT DEFAULT 'free',
    daily_requests INTEGER DEFAULT 0,
    last_request_date TEXT,
    medicine_score INTEGER DEFAULT 0,
    premium_until TEXT,
    waiting_receipt INTEGER DEFAULT 0,
    premium_expires_at TEXT,
    full_name TEXT,
    username TEXT,
    free_ai_used INTEGER DEFAULT 0,
    last_spin_date TEXT,
    has_discount INTEGER DEFAULT 0,
    discount_expires_at TEXT,
    pending_spin_prize INTEGER,
    spin_ai_bonus INTEGER DEFAULT 0,
    premium_expiry_notified_for TEXT,
    is_banned INTEGER DEFAULT 0,
    banned_until TEXT
)
"""


class _Cursor:
    def __init__(self, cur):
        self._cur = cur
        self._rows = []

    def execute(self, sql, params=()):
        sql = sql.replace("%s", "?")
        sql = re.sub(r"\s+FOR UPDATE\b", "", sql)
        sql = sql.replace("IS DISTINCT FROM", "IS NOT")
        self._cur.execute(sql, tuple(params))
        # SELECT natijasi darrov o'qib olinadi: ochiq statement o'qish qulfini ushlab, parallel commit'ni to'sib qo'ymasin
        self._rows = list(self._cur.fetchall()) if self._cur.description is not None else []
        return self

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        self._cur.close()


class _Conn:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return _Cursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class SqliteDB:
    def __init__(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = os.path.join(self._dir.name, "users.db")
        con = sqlite3.connect(self.path)
        con.execute(USERS_DDL)
        con.commit()
        con.close()

    def connect(self):
        """database.get_connection o'rniga: har chaqiruvda yangi ulanish (oqim xavfsiz)."""
        return _Conn(sqlite3.connect(self.path, timeout=30))

    def patched(self):
        return mock.patch.object(database, "get_connection", self.connect)

    def close(self):
        self._dir.cleanup()

    # ── test yordamchilari (to'g'ridan-to'g'ri SQLite) ──
    def add_user(self, user_id, **cols):
        cols.setdefault("registered_at", "2026-01-01T00:00:00+05:00")
        names = ["user_id"] + list(cols)
        con = sqlite3.connect(self.path)
        con.execute(f"INSERT INTO users ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})",
                    [user_id] + list(cols.values()))
        con.commit()
        con.close()

    def row(self, user_id):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        con.close()
        return dict(r) if r is not None else None
