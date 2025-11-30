import uuid
from typing import Dict, Any
import asyncio

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.playwright_instance = None
        self._lock = asyncio.Lock()
    
    async def get_playwright(self):
        """Get or create playwright instance"""
        if self.playwright_instance is None:
            from playwright.async_api import async_playwright
            self.playwright_instance = await async_playwright().start()
        return self.playwright_instance
    
    def create_session(self, browser_data: Dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = browser_data
        return session_id
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self.sessions.get(session_id)
    
    def remove_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    async def cleanup(self):
        """Cleanup all sessions and playwright"""
        for session_id, session_data in list(self.sessions.items()):
            try:
                await session_data["browser"].close()
            except:
                pass
            self.remove_session(session_id)
        
        if self.playwright_instance:
            await self.playwright_instance.stop()
            self.playwright_instance = None

# Global session manager instance
session_manager = SessionManager()