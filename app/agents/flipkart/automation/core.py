import json
from playwright.async_api import async_playwright
from app.agents.flipkart.config import Config
from app.agents.flipkart.utills.logger import setup_logger
from pathlib import Path
from playwright.async_api import async_playwright
import json

class FlipkartAutomation:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger()
        self.session_store_path = ".flipkart_session.json"
        
        # --- FIX ---
        # Initialize attributes from the config object.
        # We use getattr for safe access, providing None or a default value
        # in case the attribute doesn't exist in your Config object.
        
        # This resolves: AttributeError: 'FlipkartAutomation' object has no attribute 'proxy'
        self.proxy = getattr(self.config, 'PROXY', None) 
        
        # This will be loaded from config instead of being hard-coded to None
        self.user_agent = getattr(self.config, 'USER_AGENT', None)
        
        # This resolves the *next* AttributeError you would have seen:
        # 'FlipkartAutomation' object has no attribute 'timeout'
        # We'll default to 30000ms (30 seconds) if not specified in config.
        self.timeout = getattr(self.config, 'DEFAULT_TIMEOUT', 30000) 
        # --- END FIX ---

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        # self.user_agent = None # This is now handled above

    async def initialize_browser(self):
        """Initialize Playwright browser and context."""
        self.logger.info("Initializing Playwright browser...")
        
        self.playwright = await async_playwright().start() # Changed from playwright = ...
        
        browser_kwargs = {
            'headless': False,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-web-resources',
            ]
        }
        
        # if self.proxy:
        #     browser_kwargs['proxy'] = {'server': self.proxy}
        
        self.browser = await self.playwright.chromium.launch(**browser_kwargs)
        
        context_kwargs = {
            'viewport': {'width': 1280, 'height': 720},
        }
        
        # This check will also work correctly
        if self.user_agent:
            context_kwargs['user_agent'] = self.user_agent
        
        # Load existing session if available
        if Path(self.session_store_path).exists():
            try:
                with open(self.session_store_path, 'r') as f:
                    context_kwargs['storage_state'] = json.load(f)
                self.logger.info(f"Loaded session from {self.session_store_path}")
            except Exception as e:
                self.logger.warning(f"Could not load session: {e}")
        
        self.context = await self.browser.new_context(**context_kwargs)
        self.page = await self.context.new_page()
        
        # # Set default timeout
        # self.page.set_default_timeout(self.timeout)
        
        self.logger.info("Browser initialized successfully")
        # --- FIX for main.py logic ---
        # The main.py file checks the return value, so we should return True on success.
        return True

    async def close_browser(self):
        """Close browser and save session."""
        if self.context and self.session_store_path:
            try:
                storage = await self.context.storage_state(path=self.session_store_path)
                self.logger.info(f"Session saved to {self.session_store_path}")
            except Exception as e:
                self.logger.warning(f"Could not save session: {e}")
        
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        
        # --- FIX ---
        # Properly stop the playwright instance
        if self.playwright:
            await self.playwright.stop()
        # --- END FIX ---
            
        self.logger.info("Browser closed")
