from config import Config


def _set_safe_config(monkeypatch, **values):
    defaults = {
        "DEMO_MODE": "true",
        "AI_PROVIDER": "",
        "OPENAI_API_KEY": "",
        "FEATHERLESS_API_KEY": "",
    }
    defaults.update(values)
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)


def test_affiliate_link_generation_contains_tag(monkeypatch):
    monkeypatch.setenv("AMAZON_AFFILIATE_ID", "one4allmarket-21")
    cfg = Config()

    link = cfg.get_affiliate_link("https://www.amazon.com/dp/B0C1234567")

    assert "tag=one4allmarket-21" in link
    assert "/dp/B0C1234567" in link


def test_affiliate_link_invalid_url_returns_empty(monkeypatch):
    monkeypatch.setenv("AMAZON_AFFILIATE_ID", "one4allmarket-21")
    cfg = Config()

    assert cfg.get_affiliate_link("not-a-url") == ""


def test_explicit_ai_provider_takes_precedence(monkeypatch):
    _set_safe_config(
        monkeypatch,
        AI_PROVIDER="featherless",
        OPENAI_API_KEY="openai-test-key",
        FEATHERLESS_API_KEY="featherless-test-key",
    )
    assert Config().AI_PROVIDER == "featherless"


def test_selected_ai_provider_requires_its_key(monkeypatch):
    _set_safe_config(monkeypatch, AI_PROVIDER="openai")
    import pytest

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        Config()


def test_invalid_ai_provider_is_rejected(monkeypatch):
    _set_safe_config(monkeypatch, AI_PROVIDER="unknown")
    import pytest

    with pytest.raises(RuntimeError, match="AI_PROVIDER"):
        Config()
