from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
import sys
import os
import asyncio
import uuid

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.myntra.myntra_automation import (
    initiate_login,
    verify_otp_and_save_session,
    search_myntra,
    add_to_cart,
    add_new_address,
    enter_upi_and_pay
)

router = APIRouter()

# In-memory store for active browser sessions
ACTIVE_SESSIONS = {}
playwright_instance = None

class LoginRequest(BaseModel):
    mobile_number: str

class OTPRequest(BaseModel):
    session_id: str
    otp: str

class SearchRequest(BaseModel):
    query: str

class AddToCartRequest(BaseModel):
    product_url: str
    size: str = None

class AddressRequest(BaseModel):
    session_id: str
    name: str
    mobile: str
    pincode: str
    house_number: str
    street_address: str
    locality: str
    address_type: str = "HOME"  # "HOME" or "OFFICE"
    make_default: bool = False

class UpiPaymentRequest(BaseModel):
    session_id: str
    upi_id: str


@router.on_event("startup")
async def startup_event():
    global playwright_instance
    playwright_instance = await async_playwright().start()

@router.on_event("shutdown")
async def shutdown_event():
    global playwright_instance
    if playwright_instance:
        await playwright_instance.stop()

@router.post("/myntra/login")
async def login(request: LoginRequest):
    try:
        session_id = str(uuid.uuid4())
        context = await initiate_login(playwright_instance, request.mobile_number)
        ACTIVE_SESSIONS[session_id] = context
        return {
            "status": "success", 
            "session_id": session_id,
            "message": "OTP sent. Please provide OTP to /myntra/submit-otp"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/myntra/submit-otp")
async def submit_otp(request: OTPRequest):
    context = ACTIVE_SESSIONS.get(request.session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found or expired. Call /myntra/login first.")
    
    try:
        success = await verify_otp_and_save_session(context, request.otp)
        ACTIVE_SESSIONS.pop(request.session_id, None) # Clear context after success
        return {"status": "success", "message": "Login successful"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/myntra/search")
async def search(request: SearchRequest):
    try:
        products = await search_myntra(playwright_instance, request.query)
        return {"status": "success", "products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/myntra/add-to-cart")
async def add_item(request: AddToCartRequest):
    try:
        result_data = await add_to_cart(playwright_instance, request.product_url, request.size)
        
        # If the process requires adding an address, keep the session active
        if "session_id" in result_data:
            ACTIVE_SESSIONS[result_data["session_id"]] = result_data["context"]
            return {
                "status": result_data.get("status", "action_required"),
                "session_id": result_data["session_id"],
                "message": result_data["message"]
            }
            
        return {"status": "success", "message": result_data["message"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/myntra/add-address")
async def add_address_endpoint(request: AddressRequest):
    context = ACTIVE_SESSIONS.get(request.session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    
    result_message = await add_new_address(context, request.dict())
    ACTIVE_SESSIONS.pop(request.session_id, None) # Clean up session
    return {"status": "success", "message": result_message}

@router.post("/myntra/pay-with-upi")
async def pay_with_upi_endpoint(request: UpiPaymentRequest):
    context = ACTIVE_SESSIONS.get(request.session_id)
    if not context:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    
    result_message = await enter_upi_and_pay(context, request.upi_id)
    ACTIVE_SESSIONS.pop(request.session_id, None) # Clean up session
    return {"status": "success", "message": result_message}
