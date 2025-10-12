import asyncio
import json
import os
import urllib.parse
from typing import Dict, Optional, Any, List
from automation.core import FlipkartAutomation
import time

class UberSteps:
    def __init__(self, automation: FlipkartAutomation):
        self.automation = automation
        self.page = automation.page
        self.llm = automation.llm
        self.logger = automation.logger
        self.config = automation.config
        
        # User session data
        self.current_product = None
        self.shipping_info = None
        self.user_session_file = "user_session.json"
        self.user_data = self._load_user_session()
        self.search_url = None