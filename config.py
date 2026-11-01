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
        
        # Use only AMAZON_AFFILIATE_ID - no fallback to AFFILIATE_ID
        amazon_affiliate_id = os.getenv('AMAZON_AFFILIATE_ID', '').strip()
        if not amazon_affiliate_id:
            logger.warning("⚠️ AMAZON_AFFILIATE_ID not configured - affiliate links will not work properly")
        # Validate affiliate ID format (alphanumeric + hyphens, typically 10-15 chars)
        if amazon_affiliate_id and not re.match(r'^[a-zA-Z0-9\-]{10,20}$', amazon_affiliate_id):
            logger.warning(f"⚠️ AMAZON_AFFILIATE_ID format may be invalid: {amazon_affiliate_id[:10]}...")
        self.AMAZON_AFFILIATE_ID = amazon_affiliate_id
        
        # Fix typo: TELEGRAM_CHENNAL -> TELEGRAM_CHANNEL (keep fallback for backward compatibility)
        self.TELEGRAM_CHANNEL = os.getenv('TELEGRAM_CHANNEL', os.getenv('TELEGRAM_CHENNAL', ''))
        
        self.MAX_DEALS_PER_SOURCE = int(os.getenv('MAX_DEALS_PER_SOURCE', '5'))
        self.POST_INTERVAL_MINUTES = int(os.getenv('POST_INTERVAL_MINUTES', '6'))
        self.REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
        self.RATE_LIMIT_DELAY = int(os.getenv('RATE_LIMIT_DELAY', '2'))
        
        self.FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
        self.FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))

        # Demo / offline mode: allows catalog browsing without secrets.
        self.DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() in ('1', 'true', 'yes')

        # Fail closed on missing Flask secret outside explicit demo mode.
        self.FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', '').strip()
        if not self.FLASK_SECRET_KEY:
            if self.DEMO_MODE:
                self.FLASK_SECRET_KEY = 'demo-only-insecure-secret'
                logger.warning("FLASK_SECRET_KEY not set - using demo-only secret (DEMO_MODE=true)")
            else:
                raise RuntimeError(
                    "FLASK_SECRET_KEY is required. Set a strong random secret in the environment, "
                    "or run with DEMO_MODE=true for offline catalog-only demos."
                )
        elif len(self.FLASK_SECRET_KEY) < 16 and not self.DEMO_MODE:
            raise RuntimeError("FLASK_SECRET_KEY is too short (<16 chars); refusing to start.")

        # Dashboard authentication for privileged routes (/users, /merchant, /api/users ...).
        self.DASHBOARD_TOKEN = os.getenv('DASHBOARD_TOKEN', '').strip()
        if not self.DASHBOARD_TOKEN and not self.DEMO_MODE:
            logger.warning(
                "DASHBOARD_TOKEN not set - privileged dashboard/API routes will be disabled"
            )

        # Feature gates
        self.ENABLE_MERCHANT_CHECKOUT = os.getenv('ENABLE_MERCHANT_CHECKOUT', 'true').lower() in ('1', 'true', 'yes')
        self.ENABLE_EXTERNAL_AFFILIATE = os.getenv('ENABLE_EXTERNAL_AFFILIATE', 'false').lower() in ('1', 'true', 'yes')
        self.DISABLE_UNVERIFIED_AMAZON_SCRAPING = os.getenv('DISABLE_UNVERIFIED_AMAZON_SCRAPING', 'true').lower() in ('1', 'true', 'yes')

        # PayPal sandbox settings (never live)
        self.PAYPAL_ENVIRONMENT = os.getenv('PAYPAL_ENVIRONMENT', 'sandbox').strip().lower()
        if self.PAYPAL_ENVIRONMENT != 'sandbox':
            raise RuntimeError(
                f"PAYPAL_ENVIRONMENT must be 'sandbox' for this application (got "
                f"'{self.PAYPAL_ENVIRONMENT}'). Live PayPal is not supported."
            )
        self.PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID', '').strip()
        self.PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET', '').strip()
        self.PAYPAL_WEBHOOK_ID = os.getenv('PAYPAL_WEBHOOK_ID', '').strip()
        self.PAYPAL_CURRENCY = os.getenv('PAYPAL_CURRENCY', 'USD').strip().upper()

        # An explicit provider wins; automatic selection is only used when unset.
        self.FEATHERLESS_API_KEY = os.getenv('FEATHERLESS_API_KEY', '').strip()
        self.FEATHERLESS_BASE_URL = os.getenv('FEATHERLESS_BASE_URL', 'https://api.featherless.ai/v1').strip()
        self.AI_MODEL = os.getenv('AI_MODEL', '').strip()
        configured_provider = os.getenv('AI_PROVIDER', '').strip().lower()
        if configured_provider and configured_provider not in {'openai', 'featherless'}:
            raise RuntimeError("AI_PROVIDER must be 'openai' or 'featherless'.")
        if configured_provider == 'openai' and not self.OPENAI_API_KEY:
            raise RuntimeError('AI_PROVIDER=openai requires OPENAI_API_KEY.')
        if configured_provider == 'featherless' and not self.FEATHERLESS_API_KEY:
            raise RuntimeError('AI_PROVIDER=featherless requires FEATHERLESS_API_KEY.')
        if configured_provider:
            self.AI_PROVIDER = configured_provider
        elif self.OPENAI_API_KEY:
            self.AI_PROVIDER = 'openai'
        elif self.FEATHERLESS_API_KEY:
            self.AI_PROVIDER = 'featherless'
        else:
            self.AI_PROVIDER = ''

        # Commerce guardrails
        self.MAX_CART_TOTAL = os.getenv('MAX_CART_TOTAL', '500.00').strip()
        self.CART_QUOTE_TTL_MINUTES = int(os.getenv('CART_QUOTE_TTL_MINUTES', '30'))
        self.COMMERCE_DATABASE_URL = os.getenv(
            'COMMERCE_DATABASE_URL',
            os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(os.path.dirname(__file__), 'commerce.db')}")
        )
        
        self.REGIONAL_AFFILIATE_IDS = {
            'US': self.AMAZON_AFFILIATE_ID,
            'UK': os.getenv('AMAZON_AFFILIATE_ID_UK', self.AMAZON_AFFILIATE_ID),
            'DE': os.getenv('AMAZON_AFFILIATE_ID_DE', self.AMAZON_AFFILIATE_ID),
            'FR': os.getenv('AMAZON_AFFILIATE_ID_FR', self.AMAZON_AFFILIATE_ID),
            'CA': os.getenv('AMAZON_AFFILIATE_ID_CA', self.AMAZON_AFFILIATE_ID),
            'JP': os.getenv('AMAZON_AFFILIATE_ID_JP', self.AMAZON_AFFILIATE_ID),
            'AU': os.getenv('AMAZON_AFFILIATE_ID_AU', self.AMAZON_AFFILIATE_ID),
            'IN': os.getenv('AMAZON_AFFILIATE_ID_IN', self.AMAZON_AFFILIATE_ID),
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
        logger.info(f"  🛒 Amazon Affiliate ID: {self.AMAZON_AFFILIATE_ID or 'Not configured'}")
        logger.info(f"  📢 Telegram channel: {self.TELEGRAM_CHANNEL or 'Not configured'}")
        logger.info(f"  🌍 Default region: {self.DEFAULT_REGION}")
    
    @property
    def bot_configured(self) -> bool:
        
        return bool(self.BOT_TOKEN)
    
    @property
    def openai_configured(self) -> bool:
        
        return bool(self.OPENAI_API_KEY)

    @property
    def ai_configured(self) -> bool:
        """True when any supported AI provider credential is present."""
        return bool(self.OPENAI_API_KEY or self.FEATHERLESS_API_KEY)

    @property
    def paypal_configured(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)

    @property
    def dashboard_auth_enabled(self) -> bool:
        return bool(self.DASHBOARD_TOKEN)
    
    @property
    def database_configured(self) -> bool:
        
        return bool(self.DATABASE_URL and self.DATABASE_URL.startswith('postgresql'))
    
    @property
    def POST_INTERVAL_HOURS(self) -> float:
        
        return self.POST_INTERVAL_MINUTES / 60.0
    
    def validate(self) -> bool:
        """Validate configuration. Returns False when a hard requirement for the
        enabled feature set is missing; logs warnings for optional degradations."""
        ok = True

        if not self.bot_configured:
            logger.warning("⚠️ BOT_TOKEN not configured - bot functionality disabled")

        if not self.ai_configured:
            logger.warning("⚠️ No AI provider key (OPENAI_API_KEY or FEATHERLESS_API_KEY) - "
                           "AI shopping will use the deterministic fallback, labeled as non-AI")

        if not self.database_configured:
            logger.warning("⚠️ DATABASE_URL not configured - deals lane uses in-memory database "
                           "(never used for payment records)")

        if self.ENABLE_EXTERNAL_AFFILIATE and not self.AMAZON_AFFILIATE_ID:
            logger.error("❌ ENABLE_EXTERNAL_AFFILIATE=true but AMAZON_AFFILIATE_ID is missing")
            ok = False

        if self.ENABLE_MERCHANT_CHECKOUT and not self.paypal_configured:
            logger.warning("⚠️ Merchant checkout enabled but PayPal sandbox credentials are missing - "
                           "checkout endpoints will return 503 until configured")

        return ok
    
    def get_affiliate_link(self, product_url: str, region: Optional[str] = None) -> str:
        
        if not product_url:
            logger.warning("Empty product URL provided to get_affiliate_link")
            return ""
        
        # Validate URL format
        if not (product_url.startswith('http://') or product_url.startswith('https://')):
            logger.warning(f"Invalid URL format: {product_url[:50]}...")
            return ""
        
        if not self.AMAZON_AFFILIATE_ID:
            logger.warning("AMAZON_AFFILIATE_ID not configured, cannot generate affiliate link")
            return product_url  # Return original URL if no affiliate ID
        
        region = region or self.DEFAULT_REGION
        affiliate_id = self.REGIONAL_AFFILIATE_IDS.get(region, self.AMAZON_AFFILIATE_ID)
        
        # Validate affiliate ID format
        if affiliate_id and not re.match(r'^[a-zA-Z0-9\-]{10,20}$', affiliate_id):
            logger.warning(f"Invalid affiliate ID format: {affiliate_id[:10]}...")
            return product_url
        
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
            'affiliate_id': self.REGIONAL_AFFILIATE_IDS.get(effective_region, self.AMAZON_AFFILIATE_ID)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        
        return {
            'bot_configured': self.bot_configured,
            'openai_configured': self.openai_configured,
            'database_configured': self.database_configured,
            'amazon_affiliate_id': self.AMAZON_AFFILIATE_ID,
            'telegram_channel': self.TELEGRAM_CHANNEL,
            'default_region': self.DEFAULT_REGION,
            'max_deals_per_source': self.MAX_DEALS_PER_SOURCE,
            'post_interval_minutes': self.POST_INTERVAL_MINUTES,
            'supported_regions': self.get_supported_regions()
        }
