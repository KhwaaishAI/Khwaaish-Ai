import os
import json
from difflib import SequenceMatcher
import google.generativeai as genai
from dotenv import load_dotenv

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
    You are an expert order processing AI. Analyze the user's query and extract items and their quantities.
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
2. Among valid matches, prefer the most valid item name according to item name and among the same names return the cheaper ones
Return ONLY the exact valid product name from the list. If no good match, return "None"."""
    
    response = gemini_model.generate_content(prompt)
    best_match_name = response.text.strip()

    if best_match_name == "None":
        return None

    for product in scraped_products:
        if product['name'] == best_match_name:
            print(f"- Best match: '{product['name']}' at ₹{product['price']}")
            return product
    
    return None
