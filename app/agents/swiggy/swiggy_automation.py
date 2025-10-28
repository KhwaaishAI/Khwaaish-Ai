"""
Playwright MCP Agent with LangGraph + Gemini
Agent with login flow and address selection
"""
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv
from app.prompts.swiggy_prompts.swiggy_prompt import create_swiggy_prompt
from app.tools.swiggy_tools.swiggy_mcp_tools import mcp_to_langchain_tool

load_dotenv(dotenv_path='api/api_keys/.env')

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
            
            # Initialize Gemini with token limits
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0,
                max_output_tokens=1024
            )
            
            # Define message trimming function to reduce token usage
            from langchain_core.messages.utils import trim_messages, count_tokens_approximately
            
            def pre_model_hook(state):
                """Trim messages to keep only recent context"""
                trimmed = trim_messages(
                    state["messages"],
                    strategy="last",
                    token_counter=count_tokens_approximately,
                    max_tokens=12000,
                    start_on="human",
                    end_on=("human", "tool"),
                )
                return {"llm_input_messages": trimmed}
            
            # Create agent with message trimming
            agent = create_react_agent(llm, langchain_tools, pre_model_hook=pre_model_hook)
            
            # Run task
            print(f"� Starting task: Order {item} from {restaurant}\n")
            
            prompt = create_swiggy_prompt(item, restaurant, location, phone_number)
            
            result = await agent.ainvoke({
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            }, config={"recursion_limit": 150})  # Increase limit for complex tasks
            
            # Print results
            print("\n" + "="*60)
            print("📊 AGENT RESPONSE:")
            print("="*60)
            for msg in result["messages"]:
                if hasattr(msg, 'content') and msg.content:
                    content = str(msg.content)[:500]
                    print(f"\n{content}")
            
            print("\n✅ Task complete. Browser is running.")
            return "Request has been processed successfully."
