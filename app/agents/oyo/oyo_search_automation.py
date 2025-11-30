import re
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from playwright.async_api import TimeoutError
from datetime import datetime

async def set_oyo_rooms_and_guests(page, rooms, guests):
    # ==============================
    #  VALIDATION
    # ==============================
    if rooms < 1 or rooms > 6:
        raise ValueError("Rooms must be between 1 and 6.")

    if guests < rooms:
        raise ValueError("Guests must be >= rooms (each room has 1 default).")

    if guests > rooms * 3:
        raise ValueError("Max 3 guests per room!")

    print("\nOpening Guest/Room Picker...")

    # ==============================
    # 1. CLICK THE GUEST/ROOM PICKER
    # ==============================
    await page.locator(
        "div.headerSearchWidget__guestRoomPicker"
    ).click()

    await page.wait_for_timeout(800)

    # ==============================
    # 2. ADD ROOMS
    # ==============================
    print(f"Setting rooms = {rooms}")

    add_room_btn = page.locator("button.guestRoomPickerPopUp__addRoom")

    for i in range(rooms - 1):  # default is 1 room
        await add_room_btn.click()
        await page.wait_for_timeout(400)

    # ==============================
    # 3. ALLOCATE GUESTS
    # ==============================
    print(f"Setting guests = {guests}")

    remaining = guests - rooms  # default 1 per room
    print(f"Remaining guests to allocate: {remaining}")

    # fetch all room blocks
    room_blocks = page.locator("div.guestRoomPickerPopUp__roomInfo")
    room_count = await room_blocks.count()

    for r in range(room_count):

        if remaining <= 0:
            break

        # how many we can add in this room
        add_here = min(remaining, 2)  # each room can take +2 more (max=3 adults)

        plus_btn = room_blocks.nth(r).locator("span.guestRoomPickerPopUp__plus")

        for _ in range(add_here):
            await plus_btn.click()
            await page.wait_for_timeout(300)

        remaining -= add_here
        print(f"Room {r+1} allocated +{add_here} guests")

    print("Guest allocation complete.\n")

    # ==============================
    # 4. CLICK SEARCH BUTTON
    # ==============================
    await page.locator(
        "div.headerSearchWidget__comp.headerSearchWidget__search button.u-textCenter.searchButton.searchButton--header"
    ).click()

    print("Search triggered. Waiting for results...\n")


def validate_inputs(country, city, checkin, checkout, rooms, guests):
    """
    Validates and returns cleaned/validated parameters.
    """

    # --- DATE VALIDATION ---
    today = datetime.today().date()

    # Convert dd/mm/yyyy to date
    def parse_date(d):
        return datetime.strptime(d, "%d/%m/%Y").date()

    checkin_date = parse_date(checkin)
    checkout_date = parse_date(checkout)

    if checkin_date < today:
        raise ValueError("❌ Check-in date cannot be before today.")

    if checkout_date <= checkin_date:
        raise ValueError("❌ Checkout date must be after check-in date.")

    # --- ROOMS VALIDATION ---
    if rooms < 1 or rooms > 6:
        raise ValueError("❌ Rooms must be between 1 and 6.")

    # --- GUEST VALIDATION ---
    max_allowed_guests = rooms * 3
    if guests < 1 or guests > max_allowed_guests:
        raise ValueError(f"❌ Guests must be between 1 and {max_allowed_guests} for {rooms} rooms.")

    return (
        country.strip(),
        city.strip(),
        checkin_date.strftime("%d/%m/%Y"),
        checkout_date.strftime("%d/%m/%Y"),
        rooms,
        guests
    )


def build_oyo_url(country, city, checkin, checkout, rooms, guests):
    """
    Returns a valid OYO hotel search URL.
    """
    encoded_city = quote_plus(city + ", " + country)

    return (
        "https://www.oyorooms.com/search/?"
        f"location={encoded_city}"
        f"&city={quote_plus(city)}"
        "&searchType=city"
        "&coupon="
        f"&checkin={checkin}"
        f"&checkout={checkout}"
        # f"&roomConfig%5B%5D={rooms}"
        # f"&guests={guests}"
        # f"&rooms={rooms}"
        f"&countryName={quote_plus(country)}"
        f"&country={country.lower()}"
    )


async def automate_oyo_search(p, city: str, country: str, checkin: str, checkout: str, rooms: int, guests: int):
    """OYO automation with correct URL + auto-checkin/out"""

    browser = await p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )

    context = await browser.new_context(
        viewport={"width": 1280, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )

    page = await context.new_page()
    
    # Validate and clean user inputs
    try:
        country, city, checkin, checkout, rooms, guests = validate_inputs(
            country, city, checkin, checkout, rooms, guests
        )
    except ValueError as err:
        print(err)
        return []

    # Build final URL
    search_url = build_oyo_url(country, city, checkin, checkout, rooms, guests)

    print("\n➡️ Navigating to:", search_url, "\n")

    await page.goto(search_url, wait_until="networkidle")

    print("Waiting for hotel results...")

    try:
        await page.wait_for_selector("div.hotelCardListing", timeout=20000)
        print("Hotel results loaded.")
    except TimeoutError:
        print("⚠️ No hotels found.")
        await browser.close()
        return []
    
    await set_oyo_rooms_and_guests(page,rooms,guests)

    try:
        await page.wait_for_selector("div.hotelCardListing", timeout=20000)
        print("Hotel results loaded.")
    except TimeoutError:
        print("⚠️ No hotels found.")
        await browser.close()
        return []

    hotel_cards = page.locator("div.hotelCardListing")
    count = await hotel_cards.count()
    print(f"Found {count} hotels. Scraping top 20...\n")

    results = []

    for i in range(min(count, 20)):
        try:
            print(f"Scraping hotel {i+1}...")
            card = hotel_cards.nth(i)
            print("Located card.\n", card)

            # NAME
            name = (await card.locator("h3").first.text_content()).strip()
            print(f"Hotel Name: {name}")

            # Ensure card is visible so lazy-loaded parts populate
            try:
                await card.scroll_into_view_if_needed()
                await page.wait_for_timeout(600)  # small pause to allow lazy load
            except Exception:
                pass

            # PRICE
            try:
                price_node = card.locator("span.listingPrice__finalPrice").first
                price_text = await price_node.text_content(timeout=4000)
                print(f"Price Text: {price_text}")
            except Exception:
                print("Error locating price node:", e)

            # RATING 
            try:
                rating_node = card.locator("span.hotelRating__rating").first 
                print("Located rating node:", rating_node) 
                rating_text = await rating_node.text_content(timeout=4000) 
                print("Price Text:", rating_text)
            except Exception as e:
                print("Error locating rating node:", e)

            # LINK
            try:
                link = await card.locator("a").first.get_attribute("href")
                print(f"Hotel Link: {link}")
            except Exception:
                link = None

            # PRICE CLEANING
            price = re.sub(r"[^\d]", "", price_text) if price_text else None
            print(f"Cleaned Price: {price}")

            results.append({
                "name": name,
                "price": f"₹{price}" if price else None,
                "rating": rating_text if rating_text else None,
                "url": "https://www.oyorooms.com" + link if link else None
            })
            print(f"Extracted data: {results[-1]}")
            print(f"Scraped hotel {i+1} successfully ✔\n")

        except Exception as e:
            print(f"❌ Error scraping hotel {i+1}: {e}\n")
            continue

    print("Scraping complete ✔")

    await browser.close()
    return results
