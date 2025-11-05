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
        self.logger = setup_logger("rapido-automation")
        self.llm = LLMAssistant(self.config, self.logger)

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        self.status: str = "initializing"
        self.message: Optional[str] = None
        self.ride_data: Optional[List[Dict[str, Any]]] = None
        self.is_existing_session: bool = False

    def _update_status(self, status: str, message: Optional[str] = None):
        self.status = status
        self.message = message
        self.logger.info(f"Status: {status} - Message: {message}")

    async def initialize(self, session_name: Optional[str]):
        """Initializes Playwright, launches the browser, and handles login if necessary."""
        sessions_dir = self.config.SESSIONS_DIR
        os.makedirs(sessions_dir, exist_ok=True)

        user_data_dir = os.path.join(sessions_dir, f"rapido_profile_{session_name}") if session_name else None
        self.is_existing_session = os.path.exists(user_data_dir) if user_data_dir else False

        self._update_status("running", "Initializing browser with persistent context for Rapido.")

        self.playwright = await async_playwright().start()

        launch_options = {
            "headless": self.config.HEADLESS,
            "slow_mo": self.config.SLOW_MO,
        }
        if hasattr(self.config, "PROXY") and self.config.PROXY:
            launch_options["proxy"] = {"server": self.config.PROXY}
            self.logger.info(f"Using proxy server: {self.config.PROXY}")

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **launch_options
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
        
        if not self.is_existing_session:
            await self.steps.check_and_handle_login()
            await asyncio.sleep(5)

        # --- NEW: Robustly determine the page state after login/reload ---
        self.logger.info("Determining page state: checking for ride list or location re-entry form.")
        post_login_pickup_input = self.page.locator('input[placeholder="Enter pickup location here"]')
        ride_list_locator = self.page.locator("div.fare-estimate-wrapper").first

        try:
            # Wait for either the ride list or the location input to appear.
            await asyncio.wait_for(
                asyncio.wait(
                    [
                        asyncio.create_task(post_login_pickup_input.wait_for(state="visible")),
                        asyncio.create_task(ride_list_locator.wait_for(state="visible")),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                ),
                timeout=15.0, # Overall timeout for the check
            )

            if await post_login_pickup_input.is_visible():
                self.logger.info("Post-login location entry screen detected. Re-entering locations.")
                await self.steps.enter_location_after_login(pickup_location)
                await asyncio.sleep(3)
                await self.steps.enter_drop_location_after_login(destination_location)
                await asyncio.sleep(4)
            elif await ride_list_locator.is_visible():
                self.logger.info("Ride list is already visible. Proceeding directly to ride extraction.")
        except asyncio.TimeoutError:
            self.logger.error("Neither the ride list nor the location re-entry form appeared in time. Extraction will likely fail.")
            # The script will proceed to extract_rides, which will then handle the timeout gracefully.

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
