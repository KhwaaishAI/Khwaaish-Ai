import asyncio
import os
import json
import re
from playwright.async_api import async_playwright, TimeoutError
from urllib.parse import quote_plus

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

        # Enter mobile number
        print(f"📱 Filling mobile number: {mobile_number}...")
        # Updated selector based on user provided HTML: input.form-control.mobileNumberInput
        mobile_input = page.locator('input.form-control.mobileNumberInput')
        await mobile_input.wait_for(state="visible", timeout=10000)
        await mobile_input.fill(mobile_number)

        # Click Continue
        print("👆 Clicking 'Continue'...")
        continue_btn = page.locator('div.submitBottomOption, button:has-text("CONTINUE")')
        await continue_btn.click()
        
        print("✅ Mobile number submitted. Waiting for OTP screen...")
        # Wait for OTP input to confirm we are on the next screen
        await page.wait_for_selector('input[type="text"], input[type="number"]', timeout=10000)
        
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

        # Wait for automatic verification or click verify if exists
        # Myntra often auto-verifies. We'll wait a bit.
        await asyncio.sleep(2)
        
        # Check if we are logged in. Look for profile icon or check URL.
        # If there's a login button still, try clicking it.
        login_btn = page.locator('button:has-text("LOGIN"), div.submitBottomOption')
        if await login_btn.is_visible():
            print("👆 Clicking 'LOGIN' button...")
            await login_btn.click()
        
        await page.wait_for_load_state('networkidle', timeout=15000)
        
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

    try:
        await page.goto(f"https://www.myntra.com/{quote_plus(query)}", wait_until="domcontentloaded", timeout=60000)
        print("✅ Search results page loaded.")
        
        # Scrape results
        products = []
        product_cards = await page.locator('li.product-base').all()
        print(f"ℹ️ Found {len(product_cards)} products.")
        
        for i, card in enumerate(product_cards[:10]):
            try:
                brand = await card.locator('h3.product-brand').text_content()
                name = await card.locator('h4.product-product').text_content()
                price_element = card.locator('span.product-discountedPrice')
                if not await price_element.count():
                    price_element = card.locator('div.product-price span').first
                
                price = await price_element.text_content()
                link = await card.locator('a').get_attribute('href')
                
                products.append({
                    "brand": brand,
                    "name": name,
                    "price": price,
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
        print("👆 Clicking 'Add to Bag'...")
        add_btn = page.locator('div.pdp-add-to-bag, button:has-text("ADD TO BAG")')
        await add_btn.click()
        
        # Wait for confirmation (Go to Bag button usually appears)
        await page.wait_for_selector('a.pdp-goToCart, span:has-text("GO TO BAG")', timeout=10000)
        print("✅ Added to bag successfully.")
        
        await browser.close()
        return "Successfully added to bag"
    except Exception as e:
        print(f"❌ Error adding to cart: {e}")
        await browser.close()
        raise

async def book_order(playwright_instance: async_playwright):
    """Proceeds to checkout."""
    print("🛍️ Proceeding to checkout...")
    browser = await playwright_instance.chromium.launch(
        headless=HEADLESS,
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    state_path = MYNTRA_AUTH_FILE_PATH if os.path.exists(MYNTRA_AUTH_FILE_PATH) else None
    if not state_path:
        raise Exception("Not logged in. Cannot checkout.")
        
    context = await browser.new_context(
        storage_state=state_path,
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = await context.new_page()

    try:
        await page.goto("https://www.myntra.com/checkout/cart", wait_until="domcontentloaded", timeout=60000)
        print("✅ Cart page loaded.")
        
        # Click Place Order
        print("👆 Clicking 'Place Order'...")
        place_order_btn = page.locator('button:has-text("PLACE ORDER")')
        await place_order_btn.click()
        
        # Wait for address page
        await page.wait_for_load_state('networkidle')
        print("✅ Navigated to address/checkout page.")
        
        # We stop here for safety as actual booking involves payment
        print("⚠️ Stopping at address selection for safety.")
        
        await browser.close()
        return "Proceeded to checkout page"
    except Exception as e:
        print(f"❌ Error during checkout: {e}")
        await browser.close()
        raise
