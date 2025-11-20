from fastapi import APIRouter
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uuid
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.zepto.zepto_automation import automate_zepto, login_zepto, enter_otp_zepto, search_with_saved_session
from app.prompts.zepto_prompts.zepto_prompts import analyze_query

router = APIRouter()

# In-memory storage for browser sessions.
# Note: This is not suitable for production with multiple server workers.
sessions = {}


class LoginRequest(BaseModel):
    mobile_number: str
    location: str

class OtpRequest(BaseModel):
    session_id: str
    otp: str

class SearchRequest(BaseModel):
    query: str
    
@router.post("/zepto/login")
async def login(request: LoginRequest):
    session_id = str(uuid.uuid4())
    try:
        playwright = await async_playwright().start()
        browser, page = await login_zepto(request.mobile_number, request.location, playwright)
        sessions[session_id] = {"playwright": playwright, "browser": browser, "page": page}
        return {"status": "success", "message": "Login process initiated. Use the session_id to enter OTP.", "session_id": session_id}
    except Exception as e:
        if 'playwright' in locals() and playwright.is_connected():
            await playwright.stop()
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

    shopping_list = analyze_query(request.query)
    if not shopping_list:
        return {"status": "error", "message": "Could not understand or parse the query."}

    try:
        async with async_playwright() as p:
            await search_with_saved_session(shopping_list, latest_session_file, p)
        return {"status": "success", "message": "Search and add to cart process completed successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
