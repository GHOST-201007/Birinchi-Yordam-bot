"""
test_docs.py — P2-5: hujjatlar joriy holatga mos (PostgreSQL, run_dev.py faqat lokal).
"""
import os
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(PROJECT_DIR, rel), encoding="utf-8") as f:
        return f.read()


class DocsTest(unittest.TestCase):
    def test_deploy_md_says_postgres(self):
        text = read("docs/DEPLOY.md")
        self.assertNotIn("Database SQLite", text)
        self.assertIn("PostgreSQL (Neon)", text)
        self.assertIn("DATABASE_URL", text)

    def test_run_dev_marked_local_only(self):
        head = read("run_dev.py")[:600]
        self.assertIn("FAQAT LOKAL", head)


if __name__ == "__main__":
    unittest.main()
