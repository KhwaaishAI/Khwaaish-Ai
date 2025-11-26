import asyncio
from playwright.async_api import TimeoutError
import sys
import os

# Add the root directory to the Python path to enable imports from other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

DESKTOP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
DEFAULT_VIEWPORT = {"width": 1366, "height": 768}
HEADLESS_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
]


async def _click_robust(page, candidates, timeout: int = 5000):
    """Try multiple locators to click the same UI with fallbacks."""
    last_err = None
    for desc, loc in candidates:
        try:
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.scroll_into_view_if_needed()
            await loc.click(timeout=timeout)
            print(f"✅ Clicked {desc}.")
            return True
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    return False


async def _dismiss_district_overlays(page):
    """Best-effort dismissal of blocking modals/overlays on District (e.g., location prompts)."""
    try:
        # Try clicking common close / dismiss buttons inside dialogs
        await _click_robust(
            page,
            [
                ("Dialog close button", page.get_by_role("button", name="✕").first),
                ("Dialog close aria-label", page.locator('[aria-label="Close"]').first),
                ("Never allow button", page.locator('button:has-text("Never allow")').first),
                ("Allow while visiting button", page.locator('button:has-text("Allow while visiting")').first),
                ("Allow this time button", page.locator('button:has-text("Allow this time")').first),
            ],
            timeout=2000,
        )
    except Exception:
        pass

    # As a last resort, remove any blocking dialog overlay via JS
    try:
        await page.evaluate(
            """
            () => {
                const dialogs = document.querySelectorAll('div[role="dialog"]');
                dialogs.forEach(d => {
                    if (d && d.style) {
                        d.style.display = 'none';
                    }
                });
            }
            """
        )
    except Exception:
        pass


async def _select_location(page, location: str):
    """Select city/location on District by Zomato using the search box and first result."""
    print(f"➡️ Selecting District location '{location}'...")
    try:
        # On first load the location dialog is usually open; otherwise try to open it.
        search_input = page.locator('input[placeholder="Search city, area or locality"]').first
        try:
            await search_input.wait_for(state="visible", timeout=5000)
        except TimeoutError:
            # Try to click the current location chip to open the dialog
            try:
                await _click_robust(
                    page,
                    [
                        ("Header location chip", page.locator('span.dds-text-primary.dds-text-lg').first),
                    ],
                    timeout=4000,
                )
                await asyncio.sleep(0.5)
            except Exception:
                pass
            await search_input.wait_for(state="visible", timeout=5000)

        await search_input.fill(location)
        await asyncio.sleep(0.5)

        # Click the first city result button
        first_result = page.locator('button[aria-label]').first
        await first_result.wait_for(state="visible", timeout=5000)
        await first_result.click(timeout=5000)
        print("✅ District location selected.")
    except Exception as exc:
        print(f"⚠️ Failed to select District location: {exc}")
        raise


async def login_district(mobile_number: str, location: str, playwright):
    """Launch Playwright, navigate to District, set location, and initiate login."""
    print("\nStarting browser automation for District Login...")
    browser = await playwright.chromium.launch(headless=False, slow_mo=0, args=HEADLESS_ARGS)
    context = await browser.new_context(
        viewport=DEFAULT_VIEWPORT,
        user_agent=DESKTOP_USER_AGENT,
        locale="en-US",
        timezone_id="Asia/Kolkata",
        geolocation={"latitude": 22.5726, "longitude": 88.3639},  # Kolkata by default
        permissions=["geolocation"],
    )
    page = await context.new_page()

    try:
        print("➡️ Navigating to https://www.district.in/")
        await page.goto("https://www.district.in/", wait_until="domcontentloaded")
        print("✅ District homepage loaded.")

        # Select location
        await _select_location(page, location)

        # Click profile / account icon (avatar circle)
        print("\n➡️ Opening login dialog...")
        await _dismiss_district_overlays(page)
        await _click_robust(
            page,
            [
                # Use contains-class selector to avoid CSS bracket-escaping issues
                (
                    "Avatar circle by class contains",
                    page.locator(
                        "div[class*='dds-w-[42px]'][class*='dds-h-[42px]'][class*='dds-rounded-full']"
                    ).first,
                ),
            ],
            timeout=5000,
        )

        # Enter mobile number
        print("\n➡️ Entering mobile number...")
        phone_input = page.locator('input[placeholder="Enter mobile number"]').first
        await phone_input.wait_for(state="visible", timeout=8000)
        await phone_input.fill(mobile_number)
        print("✅ Mobile number entered.")

        # Click Continue
        print("\n➡️ Clicking 'Continue' button for login...")
        await _click_robust(
            page,
            [
                ("Continue text button", page.get_by_role("button", name="Continue")),
                ("Continue primary button", page.locator('button:has-text("Continue")').first),
            ],
            timeout=7000,
        )
        print("✅ District login initiated. Browser is waiting for OTP.")
        return browser, page

    except Exception as e:
        print(f"❌ District login failed: {e}")
        await browser.close()
        raise


async def enter_otp_district(page, otp: str):
    """Enter the 6-digit OTP on the District OTP screen."""
    print(f"\n➡️ Entering District OTP: {otp}")
    try:
        # Get all OTP digit inputs
        otp_inputs = await page.locator('input[aria-label^="OTP digit"]').all()
        if not otp_inputs:
            # Fallback: any 6 numeric inputs in the OTP container
            otp_inputs = await page.locator('input[inputmode="numeric"]').all()
        digits = list(otp.strip())
        for i, digit in enumerate(digits[:6]):
            if i >= len(otp_inputs):
                break
            await otp_inputs[i].fill(digit)
        print("✅ District OTP entered.")

        # Click Continue on OTP screen
        await _click_robust(
            page,
            [
                ("OTP Continue role button", page.get_by_role("button", name="Continue")),
                ("OTP Continue primary button", page.locator('button:has-text("Continue")').first),
            ],
            timeout=7000,
        )
        print("✅ District OTP submitted.")

    except Exception as e:
        print(f"❌ Error entering District OTP: {e}")
        raise


async def search_movie_district(page, query: str):
    """Search for a movie, click the first result, and return cinema sessions data."""
    print(f"\n➡️ Searching District movie: {query}")
    await _dismiss_district_overlays(page)

    try:
        # Click the header search icon (the SVG magnifier inside the small purple div)
        search_icon = page.locator(
            "div.dds-w-7.dds-h-7.dds-flex.dds-items-center.dds-cursor-pointer"
        ).first
        try:
            await search_icon.wait_for(state="visible", timeout=4000)
            await search_icon.click()
        except Exception:
            pass

        # The movie query input uses the rounded input classes; do not scope to <header>
        search_input = page.locator(
            "input.dds-rounded-lg.dds-outline-none.dds-h-10.dds-text-lg.dds-px-3.dds-border.dds-pl-3"
        ).first
        await search_input.wait_for(state="visible", timeout=5000)
        await search_input.click()
        await search_input.fill("")
        await search_input.type(query, delay=40)
        await page.wait_for_timeout(800)

        # Click first search result card (movie result)
        first_result = page.locator(
            "a.dds-cursor-pointer.dds-flex.dds-flex-row"
        ).first
        movie_title = await first_result.locator("h5").inner_text()
        await first_result.click(timeout=8000)
        print(f"✅ Opened movie page: {movie_title}")

        # Wait for cinema sessions list
        sessions_locator = page.locator("li.MovieSessionsListing_movieSessions__c4gaO")
        await sessions_locator.first.wait_for(state="visible", timeout=12000)

        cinemas = []
        cinema_items = await sessions_locator.all()
        for item in cinema_items:
            try:
                name_el = item.locator(".MovieSessionsListing_titleFlex__mE_KX a").first
                name = (await name_el.inner_text()).strip()
            except Exception:
                continue

            distance = ""
            try:
                distance_el = item.locator(".MovieSessionsListing_distance__n3Cdw").first
                distance = (await distance_el.inner_text()).strip()
            except Exception:
                pass

            cancellation = ""
            try:
                cancel_el = item.locator(".MovieSessionsListing_cancelLabel__ovJwA").first
                cancellation = (await cancel_el.inner_text()).strip()
            except Exception:
                pass

            times = []
            try:
                time_blocks = await item.locator(".MovieSessionsListing_time___f5tm").all()
                for tb in time_blocks:
                    t = (await tb.inner_text()).strip().split("\n")[0]
                    if t:
                        times.append(t)
            except Exception:
                pass

            cinemas.append(
                {
                    "name": name,
                    "distance": distance,
                    "cancellation": cancellation,
                    "times": times,
                }
            )

        return {"movie_title": movie_title, "cinemas": cinemas}

    except Exception as e:
        print(f"❌ Error searching District movie: {e}")
        raise


async def book_show_district(page, cinema_name: str, show_time: str):
    """On the movie sessions page, select the cinema+time and navigate to seat layout.

    Returns available times and seats.
    """
    print(f"\n➡️ Booking show for '{cinema_name}' at '{show_time}'")
    await _dismiss_district_overlays(page)

    try:
        cinema_item = (
            page.locator("li.MovieSessionsListing_movieSessions__c4gaO")
            .filter(has_text=cinema_name)
            .first
        )
        await cinema_item.wait_for(state="visible", timeout=8000)

        time_block = cinema_item.locator(
            "li.MovieSessionsListing_timeblock___GP_o",
        ).filter(has_text=show_time).first
        await time_block.wait_for(state="visible", timeout=5000)
        await time_block.click(timeout=5000)

        # Wait for seat layout page to load
        await page.wait_for_selector("#seat-layout-id, .SeatLayout_seatLayoutContainer__FYutn", timeout=15000)

        # Collect available times in header
        available_times = []
        try:
            header_times = await page.locator(".SeatLayoutHeader_time__AFJX0").all()
            for ht in header_times:
                txt = (await ht.inner_text()).strip().split("\n")[0]
                if txt:
                    available_times.append(txt)
        except Exception:
            pass

        # Collect available seats (spans marked as available via aria-label and role=button)
        available_seats = []
        try:
            # Wait for at least one available seat to render
            await page.locator("span[role='button'][aria-label*='available  seat']").first.wait_for(
                state="visible", timeout=10000
            )

            seats = await page.locator(
                "span[role='button'][aria-label*='available  seat']"
            ).all()
            print(f"Found {len(seats)} available seat elements")
            for s in seats:
                try:
                    aria = (await s.get_attribute("aria-label")) or ""
                    label_el = s.locator("label")
                    seat_no = (await label_el.inner_text()).strip()
                    available_seats.append({"seat": seat_no, "aria_label": aria})
                except Exception:
                    continue
        except Exception as exc:
            print(f"Seat scraping error: {exc}")

        print("✅ Reached seat layout and collected seats.")
        return {"available_times": available_times, "available_seats": available_seats}

    except Exception as e:
        print(f"❌ Error selecting cinema/time: {e}")
        raise


async def buy_ticket_district(page, seat_numbers, upi_id: str | None = None):
    """Select given seat numbers on the seat layout and proceed to payment via UPI."""
    print(f"\n➡️ Selecting seats on District: {seat_numbers}")
    try:
        # Click requested seat numbers if available
        seats = await page.locator("span[aria-label^='available']").all()
        remaining = set(str(s) for s in seat_numbers)
        for s in seats:
            if not remaining:
                break
            try:
                label_el = s.locator("label")
                seat_no = (await label_el.inner_text()).strip()
                if seat_no in remaining:
                    await s.click(timeout=3000)
                    remaining.discard(seat_no)
            except Exception:
                continue

        print(f"✅ Selected requested seats, remaining not found: {list(remaining)}")

        # Click 'Proceed' button on seat layout
        await _click_robust(
            page,
            [
                ("Proceed button", page.get_by_role("button", name="Proceed")),
                ("Proceed label button", page.locator('button:has-text("Proceed")').first),
            ],
            timeout=8000,
        )

        # Click 'Proceed To Pay' on payment summary
        await _click_robust(
            page,
            [
                (
                    "Proceed To Pay div",
                    page.locator("div.ZpayKit_proceedButton__tV_VK").first,
                ),
            ],
            timeout=10000,
        )

        print("✅ Clicked Proceed and Proceed To Pay.")

        # UPI selection logic:
        # 1) If any linked UPI tile exists, always use the first one (like your 8327050098@ybl).
        # 2) Only if there is NO linked UPI and upi_id is provided, open "Add new UPI" and type it.

        has_linked = False
        try:
            linked_tiles = page.locator("div.LinkedUPITile__Container-sc-5j1f6k-0")
            has_linked = await linked_tiles.count() > 0
        except Exception:
            linked_tiles = None
            has_linked = False

        if has_linked:
            try:
                first_linked = linked_tiles.first
                await first_linked.wait_for(state="visible", timeout=4000)
                await first_linked.click()
                print("✅ Using existing linked UPI tile.")
            except Exception as e:
                print(f"⚠️ Failed to click existing linked UPI: {e}")

        elif upi_id:
            # No linked UPI, but user provided one: use Add new UPI flow
            print(f"➡️ No linked UPI found, adding new UPI ID: {upi_id}")

            try:
                await _click_robust(
                    page,
                    [
                        (
                            "Add new UPI tile by heading",
                            page.locator('p.AddUPITile__Heading-sc-hdxyoc-2:has-text("Add new UPI")').first,
                        ),
                        (
                            "Add new UPI container",
                            page.locator("div.AddUPITile__Container-sc-hdxyoc-0").first,
                        ),
                    ],
                    timeout=8000,
                )

                upi_input = page.locator("input.sc-1yzxt5f-9").first
                await upi_input.wait_for(state="visible", timeout=8000)
                await upi_input.fill(upi_id)
            except Exception as e:
                print(f"⚠️ Failed to use Add new UPI flow: {e}")

        # At this point either an existing UPI is selected or a new UPI was (best-effort) entered.
        # Click the PAY button in both cases.
        await _click_robust(
            page,
            [
                (
                    "PAY button by class",
                    page.locator("div.ZpayKit_checkoutBtn__bMmZK").first,
                ),
                (
                    "PAY button by text",
                    page.locator('div:has-text("PAY ₹")').first,
                ),
            ],
            timeout=10000,
        )

        print("✅ Clicked PAY. Waiting 2 minutes before closing.")
        # Keep the browser open for 2 minutes so the user can approve payment
        await asyncio.sleep(120)

        return {"status": "success", "remaining_not_found": list(remaining)}

    except Exception as e:
        print(f"❌ Error buying District ticket: {e}")
        raise
