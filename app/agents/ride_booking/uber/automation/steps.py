import asyncio
import json
import os
import urllib.parse
import re
from datetime import datetime
from typing import Dict, Optional, Any, List, TYPE_CHECKING
import time
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

if TYPE_CHECKING:
    from app.agents.ride_booking.uber.core import UberAutomation

class UberSteps:
    def __init__(self, automation: "UberAutomation"):
        self.automation = automation
        self.llm = automation.llm
        self.logger = automation.logger
        self.config = automation.config
        
        # Session data for Uber
        self.pickup_location: Optional[str] = None
        self.destination_location: Optional[str] = None

    async def navigate_to_uber(self):
        """Navigates to the Uber sign-in/booking page."""
        url = "https://www.uber.com/global/en/sign-in/"
        self.logger.info(f"Navigating to Uber: {url}")
        await self.automation.page.goto(url, wait_until="domcontentloaded", timeout=self.config.TIMEOUT)
        self.logger.info("Successfully navigated to the Uber page.")

    async def click_login_link(self):
        """Finds and clicks the main 'Log in' link on the sign-in page."""
        self.logger.info("Looking for the 'Log in' link.")
        try:
            # Using get_by_role is a robust way to find the link by its accessible name.
            await self.automation.page.get_by_role("link", name="Log in").click(timeout=self.config.TIMEOUT)
            self.logger.info("Successfully clicked the 'Log in' link.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'Log in' link: {e}")
            raise

    async def enter_login_credential(self):
        """Prompts the user for their phone number or email, enters it, and proceeds."""
        credential = input("Please enter your phone number or email for Uber login: ")
        self.logger.info(f"Entering login credential received from terminal.")
        try:
            # Locate the input field by its placeholder text
            login_input_selector = "input[placeholder='Enter phone number or email']"
            await self.automation.page.wait_for_selector(login_input_selector, timeout=self.config.TIMEOUT)
            await self.automation.page.fill(login_input_selector, credential)
            self.logger.info(f"Successfully entered the credential.")

            # Click the 'Next' or 'Continue' button to proceed
            # The error log showed multiple "Continue" buttons. Using the specific
            # data-testid is the most robust way to select the correct one.
            await self.automation.page.get_by_test_id("forward-button").click()
            self.logger.info("Clicked the 'Continue' (forward) button.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Failed to enter login credential or click next: {e}")
            raise

    async def click_send_sms_code_button(self):
        """On the 'Welcome back' screen for phone logins, clicks the 'Send code via SMS' button."""
        self.logger.info("Looking for 'Send code via SMS' button on the welcome back screen.")
        try:
            # Wait for the welcome text to ensure we are on the right page
            await self.automation.page.wait_for_selector("text=/Welcome back/", timeout=self.config.TIMEOUT)
            self.logger.info("'Welcome back' screen detected.")

            await self.automation.page.get_by_role("button", name="Send code via SMS").click(timeout=self.config.TIMEOUT)
            self.logger.info("Successfully clicked 'Send code via SMS' button.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click 'Send code via SMS' button: {e}")
            raise

    async def click_login_with_email_button(self):
        """On the password prompt screen for email logins, clicks the 'login with email' button to get an OTP."""
        self.logger.info("Looking for 'login with email' button to get an OTP instead of using a password.")
        try:
            # After entering an email, Uber may ask for a password. We are opting for an OTP flow.
            # We will use a robust accessibility selector (role + name) and explicitly wait for it to
            # become visible, which handles delays in client-side rendering.
            login_button_selector = self.automation.page.get_by_role("button", name="Login with email")
            
            self.logger.info("Waiting for the 'Login with email' button to be visible...")
            await login_button_selector.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await login_button_selector.click()
            self.logger.info("Successfully clicked 'login with email' button.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click 'login with email' button: {e}")
            raise

    async def handle_post_credential_step(self):
        """
        After entering a credential, this function intelligently determines the next step.
        If a password screen appears, it clicks 'Login with email' to switch to the OTP flow.
        It ensures the browser is on the OTP entry screen before proceeding.
        """
        self.logger.info("Determining next step after credential entry...")
        try:
            otp_prompt_locator = self.automation.page.locator("text=/Enter the 4-digit code sent to/")
            login_with_email_button = self.automation.page.locator('button[data-testid="Login with email"][data-baseweb="button"]')

            # Wait for either the OTP prompt or the "Login with email" button to appear.
            await asyncio.wait([
                otp_prompt_locator.wait_for(state="visible", timeout=self.config.TIMEOUT),
                login_with_email_button.wait_for(state="visible", timeout=self.config.TIMEOUT)
            ], return_when=asyncio.FIRST_COMPLETED)

            # If the "Login with email" button is visible, it means we're on the password screen.
            if await login_with_email_button.is_visible():
                self.logger.info("Password screen detected. Clicking 'Login with email' to switch to OTP flow.")
                await login_with_email_button.click()
                # After clicking, we must wait for the actual OTP screen to appear.
                await otp_prompt_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
                self.logger.info("Switched to OTP flow successfully. OTP screen is now visible.")
            else:
                self.logger.info("OTP screen detected directly. Ready for OTP input.")
        except Exception as e:
            self.logger.error(f"Failed to handle post-credential step: {e}")
            raise

    async def enter_otp_code(self):
        """Waits for the OTP screen, prompts user for the 4-digit code, and enters it."""
        self.logger.info("Waiting for OTP to be provided via terminal...")
        try:
            otp_code = input("Please enter the 4-digit OTP you received: ")
            self.logger.info("Entering OTP received from terminal.")
            
            # The OTP fields are often separate inputs. We will fill them one by one.
            # The selector targets the inputs within the pin-code container.
            otp_inputs = await self.automation.page.locator('[data-baseweb="pin-code"] input').all()
            if len(otp_inputs) == 4:
                self.logger.info(f"Entering OTP: {otp_code}")
                for i, digit in enumerate(otp_code):
                    await otp_inputs[i].fill(digit)
                self.logger.info("Successfully entered the 4-digit OTP.")
            else:
                raise Exception(f"Expected 4 OTP input fields, but found {len(otp_inputs)}.")
        except Exception as e:
            self.logger.error(f"Failed to enter OTP code: {e}", exc_info=True)
            raise

    async def click_ride_link_after_login(self):
        """After successful login/OTP, clicks the 'Ride' link to go to the booking page."""
        self.logger.info("Looking for the 'Ride' link to proceed to booking.")
        try:
            # The aria-label is specific and a robust selector.
            # The correct method is get_by_role with the name matching the aria-label.
            # The visible text is "Ride", so we use that as the accessible name.
            ride_link_selector = self.automation.page.get_by_role("link", name="Ride", exact=True)
            await ride_link_selector.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await ride_link_selector.click()
            self.logger.info("Successfully clicked the 'Ride' link.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'Ride' link after login: {e}")
            raise

    async def enter_pickup_location(self, pickup_location: str):
        """Enters the provided pickup location into the input field."""
        self.logger.info("Looking for the 'Enter location' input field.")
        try:
            # Target the desktop form container first, then the input within it
            # 1. Define the parent container selector
            desktop_container_selector = '[data-testid="ddfd0771-ab61-4492-ae50-294a530a8923-desktop"]'

            # 2. Define the pickup input selector (note the space for descendant)
            pickup_input_selector = '[data-testid="dotcom-ui.pickup-destination.input.pickup"]'

            # 3. Combine them and add the :visible filter
            pickup_input = self.automation.page.locator(f'{desktop_container_selector} {pickup_input_selector}:visible')

            # 4. Await the action
            await pickup_input.click()
            self.logger.info("Pickup location input field is now active.")
            await asyncio.sleep(2)
            
            self.logger.info(f"Entering pickup location: '{pickup_location}'")
            await pickup_input.fill(pickup_location)
            await asyncio.sleep(3)
            self.logger.info("Successfully entered pickup location.")
            
            # Assuming 'page' is your Playwright Page object

            # --- Locator for the first suggestion ---
            # This targets the first list item with role="option" inside the listbox element.
            first_suggestion_locator = self.automation.page.locator('div[aria-label="pickup location dropdown"] li[role="option"]').first

            # --- Action to Wait and Click ---
            try:
                print("Waiting for the first address suggestion to become visible...")
                
                # Explicitly wait for the element to be visible with a generous timeout (e.g., 20 seconds)
                await first_suggestion_locator.wait_for(state="visible", timeout=20000)
                
                # Click the element
                await first_suggestion_locator.click()
                
                print("Successfully clicked the first address suggestion.")

            except TimeoutError:
                # This will catch the error if the element never becomes visible
                print("ERROR: Timed out waiting for the first address suggestion to appear and become visible.")
                # You can add a screenshot here for debugging: page.screenshot(path="timeout_error.png")

            except Exception as e:
                print(f"An unexpected error occurred during the click: {e}")
            self.logger.info("Clicked the first address suggestion to confirm pickup location.")
            
        except Exception as e:
            self.logger.error(f"Failed to enter pickup location: {e}")
            raise

    async def enter_destination_location(self, destination_location: str):
        """Enters the provided destination location into the input field."""
        self.logger.info("Looking for the 'Enter destination' input field.")
        try:
            # The destination input is usually visible after a pickup is selected.
            destination_input_selector = '[data-testid="dotcom-ui.pickup-destination.input.destination"]'
            destination_input = self.automation.page.locator(f'{destination_input_selector}:visible')

            # Wait for the input to be ready and click it.
            await destination_input.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await destination_input.click()
            self.logger.info("Destination input field is now active.")

            self.logger.info(f"Entering destination location: '{destination_location}'")
            await destination_input.fill(destination_location)
            await asyncio.sleep(5)
            self.logger.info("Successfully entered destination location.")

            # --- Wait for and click the first suggestion ---
            self.logger.info("Waiting for destination address suggestions to appear...")
            # The destination dropdown has a different aria-label
            first_suggestion_locator = self.automation.page.locator('div[aria-label="destination location dropdown"] li[role="option"]').first

            await first_suggestion_locator.wait_for(state="visible", timeout=20000)
            await first_suggestion_locator.click()
            self.logger.info("Clicked the first address suggestion to confirm destination location.")

        except Exception as e:
            self.logger.error(f"Failed to enter destination location: {e}")
            raise

    async def click_see_prices_button(self):
        """Clicks the 'See prices' button after pickup and destination are set."""
        self.logger.info("Looking for the 'See prices' button.")
        try:
            # The error log shows two "See prices" links. We must scope our search to the main
            # booking form to ensure we click the correct one.
            desktop_container_selector = '[data-testid="ddfd0771-ab61-4492-ae50-294a530a8923-desktop"]'
            see_prices_button = self.automation.page.locator(desktop_container_selector).get_by_role(
                "link", name="See prices"
            )
            
            await see_prices_button.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await see_prices_button.click()
            self.logger.info("Successfully clicked the 'See prices' button.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'See prices' button: {e}")
            raise

    async def click_add_payment_method_button(self):
        """Clicks the 'Add Payment Method' button that appears after viewing prices."""
        self.logger.info("Looking for the 'Add Payment Method' button.")
        try:
            # Based on the HTML, the clickable element is a div with `data-baseweb="block"`
            # that contains the text. This selector is more specific than text alone.
            add_payment_button = self.automation.page.locator(
                'div[data-baseweb="block"]:has-text("Add Payment Method")')
            
            await add_payment_button.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await add_payment_button.click()
            self.logger.info("Successfully clicked the 'Add Payment Method' button.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'Add Payment Method' button: {e}")
            # This step might fail if a payment method is already configured. For now, we treat it as an error.
            raise

    async def select_cash_payment_method(self):
        """Selects 'Cash' as the payment option from the list of payment methods."""
        self.logger.info("Looking for the 'Cash' payment option.")
        try:
            # The 'data-testid' provided is the most reliable selector for this element.
            cash_option_button = self.automation.page.get_by_test_id("add.pm-link.cash")
            
            await cash_option_button.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await cash_option_button.click()
            self.logger.info("Successfully selected 'Cash' as the payment method.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'Cash' payment option: {e}")
            raise

    async def click_confirm_payment_button(self):
        """Clicks the final 'Confirm' button after selecting a payment method."""
        self.logger.info("Looking for the final 'Confirm' button for payment.")
        try:
            # To be more specific, we target a button that has both the `data-baseweb="button"`
            # attribute and the accessible name "Confirm".
            confirm_button = self.automation.page.locator(
                'button[data-baseweb="button"]:has-text("Confirm")')
            
            await confirm_button.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await confirm_button.click()
            self.logger.info("Successfully clicked the 'Confirm' button for payment.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            self.logger.error(f"Could not find or click the 'Confirm' payment button: {e}")
            raise

    async def extract_uber_rides_to_json(self):
        """
        Extracts ride details (Name, Price, ETA, Product ID) from the Uber product selection list
        and saves them to a timestamped file with location context. Returns the current ride options.
        """
        page = self.automation.page
        
        # Stable Locator for all ride list items
        ride_options_locator = page.locator('li[data-testid="product_selector.list_item"]')
        
        self.logger.info("Waiting for ride options to load...")
        try:
            # Wait for at least the first ride option to be visible
            await ride_options_locator.first.wait_for(state="visible", timeout=30000)
        except PlaywrightTimeoutError:
            self.logger.error("Timed out waiting for ride options to appear on the screen.")
            return []

        ride_data = []
        count = await ride_options_locator.count()
        self.logger.info(f"Found {count} ride options. Extracting data...")
        
        for i in range(count):
            ride_element = ride_options_locator.nth(i)
            
            # --- Define Specific Locators based on the provided HTML ---
            
            # 1. Ride Name: The first <p> tag inside the list item is typically the name.
            name_locator = ride_element.locator('p').first
            
            # 2. Price: The <p> tag that contains the currency symbol '₹'.
            price_locator = ride_element.locator("p:has-text('₹')").first
            
            # 3. ETA/Time: The <p> with a specific data-testid for the ETA string.
            eta_locator = ride_element.locator('p[data-testid="product_selector.list_item.eta_string"]').first
            
            # --- Extraction and Error Handling ---
            
            try:
                # 4. Product ID (Highly reliable as a data attribute)
                product_id = await ride_element.get_attribute('data-itemid')
                
                # 5. Current Selection Status
                is_selected = await ride_element.get_attribute('aria-selected') == 'true'

                # Extract Text (use strip() to clean whitespace)
                ride_name_raw = (await name_locator.inner_text()).strip()
                price = await price_locator.inner_text()
                # Extract ETA and remove unnecessary whitespace/newlines
                eta_string = (await eta_locator.inner_text()).replace('\n', ' ').strip()
                
                # --- Logic to separate ride name and seat count ---
                ride_name = ride_name_raw
                seats = None
                # Use regex to find a number at the end of the string, which usually indicates seat count.
                match = re.search(r'^(.*?)\s*(\d+)$', ride_name_raw)
                if match:
                    # If a match is found, separate the name and the number of seats.
                    ride_name = match.group(1).strip()
                    seats = int(match.group(2))

                # Append the structured data
                ride_data.append({
                    "product_id": product_id,
                    "name": ride_name,
                    "seats": seats,
                    "price": price.strip(),
                    "eta_and_time": eta_string,
                    "is_selected": is_selected,
                })
                
            except Exception as e:
                self.logger.warning(f"Could not extract full data from ride option {i+1}. Skipping. Error: {e}")
                continue

        # --- Save to JSON ---
        if ride_data:
            # Create a directory for historical ride data if it doesn't exist.
            history_dir = os.path.join(os.path.dirname(__file__), '..', 'ride_history')
            os.makedirs(history_dir, exist_ok=True)

            # Structure the data to be saved, including locations.
            archive_data = {
                "search_timestamp": datetime.now().isoformat(),
                "ride_options": ride_data
            }

            # Generate a filename with the current date and time.
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"ride_data_{timestamp}.json"
            output_path = os.path.join(history_dir, filename)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(archive_data, f, ensure_ascii=False, indent=4)
                
            self.logger.info(f"✅ Extracted {len(ride_data)} ride options. Saved archive to {output_path}")
        else:
            self.logger.warning("Extraction failed: No ride data was collected.")
            
        return ride_data

    async def select_ride_by_product_id(self, product_id: str):
        """
        Finds and clicks on a specific ride option in the browser using its product_id.
        """
        self.logger.info(f"Attempting to select ride with product ID: {product_id}")
        try:
            # The product_id corresponds to the 'data-itemid' attribute of the list item.
            self.logger.debug(f"Looking for ride element with selector: li[data-itemid=\"{product_id}\"]")
            ride_selector = self.automation.page.locator(f'li[data-itemid="{product_id}"]')
            
            await ride_selector.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await ride_selector.click()
            self.logger.info(f"Successfully clicked on ride with product ID: {product_id}")
        except Exception as e:
            self.logger.error(f"Failed to select ride with product ID '{product_id}': {e}", exc_info=True)
            # Log all available product IDs on the page for debugging
            all_item_ids = await self.automation.page.locator('li[data-itemid]').evaluate_all("elements => elements.map(el => el.getAttribute('data-itemid'))")
            self.logger.error(f"Available data-itemid attributes on the page: {all_item_ids}")
            # Take a screenshot for visual debugging
            await self.automation.page.screenshot(path=f"uber_booking_failure_{product_id}.png")
            raise

    # async def click_request_ride_button(self):
    #     """
    #     Finds and clicks the final 'Request' button to book the selected ride.
    #     """
    #     self.logger.info("Attempting to click the 'Request' button for the selected ride.")
    #     try:
    #         # This selector is based on the provided HTML and is highly specific.
    #         request_button_selector = self.automation.page.locator('button[data-testid="request_trip_button"]')
            
    #         await request_button_selector.wait_for(state="visible", timeout=self.config.TIMEOUT)
    #         await request_button_selector.click()
    #         self.logger.info("✅ Successfully clicked the 'Request' button. The ride should be booked.")
    #     except Exception as e:
    #         self.logger.error(f"Failed to find or click the 'Request' button: {e}")
    #         raise