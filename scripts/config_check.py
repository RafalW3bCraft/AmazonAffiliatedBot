#!/usr/bin/env python3
"""Offline configuration validator for DealPilotAI.

Checks syntax/format/presence of every environment variable the app reads —
no network calls, no secret values printed. Exit 0 = all required vars sane;
exit 1 = at least one blocking problem. Optional --online flag adds read-only
auth probes (PayPal OAuth) using the real credentials.

Usage:
    python scripts/config_check.py            # offline
    python scripts/config_check.py --online   # + safe read-only probes
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROBLEMS = []
WARNINGS = []


def _get(name, default=''):
    return os.getenv(name, default).strip()


def require(name, fmt=None, fmt_desc=''):
    v = _get(name)
    if not v:
        PROBLEMS.append(f'{name}: MISSING (required)')
        return ''
    if fmt and not fmt.match(v):
        PROBLEMS.append(f'{name}: malformed (expected {fmt_desc})')
    return v


def warn_if_missing(name, why):
    if not _get(name):
        WARNINGS.append(f'{name}: not set — {why}')


def main():
    online = '--online' in sys.argv

    # --- required, fail-closed ---
    if _get('DEMO_MODE').lower() not in ('1', 'true', 'yes'):
        require('FLASK_SECRET_KEY', re.compile(r'^.{16,}$'), 'at least 16 chars')

    # --- PayPal ---
    env = _get('PAYPAL_ENVIRONMENT', 'sandbox')
    if env != 'sandbox':
        PROBLEMS.append(f"PAYPAL_ENVIRONMENT must be 'sandbox' (got {env!r}); live is refused")
    cid = _get('PAYPAL_CLIENT_ID')
    csec = _get('PAYPAL_CLIENT_SECRET')
    if bool(cid) != bool(csec):
        PROBLEMS.append('PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET must be set together')
    if cid and len(cid) < 20:
        WARNINGS.append('PAYPAL_CLIENT_ID looks too short — verify it is the SANDBOX app id')
    warn_if_missing('PAYPAL_WEBHOOK_ID', 'webhook endpoint will refuse (503)')
    cur = _get('PAYPAL_CURRENCY', 'USD').upper()
    if cur not in ('USD',):
        PROBLEMS.append(f'PAYPAL_CURRENCY {cur!r} unsupported (supported: USD)')

    # --- commerce storage ---
    cdb = _get('COMMERCE_DATABASE_URL')
    if cid and csec and _get('ENABLE_MERCHANT_CHECKOUT', 'true').lower() in ('1', 'true', 'yes'):
        if not cdb:
            WARNINGS.append('COMMERCE_DATABASE_URL unset — falls back to DATABASE_URL then local sqlite; set explicitly for production')
        elif cdb in ('memory', ''):
            PROBLEMS.append('COMMERCE_DATABASE_URL must be durable (postgresql:// or sqlite:///), not memory/empty')
        elif not (cdb.startswith('postgresql://') or cdb.startswith('sqlite:///')):
            PROBLEMS.append(f'COMMERCE_DATABASE_URL must start with postgresql:// or sqlite:/// (got {cdb[:12]}…)')

    # --- AI ---
    if not _get('OPENAI_API_KEY') and not _get('FEATHERLESS_API_KEY'):
        WARNINGS.append('No AI provider key — AI will run in deterministic-fallback mode (honest, but not real inference)')

    # --- Telegram / affiliate (Lane A) ---
    tok = _get('TELEGRAM_BOT_TOKEN')
    if tok and not re.match(r'^\d{6,}:[A-Za-z0-9_-]{30,}$', tok):
        WARNINGS.append('TELEGRAM_BOT_TOKEN fails structural check (verify via getMe)')
    aff = _get('AMAZON_AFFILIATE_ID')
    if aff and not re.match(r'^[A-Za-z0-9-]{10,20}$', aff):
        WARNINGS.append('AMAZON_AFFILIATE_ID format unusual')
    ids = _get('ADMIN_USER_IDS')
    if ids:
        for part in ids.split(','):
            if part.strip() and not part.strip().isdigit():
                PROBLEMS.append(f'ADMIN_USER_IDS entry {part.strip()!r} is not an integer')

    # --- legacy alias conflicts ---
    if _get('BOT_TOKEN') and _get('TELEGRAM_BOT_TOKEN') and _get('BOT_TOKEN') != _get('TELEGRAM_BOT_TOKEN'):
        PROBLEMS.append('BOT_TOKEN and TELEGRAM_BOT_TOKEN both set with different values — remove BOT_TOKEN')
    if _get('TELEGRAM_CHENNAL') and _get('TELEGRAM_CHANNEL') and _get('TELEGRAM_CHENNAL') != _get('TELEGRAM_CHANNEL'):
        PROBLEMS.append('TELEGRAM_CHENNAL (typo alias) conflicts with TELEGRAM_CHANNEL — remove the typo var')

    # --- report ---
    print('=== DealPilotAI offline config check ===')
    for w in WARNINGS:
        print(f'  WARN  {w}')
    for p in PROBLEMS:
        print(f'  FAIL  {p}')
    if not PROBLEMS:
        print('  offline checks: OK')

    if online and not PROBLEMS and cid and csec:
        print('--- online read-only probes ---')
        try:
            from paypal_checkout.client import get_bearer_token
            get_bearer_token(cid, csec)
            print('  PayPal sandbox OAuth: OK')
        except Exception as e:
            print(f'  PayPal sandbox OAuth: FAIL ({type(e).__name__})')
            PROBLEMS.append('PayPal OAuth probe failed — check sandbox credentials')

    print(f'=== {"FAIL" if PROBLEMS else "PASS"} ({len(PROBLEMS)} problems, {len(WARNINGS)} warnings) ===')
    return 1 if PROBLEMS else 0


if __name__ == '__main__':
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    sys.exit(main())
