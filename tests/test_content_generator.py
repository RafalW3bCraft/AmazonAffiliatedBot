"""Unit tests for content_generator.ContentGenerator.

No network access: all AI client construction is faked, and tests rely on
env manipulation via monkeypatch.
"""
import asyncio

import pytest

from content_generator import ContentGenerator
from models import Product

ENV_VARS = ("OPENAI_API_KEY", "FEATHERLESS_API_KEY", "FEATHERLESS_BASE_URL", "AI_MODEL")


@pytest.fixture
def clean_env(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def make_product() -> Product:
    return Product(
        title="Test Widget 3000",
        price="$19.99",
        discount="50% off",
        link="https://www.amazon.com/dp/B012345678",
        category="electronics",
        asin="B012345678",
        rating=4.5,
        review_count=123,
    )


class TestNoProviderFallback:
    def test_no_keys_uses_fallback_and_provider_none(self, clean_env):
        gen = ContentGenerator()
        assert gen.provider_name == "none"
        assert gen.fallback_mode is True

    def test_fallback_message_has_no_ai_claims(self, clean_env):
        gen = ContentGenerator()
        product = make_product()
        for style in ("enthusiastic", "professional", "simple"):
            msg = gen._generate_fallback_message(product, "https://amzn.to/x", style)
            assert "AI-generated" not in msg
            assert "AI generated" not in msg
            assert "AI-enhanced" not in msg
            assert "AI-powered" not in msg
            assert "AI" not in msg.split()  # no standalone 'AI' token
        desc = gen._generate_fallback_description(product, "simple")
        assert "AI" not in desc.split()
        welcome = gen._generate_fallback_welcome("Alice")
        assert "AI" not in welcome.split()

    def test_fallback_message_includes_link_and_title(self, clean_env):
        gen = ContentGenerator()
        product = make_product()
        link = "https://www.amazon.com/dp/B012345678?tag=test-21"
        for style in ("enthusiastic", "professional", "simple"):
            msg = gen._generate_fallback_message(product, link, style)
            assert link in msg
            assert product.title in msg

    def test_generate_telegram_message_fallback(self, clean_env):
        gen = ContentGenerator()
        product = make_product()
        link = "https://www.amazon.com/dp/B012345678?tag=test-21"
        msg = asyncio.run(gen.generate_telegram_message(product, link))
        assert link in msg
        assert product.title in msg
        assert "AI" not in msg.split()


class TestClosedGuard:
    def test_generate_after_close_raises(self, clean_env):
        gen = ContentGenerator()
        asyncio.run(gen.close())
        with pytest.raises(RuntimeError, match="ContentGenerator is closed"):
            asyncio.run(gen.generate_telegram_message(make_product(), "https://x"))

    def test_description_after_close_raises(self, clean_env):
        gen = ContentGenerator()
        asyncio.run(gen.close())
        with pytest.raises(RuntimeError, match="ContentGenerator is closed"):
            asyncio.run(gen.generate_deal_description(make_product()))

    def test_welcome_after_close_raises(self, clean_env):
        gen = ContentGenerator()
        asyncio.run(gen.close())
        with pytest.raises(RuntimeError, match="ContentGenerator is closed"):
            asyncio.run(gen.generate_welcome_message("Alice"))

    def test_sentiment_after_close_raises(self, clean_env):
        gen = ContentGenerator()
        asyncio.run(gen.close())
        with pytest.raises(RuntimeError, match="ContentGenerator is closed"):
            asyncio.run(gen.analyze_product_sentiment(make_product()))

    def test_close_is_idempotent(self, clean_env):
        gen = ContentGenerator()
        asyncio.run(gen.close())
        asyncio.run(gen.close())  # no error


class TestModelSelection:
    def test_openai_default_model_is_gpt4o_mini(self, clean_env, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        gen = ContentGenerator()
        assert gen.provider_name == "openai"
        assert gen.model == "gpt-4o-mini"

    def test_env_ai_model_respected_for_openai(self, clean_env, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("AI_MODEL", "gpt-4o")
        gen = ContentGenerator()
        assert gen.provider_name == "openai"
        assert gen.model == "gpt-4o"

    def test_explicit_model_overrides_env(self, clean_env, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("AI_MODEL", "gpt-4o")
        gen = ContentGenerator(model="custom-model-1")
        assert gen.model == "custom-model-1"

    def test_explicit_key_positional_first_arg(self, clean_env):
        # main.py calls ContentGenerator(self.config.OPENAI_API_KEY) positionally.
        gen = ContentGenerator("sk-explicit")
        assert gen.provider_name == "openai"
        assert gen.model == "gpt-4o-mini"


class TestFeatherless:
    def test_featherless_provider_with_model(self, clean_env, monkeypatch):
        monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test")
        monkeypatch.setenv("AI_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
        gen = ContentGenerator()
        assert gen.provider_name == "featherless"
        assert gen.model == "meta-llama/Meta-Llama-3.1-8B-Instruct"
        assert gen.base_url == "https://api.featherless.ai/v1"
        assert gen.fallback_mode is False

    def test_featherless_custom_base_url(self, clean_env, monkeypatch):
        monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test")
        monkeypatch.setenv("FEATHERLESS_BASE_URL", "https://example.test/v1")
        monkeypatch.setenv("AI_MODEL", "some-model")
        gen = ContentGenerator()
        assert gen.provider_name == "featherless"
        assert gen.base_url == "https://example.test/v1"

    def test_featherless_without_model_falls_back(self, clean_env, monkeypatch):
        monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test")
        # AI_MODEL intentionally unset.
        gen = ContentGenerator()
        assert gen.provider_name == "none"
        assert gen.fallback_mode is True
        assert gen.client is None

    def test_openai_key_wins_over_featherless(self, clean_env, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("FEATHERLESS_API_KEY", "fl-test")
        monkeypatch.setenv("AI_MODEL", "some-model")
        gen = ContentGenerator()
        assert gen.provider_name == "openai"
