"""DealPilot AI layer: provider-agnostic shopping recommendation service.

Money/price decisions are never made by the LLM. All prices, stock, and
catalog facts are revalidated server-side against the merchant catalog
before anything reaches a shopper.
"""

from ai.agent import AIShoppingService
from ai.schemas import (
    AIRecommendation,
    CartProposalItem,
    RecommendationItem,
    ShopIntent,
)
from ai.tools import CatalogProtocol, CatalogTools, ToolError

__all__ = [
    "AIRecommendation",
    "AIShoppingService",
    "CartProposalItem",
    "CatalogProtocol",
    "CatalogTools",
    "RecommendationItem",
    "ShopIntent",
    "ToolError",
]
