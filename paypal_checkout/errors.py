"""Typed exceptions for the PayPal checkout client."""


class PayPalError(Exception):
    """Base error for all PayPal client failures.

    Carries the HTTP status code and PayPal-Debug-Id header when available
    so callers can log or reconcile without parsing messages.
    """

    def __init__(self, message, status_code=None, debug_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.debug_id = debug_id


class PayPalAuthError(PayPalError):
    """OAuth token request was rejected (401) or otherwise failed."""


class PayPalApiError(PayPalError):
    """PayPal API returned a 4xx/5xx response."""


class PayPalTimeoutError(PayPalError):
    """Request to PayPal timed out."""


class PayPalAmbiguousError(PayPalError):
    """Network failure where the remote state is unknown.

    The request may or may not have reached PayPal (e.g. connection error
    after the request was sent). Callers MUST run reconciliation (fetch the
    order/token state) before taking further action — never blindly retry a
    capture, which could double-charge the payer.
    """
