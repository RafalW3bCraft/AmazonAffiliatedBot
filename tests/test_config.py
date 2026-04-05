from config import Config


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
