# BIRINCHI YORDAM — MASTER FIX & PRE-GIT / PRE-DEPLOY VALIDATION

**Purpose:** Complete a careful, evidence-based audit and repair of all confirmed, actionable issues in the local Birinchi Yordam project. When finished, the local project must be in a verified state ready for a separate GitHub commit/push step, followed by a separate production-server deployment step.

**This task ends BEFORE Git operations and BEFORE deployment.** Do not commit, push, pull, deploy, restart services, connect to the production server, or change production data. The owner will review the final report and authorize Git and server work separately.

---

## 0. NON-NEGOTIABLE SAFETY RULES

1. Work only in the local project folder:
   `C:\Users\User\Desktop\Birinchi yordam-bot`
2. First verify the current working directory and identify the actual project root. Do not assume a Git repository exists here.
3. Do not run Git commands that could stage, commit, reset, clean, checkout, merge, rebase, push, or alter a parent repository. In particular, do not operate in `C:\Users\User` merely because Git discovers a parent `.git` directory.
4. Do not touch the separate `Birinchi-Yordam-bot_GITHUB_CHECK` clone unless only reading it is essential to a clearly documented comparison. Never copy files over it automatically.
5. Do not modify or delete any backup directory, including:
   - `BACKUP_PHASE1_20261101/`
   - `Birinchi yordam-bot_BACKUP_20261018/`
   - `BY_REPAIR_BACKUP_20261024/`
   - `venv_OLD_BACKUP_20261101/`
   - any other pre-existing backup.
6. Do not modify `bot_backup_before_image_fix.py` or other historical backup snapshots. The known `IndentationError` at line 2985 in `bot_backup_before_image_fix.py` is an old-backup-only issue; it is not evidence that the active `bot.py` is broken. Do not include historical backup files in active-project compilation or test commands.
7. Do not read, print, copy into reports, expose, or change secrets: `.env`, Telegram bot tokens, Gemini keys, database passwords, private keys, credentials, or user personal data. Never paste secret values into logs or the report. You may verify that required environment variables are present without printing their values.
8. Do not connect to production PostgreSQL, the production Telegram bot, Gemini, or any live external API. Do not run tests that make real API calls. Tests must use mocks, fakes, or isolated local test resources.
9. Do not run destructive database migrations or SQL against any real database. Do not delete, truncate, reset, or overwrite any existing database file.
10. Do not install Docker, download large models, change Windows/WSL setup, alter the server, or make unrelated machine-level changes.
11. Do not make broad speculative refactors. Fix confirmed defects with the smallest safe change that solves them. Preserve existing public interfaces, product behavior, pricing, plan entitlements, callback formats, and backwards compatibility unless a verified defect requires a change.
12. Before editing, inspect the current code and the relevant audit documents. Do not trust old reports blindly; verify every finding against the current files.
13. Preserve all existing user data and project files. No `git clean`, recursive deletion, mass formatting, or bulk line-ending conversion.
14. If a change has an uncertain behavioral or data impact, do not guess. Isolate it, explain the uncertainty, and leave it unchanged pending owner review.
15. Work in small, logically grouped repair batches. After each batch, run its targeted tests before continuing. Keep a rollback path.

## 1. PROJECT CONTEXT — VERIFY BEFORE RELYING ON IT

Known project facts (verify against the current checkout):

- Project: Telegram first-aid assistant “Birinchi Yordam”.
- Local root: `C:\Users\User\Desktop\Birinchi yordam-bot`.
- Main runtime: Python, aiogram 3.x; `bot.py` and `database.py`.
- Mini App: `app/index.html`, `app/style.css`, `app/app.js` (verify actual filenames; earlier reports sometimes refer to `app.js`).
- Web server: `app_server.py`.
- Engagement logic: `services/engagement.py`, `services/engagement_scheduler.py` and related modules, if present.
- Database: PostgreSQL through `psycopg2` and a connection pool in `database.py`; some local tests use SQLite or temporary files. Verify actual implementation.
- Production server path was previously `/root/Birinchi-Yordam-bot`; production services were `birinchi-yordam-bot.service` and `birinchi-yordam-app.service`. These are context only. Do not connect to or modify production in this task.
- Local Python 3.11.9 and a project virtual environment were previously installed. Verify the interpreter and environment; do not recreate or delete environments unnecessarily.
- The project has previously been found without its own `.git`; Git commands from this project path discovered the parent `C:\Users\User` repository. Re-check safely, but do not alter that parent repository.

### Previous test baseline — historical, must be revalidated

The PHASE 3 report stated:

- `py_compile` of active files passed.
- `test_admin_auth.py`: 3 passed.
- `test_payment_fixes.py`: 29 passed.
- `test_image_handler.py`: 15 passed.
- `test_ban_cache_local.py`: 46 passed (1 delegator plus 45 isolated child tests).
- `test_approve_receipt.py`: 7 passed.
- Reported total: 100 PASS, 0 FAIL, with `test_gemini.py` and `test_menu_button.py` intentionally BLOCKED because they make real API calls.

Do not double-count the ban-cache delegator/child tests. Report both the exact number of test cases in each command and the unique total. A historical PASS is not a current PASS until rerun.

### Previous PHASE 3 changes — verify current code

Reported active files changed:

- `bot.py`: `TELEGRAM_MAX_MESSAGE_LENGTH`, `chunk_text()`, Gemini image-response delivery separated from Gemini generation; HTML parse fallback to plain text; long answer chunking; refund handling.
- `database.py`: `PooledConnectionWrapper.close()` and connection/cursor cleanup in `register_user`, `create_manual_receipt`, `reject_receipt`, `try_consume_daily_request`, `refund_daily_request`, `try_consume_free_ai`, `refund_free_ai`.
- `test_image_handler.py`: new image-response delivery and chunking tests.
- `test_payment_fixes.py`: DB cleanup/rollback and wrapper tests.

PHASE 3 read-only post-audit findings that must be addressed or conclusively dispositioned:

**BUG-002 / Telegram response delivery**
- WARNING: if the first chunk is delivered and a later chunk fails, the user may receive an incomplete answer without a clear notice. Current refund only occurs when nothing was delivered.
- WARNING: an ambiguous client-side timeout may happen after Telegram has accepted a message; blindly retrying can create duplicate messages.
- WARNING: Markdown/code spans crossing chunk boundaries may render imperfectly.
- WARNING: untested branches include later-chunk failure, HTML expansion (e.g. text containing many `&` characters), and exact fallback chunk-size limits.
- Treat Telegram “message is not modified” as a special case when the existing answer may already be visible. Do not incorrectly refund an already delivered answer.
- Ensure HTML-escaped output length is checked, not just raw source text length.

**DB connection safety**
- WARNING: `PooledConnectionWrapper.close()` lacks an explicit lock; concurrent calls on the same wrapper may race and return a connection twice. Verify actual use and make it thread-safe if the wrapper can be shared across threads.
- WARNING: approximately 25 other database functions were reported to use plain `conn.close()` without `finally`, potentially leaking pooled connections on SQL errors. Inventory all call sites and audit them individually.
- WARNING: `handle_image` calls `try_consume_*` outside its user-facing error handling; a DB exception may propagate without a helpful user response. Verify current flow and handle safely without hiding operational errors.
- The prior tests used fake connections; psycopg2 production-pool behavior was not exercised. Do not connect to production. Add realistic isolated unit tests around the wrapper and transaction lifecycle.

**Test isolation**
- WARNING: reconciliation tests modified `pending_reconcile.db` during their run. Existing local data must not be touched by test runs. Isolate every file-backed test database in a fresh temporary directory or use safe fixture injection/monkeypatching. Preserve the original file byte-for-byte if a test must inspect it. Do not simply delete or recreate it.
- Do not let tests touch `users.db`, `pending_reconcile.db`, production DB URLs, or any existing user-data file.

**Out-of-scope findings from PHASE 3 that need a full-project audit**
- Other DB functions may leak connections on exceptions.
- Some bot handlers may close cursors/connections incorrectly if acquiring a connection fails.
- DB errors in quota reservation may lack user-facing handling.

## 2. REQUIRED WORKFLOW

### Step A — Establish safe baseline and inspect project

1. Confirm the project path, list top-level files/folders, and identify active source, tests, audit documents, configuration templates, deployment files, and backups.
2. Inspect `BIRINCHI_YORDAM_MASTER_AUDIT_2026-11-01.md` and any newer audit/status documents if present. Read the whole relevant document, not only its title or first section.
3. Read the current implementation of every function touched in PHASE 3 and all callers.
4. Safely check whether this exact project directory is a Git repository. If Git resolves to `C:\Users\User` or another parent, stop Git inspection there; do not stage or change anything. This task is not a Git task.
5. Record current file hashes/timestamps for files that may be modified. Create a fresh source-only backup in a new clearly named folder if needed. Exclude `.env`, credentials, databases, logs, virtual environments, caches, and personal data. Never overwrite a prior backup.
6. Establish a baseline using only safe offline tests. Capture exact command, interpreter path/version, exit code, counts, and skipped tests. Do not run real API tests.

### Step B — Build one master issue register

Create/update a project audit document (prefer the existing master audit file) containing a numbered table with:

- ID
- Severity (P0 critical, P1 high, P2 medium, P3 low)
- Component/file/function and line numbers
- Evidence/reproduction
- User impact
- Proposed minimal fix
- Test added or test command
- Status: OPEN / FIXED / VERIFIED / DEFERRED

Include every confirmed open issue from previous audit documents and every new issue found in the current source. Avoid duplicates and preserve the historical record. Distinguish confirmed defects from observations and design improvements.

### Step C — Audit and fix the full project, by priority

Do not stop after the known PHASE 3 warnings. Inspect the active codebase systematically and fix all confirmed, actionable defects that can be safely resolved within the local project. Prioritize P0/P1, then P2. Avoid speculative redesign.

#### C1. Telegram/Gemini response delivery — BUG-002

- Keep model generation errors separate from Telegram send/edit errors.
- Validate response text, empty/None responses, unexpected response types, and status-message creation/edit behavior.
- Enforce Telegram's message length limit on the final content being sent, including prefixes and HTML expansion. Every actual send/edit must respect the limit.
- Split text without losing, duplicating, or reordering characters. Handle Unicode, long unbroken strings, whitespace, newlines, HTML entities, and Markdown/code markers.
- Ensure HTML tags/entities are valid within each chunk. If this cannot be guaranteed, use a safe plain-text path rather than sending malformed HTML.
- On HTML parse failure, use plain-text fallback, but avoid blind retries after ambiguous timeout/network errors that might duplicate a delivered message.
- Distinguish definite rejection from ambiguous delivery. Treat “message is not modified” and equivalent already-delivered states deliberately.
- If later chunks fail after earlier content was delivered, give a concise, understandable incomplete-response notice if possible. Define quota/refund behavior consistently; do not refund twice or refund an already-delivered answer. Document the policy.
- `refund_once()` must be idempotent at the handler level and must not refund on a path where the user received the full answer. Check whether the existing DB refund API itself can incorrectly reset a daily quota after concurrent use; do not assume it is safe.
- Test first-chunk failure, later-chunk failure, HTML failure, HTML-escaped expansion (many `&`, `<`, `>`), long text, empty text, Unicode, message-not-modified, definite send rejection, ambiguous timeout, and no duplicate/refund behavior.
- Preserve the existing medical photo-analysis safety behavior and the emergency-service reminder already used by the product. Do not invent medical conclusions.

#### C2. Database connection, cursor, transaction, and pool safety

- Search every `get_connection()` and cursor creation/use in `database.py`, `bot.py`, `app_server.py`, services, and relevant modules.
- Inventory every function that acquires a pooled connection. Verify all paths: success, early return, SQL exception, commit exception, rollback exception, cursor creation exception, and connection acquisition failure.
- Ensure cursor close and connection release occur exactly once and in the right order on every path.
- Use the existing `_safe_close()`/pool conventions where appropriate. Do not create incompatible cleanup abstractions.
- Review `PooledConnectionWrapper.close()` for thread-safety. If shared access is possible, implement a lock-protected one-time detach/return pattern. Ensure the underlying connection is not double-returned and pool errors are not silently hidden. Add concurrency tests with a fake pool.
- Verify that failed transactions are rolled back before a pooled connection is returned. If rollback fails, ensure the connection is discarded/closed rather than returned in an unusable transaction state, using the pool API correctly.
- Check cursor cleanup if `get_connection()` or `cursor()` itself fails.
- Review transaction boundaries and `commit()` calls. Do not accidentally commit partial operations or change atomicity.
- Fix all confirmed connection leaks in the remaining database functions, including but not limited to the previously reported functions such as `set_premium`, `add_score`, `get_score`, `check_and_grant_daily_bonus`, `handle_referral`, and `check_and_grant_spin_bonus`. Verify exact current names and behavior before editing.
- Inspect callers that catch or propagate database errors. Present a user-friendly message where appropriate, but log operational errors without leaking secrets or swallowing exceptions.
- Add tests for representative early returns and failures in every changed function or use parameterized tests where clear. Test commit failure, execute failure, cursor-close failure, rollback failure, pool-put failure, and concurrent close where applicable.

#### C3. Payments, receipts, Premium entitlement, and reconciliation

Audit the entire payment lifecycle from UI/invoice to DB persistence and Premium grant:

- Telegram Stars configuration uses the correct currency (`XTR`) and correct invoice/provider requirements for the installed aiogram/Telegram API version. Do not invent or alter provider tokens.
- Validate invoice payload, amount, currency, Telegram charge ID, user ID, plan, and expiry before granting entitlement.
- Ensure pre-checkout and successful-payment handlers are correct and do not grant Premium from an untrusted client-supplied value.
- Enforce idempotency: a Telegram charge ID must never grant Premium twice, including concurrent duplicate updates and replayed updates. Verify DB unique constraints/indexes and conflict handling; do not rely only on an in-memory check.
- Ensure payment record persistence and Premium grant are atomic, or have a reliable reconciliation state machine if atomicity is impossible.
- Check `approve_receipt_and_grant` and manual receipt state transitions: pending -> approved/rejected, atomic grant, no double grant, no approval of already-rejected/approved receipts, correct `premium_type`, expiry, and audit trail.
- Verify admin authorization on every admin payment/receipt/reconciliation action. Parse configured admin IDs safely. No default admin bypass, empty-list bypass, or user-controlled authorization.
- Check `/reconcile` and pending reconciliation retry logic: admin-only, idempotent, bounded retries, clear status transitions, no accidental duplicate grants, no credentials in logs.
- Preserve backwards compatibility for supported legacy payloads such as `premium_1month` only if current code actually supports them; document verified behavior.
- Confirm all plan prices, durations, and daily quotas from the actual code and product UI before modifying. Historical plans were reported as Pro 50 Stars / 7 days / 15 AI requests per day; Plus/Max 150 Stars / 30 days / 30 AI requests per day; Ultra 300 Stars / 30 days / 100 AI requests per day. Treat these as clues, not authority. Do not silently change prices, durations, entitlement rules, or user-facing descriptions.
- Add mocked tests for duplicate charge, concurrent charge, malformed payload, wrong amount/currency, DB failure, atomic grant rollback, admin unauthorized, receipt state transitions, and reconciliation retry. Do not call Telegram API.

#### C4. AI quota, First-Aid scope, and token-cost controls

Preserve the existing product rules exactly unless the current source and master audit explicitly document a newer approved rule:

- Every free user receives exactly **one AI response per day** (daily reset in the product's configured timezone).
- After that free AI response is consumed, further AI requests must show the Premium offer and must not call Gemini.
- Non-AI bot features and trusted local knowledge-base answers remain free and do not consume Gemini tokens.
- For in-scope first-aid/medical questions, use an approved local knowledge answer when an adequate verified answer exists. Use Gemini only when the local answer is unavailable/insufficient and the user is entitled to an AI request.
- Filter clearly out-of-scope requests before Gemini so unrelated general/world questions do not spend Gemini tokens or consume the daily AI quota; show a polite First-Aid-focused response.
- For eligible Gemini requests, reserve quota atomically before the expensive call; handle concurrent requests so two simultaneous messages cannot both use the same final free quota.
- Refund only for defined failures before a useful response is delivered, exactly once. Do not reset a user's daily quota with an overly broad `UPDATE ... free_ai_used = 0` if that could erase other successful uses or race with a second request. Verify the schema and implement a transaction-safe reservation/refund identifier if required.
- Verify Premium quotas/entitlements against the actual plan implementation. Do not let a free user bypass daily limits through photo, voice, callback, retry, or alternate handler paths.
- Ensure callbacks, photo analysis, voice analysis, and text AI use the same authoritative quota enforcement where appropriate.
- Avoid duplicate Gemini calls from aiogram handler overlap, retries, fallbacks, or duplicate update processing.
- Keep Gemini API errors, quota errors, and Telegram delivery errors distinct.
- Never log prompts containing personal data, API keys, or unnecessary medical details.
- Add mocked tests proving that non-AI/local FAQ and out-of-scope replies call Gemini zero times; free users get exactly one eligible AI call/day; later requests show Premium without Gemini; Premium limits are enforced; concurrent quota reservation is safe; failures/refunds behave as documented.

#### C5. Medical knowledge and user safety

- Audit first-aid response pathways, photo/voice analysis prompts, emergency escalation language, and local knowledge retrieval.
- Do not invent clinical facts, medication doses, or treatment instructions. Do not expand the knowledge base with unsourced claims.
- Preserve the existing emergency reminder (Uzbekistan emergency ambulance number 103) where the product currently requires it; verify current product behavior before changing placement or wording.
- For urgent or life-threatening symptoms, maintain clear emergency escalation and do not let a chatbot answer delay emergency care.
- Review whether generated photo analysis overstates certainty; ensure it communicates limitations and does not claim a definitive diagnosis.
- Verify that user profile data is optional, used only when relevant, and not leaked between users or into logs.
- Do not scrape external medical websites or add copied copyrighted content. Do not download or add new medical sources in this repair task. Record any source/clinical-review gap as an explicit issue for owner review.

#### C6. Mini App and web application

Inspect `app/`, `app_server.py`, API routes, frontend event handlers, and Telegram WebApp integration:

- Validate Telegram Mini App `initData` server-side using the official HMAC validation algorithm, constant-time comparison where appropriate, and a sensible auth-date freshness window. Never trust frontend `user_id`, Premium flags, payment status, or admin flags.
- Ensure API routes authorize the authenticated Telegram user for every read/write and cannot access another user's profile, reminders, receipts, scores, or private data by changing an ID.
- Review XSS/HTML injection, SQL injection, path traversal, unsafe file access, CSRF where applicable, CORS, HTTPS assumptions, input sizes, upload validation, rate limits, and error disclosure.
- Never put bot/Gemini/database secrets in JavaScript, HTML, static files, source maps, or API responses.
- Verify all buttons, callbacks, forms, loading/error states, payment links, Premium state, and fallback navigation. Check the previous wheel fallback to the bot link if present.
- Ensure the Mini App menu button URL follows Telegram's required URL format and does not acquire unwanted query parameters.
- Verify that payment UI and backend amount/plan are consistent and the backend remains authoritative.
- Avoid redesigning the UI or changing product wording unless fixing a confirmed defect. Preserve the established visual design.
- Add offline unit/integration tests with mocked Telegram identity and API dependencies. No real Telegram API calls.

#### C7. Scheduler, daily engagement, reminders, and callbacks

Audit `services/engagement.py`, `services/engagement_scheduler.py`, scheduling setup in `bot.py`, and related DB schema:

- Use the configured `Asia/Tashkent` timezone consistently; avoid mixing naive and aware timestamps.
- Ensure only one event per user/event/date is prepared and sent, using database uniqueness/locking/transaction guarantees rather than only an in-memory flag.
- Verify the intended daily Premium check-in time (previously 20:30 Asia/Tashkent) against current configuration before changing it.
- Ensure `sent_at` is recorded only after Telegram send succeeds; prevent duplicate sends after process restarts or concurrent workers.
- Do not send stale missed notifications for previous dates unless that is explicitly intended and documented. Avoid late recovery sends after the allowed window.
- Verify user eligibility, Premium filtering, opt-outs, blocked/banned users, and current subscription status.
- Confirm callback data format and handling, including the previously desired `engagement_answer:10:10:{event_date}` format if still present in current code. Enforce Telegram callback-data length limits.
- Ensure callback handlers validate user ownership and event date, answer callbacks reliably, and do not grant rewards repeatedly.
- Ensure cursor/connection cleanup and robust handling of Telegram errors.
- Test duplicate scheduler invocation, restart/retry behavior, boundary times, timezone/date changes, send failure, and callback replay using a fake clock and fake bot.

#### C8. Ban cache, admin authorization, referrals, rewards, and ordinary bot flows

- Recheck the thread-safe ban cache (previously max 2000 entries, TTL max 30 seconds) for correctness, invalidation on ban/unban, memory bounds, and concurrency. Confirm no DB writes occur from read-only ban checks unless required.
- Audit admin-only commands and callbacks for consistent server-side authorization.
- Audit referral, score, spin-wheel, daily bonus, and reward flows for duplicate rewards, negative/overflow values, race conditions, and transaction boundaries.
- Verify ordinary non-AI bot features still work without consuming AI/Gemini quotas.
- Check fallback handlers and state filters for duplicate replies, handler shadowing, accidental catch-all interception, and private/group chat behavior.
- Ensure bot shutdown closes scheduler, HTTP client, DB pools, and other long-lived resources correctly.

#### C9. Voice, image, uploads, and temporary files

- Verify file size/type/duration limits before downloading or processing media.
- Ensure temporary files are uniquely named, stored safely, and deleted on success and all failure paths.
- Prevent path traversal and user-controlled filenames from selecting arbitrary paths.
- Ensure STT/image API failures do not leak quota or produce duplicate replies.
- Verify unsupported media types receive a clear, safe response.
- Do not make real Gemini/Telegram calls in tests.

#### C10. Performance, resource safety, and reliability

- Inspect async handlers for blocking synchronous network/disk/DB operations that can stall aiogram's event loop. Do not change concurrency architecture blindly.
- Measure or instrument the relevant latency locally with mocks where possible: handler time, DB acquire/query/commit, Gemini duration, Telegram send/edit, image/voice processing, scheduler overlap.
- Inspect connection pool sizing and resource use against actual deployment constraints. The production machine was previously 1 vCPU / 512 MB RAM; do not increase pool/workers or introduce heavyweight services without evidence and owner approval.
- Check for unbounded tasks, memory growth, unclosed sessions, repeated database calls, N+1 patterns, excessive logging, and runaway retries.
- Optimize only confirmed bottlenecks with low-risk changes. Preserve correctness and quota/payment semantics. Do not introduce unsafe parallel Gemini calls or aggressive retries.
- Prepare a short performance findings section with measurements, or explicitly state why a reliable measurement could not be made locally.

#### C11. Configuration, dependencies, and operational readiness

- Audit `requirements.txt`, Python version assumptions, imports, environment variable names/defaults, startup sequence, health endpoints, logging, and graceful shutdown.
- Do not print secrets or alter `.env`. A safe `.env.example` may list variable names and non-secret placeholders only, but do not overwrite an existing file without review.
- Do not silently upgrade dependencies or loosen security constraints. If dependency updates are required, explain the reason, compatibility evidence, and tests; keep changes minimal.
- Verify local code still matches the production Python/runtime assumptions as far as can be established without connecting to the server.
- Check that startup failure is clear and does not leave duplicate polling processes or duplicate schedulers.

#### C12. BGE-M3 / vector knowledge-base readiness — PLAN ONLY

The product direction includes a curated first-aid knowledge base and later BGE-M3 vector retrieval. In this task:

- Inspect whether vector search, `pgvector`, embedding fields, migration scripts, or knowledge-base scaffolding already exists.
- Do not install Docker, download BGE-M3 weights, add a large model dependency, change production schema, or implement a new model service.
- Do not assume the 512 MB production server can host BGE-M3.
- Produce a practical, resource-aware implementation plan only: data format, stable Q/A IDs, source URL/title, authoring/review status, reviewed date, language, emergency category, embedding model/version, vector dimensions, retrieval thresholds, fallback-to-Gemini quota behavior, and safe migration/rollback.
- Ensure the plan respects the free AI rule and medical-source review. Similarity score must not be treated as proof of medical correctness.

### Step D — Automated testing and test hygiene

1. Ensure test fixtures use temporary DBs/files and restore environment variables after each test.
2. No test may mutate the user's existing `pending_reconcile.db`, `users.db`, or any other persistent local data. Prefer dependency injection or temporary paths. Prove isolation by checking hashes/timestamps before and after.
3. No real Telegram/Gemini calls and no production DB. Tests named `test_gemini.py`, `test_menu_button.py`, or similar must remain skipped/blocked unless their network calls are fully mocked.
4. Add targeted regressions for every fixed defect. Tests must assert outcomes, not merely call functions.
5. Include concurrency tests for quota consumption, payment idempotency, wrapper close, scheduler duplicate prevention, and receipt approval where feasible using mocks/fakes.
6. Run tests in a documented order. Capture each command, exit code, exact test count, failures/errors/skips, and whether tests were isolated.
7. Run `python -m py_compile` only on active source and test files. Explicitly exclude old backup snapshots such as `bot_backup_before_image_fix.py` because that file is a historical backup with a known indentation error.
8. Run static checks available in the project (`git diff --check` only if safely inside a real project Git worktree; otherwise use a no-index comparison against a known backup or an equivalent whitespace check). Do not invoke Git operations against the parent `C:\Users\User` repository.
9. Run the complete safe offline test suite at the end. Report the exact unique total and do not count delegator tests and their child tests twice.
10. If a test cannot be made safe or needs an unavailable live service, mark it BLOCKED with a precise reason; never label it PASS.

### Step E — Final code review and local readiness gate

Before declaring ready:

- Review every diff line for all changed files.
- Confirm no unrelated formatting churn, accidental line-ending conversions, backup edits, DB-file changes, or secret changes.
- Check imports, type compatibility, async/sync boundaries, exception flow, transaction boundaries, and all callers of modified functions.
- Confirm product behavior preserved: pricing, plan durations, quota rules, callback payloads, free local answers, language, and UI flows.
- Confirm all P0/P1 issues are FIXED and regression-tested. No unresolved P0/P1 may be silently deferred.
- P2/P3 issues must be fixed when safe, or explicitly listed as DEFERRED with reason, risk, and a recommended follow-up. Do not hide warnings to make the result look clean.
- Do not claim production readiness from mocks alone. State clearly that actual production deployment checks remain pending.

## 3. FILES / DATA THAT MUST NOT BE ACCIDENTALLY INCLUDED IN SOURCE CONTROL

Before reporting ready for Git, inspect and explicitly classify these categories:

- `.env` and every secrets/credential file
- local databases (`*.db`, `*.sqlite`, `*.sqlite3`), including `pending_reconcile.db` and `users.db`
- logs and crash dumps
- `venv/`, `venv_OLD_BACKUP_*/`, `__pycache__/`, caches, temporary files
- backups and snapshot folders
- user uploads, medical/profile data, payment/reconciliation data
- generated model weights, embeddings, datasets, and large binaries

Check `.gitignore` coverage, but do not add broad ignore rules that hide necessary source or tests. Do not stage anything and do not push. Produce a proposed source-control inclusion/exclusion list for owner review.

## 4. DEFINITION OF DONE — THIS TASK IS NOT COMPLETE UNTIL

- All active modules and audit documents have been inspected.
- Every previously known warning has a verified disposition.
- Every confirmed P0/P1 defect has been fixed and tested.
- All other confirmed, safe-to-fix issues have been repaired or transparently deferred with reasons.
- Database pool and transaction cleanup are tested for success and failure paths.
- Payment idempotency, admin authorization, and Premium grants are tested offline.
- Free AI quota, scope filter, local-answer behavior, and no-Gemini paths are tested offline.
- BUG-002 chunking, HTML fallback, partial delivery, timeout ambiguity, and refund behavior are tested offline.
- Mini App authorization and security-critical routes are audited and tested with mocks.
- Scheduler idempotency and Asia/Tashkent timing behavior are audited and tested with a fake clock.
- Tests do not mutate persistent user databases or reconciliation files.
- The final compile and safe offline test suite pass, with exact counts documented.
- No secrets, user data, or unintended files were changed or exposed.
- The master audit and numbered bug-status table are updated accurately.
- A proposed Git inclusion/exclusion list is prepared.
- No Git commit/push, no server deploy, no service restart, and no production DB/API access has occurred.

## 5. REQUIRED FINAL REPORT FORMAT

Return a clear report with these sections:

1. **Executive result:** READY FOR OWNER REVIEW / NOT READY, and why.
2. **Issue register:** ID, severity, component, finding, fix, test, status.
3. **Files changed:** exact relative paths and concise descriptions.
4. **Files not changed:** especially backups, `.env`, DB files, and production files.
5. **Tests:** exact commands, interpreter, counts, PASS/FAIL/BLOCKED, unique total, and any skips.
6. **Database safety:** functions audited, cleanup coverage, pool/thread-safety findings, transaction tests.
7. **Payments and Premium:** idempotency, receipt transitions, admin protection, reconciliation findings.
8. **AI/quota:** exact verified free/Premium quota behavior, no-token paths, scope filter, refund behavior.
9. **Mini App/security:** authentication and authorization findings, vulnerabilities fixed/deferred.
10. **Scheduler/engagement:** timezone, duplicate prevention, retries, callback checks.
11. **Performance/resource findings:** measurements and safe fixes; explicitly note unmeasured items.
12. **BGE-M3 readiness plan:** plan only; no model installation or production migration.
13. **Residual risks/deferred issues:** severity, impact, why deferred, next recommended action.
14. **Source-control proposal:** files to include and exclude; confirm `.env`, DBs, backups, caches, and user data are excluded.
15. **Production deployment checklist:** commands/steps to be performed later by the owner, but DO NOT execute them.
16. **Explicit confirmation:** “No commit, push, pull, deploy, restart, production DB access, or live API calls were performed.” This must be truthful.

At the end, STOP and wait for the owner's separate approval for GitHub operations. Do not start Git or server work automatically.

---

## 6. IMPORTANT OWNER WORKFLOW AFTER THIS TASK

After the owner reviews and accepts the final report, the next stages will be separate:

**Stage 1 — GitHub:** establish a dedicated repository/worktree for this project (do not use the accidental parent `C:\Users\User` repository), review staged files, verify secrets/database/backups are excluded, commit, and push to the intended remote/branch. No deploy in this stage.

**Stage 2 — Production server:** back up production code and configuration safely, preserve `.env` and PostgreSQL data, compare target commit, deploy deliberately, run migrations only if reviewed and approved, restart the correct systemd services, and verify bot + Mini App health/logs. Do not overwrite production data or assume Git push deployed anything.

**Do not perform either stage in this assignment.**
