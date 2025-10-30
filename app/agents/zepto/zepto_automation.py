import re
import asyncio
from playwright.async_api import TimeoutError
from urllib.parse import quote_plus
import sys
import os

# Add the root directory to the Python path to enable imports from other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.prompts.zepto_prompts.zepto_prompts import find_best_match

async def search_and_add_item(page, item_name: str, quantity: int):
    """Searches for an item, selects the best match, and adds it to the cart."""
    print(f"\nProcessing item: '{item_name}' (Quantity: {quantity})")
    
    search_url = f"https://www.zeptonow.com/search?query={quote_plus(item_name)}"
    print(f"- Navigating to search page: {search_url}")
    await page.goto(search_url)

    try:
        product_card_selector = 'div.c5SZXs.ccdFPa'
        await page.wait_for_selector(product_card_selector, timeout=15000)
        print("- Product results page loaded successfully.")
    except TimeoutError:
        print(f"⚠️ Could not find any products for '{item_name}' on the page. Skipping.")
        return

    product_locator = page.locator(product_card_selector)
    count = await product_locator.count()
    scraped_products = []
    analyze_count = min(count, 10)
    print(f"- Found {count} products. Analyzing top {analyze_count}.")

    for i in range(analyze_count):
        card = product_locator.nth(i)
        try:
            name_elem = card.locator('div[data-slot-id="ProductName"] span').first
            price_elem = card.locator('p.cGFDG0.cB6nZL span.cnL9fm').first
            
            if not await name_elem.is_visible(timeout=1000) or not await price_elem.is_visible(timeout=1000):
                continue
            
            name = (await name_elem.text_content(timeout=2000)).strip()
            price_parent = price_elem.locator('..')
            price_text = await price_parent.text_content(timeout=2000)
            price = float(re.sub(r'[^\d.]', '', price_text))
            
            scraped_products.append({'name': name, 'price': price, 'card': card})
        except Exception as e:
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
        add_button = selected_card.locator('button.ciE0m4.c2lTrV.cuPUm6.cVtNX5').first
        await add_button.click(timeout=5000)
        print("- Clicked 'ADD' once.")
        await page.wait_for_timeout(1000)
        
        # Check if Super Saver popup appeared and close it
        try:
            close_button = page.locator('button.absolute.right-3').first
            if await close_button.is_visible(timeout=2000):
                print("- Super Saver popup detected, closing it...")
                await close_button.click(timeout=5000)
                await page.wait_for_timeout(500)
        except Exception:
            pass
        
        if quantity > 1:
            for i in range(quantity - 1):
                plus_button = page.locator('button.cG8zC0[aria-label="Increase quantity"]').first
                await plus_button.click(timeout=5000)
                print(f"- Clicked '+' ({i+2}/{quantity})")
                await page.wait_for_timeout(300)
        print(f"✅ Successfully added {quantity} of '{item_name}' to cart.")

    except Exception as e:
        print(f"❌ An unexpected error occurred while adding to cart: {e}")

async def automate_zepto(shopping_list: dict, location: str, mobile_number: str, p):
    """
    Launches Playwright, navigates to Zepto, sets location, and processes the shopping list.
    """
    print("\nStep 2: Starting browser automation with Playwright for Zepto...")
    browser = await p.chromium.launch(headless=False, slow_mo=100)
    context = await browser.new_context()
    page = await context.new_page()

    try:
        print("➡️ Navigating to https://www.zeptonow.com/")
        await page.goto("https://www.zeptonow.com/")
        await page.wait_for_load_state('networkidle')
        print("✅ Zepto homepage loaded.")

        print("\n➡️ Clicking on 'Select Location' button...")
        select_location_button = page.get_by_text("Select Location").first
        await select_location_button.click()
        print("✅ 'Select Location' button clicked.")

        print(f"\n➡️ Typing location '{location}' into the search bar...")
        location_input = page.get_by_placeholder("Search a new address")
        await location_input.fill(location)
        print("✅ Location entered.")

        print("\n➡️ Waiting for location suggestions and selecting the first one...")
        first_suggestion_selector = 'div[data-testid="address-search-item"]'
        await page.wait_for_selector(first_suggestion_selector, timeout=10000)
        print("✅ Suggestions appeared.")
        
        await page.locator(first_suggestion_selector).first.click()
        print("✅ First location suggestion selected.")

        print("\n➡️ Clicking 'Confirm & Continue'...")
        confirm_button_selector = "button.cpG2SV.cdW7ko.c0WLye.cBCT4J"
        await page.locator(confirm_button_selector).click()
        print("✅ Location confirmed and set successfully!")
        
        print("\nWaiting for page to load...")
        await page.wait_for_timeout(4000)

        print("\nStep 3: Preparing to add items to cart...")
        for item, quantity in shopping_list.items():
            await search_and_add_item(page, item, quantity)
        
        print("-----------------------------------------")
        print("\n✅ All items processed. Cart should be ready.")
        
        print("\nStep 4: Clicking on cart button...")
        try:
            cart_button = page.locator('button[data-testid="cart-btn"]').first
            await cart_button.click(timeout=5000)
            print("✅ Cart button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking cart button: {e}")
            return
        
        print("\nStep 5: Clicking on 'Login' button...")
        try:
            login_button = page.locator('div.flex.items-center.justify-center h6').first
            await login_button.click(timeout=5000)
            print("✅ Login button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Login button: {e}")
            return
        
        print("\nStep 6: Entering phone number...")
        try:
            phone_input = page.locator('input[placeholder="Enter Phone Number"]').first
            await phone_input.fill(mobile_number)
            print("✅ Phone number entered successfully.")
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"❌ Error entering phone number: {e}")
            return
        
        print("\nStep 7: Clicking 'Continue' button...")
        try:
            continue_button = page.locator('button[type="button"]:has-text("Continue")').first
            await continue_button.click(timeout=5000)
            print("✅ Continue button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Continue button: {e}")
            return
        
        print("\nStep 8: Waiting for OTP entry (25 seconds)...")
        print("⏳ Please enter the OTP on the browser...")
        await asyncio.sleep(25)
        print("✅ OTP wait period completed.")
        
        print("\nStep 9: Clicking 'Add Address to proceed' button...")
        try:
            add_address_button = page.locator('button.my-2\\.5.h-\\[52px\\].w-full.rounded-xl.bg-skin-primary.text-center').first
            await add_address_button.click(timeout=5000)
            print("✅ Add Address button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Add Address button: {e}")
            return
        
        print("\nStep 10: Selecting the first saved address...")
        try:
            first_address = page.locator('div.ctyATk').first
            await first_address.click(timeout=5000)
            print("✅ First address selected.")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"❌ Error selecting address: {e}")
            return
        
        print("\nStep 11: Clicking 'Click to Pay' button...")
        try:
            pay_button = page.locator('button.my-2\\.5.h-\\[52px\\].w-full.rounded-xl.text-center.bg-skin-primary').first
            await pay_button.click(timeout=5000)
            print("✅ 'Click to Pay' button clicked successfully.")
        except Exception as e:
            print(f"❌ Error clicking 'Click to Pay' button: {e}")
            return
        
        print("\n✅ Automation script finished.")
        print("Browser will close in 10 seconds.")
        await asyncio.sleep(10)

    except TimeoutError as e:
        print(f"❌ A timeout error occurred: {e}")
        print("   The script could not find an element in time. This might be due to a slow network or a change in the website's layout.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        await browser.close()
        print("\nBrowser closed. Script finished.")
