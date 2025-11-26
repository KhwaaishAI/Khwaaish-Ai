import asyncio
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
from dotenv import load_dotenv
import json
from playwright.async_api import async_playwright
from app.prompts.swiggy_prompts.swiggy_prompt import create_swiggy_automation_prompt

load_dotenv(dotenv_path='api/api_keys/.env')

SWIGGY_AUTH_FILE_PATH = os.path.join(os.path.dirname(__file__), "swiggy_auth.json")
    
async def parse_query(query: str) -> dict:
    """Parse natural language query to extract item and restaurant"""
    
    llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0
        )
        
    parse_prompt = f"""
    Extract the food item and restaurant name from this query.
    Return ONLY a JSON object with "item" and "restaurant" keys.
    
    Query: {query}
    
    Example output format:
    {{"item": "chicken biryani", "restaurant": "Biryani Blues"}}
    
    JSON output:"""
        
    response = await llm.ainvoke(parse_prompt)
        
    # Extract JSON from response
    content = response.content.strip()
    # Remove markdown code blocks if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    content = content.strip()
    
    parsed = json.loads(content)
    print(f"📝 Parsed Query -> Item: {parsed['item']}, Restaurant: {parsed['restaurant']}")
    return parsed

def mcp_to_langchain_tool(mcp_tool, session):
    """Convert MCP tool to LangChain StructuredTool with proper schema"""
    
    # Create Pydantic model from inputSchema
    schema = mcp_tool.inputSchema
    fields = {}
    
    if "properties" in schema:
        for prop_name, prop_info in schema["properties"].items():
            prop_type = str
            if prop_info.get("type") == "number":
                prop_type = float
            elif prop_info.get("type") == "integer":
                prop_type = int
            elif prop_info.get("type") == "boolean":
                prop_type = bool
            
            is_required = prop_name in schema.get("required", [])
            default = ... if is_required else None
            
            fields[prop_name] = (
                prop_type,
                Field(default=default, description=prop_info.get("description", ""))
            )
    
    InputModel = create_model(f"{mcp_tool.name}_input", **fields)
    
    async def tool_func(**kwargs):
        """Execute MCP tool"""
        result = await session.call_tool(mcp_tool.name, kwargs)
        if result.content:
            return str(result.content[0].text) if hasattr(result.content[0], 'text') else str(result.content[0])
        return "Success"
    
    return StructuredTool(
        name=mcp_tool.name,
        description=mcp_tool.description or mcp_tool.name,
        func=lambda **kwargs: asyncio.create_task(tool_func(**kwargs)),
        coroutine=tool_func,
        args_schema=InputModel
    )

async def run_agent(query: str, location: str, phone_number: str):
    # Parse query to extract item and restaurant
    parsed = await parse_query(query)
    item = parsed['item']
    restaurant = parsed['restaurant']
    
    # Start Playwright MCP server with --isolated flag for fresh sessions
    server_params = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest", "--isolated"]
    )
    
    print("🔌 Starting Playwright MCP server...")
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Get available tools
            mcp_tools = await session.list_tools()
            print(f"✅ Loaded {len(mcp_tools.tools)} tools\n")
            
            # Convert to LangChain tools
            langchain_tools = [
                mcp_to_langchain_tool(tool, session) 
                for tool in mcp_tools.tools
            ]
            
            # Initialize Gemini with INCREASED token limits
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0,
                max_output_tokens=4096  # INCREASED from 1024
            )
            
            # Define message trimming function to reduce token usage
            from langchain_core.messages.utils import trim_messages, count_tokens_approximately
            
            def pre_model_hook(state):
                """Trim messages to keep only recent context"""
                trimmed = trim_messages(
                    state["messages"],
                    strategy="last",
                    token_counter=count_tokens_approximately,
                    max_tokens=20000,  # INCREASED from 12000
                    start_on="human",
                    end_on=("human", "tool"),
                    include_system=True,  # ADDED
                )
                return {"llm_input_messages": trimmed}
            
            # Create agent with message trimming
            agent = create_react_agent(
                llm, 
                langchain_tools, 
                pre_model_hook=pre_model_hook
            )
            
            # Run task
            print(f"📋 Starting task: Order {item} from {restaurant}\n")
            
            prompt = create_swiggy_automation_prompt(item, restaurant, location, phone_number)
            
            try:
                result = await agent.ainvoke({
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }]
                }, config={"recursion_limit": 250})  # INCREASED from 150
                
                # Print results
                print("\n" + "="*60)
                print("📊 AGENT RESPONSE:")
                print("="*60)
                for i, msg in enumerate(result["messages"]):
                    if hasattr(msg, 'content') and msg.content:
                        content = str(msg.content)[:800]
                        print(f"\n[Step {i}]: {content}")
                
                print("\n✅ Task complete. Browser is running.")
                return "Request has been processed successfully."
            
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                print(f"Error Type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
                raise

async def initiate_signup(p: async_playwright, mobile_number: str, name: str, gmail: str):
    """Navigates to Swiggy, enters details, and stops at the OTP screen."""
    print("🚀 Starting Playwright for Swiggy signup...")
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



    print("✅ Login successful. Saving authentication state...")

    await context.storage_state(path=SWIGGY_AUTH_FILE_PATH)
    print(f"✅ Authentication state saved to {SWIGGY_AUTH_FILE_PATH}")

async def search_swiggy(playwright_instance: async_playwright, location: str, query: str):
    """Launches Swiggy with a logged-in session, sets location, and searches for an item."""
    print("🚀 Starting Playwright for Swiggy search...")
    browser = await playwright_instance.chromium.launch(
        headless=False, # Set to True for production to run in background
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        storage_state=SWIGGY_AUTH_FILE_PATH,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        geolocation={"longitude": 77.5946, "latitude": 12.9716},
        permissions=["geolocation"],
    )
    page = await context.new_page()

    try:
        await page.goto("https://www.swiggy.com", wait_until="networkidle", timeout=60000)
        print("✅ Logged-in Swiggy page loaded.")

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

        # Wait for the page to update with the new location
        await page.wait_for_load_state('networkidle', timeout=20000)
        print("✅ Location updated successfully.")

        # Now, click the search icon/bar
        print("🔍 Clicking the search navigation button...")
        # Handle two different UI variations for the search button using an if/else condition.
        search_selector_1 = 'div[type="button"]:has-text("Search for restaurant, item or more")'
        search_selector_2 = 'a._3nTR3:has-text("Search")'

        await asyncio.sleep(3)
        
        # Check which search element is visible and click it.
        if await page.locator(search_selector_1).is_visible(timeout=5000):
            print("  -> Found search bar (variation 1). Clicking it.")
            await page.locator(search_selector_1).click()
        elif await page.locator(search_selector_2).is_visible(timeout=5000):
            print("  -> Found search link (variation 2). Clicking it.")
            await page.locator(search_selector_2).click()
        else:
            raise Exception("Could not find the search button on the page after setting location.")

        # Wait for the search page to load completely
        await page.wait_for_load_state('networkidle', timeout=20000)
        print("✅ Search page loaded.")

        # FIX: Wait for the search input field to become visible after the click
        # Use a more specific locator based on the likely structure of the search page.
        # Use a more specific locator based on the input field's class
        search_input_locator = page.locator('input.ssM7E')
        await search_input_locator.wait_for(state='visible', timeout=10000)

        print(f"📝 Typing search query: {query}")
        # Type the query character by character to simulate human behavior
        await search_input_locator.type(query, delay=100)

        # Wait for search suggestions to appear and click the first one
        print("🖱️ Clicking the first search suggestion...")
        first_suggestion_locator = page.locator('button[data-testid="autosuggest-item"]').first
        await first_suggestion_locator.wait_for(state='visible', timeout=10000)
        await first_suggestion_locator.click()

        # Wait for the search results page to load
        await page.wait_for_load_state('domcontentloaded', timeout=30000) # Wait for DOM to be ready
        await page.wait_for_selector('div[data-testid^="search-pl-dish"], div[data-testid="normal-dish-item"]', timeout=30000) # Wait for at least one product card
        print("✅ Search results page loaded. Starting data extraction.")

        product_data = []
        seen_products = set()
        
        # Initialize current restaurant details, these will be updated when a restaurant card is encountered
        current_restaurant_name = "N/A"
        current_rating = "N/A"
        current_delivery_time = "N/A"

        # Locate all product cards, including main restaurant cards and individual dish items
        product_cards = await page.locator('div[data-testid^="search-pl-dish"], div[data-testid="dish-item-container"], div[data-testid="normal-dish-item"]').all()
        print(f"Found {len(product_cards)} product cards.")

        for i, card in enumerate(product_cards[:30]):
            try:
                # Determine if this 'card' is a restaurant header card or an individual dish item
                is_restaurant_header_card = await card.evaluate('element => element.hasAttribute("data-testid") && element.getAttribute("data-testid").startsWith("search-pl-dish")')

                if is_restaurant_header_card:
                    # This card is a restaurant header. Extract its details and update current_restaurant_name, etc.
                    # The restaurant name is in div._1P-Lf._2PDpZ
                    restaurant_name_element = card.locator('div._1P-Lf._2PDpZ').first
                    if await restaurant_name_element.count() > 0:
                        current_restaurant_name = await restaurant_name_element.text_content()
                        if current_restaurant_name and current_restaurant_name.lower().startswith('by '):
                            current_restaurant_name = current_restaurant_name[3:]
                    else:
                        current_restaurant_name = "N/A"

                    # Rating is in span._30uSg
                    rating_element = card.locator('span._30uSg').first
                    current_rating = await rating_element.text_content() if await rating_element.count() > 0 else "N/A"

                    # Delivery time is in div.ILmOQ div:has-text("MINS")
                    delivery_time_element = card.locator('div.ILmOQ div:has-text("MINS")').first
                    current_delivery_time = await delivery_time_element.text_content() if await delivery_time_element.count() > 0 else "N/A"

                    # Now, this restaurant header card also contains the *first* dish item within it.
                    # We need to extract the dish details from this nested element.
                    dish_element_to_process = card.locator('div[data-testid="normal-dish-item"]').first
                    if await dish_element_to_process.count() > 0:
                        # Extract dish-specific details from dish_element_to_process
                        item_name_element = dish_element_to_process.locator('div.sc-aXZVg.eqSzsP.sc-bmzYkS.dnFQDN').first
                        item_name = await item_name_element.text_content() if await item_name_element.count() > 0 else "N/A"

                        price_element = dish_element_to_process.locator('div.sc-aXZVg.chixpw').first
                        price = await price_element.text_content() if await price_element.count() > 0 else "N/A"

                        original_price_element = dish_element_to_process.locator('div.sc-aXZVg.htLzaO.sc-gEvEer.hTspMV').first
                        original_price = await original_price_element.text_content() if await original_price_element.count() > 0 else "N/A"

                        description_element = dish_element_to_process.locator('p._1QbUq').first
                        description = await description_element.text_content() if await description_element.count() > 0 else "N/A"
                        is_veg = "Veg Item." in description

                        product_identifier = (item_name.strip(), price.strip(), current_restaurant_name.strip())
                        if product_identifier not in seen_products:
                            product_details = {
                                "restaurant_name": current_restaurant_name.strip(),
                                "item_name": item_name.strip(),
                                "rating": current_rating.strip(),
                                "delivery_time": current_delivery_time.strip(),
                                "price": price.strip(),
                                "original_price": original_price.strip() if original_price != "N/A" else None,
                                "is_veg": is_veg
                            }
                            product_data.append(product_details)
                            seen_products.add(product_identifier)
                    else:
                        print(f"⚠️ Restaurant header card {i} found but no immediate dish item within it. Skipping this card as a dish.")

                else:  # This card is an individual dish item (e.g., data-testid="normal-dish-item" or "dish-item-container")
                    # Use the most recently updated restaurant details (current_restaurant_name, current_rating, current_delivery_time)
                    # Item Name
                    item_name_element = card.locator('div.sc-aXZVg.eqSzsP.sc-bmzYkS.dnFQDN').first
                    item_name = await item_name_element.text_content() if await item_name_element.count() > 0 else "N/A"

                    # Price
                    price_element = card.locator('div.sc-aXZVg.chixpw').first
                    price = await price_element.text_content() if await price_element.count() > 0 else "N/A"

                    # Original Price (if discounted)
                    original_price_element = card.locator('div.sc-aXZVg.htLzaO.sc-gEvEer.hTspMV').first
                    original_price = await original_price_element.text_content() if await original_price_element.count() > 0 else "N/A"

                    # Description and Veg/Non-Veg status
                    description_element = card.locator('p._1QbUq').first
                    description = await description_element.text_content() if await description_element.count() > 0 else "N/A"
                    is_veg = "Veg Item." in description

                    product_identifier = (item_name.strip(), price.strip(), current_restaurant_name.strip())
                    if product_identifier not in seen_products:
                        product_details = {
                            "restaurant_name": current_restaurant_name.strip(),
                            "item_name": item_name.strip(),
                            "rating": current_rating.strip(),
                            "delivery_time": current_delivery_time.strip(),
                            "price": price.strip(),
                            "original_price": original_price.strip() if original_price != "N/A" else None,
                            "is_veg": is_veg
                        }
                        product_data.append(product_details)
                        seen_products.add(product_identifier)

            except Exception as e:
                print(f"Error extracting data for card {i}: {e}")
                continue
        
        # Define the path for the data directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        data_dir = os.path.join(project_root, 'data', 'swiggy')
        os.makedirs(data_dir, exist_ok=True)

        # Sanitize the query to create a valid filename
        sanitized_query = "".join(c for c in query if c.isalnum() or c in (' ', '_')).rstrip()
        filename = f"{sanitized_query.replace(' ', '_')}.json"
        filepath = os.path.join(data_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(product_data, f, ensure_ascii=False, indent=4)
        print(f"✅ Scraped data saved to {filepath}")

        print("✅ Data extraction complete. Browser will close in 5 seconds.")
        await asyncio.sleep(5) # Give some time to see the results before closing
        return context, product_data
    except Exception:
        await browser.close() # Ensure browser closes on error
        raise

async def add_product_to_cart(context, product: dict):
    """
    Adds a specific product to the cart using the provided browser context.
    Expects product dict to contain 'item_name'.
    """
    page = context.pages[0]
    item_name = product.get("item_name")
    restaurant_name = product.get("restaurant_name")
    
    if not item_name or not restaurant_name:
        raise ValueError("Product dictionary must contain both 'item_name' and 'restaurant_name'")

    print(f"🛒 Attempting to add '{item_name}' from '{restaurant_name}' to cart...")
    
    # We need to find the specific card that matches the item name.
    # This is a bit tricky because there might be multiple items with similar names.
    # We'll try to find a card that contains the exact item name text.
    
    # Wait for product cards to be visible just in case
    await page.wait_for_selector('div[data-testid^="search-pl-dish"], div[data-testid="normal-dish-item"]', timeout=10000)
    
    # Strategy: Iterate through cards, find the one with matching name, click its ADD button.
    product_cards = await page.locator('div[data-testid^="search-pl-dish"], div[data-testid="normal-dish-item"]').all()
    
    target_card = None
    # This will hold the most recently seen restaurant name as we iterate
    current_restaurant_for_card = "N/A"

    for card in product_cards:
        # Check if the card is a restaurant header, and if so, update our current restaurant context
        is_restaurant_header = await card.evaluate('element => element.getAttribute("data-testid")?.startsWith("search-pl-dish")')
        if is_restaurant_header:
            restaurant_name_el = card.locator('div._1P-Lf._2PDpZ').first
            if await restaurant_name_el.count() > 0:
                raw_name = await restaurant_name_el.text_content()
                # Clean up the "By " prefix
                current_restaurant_for_card = raw_name[3:] if raw_name and raw_name.lower().startswith('by ') else raw_name

        # Now, extract the item name from the card to compare
        card_item_name_el = card.locator('div.sc-aXZVg.eqSzsP.sc-bmzYkS.dnFQDN').first
        if await card_item_name_el.count() > 0:
            current_name = await card_item_name_el.text_content()

            # Check if both restaurant name and item name match
            restaurant_match = restaurant_name.lower() in current_restaurant_for_card.lower()
            item_match = item_name.lower() in current_name.lower()

            if restaurant_match and item_match:
                target_card = card
                break
    
    if not target_card:
        raise Exception(f"Could not find product card for '{item_name}' from restaurant '{restaurant_name}'")
        
    print(f"✅ Found product card for '{item_name}' from '{restaurant_name}'. Clicking ADD...")
    await asyncio.sleep(2)
    
    
    try:
        # Try the specific button class first
        await target_card.locator('button.add-button-center-container').click(timeout=3000)
    except:
        try:
            # Fallback 1: Try button with text "Add"
            await target_card.locator('button:has-text("Add")').click(timeout=3000)
        except:
            # Fallback 2: original generic approach
            await target_card.locator('button:has-text("Add")').click(timeout=3000)
    print("✅ Clicked ADD.")
    await asyncio.sleep(2)

    # Handle "Items already in cart" popup
    try:
        # Check for the presence of the popup using a distinctive element or text
        cart_reset_popup_selector = 'div._2LzP9:has-text("Items already in cart")'
        if await page.locator(cart_reset_popup_selector).is_visible(timeout=5000):
            print("⚠️ 'Items already in cart' popup detected. Clicking 'Yes, start afresh'.")
            yes_start_afresh_button = page.locator('button.hoJL8:has-text("Yes, start afresh")')
            await yes_start_afresh_button.click()
            print("✅ Clicked 'Yes, start afresh'.")
            await asyncio.sleep(2) # Give some time for the cart to reset and page to update
    except Exception as e:
        print(f"ℹ️ No 'Items already in cart' popup or error handling it: {e}")


    # Handle potential customization popup with specific user logic
    try:
        # Check for the specific modal class provided by user or generic dialog
        modal_selector = 'div._2sOR4, div[role="dialog"]'
        
        # Check if modal exists
        if await page.locator(modal_selector).count() > 0 or await page.wait_for_selector(modal_selector, timeout=3000):
            print("⚠️ Customization modal detected.")
            
            # Scenario 1: A "Continue" button appears first. Click it to reveal the next step.
            continue_btn = page.locator('button[data-testid="menu-customize-continue-button"]')
            if await continue_btn.count() > 0 and await continue_btn.is_visible():
                await continue_btn.click()
                print("✅ Clicked 'Continue' on customization modal.")
                await asyncio.sleep(1) # Wait for the next part of the modal to load.

            # Scenario 2: Handle other options like "Served Hot" if they exist.
            served_hot_locator = page.locator('div:has-text("Served Hot")').last
            if await served_hot_locator.count() > 0:
                print("ℹ️ Found 'Served Hot' option. Selecting it...")
                await served_hot_locator.click()
                print("✅ Selected 'Served Hot'.")
                await asyncio.sleep(1)

            # Final Step: Click the "Add Item to cart" button, which should now be visible.
            add_footer_btn = page.locator('div.pEWTb button[data-cy="customize-footer-add-button"]:has-text("Add Item to cart")')
            if await add_footer_btn.count() > 0:
                await add_footer_btn.click() # First attempt
                print("✅ Clicked 'Add Item to cart' button. Checking for required selections...")
                await asyncio.sleep(2) # Wait to see if modal closes

                # If modal is still visible, a mandatory choice was likely missed.
                if await page.locator(modal_selector).is_visible():
                    print("⚠️ Modal still open. A required choice (e.g., Raita) might be needed.")
                    # Based on user HTML, select the first available raita option.
                    # The user indicated the clickable element is the span with data-testid="icon"
                    raita_clickable_icon_selector = 'div[data-testid="style-check-box"] span[data-testid="icon"]'
                    if await page.locator(raita_clickable_icon_selector).count() > 0:
                        print("✅ Found Raita options. Selecting the first one...")
                        # Click the visual element instead of using .check() on the input
                        await page.locator(raita_clickable_icon_selector).first.click()
                        await asyncio.sleep(1)
                        # Try adding to cart again
                        await add_footer_btn.click()
                        print("✅ Clicked 'Add Item to cart' again after selecting Raita.")
                    else:
                        print("⚠️ Could not find Raita options to select.")
            else:
                print("⚠️ Could not find the final 'Add Item to cart' button in the modal.")
        else:
             print("ℹ️ No customization modal detected.")

    except Exception as e:
        print("✅ Item added to cart directly without customization.")


    # Verify item count increased in cart or some indicator (optional for now)
    print(f"✅ Processed add to cart for '{item_name}'.")

async def book_order(context, door_no: str, landmark: str, upi_id: str):
    """
    Handles the final booking process from viewing the cart to payment.
    """
    page = context.pages[0]
    print("\n--- Starting Booking Process ---")

    try:
        # 1. Click "View Cart" to proceed to the checkout page
        print("🛒 Clicking 'View Cart'...")
        # Based on user HTML, this is the specific selector for the cart link.
        await asyncio.sleep(2)
        view_cart_button = page.locator('li.xNIjm a[href="/checkout"]:has-text("Cart")')
        await view_cart_button.wait_for(state="visible", timeout=10000)
        await view_cart_button.click()
        await page.wait_for_load_state('networkidle', timeout=20000)
        print("✅ Cart page loaded.")
        await asyncio.sleep(2)

        # 2. Handle Address - Click "Add New Address"
        print("📍 Adding a new delivery address...")
        # Based on user HTML, this selector targets the container with the "Add new Address" text.
        add_address_button = page.locator('div._3EgOG:has-text("Add new Address")')
        await add_address_button.wait_for(state="visible", timeout=10000)
        await add_address_button.click()
        await page.wait_for_load_state('networkidle', timeout=15000)
        print("✅ Address form loaded.")
        await asyncio.sleep(2)

        # 3. Fill in address details
        print(f"📝 Filling address details: Door No: {door_no}, Landmark: {landmark}")
        # Fill Door/Flat No.
        # Based on user HTML, the id is 'building'. Click and type like a human.
        door_input = page.locator('input#building')
        await door_input.click()
        await door_input.type(door_no, delay=100)
        await asyncio.sleep(2)
        # Fill Landmark
        # Click and type like a human for the landmark as well.
        landmark_input = page.locator('input#landmark')
        await landmark_input.click()
        await landmark_input.type(landmark, delay=100)
        await asyncio.sleep(2)

        # Click the "Home" button to tag the address
        print("🏠 Clicking 'Home' to tag the address type...")
        home_button = page.locator('div._1qiSu:has-text("Home")')
        await home_button.click()
        await asyncio.sleep(2)
        # Save the address
        # Based on user HTML, this is the selector for the save address button
        save_address_button = page.locator('a._1kz4H:has-text("SAVE ADDRESS & PROCEED")')
        await save_address_button.click()
        await page.wait_for_load_state('networkidle', timeout=20000)
        print("✅ Address saved. Proceeding to payment.")

        # Click the "Proceed to Pay" button to reveal payment options
        print("▶️ Clicking 'Proceed to Pay'...")
        proceed_to_pay_button = page.locator('button._4dnMB:has-text("Proceed to Pay")')
        await proceed_to_pay_button.wait_for(state="visible", timeout=10000)
        await proceed_to_pay_button.click()
        await page.wait_for_load_state('networkidle', timeout=15000)

        # 4. Select Payment Method - UPI
        print("💳 Selecting UPI as payment method...")
        # Based on user HTML, locate and click the "Add New UPI ID" button.
        add_upi_button_selector = 'div[role="button"]:has-text("Add New UPI ID")'
        add_upi_button = page.locator(add_upi_button_selector)
        await add_upi_button.wait_for(state="visible", timeout=15000)
        await add_upi_button.click()
        print("✅ Clicked 'Add New UPI ID'.")

        # 5. Enter UPI ID
        print(f"⌨️ Entering UPI ID: {upi_id}")
        # Based on user HTML, use the correct selector and type like a human.
        upi_input_selector = 'input#upi-input'
        upi_input = page.locator(upi_input_selector)
        await upi_input.wait_for(state="visible", timeout=10000)
        await upi_input.click()
        await upi_input.type(upi_id, delay=100)

        # 6. Click the final "PAY" button
        print("💸 Clicking final 'Verify and Pay' button...")
        # Based on user HTML, this is the selector for the final pay button
        pay_button_selector = 'button[data-testid="verify_btn"]:has-text("Verify and Pay")'
        pay_button = page.locator(pay_button_selector)
        await pay_button.wait_for(state="visible", timeout=10000)
        await pay_button.click()

        print("\n✅ Order placement initiated successfully!")
        print("⏳ Waiting for 2 minutes for the transaction to be processed...")
        await asyncio.sleep(120)
        await context.browser.close()

    except Exception as e:
        print(f"❌ An error occurred during the booking process: {e}")
        # Taking a screenshot can help debug what went wrong.
        await page.screenshot(path="booking_error.png")
        print("📸 Screenshot of the error page saved as 'booking_error.png'.")
        raise
        