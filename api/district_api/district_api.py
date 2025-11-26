from fastapi import APIRouter
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uuid
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.district.district_automation import (
    login_district,
    enter_otp_district,
    search_movie_district,
    book_show_district,
    buy_ticket_district,
    _select_location,
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


class DistrictLoginRequest(BaseModel):
    mobile_number: str
    location: str


class DistrictOtpRequest(BaseModel):
    session_id: str
    otp: str


class DistrictSearchRequest(BaseModel):
    session_id: str
    query: str


class DistrictBookShowRequest(BaseModel):
    session_id: str
    cinema_name: str
    show_time: str


class DistrictBuyTicketRequest(BaseModel):
    session_id: str
    seats: list[str]
    upi_id: str | None = None


@router.post("/district/login")
async def district_login(request: DistrictLoginRequest):
    session_id = str(uuid.uuid4())
    try:
        playwright = await async_playwright().start()
        browser, page = await login_district(request.mobile_number, request.location, playwright)
        sessions[session_id] = {"playwright": playwright, "browser": browser, "page": page}
        return {
            "status": "success",
            "message": "District login initiated. Use the session_id to enter OTP.",
            "session_id": session_id,
        }
    except Exception as e:
        try:
            if "playwright" in locals():
                await playwright.stop()
        except Exception:
            pass
        return {"status": "error", "message": str(e)}


@router.post("/district/enter-otp")
async def district_enter_otp(request: DistrictOtpRequest):
    session = sessions.get(request.session_id)
    if not session:
        return {"status": "error", "message": "Invalid or expired session_id."}

    page = session["page"]

    # Define the path for storing session data
    session_dir = os.path.join(os.path.dirname(__file__), "session_data")
    os.makedirs(session_dir, exist_ok=True)
    storage_path = os.path.join(session_dir, f"district_session_{request.session_id}.json")

    try:
        await enter_otp_district(page, request.otp)
        # Save storage state to a file (for reuse if needed)
        await page.context.storage_state(path=storage_path)
        return {
            "status": "success",
            "message": f"District OTP submitted and session saved to {storage_path}.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/district/search-movie")
async def district_search_movie(request: DistrictSearchRequest):
    session = sessions.get(request.session_id)
    if not session:
        return {"status": "error", "message": "Invalid or expired session_id."}

    page = session["page"]
    try:
        data = await search_movie_district(page, request.query)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/district/book-show")
async def district_book_show(request: DistrictBookShowRequest):
    session = sessions.get(request.session_id)
    if not session:
        return {"status": "error", "message": "Invalid or expired session_id."}

    page = session["page"]
    try:
        data = await book_show_district(page, request.cinema_name, request.show_time)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/district/buy-ticket")
async def district_buy_ticket(request: DistrictBuyTicketRequest):
    session = sessions.get(request.session_id)
    if not session:
        return {"status": "error", "message": "Invalid or expired session_id."}

    page = session["page"]
    try:
        result = await buy_ticket_district(page, request.seats, request.upi_id)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        # Close the browser and clean up the session at the end of the payment flow
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
