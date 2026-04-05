# Amazon Affiliate Bot — Engineering Vision, Debug Report, and Completion Plan

## 1) Purpose

This document is the authoritative engineering plan for stabilizing, cleaning, and professionalizing the project.
It combines:

- Full current-state codebase analysis.
- Debug findings by module.
- Architecture and data-flow redesign.
- Iterative fix strategy with validation gates.
- Cleanup policy for unnecessary artifacts/files.

## Implementation Status (Current)

- Legacy duplicate/unreferenced artifacts were removed.
- Runtime compile integrity and diagnostics path were fixed in previous iteration.
- Shared DB lifecycle ownership has started (app-level DB manager injection into bot) to reduce duplicate initialization.
- Canonical category normalization has been applied in dashboard filters.
- Initial unit tests were added for configuration link generation and dashboard utility sanitization/guards.

---

## 2) Full Repository Scan (Code + Markdown)

### Python application modules
- `main.py`
- `config.py`
- `models.py`
- `database.py`
- `database_simple.py`
- `scraper.py`
- `telegram_bot.py`
- `scheduler.py`
- `content_generator.py`
- `link_validator.py`
- `web_dashboard_clean.py`

### Frontend and templates
- `templates/base.html`
- `templates/dashboard.html`
- `templates/deals.html`
- `templates/users.html`
- `static/css/dashboard.css`
- `static/js/dashboard.js`

### Documentation and config assets
- `README.md`
- `vision.md`
- `example.env`
- `requirements.txt`
- `LICENSE`

---

## 3) Current Quality Assessment

## A) Functional logic

### Strengths
- End-to-end intent exists: scraping → validation → content generation → posting → analytics.
- Fallback architecture exists for DB (`PostgreSQL` and in-memory).
- Dashboard APIs and rendering are implemented and functional for core metrics.

### Gaps
- Core flow orchestration is spread across `main.py`, `telegram_bot.py`, and `web_dashboard_clean.py` with overlapping lifecycle logic.
- No canonical service layer for pipeline stages; behavior is embedded in handlers and route-level code.

## B) Stability and reliability

### Strengths
- Retry/backoff logic exists in scraper and link validator.
- Many operations are wrapped with logging.

### Risks
- Heavy reliance on broad `except Exception` branches can mask root causes.
- External dependency failures (DB, Amazon anti-bot, Telegram API) are not normalized through typed error contracts.
- No automated tests are present (runtime behavior is mostly unchecked in CI-like workflows).

## C) Duplication

### Existing duplication patterns
- Data manager/resource ownership and initialization logic exists in multiple orchestration locations.
- Some fallback/retry/error-handling approaches are reimplemented instead of centralized.

### Cleanup status
- Legacy/unreferenced duplicate dashboard JS artifact removed.
- Historical bug-summary markdown removed to keep repository focused on one source of truth (`vision.md`).

## D) Missing/incomplete elements

- Missing test suite and quality gates (`pytest`, lint, typing, integration checks).
- No migrations or schema versioning for database evolution.
- No formal contract layer (interfaces/protocols) for repository/provider adapters.

## E) Overall architecture quality

Current structure is **feature-rich but monolithic in behavior composition**.
Primary improvement direction:

1. Consolidate orchestration.
2. Isolate domain logic.
3. Formalize adapters/contracts.
4. Add observability + test gates.

---

## 4) Module-by-Module Debug Findings

## `main.py`
- Acts as process orchestrator and still carries business workflow logic (deal posting pipeline details).
- Should delegate pipeline behavior to service-level components.
- `test` mode exists and should remain diagnostics-only with deterministic output.

## `telegram_bot.py`
- Handler set is broad and functional.
- Needs service extraction: commands should invoke domain services, not deep infra operations.
- Admin authorization and message composition should be centralized.

## `scheduler.py`
- Scheduling responsibilities are clear.
- Should emit structured telemetry (task runtime, failures, retries) through one monitor interface.

## `scraper.py`
- Rich parsing and fallback selector support.
- Needs parser segmentation by source type and fixtures/snapshot tests to prevent regressions.
- Scoring and filtering policy should move to domain policy module.

## `database.py` / `database_simple.py`
- Good repository parity intent.
- Should be refactored under one repository protocol to reduce branching at call sites.

## `link_validator.py`
- Good async batch and tag verification patterns.
- Should expose typed result enums for invalid causes (format, network, non-amazon, status code, tag mismatch).

## `content_generator.py`
- Fallback behavior is valuable.
- Model usage and prompt strategy should be externally configurable and tested for markdown safety.

## `web_dashboard_clean.py`
- Functional APIs with defensive serialization.
- Async loop/thread model can be moved to dedicated service boundary for cleaner ownership and observability.

## Templates + static assets
- Dashboard structure is clear.
- Category value normalization has been aligned with canonical backend keys.

---

## 5) Markdown/Documentation Audit

## `README.md`
- Broad and feature-rich but overstates readiness (tests/production reliability currently not fully enforced).
- Needs a concise “Production Readiness” section with known constraints and required env dependencies.

## `vision.md`
- Must remain single source for architecture and stabilization plan.
- Updated in this revision with explicit quality gates and cleanup policy.

## `example.env`
- Good starting baseline.
- Should add comments on required vs optional variables and secure defaults.

---

## 6) Target Industry-Grade Architecture

```text
app/
  core/
    settings.py
    logging.py
    errors.py
    telemetry.py
  domain/
    entities.py
    value_objects.py
    policies.py
    services.py
  ports/
    repositories.py
    publishers.py
    providers.py
  adapters/
    db_postgres.py
    db_memory.py
    telegram_publisher.py
    amazon_scraper.py
    openai_provider.py
    flask_api.py
  orchestration/
    pipeline.py
    scheduler.py
  entrypoints/
    cli.py
    web.py
```

### Key principles
- One owner per external resource.
- Port/adapter boundaries for external systems.
- Domain rules isolated from IO/transport logic.
- Predictable boot/shutdown lifecycle.

---

## 7) Canonical Data Flow

1. Scheduler triggers pipeline cycle.
2. Scraper adapter fetches candidates.
3. Validator adapter verifies links and tags.
4. Domain policy filters/scores candidates.
5. Repository checks dedupe + persists deals.
6. Publisher sends selected deals.
7. Analytics service updates aggregate metrics.
8. Dashboard/API reads pre-aggregated view.

---

## 8) Iteration-Based Fix and Completion Plan

## Iteration 0 — Runtime Integrity (done/ongoing)
- Compile blockers and malformed handlers fixed.
- CLI test route stabilized.
- Canonical category values aligned in dashboards.
- Removed obsolete duplicate/unnecessary files.

## Iteration 1 — Service Extraction
- Move deal posting workflow from `main.py` into `DealPipelineService`.
- Move Telegram command business actions into service calls.
- Define shared `AppContext` for injected dependencies.

## Iteration 2 — Contracts and Consistency
- Add repository/provider protocols.
- Unify result/error objects for scraping, validation, publishing.
- Enforce canonical enums for category/region/source.

## Iteration 3 — Observability and Fail-Safe Behavior
- Structured logs with correlation IDs for pipeline cycle and posted deal IDs.
- Metrics per stage (fetched, validated, deduped, posted, failed).
- Health endpoint expands to subsystem granularity.

## Iteration 4 — Test and Quality Gates
- Add unit tests for parsers, validators, and policies.
- Add integration tests with in-memory DB adapter.
- Add smoke tests for CLI modes and API endpoints.

## Iteration 5 — Production Hardening
- DB migration strategy.
- Controlled retries and circuit-breaker style throttling for external dependencies.
- Release checklist + rollback process.

---

## 9) Debug Strategy (Operational)

## Standard debug loop
1. Reproduce with a minimal deterministic command.
2. Capture full structured logs and trace.
3. Add a failing test or reproducible fixture.
4. Apply smallest valid fix.
5. Run targeted + regression checks.
6. Record incident and prevention rule.

## Priority probes
- `python -m py_compile *.py`
- `pytest -q`
- `python main.py test`
- `python main.py web`
- `python main.py post` (dry-run flag recommended in next iteration)

## Regression guards
- No new broad exception blocks without contextual logging.
- No duplicate initialization of DB/bot/scraper clients.
- No template filter values outside canonical enums.

---

## 10) Cleanup and Professional Structure Policy

### Keep
- Active runtime modules.
- Current templates/static assets in use.
- One living architecture/stabilization document (`vision.md`).

### Remove
- Dead/duplicate files not referenced by runtime.
- Historical one-off notes replaced by maintained documentation.
- Temporary logs/cache artifacts from repository state.

### Coding standards
- Type hints for public APIs.
- Service-level single responsibility.
- Test coverage for all critical workflows.
- Consistent error taxonomy and retry policy.

---

## 11) Definition of Done

A release is production-ready when:

- All modules compile and boot in declared modes.
- Critical workflows pass integration tests.
- External dependency failures are observable and recoverable.
- No duplicate/dead runtime artifacts remain.
- Documentation reflects actual runtime behavior and known constraints.
=======
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
