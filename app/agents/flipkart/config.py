import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    
    # AWS Bedrock Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION: Optional[str] = os.getenv("AWS_REGION", "us-east-1")
    
    # Provider Settings
    USE_LLM: bool = os.getenv("USE_LLM", "true").lower() == "true"
    PREFERRED_PROVIDER: str = os.getenv("PREFERRED_PROVIDER", "openai")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
    
    # Playwright Configuration
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
    SLOW_MO: int = int(os.getenv("SLOW_MO", "100"))
    TIMEOUT: int = int(os.getenv("TIMEOUT", "30000"))
    
    # Automation Settings
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY: int = int(os.getenv("RETRY_DELAY", "2"))
    
    # Flipkart Selectors
    SELECTORS = {
        "search_input": ["[name='q']", "input[title*='search']", "._3704LK"],
        "login_close": ["button._2KpZ6l._2doB4z", "[data-testid='close-modal']"],
        "product_card": ["[data-tkid]", "._1fQZEK", "a[href*='/p/']"],
        "add_to_cart": ["button:has-text('Add to Cart')", "._2KpZ6l._2U9uOA._3v1-ww"],
        "cart_icon": ["._3SkBxJ", "[href*='viewcart']", "a[href*='viewcart']"],
        "place_order": ["text=Place Order", "button:has-text('Place Order')"],
        "quantity_increase": ["button:has-text('+')", "._23FHuj", "[aria-label*='increase']"],
        "continue_button": ["button:has-text('Continue')", "._2KpZ6l._1seccl._3AWRsL"]
    }