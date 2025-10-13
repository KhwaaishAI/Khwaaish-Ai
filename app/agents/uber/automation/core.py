import asyncio
from typing import Dict, Any, Callable
from playwright.async_api import async_playwright
import os
from config import Config
from llm.assistant import LLMAssistant
from utills.logger import setup_logger
from automation.steps import UberSteps


class UberAutomation:
    def __init__(self):
        self.config = Config()
        self.logger = setup_logger()
        self.llm = LLMAssistant(self.config, self.logger)

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        """Initializes Playwright, launches the browser, and navigates to the initial page."""
        self.logger.info("🚀 Starting Uber Automation...")
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

        if saved_sessions:
            self.logger.info("Found saved sessions.")
            use_saved = input("Do you want to use a previously saved session? (Y/N): ").strip().upper()
            if use_saved == 'Y':
                print("\nAvailable sessions:")
                for i, session_file in enumerate(saved_sessions):
                    session_name = os.path.splitext(session_file)[0]
                    print(f"  {i + 1}: {session_name}")
                
                while True:
                    try:
                        choice = int(input(f"\nEnter the number of the session to use (1-{len(saved_sessions)}): "))
                        if 1 <= choice <= len(saved_sessions):
                            chosen_session_file = saved_sessions[choice - 1]
                            chosen_session_path = os.path.join(sessions_dir, chosen_session_file)
                            self.logger.info(f"Selected session: {os.path.splitext(chosen_session_file)[0]}")
                            break
                        else:
                            print("Invalid number. Please try again.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
        
        if chosen_session_path:
            self.logger.info("Loading saved session state...")
            self.context = await self.browser.new_context(
                storage_state=chosen_session_path,
                **self.playwright.devices['Desktop Chrome'],
                locale='en-IN',
                timezone_id='Asia/Kolkata',
            )
            self.page = await self.context.new_page()
            self.logger.info("Browser initialized with saved session.")
            # Navigate to a page that requires login to verify the session is active
            await self.page.goto("https://www.uber.com/in/en/start-riding/?_csid=tf88Y3Gcr0V7cKx-kcgqdA&sm_flow_id=hrZAftti&state=AScUbrw05Y_2-pEFluwHm6ezQw1Pi8a-2ytrb_vUixw%3D", wait_until="domcontentloaded")
            self.logger.info("Navigated to the Uber booking page. You should be logged in.")
            # A short wait to allow the page to settle and for you to see the result
            await asyncio.sleep(5)

        else:
            self.logger.info("Starting a new login session.")
            self.context = await self.browser.new_context(
                **self.playwright.devices['Desktop Chrome'],
                locale='en-IN',
                timezone_id='Asia/Kolkata',
            )
            self.page = await self.context.new_page()
            self.logger.info("Browser initialized successfully for a new login.")
            
            # --- Standard Login Flow ---
            await steps.navigate_to_uber()
            await steps.click_login_link()
            login_type = await steps.enter_login_credential()

            if login_type == 'P':
                await steps.click_send_sms_code_button()
                await steps.enter_otp_code(login_type)
            elif login_type == 'E':
                # await steps.click_login_with_email_button()
                await steps.enter_otp_code(login_type)

            # Wait for the page to fully transition after login.
            self.logger.info("Waiting for 15 seconds for the page to load after login...")
            await asyncio.sleep(15)

            # After successful login, save the session state
            session_name_input = input("Login successful! Enter a name to save this session (e.g., 'personal' or 'work'): ").strip()
            if not session_name_input:
                session_name = f"session_{int(asyncio.get_event_loop().time())}"
                self.logger.warning(f"No session name provided. Saving as '{session_name}'.")
            else:
                session_name = session_name_input
            
            # Automatically handle name conflicts by appending a number
            base_session_name = session_name
            counter = 1
            session_file_path = os.path.join(sessions_dir, f"{session_name}.json")
            while os.path.exists(session_file_path):
                session_name = f"{base_session_name} ({counter})"
                session_file_path = os.path.join(sessions_dir, f"{session_name}.json")
                counter += 1
            
            await self.context.storage_state(path=session_file_path)
            self.logger.info(f"Session state saved to '{os.path.basename(session_file_path)}'.")

            # Proceed to booking page
            self.logger.info("Clicking the 'Ride' link after login.")
            await steps.click_ride_link_after_login()


        # --- Common Steps After Login ---
        await steps.click_ride_link_after_login()
        await steps.enter_pickup_location()
        
        # Enter the destination location provided by the user
        await steps.enter_destination_location()
        await asyncio.sleep(3)

        # Click the button to see ride options and prices
        await steps.click_see_prices_button()
        await asyncio.sleep(3)

        # Extract ride options data to a JSON file
        ride_data = await steps.extract_uber_rides_to_json()

        # If ride data was extracted, use LLM for analysis and let the user choose.
        if ride_data:
            if self.config.USE_LLM:
                analysis_result = await self.llm.analyze_ride_options(ride_data)
                if analysis_result:
                    self.logger.info("--- LLM Ride Analysis ---")
                    print(analysis_result)
                    self.logger.info("--------------------------\n")

            # Display ride options for user selection
            self.logger.info("Please select a ride from the options below:")
            for i, ride in enumerate(ride_data):
                print(f"  {i + 1}: {ride['name']} - {ride['price']} ({ride['eta_and_time']})")
            
            # Get user choice
            while True:
                try:
                    choice_input = input(f"\nEnter the number of the ride you want to select (1-{len(ride_data)}): ")
                    choice = int(choice_input)
                    if 1 <= choice <= len(ride_data):
                        selected_ride = ride_data[choice - 1]
                        self.logger.info(f"You selected: {selected_ride['name']}")
                        await steps.select_ride_by_product_id(selected_ride['product_id'])
                        break
                    else:
                        print(f"Invalid selection. Please enter a number between 1 and {len(ride_data)}.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        # The following steps are commented out as they were in the original file.
        # You can uncomment them to proceed with payment selection.
        # # After seeing prices, click to add a payment method
        # await steps.click_add_payment_method_button()
        # await asyncio.sleep(3)
        # # Select Cash as the payment method
        # await steps.select_cash_payment_method()
        # await asyncio.sleep(3)

        # # Click the final 'Confirm' button for the payment method
        # await steps.click_confirm_payment_button()

    async def stop(self):
        """Gracefully stops the automation and closes browser resources."""
        if self.browser:
            await self.browser.close()
            self.logger.info("Browser closed.")
        if self.playwright:
            await self.playwright.stop()
            self.logger.info("Playwright stopped.")
        self.logger.info("✅ Uber Automation finished.")
