"""
test_repo_hygiene.py — P2-7: keraksiz fayllar repoda yo'q, xavfli skriptlarda ogohlantirish bor.
"""
import os
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RepoHygieneTest(unittest.TestCase):
    def test_git_history_dumps_removed(self):
        for rel in ("docs/audits/all_git_history.txt",
                    "docs/audits/all_git_history_utf8.txt",
                    "docs/audits/git_search.txt"):
            self.assertFalse(os.path.exists(os.path.join(PROJECT_DIR, rel)), rel)

    def test_dangerous_scripts_have_warning(self):
        for rel in ("scripts/patch_db.py", "scripts/measure_latency.py"):
            with open(os.path.join(PROJECT_DIR, rel), encoding="utf-8") as f:
                head = f.read(300)
            self.assertIn("PRODUCTION BAZADA", head, rel)


if __name__ == "__main__":
    unittest.main()
