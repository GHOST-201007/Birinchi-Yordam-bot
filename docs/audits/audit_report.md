# Audit report — test isolation and AI limit test (2026-10-26)

Only results that were actually run and observed are recorded here.
Interpreter: `.\venv\Scripts\python.exe` (Python 3.11).

## 1. PAY-010 — `_parse_admin_id` (bot.py)
- Bug: local `import logging` inside the function shadowed the module name -> `UnboundLocalError`.
- Fix: removed the local `import logging` lines (module-level `logging` is used). Validation logic unchanged.
- Result: `test_admin_auth` — 3/3 OK.

## 2. Production DB access during tests (test_ban_cache_local.py)
- Cause: `test_image_handler` imports `bot` at module level, which runs `load_dotenv()` and imports the
  real `database` module. When `test_ban_cache_local` was loaded later in the same process, its
  psycopg2/dotenv stubs came too late: `database` already had the real `DATABASE_URL` and real driver.
  Its Python socket guard does not cover libpq (C library), so a real connection was attempted.
- The isolation assertion used `assertEqual` on `DATABASE_URL`, which printed the full URL on failure.
- Fix (test file only):
  - Stubs and network guard are installed only in a separate process (`BY_BAN_CACHE_ISOLATED=1`).
  - In a shared process the module never imports `database`; `load_tests` runs one test that starts
    the suite in a clean child process with secret env vars removed and a stub `DATABASE_URL`.
  - The child refuses to run (`RuntimeError`) if `database`, `bot`, `psycopg2` or `dotenv` are already loaded.
  - The URL assertion no longer prints the value.
- Result: 45/45 OK in the isolated child, including `test_driver_is_stub`, `test_no_real_pool_created`,
  `test_real_get_connection_never_used`, `test_network_blocked`.

> Action needed: the production DB password was printed in an earlier failing run. Rotate it.

## 3. `test_ai_limit_free_and_premium_tiers` — `15 != 14`
- `refund_daily_request` (database.py) first runs `SELECT last_request_date FROM users WHERE user_id = %s`
  and refunds only if it equals today (column is TEXT, ISO date).
- The test's `FakeCursor` did not handle that query; it fell through to the default `(1,)` row,
  so `1 != today` and the refund was skipped. Production code is consistent with its documented behavior.
- Verdict: test fake was incomplete; production code not changed. Limits (Free 1, Pro 15, Plus 30, Ultra 100) untouched.
- Fix (test file only): `FakeCursor` handles `SELECT last_request_date`; `setUp` replaces
  `database.ThreadedConnectionPool` with a class that raises, so these tests cannot open a real DB pool.
- Result: test OK when run alone.

## 4. Full run
`.\venv\Scripts\python.exe -m unittest test_admin_auth test_payment_fixes test_image_handler test_ban_cache_local -v`
- Parent process: `Ran 41 tests — OK` (includes 1 delegating test for the ban-cache suite).
- Isolated child: `Ran 45 tests — OK`.
- Error/traceback lines in the output (`DB down`, `500 internal`) are expected logs from mocked failure-path tests.

## Changed files
- `bot.py` — `_parse_admin_id` only.
- `test_ban_cache_local.py` — isolation gating, subprocess delegation, redacted assertion.
- `test_payment_fixes.py` — FakeCursor query handler, real-pool guard.
- `test_admin_auth.py` — created earlier in this session (unchanged in this step).

No commit, push, deploy, restart, production DB connection or `.env` output was performed.
