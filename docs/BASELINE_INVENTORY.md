# Baseline Inventory — DealPilotAI (renamed from AmazonAffiliatedBot)

Audit date: 2026-10-31. Auditor: Hermes agent, Phase 0 of master build & release audit.

## Repository facts (verified via git)

- Working dir: `/mnt/hostname/DealPilotAI` (renamed from `/mnt/hostname/AmazonAffiliatedBot`;
  a stale `.venv` still referenced the old path and had to be recreated).
- Remote: `https://github.com/RafalW3bCraft/AmazonAffiliatedBot.git`
- Branches: `main` (origin HEAD), `feature/paypal-ai-dealpilot-2026` (current, local only)
- Merge-base with main: `c3d3078` (last public pre-hackathon state)
- Hackathon-period commits on this branch:
  - `9cf1887` "DealPilot AI Commerce: commerce domain, AI agent, PayPal client, web layer"
  - `b308a3b` "feat: dealpilot ai for paypal hackathon"
- Delta main..HEAD: 56 files changed, +7,734 / -176 lines.
- 24 modified-but-uncommitted files: a non-functional style pass
  (PEP 604 hints `Optional[X]` -> `X | None`, `collections.abc.Callable`), verified by diff inspection.

## What the hackathon commits added (vs c3d3078)

New packages/modules:
- `paypal_checkout/` — `client.py` (Orders v2 sandbox client, httpx), `errors.py`
- `commerce/` — `catalog.py`, `cart_service.py`, `checkout_service.py` (state machine),
  `storage.py` (SQLAlchemy 2.x), `policy.py`, `schemas.py`, `exceptions.py`
- `ai/` — `agent.py` (AIShoppingService), `providers.py` (OpenAI/Featherless selection),
  `schemas.py` (Pydantic), `tools.py` (typed catalog tools)
- `web/` — `commerce_routes.py` (928 lines: shop/cart/checkout/return/webhook/dashboard),
  `catalog_data.py`, `auth.py`, `views.py`
- `migrations/001_commerce.sql`, `config/merchant_catalog.json`
- `scripts/ai_smoke.py` — real-AI smoke probe that FAILS honestly on fallback
- Tests: `tests/commerce/` (6 modules), `tests/security/test_web_security.py`,
  `tests/integration/test_post_deals_once.py` (regression for the duplicate-post bug)

Pre-existing (pre-hackathon): `main.py`, `telegram_bot.py`, `scraper.py`, `scheduler.py`,
`content_generator.py`, `database.py`, `database_simple.py`, `web_dashboard_clean.py`,
`models.py`, `link_validator.py`, `services/deal_pipeline_service.py`, `core/`, `ports/`.

## Known old-repo defect status

Duplicate `pipeline.post_products()` in `post_deals()`: FIXED. Exactly one call remains
(main.py:259). Regression test exists: `tests/integration/test_post_deals_once.py` (passes).

Legacy aliases handled in config.py: `BOT_TOKEN` (fallback for TELEGRAM_BOT_TOKEN),
`TELEGRAM_CHENNAL` (typo, fallback for TELEGRAM_CHANNEL). Canonical names preferred.

## Baseline test result (Phase 1 gate)

- Host Python: 3.14.7 (repo targets 3.11+; PEP 604 style consistent with this)
- `python -m compileall -q .` — clean
- `pip check` — no broken requirements
- `pip-audit` — no known vulnerabilities
- pytest: 118 passed, 0 failed with `FLASK_SECRET_KEY` set.
  Without it, 5 tests fail by design (config fails closed — correct Gate-2 behavior).
- Ruff: 322 findings (style-level; not release-blocking)
- Missing dependency found: `httpx` imported by `paypal_checkout/client.py`,
  `web/commerce_routes.py`, `tests/commerce/test_paypal_client.py` but ABSENT from
  requirements.txt. Fresh install cannot run the PayPal lane. (Fix queued.)

## Live probes executed (real, not mocked)

- PayPal sandbox OAuth token fetch: OK (token_len 97)
- PayPal Orders v2 create (USD 1.00, request_id probe-order-2026-10-31-a):
  order 58M93006RW372831R status CREATED, approve link present
- PayPal Orders v2 GET same order: OK, amount/currency round-trip exact
- Flask app boot (web_dashboard_clean.create_app): / /shop /cart /api/catalog 200
- AI smoke (scripts/ai_smoke.py): Featherless key REJECTED (PermissionDeniedError);
  service correctly fell back to deterministic mode and REPORTED fallback=True
  rather than faking inference. Real-AI gate: currently FAIL (credential issue, not code).

## Blockers at this gate

1. `httpx` missing from requirements.txt (fresh-install blocker for PayPal lane).
2. No working AI provider credential: FEATHERLESS_API_KEY present but rejected
   (PermissionDeniedError — likely out of credits); OPENAI_API_KEY absent.
3. Legacy `DATABASE_URL` (Neon, user AmazonDB_owner) fails password auth — deal
   pipeline lane's Postgres is unreachable. Commerce lane unaffected (own DB URL).
4. User `.env` lacks FLASK_SECRET_KEY, PAYPAL_ENV, APP_BASE_URL, APP_ENV, AI_PROVIDER,
   AI_MODEL, COMMERCE_DATABASE_URL, DEMO_MODE.
