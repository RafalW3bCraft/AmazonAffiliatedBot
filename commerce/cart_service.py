"""Cart service: builds immutable Decimal quote snapshots from the catalog."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from .catalog import Catalog
from .exceptions import CartError, QuoteExpired, QuoteNotFound, QuoteNotOpen, QuoteStale
from .policy import MAX_LINES, SUPPORTED_CURRENCIES, max_cart_total, validate_policy
from .schemas import CartItem, CartQuoteData, QuoteLine, to_decimal
from .storage import CommerceStorage


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CartService:
    def __init__(
        self,
        catalog: Catalog,
        storage: CommerceStorage,
        config,
        clock=_utcnow,
    ):
        validate_policy(config)
        self.catalog = catalog
        self.storage = storage
        self.config = config
        self.clock = clock

    # -- quote creation ---------------------------------------------------

    def create_quote(self, actor_id: str, items: list[CartItem]) -> CartQuoteData:
        if not items:
            raise CartError("cart is empty")
        if len(items) > MAX_LINES:
            raise CartError(f"cart may have at most {MAX_LINES} lines")

        currency = getattr(self.config, "PAYPAL_CURRENCY", "USD")
        if currency not in SUPPORTED_CURRENCIES:
            raise CartError(f"currency {currency!r} not supported")

        lines: list[QuoteLine] = []
        total = to_decimal("0")
        seen: set[str] = set()
        for item in items:
            if item.sku in seen:
                raise CartError(f"duplicate line for sku {item.sku!r}")
            seen.add(item.sku)

            # Server reloads the product from the catalog — client-supplied
            # prices are never trusted.
            product = self.catalog.get_product(item.sku)
            if product is None:
                raise CartError(f"unknown sku {item.sku!r}")
            if not product.active:
                raise CartError(f"product {item.sku!r} is inactive")
            if product.stock < item.quantity:
                raise CartError(
                    f"insufficient stock for {item.sku!r}: "
                    f"have {product.stock}, want {item.quantity}"
                )
            if product.currency != currency:
                raise CartError(
                    f"product {item.sku!r} currency {product.currency!r} "
                    f"!= checkout currency {currency!r}"
                )

            line_total = to_decimal(product.price * item.quantity)
            lines.append(
                QuoteLine(
                    sku=product.sku,
                    title=product.title,
                    unit_price=product.price,
                    quantity=item.quantity,
                    line_total=line_total,
                    version=product.version,
                )
            )
            total = to_decimal(total + line_total)

        cap = max_cart_total(self.config)
        if total > cap:
            raise CartError(f"cart total {total} exceeds MAX_CART_TOTAL {cap}")

        ttl_minutes = int(getattr(self.config, "CART_QUOTE_TTL_MINUTES", 30))
        quote = CartQuoteData(
            quote_id=str(uuid.uuid4()),
            actor_id=actor_id,
            currency=currency,
            items=lines,
            total=total,
            expires_at=self.clock() + timedelta(minutes=ttl_minutes),
            status="OPEN",
        )
        self.storage.create_quote(quote)
        return quote

    # -- quote validation ---------------------------------------------------

    def _load_quote(self, quote_id: str):
        row = self.storage.get_quote(quote_id)
        if row is None:
            raise QuoteNotFound(quote_id)
        return self.storage.quote_to_data(row)

    def validate_quote(self, quote_id: str) -> CartQuoteData:
        quote = self._load_quote(quote_id)
        if quote.status != "OPEN":
            raise QuoteNotOpen(f"quote {quote_id} status is {quote.status}")
        if quote.expires_at <= self.clock():
            self.storage.update_quote_status(quote_id, "EXPIRED")
            raise QuoteExpired(quote_id)
        return quote

    def refresh_check(self, quote_id: str) -> CartQuoteData:
        """Re-read the catalog; fail if the snapshot drifted (stale)."""
        quote = self._load_quote(quote_id)
        for line in quote.items:
            product = self.catalog.get_product(line.sku)
            if product is None:
                raise QuoteStale(f"sku {line.sku!r} no longer in catalog")
            if product.version != line.version:
                raise QuoteStale(
                    f"sku {line.sku!r} version changed "
                    f"{line.version} -> {product.version}"
                )
            if product.stock < line.quantity:
                raise QuoteStale(
                    f"sku {line.sku!r} stock now {product.stock} "
                    f"< quoted quantity {line.quantity}"
                )
        return quote
