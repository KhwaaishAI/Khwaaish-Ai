from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uuid
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.blinkit.blinkit_automation import automate_blinkit, login, AUTH_FILE_PATH, enter_otp_and_save_session, search_multiple_products, add_product_to_cart, add_address, submit_upi_and_pay
from app.prompts.blinkit_prompts.blinkit_prompts import analyze_query

router = APIRouter()

# In-memory store for active browser sessions
ACTIVE_SESSIONS = {}



class LoginRequest(BaseModel):
    phone_number: str
    location: str

class OtpSubmitRequest(BaseModel):
    session_id: str
    otp: str

class SearchRequest(BaseModel):
    query: str

class AddToCartRequest(BaseModel):
    session_id: str
    product_name: str
    quantity: int

class AddAddressRequest(BaseModel):
    session_id: str
    location: str
    house_number: str
    name: str

class UpiRequest(BaseModel):
    session_id: str
    upi_id: str

@router.post("/login")
async def start_login(request: LoginRequest):
    session_id = str(uuid.uuid4())
    playwright = await async_playwright().start()
    
    try:
        context, page = await login(playwright, request.phone_number, request.location)
        ACTIVE_SESSIONS[session_id] = {"context": context, "playwright": playwright}
        return {"status": "success", "session_id": session_id, "message": "Login process initiated. Please submit OTP."}
    except Exception as e:
        # Ensure playwright is stopped on failure
        await playwright.stop()
        raise HTTPException(status_code=500, detail=f"Failed to initiate login: {e}")

@router.post("/submit-otp")
async def submit_otp(request: OtpSubmitRequest):
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found, expired, or already used.")
    
    context = session["context"]
    playwright = session["playwright"]
    
    try:
        await enter_otp_and_save_session(context, request.otp)
        return {"status": "success", "message": "OTP submitted and session saved."}
    finally:
        # Ensure cleanup happens even if OTP submission fails
        await context.browser.close()
        await playwright.stop()
        ACTIVE_SESSIONS.pop(request.session_id, None)

@router.post("/search")
async def search_for_product(request: SearchRequest):
    # Split the query by comma, strip whitespace from each item, and filter out any empty strings
    queries = [q.strip() for q in request.query.split(',') if q.strip()]
    if not queries:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if not os.path.exists(AUTH_FILE_PATH):
        raise HTTPException(status_code=401, detail="User not logged in. Please complete the login flow first.")

    session_id = str(uuid.uuid4())
    playwright = await async_playwright().start()

    try:
        context, page, results = await search_multiple_products(playwright, queries)
        # Store the context for subsequent operations like 'add-to-cart'
        ACTIVE_SESSIONS[session_id] = {"context": context, "playwright": playwright}
        
        return {
            "status": "success", 
            "session_id": session_id, 
            "message": f"Search for '{request.query}' completed. Use the session ID for next steps.",
            "results": results
        }
    except Exception as e:
        await playwright.stop()
        raise HTTPException(status_code=500, detail=f"An error occurred during search: {e}")

@router.post("/add-to-cart")
async def add_item_to_cart(request: AddToCartRequest):
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    context = session["context"]
    try:
        result = await add_product_to_cart(context, request.session_id, request.product_name, request.quantity)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add item to cart: {e}")

@router.post("/add-address")
async def add_new_address(request: AddAddressRequest):
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    context = session["context"]
    try:
        result = await add_address(context, request.session_id, request.location, request.house_number, request.name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add new address: {e}")

@router.post("/submit-upi")
async def submit_upi_payment(request: UpiRequest):
    session = ACTIVE_SESSIONS.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    context = session["context"]
    try:
        result = await submit_upi_and_pay(context, request.upi_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit UPI and pay: {e}")
