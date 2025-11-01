#!/usr/bin/env python3
import json, os, uuid
from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
from app.agents.flipkart.automation.core import FlipkartAutomation
from app.agents.flipkart.automation.steps import FlipkartSteps
from app.tools.flipkart_tools.search import FlipkartCrawler, Product # Assuming Product is importable


router = APIRouter()

# This is the ONLY place state should be stored between calls.
# It is used *exclusively* for the multi-step login.
active_sessions: Dict[str, FlipkartAutomation] = {}

# ---- Data Models ----
# (Kept your models, they are good)
class LoginStartRequest(BaseModel):
    phone: str

class LoginVerifyRequest(BaseModel):
    session_id: str
    otp: str

class ShippingInfo(BaseModel):
    name: str
    mobile: str
    address: str
    city: str
    state: str
    pincode: str

class RunRequest(BaseModel):
    product_id: str
    use_saved_shipping: bool = True
    shipping: Optional[ShippingInfo] = None
    specifications: Optional[dict] = None   


# ---- Utils ----
def load_shipping(use_saved=True, override: Optional[ShippingInfo] = None) -> Dict[str, Any]:
    session_file = "user_shipping_session.json"
    
    # If override is provided, use it and save it
    if override:
        shipping_dict = override.dict()
        with open(session_file, "w") as f:
            json.dump(shipping_dict, f, indent=2)
        return shipping_dict
    
    # If using saved and it exists, load it
    if use_saved and os.path.exists(session_file):
        try:
            with open(session_file) as f:
                return json.load(f)
        except:
            pass
            
    # If no override and not using/finding saved, raise error
    raise ValueError("Shipping info not provided and no saved session found.")

# ---- API Endpoints ----

### 🔐 Login Flow
# These two endpoints are correct and well-implemented.

@router.post("/login/start")
async def login_start(req: LoginStartRequest):
    """
    Launches browser, enters phone, and requests OTP.
    """
    automation = FlipkartAutomation()
    
    try:
        await automation.initialize_browser()
        
        # Check if session is already logged in
        await automation.page.goto("https://www.flipkart.com/account/", wait_until="networkidle")
        if "account" in automation.page.url:
            automation.logger.info("✅ Already logged in from saved session.")
            await automation.close_browser()
            return {"status": "✅ Already logged in"}
        
        # Not logged in, so proceed to login page
        await automation.page.goto("https://www.flipkart.com/account/login?ret=/", wait_until="networkidle")
        
        steps = FlipkartSteps(automation)
        
        if not await steps.login_enter_phone(req.phone):
                 raise HTTPException(status_code=500, detail="Failed to enter phone number.")

        # Create session ID and store the live browser instance
        session_id = str(uuid.uuid4())
        active_sessions[session_id] = automation

        return {"status": "✅ OTP requested", "session_id": session_id}

    except Exception as e:
        if automation:
            automation.logger.error(f"❌ Error during login start: {e}")
            await automation.close_browser()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@router.post("/login/verify")
async def login_verify(req: LoginVerifyRequest):
    """
    Submits the OTP using the session_id from /login/start.
    """
    automation = active_sessions.get(req.session_id)
    
    if not automation:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    steps = FlipkartSteps(automation)

    try:
        if not await steps.login_submit_otp(req.otp):
            raise HTTPException(status_code=400, detail="OTP verification failed. Check OTP or try again.")

        return {"status": "✅ Logged in successfully"}

    except Exception as e:
        steps.logger.error(f"❌ Error during OTP verification: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
    finally:
        # Cleanup: Close browser and remove session from memory
        await automation.close_browser()
        if req.session_id in active_sessions:
            del active_sessions[req.session_id]


### 🛍️ Search & Run Flow

@router.get("/search")
async def search_products(
    product: str,  # Required query parameter
    max_pages: int = 2  # Optional query parameter with a default
):
    """
    Search for a product, save results to JSON, and return list to user.
    Called via GET: /search?product=your_product_name&max_pages=3
    This is self-contained and closes its own browser.
    """
    automation: Optional[FlipkartAutomation] = None
    try:
        # This flow does not need to be logged in, so it's simple
        automation = FlipkartAutomation()
        await automation.initialize_browser()

        extractor = FlipkartCrawler(automation.page)  # Pass page if needed
        
        # Use the query parameters directly instead of 'req.product'
        product_list = await extractor.search(product, max_pages)

        # Save results to file for the /run_automation step
        out_dir = Path("./out/flipkart")
        out_dir.mkdir(parents=True, exist_ok=True)
        extractor.save_json(out_dir, product)

        if not product_list:
            return {"status": "No products found", "products": []}

        # Return the full list of product dicts
        return {
            "status": f"Found {len(product_list)} products",
            "products": [p.to_dict() for p in product_list]
        }
    except Exception as e:
        if automation:
            automation.logger.error(f"❌ Error during search: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    finally:
        if automation:
            await automation.close_browser()

@router.post("/run_automation")
async def run_automation(req: RunRequest):
    """
    Run full Flipkart automation for a *specific product_id*
    (from the /search endpoint)
    """
    automation: Optional[FlipkartAutomation] = None
    try:
        shipping_data = load_shipping(req.use_saved_shipping, req.shipping)
        
        automation = FlipkartAutomation()
        await automation.initialize_browser() # Starts with a saved session if available
        
        steps = FlipkartSteps(automation)
        
        # Set the data for the steps
        steps.shipping_info = shipping_data
        
        # 1. Find the product URL from the ID (which /search saved to JSON)
        product_url = await steps.step_2_select_product(req.product_id)
        if not product_url:
            raise HTTPException(status_code=404, 
                detail=f"Product ID {req.product_id} not found. Run /search first.")
        
        steps.logger.info(f"Navigating to product page: {product_url}")
        
        # 2. **Missing step**: Navigate to the product page
        await automation.page.goto(product_url, wait_until="networkidle")

        # 3. Continue the rest of the flow
        await steps.step_3_handle_product_options()
        await steps.step_4_add_to_cart_without_login()
        await steps.step_6_proceed_to_shipping()
        await steps.step_7_fill_shipping_info()
        await steps.step_8_proceed_to_payment()
        # --- End of flow ---
        
        return {"status": "🚀 Automation Completed Procede to the payment page", "product_id": req.product_id}

    except Exception as e:
        if automation:
            automation.logger.error(f"❌ Error during full automation run: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    finally:
        if automation:
            steps.logger.info("Automation run finished. Browser will close.")
            await automation.close_browser()
        


@router.post("/cleanup_stale_sessions")
async def cleanup_stale_sessions():
    """
    Forcefully closes all active browser sessions that were
    initiated by /login/start but never verified.
    
    This is a utility endpoint to clean up leaked resources.
    """
    global active_sessions
    
    # We copy the .items() into a list because we can't
    # modify a dictionary while iterating over it.
    sessions_to_close = list(active_sessions.items())
    
    if not sessions_to_close:
        return {"status": "No stale sessions found."}
        
    count = 0
    errors = []
    
    for session_id, automation in sessions_to_close:
        try:
            automation.logger.warning(f"Force-closing stale session: {session_id}")
            await automation.close_browser()
            count += 1
        except Exception as e:
            # Log the error but continue cleaning up others
            automation.logger.error(f"Error closing session {session_id}: {e}")
            errors.append(session_id)
        finally:
            # ALWAYS remove it from the dictionary
            if session_id in active_sessions:
                del active_sessions[session_id]
                
    return {
        "status": "Cleanup complete",
        "sessions_closed": count,
        "sessions_failed": errors
    }