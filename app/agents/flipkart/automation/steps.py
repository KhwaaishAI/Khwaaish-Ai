import asyncio
import json
import os
import urllib.parse
from typing import Dict, Optional, Any, List
from app.agents.flipkart.automation.core import FlipkartAutomation
import time
# from app.tools.flipkart_tools.search import FlipkartExtractor 

class FlipkartSteps:
    def __init__(self, automation: FlipkartAutomation):
        self.automation = automation
        self.page = automation.page
        self.llm = automation.llm
        self.logger = automation.logger
        self.config = automation.config
        
        # User session data
        self.current_product = None
        self.shipping_info = None
        self.user_session_file = "user_session.json"
        self.user_data = self._load_user_session()
        self.search_url = None
        # Enhanced selector fallbacks
        self.enhanced_selectors = {
            "size_options": [
                "button:has-text('10')",
                "text='10'",
                "._3V2wfe._1fGeJ5._2UyeeK",
                "button._3V2wfe",
                ".size-buttons button",
                "[data-qa*='size']",
                "button:has-text('UK 10')",
                "button:has-text('US 10')"
            ],
            "color_options": [
                "button:has-text('Black')",
                "text='Black'",
                "._3V2wfe._1fGeJ5",
                "[data-qa*='color']",
                ".color-swatch",
                "button[title*='Black']",
                "button[aria-label*='Black']"
            ],
            "add_to_cart": [
                "button:has-text('Add to Cart')",
                "button:has-text('ADD TO CART')",
                "#container > div > div._39kFie.N3De93.JxFEK3._48O0EI > div.DOjaWF.YJG4Cf > div.DOjaWF.gdgoEp.col-5-12.MfqIAz > div:nth-child(2) > div > ul > li:nth-child(1) > button",
                "button._2KpZ6l._2U9uOA._3v1-ww",
                "button._2KpZ6l._2U9uOA.ihZ75k._3AWRsL",
                ".add-to-cart-button",
                "[data-qa='add-to-cart']"
            ],
            "buy_now": [
                "button:has-text('Buy Now')",
                "button:has-text('BUY NOW')",
                "#container > div > div._39kFie.N3De93.JxFEK3._48O0EI > div.DOjaWF.YJG4Cf > div.DOjaWF.gdgoEp.col-5-12.MfqIAz > div:nth-child(2) > div > ul > li.col.col-6-12.flex > form > button",
                "button._2KpZ6l._2U9uOA._3v1-ww"
            ],
            "cart_icon": [
                "._3SkBxJ",
                "[href*='viewcart']",
                "a[href*='cart']",
                "text=Cart",
                ".cart-icon"
            ],
            "place_order": [
                "text=Place Order",
                "button:has-text('Place Order')",
                "._2KpZ6l._2U9uOA._3v1-ww"
            ],
            "login_button": [
                "button:has-text('Login')",
                "text=Login",
                "._1_3w1N",
                "._2KpZ6l._1_HQL_V"
            ]
        }

    def _load_user_session(self) -> Dict[str, Any]:
        """Load user session data from file"""
        try:
            if os.path.exists(self.user_session_file):
                with open(self.user_session_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_user_session(self):
        """Save user session data to file"""
        try:
            with open(self.user_session_file, 'w') as f:
                json.dump(self.user_data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Could not save session: {str(e)}")

    async def _login_with_phone(self):
        """Login using phone number and OTP (Flipkart-style new HTML version)."""
        import os, json, time, asyncio

        shipping_session_file = "user_shipping_session.json"
        phone = None

        # Load saved phone number
        if os.path.exists(shipping_session_file):
            try:
                with open(shipping_session_file, "r") as f:
                    saved_shipping = json.load(f)
                    phone = saved_shipping.get("mobile", "").strip()
            except Exception as e:
                self.logger.warning(f"Could not read {shipping_session_file}: {str(e)}")
                phone = None

        # Ask user for phone number
        if phone:
            print(f"📱 Found phone number in session: {phone}")
            use_existing = input("Use this phone number? [Y/n]: ").strip().lower()
            if use_existing not in ("y", "yes", ""):
                phone = input("Enter your phone number: ").strip()
        else:
            phone = input("Enter your phone number: ").strip()

        self.logger.info("🔐 Starting Flipkart phone login...")

        # --- Step 1: Fill Phone Number ---
        phone_input_selectors = [
                "input[autocomplete='off']",              # fallback for general text field
                "input.r4vIwl.Jr-g+f",                   # new Flipkart-style field
                "input._2IX_2-",                         # older Flipkart selector
                "input[type='tel']",
                "input[placeholder*='Phone']",
                "input[placeholder*='Mobile']",
                "input[label*='Email/Mobile']"         # fallback for label-based hint
            ]

        for selector in phone_input_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    await asyncio.sleep(0.5)
                    await self.page.fill(selector, phone)
                    self.logger.info(f"✅ Entered phone number using: {selector}")
                    break
            except Exception as e:
                self.logger.debug(f"Skipping {selector}: {e}")
                continue
        else:
            self.logger.error("❌ Could not find phone number input field.")
            return

        # --- Step 2: Click Continue / Request OTP ---
        continue_selectors = [
            "button._2KpZ6l._2HKlqd",
            "button[type='submit']",
            "button:has-text('Request OTP')",
            "button:has-text('Continue')",
            "button:has-text('Next')"
        ]
        for selector in continue_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    self.logger.info(f"✅ Clicked Continue button: {selector}")
                    break
            except Exception as e:
                self.logger.debug(f"Skipping continue selector {selector}: {str(e)}")
                continue

        # Wait for OTP field to appear
        await asyncio.sleep(3)

        # --- Step 3: Fill OTP ---
        otp_input_selectors = [
            "input.r4vIwl.zgwPDa.Jr-g+f",           # new OTP field
            "input[type='text'][maxlength='6']",
            "input[placeholder*='OTP']",
            "input[name*='otp']"
        ]

        otp_entered = False
        for selector in otp_input_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    await asyncio.sleep(0.5)
                    otp = input("Enter OTP received on your phone: ").strip()
                    await self.page.fill(selector, otp)
                    self.logger.info(f"✅ OTP entered using: {selector}")
                    otp_entered = True
                    break
            except Exception as e:
                self.logger.debug(f"Skipping OTP selector {selector}: {str(e)}")
                continue

        if not otp_entered:
            self.logger.error("❌ Could not find OTP input field.")
            return

        # --- Step 4: Handle Resend OTP (optional) ---
        resend_selector_js = (
            "#container > div > div.lloqNF > div > div.zuxjMQ > div:nth-child(1) > "
            "div > div > div > div > div.col.col-5-12 > div > form > div:nth-child(2) > a"
        )

        resend_option = input("Need to resend OTP? [y/N]: ").strip().lower()
        if resend_option in ("y", "yes"):
            try:
                if await self.page.is_visible(resend_selector_js, timeout=5000):
                    await self.page.click(resend_selector_js)
                    self.logger.info("🔄 OTP resend clicked.")
                    await asyncio.sleep(2)
            except Exception as e:
                self.logger.warning(f"⚠️ Could not click Resend OTP: {e}")

        # --- Step 5: Click Signup/Login Button ---
        signup_button_selector = (
            "#container > div > div.lloqNF > div > div.zuxjMQ > div:nth-child(1) > "
            "div > div > div > div > div.col.col-5-12 > div > form > div.aPGMpN > button"
        )

        try:
            if await self.page.is_visible(signup_button_selector, timeout=5000):
                await self.page.click(signup_button_selector)
                self.logger.info("✅ Clicked Signup/Login button")
            else:
                self.logger.warning("⚠️ Signup/Login button not visible.")
        except Exception as e:
            self.logger.warning(f"⚠️ Could not click Signup/Login button: {e}")

        # --- Step 6: Wait for login to finish and save session ---
        await self.page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)

        self.user_data['logged_in'] = True
        self.user_data['login_method'] = 'phone'
        self.user_data['login_timestamp'] = time.time()
        self._save_user_session()

        self.logger.info("✅ Login successful, session saved.")

    async def _login_with_email(self):
        """Login using email"""
        email = input("Enter your email: ").strip()
        
        # Click login button
        login_selectors = [
            "text=Login",
            "button:has-text('Login')",
            "a[href*='login']"
        ]
        
        for selector in login_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    break
            except:
                continue
        
        # Wait for login modal
        await asyncio.sleep(2)
        
        # Switch to email login if needed
        email_switch_selectors = [
            "text=Use Email ID",
            "text=Email",
            "button:has-text('Email')"
        ]
        
        for selector in email_switch_selectors:
            try:
                if await self.page.is_visible(selector, timeout=3000):
                    await self.page.click(selector)
                    await asyncio.sleep(1)
                    break
            except:
                continue
        
        # Enter email
        email_selectors = [
            "input[type='email']",
            "input[name*='email']",
            "input[placeholder*='Email']"
        ]
        
        for selector in email_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.fill(selector, email)
                    self.logger.info("✅ Email entered")
                    break
            except:
                continue
        
        # Click continue
        continue_selectors = [
            "button:has-text('Continue')",
            "text=CONTINUE"
        ]
        
        for selector in continue_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    break
            except:
                continue
        
        # Wait for password input
        await asyncio.sleep(3)
        
        # Ask user for password
        password = input("Enter your password: ").strip()
        
        # Enter password
        password_selectors = [
            "input[type='password']",
            "input[name*='password']",
            "input[placeholder*='Password']"
        ]
        
        for selector in password_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.fill(selector, password)
                    self.logger.info("✅ Password entered")
                    break
            except:
                continue
        
        # Click login
        login_selectors = [
            "button:has-text('Login')",
            "text=LOGIN"
        ]
        
        for selector in login_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    break
            except:
                continue
        
        # Wait for login to complete
        await self.page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)
        
        # Save login session
        self.user_data['logged_in'] = True
        self.user_data['login_method'] = 'email'
        self.user_data['login_timestamp'] = time.time()  # Add timestamp
        self._save_user_session()
        
        self.logger.info("✅ Login successful - session saved")

    async def step_0_generate_search_url(self):
        """Step 0: Use LLM to generate precise search URL"""
        if not self.current_product:
            raise Exception("No product information available")
            
        self.logger.info("🔍 Generating precise search URL...")
        
        product_info = self.current_product
        search_query = product_info.get('name', '')
        
        self.logger.info(f"🎯 Generated search query: {search_query}")
        
        # URL encode the search query
        encoded_query = urllib.parse.quote_plus(search_query)
        self.search_url = f"https://www.flipkart.com/search?q={encoded_query}"
        
        self.logger.info(f"🌐 Search URL: {self.search_url}")
        return self.search_url

    async def step_1_launch_search_url(self):
        """Step 1: Launch the generated search URL and let user select a product"""
        self.logger.info("🚀 Launching search URL...")
        
        # Extract product information
        # extracter = FlipkartExtractor()
        # product_list = extracter.extract_from_tavily(self.search_url)
        
        # if not isinstance(product_list, list):
        #     self.logger.warning(f"Product info extraction failed or unexpected format: {product_list}")
        #     product_list = []
        # else:
        #     self.logger.info("Product info extracted successfully")
        
        await self.page.goto(self.search_url, wait_until="networkidle")
        
        # Handle initial login modal if present
        # login_close_selectors = [
        #     "button._2KpZ6l._2doB4z",
        #     "[data-testid='close-modal']",
        #     "button:has-text('Close')",
        #     "button:has-text('✕')"
        # ]
        
        # for selector in login_close_selectors:
        #     try:
        #         if await self.page.is_visible(selector, timeout=5000):
        #             await self.page.click(selector)
        #             self.logger.info(f"✅ Initial modal closed: {selector}")
        #             await asyncio.sleep(1)
        #             break
        #     except:
        #         continue
        
        # Display product information to user and get selection
        # selected_product_url = await self.display_products_and_get_selection(product_list)
        
        # if selected_product_url:
        #     # Update search URL to the selected product URL
        #     self.search_url = selected_product_url
        #     self.logger.info(f"🔄 Updated search URL to selected product: {self.search_url}")
            
        #     # Navigate to the selected product page
        #     await self.page.goto(self.search_url, wait_until="networkidle")
        #     self.logger.info("✅ Selected product page loaded successfully")
        # else:
        #     self.logger.info("ℹ️  No product selected, continuing with search results page")

    async def display_products_and_get_selection(self, product_list):
        """Display products to user and return selected product URL"""
        
        if not product_list:
            print("❌ No product information available. Please select manually from the search results.")
            return None
        
        print("\n" + "="*80)
        print("🛍️  AVAILABLE PRODUCTS")
        print("="*80)
        
        # Display numbered product list
        for idx, product in enumerate(product_list, 1):
            print(f"\n#{idx}")
            print(f"📦 Name: {product.get('name', 'N/A')}")
            print(f"🏷️  Brand: {product.get('brand', 'N/A')}")
            print(f"💰 Price: ₹{product.get('current_price', 'N/A')}")
            
            if product.get('original_price') and product.get('original_price') != product.get('current_price'):
                print(f"💸 Original: ₹{product.get('original_price')} (Save {product.get('discount_percentage', 0)}%)")
            
            print(f"⭐ Rating: {product.get('rating', 'N/A')} ({product.get('ratings_count', 0)} ratings)")
            print(f"📊 Reviews: {product.get('reviews_count', 0)}")
            print(f"📦 Availability: {product.get('availability', 'N/A')}")
            
            # Display special tags if any
            special_tags = product.get('special_tags', [])
            if special_tags:
                print(f"🏆 Tags: {', '.join(special_tags)}")
            
            print(f"🔗 URL: {product.get('product_url', 'N/A')}")
            print("-" * 60)
        
        # Get user selection
        while True:
            try:
                selection = input(f"\n🎯 Select a product (1-{len(product_list)}) or press Enter to skip: ").strip()
                
                if selection == "":
                    print("⏩ Skipping product selection...")
                    return None
                
                selection_num = int(selection)
                if 1 <= selection_num <= len(product_list):
                    selected_product = product_list[selection_num - 1]
                    product_url = selected_product.get('product_url')
                    
                    if product_url:
                        print(f"✅ Selected: {selected_product.get('name')}")
                        return product_url
                    else:
                        print("❌ Selected product doesn't have a valid URL. Please choose another.")
                else:
                    print(f"❌ Please enter a number between 1 and {len(product_list)}")
                    
            except ValueError:
                print("❌ Please enter a valid number")
            except KeyboardInterrupt:
                print("\n⏹️  Selection cancelled by user")
                return None

    async def step_2_select_exact_product(self):
        """Step 2: Select the exact matching product from search results"""
        self.logger.info("🎯 Selecting exact product match...")
        
        product_name = self.current_product.get('name', '').lower()
        product_specs = self.current_product.get('specifications', {})
        
        # Wait for search results
        await self._wait_for_search_results()
        
        # Get all product elements
        product_selectors = [
            "[data-tkid]",
            "._1fQZEK", 
            "a[href*='/p/']",
            ".s1Q9rs"  # Product title
        ]
        
        exact_matches = []
        partial_matches = []
        
        for selector in product_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    try:
                        # Get product text for matching
                        element_text = await element.text_content()
                        if not element_text:
                            continue
                            
                        element_text_lower = element_text.lower()
                        
                        # Check for exact name match
                        name_match_score = self._calculate_name_match(product_name, element_text_lower)
                        
                        # Check specification matches
                        spec_match_score = self._calculate_spec_match(product_specs, element_text_lower)
                        
                        total_score = name_match_score + spec_match_score
                        
                        if total_score >= 8:  # High confidence match
                            exact_matches.append((element, total_score, element_text))
                        elif total_score >= 5:  # Partial match
                            partial_matches.append((element, total_score, element_text))
                            
                    except Exception as e:
                        continue
                        
            except Exception as e:
                continue
        
        # Sort by match score
        exact_matches.sort(key=lambda x: x[1], reverse=True)
        partial_matches.sort(key=lambda x: x[1], reverse=True)
        
        # Try exact matches first
        target_element = None
        if exact_matches:
            target_element = exact_matches[0][0]
            self.logger.info(f"✅ Found exact match: {exact_matches[0][2]}")
        elif partial_matches:
            target_element = partial_matches[0][0]
            self.logger.info(f"🔄 Using partial match: {partial_matches[0][2]}")
        else:
            # Fallback to first available product
            self.logger.warning("⚠️ No good matches found, using first available product")
            for selector in product_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements:
                        target_element = elements[0]
                        break
                except:
                    continue
        
        if not target_element:
            raise Exception("No products found in search results")
        
        # Get current page context for new tab handling
        current_page = self.page
        context = self.automation.context
        
        # Set up listener for new pages
        new_page_promise = asyncio.create_task(self._wait_for_new_page(context))
        
        # Click the selected product
        await target_element.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await target_element.click()
        self.logger.info("✅ Product clicked, waiting for new tab...")
        
        # Handle new tab
        try:
            new_page = await asyncio.wait_for(new_page_promise, timeout=10000)
            self.logger.info("🔄 New tab detected, switching to it...")
            
            await current_page.close()
            self.page = new_page
            self.automation.page = new_page
            
            await new_page.wait_for_load_state('networkidle')
            self.logger.info("✅ Successfully switched to product page")
            
        except asyncio.TimeoutError:
            self.logger.info("ℹ️ No new tab opened, continuing in current page")
            await self.page.wait_for_load_state('networkidle')
        
        # Wait for product page to load completely
        await self._wait_for_product_page_ready()
        await self._scroll_page_for_elements()
        
        self.logger.info(f"📍 Current URL: {self.page.url}")

    def _calculate_name_match(self, target_name: str, element_text: str) -> int:
        """Calculate how well the element text matches the target product name"""
        score = 0
        
        # Split into words for matching
        target_words = set(target_name.lower().split())
        element_words = set(element_text.lower().split())
        
        # Exact match bonus
        if target_name in element_text:
            score += 5
        
        # Word overlap
        common_words = target_words.intersection(element_words)
        if common_words:
            score += len(common_words) * 2
        
        # Brand/model specific matching
        if any(word in element_text for word in ['samsung', 'galaxy', 'iphone', 'oneplus', 'xiaomi', 'realme']):
            score += 1
            
        return min(score, 5)  # Cap at 5

    def _calculate_spec_match(self, specs: Dict, element_text: str) -> int:
        """Calculate how well specifications match"""
        score = 0
        element_text_lower = element_text.lower()
        
        for key, value in specs.items():
            spec_str = f"{value}".lower()
            if spec_str in element_text_lower:
                score += 2
            elif any(word in element_text_lower for word in spec_str.split()):
                score += 1
                
        return min(score, 5)  # Cap at 5

    async def step_3_handle_product_options(self):
        """Step 3: Automatically select product options and check delivery"""
        self.logger.info("⚙️ Handling product options automatically...")

        # First, check delivery availability
        available = await self._check_delivery_availability()
        if not available:
            self.logger.error("❌ Product not available for delivery in this pincode")
            raise Exception("Product not available for selected pincode")
        
        # Handle product options if present
        if self.current_product and self.current_product.get('options'):
            await self._select_product_options(self.current_product['options'])
        
        self.logger.info("✅ Product options selected successfully")

    async def _select_product_options(self, options: dict):
        """Select product options like color, size, storage using LLM-guided choice"""
        self.logger.info(f"🎨 Selecting product options: {options}")

        # Main container for options on Flipkart product page
        container_selector = "#container > div > div._39kFie.N3De93.JxFEK3._48O0EI > div.DOjaWF.YJG4Cf > div.DOjaWF.gdgoEp.col-8-12"
        try:
            container = await self.page.query_selector(container_selector)
            if not container:
                self.logger.warning("⚠️ Options container not found, skipping option selection")
                return

            # Flipkart often has option grids as multiple divs inside container
            option_sections = await container.query_selector_all("div")
            
            for key, desired_value in options.items():
                # Use llm_selection to choose the best option in available section
                selected = False
                for idx, section in enumerate(option_sections[2:7]):  # usually 3rd-7th sections
                    option_buttons = await section.query_selector_all("button, li, div")
                    for btn in option_buttons:
                        btn_text = await btn.text_content() or ""
                        btn_text = btn_text.strip().lower()
                        if self.llm_selection(key, desired_value, btn_text):
                            await btn.click()
                            await asyncio.sleep(1)  # wait for selection to register
                            self.logger.info(f"✅ Selected {key}: {btn_text}")
                            selected = True
                            break
                    if selected:
                        break

                if not selected:
                    self.logger.warning(f"⚠️ Could not select {key}='{desired_value}', defaulting to first available option")
                    # fallback: click first available option
                    for section in option_sections[2:7]:
                        first_option = await section.query_selector("button, li, div")
                        if first_option:
                            await first_option.click()
                            await asyncio.sleep(1)
                            self.logger.info(f"⚡ Defaulted {key} to first available option")
                            break

        except Exception as e:
            self.logger.warning(f"⚠️ Option selection failed: {str(e)}")

    def llm_selection(self, key: str, desired_value: str, available_value: str) -> bool:
        """
        Simple LLM-like logic to match product options intelligently.
        Returns True if available_value matches desired_value.
        """
        key = key.lower()
        desired_value = desired_value.lower()
        available_value = available_value.lower()

        # Exact match
        if desired_value in available_value:
            return True

        # Partial match logic
        if key in ['color', 'shade', 'variant']:
            return desired_value.split()[0] in available_value
        if key in ['size', 'storage', 'ram']:
            return ''.join(filter(str.isalnum, desired_value)) in ''.join(filter(str.isalnum, available_value))
        
        # fallback: simple substring match
        return desired_value in available_value

    async def _check_delivery_availability(self) -> bool:
        """Check if product is available for delivery using pincode from session.json"""
        import os, json, asyncio

        self.logger.info("📦 Checking delivery availability...")

        # Load pincode from session.json
        pincode = None
        try:
            if os.path.exists("user_shipping_session.json"):
                with open("user_shipping_session.json", "r") as f:
                    session_data = json.load(f)
                    pincode = session_data.get("pincode") or session_data.get("shipping_info", {}).get("pincode")
        except Exception as e:
            self.logger.warning(f"⚠️ Could not read pincode from session.json: {str(e)}")

        if not pincode:
            pincode = input("Enter your delivery pincode: ").strip()
            if not pincode:
                self.logger.error("❌ No pincode entered.")
                return False
            # Save pincode to session
            try:
                session_data = {}
                if os.path.exists("user_shipping_session.json"):
                    with open("user_shipping_session.json", "r") as f:
                        session_data = json.load(f)
                session_data["pincode"] = pincode
                with open("user_shipping_session.json", "w") as f:
                    json.dump(session_data, f, indent=2)
            except Exception as e:
                self.logger.warning(f"⚠️ Could not update pincode in session.json: {str(e)}")

        self.logger.info(f"📍 Using pincode: {pincode}")

        try:
            # --- Enter Pincode ---
            delivery_input_selectors = [
                "#pincodeInputId",
                "input[placeholder*='Pincode']",
                "input[id='pincodeInputId']",
                "._2JC05C",
                "._1MR4o5",
                ".delivery-info input"
            ]

            input_filled = False
            for selector in delivery_input_selectors:
                try:
                    if await self.page.is_visible(selector, timeout=3000):
                        await self.page.click(selector)
                        await self.page.fill(selector, pincode)
                        input_filled = True
                        self.logger.info(f"✅ Entered pincode in: {selector}")
                        break
                except:
                    continue

            if not input_filled:
                self.logger.warning("⚠️ Pincode input not found, skipping delivery check")
                return True  # Assume available

            # --- Click Check Delivery Button ---
            # Use robust locator: button or span inside button
            check_button_selectors = [
                "button:has-text('Check')",
                "button:has-text('Check Delivery')",
                "span:has-text('Check')",
                "#container > div > div._39kFie.N3De93.JxFEK3._48O0EI > div.DOjaWF.YJG4Cf > div.DOjaWF.gdgoEp.col-8-12 > div:nth-child(7) > div > div > div._98QWWQ > div.BvstzA > div > div.guihks.undefined > div.Ir\\+XS5._5Owjac.H1broz > span"
            ]

            button_clicked = False
            for selector in check_button_selectors:
                try:
                    if await self.page.is_visible(selector, timeout=5000):
                        await self.page.click(selector)
                        button_clicked = True
                        self.logger.info(f"✅ Clicked Check Delivery button: {selector}")
                        await asyncio.sleep(3)  # wait for page to update after click
                        break
                except:
                    continue

            if not button_clicked:
                self.logger.warning("⚠️ Check Delivery button not found, skipping check")
                return True

            # --- Check for delivery availability ---
            # Retry a couple of times with small delays
            available_selectors = [
                "text=Delivery available",
                "text=Delivery in",
                "text=Free Delivery",
                "text=Ships to your location"
            ]
            unavailable_selectors = [
                "text=Currently Unavailable",
                "text=Out of Stock",
                "text=Not deliverable",
                ".out-of-stock",
                ".unavailable"
            ]

            for attempt in range(3):  # retry 3 times
                for sel in available_selectors:
                    try:
                        if await self.page.is_visible(sel, timeout=2000):
                            self.logger.info("✅ Delivery available for this pincode")
                            return True
                    except:
                        continue
                for sel in unavailable_selectors:
                    try:
                        if await self.page.is_visible(sel, timeout=2000):
                            self.logger.error("❌ Product not available for delivery")
                            return False
                    except:
                        continue
                await asyncio.sleep(2)  # wait a bit and retry

            self.logger.info("ℹ️ Delivery status unclear after retries, assuming available")
            return True

        except Exception as e:
            self.logger.warning(f"⚠️ Delivery check failed: {str(e)}")
            return True  # Assume available on error

    async def step_4_add_to_cart_without_login(self):
        """Step 4: Add to cart without triggering login"""
        self.logger.info("🛒 Adding product to cart (no login yet)...")

        if not await self._is_product_page():
            raise Exception("Not on product page")

        await asyncio.sleep(2)
        await self.page.wait_for_load_state('networkidle')
        await self._scroll_page_for_elements()

        # Try Add to Cart
        cart_selectors = self.enhanced_selectors["add_to_cart"]

        for selector in cart_selectors:
            try:
                if not await self.page.is_visible(selector, timeout=3000):
                    await self._scroll_to_element(selector)

                if await self.page.is_visible(selector, timeout=5000):
                    is_disabled = await self.page.get_attribute(selector, "disabled")
                    if is_disabled:
                        continue

                    await self.page.click(selector)
                    self.logger.info(f"✅ Clicked Add to Cart: {selector}")

                    # Wait for cart confirmation (ignore login redirects)
                    result = await self._wait_for_cart_or_login_redirect()
                    if result in ["cart", "cart_confirmed", "unknown"]:
                        self.logger.info("✅ Added to cart successfully (no login yet)")
                        return
            except Exception:
                continue

        # If Add to Cart fails, try Buy Now (optional)
        if await self._try_buy_now():
            return

        raise Exception("Could not add to cart")

    async def _wait_for_cart_or_login_redirect(self, timeout: int = 10000):
        """Wait for either cart confirmation or login redirect"""
        self.logger.info("⏳ Waiting for cart or login redirect...")
        
        try:
            # Wait for any page change
            await self.page.wait_for_event('load', timeout=timeout)
            
            current_url = self.page.url.lower()
            
            # Check if we're on login page
            if 'login' in current_url or 'signin' in current_url:
                self.logger.info("🔐 Redirected to login page")
                return "login"
            
            # Check if we're on cart page
            if 'cart' in current_url or 'viewcart' in current_url:
                self.logger.info("✅ Navigated to cart page")
                return "cart"
            
            # Check if we're on checkout
            if 'checkout' in current_url:
                self.logger.info("✅ Navigated to checkout")
                return "checkout"
            
            # Check for cart confirmation on same page
            confirmation_selectors = [
                "text=Added to Cart",
                "text=Added to Bag",
                "text=Go to Cart"
            ]
            
            for selector in confirmation_selectors:
                try:
                    if await self.page.is_visible(selector, timeout=3000):
                        self.logger.info(f"✅ Cart confirmed: {selector}")
                        return "cart_confirmed"
                except:
                    continue
            
            self.logger.info("ℹ️ No clear redirect detected")
            return "unknown"
            
        except Exception as e:
            self.logger.warning(f"⚠️ Redirect detection failed: {str(e)}")
            return "unknown"

    async def step_6_proceed_to_shipping(self):
        """Step 6: Click Place Order, then login if required"""
        self.logger.info("🏠 Clicking Place Order...")

        # Ensure we're on cart/checkout page
        current_url = self.page.url.lower()
        if 'cart' not in current_url and 'checkout' not in current_url:
            await self._go_to_cart()

        # Click Place Order button
        place_order_selectors = self.enhanced_selectors["place_order"]
        clicked = False
        for selector in place_order_selectors:
            try:
                if await self.page.is_visible(selector, timeout=10000):
                    await self.page.click(selector)
                    self.logger.info(f"✅ Clicked Place Order: {selector}")
                    await self.page.wait_for_load_state('networkidle')
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            raise Exception("❌ Could not click Place Order")

        # Wait a short moment for redirect
        await asyncio.sleep(2)

        # Check if login page appeared
        current_url = self.page.url.lower()
        if 'login' in current_url or 'signin' in current_url or await self._check_login_required():
            self.logger.info("🔐 Login required after Place Order, proceeding with phone login")
            await self._login_with_phone()
        else:
            self.logger.info("✅ Already logged in or no login required")

    async def step_7_fill_shipping_info(self):
        """Step 7: Fill shipping information, choose from saved addresses or enter new"""
        import asyncio

        self.logger.info("🏠 Filling shipping information...")

        # --- Step 1: Detect saved addresses ---
        saved_address_selectors = [
            "div._1ruvv2",  # Flipkart saved address card
            "div._3Nyybr",  # alternative saved address card
        ]

        saved_addresses = []
        for sel in saved_address_selectors:
            try:
                if await self.page.is_visible(sel, timeout=3000):
                    elements = await self.page.query_selector_all(sel)
                    for el in elements:
                        text = (await el.inner_text()).strip()
                        if text:
                            saved_addresses.append(text)
            except:
                continue

        # --- Step 2: Let user choose saved address or new ---
        chosen_address = None
        if saved_addresses:
            self.logger.info("📋 Found saved addresses:")
            for idx, addr in enumerate(saved_addresses, 1):
                print(f"{idx}. {addr}")

            choice = input(f"Select address [1-{len(saved_addresses)}] or enter N for new: ").strip()
            if choice.lower() == 'n':
                chosen_address = self.shipping_info  # enter new
            elif choice.isdigit() and 1 <= int(choice) <= len(saved_addresses):
                chosen_address = saved_addresses[int(choice) - 1]
            else:
                print("❌ Invalid choice, entering new address.")
                chosen_address = self.shipping_info
        else:
            self.logger.info("ℹ️ No saved addresses found. Entering new address.")
            chosen_address = self.shipping_info

        # --- Step 3: If user chose new address, fill form ---
        if isinstance(chosen_address, dict):
            # Field mapping
            field_mappings = {
                "name": ["name", "fullname", "customerName"],
                "mobile": ["mobile", "phone", "contact"],
                "pincode": ["pincode", "zipcode", "zip"],
                "address": ["address", "street", "line1"],
                "locality": ["locality", "area", "sublocality"],
                "city": ["city", "town"],
                "state": ["state", "region"],
                "landmark": ["landmark", "near"]
            }

            for field_name, field_value in chosen_address.items():
                if not field_value:
                    continue

                field_patterns = field_mappings.get(field_name.lower(), [field_name])

                for pattern in field_patterns:
                    try:
                        selector = f"input[name*='{pattern}'], textarea[name*='{pattern}'], input[placeholder*='{pattern}']"
                        if await self.page.is_visible(selector, timeout=3000):
                            await self.page.fill(selector, str(field_value))
                            self.logger.info(f"✅ Filled {field_name}")
                            break
                    except:
                        continue

        elif isinstance(chosen_address, str):
            # If user selected an existing address card, click it
            for sel in saved_address_selectors:
                try:
                    elements = await self.page.query_selector_all(sel)
                    for el in elements:
                        text = (await el.inner_text()).strip()
                        if text == chosen_address:
                            await el.click()
                            self.logger.info("✅ Selected existing saved address")
                            break
                except:
                    continue

        # --- Step 4: Click continue/save ---
        await asyncio.sleep(2)
        continue_selectors = [
            "button:has-text('Continue')",
            "button:has-text('Save')",
            "button:has-text('Next')",
            "._2KpZ6l._1seccl._3AWRsL"
        ]

        for selector in continue_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    self.logger.info("✅ Shipping information submitted")
                    break
            except:
                continue

        await self.page.wait_for_load_state('networkidle')

    async def step_8_proceed_to_payment(self):
        """Step 8: Proceed to payment and stop for manual completion"""
        self.logger.info("💰 Proceeding to payment...")
        
        payment_selectors = [
            "button:has-text('Proceed to Pay')",
            "button:has-text('Proceed to Payment')",
            "button:has-text('Continue to Payment')",
            "._2KpZ6l._2U9uOA._3v1-ww"
        ]
        
        for selector in payment_selectors:
            try:
                if await self.page.is_visible(selector, timeout=10000):
                    await self.page.click(selector)
                    self.logger.info(f"✅ Clicked payment button: {selector}")
                    break
            except:
                continue
        
        self.logger.info("🎯 Automation completed! Ready for manual payment...")
        self.logger.info("💳 Please complete the payment manually in the browser")
        self.logger.info("⏳ Browser will remain open for manual completion...")
        
        # Keep browser open
        await asyncio.sleep(600)

    async def _go_to_cart(self):
        """Navigate to cart"""
        cart_selectors = self.enhanced_selectors["cart_icon"]
        
        for selector in cart_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    self.logger.info(f"✅ Navigated to cart using: {selector}")
                    await self.page.wait_for_load_state('networkidle')
                    return
            except:
                continue
        
        # Fallback: navigate directly to cart URL
        await self.page.goto("https://www.flipkart.com/viewcart", wait_until="networkidle")
        self.logger.info("✅ Navigated to cart via URL")

    async def _wait_for_search_results(self):
        """Wait for search results to load"""
        self.logger.info("⏳ Waiting for search results...")
        
        result_indicators = [
            "[data-tkid]",
            "._1fQZEK",
            ".s1Q9rs"
        ]
        
        for _ in range(3):
            for indicator in result_indicators:
                try:
                    if await self.page.is_visible(indicator, timeout=5000):
                        self.logger.info("✅ Search results loaded")
                        return
                except:
                    pass
            
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
        
        self.logger.warning("⚠️ Search results loading slowly")

    async def _wait_for_product_page_ready(self):
        """Wait for product page to be ready"""
        self.logger.info("⏳ Waiting for product page to be ready...")
        
        product_indicators = [
            "[data-id]",
            ".product-image",
            "._1AtVbE",
            ".aMaAEs"
        ]
        
        for indicator in product_indicators:
            try:
                await self.page.wait_for_selector(indicator, timeout=10000)
                self.logger.info(f"✅ Product page element found: {indicator}")
                break
            except:
                continue
        
        await asyncio.sleep(2)

    async def _scroll_page_for_elements(self):
        """Scroll page to load all elements"""
        self.logger.info("🔄 Scrolling page...")
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

    async def _scroll_to_element(self, selector: str):
        """Scroll to element"""
        try:
            await self.page.evaluate(f"document.querySelector('{selector}')?.scrollIntoView({{behavior: 'smooth', block: 'center'}})")
            await asyncio.sleep(1)
        except:
            pass

    async def _wait_for_new_page(self, context):
        """Wait for new page"""
        self.logger.info("⏳ Waiting for new page...")
        new_page = await context.wait_for_event('page')
        await new_page.wait_for_load_state('domcontentloaded')
        return new_page

    async def _is_product_page(self):
        """Check if on product page"""
        try:
            current_url = self.page.url
            return any(indicator in current_url for indicator in ['/p/', '/product/', 'pid='])
        except:
            return False

    async def _try_buy_now(self):
        """Try Buy Now button"""
        buy_now_selectors = self.enhanced_selectors["buy_now"]
        for selector in buy_now_selectors:
            try:
                if await self.page.is_visible(selector, timeout=5000):
                    await self.page.click(selector)
                    self.logger.info(f"✅ Clicked Buy Now: {selector}")
                    await self.page.wait_for_load_state('networkidle')
                    return True
            except:
                continue
        return False

    async def _check_login_required(self):
        """Check if login required"""
        login_indicators = [
            "text=Login to continue",
            "text=Please login",
            "text=Sign in to continue"
        ]
        for indicator in login_indicators:
            try:
                if await self.page.is_visible(indicator, timeout=3000):
                    return True
            except:
                continue
        return False

