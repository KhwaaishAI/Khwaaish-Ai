import asyncio
from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright
import os
from app.agents.ride_booking.config import Config
from app.agents.ride_booking.llm.assistant import LLMAssistant
from app.agents.ride_booking.utills.logger import setup_logger
from app.agents.ride_booking.uber.automation.steps import UberSteps


class UberAutomation:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger("uber-automation")
        self.llm = LLMAssistant(self.config, self.logger)

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

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

        user_data_dir = os.path.join(sessions_dir, f"uber_profile_{session_name}") if session_name else None
        is_existing_session = os.path.exists(user_data_dir) if user_data_dir else False

        self._update_status("running", "Initializing browser with persistent context.")

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

            # --- Pause for manual login ---
            print("\n" + "="*60)
            print("ACTION REQUIRED: Please complete the Uber login in the browser.")
            print("The script will wait until you are successfully logged in.")
            print("="*60 + "\n")

            # A reliable indicator of a successful login is the appearance of the
            # main ride booking interface where the pickup location is visible.
            # FIX: Scope the locator to the desktop container to avoid strict mode violation.
            desktop_container = self.page.locator('[data-testid="child-content-desktop"]')
            post_login_locator = desktop_container.locator('[aria-label="Pickup location needs to be filled in"]')
            
            self.logger.info("Waiting for user to complete login...")
            # Wait indefinitely for the post-login element to appear.
            await post_login_locator.wait_for(state="visible", timeout=0)
            self.logger.info("✅ Login confirmed. Main booking screen is visible. Resuming automation.")
            await asyncio.sleep(3) # Brief pause to let the page settle.
            

    async def search_rides(self, pickup_location: str, destination_location: str) -> List[Dict[str, Any]]:
        """Enters locations, searches for rides, and returns the extracted data."""
        self._update_status("running", "Entering ride details.")
        # await self.steps.click_ride_link_after_login()
        await asyncio.sleep(7)
        await self.steps.enter_pickup_location(pickup_location)
        await asyncio.sleep(5)
        await self.steps.enter_destination_location(destination_location)
        await asyncio.sleep(5)
        await self.steps.click_see_prices_button()
        
        # --- Intelligent Wait for Manual Verification ---
        self.logger.info("Checking for ride options or manual verification screen...")
        ride_options_locator = self.page.locator('li[data-testid="product_selector.list_item"]').first
        try:
            # Try to find the ride options with a short timeout.
            await ride_options_locator.wait_for(state="visible", timeout=10000)
            self.logger.info("Ride options detected. Proceeding to extraction.")
        except Exception:
            # If ride options are not found, pause for manual verification.
            self.logger.info("Ride options not found. Pausing for manual verification (e.g., CAPTCHA).")
            print("\n" + "="*60)
            print("ACTION REQUIRED: Please complete the verification in the browser.")
            print("The script will wait until the ride options appear.")
            print("="*60 + "\n")
            # Wait indefinitely for the ride options to appear after manual intervention.
            await ride_options_locator.wait_for(state="visible", timeout=0)
            self.logger.info("✅ Verification complete. Ride options are now visible. Resuming automation.")
        
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
        self.logger.info(f"Requesting ride: {ride_name}")
        # The click_request_ride_button method now returns True/False and handles its own exceptions.
        # We only need to call it and capture the boolean result.
        booking_successful = await self.steps.click_request_ride_button()

        if booking_successful:
            self._update_status("completed", f"Ride '{ride_name}' has been selected/requested.")
        else:
            self._update_status("running", f"Failed to request ride '{ride_name}'. It might be unavailable. Please select another ride.")
        return booking_successful

    async def stop(self):
        """Gracefully stops the automation and closes browser resources."""
        if self.status not in ["completed", "error"]:
            self._update_status("completed", "Job finished.")

        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
            self.logger.info("[Playwright stopped.")

        self.logger.info(f"✅  Automation finished.")
