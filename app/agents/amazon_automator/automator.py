# amazon_automator/automator.py
import asyncio
import json
import logging
import re
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from app.tools.Amazon_tools.search import AmazonScraper
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, expect

logger = logging.getLogger(__name__)


@dataclass
class ProductSelection:
    """Represents user's product selection."""
    asin: str
    title: str
    url: str
    specifications: Dict[str, str]


class AmazonAutomator:
    """
    Top-level orchestrator for Amazon product search, selection, and checkout.
    
    Integrates with AmazonScraper for initial search results.
    Uses Playwright for interactive browser automation.
    """
    
    # Common selectors for Amazon product pages
    SELECTORS = {
        'add_to_cart': [
            '#add-to-cart-button',
            'button[name="submit.add-to-cart"]',
            'button:has-text("Add to Cart")',
            '[data-feature-name="add-to-cart"]',
        ],
        'proceed_checkout': [
            'input[name="proceedToRetail"]',
            'input[name="proceedToCheckout"]',
            '#sc-buy-box-ptc-button input',
            'input#sc-buy-box-ptc-button',
            'button:has-text("Proceed to Checkout")',
            'a:has-text("Proceed to Checkout")',
        ],
        'login_email': [
            '#ap_email',
            'input[name="email"]',
            'input[type="email"]',
        ],
        'login_password': [
            '#ap_password',
            'input[name="password"]',
            'input[type="password"]',
        ],
        'login_submit': [
            '#continue',
            '#signInSubmit',
            'input#signInSubmit',
            'input#continue',
            'button:has-text("Sign in")',
            'input[type="submit"][aria-labelledby*="continue"]',
        ],
        'password_submit': [
            '#signInSubmit',
            'input#signInSubmit',
            'button#signInSubmit',
            'button:has-text("Sign in")',
            'input[type="submit"][aria-labelledby*="signInSubmit"]',
        ],
        'otp_input': [
            '#auth-mfa-otpcode',
            'input[name="mfaCode"]',
            'input[placeholder*="OTP"]',
        ],
        'otp_submit': [
            '#auth-mfa-confirm-button',
            'button:has-text("Verify")',
        ],
        'cart_count': [
            '#nav-cart-count',
            '[data-feature-name="cart-count"]',
        ],
    }
    
    def __init__(
        self,
        scraper: Optional['AmazonScraper'] = None,
        headful: bool = False,
        session_store_path: Optional[str] = None,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        throttle: float = 2.0,
        dry_run: bool = False,
        timeout: int = 30000,
        ):
        """
        Initialize Amazon Automator.
        
        Args:
            scraper: AmazonScraper instance for initial search
            headful: Show browser window (for debugging)
            session_store_path: Path to save/load Playwright session storage
            proxy: Proxy URL (format: http://user:pass@host:port)
            user_agent: Custom user agent string
            throttle: Delay between actions (seconds)
            dry_run: Simulate actions without clicking/changing state
            timeout: Default timeout for page operations (ms)
        """
        # BUGFIX: Use the provided scraper if available, otherwise create a new one.
        self.scraper = scraper or AmazonScraper()
        self.headful = headful
        self.session_store_path = session_store_path or ".amazon_session.json"
        self.proxy = proxy
        self.user_agent = user_agent
        self.throttle = throttle
        self.dry_run = dry_run
        self.timeout = timeout
        
        # State
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.current_product: Optional[ProductSelection] = None
        self.displayed_products: List[Dict] = []
        
        logger.info(f"AmazonAutomator initialized (dry_run={dry_run}, headful={headful})")
    
    async def _get_throttle_delay(self) -> float:
        """Return throttle delay with small random jitter for human-like behavior."""
        import random
        return self.throttle + random.uniform(0, 0.5)
    
    async def _print_interactive(self, message: str, require_confirm: bool = False) -> bool:
        """
        Print message and optionally require user confirmation.
        
        Args:
            message: Message to display
            require_confirm: If True, ask for user confirmation before proceeding
        
        Returns:
            True if user confirms or message is info-only
        """
        print(f"\n{'='*70}")
        print(message)
        print('='*70)
        
        if require_confirm:
            response = input("\n⚠️  Proceed? (yes/no): ").strip().lower()
            return response in ['yes', 'y']
        return True
    
    async def initialize_browser(self):
        """Initialize Playwright browser and context."""
        logger.info("Initializing Playwright browser...")
        
        playwright = await async_playwright().start()
        
        browser_kwargs = {
            # BUGFIX: Correctly use the headful flag from __init__
            'headless': not self.headful,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-web-resources',
            ]
        }
        
        # if self.proxy:
        #     browser_kwargs['proxy'] = {'server': self.proxy}
        
        self.browser = await playwright.chromium.launch(**browser_kwargs)
        
        context_kwargs = {
            'viewport': {'width': 1280, 'height': 720},
        }
        
        if self.user_agent:
            context_kwargs['user_agent'] = self.user_agent
        
        # Load existing session if available
        if Path(self.session_store_path).exists():
            try:
                with open(self.session_store_path, 'r') as f:
                    context_kwargs['storage_state'] = json.load(f)
                logger.info(f"Loaded session from {self.session_store_path}")
            except Exception as e:
                logger.warning(f"Could not load session: {e}")
        
        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await self.context.new_page()
        
        # Set default timeout
        self.page.set_default_timeout(self.timeout)
        
        logger.info("Browser initialized successfully")
    
    async def close_browser(self):
        """Close browser and save session."""
        if self.context and self.session_store_path:
            try:
                await self.context.storage_state(path=self.session_store_path)
                logger.info(f"Session saved to {self.session_store_path}")
            except Exception as e:
                logger.warning(f"Could not save session: {e}")
        
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        
        logger.info("Browser closed")
    
    async def find_element_safely(
        self,
        selectors: List[str],
        page: Optional[Page] = None,
        timeout: Optional[int] = None,
        ) -> Optional[Any]:
        """
        Try multiple selectors and return first matching locator.
        
        Args:
            selectors: List of CSS/text selectors to try
            page: Page object (defaults to self.page)
            timeout: Timeout in ms
        
        Returns:
            Playwright locator or None if not found
        """
        page = page or self.page
        timeout = timeout or 5000
        
        for selector in selectors:
            try:
                locator = page.locator(selector)
                await locator.wait_for(state='visible', timeout=timeout)
                logger.debug(f"Found element with selector: {selector}")
                return locator
            except Exception as e:
                logger.debug(f"Selector '{selector}' failed: {e}")
                continue
        
        logger.warning(f"No element found from selectors: {selectors}")
        return None
    
    async def safe_click(self, locator, dry_run: Optional[bool] = None, delay: bool = True):
        """
        Safely click element with optional dry-run and delay.
        
        Args:
            locator: Playwright locator
            dry_run: Override self.dry_run (optional)
            delay: Add throttle delay after click
        """
        dry = dry_run if dry_run is not None else self.dry_run
        
        if dry:
            logger.info(f"[DRY RUN] Would click: {locator}")
        else:
            try:
                await locator.scroll_into_view_if_needed()
                await locator.click()
                logger.info(f"Clicked: {locator}")
            except Exception as e:
                logger.error(f"Click failed: {e}")
                raise
        
        if delay:
            await asyncio.sleep(await self._get_throttle_delay())
    
    async def safe_fill(
        self,
        locator,
        value: str,
        dry_run: Optional[bool] = None,
        mask_value: bool = False,
        delay: bool = True
        ):
        """
        Safely fill input with optional masking for sensitive data.
        
        Args:
            locator: Playwright locator
            value: Value to fill
            dry_run: Override self.dry_run
            mask_value: Mask value in logs (for sensitive data like OTP)
            delay: Add throttle delay
        """
        dry = dry_run if dry_run is not None else self.dry_run
        display_value = '*' * len(value) if mask_value else value
        
        if dry:
            logger.info(f"[DRY RUN] Would fill: {display_value}")
        else:
            try:
                await locator.fill(value)
                logger.info(f"Filled: {display_value}")
            except Exception as e:
                logger.error(f"Fill failed: {e}")
                raise
        
        if delay:
            await asyncio.sleep(await self._get_throttle_delay())
    
    async def wait_for_navigation_or_modal(
        self,
        timeout: int = 10000,
        ) -> bool:
        """
        Wait for navigation or modal (like CAPTCHA) to appear.
        
        Returns:
            True if navigation occurred, False if modal detected
        """
        try:
            await asyncio.wait_for(
                self.page.wait_for_load_state('networkidle'),
                timeout=timeout / 1000
            )
            logger.info("Navigation completed")
            return True
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for navigation")
            return False
    
    async def detect_captcha_or_challenge(self) -> bool:
        """
        Detect common CAPTCHA/challenge indicators.
        
        Returns:
            True if CAPTCHA/challenge detected
        """
        captcha_indicators = [
            'recaptcha',
            'imgCaptcha',
            'captcha',
            'verify',
            'robot check',
        ]
        
        html = await self.page.content()
        html_lower = html.lower()
        
        for indicator in captcha_indicators:
            if indicator in html_lower:
                logger.warning(f"Potential CAPTCHA detected: {indicator} We aware while using Automation")
                return True
        return True
    
    async def handle_captcha(self):
        """Handle CAPTCHA by pausing and asking user to solve manually."""
        message = """
        🔒 CAPTCHA DETECTED
        ===================
        A CAPTCHA or verification challenge has appeared on the page.
        This tool does NOT automatically solve CAPTCHAs (by design).

        Please solve the CAPTCHA manually in the browser window.
        Once solved, press ENTER here to resume automation.
        """
        await self._print_interactive(message, require_confirm=False)
        
        # BUGFIX: Added the missing input() to pause execution for the user.
        input("\nPress ENTER here to resume automation...")
        
        logger.info("User solved CAPTCHA; resuming...")
        await asyncio.sleep(2)
    
    async def go_to_search(self, query: str) -> List[Dict]:
        """
        Execute search using AmazonScraper and return results.
        
        Args:
            query: Search query
        
        Returns:
            List of product dicts
        """
        if not self.scraper:
            raise ValueError("AmazonScraper not provided to automator")
        
        logger.info(f"Searching for: {query}")
        result = await self.scraper.search(query)
        
        products = result.get('items', [])
        logger.info(f"Found {len(products)} products")
        
        return products
    
    def display_products(self, products: List[Dict]):
        """Display products in a nice table for user selection."""
        self.displayed_products = products
        
        print("\n" + "="*100)
        print(f"{'#':<3} {'ASIN':<12} {'Title':<50} {'Price':<12} {'Rating':<8} {'Available':<10}")
        print("="*100)
        
        for idx, product in enumerate(products[:20], start=1):  # Show max 20
            asin = product.get('asin', 'N/A')[:12]
            title_str = product.get('title') or 'N/A'
            title = (title_str[:47] + '...') if len(title_str) > 50 else title_str
            price = f"₹{product.get('price', 'N/A')}" if product.get('price') else 'N/A'
            rating = f"{product.get('rating_value', 'N/A')}" if product.get('rating_value') else 'N/A'
            available = 'Yes' if product.get('available') else 'No'
            
            print(f"{idx:<3} {asin:<12} {title:<50} {price:<12} {rating:<8} {available:<10}")
        
        print("="*100 + "\n")

    def select_product(self, product_name: str, product_index: int) -> Optional[str]:
            """
            Select product by loading from the product-specific JSON file.
            
            Args:
                product_name: The name of the product search (used to find the file).
                product_index: 1-based index (matched against 'rank_on_page').
            
            Returns:
                Selected product ASIN (string) or None if not found.
            """
            output_dir = Path("./out/Amazon")
            output_dir.mkdir(exist_ok=True)
            
            # Sanitize product name to be a safe filename
            safe_name = re.sub(r'[^a-zA-Z0-9\s]', '', product_name).strip()
            safe_name = re.sub(r'\s+', '_', safe_name).lower()
            if not safe_name:
                safe_name = "default_product"
                
            # Find the product file using the new logic
            product_file = output_dir / f"{safe_name}.json"
            
            if not product_file.exists():
                raise ValueError(f"Product file not found for '{product_name}'. Please call /search first.")

            # This will store the ASIN string
            found_asin: Optional[str] = None
            items: List[Dict] = []

            try:
                with open(product_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = data.get("items", [])
                    
                    # Keep your logic of matching product_index to rank_on_page
                    for prod in items:
                        if str(prod.get("rank_on_page")) == str(product_index):
                            found_asin = prod.get("asin")
                            break
            
            except Exception as e:
                raise ValueError(f"Failed to read or parse product file {product_file}: {e}")

            if not found_asin:
                # Keep user's original error message style
                raise ValueError(f"Could not find product with rank_on_page={product_index} in {product_file}")
            # Return the ASIN string
            return found_asin
   
    async def open_product_page(self, product_url: str):
        """
        Open product page in browser.
        
        Args:
            product_url: Full product URL or ASIN
        """
        # If ASIN provided, construct URL
        if len(product_url) == 10 and product_url.isupper():
            product_url = f"https://www.amazon.in/dp/{product_url}"
        
        if not product_url.startswith('http'):
            product_url = f"https://www.amazon.in{product_url}"
        
        logger.info(f"Opening product page: {product_url}")
        
        if not self.dry_run:
            await self.page.goto(product_url)
            await asyncio.sleep(await self._get_throttle_delay())
        
        # Check for CAPTCHA
        # await self.detect_captcha_or_challenge()
        #     await self.handle_captcha()
        
        logger.info("Product page loaded")
    
    async def find_specifications(self) -> Dict[str, List[str]]:
        """
        Scan product page and find available specifications and options.
        
        Returns:
            Dict mapping spec names to available options
        """
        logger.info("Scanning for product specifications...")
        
        specs = {}
        
        # Common spec patterns on Amazon
        spec_patterns = [
            # Color/Colour variations
            {
                'name': 'Color',
                'selectors': [
                    '[data-feature-name="color_name"]',
                    '#variation_color_name li',
                    '[aria-label*="Color"]',
                    '.variation-color',
                ]
            },
            # Storage
            {
                'name': 'Storage',
                'selectors': [
                    '[data-feature-name="storage_size"]',
                    '#variation_size_name li',
                    '[aria-label*="Storage"]',
                ]
            },
            # Size
            {
                'name': 'Size',
                'selectors': [
                    '[data-feature-name="size_name"]',
                    '#variation_size_name li',
                    '[aria-label*="Size"]',
                ]
            },
            # Configuration
            {
                'name': 'Configuration',
                'selectors': [
                    '[data-feature-name="configuration"]',
                    '#variation_configuration li',
                ]
            },
        ]
        
        for spec in spec_patterns:
            options = []
            for selector in spec['selectors']:
                try:
                    locators = self.page.locator(selector)
                    count = await locators.count()
                    
                    if count > 0:
                        for i in range(count):
                            text = await locators.nth(i).text_content()
                            if text and text.strip():
                                options.append(text.strip())
                        
                        if options:
                            specs[spec['name']] = list(set(options))  # Dedupe
                            logger.info(f"Found {spec['name']}: {options}")
                            break
                except Exception as e:
                    logger.debug(f"Spec search '{selector}' failed: {e}")
                    continue
        
        logger.info(f"Specifications found: {list(specs.keys())}")
        return specs
    
    async def choose_specifications(self, spec_preferences: Dict[str, str]):
        """
        Choose product specifications (color, storage, size, etc).
        
        Args:
            spec_preferences: Dict like {'Color': 'Black', 'Storage': '256GB'}
        """
        logger.info(f"Choosing specifications: {spec_preferences}")
        
        for spec_name, spec_value in spec_preferences.items():
            logger.info(f"Selecting {spec_name}: {spec_value}")
            
            # Try common selectors
            selectors_to_try = [
                f'[data-feature-name="{spec_name.lower()}"] li:has-text("{spec_value}")',
                f'#{spec_name.lower()}_name li:has-text("{spec_value}")',
                f'[aria-label*="{spec_name}"] [aria-label*="{spec_value}"]',
                f'button:has-text("{spec_value}")',
                f'input[value="{spec_value}"]',
            ]
            
            locator = await self.find_element_safely(selectors_to_try, timeout=3000)
            
            if locator:
                try:
                    await self.safe_click(locator)
                except Exception as e:
                    logger.error(f"Failed to select {spec_name}={spec_value}: {e}")
            else:
                logger.warning(f"Could not find selector for {spec_name}={spec_value}")
                print(f"\n⚠️  Could not automatically select {spec_name}: {spec_value}")
                # NOTE: This input() call will block the server if run via API.
                # This is part of the original logic, preserved as requested.
                response = input("Continue without this selection? (yes/no): ")
                if response.lower() not in ['yes', 'y']:
                    raise ValueError(f"User cancelled: missing {spec_name}")
        
        logger.info("Specifications selection complete")
    
    async def add_to_cart(self) -> bool:
        """
        Find and click "Add to Cart" button.
        
        Returns:
            True if successful
        """
        logger.info("Looking for 'Add to Cart' button...")
        
        locator = await self.find_element_safely(self.SELECTORS['add_to_cart'], timeout=5000)
        
        if not locator:
            logger.error("'Add to Cart' button not found")
            print("\n⚠️  'Add to Cart' button not found. Please manually locate and click the 'Add to Cart' button in the browser window.")
            # NOTE: This input() call will block the server if run via API.
            input("Once you have clicked 'Add to Cart', press ENTER to continue...")
            return True
        
        await self.safe_click(locator)
        
        # Wait for confirmation
        try:
            await asyncio.wait_for(
                self.page.wait_for_selector('[data-feature-name="atc-success"]'),
                timeout=5
            )
            logger.info("Add to cart confirmed")
        except asyncio.TimeoutError:
            logger.warning("No explicit ATC confirmation found, but click executed")
        
        await asyncio.sleep(2)
        return True
    
    async def proceed_to_checkout(self) -> bool:
        """
        Click 'Proceed to Checkout' button.
        
        Returns:
            True if successful
        """
        logger.info("Proceeding to checkout...")
        
        locator = await self.find_element_safely(
            self.SELECTORS['proceed_checkout'],
            timeout=5000
        )
        
        if not locator:
            logger.error("'Proceed to Checkout' not found")
            await self.page.goto("https://www.amazon.in/gp/cart/view.html?ref_=nav_cart")
            await asyncio.sleep(await self._get_throttle_delay())
            return True
        
        await self.safe_click(locator)
        await asyncio.sleep(3)
        
        return True
    
    async def handle_login(
        self,
        # OPTIMIZATION: Renamed 'email' to 'email_or_phone' for clarity
        email_or_phone: Optional[str] = None,
        # OPTIMIZATION: Added 'password' to allow API to pass credentials
        password: Optional[str] = None,
        ) -> bool:
        """
        Handle Amazon login flow interactively.
        
        Prompts user for credentials and OTP if needed.
        
        Args:
            email_or_phone: Email/phone (prompted if not provided)
            password: Password (prompted if not provided)
        
        Returns:
            True if login successful
        """
        logger.info("Login required. Prompting user for credentials...")
        
        # ⚠️ IMPORTANT: Never store credentials in code or logs
        message = """
        🔐 LOGIN REQUIRED
        =================
        Amazon is asking you to log in. This script will NOT store or reuse credentials.

        Email/Phone will only be used for this session.
        The session will be saved for reuse on future runs (if you confirm).
                """
        
        # OPTIMIZATION: Only show confirm prompt if we need user input
        if not email_or_phone:
            await self._print_interactive(message, require_confirm=True)
            email_or_phone = input("Enter your Amazon email or phone: ").strip()
        
        # Fill email/phone
        email_locator = await self.find_element_safely(
            self.SELECTORS['login_email'],
            timeout=3000
        )
        
        if email_locator:
            await self.safe_fill(email_locator, email_or_phone, mask_value=False)
        else:
            logger.error("Email field not found")
            print("\n⚠️  Please take manual control of the browser and enter the email")
            input("Once you have entered the email, press ENTER to continue...")
            return True
        
        # Click continue/next
        # OPTIMIZATION: Replaced redundant list with SELECTORS dict
        continue_locator = await self.find_element_safely(
            self.SELECTORS['login_submit'],
            timeout=3000
        )
        if continue_locator:
            await self.safe_click(continue_locator)
            await asyncio.sleep(2)
        
        # Handle password or OTP
        # Try password first
        password_locator = await self.find_element_safely(
            self.SELECTORS['login_password'],
            timeout=3000
        )
        
        if password_locator:
            # Password flow
            # BUGFIX: Check if password arg was provided *before* prompting.
            # This fixes the UnboundLocalError and allows API to pass the password.
            if not password:
                message_pwd = """
                  🔐 PASSWORD REQUIRED
                    ====================
                    Enter your Amazon password (will not be stored):
                          """
                await self._print_interactive(message_pwd, require_confirm=False)
                password = input("Password: ").strip()
            
            await self.safe_fill(password_locator, password, mask_value=True)
            
            # Submit login
            submit_locator = await self.find_element_safely(
                self.SELECTORS['password_submit'],
                timeout=3000
            )
            if submit_locator:
                await self.safe_click(submit_locator)
        
        else:
            # Check for OTP
            otp_locator = await self.find_element_safely(
                self.SELECTORS['otp_input'],
                timeout=5000
            )
            if otp_locator:
                message_otp = """
                📱 OTP VERIFICATION
                ===================
                Amazon has sent a One-Time Password to your registered email/phone.
                This tool does NOT intercept or read OTPs automatically (for security).

                Please paste the OTP below:
                                  """
                await self._print_interactive(message_otp, require_confirm=False)
                otp = input("Enter OTP: ").strip()
                
                await self.safe_fill(otp_locator, otp, mask_value=True)
                
                # Submit OTP
                otp_submit_locator = await self.find_element_safely(
                    self.SELECTORS['otp_submit'],
                    timeout=3000
                )
                if otp_submit_locator:
                    await self.safe_click(otp_submit_locator)
        
        # Wait for successful login
        try:
            await asyncio.wait_for(
                self.page.wait_for_load_state('networkidle'),
                timeout=10
            )
            logger.info("Login successful")
            return True
        except asyncio.TimeoutError:
            logger.warning("Timeout after login attempt")
            # It might have logged in anyway, just slowly
            return True # Assume success if timeout
    
    async def reach_payment_page(self) -> bool:
        """
        Navigate to payment page (stop before final submission).
        
        Returns:
            True if reached
        """
        logger.info("Navigating to payment page...")
        
        # Handle login if prompted
        try:
            login_check = await self.find_element_safely(
                self.SELECTORS['login_email'],
                timeout=2000
            )
            if login_check:
                logger.info("Login page detected")
                # OPTIMIZATION: This will now correctly trigger interactive prompts
                # for email/pass if they weren't passed.
                success = await self.handle_login()
                if not success:
                    logger.error("Login failed")
                    print("\n⚠️  Please take manual control of the browser to proceed with login")
                    input("Once you have loged-in, press ENTER to continue...")
                    return True
        except Exception as e:
            logger.debug(f"Login check failed: {e}")
        
        logger.info("Procede with Payment")
        print("\n⚠️  Please take manual control of the browser to proceed with the payment")
        return True
    
    async def display_checkout_summary(self):
        """Display order summary from checkout page."""
        logger.info("Extracting checkout summary...")
        
        # Try to find and extract summary information
        summary_selectors = [
            '[data-feature-name="order-summary"]',
            '.order-summary',
            '[data-a-target="order-summary-container"]',
        ]
        
        print("\n" + "="*70)
        print("CHECKOUT SUMMARY")
        print("="*70)
        
        for selector in summary_selectors:
            try:
                summary = await self.page.text_content(selector)
                if summary:
                    print(summary)
                    break
            except Exception as e:
                logger.debug(f"Summary selector '{selector}' failed: {e}")
        
        # Extract cart items
        try:
            items = await self.page.locator('[data-feature-name="item"]').count()
            logger.info(f"Cart contains {items} item(s)")
        except Exception as e:
            logger.debug(f"Could not count cart items: {e}")
        
        # Try to extract total
        try:
            total = await self.page.text_content('[data-feature-name="total"]')
            if total:
                print(f"\nTotal: {total}")
        except Exception as e:
            logger.debug(f"Could not extract total: {e}")
        
        print("="*70)
        
        message = """
        ✋ PAYMENT STOPPED HERE
        =======================
        This automation script DOES NOT submit payment for legal and security reasons.
        You must complete payment manually in the browser window.

        Specifications and items have been added to your cart.
        Review the summary above and click "Place Order" to complete your purchase.
                """
        await self._print_interactive(message, require_confirm=False)