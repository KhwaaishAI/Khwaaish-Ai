from playwright.async_api import async_playwright
from app.agents.flipkart.config import Config
from app.agents.flipkart.llm.assistant import LLMAssistant
from app.agents.flipkart.utills.logger import setup_logger

class FlipkartAutomation:
    def __init__(self):
        self.config = Config()
        self.llm = LLMAssistant(self.config)
        self.logger = setup_logger()
        self.llm.set_logger(self.logger)
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def initialize_browser(self):
        """Initialize Playwright browser"""
        try:
            self.logger.info("🚀 Initializing browser...")
            self.playwright = await async_playwright().start()
            
            self.browser = await self.playwright.chromium.launch(
                headless=self.config.HEADLESS,
                slow_mo=self.config.SLOW_MO,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.config.TIMEOUT)
            
            self.logger.info("✅ Browser initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Browser initialization failed: {str(e)}")
            return False

    async def close(self):
        """Cleanup resources"""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.logger.info("✅ Cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup error: {str(e)}")