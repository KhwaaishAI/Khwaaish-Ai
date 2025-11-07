import asyncio
import json
import os
import random
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict, Any


if TYPE_CHECKING:
    from app.agents.ride_booking.rapido.core import RapidoAutomation

class RapidoSteps:
    def __init__(self, automation: "RapidoAutomation"):
        self.automation = automation
        self.llm = automation.llm
        self.logger = automation.logger
        self.config = automation.config

    async def navigate_to_rapido(self):
        """Navigates to the Rapido website."""
        # You'll need to find the correct URL for Rapido's web booking.
        url = "https://www.rapido.bike"
        self.logger.info(f"Navigating to Rapido: {url}")
        await self.automation.page.goto(url, wait_until="domcontentloaded", timeout=self.config.TIMEOUT)
        self.logger.info("Successfully navigated to the Rapido page.")

    async def enter_pickup_location(self, pickup_location: str):
        """Enters the pickup location."""
        self.logger.info(f"Attempting to enter pickup location: '{pickup_location}'")
        try:
            pickup_input = self.automation.page.locator(
                'input[placeholder="Enter Pickup Location"][aria-label="pickup"]'
            )

            self.logger.info("Clicking the pickup location input field to activate it.")
            await pickup_input.click(timeout=self.config.TIMEOUT)

            self.logger.info(f"Typing '{pickup_location}' into the input field.")
            await pickup_input.fill(pickup_location)
            self.logger.info("Successfully typed the pickup location. Waiting for suggestions...")
            await asyncio.sleep(3)  

            first_suggestion_locator = self.automation.page.locator("div.dropdown-item").first
            self.logger.info("Waiting for the first location suggestion to be visible.")
            await first_suggestion_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await first_suggestion_locator.click()
            self.logger.info("Successfully clicked the first pickup location suggestion.")
        except Exception as e:
            self.logger.error(f"Failed to enter pickup location: {e}", exc_info=True)
            raise

    async def enter_destination_location(self, destination_location: str):
        """Enters the destination location."""
        self.logger.info(f"Attempting to enter destination location: '{destination_location}'")
        try:
            drop_input = self.automation.page.locator(
                'input[placeholder="Enter Drop Location"][aria-label="drop"]'
            )

            self.logger.info("Clicking the destination location input field to activate it.")
            await drop_input.click(timeout=self.config.TIMEOUT)

            self.logger.info(f"Typing '{destination_location}' into the input field.")
            await drop_input.fill(destination_location)
            self.logger.info("Successfully typed the destination location. Waiting for suggestions...")
            await asyncio.sleep(3)  # Wait for suggestions to load.

            first_suggestion_locator = self.automation.page.locator("div.dropdown-item").first
            self.logger.info("Waiting for the first destination suggestion to be visible.")
            await first_suggestion_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await first_suggestion_locator.click()
            self.logger.info("Successfully clicked the first destination location suggestion.")
        except Exception as e:
            self.logger.error(f"Failed to enter destination location: {e}", exc_info=True)
            raise

    async def click_search_button(self):
        """Clicks the 'Book Ride' button to find rides."""
        self.logger.info("Looking for the 'Book Ride' button.")
        try:
            book_ride_button = self.automation.page.locator('button[aria-label="book-ride"]')
            await book_ride_button.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await book_ride_button.click()
            self.logger.info("Successfully clicked the 'Book Ride' button.")

            await asyncio.sleep(10)
            self.logger.info("Reloading page after initial wait.")
            await self.automation.page.reload(wait_until="networkidle", timeout=self.config.TIMEOUT)

            # --- Check for security verification failure and reload if necessary ---
            await asyncio.sleep(5)
            error_locator = self.automation.page.locator('div.error:has-text("Failed to load security verification. Please refresh the page.")')
            is_error_visible = await error_locator.is_visible(timeout=5000)
            if is_error_visible:
                self.logger.warning("Security verification error detected. Reloading page again.")
                await self.automation.page.reload(wait_until="networkidle", timeout=self.config.TIMEOUT)
                self.logger.info("Page reloaded after security error.")

                # --- Add a final check to ensure the login page loaded after the reload ---
                try:
                    self.logger.info("Verifying that the login page has loaded correctly...")
                    login_input_locator = self.automation.page.locator("input.mobile-input.phone-number")
                    await login_input_locator.wait_for(state="visible", timeout=10000)
                except Exception:
                    self.logger.warning("Login page did not load after security error reload. Attempting one final reload.")
                    await self.automation.page.reload(wait_until="networkidle", timeout=self.config.TIMEOUT)
            else:
                # Use a short timeout to quickly check if the error message is present.
                # If the locator times out, it means the error is not present, and we can continue.
                self.logger.info("No security verification error found. Proceeding.")
        except Exception as e:
            self.logger.error(f"Failed to click the 'Book Ride' button: {e}", exc_info=True)
            raise

    async def check_and_handle_login(self):
        """Checks if a login screen is present and pauses for manual user login if needed."""
        self.logger.info("Checking if login is required...")

        async def _wait_for_manual_login():
            """Internal function to pause and wait for the user to log in."""
            self.logger.info("Login screen detected. Pausing for manual user login.")
            print("\n" + "="*60)
            print("ACTION REQUIRED: Please complete the Rapido login in the browser.")
            print("The script will wait until you are successfully logged in.")
            print("="*60 + "\n")
            # --- FIX: The "Welcome" message does not appear. A more reliable indicator of a
            # successful login is the appearance of the main ride list container. ---
            post_login_container = self.automation.page.locator("div.fare-estimate-wrapper").first
            self.logger.info("Waiting for user to complete login and for ride list to appear...")
            await post_login_container.wait_for(state="visible", timeout=0) # Wait forever
            self.logger.info("✅ Login confirmed. Ride list container is visible. Resuming automation.")

        # --- Handle intermittent 'Continue Booking' button ---
        continue_booking_button = self.automation.page.locator('button.next-button:has-text("Continue Booking")')
        try:
            self.logger.info("Checking for an intermediate 'Continue Booking' button...")
            await continue_booking_button.wait_for(state="visible", timeout=5000)
            self.logger.info("'Continue Booking' button found. Clicking it to proceed to login.")
            await continue_booking_button.click()
            await asyncio.sleep(3) # Wait for the login screen to appear after the click
            
            # After clicking, we MUST wait for login.
            await _wait_for_manual_login()
            return True

        except Exception:
            self.logger.info("'Continue Booking' button not found. Proceeding with direct login check.")
            # --- If 'Continue Booking' was not found, check for the login input directly ---
            login_input_locator = self.automation.page.locator("input.mobile-input.phone-number")
            try:
                await login_input_locator.wait_for(state="visible", timeout=10000)
                await _wait_for_manual_login()
                return True
            except Exception:
                self.logger.info("Login screen not found. Assuming user is already logged in.")
                return False

    async def enter_location_after_login(self, location: str):
        """Enters the location on the screen that appears after login."""
        self.logger.info(f"Attempting to enter location post-login: '{location}'")
        try:
            initial_pickup_input = self.automation.page.locator('input[placeholder="Enter pickup location here"]')
            self.logger.info("Waiting for the initial post-login pickup input to be visible.")
            await initial_pickup_input.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await initial_pickup_input.click()
            self.logger.info("Clicked the initial pickup input. Now looking for the active input field.")
            location_input = self.automation.page.locator('input#autosuggestioninput[placeholder="Enter pickup location"]')
            self.logger.info("Waiting for the post-login pickup input to be visible.")
            await location_input.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await location_input.click()
            await location_input.fill(location)
            self.logger.info("Successfully typed location. Pressing 'Enter' to load suggestions...")
            await location_input.press("Enter")

            first_suggestion = self.automation.page.locator('div.location-item-wrap').first
            await first_suggestion.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await first_suggestion.click()
            self.logger.info("Successfully clicked the first post-login location suggestion.")
        except Exception as e:
            self.logger.error(f"Failed to enter location after login: {e}", exc_info=True)
            raise

    async def enter_drop_location_after_login(self, location: str):
        """Enters the drop location on the screen that appears after the pickup is set post-login."""
        self.logger.info(f"Attempting to enter drop location post-login: '{location}'")
        try:
            initial_drop_input = self.automation.page.locator('input[placeholder="Enter drop location here"]')
            self.logger.info("Waiting for the initial post-login pickup input to be visible.")
            await initial_drop_input.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await initial_drop_input.click()
            self.logger.info("Clicked the initial pickup input. Now looking for the active input field.")
            location_input = self.automation.page.locator(
                'input#autosuggestioninput[placeholder="Enter drop location"]'
            )

            self.logger.info("Clicking the post-login drop location input field.")
            await location_input.click()
            await location_input.fill(location)
            self.logger.info("Successfully typed location. Pressing 'Enter' to load suggestions...")
            await location_input.press("Enter")

            first_suggestion = self.automation.page.locator('div.location-item-wrap').first
            await first_suggestion.wait_for(state="visible", timeout=self.config.TIMEOUT)
            await first_suggestion.click()
            self.logger.info("Successfully clicked the first post-login drop location suggestion.")
        except Exception as e:
            self.logger.error(f"Failed to enter drop location after login: {e}", exc_info=True)
            raise

    async def extract_rides(self) -> List[Dict[str, Any]]:
        """Extracts available ride options."""
        self.logger.info("Extracting ride options from Rapido.")

        try:
            # The main container for ride options, based on the provided HTML.
            ride_container_locator = self.automation.page.locator("div.fare-estimate-wrapper")
            await ride_container_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)

            # FIX: Based on the new HTML, all ride cards are now under 'div.card-wrap'.
            ride_elements_locator = ride_container_locator.locator("div.card-wrap")
            await ride_elements_locator.first.wait_for(state="visible", timeout=self.config.TIMEOUT)

            extracted_rides = []
            all_ride_cards = await ride_elements_locator.all()
            self.logger.info(f"Found {len(all_ride_cards)} potential ride options. Extracting details...")

            for ride_card in all_ride_cards:
                try:
                    # --- FIX: Use more robust, combined selectors that work for ALL ride cards ---
                    # The ride name is in 'span.selected-service-name' (for selected) or inside 'div.card-content > div > span' (for unselected).
                    name_locator = ride_card.locator("span.selected-service-name, div.card-content span:first-child")
                    # The price is in 'div.bolder' (for selected) or a direct child 'div' of the card (for unselected).
                    # The ':has-text("₹")' ensures we only grab the div containing the price.
                    price_locator = ride_card.locator('div.bolder, div:has-text("₹")')
                    # The ETA is in 'span.eta-indication' (for selected) or 'span.service-eta' (for unselected).
                    eta_locator = ride_card.locator("span.eta-indication, span.service-eta")

                    # Ensure the essential elements (name and price) exist before trying to extract.
                    if await name_locator.count() > 0 and await price_locator.count() > 0:
                        ride_name = await name_locator.inner_text()
                        price_text = await price_locator.inner_text()
                        
                        # ETA is optional, so we handle its potential absence gracefully.
                        eta_text = "N/A"
                        if await eta_locator.count() > 0:
                            eta_text = await eta_locator.inner_text()

                        # Skip empty/invalid entries
                        if not ride_name or not price_text:
                            continue

                        extracted_rides.append({
                            "name": ride_name.strip(),
                            "price": price_text.strip(),
                            "eta": eta_text.strip(),
                            "locator": ride_card  # Storing the locator for booking
                        })
                except Exception as e:
                    self.logger.warning(f"Could not extract full data from a ride card. It might be an invalid element or missing price. Skipping. Error: {e}")
                    continue

            # --- Save to JSON ---
            if extracted_rides:
                history_dir = os.path.join(os.path.dirname(__file__), '..', 'ride_history')
                os.makedirs(history_dir, exist_ok=True)

                # Create a serializable version of the ride data
                serializable_rides = [
                    {"name": r["name"], "price": r["price"], "eta": r["eta"]} for r in extracted_rides
                ]
                archive_data = {
                    "search_timestamp": datetime.now().isoformat(),
                    "ride_options": serializable_rides
                }

                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"rapido_ride_data_{timestamp}.json"
                output_path = os.path.join(history_dir, filename)

                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(archive_data, f, ensure_ascii=False, indent=4)
                self.logger.info(f"✅ Saved ride data archive to {output_path}")

            self.logger.info(f"Successfully extracted {len(extracted_rides)} ride options.")
            return extracted_rides
        except Exception as e:
            self.logger.error(f"Failed to extract Rapido rides: {e}", exc_info=True)
            return []

    async def select_ride(self, ride_details: Dict[str, Any]):
        """
        Clicks on a specific ride option in the browser using the locator stored
        in the ride_details dictionary.
        """
        ride_name = ride_details.get("name", "Unknown Ride")
        self.logger.info(f"Attempting to select ride: '{ride_name}'")
        try:
            ride_locator = ride_details.get("locator")
            if not ride_locator:
                raise ValueError("Ride details dictionary is missing the 'locator' object.")
            
            await ride_locator.click(timeout=self.config.TIMEOUT)
            self.logger.info(f"✅ Successfully clicked on ride: '{ride_name}'")
        except Exception as e:
            self.logger.error(f"Failed to select ride '{ride_name}': {e}", exc_info=True)
            raise

    # async def click_confirm_booking_button(self, ride_details: Dict[str, Any]):
    #     """
    #     Waits for and clicks the final 'Book [Ride Name]' button.
    #     """
    #     ride_name = ride_details.get("name", "Unknown Ride")
    #     self.logger.info(f"Looking for the final 'Book {ride_name}' button.")
    #     try:
    #         # The button text is dynamic, e.g., "Book Bike", "Book Cab Economy".
    #         # We construct the selector based on the ride name.
    #         book_button_locator = self.automation.page.locator(f"button:has-text('Book {ride_name}')")

    #         self.logger.info("Waiting for the booking button to be visible...")
    #         await book_button_locator.wait_for(state="visible", timeout=self.config.TIMEOUT)
    #         await book_button_locator.click()
    #         self.logger.info(f"✅ Successfully clicked 'Book {ride_name}'. Ride should be requested.")
    #     except Exception as e:
    #         self.logger.error(f"Failed to find or click the 'Book {ride_name}' button: {e}", exc_info=True)
    #         raise
