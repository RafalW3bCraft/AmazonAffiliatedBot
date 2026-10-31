"""DealPilot commerce domain package.

Merchant-owned catalog -> cart quote (immutable Decimal price snapshot) ->
checkout state machine -> PayPal capture verification.
"""

from .exceptions import (
    AmbiguousCheckoutError,
    AmountMismatch,
    CartError,
    CatalogError,
    CheckoutError,
    DuplicateCapture,
    DuplicateRequest,
    ForbiddenBuyer,
    InvalidStateTransition,
    NotApproved,
    PolicyError,
    QuoteExpired,
    QuoteNotFound,
    QuoteNotOpen,
    QuoteStale,
)
from .schemas import (
    CartItem,
    CartQuoteData,
    CatalogProduct,
    QuoteLine,
    format_money,
    to_decimal,
)

__all__ = [
    "AmbiguousCheckoutError",
    "AmountMismatch",
    "CartError",
    "CartItem",
    "CartQuoteData",
    "CatalogError",
    "CatalogProduct",
    "CheckoutError",
    "DuplicateCapture",
    "DuplicateRequest",
    "ForbiddenBuyer",
    "InvalidStateTransition",
    "NotApproved",
    "PolicyError",
    "QuoteExpired",
    "QuoteLine",
    "QuoteNotFound",
    "QuoteNotOpen",
    "QuoteStale",
    "format_money",
    "to_decimal",
]
