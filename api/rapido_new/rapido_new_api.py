from fastapi import APIRouter
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uuid
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.rapido_new.rapido_automation import (
    book_ride_rapido,
    login_rapido,
    verify_otp_rapido,
)

router = APIRouter()

# In-memory storage for browser sessions.
# Note: This is not suitable for production with multiple server workers.
sessions = {}

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36"
)
DEFAULT_VIEWPORT = {"width": 1366, "height": 900}
HEADLESS_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
]


class RapidoBookRideRequest(BaseModel):
    pickup_location: str
    drop_location: str


class RapidoLoginRequest(BaseModel):
    session_id: str
    phone_number: str


class RapidoOtpRequest(BaseModel):
    session_id: str
    otp: str


async def _open_rapido_page(playwright):
    browser = await playwright.chromium.launch(
        headless=False,
        slow_mo=0,
        args=HEADLESS_ARGS,
    )
    context = await browser.new_context(
        viewport=DEFAULT_VIEWPORT,
        user_agent=DESKTOP_USER_AGENT,
        locale="en-US",
        timezone_id="Asia/Kolkata",
    )
    page = await context.new_page()
    return browser, page


@router.post("/rapido-new/book-ride")
async def rapido_book_ride(request: RapidoBookRideRequest):
    session_id = str(uuid.uuid4())
    try:
        playwright = await async_playwright().start()
        browser, page = await _open_rapido_page(playwright)
        sessions[session_id] = {"playwright": playwright, "browser": browser, "page": page}

        data = await book_ride_rapido(page, request.pickup_location, request.drop_location)

        return {
            "status": "success",
            "session_id": session_id,
            "data": data,
        }
    except Exception as e:
        # Best-effort cleanup
        try:
            if "browser" in locals():
                await browser.close()
        except Exception:
            pass
        try:
            if "playwright" in locals():
                await playwright.stop()
        except Exception:
            pass
        if session_id in sessions:
            del sessions[session_id]
        return {"status": "error", "message": str(e)}


@router.post("/rapido-new/login")
async def rapido_login(request: RapidoLoginRequest):
    session = sessions.get(request.session_id)
    if not session:
        return {"status": "error", "message": "Invalid or expired session_id."}

    page = session["page"]
    try:
        await login_rapido(page, request.phone_number)
        return {"status": "success", "message": "Phone number submitted, OTP requested."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/rapido-new/verify-otp")
async def rapido_verify_otp(request: RapidoOtpRequest):
    session = sessions.get(request.session_id)
    if not session:
        return {"status": "error", "message": "Invalid or expired session_id."}

    page = session["page"]
    try:
        await verify_otp_rapido(page, request.otp)
        return {"status": "success", "message": "OTP submitted. Browser kept open for 2 minutes."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        # After OTP wait completes inside automation, close browser & playwright and clear session
        try:
            await session["browser"].close()
        except Exception:
            pass
        try:
            await session["playwright"].stop()
        except Exception:
            pass
        if request.session_id in sessions:
            del sessions[request.session_id]
