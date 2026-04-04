# Amazon Affiliate Bot — Vision, Architecture, and Recovery Plan

## 1) Executive Summary

This project has strong feature ambition (scraping, Telegram automation, analytics dashboard, AI copy generation), but reliability and maintainability are constrained by syntax-level blockers, duplicated orchestration logic, and inconsistent runtime contracts between modules.

The immediate goal is **stabilization first**, then **architecture consolidation**, then **feature-hardening and observability**.

---

## 2) Current-State Functional Review

### Working feature intent (present in codebase)
- Real-time Amazon scraping and keyword search.
- Telegram command handlers with user preference flows.
- Database-backed (PostgreSQL) and in-memory fallback operation.
- Flask dashboard APIs and pages for stats/deals/users.
- OpenAI/fallback content generation.
- Link validation with async batch processing.

### Critical blockers observed
1. **Scheduler contains invalid exception syntax path for current runtime behavior and portability**, causing compile failure in validation checks.
2. **Telegram bot `/start` handler has structurally broken exception blocks and undefined variable use**, indicating merge corruption and non-runnable code path.
3. **Main entry references a non-existent `test_mode()` method**, so CLI mode `test` is broken.
4. **Category taxonomy is inconsistent between backend canonical values and frontend filter values**, causing filter mismatches.

---

## 3) Key Quality Findings (Functional Logic, Stability, Duplicates, Completeness, Architecture)

## A. Functional correctness / missing pieces
- `main.py` routes `mode == "test"` to `await app.test_mode()`, but no `test_mode` is defined on `DealBotApplication`.
- `/start` handler in `telegram_bot.py` has duplicate `except` blocks and references `welcome_msg` (undefined), indicating incomplete/invalid flow.

## B. Stability / runtime resilience
- Scheduler startup uses a brittle `TaskGroup` / `except*` path that is currently failing syntax validation in local compile checks.
- Dashboard async bridge (`run_coroutine_threadsafe(...).result(timeout=10)`) can block request handling under slow DB operations and returns `None` on timeout/error without typed fallback contracts.
- Scraper uses heuristic HTML selectors against Amazon pages (expected fragility) without source-specific parser versioning.

## C. Duplicated logic and structural redundancy
- DB initialization logic appears in both app orchestrator and bot orchestrator, allowing divergent lifecycle and hidden ownership conflicts.
- A duplicate log statement exists in scraper result return path.
- Two dashboard JS files (`dashboard.js` and `dashboard_old.js`) duplicate substantial functionality; only one is wired in templates.

## D. Incomplete/inconsistent error handling
- Mixed patterns: some flows catch broad exceptions and continue silently, others fail hard; no shared exception taxonomy.
- Admin ID parsing in bot command handlers re-parses `config.ADMIN_USER_IDS` via `str(...).split(',')`, conflicting with `Config` already materializing a typed `List[int]`.

## E. Architecture quality
- Current architecture is **module-rich but boundary-weak**: app orchestration, bot orchestration, and dashboard data access each create/own core services independently.
- No explicit domain service layer for: deal ingestion pipeline, deduplication policy, posting policy, metrics aggregation.

---

## 4) Target Architecture (Enhanced)

## A. Layered structure

```text
app/
  core/
    settings.py
    logging.py
    errors.py
  domain/
    models.py
    policies.py            # scoring, dedupe, posting thresholds
  services/
    deal_pipeline.py       # scrape -> validate -> score -> persist -> publish
    user_service.py
    analytics_service.py
  adapters/
    telegram/
    web/
    scraper/
    db/
    ai/
  workers/
    scheduler.py
  entrypoints/
    cli.py
```

### Principles
- **Single owner per resource** (DB pool, bot client, scraper session).
- **Dependency injection at entrypoint** only.
- **Pure domain logic** separated from transport/IO layers.

## B. Core contracts
- `DealRepository` interface (Postgres/InMemory implementations).
- `Publisher` interface (Telegram now; extensible later).
- `DealSource` interface (Amazon scraper now; future APIs).
- `ContentProvider` interface (OpenAI + deterministic fallback).

## C. Data flow
1. Scheduler triggers `DealPipeline.run()`.
2. Source fetches raw products.
3. Normalizer extracts canonical `DealCandidate`.
4. Validator checks URL + affiliate tag + structural fields.
5. Deduper compares ASIN + time window.
6. Scorer ranks and filters.
7. Publisher sends (with retry/backoff).
8. Repository persists deals/events.
9. Analytics aggregates materialized stats.

---

## 5) Completion Plan (Fix + Hardening)

## Iteration 0 — Compile and Boot Integrity (Day 0-1)
- Fix syntax/runtime blockers in `scheduler.py` and `telegram_bot.py`.
- Implement or remove `test_mode` CLI path in `main.py`.
- Add `python -m py_compile *.py` as mandatory pre-commit check.

**Exit criteria**
- All Python modules compile.
- `python main.py web` and `python main.py bot` start cleanly (with env-dependent warnings only).

## Iteration 1 — Ownership and Lifecycle Unification (Day 1-3)
- Centralize service creation in one bootstrap function.
- Inject shared DB manager into bot and dashboard adapters.
- Remove duplicate initialization branches.

**Exit criteria**
- Single DB manager instance per process.
- Clean shutdown closes each resource exactly once.

## Iteration 2 — Domain Consistency + Contract Enforcement (Day 3-5)
- Define canonical enums for categories/regions/sources.
- Align frontend filter values to backend canonical keys.
- Replace ad-hoc dict/string manipulations with typed DTOs.

**Exit criteria**
- Dashboard filters produce deterministic matches.
- Category keys validated centrally.

## Iteration 3 — Error Handling and Observability (Day 5-7)
- Introduce structured errors (`ConfigError`, `ProviderError`, `ValidationError`, `TransientError`).
- Add correlation IDs in logs for scrape/post cycles.
- Surface health details beyond boolean status.

**Exit criteria**
- Failures are diagnosable by error class and pipeline stage.
- Health endpoint reports subsystem-level status.

## Iteration 4 — Scraper Reliability and Testability (Week 2)
- Split source fetch and HTML parse into testable units.
- Version selector sets by source page type.
- Add snapshot-based parser tests and fallback selector metrics.

**Exit criteria**
- Parser regression tests available.
- Selector breakage detected in CI before production runtime.

## Iteration 5 — Productization and Release Discipline (Week 3+)
- Add CI matrix (lint, type, unit, smoke).
- Add migration strategy for DB schema evolution.
- Add feature flags for posting, AI usage, and strict validation modes.

**Exit criteria**
- Repeatable release pipeline with rollback plan.

---

## 6) Debug Strategy (Systematic)

## A. Debug loop per issue
1. Reproduce with minimal command.
2. Capture structured logs + stack trace.
3. Write failing test (or fixture) first.
4. Apply smallest fix.
5. Run targeted test + smoke path.
6. Add regression guard.

## B. Priority probes
- Compile probe: `python -m py_compile *.py`
- Startup probes: `python main.py web`, `python main.py bot`
- API probes: `/api/health`, `/api/stats`, `/api/deals`
- Pipeline probe: dry-run scrape->validate->score without publish.

## C. Anti-regression gates
- No broad `except Exception` without logging context + typed fallback.
- No duplicate resource initialization outside bootstrap.
- Canonical enums required for all cross-layer filters.

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

