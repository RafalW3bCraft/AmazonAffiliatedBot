"""Typed project error hierarchy."""


class AffiliateError(Exception):
    """Base exception for all project errors."""


class ScraperError(AffiliateError):
    """Raised when scraping fails."""


class LinkValidationError(AffiliateError):
    """Raised when affiliate link is invalid."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Invalid link [{reason}]: {url}")


class PublishError(AffiliateError):
    """Raised when Telegram posting fails."""


class DatabaseError(AffiliateError):
    """Raised on storage failures."""


class ConfigError(AffiliateError):
    """Raised on invalid or missing configuration."""
