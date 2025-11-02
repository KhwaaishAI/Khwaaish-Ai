import asyncio
from typing import Optional, List, Dict, Any
from playwright.async_api import async_playwright
import os

from app.agents.ride_booking.config import Config
from app.agents.ride_booking.llm.assistant import LLMAssistant
from app.agents.ride_booking.utills.logger import setup_logger

from app.agents.ride_booking.rapido.automation.steps import RapidoSteps


class RapidoAutomation:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger()
        self.llm = LLMAssistant(self.config, self.logger)

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        self.status: str = "initializing"
        self.message: Optional[str] = None
        self.ride_data: Optional[List[Dict[str, Any]]] = None

    def _update_status(self, status: str, message: Optional[str] = None):
        self.status = status
        self.message = message
        self.logger.info(f"Status: {status} - Message: {message}")

    async def initialize(self, session_name: Optional[str]):
        """Initializes Playwright, launches the browser, and handles login if necessary."""
        sessions_dir = self.config.SESSIONS_DIR
        os.makedirs(sessions_dir, exist_ok=True)
        user_data_dir = os.path.join(sessions_dir, f"rapido_profile_{session_name}") if session_name else None

        self._update_status("running", "Initializing browser for Rapido.")
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=self.config.HEADLESS,
            slow_mo=self.config.SLOW_MO,
            locale='en-IN',
            timezone_id='Asia/Kolkata',
        )
        self.page = await self.context.new_page()
        self.steps = RapidoSteps(self)
        await self.steps.navigate_to_rapido()

    async def search_rides(self, pickup_location: str, destination_location: str) -> List[Dict[str, Any]]:
        """Enters locations, searches for rides, and returns the extracted data."""
        self._update_status("running", "Entering ride details for Rapido.")
        await self.steps.enter_pickup_location(pickup_location)
        await self.steps.enter_destination_location(destination_location)
        await self.steps.click_search_button()
        await asyncio.sleep(5)


        # After attempting to search, check if a login is required.
        await self.steps.check_and_handle_login()
        await asyncio.sleep(5)

        # After login, a new location prompt appears. We re-enter the pickup location.
        self.logger.info("Handling post-login location entry.")
        await self.steps.enter_location_after_login(pickup_location)
        await asyncio.sleep(3)
        await self.steps.enter_drop_location_after_login(destination_location)
        await asyncio.sleep(4)
        


        self.ride_data = await self.steps.extract_rides()
        return self.ride_data

    async def book_ride(self, ride_details: Dict[str, Any]):
        """Selects a specific ride from the list and clicks the final book button."""
        if not ride_details or 'name' not in ride_details:
            raise ValueError("Invalid ride details provided for booking.")

        ride_name = ride_details['name']
        self._update_status("running", f"Selecting ride '{ride_name}' on Rapido.")

        # You'll need a way to identify the ride to click, e.g., by name or a unique ID.
        await self.steps.select_ride(ride_details)
        # await self.steps.click_confirm_booking_button(ride_details)

        self._update_status("completed", f"Ride '{ride_name}' has been booked on Rapido.")

    async def stop(self):
        """Gracefully stops the automation and closes browser resources."""
        if self.status not in ["completed", "error"]:
            self._update_status("completed", "Job finished.")

        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        self.logger.info("✅ Rapido automation finished.")
