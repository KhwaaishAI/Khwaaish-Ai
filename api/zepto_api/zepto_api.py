from fastapi import APIRouter
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uuid
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.zepto.zepto_automation import (
    login_zepto,
    enter_otp_zepto,
    search_products_zepto,
    add_to_cart_and_checkout,
)
from app.prompts.zepto_prompts.zepto_prompts import analyze_query

router = APIRouter()

# In-memory storage for browser sessions.
# Note: This is not suitable for production with multiple server workers.
sessions = {}

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36"
)
DEFAULT_VIEWPORT = {"width": 1366, "height": 900}
DEFAULT_GEOLOCATION = {"latitude": 19.0760, "longitude": 72.8777}
HEADLESS_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
]


class LoginRequest(BaseModel):
    mobile_number: str
    location: str

class OtpRequest(BaseModel):
    session_id: str
    otp: str

class SearchRequest(BaseModel):
    query: str
    max_items: int | None = 20

class AddToCartRequest(BaseModel):
    product_name: str
    quantity: int = 1
    upi_id: str | None = None
    hold_seconds: int | None = 0
    
@router.post("/zepto/login")
async def login(request: LoginRequest):
    session_id = str(uuid.uuid4())
    try:
        playwright = await async_playwright().start()
        browser, page = await login_zepto(request.mobile_number, request.location, playwright)
        sessions[session_id] = {"playwright": playwright, "browser": browser, "page": page}
        return {"status": "success", "message": "Login process initiated. Use the session_id to enter OTP.", "session_id": session_id}
    except Exception as e:
        try:
            if 'playwright' in locals():
                await playwright.stop()
        except Exception:
            pass
        return {"status": "error", "message": str(e)}

@router.post("/zepto/enter-otp")
async def enter_otp(request: OtpRequest):
    session = sessions.get(request.session_id)
    if not session:
        return {"status": "error", "message": "Invalid or expired session_id."}
    
    page = session["page"]

    # Define the path for storing session data
    session_dir = os.path.join(os.path.dirname(__file__), "session_data")
    os.makedirs(session_dir, exist_ok=True)
    storage_path = os.path.join(session_dir, f"zepto_session_{request.session_id}.json")

    try:
        await enter_otp_zepto(page, request.otp)
        # Save storage state to a file
        await page.context.storage_state(path=storage_path)
        return {"status": "success", "message": f"OTP submitted and session saved to {storage_path}."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        # Always close the browser and clean up the session
        await session["browser"].close()
        await session["playwright"].stop()
        if request.session_id in sessions:
            del sessions[request.session_id]


async def _open_zepto_page(playwright, storage_state_path: str):
    """Launch Chromium in headless mode with human-like settings and return (browser, page)."""
    browser = await playwright.chromium.launch(
        headless=True,
        slow_mo=50,
        args=HEADLESS_ARGS,
    )
    context = await browser.new_context(
        storage_state=storage_state_path,
        viewport=DEFAULT_VIEWPORT,
        user_agent=DESKTOP_USER_AGENT,
        locale="en-US",
        timezone_id="Asia/Kolkata",
        geolocation=DEFAULT_GEOLOCATION,
        permissions=["geolocation"],
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = await context.new_page()
    await page.goto("https://www.zeptonow.com/", wait_until="domcontentloaded")
    return browser, page

@router.post("/zepto/search")
async def search(request: SearchRequest):
    session_dir = os.path.join(os.path.dirname(__file__), "session_data")
    
    # Find the most recent session file
    try:
        session_files = [os.path.join(session_dir, f) for f in os.listdir(session_dir) if f.startswith("zepto_session_") and f.endswith(".json")]
        if not session_files:
            return {"status": "error", "message": "No saved login sessions found. Please log in first."}
        
        latest_session_file = max(session_files, key=os.path.getmtime)
        print(f"Using latest session file: {latest_session_file}")
    except FileNotFoundError:
        return {"status": "error", "message": "Session data directory not found. Please log in first."}

    try:
        async with async_playwright() as p:
            browser, page = await _open_zepto_page(p, latest_session_file)
            products = await search_products_zepto(page, request.query, max_items=(request.max_items or 20))
            await browser.close()
        return {"status": "success", "products": products}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/zepto/add-to-cart")
async def add_to_cart(request: AddToCartRequest):
    session_dir = os.path.join(os.path.dirname(__file__), "session_data")
    try:
        session_files = [os.path.join(session_dir, f) for f in os.listdir(session_dir) if f.startswith("zepto_session_") and f.endswith(".json")]
        if not session_files:
            return {"status": "error", "message": "No saved login sessions found. Please log in first."}
        latest_session_file = max(session_files, key=os.path.getmtime)
        print(f"Using latest session file: {latest_session_file}")
    except FileNotFoundError:
        return {"status": "error", "message": "Session data directory not found. Please log in first."}

    try:
        async with async_playwright() as p:
            browser, page = await _open_zepto_page(p, latest_session_file)
            await add_to_cart_and_checkout(page, request.product_name, request.quantity, request.upi_id, None)
            # Keep the browser open for the user to approve the payment on phone (if requested)
            if request.hold_seconds and request.hold_seconds > 0:
                await page.wait_for_timeout(request.hold_seconds * 1000)
            await browser.close()
        return {
            "status": "success",
            "message": "Item added to cart and proceeded to Click to Pay.",
            "upi_status": "provided" if request.upi_id else "not_provided",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
