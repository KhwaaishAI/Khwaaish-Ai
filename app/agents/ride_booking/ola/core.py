import asyncio
from typing import Optional, List, Dict, Any
from playwright.async_api import async_playwright
import os
import shutil
import tempfile

from app.agents.ride_booking.config import Config
from app.agents.ride_booking.llm.assistant import LLMAssistant 
from app.agents.ride_booking.utills.logger import setup_logger 

from app.agents.ride_booking.ola.automation.steps import OlaSteps


class OlaAutomation:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger()
        self.llm = LLMAssistant(self.config, self.logger)

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.temp_user_data_dir = None # To hold the path of the temporary directory

        self.status: str = "initializing"
        self.message: Optional[str] = None

    def _update_status(self, status: str, message: Optional[str] = None):
        self.status = status
        self.message = message
        self.logger.info(f"Status: {status} - Message: {message}")

    async def initialize(self, session_name: Optional[str]):
        """Initializes Playwright, launches the browser, and handles login if necessary."""
        sessions_dir = self.config.SESSIONS_DIR
        os.makedirs(sessions_dir, exist_ok=True)
        
        original_user_data_dir = os.path.join(sessions_dir, f"ola_profile_{session_name}") if session_name else None
        is_existing_session = os.path.exists(original_user_data_dir) if original_user_data_dir else False

        # --- Use a temporary copy of the session to avoid modifying the original ---
        if is_existing_session:
            # Create a temporary directory and copy the original profile into it.
            self.temp_user_data_dir = tempfile.mkdtemp()
            user_data_dir = os.path.join(self.temp_user_data_dir, f"ola_profile_{session_name}")
            self.logger.info(f"Copying existing session '{original_user_data_dir}' to temporary location '{user_data_dir}' for this run.")
            shutil.copytree(original_user_data_dir, user_data_dir)
        else:
            # If no session exists, we will create it in the original directory.
            user_data_dir = original_user_data_dir

        self._update_status("running", "Initializing browser with persistent context.")
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=self.config.HEADLESS,
            slow_mo=self.config.SLOW_MO,
            locale='en-IN',
            timezone_id='Asia/Kolkata',
        )
        self.page = await self.context.new_page()
        self.steps = OlaSteps(self)
        await self.steps.navigate_to_ola_Cabs()
        await asyncio.sleep(5)

    async def search_rides(self, pickup_location: str, destination_location: str) -> List[Dict[str, Any]]:
        """Enters locations, searches for rides, and returns the extracted data."""
        await self.steps.enter_pickup_location(pickup_location)
        await asyncio.sleep(5)
        await self.steps.enter_destination_location(destination_location)
        await asyncio.sleep(5)
        await self.steps.click_search_cabs_button()

        # --- CRITICAL FIX: Wait for the first ride option to be visible ---
        # Instead of a fixed sleep, we wait for the content to actually load.
        self.logger.info("Waiting for ride options to load on the new page...")
        first_ride_locator = self.page.locator("ola-cabs div.row.cab-row").first
        await first_ride_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)

        # On the booking page, check if login is needed.
        await self.steps.check_and_perform_login()

        # --- Extract ride data ---
        self.ride_data = await self.steps.extract_rides()
        return self.ride_data

    async def book_ride(self, ride_details: Dict[str, Any]):
        """Selects a specific ride from the list and clicks the final book button."""
        if not ride_details or 'locator' not in ride_details:
            raise ValueError("Invalid ride details provided for booking. The 'locator' is missing.")

        ride_name = ride_details['name']
        self._update_status("running", f"Selecting ride '{ride_name}' on the page.")

        # The API now passes the full ride object, including the locator. We use it directly.
        ride_to_book = ride_details

        await ride_to_book['locator'].click()
        self.logger.info(f"Successfully clicked the ride option for '{ride_name}'.")
        await asyncio.sleep(10)

        # # Click the final 'Confirm and Book' button
        # self.logger.info("Looking for the 'Confirm and Book' button.")
        # book_button_locator = self.page.locator('div.footer button.nxt-btn-active')
        # await book_button_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
        # await book_button_locator.click()
        # self.logger.info("✅ Successfully clicked the 'Confirm and Book' button. Ride should be booked.")
        # self._update_status("completed", f"Ride '{ride_name}' has been booked.")

    async def stop(self):
        """Gracefully stops the automation and closes browser resources."""
        if self.status not in ["completed", "error"]:
            self._update_status("completed", "Job finished.")

        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

        # --- Clean up the temporary session directory if it was used ---
        if self.temp_user_data_dir and os.path.exists(self.temp_user_data_dir):
            self.logger.info(f"Removing temporary session directory: {self.temp_user_data_dir}")
            shutil.rmtree(self.temp_user_data_dir)

        self.logger.info(f"✅ Ola automation finished.")
