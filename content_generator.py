import json
import logging
import os
import random
from typing import Optional, Dict, Any

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from models import Product

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"


class ContentGenerator:
    """Generates deal content using an OpenAI-compatible chat API.

    Provider resolution order (first match wins):
      1. Explicit constructor args (api_key/model/base_url).
      2. OPENAI_API_KEY env -> OpenAI, model from AI_MODEL env or 'gpt-4o-mini'.
      3. FEATHERLESS_API_KEY env -> Featherless, base_url from FEATHERLESS_BASE_URL,
         model from AI_MODEL env (required; without it the provider is treated
         as unconfigured and the deterministic template fallback is used).
      4. No credentials -> deterministic template fallback.

    Fallback content never claims to be AI-generated.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None):
        self._closed = False
        self.client = None
        self.model: Optional[str] = None
        self.base_url: Optional[str] = None
        self._provider = "none"
        self.fallback_mode = True

        env_model = os.getenv("AI_MODEL", "").strip() or None
        openai_key = os.getenv("OPENAI_API_KEY", "").strip() or None
        featherless_key = os.getenv("FEATHERLESS_API_KEY", "").strip() or None

        # Resolution order: explicit args -> env AI_MODEL -> provider default.
        effective_key = api_key or openai_key or featherless_key
        if not effective_key or not OPENAI_AVAILABLE:
            if not OPENAI_AVAILABLE:
                logger.warning("openai package not available - using template content generation")
            else:
                logger.warning("No AI provider key configured - using template content generation")
            return

        if api_key or openai_key:
            # Explicit key or OPENAI_API_KEY: OpenAI-compatible provider.
            self._provider = "openai"
            self.model = model or env_model or DEFAULT_OPENAI_MODEL
            self.base_url = base_url or None
        else:
            # Featherless fallback when only FEATHERLESS_API_KEY is set.
            self.base_url = base_url or os.getenv(
                "FEATHERLESS_BASE_URL", DEFAULT_FEATHERLESS_BASE_URL
            ).strip() or DEFAULT_FEATHERLESS_BASE_URL
            self.model = model or env_model
            if not self.model:
                logger.warning(
                    "FEATHERLESS_API_KEY set but AI_MODEL is empty - "
                    "treating provider as unconfigured; using template fallback"
                )
                return
            self._provider = "featherless"

        self.fallback_mode = False
        if self.base_url:
            self.client = AsyncOpenAI(api_key=effective_key, base_url=self.base_url)
        else:
            self.client = AsyncOpenAI(api_key=effective_key)
        logger.info(
            f"Content generator initialized: provider={self._provider} model={self.model}"
        )

    @property
    def provider_name(self) -> str:
        """'openai' | 'featherless' | 'none'."""
        return self._provider

    def _check_open(self):
        if self._closed:
            raise RuntimeError("ContentGenerator is closed")

    async def initialize(self):
        self._check_open()
        if not self.fallback_mode:
            try:
                await self._test_connection()
                logger.info("AI provider connection verified")
            except Exception as e:
                logger.warning(f"AI provider test failed, switching to fallback: {e}")
                self.fallback_mode = True

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self.client:
            try:
                await self.client.close()
            finally:
                self.client = None

    async def _test_connection(self):
        self._check_open()
        if not self.client:
            raise Exception("AI client not initialized")

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10
        )

        if not response.choices:
            raise Exception("No response from AI provider")

    async def generate_telegram_message(self, product: Product, affiliate_link: str,
                                      style: str = "enthusiastic") -> str:
        self._check_open()
        if self.fallback_mode:
            return self._generate_fallback_message(product, affiliate_link, style)

        try:
            if not self.client:
                return self._generate_fallback_message(product, affiliate_link, style)

            prompt = self._build_telegram_prompt(product, style)

            response = await self.client.chat.completions.create(
                model=self.model,
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
                logger.warning(f"{self._provider} quota exceeded, using fallback content")
                self.fallback_mode = True
            elif "401" in error_msg:
                logger.warning(f"{self._provider} API key invalid, using fallback content")
                self.fallback_mode = True
            else:
                logger.error(f"Content generation failed ({self._provider}): {e}")
            return self._generate_fallback_message(product, affiliate_link, style)

    async def generate_deal_description(self, product: Product, style: str = "professional") -> str:
        self._check_open()
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
                model=self.model,
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
        self._check_open()
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
                model=self.model,
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
        self._check_open()
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
                model=self.model,
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

    # ------------------------------------------------------------------
    # Deterministic template fallback. NOTE: none of these strings may
    # claim the content is AI-generated; keep wording neutral.
    # ------------------------------------------------------------------

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
