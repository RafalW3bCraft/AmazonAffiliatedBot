"""DealPilot commerce blueprint: two-lane shop (merchant PayPal checkout +
external affiliate links), AI recommend API, cart quotes, PayPal
return/cancel, orders, merchant dashboard, and the PayPal webhook.

All heavy dependencies (commerce, ai, paypal_checkout) are imported lazily
inside the service factory with per-module try/except so this blueprint
imports cleanly while sibling packages are still being built; a missing lane
returns 503 on its endpoints, never a fake success.
"""
import collections.abc as _abc
import hashlib
import hmac
import json
import logging
import threading
import time
from urllib.parse import urlparse

import httpx
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from web import views as vm
from web.auth import (
    csrf_token,
    current_actor_id,
    ensure_actor,
    is_merchant,
    require_merchant,
    verify_csrf,
)

logger = logging.getLogger(__name__)

CATALOG_PATH = 'config/merchant_catalog.json'
MERCHANT_NAME = 'DealPilot Demo Merchant'

ALLOWED_WEBHOOK_EVENTS = {
    'PAYMENT.CAPTURE.COMPLETED',
    'PAYMENT.CAPTURE.PENDING',
    'PAYMENT.CAPTURE.DENIED',
    'CHECKOUT.ORDER.APPROVED',
}

PAYPAL_API_BASE = {
    'sandbox': 'https://api-m.sandbox.paypal.com',
}

# Exception names the commerce package defines; resolved lazily so the
# module imports even while commerce/ does not exist yet.
_COMMERCE_ERRORS = {}


def _commerce_exceptions():
    """Resolve commerce exception classes, falling back to the offline set."""
    if _COMMERCE_ERRORS:
        return _COMMERCE_ERRORS
    from web import catalog_data as offline
    names = [
        'QuoteNotFound', 'QuoteExpired', 'QuoteStale', 'QuoteNotOpen',
        'ForbiddenBuyer', 'NotApproved', 'AmountMismatch', 'CheckoutError',
        'AmbiguousCheckoutError',
    ]
    try:
        import commerce.exceptions as ce  # type: ignore
        for n in names:
            _COMMERCE_ERRORS[n] = getattr(ce, n, getattr(offline, n))
    except Exception:
        for n in names:
            _COMMERCE_ERRORS[n] = getattr(offline, n)
    return _COMMERCE_ERRORS


def _err(name):
    return _commerce_exceptions()[name]


class _CartErrorBase(Exception):
    pass


def _cart_errors():
    """Real commerce CartError classes (400-worthy) + fallback ValueError."""
    try:
        from commerce.exceptions import CartError, PolicyError  # type: ignore
        return (CartError, PolicyError)
    except Exception:
        return (ValueError,)


def _get(obj, name, default=None):
    """Attribute/key access that never resolves dict methods (e.g. 'items')."""
    if isinstance(obj, _abc.Mapping):
        return obj[name] if name in obj else default
    return getattr(obj, name, default)


def _storage_supports(storage, style):
    """Probe the real CommerceStorage signature style for get_attempt etc."""
    import inspect
    try:
        params = inspect.signature(storage.get_attempt).parameters
        return style in params
    except (TypeError, ValueError):
        return False


def _fetch_attempt(storage, key):
    """Fetch an attempt by attempt_id(pk), request_id, or paypal_order_id,
    adapting to both the real CommerceStorage (keyword style) and the
    offline InMemoryCommerceStorage (single-key style). Returns a plain dict."""
    attempt = None
    if _storage_supports(storage, 'paypal_order_id'):
        try:
            attempt = storage.get_attempt(paypal_order_id=key)
        except Exception:
            attempt = None
        if attempt is None:
            try:
                attempt = storage.get_attempt(attempt_id=int(key))
            except (TypeError, ValueError):
                attempt = None
            except Exception:
                attempt = None
        if attempt is None:
            try:
                attempt = storage.get_attempt(request_id=key)
            except Exception:
                attempt = None
    else:
        try:
            attempt = storage.get_attempt(key)
        except Exception:
            attempt = None
    return _row_to_attempt_dict(attempt)


def _row_to_attempt_dict(attempt):
    """Normalize any attempt representation (ORM row / dict / object) to a
    plain dict with attempt_id (int pk), buyer_id, status, timestamps."""
    if attempt is None:
        return None
    if isinstance(attempt, dict):
        d = dict(attempt)
        if 'attempt_id' not in d and 'id' in d:
            d['attempt_id'] = d['id']
        return d
    return {
        'attempt_id': _get(attempt, 'id'),
        'buyer_id': _get(attempt, 'buyer_id', ''),
        'request_id': _get(attempt, 'request_id', ''),
        'paypal_order_id': _get(attempt, 'paypal_order_id'),
        'status': _get(attempt, 'status', ''),
        'created_at': _get(attempt, 'created_at'),
        'updated_at': _get(attempt, 'updated_at'),
    }


def _fetch_capture(storage, attempt_pk):
    """Capture row for an attempt across storage variants -> plain dict."""
    try:
        if hasattr(storage, 'get_capture_for_attempt'):
            cap = storage.get_capture_for_attempt(attempt_pk)
        else:
            cap = storage.get_capture(attempt_id=attempt_pk)
    except Exception:
        cap = None
    if cap is None:
        return None
    if isinstance(cap, dict):
        return dict(cap)
    return {
        'paypal_capture_id': _get(cap, 'paypal_capture_id', ''),
        'amount': _get(cap, 'amount'),
        'currency': _get(cap, 'currency', ''),
        'status': _get(cap, 'status', ''),
        'verified_at': _get(cap, 'verified_at'),
    }


def _quote_to_dict(storage, quote_id):
    """Load a quote as a plain dict regardless of storage row type."""
    row = storage.get_quote(quote_id)
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    if hasattr(storage, 'quote_to_data'):
        try:
            data = storage.quote_to_data(row)
            if hasattr(data, 'model_dump'):
                return data.model_dump()
        except Exception:
            pass
    if hasattr(row, 'model_dump'):
        return row.model_dump()
    # ORM row fallback
    items = _get(row, 'items_json', []) or []
    if isinstance(items, str):
        items = json.loads(items)
    return {
        'quote_id': _get(row, 'quote_id'),
        'actor_id': _get(row, 'actor_id', ''),
        'currency': _get(row, 'currency', 'USD'),
        'items': items,
        'total': _get(row, 'total'),
        'status': _get(row, 'status', 'OPEN'),
        'expires_at': _get(row, 'expires_at'),
    }


class _RateBucket:
    """Simple in-process fixed-window rate limiter (per actor)."""

    def __init__(self, limit_per_minute=20):
        self.limit = limit_per_minute
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.time()
        with self._lock:
            window = [t for t in self._hits.get(key, []) if now - t < 60]
            if len(window) >= self.limit:
                self._hits[key] = window
                return False
            window.append(now)
            self._hits[key] = window
            return True


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------

def _build_services(config):
    """Create/cache lane services on current_app.extensions['dealpilot'].
    Each lane is independent; failures log and disable only that lane."""
    app = current_app
    ext = app.extensions.setdefault('dealpilot', {})
    if ext.get('services_built'):
        return ext
    ext['config'] = config

    # Catalog lane
    catalog = None
    try:
        from commerce.catalog import Catalog  # type: ignore
        catalog = Catalog(CATALOG_PATH)
        logger.info('DealPilot: commerce.catalog.Catalog loaded')
    except Exception as e:
        logger.warning(f'DealPilot: commerce.catalog unavailable ({e}); using offline catalog')
        try:
            from web.catalog_data import SimpleCatalog
            catalog = SimpleCatalog(CATALOG_PATH)
        except Exception as e2:
            logger.error(f'DealPilot: offline catalog also failed: {e2}')
            catalog = None
    ext['catalog'] = catalog

    # Storage lane. Payment records must be durable: when checkout is possible
    # (PayPal creds configured and merchant checkout enabled) a storage failure
    # disables checkout entirely rather than falling back to process-local
    # memory. In-memory storage is permitted ONLY when checkout can never run
    # (DEMO_MODE, checkout disabled, or no PayPal credentials) so the demo UI
    # and deterministic-AI pages still work offline.
    storage = getattr(app, 'commerce_storage', None)
    if storage is None:
        checkout_configured = bool(
            getattr(config, 'ENABLE_MERCHANT_CHECKOUT', True)
            and getattr(config, 'PAYPAL_CLIENT_ID', '')
            and getattr(config, 'PAYPAL_CLIENT_SECRET', '')
            and not getattr(config, 'DEMO_MODE', False)
        )
        try:
            from commerce.storage import CommerceStorage  # type: ignore
            storage = CommerceStorage(config.COMMERCE_DATABASE_URL)
            logger.info('DealPilot: commerce.storage.CommerceStorage ready')
        except Exception as e:
            if checkout_configured:
                logger.error(
                    f'DealPilot: durable storage unavailable ({e}) and checkout '
                    'is configured - REFUSING in-memory payment storage; '
                    'checkout lane disabled (catalog/AI lanes unaffected)'
                )
                storage = None
            else:
                logger.warning(
                    f'DealPilot: commerce.storage unavailable ({e}); using '
                    'in-memory storage (checkout not configured, demo only)'
                )
                from web.catalog_data import InMemoryCommerceStorage
                storage = InMemoryCommerceStorage(config.COMMERCE_DATABASE_URL)
        if storage is not None:
            try:
                app.commerce_storage = storage
            except Exception:
                pass
    ext['storage'] = storage
    # Durability gate: payment records must never live in process memory when
    # checkout is possible. In-memory storage is acceptable only while checkout
    # is unconfigured (demo/catalog browsing). Detect it structurally so this
    # holds regardless of which storage class was imported.
    if storage is not None:
        from web.catalog_data import InMemoryCommerceStorage as _IM
        if isinstance(storage, _IM):
            ext['storage_durable'] = False
        else:
            ext['storage_durable'] = True
    else:
        ext['storage_durable'] = False

    if catalog is not None and storage is not None:
        try:
            storage.upsert_products(catalog.list_products(active_only=False))
        except Exception as e:
            logger.warning(f'DealPilot: upsert_products failed (non-fatal): {e}')

    # Cart lane
    cart_service = None
    if catalog is not None and storage is not None:
        try:
            from commerce.cart_service import CartService  # type: ignore
            cart_service = CartService(catalog, storage, config)
            logger.info('DealPilot: commerce.cart_service.CartService loaded')
        except Exception as e:
            logger.warning(f'DealPilot: commerce.cart_service unavailable ({e}); using offline cart')
            from web.catalog_data import SimpleCartService
            cart_service = SimpleCartService(catalog, storage, config)
    ext['cart_service'] = cart_service

    # AI lane
    ai_service = None
    if catalog is not None:
        try:
            from ai.agent import AIShoppingService  # type: ignore
            ai_service = AIShoppingService(config, catalog)
            logger.info('DealPilot: ai.agent.AIShoppingService loaded')
        except Exception as e:
            logger.warning(f'DealPilot: ai.agent unavailable ({e}); using deterministic fallback')
            from web.catalog_data import DeterministicAI
            ai_service = DeterministicAI(config, catalog)
    ext['ai_service'] = ai_service

    # PayPal + checkout lane
    paypal_client = None
    if getattr(config, 'PAYPAL_CLIENT_ID', '') and getattr(config, 'PAYPAL_CLIENT_SECRET', ''):
        try:
            from paypal_checkout.client import PayPalClient  # type: ignore
            paypal_client = PayPalClient(
                config.PAYPAL_CLIENT_ID,
                config.PAYPAL_CLIENT_SECRET,
                environment=getattr(config, 'PAYPAL_ENVIRONMENT', 'sandbox') or 'sandbox',
            )
            logger.info('DealPilot: PayPal sandbox client configured')
        except Exception as e:
            logger.error(f'DealPilot: PayPal client init failed ({e}); checkout lane disabled')
            paypal_client = None
    ext['paypal_client'] = paypal_client

    # Token getter for webhook verification: reuse the PayPal client when
    # available, otherwise mint a bare OAuth token via the shared httpx
    # helper (tests monkeypatch this).
    def _token_getter():
        client = ext.get('paypal_client')
        if client is not None and hasattr(client, 'get_access_token'):
            return client.get_access_token()
        from paypal_checkout.client import get_bearer_token  # type: ignore
        return get_bearer_token(
            config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET,
            environment=getattr(config, 'PAYPAL_ENVIRONMENT', 'sandbox') or 'sandbox',
        )
    ext['token_getter'] = _token_getter

    checkout_service = None
    # Payment-critical gate: checkout runs ONLY on durable storage. If storage
    # is in-memory (or missing) while PayPal is configured, refuse to build the
    # checkout service — /checkout/start will return 503 instead of recording
    # payment state in process memory.
    if not ext.get('storage_durable', False):
        if paypal_client is not None:
            logger.error(
                'DealPilot: PayPal is configured but storage is not durable - '
                'checkout lane disabled (set COMMERCE_DATABASE_URL to a '
                'persistent postgresql:// or sqlite:/// URL)'
            )
    elif ext['cart_service'] is not None and paypal_client is not None:
        try:
            from commerce.checkout_service import CheckoutService  # type: ignore
            checkout_service = CheckoutService(storage, ext['cart_service'], paypal_client, config)
            logger.info('DealPilot: commerce.checkout_service.CheckoutService loaded')
        except Exception as e:
            logger.error(f'DealPilot: CheckoutService unavailable ({e}); checkout lane disabled')
            checkout_service = None
    ext['checkout_service'] = checkout_service

    ext['rate_bucket'] = _RateBucket(limit_per_minute=20)
    ext['services_built'] = True
    return ext


def _services():
    return current_app.extensions.get('dealpilot', {})


def _lane_unavailable(lane):
    return jsonify({'error': f'{lane} unavailable', 'detail': f'{lane} lane is not configured'}), 503


def _wants_json():
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept or request.is_json


def _quote_to_vm(quote):
    """Normalize a quote (pydantic object, dataclass, or dict) to a view model."""
    if isinstance(quote, dict):
        quote = dict(quote)
    elif hasattr(quote, 'model_dump'):
        quote = quote.model_dump()
    return vm.quote_vm(quote)


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def _cert_url_ok(cert_url):
    """SSRF guard: only https URLs on a *.paypal.com host are acceptable.
    We never fetch the cert ourselves - PayPal's verify endpoint does."""
    try:
        parsed = urlparse(str(cert_url))
    except Exception:
        return False
    if parsed.scheme != 'https':
        return False
    host = (parsed.hostname or '').lower()
    return host == 'paypal.com' or host.endswith('.paypal.com')


def _paypal_base(config):
    env = (getattr(config, 'PAYPAL_ENVIRONMENT', 'sandbox') or 'sandbox').lower()
    return PAYPAL_API_BASE.get(env, PAYPAL_API_BASE['sandbox'])


def _verify_webhook_signature(config, headers, raw_body):
    """Official PayPal verification: POST verify-webhook-signature with the
    transmission metadata. Returns True only on verification_status SUCCESS.
    Raises ValueError on unconfigured/garbage input (caller -> 400/503)."""
    webhook_id = getattr(config, 'PAYPAL_WEBHOOK_ID', '') or ''
    if not webhook_id:
        raise RuntimeError('PAYPAL_WEBHOOK_ID not configured')
    required = [
        'PAYPAL-TRANSMISSION-ID', 'PAYPAL-TRANSMISSION-TIME',
        'PAYPAL-TRANSMISSION-SIG', 'PAYPAL-CERT-URL', 'PAYPAL-AUTH-ALGO',
    ]
    missing = [h for h in required if not headers.get(h)]
    if missing:
        logger.info('PayPal webhook rejected: missing transmission headers')
        raise ValueError('missing signature headers')
    cert_url = headers.get('PAYPAL-CERT-URL', '')
    if not _cert_url_ok(cert_url):
        logger.warning('PayPal webhook rejected: cert_url failed SSRF guard')
        raise ValueError('cert_url rejected')

    token_getter = _services().get('token_getter')
    try:
        if token_getter is not None:
            token = token_getter()
        else:
            token = None
    except Exception as e:
        logger.error(f'PayPal webhook: token fetch failed: {e}')
        raise RuntimeError('webhook verification unavailable')

    if token is None:
        # Credentials absent: cannot verify - treat as unconfigured.
        raise RuntimeError('webhook verification unavailable (no PayPal credentials)')

    payload = {
        'auth_algo': headers.get('PAYPAL-AUTH-ALGO'),
        'cert_url': cert_url,
        'transmission_id': headers.get('PAYPAL-TRANSMISSION-ID'),
        'transmission_time': headers.get('PAYPAL-TRANSMISSION-TIME'),
        'transmission_sig': headers.get('PAYPAL-TRANSMISSION-SIG'),
        'webhook_id': webhook_id,
        'webhook_event': json.loads(raw_body.decode('utf-8')),
    }
    resp = httpx.post(
        f'{_paypal_base(config)}/v1/notifications/verify-webhook-signature',
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error(f'PayPal webhook verify HTTP {resp.status_code}')
        return False
    status = (resp.json() or {}).get('verification_status')
    return status == 'SUCCESS'


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

def create_commerce_blueprint(config):
    bp = Blueprint('commerce', __name__)

    @bp.before_app_request
    def _ensure_services():
        _build_services(config)

    @bp.app_context_processor
    def _inject_template_globals():
        return {
            'csrf_token': csrf_token(),
            'demo_mode': bool(getattr(config, 'DEMO_MODE', False)),
            'merchant_name': MERCHANT_NAME,
        }

    # -- public pages ------------------------------------------------------

    @bp.route('/shop')
    def shop():
        svc = _services()
        catalog = svc.get('catalog')
        lang = request.args.get('lang', 'en')
        labels = vm.labels_for(lang)
        products = []
        if catalog is not None:
            try:
                products = [vm.product_card(p) for p in catalog.list_products()]
            except Exception as e:
                logger.error(f'/shop catalog error: {e}')
        return render_template(
            'shop.html', products=products, labels=labels, lang=lang,
            ai_enabled=svc.get('ai_service') is not None,
            affiliate_enabled=bool(getattr(config, 'ENABLE_EXTERNAL_AFFILIATE', False)),
        )

    @bp.route('/api/catalog')
    def api_catalog():
        catalog = _services().get('catalog')
        if catalog is None:
            return _lane_unavailable('catalog')
        try:
            return jsonify([vm.product_card(p) for p in catalog.list_products()])
        except Exception as e:
            logger.error(f'/api/catalog error: {e}')
            return _lane_unavailable('catalog')

    @bp.route('/api/csrf')
    def api_csrf():
        return jsonify({'csrf_token': csrf_token()})

    # -- AI recommend --------------------------------------------------------

    @bp.route('/api/ai/recommend', methods=['POST'])
    def ai_recommend():
        if not verify_csrf():
            return jsonify({'error': 'invalid or missing CSRF token'}), 403
        svc = _services()
        actor = ensure_actor()
        if not svc.get('rate_bucket', _RateBucket()).allow(actor + ':ai'):
            return jsonify({'error': 'rate limit exceeded'}), 429
        ai = svc.get('ai_service')
        if ai is None:
            return _lane_unavailable('ai')
        data = request.get_json(silent=True) or {}
        query = str(data.get('query', ''))[:500]
        locale = str(data.get('locale', request.args.get('lang', 'en')))[:8]
        budget = data.get('budget')
        try:
            rec = ai.recommend(query, locale=locale, budget_hint=budget, actor_id=actor)
        except Exception as e:
            logger.error(f'AI recommend failed: {e}')
            return jsonify({'error': 'recommendation unavailable'}), 503
        if hasattr(rec, 'model_dump'):
            rec = rec.model_dump()
        rec = dict(rec or {})
        fallback = bool(rec.get('fallback'))
        out = {
            'items': [
                {
                    'sku': str(i.get('sku', '')),
                    'reason': str(i.get('reason', '')),
                    'price': vm.money_str(i.get('price', '0')),
                    'currency': str(i.get('currency', 'USD')),
                }
                for i in (rec.get('items') or [])[:4]
            ],
            'tradeoffs': str(rec.get('tradeoffs', '')),
            'missing_info': [str(m) for m in (rec.get('missing_info') or [])],
            'cart_proposal': [
                {'sku': str(i.get('sku', '')), 'quantity': int(i.get('quantity', 1) or 1)}
                for i in (rec.get('cart_proposal') or [])
            ],
            'confidence': str(rec.get('confidence', 'low')),
            'provider': str(rec.get('provider', '')),
            'fallback': fallback,
        }
        if fallback:
            out['ai_disclaimer'] = 'deterministic ranking, not AI'
        # Redacted agent session record (input hash only, no raw query).
        storage = svc.get('storage')
        if storage is not None and hasattr(storage, 'record_agent_session'):
            try:
                storage.record_agent_session(
                    actor_id=actor,
                    model=out['provider'],
                    input_hash=hashlib.sha256(query.encode()).hexdigest(),
                    output_redacted=json.dumps({'skus': [i['sku'] for i in out['items']]}),
                )
            except Exception as e:
                logger.debug(f'agent session record failed: {e}')
        return jsonify(out)

    # -- cart / quote -------------------------------------------------------

    @bp.route('/cart/quote', methods=['POST'])
    def cart_quote():
        if not verify_csrf():
            return jsonify({'error': 'invalid or missing CSRF token'}), 403
        svc = _services()
        cart = svc.get('cart_service')
        if cart is None:
            return _lane_unavailable('cart')
        actor = ensure_actor()
        data = request.get_json(silent=True) or {}
        items = data.get('items') or []
        # Only sku+quantity are honored; any client-sent price is discarded.
        clean = []
        for it in items[:10]:
            if not isinstance(it, dict):
                continue
            try:
                clean.append({'sku': str(it.get('sku', '')), 'quantity': int(it.get('quantity', 1))})
            except (TypeError, ValueError):
                continue
        cart_errors = _cart_errors()
        if cart_errors != (ValueError,):
            try:
                from commerce.schemas import CartItem  # type: ignore
                cart_items = [CartItem(sku=i['sku'], quantity=i['quantity']) for i in clean]
            except Exception:
                cart_items = clean
        else:
            cart_items = clean
        try:
            quote = cart.create_quote(actor, cart_items)
        except cart_errors as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.error(f'quote creation failed: {e}')
            return jsonify({'error': 'could not create quote'}), 500
        if hasattr(quote, 'model_dump'):
            quote_id = quote.model_dump().get('quote_id')
        elif isinstance(quote, dict):
            quote_id = quote.get('quote_id')
        else:
            quote_id = getattr(quote, 'quote_id', None)
        if _wants_json():
            return jsonify({'quote_id': quote_id, 'redirect': url_for('commerce.cart', quote_id=quote_id)})
        return redirect(url_for('commerce.cart', quote_id=quote_id))

    @bp.route('/cart')
    def cart():
        svc = _services()
        cart_svc = svc.get('cart_service')
        quote_id = request.args.get('quote_id', '')
        quote = None
        error = None
        if quote_id and cart_svc is not None:
            try:
                raw = _quote_to_dict(svc['storage'], quote_id) if svc.get('storage') else None
                if raw is None:
                    raise _err('QuoteNotFound')(quote_id)
                quote = _quote_to_vm(raw)
                # expiry check for display
                try:
                    cart_svc.validate_quote(quote_id)
                    quote['expired'] = False
                except _err('QuoteExpired'):
                    quote['expired'] = True
                except Exception:
                    quote['expired'] = False
            except _err('QuoteNotFound'):
                error = 'Quote not found.'
            except Exception as e:
                logger.error(f'/cart error: {e}')
                error = 'Could not load quote.'
        return render_template(
            'cart.html', quote=quote, error=error,
            labels=vm.labels_for(request.args.get('lang', 'en')),
            fulfillment=vm.FULFILLMENT_TEXT,
            message=request.args.get('message', ''),
        )

    # -- checkout ------------------------------------------------------------

    @bp.route('/checkout/start', methods=['POST'])
    def checkout_start():
        if not verify_csrf():
            return jsonify({'error': 'invalid or missing CSRF token'}), 403
        svc = _services()
        actor = ensure_actor()
        if not svc.get('rate_bucket', _RateBucket()).allow(actor + ':checkout'):
            return jsonify({'error': 'rate limit exceeded'}), 429
        checkout = svc.get('checkout_service')
        if checkout is None:
            # Never fake a checkout: PayPal creds/service missing -> 503.
            return jsonify({
                'error': 'checkout unavailable',
                'detail': 'PayPal sandbox is not configured on this server',
            }), 503
        data = request.get_json(silent=True) or {}
        quote_id = str(data.get('quote_id', ''))
        if not quote_id:
            return jsonify({'error': 'quote_id required'}), 400
        try:
            result = checkout.start_checkout(actor, quote_id, buyer_id=actor)
        except _err('QuoteNotFound'):
            return jsonify({'error': 'quote not found'}), 404
        except _err('QuoteExpired'):
            return jsonify({'error': 'quote expired'}), 410
        except _err('QuoteStale'):
            return jsonify({'error': 'quote is stale; refresh your cart'}), 409
        except _err('AmbiguousCheckoutError'):
            return jsonify({'error': 'checkout state ambiguous; merchant will reconcile'}), 202
        except _err('CheckoutError') as e:
            return jsonify({'error': f'checkout failed: {e}'}), 502
        except Exception as e:
            logger.error(f'checkout_start unexpected: {e}')
            return jsonify({'error': 'checkout failed'}), 500
        return jsonify({
            'approve_url': result.get('approve_url'),
            'attempt_id': result.get('attempt_id'),
        })

    @bp.route('/checkout')
    def checkout_page():
        return render_template('checkout.html', quote_id=request.args.get('quote_id', ''))

    # -- PayPal return / cancel ----------------------------------------------

    @bp.route('/paypal/return')
    def paypal_return():
        svc = _services()
        token = request.args.get('token', '')  # PayPal order id
        if not token:
            return redirect(url_for('commerce.cart', message='Missing PayPal order token.'))
        storage = svc.get('storage')
        checkout = svc.get('checkout_service')
        attempt = _fetch_attempt(storage, token) if storage is not None else None
        if attempt is None:
            logger.info(f'/paypal/return unknown token (no state change): {token[:8]}…')
            return redirect(url_for('commerce.cart', message='Unknown or expired PayPal order.'))
        attempt_id = attempt['attempt_id']
        if checkout is None:
            return redirect(url_for('commerce.order_status', attempt_id=attempt_id))
        buyer = current_actor_id()
        try:
            result = checkout.capture_after_approval(buyer, attempt_id, buyer_id=buyer)
        except _err('ForbiddenBuyer'):
            return redirect(url_for('commerce.cart', message='This order belongs to a different session.'))
        except _err('NotApproved'):
            return redirect(url_for('commerce.cart', message='Payment was not approved at PayPal.'))
        except _err('AmountMismatch'):
            logger.error(f'/paypal/return amount mismatch attempt={attempt_id}')
            return redirect(url_for('commerce.order_status', attempt_id=attempt_id))
        except Exception as e:
            logger.error(f'/paypal/return capture error: {e}')
            return redirect(url_for('commerce.order_status', attempt_id=attempt_id))
        status = str((result or {}).get('status', ''))
        if status == 'PAID':
            return redirect(url_for('commerce.order_status', attempt_id=attempt_id, receipt='1'))
        if status in ('CAPTURE_PENDING', 'PENDING'):
            aid = str(attempt_id or '')
            return render_template('order_status.html', order={
                'attempt_id': aid, 'masked_id': aid[-6:],
                'status': 'CAPTURE_PENDING', 'status_label': 'Capture pending',
                'is_final': False, 'amount': '', 'currency': '', 'capture_id': '',
                'verified': False, 'verified_at': '', 'created_at': '', 'updated_at': '',
                'sandbox_note': vm.SANDBOX_RECEIPT_NOTE,
            }, pending=True)
        return redirect(url_for('commerce.order_status', attempt_id=attempt_id))

    @bp.route('/paypal/cancel')
    def paypal_cancel():
        svc = _services()
        storage = svc.get('storage')
        token = request.args.get('token', '')
        if storage is not None and token:
            try:
                attempt = _fetch_attempt(storage, token)
                if attempt:
                    storage.set_attempt_status(attempt['attempt_id'], 'CANCELED')
            except Exception as e:
                logger.warning(f'/paypal/cancel state update failed: {e}')
        return redirect(url_for('commerce.cart', message='Checkout canceled.'))

    # -- orders ----------------------------------------------------------------

    def _load_attempt(attempt_id):
        storage = _services().get('storage')
        if storage is None:
            return None, None
        attempt = _fetch_attempt(storage, str(attempt_id))
        capture = None
        if attempt is not None:
            capture = _fetch_capture(storage, attempt['attempt_id'])
            if capture is None:
                capture = attempt.get('capture')
        return attempt, capture

    def _can_view(attempt):
        if is_merchant(config):
            return True
        owner = str(attempt.get('buyer_id', ''))
        return bool(owner) and hmac.compare_digest(owner, str(current_actor_id()))

    @bp.route('/orders/<attempt_id>')
    def order_status(attempt_id):
        attempt, capture = _load_attempt(attempt_id)
        if attempt is None:
            return jsonify({'error': 'order not found'}), 404
        if not _can_view(attempt):
            return jsonify({'error': 'order not found'}), 404
        order = vm.order_vm(attempt, capture)
        receipt = request.args.get('receipt') == '1'
        return render_template('order_status.html', order=order, receipt=receipt, pending=False)

    @bp.route('/orders/<attempt_id>/status.json')
    def order_status_json(attempt_id):
        svc = _services()
        attempt, capture = _load_attempt(attempt_id)
        if attempt is None:
            return jsonify({'error': 'order not found'}), 404
        if not _can_view(attempt):
            return jsonify({'error': 'order not found'}), 404
        if attempt.get('status') not in ('PAID', 'FAILED', 'CANCELED'):
            checkout = svc.get('checkout_service')
            if checkout is not None:
                try:
                    checkout.reconcile(attempt['attempt_id'])  # bounded self-heal
                    attempt, capture = _load_attempt(attempt_id)
                except Exception as e:
                    logger.warning(f'reconcile failed for {attempt_id}: {e}')
        return jsonify(vm.order_vm(attempt, capture))

    # -- merchant dashboard -----------------------------------------------------

    @bp.route('/merchant')
    @require_merchant
    def merchant():
        svc = _services()
        storage = svc.get('storage')
        orders, raw_stats, sessions = [], {}, []
        if storage is not None:
            try:
                for row in storage.list_orders(limit=100):
                    d = _row_to_attempt_dict(row)
                    if d is None:
                        continue
                    capture = d.pop('capture', None) or _fetch_capture(storage, d.get('attempt_id'))
                    orders.append(vm.order_vm(d, capture))
            except Exception as e:
                logger.error(f'/merchant list_orders error: {e}')
            try:
                raw_stats = storage.funnel_stats() or {}
            except Exception as e:
                logger.error(f'/merchant funnel_stats error: {e}')
                raw_stats = {}
            try:
                if hasattr(storage, 'list_agent_sessions'):
                    for s in storage.list_agent_sessions(limit=20):
                        sessions.append({
                            'actor_id': str(s.get('actor_id', ''))[:8] + '…',
                            'model': str(s.get('model', '')),
                            'input_hash': str(s.get('input_hash', ''))[:12] + '…',
                            'created_at': vm.iso(s.get('created_at')),
                        })
            except Exception as e:
                logger.debug(f'/merchant agent sessions error: {e}')
        # Normalize funnel shapes (real storage vs offline storage).
        by_status = raw_stats.get('by_status') or raw_stats.get('attempts_by_status') or {}
        gmv = raw_stats.get('paid_gmv')
        if gmv is None:
            gmv = vm.money_str(raw_stats.get('verified_capture_total', '0'))
        abandoned = raw_stats.get('abandoned_carts')
        if abandoned is None:
            abandoned = by_status.get('AWAITING_BUYER_APPROVAL', 0) + by_status.get('ORDER_CREATED', 0)
        stats = {
            'by_status': by_status,
            'paid_gmv': gmv,
            'currency': raw_stats.get('currency', getattr(config, 'PAYPAL_CURRENCY', 'USD')),
            'abandoned_carts': abandoned,
        }
        return render_template(
            'merchant.html', orders=orders, stats=stats, gmv=gmv,
            sessions=sessions, by_status_items=list(by_status.items()),
            fulfillment=vm.FULFILLMENT_TEXT,
            sandbox_note=vm.SANDBOX_RECEIPT_NOTE,
        )

    # -- PayPal webhook ------------------------------------------------------------

    @bp.route('/webhooks/paypal', methods=['POST'])
    def paypal_webhook():
        svc = _services()
        webhook_id = getattr(config, 'PAYPAL_WEBHOOK_ID', '') or ''
        creds_ok = bool(
            (getattr(config, 'PAYPAL_CLIENT_ID', '') and getattr(config, 'PAYPAL_CLIENT_SECRET', ''))
            or svc.get('paypal_client') is not None
        )
        if not webhook_id or not creds_ok:
            return jsonify({'error': 'webhook not configured'}), 503
        raw_body = request.get_data(cache=True)
        try:
            event = json.loads(raw_body.decode('utf-8'))
        except Exception:
            return jsonify({'error': 'invalid JSON body'}), 400
        event_id = str(event.get('id', ''))[:128]
        event_type = str(event.get('event_type', ''))[:64]
        # SSRF guard runs before any outbound call.
        try:
            ok = _verify_webhook_signature(config, request.headers, raw_body)
        except ValueError as e:
            logger.info(f'webhook rejected event={event_id} type={event_type}: {e}')
            return jsonify({'error': str(e)}), 400
        except RuntimeError as e:
            logger.error(f'webhook verification unavailable: {e}')
            return jsonify({'error': 'webhook verification unavailable'}), 503
        if not ok:
            logger.info(f'webhook bad signature event={event_id} type={event_type}')
            return jsonify({'error': 'signature verification failed'}), 400
        if event_type not in ALLOWED_WEBHOOK_EVENTS:
            logger.info(f'webhook ignored unknown type={event_type} id={event_id}')
            return jsonify({'ignored': True}), 200
        storage = svc.get('storage')
        if storage is None:
            return jsonify({'error': 'storage unavailable'}), 503
        is_new = storage.record_event(
            event_id, event_type=event_type,
            verification_result='SUCCESS', processing_state='RECEIVED',
        )
        if not is_new:
            return jsonify({'duplicate': True}), 200
        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            checkout = svc.get('checkout_service')
            if checkout is not None:
                try:
                    resource = event.get('resource', {}) or {}
                    # capture resource links back to the order via supplementary_data
                    order_id = (
                        (resource.get('supplementary_data', {}) or {})
                        .get('related_ids', {}) or {}
                    ).get('order_id') or resource.get('id', '')
                    attempt = _fetch_attempt(storage, order_id) if order_id else None
                    if attempt is not None:
                        checkout.reconcile(attempt['attempt_id'])
                except Exception as e:
                    # Handled: never 5xx a verified webhook over reconcile.
                    logger.error(f'webhook reconcile failed event={event_id}: {e}')
        return jsonify({'received': True}), 200

    return bp
