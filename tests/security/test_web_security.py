"""Security tests for the DealPilot web layer.

Covers: privileged API auth + payload minimization, public config leakage,
PayPal webhook signature/SSRF/allowlist/dedup behavior (all HTTP mocked,
no network), session cookie flags, and merchant fail-closed behavior.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WEBHOOK_HEADERS = {
    'PAYPAL-TRANSMISSION-ID': 'tx-1',
    'PAYPAL-TRANSMISSION-TIME': '2026-10-30T00:00:00Z',
    'PAYPAL-TRANSMISSION-SIG': 'sig',
    'PAYPAL-CERT-URL': 'https://api-m.sandbox.paypal.com/cert.pem',
    'PAYPAL-AUTH-ALGO': 'SHA256withRSA',
}


def _env(monkeypatch, tmp_path, **overrides):
    env = {
        'DEMO_MODE': 'false',
        'FLASK_SECRET_KEY': 's' * 32,
        'ENABLE_MERCHANT_CHECKOUT': 'true',
        'COMMERCE_DATABASE_URL': f"sqlite:///{tmp_path}/sec.db",
        'DATABASE_URL': '',
        'OPENAI_API_KEY': '',
        'FEATHERLESS_API_KEY': '',
        'DASHBOARD_TOKEN': '',
        'PAYPAL_CLIENT_ID': '',
        'PAYPAL_CLIENT_SECRET': '',
        'PAYPAL_WEBHOOK_ID': '',
    }
    env.update(overrides)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def _make_app(monkeypatch, tmp_path, **overrides):
    _env(monkeypatch, tmp_path, **overrides)
    from config import Config
    from web_dashboard_clean import create_app
    cfg = Config()
    app = create_app(cfg)
    # Services are built lazily on first request; force the build now so
    # tests can stub services on app.extensions['dealpilot'].
    import web.commerce_routes as cr
    with app.test_request_context('/'):
        cr._build_services(cfg)
    return app


# -- 1. /api/users auth + minimization -------------------------------------

def test_api_users_requires_token_and_minimizes_payload(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, DASHBOARD_TOKEN='tok-123')
    client = app.test_client()
    assert client.get('/api/users').status_code in (401, 404)
    resp = client.get('/api/users', headers={'Authorization': 'Bearer tok-123'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'username' not in body and 'first_name' not in body
    for value in body.values():
        if isinstance(value, dict):
            assert 'username' not in value and 'first_name' not in value


def test_api_users_fail_closed_without_token_configured(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path)  # no DASHBOARD_TOKEN, non-demo
    assert app.test_client().get('/api/users').status_code in (401, 404)


# -- 2. /api/config leakage ---------------------------------------------------

def test_api_config_has_no_affiliate_id_or_secrets(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, DEMO_MODE='true',
                    AMAZON_AFFILIATE_ID='mytag-20')
    resp = app.test_client().get('/api/config')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'amazon_affiliate_id' not in body
    assert 'AMAZON_AFFILIATE_ID' not in body
    assert 'mytag-20' not in str(body)
    for key in body:
        assert 'secret' not in key.lower()
        assert 'token' not in key.lower()
        assert 'key' not in key.lower()


# -- 3. Webhook security --------------------------------------------------------

def _post_webhook(client, event, headers=None):
    return client.post('/webhooks/paypal', json=event, headers=headers or {})


def test_webhook_unconfigured_returns_503(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path)  # no webhook id, no creds
    resp = _post_webhook(app.test_client(), {'id': 'e1', 'event_type': 'X'})
    assert resp.status_code == 503


def test_webhook_missing_signature_headers_400(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path,
                    PAYPAL_CLIENT_ID='cid', PAYPAL_CLIENT_SECRET='sec',
                    PAYPAL_WEBHOOK_ID='wh-1')
    resp = _post_webhook(app.test_client(), {'id': 'e1', 'event_type': 'X'})
    assert resp.status_code == 400


def _stub_verification(monkeypatch, app, status='SUCCESS'):
    """Stub the token getter + outbound verify call; returns recorded posts."""
    import web.commerce_routes as cr

    class _Resp:
        status_code = 200

        def json(self):
            return {'verification_status': status}

    posts = []
    ext = app.extensions['dealpilot']
    ext['token_getter'] = lambda: 'fake-token'
    monkeypatch.setattr(cr.httpx, 'post', lambda *a, **k: (posts.append((a, k)), _Resp())[1])
    return posts


def test_webhook_ssrf_cert_url_rejected_without_fetch(monkeypatch, tmp_path):
    import web.commerce_routes as cr

    app = _make_app(monkeypatch, tmp_path,
                    PAYPAL_CLIENT_ID='cid', PAYPAL_CLIENT_SECRET='sec',
                    PAYPAL_WEBHOOK_ID='wh-1')
    posts = _stub_verification(monkeypatch, app)

    def _no_fetch(*args, **kwargs):
        raise AssertionError('outbound HTTP must not happen for rejected cert_url')

    monkeypatch.setattr(cr.httpx, 'post', _no_fetch)

    headers = dict(WEBHOOK_HEADERS)
    headers['PAYPAL-CERT-URL'] = 'http://169.254.169.254/latest'
    resp = _post_webhook(app.test_client(), {'id': 'e1', 'event_type': 'X'}, headers)
    assert resp.status_code == 400
    assert posts == []


def test_webhook_unknown_event_ignored_after_successful_verification(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path,
                    PAYPAL_CLIENT_ID='cid', PAYPAL_CLIENT_SECRET='sec',
                    PAYPAL_WEBHOOK_ID='wh-1')
    _stub_verification(monkeypatch, app)
    resp = _post_webhook(
        app.test_client(),
        {'id': 'evt-unknown', 'event_type': 'SOME.OTHER.EVENT'},
        WEBHOOK_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.get_json() == {'ignored': True}


def test_webhook_duplicate_event_id_processed_once(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path,
                    PAYPAL_CLIENT_ID='cid', PAYPAL_CLIENT_SECRET='sec',
                    PAYPAL_WEBHOOK_ID='wh-1')
    _stub_verification(monkeypatch, app)
    client = app.test_client()
    event = {
        'id': 'evt-dup',
        'event_type': 'PAYMENT.CAPTURE.PENDING',
        'resource': {'id': 'cap-1'},
    }
    first = _post_webhook(client, event, WEBHOOK_HEADERS)
    assert first.status_code == 200

    # Count events in storage; second identical POST must not add another.
    storage = app.extensions['dealpilot']['storage']
    second = _post_webhook(client, event, WEBHOOK_HEADERS)
    assert second.status_code == 200
    assert second.get_json() == {'duplicate': True}

    # Verify dedup through storage semantics: recording the same id again
    # must report a duplicate (False).
    assert storage.record_event('evt-dup', event_type='X',
                                verification_result='SUCCESS',
                                processing_state='RECEIVED') is False

    # And the first POST did record it exactly once.
    with storage.session() as s:
        from commerce.storage import PaymentEvent
        count = s.query(PaymentEvent).filter_by(provider_event_id='evt-dup').count()
    assert count == 1


def test_webhook_bad_signature_status_400(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path,
                    PAYPAL_CLIENT_ID='cid', PAYPAL_CLIENT_SECRET='sec',
                    PAYPAL_WEBHOOK_ID='wh-1')
    _stub_verification(monkeypatch, app, status='FAILURE')
    resp = _post_webhook(
        app.test_client(),
        {'id': 'evt-bad', 'event_type': 'PAYMENT.CAPTURE.PENDING', 'resource': {}},
        WEBHOOK_HEADERS,
    )
    assert resp.status_code == 400


# -- 4. session cookie flags ---------------------------------------------------

def test_session_cookie_flags(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path, DEMO_MODE='true')
    assert app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    # Secure only under https scheme; local demo runs http.
    assert app.config['SESSION_COOKIE_SECURE'] is False


# -- 5. /merchant fail-closed in non-demo ---------------------------------------

def test_merchant_fail_closed_non_demo(monkeypatch, tmp_path):
    app = _make_app(monkeypatch, tmp_path)  # non-demo, no DASHBOARD_TOKEN
    assert app.test_client().get('/merchant').status_code in (401, 404)

    app2 = _make_app(monkeypatch, tmp_path / 'b', DASHBOARD_TOKEN='tok-9')
    assert app2.test_client().get('/merchant').status_code == 401
