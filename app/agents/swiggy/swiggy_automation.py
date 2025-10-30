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
from app.prompts.swiggy_prompts.swiggy_prompt import create_swiggy_automation_prompt

load_dotenv(dotenv_path='api/api_keys/.env')

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
