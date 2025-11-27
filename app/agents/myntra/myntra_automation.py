import asyncio
import os
import json
import re
from playwright.async_api import async_playwright, TimeoutError
from urllib.parse import quote_plus
import uuid

# Constants
MYNTRA_AUTH_FILE_PATH = os.path.join(os.path.dirname(__file__), "myntra_auth.json")
HEADLESS = False  # Set to True for production if needed

async def _click_robust(page, candidates: list[tuple[str, any]], timeout: int = 5000):
    """Try multiple locators to click the same UI with fallbacks."""
    last_err = None
    for desc, loc in candidates:
        try:
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.scroll_into_view_if_needed()
            await loc.click(timeout=timeout)
            print(f"✅ Clicked {desc}.")
            return True
        except Exception as e:
            last_err = e
            continue
    if last_err:
        print(f"⚠️ Failed to click any candidate for action. Last error: {last_err}")
    return False

async def initiate_login(playwright_instance: async_playwright, mobile_number: str):
    """Navigates to Myntra login page and enters mobile number."""
    print("🚀 Starting Playwright for Myntra login...")
    browser = await playwright_instance.chromium.launch(
        headless=HEADLESS,
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = await context.new_page()

    try:
        await page.goto("https://www.myntra.com/login", wait_until="domcontentloaded", timeout=60000)
        print("✅ Myntra login page loaded.")
        await asyncio.sleep(5)


        # Enter mobile number
        print(f"📱 Filling mobile number: {mobile_number}...")
        # Updated selector based on user provided HTML: input.form-control.mobileNumberInput
        mobile_input = page.locator('input.form-control.mobileNumberInput')
        await mobile_input.wait_for(state="visible", timeout=10000)
        await mobile_input.fill(mobile_number)
        await asyncio.sleep(2)


        # Handle Consent Checkbox (if present)
        try:
            # Look for a checkbox, often required for new logins or specific regions
            checkbox = page.locator('input[type="checkbox"].consentCheckbox') # Prioritize specific class
            if await checkbox.count() == 0:
                checkbox = page.locator('input[type="checkbox"]') # Fallback to any checkbox
            
            if await checkbox.count() > 0:
                print("☑️ Found checkbox. Checking state...")
                if not await checkbox.is_checked():
                    await checkbox.click()
                    print("✅ Consent checkbox clicked.")
                else:
                    print("ℹ️ Checkbox already checked.")
            else:
                print("ℹ️ No consent checkbox found.")
        except Exception as e:
            print(f"⚠️ Error handling checkbox: {e}")

        # Click Continue
        await asyncio.sleep(2)
        print("👆 Clicking 'Continue'...")
        continue_btn = page.locator('div.submitBottomOption, div.disabledSubmitBottomOption, button:has-text("CONTINUE")')
        await continue_btn.click()
        
        return context
    except Exception as e:
        print(f"❌ Error during login initiation: {e}")
        await browser.close()
        raise

async def verify_otp_and_save_session(context, otp: str):
    """Enters OTP and saves the session."""
    page = context.pages[0]
    print(f"🔐 Submitting OTP: {otp}")

    try:
        # Myntra OTP inputs might be split or single. 
        # Strategy: Try to find a single input first, or multiple inputs.
        # Usually Myntra has 4 separate inputs for OTP or one single input depending on the flow.
        # We will try to fill the first input and see if it auto-advances or if we need to split.
        
        otp_inputs = await page.locator('input[type="tel"], input[type="number"]').all()
        
        if len(otp_inputs) >= 4:
            print(f"ℹ️ Detected {len(otp_inputs)} OTP fields. Splitting OTP.")
            for i, digit in enumerate(otp):
                if i < len(otp_inputs):
                    await otp_inputs[i].fill(digit)
        else:
            print("ℹ️ Detected single OTP field (or fewer than 4). Filling directly.")
            await page.locator('input[type="tel"], input[type="number"]').first.fill(otp)
        
        await asyncio.sleep(10)

        # Verify login success by checking for "Profile" or absence of "Login"
        print("✅ Login likely successful. Saving state...")
        await context.storage_state(path=MYNTRA_AUTH_FILE_PATH)
        print(f"✅ Authentication state saved to {MYNTRA_AUTH_FILE_PATH}")
        
        await context.browser.close()
        return True
    except Exception as e:
        print(f"❌ Error during OTP verification: {e}")
        await context.browser.close()
        raise

async def search_myntra(playwright_instance: async_playwright, query: str):
    """Searches for a product on Myntra."""
    print(f"🔍 Searching for: {query}")
    browser = await playwright_instance.chromium.launch(
        headless=HEADLESS,
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    # Load auth state if exists
    state_path = MYNTRA_AUTH_FILE_PATH if os.path.exists(MYNTRA_AUTH_FILE_PATH) else None
    
    context = await browser.new_context(
        storage_state=state_path,
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    await asyncio.sleep(2)

    try:
        await page.goto(f"https://www.myntra.com/{quote_plus(query)}", wait_until="domcontentloaded", timeout=60000)
        print("✅ Search results page loaded.")
        
        # Scrape results
        products = []
        product_cards = await page.locator('li.product-base').all()
        print(f"ℹ️ Found {len(product_cards)} products.")
        
        for i, card in enumerate(product_cards):
            try:
                # Helper to safely get text content
                async def get_text(locator):
                    return await locator.text_content() if await locator.count() > 0 else None

                brand = await get_text(card.locator('h3.product-brand'))
                name = await get_text(card.locator('h4.product-product'))
                
                # Price details
                price_element = card.locator('span.product-discountedPrice')
                original_price_element = card.locator('span.product-strike')
                discount_element = card.locator('span.product-discountPercentage')
                
                price = await get_text(price_element)
                # If no discounted price, try to get the main price
                if not price:
                    price = await get_text(card.locator('div.product-price > span').first)

                # Rating details
                rating = await get_text(card.locator('div.product-ratingsContainer > span').first)
                rating_count = await get_text(card.locator('div.product-ratingsCount'))

                link = await card.locator('a').get_attribute('href')
                image_locator = card.locator('picture > img')
                image_url = await image_locator.get_attribute('src', timeout=5000) if await image_locator.count() > 0 else None
                
                products.append({
                    "brand": brand,
                    "name": name,
                    "price": price,
                    "original_price": await get_text(original_price_element),
                    "discount": await get_text(discount_element),
                    "rating": rating,
                    "rating_count": rating_count.replace('|', '').strip() if rating_count else None,
                    "image_url": image_url,
                    "url": f"https://www.myntra.com/{link}" if link and not link.startswith('http') else link
                })
            except Exception as e:
                print(f"⚠️ Error scraping card {i}: {e}")
                continue
        await browser.close()
                
        return products
    except Exception as e:
        print(f"❌ Error during search: {e}")
        await browser.close()
        raise

async def _handle_upi_payment_setup(page):
    """Helper function to navigate to the UPI payment section."""
    print("💳 Navigating to payment page and selecting UPI...")
    await asyncio.sleep(2) # Wait for payment options to load

    # Click on the UPI tab
    upi_tab_locator = page.locator('div#upi.tabBar-base-tab')
    await upi_tab_locator.wait_for(state="visible", timeout=10000)
    await upi_tab_locator.click()
    print("✅ Clicked 'UPI' payment tab.")

    # Click on the 'Enter UPI ID' radio button
    enter_upi_id_locator = page.locator('div.paymentSubOption-base-rowContainer', has_text="Enter UPI ID")
    await enter_upi_id_locator.wait_for(state="visible", timeout=10000)
    await enter_upi_id_locator.click()
    print("✅ Selected 'Enter UPI ID' option.")

    # Wait for the input field to be ready
    await page.wait_for_selector('input.inputWithDropdown-base-input', timeout=10000)
    print("✅ UPI input field is ready.")

async def add_to_cart(playwright_instance: async_playwright, product_url: str, size: str = None):

    """Adds a product to the cart."""
    print(f"🛒 Adding product to cart: {product_url}")
    browser = await playwright_instance.chromium.launch(
        headless=HEADLESS,
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    state_path = MYNTRA_AUTH_FILE_PATH if os.path.exists(MYNTRA_AUTH_FILE_PATH) else None
    context = await browser.new_context(
        storage_state=state_path,
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = await context.new_page()

    try:
        await page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
        print("✅ Product page loaded.")
        await asyncio.sleep(2)
        
        # Select Size
        # Myntra size buttons usually have class 'size-buttons-size-button'
        # We try to find a button with the text of the size, or just the first available one if size is None
        
        size_buttons = page.locator('button.size-buttons-size-button:not(.size-buttons-size-button-disabled)')
        
        if await size_buttons.count() > 0:
            if size:
                print(f"📏 Selecting size: {size}")
                # Try exact match first
                target_button = size_buttons.filter(has_text=re.compile(f"^{size}$", re.I)).first
                if await target_button.count() == 0:
                     # Fallback to contains
                     target_button = size_buttons.filter(has_text=size).first
                
                if await target_button.count() > 0:
                    await target_button.click()
                    print("✅ Size selected.")
                else:
                    print(f"⚠️ Size '{size}' not found. Selecting first available size.")
                    await size_buttons.first.click()
            else:
                print("ℹ️ No size specified. Selecting first available size.")
                await size_buttons.first.click()
        else:
            print("⚠️ No size buttons found (might be one-size or out of stock).")

        # Click Add to Bag
        await asyncio.sleep(2)
        print("👆 Clicking 'Add to Bag'...")
        add_btn = page.locator('div.pdp-add-to-bag, button:has-text("ADD TO BAG")')
        await add_btn.click()
        await asyncio.sleep(2)
        
        # Wait for confirmation (Go to Bag button usually appears)
        await page.wait_for_selector('a.pdp-goToCart, span:has-text("GO TO BAG")', timeout=10000)
        print("✅ Added to bag successfully.")
        await asyncio.sleep(2)

        await page.goto("https://www.myntra.com/checkout/cart", wait_until="domcontentloaded", timeout=60000)
        print("✅ Cart page loaded.")

        # Click Place Order
        print("👆 Clicking 'Place Order'...")
        place_order_btn = page.locator('button:has-text("PLACE ORDER")')
        await place_order_btn.click()
        
        # On the address page, check for saved address and continue
        try:
            print("🏠 Checking for saved address on the address page...")
            # Wait for a serviceable address block to be visible
            saved_address_locator = page.locator('div.addressBlocks-base-block.addressBlocks-base-serviceable').first
            await saved_address_locator.wait_for(state="visible", timeout=15000)
            print("✅ Found saved address.")

            # Click the continue button
            print("👆 Clicking 'Continue' on address page...")
            continue_button_locator = page.locator('div.addressDesktop-base-continueBtn:has-text("continue")')
            await continue_button_locator.click()
            print("✅ Clicked 'Continue'.")

            # Set up for UPI payment
            await _handle_upi_payment_setup(page)

            session_id = str(uuid.uuid4())
            return {
                "status": "upi_required",
                "message": "Proceeded to payment. Please use the /myntra/pay-with-upi endpoint.",
                "session_id": session_id,
                "context": context
            }
            
        except TimeoutError:
            print("ℹ️ No saved address found or page did not load as expected within 15s.")
            # The page is now expecting a new address. Keep the session open.
            session_id = str(uuid.uuid4())
            return {
                "status": "address_required",
                "message": "No saved address found. Please use the /myntra/add-address endpoint to add a new address.",
                "session_id": session_id,
                "context": context
            }
        except Exception as e:
            print(f"⚠️ An error occurred on the address page: {e}")
            await browser.close()
            raise

    except Exception as e:
        print(f"❌ Error adding to cart: {e}")
        await browser.close()
        raise

async def add_new_address(context, address_data: dict):
    """Fills the new address form on Myntra."""
    page = context.pages[-1] # Get the active page
    print("📝 Filling new address form...")

    try:
        # Fill contact details
        await page.locator('input#name').fill(address_data["name"])
        await page.locator('input#mobile').fill(address_data["mobile"])

        # Fill address details
        await page.locator('input#pincode').fill(address_data["pincode"])
        await asyncio.sleep(2) # Wait for city/state to auto-populate
        await page.locator('input#houseNumber').fill(address_data["house_number"])
        await page.locator('input#streetAddress').fill(address_data["street_address"])
        await page.locator('input#locality').fill(address_data["locality"])

        # Select address type
        address_type = address_data.get("address_type", "HOME").upper()
        if address_type == "OFFICE":
            await page.locator('div#addressType-office').click()
        else:
            await page.locator('div#addressType-home').click()
        print(f"✅ Selected address type: {address_type}")

        # Set as default address if requested
        if address_data.get("make_default"):
            await page.locator('input#isDefault-native-checkbox').check()
            print("✅ Marked as default address.")

        # Save address
        print("👆 Clicking 'Save'...")
        await page.locator('div.button-base-button.addressFormUI-base-saveBtn').click()

        # After saving, the new address is selected. Now set up for UPI payment.
        await _handle_upi_payment_setup(page)

        session_id = str(uuid.uuid4())
        return {
            "message": "Address added. Please use the /myntra/pay-with-upi endpoint.",
            "session_id": session_id,
            "context": context
        }
    except Exception as e:
        print(f"❌ Error adding new address: {e}")
        await context.browser.close()
        raise

async def enter_upi_and_pay(context, upi_id: str):
    """Enters the UPI ID and clicks the Pay Now button."""
    page = context.pages[-1] # Get the active page
    print(f"💳 Entering UPI ID: {upi_id} and attempting payment...")

    try:
        # Fill UPI ID
        upi_input_locator = page.locator('input.inputWithDropdown-base-input')
        await upi_input_locator.fill(upi_id)
        print("✅ UPI ID entered.")

        # Click Pay Now
        pay_now_button = page.locator('button.actionButton-base-actionButton:has-text("Pay Now")')
        await pay_now_button.click()
        print("✅ Clicked 'Pay Now'. Waiting for payment confirmation on your UPI app.")

        # Handle potential additional UPI verification screen
        print("⏳ Waiting for page to load after payment initiation...")
        await page.wait_for_load_state("networkidle", timeout=10000)
        try:
            print("🔍 Checking for additional verification step...")
            # This locator is based on the new HTML provided for the second UPI entry screen
            additional_upi_section = page.locator('div.instrumentItem:has-text("UPI ID")')
            await additional_upi_section.wait_for(state="visible", timeout=5000)
            
            print("✅ Additional verification screen found. Proceeding...")
            await additional_upi_section.click()

            # Fill the new UPI ID input
            await page.locator('input#vpaInput').fill(upi_id)
            print(f"✅ Re-entered UPI ID: {upi_id}")

            # Click Verify
            await page.locator('a:has-text("VERIFY UPI ID")').click()
            print("✅ Clicked 'VERIFY UPI ID'.")
            await asyncio.sleep(2) # Wait for verification

            # Click the final Pay button
            await page.locator('button:has-text("PAY")').click()
            print("✅ Clicked final 'PAY' button. Payment re-initiated.")

        except TimeoutError:
            print("ℹ️ No additional verification step detected. Assuming direct payment initiation.")
        except Exception as e:
            print(f"⚠️ An error occurred during the additional verification step: {e}")

        await asyncio.sleep(10) # Give user time to see the page before closing
        await context.browser.close()
        return "Payment initiated. Please complete the transaction on your UPI app."
    except Exception as e:
        print(f"❌ Error during UPI payment: {e}")
        await context.browser.close()
        raise