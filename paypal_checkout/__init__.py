"""Synchronous PayPal Orders v2 sandbox client."""

from .client import PayPalClient
from .errors import (
    PayPalAmbiguousError,
    PayPalApiError,
    PayPalAuthError,
    PayPalError,
    PayPalTimeoutError,
)

__all__ = [
    "PayPalClient",
    "PayPalError",
    "PayPalAuthError",
    "PayPalApiError",
    "PayPalTimeoutError",
    "PayPalAmbiguousError",
]
