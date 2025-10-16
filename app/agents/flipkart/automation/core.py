import asyncio
from typing import Dict, Any, Callable
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

    async def execute_step_with_retry(self, step_func: Callable, step_name: str) -> Any:
        """Execute step with retry mechanism and LLM fallback"""
        for attempt in range(self.config.MAX_RETRIES):
            try:
                self.logger.info(f"🔄 {step_name} - Attempt {attempt + 1}")
                result = await step_func()
                self.logger.info(f"✅ {step_name} completed")
                return result
                
            except Exception as e:
                self.logger.warning(f"⚠️ {step_name} failed: {str(e)}")
                
                if attempt < self.config.MAX_RETRIES - 1:
                    # Get DOM for LLM analysis
                    dom_snapshot = await self._get_dom_snapshot()
                    recovery_plan = await self.llm.analyze_failure(
                        step_name, str(e), dom_snapshot
                    )
                    await self._execute_recovery_plan(recovery_plan)
                    await asyncio.sleep(self.config.RETRY_DELAY)
                else:
                    self.logger.error(f"❌ {step_name} failed after {self.config.MAX_RETRIES} attempts")
                    raise

    async def _get_dom_snapshot(self) -> Dict[str, Any]:
        """Get current DOM state"""
        if not self.page:
            return {}
            
        return await self.page.evaluate("""
            () => ({
                title: document.title,
                url: window.location.href,
                body: document.body.outerHTML
            })
        """)

    async def _execute_recovery_plan(self, recovery_plan: Dict[str, Any]):
        """Execute recovery actions"""
        actions = recovery_plan.get('actions', [])
        self.logger.info(f"Executing recovery plan with {len(actions)} actions")
        
        for action in actions:
            action_type = action.get('type')
            selector = action.get('selector', '')
            
            try:
                if action_type == 'click' and selector:
                    await self.page.click(selector)
                elif action_type == 'wait' and selector:
                    await self.page.wait_for_selector(selector, timeout=5000)
                elif action_type == 'navigate':
                    await self.page.goto(action.get('url', 'https://www.flipkart.com'))
                elif action_type == 'reload':
                    await self.page.reload()
                elif action_type == 'wait':
                    await asyncio.sleep(2)
                    
            except Exception as e:
                self.logger.warning(f"Recovery action failed: {str(e)}")

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