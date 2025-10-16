import asyncio
import re
import json
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig


class FlipkartSearchTool:
    """
    A tool class for searching and extracting product information from Flipkart
    """
    
    def __init__(self, base_url="https://www.flipkart.com"):
        """
        Initialize the Flipkart Search Tool
        
        Args:
            base_url: Base URL for Flipkart (default: https://www.flipkart.com)
        """
        self.base_url = base_url
        self.product_card_selector = "div[data-id]"
        self.page_js = """
// remove modal/popups if visible
try {
  const modal = document.querySelector('div._2Xfa2_') || document.querySelector('._2KpZ6l._2doB4z');
  if (modal) { modal.remove(); }
} catch(e){}

// helper to sleep
function sleep(ms){ return new Promise(resolve => setTimeout(resolve, ms)); }

// scroll slowly to bottom to trigger lazy loading
async function progressiveScroll(steps=15, delay=300){
  const height = document.body.scrollHeight;
  for (let i=1; i<=steps; i++){
    window.scrollTo(0, Math.floor((height * i)/steps));
    await sleep(delay);
  }
  await sleep(800);
}
await progressiveScroll(15, 300);
"""
    
    async def search(self, query, save_html=True, save_json=True):
        """
        Search Flipkart for products and extract information
        
        Args:
            query: Search query string
            save_html: Whether to save extracted HTML (default: True)
            save_json: Whether to save extracted JSON (default: True)
        
        Returns:
            List of product dictionaries
        """
        search_url = f"{self.base_url}/search?q={query}"
        
        config = CrawlerRunConfig(
            css_selector=self.product_card_selector,
            extraction_strategy=None,
            markdown_generator=False,
            js_code=self.page_js,
            wait_for=self.product_card_selector,
            screenshot=False,
            pdf=False,
            capture_mhtml=False,
            verbose=True
        )
        
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=search_url, config=config)
            html = result.cleaned_html or result.raw_html or ""
            
            # Save extracted HTML section (optional)
            if save_html:
                with open(f"flipkart_search_{query}.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"✓ Saved HTML to flipkart_search_{query}.html")
            
            # If nothing extracted, show warning
            if not html.strip():
                print("⚠️ No HTML extracted. Page may be blocking crawler or structure changed.")
                return []
            
            # Parse HTML into JSON
            products = self.extract_flipkart_products(html)
            
            # Save to JSON (optional)
            if save_json:
                with open(f"flipkart_{query}.json", 'w', encoding='utf-8') as f:
                    json.dump(products, f, ensure_ascii=False, indent=2)
                print(f"✓ Saved {len(products)} products to flipkart_{query}.json")
            
            return products
    
    def extract_flipkart_products(self, html_content):
        """
        Extract product information from Flipkart search page HTML
        Handles multiple product card layouts
        
        Args:
            html_content: HTML content as string
        
        Returns:
            List of product dictionaries
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        products = []
        
        # Find all product links - they contain "/p/" in href
        product_links = soup.find_all('a', href=re.compile(r'/p/'))
        
        # Group links by product (multiple links can point to same product)
        product_groups = {}
        for link in product_links:
            href = link.get('href', '')
            if '/p/' in href:
                # Extract product ID from URL
                product_id = re.search(r'/p/([^?]+)', href)
                if product_id:
                    pid = product_id.group(1)
                    if pid not in product_groups:
                        product_groups[pid] = []
                    product_groups[pid].append(link)
        
        # Process each unique product
        for pid, links in product_groups.items():
            try:
                product = {}
                
                # Find the parent container that holds all product info
                container = None
                for link in links:
                    parent = link.find_parent('div')
                    depth = 0
                    while parent and depth < 5:
                        if parent.find('img') and len(parent.find_all('div', recursive=False)) > 1:
                            container = parent
                            break
                        parent = parent.find_parent('div')
                        depth += 1
                    if container:
                        break
                
                if not container:
                    container = links[0].find_parent('div')
                
                # Extract product URL (use first link)
                href = links[0].get('href', '')
                if href:
                    product['url'] = urljoin(self.base_url, href)
                
                # Extract product name - Try multiple methods
                name = None
                
                # Method 1: Look for title attribute in <a> tag
                for link in links:
                    title = link.get('title')
                    if title and title != '':
                        name = title
                        break
                
                # Method 2: Look for text in <a> tag
                if not name:
                    for link in links:
                        text = link.get_text(strip=True)
                        if text and len(text) > 10 and 'http' not in text:
                            name = text
                            break
                
                # Method 3: Look for image alt text
                if not name:
                    img = container.find('img') if container else None
                    if img and img.get('alt'):
                        name = img.get('alt')
                
                if name:
                    product['name'] = name
                
                # Extract brand
                brand_div = container.find('div', string=re.compile(r'^[A-Z][A-Za-z\s&]+$')) if container else None
                if brand_div:
                    brand_text = brand_div.get_text(strip=True)
                    if len(brand_text) < 30 and brand_text.isupper():
                        product['brand'] = brand_text
                
                # Extract image URL
                img = container.find('img') if container else None
                if img:
                    img_src = img.get('src', '')
                    if img_src:
                        product['image_url'] = img_src
                
                # Extract rating
                rating_div = container.find('div', string=re.compile(r'^\d+\.?\d*$')) if container else None
                if rating_div:
                    try:
                        product['rating'] = float(rating_div.get_text(strip=True))
                    except ValueError:
                        pass
                
                # Extract ratings count and reviews count
                if container:
                    ratings_text = container.find(string=re.compile(r'Ratings|Reviews'))
                    if ratings_text:
                        parent = ratings_text.find_parent()
                        if parent:
                            text = parent.get_text(strip=True)
                            
                            ratings_match = re.search(r'([\d,]+)\s*Ratings', text)
                            if ratings_match:
                                product['ratings_count'] = ratings_match.group(1).replace(',', '')
                            
                            reviews_match = re.search(r'([\d,]+)\s*Reviews', text)
                            if reviews_match:
                                product['reviews_count'] = reviews_match.group(1).replace(',', '')
                
                # Extract specifications from list items
                if container:
                    spec_list = container.find('ul')
                    if spec_list:
                        specs = []
                        for li in spec_list.find_all('li'):
                            spec_text = li.get_text(strip=True)
                            if spec_text and 'Add to Compare' not in spec_text:
                                specs.append(spec_text)
                        if specs:
                            product['specifications'] = specs
                
                # Extract prices (current price and original price)
                if container:
                    price_divs = container.find_all('div', string=re.compile(r'₹[\d,]+'))
                    prices = []
                    for price_div in price_divs:
                        price_text = price_div.get_text(strip=True)
                        price_match = re.search(r'₹([\d,]+)', price_text)
                        if price_match:
                            prices.append({
                                'value': price_match.group(1).replace(',', ''),
                                'display': price_text
                            })
                    
                    if len(prices) >= 1:
                        product['current_price'] = prices[0]['value']
                        product['current_price_display'] = prices[0]['display']
                    
                    if len(prices) >= 2:
                        product['original_price'] = prices[1]['value']
                        product['original_price_display'] = prices[1]['display']
                    
                    # Extract discount percentage
                    discount_span = container.find('span', string=re.compile(r'\d+%\s*off'))
                    if discount_span:
                        discount_text = discount_span.get_text(strip=True)
                        discount_match = re.search(r'(\d+)%', discount_text)
                        if discount_match:
                            product['discount_percentage'] = discount_match.group(1)
                
                # Extract special tags/badges
                if container:
                    badges = []
                    badge_texts = ['Top Discount', 'Best Seller', 'Trending', 'New', 'Limited', 'Sale']
                    for badge_text in badge_texts:
                        badge_div = container.find('div', string=re.compile(badge_text, re.IGNORECASE))
                        if badge_div:
                            badges.append(badge_div.get_text(strip=True))
                    if badges:
                        product['badges'] = badges
                
                # Extract availability status
                if container:
                    availability = container.find('div', string=re.compile(r'Only \d+ left|Out of Stock|Currently unavailable'))
                    if availability:
                        avail_text = availability.get_text(strip=True)
                        product['availability'] = avail_text
                        
                        # Skip products that are unavailable
                        if 'Out of Stock' in avail_text or 'unavailable' in avail_text.lower():
                            continue
                
                # Extract exchange offer
                if container:
                    exchange_div = container.find('div', string=re.compile(r'Off on Exchange'))
                    if exchange_div:
                        parent = exchange_div.find_parent('div')
                        if parent:
                            exchange_text = parent.get_text(strip=True)
                            exchange_match = re.search(r'₹([\d,]+)', exchange_text)
                            if exchange_match:
                                product['exchange_offer'] = exchange_match.group(1).replace(',', '')
                
                # Extract F-Assured badge
                if container:
                    fassured_img = container.find('img', src=re.compile(r'fa_.*\.png'))
                    if fassured_img:
                        product['f_assured'] = True
                
                # Only add product if it has at least a name or title
                if 'name' in product and product['name']:
                    products.append(product)
                    
            except Exception as e:
                print(f"Error extracting product {pid}: {e}")
                continue
        
        return products
    
    def search_sync(self, query, save_html=True, save_json=True):
        """
        Synchronous wrapper for search method
        
        Args:
            query: Search query string
            save_html: Whether to save extracted HTML (default: True)
            save_json: Whether to save extracted JSON (default: True)
        
        Returns:
            List of product dictionaries
        """
        return asyncio.run(self.search(query, save_html, save_json))


# Example usage
if __name__ == "__main__":
    # Create instance
    flipkart_tool = FlipkartSearchTool()
    
    # Search for products (async)
    async def test_search():
        products = await flipkart_tool.search("iphone 15 plus")
        print(f"\n✓ Found {len(products)} products")
        
        if products:
            print("\nFirst product:")
            print(json.dumps(products[0], indent=2, ensure_ascii=False))
    
    # Run async search
    asyncio.run(test_search())
    
    # Or use synchronous version
    # products = flipkart_tool.search_sync("iphone 15 plus")