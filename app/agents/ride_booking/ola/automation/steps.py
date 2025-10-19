import asyncio
from typing import TYPE_CHECKING, List, Dict, Any
 
if TYPE_CHECKING:
    # This will point to the OlaAutomation class you will create in core.py
    from app.agents.ride_booking.ola.core import OlaAutomation

class OlaSteps:
    def __init__(self, automation: "OlaAutomation"):
        self.automation = automation
        self.llm = automation.llm
        self.logger = automation.logger
        self.config = automation.config

    async def navigate_to_ola_Cabs(self):
        """Navigates to the Ola Cabs"""
        url = "https://www.olacabs.com/"
        self.logger.info(f"Navigating to Ola Cabs: {url}")
        await self.automation.page.goto(url, wait_until="domcontentloaded", timeout=self.config.TIMEOUT)
        self.logger.info("Successfully navigated to the Ola Corporate login page.")


    async def enter_pickup_location(self, pickup_location: str):
        """Clicks and types the pickup location into the input field."""
        self.logger.info(f"Attempting to enter pickup location: '{pickup_location}'")
        try:
            # This selector specifically targets the pickup location input field.
            current_location_input = self.automation.page.locator("div.current_location input#textbox1")

            self.logger.info("Clicking the 'Current Location' input field to activate it.")
            await current_location_input.click(timeout=self.config.TIMEOUT)
            await asyncio.sleep(2)

            self.logger.info(f"Typing '{pickup_location}' into the input field.")
            await current_location_input.fill(pickup_location)
            self.logger.info("Successfully typed the pickup location. Waiting for suggestions...")
            await asyncio.sleep(5) 

            first_suggestion_locator = self.automation.page.locator("ul#search_location_list li.item").first
            
            self.logger.info("Waiting for the first location suggestion to be visible.")
            await first_suggestion_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await first_suggestion_locator.click()
            self.logger.info("Successfully clicked the first pickup location suggestion.")
        except Exception as e:
            self.logger.error(f"Failed to enter pickup location: {e}", exc_info=True)
            raise

    async def enter_destination_location(self, destination_location: str):
        """Clicks and types the destination location into the input field."""
        self.logger.info(f"Attempting to enter destination location: '{destination_location}'")
        try:
            # This selector specifically targets the destination input field.
            destination_input = self.automation.page.locator("div.enter_destination input#destination_location")

            self.logger.info("Clicking the 'Enter location' (destination) input field to activate it.")
            await destination_input.click(timeout=self.config.TIMEOUT)

            self.logger.info(f"Typing '{destination_location}' into the input field.")
            await destination_input.fill(destination_location)
            self.logger.info("Successfully typed the destination location. Waiting for suggestions...")
            await asyncio.sleep(2) # Wait for suggestions to populate

            # --- Click the first suggestion ---
            # Based on the HTML, we target the first item inside the destination suggestion list.
            first_suggestion_locator = self.automation.page.locator("ul#destination_location_list li.item").first
            
            self.logger.info("Waiting for the first destination suggestion to be visible.")
            await first_suggestion_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await first_suggestion_locator.click()
            self.logger.info("Successfully clicked the first destination location suggestion.")
        except Exception as e:
            self.logger.error(f"Failed to enter destination location: {e}", exc_info=True)
            raise

    async def click_search_cabs_button(self):
        """Clicks the 'SEARCH OLA CABS' button and handles the new tab that opens."""
        self.logger.info("Looking for the 'SEARCH OLA CABS' button.")
        try:
            async with self.automation.context.expect_page() as new_page_info:
                self.logger.info("Preparing to click search and catch the new tab.")
                search_button_locator = self.automation.page.locator(
                    'button.search_btn[event-name="desktop_booking_widget_daily_search"]'
                )
                await search_button_locator.click()
                self.logger.info("Successfully clicked the 'SEARCH OLA CABS' button.")

            new_page = await new_page_info.value
            self.logger.info(f"New tab opened with URL: {new_page.url}. Switching context to the new tab.")
            
            # Wait for the new page to finish loading its content.
            await new_page.wait_for_load_state("domcontentloaded")

            # Close the original, now obsolete page.
            await self.automation.page.close()
            
            # IMPORTANT: Update the automation's page reference to the new page.
            self.automation.page = new_page
            self.logger.info("Automation context successfully switched to the new page.")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'SEARCH OLA CABS' button: {e}", exc_info=True)
            raise

    async def check_and_perform_login(self) -> bool:
        """
        Checks if a login is required on the current page and performs it if so.
        Returns True if login was performed, False otherwise.
        """
        self.logger.info("Checking if login is required...")
        login_button_locator = self.automation.page.locator('header#header span#login:has-text("LOG IN")')
        
        try:
            # Use a short timeout to quickly check for the button's existence.
            await login_button_locator.wait_for(state="visible", timeout=5000)
        except Exception: # This specifically catches the timeout if the button is not found.
            # If the button is not found within the timeout, we assume the user is already logged in.
            self.logger.info("Login button not found. Assuming user is already logged in.")
            return False

        # If the button was found, we proceed with the login flow outside the initial try...except.
        self.logger.info("Login button found. Proceeding with login flow.")
        phone_number = input("Please enter your 10-digit phone number for login: ")
        await self.click_login_button()
        await self.enter_phone_number(phone_number)
        return True


    async def click_login_button(self):
        """Clicks the 'LOG IN' button in the header and waits for the page to navigate."""
        self.logger.info("Looking for the 'LOG IN' button in the header.")
        try:
            # This selector is specific, looking for the span with id 'login' inside the header.
            # The click navigates on the same page to a login URL.
            login_button_locator = self.automation.page.locator('header#header span#login:has-text("LOG IN")')
            await login_button_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await login_button_locator.click()
            self.logger.info("Successfully clicked the 'LOG IN' button.")

            # Wait for the URL to change to the login deeplink on the same page.
            self.logger.info("Waiting for navigation to the login page...")
            await self.automation.page.wait_for_url("**/login**", timeout=self.config.TIMEOUT)
            await self.automation.page.wait_for_load_state("domcontentloaded")
            
            self.logger.info(f"Successfully navigated to the login page: {self.automation.page.url}")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'LOG IN' button: {e}", exc_info=True)
            raise

    async def enter_phone_number(self, phone_number: str):
        """Finds the phone number input field inside the login iframe and enters the number."""
        self.logger.info("Attempting to enter phone number.")
        try:
            self.logger.info("Waiting for the iframe container to be visible.")
            await self.automation.page.locator('div.iframe-container').wait_for(state="visible", timeout=15000)
            
            # Based on the provided HTML, the iframe has a specific ID 'ssoiframe'.
            self.logger.info("Locating the iframe with ID 'ssoiframe'.")
            login_frame_locator = self.automation.page.frame_locator('iframe#ssoIframe')

            # Now, locate the input field *within* the context of the iframe.
            phone_input_locator = login_frame_locator.locator('div.sso__phone__wrapper input#phone-number')
            self.logger.info("Waiting for the phone number input field to be visible inside the iframe.")
            await phone_input_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await phone_input_locator.fill(phone_number)
            self.logger.info("Successfully entered the phone number.")

            await asyncio.sleep(2)
            await login_frame_locator.locator('div.sso__cta:has-text("Next")').click()
            self.logger.info("Clicked 'Next' button. Waiting for OTP screen.")
            await asyncio.sleep(2)

            # --- New: Handle OTP Entry ---
            self.logger.info("Waiting for OTP input field to appear.")
            otp_input_locator = login_frame_locator.locator('div.sso__new-user__otp-wrapper input#otp')
            await otp_input_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
            
            otp_code = input("Please enter the 4-digit OTP you received: ")
            await otp_input_locator.fill(otp_code)
            self.logger.info("Successfully entered the OTP.")

            # --- Click the final 'Log In' button ---
            await asyncio.sleep(3) # Wait for 3 seconds as requested.
            self.logger.info("Looking for the 'Log In' button to complete sign-in.")
            await login_frame_locator.locator('div.sso__cta:has-text("Log In")').click()
            self.logger.info("Successfully clicked the 'Log In' button.")

            # --- CRUCIAL STEP: Wait for login confirmation ---
            # After clicking 'Log In', the iframe closes and the main page reloads.
            # We must wait for an element that confirms we are truly logged in before proceeding.
            # The user profile icon is a reliable indicator.
            self.logger.info("Waiting for login to complete and profile icon to appear...")
            await self.automation.page.locator('header#header div#icon').wait_for(state="visible", timeout=self.config.TIMEOUT)
            self.logger.info("✅ Login confirmed. Profile icon is visible.")
        except Exception as e:
            self.logger.error(f"Failed to enter phone number: {e}", exc_info=True)
            raise

    async def extract_rides(self) -> List[Dict[str, Any]]:
        """
        Extracts ride details from the Shadow DOM and returns them as a list of dictionaries.
        """
        self.logger.info("Attempting to extract ride options...")
        try:
            # The ride options are inside a shadow-root of the <ola-cabs> component.
            # Playwright can pierce the shadow DOM automatically with its locators.
            ride_rows_locator = self.automation.page.locator("ola-cabs div.row.cab-row")

            # Wait for the first ride option to become visible.
            await ride_rows_locator.first.wait_for(state="visible", timeout=self.config.TIMEOUT)
            self.logger.info("Ride options are visible. Starting extraction.")

            extracted_rides = []
            all_ride_rows = await ride_rows_locator.all()

            for ride_row in all_ride_rows:
                # The name and price are inside the same parent div.
                cab_name_locator = ride_row.locator("div.cab-name")
                price_locator = cab_name_locator.locator("span.price")

                # --- Robustness Check ---
                # Check if both the name and price elements exist before trying to extract text.
                # This prevents timeouts on rows that are not actual ride options.
                if await cab_name_locator.count() > 0 and await price_locator.count() > 0:
                    # Extract the full text and the price text separately.
                    full_text = await cab_name_locator.inner_text()
                    price_text = await price_locator.inner_text()

                    # The ride name is the full text with the price part removed.
                    ride_name = full_text.replace(price_text, "").strip()
                    
                    if ride_name and price_text:
                        extracted_rides.append({
                            "name": ride_name, 
                            "price": price_text.strip(),
                            "locator": ride_row
                        })

            if not extracted_rides:
                self.logger.warning("No ride options were extracted. The page structure might have changed.")
                return []

            self.logger.info(f"Successfully extracted {len(extracted_rides)} ride options.")
            return extracted_rides

        except Exception as e:
            self.logger.error(f"Failed to extract or select rides: {e}", exc_info=True)
            raise
