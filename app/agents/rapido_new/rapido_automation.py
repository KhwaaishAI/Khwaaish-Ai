import asyncio
from playwright.async_api import Page


async def open_rapido_home(page: Page):
    await page.goto("https://www.rapido.bike/", wait_until="domcontentloaded")


async def book_ride_rapido(page: Page, pickup: str, drop: str):
    await open_rapido_home(page)

    pickup_input = page.locator('input[aria-label="pickup"][placeholder="Enter Pickup Location"]').first
    drop_input = page.locator('input[aria-label="drop"][placeholder="Enter Drop Location"]').first

    await pickup_input.wait_for(state="visible", timeout=10000)
    await pickup_input.fill(pickup)
    await asyncio.sleep(0.5)

    # Click first pickup suggestion if dropdown appears
    try:
        pickup_wrapper = page.locator('div.jsx-2715316807.inputWrapper').nth(0)
        suggestion = pickup_wrapper.locator('div.jsx-2715316807.dropdown-item').first
        await suggestion.wait_for(state="visible", timeout=5000)
        await suggestion.click()
        await asyncio.sleep(0.5)
    except Exception:
        pass

    await drop_input.wait_for(state="visible", timeout=10000)
    await drop_input.fill(drop)
    await asyncio.sleep(0.5)

    # Click first drop suggestion if dropdown appears
    try:
        drop_wrapper = page.locator('div.jsx-2715316807.inputWrapper').nth(1)
        drop_suggestion = drop_wrapper.locator('div.jsx-2715316807.dropdown-item').first
        await drop_suggestion.wait_for(state="visible", timeout=5000)
        await drop_suggestion.click()
        await asyncio.sleep(0.5)
    except Exception:
        pass

    # Now click Book Ride (robustly, in case something still overlays it)
    book_button = page.locator('button[aria-label="book-ride"]').first
    await book_button.wait_for(state="visible", timeout=10000)
    try:
        await book_button.click(timeout=5000)
    except Exception:
        # Fallback: force click via JS
        await page.evaluate(
            "el => el.click()",
            book_button,
        )

    # Wait for fare estimate block
    wrapper = page.locator('div.fare-estimate-wrapper').first
    await wrapper.wait_for(state="visible", timeout=15000)

    cards = wrapper.locator('div.card-wrap')
    count = await cards.count()
    services = []
    for i in range(count):
        card = cards.nth(i)
        try:
            name_el = card.locator('div.card-content').first
            price_el = card.locator('div:not(.card-header-wrap)').nth(1)
            name = (await name_el.text_content() or "").strip()
            price_range = (await price_el.text_content() or "").strip()
            if name:
                services.append({"service": name, "price_range": price_range})
        except Exception:
            continue

    # Click Continue Booking
    continue_btn = page.locator('button.next-button:has-text("Continue Booking")').first
    await continue_btn.wait_for(state="visible", timeout=15000)
    await continue_btn.click()

    return {"services": services}


async def login_rapido(page: Page, phone_number: str):
    """Fill the phone number field and leave CAPTCHA / Get OTP click to the user."""
    # Ensure we are on the login view. Phone input usually has class "mobile-input" and no name.
    phone_input = page.locator('input.mobile-input[type="tel"]').first
    await phone_input.wait_for(state="visible", timeout=15000)

    # Normalize to 10 digits (Rapido expects 10-digit Indian mobile number)
    digits_only = "".join(ch for ch in phone_number if ch.isdigit())[-10:]
    await phone_input.click()
    await phone_input.fill("")
    await phone_input.type(digits_only, delay=50)

    # At this point the phone field is filled. User should solve CAPTCHA and click Get OTP manually.


async def verify_otp_rapido(page: Page, otp: str):
    otp_digits = list(otp.strip())[:6]
    wrapper = page.locator('div.otp-wrapper.wrapper').first
    await wrapper.wait_for(state="visible", timeout=15000)
    inputs = await wrapper.locator('input.otp-input').all()

    for i, digit in enumerate(otp_digits):
        if i >= len(inputs):
            break
        await inputs[i].fill(digit)

    # Keep Chromium open for 2 minutes after OTP entry
    await asyncio.sleep(120)
