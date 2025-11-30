from fastapi import APIRouter
from pydantic import BaseModel
from playwright.async_api import async_playwright
import sys
import os

# Add root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.oyo.oyo_search_automation import automate_oyo_search
from app.agents.oyo.oyo_login_automation import oyo_login
from app.agents.oyo.oyo_session_manager import session_manager
from app.agents.oyo.oyo_otp_automation import verify_otp_automation

router = APIRouter()

class OyoSearchRequest(BaseModel):
    city: str
    country: str
    checkin: str
    checkout: str
    rooms: int
    guests: int

class OyoLoginRequest(BaseModel):
    phone_number: str

class OyoOtpRequest(BaseModel):
    api_session_id: str
    otp: str

@router.post("/oyo/search")
async def oyo_search(request: OyoSearchRequest):

    async with async_playwright() as p:
        results = await automate_oyo_search(
            p,
            city=request.city,
            country=request.country,
            checkin=request.checkin,
            checkout=request.checkout,
            rooms=request.rooms,
            guests=request.guests,
        )

    return {"status": "success", "results": results}


@router.post("/oyo/login")
async def oyo_login_api(request: OyoLoginRequest):
    try:
        login_data = await oyo_login(phone_number=request.phone_number)

        # Extract session cookies
        session_cookies = login_data.get("session_cookies", [])
        
        # Find the most likely session ID
        session_id_value = None
        preferred_names = ["sessionid", "SESSION", "sid", "auth_token"]
        
        for name in preferred_names:
            for cookie in session_cookies:
                if cookie["name"].lower() == name.lower():
                    session_id_value = cookie["value"]
                    break
            if session_id_value:
                break

        return {
            "status": "success",
            "api_session_id": login_data["session_id"],  # This is OUR session ID to track the browser
            "website_session_id": session_id_value,  # This is the website's session ID
            "session_cookies": session_cookies,
            "all_cookies_count": len(login_data["cookies"]),
            "message": "OTP sent successfully. Browser is kept open. Use api_session_id for OTP verification."
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Login failed: {str(e)}"
        }

@router.post("/oyo/verify-otp")
async def oyo_verify_otp(request: OyoOtpRequest):
    try:
        print(f"Looking for session: {request.api_session_id}")
        print(f"Available sessions: {list(session_manager.sessions.keys())}")
        
        # Get the browser session
        session_data = session_manager.get_session(request.api_session_id)
        if not session_data:
            return {
                "status": "error",
                "message": f"Session not found or expired. Session ID: {request.api_session_id}"
            }

        # Call the automation function
        result = await verify_otp_automation(session_data, request.otp)

        return {
            "status": "success",
            "api_session_id": request.api_session_id,  # Return the same session ID
            "website_session_id": result["session_id"],  # The actual website session
            "session_cookies": result["session_cookies"],
            "message": "OTP verified successfully. Browser session is still active."
        }

    except Exception as e:
        print(f"OTP verification error: {e}")
        # Clean up on error
        # session_data = session_manager.get_session(request.api_session_id)
        # if session_data:
        #     try:
        #         await session_data["browser"].close()
        #     except:
        #         pass
        #     session_manager.remove_session(request.api_session_id)
        
        return {
            "status": "error",
            "message": f"OTP verification failed: {str(e)}"
        }

@router.get("/oyo/sessions")
async def list_sessions():
    """Debug endpoint to see active sessions"""
    return {
        "active_sessions": list(session_manager.sessions.keys()),
        "session_count": len(session_manager.sessions)
    }

@router.post("/oyo/cleanup/{session_id}")
async def cleanup_session(session_id: str):
    try:
        session_data = session_manager.get_session(session_id)
        if session_data:
            await session_data["browser"].close()
            session_manager.remove_session(session_id)
            return {"status": "success", "message": "Session cleaned up"}
        else:
            return {"status": "error", "message": "Session not found"}
    except Exception as e:
        return {"status": "error", "message": f"Cleanup failed: {str(e)}"}