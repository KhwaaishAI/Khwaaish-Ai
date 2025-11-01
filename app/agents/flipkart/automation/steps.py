import asyncio
import json
import os
import urllib.parse
from typing import Dict, Optional, Any, List
from app.tools.flipkart_tools.search import FlipkartCrawler, Product
from app.agents.flipkart.automation.core import FlipkartAutomation
import time
from pathlib import Path


class FlipkartSteps:
    def __init__(self, automation: FlipkartAutomation):
        self.automation = automation
        self.page = automation.page
        self.logger = automation.logger
        self.config = automation.config
        self.current_product = None
        self.shipping_info = None
        self.search_url = None
        self.user_session_file = "user_session.json"
        self.user_data = self._load_user_session()
        
        
        self.selectors = {
            "size": ["button:has-text('10')", "text='10'", "._3V2wfe._1fGeJ5._2UyeeK", "[data-qa*='size']"],
            "color": ["button:has-text('Black')", "text='Black'", "[data-qa*='color']"],
            "add_to_cart": ["button:has-text('Add to Cart')", "button:has-text('ADD TO CART')", "[data-qa='add-to-cart']"],
            "buy_now": ["button:has-text('Buy Now')", "button:has-text('BUY NOW')"],
            "cart_icon": ["._3SkBxJ", "[href*='viewcart']", "a[href*='cart']"],
            "place_order": ["text=Place Order", "button:has-text('Place Order')"],
            "login": ["button:has-text('Login')", "text=Login"],
            "phone_input":["input[autocomplete='off']","input.r4vIwl.Jr-g+f","input[type='tel']","#container > div > div.VCR99n > div > div.Sm1-5F.col.col-3-5 > div > form > div.I-qZ4M.vLRlQb > input"],
            "continue_btn": ["button._2KpZ6l._2HKlqd", "button[type='submit']", "button:has-text('Continue')"],
            "otp_input": ["input.r4vIwl.zgwPDa.Jr-g+f", "input[type='text'][maxlength='6']", "input[placeholder*='OTP']"],
            "pincode_input": ["#pincodeInputId", "input[placeholder*='Pincode']", "._2JC05C"],
            "check_btn": ["button:has-text('Check')", "button:has-text('Check Delivery')"]
        }

    def _load_user_session(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.user_session_file):
                with open(self.user_session_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_user_session(self):
        try:
            with open(self.user_session_file, 'w') as f:
                json.dump(self.user_data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Could not save session: {str(e)}")

    async def _find_element(self, selectors: List[str], timeout: int = 5000, click: bool = False) -> bool:
        """Universal element finder - returns True if found/clicked"""
        for selector in selectors:
            try:
                if await self.page.is_visible(selector, timeout=timeout):
                    if click:
                        await self.page.click(selector)
                    return True
            except:
                continue
        return False

    async def _fill_input(self, value: str, selectors: List[str], timeout: int = 5000) -> bool:
        """Universal input filler"""
        for selector in selectors:
            try:
                if await self.page.is_visible(selector, timeout=timeout):
                    await self.page.click(selector)
                    await asyncio.sleep(0.3)
                    await self.page.fill(selector, value)
                    return True
            except:
                continue
        return False

    async def login_enter_phone(self, phone: str) -> bool:
        """
        API-friendly function: Enters the phone number and requests the OTP.
        Called by /login/start.
        """
        self.logger.info(f"🔐 Starting API login for phone: {phone}")

        # Fill phone
        if not await self._fill_input(phone, self.selectors["phone_input"]):
            self.logger.error("❌ Phone input not found")
            return False
        self.logger.info("✅ Phone entered")

        # Click continue
        if not await self._find_element(self.selectors["continue_btn"], click=True):
            self.logger.warning("⚠️ Continue button not found")
            return False
        
        await asyncio.sleep(2)  # Wait for OTP page to presumably load
        self.logger.info("✅ OTP requested, page is waiting for input.")
        return "✅ OTP requested, page is waiting for input."

    async def login_submit_otp(self, otp: str) -> bool:
        """
        API-friendly function: Submits the OTP to complete login.
        Called by /login/verify.
        """
        self.logger.info("🔐 Submitting OTP...")

        # Fill OTP
        if not await self._fill_input(otp, self.selectors["otp_input"]):
            self.logger.error("❌ OTP input not found")
            return False
        self.logger.info("✅ OTP entered")

        # Click signup/login button
        await asyncio.sleep(1)
        if not await self._find_element(self.selectors["continue_btn"], timeout=5000, click=True):
             self.logger.error("❌ Login/Verify button not found")
             return False
        
        await self.page.wait_for_load_state('networkidle')
        
        # You should add a check here to confirm login was successful
        # e.g., check for "My Account" element

        self.user_data['logged_in'] = True
        self.user_data['login_timestamp'] = time.time()
        self._save_user_session()
        self.logger.info("✅ Login successful")
        return "✅ Login successful"

    async def _login_with_phone(self, phone:Optional[int], use_session:bool):
        """
        Optimized phone login - FOR SCRIPT USE ONLY (due to input()).
        This is your original function, left here for your reference
        or for running as a standalone script.
        """
        self.logger.warning("Using legacy _login_with_phone with input(). This will block an API server.")
        if use_session:
            session_file = "user_shipping_session.json"
            phone = None
            try:
                if os.path.exists(session_file):
                    with open(session_file, 'r') as f:
                        phone = json.load(f).get('mobile', '').strip()
            except:
                pass

        if not phone:
            phone = phone or input("📱 Enter phone number: ").strip() # <--- BLOCKS API

        self.logger.info("🔐 Starting phone login...")

        # Fill phone
        if not await self._fill_input(phone, self.selectors["phone_input"]):
            self.logger.error("❌ Phone input not found")
            return False
        self.logger.info("✅ Phone entered")

        # Click continue
        if not await self._find_element(self.selectors["continue_btn"], click=True):
            self.logger.warning("⚠️ Continue button not found")
        await asyncio.sleep(2)

        # Fill OTP
        otp = input("Enter OTP: ").strip() # <--- BLOCKS API
        if not await self._fill_input(otp, self.selectors["otp_input"]):
            self.logger.error("❌ OTP input not found")
            return False
        self.logger.info("✅ OTP entered")

        # Click signup
        await asyncio.sleep(1)
        await self._find_element(self.selectors["continue_btn"], timeout=3000, click=True)
        await self.page.wait_for_load_state('networkidle')

        self.user_data['logged_in'] = True
        self.user_data['login_timestamp'] = time.time()
        self._save_user_session()
        self.logger.info("✅ Login successful")
        return True

    async def step_0_generate_search_url(self):
        """Generate search URL"""
        if not self.current_product:
            raise Exception("No product information available")
        
        search_query = self.current_product.get('name', '')
        self.search_url = f"https://www.flipkart.com/search?q={urllib.parse.quote_plus(search_query)}"
        await self.page.goto(self.search_url, wait_until="networkidle")
        self.logger.info(f"🌐 Search URL: {self.search_url}")
        return

    async def step_1_launch_search_url(self):
        """Launch search and select product"""
        self.logger.info("🚀 Launching search...")
        
        try:
            extracter = FlipkartCrawler()
            product_list = await extracter.search(self.current_product.get('name', ''))
            if not product_list:
                self.logger.warning("❌ No products found")
                return False
        except Exception as e:
            self.logger.warning(f"Product extraction error: {e}")
            return False
        
        await self.page.goto(self.search_url, wait_until="networkidle")
        selected_url = await self._display_and_select_products(product_list)
        summary = extracter.get_summary()
        print(f"\n✓ Search Summary:")
        print(f"  Total products: {summary['total_products']}")
        print(f"  With price: {summary['with_price']}")
        print(f"  With rating: {summary['with_rating']}")
        if summary["avg_rating"]:
            print(f"  Avg rating: {summary['avg_rating']:.2f}")
            
        if selected_url:
            self.search_url = selected_url
            await self.page.goto(selected_url, wait_until="networkidle")
            self.logger.info("✅ Product selected")
            return True
        return False

    async def _display_and_select_products(self, products: List["Product"]) -> Optional[str]:
        """Display Product objects (Flipkart results) and get user's selection."""
        if not products:
            print("No products found.")
            return None

        print("\n" + "=" * 80)
        print("🛍️  AVAILABLE PRODUCTS")
        print("=" * 80)

        for idx, p in enumerate(products, 1):
            title = (p.title or "N/A").strip()
            price = p.price
            discount = p.discount_percent
            currency = p.currency or "INR"
            rating = p.rating
            availability = p.availability or "Unknown"
            seller = p.seller or "N/A"

            # Format price display
            price_str = f"{currency} {price:,.2f}" if price is not None else "N/A"

            print(f"\n#{idx}. {title[:70]}")
            print(f"   💰 {price_str}", end="")
            if discount:
                print(f"   🔖 {discount:.0f}% off", end="")
            print()
            if rating:
                print(f"   ⭐ {rating}", end="")
            print(f"   | 🏷️ {seller}    | 📦 {availability}")

        # Ask user for a selection
        try:
            choice = input(f"\nSelect a product (1-{len(products)}) or press Enter to skip: ").strip()
            if choice:
                num = int(choice)
                if 1 <= num <= len(products):
                    selected = products[num - 1]
                    print(f"✅ Selected: {selected.title}")
                    print(f"🔗 URL: {selected.product_url}")
                    return selected.product_url
                else:
                    print("⚠️ Invalid selection number.")
        except ValueError:
            print("⚠️ Please enter a valid number.")
        except Exception as e:
            print(f"⚠️ Error: {e}")

        print("No selection made.")
        return None

    async def step_2_select_product(self, product_id: str):
        """Select product"""

        out_path = Path("./out/flipkart")
        found_url = None

        # Look for files matching pattern in ./out/flipkart
        for file in out_path.glob("products-*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    products = json.load(f)
                    for prod in products:
                        if str(prod.get("id") or "") == str(product_id):
                            found_url = prod.get("product_url")
                            break
                    if found_url:
                        break
            except Exception:
                continue

        self.selected_url = found_url
        return self.selected_url

    async def step_3_handle_product_options(self):
        """Handle product options and delivery check"""
        self.logger.info("⚙️ Handling product options...")
        
        available = await self._check_delivery_availability()
        if not available:
            raise Exception("❌ Product not available for delivery")
        
        if self.current_product and self.current_product.get('options'):
            await self._select_product_options(self.current_product['options'])
        
        self.logger.info("✅ Product options ready")

    async def _select_product_options(self, options: dict):
        """Select product options"""
        self.logger.info(f"🎨 Selecting options: {options}")
        
        try:
            container = await self.page.query_selector("#container div._39kFie")
            if not container:
                return
            
            sections = await container.query_selector_all("div")
            
            for key, desired in options.items():
                for section in sections[2:7]:
                    buttons = await section.query_selector_all("button, li, div")
                    for btn in buttons:
                        text = (await btn.text_content() or "").strip().lower()
                        if self._matches_option(key, desired.lower(), text):
                            await btn.click()
                            await asyncio.sleep(1)
                            self.logger.info(f"✅ Selected {key}: {text}")
                            break
        except Exception as e:
            self.logger.warning(f"⚠️ Option selection failed: {e}")

    def _matches_option(self, key: str, desired: str, available: str) -> bool:
        """Check if option matches"""
        if desired in available:
            return True
        if key in ['size', 'storage', 'ram']:
            return ''.join(filter(str.isalnum, desired)) in ''.join(filter(str.isalnum, available))
        return desired.split()[0] in available if desired else False

    async def _check_delivery_availability(self) -> bool:
        """Check delivery availability"""
        self.logger.info("📦 Checking delivery...")
        
        pincode = self._get_pincode()
        if not pincode:
            return True

        if not await self._fill_input(pincode, self.selectors["pincode_input"], 3000):
            self.logger.warning("⚠️ Pincode input not found")
            return True

        await asyncio.sleep(2)
        
        if not await self._find_element(self.selectors["check_btn"], 5000, click=True):
            self.logger.warning("⚠️ Check button not found")
            return True

        await asyncio.sleep(2)

        available = ["text=Delivery available", "text=Delivery in", "text=Free Delivery"]
        unavailable = ["text=Currently Unavailable", "text=Out of Stock", "text=Not deliverable"]

        for _ in range(2):
            for sel in available:
                try:
                    if await self.page.is_visible(sel, timeout=2000):
                        self.logger.info("✅ Delivery available")
                        return True
                except:
                    pass
            for sel in unavailable:
                try:
                    if await self.page.is_visible(sel, timeout=2000):
                        self.logger.error("❌ Not available")
                        return False
                except:
                    pass
            await asyncio.sleep(1)

        return True

    def _get_pincode(self) -> Optional[str]:
        """Get pincode from session or user"""
        try:
            if os.path.exists("user_shipping_session.json"):
                with open("user_shipping_session.json", 'r') as f:
                    return json.load(f).get('pincode')
        except:
            pass
        return input("📍 Enter pincode: ").strip() or None

    async def step_4_add_to_cart_without_login(self):
        """Add to cart"""
        self.logger.info("🛒 Adding to cart...")
        
        if not await self._is_product_page():
            raise Exception("Not on product page")

        await asyncio.sleep(1)
        await self.page.wait_for_load_state('networkidle')
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        if await self._find_element(self.selectors["add_to_cart"], click=True):
            self.logger.info("✅ Added to cart")
            return
        
        if await self._find_element(self.selectors["buy_now"], click=True):
            self.logger.info("✅ Buy Now clicked")
            return

        raise Exception("Could not add to cart")

    async def _is_product_page(self) -> bool:
        """Check if on product page"""
        return any(x in self.page.url for x in ['/p/', '/product/', 'pid='])

    async def step_6_proceed_to_shipping(self):
        """Proceed to shipping"""
        self.logger.info("🏠 Proceeding to shipping...")
        
        if 'cart' not in self.page.url.lower():
            await self._go_to_cart()
        
        if 'login' in self.page.url.lower() or await self._check_login_required():
            self.logger.info("🔐 Login required")
            use_session = os.path.exists("user_shipping_session.json")
            await self._login_with_phone(phone=None, use_session=use_session) # Fixed: added phone=None

        if not await self._find_element(self.selectors["place_order"], click=True):
            self.logger.error("❌ Could not click Place Order")
            input("Press Enter after manual click: ")

        await asyncio.sleep(2)
        
        if 'login' in self.page.url.lower() or await self._check_login_required():
            self.logger.info("🔐 Login required")
            use_session = os.path.exists("user_shipping_session.json")
            await self._login_with_phone(phone=None, use_session=use_session) # Fixed: added phone=None
        else:
            self.logger.info("✅ Already logged in")

    async def _go_to_cart(self):
        """Navigate to cart"""
        if await self._find_element(self.selectors["cart_icon"], click=True):
            await self.page.wait_for_load_state('networkidle')
        else:
            await self.page.goto("https://www.flipkart.com/viewcart", wait_until="networkidle")
        self.logger.info("✅ Cart page loaded")

    async def _check_login_required(self) -> bool:
        """Check if login required"""
        login_texts = ["text=Login to continue", "text=Please login", "text=Sign in to continue"]
        return await self._find_element(login_texts, 3000)

    async def step_7_fill_shipping_info(self):
        """Fill shipping information"""
        self.logger.info("🏠 Filling shipping info...")
        
        if not self.shipping_info:
            self.logger.warning("⚠️ No shipping info available")
            return

        field_map = {
            "name": ["name", "fullname", "customerName"],
            "mobile": ["mobile", "phone", "contact"],
            "pincode": ["pincode", "zipcode"],
            "address": ["address", "street", "line1"],
            "city": ["city", "town"],
            "state": ["state", "region"]
        }

        for field, patterns in field_map.items():
            value = self.shipping_info.get(field, '')
            if value:
                for pattern in patterns:
                    if await self._fill_input(str(value), [f"input[name*='{pattern}']"], 3000):
                        break

        await asyncio.sleep(1)
        await self._find_element(["button:has-text('Continue')", "button:has-text('Save')"], click=True)
        await self.page.wait_for_load_state('networkidle')
        self.logger.info("✅ Shipping info submitted")

    async def step_8_proceed_to_payment(self):
        """Proceed to payment"""
        self.logger.info("💰 Proceeding to payment...")
        
        # payment_selectors = ["button:has-text('Proceed to Pay')", "button:has-text('Proceed to Payment')"]
        # if await self._find_element(payment_selectors, 10000, click=True):
        self.logger.info("🎯 Ready for manual payment...")
        print("💳 Complete payment manually. Browser will stay open for 10 minutes...")
        await asyncio.sleep(60)
