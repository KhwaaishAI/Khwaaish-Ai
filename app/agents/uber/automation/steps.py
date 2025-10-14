import asyncio
import json
import os
import urllib.parse
from typing import Dict, Optional, Any, List, TYPE_CHECKING
import time
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

if TYPE_CHECKING:
    from automation.core import UberAutomation

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
        """Enters the user's phone number or email into the login field and proceeds.
        Returns the login type ('P' for phone, 'E' for email) to determine the next step.
        """
        # --- Interactive Login ---
        # Ask the user for their preferred login method.
        login_type_prompt = "How would you like to log in? (P)hone or (E)mail: "
        self.logger.info(login_type_prompt)
        login_type = input(login_type_prompt).strip().upper()

        if login_type == 'P':
            credential_prompt = "Please enter your phone number (e.g., +15551234567): "
        elif login_type == 'E':
            credential_prompt = "Please enter your email address: "
        else:
            self.logger.error("Invalid selection. Please run the script again and choose 'P' or 'E'.")
            raise ValueError("Invalid login type selected.")

        self.logger.info(credential_prompt)
        credential = input(credential_prompt).strip()

        self.logger.info(f"Entering login credential for user.")
        try:
            # Locate the input field by its placeholder text
            login_input_selector = "input[placeholder='Enter phone number or email']"
            await self.automation.page.wait_for_selector(login_input_selector, timeout=self.config.TIMEOUT)
            await self.automation.page.fill(login_input_selector, credential)
            self.logger.info("Successfully entered the phone number/email.")

            # Click the 'Next' or 'Continue' button to proceed
            # The error log showed multiple "Continue" buttons. Using the specific
            # data-testid is the most robust way to select the correct one.
            await self.automation.page.get_by_test_id("forward-button").click()
            self.logger.info("Clicked the 'Continue' (forward) button.")
            await self.automation.page.wait_for_load_state("domcontentloaded")
            return login_type
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

    async def enter_otp_code(self, login_type: str):
        """Waits for the OTP screen, prompts user for the 4-digit code, and enters it."""
        self.logger.info("Waiting for the OTP entry screen...")
        try:
            # Wait for the instruction text to ensure the page is ready
            await self.automation.page.wait_for_selector("text=/Enter the 4-digit code sent to/", timeout=self.config.TIMEOUT)
            self.logger.info("OTP screen detected.")

            if login_type == 'P':
                otp_prompt = "Enter the 4-digit code sent via SMS at: "
            else:  # 'E'
                otp_prompt = "Please enter the 4-digit code you received via Email: "

            # Prompt user for the OTP from the terminal
            self.logger.info(otp_prompt)
            otp_code = input(otp_prompt).strip()

            if not otp_code.isdigit() or len(otp_code) != 4:
                self.logger.error("Invalid OTP format. It must be a 4-digit number.")
                raise ValueError("Invalid OTP format.")

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
            self.logger.error(f"Failed to enter OTP code: {e}")
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
            await asyncio.sleep(3)
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

    async def extract_uber_rides_to_json(self, filename="uber_rides_data.json"):
        """
        Extracts ride details (Name, Price, ETA, Product ID) from the Uber product selection list
        and saves them to a JSON file, using highly specific locators.
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
            return None

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
                ride_name = await name_locator.inner_text()
                price = await price_locator.inner_text()
                # Extract ETA and remove unnecessary whitespace/newlines
                eta_string = (await eta_locator.inner_text()).replace('\n', ' ').strip()
                
                # Append the structured data
                ride_data.append({
                    "product_id": product_id,
                    "name": ride_name.strip(),
                    "price": price.strip(),
                    "eta_and_time": eta_string,
                    "is_selected": is_selected,
                })
                
            except Exception as e:
                self.logger.warning(f"Could not extract full data from ride option {i+1}. Skipping. Error: {e}")
                continue

        # --- Save to JSON ---
        if ride_data:
            # Ensure the path is within the agent's directory
            output_path = os.path.join(os.path.dirname(__file__), '..', filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(ride_data, f, ensure_ascii=False, indent=4)
                
            self.logger.info(f"✅ Successfully extracted {len(ride_data)} ride options and saved to {output_path}")
        else:
            self.logger.warning("Extraction failed: No ride data was successfully collected.")
            
        return ride_data

    async def select_ride_by_product_id(self, product_id: str):
        """
        Finds and clicks on a specific ride option in the browser using its product_id.
        """
        self.logger.info(f"Attempting to select ride with product ID: {product_id}")
        try:
            # The product_id corresponds to the 'data-itemid' attribute of the list item.
            ride_selector = self.automation.page.locator(f'li[data-itemid="{product_id}"]')
            
            await ride_selector.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await ride_selector.click()
            self.logger.info(f"Successfully clicked on ride with product ID: {product_id}")
        except Exception as e:
            self.logger.error(f"Failed to select ride with product ID '{product_id}': {e}")
            raise