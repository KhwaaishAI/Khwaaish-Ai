import asyncio
from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright
import os
from app.agents.ride_booking.config import Config
import shutil
import tempfile
import difflib
from app.agents.ride_booking.llm.assistant import LLMAssistant
from app.agents.ride_booking.utills.logger import setup_logger
from app.agents.ride_booking.uber.automation.steps import UberSteps


class UberAutomation:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger()
        self.llm = LLMAssistant(self.config, self.logger)

        self.playwright = None
        self.context = None
        self.page = None
        self.temp_user_data_dir = None # To hold the path of the temporary directory

        # --- State Management for API ---
        self.status: str = "initializing"
        self.message: Optional[str] = None
        self.ride_data: Optional[List[Dict[str, Any]]] = None

    def _update_status(self, status: str, message: Optional[str] = None):
        self.status = status
        self.message = message
        self.logger.info(f"[Status: {status} - Message: {message}")

    async def initialize(self, session_name: Optional[str]):
        """Initializes Playwright, launches the browser, and handles login if necessary."""
        sessions_dir = self.config.SESSIONS_DIR
        os.makedirs(sessions_dir, exist_ok=True)

        original_user_data_dir = os.path.join(sessions_dir, f"uber_profile_{session_name}") if session_name else None
        is_existing_session = os.path.exists(original_user_data_dir) if original_user_data_dir else False

        # --- Use a temporary copy of the session to avoid modifying the original ---
        if is_existing_session:
            # Create a temporary directory and copy the original profile into it.
            self.temp_user_data_dir = tempfile.mkdtemp()
            user_data_dir = os.path.join(self.temp_user_data_dir, f"uber_profile_{session_name}")
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
        self.steps = UberSteps(self)

        if is_existing_session:
            # --- EXISTING SESSION WORKFLOW ---
            self._update_status("running", "Existing session found. Navigating directly to ride booking page.")
            ride_url = "https://www.uber.com/in/en/start-riding/?_csid=tf88Y3Gcr0V7cKx-kcgqdA&sm_flow_id=hrZAftti&state=AScUbrw05Y_2-pEFluwHm6ezQw1Pi8a-2ytrb_vUixw%3D"
            await self.page.goto(ride_url, wait_until="domcontentloaded")
            await asyncio.sleep(5)


        if not is_existing_session:
            # --- NEW SESSION WORKFLOW ---
            self._update_status("running", "New or invalid session. Starting from the login page.")
            await self.steps.navigate_to_uber()
            await self.steps.click_login_link()
            await self.steps.enter_login_credential()
            await self.steps.handle_post_credential_step()
            await self.steps.enter_otp_code()
            

    async def search_rides(self, pickup_location: str, destination_location: str) -> List[Dict[str, Any]]:
        """Enters locations, searches for rides, and returns the extracted data."""
        self._update_status("running", "Entering ride details.")
        # await self.steps.click_ride_link_after_login()
        # await asyncio.sleep(5)
        await self.steps.enter_pickup_location(pickup_location)
        await asyncio.sleep(5)
        await self.steps.enter_destination_location(destination_location)
        await asyncio.sleep(5)
        await self.steps.click_see_prices_button()
        await asyncio.sleep(5)


        self._update_status("running", "Extracting ride options.")
        extracted_data = await self.steps.extract_uber_rides_to_json()
        self.ride_data = extracted_data if extracted_data else []
        return self.ride_data

    async def book_ride(self, ride_details: Dict[str, Any]):
        """Selects a specific ride from the list and clicks the final request button."""
        # The API passes the full ride object. We use it directly.
        if not ride_details or 'product_id' not in ride_details or 'name' not in ride_details:
            raise ValueError("Invalid ride details provided for booking.")

        product_id = ride_details['product_id']
        ride_name = ride_details['name']

        self._update_status("running", f"Selecting ride '{ride_name}' on the page.")
        await self.steps.select_ride_by_product_id(product_id)
        await asyncio.sleep(10)

        # The final booking step is commented out in steps.py, but if enabled, it would be called here.
        # self.logger.info(f"Requesting ride: {ride_name}")
        # await self.steps.click_request_ride_button()

        self._update_status("completed", f"Ride '{ride_name}' has been selected/requested.")

    async def stop(self):
        """Gracefully stops the automation and closes browser resources."""
        if self.status not in ["completed", "error"]:
            self._update_status("completed", "Job finished.")

        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
            self.logger.info("[Playwright stopped.")

        # --- Clean up the temporary session directory if it was used ---
        if self.temp_user_data_dir and os.path.exists(self.temp_user_data_dir):
            self.logger.info(f"Removing temporary session directory: {self.temp_user_data_dir}")
            shutil.rmtree(self.temp_user_data_dir)

        self.logger.info(f"✅  Automation finished.")
