# AmazonAffiliatedBot — Architecture Audit, Stabilization Plan, and Product Vision

## 1) Executive Summary

This repository has a strong functional foundation (scraping, posting, dashboard, and analytics), but it currently mixes **production logic**, **fallback/development logic**, and **partially duplicated workflows** in ways that reduce reliability.

The most important systemic issues are:

1. **Broken / inconsistent orchestration flow** between `main.py`, `TaskScheduler`, and `AffiliateBot`.
2. **Incomplete / inconsistent error handling and lifecycle management** (async loop/thread lifetime, duplicate initializations, undefined call paths).
3. **Duplicate logic and drift** across database backends, dashboard JS variants, and deal posting paths.
4. **Configuration and runtime coupling** that makes behavior environment-dependent and hard to predict.

The target architecture should move toward a layered model:

- **Adapters:** Amazon scraping, Telegram, OpenAI, storage.
- **Application Services:** Deal ingestion, validation, ranking, publication, analytics materialization.
- **Interfaces:** Bot handlers, API routes, scheduler, and CLI commands.

---

## 2) Current Functional Logic (What Exists Today)

### Ingestion + Publication
- `DealScraper` pulls from multiple Amazon sources, extracts products using flexible selectors, filters/scoring, and returns top candidates.
- `main.DealBotApplication.post_deals()` performs scraping, link validation, duplicate checks, content generation, Telegram posting, and persistence.
- `AffiliateBot.post_deals()` has a second, partially overlapping publication flow.

### Bot Interaction
- `AffiliateBot` registers many command/callback handlers and serves:
  - onboarding/help,
  - category/region preferences,
  - search,
  - stats,
  - admin actions (manual add and broadcast).

### Storage
- `DatabaseManager` (PostgreSQL + `asyncpg`) and `SimpleDatabaseManager` (in-memory fallback) implement mostly shared method signatures.

### Dashboard
- Flask app (`web_dashboard_clean.py`) exposes pages and JSON APIs.
- Async DB access is bridged using a background event loop (`AsyncDataManager`) and `run_coroutine_threadsafe`.

---

## 3) Detailed Audit Findings

## A. Functional Logic and Correctness

### A1) Undefined command path in main CLI
- `main.py` routes `python main.py test` to `app.test_mode()`, but no `test_mode` method exists.
- Impact: runtime crash for `test` mode.
- Severity: **High**.

### A2) Scheduler-to-bot contract mismatch risk
- `TaskScheduler` calls `self.bot.post_deals()`, assuming bot object owns canonical publishing behavior.
- In hybrid mode, scheduler is initialized with `AffiliateBot`; but `main.py` also implements its own richer `post_deals()` workflow.
- Impact: duplicate behavior, drift, and inconsistent posting quality depending on execution path.
- Severity: **High**.

### A3) Duplicate/competing publication pipelines
- `main.DealBotApplication.post_deals()` and `AffiliateBot.post_deals()` overlap in responsibilities.
- They differ in duplicate logic, link validation breadth, and fallback behavior.
- Impact: non-deterministic behavior and maintenance burden.
- Severity: **High**.

### A4) Duplicate database initialization paths
- `DealBotApplication.initialize()` initializes DB manager.
- `AffiliateBot.initialize()` initializes its own DB manager again.
- Impact: unnecessary resource creation, possible inconsistency in in-memory mode (separate stores).
- Severity: **High**.

## B. Stability and Runtime Safety

### B1) Python version/runtime incompatibility
- `scheduler.py` uses `except*` and `TaskGroup` style path. `except*` causes SyntaxError on Python 3.10.
- Repo `README` asks for Python 3.11+, but environment drift can hard-fail startup.
- Impact: startup failure in non-3.11 environments.
- Severity: **High**.

### B2) AsyncDataManager thread lifecycle leak
- `AsyncDataManager` creates daemon thread + loop, but no explicit graceful stop/join exposed or used.
- Impact: resource leaks, harder testability/shutdown determinism.
- Severity: **Medium**.

### B3) Broad exception swallowing in parsing and posting
- Multiple `except:`/broad exception blocks continue silently (especially in scraper extraction helpers).
- Impact: hidden data quality failures, hard debugging.
- Severity: **Medium**.

### B4) Repetitive logging / accidental duplication
- `scrape_real_amazon_deals()` logs `Returning X top-scored deals` twice.
- Impact: minor noise, but indicates copy-paste drift.
- Severity: **Low**.

## C. Duplicates and Structural Drift

### C1) Dashboard JS duplicate versions
- `static/js/dashboard_old.js` and `static/js/dashboard.js` contain heavily overlapping logic.
- Impact: maintenance confusion and risk of patching wrong file.
- Severity: **Medium**.

### C2) Backend parity drift between `database.py` and `database_simple.py`
- Similar APIs maintained manually; behavior differs subtly (e.g., ordering/duplicate semantics).
- Impact: behavior changes by environment; bugs hard to reproduce.
- Severity: **Medium**.

### C3) Business logic split across handlers and services
- Bot command handlers perform service-level concerns (validation, ranking decisions, message rendering choices).
- Impact: low cohesion and reduced testability.
- Severity: **Medium**.

## D. Error Handling Gaps

### D1) Weak structured error taxonomy
- Errors are mostly logged as strings; no domain-specific exception classes.
- Impact: difficult retry/backoff policy by error class.
- Severity: **Medium**.

### D2) Partial fallback consistency
- Some paths degrade gracefully (fallback text on image failure), others return empty data with no user-facing context.
- Severity: **Low/Medium**.

### D3) Lack of defensive throttling in all paths
- Scraper has delays and retries; however, message broadcasting and some loops rely on fixed sleeps without robust Telegram/API rate envelope.
- Severity: **Medium**.

## E. Architecture and Codebase Quality

### E1) Missing service boundary abstraction
- No clear `DealPublishingService`, `DealIngestionService`, `AnalyticsService`, etc.
- Consequence: orchestration logic duplicated and embedded in entrypoints/handlers.

### E2) Missing automated test harness
- No unit/integration tests for scraper parsing, affiliate link generation/verification, or API contracts.
- Consequence: regressions likely.

### E3) Operational observability is log-heavy but metric-light
- No counters/timers/health dimensions beyond basic endpoint checks.
- Consequence: reactive rather than proactive operations.

---

## 4) Fix & Completion Plan (Phased)

## Phase 0 — Baseline and Safety Rails (Day 0–1)
1. Introduce a **single runtime compatibility guard** at startup (Python version check with clear error).
2. Add a missing `test` command implementation or remove route.
3. Add centralized constants for retry/timeouts/rate windows.
4. Create minimal smoke tests for startup and basic API endpoint responses.

**Deliverable:** app starts predictably in supported runtime; command surface is valid.

## Phase 1 — Unify Core Services (Day 1–3)
1. Create `services/` layer:
   - `DealIngestionService` (scrape, parse, dedupe candidates)
   - `DealValidationService` (link checks, quality gates)
   - `DealPublishingService` (content gen, Telegram send, DB persist)
   - `AnalyticsService` (stats aggregates + transformations)
2. Refactor both `main.py` and `AffiliateBot` to call the same service APIs.
3. Eliminate duplicate publication implementations.

**Deliverable:** one canonical posting path for scheduler, manual trigger, and bot/admin flows.

## Phase 2 — Data Access Normalization (Day 3–5)
1. Define a repository protocol/interface for storage operations.
2. Make PostgreSQL and in-memory implementations conform via shared tests.
3. Ensure deterministic ordering and duplicate semantics across backends.
4. Add transaction wrappers for multi-step write operations.

**Deliverable:** backend parity and safer persistence behavior.

## Phase 3 — API/UI and Dashboard Consolidation (Day 5–6)
1. Remove/archive `dashboard_old.js`; keep one maintained dashboard script.
2. Introduce typed API response schema contracts.
3. Centralize frontend utility functions and error rendering.
4. Add dashboard self-check and stale-data indicators.

**Deliverable:** lower frontend drift and clearer API guarantees.

## Phase 4 — Reliability & Observability (Day 6–8)
1. Add structured logging context (request-id/run-id/deal-id).
2. Emit counters and timers (scrape success ratio, publish failures by reason).
3. Implement circuit-breaker/backoff envelopes for scraper and Telegram posting.
4. Add watchdog heartbeat in scheduler loop.

**Deliverable:** measurable, operable system with predictable degradation.

## Phase 5 — Test Coverage & Hardening (Day 8–10)
1. Unit tests for:
   - URL/affiliate tag generation and validation
   - parsing helpers/rating/discount extraction
   - category classification fallback behavior
2. Integration tests for:
   - end-to-end `post_deals` with mocked adapters
   - API endpoint contract validation
3. Regression suite for known failure classes (0 deals, link invalid, image fail, DB down).

**Deliverable:** confidence in release changes.

---

## 5) Iteration / Debug Strategy

### Iteration Model
- Work in short, test-first loops:
  1. Reproduce issue with explicit failing scenario.
  2. Add/extend automated test asserting expected behavior.
  3. Implement minimal fix.
  4. Run focused suite + smoke tests.
  5. Observe logs/metrics for one cycle before broad rollout.

### Debug Playbook
- **Scraping failures:** capture selector hit counts, sample HTML snapshots, and response metadata.
- **Posting failures:** classify by link validation/content generation/Telegram transport.
- **DB inconsistencies:** replay sequence against both backends with shared fixtures.
- **Scheduler anomalies:** monitor task liveness, next-run timestamps, and exception histogram.

### Release Safety
- Use feature flags for:
  - strict vs relaxed quality filter,
  - image posting enablement,
  - link-validation hard-fail vs soft-fail.
- Roll out changes with canary intervals (e.g., one posting cycle) before full enablement.

---

## 6) Enhanced Target Architecture (Vision)

## Layered Architecture

1. **Domain Layer**
   - `Product`, `Deal`, `User`, `DealStats`, plus domain policies (quality scoring, dedupe rules).

2. **Application Layer (Services)**
   - `IngestionService` → produces normalized candidate deals.
   - `ValidationService` → validates URLs, affiliate tags, and quality thresholds.
   - `PublishingService` → renders content, sends to Telegram, stores outcomes.
   - `AnalyticsService` → computes/serves dashboard-friendly aggregates.

3. **Infrastructure Layer**
   - `AmazonScraperAdapter`, `TelegramAdapter`, `OpenAIAdapter`, `PostgresRepository`, `InMemoryRepository`.

4. **Interface Layer**
   - Telegram command handlers.
   - Flask API + pages.
   - Scheduler and CLI entrypoints.

## Data Flow (Canonical)
1. Scheduler/manual trigger emits `PublishCycleRequested`.
2. Ingestion scrapes sources and normalizes products.
3. Validation applies URL checks + quality filters + dedupe window.
4. Publishing generates content, posts, and persists outcome atomically.
5. Analytics updates derived metrics (or computes on read).
6. Dashboard/API returns consistent DTO schemas.

---

## 7) Feature Roadmap

## Near-term (2-4 weeks)
- Stabilized runtime.
- Reliable posting pipeline.
- Accurate dashboard filtering.
- Better admin/security controls.

## Mid-term (1-2 months)
- Multi-source deal ingestion.
- A/B content style optimization.
- Advanced attribution/clickstream modeling.

## Long-term (quarterly)
- Multi-channel publishing (Telegram + webhooks + email).
- Region-specific optimization policies.
- ML-assisted deal quality prediction.

---

## 8) Definition of Done (Project Quality)

A release is considered healthy only if:
- All modules compile and start in supported modes.
- End-to-end pipeline runs with deterministic error reporting.
- Dashboard reflects canonical data model.
- Duplicate logic reduced to single authoritative services.
- Tests cover parser, link validation, pipeline orchestration, and API contracts.

## Near-term (v2.1)
- Canonical service layer and unified posting flow.
- Runtime compatibility guard and startup diagnostics.
- Deterministic storage behavior across backends.

## Mid-term (v2.2)
- Better observability (metrics, traces, alert-ready logs).
- Selective scraping strategies by region/category.
- Anti-duplication enhancements (semantic title similarity + ASIN).

## Long-term (v3.x)
- Event-driven architecture (queue-based publish pipeline).
- Multi-channel publishing (Telegram + email/web push).
- ML-assisted ranking and personalized deal recommendations.

---

## 8) Definition of Done for “Stabilized Core”

1. One canonical publication pipeline used by scheduler, bot, and CLI.
2. No undefined command paths and no duplicate runtime initializations.
3. Shared test suite passes for both storage backends.
4. Dashboard/API contract tests pass.
5. Structured logs + key reliability metrics available.
6. Regression suite covers top known failure modes.

---

## 9) Suggested Immediate Next Actions

1. Resolve `test` mode path and runtime compatibility gate first.
2. Extract unified deal publishing service and migrate all callers.
3. Consolidate dashboard JS and remove stale duplicate file.
4. Add first-wave tests (affiliate links + scraper parsing + API smoke).

These steps provide the highest impact/risk reduction ratio and create a clean base for all future feature work.
