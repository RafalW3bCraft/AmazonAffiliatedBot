"""Read-only tool registry over a merchant catalog.

The catalog is duck-typed via :class:`CatalogProtocol` (structural typing)
so this module never imports ``commerce`` at module import time and cannot
create an import cycle while commerce.catalog is built in parallel.

All tools are strictly read-only: no cart mutation, no checkout, no price
changes. Any unknown SKU raises :class:`ToolError`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


class ToolError(Exception):
    """Raised when a tool call is invalid (e.g. unknown SKU)."""


@runtime_checkable
class CatalogProtocol(Protocol):
    """Structural interface expected from commerce.catalog.

    Implementations expose product objects with attributes:
    sku, title, description, price (Decimal), currency, stock, category,
    active — plus the two lookup functions below.
    """

    def search_products(
        self,
        query: str,
        category: str | None = None,
        budget_max: Decimal | None = None,
        limit: int = 8,
    ) -> list[Any]: ...

    def get_product(self, sku: str) -> Any | None: ...


def _product_to_dict(product: Any) -> dict:
    return {
        "sku": str(product.sku),
        "title": str(product.title),
        "description": str(product.description),
        "price": str(product.price),
        "currency": str(product.currency),
        "stock": int(product.stock),
        "category": str(product.category),
        "active": bool(product.active),
    }


class CatalogTools:
    """Read-only tool registry. Every method validates inputs and never
    mutates the underlying catalog."""

    def __init__(self, catalog: CatalogProtocol) -> None:
        self._catalog = catalog

    # -- tools -----------------------------------------------------------

    def catalog_search(
        self,
        query: str,
        category: str | None = None,
        budget_max: Decimal | None = None,
        limit: int = 8,
    ) -> list[dict]:
        """Search active products. Returns plain dicts (JSON-safe)."""
        if limit < 1:
            raise ToolError("limit must be >= 1")
        products = self._catalog.search_products(
            query=query, category=category, budget_max=budget_max, limit=limit
        )
        return [_product_to_dict(p) for p in products]

    def get_product(self, sku: str) -> dict | None:
        """Fetch one product by SKU. None if not found."""
        product = self._catalog.get_product(sku)
        if product is None:
            return None
        return _product_to_dict(product)

    def compare_products(self, skus: list[str]) -> list[dict]:
        """Fetch several products for side-by-side comparison.

        Raises ToolError if any SKU is unknown.
        """
        out: list[dict] = []
        for sku in skus:
            product = self._catalog.get_product(sku)
            if product is None:
                raise ToolError(f"unknown sku: {sku}")
            out.append(_product_to_dict(product))
        return out

    def calculate_quote(self, items: list[dict]) -> dict:
        """Quote a set of {sku, quantity} lines using exact Decimal math.

        Returns {"lines": [...], "total": str(Decimal), "currency": str}.
        Raises ToolError on unknown SKU, bad quantity, or mixed currencies.
        """
        lines: list[dict] = []
        total = Decimal(0)
        currency: str | None = None
        for entry in items:
            sku = str(entry.get("sku", ""))
            try:
                quantity = int(entry.get("quantity", 0))
            except (TypeError, ValueError):
                raise ToolError(f"invalid quantity for sku {sku}")
            if quantity < 1 or quantity > 10:
                raise ToolError(f"quantity out of range (1..10) for sku {sku}")
            product = self._catalog.get_product(sku)
            if product is None:
                raise ToolError(f"unknown sku: {sku}")
            unit_price = Decimal(str(product.price))
            line_total = unit_price * quantity
            prod_currency = str(product.currency)
            if currency is None:
                currency = prod_currency
            elif currency != prod_currency:
                raise ToolError("mixed currencies in quote")
            total += line_total
            lines.append(
                {
                    "sku": sku,
                    "quantity": quantity,
                    "unit_price": str(unit_price),
                    "line_total": str(line_total),
                    "currency": prod_currency,
                }
            )
        return {
            "lines": lines,
            "total": str(total),
            "currency": currency or "",
        }
