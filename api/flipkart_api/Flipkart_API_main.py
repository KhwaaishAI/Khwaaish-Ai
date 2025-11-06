from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import json
import asyncio
from pathlib import Path
from datetime import datetime

from app.agents.flipkart.automation.core import FlipkartAutomation
from app.agents.flipkart.automation.steps import FlipkartSteps
from app.tools.flipkart_tools.search import FlipkartCrawler
from app.agents.flipkart.utills.logger import setup_logger

logger = setup_logger()
router = APIRouter()

# Global store for active browser sessions
active_sessions: Dict[str, FlipkartAutomation] = {}

# ===== Models =====
class LoginRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=10)

class OTPVerifyRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=10)
    otp: str = Field(..., min_length=6, max_length=6)

class SearchRequest(BaseModel):
    product_name: str
    max_pages: int = Field(default=1, ge=1, le=5)

class ShippingInfo(BaseModel):
    name: str
    mobile: str
    address: str
    city: str
    state: str
    pincode: str

class AutomationRequest(BaseModel):
    phone: str
    product_name: str
    product_id: str
    use_saved_shipping: bool = False
    shipping: Optional[ShippingInfo] = None
    specifications: Optional[Dict[str, Any]] = None

# ===== Endpoints =====

@router.post("/login")
async def login(request: LoginRequest):
    """Start login - opens browser and requests OTP"""
    phone = request.phone
    
    if phone in active_sessions:
        raise HTTPException(400, "Session already active. Complete or close first.")
    
    try:
        # Initialize browser
        automation = FlipkartAutomation()
        await automation.initialize_browser()
        
        # Navigate to Flipkart
        await automation.page.goto("https://www.flipkart.com/account/login?ret=/")
        asyncio.sleep(20)
        
        # Initialize steps
        steps = FlipkartSteps(automation)
        
        # Request OTP
        result = await steps.login_enter_phone(phone)
        
        if not result:
            await automation.close_browser()
            raise HTTPException(500, "Failed to request OTP")
        
        # Store session
        active_sessions[phone] = automation
        
        return {
            "status": "success",
            "message": "OTP sent. Browser kept open for verification.",
            "phone": phone,
            "instruction": "Call /flipkart/verify-otp with OTP to complete login"
        }
    
    except Exception as e:
        if phone in active_sessions:
            await active_sessions[phone].close_browser()
            del active_sessions[phone]
        raise HTTPException(500, f"Login failed: {str(e)}")


@router.post("/verify-otp")
async def verify_otp(request: OTPVerifyRequest):
    """Verify OTP and save session"""
    phone = request.phone
    otp = request.otp
    
    if phone not in active_sessions:
        raise HTTPException(400, "No active login session. Call /login first.")
    
    automation = active_sessions[phone]
    
    try:
        steps = FlipkartSteps(automation)
        result = await steps.login_submit_otp(otp)
        
        if result:
            # Save session with phone identifier
            session_dir = Path("sessions")
            session_dir.mkdir(exist_ok=True)
            session_file = session_dir / f".flipkart_session_{phone}.json"
            
            if automation.context:
                await automation.context.storage_state(path=str(session_file))
                automation.logger.info(f"Session saved: {session_file}")
            
            # Close browser
            await automation.close_browser()
            del active_sessions[phone]
            
            return {
                "status": "success",
                "message": "Login successful. Session saved.",
                "phone": phone
            }
        else:
            raise HTTPException(401, "OTP verification failed")
    
    except Exception as e:
        await automation.close_browser()
        del active_sessions[phone]
        raise HTTPException(500, f"Verification failed: {str(e)}")


@router.post("/search")
async def search_products(request: SearchRequest):
    """Search Flipkart products and save results"""
    try:
        crawler = FlipkartCrawler(concurrency=2, rate_limit_delay=1.0)
        
        # Search products
        products = await crawler.search(request.product_name, max_pages=request.max_pages)
        
        if not products:
            return {
                "status": "no_results",
                "message": "No products found",
                "total": 0
            }
        
        # Save to file
        output_dir = Path("./out/flipkart")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        slug = request.product_name.lower().replace(" ", "_")[:50]
        file_path = crawler.save_json(output_dir, slug)
        
        # Get summary
        summary = crawler.get_summary()
        
        return {
            "status": "success",
            "message": f"Found {len(products)} products",
            "file_path": str(file_path),
            "total": len(products),
            "summary": summary,
            "products": [p.to_dict() for p in products[:10]]  # Return first 10
        }
    
    except Exception as e:
        raise HTTPException(500, f"Search failed: {str(e)}")


@router.post("/run-automation")
async def run_automation(request: AutomationRequest, background_tasks: BackgroundTasks):
    """Execute complete Flipkart purchase automation"""
    
    # 1. Check product file exists
    output_dir = Path("./out/flipkart")
    slug = request.product_name.lower().replace(" ", "_")[:50]
    product_file = output_dir / f"products-{slug}.json"
    
    if not product_file.exists():
        raise HTTPException(404, "Product not found. Search for the product first using /search")
    
    # 2. Find product by ID
    try:
        with open(product_file, 'r') as f:
            products = json.load(f)
        
        product = next((p for p in products if str(p.get('id')) == request.product_id), None)
        
        if not product:
            raise HTTPException(404, f"Product ID {request.product_id} not found in search results")
        
        product_url = product.get('product_url')
        if not product_url:
            raise HTTPException(400, "Product URL not available")
    
    except json.JSONDecodeError:
        raise HTTPException(500, "Invalid product file format")
    logger.info("Step 3 session loading")
    # 3. Check session exists
    session_file = Path(f"sessions/.flipkart_session_{request.phone}.json")
    if not session_file.exists():
        raise HTTPException(401, "User not logged in. Please login first using /login")
    
    logger.info("setp 4 shipping")
    # 4. Prepare shipping info
    if request.use_saved_shipping:
        shipping_file = Path("session/user_shipping_session.json")
        if shipping_file.exists():
            with open(shipping_file, 'r') as f:
                shipping_info = json.load(f)
        else:
            raise HTTPException(400, "No saved shipping info found")
    elif request.shipping:
        shipping_info = request.shipping.dict()
    else:
        raise HTTPException(400, "Shipping info required when use_saved_shipping=false")
    
    # 5. Run automation
    try:
        automation = FlipkartAutomation()
        await automation.initialize_browser()
        
        logger.info("Navigate to product")
        await automation.page.goto(product_url)
        
        logger.info("nitialize steps")
        steps = FlipkartSteps(automation)
        steps.current_product = {
            'name': request.product_name,
            'options': request.specifications or {}
        }
        steps.shipping_info = shipping_info
        steps.search_url = product_url
        
        logger.info("Execute automation steps")
        await steps.step_3_handle_product_options()
        logger.info("Step 3 completed")
        await steps.step_4_add_to_cart_without_login()
        logger.info("Step 4 completed")
        await steps.step_6_proceed_to_shipping()
        logger.info("Step 6 completed")
        await steps.step_7_fill_shipping_info()
        logger.info("Step 7 completed")
        
        # Keep browser open for payment
        background_tasks.add_task(steps.step_8_proceed_to_payment)
        
        return {
            "status": "success",
            "message": "Automation completed. Browser kept open for manual payment.",
            "product_name": request.product_name,
            "product_id": request.product_id,
            "product_url": product_url,
            "instruction": "Complete payment manually in the browser window"
        }
    
    except Exception as e:
        if automation:
            await automation.close_browser()
        raise HTTPException(500, f"Automation failed: {str(e)}")


@router.get("/status/{phone}")
async def get_status(phone: str):
    """Check login/session status"""
    session_file = Path(f"sessions/.flipkart_session_{phone}.json")
    
    return {
        "phone": phone,
        "logged_in": session_file.exists(),
        "active_session": phone in active_sessions,
        "session_file": str(session_file) if session_file.exists() else None
    }


@router.delete("/session/{phone}")
async def delete_session(phone: str):
    """Delete saved session"""
    session_file = Path(f"sessions/.flipkart_sessions_{phone}.json")
    
    if session_file.exists():
        session_file.unlink()
        return {"status": "success", "message": "Session deleted"}
    
    raise HTTPException(404, "Session not found")