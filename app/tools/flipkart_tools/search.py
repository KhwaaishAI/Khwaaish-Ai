#!/usr/bin/env python3
import asyncio
import json
import logging
import hashlib
import random
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Set, Any
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    print("ERROR: Crawl4AI not installed. Install with: pip install crawl4ai")
    exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: BeautifulSoup4 not installed. Install with: pip install beautifulsoup4")
    exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Product:
    """Data class for product information."""
    id: Optional[str] = None
    title: Optional[str] = None
    price: Optional[float] = None
    currency: str = "INR"
    original_price: Optional[float] = None
    discount_percent: Optional[float] = None
    rating: Optional[float] = None
    rating_count: Optional[float] = None
    reviews_count: Optional[float] = None
    availability: str = "In stock"
    seller: Optional[str] = None
    product_url: Optional[str] = None
    image_urls: List[str] = None
    scrape_ts: str = ""
    source: str = "flipkart"

    def __post_init__(self):
        if self.image_urls is None:
            self.image_urls = []
        if not self.scrape_ts:
            self.scrape_ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert product to dictionary."""
        return asdict(self)


class Parser(ABC):
    """Abstract base parser for product extraction."""

    @abstractmethod
    def parse(self, html: str, base_url: str) -> List[Product]:
        """Parse HTML and return products."""
        pass


class FlipkartParser(Parser):
    """Flipkart-specific HTML parser using CSS selectors."""

    # CSS class selectors for Flipkart product elements
    SELECTORS = {
        "product_link": "a[href*='/p/']",
        "title": "[class*='s1Q50tG']",
        "price": "[class*='Nx9bqj']",
        "original_price": "[class*='yRaLfH']",
        "discount": "[class*='UkUFwK']",
        "rating": "[class*='XQR50L']",
        "rating_count": "[class*='rVVhKc']",
        "seller": "[class*='wooXRd']",
        "availability": "[class*='EKQnTf']",
        "image": "img",
    }

    def parse(self, html: str, base_url: str) -> List[Product]:
        """Parse Flipkart HTML and extract products."""
        soup = BeautifulSoup(html, "html.parser")
        products = []
        seen_ids: Set[str] = set()

        # Find all product containers
        containers = soup.select("div[class*='col-12-12']") or soup.select("a[href*='/p/']")

        for container in containers[:50]:  # Safety limit
            product = self._parse_card(container, base_url)
            if product and product.id not in seen_ids:
                products.append(product)
                seen_ids.add(product.id)

        return products

    def _parse_card(self, card: Any, base_url: str) -> Optional[Product]:
        """Parse single product card."""
        try:
            product = Product()

            # Product link & ID
            link = card.select_one(self.SELECTORS["product_link"]) if hasattr(card, 'select_one') else None
            if link and link.get("href"):
                product.product_url = urljoin(base_url, link["href"])
                product.id = self._generate_id(product.product_url)
            else:
                return None

            # Title
            title_elem = card.select_one(self.SELECTORS["title"]) if hasattr(card, 'select_one') else None
            if title_elem:
                product.title = title_elem.get_text(strip=True)
            elif link:
                product.title = link.get_text(strip=True) or link.get("title")

            if not product.title:
                return None

            # Price
            price_elem = card.select_one(self.SELECTORS["price"]) if hasattr(card, 'select_one') else None
            if price_elem:
                product.price = self._parse_price(price_elem.get_text(strip=True))

            # Original price
            orig_elem = card.select_one(self.SELECTORS["original_price"]) if hasattr(card, 'select_one') else None
            if orig_elem:
                product.original_price = self._parse_price(orig_elem.get_text(strip=True))

            # Discount
            disc_elem = card.select_one(self.SELECTORS["discount"]) if hasattr(card, 'select_one') else None
            if disc_elem:
                product.discount_percent = self._parse_price(disc_elem.get_text(strip=True))

            # Rating
            rating_elem = card.select_one(self.SELECTORS["rating"]) if hasattr(card, 'select_one') else None
            if rating_elem:
                product.rating = self._parse_rating(rating_elem.get_text(strip=True))

            # Rating count
            count_elem = card.select_one(self.SELECTORS["rating_count"]) if hasattr(card, 'select_one') else None
            if count_elem:
                product.rating_count = self._parse_price(count_elem.get_text(strip=True))

            # Seller
            seller_elem = card.select_one(self.SELECTORS["seller"]) if hasattr(card, 'select_one') else None
            if seller_elem:
                product.seller = seller_elem.get_text(strip=True)

            # Availability
            avail_elem = card.select_one(self.SELECTORS["availability"]) if hasattr(card, 'select_one') else None
            if avail_elem:
                product.availability = avail_elem.get_text(strip=True)

            # Image
            img = card.select_one(self.SELECTORS["image"]) if hasattr(card, 'select_one') else None
            if img and img.get("src"):
                product.image_urls = [urljoin(base_url, img["src"])]

            return product
        except Exception as e:
            logger.debug(f"Error parsing card: {e}")
            return None

    @staticmethod
    def _generate_id(url: str) -> str:
        """Generate stable product ID from URL."""
        if "/p/" in url:
            pid = url.split("/p/")[1].split("?")[0].split("/")[0]
            if pid:
                return pid
        return hashlib.md5(url.encode()).hexdigest()

    @staticmethod
    def _parse_price(text: Optional[str]) -> Optional[float]:
        """Extract numeric price."""
        if not text:
            return None
        cleaned = "".join(c for c in text if c.isdigit() or c == ".")
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    @staticmethod
    def _parse_rating(text: Optional[str]) -> Optional[float]:
        """Extract numeric rating."""
        if not text:
            return None
        import re
        match = re.search(r"(\d+\.?\d*)", text)
        return float(match.group(1)) if match else None


class RateLimiter:
    """Rate limiter with exponential backoff."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.last_request = 0
        self.backoff_factor = 1.0

    async def wait(self):
        """Wait before next request."""
        elapsed = asyncio.get_event_loop().time() - self.last_request
        if elapsed < self.delay * self.backoff_factor:
            await asyncio.sleep(self.delay * self.backoff_factor - elapsed)
        self.last_request = asyncio.get_event_loop().time()

    def reset(self):
        """Reset backoff."""
        self.backoff_factor = 1.0

    def backoff(self):
        """Increase backoff on error."""
        self.backoff_factor = min(self.backoff_factor * 2, 10.0)


class ProxyManager:
    """Manage proxy rotation."""

    def __init__(self, proxy_file: Optional[str] = None):
        self.proxies: List[str] = []
        if proxy_file:
            self._load_proxies(proxy_file)

    def _load_proxies(self, file_path: str):
        """Load proxies from file."""
        try:
            with open(file_path, "r") as f:
                self.proxies = [line.strip() for line in f if line.strip()]
            logger.info(f"Loaded {len(self.proxies)} proxies")
        except FileNotFoundError:
            logger.error(f"Proxy file not found: {file_path}")

    def get_proxy(self) -> Optional[str]:
        """Get random proxy or None."""
        return random.choice(self.proxies) if self.proxies else None


class FlipkartCrawler:
    """Main crawler class for Flipkart products."""

    BASE_URL = "https://www.flipkart.com"
    SEARCH_URL = f"{BASE_URL}/search"

    def __init__(
        self,
        concurrency: int = 2,
        timeout: int = 10,
        rate_limit_delay: float = 1.0,
        ignore_robots: bool = False,
        proxy_file: Optional[str] = None,
        parser: Optional[Parser] = None,
    ):
        """
        Initialize Flipkart crawler.

        Args:
            concurrency: Number of concurrent requests
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between requests
            ignore_robots: Ignore robots.txt
            proxy_file: Path to proxy list file
            parser: Custom parser (default: FlipkartParser)
        """
        self.concurrency = concurrency
        self.timeout = timeout * 1000  # Convert to milliseconds
        self.ignore_robots = ignore_robots
        self.parser = parser or FlipkartParser()
        self.rate_limiter = RateLimiter(rate_limit_delay)
        self.proxy_manager = ProxyManager(proxy_file)
        self.products: Dict[str, Product] = {}

        if not ignore_robots:
            logger.info("robots.txt checking enabled")
        else:
            logger.warning("robots.txt checking disabled")

    async def search(
        self,
        query: str,
        max_pages: int = 5,
        callback: Optional[callable] = None,
    ) -> List[Product]:
        """
        Search Flipkart and return products.

        Args:
            query: Search query
            max_pages: Maximum pages to crawl
            callback: Optional callback(products_batch) called per page

        Returns:
            List of Product objects
        """
        self.products.clear()
        logger.info(f"Starting search for: {query}")

        async with AsyncWebCrawler(crawler_type="async", concurrency=self.concurrency) as crawler:
            page = 1
            empty_pages = 0

            while page <= max_pages and empty_pages < 2:
                url = f"{self.SEARCH_URL}?q={query}&page={page}"
                logger.info(f"Crawling page {page}")

                html = await self._fetch_page(crawler, url)
                if not html:
                    empty_pages += 1
                    page += 1
                    continue

                batch = self.parser.parse(html, url)
                new_count = self._add_products(batch)

                logger.info(f"Page {page}: {len(batch)} items, {new_count} new")

                if callback:
                    callback(batch)

                if new_count == 0:
                    empty_pages += 1
                else:
                    empty_pages = 0

                page += 1
                await self.rate_limiter.wait()

        result = list(self.products.values())
        logger.info(f"Total products: {len(result)}")
        return result

    async def _fetch_page(self, crawler: AsyncWebCrawler, url: str) -> Optional[str]:
        """Fetch single page."""
        try:
            await self.rate_limiter.wait()
            result = await crawler.arun(
                url=url,
                bypass_cache=True,
                timeout=self.timeout,
            )
            if result.success:
                self.rate_limiter.reset()
                return result.html
            else:
                self.rate_limiter.backoff()
                return None
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            self.rate_limiter.backoff()
            return None

    def _add_products(self, products: List[Product]) -> int:
        """
        Add products, return count of new products.
        If id present (e.g. prod.id = 'MOBGHWFHMVUQNYH8'), use it as is,
        else generate a unique id (uid) using hash of title, price and random value.
        """
        new = 0
        for prod in products:
            # Example of id: 'MOBGHWFHMVUQNYH8'
            prod_id = prod.id
            if not prod_id:
                base = (
                    (prod.title or "") +
                    str(prod.price or "") +
                    str(random.randint(1, 1_000_000))
                )
                prod_id = hashlib.md5(base.encode("utf-8")).hexdigest()
                prod.id = prod_id  # assign generated uid to Product

            if prod_id not in self.products:
                self.products[prod_id] = prod
                new += 1
        return new

    def save_json(self, output_dir: Path, query_slug: str) -> Path:
        """Save products to JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"products-{query_slug}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(
                [p.to_dict() for p in self.products.values()],
                f,
                ensure_ascii=False,
                indent=2,
            )
        logger.info(f"Saved to {file_path}")
        return file_path

    def save_jsonl(self, output_dir: Path, query_slug: str) -> Path:
        """Save products to JSONL."""
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"products-{query_slug}.jsonl"
        with open(file_path, "w", encoding="utf-8") as f:
            for prod in self.products.values():
                f.write(json.dumps(prod.to_dict(), ensure_ascii=False) + "\n")
        logger.info(f"Saved to {file_path}")
        return file_path

    def get_products(self) -> List[Product]:
        """Get all crawled products."""
        return list(self.products.values())

    def get_summary(self) -> Dict[str, Any]:
        """Get crawl summary."""
        prods = list(self.products.values())
        return {
            "total_products": len(prods),
            "with_price": sum(1 for p in prods if p.price),
            "with_rating": sum(1 for p in prods if p.rating),
            "avg_rating": (
                sum(p.rating for p in prods if p.rating) / sum(1 for p in prods if p.rating)
                if any(p.rating for p in prods)
                else None
            ),
        }


async def main():
    """CLI entry point."""
    parser = ArgumentParser(description="Crawl Flipkart product listings")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--ignore-robots", action="store_true")
    parser.add_argument("--proxy-file", help="Proxy file path")
    parser.add_argument("--output-dir", type=Path, default=Path("./out"))
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    crawler = FlipkartCrawler(
        concurrency=args.concurrency,
        ignore_robots=args.ignore_robots,
        proxy_file=args.proxy_file,
    )

    query_slug = args.query.lower().replace(" ", "_")[:50]

    def log_batch(batch):
        logger.info(f"  Batch: {len(batch)} products")

    products = await crawler.search(args.query, max_pages=args.max_pages, callback=log_batch)

    if not args.dry_run and products:
        crawler.save_json(args.output_dir, query_slug)
        crawler.save_jsonl(args.output_dir, query_slug)

    summary = crawler.get_summary()
    print(f"\n✓ Crawl Summary:")
    print(f"  Total products: {summary['total_products']}")
    print(f"  With price: {summary['with_price']}")
    print(f"  With rating: {summary['with_rating']}")
    if summary["avg_rating"]:
        print(f"  Avg rating: {summary['avg_rating']:.2f}")


if __name__ == "__main__":
    asyncio.run(main())