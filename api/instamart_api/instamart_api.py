from fastapi import APIRouter
from app.agents.instamart import instamart_automation
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
    location: str

class OtpSubmitRequest(BaseModel):
    session_id: str
    otp: str = Field(..., min_length=6, max_length=6)

class SearchRequest(BaseModel):
    query: str

class AddToCartRequest(BaseModel):
    session_id: str
    product_name: str
    quantity: int


@router.post("/instamart/signup")
async def swiggy_signup_endpoint(request: SignupRequest):
    """Endpoint to automate Instamart signup (uses Swiggy login)."""
    session_id = str(uuid.uuid4())
    playwright = await async_playwright().start()
    try:
        context = await instamart_automation.initiate_signup(playwright, request.mobile_number, request.name, request.gmail, request.location)
        ACTIVE_SESSIONS[session_id] = {"context": context, "playwright": playwright}
        return {"status": "success", "session_id": session_id, "message": "OTP screen reached. Please submit OTP using the /instamart/submit-otp endpoint."}
    except Exception as e:
        await playwright.stop()
        raise HTTPException(status_code=500, detail=f"Failed to initiate signup: {str(e)}")

@router.post("/instamart/submit-otp")
async def submit_swiggy_otp(request: OtpSubmitRequest):
    """Endpoint to submit OTP and complete login."""
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    
    context = session["context"]
    playwright = session["playwright"]
    
    try:
        await instamart_automation.enter_otp_and_save_session(context, request.otp)
        return {"status": "success", "message": "OTP submitted successfully and session has been saved. Browser closed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit OTP: {str(e)}")
    finally: 
        await context.browser.close()
        await playwright.stop()
        ACTIVE_SESSIONS.pop(request.session_id, None)

@router.post("/instamart/search")
async def instamart_search_endpoint(request: SearchRequest):
    """Endpoint to search for items on Instamart using a logged-in session."""
    if not os.path.exists(instamart_automation.INSTAMART_AUTH_FILE_PATH):
        raise HTTPException(status_code=401, detail="Authentication state not found. Please complete signup/login first.")

    session_id = str(uuid.uuid4())
    playwright = await async_playwright().start()
    browser = None
    try:
        browser, context, search_results = await instamart_automation.search_instamart(playwright, request.query)

        # Store the browser and context so they can be used by other endpoints
        ACTIVE_SESSIONS[session_id] = {"context": context, "browser": browser, "playwright": playwright}

        return {
            "status": "success",
            "session_id": session_id,
            "message": f"Search for '{request.query}' completed. Session is active for further actions.",
            "results": search_results
        }
    except Exception as e:
        if browser:
            await browser.close()
        await playwright.stop()
        raise HTTPException(status_code=500, detail=f"An error occurred during the search: {str(e)}")

@router.post("/instamart/add-to-cart")
async def instamart_add_to_cart_endpoint(request: AddToCartRequest):
    """Endpoint to add a specified product to the Instamart cart."""
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired. Please perform a search first.")

    context = session.get("context") # The add_to_cart function uses the context from the session
    if not context:
        raise HTTPException(status_code=404, detail="Browser context not found in the session.")

    try:
        bill_details = await instamart_automation.add_to_cart(context, request.product_name, request.quantity)
        return {
            "status": "success",
            "message": f"Successfully added '{request.product_name}' and navigated to cart.",
            "bill_details": bill_details
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add item to cart: {str(e)}")
