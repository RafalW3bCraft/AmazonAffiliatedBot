
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import asyncpg
from models import Deal, User, DealStats, Product, ClickEvent

logger = logging.getLogger(__name__)


class DatabaseManager:
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        
    async def initialize(self):
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60,
                ssl='require'
            )
            
            await self._create_tables()
            
            logger.info("✅ PostgreSQL database initialized")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("📊 Database connections closed")
    
    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    category VARCHAR(50) DEFAULT 'all',
                    region VARCHAR(10) DEFAULT 'US',
                    language_code VARCHAR(10) DEFAULT 'en',
                    is_active BOOLEAN DEFAULT TRUE,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_clicks INTEGER DEFAULT 0,
                    total_conversions INTEGER DEFAULT 0,
                    total_earnings DECIMAL(10,2) DEFAULT 0.00
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS deals (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    price VARCHAR(50),
                    discount VARCHAR(50),
                    category VARCHAR(50),
                    source VARCHAR(100),
                    asin VARCHAR(20),
                    affiliate_link TEXT,
                    original_link TEXT,
                    description TEXT,
                    generated_content TEXT,
                    content_style VARCHAR(50) DEFAULT 'simple',
                    rating DECIMAL(3,2) DEFAULT 0.00,
                    review_count INTEGER DEFAULT 0,
                    image_url TEXT,
                    clicks INTEGER DEFAULT 0,
                    conversions INTEGER DEFAULT 0,
                    earnings DECIMAL(10,2) DEFAULT 0.00,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS click_events (
                    id SERIAL PRIMARY KEY,
                    deal_id INTEGER REFERENCES deals(id) ON DELETE CASCADE,
                    user_id BIGINT,
                    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address INET,
                    user_agent TEXT,
                    referrer TEXT
                )
            """)
            
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_deals_asin ON deals(asin)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_deals_posted_at ON deals(posted_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_deals_category ON deals(category)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_click_events_deal_id ON click_events(deal_id)")
            
            logger.info("📋 Database tables created/verified")
    
    
    async def add_user(self, user_id: int, username: str = None, 
                      first_name: str = None, last_name: str = None) -> User:
        """Add or update user in database."""
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            
            if existing:
                await conn.execute(
                    "UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = $1",
                    user_id
                )
                return self._row_to_user(existing)
            else:
                row = await conn.fetchrow("""
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES ($1, $2, $3, $4)
                    RETURNING *
                """, user_id, username, first_name, last_name)
                
                logger.info(f"👤 New user added: {first_name or username or user_id}")
                return self._row_to_user(row)
    
    async def get_user(self, user_id: int) -> Optional[User]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            return self._row_to_user(row) if row else None
    
    async def update_user_preferences(self, user_id: int, category: str = None, 
                                    region: str = None) -> bool:
        """Update user preferences."""
        async with self.pool.acquire() as conn:
            updates = []
            values = []
            param_count = 1
            
            if category:
                updates.append(f"category = ${param_count}")
                values.append(category)
                param_count += 1
            
            if region:
                updates.append(f"region = ${param_count}")
                values.append(region)
                param_count += 1
            
            if updates:
                updates.append(f"last_seen = CURRENT_TIMESTAMP")
                values.append(user_id)
                
                query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ${param_count}"
                result = await conn.execute(query, *values)
                return result != "UPDATE 0"
            
            return False
    
    async def get_active_users(self, days: int = 30) -> List[User]:
        async with self.pool.acquire() as conn:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            rows = await conn.fetch("""
                SELECT * FROM users 
                WHERE is_active = TRUE AND last_seen >= $1
                ORDER BY last_seen DESC
            """, cutoff_date)
            
            return [self._row_to_user(row) for row in rows]
    
    
    async def add_deal(self, product: Product, affiliate_link: str, 
                      source: str = "scraper", content_style: str = "simple") -> Deal:
        """Add a new deal to database."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO deals (
                    title, price, discount, category, source, asin,
                    affiliate_link, original_link, description,
                    content_style, rating, review_count, image_url
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING *
            """, 
                product.title, product.price, product.discount, product.category,
                source, product.asin, affiliate_link, product.link,
                product.description, content_style, product.rating,
                product.review_count, product.image_url
            )
            
            logger.info(f"💰 Deal added: {product.title[:50]}...")
            return self._row_to_deal(row)
    
    async def get_deal(self, deal_id: int) -> Optional[Deal]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM deals WHERE id = $1", deal_id
            )
            return self._row_to_deal(row) if row else None
    
    async def get_deal_by_asin(self, asin: str) -> Optional[Deal]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM deals WHERE asin = $1 ORDER BY posted_at DESC LIMIT 1", 
                asin
            )
            return self._row_to_deal(row) if row else None
    
    async def get_recent_deals(self, hours: int = 24, limit: int = 50, 
                             category: str = None) -> List[Deal]:
        """Get recent deals."""
        async with self.pool.acquire() as conn:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            if category and category != 'all':
                query = """
                    SELECT * FROM deals 
                    WHERE is_active = TRUE AND posted_at >= $1 AND category = $2
                    ORDER BY posted_at DESC LIMIT $3
                """
                rows = await conn.fetch(query, cutoff_time, category, limit)
            else:
                query = """
                    SELECT * FROM deals 
                    WHERE is_active = TRUE AND posted_at >= $1
                    ORDER BY posted_at DESC LIMIT $2
                """
                rows = await conn.fetch(query, cutoff_time, limit)
            
            return [self._row_to_deal(row) for row in rows]
    
    async def update_deal_stats(self, deal_id: int, clicks: int = 0, 
                               conversions: int = 0, earnings: float = 0.0) -> bool:
        """Update deal statistics."""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE deals SET 
                    clicks = clicks + $1,
                    conversions = conversions + $2,
                    earnings = earnings + $3,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
            """, clicks, conversions, earnings, deal_id)
            
            return result != "UPDATE 0"
    
    async def cleanup_old_deals(self, days: int = 30) -> int:
        async with self.pool.acquire() as conn:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            result = await conn.execute(
                "DELETE FROM deals WHERE posted_at < $1", cutoff_date
            )
            
            deleted_count = int(result.split()[-1]) if result.startswith("DELETE") else 0
            logger.info(f"🧹 Cleaned up {deleted_count} old deals")
            return deleted_count
    
    
    async def get_deal_stats(self) -> DealStats:
        async with self.pool.acquire() as conn:
            basic_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_deals,
                    SUM(clicks) as total_clicks,
                    SUM(conversions) as total_conversions,
                    SUM(earnings) as total_earnings
                FROM deals 
                WHERE is_active = TRUE
            """)
            
            recent_count = await conn.fetchval("""
                SELECT COUNT(*) FROM deals 
                WHERE is_active = TRUE 
                AND posted_at >= NOW() - INTERVAL '24 hours'
            """)
            
            active_users = await conn.fetchval("""
                SELECT COUNT(*) FROM users 
                WHERE is_active = TRUE 
                AND last_seen >= NOW() - INTERVAL '30 days'
            """)
            
            category_rows = await conn.fetch("""
                SELECT category, COUNT(*) as count
                FROM deals 
                WHERE is_active = TRUE
                GROUP BY category
                ORDER BY count DESC
            """)
            
            source_rows = await conn.fetch("""
                SELECT source, COUNT(*) as count
                FROM deals 
                WHERE is_active = TRUE
                GROUP BY source
                ORDER BY count DESC
            """)
            
            return DealStats(
                total_deals=basic_stats['total_deals'] or 0,
                recent_deals=recent_count or 0,
                total_clicks=basic_stats['total_clicks'] or 0,
                total_conversions=basic_stats['total_conversions'] or 0,
                total_earnings=float(basic_stats['total_earnings'] or 0),
                active_users=active_users or 0,
                category_stats={row['category']: row['count'] for row in category_rows},
                source_stats={row['source']: row['count'] for row in source_rows}
            )
    
    async def record_click_event(self, deal_id: int, user_id: int, 
                                ip_address: str = None, user_agent: str = None,
                                referrer: str = None) -> ClickEvent:
        """Record a click event."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO click_events (deal_id, user_id, ip_address, user_agent, referrer)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
            """, deal_id, user_id, ip_address, user_agent, referrer)
            
            await conn.execute(
                "UPDATE deals SET clicks = clicks + 1 WHERE id = $1", deal_id
            )
            
            return self._row_to_click_event(row)
    
    
    def _row_to_user(self, row) -> User:
        return User(
            id=row['id'],
            user_id=row['user_id'],
            username=row['username'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            category=row['category'],
            region=row['region'],
            language_code=row['language_code'],
            is_active=row['is_active'],
            joined_at=row['joined_at'],
            last_seen=row['last_seen'],
            total_clicks=row['total_clicks'],
            total_conversions=row['total_conversions'],
            total_earnings=float(row['total_earnings'])
        )
    
    def _row_to_deal(self, row) -> Deal:
        return Deal(
            id=row['id'],
            title=row['title'],
            price=row['price'],
            discount=row['discount'],
            category=row['category'],
            source=row['source'],
            asin=row['asin'],
            affiliate_link=row['affiliate_link'],
            original_link=row['original_link'],
            description=row['description'],
            generated_content=row['generated_content'],
            content_style=row['content_style'],
            rating=float(row['rating']) if row['rating'] else 0.0,
            review_count=row['review_count'],
            image_url=row['image_url'],
            clicks=row['clicks'],
            conversions=row['conversions'],
            earnings=float(row['earnings']),
            posted_at=row['posted_at'],
            updated_at=row['updated_at'],
            is_active=row['is_active']
        )
    
    def _row_to_click_event(self, row) -> ClickEvent:
        return ClickEvent(
            id=row['id'],
            deal_id=row['deal_id'],
            user_id=row['user_id'],
            clicked_at=row['clicked_at'],
            ip_address=str(row['ip_address']) if row['ip_address'] else None,
            user_agent=row['user_agent'],
            referrer=row['referrer']
        )
