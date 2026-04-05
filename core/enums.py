"""Canonical enums used across layers."""

from enum import Enum


class Category(str, Enum):
    ELECTRONICS = "electronics"
    FASHION = "fashion"
    HOME = "home"
    BOOKS = "books"
    SPORTS = "sports"
    BEAUTY = "beauty"
    GENERAL = "general"


class Region(str, Enum):
    US = "US"
    UK = "UK"
    DE = "DE"
    FR = "FR"
    CA = "CA"
    JP = "JP"
    AU = "AU"
    IN = "IN"


class DealSource(str, Enum):
    SCRAPER = "scraper"
    MANUAL = "manual"
