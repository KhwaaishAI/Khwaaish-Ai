import re
import asyncio
from playwright.async_api import TimeoutError
from urllib.parse import quote_plus
import sys
import os

# Add the root directory to the Python path to enable imports from other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.prompts.zepto_prompts.zepto_prompts import find_best_match

# Headless-friendly browser settings (align with API usage)
DESKTOP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
DEFAULT_VIEWPORT = {"width": 1366, "height": 768}
DEFAULT_GEOLOCATION = {"latitude": 19.0760, "longitude": 72.8777}
HEADLESS_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-web-security",
]

async def _click_robust(page, candidates: list[tuple[str, any]], timeout: int = 5000):
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

async def search_and_add_item(page, item_name: str, quantity: int):
    """Searches for an item, selects the best match, and adds it to the cart."""
    print(f"\nProcessing item: '{item_name}' (Quantity: {quantity})")
    
    search_url = f"https://www.zeptonow.com/search?query={quote_plus(item_name)}"
    print(f"- Navigating to search page: {search_url}")
    await page.goto(search_url)

    try:
        product_card_selector = 'a.B4vNQ'
        await page.wait_for_selector(product_card_selector, timeout=15000)
        print("- Product results page loaded successfully.")
    except TimeoutError:
        print(f"⚠️ Could not find any products for '{item_name}' on the page. Skipping.")
        return

    product_locator = page.locator(product_card_selector)
    count = await product_locator.count()
    scraped_products = []
    analyze_count = min(count, 10)
    print(f"- Found {count} products. Analyzing top {analyze_count}.")

    for i in range(analyze_count):
        card = product_locator.nth(i)
        try:
            name_elem = card.locator('div[data-slot-id="ProductName"] span').first
            price_elem = card.locator('div[data-slot-id="EdlpPrice"] span').first
            
            if not await name_elem.is_visible(timeout=1000) or not await price_elem.is_visible(timeout=1000):
                continue
            
            name = (await name_elem.text_content(timeout=2000)).strip()
            price_text = (await price_elem.text_content(timeout=2000)).strip()
            price = float(re.sub(r'[^\d.]', '', price_text))
            
            scraped_products.append({'name': name, 'price': price, 'card': card})
        except Exception:
            continue 

    selected_card = None
    if scraped_products:
        best_match_product = find_best_match(item_name, scraped_products)
        
        if not best_match_product:
            print("- No match found, falling back to the cheapest product.")
            scraped_products.sort(key=lambda p: p['price'])
            best_match_product = scraped_products[0] if scraped_products else None

        if best_match_product:
            selected_card = best_match_product['card']
            print(f"- Final selection: '{best_match_product['name']}' at ₹{best_match_product['price']}")
    else:
        # Scraping failed but product cards exist; fall back to first visible card.
        if count == 0:
            print(f"⚠️ No product cards available for '{item_name}'. Skipping.")
            return
        selected_card = product_locator.nth(0)
        print(f"⚠️ Could not scrape product details for '{item_name}'. Falling back to first product card.")
    
    try:
        await _click_robust(
            page,
            [
                ("Card 'ADD' button by text", selected_card.get_by_role("button", name=re.compile(r"^ADD$", re.I)).first),
                ("Card 'ADD' by data attribute", selected_card.locator('button[data-show-variant-selector="false"]').first),
                ("Card 'ADD' by class variant 1", selected_card.locator('button.ciE0m4.c2lTrV.cuPUm6.cnCei3').first),
                ("Card 'ADD' by class variant 2", selected_card.locator('button.ciE0m4.c2lTrV.cuPUm6.cVtNX5').first),
            ],
            timeout=6000,
        )
        print("- Clicked 'ADD' once.")
        await page.wait_for_timeout(1000)
        
        # Check if Super Saver popup appeared and close it
        try:
            close_button = page.locator('button.absolute.right-3').first
            if await close_button.is_visible(timeout=2000):
                print("- Super Saver popup detected, closing it...")
                await close_button.click(timeout=5000)
                await page.wait_for_timeout(500)
        except Exception:
            pass
        
        if quantity > 1:
            for i in range(quantity - 1):
                plus_button = page.locator('button.cG8zC0[aria-label="Increase quantity"]').first
                await plus_button.click(timeout=5000)
                print(f"- Clicked '+' ({i+2}/{quantity})")
                await page.wait_for_timeout(300)
        print(f"✅ Successfully added {quantity} of '{item_name}' to cart.")

    except Exception as e:
        print(f"❌ An unexpected error occurred while adding to cart: {e}")

async def search_products_zepto(page, query: str, max_items: int = 20):
    """Navigate to Zepto search and return a list of products with name and price."""
    search_url = f"https://www.zeptonow.com/search?query={quote_plus(query)}"
    print(f"- Navigating to search page: {search_url}")
    await page.goto(search_url)
    await _ensure_location_selected(page)

    product_card_selector = 'a.B4vNQ'
    for attempt in range(2):
        try:
            await page.wait_for_selector(product_card_selector, timeout=15000)
            break
        except TimeoutError:
            if attempt == 0:
                print("⚠️ Product cards not visible yet. Trying to re-confirm location and retry search once more.")
                await _ensure_location_selected(page, force_click=True)
                await page.reload()
                continue
            print("⚠️ No product cards rendered for Zepto search even after retry.")
            return []

    product_locator = page.locator(product_card_selector)
    count = await product_locator.count()
    scraped = []
    for i in range(min(count, max_items)):
        card = product_locator.nth(i)
        try:
            name_elem = card.locator('div[data-slot-id="ProductName"] span').first
            price_elem = card.locator('div[data-slot-id="EdlpPrice"] span').first
            if not await name_elem.is_visible(timeout=1000) or not await price_elem.is_visible(timeout=1000):
                continue
            name = (await name_elem.text_content(timeout=2000)).strip()
            price_text = (await price_elem.text_content(timeout=2000)).strip()
            price = float(re.sub(r'[^\d.]', '', price_text))
            scraped.append({"name": name, "price": price})
        except Exception:
            continue
    if not scraped:
        print("⚠️ Scraper could not extract product name/price despite cards being present. Check selectors.")
    return scraped

async def add_to_cart_and_checkout(page, product_name: str, quantity: int, upi_id: str | None = None, address_details: dict | None = None):
    """Add a specific product then open cart, resolve address, click Click to Pay, and optionally auto-complete UPI."""
    await search_and_add_item(page, product_name, quantity)
    # Cart button
    await _click_robust(
        page,
        [
            ("cart button [data-testid=cart-btn]", page.locator('button[data-testid="cart-btn"]').first),
            ("Cart button by aria-label", page.get_by_role("button", name="Cart").first),
        ],
        timeout=7000,
    )
    await page.wait_for_timeout(1000)

    await _handle_address_requirement(page, address_details)

    # Click to Pay
    await _click_robust(
        page,
        [
            ("Click to Pay primary button (class)", page.locator('button.my-2\\.5.h-\\[52px\\].w-full.rounded-xl.text-center.bg-skin-primary').first),
            ("Click to Pay by text", page.get_by_role("button", name=re.compile(r"Click to Pay", re.I)).first),
        ],
        timeout=7000,
    )

    await _handle_address_requirement(page, address_details)

    upi_status = "not_requested"
    if upi_id:
        print("- UPI ID provided; attempting to complete payment via UPI.")
        success = await _handle_upi_payment(page, upi_id)
        upi_status = "completed" if success else "not_found"
        if success:
            print("✅ UPI Verify and Pay clicked successfully.")
        else:
            print("⚠️ Could not automatically locate UPI controls after Click to Pay.")
    else:
        print("ℹ️ No UPI ID supplied in request; leaving payment screen for manual completion.")
    return {"added": True, "upi_status": upi_status}

async def _handle_address_requirement(page, address_details: dict | None):
    """Ensures an address is selected by prioritizing saved cards, else adds new if data provided."""
    selected = await _select_saved_address_if_needed(page)
    if selected:
        return True
    if address_details:
        added = await _add_address_if_form_present(page, address_details)
        if added:
            return True
    return False


async def _open_location_picker(page, timeout: int = 6000) -> bool:
    """Try multiple triggers to open Zepto's location/search dialog."""
    async def _dialog_visible(timeout_ms: int = 1200) -> bool:
        try:
            await page.wait_for_selector('input[placeholder="Search a new address"]', timeout=timeout_ms, state="visible")
            return True
        except Exception:
            try:
                await page.wait_for_selector('div[data-testid="address-search-container"]', timeout=timeout_ms, state="visible")
                return True
            except Exception:
                try:
                    await page.wait_for_selector('div[role="dialog"]', timeout=timeout_ms, state="visible")
                    return True
                except Exception:
                    pass
            return False

    try:
        if await _dialog_visible():
            return True

        await page.wait_for_timeout(300)
        try:
            await page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass

        # Ensure page hydrated: wait for logo or Next.js data, reload once if not present
        try:
            hydrated = False
            try:
                await page.wait_for_selector('a[data-testid="zepto-logo"]', timeout=2000)
                hydrated = True
            except Exception:
                pass
            if not hydrated:
                try:
                    await page.wait_for_function("() => !!window.__NEXT_DATA__", timeout=2000)
                    hydrated = True
                except Exception:
                    pass
            if not hydrated:
                await page.reload(wait_until='domcontentloaded')
                await page.wait_for_timeout(500)
        except Exception:
            pass

        # Dismiss possible overlays/banners that may block header clicks
        try:
            await _click_robust(
                page,
                [
                    ("Cookie accept button", page.locator('button:has-text("Accept")').first),
                    ("Cookie allow button", page.locator('button:has-text("Allow")').first),
                    ("Got it button", page.locator('button:has-text("Got it")').first),
                    ("OK button", page.locator('button:has-text("OK")').first),
                    ("Close toast", page.locator('button[aria-label="Close"], svg[aria-label="Close"]').first),
                ],
                timeout=1200,
            )
        except Exception:
            pass

        # Wait for any header location button/address chip to render before attempting clicks.
        await page.wait_for_timeout(300)
        try:
            await page.wait_for_selector(
                'div.__6VhjW, button[aria-haspopup="dialog"][aria-label], button[aria-label="Select Location"], h3[data-testid="user-address"], button.__4y7HY, span.cTJX6L',
                timeout=timeout,
            )
        except Exception:
            pass

        candidates = [
            ("Header container-scoped dialog button", page.locator('div.__6VhjW').locator('button[aria-haspopup="dialog"]').first),
            ("Header dialog button w/aria-label", page.locator('button[aria-haspopup="dialog"][aria-label]').first),
            ("Header Select Location button", page.locator('button[aria-label="Select Location"]').first),
            ("Header button containing user-address chip", page.locator('button:has(h3[data-testid="user-address"])').first),
            ("H3 user-address chip", page.locator('h3[data-testid="user-address"]').first),
            ("Header location role button", page.get_by_role("button", name=re.compile(r"Select Location|Deliver", re.I)).first),
            ("Header __4y7HY button", page.locator('button.__4y7HY').first),
            ("Generic span chip", page.locator('span.cTJX6L').first),
            ("Delivery In container", page.locator('div[data-testid="delivery-time"]').locator('..').locator('button').first),
        ]

        # Debug: log candidate availability counts
        try:
            for desc, loc in candidates:
                try:
                    cnt = await loc.count()
                    print(f"[DBG] Candidate '{desc}' count: {cnt}")
                except Exception:
                    print(f"[DBG] Candidate '{desc}' count: error")
        except Exception:
            pass

        for attempt in range(4):
            for desc, locator in candidates:
                try:
                    if await locator.count() == 0:
                        continue
                    await locator.scroll_into_view_if_needed()
                    try:
                        await locator.click(timeout=timeout)
                    except Exception:
                        await locator.click(timeout=timeout, force=True)
                    print(f"➡️ Triggered location dialog via {desc} (attempt {attempt + 1}).")
                    await page.wait_for_timeout(800)
                    if await _dialog_visible(2500):
                        return True
                except Exception:
                    continue

            # Bounding-box fallback using mouse for the primary dialog button.
            primary_chip = page.locator('button[aria-haspopup="dialog"][aria-label]').first
            try:
                if await primary_chip.count() > 0:
                    box = await primary_chip.bounding_box()
                    if box:
                        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        await page.wait_for_timeout(800)
                        if await _dialog_visible(2500):
                            print("➡️ Triggered location dialog via mouse bounding-box fallback.")
                            return True
            except Exception:
                pass

            # Coordinate-based click using DOM bounding rect via JS (more resilient in headless)
            try:
                coords = await page.evaluate(
                    """
                    () => {
                        const header = document.querySelector('div.__6VhjW');
                        const btn = header ? header.querySelector('button[aria-haspopup="dialog"]') : null;
                        const target = btn || document.querySelector('button[aria-haspopup="dialog"][aria-label]') || document.querySelector('button.__4y7HY');
                        if (!target) return null;
                        const r = target.getBoundingClientRect();
                        return { x: Math.floor(r.left + r.width/2), y: Math.floor(r.top + r.height/2) };
                    }
                    """
                )
                if coords and isinstance(coords.get("x"), (int, float)) and isinstance(coords.get("y"), (int, float)):
                    await page.mouse.click(coords["x"], coords["y"])
                    await page.wait_for_timeout(800)
                    if await _dialog_visible(2500):
                        print("➡️ Triggered location dialog via coordinate-based click.")
                        return True
            except Exception:
                pass

            # Focus + Enter fallback
            try:
                if await primary_chip.count() > 0:
                    await primary_chip.focus()
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(600)
                    if await _dialog_visible(2500):
                        print("➡️ Triggered location dialog via keyboard Enter fallback.")
                        return True
            except Exception:
                pass

            # Keyboard Tab-walk fallback: focus header then Tab to the chip and Enter
            try:
                await page.keyboard.press("Home")
                for _ in range(5):
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(150)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(800)
                if await _dialog_visible(2500):
                    print("➡️ Triggered location dialog via keyboard Tab-walk fallback.")
                    return True
            except Exception:
                pass

            clicked_via_eval = await page.evaluate(
                """
                () => {
                    const selectors = [
                        'button[aria-haspopup="dialog"][aria-label]',
                        'button[aria-label="Select Location"]',
                        'button.__4y7HY',
                        '[data-testid="user-address"]',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            try {
                                const evt = new MouseEvent('click', {bubbles:true,cancelable:true,view:window});
                                el.dispatchEvent(evt);
                                if (typeof el.click === 'function') el.click();
                                return true;
                            } catch(e) {}
                        }
                    }
                    const header = document.querySelector('div.__6VhjW');
                    const btn = header ? header.querySelector('button[aria-haspopup="dialog"]') : null;
                    if (btn) {
                        try {
                            const evt = new MouseEvent('click', {bubbles:true,cancelable:true,view:window});
                            btn.dispatchEvent(evt);
                            if (typeof btn.click === 'function') btn.click();
                            return true;
                        } catch(e) {}
                    }
                    return false;
                }
                """
            )
            if clicked_via_eval:
                await page.wait_for_timeout(800)
                if await _dialog_visible(2500):
                    print("➡️ Triggered location dialog via JS fallback.")
                    return True

            print(f"⚠️ Attempt {attempt + 1} failed to open location dialog; retrying...")
            await page.wait_for_timeout(600)
        return False
    except Exception as exc:
        print(f"⚠️ Unable to click location picker automatically: {exc}")
        return False


async def _select_location_from_search(page, location: str, suggestion_index: int = 0) -> bool:
    """Open the location dialog, type the query, click a suggestion, and confirm."""
    # If header already shows an address (not "Select Location"), proceed.
    try:
        header_text = await page.locator('h3[data-testid="user-address"]').first.text_content(timeout=1500)
        print(f"[DBG] Header user-address text: {header_text!r}")
        if header_text and 'select location' not in header_text.lower():
            print("ℹ️ Header already shows a selected address; proceeding without reopening dialog.")
            return True
    except Exception:
        pass

    opened = await _open_location_picker(page)
    if not opened:
        # Try one more time: if address is visible, accept it and proceed.
        try:
            header_text = await page.locator('h3[data-testid="user-address"]').first.text_content(timeout=1500)
            print(f"[DBG] Retry header user-address text: {header_text!r}")
            if header_text and 'select location' not in header_text.lower():
                print("ℹ️ Using already-selected header address as location.")
                return True
        except Exception:
            pass
        try:
            search_link = page.locator('a[data-testid="search-bar-icon"]').first
            if await search_link.count() > 0:
                await search_link.click()
                await page.wait_for_load_state('domcontentloaded')
                await page.wait_for_timeout(600)
                opened = await _open_location_picker(page, timeout=8000)
        except Exception:
            pass
        if not opened:
            # Direct navigation to search page as last resort, then retry open
            try:
                await page.goto('https://www.zeptonow.com/search', wait_until='domcontentloaded')
                await page.wait_for_timeout(800)
                opened = await _open_location_picker(page, timeout=8000)
            except Exception:
                pass
        if not opened:
            return False

    try:
        location_input = page.get_by_placeholder("Search a new address")
        await location_input.wait_for(state="visible", timeout=5000)
        await location_input.click()
        await location_input.fill(location)
        print("✅ Location entered.")

        suggestions = page.locator('div[data-testid="address-search-item"]')
        await suggestions.first.wait_for(state="visible", timeout=8000)
        await page.wait_for_timeout(500)
        suggestion = suggestions.nth(suggestion_index)
        await suggestion.click()
        print("✅ Location suggestion selected.")
        await page.wait_for_timeout(1000)

        try:
            await _click_robust(
                page,
                [
                    ("Confirm & Continue [data-testid]", page.get_by_test_id("location-confirm-btn")),
                    ("Confirm & Continue button text", page.locator('button:has-text("Confirm & Continue")').first),
                    ("Confirm & Continue role button", page.get_by_role("button", name=re.compile(r"Confirm .* Continue", re.I)).first),
                ],
                timeout=6000,
            )
            print("✅ Location confirmed via 'Confirm & Continue'.")
            await page.wait_for_timeout(1000)
        except Exception:
            print("ℹ️ Confirm button not found; assuming location already applied.")
        return True
    except Exception as exc:
        print(f"❌ Failed to select location: {exc}")
        return False


async def _ensure_location_selected(page, force_click: bool = False):
    """Ensure Zepto shows products by selecting an existing saved address/location."""
    try:
        triggers = [
            ("Select Location header button", page.locator('button:has-text("Select Location")').first),
            ("Deliver to location CTA", page.locator('button:has-text("Deliver Here")').first),
            ("Add address to proceed button", page.locator('button:has-text("Add address to proceed")').first),
        ]

        if force_click:
            for desc, loc in triggers:
                try:
                    await loc.click(timeout=1500)
                    print(f"➡️ Triggered location dialog via {desc}.")
                    break
                except Exception:
                    continue
        else:
            for desc, loc in triggers:
                try:
                    if await loc.is_visible(timeout=1000):
                        await loc.click()
                        print(f"➡️ Location selector opened via {desc}.")
                        break
                except Exception:
                    continue

        await _handle_address_requirement(page, None)
    except Exception as exc:
        print(f"⚠️ Unable to auto-select Zepto location: {exc}")

async def _select_saved_address_if_needed(page, timeout: int = 6000):
    """If the address chooser modal appears, select the first saved address and confirm."""
    try:
        modal_locator = page.locator('div:has-text("Select an Address")').first
        try:
            await modal_locator.wait_for(state="visible", timeout=timeout)
        except Exception:
            try:
                await _click_robust(
                    page,
                    [
                        ("Add address to proceed button", page.locator('button:has-text("Add address to proceed")').first),
                        ("Add address footer button", page.locator('button:has-text("Add Address to proceed")').first),
                    ],
                    timeout=4000,
                )
                await modal_locator.wait_for(state="visible", timeout=timeout)
            except Exception:
                return False
        # Prefer the saved address tile within the saved list container
        saved_tile = modal_locator.locator('div.fsVuP div.cgG1vl').first
        await saved_tile.wait_for(state="visible", timeout=2000)
        await saved_tile.click()
        print("✅ Selected the first saved address from the modal.")
        await page.wait_for_timeout(500)
        try:
            # Click the Save Address button in the modal after choosing the tile
            await _click_robust(
                page,
                [
                    ("Save Address button in modal", modal_locator.locator('button:has-text("Save Address")').first),
                    ("Save Address button global fallback", page.locator('button:has-text("Save Address")').first),
                ],
                timeout=4000,
            )
            print("✅ Clicked 'Save Address' in the address modal.")
            await page.wait_for_timeout(800)
        except Exception:
            pass
        try:
            await _click_robust(
                page,
                [
                    ("Confirm & Continue modal button", page.locator('button.cpG2SV.cdW7ko.c0WLye.cBCT4J').first),
                    ("Confirm & Continue [data-testid]", page.get_by_test_id("location-confirm-btn")),
                ],
                timeout=4000,
            )
            print("✅ Confirmed address via 'Confirm & Continue'.")
            await page.wait_for_timeout(1000)
        except Exception:
            pass
        return True
    except Exception:
        return False

async def _add_address_if_form_present(page, address_details: dict | None, timeout: int = 5000):
    """Fill and save the Add Address form when address details are provided."""
    if not address_details:
        return False

    modal_selector = 'div:has-text("Add Address Details")'
    modal = page.locator(modal_selector).first

    async def _ensure_modal_visible():
        try:
            await modal.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            try:
                await _click_robust(
                    page,
                    [
                        ("Add Address to proceed button", page.locator('button:has-text("Add Address to proceed")').first),
                        ("Add New Address option", page.locator('div:has-text("Add New Address")').first),
                    ],
                    timeout=3000,
                )
                await page.wait_for_timeout(800)
                await modal.wait_for(state="visible", timeout=timeout)
                return True
            except Exception:
                return False

    if not await _ensure_modal_visible():
        return False

    tag = (address_details.get("tag") or "").strip()
    if tag:
        try:
            await _click_robust(
                page,
                [
                    (f"Save address as {tag}", modal.locator(f'button:has-text("{tag}")').first),
                    (f"Save address label {tag}", modal.locator(f'label:has-text("{tag}")').first),
                ],
                timeout=3000,
            )
        except Exception:
            pass

    building_type = (address_details.get("building_type") or "").strip()
    if building_type:
        try:
            await _click_robust(
                page,
                [
                    (f"Building type {building_type}", modal.locator(f'button:has-text("{building_type}")').first),
                    (f"Building type label {building_type}", modal.locator(f'label:has-text("{building_type}")').first),
                ],
                timeout=3000,
            )
        except Exception:
            pass

    async def _fill_field(selector: str, value: str | None, description: str):
        if not value:
            return
        try:
            field = modal.locator(selector).first
            await field.wait_for(state="visible", timeout=2000)
            await field.fill(value)
            print(f"   - Filled {description}: {value}")
        except Exception:
            print(f"⚠️ Unable to fill {description} (selector {selector}).")

    await _fill_field('input[name="flatDetails"]', address_details.get("flat_details"), "Flat/Floor")
    await _fill_field('input[name="buildingName"]', address_details.get("building_name"), "Building name")
    await _fill_field('input[name="landmark"]', address_details.get("landmark"), "Landmark")
    await _fill_field('input[name="receiverName"]', address_details.get("receiver_name"), "Receiver name")

    try:
        await _click_robust(
            page,
            [
                ("Save Address button", modal.locator('button:has-text("Save Address")').first),
                ("Save Address button (fallback)", page.locator('button:has-text("Save Address")').first),
            ],
            timeout=5000,
        )
        print("✅ Address form submitted via 'Save Address'.")
    except Exception:
        return False

    try:
        await modal.wait_for(state="hidden", timeout=8000)
    except Exception:
        pass
    await page.wait_for_timeout(1500)
    return True

async def _handle_upi_payment(page, upi_id: str | None) -> bool:
    """Attempt to select UPI option, fill VPA, and click Verify & Pay."""
    if not upi_id:
        return False
    await asyncio.sleep(2)
    context = page.context
    for attempt in range(4):
        surfaces = []
        for p in context.pages:
            surfaces.append(p)
            for frame in p.frames:
                if frame is not p.main_frame:
                    surfaces.append(frame)
        for surface in surfaces:
            try:
                if await _try_upi_on_surface(surface, upi_id):
                    return True
            except Exception:
                continue
        await asyncio.sleep(1.5)
    return False

async def _try_upi_on_surface(surface, upi_id: str) -> bool:
    """Attempt the UPI flow on a specific page/frame surface."""
    upi_candidates = [
        ("UPI nav icon", surface.locator('[testid="nvb_icon_upi"]').first),
        ("UPI nav row", surface.locator('div:has([testid="nvb_icon_upi"])').first),
        ("UPI nav text", surface.locator('div:has-text("UPI")').first),
    ]
    upi_clicked = False
    for desc, locator in upi_candidates:
        try:
            await locator.wait_for(state="visible", timeout=2000)
            await locator.scroll_into_view_if_needed()
            await locator.click(timeout=2000)
            print(f"✅ Selected UPI option via {desc}.")
            upi_clicked = True
            break
        except Exception:
            continue
    if not upi_clicked:
        return False

    await asyncio.sleep(0.3)
    input_candidates = [
        ("UPI input [testid]", surface.locator('input[testid="edt_vpa"]').first),
        ("UPI input by id", surface.locator('#20000267').first),
        ("UPI input by placeholder", surface.locator('input[placeholder*="upi"]').first),
    ]
    filled = False
    for desc, locator in input_candidates:
        try:
            await locator.wait_for(state="visible", timeout=2000)
            await locator.fill(upi_id)
            print(f"✅ Filled UPI ID via {desc}.")
            filled = True
            break
        except Exception:
            continue
    if not filled:
        return False

    await asyncio.sleep(0.3)
    verify_candidates = [
        ("Verify button [testid]", surface.locator('[testid="btn_enabled"]').first),
        ("Verify div role button", surface.locator('div[role="button"]:has-text("Verify and Pay")').first),
        ("Verify button element", surface.locator('button:has-text("Verify and Pay")').first),
        ("Verify text", surface.locator('text="Verify and Pay"').first),
    ]
    for desc, locator in verify_candidates:
        try:
            await locator.wait_for(state="visible", timeout=4000)
            await locator.scroll_into_view_if_needed()
            try:
                await locator.click(timeout=4000)
            except Exception:
                try:
                    await locator.focus()
                    await locator.press("Enter")
                except Exception:
                    continue
            print(f"✅ Clicked {desc}.")
            return True
        except Exception:
            continue
    return False
async def automate_zepto(shopping_list: dict, location: str, mobile_number: str, p):
    """
    Launches Playwright, navigates to Zepto, sets location, and processes the shopping list.
    """
    print("\nStep 2: Starting browser automation with Playwright for Zepto...")
    browser = await p.chromium.launch(headless=True, slow_mo=100)
    context = await browser.new_context()
    page = await context.new_page()

    try:
        print("➡️ Navigating to https://www.zeptonow.com/")
        await page.goto("https://www.zeptonow.com/")
        await page.wait_for_load_state('networkidle')
        print("✅ Zepto homepage loaded.")

        print("\n➡️ Clicking on 'Select Location' button...")
        select_location_button = page.get_by_text("Select Location").first
        await select_location_button.click()
        print("✅ 'Select Location' button clicked.")

        print(f"\n➡️ Typing location '{location}' into the search bar...")
        location_input = page.get_by_placeholder("Search a new address")
        await location_input.fill(location)
        print("✅ Location entered.")

        print("\n➡️ Waiting for location suggestions and selecting the first one...")
        first_suggestion_selector = 'div[data-testid="address-search-item"]'
        await page.wait_for_selector(first_suggestion_selector, timeout=10000)
        print("✅ Suggestions appeared.")
        
        await page.locator(first_suggestion_selector).first.click()
        print("✅ First location suggestion selected.")

        print("\n➡️ Clicking 'Confirm & Continue'...")
        confirm_button_selector = "button.cpG2SV.cdW7ko.c0WLye.cBCT4J"
        await page.locator(confirm_button_selector).click()
        print("✅ Location confirmed and set successfully!")
        
        print("\nWaiting for page to load...")
        await page.wait_for_timeout(4000)

        print("\nStep 3: Preparing to add items to cart...")
        for item, quantity in shopping_list.items():
            await search_and_add_item(page, item, quantity)
        
        print("-----------------------------------------")
        print("\n✅ All items processed. Cart should be ready.")
        
        print("\nStep 4: Clicking on cart button...")
        try:
            cart_button = page.locator('button[data-testid="cart-btn"]').first
            await cart_button.click(timeout=5000)
            print("✅ Cart button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking cart button: {e}")
            return
        
        print("\nStep 5: Clicking on 'Login' button...")
        try:
            login_button = page.locator('div.flex.items-center.justify-center h6').first
            await login_button.click(timeout=5000)
            print("✅ Login button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Login button: {e}")
            return
        
        print("\nStep 6: Entering phone number...")
        try:
            phone_input = page.locator('input[placeholder="Enter Phone Number"]').first
            await phone_input.fill(mobile_number)
            print("✅ Phone number entered successfully.")
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"❌ Error entering phone number: {e}")
            return
        
        print("\nStep 7: Clicking 'Continue' button...")
        try:
            continue_button = page.locator('button[type="button"]:has-text("Continue")').first
            await continue_button.click(timeout=5000)
            print("✅ Continue button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Continue button: {e}")
            return
        
        print("\nStep 8: Waiting for OTP entry (25 seconds)...")
        print("⏳ Please enter the OTP on the browser...")
        await asyncio.sleep(25)
        print("✅ OTP wait period completed.")
        
        print("\nStep 9: Clicking 'Add Address to proceed' button...")
        try:
            add_address_button = page.locator('button.my-2\\.5.h-\\[52px\\].w-full.rounded-xl.bg-skin-primary.text-center').first
            await add_address_button.click(timeout=5000)
            print("✅ Add Address button clicked successfully.")
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f"❌ Error clicking Add Address button: {e}")
            return
        
        print("\nStep 10: Selecting the first saved address...")
        try:
            first_address = page.locator('div.ctyATk').first
            await first_address.click(timeout=5000)
            print("✅ First address selected.")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"❌ Error selecting address: {e}")
            return
        
        print("\nStep 11: Clicking 'Click to Pay' button...")
        try:
            pay_button = page.locator('button.my-2\\.5.h-\\[52px\\].w-full.rounded-xl.text-center.bg-skin-primary').first
            await pay_button.click(timeout=5000)
            print("✅ 'Click to Pay' button clicked successfully.")
        except Exception as e:
            print(f"❌ Error clicking 'Click to Pay' button: {e}")
            return
        
        print("\n✅ Automation script finished.")
        print("Browser will close in 10 seconds.")
        await asyncio.sleep(10)

    except TimeoutError as e:
        print(f"❌ A timeout error occurred: {e}")
        print("   The script could not find an element in time. This might be due to a slow network or a change in the website's layout.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        await browser.close()
        print("\nBrowser closed. Script finished.")

async def login_zepto(mobile_number: str, location: str, playwright):
    """
    Launches Playwright, navigates to Zepto, sets location, and performs login.
    Returns the browser and page objects to continue the session.
    """
    print("\nStarting browser automation with Playwright for Zepto Login...")
    browser = await playwright.chromium.launch(headless=True, slow_mo=50, args=HEADLESS_ARGS)
    context = await browser.new_context(
        viewport=DEFAULT_VIEWPORT,
        user_agent=DESKTOP_USER_AGENT,
        locale="en-US",
        timezone_id="Asia/Kolkata",
        geolocation=DEFAULT_GEOLOCATION,
        permissions=["geolocation"],
    )
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = await context.new_page()

    try:
        print("➡️ Navigating to https://www.zeptonow.com/")
        await page.goto("https://www.zeptonow.com/")
        await page.wait_for_load_state('networkidle')
        print("✅ Zepto homepage loaded.")

        print(f"\n➡️ Setting location to '{location}'...")
        location_ok = await _select_location_from_search(page, location)
        if not location_ok:
            await browser.close()
            raise RuntimeError("Unable to set Zepto location from search dialog.")
        await page.wait_for_load_state('networkidle')


        print("\n➡️ Clicking on 'Login' button...")
        await _click_robust(
            page,
            [
                ("Header login container [data-testid]", page.locator('div[data-testid="login-btn"]').first),
                ("Header login span", page.locator('span[data-testid="login-btn"]').first),
                ("Header login text", page.locator('div:has(span[data-testid="login-btn"]):has-text("login")').first),
                ("Header login by role", page.get_by_role("button", name=re.compile(r"login", re.I)).first),
            ],
            timeout=6000,
        )
        print("✅ Login button clicked successfully.")
        await page.wait_for_timeout(2000)

        print("\n➡️ Entering phone number...")
        try:
            phone_input = page.get_by_placeholder("Enter Phone Number")
            await phone_input.fill(mobile_number)
            print("✅ Phone number entered successfully.")
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"❌ Error entering phone number: {e}")
            await browser.close()
            raise

        print("\n➡️ Clicking 'Continue' button...")
        await _click_robust(
            page,
            [
                ("Gradient Continue button", page.locator('button:has(div:has-text("Continue"))').first),
                ("Rounded Continue button", page.locator('button.rounded-3xl:has-text("Continue")').first),
                ("Continue role button", page.get_by_role("button", name=re.compile(r"^Continue$", re.I)).first),
            ],
            timeout=7000,
        )
        print("✅ Continue button clicked successfully.")

        print("\n✅ Login initiated. Browser is waiting for OTP.")
        return browser, page

    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        await browser.close()
        print("\nBrowser closed due to error.")
        raise

async def enter_otp_zepto(page, otp: str):
    """
    Enters the OTP on the provided page.
    """
    print(f"\n➡️ Entering OTP: {otp}")
    try:
        # The OTP input is a single input field that visually looks like 6 boxes.
        # We can target it and fill it directly.
        otp_input_selector = 'input[inputmode="numeric"][maxlength="6"]'
        await page.wait_for_selector(otp_input_selector, timeout=10000)
        
        await page.locator(otp_input_selector).first.fill(otp)
        
        print("✅ OTP entered successfully.")
        await page.wait_for_timeout(5000) # Wait for login to complete

    except Exception as e:
        print(f"❌ Error entering OTP: {e}")
        raise

async def search_with_saved_session(shopping_list: dict, session_path: str, p):
    """
    Launches a browser, loads a saved session state, and processes a shopping list.
    """
    print("\nStarting browser automation with a saved session...")
    browser = await p.chromium.launch(headless=False, slow_mo=100)
    
    try:
        # Create a new context with the saved storage state
        context = await browser.new_context(storage_state=session_path)
        page = await context.new_page()
        
        print("➡️ Navigating to Zepto homepage to initialize session...")
        await page.goto("https://www.zeptonow.com/", wait_until="networkidle")
        print("✅ Homepage loaded with saved session.")

        print("\n➡️ Preparing to add items to cart...")
        for item, quantity in shopping_list.items():
            await search_and_add_item(page, item, quantity)
        
        print("\n✅ All items processed. The browser will close in 10 seconds.")
        await asyncio.sleep(10)

    finally:
        await browser.close()
        print("\nBrowser closed. Logged-in search finished.")
