"""Checkout service tests with an injected fake PayPal gateway."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from commerce.cart_service import CartService
from commerce.catalog import Catalog
from commerce.checkout_service import (
    APPROVED,
    AWAITING_BUYER_APPROVAL,
    CAPTURE_PENDING,
    FAILED,
    PAID,
    REQUIRES_REVIEW,
    CheckoutService,
    GatewayTimeout,
)
from commerce.exceptions import (
    AmbiguousCheckoutError,
    AmountMismatch,
    CheckoutError,
    ForbiddenBuyer,
    NotApproved,
    QuoteExpired,
)
from commerce.schemas import CartItem
from commerce.storage import CommerceStorage

CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "merchant_catalog.json"
BUYER = "buyer-123"


class FakeConfig:
    PAYPAL_CURRENCY = "USD"
    MAX_CART_TOTAL = "500.00"
    CART_QUOTE_TTL_MINUTES = 30
    DEMO_MODE = False
    ENABLE_MERCHANT_CHECKOUT = True


class MutableClock:
    def __init__(self):
        self.now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class FakeGatewayError(Exception):
    pass


class FakeGateway:
    """Programmable fake of the PayPalClient interface."""

    def __init__(self):
        self.create_calls = []
        self.get_calls = []
        self.capture_calls = []
        self.orders: dict[str, dict] = {}
        self._seq = 0
        # programmables
        self.create_error: Exception | None = None
        self.capture_error: Exception | None = None
        self.order_status = "APPROVED"
        self.capture_status = "COMPLETED"
        self.amount_override: str | None = None
        self.currency_override: str | None = None
        self.tamper_order_amount: str | None = None
        self.remote_completed_after_timeout = False

    def create_order(self, intent, purchase_units, request_id):
        self.create_calls.append(
            {"intent": intent, "purchase_units": purchase_units, "request_id": request_id}
        )
        if self.create_error:
            raise self.create_error
        self._seq += 1
        order_id = f"ORDER-{self._seq:04d}"
        amount = dict(purchase_units[0]["amount"])
        if self.amount_override:
            amount["value"] = self.amount_override
        if self.currency_override:
            amount["currency_code"] = self.currency_override
        self.orders[order_id] = {
            "id": order_id,
            "status": self.order_status,
            "purchase_units": [{"amount": amount}],
            "links": [{"rel": "approve", "href": f"https://paypal.test/approve/{order_id}"}],
        }
        return self.orders[order_id]

    def get_order(self, order_id):
        self.get_calls.append(order_id)
        order = self.orders[order_id]
        if self.tamper_order_amount:
            order["purchase_units"][0]["amount"]["value"] = self.tamper_order_amount
        return order

    def capture_order(self, order_id, request_id):
        self.capture_calls.append({"order_id": order_id, "request_id": request_id})
        if self.capture_error:
            if self.remote_completed_after_timeout:
                # the capture actually went through remotely
                self.orders[order_id]["status"] = "COMPLETED"
                amount = self.orders[order_id]["purchase_units"][0]["amount"]
                self.orders[order_id]["purchase_units"][0]["payments"] = {
                    "captures": [
                        {
                            "id": f"CAP-{order_id}",
                            "status": "COMPLETED",
                            "amount": dict(amount),
                        }
                    ]
                }
            raise self.capture_error
        amount = self.orders[order_id]["purchase_units"][0]["amount"]
        capture = {
            "id": f"CAP-{order_id}-{len(self.capture_calls)}",
            "status": self.capture_status,
            "amount": dict(amount),
        }
        if self.capture_status == "COMPLETED":
            self.orders[order_id]["status"] = "COMPLETED"
        self.orders[order_id]["purchase_units"][0].setdefault("payments", {}).setdefault(
            "captures", []
        ).append(capture)
        return {
            "id": order_id,
            "status": self.orders[order_id]["status"],
            "purchase_units": self.orders[order_id]["purchase_units"],
        }


@pytest.fixture()
def env(tmp_path):
    storage = CommerceStorage(f"sqlite:///{tmp_path}/commerce.db")
    clock = MutableClock()
    catalog = Catalog(CATALOG_PATH)
    cart = CartService(catalog, storage, FakeConfig(), clock=clock)
    gateway = FakeGateway()
    checkout = CheckoutService(storage, cart, gateway, FakeConfig(), clock=clock)
    return type("Env", (), {
        "storage": storage, "clock": clock, "catalog": catalog,
        "cart": cart, "gateway": gateway, "checkout": checkout,
    })


def make_quote(env, sku="DP-LAMP-001", qty=1):
    return env.cart.create_quote("actor-1", [CartItem(sku=sku, quantity=qty)])


def test_happy_path_create_approve_capture_paid(env):
    quote = make_quote(env, qty=2)
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    assert started["status"] == AWAITING_BUYER_APPROVAL
    assert started["paypal_order_id"].startswith("ORDER-")
    assert "approve" in started["approve_url"]
    # gateway got the right amount (24.99 * 2 = 49.98)
    call = env.gateway.create_calls[0]
    assert call["purchase_units"][0]["amount"]["value"] == "49.98"
    assert call["purchase_units"][0]["amount"]["currency_code"] == "USD"

    result = env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)
    assert result["status"] == PAID
    assert result["capture_id"].startswith("CAP-")
    capture = env.storage.get_capture(capture_id=result["capture_id"])
    assert capture is not None
    assert str(capture.amount) == "49.98"
    assert capture.currency == "USD"
    assert capture.status == "COMPLETED"
    assert capture.verified_at is not None
    # quote marked PAID
    assert env.storage.get_quote(quote.quote_id).status == "PAID"


def test_repeated_start_checkout_idempotent(env):
    quote = make_quote(env)
    first = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    second = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    assert first["attempt_id"] == second["attempt_id"]
    assert len(env.gateway.create_calls) == 1  # create_order called once


def test_capture_before_approved(env):
    quote = make_quote(env)
    env.gateway.order_status = "CREATED"  # buyer never approved
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    with pytest.raises(NotApproved):
        env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)


def test_tampered_amount_mismatch_and_review(env):
    quote = make_quote(env, qty=2)  # 49.98
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    env.gateway.tamper_order_amount = "4.98"
    with pytest.raises(AmountMismatch):
        env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)
    attempt = env.storage.get_attempt(attempt_id=started["attempt_id"])
    assert attempt.status == REQUIRES_REVIEW


def test_wrong_buyer_forbidden(env):
    quote = make_quote(env)
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    with pytest.raises(ForbiddenBuyer):
        env.checkout.capture_after_approval("actor-1", started["attempt_id"], "buyer-999")


def test_double_capture_single_flight(env):
    quote = make_quote(env)
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    r1 = env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)
    assert r1["status"] == PAID
    r2 = env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)
    assert r2["status"] == PAID
    assert len(env.gateway.capture_calls) == 1
    captures = env.storage.list_orders()  # ensure attempt list sane
    assert captures[0]["status"] == PAID


def test_expired_quote_rejected(env):
    quote = make_quote(env)
    env.clock.advance(minutes=31)
    with pytest.raises(QuoteExpired):
        env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)


def test_gateway_5xx_on_create_marks_failed(env):
    env.gateway.create_error = FakeGatewayError("502 bad gateway")
    quote = make_quote(env)
    with pytest.raises(CheckoutError):
        env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    attempts = env.storage.list_orders()
    assert attempts[0]["status"] == FAILED


def test_ambiguous_timeout_on_capture_then_reconcile_recovers(env):
    quote = make_quote(env)
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    env.gateway.capture_error = GatewayTimeout("timeout")
    env.gateway.remote_completed_after_timeout = True
    with pytest.raises(AmbiguousCheckoutError):
        env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)
    attempt = env.storage.get_attempt(attempt_id=started["attempt_id"])
    assert attempt.status == REQUIRES_REVIEW
    # reconcile reads the remote COMPLETED capture and self-heals
    env.gateway.capture_error = None
    healed = env.checkout.reconcile(started["attempt_id"])
    assert healed["status"] == PAID
    assert env.storage.get_capture(capture_id=healed["capture_id"]) is not None
    assert env.storage.get_quote(quote.quote_id).status == "PAID"


def test_currency_mismatch_rejected(env):
    quote = make_quote(env)
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    # tamper remote currency
    order = env.gateway.orders[started["paypal_order_id"]]
    order["purchase_units"][0]["amount"]["currency_code"] = "EUR"
    with pytest.raises(AmountMismatch):
        env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)


def test_pending_capture_does_not_mark_paid(env):
    quote = make_quote(env)
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    env.gateway.capture_status = "PENDING"
    result = env.checkout.capture_after_approval("actor-1", started["attempt_id"], BUYER)
    assert result["status"] == CAPTURE_PENDING
    attempt = env.storage.get_attempt(attempt_id=started["attempt_id"])
    assert attempt.status == CAPTURE_PENDING
    assert env.storage.get_capture(attempt_id=started["attempt_id"]) is None
    assert env.storage.get_quote(quote.quote_id).status != "PAID"


def test_get_order_status_buyer_and_merchant(env):
    quote = make_quote(env)
    started = env.checkout.start_checkout("actor-1", quote.quote_id, BUYER)
    view = env.checkout.get_order_status(BUYER, started["attempt_id"])
    assert view["status"] == AWAITING_BUYER_APPROVAL
    merchant_view = env.checkout.get_order_status("merchant:admin", started["attempt_id"])
    assert merchant_view["attempt_id"] == started["attempt_id"]
    with pytest.raises(ForbiddenBuyer):
        env.checkout.get_order_status("random-user", started["attempt_id"])
