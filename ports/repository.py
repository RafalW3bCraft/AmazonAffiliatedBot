from typing import Protocol, List, Optional, runtime_checkable
from models import Deal, User


@runtime_checkable
class DealRepository(Protocol):
    async def initialize(self) -> None:
        ...

    async def add_deal(self, product, affiliate_link: str, source: str = "scraper", content_style: str = "simple") -> Deal:
        ...

    async def get_recent_deals(self, hours: int = 24, limit: int = 50, category: Optional[str] = None) -> List[Deal]:
        ...

    async def get_active_users(self, days: int = 30) -> List[User]:
        ...

    async def get_deal_stats(self):
        ...

    async def close(self) -> None:
        ...
