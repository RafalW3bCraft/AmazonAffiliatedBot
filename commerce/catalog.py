"""Merchant-owned product catalog, loaded from config/merchant_catalog.json.

Defensive guards: only source == 'MERCHANT' products are accepted, and any
SKU shaped like an Amazon ASIN (10-char uppercase alnum starting with B0)
is rejected so Amazon items can never leak into the checkout flow.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from .exceptions import CatalogError
from .schemas import CatalogProduct

_ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")


def _looks_like_asin(sku: str) -> bool:
    return bool(_ASIN_RE.match(sku))


class Catalog:
    def __init__(self, catalog_path):
        self._path = Path(catalog_path)
        self._products: dict[str, CatalogProduct] = {}
        self.reload()

    def reload(self) -> None:
        if not self._path.exists():
            raise CatalogError(f"catalog file not found: {self._path}")
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CatalogError(f"catalog file is not valid JSON: {exc}") from exc
        if isinstance(raw, dict) and isinstance(raw.get("products"), list):
            raw = raw["products"]
        if not isinstance(raw, list):
            raise CatalogError(
                "catalog root must be a JSON array of products "
                "(or an object with a 'products' array)"
            )

        products: dict[str, CatalogProduct] = {}
        for entry in raw:
            sku = str(entry.get("sku", ""))
            if _looks_like_asin(sku):
                # Reject Amazon-shaped SKUs outright — Amazon data must never
                # enter this merchant-owned checkout.
                raise CatalogError(
                    f"sku {sku!r} looks like an Amazon ASIN; rejected"
                )
            data = dict(entry)
            data.setdefault("source", "MERCHANT")
            product = CatalogProduct.model_validate(data)
            if product.source != "MERCHANT":
                raise CatalogError(
                    f"sku {sku!r} has source {product.source!r}; only MERCHANT allowed"
                )
            if product.sku in products:
                raise CatalogError(f"duplicate sku {product.sku!r} in catalog")
            products[product.sku] = product
        self._products = products

    def list_products(self, active_only: bool = True) -> list[CatalogProduct]:
        items = list(self._products.values())
        if active_only:
            items = [p for p in items if p.active]
        return sorted(items, key=lambda p: (p.price, p.sku))

    def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        budget_max: Decimal | None = None,
        limit: int = 8,
    ) -> list[CatalogProduct]:
        results = [p for p in self._products.values() if p.active]
        if query:
            needle = query.casefold()
            results = [
                p
                for p in results
                if needle in p.title.casefold()
                or needle in p.description.casefold()
                or needle in p.category.casefold()
            ]
        if category:
            cat = category.casefold()
            results = [p for p in results if p.category.casefold() == cat]
        if budget_max is not None:
            results = [p for p in results if p.price <= budget_max]
        # Deterministic order: price ascending, then sku as stable tie-break.
        results.sort(key=lambda p: (p.price, p.sku))
        return results[:limit]

    def get_product(self, sku: str) -> CatalogProduct | None:
        return self._products.get(sku)
