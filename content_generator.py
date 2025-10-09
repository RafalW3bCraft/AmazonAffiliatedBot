import json
import logging
import random
from typing import Optional, Dict, Any

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from models import Product

logger = logging.getLogger(__name__)


class ContentGenerator:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = None
        self.fallback_mode = not (OPENAI_AVAILABLE and api_key)
        
        if self.fallback_mode:
            logger.warning("🤖 OpenAI not available - using fallback content generation")
        elif OPENAI_AVAILABLE:
            self.client = AsyncOpenAI(api_key=api_key)
            logger.info("🧠 OpenAI content generator initialized")
    
    async def initialize(self):
        if not self.fallback_mode:
            try:
                await self._test_openai_connection()
                logger.info("✅ OpenAI connection verified")
            except Exception as e:
                logger.warning(f"OpenAI test failed, switching to fallback: {e}")
                self.fallback_mode = True
    
    async def close(self):
        if self.client:
            await self.client.close()
    
    async def _test_openai_connection(self):
        if not self.client:
            raise Exception("OpenAI client not initialized")
        
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10
        )
        
        if not response.choices:
            raise Exception("No response from OpenAI")
    
    async def generate_telegram_message(self, product: Product, affiliate_link: str, 
                                      style: str = "enthusiastic") -> str:
        if self.fallback_mode:
            return self._generate_fallback_message(product, affiliate_link, style)
        
        try:
            if not self.client:
                return self._generate_fallback_message(product, affiliate_link, style)
                
            prompt = self._build_telegram_prompt(product, style)
            
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert Amazon affiliate marketer. Create engaging, "
                                 "concise Telegram messages that drive clicks and conversions. "
                                 "Use emojis, highlight savings, and create urgency. "
                                 "Keep messages under 300 words. Format for Telegram Markdown."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.8
            )
            
            content = response.choices[0].message.content
            message = content.strip() if content else ""
            
            message += f"\n\n🛒 **[Get This Deal]({affiliate_link})**"
            
            return message
            
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "quota" in error_msg.lower():
                logger.warning(f"OpenAI quota exceeded, using fallback content")
                self.fallback_mode = True
            elif "401" in error_msg:
                logger.warning(f"OpenAI API key invalid, using fallback content")
                self.fallback_mode = True
            else:
                logger.error(f"OpenAI content generation failed: {e}")
            return self._generate_fallback_message(product, affiliate_link, style)
    
    async def generate_deal_description(self, product: Product, style: str = "professional") -> str:
        if self.fallback_mode:
            return self._generate_fallback_description(product, style)
        
        try:
            prompt = f"""
            Create a compelling product description for this Amazon deal:
            
            Product: {product.title}
            Price: {product.price}
            Discount: {product.discount}
            Category: {product.category}
            Rating: {product.rating}/5 ({product.review_count} reviews)
            Current Description: {product.description or 'None provided'}
            
            Style: {style}
            
            Create a description that:
            - Highlights key benefits and features
            - Emphasizes the value and savings
            - Uses persuasive language
            - Is 100-200 words
            - Includes relevant emojis
            """
            
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert copywriter specializing in e-commerce product descriptions."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Description generation failed: {e}")
            return self._generate_fallback_description(product, style)
    
    async def generate_welcome_message(self, user_name: str) -> str:
        if self.fallback_mode:
            return self._generate_fallback_welcome(user_name)
        
        try:
            prompt = f"""
            Create a warm, engaging welcome message for a new user of an Amazon deals bot.
            User name: {user_name}
            
            The message should:
            - Be personal and friendly
            - Explain what the bot does
            - Encourage engagement
            - Use appropriate emojis
            - Be 50-100 words
            - Include markdown formatting for Telegram
            """
            
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a friendly bot assistant that helps users find great Amazon deals."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.8
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Welcome message generation failed: {e}")
            return self._generate_fallback_welcome(user_name)
    
    async def analyze_product_sentiment(self, product: Product) -> Dict[str, Any]:
        if self.fallback_mode:
            return {
                'sentiment_score': 0.7,
                'confidence': 0.6,
                'key_points': ['Good value', 'Popular item', 'Positive reviews']
            }
        
        try:
            prompt = f"""
            Analyze the sentiment and appeal of this Amazon product:
            
            Title: {product.title}
            Price: {product.price}
            Discount: {product.discount}
            Rating: {product.rating}/5 ({product.review_count} reviews)
            Description: {product.description or 'None'}
            
            Provide analysis in JSON format:
            {{
                "sentiment_score": 0.0-1.0,
                "confidence": 0.0-1.0,
                "key_points": ["point1", "point2", "point3"],
                "appeal_factors": ["factor1", "factor2"],
                "concerns": ["concern1", "concern2"] or [],
                "recommendation": "buy/consider/avoid"
            }}
            """
            
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert product analyst. Respond only with valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=300,
                temperature=0.3
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return {
                'sentiment_score': 0.7,
                'confidence': 0.5,
                'key_points': ['Product analysis unavailable'],
                'appeal_factors': ['Price discount'],
                'concerns': [],
                'recommendation': 'consider'
            }
    
    def _build_telegram_prompt(self, product: Product, style: str) -> str:
        return f"""
        Create a {style} Telegram message for this Amazon deal:
        
        Product: {product.title}
        Price: {product.price}
        Discount: {product.discount}
        Category: {product.category}
        Rating: {product.rating}/5 ⭐ ({product.review_count} reviews)
        Description: {product.description or 'Great deal on Amazon!'}
        
        Requirements:
        - Start with eye-catching emojis
        - Highlight the discount/savings
        - Mention key product benefits
        - Create urgency (limited time, stock, etc.)
        - Use Telegram markdown formatting
        - End with a strong call-to-action
        - Keep under 280 characters
        
        Do NOT include the affiliate link - it will be added separately.
        """
    
    
    def _generate_fallback_message(self, product: Product, affiliate_link: str, style: str) -> str:
        templates = {
            "enthusiastic": [
                "🔥 **AMAZING DEAL ALERT!** 🔥\n\n💫 {title}\n💰 **{price}** ({discount})\n⭐ {rating}/5 ({review_count} reviews)\n\n🚨 LIMITED TIME OFFER! Don't miss out!\n\n🛒 **[Get This Deal Now]({link})**",
                "💥 **INCREDIBLE SAVINGS!** 💥\n\n✨ {title}\n🎯 **{price}** - Save with {discount}!\n⭐ {rating}/5 stars ({review_count} reviews)\n\n⏰ Hurry! This deal won't last long!\n\n🛒 **[Shop Now]({link})**"
            ],
            "professional": [
                "📦 **Featured Deal**\n\n**{title}**\n\n💵 Price: **{price}**\n🏷️ Discount: {discount}\n⭐ Rating: {rating}/5 ({review_count} reviews)\n\n🛒 **[View Deal]({link})**",
                "🛍️ **Product Spotlight**\n\n{title}\n\n**Price:** {price}\n**Savings:** {discount}\n**Customer Rating:** {rating}/5 ⭐\n\n🔗 **[Get This Deal]({link})**"
            ],
            "simple": [
                "🛒 **{title}**\n\n💰 {price} ({discount})\n⭐ {rating}/5\n\n🔗 **[Buy Now]({link})**",
                "📦 {title}\n\n{price} - {discount}\n{rating}/5 ⭐ ({review_count} reviews)\n\n**[Get Deal]({link})**"
            ]
        }
        
        style_templates = templates.get(style, templates["simple"])
        template = random.choice(style_templates)
        
        return template.format(
            title=product.title[:80] + "..." if len(product.title) > 80 else product.title,
            price=product.price,
            discount=product.discount,
            rating=product.rating or "4.0",
            review_count=product.review_count or "100+",
            link=affiliate_link
        )
    
    def _generate_fallback_description(self, product: Product, style: str) -> str:
        base_descriptions = {
            "enthusiastic": f"🌟 Get ready to be amazed by this incredible {product.category} deal! {product.title} is now available at an unbeatable price of {product.price} with {product.discount}! Don't let this opportunity slip away!",
            "professional": f"This {product.category} item offers excellent value at {product.price}. With {product.discount}, it represents significant savings for customers looking for quality products in this category.",
            "simple": f"{product.title} is now available for {product.price} with {product.discount}. Good deal in the {product.category} category."
        }
        
        return base_descriptions.get(style, base_descriptions["simple"])
    
    def _generate_fallback_welcome(self, user_name: str) -> str:
        messages = [
            f"🎉 Welcome {user_name}! I'm here to help you find the best Amazon deals and save money! 💰\n\nGet ready for amazing discounts, exclusive offers, and unbeatable prices! 🛍️",
            f"👋 Hi {user_name}! Welcome to your personal deal finder! 🔍\n\nI'll help you discover incredible Amazon deals and save big on quality products! ⭐",
            f"🌟 Hello {user_name}! Thanks for joining! I'm your deal-hunting assistant! 🛒\n\nLet's find you some amazing bargains and fantastic savings! 💫"
        ]
        
        return random.choice(messages)
