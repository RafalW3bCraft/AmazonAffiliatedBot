import asyncio
from unittest.mock import AsyncMock, MagicMock

from services.deal_pipeline_service import DealPipelineService, PipelineResult
from models import Product


def test_pipeline_happy_path_posts_one_deal():
    db = AsyncMock()
    db.get_deal_by_asin.return_value = None
    db.add_deal.return_value = True

    content = AsyncMock()
    content.generate_telegram_message.return_value = "Deal content"

    publisher = AsyncMock()

    service = DealPipelineService(
        db_manager=db,
        content_generator=content,
        affiliate_link_builder=lambda url: f"{url}?tag=test-21",
        telegram_client=publisher,
        telegram_channel="@test_channel",
    )

    products = [
        Product(
            title="Product 1",
            price="$9.99",
            discount="20% off",
            link="https://www.amazon.com/dp/B0C1234567",
            category="electronics",
            asin="B0C1234567",
        )
    ]

    result = asyncio.run(service.post_products(products))

    assert isinstance(result, PipelineResult)
    assert result.posted == 1
    assert result.failed == 0
    publisher.send_message.assert_awaited()
    db.add_deal.assert_awaited()


def test_pipeline_skips_recent_duplicate():
    existing = MagicMock()
    from datetime import datetime, timezone
    existing.posted_at = datetime.now(timezone.utc)

    db = AsyncMock()
    db.get_deal_by_asin.return_value = existing

    content = AsyncMock()
    publisher = AsyncMock()

    service = DealPipelineService(
        db_manager=db,
        content_generator=content,
        affiliate_link_builder=lambda url: f"{url}?tag=test-21",
        telegram_client=publisher,
        telegram_channel="@test_channel",
        dedupe_hours=24,
    )

    products = [
        Product(
            title="Product 1",
            price="$9.99",
            discount="20% off",
            link="https://www.amazon.com/dp/B0C1234567",
            category="electronics",
            asin="B0C1234567",
        )
    ]

    result = asyncio.run(service.post_products(products))

    assert result.posted == 0
    assert result.deduped_out == 1
    publisher.send_message.assert_not_awaited()
