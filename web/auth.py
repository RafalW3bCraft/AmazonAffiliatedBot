"""Auth/session helpers for the DealPilot web layer.

Buyer identity is a random actor id in the Flask session cookie. Merchant
access is gated by DASHBOARD_TOKEN (Bearer header or ?token=) with a
demo-mode bypass that is clearly labeled in the UI.
"""
import functools
import hmac
import logging
import secrets
import uuid

from flask import abort, current_app, jsonify, request, session

logger = logging.getLogger(__name__)

CSRF_SESSION_KEY = 'csrf_token'
ACTOR_SESSION_KEY = 'actor_id'


def current_actor_id():
    """Return the session buyer/actor id, creating one lazily."""
    actor = session.get(ACTOR_SESSION_KEY)
    if not actor:
        actor = uuid.uuid4().hex
        session[ACTOR_SESSION_KEY] = actor
    return actor


def ensure_actor():
    """Ensure an actor id exists for this session. Returns it."""
    return current_actor_id()


def apply_security(app):
    """Session cookie hardening. Secure flag is set when the deployment
    serves https (checked per-request via request.scheme by Flask when the
    config flag is a callable is not supported, so we set it statically if
    PREFERRED_URL_SCHEME is https, otherwise rely on proxy config)."""
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Only mark cookies Secure when the app is served over https; in local
    # demo (http) a Secure cookie would be dropped by the browser.
    scheme = app.config.get('PREFERRED_URL_SCHEME', 'http')
    app.config['SESSION_COOKIE_SECURE'] = (scheme == 'https')


def csrf_token():
    """Per-session CSRF token, created on demand."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def verify_csrf():
    """Check the CSRF token from header or form field against the session."""
    expected = session.get(CSRF_SESSION_KEY)
    if not expected:
        return False
    provided = (
        request.headers.get('X-CSRF-Token')
        or request.form.get('csrf_token')
        or (request.get_json(silent=True) or {}).get('csrf_token')
        or ''
    )
    return bool(provided) and hmac.compare_digest(str(provided), expected)


def require_csrf(view):
    """Decorator: 403 on POST writes without a valid CSRF token."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not verify_csrf():
            return jsonify({'error': 'invalid or missing CSRF token'}), 403
        return view(*args, **kwargs)
    return wrapper


def _merchant_token_valid(config):
    token = getattr(config, 'DASHBOARD_TOKEN', '') or ''
    if not token:
        return None  # no token configured
    provided = request.headers.get('Authorization', '')
    if provided.startswith('Bearer '):
        provided = provided[7:]
    else:
        provided = request.args.get('token', '')
    return bool(provided) and hmac.compare_digest(str(provided), token)


def is_merchant(config):
    """True only when the request carries a valid merchant token.

    DEMO_MODE opens the /merchant *page* (via require_merchant), but it must
    never make an arbitrary requester 'merchant' for buyer-order ownership
    checks - otherwise any demo visitor could read every order.
    """
    valid = _merchant_token_valid(config)
    return bool(valid)


def require_merchant(view):
    """Merchant gate: DASHBOARD_TOKEN via Bearer or ?token=. With no token
    configured: 404 in production (fail closed), allowed in DEMO_MODE with a
    visible banner (templates read `demo_mode`)."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        config = current_app.extensions['dealpilot']['config']
        valid = _merchant_token_valid(config)
        if valid is None:
            if getattr(config, 'DEMO_MODE', False):
                return view(*args, **kwargs)
            abort(404)
        if not valid:
            return jsonify({'error': 'authentication required'}), 401
        return view(*args, **kwargs)
    return wrapper
