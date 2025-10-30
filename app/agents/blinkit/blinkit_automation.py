import re
import asyncio
from playwright.async_api import TimeoutError
from urllib.parse import quote_plus
import sys
import os

# Add the root directory to the Python path to enable imports from other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.prompts.blinkit_prompts.blinkit_prompts import find_best_match

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
        add_button = selected_card.get_by_role("button", name="ADD")
        await add_button.click(timeout=5000)
        print("- Clicked 'ADD' once.")
        await page.wait_for_timeout(500)
        
        if quantity > 1:
            for i in range(quantity - 1):
                plus_button = selected_card.locator('button:has(span.icon-plus)').first
                await plus_button.click(timeout=5000)
                print(f"- Clicked '+' ({i+2}/{quantity})")
                await page.wait_for_timeout(300)
        print(f"✅ Successfully added {quantity} of '{item_name}' to cart.")

    except Exception as e:
        print(f"❌ An unexpected error occurred while adding to cart: {e}")

async def automate_blinkit(shopping_list: dict, location: str, mobile_number: str, p):
    """Launches Playwright to set location and process the shopping list."""
    print("\nStep 2: Starting browser automation with Playwright...")
    browser = await p.chromium.launch(headless=False, slow_mo=50)
    context = await browser.new_context()
    page = await context.new_page()

    print("Navigating to Blinkit...")
    await page.goto("https://www.blinkit.com/")
    
    location_input = page.get_by_placeholder("search delivery location")
    await location_input.fill(location)
    await page.locator(".LocationSearchList__LocationListContainer-sc-93rfr7-0").first.click()
    
    print("Location set. Waiting for 4 seconds before searching for items...")
    await page.wait_for_timeout(4000)
    print("Main page loaded.")

    print("\nStep 3: Preparing to add items to cart...")
    for item, quantity in shopping_list.items():
        await search_and_add_item(page, item, quantity)
    
    print("-----------------------------------------")
    
    print("\n✅ All items processed. Cart should be ready.")
    
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
    
    print("\nStep 8: Waiting for OTP entry (20 seconds)...")
    print("⏳ Please enter the OTP on the browser...")
    await asyncio.sleep(30)
    print("✅ OTP wait period completed.")
    
    print("\nStep 9: Waiting for page to load after OTP...")
    await page.wait_for_timeout(3000)
    try:
        proceed_button = page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Proceed")').first
        await proceed_button.click(timeout=5000)
        print("✅ Final Proceed button clicked successfully.")
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"❌ Error clicking final Proceed button: {e}")
        return

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
