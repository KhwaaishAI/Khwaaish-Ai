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
        # Use a more specific locator for the search button on the home page
        await page.locator('div[type="button"]:has-text("Search for restaurant, item or more")').click()

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
        # Locate all product cards. Using data-testid for robustness.
        product_cards = await page.locator('div[data-testid^="search-pl-dish"], div[data-testid="normal-dish-item"]').all()
        print(f"Found {len(product_cards)} product cards.")

        for i, card in enumerate(product_cards[:30]):
            try:
                restaurant_name = await card.locator('div._1P-Lf._2PDpZ').first.text_content() if await card.locator('div._1P-Lf._2PDpZ').count() > 0 else "N/A"
                rating = await card.locator('span._30uSg').first.text_content() if await card.locator('span._30uSg').count() > 0 else "N/A"
                delivery_time = await card.locator('div:has-text("MINS")').first.text_content() if await card.locator('div:has-text("MINS")').count() > 0 else "N/A"
                
                # Item Name - often in a specific div or from description
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

                product_data.append({
                    "restaurant_name": restaurant_name.strip(),
                    "item_name": item_name.strip(),
                    "rating": rating.strip(),                    
                    "price": price.strip(),
                    "original_price": original_price.strip() if original_price != "N/A" else None,
                    "is_veg": is_veg
                })
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

        