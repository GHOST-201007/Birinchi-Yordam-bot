"""
test_medicine_search.py — P1-1: oddiy chat so'zlariga dori kartasi chiqmasligi kerak.

medicine_db vaqtinchalik SQLite faylga yo'naltiriladi (production bazaga tegilmaydi).
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import medicine_db  # noqa: E402

CHAT_WORDS = [
    "ha", "ok", "rahmat", "salom", "yo'q", "yoq", "xo'p", "mayli", "assalomu alaykum",
    "qalaysiz", "yaxshi", "zo'r", "tushundim", "bilmadim", "nima", "kim", "qachon",
    "hm", "ha rahmat", "katta rahmat", "xayr", "ertaga", "bugun", "ajoyib", "albatta",
    "привет", "спасибо", "да", "нет", "ок",
]

REAL_MEDICINES = ["Paratsetamol", "Paracetamol", "No-shpa", "Aspirin", "Ibuprofen", "Smekta", "Loratadin"]


class MedicineSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        cls.patches = [
            mock.patch.object(medicine_db, "DB_TYPE", "sqlite"),
            mock.patch.object(medicine_db, "sqlite3", sqlite3, create=True),
            mock.patch.object(medicine_db, "_get_conn", lambda: sqlite3.connect(cls.db_path)),
        ]
        for p in cls.patches:
            p.start()
        medicine_db._cache.clear()
        medicine_db.init_medicine_db()

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):
            p.stop()
        medicine_db._cache.clear()
        os.remove(cls.db_path)

    def test_chat_words_not_found(self):
        for word in CHAT_WORDS:
            with self.subTest(word=word):
                result = medicine_db.find_medicine(word)
                self.assertFalse(result["found"], f"'{word}' → {result['source']}")

    def test_real_medicines_found(self):
        for name in REAL_MEDICINES:
            with self.subTest(name=name):
                self.assertTrue(medicine_db.find_medicine(name)["found"], name)

    def test_active_ingredient_whole_word(self):
        self.assertTrue(medicine_db.find_medicine("drotaverin")["found"])
        # So'z ichidagi bo'lak bo'yicha topilmaydi
        self.assertFalse(medicine_db.find_medicine("salitsil")["found"])

    def test_small_typo_still_found(self):
        self.assertTrue(medicine_db.find_medicine("Ibuprofn")["found"])


if __name__ == "__main__":
    unittest.main()
