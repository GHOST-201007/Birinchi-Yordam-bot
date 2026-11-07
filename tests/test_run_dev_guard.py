"""
test_run_dev_guard.py — run_dev.py himoyasi: RUN_DEV_ALLOWED=1 bo'lmasa (production BOT_TOKEN bilan tasodifan
ishga tushmasligi uchun) hech narsa qilmasdan to'xtaydi.

run_dev.py import qilinmaydi (u modul darajasida servislarni ishga tushiradi). Guard funksiyasi AST orqali ajratib
olinadi; haqiqiy jarayon esa bo'sh PATH li vaqtinchalik papkadagi NUSXADA ishga tushiriladi: .env, bot.py,
app_server.py, cloudflared/npx u yerda yo'q, shuning uchun guard buzilgan taqdirda ham hech qanday yon ta'sir bo'lmaydi.
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DEV = os.path.join(PROJECT_DIR, "run_dev.py")

SIDE_EFFECT_CALLS = {"Popen", "open", "signal", "run", "system", "remove", "write", "connect_ex", "sleep"}


def load_tree():
    with open(RUN_DEV, encoding="utf-8") as f:
        return ast.parse(f.read())


def load_guard():
    tree = load_tree()
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check_dev_allowed")
    ns = {"os": os}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), RUN_DEV, "exec"), ns)
    return ns["check_dev_allowed"]


def call_name(node):
    f = node.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)


class GuardFunctionTest(unittest.TestCase):
    def setUp(self):
        self.check = load_guard()

    def test_only_exact_1_allows(self):
        self.assertTrue(self.check({"RUN_DEV_ALLOWED": "1"}))
        for value in ("0", "", "true", "yes", "True", " 1", "1 ", "01", "2"):
            with self.subTest(value=value):
                self.assertFalse(self.check({"RUN_DEV_ALLOWED": value}))

    def test_missing_variable_blocks(self):
        self.assertFalse(self.check({}))
        self.assertFalse(self.check({"BOT_TOKEN": "123:abc", "MINI_APP_URL": "https://x.trycloudflare.com"}))

    def test_default_reads_process_environment_not_dotenv(self):
        with mock.patch.dict(os.environ, {"RUN_DEV_ALLOWED": "1"}):
            self.assertTrue(self.check())
        env = {k: v for k, v in os.environ.items() if k != "RUN_DEV_ALLOWED"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(self.check())


class GuardPlacementTest(unittest.TestCase):
    def test_guard_runs_before_any_side_effect_and_exits_nonzero(self):
        tree = load_tree()
        idx = None
        for i, node in enumerate(tree.body):
            if isinstance(node, ast.If) and any(isinstance(c, ast.Call) and call_name(c) == "check_dev_allowed"
                                               for c in ast.walk(node.test)):
                idx = i
                guard = node
                break
        self.assertIsNotNone(idx, "run_dev.py da check_dev_allowed() tekshiruvi topilmadi")
        # Guard'dan oldingi modul darajasidagi gaplarda yon ta'sirli chaqiruvlar bo'lmasligi kerak
        for node in tree.body[:idx]:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef)):
                continue
            for c in ast.walk(node):
                if isinstance(c, ast.Call):
                    self.assertNotIn(call_name(c), SIDE_EFFECT_CALLS, f"guard'dan oldin yon ta'sir: {call_name(c)}")
        # Guard ichida nol bo'lmagan kod bilan chiqish bor
        exits = [c for c in ast.walk(guard) if isinstance(c, ast.Call) and call_name(c) == "exit"]
        self.assertTrue(exits and all(isinstance(e.args[0], ast.Constant) and e.args[0].value == 1 for e in exits))


class GuardProcessTest(unittest.TestCase):
    def run_copy(self, allowed):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "run_dev.py")
            shutil.copy(RUN_DEV, script)
            env = {k: v for k, v in os.environ.items() if k != "RUN_DEV_ALLOWED"}
            env.update({"PATH": tmp, "PYTHONIOENCODING": "utf-8", "BOT_TOKEN": "111:PROD-TOKEN-MARKER"})
            if allowed:
                env["RUN_DEV_ALLOWED"] = "1"
            proc = subprocess.run([sys.executable, script], cwd=tmp, env=env, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=60)
            return proc, os.listdir(tmp)

    def test_blocked_without_permission_exit_1_no_side_effects(self):
        proc, files = self.run_copy(allowed=False)
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("RUN_DEV_ALLOWED=1", out)
        self.assertIn("production", out)
        self.assertNotIn("Veb-server", out)                   # hech qanday ish boshlanmagan
        self.assertNotIn("PROD-TOKEN-MARKER", out)            # token chiqarilmaydi
        self.assertEqual(files, ["run_dev.py"])               # .env va boshqa fayl yaratilmagan

    def test_proceeds_when_explicitly_allowed(self):
        # Sandbox'da app_server.py yo'q: skript guard'dan o'tib, veb-server bosqichida o'zi to'xtaydi
        proc, files = self.run_copy(allowed=True)
        out = proc.stdout + proc.stderr
        self.assertNotIn("to'xtatildi: RUN_DEV_ALLOWED", out)
        self.assertIn("Veb-server", out)
        self.assertEqual(files, ["run_dev.py"])


if __name__ == "__main__":
    unittest.main()
