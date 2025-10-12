import asyncio
from typing import Dict, Any, Callable
from playwright.async_api import async_playwright
from config import Config
from llm.assistant import LLMAssistant
from utills.logger import setup_logger

class UberAutomation:
    def __init__(self):
        self.config = Config()
        self.llm = LLMAssistant(self.config)
        self.logger = setup_logger()
        self.llm.set_logger(self.logger)
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
