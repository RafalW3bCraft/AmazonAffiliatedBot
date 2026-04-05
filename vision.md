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
=======
# vision.md
# Amazon Affiliate Bot — Advanced Implementation & AI Agent Task Memory
# Auto-generated from vision.md analysis | Version: 1.0 | April 2026
# 
# PURPOSE: This file is the authoritative task memory for AI agents and AI assistants.
# Each stage is atomic, independently executable, and tracks state.
# Format: STAGE > SCAN > ANALYZE > DEBUG > FIX > VERIFY > ITERATE

---

## 🧠 AGENT MEMORY HEADER
```yaml
project: amazon-affiliate-bot
language: python3.11+
entrypoints: [main.py, web_dashboard_clean.py, telegram_bot.py]
db_backends: [postgresql, in-memory]
framework: [flask, asyncpg, python-telegram-bot]
current_status: stabilization-in-progress
last_completed_stage: STAGE-0 (partial)
next_required_stage: STAGE-1
agent_instruction: >
  Execute each STAGE sequentially. Never skip a STAGE.
  After each STAGE, update [STATUS] tag. Log all fix outcomes.
  On failure, go to ROLLBACK protocol at bottom of this file.
```

---

## ═══════════════════════════════════════════
## STAGE 0 — BASELINE SCAN & RUNTIME INTEGRITY
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [x] PARTIAL | [ ] COMPLETE

### 0.1 — Python Version Guard
**Bug:** No startup version check. Python <3.11 causes silent SyntaxError from `except*` in scheduler.py  
**Severity:** CRITICAL — startup crash

**Debug Command:**
```bash
python --version
python -c "import sys; assert sys.version_info >= (3,11), f'Need Python 3.11+, got {sys.version_info}'"
```

**Scan Command:**
```bash
grep -rn "except\*\|TaskGroup" scheduler.py
python -m py_compile scheduler.py
```

**Fix — Add to top of main.py:**
```python
import sys
if sys.version_info < (3, 11):
    print(f"[FATAL] Python 3.11+ required. Current: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)
```

**Verify:**
```bash
python main.py --version-check  # should print OK
python -m py_compile main.py scheduler.py telegram_bot.py database.py
```

---

### 0.2 — Full Module Compile Check
**Bug:** Undiscovered syntax errors may exist across modules  
**Severity:** HIGH

**Scan Command:**
```bash
python -m py_compile main.py config.py models.py database.py database_simple.py \
  scraper.py telegram_bot.py scheduler.py content_generator.py \
  link_validator.py web_dashboard_clean.py
echo "Exit code: $?"
```

**Expected Output:** No output, exit code 0  
**On Failure:** Run per-file to isolate:
```bash
for f in *.py; do python -m py_compile "$f" && echo "OK: $f" || echo "FAIL: $f"; done
```

---

### 0.3 — Undefined `test_mode()` Method
**Bug:** `main.py` routes `python main.py test` to `app.test_mode()` but method does not exist  
**Severity:** HIGH — RuntimeError on test command

**Scan Command:**
```bash
grep -n "test_mode\|def test" main.py
grep -n ""test"\|'test'" main.py
```

**Fix — Add to DealBotApplication class in main.py:**
```python
async def test_mode(self):
    """Diagnostics-only test mode with deterministic output."""
    logger.info("[TEST MODE] Starting diagnostics...")
    # 1. DB connectivity
    try:
        await self.db_manager.initialize()
        logger.info("[TEST] DB: OK")
    except Exception as e:
        logger.error(f"[TEST] DB: FAIL — {e}")
    # 2. Config validation
    try:
        from config import Config
        cfg = Config()
        assert cfg.TELEGRAM_BOT_TOKEN, "Missing TELEGRAM_BOT_TOKEN"
        logger.info("[TEST] Config: OK")
    except Exception as e:
        logger.error(f"[TEST] Config: FAIL — {e}")
    # 3. Scraper ping (no real request)
    logger.info("[TEST] Scraper module: IMPORTABLE")
    logger.info("[TEST MODE] Diagnostics complete.")
```

**Verify:**
```bash
python main.py test
# Expected: no crash, structured diagnostic output
```

---

### 0.4 — Dead File Cleanup
**Bug:** `static/js/dashboard_old.js` causes maintenance confusion  
**Severity:** MEDIUM

**Scan Command:**
```bash
find . -name "*.js" | xargs grep -l "dashboard"
grep -rn "dashboard_old" templates/
```

**Fix:**
```bash
# Only remove if NOT referenced in any template
grep -rn "dashboard_old.js" templates/ || rm static/js/dashboard_old.js
git rm --cached static/js/dashboard_old.js 2>/dev/null || true
```

**Verify:**
```bash
grep -rn "dashboard_old" . --include="*.html" --include="*.py"
# Expected: 0 results
```

---

### 0.5 — STAGE 0 Gate Checklist
```
[ ] python --version returns 3.11+
[ ] All .py files compile without error
[ ] python main.py test runs without crash
[ ] No undefined method calls in CLI routing
[ ] dashboard_old.js removed or confirmed unreferenced
```

---

## ═══════════════════════════════════════════
## STAGE 1 — DUPLICATE PIPELINE ELIMINATION
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [ ] COMPLETE

### 1.1 — Identify Dual Publication Paths
**Bug:** `main.DealBotApplication.post_deals()` AND `AffiliateBot.post_deals()` both exist with overlapping logic  
**Severity:** HIGH — non-deterministic behavior

**Scan Command:**
```bash
grep -n "def post_deals" main.py telegram_bot.py
grep -n "post_deals" main.py telegram_bot.py scheduler.py
```

**Analyze:**
```bash
# Compare both implementations
grep -A 40 "def post_deals" main.py > /tmp/post_deals_main.txt
grep -A 40 "def post_deals" telegram_bot.py > /tmp/post_deals_bot.txt
diff /tmp/post_deals_main.txt /tmp/post_deals_bot.txt
```

**Fix — Create `services/deal_pipeline_service.py`:**
```python
# services/deal_pipeline_service.py
from dataclasses import dataclass
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class PipelineResult:
    fetched: int = 0
    validated: int = 0
    deduped: int = 0
    posted: int = 0
    failed: int = 0
    errors: List[str] = None

    def __post_init__(self):
        self.errors = self.errors or []

class DealPipelineService:
    """Single canonical deal publication pipeline. All callers use this."""

    def __init__(self, scraper, validator, content_gen, publisher, repository):
        self.scraper = scraper
        self.validator = validator
        self.content_gen = content_gen
        self.publisher = publisher
        self.repository = repository

    async def run_cycle(self, max_deals: int = 5) -> PipelineResult:
        result = PipelineResult()
        try:
            candidates = await self.scraper.fetch_candidates()
            result.fetched = len(candidates)
            valid = await self.validator.validate_batch(candidates)
            result.validated = len(valid)
            new_deals = await self.repository.filter_new(valid)
            result.deduped = len(new_deals)
            for deal in new_deals[:max_deals]:
                try:
                    content = await self.content_gen.generate(deal)
                    await self.publisher.publish(deal, content)
                    await self.repository.save(deal)
                    result.posted += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(str(e))
                    logger.error(f"[PIPELINE] Failed deal {deal}: {e}")
        except Exception as e:
            logger.error(f"[PIPELINE] Cycle error: {e}")
            result.errors.append(str(e))
        return result
```

**Migration Steps:**
```bash
# 1. Create services/ directory
mkdir -p services
touch services/__init__.py

# 2. Move logic to DealPipelineService (above)
# 3. Refactor main.py to call service
grep -n "await.*post_deals\|self.post_deals" main.py
# 4. Refactor telegram_bot.py to call service  
grep -n "await.*post_deals\|self.post_deals" telegram_bot.py
# 5. Refactor scheduler.py
grep -n "post_deals" scheduler.py
```

**Verify:**
```bash
grep -rn "def post_deals" . --include="*.py"
# Expected: 0 standalone implementations; only service calls remain
python -m py_compile services/deal_pipeline_service.py
```

---

### 1.2 — Duplicate DB Initialization
**Bug:** Both `DealBotApplication.initialize()` and `AffiliateBot.initialize()` create separate DB managers  
**Severity:** HIGH — in-memory mode gets two separate stores

**Scan Command:**
```bash
grep -n "DatabaseManager\|initialize\|db_manager" main.py telegram_bot.py | grep -v "^.*#"
```

**Fix — Inject shared DB manager:**
```python
# In main.py — DealBotApplication.initialize()
self.db_manager = DatabaseManager(self.config)
await self.db_manager.initialize()

# Pass to bot INSTEAD of letting bot create its own:
self.bot = AffiliateBot(self.config, db_manager=self.db_manager)  # injected

# In telegram_bot.py — AffiliateBot.__init__():
def __init__(self, config, db_manager=None):
    self.db_manager = db_manager  # use injected; don't re-init
    if self.db_manager is None:
        # standalone mode only
        self.db_manager = DatabaseManager(config)
```

**Verify:**
```bash
python main.py test
# Check logs: should see "DB initialized" exactly ONCE
grep -c "DB initialized\|database.*init" /tmp/bot_test.log
```

---

### 1.3 — STAGE 1 Gate Checklist
```
[ ] services/ directory exists with deal_pipeline_service.py
[ ] DealPipelineService used by main.py, telegram_bot.py, scheduler.py
[ ] Old post_deals() implementations removed or delegated
[ ] DB manager initialized exactly once per process
[ ] python main.py test shows single DB init log line
[ ] python -m py_compile services/*.py passes
```

---

## ═══════════════════════════════════════════
## STAGE 2 — CONTRACT LAYER & ERROR TAXONOMY
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [ ] COMPLETE

### 2.1 — Repository Protocol Interface
**Bug:** `database.py` and `database_simple.py` have parallel APIs with behavioral drift  
**Severity:** MEDIUM — bugs only reproducible in one backend

**Scan Command:**
```bash
grep -n "^    async def " database.py > /tmp/db_methods.txt
grep -n "^    async def " database_simple.py > /tmp/dbs_methods.txt
diff /tmp/db_methods.txt /tmp/dbs_methods.txt
```

**Fix — Create `ports/repository.py`:**
```python
# ports/repository.py
from typing import Protocol, List, Optional, runtime_checkable
from models import Deal, User

@runtime_checkable
class DealRepository(Protocol):
    async def initialize(self) -> None: ...
    async def save_deal(self, deal: Deal) -> bool: ...
    async def get_deals(self, limit: int = 50, category: Optional[str] = None) -> List[Deal]: ...
    async def deal_exists(self, url: str) -> bool: ...
    async def get_stats(self) -> dict: ...
    async def close(self) -> None: ...

# Validate conformance:
# assert isinstance(db_manager, DealRepository)
# assert isinstance(simple_db, DealRepository)
```

**Verify:**
```bash
python -c "
from ports.repository import DealRepository
from database import DatabaseManager
from database_simple import SimpleDatabaseManager
# Both must satisfy protocol
print('Protocol check: OK')
"
```

---

### 2.2 — Typed Error Taxonomy
**Bug:** All errors are untyped strings; no domain exception classes  
**Severity:** MEDIUM — can't retry by error type

**Fix — Create `core/errors.py`:**
```python
# core/errors.py

class AffiliateError(Exception):
    """Base exception for all project errors."""
    pass

class ScraperError(AffiliateError):
    """Raised when scraping fails."""
    pass

class LinkValidationError(AffiliateError):
    """Raised when affiliate link is invalid."""
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason  # format|network|non_amazon|status_code|tag_mismatch
        super().__init__(f"Invalid link [{reason}]: {url}")

class PublishError(AffiliateError):
    """Raised when Telegram posting fails."""
    pass

class DatabaseError(AffiliateError):
    """Raised on storage failures."""
    pass

class ConfigError(AffiliateError):
    """Raised on invalid or missing configuration."""
    pass
```

**Scan for bare exceptions to replace:**
```bash
grep -n "except Exception\|except:\|except BaseException" *.py | grep -v "test\|#"
# List all locations — replace with typed catches where possible
```

**Verify:**
```bash
python -c "from core.errors import LinkValidationError; e = LinkValidationError('http://x.com', 'tag_mismatch'); print(e)"
```

---

### 2.3 — Canonical Enums
**Bug:** Category/region/source strings used as raw literals across codebase  
**Severity:** MEDIUM — typos cause silent filter failures

**Scan Command:**
```bash
grep -rn "category\|region\|source" *.py | grep "==" | grep "'\|"" | head -30
```

**Fix — Add to `models.py` or new `core/enums.py`:**
```python
from enum import Enum

class Category(str, Enum):
    ELECTRONICS = "electronics"
    FASHION = "fashion"
    HOME = "home"
    BOOKS = "books"
    SPORTS = "sports"
    OTHER = "other"

class Region(str, Enum):
    IN = "in"
    US = "us"
    UK = "uk"

class DealSource(str, Enum):
    AMAZON_DEALS = "amazon_deals"
    AMAZON_MOVERS = "amazon_movers"
    MANUAL = "manual"
```

**Verify:**
```bash
python -c "from core.enums import Category; print(Category.ELECTRONICS.value)"
```

---

### 2.4 — STAGE 2 Gate Checklist
```
[ ] ports/repository.py exists with DealRepository Protocol
[ ] Both DB backends satisfy Protocol (runtime check passes)
[ ] core/errors.py exists with typed exception hierarchy
[ ] core/enums.py exists with Category, Region, DealSource
[ ] At least 50% of bare `except Exception` replaced with typed catches
[ ] python -m py_compile core/*.py ports/*.py passes
```

---

## ═══════════════════════════════════════════
## STAGE 3 — OBSERVABILITY & STRUCTURED LOGGING
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [ ] COMPLETE

### 3.1 — Structured Logging with Correlation IDs
**Bug:** Logs are flat strings; no run-id/deal-id correlation  
**Severity:** MEDIUM — hard to trace multi-step failures

**Fix — Create `core/logging.py`:**
```python
# core/logging.py
import logging
import uuid
from contextvars import ContextVar

run_id: ContextVar[str] = ContextVar("run_id", default="no-run")
deal_id: ContextVar[str] = ContextVar("deal_id", default="no-deal")

class CorrelationFilter(logging.Filter):
    def filter(self, record):
        record.run_id = run_id.get()
        record.deal_id = deal_id.get()
        return True

def configure_logging(level=logging.INFO):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] run=%(run_id)s deal=%(deal_id)s %(name)s: %(message)s"
    ))
    handler.addFilter(CorrelationFilter())
    logging.root.setLevel(level)
    logging.root.handlers = [handler]

def new_run_context() -> str:
    rid = str(uuid.uuid4())[:8]
    run_id.set(rid)
    return rid
```

**Integration:**
```python
# At start of each pipeline cycle in deal_pipeline_service.py:
from core.logging import new_run_context
async def run_cycle(self, ...):
    rid = new_run_context()
    logger.info(f"Pipeline cycle start run={rid}")
    ...
```

**Verify:**
```bash
python -c "
from core.logging import configure_logging, new_run_context
import logging
configure_logging()
new_run_context()
logging.getLogger('test').info('Test message')
"
# Expected: structured output with run_id
```

---

### 3.2 — Stage Metrics Counters
**Bug:** No per-stage counters (fetched/validated/posted/failed)  
**Severity:** MEDIUM — can't detect silent degradation

**Fix — Create `core/telemetry.py`:**
```python
# core/telemetry.py
from collections import defaultdict
from threading import Lock
import time

class Metrics:
    def __init__(self):
        self._counts = defaultdict(int)
        self._timers = {}
        self._lock = Lock()

    def increment(self, key: str, value: int = 1):
        with self._lock:
            self._counts[key] += value

    def timer_start(self, key: str):
        self._timers[key] = time.monotonic()

    def timer_stop(self, key: str) -> float:
        elapsed = time.monotonic() - self._timers.pop(key, time.monotonic())
        with self._lock:
            self._counts[f"{key}_ms"] += int(elapsed * 1000)
        return elapsed

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._counts)

metrics = Metrics()  # global singleton
```

**Integration Points:**
```python
# In DealPipelineService.run_cycle():
metrics.increment("pipeline.fetched", result.fetched)
metrics.increment("pipeline.posted", result.posted)
metrics.increment("pipeline.failed", result.failed)

# In web_dashboard_clean.py health endpoint:
from core.telemetry import metrics
@app.route("/health")
def health():
    return jsonify({"status": "ok", "metrics": metrics.snapshot()})
```

---

### 3.3 — AsyncDataManager Thread Leak Fix
**Bug:** Background event loop thread in `AsyncDataManager` has no graceful shutdown  
**Severity:** MEDIUM — resource leak, test unpredictability

**Scan Command:**
```bash
grep -n "AsyncDataManager\|daemon\|Thread\|run_forever" web_dashboard_clean.py
```

**Fix:**
```python
# In AsyncDataManager class:
def stop(self):
    if self._loop and self._loop.is_running():
        self._loop.call_soon_threadsafe(self._loop.stop)
    if self._thread and self._thread.is_alive():
        self._thread.join(timeout=5.0)

# Register cleanup at Flask shutdown:
import atexit
atexit.register(async_data_manager.stop)
```

**Verify:**
```bash
python -c "
import web_dashboard_clean as w
m = w.AsyncDataManager()
m.stop()
print('Clean shutdown: OK')
"
```

---

### 3.4 — STAGE 3 Gate Checklist
```
[ ] core/logging.py exists with CorrelationFilter
[ ] core/telemetry.py exists with Metrics singleton
[ ] pipeline cycle logs show run_id in every line
[ ] /health endpoint returns metrics snapshot
[ ] AsyncDataManager has stop() method called on shutdown
[ ] Double-logging bug in scraper fixed (search: "Returning X top-scored" duplicate)
```

---

## ═══════════════════════════════════════════
## STAGE 4 — TEST SUITE & QUALITY GATES
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [ ] COMPLETE

### 4.1 — Test Infrastructure Setup
```bash
pip install pytest pytest-asyncio pytest-cov httpx

# Create test directory
mkdir -p tests/unit tests/integration tests/fixtures
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py

# pytest config
cat > pytest.ini << EOF
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
EOF
```

---

### 4.2 — Unit Tests: Link Validation
```python
# tests/unit/test_link_validator.py
import pytest
from link_validator import LinkValidator  # adjust import

@pytest.mark.parametrize("url,expected", [
    ("https://www.amazon.in/dp/B09X123?tag=mytag-21", True),
    ("https://amazon.in/dp/ABC", False),          # missing tag
    ("https://google.com/dp/ABC?tag=x", False),   # not amazon
    ("not-a-url", False),                          # malformed
    ("", False),                                   # empty
])
def test_affiliate_link_validation(url, expected):
    result = LinkValidator.is_valid_affiliate_url(url, required_tag="mytag-21")
    assert result == expected, f"URL: {url}"
```

---

### 4.3 — Unit Tests: Scraper Parsing
```python
# tests/unit/test_scraper.py
import pytest
from scraper import DealScraper

SAMPLE_HTML = """
<div class="s-result-item" data-asin="B09TESTX">
  <span class="a-price-whole">1,299</span>
  <span class="a-offscreen">₹2,499</span>
  <span class="a-text-bold">48% off</span>
  <img src="https://m.media-amazon.com/images/test.jpg" />
  <a class="a-link-normal" href="/dp/B09TESTX?ref=test">Test Product</a>
</div>
"""

def test_parse_price():
    scraper = DealScraper.__new__(DealScraper)
    price = scraper._extract_price(SAMPLE_HTML)
    assert price > 0

def test_parse_discount():
    scraper = DealScraper.__new__(DealScraper)
    discount = scraper._extract_discount(SAMPLE_HTML)
    assert 0 < discount <= 100
```

---

### 4.4 — Integration Tests: Pipeline with Mocks
```python
# tests/integration/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.deal_pipeline_service import DealPipelineService, PipelineResult

@pytest.fixture
def mock_pipeline():
    scraper = AsyncMock()
    validator = AsyncMock()
    content_gen = AsyncMock()
    publisher = AsyncMock()
    repo = AsyncMock()

    scraper.fetch_candidates.return_value = [MagicMock(url="https://amazon.in/dp/TEST?tag=x")]
    validator.validate_batch.return_value = scraper.fetch_candidates.return_value
    repo.filter_new.return_value = scraper.fetch_candidates.return_value
    content_gen.generate.return_value = "Great deal!"
    publisher.publish.return_value = True
    repo.save.return_value = True

    return DealPipelineService(scraper, validator, content_gen, publisher, repo)

@pytest.mark.asyncio
async def test_pipeline_happy_path(mock_pipeline):
    result = await mock_pipeline.run_cycle(max_deals=1)
    assert isinstance(result, PipelineResult)
    assert result.posted == 1
    assert result.failed == 0

@pytest.mark.asyncio
async def test_pipeline_zero_deals(mock_pipeline):
    mock_pipeline.scraper.fetch_candidates.return_value = []
    result = await mock_pipeline.run_cycle()
    assert result.fetched == 0
    assert result.posted == 0
```

---

### 4.5 — API Smoke Tests
```python
# tests/integration/test_api.py
import pytest
from web_dashboard_clean import create_app  # adjust if needed

@pytest.fixture
def client():
    app = create_app(testing=True)
    with app.test_client() as c:
        yield c

def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"

def test_deals_page(client):
    r = client.get("/deals")
    assert r.status_code == 200

def test_api_deals_json(client):
    r = client.get("/api/deals")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
```

---

### 4.6 — Run All Tests + Coverage
```bash
# Full test run
pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html:htmlcov/

# Quick smoke only
pytest tests/ -q -x --tb=short

# Only unit tests
pytest tests/unit/ -v

# Only integration
pytest tests/integration/ -v
```

**Coverage Gate:**
```bash
pytest --cov=. --cov-fail-under=60  # fail if < 60% coverage
```

---

### 4.7 — STAGE 4 Gate Checklist
```
[ ] pytest runs without collection errors
[ ] tests/unit/test_link_validator.py passes all parametrize cases
[ ] tests/unit/test_scraper.py passes price/discount extraction
[ ] tests/integration/test_pipeline.py passes happy path + zero deals
[ ] tests/integration/test_api.py passes health + deals endpoints
[ ] Coverage >= 60%
[ ] No new test failures on re-run (deterministic)
```

---

## ═══════════════════════════════════════════
## STAGE 5 — PRODUCTION HARDENING
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [ ] COMPLETE

### 5.1 — Circuit Breaker for External APIs
**Bug:** No circuit-breaker; failed scraper/Telegram calls retry infinitely  
**Severity:** HIGH in production

**Fix — Create `core/circuit_breaker.py`:**
```python
# core/circuit_breaker.py
import time
from enum import Enum

class State(Enum):
    CLOSED = "closed"       # normal
    OPEN = "open"           # failing, reject calls
    HALF_OPEN = "half_open" # testing recovery

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.state = State.CLOSED
        self._failures = 0
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._opened_at = None

    def call_succeeded(self):
        self._failures = 0
        self.state = State.CLOSED

    def call_failed(self):
        self._failures += 1
        if self._failures >= self._threshold:
            self.state = State.OPEN
            self._opened_at = time.monotonic()

    def is_available(self) -> bool:
        if self.state == State.CLOSED:
            return True
        if self.state == State.OPEN:
            if time.monotonic() - self._opened_at > self._recovery_timeout:
                self.state = State.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: try once
```

**Integration:**
```python
# In scraper.py:
scraper_cb = CircuitBreaker(failure_threshold=3, recovery_timeout=120)

async def fetch_with_cb():
    if not scraper_cb.is_available():
        raise ScraperError("Circuit open — Amazon scraper offline")
    try:
        result = await actual_fetch()
        scraper_cb.call_succeeded()
        return result
    except Exception as e:
        scraper_cb.call_failed()
        raise ScraperError(str(e)) from e
```

---

### 5.2 — Scheduler Watchdog
**Bug:** Scheduler tasks can silently die without detection  
**Severity:** MEDIUM

**Scan Command:**
```bash
grep -n "while True\|asyncio.sleep\|schedule" scheduler.py | head -20
```

**Fix — Add heartbeat to scheduler:**
```python
# In scheduler.py:
import asyncio
from core.telemetry import metrics

async def watchdog_loop(interval: int = 300):
    """Emit heartbeat every interval seconds. Alert if missed."""
    while True:
        metrics.increment("scheduler.heartbeat")
        await asyncio.sleep(interval)

# Start alongside main scheduler loop
asyncio.create_task(watchdog_loop())
```

---

### 5.3 — Rate Limiting for Telegram Broadcasts
**Bug:** Broadcast loops use fixed `asyncio.sleep` without respecting Telegram rate envelope  
**Severity:** MEDIUM — can trigger 429 Too Many Requests

**Scan Command:**
```bash
grep -n "send_message\|asyncio.sleep\|broadcast" telegram_bot.py | head -20
```

**Fix:**
```python
# Telegram limits: ~30 msgs/sec per bot, ~1 msg/sec per chat
TELEGRAM_RATE_LIMIT = 1.0  # seconds between per-chat messages

async def broadcast_with_rate_limit(self, chat_ids: list, message: str):
    for i, chat_id in enumerate(chat_ids):
        try:
            await self.bot.send_message(chat_id, message)
        except Exception as e:
            logger.warning(f"Broadcast fail {chat_id}: {e}")
        await asyncio.sleep(TELEGRAM_RATE_LIMIT)
        if i % 25 == 0 and i > 0:
            await asyncio.sleep(2.0)  # extra buffer every 25 msgs
```

---

### 5.4 — example.env Documentation Audit
**Scan Command:**
```bash
cat example.env
grep -v "^#" example.env | grep "=" | awk -F= '{print $1}' > /tmp/env_keys.txt
cat /tmp/env_keys.txt
```

**Fix — Add inline comments for all keys in example.env:**
```bash
# Required keys should be marked:
# TELEGRAM_BOT_TOKEN=             # REQUIRED: From @BotFather
# AMAZON_ASSOCIATE_TAG=           # REQUIRED: Your affiliate tag (e.g. mytag-21)
# DATABASE_URL=                   # OPTIONAL: PostgreSQL URL; falls back to in-memory
# OPENAI_API_KEY=                 # OPTIONAL: For AI content generation
# ADMIN_TELEGRAM_IDS=             # REQUIRED: Comma-separated admin user IDs
```

---

### 5.5 — STAGE 5 Gate Checklist
```
[ ] core/circuit_breaker.py exists and tested
[ ] Scraper uses CircuitBreaker wrapper
[ ] Scheduler has watchdog_loop task running
[ ] Broadcast uses rate-limited send function
[ ] example.env has REQUIRED/OPTIONAL comments on all keys
[ ] python main.py test shows circuit breaker state in diagnostics
```

---

## ═══════════════════════════════════════════
## STAGE 6 — LINT, TYPING & CI GATES
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [ ] COMPLETE

### 6.1 — Install and Run Linters
```bash
pip install ruff mypy black

# Auto-format
black *.py services/ core/ ports/ tests/

# Lint
ruff check *.py services/ core/ ports/ --fix

# Type checking
mypy main.py --ignore-missing-imports --no-strict-optional
mypy services/ core/ --ignore-missing-imports
```

### 6.2 — Type Hints Audit
**Scan for untyped public functions:**
```bash
grep -n "^def \|^    def " *.py | grep -v "def __" | head -40
# Add return type and param types to all public methods
```

### 6.3 — Create `.github/workflows/ci.yml` (or local Makefile)
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install -r requirements.txt pytest pytest-asyncio ruff
      - run: ruff check .
      - run: python -m py_compile main.py config.py models.py
      - run: pytest tests/ -q --tb=short
```

**Or Makefile:**
```makefile
.PHONY: lint test check

lint:
	ruff check . --fix
	black .

test:
	pytest tests/ -q --tb=short

check: lint test
	python -m py_compile *.py
	echo "All checks passed"
```

### 6.4 — STAGE 6 Gate Checklist
```
[ ] ruff check passes with 0 errors
[ ] black formats without changes
[ ] mypy passes on core/ and services/
[ ] CI workflow file exists
[ ] make check runs lint + test in one command
```

---

## ═══════════════════════════════════════════
## STAGE 7 — FINAL INTEGRATION VERIFICATION
## ═══════════════════════════════════════════
> STATUS: [ ] PENDING | [ ] IN_PROGRESS | [ ] COMPLETE

### 7.1 — Full Boot Test
```bash
# Test all startup modes
python main.py test           # diagnostics mode
python main.py web &          # web dashboard
sleep 3 && curl http://localhost:5000/health
curl http://localhost:5000/api/deals
kill %1

# Dry-run post (if dry-run flag exists)
python main.py post --dry-run 2>&1 | tail -20
```

### 7.2 — End-to-End Pipeline Smoke
```bash
# Run full pytest suite
pytest tests/ -v --tb=long 2>&1 | tee /tmp/final_test.log
grep -E "PASSED|FAILED|ERROR" /tmp/final_test.log
grep "FAILED\|ERROR" /tmp/final_test.log && echo "FAILURES EXIST" || echo "ALL PASSED"
```

### 7.3 — Regression Check for Known Bugs
```bash
# A1: test_mode exists
grep -n "def test_mode" main.py && echo "A1: OK" || echo "A1: MISSING"

# A2: single DB init
grep -c "db_manager.*initialize\|initialize.*db" main.py

# B1: Python version guard
grep -n "sys.version_info" main.py && echo "B1: OK" || echo "B1: MISSING"

# C1: dashboard_old.js gone
ls static/js/dashboard_old.js 2>/dev/null && echo "C1: STILL EXISTS" || echo "C1: REMOVED"

# C3: services/ layer exists
ls services/deal_pipeline_service.py && echo "C3: OK" || echo "C3: MISSING"
```

### 7.4 — FINAL Definition of Done
```
[ ] All STAGE gate checklists: COMPLETE
[ ] python -m py_compile *.py services/*.py core/*.py ports/*.py — exit 0
[ ] pytest tests/ — 0 failures, >= 60% coverage
[ ] python main.py test — no crash, structured output
[ ] /health endpoint returns {"status": "ok"} with metrics
[ ] No grep hit for: dashboard_old.js, def post_deals (duplicate), DatabaseManager() (duplicate init)
[ ] ruff check passes
[ ] README updated to reflect actual production constraints
```

---

## ═══════════════════════════════════════════
## 🔁 ROLLBACK PROTOCOL
## ═══════════════════════════════════════════

If a STAGE introduces a regression:
```bash
# 1. Identify broken stage
pytest tests/ -q 2>&1 | head -30

# 2. Git rollback single file
git checkout HEAD -- <broken_file>.py

# 3. Stash work-in-progress
git stash push -m "stage-N-wip"

# 4. Re-run gate check
pytest tests/ -q && python main.py test

# 5. Log incident
echo "$(date): Stage N rollback — reason" >> INCIDENTS.md
```

---

## ═══════════════════════════════════════════
## 🤖 AI AGENT TASK MEMORY INDEX
## ═══════════════════════════════════════════

> Agents: Read this section first. It summarizes ALL actionable tasks with IDs.

| Task ID | Stage | File | Action | Priority | Status |
|---------|-------|------|--------|----------|--------|
| T-01 | 0.1 | main.py | Add Python version guard | CRITICAL | [ ] |
| T-02 | 0.2 | *.py | Run py_compile on all modules | CRITICAL | [ ] |
| T-03 | 0.3 | main.py | Implement test_mode() method | HIGH | [ ] |
| T-04 | 0.4 | static/js/ | Remove dashboard_old.js | MEDIUM | [ ] |
| T-05 | 1.1 | services/ | Create DealPipelineService | HIGH | [ ] |
| T-06 | 1.2 | main.py + telegram_bot.py | Inject shared DB manager | HIGH | [ ] |
| T-07 | 2.1 | ports/repository.py | Create DealRepository Protocol | MEDIUM | [ ] |
| T-08 | 2.2 | core/errors.py | Create typed error hierarchy | MEDIUM | [ ] |
| T-09 | 2.3 | core/enums.py | Create canonical enums | MEDIUM | [ ] |
| T-10 | 3.1 | core/logging.py | Structured logging + run_id | MEDIUM | [ ] |
| T-11 | 3.2 | core/telemetry.py | Metrics counters per stage | MEDIUM | [ ] |
| T-12 | 3.3 | web_dashboard_clean.py | Fix AsyncDataManager thread leak | MEDIUM | [ ] |
| T-13 | 4.1 | tests/ | Setup pytest infrastructure | HIGH | [ ] |
| T-14 | 4.2 | tests/unit/ | Link validator unit tests | HIGH | [ ] |
| T-15 | 4.3 | tests/unit/ | Scraper parsing unit tests | HIGH | [ ] |
| T-16 | 4.4 | tests/integration/ | Pipeline integration tests | HIGH | [ ] |
| T-17 | 4.5 | tests/integration/ | API smoke tests | HIGH | [ ] |
| T-18 | 5.1 | core/circuit_breaker.py | Circuit breaker for external APIs | HIGH | [ ] |
| T-19 | 5.2 | scheduler.py | Add watchdog heartbeat task | MEDIUM | [ ] |
| T-20 | 5.3 | telegram_bot.py | Rate-limited broadcast function | MEDIUM | [ ] |
| T-21 | 5.4 | example.env | Document required vs optional keys | LOW | [ ] |
| T-22 | 6.1 | all | Run ruff + black + mypy | MEDIUM | [ ] |
| T-23 | 6.3 | .github/ | Create CI workflow | LOW | [ ] |
| T-24 | 7.1 | — | Full boot test all modes | CRITICAL | [ ] |
| T-25 | 7.3 | — | Run regression check script | CRITICAL | [ ] |

---

## ═══════════════════════════════════════════
## 📁 TARGET DIRECTORY STRUCTURE
## ═══════════════════════════════════════════

```
project/
├── main.py                    # entrypoint (thin orchestrator)
├── config.py                  # env/settings loader
├── models.py                  # domain entities + enums
├── requirements.txt
├── example.env                # documented env template
├── pytest.ini
├── Makefile
│
├── core/
│   ├── __init__.py
│   ├── errors.py              # typed exception hierarchy [T-08]
│   ├── enums.py               # canonical enums [T-09]
│   ├── logging.py             # structured logging + run_id [T-10]
│   ├── telemetry.py           # metrics counters [T-11]
│   └── circuit_breaker.py    # circuit breaker [T-18]
│
├── ports/
│   ├── __init__.py
│   └── repository.py         # DealRepository Protocol [T-07]
│
├── services/
│   ├── __init__.py
│   └── deal_pipeline_service.py  # unified pipeline [T-05]
│
├── adapters/
│   ├── db_postgres.py         # (rename from database.py)
│   └── db_memory.py           # (rename from database_simple.py)
│
├── scraper.py
├── telegram_bot.py
├── scheduler.py
├── content_generator.py
├── link_validator.py
├── web_dashboard_clean.py
│
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── deals.html
│   └── users.html
│
├── static/
│   ├── css/dashboard.css
│   └── js/dashboard.js        # (dashboard_old.js REMOVED) [T-04]
│
└── tests/
    ├── __init__.py
    ├── unit/
    │   ├── test_link_validator.py   [T-14]
    │   └── test_scraper.py          [T-15]
    └── integration/
        ├── test_pipeline.py         [T-16]
        └── test_api.py              [T-17]
```

---

*End of vision.md — Agent: mark each [x] upon task completion and commit.*
