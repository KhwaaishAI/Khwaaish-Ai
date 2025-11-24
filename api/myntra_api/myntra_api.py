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
    book_order
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
        result = await add_to_cart(playwright_instance, request.product_url, request.size)
        return {"status": "success", "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/myntra/book")
async def book():
    try:
        result = await book_order(playwright_instance)
        return {"status": "success", "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

