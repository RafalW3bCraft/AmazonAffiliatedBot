"""View-model builders for the DealPilot templates.

Everything that reaches a template is a plain dict of strings/ints/bools.
No Decimal objects, no datetime objects (ISO strings only) leak through.
"""
import collections.abc as _abc
from decimal import Decimal, InvalidOperation

HI_LABELS = {
    'shop_title': 'DealPilot स्टोर',
    'lane1': 'लेन 1: मर्चेंट स्टोर — PayPal सैंडबॉक्स से खरीदें।',
    'lane2': 'लेन 2: अमेज़न डील्स — बाहरी एफिलिएट लिंक, चेकआउट अमेज़न पर।',
    'search': 'खोजें',
    'ask_ai': 'AI से पूछें',
    'add_to_cart': 'कार्ट में डालें',
    'view_cart': 'कार्ट देखें',
    'checkout': 'PayPal से भुगतान करें (सैंडबॉक्स)',
    'total': 'कुल',
    'price': 'कीमत',
    'stock': 'स्टॉक',
    'quantity': 'मात्रा',
}

EN_LABELS = {
    'shop_title': 'DealPilot Store',
    'lane1': 'Lane 1: Merchant store - buy with PayPal sandbox.',
    'lane2': 'Lane 2: Amazon deals - external affiliate links, checkout on Amazon.',
    'search': 'Search',
    'ask_ai': 'Ask the shopping assistant',
    'add_to_cart': 'Add to cart',
    'view_cart': 'View cart',
    'checkout': 'Pay with PayPal (Sandbox)',
    'total': 'Total',
    'price': 'Price',
    'stock': 'Stock',
    'quantity': 'Qty',
}

FULFILLMENT_TEXT = (
    'Demo fulfillment: digital/demo goods only. Nothing is shipped; '
    'PayPal sandbox payments are not real charges.'
)
SANDBOX_RECEIPT_NOTE = 'Sandbox test transaction - not a tax receipt.'


def labels_for(lang):
    return HI_LABELS if str(lang or '').lower().startswith('hi') else EN_LABELS


def money_str(value):
    """Format any money-ish value as '24.99'. Never raises."""
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
        return f'{d:.2f}'
    except (InvalidOperation, ValueError, TypeError):
        return '0.00'


def iso(dt):
    """datetime -> iso string; anything else -> str()."""
    if dt is None:
        return ''
    if hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return str(dt)


def _get(obj, name, default=None):
    """Attribute/key access that never resolves dict methods (e.g. 'items')."""
    if isinstance(obj, _abc.Mapping):
        return obj[name] if name in obj else default
    return getattr(obj, name, default)


def product_card(p):
    return {
        'sku': str(_get(p, 'sku', '')),
        'title': str(_get(p, 'title', '')),
        'description': str(_get(p, 'description', '')),
        'price': money_str(_get(p, 'price', '0')),
        'currency': str(_get(p, 'currency', 'USD')),
        'stock': int(_get(p, 'stock', 0) or 0),
        'category': str(_get(p, 'category', '')),
        'active': bool(_get(p, 'active', True)),
        'lane': 'MERCHANT - PayPal checkout',
    }


def quote_vm(quote):
    """CartQuoteData/dict/row -> template-safe quote view model."""
    items = []
    for it in (_get(quote, 'items', []) or []):
        unit = _get(it, 'unit_price', _get(it, 'price', '0'))
        qty = int(_get(it, 'quantity', 1) or 1)
        line = _get(it, 'line_total', None)
        if line is None:
            try:
                line = Decimal(str(unit)) * qty
            except (InvalidOperation, ValueError, TypeError):
                line = Decimal('0')
        items.append({
            'sku': str(_get(it, 'sku', '')),
            'title': str(_get(it, 'title', '')),
            'quantity': qty,
            'unit_price': money_str(unit),
            'line_total': money_str(line),
        })
    expires_at = _get(quote, 'expires_at', None)
    return {
        'quote_id': str(_get(quote, 'quote_id', '')),
        'items': items,
        'total': money_str(_get(quote, 'total', '0')),
        'currency': str(_get(quote, 'currency', 'USD')),
        'status': str(_get(quote, 'status', 'OPEN')),
        'expires_at': iso(expires_at),
        'expires_at_ts': int(expires_at.timestamp()) if (expires_at is not None and hasattr(expires_at, 'timestamp')) else 0,
        'merchant_name': 'DealPilot Demo Merchant',
        'fulfillment': FULFILLMENT_TEXT,
    }


STATUS_LABELS = {
    'ORDER_CREATED': 'Order created',
    'AWAITING_BUYER_APPROVAL': 'Awaiting buyer approval',
    'APPROVED': 'Approved',
    'CAPTURE_PENDING': 'Capture pending',
    'PAID': 'Paid',
    'FAILED': 'Failed',
    'CANCELED': 'Canceled',
    'REQUIRES_REVIEW': 'Requires review',
}


def order_vm(attempt, capture=None):
    """Checkout attempt row/dict (+ optional capture) -> receipt view model."""
    attempt_id = str(_get(attempt, 'attempt_id', _get(attempt, 'id', '')))
    status = str(_get(attempt, 'status', 'UNKNOWN'))
    amount = _get(capture, 'amount', None) if capture else None
    currency = _get(capture, 'currency', None) if capture else None
    if amount is None:
        amount = _get(attempt, 'amount', _get(attempt, 'total', ''))
    if currency is None:
        currency = _get(attempt, 'currency', '')
    capture_id = str(_get(capture, 'paypal_capture_id', _get(capture, 'capture_id', ''))) if capture else ''
    verified_at = _get(capture, 'verified_at', None) if capture else None
    masked = ('…' + attempt_id[-6:]) if len(attempt_id) > 6 else attempt_id
    return {
        'attempt_id': attempt_id,
        'masked_id': masked,
        'status': status,
        'status_label': STATUS_LABELS.get(status, status.replace('_', ' ').title()),
        'is_final': status in ('PAID', 'FAILED', 'CANCELED'),
        'amount': money_str(amount) if amount not in (None, '') else '',
        'currency': str(currency or ''),
        'capture_id': capture_id,
        'verified': bool(verified_at),
        'verified_at': iso(verified_at),
        'created_at': iso(_get(attempt, 'created_at', None)),
        'updated_at': iso(_get(attempt, 'updated_at', None)),
        'sandbox_note': SANDBOX_RECEIPT_NOTE,
    }
