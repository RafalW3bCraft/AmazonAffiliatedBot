"""Offline merchant-owned demo catalog + services fallback.

Used only when the `commerce`/`ai` packages (built in parallel workstreams)
are not importable, so the web layer stays fully functional: pages, quotes,
deterministic AI-fallback recommendations. Prices here mirror
config/merchant_catalog.json; the real Catalog re-reads that file when the
commerce package is present.
"""
import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

logger = logging.getLogger(__name__)


class QuoteNotFound(Exception):
    pass


class QuoteExpired(Exception):
    pass


class QuoteStale(Exception):
    pass


class QuoteNotOpen(Exception):
    pass


class ForbiddenBuyer(Exception):
    pass


class NotApproved(Exception):
    pass


class AmountMismatch(Exception):
    pass


class CheckoutError(Exception):
    pass


class AmbiguousCheckoutError(CheckoutError):
    pass


@dataclass
class SimpleProduct:
    sku: str
    title: str
    description: str
    price: Decimal
    currency: str = 'USD'
    stock: int = 0
    category: str = ''
    version: int = 1
    source: str = 'MERCHANT'
    rights_evidence: str = 'original copy authored for hackathon demo, 2026-10'
    active: bool = True


_ASIN_RE = re.compile(r'^B0[A-Z0-9]{8}$')


class SimpleCatalog:
    """Loads config/merchant_catalog.json with defensive guards."""

    def __init__(self, path):
        self._path = Path(path)
        self._products = []
        self._load()

    def _load(self):
        try:
            raw = json.loads(self._path.read_text())
            entries = raw.get('products', raw if isinstance(raw, list) else [])
        except Exception as e:
            logger.error(f'SimpleCatalog: failed to load {self._path}: {e}')
            entries = []
        for e in entries:
            try:
                sku = str(e.get('sku', ''))
                if e.get('source', 'MERCHANT') != 'MERCHANT':
                    continue
                if _ASIN_RE.match(sku):
                    continue  # defensive: Amazon ASINs never enter checkout
                self._products.append(SimpleProduct(
                    sku=sku,
                    title=str(e.get('title', '')),
                    description=str(e.get('description', '')),
                    price=Decimal(str(e.get('price', '0'))),
                    currency=str(e.get('currency', 'USD')),
                    stock=int(e.get('stock', 0)),
                    category=str(e.get('category', '')),
                    version=int(e.get('version', 1)),
                    active=bool(e.get('active', True)),
                ))
            except Exception as ex:
                logger.warning(f'SimpleCatalog: skipping bad entry: {ex}')

    def list_products(self, active_only=True):
        return [p for p in self._products if (p.active or not active_only)]

    def get_product(self, sku):
        for p in self._products:
            if p.sku == sku:
                return p
        return None

    def search_products(self, query=None, category=None, budget_max=None, limit=8):
        results = []
        q = (query or '').strip().lower()
        for p in self.list_products():
            if category and p.category.lower() != str(category).lower():
                continue
            if budget_max is not None and p.price > Decimal(str(budget_max)):
                continue
            if q:
                hay = f'{p.title} {p.description} {p.category}'.lower()
                if q not in hay and not any(tok in hay for tok in q.split()):
                    continue
            results.append(p)
        results.sort(key=lambda p: (p.price, p.sku))
        return results[:limit]


class InMemoryCommerceStorage:
    """Process-local fallback storage used only when commerce.storage is
    absent. Warns loudly: payment rows here are not durable."""

    def __init__(self, url='memory'):
        self._lock = threading.RLock()
        self.quotes = {}
        self.attempts = {}
        self.captures = {}
        self.events = {}
        self.agent_sessions = []
        self._counter = 0
        logger.warning('InMemoryCommerceStorage in use - checkout rows are process-local')

    def ready(self):
        return True

    def upsert_products(self, products):
        return len(products)

    def create_quote(self, quote):
        with self._lock:
            row = dict(quote)
            row['id'] = self._next_id()
            self.quotes[quote['quote_id']] = row
            return dict(row)

    def get_quote(self, quote_id):
        q = self.quotes.get(quote_id)
        return dict(q) if q else None

    def update_quote_status(self, quote_id, status):
        with self._lock:
            if quote_id in self.quotes:
                self.quotes[quote_id]['status'] = status

    def _next_id(self):
        with self._lock:
            self._counter += 1
            return self._counter

    def create_checkout_attempt(self, cart_quote_id, buyer_id, request_id):
        with self._lock:
            for a in self.attempts.values():
                if a['request_id'] == request_id:
                    raise ValueError('DuplicateRequest')
            attempt_id = f'att-{uuid.uuid4().hex[:12]}'
            row = {
                'id': self._next_id(),
                'attempt_id': attempt_id,
                'cart_quote_id': cart_quote_id,
                'buyer_id': buyer_id,
                'request_id': request_id,
                'paypal_order_id': None,
                'status': 'ORDER_CREATED',
                'created_at': datetime.now(UTC),
                'updated_at': datetime.now(UTC),
            }
            self.attempts[attempt_id] = row
            return dict(row)

    def attach_paypal_order(self, attempt_id, paypal_order_id):
        with self._lock:
            a = self.attempts.get(attempt_id)
            if a:
                a['paypal_order_id'] = paypal_order_id
                a['updated_at'] = datetime.now(UTC)

    def get_attempt(self, key):
        with self._lock:
            if key in self.attempts:
                return dict(self.attempts[key])
            for a in self.attempts.values():
                if a.get('request_id') == key or a.get('paypal_order_id') == key:
                    return dict(a)
        return None

    def set_attempt_status(self, attempt_id, status):
        with self._lock:
            a = self.attempts.get(attempt_id)
            if a:
                a['status'] = status
                a['updated_at'] = datetime.now(UTC)

    def record_capture(self, attempt_id, capture_id, amount, currency, status, verified_at=None):
        with self._lock:
            if capture_id in self.captures:
                raise ValueError('DuplicateCapture')
            row = {
                'paypal_capture_id': capture_id,
                'attempt_id': attempt_id,
                'amount': Decimal(str(amount)),
                'currency': currency,
                'status': status,
                'verified_at': verified_at,
            }
            self.captures[capture_id] = row
            return dict(row)

    def get_capture(self, capture_id):
        c = self.captures.get(capture_id)
        return dict(c) if c else None

    def get_capture_for_attempt(self, attempt_id):
        for c in self.captures.values():
            if c['attempt_id'] == attempt_id:
                return dict(c)
        return None

    def record_event(self, provider_event_id, event_type='', verification_result='', processing_state=''):
        with self._lock:
            if provider_event_id in self.events:
                return False
            self.events[provider_event_id] = {
                'provider_event_id': provider_event_id,
                'event_type': event_type,
                'verification_result': verification_result,
                'processing_state': processing_state,
                'received_at': datetime.now(UTC),
            }
            return True

    def list_orders(self, limit=50, offset=0):
        with self._lock:
            rows = sorted(self.attempts.values(), key=lambda a: a['created_at'], reverse=True)
            out = []
            for a in rows[offset:offset + limit]:
                d = dict(a)
                d['capture'] = self.get_capture_for_attempt(a['attempt_id'])
                out.append(d)
            return out

    def funnel_stats(self):
        with self._lock:
            by_status = {}
            for a in self.attempts.values():
                by_status[a['status']] = by_status.get(a['status'], 0) + 1
            verified_total = sum(
                (c['amount'] for c in self.captures.values() if c.get('verified_at')),
                Decimal(0),
            )
            abandoned = by_status.get('AWAITING_BUYER_APPROVAL', 0) + by_status.get('ORDER_CREATED', 0)
            return {
                'by_status': by_status,
                'paid_gmv': f'{verified_total:.2f}',
                'currency': 'USD',
                'abandoned_carts': abandoned,
                'total_attempts': len(self.attempts),
            }

    def record_agent_session(self, actor_id, model, input_hash, output_redacted, approved_quote_id=None):
        with self._lock:
            self.agent_sessions.append({
                'actor_id': actor_id,
                'model': model,
                'input_hash': input_hash,
                'output_redacted': output_redacted,
                'approved_quote_id': approved_quote_id,
                'created_at': datetime.now(UTC),
            })

    def list_agent_sessions(self, limit=20):
        with self._lock:
            return list(reversed(self.agent_sessions[-limit:]))


class SimpleCartService:
    """Server-authoritative quote service used when commerce.cart_service
    is unavailable. Immutable price snapshot from the catalog, Decimal math,
    TTL expiry. Client-supplied prices are ignored by construction."""

    def __init__(self, catalog, storage, config):
        self.catalog = catalog
        self.storage = storage
        self.config = config
        self.ttl_minutes = int(getattr(config, 'CART_QUOTE_TTL_MINUTES', 30) or 30)
        try:
            self.max_total = Decimal(str(getattr(config, 'MAX_CART_TOTAL', '500.00') or '500.00'))
        except Exception:
            self.max_total = Decimal('500.00')

    def create_quote(self, actor_id, items):
        if not items:
            raise ValueError('cart is empty')
        if len(items) > 10:
            raise ValueError('too many distinct items (max 10)')
        lines = []
        total = Decimal(0)
        currency = 'USD'
        for it in items:
            sku = str(it.get('sku', ''))
            try:
                qty = int(it.get('quantity', 1))
            except (TypeError, ValueError):
                qty = 1
            if qty < 1 or qty > 10:
                raise ValueError(f'quantity out of bounds for {sku}')
            product = self.catalog.get_product(sku)
            if product is None:
                raise ValueError(f'unknown sku: {sku}')
            if not product.active:
                raise ValueError(f'product inactive: {sku}')
            if product.stock < qty:
                raise ValueError(f'insufficient stock for {sku}')
            unit = product.price  # catalog price only - never trust client
            line_total = (unit * qty).quantize(Decimal('0.01'))
            total += line_total
            currency = product.currency
            lines.append({
                'sku': sku,
                'title': product.title,
                'unit_price': unit,
                'quantity': qty,
                'line_total': line_total,
                'version': product.version,
            })
        if total > self.max_total:
            raise ValueError(f'cart total exceeds maximum {self.max_total}')
        quote = {
            'quote_id': str(uuid.uuid4()),
            'actor_id': actor_id,
            'currency': currency,
            'items': lines,
            'total': total.quantize(Decimal('0.01')),
            'status': 'OPEN',
            'expires_at': datetime.now(UTC) + timedelta(minutes=self.ttl_minutes),
            'version': 1,
            'created_at': datetime.now(UTC),
        }
        self.storage.create_quote(quote)
        return quote

    def validate_quote(self, quote_id):
        row = self.storage.get_quote(quote_id)
        if not row:
            raise QuoteNotFound(quote_id)
        if row.get('status') != 'OPEN':
            raise QuoteNotOpen(str(row.get('status')))
        expires = row.get('expires_at')
        now = datetime.now(UTC)
        if expires is not None:
            exp = expires if getattr(expires, 'tzinfo', None) else expires.replace(tzinfo=UTC)
            if now > exp:
                self.storage.update_quote_status(quote_id, 'EXPIRED')
                raise QuoteExpired(quote_id)
        return row

    def refresh_check(self, quote_id):
        row = self.storage.get_quote(quote_id)
        if not row:
            raise QuoteNotFound(quote_id)
        for line in row.get('items', []):
            product = self.catalog.get_product(line['sku'])
            if product is None or product.version != line.get('version'):
                raise QuoteStale(quote_id)
            if product.stock < int(line['quantity']):
                raise QuoteStale(quote_id)
        return True


class DeterministicAI:
    """Offline deterministic 'recommendation' used when ai.agent is missing
    or no provider key is configured. Never presents itself as AI."""

    def __init__(self, config, catalog):
        self.config = config
        self.catalog = catalog
        self._buckets = {}
        self._lock = threading.Lock()

    def _rate_ok(self, actor_id):
        now = datetime.now(UTC)
        with self._lock:
            calls = [t for t in self._buckets.get(actor_id, []) if (now - t).total_seconds() < 60]
            if len(calls) >= 10:
                return False
            calls.append(now)
            self._buckets[actor_id] = calls
            return True

    def recommend(self, query, locale='en', budget_hint=None, actor_id='anon'):
        if not self._rate_ok(actor_id):
            return {
                'items': [],
                'tradeoffs': '',
                'missing_info': ['rate limit reached, try again in a minute'],
                'cart_proposal': [],
                'confidence': 'low',
                'provider': 'deterministic-fallback',
                'fallback': True,
                'rate_limited': True,
            }
        query = str(query or '')[:500]
        budget = budget_hint
        if budget is None:
            m = re.search(r'(\d+(?:\.\d{1,2})?)', query)
            if m and re.search(r'(under|below|max|budget|less than|\$)', query, re.IGNORECASE):
                budget = m.group(1)
        results = self.catalog.search_products(query=query, budget_max=budget, limit=4)
        items = [{
            'sku': p.sku,
            'reason': f'Matches your search ({p.category}).',
            'price': f'{p.price:.2f}',
            'currency': p.currency,
        } for p in results]
        missing = []
        if budget is None and not re.search(r'\d', query):
            missing.append('budget')
        if str(locale).startswith('hi') and not items:
            tradeoffs = 'कोई मेल नहीं मिला।'
        else:
            tradeoffs = 'Ranked by price (lowest first) among catalog matches.'
        return {
            'items': items,
            'tradeoffs': tradeoffs,
            'missing_info': missing,
            'cart_proposal': [{'sku': it['sku'], 'quantity': 1} for it in items[:4]],
            'confidence': 'low',
            'provider': 'deterministic-fallback',
            'fallback': True,
        }
