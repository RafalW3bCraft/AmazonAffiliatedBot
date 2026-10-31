"""Catalog tests: JSON load, 8 valid products, ASIN guard, search, get."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from commerce.catalog import Catalog
from commerce.exceptions import CatalogError

CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "merchant_catalog.json"


@pytest.fixture()
def catalog() -> Catalog:
    return Catalog(CATALOG_PATH)


def test_loads_eight_valid_products(catalog):
    products = catalog.list_products()
    assert len(products) == 8
    skus = {p.sku for p in products}
    assert len(skus) == 8
    for p in products:
        assert p.source == "MERCHANT"
        assert p.currency == "USD"
        assert p.active is True
        assert p.version >= 1
        assert p.stock >= 0
        assert p.price > Decimal(0)
        assert p.rights_evidence


def test_required_skus_present(catalog):
    skus = {p.sku for p in catalog.list_products()}
    assert {"DP-LAMP-001", "DP-PLANT-008", "DP-HUB-007"} <= skus


def test_no_brand_names(catalog):
    banned = {"amazon", "anker", "logitech", "samsung", "apple", "ikea"}
    for p in catalog.list_products():
        text = f"{p.title} {p.description}".casefold()
        for brand in banned:
            assert brand not in text, f"{p.sku} mentions {brand}"


def test_asin_looking_sku_rejected(tmp_path):
    bad = [
        {
            "sku": "B0ABC12345",
            "title": "Sneaky Amazon Import",
            "description": "Should never pass the guard.",
            "price": "9.99",
            "currency": "USD",
            "stock": 1,
            "category": "misc",
            "version": 1,
            "rights_evidence": "none",
            "active": True,
        }
    ]
    path = tmp_path / "bad_catalog.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(CatalogError):
        Catalog(path)


def test_non_merchant_source_rejected(tmp_path):
    bad = [
        {
            "sku": "DP-FAKE-001",
            "title": "Wrong source",
            "description": "Scraped item must be rejected.",
            "price": "9.99",
            "currency": "USD",
            "stock": 1,
            "category": "misc",
            "version": 1,
            "source": "AMAZON",
            "rights_evidence": "none",
            "active": True,
        }
    ]
    path = tmp_path / "bad_source.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(Exception):
        Catalog(path)


def test_search_query_case_insensitive(catalog):
    results = catalog.search_products(query="LAMP")
    assert len(results) == 1
    assert results[0].sku == "DP-LAMP-001"
    # substring match across title/description/category
    results2 = catalog.search_products(query="desk")
    assert len(results2) >= 2


def test_search_category_filter(catalog):
    results = catalog.search_products(category="ergonomics")
    assert results
    assert all(p.category == "ergonomics" for p in results)


def test_search_budget_filter(catalog):
    budget = Decimal("20.00")
    results = catalog.search_products(budget_max=budget)
    assert results
    assert all(p.price <= budget for p in results)
    # deterministic order: price ascending
    prices = [p.price for p in results]
    assert prices == sorted(prices)


def test_search_limit(catalog):
    results = catalog.search_products(limit=3)
    assert len(results) == 3


def test_get_product(catalog):
    lamp = catalog.get_product("DP-LAMP-001")
    assert lamp is not None
    assert lamp.title == "Compact LED Desk Lamp"
    assert catalog.get_product("DP-NOPE-999") is None


def test_inactive_hidden_by_default(tmp_path):
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    products = data["products"] if isinstance(data, dict) else data
    products[0]["active"] = False
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(products), encoding="utf-8")
    cat = Catalog(path)
    assert len(cat.list_products(active_only=True)) == 7
    assert len(cat.list_products(active_only=False)) == 8
