"""
test_requirements_pinned.py — P2-4: requirements.txt dagi barcha kutubxonalar serverdagi versiyaga qotirilgan.
"""
import os
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = {"aiogram", "aiohttp", "apscheduler", "google-genai", "psycopg2-binary", "python-dotenv"}


class RequirementsPinnedTest(unittest.TestCase):
    def test_all_pinned(self):
        with open(os.path.join(PROJECT_DIR, "requirements.txt"), encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        names = set()
        for line in lines:
            self.assertIn("==", line, f"qotirilmagan: {line}")
            names.add(line.split("==")[0].lower())
        self.assertEqual(names, REQUIRED)


if __name__ == "__main__":
    unittest.main()
