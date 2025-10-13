import os
from tavily import TavilyClient
from dotenv import load_dotenv
import json
from app.prompts.flipkart_prompts.flipkart_prompt import product_info_prompt
from config import Config

load_dotenv()



from app.agents.flipkart.llm.assistant import LLMAssistant

llm = LLMAssistant(Config)

async def tavily(url, automation=None):
    import logging
    if automation and hasattr(automation, 'logger'):
        logger = automation.logger
    else:
        logger = logging.getLogger("flipkart_tools.search")
    
    tavily_api_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_api_key:
        logger.warning("TAVILY_API_KEY not found in environment variables.")
        return None

    tavily_client = TavilyClient(api_key=tavily_api_key)
    try:
        logger.info(f"Extracting content from URL: {url}")
        response = tavily_client.extract(url)

        # New response structure
        results = response.get("results", [])
        if not results:
            logger.warning("No results returned from Tavily.")
            return None

        first_result = results[0]
        raw_content = first_result.get("raw_content", "")
        images = first_result.get("images", [])
        favicon = first_result.get("favicon", "")
        extracted_url = first_result.get("url", "")

        if raw_content:
            logger.info("Successfully extracted raw_content from Tavily.")
        else:
            logger.warning("raw_content is empty for the given URL.")

        return {
            "raw_content": raw_content,
            "images": images,
            "favicon": favicon,
            "url": extracted_url
        }

    except Exception as e:
        logger.error(f"Error extracting content from Tavily: {str(e)}")
        return None


async def product_info(url):
    # Get content from Tavily
    content_data = await tavily(url)
    if not content_data or not content_data.get("raw_content"):
        return {"error": "No content extracted from URL."}

    raw_html = content_data["raw_content"]
    user_query = f"RAW_HTML:{raw_html}"

    try:
        # Analyze content with LLM
        result = await llm.invoke(product_info_prompt, user_query)
        if result:
            try:
                analysis_json = json.loads(result)
            except Exception:
                analysis_json = {"raw_output": result}
            analysis = analysis_json
        else:
            analysis = {"error": "LLM did not return a response"}
    except Exception as e:
        analysis = {"error": "Exception during analysis", "details": str(e)}

    # Include Tavily metadata in output
    analysis["_source"] = {
        "url": content_data.get("url"),
        "images": content_data.get("images"),
        "favicon": content_data.get("favicon")
    }

    # Save analyzed data to file
    filename = "flipkart.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"error": "Failed to save analysis output.", "details": str(e)}

    return analysis
