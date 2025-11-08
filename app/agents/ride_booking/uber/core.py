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

        # --- Human-like Browser Configuration ---
        # Use a common User-Agent to blend in.
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

        launch_options = {
            "headless": self.config.HEADLESS,
            "slow_mo": self.config.SLOW_MO,
            "user_agent": user_agent,
            "locale": "en-IN", # Set locale to English (India)
            "timezone_id": "Asia/Kolkata", # Set timezone to India Standard Time
        }
        if hasattr(self.config, "PROXY") and self.config.PROXY:
            launch_options["proxy"] = {"server": self.config.PROXY}
            self.logger.info(f"Using proxy server: {self.config.PROXY}")

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **launch_options
        )

        # Use the first page of the context, or create one if none exists.
        # This is more robust than always creating a new page.
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        self.steps = UberSteps(self)

        if is_existing_session:
            # --- EXISTING SESSION WORKFLOW ---
            self._update_status("running", "Existing session found. Navigating directly to ride booking page.")
            ride_url = "https://www.uber.com/in/en/start-riding/?_csid=tf88Y3Gcr0V7cKx-kcgqdA&sm_flow_id=hrZAftti&state=AScUbrw05Y_2-pEFluwHm6ezQw1Pi8a-2ytrb_vUixw%3D"
            await self.page.goto(ride_url, wait_until="domcontentloaded")
            # Wait for the main content to be ready instead of a fixed sleep
            await self.page.locator('[data-testid="child-content-desktop"]').wait_for(state="visible", timeout=30000)

        # The initialize method is now only responsible for setting up the browser.
        # The API endpoints or main script will handle navigation and login steps.
        # If it's not an existing session, we just leave the browser ready.
        self._update_status("initialized", "Browser is ready. Awaiting instructions.")
        self.logger.info("Browser initialized successfully. The instance is ready.")
            

    async def search_rides(self, pickup_location: str, destination_location: str) -> List[Dict[str, Any]]:
        """Enters locations, searches for rides, and returns the extracted data."""
        self._update_status("running", "Entering ride details.")

        # await self.steps.click_ride_link_after_login()

        await self.steps.enter_pickup_location(pickup_location)
        # Wait for the destination input to be ready before proceeding
        # await self.page.locator('[aria-label="Destination"]').wait_for(state="visible", timeout=15000)
        await asyncio.sleep(3)
        await self.steps.enter_destination_location(destination_location)
        await asyncio.sleep(3)
        await self.steps.click_see_prices_button()
        # --- Intelligent Wait for Manual Verification ---
        self.logger.info("Checking for ride options or manual verification screen...")
        ride_options_locator = self.page.locator('li[data-testid="product_selector.list_item"]').first
        try:
            # Try to find the ride options with a short timeout.
            await ride_options_locator.wait_for(state="visible", timeout=10000)
            self.logger.info("Ride options detected. Proceeding to extraction.")
        except Exception:
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
        # Wait for the final confirmation button to become visible after selecting a ride
        await self.page.locator('button:has-text("Request")').last.wait_for(state="visible", timeout=20000)

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
