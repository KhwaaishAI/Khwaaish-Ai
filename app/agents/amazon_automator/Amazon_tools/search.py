import asyncio
import json
import re
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from enum import Enum

# Crawl4AI imports
from crawl4ai import AsyncWebCrawler, CacheMode


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScraperStatus(Enum):
    """Status enum for scraper states."""
    IDLE = "idle"
    CRAWLING = "crawling"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class Product:
    """Product data model."""
    asin: Optional[str]
    title: Optional[str]
    url: Optional[str]
    price: Optional[float]
    price_text: Optional[str]
    currency: Optional[str]
    available: bool
    image: Optional[str]
    rating_value: Optional[float]
    rating_count: Optional[int]
    badges: list
    sponsored: bool
    rank_on_page: int
    scraped_at: str


class AmazonScraper:
    """
    Class-based Amazon.in product scraper using Crawl4AI.
    
    Attributes:
        max_pages: Maximum pages to crawl
        max_items: Maximum items to extract
        headful: Enable visible browser window
        proxies: List of proxy URLs
        user_agents: List of user agents for rotation
        throttle: Delay between requests (seconds)
        status: Current scraper status
    """
    
    # Default user agents
    DEFAULT_USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    ]
    
    # Default settings
    MAX_RETRIES = 3
    BASE_URL = "https://www.amazon.in/s?k={}"
    AMAZON_DOMAIN = "https://www.amazon.in"
    
    def __init__(
        self,
        max_pages: int = 3,
        max_items: Optional[int] = None,
        headful: bool = False,
        proxies: Optional[list] = None,
        user_agents: Optional[list] = None,
        throttle: float = 2.0
        ):
        """
        Initialize the AmazonScraper.
        
        Args:
            max_pages: Maximum pages to crawl (default: 3)
            max_items: Maximum items to extract (default: None = unlimited)
            headful: Enable visible browser window (default: False)
            proxies: List of proxy URLs (default: None)
            user_agents: Custom user agents (default: uses sensible defaults)
            throttle: Delay between requests in seconds (default: 2.0)
        """
        self.max_pages = max_pages
        self.max_items = max_items
        self.headful = headful
        self.proxies = proxies or []
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS
        self.throttle = throttle
        self.status = ScraperStatus.IDLE
        
        # State tracking
        self.all_products = []
        self.seen_asins = set()
        self.errors = []
        self.pages_crawled = 0
        self.current_page = 1
        self.next_page_url = None
        self.crawler = None
        
        logger.info(f"AmazonScraper initialized with max_pages={max_pages}, throttle={throttle}s")
    
    def reset(self):
        """Reset scraper state for a new search."""
        self.all_products = []
        self.seen_asins = set()
        self.errors = []
        self.pages_crawled = 0
        self.current_page = 1
        self.next_page_url = None
        self.status = ScraperStatus.IDLE
        logger.info("Scraper state reset")
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """Extract numeric price from text, handling INR currency."""
        if not price_text:
            return None
        cleaned = re.sub(r'[₹,\s]', '', price_text)
        match = re.search(r'(\d+(?:\.\d+)?)', cleaned)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, TypeError):
                return None
        return None
    
    def _extract_asin_from_url(self, url: str) -> Optional[str]:
        """Extract ASIN from Amazon product URL."""
        match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return match.group(1) if match else None
    
    def _extract_products_from_html(self, html: str, page_num: int) -> tuple[list[Product], bool]:
        """
        Extract products from raw HTML using CSS selectors.
        
        Args:
            html: Raw HTML content
            page_num: Current page number
        
        Returns:
            Tuple of (products list, has_captcha_detected)
        """
        from bs4 import BeautifulSoup
        
        products = []
        
        # Check for CAPTCHA/verifier pages
        captcha_indicators = [
            'robot check',
            'seems you are a bot',
            'imgCaptcha',
            'g-recaptcha'
        ]
        html_lower = html.lower()
        has_captcha = any(indicator in html_lower for indicator in captcha_indicators)
        
        if has_captcha:
            logger.warning(f"CAPTCHA detected on page {page_num}")
            return [], True
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Primary: div with data-asin attribute and s-result-item class
        product_containers = soup.select('div[data-asin].s-result-item')
        if not product_containers:
            product_containers = soup.select('div[data-asin]')
        
        logger.info(f"Found {len(product_containers)} product containers on page {page_num}")
        
        rank = 1
        for idx, container in enumerate(product_containers, start=1):
            try:
                # Extract ASIN
                asin = container.get('data-asin', '').strip()
                if not asin or asin in self.seen_asins:
                    continue
                
                # Extract title (primary + fallback)
                title = None
                title_elem = container.select_one('h2 a span')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    h2 = container.select_one('h2')
                    if h2:
                        spans = h2.find_all('span')
                        if spans:
                            title = spans[0].get_text(strip=True)
                
                # Extract URL
                url = None
                title_link = container.select_one('h2 a')
                if title_link and title_link.get('href'):
                    url = self.AMAZON_DOMAIN + title_link.get('href')
                else:
                    first_link = container.select_one('a[href*="/dp/"]')
                    if first_link:
                        url = self.AMAZON_DOMAIN + first_link.get('href')
                
                # Extract image URL
                image = None
                img_elem = container.select_one('img')
                if img_elem and img_elem.get('src'):
                    image = img_elem.get('src')
                
                # Extract price
                price_text = None
                price = None
                currency = None
                price_elem = container.select_one('.a-price-whole')
                if not price_elem:
                    price_elem = container.select_one('[data-a-color="price"]')
                if not price_elem:
                    price_elem = container.select_one('.a-price')
                
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price = self._parse_price(price_text)
                    if price_text and '₹' in price_text:
                        currency = 'INR'
                
                # Determine availability
                available = price is not None
                unavailable_elem = container.select_one('.a-size-base-plus.a-color-price')
                if unavailable_elem and 'unavailable' in unavailable_elem.get_text(strip=True).lower():
                    available = False
                
                # Extract rating value
                rating_value = None
                rating_elem = container.select_one('.a-star-small span')
                if rating_elem:
                    rating_text = rating_elem.get_text(strip=True)
                    match = re.search(r'(\d+\.?\d*)', rating_text)
                    if match:
                        rating_value = float(match.group(1))
                
                # Extract rating count
                rating_count = None
                rating_count_elem = container.select_one('.a-size-base')
                if rating_count_elem:
                    count_text = rating_count_elem.get_text(strip=True)
                    match = re.search(r'([\d,]+)', count_text)
                    if match:
                        try:
                            rating_count = int(match.group(1).replace(',', ''))
                        except ValueError:
                            pass
                
                # Extract badges
                badges = []
                badge_elems = container.select('[aria-label*="Prime"], .a-badge')
                for badge_elem in badge_elems:
                    badge_text = badge_elem.get_text(strip=True)
                    if badge_text and badge_text not in badges:
                        badges.append(badge_text)
                
                # Check if sponsored
                sponsored = bool(container.select_one('[aria-label*="Sponsored"], .a-badge-sponsored'))
                
                product = Product(
                    asin=asin,
                    title=title,
                    url=url,
                    price=price,
                    price_text=price_text,
                    currency=currency,
                    available=available,
                    image=image,
                    rating_value=rating_value,
                    rating_count=rating_count,
                    badges=badges,
                    sponsored=sponsored,
                    rank_on_page=rank,
                    scraped_at=datetime.utcnow().isoformat() + 'Z'
                )
                products.append(product)
                rank += 1
                logger.debug(f"Extracted: {asin} - {title[:50] if title else 'N/A'}")
            
            except Exception as e:
                logger.error(f"Error extracting product {idx}: {e}")
                continue
        
        return products, False
    
    async def _crawl_page(self, url: str, user_agent: str) -> Optional[str]:
        """
        Crawl a single page with retry logic.
        
        Args:
            url: URL to crawl
            user_agent: User agent string
        
        Returns:
            HTML content or None if failed
        """
        retry_count = 0
        
        while retry_count < self.MAX_RETRIES:
            try:
                logger.info(f"Crawling: {url[:80]}... (attempt {retry_count + 1}/{self.MAX_RETRIES})")
                
                result = await self.crawler.arun(
                    url=url,
                    user_agent=user_agent,
                    bypass_cache=True,
                    wait_for='window.scrollY > 1000'
                )
                
                if result.success:
                    logger.info("Successfully fetched page")
                    return result.html
                else:
                    logger.warning(f"Crawl failed: {result.error_message}")
                    retry_count += 1
                    if retry_count < self.MAX_RETRIES:
                        backoff = self.throttle * (2 ** retry_count)
                        logger.info(f"Retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
            
            except Exception as e:
                logger.error(f"Exception during crawl: {e}")
                retry_count += 1
                if retry_count < self.MAX_RETRIES:
                    backoff = self.throttle * (2 ** retry_count)
                    await asyncio.sleep(backoff)
        
        self.errors.append(f"Failed to crawl {url} after {self.MAX_RETRIES} retries")
        return None
    
    async def search(self, query: str) -> dict:
        """
        Execute the search.
        
        Args:
            query: Search query string
        
        Returns:
            Dictionary with items, errors, and metadata
        """
        self.reset()
        self.status = ScraperStatus.CRAWLING
        
        logger.info(f"Starting search for: {query}")
        
        crawler_kwargs = {
            'headless': not self.headful,
            'cache_mode': CacheMode.BYPASS,
            'verbose': True,
        }
        
        if self.proxies:
            crawler_kwargs['proxy'] = self.proxies[0] if len(self.proxies) == 1 else self.proxies
        
        try:
            async with AsyncWebCrawler(**crawler_kwargs) as crawler:
                self.crawler = crawler
                user_agent_idx = 0
                
                while (self.current_page <= self.max_pages and 
                       (self.max_items is None or len(self.all_products) < self.max_items)):
                    
                    try:
                        # Build URL
                        if self.current_page == 1:
                            url = self.BASE_URL.format(query)
                        else:
                            url = self.next_page_url or f"{self.BASE_URL.format(query)}&page={self.current_page}"
                        
                        # Select user agent
                        ua = self.user_agents[user_agent_idx % len(self.user_agents)]
                        user_agent_idx += 1
                        
                        # Crawl page
                        html_content = await self._crawl_page(url, ua)
                        
                        if html_content is None:
                            break
                        
                        # Extract products
                        products, has_captcha = self._extract_products_from_html(html_content, self.current_page)
                        
                        if has_captcha:
                            self.errors.append(f"CAPTCHA detected on page {self.current_page}; stopping")
                            break
                        
                        # Deduplicate and add
                        for product in products:
                            if product.asin not in self.seen_asins:
                                self.seen_asins.add(product.asin)
                                self.all_products.append(product)
                                
                                if self.max_items and len(self.all_products) >= self.max_items:
                                    break
                        
                        self.pages_crawled += 1
                        logger.info(f"Page {self.current_page} complete: {len(products)} products, total {len(self.all_products)}")
                        
                        # Detect next page
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html_content, 'html.parser')
                        next_link = soup.select_one('li.a-last a')
                        if not next_link:
                            next_link = soup.select_one('a[aria-label="Next"]')
                        
                        if next_link and next_link.get('href'):
                            self.next_page_url = self.AMAZON_DOMAIN + next_link.get('href')
                            self.current_page += 1
                        else:
                            logger.info("No next page found")
                            break
                        
                        # Throttle
                        if self.current_page <= self.max_pages:
                            await asyncio.sleep(self.throttle)
                    
                    except Exception as e:
                        self.errors.append(f"Error on page {self.current_page}: {str(e)}")
                        logger.error(f"Error on page {self.current_page}: {e}", exc_info=True)
                        break
        
        except Exception as e:
            self.errors.append(f"Crawler initialization error: {str(e)}")
            logger.error(f"Crawler error: {e}", exc_info=True)
            self.status = ScraperStatus.ERROR
            return self._get_result_dict(query)
        
        self.status = ScraperStatus.COMPLETE
        return self._get_result_dict(query)
    
    def _get_result_dict(self, query: str) -> dict:
        """Build result dictionary."""
        items_dicts = [asdict(p) for p in self.all_products]
        
        return {
            "items": items_dicts,
            "errors": self.errors,
            "meta": {
                "pages_crawled": self.pages_crawled,
                "items_extracted": len(self.all_products),
                "query": query,
                "status": self.status.value,
                "max_pages": self.max_pages,
                "max_items": self.max_items,
            }
        }
    
    def get_products_by_filter(self, min_rating: Optional[float] = None, 
                               max_price: Optional[float] = None,
                               available_only: bool = True) -> list[Product]:
        """
        Filter extracted products.
        
        Args:
            min_rating: Minimum rating (default: None)
            max_price: Maximum price in INR (default: None)
            available_only: Only return available products (default: True)
        
        Returns:
            Filtered list of products
        """
        filtered = self.all_products
        
        if available_only:
            filtered = [p for p in filtered if p.available]
        
        if min_rating is not None:
            filtered = [p for p in filtered if p.rating_value and p.rating_value >= min_rating]
        
        if max_price is not None:
            filtered = [p for p in filtered if p.price and p.price <= max_price]
        
        logger.info(f"Filtered products: {len(filtered)} items")
        return filtered
    
    def export_to_json(self, filepath: str):
        """Export current products to JSON file."""
        items_dicts = [asdict(p) for p in self.all_products]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "items": items_dicts,
                "meta": {
                    "total_items": len(self.all_products),
                    "pages_crawled": self.pages_crawled,
                    "exported_at": datetime.utcnow().isoformat() + 'Z'
                }
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Exported {len(self.all_products)} items to {filepath}")
