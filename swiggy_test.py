"""
COMPLETE SWIGGY AUTOMATION - Your Working Code + Fixes
"""
import asyncio
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path='api/api_keys/.env')

# ============================================================================
# PART 1: MCP TOOL CONVERTER - YOUR ORIGINAL CODE
# ============================================================================

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

# ============================================================================
# PART 2: SWIGGY AUTOMATION PROMPT WITH YOUR SELECTORS
# ============================================================================

def create_swiggy_automation_prompt(item: str, restaurant: str, location: str, phone_number: str) -> str:
    """Create automation prompt with your exact HTML selectors"""
    
    prompt = f"""
You are a web automation agent for Swiggy food ordering. Follow each step carefully.

TASK PARAMETERS:
- Location: {location}
- Restaurant: {restaurant}
- Item to order: {item}
- Phone number: {phone_number}

STEP 1: NAVIGATE AND LOAD
- Navigate to https://www.swiggy.com
- Wait 2 seconds for page to fully render
- Take page snapshot

STEP 2: SET DELIVERY LOCATION
- Find input element:
  * type="text"
  * class="_5ZhdF _3GoNS _1LZf8"
  * name="location"
  * placeholder="Enter your delivery location"
- Click on this input field
- Type "{location}"
- Wait 1 seconds
- Look for suggestions in <div class="kuQWc"> elements
- Click the first suggestion
- Wait 2 seconds for page to reload with location set
- Take page snapshot

STEP 3: SEARCH FOR RESTAURANT
- Navigate to https://www.swiggy.com/search
- Wait 1 seconds
- Find input element:
  * type="text"
  * class="ssM7E"
  * placeholder="Search for restaurants and food"
- Click the search input
- Type "{restaurant}"
- Wait 1 seconds for suggestions to appear
- Look for suggestion items with:
  * tag: <button class="xN32R" data-testid="autosuggest-item">
  * Inside: <div class="_38J4H"> contains restaurant name
  * Inside: <div class="_2B_8A"> contains type (should say "Restaurant", not "Dish")
- Find the FIRST suggestion where:
  * Restaurant name matches or contains "{restaurant}"
  * Type is "Restaurant" (not "Dish")
- Click on this suggestion button
- Wait 1 seconds
- Now look for and click the restaurant card:
  * Find: <div data-testid="resturant-card-name" class="_1XaJt">
  * This div contains the restaurant name "{restaurant}"
  * Click on this div to open the restaurant page
- Wait 1 seconds for menu to load completely
- Take page snapshot


STEP 4: SEARCH AND ADD ITEM TO CART
- Find the search input with:
  * type="text"
  * class="_2cVkR"
  * placeholder="Search in La Pino'z Pizza"
  * data-cy="menu-search-header"
- Click on this search input
- Type "{item}"
- Wait 2 seconds for item suggestions to load
- Look for item suggestions in divs with:
  * aria-hidden="true"
  * class contains "sc-aXZVg eqSzsP sc-bmzYkS dnFQDN"
  * Text content contains "{item}" name
- Find the FIRST matching item suggestion with name "{item}"
- Click on this item suggestion div
- Wait 1 second
- Look for the ADD button with:
  * class contains "sc-ggpjZQ sc-cmaqmh jTEuJQ fcfoYo add-button-center-container"
  * Inside: <div class="sc-aXZVg biMKCZ">Add</div>
- Click the ADD button (item is now added to cart)
- Wait 1 second
- Take page snapshot

STEP 5: VIEW CART AND PROCEED TO CHECKOUT
- Look for the cart display with:
  * class="_1JiK6"
  * Contains text showing item count and price (e.g., "1 Item | ₹269")
  * Inside: <span class="ZVNHp"><span>View Cart</span>
- Click on the "View Cart" section to open cart
- Wait 3 seconds for cart page to load
- Take page snapshot

STEP 6: LOGIN - CLICK LOGIN BUTTON
- Look for login option with:
  * class="WO7LQ _2ThIK"
  * Inside: <div class="_2UOuf">LOG IN</div>
- Click on the "LOG IN" button/div
- Wait 2 seconds for login form to appear
- Take page snapshot

STEP 7: LOGIN - ENTER PHONE NUMBER
- Find phone input with:
  * class="_5ZhdF"
  * type="tel"
  * name="mobile"
  * id="mobile"
  * maxlength="10"
- Click on this input field
- Type "{phone_number}" (10 digits only, without country code)
- Wait 1 second
- "class="ApfF7"" find this and click on login button
- Take page snapshot


STEP 9: WAIT FOR OTP ENTRY (USER MANUAL)
- Wait for OTP input field with:
  * class="_5ZhdF"
  * type="text"
  * name="otp"
  * id="otp"
  * maxlength="6"
- Wait 20 seconds for user to manually enter OTP in this field
- Do NOT attempt to auto-fill OTP
- Take page snapshot after user enters OTP

STEP 10: VERIFY OTP
- Find  the class="ApfF7" and click the verify button with:
- Wait 5 seconds for login to complete
- Take page snapshot

STEP 10: SELECT ADDRESS
- Find and click first address or Home address
- Wait 2 seconds
- Take page snapshot

STEP 11: PROCEED TO PAYMENT
- Click Proceed/Continue button
- Wait 5 seconds
- Take page snapshot

STEP 12: FINAL
- Take screenshot of payment page
- Report completion
"""
    
    return prompt

# ============================================================================
# PART 3: MAIN AUTOMATION - YOUR ORIGINAL FUNCTION
# ============================================================================

async def run_agent(item: str, restaurant: str, location: str, phone_number: str):
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

# ============================================================================
# PART 4: TEST FILE ENTRY POINT
# ============================================================================

async def main():
    """Test entry point"""
    result = await run_agent(
        item="pepper chicken biriyani 650gms",
        restaurant="thalairaj biriyanni",
        location="noida sector 137",
        phone_number="9876543210"
    )
    print(f"\nFinal Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())