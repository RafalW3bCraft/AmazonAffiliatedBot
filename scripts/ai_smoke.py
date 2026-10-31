#!/usr/bin/env python3
"""Gate 2 evidence: real AI smoke test against the configured provider.

Runs the production AIShoppingService against the live provider (OpenAI if
OPENAI_API_KEY set, else Featherless), prints the raw structured result, and
exits 0 only if: provider call succeeded, output validated against the strict
schema, all returned SKUs exist in the merchant catalog, and all prices match
the catalog exactly. Writes a redacted evidence record to docs/evidence/.

Usage:
    .venv/bin/python scripts/ai_smoke.py
"""
import json
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from ai.agent import AIShoppingService
from commerce.catalog import Catalog
from config import Config


def main() -> int:
    config = Config()
    if not config.ai_configured:
        print("REAL_AI_SMOKE=BLOCKED (no OPENAI_API_KEY or FEATHERLESS_API_KEY)")
        return 2

    catalog = Catalog(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   'config', 'merchant_catalog.json'))
    service = AIShoppingService(config, catalog)

    query = ("Find the best desk setup under $80. I prefer a compact LED lamp "
             "and a desk organizer. Explain the tradeoffs.")
    result = service.recommend(query, locale='en', actor_id='smoke-test')

    print("=== REAL AI SMOKE ===")
    print(f"provider={result.provider} fallback={result.fallback} confidence={result.confidence}")
    print(f"items={len(result.items)} cart_proposal={len(result.cart_proposal)}")
    for it in result.items:
        print(f"  - {it.sku} {it.currency} {it.price}: {it.reason[:80]}")
    if result.missing_info:
        print(f"missing_info={result.missing_info}")
    print(f"tradeoffs={result.tradeoffs[:200]}")

    # Grounding verification (independent of what the service already checks)
    failures = []
    if result.fallback:
        failures.append("provider fell back to deterministic mode (not a real AI pass)")
    for it in result.items:
        p = catalog.get_product(it.sku)
        if p is None:
            failures.append(f"hallucinated SKU {it.sku}")
        elif str(p.price) != it.price:
            failures.append(f"price mismatch {it.sku}: catalog {p.price} vs ai {it.price}")

    evidence = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "provider": result.provider,
        "model": getattr(config, 'AI_MODEL', '') or 'provider-default',
        "fallback": result.fallback,
        "query": query,
        "items": [{"sku": i.sku, "price": i.price, "currency": i.currency} for i in result.items],
        "confidence": result.confidence,
        "grounding_failures": failures,
    }
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'docs', 'evidence')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'ai_smoke.json')
    with open(out_path, 'w') as f:
        json.dump(evidence, f, indent=2)
    print(f"evidence written: {out_path}")

    if failures:
        print("REAL_AI_SMOKE=FAIL " + "; ".join(failures))
        return 1
    print("REAL_AI_SMOKE=PASS")
    return 0


if __name__ == '__main__':
    sys.exit(main())
