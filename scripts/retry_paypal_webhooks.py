#!/usr/bin/env python3
"""Retry durable, verified PayPal webhook events that need reconciliation.

Run once or schedule periodically with the application's sandbox environment.
No webhook payloads or credentials are printed.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import Config
from web.commerce_routes import _build_services, process_pending_webhook_events
from web_dashboard_clean import create_app


def main() -> int:
    config = Config()
    app = create_app(config)
    with app.app_context():
        services = _build_services(config)
        storage = services.get("storage")
        checkout = services.get("checkout_service")
        if storage is None:
            print("WEBHOOK_RETRY=BLOCKED; configure durable COMMERCE_DATABASE_URL")
            return 2
        if checkout is None:
            print(
                "WEBHOOK_RETRY=BLOCKED; configure PAYPAL_CLIENT_ID and "
                "PAYPAL_CLIENT_SECRET"
            )
            return 2

        processed = process_pending_webhook_events(storage, checkout)
        remaining = len(storage.list_retryable_events())
        print(
            f"WEBHOOK_RETRY=COMPLETE processed={processed} remaining={remaining}"
        )
        return 1 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())