# Dependency Audit — DealPilotAI

Date: 2026-10-31. Environment: Python 3.14.7 venv, `pip check` clean, `pip-audit` clean.

## requirements.txt (as committed)

aiofiles, aiogram, aiohttp, asyncpg, beautifulsoup4, click, flask, gunicorn,
itsdangerous, jinja2, lxml, markupsafe, openai, psycopg2-binary, psycopg,
pydantic, pydantic-settings, python-dotenv, sqlalchemy, trafilatura, werkzeug

## Findings

| # | Finding | Severity | Evidence | Correction |
|---|---------|----------|----------|------------|
| 1 | `httpx` imported but not declared | HIGH (fresh-install break) | imports in paypal_checkout/client.py:10, web/commerce_routes.py:19, tests/commerce/test_paypal_client.py:9; ModuleNotFoundError on fresh venv | Add `httpx` to requirements.txt |
| 2 | No pins anywhere | MEDIUM (reproducibility) | requirements.txt has zero version specifiers | Generate lockfile (pip-compile or pip freeze) before submission |
| 3 | Dual PG drivers (psycopg2-binary + psycopg + asyncpg) | LOW | requirements.txt | Keep (different lanes), document why |
| 4 | Dev tools not declared (pytest, pytest-asyncio, ruff) | LOW | installed ad-hoc in audit venv | Add requirements-dev.txt or [dev] extra |
| 5 | openai SDK used for both OpenAI + Featherless | INFO | ai/providers.py build_client() | Documented in code; fine |

## Vulnerability scan

`pip-audit` (2026-10-31, full resolved env): **No known vulnerabilities found.**

## Runtime verification

All committed deps install cleanly on Python 3.14.7; 118/118 tests pass
(with FLASK_SECRET_KEY provided). aiogram/trafilatura/asyncpg import fine on 3.14.
