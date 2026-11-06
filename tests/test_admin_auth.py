import os
import sys
import unittest
import importlib
import logging
from io import StringIO

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

class TestAdminAuth(unittest.TestCase):
    def setUp(self):
        # Ensure fresh import each test
        if 'bot' in sys.modules:
            del sys.modules['bot']
        self.original_env = os.environ.copy()
        # Capture logs
        self.log_stream = StringIO()
        self.handler = logging.StreamHandler(self.log_stream)
        self.logger = logging.getLogger()
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        self.logger.removeHandler(self.handler)
        self.handler.close()

    def test_valid_admin_id(self):
        os.environ['ADMIN_ID'] = '12345'
        import bot
        importlib.reload(bot)
        self.assertEqual(bot.ADMIN_ID, 12345)
        self.assertIn('ADMIN_ID set to 12345', self.log_stream.getvalue())

    def test_invalid_non_numeric(self):
        os.environ['ADMIN_ID'] = 'abc'
        # Import should cause SystemExit due to invalid ADMIN_ID
        with self.assertRaises(SystemExit):
            import bot
            importlib.reload(bot)

    def test_zero_admin_id_warns(self):
        os.environ['ADMIN_ID'] = '0'
        import bot
        importlib.reload(bot)
        self.assertEqual(bot.ADMIN_ID, 0)
        self.assertIn('ADMIN_ID set to 0; admin‑only commands will be disabled.', self.log_stream.getvalue())

if __name__ == '__main__':
    unittest.main()
