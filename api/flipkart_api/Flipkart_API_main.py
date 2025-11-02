# #!/usr/bin/env python3
# import json, os, uuid, re, logging
# from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
# from pydantic import BaseModel
# from typing import Optional, Dict, Any, List
# from pathlib import Path
# from app.agents.flipkart.automation.core import FlipkartAutomation
# from app.agents.flipkart.automation.steps import FlipkartSteps
# import asyncio
# from app.tools.flipkart_tools.search import FlipkartCrawler, Product # Assuming Product is importable

# # Initialize logger
# logger = logging.getLogger(__name__)
# router = APIRouter()

# # ---- Global State ----
# # In-memory store for simple API state (e.g., "logged_in")
# sessions: Dict[str, Dict[str, Any]] = {}

# # Temporary store for live browser objects during OTP flow
# live_otp_sessions: Dict[str, FlipkartAutomation] = {}

# # ---- Data Models ----

# class LoginStartRequest(BaseModel):
#     phone: str

# class LoginVerifyRequest(BaseModel):
#     phone: str  # Changed from session_id
#     otp: str

# class ShippingInfo(BaseModel):
#     name: str
#     mobile: str
#     address: str
#     city: str
#     state: str
#     pincode: str

# # UPDATED: RunRequest to match new requirements
# class RunRequest(BaseModel):
#     phone: str                        # To check login state
#     product_name: str                 # To find the JSON file
#     product_id: str                   # To pick from the JSON file
#     use_saved_shipping: bool = True
#     shipping: Optional[ShippingInfo] = None
#     specifications: Optional[dict] = None

# # ---- Utils ----

# def _get_flipkart_product_filepath(product_name: str) -> Path:
#     """Generates a consistent, safe file path for a product search."""
#     output_dir = Path("./out/flipkart")
#     output_dir.mkdir(parents=True, exist_ok=True)
    
#     safe_name = re.sub(r'[^a-zA-Z0-9\s]', '', product_name).strip()
#     safe_name = re.sub(r'\s+', '_', safe_name).lower()
#     if not safe_name:
#         safe_name = "default_product"
    
#     return output_dir / f"{safe_name}.json"

# async def _is_flipkart_session_valid() -> bool:
#     """
#     Headlessly checks if the default .flipkart_session.json is valid.
#     (This logic remains from your original, checking a global session)
#     """
#     automation = FlipkartAutomation(headful=False)
#     try:
#         await automation.initialize_browser()
#         await automation.page.goto("https://www.flipkart.com/account/", wait_until="networkidle")
        
#         if "account" in automation.page.url and "login" not in automation.page.url:
#             automation.logger.info("✅ Flipkart session is valid.")
#             return True
#         else:
#             automation.logger.info("Flipkart session is invalid or expired.")
#             return False
#     except Exception as e:
#         automation.logger.warning(f"Flipkart session validation failed: {e}")
#         return False
#     finally:
#         if automation:
#             await automation.close_browser()

# def load_shipping(use_saved=True, override: Optional[ShippingInfo] = None) -> Dict[str, Any]:
#     """Loads shipping info (unchanged)."""
#     session_file = "user_shipping_session.json"
    
#     if override:
#         shipping_dict = override.dict()
#         with open(session_file, "w") as f:
#             json.dump(shipping_dict, f, indent=2)
#         return shipping_dict
    
#     if use_saved and os.path.exists(session_file):
#         try:
#             with open(session_file) as f:
#                 return json.load(f)
#         except:
#             pass
            
#     raise ValueError("Shipping info not provided and no saved session found.")

# # ---- API Endpoints ----

# ### 🔐 Login Flow
# @router.post("/login")
# async def login_start(req: LoginStartRequest):
#     """
#     Checks for valid session. If invalid, starts OTP flow.
#     Uses phone number as the key.
#     """
#     phone = req.phone
#     automation: Optional[FlipkartAutomation] = None
    
#     try:
#         # 1. Check if session is already valid
#         if await _is_flipkart_session_valid():
#             logger.info("Flipkart session is valid.")
#             # Update in-memory state for this user
#             sessions[phone] = {"state": "logged_in"}
#             return {"status": "✅ Already logged in"}
            
#         # 2. Session is invalid, start new login
#         logger.info("Session invalid, proceeding with new login.")
#         automation = FlipkartAutomation(headful=True) # Headful for OTP
#         await automation.initialize_browser()
        
#         # Go to login page
#         await automation.page.goto("https://www.flipkart.com/account/login?ret=/", wait_until="networkidle")
        
#         steps = FlipkartSteps(automation)
        
#         if not await steps.login_enter_phone(req.phone):
#             raise HTTPException(status_code=500, detail="Failed to enter phone number.")

#         # 3. Store the live browser by phone number for verification
#         live_otp_sessions[phone] = automation

#         return {"status": "✅ OTP requested", "phone": phone}

#     except Exception as e:
#         if automation:
#             automation.logger.error(f"❌ Error during login start: {e}")
#             await automation.close_browser()
#         # Clean up if failed
#         if phone in live_otp_sessions:
#             del live_otp_sessions[phone]
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


# @router.post("/login/verify")
# async def login_verify(req: LoginVerifyRequest):
#     """
#     Submits the OTP using the phone number as the key.
#     """
#     phone = req.phone
#     automation = live_otp_sessions.get(phone)
    
#     if not automation:
#         raise HTTPException(status_code=404, detail="Session not found or expired. Please try /login again.")

#     steps = FlipkartSteps(automation)

#     try:
#         if not await steps.login_submit_otp(req.otp):
#             raise HTTPException(status_code=400, detail="OTP verification failed. Check OTP or try again.")

#         # On success, update the in-memory state
#         sessions[phone] = {"state": "logged_in"}
#         return {"status": "✅ Logged in successfully"}

#     except Exception as e:
#         steps.logger.error(f"❌ Error during OTP verification: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    
#     finally:
#         # Cleanup: Close browser and remove session from memory
#         if automation:
#             await automation.close_browser()
#         if phone in live_otp_sessions:
#             del live_otp_sessions[phone]


# ### 🛍️ Search & Run Flow

# @router.get("/search")
# async def search_products(
#     product: str, 
#     max_pages: int = 2,
#     background_tasks: Optional[BackgroundTasks] = None # Make explicit
# ):
#     """
#     Search for a product. Checks cache first.
#     If not in cache, runs scraper in background.
#     """
#     product_file_path = _get_flipkart_product_filepath(product)

#     # 1. Check if file already exists in cache
#     if product_file_path.exists():
#         try:
#             with open(product_file_path, "r") as f:
#                 data = json.load(f)
#             return {
#                 "status": "✅ Product found in cache",
#                 "products": data
#             }
#         except Exception as e:
#             logger.warning(f"Could not read cache file {product_file_path}: {e}. Rescraping.")

#     # 2. Define the background task if file not found
#     async def scraping_task():
#         automation: Optional[FlipkartAutomation] = None
#         try:
#             automation = FlipkartAutomation(headful=False) # Run search headlessly
#             await automation.initialize_browser()
#             extractor = FlipkartCrawler(automation.page)
            
#             product_list = await extractor.search(product, max_pages)
#             product_list_dicts = [p.to_dict() for p in product_list]
            
#             with open(product_file_path, "w") as f:
#                 json.dump(product_list_dicts, f, indent=2)
            
#             logger.info(f"Scraping complete. Saved to {product_file_path}")

#         except Exception as e:
#             if automation:
#                 automation.logger.error(f"❌ Error during background search: {e}")
#         finally:
#             if automation:
#                 await automation.close_browser()

#     # 3. Add the task to run in the background
#     if background_tasks:
#         background_tasks.add_task(scraping_task)
#     else:
#         # This case handles if the function is called without a BG task context
#         # In a real app, you'd just let the BG task be injected.
#         asyncio.create_task(scraping_task())


#     # 4. Return an immediate response
#     return {
#         "status": "⏳ Product not in cache. Search started in background.",
#         "output_file": str(product_file_path)
#     }

# @router.post("/run_automation")
# async def run_automation(req: RunRequest):
#     """
#     Run full Flipkart automation for a *specific product_id*.
#     Checks for product file and valid login session first.
#     """
#     automation: Optional[FlipkartAutomation] = None
#     phone = req.phone
    
#     # 1. Check if product file exists
#     product_file_path = _get_flipkart_product_filepath(req.product_name)
#     if not product_file_path.exists():
#         raise HTTPException(
#             status_code=404, 
#             detail=f"Product file for '{req.product_name}' not found. Please call /search first."
#         )

#     # 2. Check if user is logged in (using the new `sessions` dict)
#     if phone not in sessions or sessions[phone].get("state") != "logged_in":
#         raise HTTPException(
#             status_code=403, 
#             detail="User not logged in. Please call /login first."
#         )

#     # 3. Load product URL from the file
#     product_url: Optional[str] = None
#     try:
#         with open(product_file_path) as f:
#             products = json.load(f)
#             for prod in products:
#                 if prod.get('id') == req.product_id:
#                     product_url = prod.get('url')
#                     break
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error reading product file: {e}")

#     if not product_url:
#         raise HTTPException(
#             status_code=404,
#             detail=f"Product ID {req.product_id} not found in file '{req.product_name}.json'."
#         )

#     # 4. Both checks passed, proceed with automation
#     try:
#         shipping_data = load_shipping(req.use_saved_shipping, req.shipping)
        
#         # This will initialize and load the *global* logged-in session
#         automation = FlipkartAutomation(headful=True) 
#         await automation.initialize_browser() 
        
#         steps = FlipkartSteps(automation)
#         steps.shipping_info = shipping_data
        
#         steps.logger.info(f"Navigating to product page: {product_url}")
#         await automation.page.goto(product_url, wait_until="networkidle")

#         steps.specifications = req.specifications or {} 
#         await steps.step_3_handle_product_options()
#         await steps.step_4_add_to_cart_without_login() 
#         await steps.step_6_proceed_to_shipping()
#         await steps.step_7_fill_shipping_info()
#         await steps.step_8_proceed_to_payment()
        
#         return {"status": "🚀 Automation Completed. Proceed to the payment page", "product_id": req.product_id}

#     except Exception as e:
#         if automation:
#             automation.logger.error(f"❌ Error during full automation run: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
#     finally:
#         if automation:
#             # Assuming 'steps' is defined if 'automation' is
#             try:
#                 steps.logger.info("Automation run finished. Browser will close.")
#             except:
#                 logger.info("Automation run finished. Browser will close.")
#             await automation.close_browser()
            
            
# @router.post("/cleanup_stale_sessions")
# async def cleanup_stale_sessions():
#     """
#     Forcefully closes all active browser sessions that were
#     initiated by /login but never verified.
#     """
#     global live_otp_sessions # Use the new dict name
#     sessions_to_close = list(live_otp_sessions.items())
    
#     if not sessions_to_close:
#         return {"status": "No stale sessions found."}
        
#     count = 0
#     errors = []
    
#     for phone, automation in sessions_to_close: # Key is now phone
#         try:
#             automation.logger.warning(f"Force-closing stale session for phone: {phone}")
#             await automation.close_browser()
#             count += 1
#         except Exception as e:
#             automation.logger.error(f"Error closing session {phone}: {e}")
#             errors.append(phone)
#         finally:
#             if phone in live_otp_sessions:
#                 del live_otp_sessions[phone]
                
#     return {
#         "status": "Cleanup complete",
#         "sessions_closed": count,
#         "sessions_failed_for_phones": errors
#     }