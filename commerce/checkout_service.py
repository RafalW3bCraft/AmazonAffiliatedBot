"""Checkout state machine with idempotency and PayPal capture verification.

The gateway is injected (any object with create_order/get_order/capture_order)
— unit tests fake it; production wires paypal_checkout.PayPalClient.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from .cart_service import CartService
from .exceptions import (
    AmbiguousCheckoutError,
    AmountMismatch,
    CheckoutError,
    DuplicateCapture,
    ForbiddenBuyer,
    InvalidStateTransition,
    NotApproved,
    QuoteExpired,
)
from .policy import assert_checkout_allowed
from .schemas import format_money, to_decimal
from .storage import CommerceStorage
from paypal_checkout.errors import (
    PayPalAmbiguousError,
    PayPalApiError,
    PayPalAuthError,
    PayPalTimeoutError,
)

# -- states ---------------------------------------------------------------

ORDER_CREATED = "ORDER_CREATED"
AWAITING_BUYER_APPROVAL = "AWAITING_BUYER_APPROVAL"
APPROVED = "APPROVED"
CAPTURE_PENDING = "CAPTURE_PENDING"
PAID = "PAID"
FAILED = "FAILED"
CANCELED = "CANCELED"
REQUIRES_REVIEW = "REQUIRES_REVIEW"

ALLOWED: dict[str, tuple[str, ...]] = {
    ORDER_CREATED: (AWAITING_BUYER_APPROVAL, FAILED, CANCELED, REQUIRES_REVIEW),
    AWAITING_BUYER_APPROVAL: (APPROVED, CAPTURE_PENDING, FAILED, CANCELED, REQUIRES_REVIEW),
    APPROVED: (CAPTURE_PENDING, FAILED, CANCELED, REQUIRES_REVIEW),
    CAPTURE_PENDING: (PAID, FAILED, REQUIRES_REVIEW),
    PAID: (),
    FAILED: (),
    CANCELED: (),
    REQUIRES_REVIEW: (AWAITING_BUYER_APPROVAL, CAPTURE_PENDING, PAID, FAILED, CANCELED),
}

# Capture is allowed until quote expiry plus this grace window.
CAPTURE_GRACE = timedelta(minutes=15)
CAPTURE_OWNERSHIP_TTL = timedelta(minutes=2)

TERMINAL = (FAILED, CANCELED)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_ambiguous_gateway_error(exc: Exception) -> bool:
    return isinstance(
        exc,
        (GatewayTimeout, TimeoutError, PayPalTimeoutError, PayPalAmbiguousError),
    ) or (
        isinstance(exc, PayPalApiError)
        and (exc.status_code is None or exc.status_code >= 500)
    )


class GatewayTimeout(Exception):
    """Tests/fakes raise this to simulate an ambiguous gateway timeout."""


class CheckoutService:
    def __init__(
        self,
        storage: CommerceStorage,
        cart_service: CartService,
        gateway,
        config,
        clock=_utcnow,
    ):
        assert_checkout_allowed(config)
        self.storage = storage
        self.cart_service = cart_service
        self.gateway = gateway
        self.config = config
        self.clock = clock

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _request_id(quote_id: str, buyer_id: str) -> str:
        return hashlib.sha256(f"{quote_id}:{buyer_id}".encode()).hexdigest()

    def _transition(self, attempt_id: int, current: str, new: str) -> None:
        if new not in ALLOWED.get(current, ()):
            raise InvalidStateTransition(f"{current} -> {new} not allowed")
        self.storage.require_transition(attempt_id, new, (current,))

    @staticmethod
    def _approve_url(order: dict) -> str | None:
        for link in order.get("links", []) or []:
            if link.get("rel") == "approve":
                return link.get("href")
        return None

    @staticmethod
    def _order_amount(order: dict) -> tuple[str, str]:
        units = order.get("purchase_units") or []
        amount = (units[0].get("amount") or {}) if units else {}
        return str(amount.get("value", "")), str(amount.get("currency_code", ""))

    @staticmethod
    def _captures_from_order(order: dict) -> list[dict]:
        out: list[dict] = []
        for unit in order.get("purchase_units") or []:
            payments = unit.get("payments") or {}
            for cap in payments.get("captures") or []:
                out.append(cap)
        return out

    # -- start_checkout ---------------------------------------------------

    def start_checkout(self, actor_id: str, quote_id: str, buyer_id: str) -> dict:
        quote = self.cart_service.validate_quote(quote_id, actor_id=actor_id)
        self.cart_service.refresh_check(quote_id, actor_id=actor_id)

        request_id = self._request_id(quote_id, buyer_id)
        existing = self.storage.get_attempt(request_id=request_id)
        if existing is not None and existing.status not in TERMINAL:
            # Idempotent replay: return the same attempt, no new gateway call.
            return {
                "attempt_id": existing.id,
                "paypal_order_id": existing.paypal_order_id,
                "approve_url": None,
                "status": existing.status,
            }

        quote_row = self.storage.get_quote(quote_id)
        attempt = self.storage.create_checkout_attempt(
            cart_quote_id=quote_row.id,
            buyer_id=buyer_id,
            request_id=request_id,
            status=ORDER_CREATED,
        )

        purchase_units = [
            {
                "reference_id": quote_id,
                "custom_id": str(attempt.id),
                "amount": {
                    "currency_code": quote.currency,
                    "value": format_money(quote.total),
                },
            }
        ]
        try:
            order = self.gateway.create_order(
                intent="CAPTURE",
                purchase_units=purchase_units,
                request_id=request_id,
            )
        except Exception as exc:
            if not _is_ambiguous_gateway_error(exc):
                self._transition(attempt.id, ORDER_CREATED, FAILED)
                raise CheckoutError(
                    f"gateway create_order failed: {type(exc).__name__}"
                ) from exc
            # Outcome unknown — the order may exist remotely.
            self._transition(attempt.id, ORDER_CREATED, REQUIRES_REVIEW)
            raise AmbiguousCheckoutError(
                f"create_order outcome unknown for attempt {attempt.id}: "
                f"{type(exc).__name__}"
            ) from exc

        paypal_order_id = order.get("id")
        self.storage.attach_paypal_order(attempt.id, paypal_order_id)
        self._transition(attempt.id, ORDER_CREATED, AWAITING_BUYER_APPROVAL)
        return {
            "attempt_id": attempt.id,
            "paypal_order_id": paypal_order_id,
            "approve_url": self._approve_url(order),
            "status": AWAITING_BUYER_APPROVAL,
        }

    # -- capture_after_approval ---------------------------------------------

    def capture_after_approval(
        self, actor_id: str, attempt_id: int, buyer_id: str
    ) -> dict:
        attempt = self.storage.get_attempt(attempt_id=attempt_id)
        if attempt is None:
            raise CheckoutError(f"unknown attempt {attempt_id}")
        if attempt.buyer_id != buyer_id:
            raise ForbiddenBuyer(
                f"buyer {buyer_id!r} does not own attempt {attempt_id}"
            )
        if attempt.status == PAID:
            return {"attempt_id": attempt_id, "status": PAID}
        if attempt.status in TERMINAL:
            raise CheckoutError(f"attempt {attempt_id} is {attempt.status}")
        if attempt.status in (CAPTURE_PENDING, REQUIRES_REVIEW):
            self.reconcile(attempt_id)
            attempt = self.storage.get_attempt(attempt_id=attempt_id)
            if attempt.status == PAID:
                return {"attempt_id": attempt_id, "status": PAID}
            if attempt.status not in (AWAITING_BUYER_APPROVAL, APPROVED):
                return {"attempt_id": attempt_id, "status": attempt.status}

        quote_row = self.storage.get_quote_by_pk(attempt.cart_quote_id)
        quote = self.storage.quote_to_data(quote_row)
        now = self.clock()
        if now > quote.expires_at + CAPTURE_GRACE:
            raise QuoteExpired(
                f"quote {quote.quote_id} expired beyond capture grace"
            )

        try:
            order = self.gateway.get_order(attempt.paypal_order_id)
        except Exception as exc:
            review_sources = (
                ORDER_CREATED,
                AWAITING_BUYER_APPROVAL,
                APPROVED,
                REQUIRES_REVIEW,
            )
            if not _is_ambiguous_gateway_error(exc):
                if isinstance(exc, PayPalAuthError):
                    self.storage.set_attempt_status(
                        attempt_id, REQUIRES_REVIEW, review_sources
                    )
                    raise CheckoutError(
                        "PayPal authentication failed during order lookup"
                    ) from exc
                raise CheckoutError(
                    f"PayPal order lookup failed: {type(exc).__name__}"
                ) from exc
            self.storage.set_attempt_status(
                attempt_id, REQUIRES_REVIEW, review_sources
            )
            raise AmbiguousCheckoutError(
                f"get_order outcome unknown for attempt {attempt_id}: "
                f"{type(exc).__name__}"
            ) from exc

        if order.get("status") != "APPROVED":
            raise NotApproved(
                f"order {attempt.paypal_order_id} status is "
                f"{order.get('status')!r}, need 'APPROVED'"
            )

        # Amount/currency must match the quote snapshot EXACTLY.
        value, currency = self._order_amount(order)
        expected = format_money(quote.total)
        if value != expected or currency != quote.currency:
            self.storage.set_attempt_status(
                attempt_id,
                REQUIRES_REVIEW,
                (AWAITING_BUYER_APPROVAL, APPROVED, REQUIRES_REVIEW),
            )
            raise AmountMismatch(
                f"order amount {value} {currency} != quote {expected} {quote.currency}"
            )

        # Single-flight: only one worker may flip into CAPTURE_PENDING.
        capture_request_id = attempt.capture_request_id or f"capture-{attempt_id}"
        moved = self.storage.set_attempt_status(
            attempt_id,
            CAPTURE_PENDING,
            (AWAITING_BUYER_APPROVAL, APPROVED),
            capture_request_id=capture_request_id,
        )
        if not moved:
            current = self.storage.get_attempt(attempt_id=attempt_id)
            return {"attempt_id": attempt_id, "status": current.status}

        attempt = self.storage.get_attempt(attempt_id=attempt_id)
        capture_request_id = attempt.capture_request_id
        try:
            response = self.gateway.capture_order(
                attempt.paypal_order_id, request_id=capture_request_id
            )
        except Exception as exc:
            if not _is_ambiguous_gateway_error(exc):
                if isinstance(exc, PayPalAuthError):
                    self.storage.set_attempt_status(
                        attempt_id, REQUIRES_REVIEW, (CAPTURE_PENDING,)
                    )
                    raise CheckoutError(
                        "PayPal authentication failed during capture"
                    ) from exc
                self.storage.set_attempt_status(
                    attempt_id, FAILED, (CAPTURE_PENDING,)
                )
                raise CheckoutError(
                    f"gateway capture_order failed: {type(exc).__name__}"
                ) from exc
            self.storage.set_attempt_status(
                attempt_id, REQUIRES_REVIEW, (CAPTURE_PENDING,)
            )
            raise AmbiguousCheckoutError(
                f"capture outcome unknown for attempt {attempt_id}: "
                f"{type(exc).__name__}"
            ) from exc

        captures = self._captures_from_order(response)
        completed = next(
            (c for c in captures if c.get("status") == "COMPLETED"), None
        )
        if completed is None:
            denied = next((c for c in captures if c.get("status") == "DENIED"), None)
            if denied is not None:
                self.storage.set_attempt_status(
                    attempt_id, FAILED, (CAPTURE_PENDING,)
                )
                return {"attempt_id": attempt_id, "status": FAILED}
            pending = next((c for c in captures if c.get("status") == "PENDING"), None)
            if pending is not None:
                # No fake success: stay CAPTURE_PENDING until webhook/reconcile.
                return {"attempt_id": attempt_id, "status": CAPTURE_PENDING}
            self.storage.set_attempt_status(attempt_id, REQUIRES_REVIEW, (CAPTURE_PENDING,))
            raise AmbiguousCheckoutError(
                "capture response had no COMPLETED or PENDING capture"
            )

        cap_amount = (completed.get("amount") or {})
        if (
            str(cap_amount.get("value", "")) != expected
            or str(cap_amount.get("currency_code", "")) != quote.currency
        ):
            self.storage.set_attempt_status(attempt_id, REQUIRES_REVIEW, (CAPTURE_PENDING,))
            raise AmountMismatch("capture amount differs from quote snapshot")

        capture_id = completed.get("id")
        try:
            self.storage.record_capture(
                attempt_id=attempt_id,
                capture_id=capture_id,
                amount=to_decimal(expected),
                currency=quote.currency,
                status="COMPLETED",
                verified_at=now.replace(tzinfo=None),
            )
        except DuplicateCapture:
            # Already recorded (webhook or prior reconcile) — idempotent.
            pass

        self.storage.set_attempt_status(attempt_id, PAID, (CAPTURE_PENDING,))
        self.storage.update_quote_status(quote.quote_id, "PAID")
        return {
            "attempt_id": attempt_id,
            "status": PAID,
            "capture_id": capture_id,
        }

    def cancel_before_capture(
        self, buyer_id: str, attempt_id: int, paypal_order_id: str
    ) -> bool:
        """Cancel only the owning buyer's matching, uncaptured PayPal order."""
        attempt = self.storage.get_attempt(attempt_id=attempt_id)
        eligible = (ORDER_CREATED, AWAITING_BUYER_APPROVAL, APPROVED)
        if (
            attempt is None
            or attempt.buyer_id != buyer_id
            or attempt.paypal_order_id != paypal_order_id
            or attempt.status not in eligible
        ):
            return False

        try:
            order = self.gateway.get_order(paypal_order_id)
        except Exception:
            return False
        if (
            order.get("id") != paypal_order_id
            or order.get("status") not in {"CREATED", "APPROVED"}
            or self._captures_from_order(order)
        ):
            return False

        return self.storage.set_attempt_status(
            attempt_id, CANCELED, eligible
        )

    # -- reconcile ----------------------------------------------------------

    def reconcile(self, attempt_id: int) -> dict:
        """Self-heal: read the remote order and align local state."""
        attempt = self.storage.get_attempt(attempt_id=attempt_id)
        if attempt is None:
            raise CheckoutError(f"unknown attempt {attempt_id}")
        order = self.gateway.get_order(attempt.paypal_order_id)
        remote_status = order.get("status")

        if order.get("id") != attempt.paypal_order_id:
            return {"attempt_id": attempt_id, "status": REQUIRES_REVIEW}

        quote = self.storage.quote_to_data(
            self.storage.get_quote_by_pk(attempt.cart_quote_id)
        )
        value, currency = self._order_amount(order)
        if value != format_money(quote.total) or currency != quote.currency:
            self.storage.set_attempt_status(
                attempt_id,
                REQUIRES_REVIEW,
                (ORDER_CREATED, AWAITING_BUYER_APPROVAL, APPROVED, REQUIRES_REVIEW),
            )
            return {"attempt_id": attempt_id, "status": REQUIRES_REVIEW}

        captures = self._captures_from_order(order)
        completed = next((c for c in captures if c.get("status") == "COMPLETED"), None)
        if completed is not None:
            cap_amount = (completed.get("amount") or {})
            value = str(cap_amount.get("value", ""))
            currency = str(cap_amount.get("currency_code", ""))
            if value == format_money(quote.total) and currency == quote.currency:
                capture_id = completed.get("id")
                if self.storage.get_capture(capture_id=capture_id) is None:
                    try:
                        self.storage.record_capture(
                            attempt_id=attempt_id,
                            capture_id=capture_id,
                            amount=to_decimal(value),
                            currency=currency,
                            status="COMPLETED",
                            verified_at=self.clock().replace(tzinfo=None),
                        )
                    except DuplicateCapture:
                        pass
                self.storage.set_attempt_status(
                    attempt_id,
                    PAID,
                    (ORDER_CREATED, AWAITING_BUYER_APPROVAL, APPROVED,
                     CAPTURE_PENDING, REQUIRES_REVIEW),
                )
                self.storage.update_quote_status(quote.quote_id, "PAID")
                return {"attempt_id": attempt_id, "status": PAID, "capture_id": capture_id}

        if any(capture.get("status") == "DENIED" for capture in captures):
            self.storage.set_attempt_status(
                attempt_id,
                FAILED,
                (ORDER_CREATED, AWAITING_BUYER_APPROVAL, APPROVED,
                 CAPTURE_PENDING, REQUIRES_REVIEW),
            )
            return {"attempt_id": attempt_id, "status": FAILED}

        if any(capture.get("status") == "PENDING" for capture in captures):
            self.storage.set_attempt_status(
                attempt_id,
                CAPTURE_PENDING,
                (ORDER_CREATED, AWAITING_BUYER_APPROVAL, APPROVED, REQUIRES_REVIEW),
            )
            return {"attempt_id": attempt_id, "status": CAPTURE_PENDING}

        if remote_status == "APPROVED":
            current_state = attempt.status
            if current_state in (CAPTURE_PENDING, REQUIRES_REVIEW):
                updated_at = attempt.updated_at
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=UTC)
                ownership_is_fresh = (
                    attempt.capture_request_id is not None
                    and self.clock() - updated_at < CAPTURE_OWNERSHIP_TTL
                )
                if ownership_is_fresh:
                    return {"attempt_id": attempt_id, "status": current_state}
                changed = self.storage.set_attempt_status(
                    attempt_id, AWAITING_BUYER_APPROVAL, (current_state,)
                )
                if not changed:
                    attempt = self.storage.get_attempt(attempt_id=attempt_id)
                    return {"attempt_id": attempt_id, "status": attempt.status}
            elif current_state == ORDER_CREATED:
                self.storage.set_attempt_status(
                    attempt_id, AWAITING_BUYER_APPROVAL, (ORDER_CREATED,)
                )
            elif current_state not in (AWAITING_BUYER_APPROVAL, APPROVED):
                return {"attempt_id": attempt_id, "status": current_state}
            return {
                "attempt_id": attempt_id,
                "status": AWAITING_BUYER_APPROVAL,
            }
        return {"attempt_id": attempt_id, "status": attempt.status}

    # -- status view --------------------------------------------------------

    def get_order_status(self, actor_id: str, attempt_id: int) -> dict:
        attempt = self.storage.get_attempt(attempt_id=attempt_id)
        if attempt is None:
            raise CheckoutError(f"unknown attempt {attempt_id}")
        # Buyer or merchant (actor marked 'merchant:*') may view; redacted.
        if attempt.buyer_id != actor_id and not str(actor_id).startswith("merchant:"):
            raise ForbiddenBuyer(actor_id)
        return {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "paypal_order_id": attempt.paypal_order_id,
        }
