import os
import json
import asyncio
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from difflib import SequenceMatcher
import google.generativeai as genai  # Make sure this is installed: pip install google-generativeai

# ------------------------ GEMINI QUERY ANALYZER SETUP ------------------------
load_dotenv(dotenv_path='api/api_keys/.env')
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in .env file.")
    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
except (TypeError, ValueError) as e:
    print(f"❌ ERROR: {e}")
    exit()

def analyze_query(user_query: str) -> dict:
    """Analyzes a food order query and returns structured JSON data."""
    prompt = f"""
    You are an expert food order processing AI.
    Analyze the user's query and extract all food items, their quantities, and restaurant name.
    Return the output ONLY as a valid JSON list of objects with this exact structure:
    [
        {{
            "item": "<item_name>",
            "quantity": <integer>,
            "restaurant": "<restaurant_name>"
        }}
    ]
    If quantity is not specified, assume it is 1.
    The same restaurant applies to all items if not otherwise stated.
    User Query: "{user_query}"
    JSON Output:
    """
    print("Step 1: Analyzing user query with Gemini...")
    response = gemini_model.generate_content(prompt)
    try:
        response_text = response.text.strip().strip("```json").strip("```").strip()
        parsed_items = json.loads(response_text)
        print("\n✅ Query successfully analyzed! Parsed JSON data:\n")
        print(json.dumps(parsed_items, indent=4))
        return parsed_items
    except (json.JSONDecodeError, IndexError) as e:
        print(f"❌ ERROR: Could not parse model's response. Raw response: {response.text}")
        return {}

def similarity_match(query: str, target: str) -> float:
    """Calculate similarity between two strings."""
    return SequenceMatcher(None, query.lower(), target.lower()).ratio()

# ------------------------ PLAYWRIGHT AUTOMATION ------------------------
async def open_swiggy(parsed_items):
    print("\nStep 2: Initializing Playwright...")
    print("Step 3: Starting browser automation with Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        context = await browser.new_context()
        page = await context.new_page()
        print("Navigating to Swiggy...")
        await page.goto("https://www.swiggy.com/search")
        print("Swiggy opened successfully!")
        print("Page title:", await page.title())
        print("\nClicking on the location selection button...")
        location_button = page.locator("div.wuQJ3")
        await location_button.click()
        location_to_search = "paras tierea sector 137"
        print(f"Typing '{location_to_search}' into the location search bar...")
        location_input = page.locator('input._5ZhdF._3GoNS.itiW2')
        await location_input.fill(location_to_search)
        print("Waiting for 3 seconds for location suggestions to load...")
        await page.wait_for_timeout(3000)
        print("Clicking the first location suggestion...")
        suggestion = page.locator('div._2RwM6').first
        await suggestion.click()
        print("\nLocation selected. Waiting for the restaurant page to load...")
        await page.wait_for_timeout(5000)
        
        # -------- NEW: RESTAURANT SEARCH AND SELECTION --------
        if parsed_items and len(parsed_items) > 0:
            restaurant_name = parsed_items[0].get("restaurant", "")
            
            if restaurant_name:
                print(f"\nStep 4: Searching for restaurant '{restaurant_name}'...")
                
                # Fill the restaurant search input
                restaurant_search_input = page.locator('input.ssM7E')
                await restaurant_search_input.fill(restaurant_name)
                print(f"Typed '{restaurant_name}' in restaurant search bar")
                
                # Wait for suggestions to load
                print("Waiting for suggestions to load...")
                await page.wait_for_timeout(6000)
                
                # Get all suggestion items
                suggestion_items = page.locator('button.xN32R')
                count = await suggestion_items.count()
                
                if count > 0:
                    print(f"Found {count} suggestion(s)")
                    
                    best_match = None
                    best_score = 0
                    best_index = 0
                    
                    # Find the best matching restaurant
                    for i in range(count):
                        try:
                            item = suggestion_items.nth(i)
                            restaurant_text = await item.locator('div._38J4H').text_content(timeout=5000)
                            item_type = await item.locator('div._2B_8A').text_content(timeout=5000)
                            
                            # Only consider restaurants, not dishes
                            if item_type and restaurant_text and "Restaurant" in item_type:
                                similarity_score = similarity_match(restaurant_name, restaurant_text)
                                print(f"  [{i}] {restaurant_text.strip()} - Similarity: {similarity_score:.2%}")
                                
                                if similarity_score > best_score:
                                    best_score = similarity_score
                                    best_match = restaurant_text.strip()
                                    best_index = i
                        except Exception as e:
                            print(f"  [{i}] Skipped (element not accessible)")
                    
                    if best_match:
                        print(f"\n✅ Best match found: '{best_match}' with {best_score:.2%} similarity")
                        print(f"Clicking on the matching restaurant...")
                        await suggestion_items.nth(best_index).click()
                        
                        # Wait for restaurant to load
                        await page.wait_for_timeout(6000)
                        
                        # Click on the restaurant card to open it
                        print("Opening restaurant details...")
                        restaurant_card = page.locator('div._3F-jI')
                        if await restaurant_card.count() > 0:
                            await restaurant_card.first.click()
                            print("✅ Restaurant opened successfully!")
                            await page.wait_for_timeout(6000)
                        else:
                            print("⚠️ Restaurant card not found, but suggestion was clicked")
                    else:
                        print("❌ No matching restaurant found in suggestions")
                else:
                    print("❌ No suggestions found")
        
        print("\nBrowser will close in 15 seconds...")
        await asyncio.sleep(15)
        print("Closing browser...")
        await browser.close()

# ------------------------ MAIN EXECUTION FLOW ------------------------
if __name__ == "__main__":
    user_query = "order me cheese pizza 2, diet coke, chicken pizza from thalairaj biriyani"
    parsed_json = analyze_query(user_query)
    # Proceed to Playwright automation with parsed data
    asyncio.run(open_swiggy(parsed_json))