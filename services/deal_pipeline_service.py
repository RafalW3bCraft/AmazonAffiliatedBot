from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from typing import Callable, List, Optional, Any

from models import Product
from core.telemetry import metrics
from core.logging import new_run_context, deal_id

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    fetched: int = 0
    posted: int = 0
    deduped_out: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)


class DealPipelineService:
    """Canonical pipeline for posting deals to Telegram + repository."""

    def __init__(
        self,
        db_manager: Any,
        content_generator: Any,
        affiliate_link_builder: Callable[[str], str],
        telegram_client: Optional[Any] = None,
        telegram_channel: Optional[str] = None,
        source: str = "scraper",
        content_style: str = "enthusiastic",
        dedupe_hours: int = 2,
    ):
        self.db_manager = db_manager
        self.content_generator = content_generator
        self.affiliate_link_builder = affiliate_link_builder
        self.telegram_client = telegram_client
        self.telegram_channel = telegram_channel
        self.source = source
        self.content_style = content_style
        self.dedupe_hours = dedupe_hours

    async def post_products(self, products: List[Product]) -> PipelineResult:
        run = new_run_context()
        logger.info(f"[PIPELINE] Starting cycle run={run}")
        result = PipelineResult(fetched=len(products))
        metrics.increment("pipeline.fetched", len(products))

        for product in products:
            try:
                deal_id.set(product.asin or "no-asin")
                if await self._is_recent_duplicate(product):
                    result.deduped_out += 1
                    metrics.increment("pipeline.deduped_out")
                    continue

                affiliate_link = self.affiliate_link_builder(product.link)
                message = await self.content_generator.generate_telegram_message(product, affiliate_link)

                await self._publish(product, message)
                await self._save(product, affiliate_link)

                result.posted += 1
                metrics.increment("pipeline.posted")
                await asyncio.sleep(2)
            except Exception as e:
                result.failed += 1
                result.errors.append(str(e))
                metrics.increment("pipeline.failed")
                logger.error(f"[PIPELINE] Failed posting {product.title[:50]}...: {e}")

        logger.info(
            f"[PIPELINE] Completed run={run} fetched={result.fetched} posted={result.posted} "
            f"deduped={result.deduped_out} failed={result.failed}"
        )
        return result

    async def _is_recent_duplicate(self, product: Product) -> bool:
        if not self.db_manager or not product.asin:
            return False

        existing = await self.db_manager.get_deal_by_asin(product.asin)
        if not existing or not getattr(existing, "posted_at", None):
            return False

        posted_at = existing.posted_at
        now = datetime.now(timezone.utc)
        posted_time = posted_at.replace(tzinfo=timezone.utc) if posted_at.tzinfo is None else posted_at
        return (now - posted_time) < timedelta(hours=self.dedupe_hours)

    async def _publish(self, product: Product, message: str) -> None:
        if not self.telegram_channel or not self.telegram_client:
            return

        if product.image_url and product.image_url.strip():
            try:
                await self.telegram_client.send_photo(
                    chat_id=self.telegram_channel,
                    photo=product.image_url,
                    caption=message,
                    parse_mode="Markdown",
                )
                return
            except Exception as img_error:
                logger.warning(f"[PIPELINE] Image send failed, fallback to text: {img_error}")

        await self.telegram_client.send_message(
            chat_id=self.telegram_channel,
            text=message,
            parse_mode="Markdown",
            disable_web_page_preview=False,
        )

    async def _save(self, product: Product, affiliate_link: str) -> None:
        if not self.db_manager:
            return

        await self.db_manager.add_deal(
            product=product,
            affiliate_link=affiliate_link,
            source=self.source,
            content_style=self.content_style,
        )
