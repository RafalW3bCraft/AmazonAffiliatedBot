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

---

## 12) AI Agent Task Memory (Imported from Requested Advanced Vision)

This section captures the requested STAGE-based execution memory format:
`STAGE > SCAN > ANALYZE > DEBUG > FIX > VERIFY > ITERATE`.

### Current Stage Status

- **STAGE 0 (Baseline integrity):** partial → in progress  
  - Python version guard added.  
  - Compile checks and test diagnostics available.  
- **STAGE 1 (Duplicate pipeline elimination):** in progress  
  - Shared DB manager injection active between `main.py` and `telegram_bot.py`.  
  - Canonical `DealPipelineService` introduced and wired into posting flows.
- **STAGE 2 (Contracts/errors/enums):** started  
  - Added `core/errors.py`, `core/enums.py`, and `ports/repository.py`.  
- **STAGE 3 (Observability):** started  
  - Added `core/telemetry.py`, scheduler heartbeat metric, health metrics exposure, and correlation logging context helpers.
- **STAGE 4 (Tests and quality gates):** partial  
  - Baseline tests, pipeline integration tests, and API smoke tests present and passing.  
- **STAGE 5+ (hardening/CI):** pending

### Task Memory Index (Condensed)

| Task ID | Stage | Action | Status |
|---|---|---|---|
| T-01 | 0 | Add Python 3.11+ version guard | ✅ Complete |
| T-02 | 0 | Full module compile checks | ✅ Complete |
| T-03 | 0 | Ensure diagnostics `test_mode` works | ✅ Complete |
| T-04 | 0 | Remove `dashboard_old.js` legacy file | ✅ Complete |
| T-05 | 1 | Create canonical pipeline service | ✅ Complete |
| T-06 | 1 | Single DB manager lifecycle per process | ✅ Partial/Active |
| T-07 | 2 | Add repository protocol | ✅ Complete |
| T-08 | 2 | Add typed error hierarchy | ✅ Complete |
| T-09 | 2 | Add canonical enums | ✅ Complete |
| T-10 | 3 | Structured correlation logging | ✅ Partial/Active |
| T-11 | 3 | Metrics counters and health exposure | ✅ Partial/Active |
| T-12 | 3 | AsyncDataManager graceful stop | ✅ Complete |
| T-13 | 4 | Pytest infrastructure | ✅ Complete |
| T-14 | 4 | Link validation/config tests | ✅ Partial/Active |
| T-15 | 4 | Scraper parsing tests | ⏳ Pending |
| T-16 | 4 | Pipeline integration tests | ✅ Partial/Active |
| T-17 | 4 | API smoke tests | ✅ Partial/Active |
| T-18 | 5 | Circuit breaker for external APIs | ⏳ Pending |
| T-19 | 5 | Scheduler watchdog heartbeat | ✅ Complete |
| T-20 | 5 | Broadcast rate limiting strategy | ✅ Complete |
| T-21 | 5 | `example.env` required/optional docs | ⏳ Pending |
| T-22 | 6 | Ruff + Black + Mypy checks | ⏳ Pending |
| T-23 | 6 | CI workflow file | ⏳ Pending |
| T-24 | 7 | Full multi-mode boot verification | ⏳ Pending |
| T-25 | 7 | Regression script for known bugs | ⏳ Pending |
