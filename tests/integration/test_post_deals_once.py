"""Regression test: DealBotApplication.post_deals must run the deal pipeline
EXACTLY once per invocation (duplicate-post bug fix in main.py).

All external components (scraper, link validator, content generator,
pipeline service) are replaced with counting fakes - no network, no real
Telegram, no AI provider calls.
"""
import asyncio
from types import SimpleNamespace

from models import Product


FAKE_PRODUCTS = [
    Product(
        title="Product One",
        price="$9.99",
        discount="20% off",
        link="https://www.amazon.com/dp/B0C1111111",
        category="electronics",
        asin="B0C1111111",
    ),
    Product(
        title="Product Two",
        price="$19.99",
        discount="30% off",
        link="https://www.amazon.com/dp/B0C2222222",
        category="home",
        asin="B0C2222222",
    ),
]


def test_post_deals_runs_pipeline_exactly_once(monkeypatch):
    # --- Fakes -------------------------------------------------------------
    scraper_calls = {"initialize": 0, "scrape": 0, "close": 0}

    class FakeScraper:
        def __init__(self, *args, **kwargs):
            pass

        async def initialize(self):
            scraper_calls["initialize"] += 1

        async def scrape_real_amazon_deals(self):
            scraper_calls["scrape"] += 1
            return list(FAKE_PRODUCTS)

        async def close(self):
            scraper_calls["close"] += 1

    class FakeValidationResult:
        is_valid = True
        error_message = None

    class FakeValidator:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def validate_links_batch(self, links):
            return [FakeValidationResult() for _ in links]

        def get_validation_stats(self, results):
            return {"valid_links": len(results), "total_links": len(results),
                    "success_rate": 100.0}

    generator_calls = {"initialize": 0, "close": 0, "generate": 0}

    class FakeContentGenerator:
        def __init__(self, *args, **kwargs):
            pass

        async def initialize(self):
            generator_calls["initialize"] += 1

        async def close(self):
            generator_calls["close"] += 1

        async def generate_telegram_message(self, product, affiliate_link, style="enthusiastic"):
            generator_calls["generate"] += 1
            return f"msg:{product.title}"

    pipeline_calls = []

    class FakePipelineResult:
        def __init__(self, products):
            self.fetched = len(products)
            self.posted = len(products)
            self.deduped_out = 0
            self.failed = 0

    class FakePipelineService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def post_products(self, products):
            pipeline_calls.append(list(products))
            return FakePipelineResult(products)

    # --- Patching (targets = where post_deals imports the names) -----------
    monkeypatch.setattr("main.DealScraper", FakeScraper)
    monkeypatch.setattr("main.ContentGenerator", FakeContentGenerator)
    monkeypatch.setattr("main.DealPipelineService", FakePipelineService)
    monkeypatch.setattr("link_validator.LinkValidator", FakeValidator)

    import main

    app = main.DealBotApplication.__new__(main.DealBotApplication)

    minimal_config = SimpleNamespace(
        MAX_DEALS_PER_SOURCE=5,
        AMAZON_AFFILIATE_ID="testaffiliate-20",
        OPENAI_API_KEY="",
        TELEGRAM_CHANNEL="@test_channel",
        get_affiliate_link=lambda url: f"{url}?tag=testaffiliate-20",
    )
    app.config = minimal_config
    app.bot = SimpleNamespace(bot=object())  # truthy bot with .bot telegram client
    app.db_manager = None

    posted = asyncio.run(app.post_deals())

    # --- Assertions ---------------------------------------------------------
    assert len(pipeline_calls) == 1, (
        f"pipeline.post_products must run exactly once, got {len(pipeline_calls)} calls"
    )
    assert pipeline_calls[0] == FAKE_PRODUCTS
    assert generator_calls["initialize"] == 1
    assert generator_calls["close"] == 1, (
        f"content generator must be closed exactly once, got {generator_calls['close']}"
    )
    assert posted == len(FAKE_PRODUCTS)
    assert scraper_calls == {"initialize": 1, "scrape": 1, "close": 1}
