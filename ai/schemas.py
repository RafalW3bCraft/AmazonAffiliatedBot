"""Strict pydantic v2 schemas for the AI shopping layer."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ShopIntent(BaseModel):
    """Structured extraction of what the shopper is asking for."""

    model_config = ConfigDict(extra="forbid")

    budget_max: Decimal | None = None
    category: str | None = None
    locale: str = "en"
    raw_query: str = Field(default="", max_length=500)


class RecommendationItem(BaseModel):
    """A single recommended product.

    ``price`` is a server-verified echo of the catalog price as a string,
    never a model-invented number.
    """

    model_config = ConfigDict(extra="forbid")

    sku: str
    reason: str
    price: str
    currency: str


class CartProposalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    quantity: int = Field(ge=1, le=10)


class AIRecommendation(BaseModel):
    """Top-level recommendation payload returned to callers."""

    model_config = ConfigDict(extra="forbid")

    intent_summary: str
    items: list[RecommendationItem] = Field(default_factory=list, max_length=4)
    tradeoffs: str = ""
    missing_info: list[str] = Field(default_factory=list)
    cart_proposal: list[CartProposalItem] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    provider: str = ""
    fallback: bool = False
