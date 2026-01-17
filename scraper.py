"""
Real-time Amazon Deal Scraper - Production Version
Only uses live data sources, no mock or demo content.
Fetches latest and catchy deals from Amazon Associates sources.
"""

import asyncio
import logging
import aiohttp
import re
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from models import Product

logger = logging.getLogger(__name__)


class DealScraper:
    """Real-time Amazon deal scraper with no mock data."""
    
    def __init__(self, max_deals_per_source: int = 5, request_timeout: int = 30):
        """Initialize scraper with configuration."""
        self.max_deals_per_source = max_deals_per_source
        self.request_timeout = request_timeout
        self.session = None
        # Prioritize deal pages over generic search results
        # Order matters - more specific deal pages first
        self.amazon_sources = [
            "https://www.amazon.com/gp/goldbox/ref=nav_cs_gb",  # Today's Deals
            "https://www.amazon.com/gp/goldbox/ref=nav_cs_gb_azl",  # Lightning Deals
            "https://www.amazon.com/deals",  # Best Deals
            "https://www.amazon.com/gp/goldbox",  # Goldbox (fallback)
            "https://www.amazon.com/s?k=deals&i=specialty-aps&ref=sr_pg_1",  # Deals search
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
        self.rate_limit_delay = 5
        # Deal quality thresholds
        self.MIN_DISCOUNT_PERCENT = 20  # Minimum 20% discount
        self.MIN_RATING = 4.0  # Minimum 4.0 stars
        self.MIN_REVIEWS = 50  # Minimum 50 reviews
        self.deal_timestamps: Dict[str, datetime] = {}  # Track when deals were first seen
        
    async def initialize(self):
        """Initialize async session."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self.headers
            )
            
    async def close(self):
        """Close session."""
        if self.session:
            await self.session.close()
            
    async def scrape_real_amazon_deals(self) -> List[Product]:
        """Scrape real Amazon deals from multiple sources, prioritizing latest and catchy deals."""
        if not self.session:
            await self.initialize()
            
        all_deals = []
        
        for source_url in self.amazon_sources:
            try:
                logger.info(f"Scraping real deals from: {source_url}")
                deals = await self._scrape_source(source_url)
                all_deals.extend(deals)
                
                # Exponential backoff on rate limiting
                await asyncio.sleep(self.rate_limit_delay)
                
            except Exception as e:
                logger.warning(f"Failed to scrape {source_url}: {e}")
                continue
        
        # Remove duplicates by ASIN
        unique_deals = []
        seen_asins = set()
        
        for deal in all_deals:
            if deal.asin and deal.asin not in seen_asins:
                unique_deals.append(deal)
                seen_asins.add(deal.asin)
                # Track when deal was first seen
                if deal.asin not in self.deal_timestamps:
                    self.deal_timestamps[deal.asin] = datetime.now()
        
        logger.info(f"Scraped {len(unique_deals)} unique deals from Amazon")
        
        if len(unique_deals) == 0:
            logger.warning("⚠️ No deals scraped at all. This may indicate Amazon HTML structure changed or rate limiting.")
            return []
        
        # Filter for catchy deals (meet quality thresholds)
        catchy_deals = self._filter_catchy_deals(unique_deals)
        logger.info(f"Filtered to {len(catchy_deals)} catchy deals (min {self.MIN_DISCOUNT_PERCENT}% off, {self.MIN_RATING}+ stars, {self.MIN_REVIEWS}+ reviews)")
        
        # If no catchy deals but we have some deals, relax filters and use best available
        if len(catchy_deals) == 0 and len(unique_deals) > 0:
            logger.warning(f"⚠️ No deals met strict quality criteria. Relaxing filters to use best available deals.")
            # Use relaxed criteria: any discount, 3.5+ rating, 10+ reviews
            relaxed_deals = []
            for deal in unique_deals:
                discount_pct = self._extract_discount_percentage(deal.discount)
                rating = deal.rating or 0.0
                reviews = deal.review_count or 0
                
                if (discount_pct >= 10 and rating >= 3.5 and reviews >= 10) or (rating >= 4.0 and reviews >= 20):
                    relaxed_deals.append(deal)
            
            if relaxed_deals:
                logger.info(f"Found {len(relaxed_deals)} deals with relaxed criteria")
                catchy_deals = relaxed_deals
            else:
                # Last resort: use any deals with at least some rating
                logger.warning("Using any deals with rating > 0 as last resort")
                catchy_deals = [d for d in unique_deals if d.rating > 0 or d.review_count > 0]
        
        if len(catchy_deals) == 0:
            logger.warning("No deals found even with relaxed criteria. Returning empty list.")
            return []
        
        # Score and sort deals by quality
        scored_deals = [(deal, self._score_deal(deal)) for deal in catchy_deals]
        scored_deals.sort(key=lambda x: x[1], reverse=True)  # Sort by score descending
        
        # Return top deals
        top_deals = [deal for deal, score in scored_deals[:self.max_deals_per_source * len(self.amazon_sources)]]
        
        logger.info(f"Returning {len(top_deals)} top-scored deals")
        
        logger.info(f"Returning {len(top_deals)} top-scored deals")
        return top_deals
    
    async def search_products_by_keyword(
        self, 
        keyword: str, 
        max_results: int = 20,
        affiliate_id: str = None,
        min_rating: float = 4.0,
        min_reviews: int = 50
    ) -> List[Product]:
        """Search Amazon products by keyword with affiliate tag."""
        if not self.session:
            await self.initialize()
        
        if not keyword or not keyword.strip():
            logger.warning("Empty keyword provided for search")
            return []
        
        # Build search URL
        keyword_encoded = keyword.strip().replace(' ', '+')
        search_url = f"https://www.amazon.com/s?k={keyword_encoded}"
        
        # Add affiliate tag if provided
        if affiliate_id:
            search_url += f"&tag={affiliate_id}"
        
        logger.info(f"Searching Amazon for: {keyword}")
        
        try:
            deals = await self._scrape_source(search_url)
            
            # Filter by quality criteria
            filtered_deals = []
            for deal in deals[:max_results]:
                if (deal.rating >= min_rating and 
                    deal.review_count >= min_reviews):
                    filtered_deals.append(deal)
            
            logger.info(f"Found {len(filtered_deals)} quality products for '{keyword}'")
            return filtered_deals
            
        except Exception as e:
            logger.error(f"Error searching for '{keyword}': {e}")
            return []
    
    async def get_deal_of_the_day(self, affiliate_id: str = None) -> Optional[Product]:
        """Get Amazon's Deal of the Day."""
        if not self.session:
            await self.initialize()
        
        deal_of_day_urls = [
            "https://www.amazon.com/gp/goldbox/ref=nav_cs_gb_azl",  # Lightning Deals
            "https://www.amazon.com/gp/goldbox",  # Goldbox
        ]
        
        for url in deal_of_day_urls:
            try:
                if affiliate_id:
                    # Add affiliate tag to URL
                    separator = '&' if '?' in url else '?'
                    url = f"{url}{separator}tag={affiliate_id}"
                
                logger.info(f"Fetching Deal of the Day from: {url}")
                deals = await self._scrape_source(url)
                
                if deals:
                    # Get the first deal (usually the featured one)
                    deal = deals[0]
                    logger.info(f"Deal of the Day found: {deal.title[:50]}...")
                    return deal
                    
            except Exception as e:
                logger.warning(f"Failed to get Deal of the Day from {url}: {e}")
                continue
        
        logger.warning("No Deal of the Day found")
        return None
    
    async def _scrape_source(self, url: str) -> List[Product]:
        """Scrape deals from a specific Amazon source with improved error handling and rate limiting."""
        if not self.session:
            logger.error("Session not initialized")
            return []
            
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                async with self.session.get(url) as response:
                    if response.status == 429:
                        retry_delay = min(retry_delay * 2, 60)  # Exponential backoff, max 60s
                        logger.warning(f"Rate limited by {url}, waiting {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        return []
                    elif response.status != 200:
                        logger.warning(f"HTTP {response.status} for {url}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        return []
                    
                    html = await response.text()
                    
                    # Check if we got a valid HTML response
                    if len(html) < 1000:
                        logger.warning(f"Received very short response ({len(html)} bytes) from {url}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        return []
                    
                    # Check for Amazon error pages
                    if 'captcha' in html.lower() or 'robot' in html.lower() or 'access denied' in html.lower():
                        logger.warning(f"Amazon blocking detected (captcha/robot) for {url}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * 2)
                            continue
                        return []
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    deals = self._parse_amazon_deals(soup, url)
                    logger.info(f"Extracted {len(deals)} deals from {url}")
                    return deals
                    
            except asyncio.TimeoutError:
                logger.warning(f"Timeout scraping {url} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return []
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return []
        
        return []
    
    def _parse_amazon_deals(self, soup: BeautifulSoup, source_url: str) -> List[Product]:
        """Parse Amazon deal structures from HTML with improved selectors for deal pages."""
        deals = []
        
        # Prioritize deal-specific selectors first - expanded list for better coverage
        deal_selectors = [
            '[data-component-type="s-deals-result"]',  # Deal-specific results
            '[data-component-type="s-search-result"]',  # Search results
            '.s-result-item[data-asin]',  # Results with ASIN
            '[data-asin]',  # Any element with ASIN
            '.s-result-item',  # Generic result items
            '.DealCard',  # Deal cards
            '.dealContainer',  # Deal containers
            '.s-main-slot .s-result-item',  # Main slot results
            '.s-result-list .s-result-item',  # Result list items
            'div[data-asin]',  # Divs with ASIN
            '.s-card-container',  # Card containers
            '.s-card-border',  # Card borders
        ]
        
        total_elements_found = 0
        for selector in deal_selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    total_elements_found += len(elements)
                    logger.info(f"Found {len(elements)} elements with selector: {selector}")
                    
                    for element in elements[:self.max_deals_per_source * 2]:  # Process more elements
                        try:
                            product = self._extract_product_data(element, source_url)
                            if product and product.asin:
                                deals.append(product)
                                logger.debug(f"Successfully extracted product: {product.title[:50]}...")
                                
                        except Exception as e:
                            logger.debug(f"Failed to extract product from element: {e}")
                            continue
                    
                    # If we found deals with this selector, prioritize it
                    if deals:
                        logger.info(f"Successfully extracted {len(deals)} deals using selector: {selector}")
                        break
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        if total_elements_found == 0:
            logger.warning(f"No elements found with any selector for URL: {source_url}")
            # Try to find any ASINs in the page as last resort
            try:
                all_asins = soup.find_all(attrs={'data-asin': True})
                if all_asins:
                    logger.info(f"Found {len(all_asins)} elements with data-asin attribute, but couldn't parse them")
            except Exception as e:
                logger.debug(f"Failed to find ASINs: {e}")
        
        if not deals:
            logger.warning(f"No deals extracted from {source_url}. Total elements found: {total_elements_found}")
        
        return deals
    
    def _extract_product_data(self, element, source_url: str) -> Optional[Product]:
        """Extract product data from HTML element."""
        try:
            # Try multiple ways to get ASIN
            asin = element.get('data-asin')
            if not asin:
                # Try to find ASIN in href attributes
                links = element.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    asin_match = re.search(r'/dp/([A-Z0-9]{10})', href)
                    if asin_match:
                        asin = asin_match.group(1)
                        break
                    asin_match = re.search(r'/gp/product/([A-Z0-9]{10})', href)
                    if asin_match:
                        asin = asin_match.group(1)
                        break
            
            if not asin:
                # Last resort: search in entire element text
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', str(element))
                if asin_match:
                    asin = asin_match.group(1)
            
            if not asin or len(asin) != 10:
                return None
            
            title_selectors = [
                'h2 a span.a-text-normal',
                'h3 a span',
                'h2 a span',
                '[data-cy="title-recipe-collection"]',
                '.s-size-mini span',
                '.a-link-normal span',
                '.a-text-normal',
                'span.a-text-normal',
                'a.a-link-normal span',
                'h2 span',
                'h3 span',
            ]
            title = self._extract_text_by_selectors(element, title_selectors)
            
            if not title or len(title.strip()) < 5:
                # Try to get from link text
                link = element.find('a', href=True)
                if link:
                    title = link.get_text(strip=True)
            
            if not title or len(title.strip()) < 5:
                return None
            
            price_selectors = [
                '.a-price-whole',
                '.a-price .a-offscreen',
                '.a-offscreen',
                '.a-price',
                '[data-a-color="price"]',
                '.a-price-symbol',
                '.a-price-fraction',
                'span.a-price',
                '.s-price-instructions-style',
            ]
            price = self._extract_text_by_selectors(element, price_selectors)
            
            # If price not found, try to extract from price span
            if not price:
                price_span = element.find('span', class_=re.compile(r'price|Price'))
                if price_span:
                    price = price_span.get_text(strip=True)
            
            # Improved discount extraction with more selectors
            discount_selectors = [
                '.savingsPercentage',
                '.a-badge-text',
                '[data-a-badge-color="sx-lightning-deal-red"]',
                '.a-size-base.a-color-price',  # Price savings
                '.a-color-price',  # Price color indicators
                '[aria-label*="%"]',  # Any element with percentage
            ]
            discount = self._extract_text_by_selectors(element, discount_selectors)
            
            # Also check for deal badges
            deal_badge_selectors = [
                '[data-a-badge-color="sx-lightning-deal-red"]',
                '.a-badge-text:contains("Lightning")',
                '.a-badge-text:contains("Deal")',
                '.a-badge-text:contains("Limited")',
            ]
            deal_badge = self._extract_text_by_selectors(element, deal_badge_selectors)
            if deal_badge and not discount:
                discount = deal_badge
            
            rating_selectors = [
                '.a-icon-alt',
                '[aria-label*="stars"]',
                '[aria-label*="out of"]',
                '.a-icon-star',
                'span[aria-label]',
            ]
            rating_text = self._extract_text_by_selectors(element, rating_selectors)
            rating = self._extract_rating(rating_text) if rating_text else 0.0
            
            # Also try to extract from star elements
            if rating == 0.0:
                star_elements = element.find_all(class_=re.compile(r'star|rating|Rating'))
                for star_elem in star_elements:
                    aria_label = star_elem.get('aria-label', '')
                    if aria_label:
                        rating = self._extract_rating(aria_label)
                        if rating > 0:
                            break
            
            review_selectors = [
                '.a-size-base',
                'a[href*="#customerReviews"]',
                '.a-link-normal',
                'span.a-size-base',
            ]
            review_text = self._extract_text_by_selectors(element, review_selectors)
            review_count = self._extract_review_count(review_text) if review_text else 0
            
            # Try to find review count in links
            if review_count == 0:
                review_links = element.find_all('a', href=re.compile(r'reviews|ratings'))
                for link in review_links:
                    link_text = link.get_text(strip=True)
                    review_count = self._extract_review_count(link_text)
                    if review_count > 0:
                        break
            
            # Extract product image
            image_selectors = [
                'img[data-image-latency]',
                '.s-image',
                'img.a-dynamic-image',
                '[data-image-index="0"] img',
                'img.s-image',
                '.s-product-image-container img',
                'img[data-a-dynamic-image]',
                '.a-dynamic-image',
                'img[src*="images-amazon"]'
            ]
            image_url = self._extract_image_url(element, image_selectors)
            
            amazon_link = f"https://www.amazon.com/dp/{asin}"
            
            category = self._determine_category(title, element)
            
            product = Product(
                title=title.strip(),
                price=self._clean_price(price) if price else "Price not available",
                discount=self._clean_discount(discount) if discount else "",
                link=amazon_link,
                category=category,
                asin=asin,
                rating=rating,
                review_count=review_count,
                description=self._extract_description(element),
                image_url=image_url
            )
            
            return product
            
        except Exception as e:
            logger.debug(f"Error extracting product data: {e}")
            return None
    
    def _extract_text_by_selectors(self, element, selectors: List[str]) -> Optional[str]:
        """Extract text using multiple CSS selectors."""
        for selector in selectors:
            try:
                found = element.select_one(selector)
                if found and found.get_text(strip=True):
                    return found.get_text(strip=True)
            except:
                continue
        return None
    
    def _extract_image_url(self, element, selectors: List[str]) -> str:
        """Extract product image URL from HTML element."""
        for selector in selectors:
            try:
                img_element = element.select_one(selector)
                if img_element:
                    # Try src attribute first
                    image_url = img_element.get('src') or img_element.get('data-src')
                    if image_url:
                        # Clean up Amazon image URL (remove size parameters for full resolution)
                        if 'images-na.ssl-images-amazon.com' in image_url or 'images-amazon.com' in image_url:
                            # Remove size parameters to get full resolution
                            image_url = re.sub(r'\._[A-Z0-9,]+_\.', '.', image_url)
                            return image_url
            except Exception as e:
                logger.debug(f"Failed to extract image with selector {selector}: {e}")
                continue
        
        # If no image found with selectors, try to get from data attributes
        try:
            img_elem = element.select_one('img[data-a-dynamic-image]')
            if img_elem:
                import json
                try:
                    dynamic_images = img_elem.get('data-a-dynamic-image', '{}')
                    if dynamic_images:
                        dynamic_images_dict = json.loads(dynamic_images)
                        if dynamic_images_dict:
                            # Get the first (usually largest) image
                            image_url = list(dynamic_images_dict.keys())[0]
                            # Clean up the URL
                            image_url = re.sub(r'\._[A-Z0-9,]+_\.', '.', image_url)
                            return image_url
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
        except Exception as e:
            logger.debug(f"Failed to extract image from data attributes: {e}")
        
        return ""
    
    def _clean_price(self, price_text: str) -> str:
        """Clean and format price text."""
        if not price_text:
            return "Price not available"
        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
        if price_match:
            return f"${price_match.group()}"
        return price_text[:50]
    
    def _clean_discount(self, discount_text: str) -> str:
        if not discount_text:
            return ""
        percent_match = re.search(r'(\d+)%', discount_text)
        if percent_match:
            return f"{percent_match.group(1)}% off"
        return discount_text[:20]
    
    def _extract_rating(self, rating_text: str) -> float:
        """Extract rating from text."""
        if not rating_text:
            return 0.0
        
        # Try multiple patterns
        patterns = [
            r'(\d+\.?\d*)\s*out of',  # "4.5 out of 5"
            r'(\d+\.?\d*)\s*stars?',  # "4.5 stars"
            r'(\d+\.?\d*)\s*\/\s*5',  # "4.5/5"
            r'rating[:\s]+(\d+\.?\d*)',  # "rating: 4.5"
            r'(\d+\.?\d*)',  # Just a number
        ]
        
        for pattern in patterns:
            rating_match = re.search(pattern, rating_text.lower())
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                    # Validate rating is between 0 and 5
                    if 0 <= rating <= 5:
                        return rating
                except:
                    continue
        
        return 0.0
    
    def _extract_review_count(self, review_text: str) -> int:
        """Extract review count from text."""
        if not review_text:
            return 0
        
        # Handle formats like "1,234", "1.2k", "1.5K", etc.
        review_text_clean = review_text.replace(',', '').strip()
        
        # Check for "k" or "K" suffix (thousands)
        k_match = re.search(r'([\d.]+)\s*[kK]', review_text_clean)
        if k_match:
            try:
                return int(float(k_match.group(1)) * 1000)
            except:
                pass
        
        # Regular number match
        number_match = re.search(r'([\d,]+)', review_text_clean)
        if number_match:
            try:
                return int(number_match.group(1).replace(',', ''))
            except:
                pass
        
        return 0
    
    def _extract_discount_percentage(self, discount_text: str) -> float:
        """Extract discount percentage as a float."""
        if not discount_text:
            return 0.0
        
        # Look for percentage patterns: "20%", "20% off", "Save 20%", etc.
        percent_match = re.search(r'(\d+)\s*%', discount_text)
        if percent_match:
            try:
                return float(percent_match.group(1))
            except:
                pass
        
        return 0.0
    
    def _filter_catchy_deals(self, deals: List[Product]) -> List[Product]:
        """Filter deals to only include catchy ones meeting quality thresholds."""
        catchy_deals = []
        
        for deal in deals:
            discount_pct = self._extract_discount_percentage(deal.discount)
            rating = deal.rating or 0.0
            reviews = deal.review_count or 0
            
            # Check if deal meets minimum thresholds
            if (discount_pct >= self.MIN_DISCOUNT_PERCENT and 
                rating >= self.MIN_RATING and 
                reviews >= self.MIN_REVIEWS):
                catchy_deals.append(deal)
            else:
                logger.debug(f"Deal filtered out: {deal.title[:30]}... (discount: {discount_pct}%, rating: {rating}, reviews: {reviews})")
        
        return catchy_deals
    
    def _score_deal(self, deal: Product) -> float:
        """Calculate a quality score for a deal. Higher is better."""
        score = 0.0
        
        # Discount percentage (0-50 points, higher discount = higher score)
        discount_pct = self._extract_discount_percentage(deal.discount)
        score += min(discount_pct * 2, 50)  # Max 50 points for discount
        
        # Rating (0-30 points, 4.0+ gets full points)
        rating = deal.rating or 0.0
        if rating >= 4.5:
            score += 30
        elif rating >= 4.0:
            score += 20
        elif rating >= 3.5:
            score += 10
        
        # Review count (0-20 points, more reviews = more trustworthy)
        reviews = deal.review_count or 0
        if reviews >= 1000:
            score += 20
        elif reviews >= 500:
            score += 15
        elif reviews >= 100:
            score += 10
        elif reviews >= 50:
            score += 5
        
        # Deal freshness bonus (0-10 points, newer deals prioritized)
        if deal.asin in self.deal_timestamps:
            time_since_seen = datetime.now() - self.deal_timestamps[deal.asin]
            if time_since_seen < timedelta(hours=1):
                score += 10
            elif time_since_seen < timedelta(hours=6):
                score += 7
            elif time_since_seen < timedelta(hours=24):
                score += 5
        
        # Deal badge bonus (Lightning Deal, Limited Time, etc.)
        if deal.discount:
            discount_lower = deal.discount.lower()
            if 'lightning' in discount_lower or 'limited' in discount_lower:
                score += 5
        
        return score
    
    def _determine_category(self, title: str, element) -> str:
        """Determine product category from title and element."""
        title_lower = title.lower()
        
        category_map = {
            'electronics': ['phone', 'tablet', 'laptop', 'speaker', 'headphone', 'camera', 'tv', 'smart', 'wireless'],
            'home': ['kitchen', 'cooking', 'chair', 'table', 'lamp', 'bed', 'pillow', 'blanket'],
            'fashion': ['shirt', 'pants', 'dress', 'shoes', 'jacket', 'jeans', 'clothing'],
            'sports': ['fitness', 'exercise', 'gym', 'workout', 'sports', 'running', 'yoga'],
            'beauty': ['beauty', 'skincare', 'makeup', 'hair', 'cosmetic', 'shampoo'],
            'books': ['book', 'kindle', 'novel', 'textbook', 'magazine']
        }
        
        for category, keywords in category_map.items():
            if any(keyword in title_lower for keyword in keywords):
                return category
        
        return 'general'
    
    def _extract_description(self, element) -> str:
        """Extract product description or features."""
        desc_selectors = [
            '.a-size-base-plus',
            '.s-color-secondary',
            '[data-cy="secondary-recipe-collection"]'
        ]
        
        description = self._extract_text_by_selectors(element, desc_selectors)
        if description:
            return description[:200]
        
        return "Amazon product with great reviews and competitive pricing."
    
    async def get_sample_deals(self) -> List[Product]:
        """Get real deals - no sample/mock data."""
        logger.info("Fetching real Amazon deals")
        
        try:
            real_deals = await self.scrape_real_amazon_deals()
            if real_deals:
                logger.info(f"Found {len(real_deals)} real deals")
                return real_deals
        except Exception as e:
            logger.error(f"Real scraping failed: {e}")
        
        logger.warning("No real deals available from scraping")
        return []
    
    async def scrape_specific_deal(self, url: str) -> Optional[Product]:
        """Scrape a specific Amazon product from URL with validation."""
        if not self.session:
            await self.initialize()
        
        if not self.session:
            logger.error("Failed to initialize session for scraping")
            return None
        
        # Validate URL format and security
        if not url or not isinstance(url, str):
            logger.warning("Invalid URL provided: empty or not a string")
            return None
        
        # Sanitize URL - remove any potential script injections
        url = url.strip()
        if not (url.startswith('http://') or url.startswith('https://')):
            logger.warning(f"Invalid URL format (must start with http:// or https://): {url[:50]}...")
            return None
        
        # Validate it's an Amazon URL
        amazon_domains = ['amazon.com', 'amazon.co.uk', 'amazon.de', 'amazon.fr', 
                         'amazon.ca', 'amazon.com.au', 'amazon.co.jp', 'amazon.in']
        if not any(domain in url.lower() for domain in amazon_domains):
            logger.warning(f"URL is not from Amazon: {url[:50]}...")
            return None
        
        # Additional security: check for suspicious patterns
        suspicious_patterns = ['javascript:', 'data:', 'vbscript:', '<script']
        if any(pattern in url.lower() for pattern in suspicious_patterns):
            logger.warning(f"Suspicious URL pattern detected: {url[:50]}...")
            return None
        
        try:
            logger.info(f"Scraping specific deal from: {url}")
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                title = self._extract_text_by_selectors(soup, [
                    '.product-title',
                    'h1.a-size-large'
                ])
                
                price = self._extract_text_by_selectors(soup, [
                    '.a-price-whole',
                    '.a-price .a-offscreen',
                    '.price .a-price-whole'
                ])
                
                discount = self._extract_text_by_selectors(soup, [
                    '.savingsPercentage',
                    '.a-badge-text'
                ])
                
                if not title:
                    logger.warning("Could not extract product title")
                    return None
                
                asin = self._extract_asin(url)
                
                product = Product(
                    title=title.strip(),
                    price=self._clean_price(price) if price else "Price not available",
                    discount=self._clean_discount(discount) if discount else "",
                    link=url,
                    category=self._determine_category(title, soup),
                    asin=asin,
                    description=""
                )
                
                logger.info(f"Successfully scraped product: {title[:50]}...")
                return product
                
        except Exception as e:
            logger.error(f"Error scraping specific deal: {e}")
            return None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    
    def _extract_asin(self, url: str) -> str:
        """Extract ASIN from Amazon URL."""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if asin_match:
            return asin_match.group(1)
        
        asin_match = re.search(r'/gp/product/([A-Z0-9]{10})', url)
        if asin_match:
            return asin_match.group(1)
        
        return ""