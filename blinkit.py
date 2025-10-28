import os
import json
import re
import asyncio
from playwright.async_api import async_playwright, TimeoutError
import google.generativeai as genai
from dotenv import load_dotenv
from urllib.parse import quote_plus
from difflib import SequenceMatcher

# --- Gemini Setup and Functions ---

load_dotenv(dotenv_path='api/api_keys/.env')

try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in .env file.")
    genai.configure(api_key=api_key)
    # Use a faster, more recent model for these tasks
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
except (TypeError, ValueError) as e:
    print(f"❌ ERROR: {e}")
    exit()

def analyze_query(user_query: str) -> dict:
    """Analyzes a grocery query using Gemini and returns a structured dictionary."""
    prompt = f"""
    You are an expert order processing AI. Analyze the user's query and extract item names and their quantities.
    Return the output ONLY as a valid JSON object where keys are item names (strings) and values are quantities (integers).
    If quantity is not specified, assume it is 1. Do not include any other text or markdown formatting.

    User Query: "{user_query}"
    JSON Output:
    """
    print("Step 1: Analyzing user query with Gemini...")
    response = gemini_model.generate_content(prompt)
    
    try:
        response_text = response.text.strip().strip("```json").strip()
        parsed_items = json.loads(response_text)
        print("✅ Analysis successful!")
        return parsed_items
    except (json.JSONDecodeError, IndexError) as e:
        print(f"❌ ERROR: Could not parse model's response. Raw response: {response.text}")
        return {}

def string_similarity(a: str, b: str) -> float:
    """Calculate similarity between two strings (0 to 1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_best_match(query_item: str, scraped_products: list) -> dict | None:
    """Uses LLM to find the best product match from a scraped list."""
    if not scraped_products:
        return None

    product_names = [p['name'] for p in scraped_products]
    
    products_with_prices = [{'name': p['name'], 'price': p['price']} for p in scraped_products]
    
    prompt = f"""You are selecting the best grocery product match.
User search: "{query_item}"
Product options with prices: {json.dumps(products_with_prices)}

IMPORTANT: 
1. If the user is searching for a fruit or vegetable, only select the actual fresh produce item, NOT juices, smoothies, or processed products.
2. Among valid matches,  most valid produt name option and among most valid product name options prefer the cheapest one
Return ONLY the exact product name from the list. If no good match, return "None"."""
    
    response = gemini_model.generate_content(prompt)
    best_match_name = response.text.strip()

    if best_match_name == "None":
        return None

    for product in scraped_products:
        if product['name'] == best_match_name:
            print(f"- Best match: '{product['name']}' at ₹{product['price']}")
            return product
    
    return None

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

async def automate_blinkit(shopping_list: dict, location: str, mobile_number: str):
    """Launches Playwright to set location and process the shopping list."""
    print("\nStep 2: Starting browser automation with Playwright...")
    async with async_playwright() as p:
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
        await asyncio.sleep(25)
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

# --- Main execution block ---
if __name__ == "__main__":
    async def main():
        user_grocery_query = "order me 2 coke kitkat 3 1 sonpapdi"
        user_location = "noida sector 137"
        user_mobile = "7842848429" # Replace with a valid number for testing
        
        shopping_list = analyze_query(user_grocery_query)

        if shopping_list:
            print("\n--- Stored Shopping List ---")
            print(shopping_list)
            print("----------------------------")
            await automate_blinkit(shopping_list, user_location, user_mobile)
        else:
            print("\nCould not create a shopping list. Aborting browser automation.")
    
    asyncio.run(main())
