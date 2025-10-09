from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Product:
    title: str
    price: str
    discount: str
    link: str
    category: str
    asin: str = ""
    description: str = ""
    rating: float = 0.0
    review_count: int = 0
    image_url: str = ""
    features: list = field(default_factory=list)
    
    def is_valid(self) -> bool:
        return bool(self.title and self.price and self.link)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'price': self.price,
            'discount': self.discount,
            'link': self.link,
            'category': self.category,
            'asin': self.asin,
            'description': self.description,
            'rating': self.rating,
            'review_count': self.review_count,
            'image_url': self.image_url,
            'features': self.features
        }


@dataclass
class Deal:
    id: Optional[int] = None
    title: str = ""
    price: str = ""
    discount: str = ""
    category: str = ""
    source: str = ""
    asin: str = ""
    affiliate_link: str = ""
    original_link: str = ""
    description: str = ""
    generated_content: str = ""
    content_style: str = "simple"
    rating: float = 0.0
    review_count: int = 0
    image_url: str = ""
    clicks: int = 0
    conversions: int = 0
    earnings: float = 0.0
    posted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True
    
    def to_product(self) -> Product:
        return Product(
            title=self.title,
            price=self.price,
            discount=self.discount,
            link=self.original_link or self.affiliate_link,
            category=self.category,
            asin=self.asin,
            description=self.description,
            rating=self.rating,
            review_count=self.review_count,
            image_url=self.image_url
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'price': self.price,
            'discount': self.discount,
            'category': self.category,
            'source': self.source,
            'asin': self.asin,
            'affiliate_link': self.affiliate_link,
            'original_link': self.original_link,
            'description': self.description,
            'generated_content': self.generated_content,
            'content_style': self.content_style,
            'rating': self.rating,
            'review_count': self.review_count,
            'image_url': self.image_url,
            'clicks': self.clicks,
            'conversions': self.conversions,
            'earnings': self.earnings,
            'posted_at': self.posted_at.isoformat() if self.posted_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active
        }


@dataclass
class User:
    id: Optional[int] = None
    user_id: int = 0
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    category: str = "all"
    region: str = "US"
    language_code: str = "en"
    is_active: bool = True
    joined_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    total_clicks: int = 0
    total_conversions: int = 0
    total_earnings: float = 0.0
    
    def display_name(self) -> str:
        if self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User{self.user_id}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'category': self.category,
            'region': self.region,
            'language_code': self.language_code,
            'is_active': self.is_active,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'total_clicks': self.total_clicks,
            'total_conversions': self.total_conversions,
            'total_earnings': self.total_earnings,
            'display_name': self.display_name()
        }


@dataclass
class DealStats:
    total_deals: int = 0
    recent_deals: int = 0
    total_clicks: int = 0
    total_conversions: int = 0
    total_earnings: float = 0.0
    active_users: int = 0
    category_stats: Dict[str, int] = field(default_factory=dict)
    source_stats: Dict[str, int] = field(default_factory=dict)
    
    def conversion_rate(self) -> float:
        if self.total_clicks == 0:
            return 0.0
        return (self.total_conversions / self.total_clicks) * 100
    
    def average_earnings_per_deal(self) -> float:
        if self.total_deals == 0:
            return 0.0
        return self.total_earnings / self.total_deals
    
    def average_earnings_per_click(self) -> float:
        if self.total_clicks == 0:
            return 0.0
        return self.total_earnings / self.total_clicks
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_deals': self.total_deals,
            'recent_deals': self.recent_deals,
            'total_clicks': self.total_clicks,
            'total_conversions': self.total_conversions,
            'total_earnings': self.total_earnings,
            'active_users': self.active_users,
            'conversion_rate': self.conversion_rate(),
            'average_earnings_per_deal': self.average_earnings_per_deal(),
            'average_earnings_per_click': self.average_earnings_per_click(),
            'category_stats': self.category_stats,
            'source_stats': self.source_stats
        }


@dataclass
class ClickEvent:
    id: Optional[int] = None
    deal_id: int = 0
    user_id: int = 0
    clicked_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    referrer: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'deal_id': self.deal_id,
            'user_id': self.user_id,
            'clicked_at': self.clicked_at.isoformat() if self.clicked_at else None,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'referrer': self.referrer
        }


CATEGORY_MAPPING = {
    'electronics': '📱 Electronics',
    'home': '🏠 Home & Kitchen',
    'fashion': '👕 Fashion',
    'sports': '⚽ Sports & Outdoors',
    'beauty': '💄 Beauty & Personal Care',
    'books': '📚 Books',
    'tools': '🔧 Tools & Hardware',
    'automotive': '🚗 Automotive',
    'toys': '🧸 Toys & Games',
    'office': '📋 Office Products',
    'health': '🏥 Health & Wellness',
    'garden': '🌱 Garden & Outdoor',
    'pet': '🐕 Pet Supplies',
    'baby': '👶 Baby Products',
    'music': '🎵 Music & Audio',
    'movies': '🎬 Movies & TV',
    'gaming': '🎮 Gaming',
    'arts': '🎨 Arts & Crafts',
    'industrial': '🏭 Industrial & Scientific',
    'grocery': '🛒 Grocery & Food'
}

CONTENT_STYLES = {
    'simple': 'Simple and direct',
    'enthusiastic': 'Enthusiastic and engaging',
    'professional': 'Professional and informative',
    'casual': 'Casual and friendly',
    'urgent': 'Urgent and time-sensitive'
}

SUPPORTED_REGIONS = {
    'US': '🇺🇸 United States',
    'UK': '🇬🇧 United Kingdom',
    'DE': '🇩🇪 Germany',
    'FR': '🇫🇷 France',
    'CA': '🇨🇦 Canada',
    'JP': '🇯🇵 Japan',
    'AU': '🇦🇺 Australia',
    'IN': '🇮🇳 India'
}
