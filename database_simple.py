"""
Simple in-memory database manager for Amazon Affiliate Deal Bot.
Used as fallback when PostgreSQL is not available.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from models import Deal, User, DealStats, Product, ClickEvent

logger = logging.getLogger(__name__)


class SimpleDatabaseManager:
    """Simple in-memory database manager for development and testing."""
    
    def __init__(self):
        """Initialize in-memory storage."""
        self.users: Dict[int, User] = {}
        self.deals: Dict[int, Deal] = {}
        self.click_events: List[ClickEvent] = []
        self.next_deal_id = 1
        self.next_user_id = 1
        self.next_click_id = 1
        
        logger.info("📝 Simple in-memory database initialized")
    
    async def initialize(self):
        """Initialize database (no-op for in-memory)."""
        logger.info("✅ Simple database ready")
    
    async def close(self):
        """Close database (no-op for in-memory)."""
        logger.info("📊 Simple database closed")
    
    
    async def add_user(self, user_id: int, username: str = None, 
                      first_name: str = None, last_name: str = None) -> User:
        """Add or update user."""
        if user_id in self.users:
            user = self.users[user_id]
            user.last_seen = datetime.utcnow()
            return user
        else:
            user = User(
                id=self.next_user_id,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                joined_at=datetime.utcnow(),
                last_seen=datetime.utcnow()
            )
            self.users[user_id] = user
            self.next_user_id += 1
            
            logger.info(f"👤 New user added: {first_name or username or user_id}")
            return user
    
    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by Telegram user ID."""
        return self.users.get(user_id)
    
    async def update_user_preferences(self, user_id: int, category: str = None, 
                                    region: str = None) -> bool:
        """Update user preferences."""
        if user_id in self.users:
            user = self.users[user_id]
            if category:
                user.category = category
            if region:
                user.region = region
            user.last_seen = datetime.utcnow()
            return True
        return False
    
    async def get_active_users(self, days: int = 30) -> List[User]:
        """Get users active in the last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return [
            user for user in self.users.values()
            if user.is_active and user.last_seen and user.last_seen >= cutoff_date
        ]
    
    
    async def add_deal(self, product: Product, affiliate_link: str, 
                      source: str = "scraper", content_style: str = "simple") -> Deal:
        """Add a new deal."""
        deal = Deal(
            id=self.next_deal_id,
            title=product.title,
            price=product.price,
            discount=product.discount,
            category=product.category,
            source=source,
            asin=product.asin,
            affiliate_link=affiliate_link,
            original_link=product.link,
            description=product.description,
            content_style=content_style,
            rating=product.rating,
            review_count=product.review_count,
            image_url=product.image_url,
            posted_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.deals[deal.id] = deal
        self.next_deal_id += 1
        
        logger.info(f"💰 Deal added: {product.title[:50]}...")
        return deal
    
    async def get_deal(self, deal_id: int) -> Optional[Deal]:
        """Get deal by ID."""
        return self.deals.get(deal_id)
    
    async def get_deal_by_asin(self, asin: str) -> Optional[Deal]:
        """Get deal by ASIN."""
        for deal in self.deals.values():
            if deal.asin == asin and deal.is_active:
                return deal
        return None
    
    async def get_recent_deals(self, hours: int = 24, limit: int = 50, 
                             category: str = None) -> List[Deal]:
        """Get recent deals."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        filtered_deals = [
            deal for deal in self.deals.values()
            if (deal.is_active and 
                deal.posted_at and deal.posted_at >= cutoff_time and
                (not category or category == 'all' or deal.category == category))
        ]
        
        filtered_deals.sort(key=lambda x: x.posted_at or datetime.min, reverse=True)
        return filtered_deals[:limit]
    
    async def update_deal_stats(self, deal_id: int, clicks: int = 0, 
                               conversions: int = 0, earnings: float = 0.0) -> bool:
        """Update deal statistics."""
        if deal_id in self.deals:
            deal = self.deals[deal_id]
            deal.clicks += clicks
            deal.conversions += conversions
            deal.earnings += earnings
            deal.updated_at = datetime.utcnow()
            return True
        return False
    
    async def cleanup_old_deals(self, days: int = 30) -> int:
        """Clean up old deals."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        old_deal_ids = [
            deal_id for deal_id, deal in self.deals.items()
            if deal.posted_at and deal.posted_at < cutoff_date
        ]
        
        for deal_id in old_deal_ids:
            del self.deals[deal_id]
        
        logger.info(f"🧹 Cleaned up {len(old_deal_ids)} old deals")
        return len(old_deal_ids)
    
    
    async def get_deal_stats(self) -> DealStats:
        """Get comprehensive deal statistics."""
        active_deals = [deal for deal in self.deals.values() if deal.is_active]
        
        total_deals = len(active_deals)
        total_clicks = sum(deal.clicks for deal in active_deals)
        total_conversions = sum(deal.conversions for deal in active_deals)
        total_earnings = sum(deal.earnings for deal in active_deals)
        
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        recent_deals = len([
            deal for deal in active_deals
            if deal.posted_at and deal.posted_at >= cutoff_time
        ])
        
        active_users = len(await self.get_active_users(30))
        
        category_stats = {}
        for deal in active_deals:
            category = deal.category or 'unknown'
            category_stats[category] = category_stats.get(category, 0) + 1
        
        source_stats = {}
        for deal in active_deals:
            source = deal.source or 'unknown'
            source_stats[source] = source_stats.get(source, 0) + 1
        
        return DealStats(
            total_deals=total_deals,
            recent_deals=recent_deals,
            total_clicks=total_clicks,
            total_conversions=total_conversions,
            total_earnings=total_earnings,
            active_users=active_users,
            category_stats=category_stats,
            source_stats=source_stats
        )
    
    async def record_click_event(self, deal_id: int, user_id: int, 
                                ip_address: str = None, user_agent: str = None,
                                referrer: str = None) -> ClickEvent:
        """Record a click event."""
        click_event = ClickEvent(
            id=self.next_click_id,
            deal_id=deal_id,
            user_id=user_id,
            clicked_at=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent,
            referrer=referrer
        )
        
        self.click_events.append(click_event)
        self.next_click_id += 1
        
        if deal_id in self.deals:
            self.deals[deal_id].clicks += 1
            self.deals[deal_id].updated_at = datetime.utcnow()
        
        return click_event
