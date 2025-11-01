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
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.user_agent = None

    async def initialize_browser(self):
        """Initialize Playwright browser and context."""
        self.logger.info("Initializing Playwright browser...")
        
        playwright = await async_playwright().start()
        
        browser_kwargs = {
            'headless': False,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-web-resources',
            ]
        }
        
        # if self.proxy:
        #     browser_kwargs['proxy'] = {'server': self.proxy}
        
        self.browser = await playwright.chromium.launch(**browser_kwargs)
        
        context_kwargs = {
            'viewport': {'width': 1280, 'height': 720},
        }
        
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
        
        self.logger.info("Browser closed")
