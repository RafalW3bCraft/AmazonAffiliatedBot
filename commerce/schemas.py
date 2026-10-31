"""Pydantic v2 schemas for the commerce domain + Decimal money helpers."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CENTS = Decimal("0.01")


def to_decimal(value) -> Decimal:
    """Coerce a str/int/float/Decimal into a Decimal quantized to 0.01."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def format_money(value) -> str:
    """Format a Decimal money amount as a 2dp string, e.g. '24.99'."""
    return f"{to_decimal(value):.2f}"


_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class CatalogProduct(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    price: Decimal
    currency: str
    stock: int = Field(ge=0)
    category: str = Field(min_length=1)
    version: int = Field(ge=1)
    source: Literal["MERCHANT"] = "MERCHANT"
    rights_evidence: str = Field(min_length=1)
    active: bool

    @field_validator("price", mode="before")
    @classmethod
    def _price_decimal(cls, v):
        return to_decimal(v)

    @field_validator("currency")
    @classmethod
    def _currency_iso(cls, v: str) -> str:
        if not _CURRENCY_RE.match(v):
            raise ValueError("currency must be 3 uppercase letters")
        return v


class CartItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=10)


class QuoteLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str
    title: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    version: int


class CartQuoteData(BaseModel):
    model_config = ConfigDict(frozen=True)

    quote_id: str
    actor_id: str
    currency: str
    items: list[QuoteLine]
    total: Decimal
    expires_at: datetime
    status: str = "OPEN"
