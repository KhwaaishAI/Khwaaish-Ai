import asyncio
import os
from dotenv import load_dotenv
import json
from playwright.async_api import async_playwright

load_dotenv(dotenv_path='api/api_keys/.env')

INSTAMART_AUTH_FILE_PATH = os.path.join(os.path.dirname(__file__), "instamart_auth.json")
    
async def initiate_signup(p: async_playwright, mobile_number: str, name: str, gmail: str, location: str):
    """Navigates to Swiggy (for Instamart), enters details, and stops at the OTP screen."""
    print("🚀 Starting Playwright for Instamart signup...")
    browser = await p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        geolocation={"longitude": 77.5946, "latitude": 12.9716},
        permissions=["geolocation"],
    )
    page = await context.new_page()

    await page.goto("https://www.swiggy.com", wait_until="networkidle", timeout=60000)
    print("✅ Swiggy page loaded.")

    # Click the location selector at the top
    print("👆 Clicking the main location selector...")
    # The div with class _22e_H contains the location info
    await page.locator('div._22e_H').click()

    # Fill in the new location
    print(f"📍 Typing new location: {location}")
    location_input_selector = 'input#location'
    await page.locator(location_input_selector).fill(location)
    await asyncio.sleep(2)  # Wait for suggestions to appear

    # Wait for suggestions and click the first one
    print("🖱️ Clicking the first location suggestion...")
    first_suggestion_selector = 'div._2BgUI'
    await page.locator(first_suggestion_selector).first.wait_for(state='visible', timeout=10000)
    await page.locator(first_suggestion_selector).first.click()
    await asyncio.sleep(5)  # Wait for the page to update
    print("🖱️ Clicked the first location suggestion...")

    # Wait for the page to update with the new location
    await page.wait_for_load_state('networkidle', timeout=20000)
    print("✅ Location updated successfully.")

    print("👆 Clicking 'Sign in' button...")
    signin_button = page.locator('div._3chg9 > a._5-C04:has-text("Sign in")')
    await signin_button.wait_for(state='visible')
    await signin_button.click()

    print(f"📱 Filling mobile number: {mobile_number}...")
    await page.locator('input#mobile').fill(mobile_number)
    await page.locator("a:has-text('Login')").click()

    # Wait for either OTP field or Name field to appear
    await page.wait_for_selector("input#otp, input#name", timeout=10000)

    # If 'name' input is visible, it's a new user signup flow
    if await page.locator('input#name').is_visible():
        print("📝 New user detected. Filling name and email...")
        await page.locator('input#name').fill(name)
        await page.locator('input#email').fill(gmail)
        await page.locator("a:has-text('CONTINUE')").click()
        print("✅ Name and email submitted. Waiting for OTP screen.")

    # Check for OTP field and confirm it's visible
    await page.locator('input#otp').wait_for(state='visible', timeout=10000)
    print("⚠️ OTP screen detected. Pausing for user to submit OTP via API.")
    
    return context

async def enter_otp_and_save_session(context, otp: str):
    """Enters the OTP, verifies, and saves the authentication state."""
    page = context.pages[0]
    print(f"Submitting OTP: {otp}")
    
    await page.locator('input#otp').fill(otp)
    print("✅ OTP entered.")

    # Click the "VERIFY OTP" button
    await page.locator('a.lyOGZ:has-text("VERIFY OTP")').click()
    print("✅ Clicked 'VERIFY OTP'. Waiting for login to complete...")
    await asyncio.sleep(5)



    print("✅ Login successful. Saving Instamart authentication state...")

    await context.storage_state(path=INSTAMART_AUTH_FILE_PATH)
    print(f"✅ Authentication state saved to {INSTAMART_AUTH_FILE_PATH}")

async def search_instamart(playwright_instance: async_playwright, query: str):
    """Launches Instamart with a logged-in session and searches for an item."""
    print("🚀 Starting Playwright for Instamart search...")
    browser = await playwright_instance.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        storage_state=INSTAMART_AUTH_FILE_PATH,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
    )
    page = await context.new_page()

    try:
        await page.goto("https://www.swiggy.com/instamart")
        await asyncio.sleep(10)
        print("✅ Logged-in Instamart page loaded.")

        # 1. Click the main search bar container
        print("🔍 Clicking the search container...")
        search_container_button = page.locator('button[data-testid="search-container"]')
        await search_container_button.wait_for(state='visible', timeout=10000)
        await search_container_button.click()

        # 2. Wait for the search input field to appear and type the query
        # The input field appears after the container is clicked.
        search_input_locator = page.locator('input[data-testid="search-page-header-search-bar-input"]')
        await search_input_locator.wait_for(state='visible', timeout=10000)
        print(f"📝 Typing search query: '{query}'")
        await search_input_locator.type(query, delay=120) # Typing with a delay to simulate human behavior

        # 3. Press Enter to initiate the search
        await search_input_locator.press('Enter')
        print("✅ Search submitted. Waiting for results to load...")
        await asyncio.sleep(5)

        # 8. Scrape the product data
        print("🔍 Scraping product data...")
        await page.wait_for_selector('div[data-testid="item-collection-card-full"]', timeout=20000)
        product_cards = await page.locator('div[data-testid="item-collection-card-full"]').all()
        print(f"Found {len(product_cards)} product cards.")

        product_data = []
        for card in product_cards:
            try:
                async def get_text(locator):
                    return await locator.text_content() if await locator.count() > 0 else "N/A"

                name = await get_text(card.locator('div._1lbNR'))
                description = await get_text(card.locator('div._3bM-V'))
                delivery_time = await get_text(card.locator('div._1y_Uf'))
                quantity = await get_text(card.locator('xpath=./following-sibling::div').locator('div._3wq_F'))

                # Select the price that is NOT the original price (i.e., not struck-through)
                price = await get_text(card.locator('xpath=./following-sibling::div').locator('div._2jn41:not(._3eAjW)'))
                # Select the original price, which has the strikethrough class
                original_price = await get_text(card.locator('xpath=./following-sibling::div').locator('div._3eAjW'))

                image_element = card.locator('img._16I1D')
                image_url = await image_element.get_attribute('src') if await image_element.count() > 0 else "N/A"

                product_details = {
                    "name": name.strip(),
                    "description": description.strip(),
                    "delivery_time": delivery_time.strip(),
                    "quantity": quantity.strip(),
                    "price": price.strip(),
                    "original_price": original_price.strip() if original_price else "N/A",
                    "image_url": image_url
                }
                product_data.append(product_details)

            except Exception as e:
                print(f"Error extracting data for a card: {e}")
                continue

        # 9. Save data to a file
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(project_root, 'data', 'instamart')
        os.makedirs(data_dir, exist_ok=True)

        sanitized_query = "".join(c for c in query if c.isalnum() or c in (' ', '_')).rstrip()
        filename = f"{sanitized_query.replace(' ', '_')}.json"
        filepath = os.path.join(data_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(product_data, f, ensure_ascii=False, indent=4)
        print(f"✅ Scraped data saved to {filepath}")

        return browser, context, product_data

    except Exception as e:
        if browser: await browser.close()
        raise e

async def add_to_cart(context, product_name: str, quantity: int):
    """Finds a product by name, selects the desired quantity, and adds it to the cart."""
    page = context.pages[-1]  # Get the last active page
    print(f"🛒 Attempting to add '{product_name}' with quantity '{quantity}' to cart...")

    product_cards = await page.locator('div[data-testid="item-collection-card-full"]').all()
    if not product_cards:
        raise Exception("No product cards found on the page.")

    product_found = False
    for card in product_cards:
        name_locator = card.locator('div._1lbNR')
        current_product_name = await name_locator.text_content()

        if current_product_name and product_name.lower() in current_product_name.lower():
            product_found = True
            print(f"✅ Found product: {current_product_name}")

            # Click the main 'ADD' button on the product card
            add_button = card.locator('div[data-testid="buttonpair-add"]')
            await add_button.click(force=True)
            print(f"✅ Clicked 'ADD' on product card for '{product_name}'.")

            # Wait briefly to see if a customization pop-up appears
            try:
                popup_selector = 'div[data-testid="InstamartItemCustomizationWidget"]'
                await page.wait_for_selector(popup_selector, timeout=3000)
                print("ℹ️ Customization pop-up detected.")

                # Target the last variant in the pop-up, which is typically the single-item option.
                last_variant_container = page.locator('div[data-testid="variants-container"]').last
                if await last_variant_container.count() > 0:
                    print(f"✅ Found single-item variant in pop-up.")
                    # Click the 'ADD' button within the last variant's container
                    variant_add_button = last_variant_container.locator('button[data-testid="add_buttons_center"]')
                    await variant_add_button.click()
                    print(f"✅ Clicked 'ADD' for single item inside pop-up.")

                    # Click the '+' button for the remaining quantity
                    plus_button = last_variant_container.locator('button[data-testid="add_buttons_plus"]')
                    if quantity > 1:
                        print(f"➕ Increasing quantity to {quantity}...")
                        for _ in range(quantity - 1):
                            await plus_button.click()
                            await asyncio.sleep(0.2) # Small delay between clicks
                    
                    # Click the confirm button to close the pop-up and add to cart
                    await asyncio.sleep(1)
                    confirm_button_selector = 'button[data-testid="InstamartItemCustomizationWidget-cta"]'
                    await page.locator(confirm_button_selector).click()
                    print("✅ Clicked 'Confirm' in pop-up.")
                else:
                    raise Exception("Could not find variant container in the customization pop-up.")

            except Exception as e:
                if "timeout" in str(e).lower():
                    print("✅ No customization pop-up appeared. Item likely added directly.")
                    # If no popup, the 'add_button' now acts as a '+' button.
                    # We already clicked it once, so we click 'quantity - 1' more times.
                    if quantity > 1:
                        print(f"➕ Increasing quantity to {quantity}...")
                        for _ in range(quantity - 1):
                            await add_button.click()
                            await asyncio.sleep(0.2) # Small delay between clicks
                else:
                    raise e # Re-raise other exceptions
            
            # After adding the item, click the 'Go to Cart' button
            await asyncio.sleep(1)
            print("🛒 Navigating to cart page...")
            cart_button_selector = 'button[data-testid="bottom-cart-hud"]'
            cart_button = page.locator(cart_button_selector)
            await cart_button.wait_for(state='visible', timeout=10000)
            await cart_button.click()
            print("✅ Clicked 'Go to Cart'. Waiting for cart page to load...")
            await asyncio.sleep(4)
            print("✅ Cart page loaded. Scraping bill details...")

            # Scrape the bill details from the cart page
            bill_details = await scrape_bill_details(page)
            return bill_details

    if not product_found:
        raise Exception(f"Product '{product_name}' not found in search results.")

async def scrape_bill_details(page):
    """Scrapes the bill details from the cart page."""
    bill_container = page.locator('div#bill_details')
    await bill_container.wait_for(state='visible', timeout=10000)

    line_items = await bill_container.locator('div._1hlnr').all()
    bill_data = {}

    for item in line_items:
        label_element = item.locator('div._2w8Td')
        value_element = item.locator('div._2B_Hy')

        if await label_element.count() > 0 and await value_element.count() > 0:
            label = (await label_element.text_content() or "").strip()
            
            # Get all child divs within the value container
            value_divs = await value_element.locator('div').all()
            
            if len(value_divs) > 1:
                # If there are multiple values (e.g., original and discounted)
                bill_data[label] = {
                    "original": (await value_divs[0].text_content() or "").strip(),
                    "final": (await value_divs[1].text_content() or "").strip()
                }
            else:
                # If there is only a single value
                value = (await value_element.text_content() or "").strip()
                bill_data[label] = value

    print(f"✅ Scraped bill details: {bill_data}")
    return bill_data
