from config import Config
from web_dashboard_clean import create_app


def test_health_endpoint_returns_json():
    app = create_app(Config())
    with app.test_client() as client:
        response = client.get('/api/health')
        assert response.status_code in (200, 503)
        data = response.get_json()
        assert isinstance(data, dict)
        assert 'status' in data


def test_deals_page_renders():
    app = create_app(Config())
    with app.test_client() as client:
        response = client.get('/deals')
        assert response.status_code == 200


def test_api_deals_returns_list():
    app = create_app(Config())
    with app.test_client() as client:
        response = client.get('/api/deals')
        assert response.status_code == 200
        assert isinstance(response.get_json(), list)
