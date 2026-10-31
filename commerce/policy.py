"""Commerce policy guards: currency set, cart total cap, quantity bounds."""

from __future__ import annotations

from decimal import Decimal

from .exceptions import PolicyError
from .schemas import to_decimal

SUPPORTED_CURRENCIES = {"USD"}
MIN_QUANTITY = 1
MAX_QUANTITY = 10
MAX_LINES = 10


def validate_policy(config) -> None:
    """Startup-time policy sanity check.

    Raises PolicyError if the configured PayPal currency is not in the
    supported set — better to crash at boot than to quote an unsupported
    currency at checkout time.
    """
    currency = getattr(config, "PAYPAL_CURRENCY", None)
    if currency not in SUPPORTED_CURRENCIES:
        raise PolicyError(
            f"PAYPAL_CURRENCY {currency!r} not supported; "
            f"supported: {sorted(SUPPORTED_CURRENCIES)}"
        )


def max_cart_total(config) -> Decimal:
    """Return MAX_CART_TOTAL from config as a Decimal (config stores a str)."""
    return to_decimal(getattr(config, "MAX_CART_TOTAL", "500.00"))


def assert_checkout_allowed(config) -> None:
    """Guard: DEMO_MODE must never fake payments.

    DEMO_MODE exists to seed the catalog and exercise the UI without a real
    merchant account, but any checkout attempt MUST still go through a real
    PayPal capture. Raising here (rather than silently succeeding) is the
    tripwire that prevents a demo build from pretending money moved.
    """
    if getattr(config, "DEMO_MODE", False) and not getattr(
        config, "ENABLE_MERCHANT_CHECKOUT", True
    ):
        raise RuntimeError(
            "DEMO_MODE may seed the catalog but must not bypass real PayPal "
            "capture; ENABLE_MERCHANT_CHECKOUT is disabled."
        )
