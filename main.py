#!/usr/bin/env python3

import asyncio
import logging
import signal
import sys
import threading
from typing import Optional

import dotenv

# Load environment variables
dotenv.load_dotenv()

if sys.version_info < (3, 11):
    print(f"[FATAL] Python 3.11+ required. Current: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)


from config import Config
from telegram_bot import AffiliateBot
from web_dashboard_clean import create_app
from scheduler import TaskScheduler
from database import DatabaseManager
from database_simple import SimpleDatabaseManager
from content_generator import ContentGenerator
from scraper import DealScraper
from services.deal_pipeline_service import DealPipelineService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('dealbot.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


def check_python_runtime() -> bool:
    """Return True for recommended runtime (3.11+), False otherwise."""
    return sys.version_info >= (3, 11)


class DealBotApplication:
    
    
    def __init__(self):
        
        self.config = Config()
        self.running = False
        self.bot: Optional[AffiliateBot] = None
        self.db_manager = None  # Can be DatabaseManager or SimpleDatabaseManager
        self.scheduler: Optional[TaskScheduler] = None
        self.web_app = None
        self.web_thread: Optional[threading.Thread] = None
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    async def initialize(self) -> bool:
        
        try:
            logger.info("🚀 Initializing Amazon Affiliate Deal Bot...")
            
            # Validate configuration
            if not self.config.validate():
                logger.error("❌ Configuration validation failed")
                return False
            
            # Initialize database manager (prevent multiple initializations)
            if not self.db_manager:
                try:
                    if self.config.database_configured:
                        self.db_manager = DatabaseManager(self.config.DATABASE_URL)
                        logger.info("📊 Using PostgreSQL database")
                        await self.db_manager.initialize()
                    else:
                        self.db_manager = SimpleDatabaseManager()
                        logger.info("📊 Using in-memory database")
                        await self.db_manager.initialize()
                except Exception as e:
                    logger.warning(f"Database initialization failed: {e}, falling back to in-memory database")
                    self.db_manager = SimpleDatabaseManager()
                    await self.db_manager.initialize()
            else:
                logger.info("📊 Database manager already initialized")
            
            # Initialize Telegram bot
            if self.config.bot_configured:
                self.bot = AffiliateBot(self.config, db_manager=self.db_manager)
                await self.bot.initialize()
                logger.info("🤖 Telegram bot initialized")
            else:
                logger.warning("⚠️ Telegram bot not configured (missing BOT_TOKEN)")
            
            # Initialize task scheduler
            if self.bot:
                self.scheduler = TaskScheduler(self.bot, self.config)
                logger.info("⏰ Task scheduler initialized")
            
            # Initialize web dashboard
            self.web_app = create_app(self.config)
            logger.info("🌐 Web dashboard initialized")
            
            logger.info("✅ All components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False
    
    async def start_bot_only(self):
        
        if not self.bot:
            logger.error("❌ Bot not initialized")
            return
        
        try:
            logger.info("🤖 Starting Telegram bot only...")
            await self.bot.start_polling()
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
    
    async def start_web_only(self):
        
        try:
            logger.info("🌐 Starting web dashboard only...")
            if self.web_app:
                self.web_app.run(
                    host=self.config.FLASK_HOST,
                    port=self.config.FLASK_PORT,
                    debug=False
                )
            else:
                logger.error("❌ Web app not initialized")
        except Exception as e:
            logger.error(f"❌ Web dashboard error: {e}")
    
    async def start_hybrid_mode(self):
        
        if not self.bot:
            logger.error("❌ Cannot start hybrid mode without bot")
            return
        
        try:
            logger.info("🚀 Starting hybrid mode (bot + web dashboard)...")
            
            # Start web dashboard in a separate thread with proper initialization
            import threading
            import time
            
            def run_web():
                try:
                    # Give a moment for the main thread to set up
                    time.sleep(1)
                    logger.info(f"🌐 Web dashboard thread starting on {self.config.FLASK_HOST}:{self.config.FLASK_PORT}")
                    if self.web_app:
                        self.web_app.run(
                            host=self.config.FLASK_HOST,
                            port=self.config.FLASK_PORT,
                            debug=False,
                            use_reloader=False,
                            threaded=True
                        )
                except Exception as e:
                    logger.error(f"Web dashboard thread error: {e}")
            
            self.web_thread = threading.Thread(target=run_web, daemon=True)
            self.web_thread.start()
            
            # Wait a moment for web server to start
            await asyncio.sleep(2)
            logger.info(f"🌐 Web dashboard should be running on http://{self.config.FLASK_HOST}:{self.config.FLASK_PORT}")
            
            # Start task scheduler
            if self.scheduler:
                scheduler_task = asyncio.create_task(self.scheduler.start())
                logger.info("⏰ Task scheduler started")
            
            # Start bot polling
            logger.info("🤖 Starting bot polling...")
            await self.bot.start_polling()
            
        except Exception as e:
            logger.error(f"❌ Hybrid mode error: {e}")
    

    
    async def post_deals(self) -> int:
        
        if not self.bot:
            logger.warning("⚠️ No bot available for posting deals")
            return 0
        
        try:
            from link_validator import LinkValidator
            
            # Get new deals from scraper
            scraper = DealScraper(
                max_deals_per_source=self.config.MAX_DEALS_PER_SOURCE
            )
            await scraper.initialize()
            
            deals = await scraper.scrape_real_amazon_deals()
            await scraper.close()
            
            if not deals:
                logger.warning("⚠️ No new deals found from scraper. This may indicate:")
                logger.warning("  1. Amazon HTML structure changed")
                logger.warning("  2. Rate limiting by Amazon")
                logger.warning("  3. Quality filters too strict")
                logger.warning("  4. Network connectivity issues")
                return 0
            
            # Validate all affiliate links before posting
            async with LinkValidator(expected_affiliate_tag=self.config.AMAZON_AFFILIATE_ID) as validator:
                affiliate_links = [self.config.get_affiliate_link(deal.link) for deal in deals]
                validation_results = await validator.validate_links_batch(affiliate_links)
                
                # Log validation statistics
                stats = validator.get_validation_stats(validation_results)
                logger.info(f"🔗 Link validation: {stats['valid_links']}/{stats['total_links']} valid ({stats['success_rate']:.1f}%)")
                
                # Filter deals to only include those with valid links
                valid_deals = []
                for deal, result in zip(deals, validation_results):
                    if result.is_valid:
                        valid_deals.append(deal)
                    else:
                        logger.warning(f"❌ Excluding deal with invalid link: {deal.title[:30]}... ({result.error_message})")
            
            if not valid_deals:
                logger.warning("⚠️ No deals with valid links found")
                return 0
            
            content_generator = ContentGenerator(self.config.OPENAI_API_KEY)
            await content_generator.initialize()
            try:
                pipeline = DealPipelineService(
                    db_manager=self.db_manager,
                    content_generator=content_generator,
                    affiliate_link_builder=self.config.get_affiliate_link,
                    telegram_client=self.bot.bot if self.bot else None,
                    telegram_channel=self.config.TELEGRAM_CHANNEL,
                    source="scraper",
                    content_style="enthusiastic",
                    dedupe_hours=2,
                )
                result = await pipeline.post_products(valid_deals)
            finally:
                await content_generator.close()



            pipeline = DealPipelineService(
                db_manager=self.db_manager,
                content_generator=content_generator,
                affiliate_link_builder=self.config.get_affiliate_link,
                telegram_client=self.bot.bot if self.bot else None,
                telegram_channel=self.config.TELEGRAM_CHANNEL,
                source="scraper",
                content_style="enthusiastic",
                dedupe_hours=2,
            )
            result = await pipeline.post_products(valid_deals)

            await content_generator.close()
            logger.info(
                f"📢 Pipeline cycle complete: fetched={result.fetched}, posted={result.posted}, "
                f"deduped={result.deduped_out}, failed={result.failed}"
            )
            return result.posted
            
        except Exception as e:
            logger.error(f"Error posting deals: {e}")
            return 0
    
    async def cleanup(self):
        
        try:
            logger.info("🧹 Cleaning up application resources...")
            
            # Stop scheduler
            if self.scheduler:
                await self.scheduler.stop()
            
            # Close bot
            if self.bot:
                await self.bot.cleanup()
            
            # Close database
            if self.db_manager:
                await self.db_manager.close()
            
            logger.info("✅ Cleanup completed")
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def test_mode(self):
        """Run a lightweight diagnostics pass without starting long-running services."""
        logger.info("🧪 Running diagnostics test mode...")

        diagnostics = {
            "config_valid": self.config.validate(),
            "bot_configured": self.config.bot_configured,
            "database_configured": self.config.database_configured,
            "web_ready": self.web_app is not None,
        }

        if self.db_manager:
            try:
                stats = await self.db_manager.get_deal_stats()
                diagnostics["database_connected"] = stats is not None
            except Exception as db_error:
                diagnostics["database_connected"] = False
                logger.warning(f"Database diagnostics check failed: {db_error}")
        else:
            diagnostics["database_connected"] = False

        for key, value in diagnostics.items():
            logger.info(f"🔍 {key}: {value}")


async def main():
    app = None
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--version-check":
            ok = check_python_runtime()
            if ok:
                print(f"Python version OK: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
                return 0
            print(
                f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} detected; "
                "3.11+ is recommended."
            )
            return 1

        app = DealBotApplication()

        if not check_python_runtime():
            logger.warning(
                f"⚠️ Running on Python {sys.version_info.major}.{sys.version_info.minor}. "
                "Python 3.11+ is recommended."
            )

            print(f"Python version OK: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
            return 0

        # Initialize application
        if not await app.initialize():
            logger.error("❌ Failed to initialize application")
            return 1
        
        # Check command line arguments
        if len(sys.argv) > 1:
            mode = sys.argv[1].lower()
            
            if mode == "bot":
                await app.start_bot_only()
            elif mode == "web":
                await app.start_web_only()
            elif mode == "test":
                await app.test_mode()
            elif mode == "post":
                count = await app.post_deals()
                print(f"Posted {count} deals")
            else:
                logger.error(f"Unknown mode: {mode}")
                return 1
        else:
            # Default: hybrid mode
            await app.start_hybrid_mode()
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("👋 Application stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Application error: {e}")
        return 1
    finally:
        if app:
            await app.cleanup()


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
