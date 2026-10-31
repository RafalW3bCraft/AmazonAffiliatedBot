"""Contract tests for paypal_checkout.PayPalClient.

All HTTP is stubbed with httpx.MockTransport — no network access.
"""

import json
import re

import httpx
import pytest

from paypal_checkout import (
    PayPalApiError,
    PayPalAmbiguousError,
    PayPalAuthError,
    PayPalClient,
    PayPalTimeoutError,
)

CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
TOKEN_BODY = {"access_token": "sandbox-token-123", "expires_in": 3600}

ORDER_BODY = {
    "id": "ORDER-1",
    "status": "CREATED",
    "intent": "CAPTURE",
    "purchase_units": [
        {"reference_id": "default", "amount": {"currency_code": "USD", "value": "10.00"}}
    ],
}

CAPTURE_BODY = {
    "id": "ORDER-1",
    "status": "COMPLETED",
    "purchase_units": [
        {
            "payments": {
                "captures": [
                    {
                        "id": "CAPTURE-1",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "10.00"},
                    }
                ]
            }
        }
    ],
}


def make_transport(routes):
    """Build a MockTransport from {path: handler_or_body} routes."""

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json=TOKEN_BODY)
        route = routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})
        return route(request)

    return httpx.MockTransport(handler)


def make_client(routes=None, transport=None):
    transport = transport or make_transport(routes or {})
    http_client = httpx.Client(
        base_url="https://api-m.sandbox.paypal.com", transport=transport
    )
    return PayPalClient(CLIENT_ID, CLIENT_SECRET, http_client=http_client)


def json_route(body, status=200, record=None, headers=None):
    def handler(request):
        if record is not None:
            record.append(request)
        return httpx.Response(status, json=body, headers=headers or {})

    return handler


# 1. OAuth token success + caching
def test_token_success_and_caching():
    token_calls = []
    seen_auth = []

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            token_calls.append(request)
            seen_auth.append(request.headers.get("Authorization"))
            return httpx.Response(200, json=TOKEN_BODY)
        return httpx.Response(200, json=ORDER_BODY)

    client = make_client(transport=httpx.MockTransport(handler))

    first = client.get_access_token()
    second = client.get_access_token()

    assert first == "sandbox-token-123"
    assert second == first
    # Cached: the token endpoint was hit exactly once
    assert len(token_calls) == 1
    # Basic auth was used for the token request
    assert seen_auth[0].startswith("Basic ")


# 2. OAuth 401 -> PayPalAuthError
def test_token_401_raises_auth_error():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(
                401,
                json={"error": "invalid_client"},
                headers={"PayPal-Debug-Id": "dbg-401"},
            )
        return httpx.Response(200, json=ORDER_BODY)

    client = make_client(transport=httpx.MockTransport(handler))

    with pytest.raises(PayPalAuthError) as excinfo:
        client.get_access_token()
    assert excinfo.value.status_code == 401
    assert excinfo.value.debug_id == "dbg-401"


# 3. create_order: body, headers, sandbox URL; live env forbidden
def test_create_order_body_headers_and_sandbox_url():
    sent = []
    routes = {"/v2/checkout/orders": json_route(ORDER_BODY, 201, record=sent)}
    client = make_client(routes)

    result = client.create_order(
        purchase_units=[
            {"amount": {"currency_code": "USD", "value": "10.00"}}
        ],
        request_id="req-fixed-1",
    )

    assert result == ORDER_BODY
    assert len(sent) == 1
    request = sent[0]
    assert request.url.path == "/v2/checkout/orders"
    assert request.url.host == "api-m.sandbox.paypal.com"
    assert "api-m.paypal.com" not in request.url.host

    body = json.loads(request.content)
    assert body["intent"] == "CAPTURE"
    assert body["purchase_units"][0]["amount"]["value"] == "10.00"

    assert request.headers["Authorization"] == "Bearer sandbox-token-123"
    assert request.headers["PayPal-Request-Id"] == "req-fixed-1"
    assert request.headers["Prefer"] == "return=representation"
    assert client.last_request_id == "req-fixed-1"


def test_create_order_generates_request_id_when_omitted():
    sent = []
    routes = {"/v2/checkout/orders": json_route(ORDER_BODY, 201, record=sent)}
    client = make_client(routes)

    client.create_order(purchase_units=[])
    request_id = sent[0].headers["PayPal-Request-Id"]
    assert request_id
    assert client.last_request_id == request_id


def test_live_environment_rejected():
    with pytest.raises(ValueError):
        PayPalClient(CLIENT_ID, CLIENT_SECRET, environment="live")
    with pytest.raises(ValueError):
        PayPalClient(CLIENT_ID, CLIENT_SECRET, environment="production")


# 4. get_order path correct
def test_get_order_path():
    sent = []
    routes = {"/v2/checkout/orders/ORDER-42": json_route(ORDER_BODY, record=sent)}
    client = make_client(routes)

    result = client.get_order("ORDER-42")

    assert result == ORDER_BODY
    assert len(sent) == 1
    assert sent[0].method == "GET"
    assert sent[0].url.path == "/v2/checkout/orders/ORDER-42"
    assert sent[0].headers["Authorization"] == "Bearer sandbox-token-123"


# 5. capture_order posts to /capture with idempotency header
def test_capture_order_posts_to_capture_with_request_id():
    sent = []
    routes = {
        "/v2/checkout/orders/ORDER-1/capture": json_route(CAPTURE_BODY, record=sent)
    }
    client = make_client(routes)

    result = client.capture_order("ORDER-1", request_id="req-capture-1")

    assert result == CAPTURE_BODY
    assert len(sent) == 1
    request = sent[0]
    assert request.method == "POST"
    assert request.url.path == "/v2/checkout/orders/ORDER-1/capture"
    assert request.headers["PayPal-Request-Id"] == "req-capture-1"
    assert request.headers["Authorization"] == "Bearer sandbox-token-123"
    assert client.last_request_id == "req-capture-1"


# 6. 4xx/5xx -> PayPalApiError with status_code
def test_create_order_4xx_raises_api_error():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json=TOKEN_BODY)
        return httpx.Response(
            400,
            json={"name": "INVALID_REQUEST"},
            headers={"PayPal-Debug-Id": "dbg-400"},
        )

    client = make_client(transport=httpx.MockTransport(handler))

    with pytest.raises(PayPalApiError) as excinfo:
        client.create_order(purchase_units=[])
    assert excinfo.value.status_code == 400
    assert excinfo.value.debug_id == "dbg-400"


def test_create_order_5xx_raises_api_error():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json=TOKEN_BODY)
        return httpx.Response(
            500,
            json={"name": "INTERNAL_SERVER_ERROR"},
            headers={"PayPal-Debug-Id": "dbg-500"},
        )

    client = make_client(transport=httpx.MockTransport(handler))

    with pytest.raises(PayPalApiError) as excinfo:
        client.capture_order("ORDER-1")
    assert excinfo.value.status_code == 500
    assert excinfo.value.debug_id == "dbg-500"


# 7. Timeout -> PayPalTimeoutError
def test_timeout_raises_paypal_timeout_error():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json=TOKEN_BODY)
        raise httpx.ConnectTimeout("timed out", request=request)

    client = make_client(transport=httpx.MockTransport(handler))

    with pytest.raises(PayPalTimeoutError):
        client.create_order(purchase_units=[])


def test_token_timeout_raises_paypal_timeout_error():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    client = make_client(transport=httpx.MockTransport(handler))

    with pytest.raises(PayPalTimeoutError):
        client.get_access_token()


def test_connection_error_raises_ambiguous_error():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json=TOKEN_BODY)
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(transport=httpx.MockTransport(handler))

    with pytest.raises(PayPalAmbiguousError):
        client.capture_order("ORDER-1")


# 8. Amount strings pass through verbatim
def test_amount_strings_pass_through_verbatim():
    sent = []
    routes = {"/v2/checkout/orders": json_route(ORDER_BODY, 201, record=sent)}
    client = make_client(routes)

    client.create_order(
        purchase_units=[
            {
                "amount": {
                    "currency_code": "USD",
                    "value": "10.00",
                    "breakdown": {
                        "item_total": {"currency_code": "USD", "value": "9.50"},
                        "tax_total": {"currency_code": "USD", "value": "0.50"},
                    },
                }
            }
        ]
    )

    raw = json.loads(sent[0].content)
    amount = raw["purchase_units"][0]["amount"]
    assert amount["value"] == "10.00"
    assert isinstance(amount["value"], str)
    assert amount["breakdown"]["item_total"]["value"] == "9.50"
    assert isinstance(amount["breakdown"]["item_total"]["value"], str)
    # No float leakage anywhere in the serialized payload
    assert not re.search(rb'"value":\s*10\.0\b', sent[0].content)
