import re
import asyncio
import json
from playwright.async_api import TimeoutError
from urllib.parse import quote_plus
import sys
import os
from datetime import datetime

# Add the root directory to the Python path to enable imports from other modules
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(MODULE_DIR))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.prompts.blinkit_prompts.blinkit_prompts import find_best_match

# Path to store authentication state
AUTH_FILE_PATH = os.path.join(MODULE_DIR, "playwright_auth.json")
SEARCH_HISTORY_DIR = os.path.join(MODULE_DIR, "search_history")

# Utility: safe sleep with small logs
async def safe_sleep(ms: int = 500):
    await asyncio.sleep(ms / 1000)


async def search_and_add_item(page, item_name: str, quantity: int):
    """Searches for an item, selects the best match, and adds it to the cart."""
    print(f"\nProcessing item: '{item_name}' (Quantity: {quantity})")
    search_url = f"https://www.blinkit.com/s/?q={quote_plus(item_name)}"
    print(f"- Navigating to search page: {search_url}")
    await page.goto(search_url, wait_until="domcontentloaded")

    try:
        first_product_card_selector = 'div[id][data-pf="reset"]'
        await page.wait_for_selector(first_product_card_selector, timeout=15000)
        print("- Product results page loaded successfully.")
    except TimeoutError:
        print(f"⚠ Could not find any products for '{item_name}' on the page. Skipping.")
        return

    product_locator = page.locator(first_product_card_selector)
    count = await product_locator.count()
    scraped_products = []
    print(f"- Found {count} products. Analyzing top 10.")

    for i in range(min(count, 10)):
        card = product_locator.nth(i)
        try:
            name_elem = card.locator('.tw-text-300.tw-font-semibold.tw-line-clamp-2').first
            price_elem = card.locator('.tw-text-200.tw-font-semibold').first

            if not await name_elem.is_visible(timeout=1000) or not await price_elem.is_visible(timeout=1000):
                continue

            name = (await name_elem.text_content(timeout=2000)) or ""
            price_text = (await price_elem.text_content(timeout=2000)) or ""
            price = float(re.sub(r'[^\d.]', '', price_text)) if price_text else float('inf')

            scraped_products.append({'name': name.strip(), 'price': price, 'card': card})
        except Exception:
            continue

    if not scraped_products:
        print(f"⚠ Could not scrape product details for '{item_name}'. Skipping.")
        return

    best_match_product = find_best_match(item_name, scraped_products)

    if not best_match_product:
        print("- No match found, falling back to the cheapest product.")
        scraped_products.sort(key=lambda p: p['price'])
        best_match_product = scraped_products[0] if scraped_products else None

    if not best_match_product:
        print(f"❌ Critical Error: Could not select any product for '{item_name}'. Skipping.")
        return

    selected_card = best_match_product['card']
    print(f"- Final selection: '{best_match_product['name']}' at ₹{best_match_product['price']}")

    try:
        add_button = selected_card.locator('div[role="button"]:has-text("ADD")')
        await add_button.click(timeout=5000)
        print("- Clicked 'ADD' once.")
        await safe_sleep(500)

        if quantity > 1:
            for i in range(quantity - 1):
                plus_button = selected_card.locator('button:has(span.icon-plus)')
                await plus_button.click(timeout=5000)
                print(f"- Clicked '+' to increase quantity to {i+2}")
                await safe_sleep(300)
        print(f"✅ Successfully added {quantity} of '{item_name}' to cart.")

    except Exception as e:
        print(f"❌ An unexpected error occurred while adding to cart: {e}")


async def _click_checkout_strip_cta(page, label: str, timeout: int = 7000):
    """Clicks the CheckoutStrip CTA that contains the given label."""
    strip_locator = page.locator(
        f'div.CheckoutStrip__StripContainer-sc-1fzbdhy-8:has-text("{label}")'
    ).first
    await strip_locator.wait_for(state="visible", timeout=timeout)
    await strip_locator.scroll_into_view_if_needed()

    cta_locator = strip_locator.locator(
        'div.CheckoutStrip__CTAText-sc-1fzbdhy-13', has_text=label
    ).first
    try:
        await cta_locator.click(timeout=timeout)
    except Exception:
        # Fall back to clicking the full strip via JS if the CTA is not clickable
        await strip_locator.evaluate("el => el.click()")


async def _click_pay_now_button(page, payment_frame=None, timeout: int = 6000):
    """Attempts multiple selectors to click the Pay Now/Checkout button."""
    candidates = [
        ("'Pay Now' button on page (Zpayments primary)", page.locator('.Zpayments__Button-sc-127gezb-3:has-text("Pay Now")').first),
        ("'Pay Now' button on page (container->button)", page.locator('.Zpayments__PayNowButtonContainer-sc-127gezb-4 .Zpayments__Button-sc-127gezb-3').first),
        ("'Pay Now' button on page (legacy)", page.locator('.Zpayments_PayNowButtonContainer-sc-127gezb-4 .Zpayments_Button-sc-127gezb-3').first),
        ("'Pay Now' button on page", page.locator('button:has-text("Pay Now")').first),
        ("'Pay Now' text on page", page.locator('text="Pay Now"').first),
    ]
    if payment_frame:
        candidates.extend([
            ("'Pay Now' inside payment iframe", payment_frame.locator('button:has-text("Pay Now")').first),
            ("'Checkout' inside payment iframe", payment_frame.locator('button:has-text("Checkout")').first),
            ("'Continue' inside payment iframe", payment_frame.locator('button:has-text("Continue")').first),
        ])

    last_error = None
    for description, locator in candidates:
        try:
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click(timeout=timeout)
            print(f"✅ Clicked {description}.")
            return description
        except Exception as e:
            last_error = e
            continue

    raise TimeoutError(f"Could not locate a clickable Pay Now button. Last error: {last_error}")


async def _wait_for_payment_iframe_ready(page, iframe_selector="#payment_widget", timeout=60000):
    """Robust strategy to wait until the payment iframe is attached and the internal UI is ready.

    Note: directly accessing iframe.contentDocument can be blocked for cross-origin frames. We therefore:
      1. wait for the iframe element to be attached
      2. wait for the iframe src to contain the expected payment path
      3. use frameLocator to wait for UI elements inside the iframe (Playwright handles cross-origin)
    """
    print("Waiting for payment iframe to attach...")
    # Stage 1: iframe element is attached
    await page.wait_for_selector(iframe_selector, state="attached", timeout=timeout)

    print("Iframe attached. Waiting for iframe src to contain payment path...")
    # Stage 2: iframe's src becomes the payment provider (Zomato zpaykit init)
    # This is safe to check even if the iframe is cross-origin because we only read the attribute.
    await page.wait_for_function(
        f"() => {{ const f = document.querySelector('{iframe_selector}'); return !!(f && f.src && f.src.includes('zpaykit/init')); }}",
        timeout=timeout,
    )

    print("Iframe src indicates payment provider. Waiting for payment UI inside iframe...")
    # Stage 3: use frameLocator to wait for typical payment UI elements.
    frame = page.frame_locator(iframe_selector)

    # Try multiple selectors (Pay Now, Checkout, or a known section). Wait until any one appears.
    candidate_selectors = [
        'button:has-text("Pay Now")',
        'button:has-text("Pay")',
        'button:has-text("Checkout")',
        'section',
        'div[data-test-id]'
    ]

    deadline = asyncio.get_event_loop().time() + (timeout / 1000)
    last_error = None
    for sel in candidate_selectors:
        remaining = max(1000, int((deadline - asyncio.get_event_loop().time()) * 1000))
        try:
            await frame.locator(sel).first.wait_for(state="visible", timeout=remaining)
            print(f"Found payment UI using selector: {sel}")
            return frame
        except Exception as e:
            last_error = e
            # try next selector
            continue

    # If nothing matched, raise TimeoutError with context
    raise TimeoutError(f"Timed out waiting for payment UI inside iframe. Last error: {last_error}")


async def automate_blinkit(shopping_list: dict, location: str, mobile_number: str, p, upi_id: str | None = None):
    """Launches Playwright to set location and process the shopping list."""
    print("\nStep 2: Starting browser automation with Playwright...")

    context_options = {}
    if os.path.exists(AUTH_FILE_PATH):
        print("- Found existing authentication file. Loading session...")
        context_options['storage_state'] = AUTH_FILE_PATH

    browser = await p.chromium.launch(headless=False, slow_mo=10)
    context = await browser.new_context(**context_options)
    page = await context.new_page()

    print("Navigating to Blinkit...")
    await page.goto("https://www.blinkit.com/", wait_until="domcontentloaded")

    location_input = page.get_by_placeholder("search delivery location")
    await location_input.fill(location)
    try:
        await page.locator(".LocationSearchList__LocationListContainer-sc-93rfr7-0").first.click()
    except TimeoutError:
        try:
            await page.wait_for_selector("input[placeholder*='Search for']", timeout=5000)
            print("- Location seems to be already set from the session.")
        except TimeoutError:
            print("❌ Critical Error: Could not set location or verify main page.")

    print("Location set. Waiting for 1.5 seconds before searching for items...")
    await page.wait_for_timeout(1500)
    print("Main page loaded.")

    print("\nStep 3: Preparing to add items to cart...")
    for item, quantity in shopping_list.items():
        await search_and_add_item(page, item, quantity)

    print("-----------------------------------------")
    print("\n✅ All items processed. Cart should be ready.")

    # Check if we are already logged in by looking for a "Proceed" button instead of "Login to Proceed"
    try:
        is_logged_in = await page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Proceed")').is_visible()
    except Exception:
        is_logged_in = False

    if not is_logged_in:
        print("\n- User not logged in. Starting login flow...")
        print("\nStep 4: Clicking on cart button...")
        try:
            cart_button = page.locator('div.CartButton__Button-sc-1fuy2nj-5').first
            await cart_button.click(timeout=5000)
            print("✅ Cart button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking cart button: {e}")
            return

        print("\nStep 5: Clicking on 'Login to Proceed' button...")
        try:
            login_button = page.locator('div.CheckoutStrip__CTAText-sc-1fzbdhy-13:has-text("Login to Proceed")').first
            await login_button.click(timeout=5000)
            print("✅ Login to Proceed clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Login to Proceed: {e}")
            return

        print("\nStep 6: Entering phone number...")
        try:
            phone_input = page.locator('input.login-phone__input[data-test-id="phone-no-text-box"]').first
            await phone_input.fill(mobile_number)
            print("✅ Phone number entered successfully.")
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"❌ Error entering phone number: {e}")
            return

        print("\nStep 7: Clicking 'Continue' button...")
        try:
            continue_button = page.locator('button.PhoneNumberLogin__LoginButton-sc-1j06udd-4:has-text("Continue")').first
            await continue_button.click(timeout=5000)
            print("✅ Continue button clicked successfully.")
        except Exception as e:
            print(f"❌ Error clicking Continue button: {e}")
            return

        print("\nStep 8: Waiting for OTP entry (30 seconds)...")
        print("⏳ Please enter the OTP on the browser...")
        await asyncio.sleep(30)
        print("✅ OTP wait period completed.")

        print("\nStep 9: Waiting for page to load after OTP...")
        await page.wait_for_timeout(3000)
        try:
            await _click_checkout_strip_cta(page, "Proceed", timeout=8000)
            print("✅ Final Proceed button clicked successfully.")
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"❌ Error clicking final Proceed button: {e}")
            return
    else:
        print("\n- User is already logged in. Proceeding with checkout...")
        try:
            await _click_checkout_strip_cta(page, "Proceed", timeout=8000)
            print("✅ Clicked 'Proceed' button.")
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"❌ Error clicking proceed: {e}")
            return

    print("\nStep 10: Selecting the first saved address...")
    try:
        first_address = page.locator('div.AddressList__AddressItemWrapper-sc-zt55li-1').first
        await first_address.click(timeout=5000)
        print("✅ First address selected.")
        print("Waiting for page to load...")
        await page.wait_for_timeout(4000)
    except Exception as e:
        print(f"❌ Error selecting address: {e}")
        return

    print("\nStep 11: Clicking 'Proceed To Pay'...")
    try:
        await _click_checkout_strip_cta(page, "Proceed To Pay", timeout=8000)
        print("✅ 'Proceed To Pay' button clicked successfully.")
    except Exception as e:
        print(f"❌ Error clicking 'Proceed To Pay' button: {e}")
        return

    # NEW: Robust waiting for payment iframe and flow
    try:
        print("\n--- Now handling payment options (iframe) ---")
        payment_frame = await _wait_for_payment_iframe_ready(page, iframe_selector="#payment_widget", timeout=60000)

        # Try 'Cash' option inside the frame first (many pages expose payment methods inside iframe)
        try:
            cash_option_selector = 'div[role="button"][aria-label="Cash"]'
            await payment_frame.locator(cash_option_selector).first.wait_for(state="visible", timeout=5000)
            await payment_frame.locator(cash_option_selector).first.click()
            print("✅ Selected 'Cash' as the payment method.")

            await _click_pay_now_button(page, payment_frame)
            print("✅ Pay Now sequence completed.")

        except Exception:
            print("⚠ 'Cash' option not found inside iframe, trying saved UPI or Add new UPI flow.")
            saved_upi_selector = 'div[class*="LinkedUPITile__Container"]:has-text("Please press continue to complete the purchase.")'
            try:
                await payment_frame.locator(saved_upi_selector).first.wait_for(state="visible", timeout=3000)
                print("- Found a saved UPI ID. Clicking Pay Now on page.")
                await _click_pay_now_button(page, payment_frame)
                print("✅ Pay Now sequence completed with saved UPI.")
            except Exception:
                # No saved UPI tile — click 'Add new UPI ID' and inform caller
                upi_option_selector = 'div[role="button"][aria-label="Add new UPI ID"]'
                try:
                    await payment_frame.locator(upi_option_selector).first.wait_for(state="visible", timeout=5000)
                    await payment_frame.locator(upi_option_selector).first.click()
                    print("✅ Clicked 'Add new UPI ID'. Ready for UPI input.")
                    if upi_id:
                        print("- UPI ID provided by caller. Submitting now...")
                        await submit_upi_and_pay(context, upi_id)
                        print("✅ UPI submitted successfully.")
                    else:
                        return {"status": "upi_id_needed", "message": "Cash not available. Please provide a UPI ID via submit_upi_and_pay."}
                except Exception as e:
                    print(f"❌ Could not find payment options inside iframe: {e}")
                    return {"status": "error", "message": "Payment UI not found."}

    except TimeoutError as te:
        print(f"❌ Timeout while waiting for payment iframe/UI: {te}")
        raise
    except Exception as e:
        print(f"❌ An error occurred during the add-to-cart and proceed flow: {e}")
        raise

    print("\n✅ Automation script finished.")
    print("Browser will close in 10 seconds.")
    await asyncio.sleep(10)


async def login(p, mobile_number: str, location: str) -> tuple:
    """
    Launches Playwright, navigates to Blinkit, and proceeds until the OTP screen.
    Returns the browser context and page for the next step.
    """
    print("\nStarting browser automation for Blinkit login...")
    browser = await p.chromium.launch(headless=False, slow_mo=5)
    context = await browser.new_context()
    page = await context.new_page()
    try:
        print("Navigating to Blinkit...")
        await page.goto("https://www.blinkit.com/", wait_until="domcontentloaded")
        location_input_selector = 'div.display--table-cell.full-width > input[placeholder="search delivery location"]'
        location_input = page.locator(location_input_selector)
        await location_input.click()
        await location_input.fill(location)
        await page.wait_for_timeout(1000)
        await page.locator(".LocationSearchList__LocationListContainer-sc-93rfr7-0").first.click()
        print(f"✅ Location set to '{location}'.")
        await page.locator("div.bFHCDW:has-text('Login')").first.wait_for(timeout=15000)

        print("Clicking on the main login button...")
        login_button = page.locator("div.bFHCDW:has-text('Login')").first
        await login_button.click(timeout=5000)
        print("✅ Login button clicked.")

        print("Entering phone number...")
        phone_input = page.locator('input.login-phone__input[data-test-id="phone-no-text-box"]').first
        await phone_input.wait_for(timeout=10000)
        await phone_input.fill(mobile_number)
        print(f"✅ Phone number '{mobile_number}' entered successfully.")

        continue_button = page.locator('button.PhoneNumberLogin__LoginButton-sc-1j06udd-4:has-text("Continue")').first
        await continue_button.click(timeout=5000)
        print("✅ Clicked 'Continue' button.")

        print("\n✅ OTP screen reached. Ready for OTP submission.")
        return context, page

    except Exception as e:
        if 'context' in locals() and context:
            await context.browser.close()
        print(f"❌ An error occurred during login automation: {e}")
        raise


async def enter_otp_and_save_session(context, otp: str):
    """Enters the OTP, saves the session state, and closes the browser."""
    page = context.pages[0]
    print(f"\nSubmitting OTP: {otp}")
    otp_inputs = page.locator('input[data-test-id="otp-text-box"]')
    for i, digit in enumerate(otp):
        await otp_inputs.nth(i).fill(digit)

    print("✅ OTP entered. Waiting 10 seconds for session to be established...")
    await asyncio.sleep(10)

    await context.storage_state(path=AUTH_FILE_PATH)
    print(f"✅ Authentication state saved to {AUTH_FILE_PATH}")


async def add_product_to_cart(context, session_id: str, product_name: str, quantity: int, upi_id: str | None = None):
    """Finds a specific product on the current page and adds it to the cart."""
    page = context.pages[0]
    print(f"\nAttempting to add '{product_name}' (Quantity: {quantity}) to cart.")
    await search_and_add_item(page, product_name, quantity)

    try:
        cart_button_selector = 'div.CartButton__Button-sc-1fuy2nj-5'
        cart_button = page.locator(cart_button_selector).first
        await cart_button.wait_for(state="visible", timeout=5000)

        cart_text = await cart_button.text_content()
        if cart_text and ("item" in cart_text or "items" in cart_text):
            await cart_button.click()
            print("✅ Clicked the main cart button to view cart summary.")

            await _click_checkout_strip_cta(page, "Proceed", timeout=8000)
            print("✅ Clicked 'Proceed' on the checkout strip.")
            await page.wait_for_timeout(2000)

            saved_address_selector = 'div[class*="AddressList__AddressItemWrapper"]'
            try:
                await page.locator(saved_address_selector).first.wait_for(state="visible", timeout=7000)
                print("- Found a saved address. Selecting it.")
                await page.locator(saved_address_selector).first.click()
                print("✅ First saved address selected.")
            except TimeoutError:
                print("- No saved address found.")
                return {"status": "address_needed", "session_id": session_id, "message": "No saved address found. Please provide a new address."}

            await _click_checkout_strip_cta(page, "Proceed To Pay", timeout=8000)
            print("✅ Clicked 'Proceed To Pay'.")

            # Wait and handle payment iframe
            try:
                payment_frame = await _wait_for_payment_iframe_ready(page, iframe_selector="#payment_widget", timeout=60000)
                # Similar logic as in automate_blinkit; try cash then UPI
                try:
                    cash_selector = 'div[role="button"][aria-label="Cash"]'
                    await payment_frame.locator(cash_selector).first.wait_for(state="visible", timeout=4000)
                    await payment_frame.locator(cash_selector).first.click()
                    print("✅ Selected Cash inside iframe.")
                    await _click_pay_now_button(page, payment_frame)
                    print("✅ Pay Now sequence completed.")
                except Exception:
                    print("- Cash not available inside iframe during add_product_to_cart flow.")
                    # try UPI saved
                    saved_upi_selector = 'div[class*="LinkedUPITile__Container"]:has-text("Please press continue to complete the purchase.")'
                    if await payment_frame.locator(saved_upi_selector).count() > 0:
                        print("- Found a saved UPI ID. Clicking Pay Now on page.")
                        await _click_pay_now_button(page, payment_frame)
                        print("✅ Pay Now sequence completed with saved UPI.")
                    else:
                        # click Add new UPI ID & inform caller
                        upi_option_selector = 'div[role="button"][aria-label="Add new UPI ID"]'
                        if await payment_frame.locator(upi_option_selector).count() > 0:
                            await payment_frame.locator(upi_option_selector).first.click()
                            print("✅ Clicked Add new UPI ID inside iframe.")
                            if upi_id:
                                print("- UPI ID provided by caller. Submitting now...")
                                await submit_upi_and_pay(context, upi_id)
                                print("✅ UPI submitted successfully.")
                            else:
                                return {"status": "upi_id_needed", "session_id": session_id, "message": "Provide UPI via submit_upi_and_pay"}
                        else:
                            print("❌ No recognizable payment option found.")
                            return {"status": "error", "message": "No payment option found."}

            except Exception as e:
                print(f"❌ Error while handling payment iframe: {e}")
                return {"status": "error", "message": str(e)}

        else:
            print("⚠ Cart appears empty, not clicking the cart button.")
            return {"status": "error", "message": "Cart is empty."}
    except Exception as e:
        print(f"❌ An error occurred during the add-to-cart and proceed flow: {e}")
        raise


async def add_or_select_address(context, location: str, house_number: str, name: str):
    """
    This function is deprecated and will be replaced by proceed_to_address and add_address.
    """
    pass


async def add_address(context, session_id: str, location: str, house_number: str, name: str):
    """
    Adds a new address to the user's account.
    """
    page = context.pages[0]
    print("\n--- Adding New Address ---")
    try:
        add_address_selector = 'div[class*=\"CartAddress_AddAddressContainer"]:has(div[class*=\"CartAddress_PlusIcon\"]):has-text(\"Add a new address\")'
        add_address_button = page.locator(add_address_selector).first
        await add_address_button.wait_for(state="visible", timeout=5000)
        await add_address_button.click()
        print("✅ Clicked 'Add a new address'.")

        address_input_selector = 'div.Select-input > input'
        await page.locator(address_input_selector).first.fill(location)
        print(f"- Filled address: '{location}'. Waiting for suggestions...")
        await page.wait_for_timeout(3000)
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("Enter")
        print("✅ Selected the first address suggestion.")
        await page.wait_for_timeout(1000)

        house_number_input = page.locator('div[class*=\"TextInput__StyledTextInput\"] input#address')
        await house_number_input.click()
        await house_number_input.fill(house_number)
        print(f"- Filled house number: '{house_number}'.")
        name_input = page.locator('div[class*=\"TextInput__StyledTextInput\"] input#name')
        await name_input.click()
        await name_input.fill(name)
        print(f"- Filled name: '{name}'.")

        save_address_selector = 'div[class*=\"SaveAddressButton\"]:has-text(\"Save Address\")'
        save_address_button = page.locator(save_address_selector).first
        await save_address_button.wait_for(state="visible", timeout=5000)
        await save_address_button.click()
        print("✅ Clicked 'Save Address'.")
        return {"status": "success", "message": "Successfully added new address."}

    except Exception as address_error:
        print(f"❌ An error occurred while adding address: {address_error}")
        return {"status": "error", "message": str(address_error)}


async def submit_upi_and_pay(context, upi_id: str):
    """
    Enters the provided UPI ID and clicks the final pay button.
    """
    page = context.pages[0]
    print(f"\n--- Submitting UPI ID: {upi_id} ---")
    try:
        frame = page.frame_locator("#payment_widget")
        upi_input_selector = 'input[class*=\"sc-1yzxt5f-9\"]'
        upi_input = frame.locator(upi_input_selector).first
        await upi_input.wait_for(state="visible", timeout=7000)
        await upi_input.click()
        await upi_input.fill(upi_id)
        print(f"✅ Filled UPI ID: '{upi_id}'.")

        # Click the final "Checkout" / "Pay" button inside iframe
        pay_button = frame.locator('button:has-text(\"Checkout\")').first
        await pay_button.wait_for(state="visible", timeout=7000)
        await pay_button.click()
        print("✅ Clicked final 'Checkout' button to complete the transaction.")
        return {"status": "success", "message": "UPI payment initiated successfully."}
    except Exception as e:
        print(f"❌ An error occurred during UPI submission: {e}")
        raise


async def search_multiple_products(p, queries: list[str]) -> tuple[any, any, dict]:
    """
    Launches a browser, logs in with saved state, and searches for multiple products.
    Returns the context, page, and scraped results to keep the session alive.
    """
    print("\nStarting browser automation for multi-product search...")
    if not os.path.exists(AUTH_FILE_PATH):
        print("❌ Authentication file not found. Please login first.")
        return {"error": "User not logged in. Please use the /login endpoint first."}

    browser = await p.chromium.launch(headless=False, slow_mo=5)
    context = await browser.new_context(storage_state=AUTH_FILE_PATH)
    page = await context.new_page()

    print("Navigating to Blinkit home page to initialize session...")
    await page.goto("https://www.blinkit.com/", wait_until="domcontentloaded")
    print("- Allowing time for session to be recognized...")
    await page.wait_for_timeout(1000)

    all_results = {}
    for query in queries:
        print(f"\n--- Searching for: '{query}' ---")
        products = await search_products(page, query)
        all_results[query] = products

    return context, page, all_results


async def search_products(page, query: str) -> list:
    """
    Searches for a single product query on an existing Playwright page.
    """
    try:
        search_url = f"https://www.blinkit.com/s/?q={quote_plus(query)}"
        print(f"- Navigating to search URL: {search_url}")
        await page.goto(search_url, wait_until="domcontentloaded")

        product_card_selector = 'div[id][data-pf=\"reset\"]'
        await page.wait_for_selector(product_card_selector, timeout=15000)
        print("- Product results page loaded.")

        product_cards = await page.locator(product_card_selector).all()
        scraped_products = []
        print(f"- Found {len(product_cards)} products. Scraping details...")

        for card in product_cards:
            try:
                name = await card.locator('.tw-text-300.tw-font-semibold.tw-line-clamp-2').text_content(timeout=2000)
                price_text = await card.locator('.tw-text-200.tw-font-semibold').text_content(timeout=2000)
                price = float(re.sub(r'[^\d.]', '', price_text))
                scraped_products.append({'name': name.strip(), 'price': price})
            except Exception:
                continue

        try:
            os.makedirs(SEARCH_HISTORY_DIR, exist_ok=True)
            timestamp = datetime.utcnow()
            search_data = {
                "query": query,
                "timestamp": timestamp.isoformat() + "Z",
                "products": scraped_products
            }
            filename = f"search_{query.replace(' ', '')}{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(SEARCH_HISTORY_DIR, filename)
            with open(filepath, 'w') as f:
                json.dump(search_data, f, indent=4)
            print(f"✅ Search results for '{query}' saved to {filepath}")
        except Exception as e:
            print(f"⚠ Could not save search history: {e}")

        return scraped_products
    except Exception as e:
        error_message = f"An error occurred while searching for '{query}': {e}"
        print(f"❌ {error_message}")
        return {"error": error_message}