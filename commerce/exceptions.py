"""Commerce domain exceptions."""


class CommerceError(Exception):
    """Base for all commerce domain errors."""


class CatalogError(CommerceError):
    """Catalog load/validation problem."""


class PolicyError(CommerceError):
    """Policy violation (currency, cart total, quantity bounds)."""


class CartError(CommerceError):
    """Cart/quote lifecycle problem."""


class QuoteNotFound(CartError):
    pass


class QuoteExpired(CartError):
    pass


class QuoteNotOpen(CartError):
    pass


class QuoteStale(CartError):
    """Catalog moved on since the quote snapshot (version/stock changed)."""


class DuplicateRequest(CommerceError):
    """checkout_attempts.request_id unique violation."""


class DuplicateCapture(CommerceError):
    """payment_captures.paypal_capture_id unique violation."""


class CheckoutError(CommerceError):
    """Gateway or state failure during checkout."""


class AmbiguousCheckoutError(CheckoutError):
    """Gateway outcome unknown (timeout / 5xx after request possibly accepted).

    Caller must reconcile via gateway.get_order before retrying.
    """


class InvalidStateTransition(CheckoutError):
    pass


class ForbiddenBuyer(CheckoutError):
    pass


class NotApproved(CheckoutError):
    pass


class AmountMismatch(CheckoutError):
    pass
