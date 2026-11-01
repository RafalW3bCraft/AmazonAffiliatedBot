# HACKATHON_CHANGELOG — DealPilot AI (PayPal AI Hackathon 2026)

Submission Period: Oct 1 – Nov 12, 2026 (PT). All hackathon work is in local
commits 9cf1887 + b308a3b on branch `feature/paypal-ai-dealpilot-2026`,
unpublished at audit time.

## Before (public main @ c3d3078): AmazonAffiliatedBot

- Telegram deal bot: scrape Amazon deals, dedupe, publish to a channel on a schedule.
- Flask dashboard for deal/user analytics.
- OpenAI-based deal description generator with fallback.
- Persistent deal storage (Postgres via DATABASE_URL).
- Known defect: `post_deals()` called `pipeline.post_products()` twice per run.

## After (DealPilotAI): two-lane commerce app

### Lane A — affiliate discovery (preserved)
- Scrape/search/category/region commands, admin gating, scheduler all retained.
- Duplicate-post defect FIXED (one call, main.py:259) + regression test.

### Lane B — merchant AI checkout (new)
- `commerce/` domain: catalog, cart quotes (server-side Decimal totals), checkout
  state machine (ORDER_CREATED → AWAITING_BUYER_APPROVAL → APPROVED → CAPTURE_PENDING
  → PAID, plus FAILED/CANCELED/REQUIRES_REVIEW), durable SQLAlchemy storage with
  unique constraints on PayPal order/capture/event IDs.
- `paypal_checkout/`: sandbox-only httpx client (hard-refuses live hosts), OAuth
  token cache, Orders v2 create/get/capture with PayPal-Request-Id idempotency,
  typed errors distinguishing timeout vs. ambiguous transport failure.
- `web/commerce_routes.py`: buyer journey (shop → cart → PayPal redirect →
  return/cancel → receipt), merchant dashboard, webhook endpoint using PayPal's
  official verify-webhook-signature endpoint with SSRF guard on cert_url and
  idempotent event delivery.
- `ai/`: AIShoppingService with typed tools (catalog_search, compare, propose_cart,
  explain_cart), Pydantic-validated structured output, honest AI_UNAVAILABLE /
  deterministic-fallback state (never fakes inference).
- Config: config.py hard-fails without FLASK_SECRET_KEY; checkout requires explicit
  env; in-memory payment storage refused.

## Environment variable changes

Added by hackathon commits: PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET,
PAYPAL_WEBHOOK_ID, PAYPAL_ENVIRONMENT, PAYPAL_CURRENCY, DASHBOARD_TOKEN,
DEMO_MODE, ENABLE_MERCHANT_CHECKOUT, ENABLE_EXTERNAL_AFFILIATE,
CART_QUOTE_TTL_MINUTES, MAX_CART_TOTAL, FEATHERLESS_API_KEY, FEATHERLESS_BASE_URL,
AI_PROVIDER, AI_MODEL, COMMERCE_DATABASE_URL, DISABLE_UNVERIFIED_AMAZON_SCRAPING.

## Test changes

Added tests/commerce/ (catalog, cart, checkout, PayPal client, AI agent, web
routes), tests/security/test_web_security.py, tests/integration/test_post_deals_once.py.
Total: 118 passing.

## Evidence of genuine capability (live probes, 2026-10-31)

- PayPal sandbox OAuth: OK
- Orders v2 create+fetch (USD 1.00, probe-order-2026-10-31-a): order 58M93006RW372831R
- Web app boots; / /shop /cart /api/catalog return 200

## Not yet done

See docs/BASELINE_INVENTORY.md §Blockers and the final audit report §K.
