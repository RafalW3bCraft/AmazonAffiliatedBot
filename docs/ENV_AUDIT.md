# Environment Variable Audit — DealPilotAI

Date: 2026-10-31. Source of truth: live grep of `os.getenv`/`os.environ` across the
active tree, plus config.py semantics. Secret values never displayed.

Legend — REQUIRED?: YES (app refuses without), LANE (that lane disabled without),
OPT (has safe default).

| NAME | REQUIRED? | DEFAULT | EXPECTED FORMAT | SOURCE | VALIDATION | TEST RESULT | CORRECTION NEEDED |
|------|-----------|---------|-----------------|--------|------------|-------------|-------------------|
| FLASK_SECRET_KEY | YES (non-demo) | none (fail-closed) | 32+ char random hex | config.py:51 | RuntimeError if absent & not DEMO_MODE | PASS (5 tests fail closed w/o it) | Add to local `.env` (gen: `python -c "import secrets;print(secrets.token_hex(32))"`) |
| PAYPAL_CLIENT_ID | LANE | '' | sandbox app client id | config.py:77 | presence gate; live OAuth probe | PASS (real sandbox OAuth OK) | none |
| PAYPAL_CLIENT_SECRET | LANE | '' | sandbox app secret | config.py:78 | presence gate | PASS (OAuth OK) | none |
| PAYPAL_WEBHOOK_ID | LANE | '' | sandbox webhook id | config.py:79 | RuntimeError in webhook verify if missing | PASS (503 when unset) | none |
| PAYPAL_ENVIRONMENT | YES | 'sandbox' | literal `sandbox` | config.py:71-76 | RuntimeError unless exactly 'sandbox' | PASS | none (brief's `PAYPAL_ENV` name rejected — code name kept, documented) |
| PAYPAL_CURRENCY | OPT | 'USD' | ISO-4217 in {USD} | config.py:80, policy.py | PolicyError at boot if unsupported | PASS | none |
| APP_BASE_URL | OPT | derived | https URL when public | (return/cancel URLs) | urlparse | NOT TESTED externally | set when publicly hosted (needed for real PayPal redirect flow) |
| COMMERCE_DATABASE_URL | LANE | DATABASE_URL → local sqlite | postgresql:// or sqlite:/// | config.py:96-99, storage.py:159 | RuntimeError on 'memory'/empty; NEW: web layer refuses in-memory fallback when checkout configured | PASS (regression test added) | set explicitly for production; do NOT rely on DATABASE_URL fallback |
| DATABASE_URL | LANE-A | '' | postgres DSN | config.py:30 | — | FAIL (Neon creds in .env rejected: password auth failed for AmazonDB_owner) | rotate/repair Neon credentials or point at reachable DB |
| AI_PROVIDER | OPT | auto from keys | 'openai'\|'featherless'\|'' | config.py:86-91 | selection logic | PASS | none |
| AI_MODEL | OPT | provider default | valid model id | config.py:85 | — | NOT TESTED (no working key) | set when key available |
| OPENAI_API_KEY | LANE | '' | sk-... | config.py | — | ABSENT in .env | add if using OpenAI |
| FEATHERLESS_API_KEY | LANE | '' | token | config.py:83 | live smoke probe | FAIL (PermissionDeniedError — key rejected/out of credits) | replace with funded key or use OpenAI |
| FEATHERLESS_BASE_URL | OPT | api.featherless.ai/v1 | https URL | config.py:84 | — | PASS | none |
| TELEGRAM_BOT_TOKEN | LANE-A | '' | \d+:[A-Za-z0-9_-]{35} | config.py:16 | structural | present, NOT live-verified | verify via getMe before demo |
| TELEGRAM_CHANNEL | LANE-A | '' | @channel or id | config.py | — | present | none |
| ADMIN_USER_IDS | OPT | '' | comma-sep ints | config.py | int parse | NOT TESTED | none |
| AMAZON_AFFILIATE_ID | LANE-A | '' | 10-20 alnum+hyphen | config.py:23-28 | regex + warning | present (format valid) | none |
| AMAZON_AFFILIATE_ID_{UK,DE,FR,IN,JP,CA,AU} | OPT | '' | regional tags | config.py | regex | absent | optional |
| DASHBOARD_TOKEN | OPT | '' (routes disabled) | bearer token | config.py:60 | fail-closed warning | PASS (401/404 without) | set for /merchant + /api/users |
| DEMO_MODE | OPT | false | true/false | config.py | policy.assert_checkout_allowed tripwire | PASS | none |
| ENABLE_MERCHANT_CHECKOUT | OPT | true | bool | config.py:66 | DEMO_MODE tripwire | PASS | none |
| ENABLE_EXTERNAL_AFFILIATE | OPT | false | bool | config.py:67 | — | PASS | set true to show affiliate lane |
| DISABLE_UNVERIFIED_AMAZON_SCRAPING | OPT | true | bool | config.py:68 | — | PASS | none |
| CART_QUOTE_TTL_MINUTES | OPT | 30 | int | config.py:95 | int() | PASS | none |
| MAX_CART_TOTAL | OPT | 500.00 | decimal | config.py:94 | Decimal via policy | PASS | none |
| FLASK_HOST / FLASK_PORT | OPT | 0.0.0.0/5000 | host/int | config.py | — | PASS | none |
| DEFAULT_REGION, MAX_DEALS_PER_SOURCE, POST_INTERVAL_MINUTES, REQUEST_TIMEOUT, RATE_LIMIT_DELAY | OPT | sane | int/str | config.py | int parse | PASS | none |
| BOT_TOKEN, TELEGRAM_CHENNAL | legacy | '' | — | config.py:16 | fallback aliases for canonical names | PASS | keep as back-compat only |
| PGHOST/PGUSER/PGPASSWORD/PGDATABASE (+PG* libpq vars) | OPT | — | libpq env | (asyncpg/psycopg) | — | present but DB unreachable | same as DATABASE_URL |
| CHANNEL3_API_KEY | LANE (stretch) | '' | sponsor key | not yet wired | — | present, integration NOT implemented | Phase 5 stretch goal |

## Offline vs online checks

- `scripts/config_check.py` provides offline syntax/format validation (no network).
- Live probes performed in this audit (read-only): PayPal OAuth OK, Orders v2
  create+fetch OK, Featherless REJECTED (PermissionDeniedError), Neon DB auth FAIL.

## Gate 2 status

Every variable classified. No silent checkout-critical fallback remains:
storage fallback to in-memory is now refused when checkout is configured
(web/commerce_routes.py), and CommerceStorage itself rejects 'memory'/empty URLs.
