from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import logging
from pathlib import Path
from datetime import datetime
import json
import re

# Assuming automator is in this path
from app.agents.amazon_automator.automator import AmazonAutomator
# Assuming search is in this path
from app.tools.Amazon_tools.search import AmazonScraper

logger = logging.getLogger(__name__)
router = APIRouter()

# ----------------------------
# In-memory state store
# ----------------------------
# This holds simple API state, like "logged_in"
sessions: Dict[str, Dict[str, Any]] = {}  # key: email_or_phone

# ----------------------------
# Helper Functions
# ----------------------------

def _get_session_filepath(email_or_phone: str) -> str:
    """Generates a consistent session file path for a user."""
    # Sanitize email/phone to be a safe filename
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', email_or_phone)
    return f".{safe_name}_session.json"

def _get_product_filepath(product_name: str) -> Path:
    """Generates a consistent, safe file path for a product search."""
    # Ensure the ./out directory exists
    output_dir = Path("./out/Amazon")
    output_dir.mkdir(exist_ok=True)
    
    # Sanitize product name to be a safe filename
    safe_name = re.sub(r'[^a-zA-Z0-9\s]', '', product_name).strip()
    safe_name = re.sub(r'\s+', '_', safe_name).lower()
    if not safe_name:
        safe_name = "default_product"
    
    return output_dir / f"{safe_name}.json"

async def _is_session_valid(session_file: str) -> bool:
    """
    Headlessly checks if a saved session is still valid
    by loading a page and looking for a logged-in indicator.
    """
    if not Path(session_file).exists():
        return False
        
    logger.info(f"Validating session: {session_file}")
    automator = AmazonAutomator(
        headful=False, # Run headlessly
        session_store_path=session_file
    )
    try:
        await automator.initialize_browser()
        # Go to a page that reliably shows login state
        await automator.page.goto("https://www.amazon.in/gp/css/homepage.html", wait_until="networkidle")
        
        # Look for a "Hello" message or account holder name
        # This selector is more reliable than just checking for "Sign in"
        logged_in_indicator = automator.page.locator("#nav-link-accountList-nav-line-1")
        content = await logged_in_indicator.text_content(timeout=5000)
        
        if "Hello, Sign in" in content or not content:
            logger.warning(f"Session {session_file} is expired.")
            return False
        
        logger.info(f"Session {session_file} is valid.")
        return True
    except Exception as e:
        logger.warning(f"Session validation failed for {session_file}: {e}")
        return False
    finally:
        if automator:
            await automator.close_browser()

# ----------------------------
# Request models
# ----------------------------
class LoginRequest(BaseModel):
    email_or_phone: str
    password: str

class SearchRequest(BaseModel):
    product_name: str
    max_pages: Optional[int] = 2
    max_items: Optional[int] = None

class ProductSelectionRequest(BaseModel):
    email_or_phone: str
    product_name: str # User specifies which search to use
    product_index: int
    specifications: Optional[Dict[str, str]] = None

# ----------------------------
# Endpoint: Login
# ----------------------------
@router.post("/login")
async def login_user(request: LoginRequest):
    """
    Logs user in. If a valid session file exists, it confirms login.
    If not, or if session is expired, it performs a new login.
    """
    phone = request.email_or_phone
    session_file_path = _get_session_filepath(phone)

    # Check if a valid session *already* exists
    if await _is_session_valid(session_file_path):
        # Update in-memory state
        sessions[phone] = {
            "state": "logged_in",
            "session_file": session_file_path
        }
        return {"message": "✅ Already logged in. Session is valid.", "email_or_phone": phone}

    # If session is invalid or doesn't exist, perform a new login
    logger.info(f"No valid session found for {phone}. Performing new login.")
    automator = AmazonAutomator(
        headful=True, # Headful for manual login/CAPTCHA
        session_store_path=session_file_path
    )
    
    try:
        await automator.initialize_browser() # This will load old session if it exists
        
        await automator.page.goto(
            "https://www.amazon.in/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.in%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=inflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0",
            wait_until="networkidle"
        )
        
        success = await automator.handle_login(request.email_or_phone, request.password)
        
        if not success:
            raise HTTPException(status_code=401, detail="Invalid credentials or login failed")

        # Store simple state in the in-memory session
        sessions[phone] = {
            "state": "logged_in",
            "session_file": session_file_path
        }

        return {"message": "✅ Login successful", "email_or_phone": phone}

    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # CRITICAL: Always close the browser, which saves the new session
        if automator:
            await automator.close_browser()

# ----------------------------
# Endpoint: Search
# ----------------------------

@router.post("/search")
async def run_search_flow(
    request: SearchRequest,
    background_tasks: BackgroundTasks
):
    """
    Searches for a product. If a JSON file exists in ./out, returns it.
    If not, starts a background scraping task. Independent of login.
    """
    product_file_path = _get_product_filepath(request.product_name)

    # 1. Check if file already exists in cache
    if product_file_path.exists():
        logger.info(f"Found cached product file: {product_file_path}")
        # Optionally, load and return the data
        try:
            with open(product_file_path, "r") as f:
                data = json.load(f)
            return {
                "message": "Product found in cache.",
                "file_path": str(product_file_path),
                "data": data # Returning the data
            }
        except Exception as e:
            logger.warning(f"Could not read cache file {product_file_path}: {e}")
            # Proceed to re-scrape

    # 2. Define the background task if file not found or unreadable
    async def scraping_task():
        try:
            logger.info(f"Starting background scrape for '{request.product_name}'")
            extractor = AmazonScraper(
                max_pages=request.max_pages,
                max_items=request.max_items
            )
            results = await extractor.search(request.product_name)
            
            if not results.get("items"):
                logger.error(f"No products found for '{request.product_name}'")
                return

            # Save the results to the product file
            extractor.export_to_json(str(product_file_path))
            logger.info(f"Search complete. Saved to {product_file_path}")

        except Exception as e:
            logger.error(f"Error in background scraping flow: {e}", exc_info=True)

    # 3. Add the task to run in the background
    background_tasks.add_task(scraping_task)

    # 4. Return an immediate response
    return {
        "message": "Search started in the background.",
        "detail": f"No cache found for '{request.product_name}'. Scraper is running.",
        "output_file": str(product_file_path)
    }

# ----------------------------
# Endpoint: Product selection
# ----------------------------
@router.post("/select-product")
async def select_product(request: ProductSelectionRequest):
    """
    Runs the checkout automation for a selected product.
    Requires that the product JSON exists and the user is logged in.
    """
    phone = request.email_or_phone
    product_name = request.product_name
    product_file_path = _get_product_filepath(product_name)

    # 1. Check if the product file exists
    if not product_file_path.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"Product file not found for '{product_name}'. Please call /search first."
        )

    # 2. Check if the user is logged in (in-memory state)
    if phone not in sessions or sessions[phone].get("state") != "logged_in":
        raise HTTPException(
            status_code=403, 
            detail="User not logged in. Please call /login first."
        )
    
    session_file = sessions[phone].get("session_file")
    if not session_file:
        raise HTTPException(status_code=403, detail="Session file path not found. Please /login again.")

    # 3. Load product data from the file
    try:
        with open(product_file_path, "r") as f:
            product_data = json.load(f)
        products_list = product_data.get("items")
        if not products_list:
            raise HTTPException(status_code=404, detail="Product file is empty or invalid.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read product file: {e}")

    # 4. Initialize Automator for the checkout flow
    automator = AmazonAutomator(
        headful=True, # User must see this flow
        session_store_path=session_file
    )
    
    specifications = request.specifications

    try:
        # This will load the saved session file and be logged in
        await automator.initialize_browser()
        
        
        # Select the product from the list
        selected_product = automator.select_product(request.product_name,request.product_index)

        # 5. Define and run the continuation task (synchronously)
        async def continue_task():
            try:
                print("\n🌐 STEP 3: OPENING PRODUCT PAGE...")
                await automator.open_product_page(selected_product)

                print("\n⚙️ STEP 4: SPECIFICATIONS...")
                available_specs = await automator.find_specifications()

                if available_specs:
                #     print(f"Available specifications: {list(available_specs.keys())}")
                    
                #     local_specs = specifications # Use specs from request
                #     if not local_specs:
                #         print("No specifications provided in request. Prompting user on server console...")
                #         local_specs = {} # Re-init as empty dict
                #         for spec_name, options in available_specs.items():
                #             print(f"\n{spec_name} options: {options}")
                #             choice = input(f"Choose {spec_name} (or press Enter to skip): ").strip()
                #             if choice:
                #                 local_specs[spec_name] = choice
                    local_specs = specifications 
                    if local_specs:
                            print(f"Using specifications: {local_specs}")
                            await automator.choose_specifications(local_specs)

                print("\n🛒 STEP 5: ADDING TO CART...")
                if not await automator.add_to_cart():
                    raise Exception("Failed to add to cart")

                print("\n💳 STEP 6: PROCEEDING TO CHECKOUT...")
                if not await automator.proceed_to_checkout():
                    raise Exception("Failed to proceed to checkout")

                print("\n💰 STEP 7: REACHING PAYMENT PAGE...")
                if not await automator.reach_payment_page():
                    raise Exception("Failed to reach payment page")

                sessions[phone]["state"] = "completed"
                print("\n🎉 AUTOMATION COMPLETED. Please complete payment in browser.")

            except Exception as e:
                logger.error(f"Continuation error: {e}", exc_info=True)
                sessions[phone]["state"] = "error"
                raise # Re-raise to be caught by the outer block

        # 6. Run the task
        await continue_task() 

        return {
            "message": f"Product {request.product_index} selected. Automation run has finished.",
            "state": sessions[phone]["state"],
            "selected_product": selected_product,
        }
    except Exception as e:
        # Catch errors from continue_task or initialization
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
    finally:
        # 7. CRITICAL: Always close the browser when done
        if automator:
            await automator.close_browser()
            # Reset state to 'logged_in' after completion or error
            if sessions.get(phone):
                 sessions[phone]["state"] = "logged_in"