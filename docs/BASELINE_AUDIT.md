# Baseline Audit — DealPilot AI Commerce

Date: 2026-10-30 (UTC)
Auditor: Hermes (automated + manual inspection)

## Repository state

- Remote: https://github.com/RafalW3bCraft/AmazonAffiliatedBot
- Pre-hackathon baseline commit (main): `c3d30781baed4e7ae4375de7fde67295eff84d30` — "Merge pull request #9" (recorded in master prompt as 2026-04-05)
- Working branch for all new work: `feature/paypal-ai-dealpilot-2026`
- Git status at audit start: clean except untracked `DealPilot_AI_PayPal_Hackathon_Hermes_Master_Prompt.md` (the build prompt; committed to feature branch as record of requirements)
- License: MIT (root `LICENSE`) — preserved
- Python runtime on build host: **3.14.7** (repo requires 3.11+; compatible)

## Entrypoints

| Entrypoint | Role |
|---|---|
| `main.py` | Orchestrator: aiogram polling, scheduler, Flask thread, DB fallback. Modes: `bot`, `web`, `test`, `post`, hybrid default |
| `telegram_bot.py` | aiogram bot (AffiliateBot) |
| `web_dashboard_clean.py` | Flask dashboard (`create_app(config)`), also standalone `__main__` |
| `scheduler.py` | Periodic deal posting |
| `scraper.py` | Amazon HTML scraping (disabled by default for hackathon per rights review) |
| `content_generator.py` | AsyncOpenAI content generation, hard-coded `gpt-4o`, template fallback |
| `services/deal_pipeline_service.py` | Deal formatting/publish/persist/dedupe/telemetry |
| `database.py` / `database_simple.py` | PostgreSQL / in-memory fallback |

## Baseline verification results (real, executed 2026-10-30)

| Gate 0 check | Command | Result |
|---|---|---|
| Byte-compile | `python -m compileall -q .` | exit 0, PASS |
| Dependency install | `pip install -r requirements.txt pytest pytest-asyncio httpx` (venv `.venv`) | exit 0, PASS |
| Unit tests | `.venv/bin/python -m pytest -q` | **10 passed, 0 failed** in 28.28s |
| Diagnostics | `python main.py test` | exit 0; all diagnostics True, BUT `database_connected: True` came from the **in-memory fallback**, not PostgreSQL (see defect D4) |
| Existing test coverage | `tests/` | `test_config.py`, `test_dashboard_utils.py`, `tests/integration/` — no coverage of pipeline double-post, dashboard auth, or payments |

Environment available on this host (names only, values not committed): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL`, `DATABASE_URL` (+ PG* fields), `AMAZON_AFFILIATE_ID`, `FEATHERLESS_API_KEY`. **No `OPENAI_API_KEY`, no `PAYPAL_*` credentials present.** Per user directive, Featherless is the AI provider when OpenAI is absent.

## Confirmed defects (pre/post table)

| # | Defect | Evidence (pre) | Fix | State |
|---|---|---|---|---|
| D1 | `main.py::post_deals()` invokes `DealPipelineService.post_products(valid_deals)` **twice** (line 259 inside try, line 275 after `finally` closes the content generator). Second run reuses a closed `ContentGenerator` (use-after-close) and double-posts every deal | main.py:248-277 | Single pipeline invocation; generator closed once in `finally`; regression test proves exactly-once publish | FIXED |
| D2 | `/api/users` and `/users` return Telegram `user_id`, `username`, `first_name`, `last_name` with **no authentication** | web_dashboard_clean.py:161-163, 339-382 | Dashboard token auth (env `DASHBOARD_TOKEN`) required on privileged routes; response minimized to aggregate counts, PII dropped | FIXED |
| D3 | `/api/config` exposes `amazon_affiliate_id` publicly | web_dashboard_clean.py:384-399 | Affiliate ID removed from public payload | FIXED |
| D4 | Flask secret insecure fallback `'dev-secret-key-change-in-production'` (config.py:40) and `'dev-key-change-in-production'` (web_dashboard_clean.py:145); `Config.validate()` always returns `True` | config.py:40, 101-115 | Fail-closed: missing `FLASK_SECRET_KEY` in production mode raises; explicit `DEMO_MODE`/offline mode allowed with warning; `validate()` reports real failures | FIXED |
| D5 | DB failure paths return HTTP 200 with error payload (`/api/stats` error branch) | web_dashboard_clean.py:166-284 | Error branches return 503 | FIXED |
| D6 | `main.py test` reports `database_connected: True` via silent in-memory fallback although `DATABASE_URL` is set — false-success diagnostics | main.py:91-94, 310-333 | Fallback still allowed for deals lane, but diagnostics now report which backend answered; payment lane never uses in-memory storage | FIXED (commerce storage is always durable) |
| D7 | `.gitignore` only contains `.env` | .gitignore | Expanded: logs, caches, venv, DB files, generated artifacts | FIXED |
| D8 | `README.md` clone URL uses `yourusername`; metrics claims unverified | README.md | Corrected URL; claims reconciled with measured behavior | FIXED |
| D9 | `scraper.py` scrapes Amazon HTML; rights not verified for hackathon demo | scraper.py | Scraping disabled by default via `DISABLE_UNVERIFIED_AMAZON_SCRAPING=true`; affiliate lane uses fixtures/authorized data only | FIXED (config gate) |
| D10 | `content_generator.py` hard-codes model `gpt-4o` without availability verification | content_generator.py | Model configurable via `AI_MODEL`; Featherless provider adapter added; template fallback never labeled as AI | FIXED |

## Baseline -> significant-change proof

All post-baseline work is committed on `feature/paypal-ai-dealpilot-2026` with dated commits; see `HACKATHON_CHANGELOG.md` for the commit/file list mapping to this audit table.
