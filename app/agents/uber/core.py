import asyncio
from typing import Dict, Any, Callable, Optional, List
from playwright.async_api import async_playwright
import os
from app.agents.uber.config import Config
import difflib
from app.agents.uber.llm.assistant import LLMAssistant
from app.agents.uber.utills.logger import setup_logger
from app.agents.uber.automation.steps import UberSteps


class UberAutomation:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.config = Config()
        self.logger = setup_logger()
        self.llm = LLMAssistant(self.config, self.logger)

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # --- State Management for API ---
        self.status: str = "initializing"
        self.message: Optional[str] = None
        self.ride_data: Optional[List[Dict[str, Any]]] = None
        self.user_choice_event: Optional[asyncio.Event] = None
        self.user_choice: Optional[int] = None

        # --- State for API-driven Login ---
        self.login_credential_event: Optional[asyncio.Event] = None
        self.login_credential: Optional[Dict[str, str]] = None
        self.otp_event: Optional[asyncio.Event] = None
        self.otp_code: Optional[str] = None
        self.session_name_to_save: Optional[str] = None

    def _update_status(self, status: str, message: Optional[str] = None):
        self.status = status
        self.message = message
        self.logger.info(f"[Job {self.job_id}] Status: {status} - Message: {message}")

    async def start(self, session_name: Optional[str], pickup_location: str, destination_location: str, preferred_ride_choice: str):
        """Initializes Playwright, launches the browser, and navigates to the initial page."""
        self._update_status("running", "Initializing browser.")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.config.HEADLESS,
            slow_mo=self.config.SLOW_MO
        )
        
        steps = UberSteps(self)
        sessions_dir = self.config.SESSIONS_DIR
        os.makedirs(sessions_dir, exist_ok=True) # Ensure the sessions directory exists
        
        saved_sessions = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]
        chosen_session_path = None

        if session_name:
            session_file = f"{session_name}.json"
            if session_file in saved_sessions:
                chosen_session_path = os.path.join(sessions_dir, session_file)
                self._update_status("running", f"Attempting to use session: '{session_name}'")
        
        if chosen_session_path:
            self._update_status("running", "Loading saved session state.")
            self.context = await self.browser.new_context(
                storage_state=chosen_session_path,
                **self.playwright.devices['Desktop Chrome'],
                locale='en-IN',
                timezone_id='Asia/Kolkata',
            )
            self.page = await self.context.new_page()
            self._update_status("running", "Browser initialized with saved session.")
            await self.page.goto("https://www.uber.com/in/en/start-riding/?_csid=tf88Y3Gcr0V7cKx-kcgqdA&sm_flow_id=hrZAftti&state=AScUbrw05Y_2-pEFluwHm6ezQw1Pi8a-2ytrb_vUixw%3D", wait_until="domcontentloaded")
            self._update_status("running", "Navigated to Uber. Verifying session.")
            await asyncio.sleep(3)

        else:
            self._update_status("running", "No session provided. Starting new login flow.")
            self.context = await self.browser.new_context(
                **self.playwright.devices['Desktop Chrome'],
                locale='en-IN',
                timezone_id='Asia/Kolkata',
            )
            self.page = await self.context.new_page()
            self._update_status("running", "Browser initialized for new login.")
            
            # --- Standard Login Flow ---
            await steps.navigate_to_uber()
            await steps.click_login_link()

            # Wait for credentials via API
            self._update_status("waiting_for_credentials", "Please provide login credentials via the API.")
            self.login_credential_event = asyncio.Event()
            await self.login_credential_event.wait()

            login_type = await steps.enter_login_credential()

            await steps.handle_post_credential_step()

            # Wait for OTP via API
            self._update_status("waiting_for_otp", "Please provide the 4-digit OTP via the API.")
            self.otp_event = asyncio.Event()
            await self.otp_event.wait()

            await steps.enter_otp_code(login_type)

            self.logger.info("Waiting for page to load after login...")
            await asyncio.sleep(5)

            # Save the new session state
            session_name = self.session_name_to_save or f"session_{int(asyncio.get_event_loop().time())}"
            session_file_path = os.path.join(sessions_dir, f"{session_name}.json")
            # Simple overwrite for now; can add conflict handling later if needed.
            await self.context.storage_state(path=session_file_path)
            self.logger.info(f"Login successful. Session state saved to '{os.path.basename(session_file_path)}'.")

            self._update_status("running", "Login successful. Proceeding to book ride.")


        # --- Common Steps to Book a Ride ---
        await asyncio.sleep(5)
        await steps.click_ride_link_after_login()
        await asyncio.sleep(2)
        await steps.enter_pickup_location(pickup_location)
        await asyncio.sleep(2)
        await steps.enter_destination_location(destination_location)
        await asyncio.sleep(2)
        await steps.click_see_prices_button()
        await asyncio.sleep(2)

        self._update_status("running", "Extracting ride options.")
        extracted_data = await steps.extract_uber_rides_to_json()
        self.ride_data = extracted_data if extracted_data else []

        if self.ride_data:
            # --- Enhanced Matching Logic ---
            # Find the best match for the preferred ride, allowing for typos.
            ride_names = [ride['name'] for ride in self.ride_data]
            best_matches = difflib.get_close_matches(preferred_ride_choice, ride_names, n=1, cutoff=0.6)

            matched_ride = None
            if best_matches:
                best_match_name = best_matches[0]
                # Find the full ride object from the matched name
                matched_ride = next((ride for ride in self.ride_data if ride['name'] == best_match_name), None)

            
            if matched_ride:
                self._update_status("running", f"Preferred ride '{preferred_ride_choice}' found. Automatically selecting.")
                await steps.select_ride_by_product_id(matched_ride['product_id'])
                self._update_status("completed", "Ride has been selected.")
            else:
                self._update_status("waiting_for_ride_choice", f"Preferred ride '{preferred_ride_choice}' not available. Please select from the available options.")
                
                self.user_choice_event = asyncio.Event()
                await self.user_choice_event.wait() # Pause execution until the /select-ride endpoint is called

                if self.user_choice is not None:
                    selected_ride = self.ride_data[self.user_choice]
                    self._update_status("running", f"User selected: {selected_ride['name']}. Proceeding.")
                    await steps.select_ride_by_product_id(selected_ride['product_id'])
                    self._update_status("completed", "Ride has been selected.")
                else:
                    self._update_status("error", "No ride was selected.")
        else:
            self._update_status("error", "Could not extract any ride data.")

    async def stop(self):
        """Gracefully stops the automation and closes browser resources."""
        if self.status not in ["completed", "error"]:
            self._update_status("completed", "Job finished.")

        if self.browser:
            await self.browser.close()
            self.logger.info(f"[Job {self.job_id}] Browser closed.")
        if self.playwright:
            await self.playwright.stop()
            self.logger.info(f"[Job {self.job_id}] Playwright stopped.")
        self.logger.info(f"✅ [Job {self.job_id}] Automation finished.")
