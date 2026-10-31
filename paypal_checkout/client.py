"""Synchronous PayPal Orders v2 sandbox client built on httpx.

Intended for use inside Flask request flows. Sandbox-only by design: the
client refuses to be pointed at the live api-m.paypal.com host.
"""

import time
import uuid

import httpx

from .errors import (
    PayPalAmbiguousError,
    PayPalApiError,
    PayPalAuthError,
    PayPalTimeoutError,
)

SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"
LIVE_HOST_FRAGMENT = "api-m.paypal.com"
TOKEN_EXPIRY_MARGIN_SECONDS = 60


def _require_sandbox(environment):
    if environment != "sandbox":
        raise ValueError(
            "PayPalClient is sandbox-only: environment must be 'sandbox', "
            f"got {environment!r}. Live endpoints are never allowed."
        )


def get_bearer_token(client_id, client_secret, environment="sandbox",
                     timeout=15.0, http_client=None):
    """One-shot OAuth client-credentials token fetch (sandbox only).

    Shared helper for callers that need a bare bearer token outside the
    Orders v2 flow (e.g. webhook signature verification). Raises the same
    typed errors as PayPalClient.
    """
    _require_sandbox(environment)
    client = http_client or httpx.Client(base_url=SANDBOX_BASE_URL, timeout=timeout)
    try:
        response = client.post(
            "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
        )
    except httpx.TimeoutException as exc:
        raise PayPalTimeoutError(f"Token request timed out: {exc}") from exc
    except httpx.TransportError as exc:
        raise PayPalAmbiguousError(f"Token request failed: {exc}") from exc
    finally:
        if http_client is None:
            client.close()
    if response.status_code >= 400:
        raise PayPalAuthError(
            "PayPal OAuth rejected the client credentials",
            status_code=response.status_code,
            debug_id=response.headers.get("PayPal-Debug-Id"),
        )
    return response.json()["access_token"]


class PayPalClient:
    """Synchronous PayPal Orders v2 client (sandbox environment only)."""

    def __init__(self, client_id, client_secret, environment="sandbox",
                 http_client=None, timeout=20.0):
        _require_sandbox(environment)
        self._client_id = client_id
        self._client_secret = client_secret
        self._environment = environment
        self._base_url = SANDBOX_BASE_URL
        self._timeout = timeout
        self._client = http_client or httpx.Client(
            base_url=self._base_url, timeout=timeout
        )
        self._access_token = None
        self._token_expires_at = 0.0
        self.last_request_id = None

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    def get_access_token(self):
        """Return a cached OAuth access token, refreshing it when expired.

        Caches the token with a 60s expiry margin. Raises PayPalAuthError on
        401 from the token endpoint.
        """
        now = time.monotonic()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        try:
            response = self._client.post(
                "/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException as exc:
            raise PayPalTimeoutError(f"Token request timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise PayPalAmbiguousError(
                f"Token request failed, remote state unknown: {exc}"
            ) from exc

        if response.status_code == 401:
            raise PayPalAuthError(
                "PayPal OAuth rejected the client credentials",
                status_code=response.status_code,
                debug_id=response.headers.get("PayPal-Debug-Id"),
            )
        if response.status_code >= 400:
            raise PayPalApiError(
                f"Token request failed with {response.status_code}",
                status_code=response.status_code,
                debug_id=response.headers.get("PayPal-Debug-Id"),
            )

        body = response.json()
        self._access_token = body["access_token"]
        expires_in = int(body.get("expires_in", 0))
        self._token_expires_at = now + max(expires_in - TOKEN_EXPIRY_MARGIN_SECONDS, 0)
        return self._access_token

    # ------------------------------------------------------------------
    # Orders v2
    # ------------------------------------------------------------------

    def create_order(self, intent="CAPTURE", purchase_units=None, request_id=None):
        """Create an order via POST /v2/checkout/orders.

        Sends a PayPal-Request-Id header for idempotency (a uuid4 is
        generated when request_id is not given) and asks PayPal for
        return=representation. The request id used is exposed on
        ``last_request_id``. Returns the parsed JSON order object.

        All money values inside purchase_units must be strings (e.g.
        "10.00") — they are passed through verbatim, never as floats.
        """
        payload = {"intent": intent, "purchase_units": purchase_units or []}
        return self._authed_request(
            "POST",
            "/v2/checkout/orders",
            request_id=request_id,
            json=payload,
            prefer_representation=True,
        )

    def get_order(self, order_id):
        """Fetch an order via GET /v2/checkout/orders/{order_id}."""
        return self._authed_request("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id, request_id=None):
        """Capture an approved order via POST /v2/checkout/orders/{id}/capture.

        Only call this after the payer has approved the order in the PayPal
        flow. Sends a PayPal-Request-Id header for idempotency; the id used
        is exposed on ``last_request_id``. If this raises
        PayPalAmbiguousError, reconcile via get_order before any retry —
        never blindly re-capture. Returns the parsed JSON response.
        """
        return self._authed_request(
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            request_id=request_id,
            json={},
            prefer_representation=True,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _authed_request(self, method, path, request_id=None, json=None,
                        prefer_representation=False):
        token = self.get_access_token()
        if request_id is None:
            request_id = str(uuid.uuid4())
        self.last_request_id = request_id

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,
        }
        if prefer_representation:
            headers["Prefer"] = "return=representation"

        try:
            response = self._client.request(
                method, path, json=json, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise PayPalTimeoutError(f"{method} {path} timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise PayPalAmbiguousError(
                f"{method} {path} failed, remote state unknown — reconcile "
                f"before retrying: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise PayPalApiError(
                f"{method} {path} failed with {response.status_code}",
                status_code=response.status_code,
                debug_id=response.headers.get("PayPal-Debug-Id"),
            )
        return response.json()

    def close(self):
        """Close the underlying httpx client."""
        self._client.close()
