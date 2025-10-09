import os
import re
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    
    
    def __init__(self):
        
        self.BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', os.getenv('BOT_TOKEN', ''))
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
        self.DATABASE_URL = os.getenv('DATABASE_URL', '')
        
        self.AFFILIATE_ID = os.getenv('AMAZON_AFFILIATE_ID', os.getenv('AFFILIATE_ID', 'youcanhaveita-21'))
        
        self.TELEGRAM_CHANNEL = os.getenv('TELEGRAM_CHANNEL', os.getenv('TELEGRAM_CHENNAL', '@one4all_market'))
        
        self.MAX_DEALS_PER_SOURCE = int(os.getenv('MAX_DEALS_PER_SOURCE', '5'))
        self.POST_INTERVAL_MINUTES = int(os.getenv('POST_INTERVAL_MINUTES', '6'))
        self.REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
        self.RATE_LIMIT_DELAY = int(os.getenv('RATE_LIMIT_DELAY', '2'))
        
        self.FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
        self.FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))
        self.FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
        
        self.REGIONAL_AFFILIATE_IDS = {
            'US': self.AFFILIATE_ID,
            'UK': os.getenv('AFFILIATE_ID_UK', self.AFFILIATE_ID),
            'DE': os.getenv('AFFILIATE_ID_DE', self.AFFILIATE_ID),
            'FR': os.getenv('AFFILIATE_ID_FR', self.AFFILIATE_ID),
            'CA': os.getenv('AFFILIATE_ID_CA', self.AFFILIATE_ID),
            'JP': os.getenv('AFFILIATE_ID_JP', self.AFFILIATE_ID),
            'AU': os.getenv('AFFILIATE_ID_AU', self.AFFILIATE_ID),
            'IN': os.getenv('AFFILIATE_ID_IN', self.AFFILIATE_ID),
        }
        
        self.REGIONAL_CURRENCIES = {
            'US': {'symbol': '$', 'code': 'USD', 'domain': 'amazon.com'},
            'UK': {'symbol': '£', 'code': 'GBP', 'domain': 'amazon.co.uk'},
            'DE': {'symbol': '€', 'code': 'EUR', 'domain': 'amazon.de'},
            'FR': {'symbol': '€', 'code': 'EUR', 'domain': 'amazon.fr'},
            'CA': {'symbol': 'C$', 'code': 'CAD', 'domain': 'amazon.ca'},
            'JP': {'symbol': '¥', 'code': 'JPY', 'domain': 'amazon.co.jp'},
            'AU': {'symbol': 'A$', 'code': 'AUD', 'domain': 'amazon.com.au'},
            'IN': {'symbol': '₹', 'code': 'INR', 'domain': 'amazon.in'},
        }
        
        self.DEFAULT_REGION = os.getenv('DEFAULT_REGION', 'US')
        
        admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
        self.ADMIN_USER_IDS = [int(uid.strip()) for uid in admin_ids_str.split(',') if uid.strip().isdigit()] if admin_ids_str else []
        
        self._log_configuration()
    
    def _log_configuration(self):
        
        logger.info("📋 Configuration loaded:")
        logger.info(f"  🤖 Bot configured: {self.bot_configured}")
        logger.info(f"  🧠 OpenAI configured: {self.openai_configured}")
        logger.info(f"  📊 Database configured: {self.database_configured}")
        logger.info(f"  🛒 Affiliate ID: {self.AFFILIATE_ID}")
        logger.info(f"  📢 Telegram channel: {self.TELEGRAM_CHANNEL or 'Not configured'}")
        logger.info(f"  🌍 Default region: {self.DEFAULT_REGION}")
    
    @property
    def bot_configured(self) -> bool:
        
        return bool(self.BOT_TOKEN)
    
    @property
    def openai_configured(self) -> bool:
        
        return bool(self.OPENAI_API_KEY)
    
    @property
    def database_configured(self) -> bool:
        
        return bool(self.DATABASE_URL and self.DATABASE_URL.startswith('postgresql'))
    
    @property
    def POST_INTERVAL_HOURS(self) -> float:
        
        return self.POST_INTERVAL_MINUTES / 60.0
    
    def validate(self) -> bool:
        
        if not self.bot_configured:
            logger.warning("⚠️ BOT_TOKEN not configured - bot functionality disabled")
        
        if not self.openai_configured:
            logger.warning("⚠️ OPENAI_API_KEY not configured - using fallback content generation")
        
        if not self.database_configured:
            logger.warning("⚠️ DATABASE_URL not configured - using in-memory database")
        return True
    
    def get_affiliate_link(self, product_url: str, region: Optional[str] = None) -> str:
        
        if not product_url:
            return ""
        
        region = region or self.DEFAULT_REGION
        affiliate_id = self.REGIONAL_AFFILIATE_IDS.get(region, self.AFFILIATE_ID)
        
        try:
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', product_url)
            if not asin_match:
                asin_match = re.search(r'/gp/product/([A-Z0-9]{10})', product_url)
            
            if asin_match:
                asin = asin_match.group(1)
                
                if 'amazon.co.uk' in product_url:
                    domain = 'amazon.co.uk'
                elif 'amazon.de' in product_url:
                    domain = 'amazon.de'
                elif 'amazon.fr' in product_url:
                    domain = 'amazon.fr'
                elif 'amazon.ca' in product_url:
                    domain = 'amazon.ca'
                elif 'amazon.com.au' in product_url:
                    domain = 'amazon.com.au'
                elif 'amazon.co.jp' in product_url:
                    domain = 'amazon.co.jp'
                elif 'amazon.in' in product_url:
                    domain = 'amazon.in'
                else:
                    domain = 'www.amazon.com'
                
                return f"https://{domain}/dp/{asin}?tag={affiliate_id}&linkCode=as2&camp=1789&creative=9325"
            
            separator = '&' if '?' in product_url else '?'
            return f"{product_url}{separator}tag={affiliate_id}&linkCode=as2&camp=1789&creative=9325"
            
        except Exception as e:
            logger.error(f"Error generating affiliate link: {e}")
            separator = '&' if '?' in product_url else '?'
            return f"{product_url}{separator}tag={affiliate_id}"
    
    def get_regional_currency(self, region: Optional[str] = None) -> Dict[str, str]:
        
        region = region or self.DEFAULT_REGION
        return self.REGIONAL_CURRENCIES.get(region, self.REGIONAL_CURRENCIES['US'])
    
    def format_price_for_region(self, price: str, region: Optional[str] = None) -> str:
        
        region = region or self.DEFAULT_REGION
        currency_info = self.get_regional_currency(region)
        
        try:
            numeric_price = re.sub(r'[^\d.,]', '', price)
            
            if ',' in numeric_price and '.' in numeric_price:
                numeric_price = numeric_price.replace(',', '')
            elif ',' in numeric_price and region in ['DE', 'FR']:
                numeric_price = numeric_price.replace(',', '.')
            
            price_value = float(numeric_price)
            
            if region == 'JP':
                return f"{currency_info['symbol']}{int(price_value):,}"
            else:
                return f"{currency_info['symbol']}{price_value:,.2f}"
                
        except (ValueError, TypeError):
            return f"{currency_info['symbol']}{price}"
    
    def get_supported_regions(self) -> list:
        
        return list(self.REGIONAL_CURRENCIES.keys())
    
    def get_region_info(self, region: Optional[str] = None) -> Dict[str, Any]:
        
        effective_region: str = region or self.DEFAULT_REGION
        
        if effective_region not in self.REGIONAL_CURRENCIES:
            effective_region = self.DEFAULT_REGION
        
        currency_info = self.REGIONAL_CURRENCIES[effective_region]
        
        return {
            'region': effective_region,
            'currency_symbol': currency_info['symbol'],
            'currency_code': currency_info['code'],
            'amazon_domain': currency_info['domain'],
            'affiliate_id': self.REGIONAL_AFFILIATE_IDS.get(effective_region, self.AFFILIATE_ID)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        
        return {
            'bot_configured': self.bot_configured,
            'openai_configured': self.openai_configured,
            'database_configured': self.database_configured,
            'affiliate_id': self.AFFILIATE_ID,
            'telegram_channel': self.TELEGRAM_CHANNEL,
            'default_region': self.DEFAULT_REGION,
            'max_deals_per_source': self.MAX_DEALS_PER_SOURCE,
            'post_interval_minutes': self.POST_INTERVAL_MINUTES,
            'supported_regions': self.get_supported_regions()
        }
