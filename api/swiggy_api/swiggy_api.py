from fastapi import APIRouter
from app.agents.swiggy import swiggy_automation
import asyncio
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright
import uuid
from fastapi import HTTPException
import os

router = APIRouter()

# In-memory store for active browser sessions
ACTIVE_SESSIONS = {}

class SignupRequest(BaseModel):
    mobile_number: str
    name: str
    gmail: str

class OtpSubmitRequest(BaseModel):
    session_id: str
    otp: str = Field(..., min_length=6, max_length=6)

class SearchRequest(BaseModel):
    location: str
    query: str

class AddToCartRequest(BaseModel):
    session_id: str
    product: dict

@router.post("/swiggy/signup")
async def swiggy_signup_endpoint(request: SignupRequest):
    """Endpoint to automate Swiggy signup."""
    session_id = str(uuid.uuid4())
    playwright = await async_playwright().start()
    try:
        context = await swiggy_automation.initiate_signup(playwright, request.mobile_number, request.name, request.gmail)
        ACTIVE_SESSIONS[session_id] = {"context": context, "playwright": playwright}
        return {"status": "success", "session_id": session_id, "message": "OTP screen reached. Please submit OTP using the /swiggy/submit-otp endpoint."}
    except Exception as e:
        await playwright.stop()
        raise HTTPException(status_code=500, detail=f"Failed to initiate signup: {str(e)}")

@router.post("/swiggy/submit-otp")
async def submit_swiggy_otp(request: OtpSubmitRequest):
    """Endpoint to submit OTP and complete login."""
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    
    context = session["context"]
    playwright = session["playwright"]
    
    try:
        await swiggy_automation.enter_otp_and_save_session(context, request.otp)
        return {"status": "success", "message": "OTP submitted successfully and session has been saved. Browser closed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit OTP: {str(e)}")
    finally: # Ensure browser is always closed and session removed from memory after OTP submission
        await context.browser.close()
        await playwright.stop()
        ACTIVE_SESSIONS.pop(request.session_id, None)

@router.post("/swiggy/search")
async def swiggy_search_endpoint(request: SearchRequest):
    """Endpoint to search for items on Swiggy using a logged-in session."""
    # Check if authentication file exists
    if not os.path.exists(swiggy_automation.SWIGGY_AUTH_FILE_PATH):
        raise HTTPException(status_code=401, detail="Authentication state not found. Please complete signup/login first.")
    
    session_id = str(uuid.uuid4())
    playwright = await async_playwright().start()
    try:
        context, search_results = await swiggy_automation.search_swiggy(playwright, request.location, request.query)
        
        # Store the new active session
        ACTIVE_SESSIONS[session_id] = {"context": context, "playwright": playwright}
        
        return {
            "status": "success", 
            "session_id": session_id,
            "message": f"Search for '{request.query}' at '{request.location}' completed successfully. Session is active for booking.", 
            "results": search_results
        }
    except Exception as e:
        await playwright.stop()
        raise HTTPException(status_code=500, detail=f"An error occurred during the search: {str(e)}")

@router.post("/swiggy/add-to-cart")
async def swiggy_add_to_cart_endpoint(request: AddToCartRequest):
    """Endpoint to add an item to the cart using an active session."""
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        print(f"❌ Session '{request.session_id}' not found. Active sessions: {list(ACTIVE_SESSIONS.keys())}")
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    
    context = session["context"]
    
    try:
        await swiggy_automation.add_product_to_cart(context, request.product)
        return {
            "status": "success", 
            "message": f"Item '{request.product.get('item_name')}' added to cart successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add item to cart: {str(e)}")
