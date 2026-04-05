import asyncio
import logging
from typing import Optional, Union

try:
    from aiogram import Bot, Dispatcher, types, F
    from aiogram.filters import Command
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.exceptions import TelegramAPIError
    AIOGRAM_AVAILABLE = True
except ImportError:
    AIOGRAM_AVAILABLE = False
    class Bot: pass
    class Dispatcher: pass
    class InlineKeyboardMarkup: pass
    class InlineKeyboardButton: pass
    class F: pass
    def Command(**kwargs): pass

from config import Config
from database import DatabaseManager
from database_simple import SimpleDatabaseManager
from content_generator import ContentGenerator
from scraper import DealScraper
from services.deal_pipeline_service import DealPipelineService

logger = logging.getLogger(__name__)
TELEGRAM_RATE_LIMIT_SECONDS = 1.0


class AffiliateBot:
    
    def __init__(self, config: Config, db_manager: Optional[Union[DatabaseManager, SimpleDatabaseManager]] = None):
        if not AIOGRAM_AVAILABLE:
            raise ImportError("aiogram is required for Telegram bot functionality")
        
        self.config = config
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.db_manager: Optional[Union[DatabaseManager, SimpleDatabaseManager]] = db_manager
        self.manage_db_lifecycle = db_manager is None
        self.content_generator: Optional[ContentGenerator] = None
        self.scraper: Optional[DealScraper] = None
        
        self._initialize_components()
    
    def _initialize_components(self):
        if not self.config.bot_configured:
            raise ValueError("Bot token not configured")
        
        self.bot = Bot(token=self.config.BOT_TOKEN)
        self.dp = Dispatcher()
        
        if self.db_manager is None:
            if self.config.database_configured:
                self.db_manager = DatabaseManager(self.config.DATABASE_URL)
            else:
                self.db_manager = SimpleDatabaseManager()
        
        self.content_generator = ContentGenerator(self.config.OPENAI_API_KEY)
        
        self.scraper = DealScraper(
            max_deals_per_source=self.config.MAX_DEALS_PER_SOURCE,
            request_timeout=self.config.REQUEST_TIMEOUT
        )
        
        self._register_handlers()
        
        logger.info("🤖 Bot components initialized")
    
    def _register_handlers(self):
        self.dp.message.register(self.cmd_start, Command(commands=['start']))
        self.dp.message.register(self.cmd_help, Command(commands=['help']))
        self.dp.message.register(self.cmd_deals, Command(commands=['deals']))
        self.dp.message.register(self.cmd_category, Command(commands=['category']))
        self.dp.message.register(self.cmd_region, Command(commands=['region']))
        self.dp.message.register(self.cmd_stats, Command(commands=['stats']))
        self.dp.message.register(self.cmd_electronics, Command(commands=['electronics']))
        self.dp.message.register(self.cmd_home, Command(commands=['home']))
        self.dp.message.register(self.cmd_fashion, Command(commands=['fashion']))
        self.dp.message.register(self.cmd_sports, Command(commands=['sports']))
        self.dp.message.register(self.cmd_beauty, Command(commands=['beauty']))
        self.dp.message.register(self.cmd_books, Command(commands=['books']))
        self.dp.message.register(self.cmd_search, Command(commands=['search']))
        
        self.dp.message.register(self.cmd_admin, Command(commands=['admin']))
        self.dp.message.register(self.cmd_add_deal, Command(commands=['add_deal']))
        self.dp.message.register(self.cmd_broadcast, Command(commands=['broadcast']))
        
        self.dp.callback_query.register(self.handle_category_selection, F.data.startswith('category:'))
        self.dp.callback_query.register(self.handle_region_selection, F.data.startswith('region:'))
        self.dp.callback_query.register(self.handle_deal_action, F.data.startswith('deal:'))
        
        self.dp.message.register(self.handle_text_message, F.text)
        
        logger.info("🎯 Bot handlers registered")
    
    async def initialize(self):
        try:
            if self.db_manager and self.manage_db_lifecycle:
                await self.db_manager.initialize()
            await self.content_generator.initialize()
            await self.scraper.initialize()
            
            logger.info("✅ Bot services initialized successfully")
            
        except Exception as e:
            logger.error(f"Bot initialization failed: {e}")
            raise
    
    async def start_polling(self):
        try:
            await self.initialize()
            logger.info("🤖 Starting Telegram bot polling...")
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Bot polling failed: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        try:
            if self.scraper:
                await self.scraper.close()
            if self.content_generator:
                await self.content_generator.close()
            if self.db_manager and self.manage_db_lifecycle:
                await self.db_manager.close()
            if self.bot:
                await self.bot.session.close()
            
            logger.info("🧹 Bot cleanup completed")
            
        except Exception as e:
            logger.error(f"Bot cleanup error: {e}")
    
    
    async def cmd_start(self, message):
        try:
            user = message.from_user
            if not user:
                return
            
            await self.db_manager.add_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            
            welcome_message = f"""
🛒 *Welcome to Amazon Deal Bot!*

Hi {user.first_name or 'there'}! I help you find the best Amazon deals with instant notifications.

*Available Commands:*
• /deals - Get latest deals
• /category - Choose preferred categories  
• /region - Set your region
• /help - Show all commands

Ready to save money? Use /deals to see current offers!
"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔥 Latest Deals", callback_data="deals:latest")],
                [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings:main")]
            ])
            
            await message.reply(welcome_message, parse_mode="Markdown", reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error in /start command: {e}")
            try:
                await message.reply("Welcome! Use /deals to see current Amazon offers.")
            except Exception:
                await message.answer("Welcome! I'll help you find the best Amazon deals! 🛍️")
    
    async def cmd_help(self, message):
        try:
            help_text = """🤖 **Deal Bot Help**

**Available Commands:**
• /start - Welcome and setup
• /deals - Latest deals (all categories)
• /search <keyword> - Search products by keyword
• /category - Set your preferences
• /region - Set your region
• /stats - Your statistics

**Quick Category Commands:**
• /electronics - Electronics deals
• /home - Home and Kitchen deals
• /fashion - Fashion deals
• /sports - Sports and Outdoors deals
• /beauty - Beauty deals
• /books - Books deals

**How it works:**
1. Use /search to find specific products
2. Use category commands for specific deals
3. Set your region for local pricing
4. Get instant deal notifications
5. Click links to shop with discounts

**Supported Regions:**
US, UK, DE, FR, CA, JP, AU, IN

Need help? Just ask!"""
            
            await message.reply(help_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in /help command: {e}")
            await message.reply("Here are the available commands: /start /deals /category /region /stats /help")
    
    async def cmd_deals(self, message):
        try:
            user_id = message.from_user.id
            
            # Get user preferences
            try:
                user = await self.db_manager.get_user(user_id)
                category_filter = user.category if user else 'all'
            except Exception as e:
                logger.warning(f"Error getting user preferences: {e}")
                category_filter = 'all'
            
            # Get recent deals
            recent_deals = await self.db_manager.get_recent_deals(hours=24, limit=5)
            
            if not recent_deals:
                await message.answer("🔍 No recent deals found. Check back soon for new deals! ⏰")
                return
            
            # Filter by user category if specified
            if category_filter != 'all':
                recent_deals = [d for d in recent_deals if d.category == category_filter]
            
            if not recent_deals:
                await message.answer(f"🔍 No recent deals found for **{category_filter}** category. Check back soon! ⏰", parse_mode="Markdown")
                return
            
            await message.answer(f"🔥 **Latest Deals ({len(recent_deals)} found):**", parse_mode="Markdown")
            
            # Send each deal
            for deal in recent_deals:
                deal_product = deal.to_product()
                deal_message = await self.content_generator.generate_telegram_message(
                    deal_product, deal.affiliate_link
                )
                
                # Create deal keyboard
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Get This Deal", url=deal.affiliate_link)],
                    [InlineKeyboardButton(text="👍 Like", callback_data=f"deal:like:{deal.id}"),
                     InlineKeyboardButton(text="💬 Share", callback_data=f"deal:share:{deal.id}")]
                ])
                
                await message.answer(deal_message, reply_markup=keyboard, parse_mode="Markdown")
                await asyncio.sleep(0.5)  # Avoid rate limits
                
        except Exception as e:
            logger.error(f"Error in deals command: {e}")
            await message.answer("❌ Error loading deals. Please try again later.")
    
    async def _get_category_deals(self, message, category: str, category_emoji: str):
        try:
            from link_validator import LinkValidator
            
            recent_deals = await self.db_manager.get_recent_deals(hours=24, limit=10)
            
            # Filter by category
            category_deals = [d for d in recent_deals if d.category == category]
            
            if not category_deals:
                await message.answer(f"{category_emoji} No recent {category} deals found. Check back soon!")
                return
            
            # Validate links before sending to user
            async with LinkValidator() as validator:
                affiliate_links = [deal.affiliate_link for deal in category_deals]
                validation_results = await validator.validate_links_batch(affiliate_links)
                
                # Filter to only valid deals
                valid_deals = []
                for deal, result in zip(category_deals, validation_results):
                    if result.is_valid:
                        valid_deals.append(deal)
            
            if not valid_deals:
                await message.answer(f"{category_emoji} No valid {category} deals available right now. Please try again later!")
                return
            
            await message.answer(f"{category_emoji} *{category.title()} Deals ({len(valid_deals)} verified):*", parse_mode="Markdown")
            
            # Send each validated deal
            for deal in valid_deals:
                deal_product = deal.to_product()
                deal_message = await self.content_generator.generate_telegram_message(
                    deal_product, deal.affiliate_link
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Get This Deal", url=deal.affiliate_link)],
                    [InlineKeyboardButton(text="👍 Like", callback_data=f"deal:like:{deal.id}"),
                     InlineKeyboardButton(text="💬 Share", callback_data=f"deal:share:{deal.id}")]
                ])
                
                await message.answer(deal_message, reply_markup=keyboard, parse_mode="Markdown")
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Error in {category} deals command: {e}")
            await message.answer(f"❌ Error loading {category} deals. Please try again later.")
    
    async def cmd_electronics(self, message):
        await self._get_category_deals(message, "electronics", "📱")
    
    async def cmd_home(self, message):
        await self._get_category_deals(message, "home", "🏠")
    
    async def cmd_fashion(self, message):
        await self._get_category_deals(message, "fashion", "👕")
    
    async def cmd_sports(self, message):
        await self._get_category_deals(message, "sports", "⚽")
    
    async def cmd_beauty(self, message):
        await self._get_category_deals(message, "beauty", "💄")
    
    async def cmd_books(self, message):
        await self._get_category_deals(message, "books", "📚")
    
    async def cmd_search(self, message):
        """Search for products by keyword."""
        try:
            # Extract keyword from message
            text_parts = message.text.split(maxsplit=1)
            if len(text_parts) < 2:
                await message.answer(
                    "🔍 **Product Search**\n\n"
                    "Usage: `/search <keyword>`\n\n"
                    "Example: `/search wireless headphones`\n\n"
                    "I'll search Amazon and show you the best matching products!",
                    parse_mode="Markdown"
                )
                return
            
            keyword = text_parts[1].strip()
            
            if len(keyword) < 3:
                await message.answer("❌ Search keyword must be at least 3 characters long.")
                return
            
            await message.answer(f"🔍 Searching for '{keyword}'...")
            
            # Search products
            products = await self.scraper.search_products_by_keyword(
                keyword=keyword,
                max_results=10,
                affiliate_id=self.config.AMAZON_AFFILIATE_ID
            )
            
            if not products:
                await message.answer(
                    f"❌ No products found for '{keyword}'. Try a different search term."
                )
                return
            
            await message.answer(
                f"✅ Found {len(products)} products for '{keyword}':",
                parse_mode="Markdown"
            )
            
            # Send each product
            for product in products[:5]:  # Limit to 5 results
                affiliate_link = self.config.get_affiliate_link(product.link)
                message_text = await self.content_generator.generate_telegram_message(
                    product, affiliate_link
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Get This Deal", url=affiliate_link)]
                ])
                
                # Send with image if available
                if product.image_url:
                    try:
                        await self.bot.send_photo(
                            chat_id=message.chat.id,
                            photo=product.image_url,
                            caption=message_text,
                            reply_markup=keyboard,
                            parse_mode="Markdown"
                        )
                    except Exception as img_error:
                        logger.warning(f"Failed to send image for {product.title[:30]}: {img_error}")
                        # Fallback to text if image fails
                        await message.answer(message_text, reply_markup=keyboard, parse_mode="Markdown")
                else:
                    await message.answer(message_text, reply_markup=keyboard, parse_mode="Markdown")
                
                await asyncio.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            logger.error(f"Error in search command: {e}")
            await message.answer("❌ Error searching products. Please try again later.")
    
    async def cmd_category(self, message):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Electronics", callback_data="category:electronics"),
             InlineKeyboardButton(text="🏠 Home & Kitchen", callback_data="category:home")],
            [InlineKeyboardButton(text="👕 Fashion", callback_data="category:fashion"),
             InlineKeyboardButton(text="⚽ Sports", callback_data="category:sports")],
            [InlineKeyboardButton(text="💄 Beauty", callback_data="category:beauty"),
             InlineKeyboardButton(text="📚 Books", callback_data="category:books")],
            [InlineKeyboardButton(text="🔧 Tools", callback_data="category:tools"),
             InlineKeyboardButton(text="🚗 Automotive", callback_data="category:automotive")],
            [InlineKeyboardButton(text="🧸 Toys", callback_data="category:toys"),
             InlineKeyboardButton(text="📋 Office", callback_data="category:office")],
            [InlineKeyboardButton(text="🛍️ All Categories", callback_data="category:all")]
        ])
        
        await message.answer(
            "🎯 **Choose your preferred category:**\n\nI'll send you deals that match your interests!",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    async def cmd_region(self, message):
        try:
            user_id = message.from_user.id
            
            # Get current user region
            try:
                user = await self.db_manager.get_user(user_id)
                current_region = user.region if user else "US"
            except Exception as e:
                logger.warning(f"Failed to get user region: {e}")
                current_region = "US"
            
            currency_info = self.config.get_regional_currency(current_region)
            
            region_text = f"""
🌍 **Choose Your Amazon Region**

Current: **{current_region}** ({currency_info['symbol']} {currency_info['code']})

Select your preferred Amazon marketplace to get deals with correct pricing and links:
""".strip()
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🇺🇸 US ($)", callback_data="region:US"),
                 InlineKeyboardButton(text="🇬🇧 UK (£)", callback_data="region:UK")],
                [InlineKeyboardButton(text="🇩🇪 DE (€)", callback_data="region:DE"),
                 InlineKeyboardButton(text="🇫🇷 FR (€)", callback_data="region:FR")],
                [InlineKeyboardButton(text="🇨🇦 CA (CA$)", callback_data="region:CA"),
                 InlineKeyboardButton(text="🇯🇵 JP (¥)", callback_data="region:JP")],
                [InlineKeyboardButton(text="🇦🇺 AU (AU$)", callback_data="region:AU"),
                 InlineKeyboardButton(text="🇮🇳 IN (₹)", callback_data="region:IN")]
            ])
            
            await message.answer(region_text, reply_markup=keyboard, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in region command: {e}")
            await message.answer("❌ Error loading region settings. Please try again later.")
    
    async def cmd_stats(self, message):
        try:
            if not self.db_manager:
                await message.reply("Database not available. Please try again later.")
                return
                
            stats = await self.db_manager.get_deal_stats()
            
            if not stats:
                await message.reply("📊 No statistics available yet. The bot is still collecting data!")
                return
            
            stats_text = f"""
📊 *Deal Bot Statistics*

🛍️ *Total Deals:* {stats.total_deals}
🔥 *Recent Deals:* {stats.recent_deals} (24h)
👆 *Total Clicks:* {stats.total_clicks}
💰 *Total Earnings:* ${stats.total_earnings:.2f}
👥 *Active Users:* {stats.active_users}
📈 *Conversion Rate:* {stats.conversion_rate():.1f}%

*Top Categories:*
""".strip()
            
            # Add top categories
            if stats.category_stats:
                sorted_categories = sorted(stats.category_stats.items(), key=lambda x: x[1], reverse=True)
                for category, count in sorted_categories[:5]:
                    emoji = {'electronics': '📱', 'home': '🏠', 'fashion': '👕', 'sports': '⚽', 'beauty': '💄'}.get(category, '🛍️')
                    stats_text += f"\n{emoji} {category.title()}: {count}"
            else:
                stats_text += "\nNo category data available yet."
            
            await message.reply(stats_text, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await message.reply("Error loading statistics. Please try again later.")
    
    async def cmd_admin(self, message):
        # Simple admin check - in production, use proper admin verification
        user_id = message.from_user.id
        admin_ids = self.config.ADMIN_USER_IDS or []
        
        if admin_ids and user_id not in admin_ids:
            await message.answer("❌ Access denied. Admin only.")
            return
        
        admin_text = """
🔧 **Admin Panel**

**Available Commands:**
• `/add_deal <url>` - Add deal manually
• `/broadcast <message>` - Send message to all users
• `/stats` - View detailed statistics

**Quick Actions:**
• Post deals now
• Clean database
• View logs
""".strip()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Post Deals Now", callback_data="admin:post_deals")],
            [InlineKeyboardButton(text="🧹 Clean Database", callback_data="admin:cleanup")],
            [InlineKeyboardButton(text="📊 Full Stats", callback_data="admin:full_stats")]
        ])
        
        await message.answer(admin_text, reply_markup=keyboard, parse_mode="Markdown")
    
    async def cmd_add_deal(self, message):
        # Extract URL from message
        text_parts = message.text.split(maxsplit=1)
        if len(text_parts) < 2:
            await message.answer("❌ Please provide a product URL: `/add_deal <amazon_url>`", parse_mode="Markdown")
            return
        
        url = text_parts[1].strip()
        
        try:
            # Scrape the specific deal
            product = await self.scraper.scrape_specific_deal(url)
            
            if not product:
                await message.answer("❌ Could not extract product information from that URL.")
                return
            
            # Validate the link before adding
            from link_validator import LinkValidator
            async with LinkValidator() as validator:
                result = await validator.validate_link(url)
                if not result.is_valid:
                    await message.answer(f"❌ Invalid or broken link: {result.error_message}")
                    return
            
            # Generate affiliate link
            affiliate_link = self.config.get_affiliate_link(url)
            
            # Add to database
            deal = await self.db_manager.add_deal(
                product=product,
                affiliate_link=affiliate_link,
                source="manual",
                content_style="simple"
            )
            
            await message.answer(f"✅ Deal added successfully!\n\n**{product.title}**\nPrice: {product.price}\nDeal ID: {deal.id}")
            
        except Exception as e:
            logger.error(f"Error adding manual deal: {e}")
            await message.answer("❌ Error adding deal. Please check the URL and try again.")
    
    async def cmd_broadcast(self, message):
        # Simple admin check
        user_id = message.from_user.id
        admin_ids = self.config.ADMIN_USER_IDS or []
        
        if admin_ids and user_id not in admin_ids:
            await message.answer("❌ Access denied. Admin only.")
            return
        
        # Extract message
        text_parts = message.text.split(maxsplit=1)
        if len(text_parts) < 2:
            await message.answer("❌ Please provide a message: `/broadcast <your_message>`", parse_mode="Markdown")
            return
        
        broadcast_message = text_parts[1].strip()
        
        try:
            # Get all active users
            users = await self.db_manager.get_active_users(days=30)
            sent_count, failed_count = await self._broadcast_with_rate_limit(
                [user.user_id for user in users],
                f"📢 **Broadcast Message**\n\n{broadcast_message}"
            )
            
            await message.answer(f"✅ Broadcast sent!\n\n📤 Sent: {sent_count}\n❌ Failed: {failed_count}")
            
        except Exception as e:
            logger.error(f"Error in broadcast: {e}")
            await message.answer("❌ Error sending broadcast message.")

    async def _broadcast_with_rate_limit(self, chat_ids: list[int], text: str) -> tuple[int, int]:
        sent_count = 0
        failed_count = 0

        for index, chat_id in enumerate(chat_ids):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown"
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send broadcast to user {chat_id}: {e}")
                failed_count += 1

            await asyncio.sleep(TELEGRAM_RATE_LIMIT_SECONDS)
            if index > 0 and index % 25 == 0:
                await asyncio.sleep(2.0)

        return sent_count, failed_count
    
    # Callback Query Handlers
    
    async def handle_category_selection(self, callback_query):
        try:
            category = callback_query.data.split(":", 1)[1]
            user_id = callback_query.from_user.id
            
            # Update user preferences
            success = await self.db_manager.update_user_preferences(user_id, category=category)
            
            if success:
                category_name = category.title() if category != 'all' else 'All Categories'
                await callback_query.message.edit_text(
                    f"✅ **Category Updated!**\n\nYou'll now receive deals for: **{category_name}**\n\nUse /deals to see the latest offers!",
                    parse_mode="Markdown"
                )
            else:
                await callback_query.answer("❌ Failed to update preferences", show_alert=True)
            
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error handling category selection: {e}")
            await callback_query.answer("❌ Error updating category", show_alert=True)
    
    async def handle_region_selection(self, callback_query):
        try:
            region = callback_query.data.split(":", 1)[1]
            user_id = callback_query.from_user.id
            
            # Update user preferences
            success = await self.db_manager.update_user_preferences(user_id, region=region)
            
            if success:
                region_info = self.config.get_region_info(region)
                await callback_query.message.edit_text(
                    f"✅ **Region Updated!**\n\n🌍 **Region:** {region_info['region']}\n💰 **Currency:** {region_info['currency_symbol']} ({region_info['currency_code']})\n🛒 **Amazon:** {region_info['amazon_domain']}\n\nPrices will now be shown in your local currency!",
                    parse_mode="Markdown"
                )
            else:
                await callback_query.answer("❌ Failed to update region", show_alert=True)
            
            await callback_query.answer()
            
        except Exception as e:
            logger.error(f"Error handling region selection: {e}")
            await callback_query.answer("❌ Error updating region", show_alert=True)
    
    async def handle_deal_action(self, callback_query):
        try:
            action_data = callback_query.data.split(":", 2)
            action = action_data[1]
            deal_id = int(action_data[2]) if len(action_data) > 2 else 0
            
            if action == "like":
                await callback_query.answer("👍 Thanks for liking this deal!", show_alert=False)
                # Could track likes in database
                
            elif action == "share":
                await callback_query.answer("💬 Deal link copied! Share with friends!", show_alert=False)
                # Could provide share options
                
            else:
                await callback_query.answer("❓ Unknown action", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error handling deal action: {e}")
            await callback_query.answer("❌ Error processing action", show_alert=True)
    
    async def handle_text_message(self, message):
        text = message.text.lower()
        
        # Simple command recognition
        if any(word in text for word in ['deal', 'deals', 'discount', 'sale']):
            await message.answer("🔍 Looking for deals? Use /deals to see the latest offers!")
        elif any(word in text for word in ['help', 'how', 'what']):
            await message.answer("ℹ️ Need help? Use /help to see all available commands!")
        elif any(word in text for word in ['category', 'categories']):
            await message.answer("🎯 Set your preferences with /category")
        elif any(word in text for word in ['region', 'country', 'currency']):
            await message.answer("🌍 Set your region with /region")
        else:
            # Default response
            responses = [
                "👋 Hi there! Use /help to see what I can do!",
                "🛍️ Looking for deals? Try /deals to see the latest offers!",
                "💡 Tip: Use /category to set your preferences!"
            ]
            import random
            await message.answer(random.choice(responses))
    
    # Utility methods
    
    async def post_deals(self) -> int:
        try:
            # Get new deals from scraper
            deals = await self.scraper.scrape_real_amazon_deals()
            
            if not deals:
                logger.info("ℹ️ No new deals found")
                return 0

            pipeline = DealPipelineService(
                db_manager=self.db_manager,
                content_generator=self.content_generator,
                affiliate_link_builder=self.config.get_affiliate_link,
                telegram_client=self.bot,
                telegram_channel=self.config.TELEGRAM_CHANNEL,
                source="scraper",
                content_style="enthusiastic",
                dedupe_hours=24,
            )
            result = await pipeline.post_products(deals)
            logger.info(
                f"📢 Pipeline cycle complete: fetched={result.fetched}, posted={result.posted}, "
                f"deduped={result.deduped_out}, failed={result.failed}"
            )
            return result.posted
            
        except Exception as e:
            logger.error(f"Error in post_deals: {e}")
            return 0
