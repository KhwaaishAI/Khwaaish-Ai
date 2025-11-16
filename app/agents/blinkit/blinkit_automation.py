import re
import asyncio
import json
from playwright.async_api import TimeoutError
from urllib.parse import quote_plus
import sys
import os
from datetime import datetime

# Add the root directory to the Python path to enable imports from other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.prompts.blinkit_prompts.blinkit_prompts import find_best_match

# Path to store authentication state
AUTH_FILE_PATH = os.path.join(os.path.dirname(__file__), "playwright_auth.json")
SEARCH_HISTORY_DIR = os.path.join(os.path.dirname(__file__), "search_history")

async def search_and_add_item(page, item_name: str, quantity: int):
    """Searches for an item, selects the best match, and adds it to the cart."""
    print(f"\nProcessing item: '{item_name}' (Quantity: {quantity})")
    
    search_url = f"https://www.blinkit.com/s/?q={quote_plus(item_name)}"
    print(f"- Navigating to search page: {search_url}")
    await page.goto(search_url)

    try:
        first_product_card_selector = 'div[id][data-pf="reset"]'
        await page.wait_for_selector(first_product_card_selector, timeout=15000)
        print("- Product results page loaded successfully.")
    except TimeoutError:
        print(f"⚠️ Could not find any products for '{item_name}' on the page. Skipping.")
        return

    product_locator = page.locator(first_product_card_selector)
    count = await product_locator.count()
    scraped_products = []
    print(f"- Found {count} products. Analyzing top 10.")

    for i in range(min(count, 10)):
        card = product_locator.nth(i)
        try:
            name_elem = card.locator('.tw-text-300.tw-font-semibold.tw-line-clamp-2').first
            price_elem = card.locator('.tw-text-200.tw-font-semibold').first
            
            if not await name_elem.is_visible(timeout=1000) or not await price_elem.is_visible(timeout=1000):
                continue
            
            name = (await name_elem.text_content(timeout=2000)).strip()
            price_text = await price_elem.text_content(timeout=2000)
            price = float(re.sub(r'[^\d.]', '', price_text))
            
            scraped_products.append({'name': name, 'price': price, 'card': card})
        except Exception:
            continue 

    if not scraped_products:
        print(f"⚠️ Could not scrape product details for '{item_name}'. Skipping.")
        return

    best_match_product = find_best_match(item_name, scraped_products)
    
    if not best_match_product:
        print("- No match found, falling back to the cheapest product.")
        scraped_products.sort(key=lambda p: p['price'])
        best_match_product = scraped_products[0] if scraped_products else None

    if not best_match_product:
        print(f"❌ Critical Error: Could not select any product for '{item_name}'. Skipping.")
        return

    selected_card = best_match_product['card']
    print(f"- Final selection: '{best_match_product['name']}' at ₹{best_match_product['price']}")
    
    try:
        add_button = selected_card.locator('div[role="button"]:has-text("ADD")')
        await add_button.click(timeout=5000)
        print("- Clicked 'ADD' once.")
        await page.wait_for_timeout(500)
        
        if quantity > 1:
            for i in range(quantity - 1):
                plus_button = selected_card.locator('button:has(span.icon-plus)')
                await plus_button.click(timeout=5000)
                print(f"- Clicked '+' to increase quantity to {i+2}")
                await page.wait_for_timeout(300)
        print(f"✅ Successfully added {quantity} of '{item_name}' to cart.")

    except Exception as e:
        print(f"❌ An unexpected error occurred while adding to cart: {e}")

async def automate_blinkit(shopping_list: dict, location: str, mobile_number: str, p):
    """Launches Playwright to set location and process the shopping list."""
    print("\nStep 2: Starting browser automation with Playwright...")
    
    context_options = {}
    if os.path.exists(AUTH_FILE_PATH):
        print("- Found existing authentication file. Loading session...")
        context_options['storage_state'] = AUTH_FILE_PATH

    browser = await p.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context(**context_options)
    page = await context.new_page()

    print("Navigating to Blinkit...")
    await page.goto("https://www.blinkit.com/")
    
    location_input = page.get_by_placeholder("search delivery location")
    await location_input.fill(location)
    try:
        await page.locator(".LocationSearchList__LocationListContainer-sc-93rfr7-0").first.click()
    except TimeoutError:
        # If the location is already set from the previous session, this might not be needed.
        # We can check if we are on the main page by looking for the search bar.
        try:
            await page.wait_for_selector("input[placeholder*='Search for']", timeout=5000)
            print("- Location seems to be already set from the session.")
        except TimeoutError:
            print("❌ Critical Error: Could not set location or verify main page.")
    
    print("Location set. Waiting for 4 seconds before searching for items...")
    await page.wait_for_timeout(4000)
    print("Main page loaded.")

    print("\nStep 3: Preparing to add items to cart...")
    for item, quantity in shopping_list.items():
        await search_and_add_item(page, item, quantity)
    
    print("-----------------------------------------")
    
    print("\n✅ All items processed. Cart should be ready.")
    
    # Check if we are already logged in by looking for a "Proceed" button instead of "Login to Proceed"
    is_logged_in = await page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Proceed")').is_visible()

    if not is_logged_in:
        print("\n- User not logged in. Starting login flow...")
        print("\nStep 4: Clicking on cart button...")
        try:
            cart_button = page.locator('div.CartButton__Button-sc-1fuy2nj-5').first
            await cart_button.click(timeout=5000)
            print("✅ Cart button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking cart button: {e}")
            return
        
        print("\nStep 5: Clicking on 'Login to Proceed' button...")
        try:
            login_button = page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Login to Proceed")').first
            await login_button.click(timeout=5000)
            print("✅ Login to Proceed clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Login to Proceed: {e}")
            return
        
        print("\nStep 6: Entering phone number...")
        try:
            phone_input = page.locator('input.login-phone__input[data-test-id="phone-no-text-box"]').first
            await phone_input.fill(mobile_number)
            print("✅ Phone number entered successfully.")
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"❌ Error entering phone number: {e}")
            return
        
        print("\nStep 7: Clicking 'Continue' button...")
        try:
            continue_button = page.locator('button.PhoneNumberLogin__LoginButton-sc-1j06udd-4:has-text("Continue")').first
            await continue_button.click(timeout=5000)
            print("✅ Continue button clicked successfully.")
        except Exception as e:
            print(f"❌ Error clicking Continue button: {e}")
            return
        
        print("\nStep 8: Waiting for OTP entry (30 seconds)...")
        print("⏳ Please enter the OTP on the browser...")
        await asyncio.sleep(30)
        print("✅ OTP wait period completed.")
        
        print("\nStep 9: Waiting for page to load after OTP...")
        await page.wait_for_timeout(3000)
        try:
            # After OTP, the button should now say "Proceed"
            proceed_button = page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Proceed")').first
            await proceed_button.click(timeout=5000)
            print("✅ Final Proceed button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking final Proceed button: {e}")
            return
    else:
        print("\n- User is already logged in. Proceeding with checkout...")
        await page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Proceed")').first.click(timeout=5000)
        print("✅ Clicked 'Proceed' button.")
        await page.wait_for_timeout(2000)

    print("\nStep 10: Selecting the first saved address...")
    try:
        first_address = page.locator('div.AddressList__AddressItemWrapper-sc-zt55li-1').first
        await first_address.click(timeout=5000)
        print("✅ First address selected.")
        print("Waiting for page to load...")
        await page.wait_for_timeout(4000)
    except Exception as e:
        print(f"❌ Error selecting address: {e}")
        return

    print("\nStep 11: Clicking 'Proceed To Pay'...")
    try:
        proceed_to_pay_button = page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Proceed To Pay")').first
        await proceed_to_pay_button.click(timeout=5000)
        print("✅ 'Proceed To Pay' button clicked successfully.")
    except Exception as e:
        print(f"❌ Error clicking 'Proceed To Pay' button: {e}")
        return
        
    print("\n✅ Automation script finished.")
    print("Browser will close in 10 seconds.")
    await asyncio.sleep(10)

async def login(p, mobile_number: str, location: str) -> tuple:
    """
    Launches Playwright, navigates to Blinkit, and proceeds until the OTP screen.
    Returns the browser context and page for the next step.
    """
    print("\nStarting browser automation for Blinkit login...")
    browser = await p.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context()
    page = await context.new_page()
    try:
        print("Navigating to Blinkit...")
        # Use a more reliable wait strategy and a clean URL
        await page.goto("https://www.blinkit.com/", wait_until="domcontentloaded")
        # Check if the location input field is present on the landing page
        location_input_selector = 'div.display--table-cell.full-width > input[placeholder="search delivery location"]'
        location_input = page.locator(location_input_selector)
        await location_input.click()
        await location_input.fill(location)
        await page.wait_for_timeout(1000)
        await page.locator(".LocationSearchList__LocationListContainer-sc-93rfr7-0").first.click()
        print(f"✅ Location set to '{location}'.")
        # After setting location, the page reloads. We must wait for the login button to appear again.
        print("- Waiting for page to reload after setting location...")
        await page.locator("div.bFHCDW:has-text('Login')").first.wait_for(timeout=15000)


        print("Clicking on the main login button...")
        # Target the most specific element containing the text "Login"
        login_button = page.locator("div.bFHCDW:has-text('Login')").first
        await login_button.click(timeout=5000)
        print("✅ Login button clicked.")

        print("Entering phone number...")
        phone_input = page.locator('input.login-phone__input[data-test-id="phone-no-text-box"]').first
        # Wait for the phone input to be visible after clicking login
        await phone_input.wait_for(timeout=10000)
        await phone_input.fill(mobile_number)
        print(f"✅ Phone number '{mobile_number}' entered successfully.")

        continue_button = page.locator('button.PhoneNumberLogin__LoginButton-sc-1j06udd-4:has-text("Continue")').first
        await continue_button.click(timeout=5000)
        print("✅ Clicked 'Continue' button.")

        print("\n✅ OTP screen reached. Ready for OTP submission.")
        return context, page

    except Exception as e:
        # If something goes wrong, close the browser to prevent orphaned processes
        if 'context' in locals() and context:
            await context.browser.close()
        print(f"❌ An error occurred during login automation: {e}")
        raise

async def enter_otp_and_save_session(context, otp: str):
    """Enters the OTP, saves the session state, and closes the browser."""
    page = context.pages[0]
    print(f"\nSubmitting OTP: {otp}")
    otp_inputs = page.locator('input[data-test-id="otp-text-box"]')
    for i, digit in enumerate(otp):
        await otp_inputs.nth(i).fill(digit)
    
    print("✅ OTP entered. Waiting 10 seconds for session to be established...")
    await asyncio.sleep(10)
    
    await context.storage_state(path=AUTH_FILE_PATH)
    print(f"✅ Authentication state saved to {AUTH_FILE_PATH}")

async def add_product_to_cart(context, session_id: str, product_name: str, quantity: int):
    """Finds a specific product on the current page and adds it to the cart."""
    page = context.pages[0]
    print(f"\nAttempting to add '{product_name}' (Quantity: {quantity}) to cart.")

    # We will use the existing search_and_add_item function's logic here
    # In a real-world scenario, you might refactor this further
    # For now, we'll call the search and add logic directly.
    await search_and_add_item(page, product_name, quantity)

    # After adding, click the main cart button to proceed
    try:
        cart_button_selector = 'div.CartButton__Button-sc-1fuy2nj-5'
        cart_button = page.locator(cart_button_selector).first
        await cart_button.wait_for(state="visible", timeout=5000)
        
        # Check if cart is not empty before clicking
        cart_text = await cart_button.text_content()
        if "item" in cart_text or "items" in cart_text:
            await cart_button.click()
            print("✅ Clicked the main cart button to view cart summary.")

            # Click the "Proceed" button on the checkout strip
            proceed_selector = 'div[class*="CartAddressCheckout__Container"] div[tabindex="0"][class*="CheckoutStrip__AmountContainer"]'
            proceed_button = page.locator(proceed_selector).first
            await proceed_button.wait_for(state="visible", timeout=7000)
            await proceed_button.click()
            print("✅ Clicked 'Proceed' on the checkout strip.")
            await page.wait_for_timeout(2000) # Wait for address page to load

            saved_address_selector = 'div[class*="AddressList__AddressItemWrapper"]'
            
            # Check if a saved address exists
            try:
                await page.locator(saved_address_selector).first.wait_for(state="visible", timeout=7000)
                print("- Found a saved address. Selecting it.")
                await page.locator(saved_address_selector).first.click()
                print("✅ First saved address selected.")

                # Click the "Proceed To Pay" button
                proceed_to_pay_selector = 'div[class*="CheckoutStrip__AmountContainer"]:has-text("Proceed To Pay")'
                proceed_to_pay_button = page.locator(proceed_to_pay_selector).first
                await proceed_to_pay_button.wait_for(state="visible", timeout=5000)
                await proceed_to_pay_button.click()
                print("✅ Clicked 'Proceed To Pay'.")
                return {"status": "success", "message": "Selected existing address and proceeded to payment."}
            except TimeoutError:
                # If no saved address is found, inform the user to call the add_address endpoint
                print("- No saved address found.")
                return {"status": "address_needed", "session_id": session_id, "message": "No saved address found. Please provide a new address."}
        else:
            print("⚠️ Cart appears empty, not clicking the cart button.")
            return {"status": "error", "message": "Cart is empty."}
    except Exception as e:
        print(f"❌ An error occurred during the add-to-cart and proceed flow: {e}")
        raise

async def add_or_select_address(context, location: str, house_number: str, name: str):
    """
    This function is deprecated and will be replaced by proceed_to_address and add_address.
    """
    pass

async def add_address(context, session_id: str, location: str, house_number: str, name: str):
    """
    Adds a new address to the user's account.
    """
    page = context.pages[0]
    print("\n--- Adding New Address ---")
    try:
        # Click "Add a new address"
        add_address_selector = 'div[class*="CartAddress__AddAddressContainer"]:has(div[class*="CartAddress__PlusIcon"]):has-text("Add a new address")'
        add_address_button = page.locator(add_address_selector).first
        await add_address_button.wait_for(state="visible", timeout=5000)
        await add_address_button.click()
        print("✅ Clicked 'Add a new address'.")

        # Fill in the new address details
        address_input_selector = 'div.Select-input > input'
        await page.locator(address_input_selector).first.fill(location)
        print(f"- Filled address: '{location}'. Waiting for suggestions...")
        await page.wait_for_timeout(3000) # Wait for suggestions to load
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("Enter")
        print("✅ Selected the first address suggestion.")
        await page.wait_for_timeout(1000)

        # Fill in house number and name
        house_number_input = page.locator('div[class*="TextInput__StyledTextInput"] input#address')
        await house_number_input.click()
        await house_number_input.fill(house_number)
        print(f"- Filled house number: '{house_number}'.")
        name_input = page.locator('div[class*="TextInput__StyledTextInput"] input#name')
        await name_input.click()
        await name_input.fill(name)
        print(f"- Filled name: '{name}'.")

        # Click the "Save Address" button to confirm
        save_address_selector = 'div[class*="SaveAddressButton"]:has-text("Save Address")'
        save_address_button = page.locator(save_address_selector).first
        await save_address_button.wait_for(state="visible", timeout=5000)
        await save_address_button.click()
        print("✅ Clicked 'Save Address'.")
        return {"status": "success", "message": "Successfully added new address."}

    except Exception as address_error:
        print(f"❌ An error occurred while adding address: {address_error}")
        return {"status": "error", "message": str(address_error)}

async def search_multiple_products(p, queries: list[str]) -> tuple[any, any, dict]:
    """
    Launches a browser, logs in with saved state, and searches for multiple products.
    Returns the context, page, and scraped results to keep the session alive.
    """
    print("\nStarting browser automation for multi-product search...")
    if not os.path.exists(AUTH_FILE_PATH):
        print("❌ Authentication file not found. Please login first.")
        return {"error": "User not logged in. Please use the /login endpoint first."}

    browser = await p.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context(storage_state=AUTH_FILE_PATH)
    page = await context.new_page()

    print("Navigating to Blinkit home page to initialize session...")
    await page.goto("https://www.blinkit.com/", wait_until="domcontentloaded")
    print("- Allowing time for session to be recognized...")
    await page.wait_for_timeout(3000)

    # Although we search for multiple items, we will land on the page of the *last* item.
    # The user can then choose to add an item from that page.
    all_results = {}
    for query in queries:
        print(f"\n--- Searching for: '{query}' ---")
        products = await search_products(page, query)
        all_results[query] = products
    
    return context, page, all_results
async def search_products(page, query: str) -> list:
    """
    Searches for a single product query on an existing Playwright page.
    """
    try:
        search_url = f"https://www.blinkit.com/s/?q={quote_plus(query)}"
        print(f"- Navigating to search URL: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded")

        product_card_selector = 'div[id][data-pf="reset"]'
        await page.wait_for_selector(product_card_selector, timeout=15000)
        print("- Product results page loaded.")

        product_cards = await page.locator(product_card_selector).all()
        scraped_products = []
        print(f"- Found {len(product_cards)} products. Scraping details...")

        for card in product_cards:
            try:
                name = await card.locator('.tw-text-300.tw-font-semibold.tw-line-clamp-2').text_content(timeout=2000)
                price_text = await card.locator('.tw-text-200.tw-font-semibold').text_content(timeout=2000)
                price = float(re.sub(r'[^\d.]', '', price_text))
                scraped_products.append({'name': name.strip(), 'price': price})
            except Exception:
                continue

        # Save the results to a local JSON file
        try:
            os.makedirs(SEARCH_HISTORY_DIR, exist_ok=True)
            timestamp = datetime.utcnow()
            search_data = {
                "query": query,
                "timestamp": timestamp.isoformat() + "Z",
                "products": scraped_products
            }
            filename = f"search_{query.replace(' ', '_')}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(SEARCH_HISTORY_DIR, filename)
            with open(filepath, 'w') as f:
                json.dump(search_data, f, indent=4)
            print(f"✅ Search results for '{query}' saved to {filepath}")
        except Exception as e:
            print(f"⚠️ Could not save search history: {e}")

        return scraped_products
    except Exception as e:
        error_message = f"An error occurred while searching for '{query}': {e}"
        print(f"❌ {error_message}")
        return {"error": error_message}
