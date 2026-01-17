import asyncio
import aiohttp
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

@dataclass
class LinkValidationResult:
    
    url: str
    is_valid: bool
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    redirect_url: Optional[str] = None
    response_time: float = 0.0

class LinkValidator:
    
    
    def __init__(self, timeout: int = 15, max_retries: int = 2, expected_affiliate_tag: str = None):
        
        self.timeout = timeout
        self.max_retries = max_retries
        self.expected_affiliate_tag = expected_affiliate_tag
        self.session = None
        
    async def initialize(self):
        
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            }
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=headers
            )
            logger.info("🔗 Link validator session initialized")

    async def close(self):
        
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("🔗 Link validator session closed")

    async def validate_link(self, url: str) -> LinkValidationResult:
        
        if not self.session:
            await self.initialize()
            
        start_time = asyncio.get_event_loop().time()
        
        try:
            if not self._is_valid_url_format(url):
                return LinkValidationResult(
                    url=url,
                    is_valid=False,
                    error_message="Invalid URL format"
                )
            
            if not self._is_amazon_link(url):
                return LinkValidationResult(
                    url=url,
                    is_valid=False,
                    error_message="Not an Amazon link"
                )
            
            for attempt in range(self.max_retries + 1):
                try:
                    headers = {'Range': 'bytes=0-1023'}
                    
                    async with self.session.get(url, headers=headers, allow_redirects=True) as response:
                        response_time = asyncio.get_event_loop().time() - start_time
                        
                        if response.status in [200, 206, 416]:
                            final_url = str(response.url)
                            
                            # If expected_tag is provided, verify it
                            if self.expected_affiliate_tag:
                                tag_valid, tag_error = self.verify_affiliate_tag(
                                    final_url, 
                                    self.expected_affiliate_tag
                                )
                                if not tag_valid:
                                    logger.warning(f"⚠️ Affiliate tag verification failed for {url[:50]}...: {tag_error}")
                                    # Still return valid=True for URL, but log the warning
                            
                            logger.debug(f"✅ Link validated: {url[:50]}... ({response.status})")
                            return LinkValidationResult(
                                url=url,
                                is_valid=True,
                                status_code=response.status,
                                redirect_url=final_url if final_url != url else None,
                                response_time=response_time
                            )
                        elif response.status == 405:
                            async with self.session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=5)) as response2:
                                if response2.status == 200:
                                    final_url = str(response2.url)
                                    
                                    # Verify affiliate tag if provided
                                    if self.expected_affiliate_tag:
                                        tag_valid, tag_error = self.verify_affiliate_tag(
                                            final_url,
                                            self.expected_affiliate_tag
                                        )
                                        if not tag_valid:
                                            logger.warning(f"⚠️ Affiliate tag verification failed (fallback) for {url[:50]}...: {tag_error}")
                                    
                                    logger.debug(f"✅ Link validated (fallback): {url[:50]}... (200 OK)")
                                    return LinkValidationResult(
                                        url=url,
                                        is_valid=True,
                                        status_code=response2.status,
                                        redirect_url=final_url if final_url != url else None,
                                        response_time=response_time
                                    )
                                else:
                                    logger.warning(f"❌ Link failed: {url[:50]}... (Status: {response2.status})")
                                    return LinkValidationResult(
                                        url=url,
                                        is_valid=False,
                                        status_code=response2.status,
                                        error_message=f"HTTP {response2.status}",
                                        response_time=response_time
                                    )
                        else:
                            logger.warning(f"❌ Link failed: {url[:50]}... (Status: {response.status})")
                            return LinkValidationResult(
                                url=url,
                                is_valid=False,
                                status_code=response.status,
                                error_message=f"HTTP {response.status}",
                                response_time=response_time
                            )
                            
                except asyncio.TimeoutError:
                    if attempt < self.max_retries:
                        logger.debug(f"⏳ Timeout on attempt {attempt + 1}, retrying: {url[:50]}...")
                        await asyncio.sleep(1)
                        continue
                    else:
                        return LinkValidationResult(
                            url=url,
                            is_valid=False,
                            error_message="Request timeout",
                            response_time=asyncio.get_event_loop().time() - start_time
                        )
                        
                except aiohttp.ClientError as e:
                    if attempt < self.max_retries:
                        logger.debug(f"🔄 Client error on attempt {attempt + 1}, retrying: {str(e)[:50]}...")
                        await asyncio.sleep(1)
                        continue
                    else:
                        return LinkValidationResult(
                            url=url,
                            is_valid=False,
                            error_message=f"Client error: {str(e)}",
                            response_time=asyncio.get_event_loop().time() - start_time
                        )
                        
        except Exception as e:
            logger.error(f"❌ Unexpected error validating link: {e}")
            return LinkValidationResult(
                url=url,
                is_valid=False,
                error_message=f"Unexpected error: {str(e)}",
                response_time=asyncio.get_event_loop().time() - start_time
            )

    async def validate_links_batch(self, urls: List[str], max_concurrent: int = 10) -> List[LinkValidationResult]:
        
        if not urls:
            return []
            
        if not self.session:
            await self.initialize()
            
        logger.info(f"🔍 Validating {len(urls)} links (max concurrent: {max_concurrent})")
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def validate_with_semaphore(url: str) -> LinkValidationResult:
            async with semaphore:
                return await self.validate_link(url)
        
        tasks = [validate_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        validated_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ Exception validating {urls[i]}: {result}")
                validated_results.append(LinkValidationResult(
                    url=urls[i],
                    is_valid=False,
                    error_message=f"Exception: {str(result)}"
                ))
            else:
                validated_results.append(result)
        
        valid_count = sum(1 for r in validated_results if r.is_valid)
        invalid_count = len(validated_results) - valid_count
        logger.info(f"✅ Validation complete: {valid_count} valid, {invalid_count} invalid links")
        
        return validated_results

    def _is_valid_url_format(self, url: str) -> bool:
        
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc)
        except Exception:
            return False

    def _is_amazon_link(self, url: str) -> bool:
        
        try:
            parsed = urlparse(url)
            amazon_domains = [
                'amazon.com', 'amazon.co.uk', 'amazon.de', 'amazon.fr', 
                'amazon.it', 'amazon.es', 'amazon.ca', 'amazon.com.mx',
                'amazon.com.br', 'amazon.in', 'amazon.co.jp', 'amazon.com.au'
            ]
            
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            
            is_amazon = domain in amazon_domains
            
            # Additional validation: check if URL contains valid ASIN pattern
            if is_amazon:
                import re
                # Check for ASIN in URL path (/dp/ASIN or /gp/product/ASIN)
                asin_pattern = r'/(?:dp|gp/product)/([A-Z0-9]{10})'
                asin_match = re.search(asin_pattern, parsed.path)
                if asin_match:
                    asin = asin_match.group(1)
                    # Validate ASIN format (10 alphanumeric characters)
                    if not re.match(r'^[A-Z0-9]{10}$', asin):
                        logger.debug(f"Invalid ASIN format in URL: {asin}")
                        return False
            
            return is_amazon
        except Exception as e:
            logger.debug(f"Error validating Amazon link: {e}")
            return False
    
    def verify_affiliate_tag(self, url: str, expected_tag: str) -> tuple:
        """Verify affiliate tag is present in URL.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url or not expected_tag:
            return False, "Missing URL or affiliate tag"
        
        try:
            from urllib.parse import urlparse, parse_qs
            
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # Check for tag parameter
            tag_values = params.get('tag', [])
            if not tag_values:
                return False, "No 'tag' parameter found in URL"
            
            actual_tag = tag_values[0]
            if actual_tag != expected_tag:
                return False, f"Tag mismatch: expected '{expected_tag}', got '{actual_tag}'"
            
            return True, "Tag verified"
            
        except Exception as e:
            return False, f"Error verifying tag: {str(e)}"

    def get_validation_stats(self, results: List[LinkValidationResult]) -> Dict[str, Any]:
        
        if not results:
            return {}
            
        valid_results = [r for r in results if r.is_valid]
        invalid_results = [r for r in results if not r.is_valid]
        
        error_types = {}
        for result in invalid_results:
            error = result.error_message or "Unknown error"
            error_types[error] = error_types.get(error, 0) + 1
        
        response_times = [r.response_time for r in results if r.response_time > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'total_links': len(results),
            'valid_links': len(valid_results),
            'invalid_links': len(invalid_results),
            'success_rate': len(valid_results) / len(results) * 100 if results else 0,
            'average_response_time': round(avg_response_time, 3),
            'error_breakdown': error_types
        }

    async def __aenter__(self):
        
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        
        await self.close()