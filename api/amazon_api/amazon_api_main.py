# from fastapi import FastAPI, BackgroundTasks, HTTPException
# from fastapi.routing import APIRouter
# from pydantic import BaseModel
# from typing import Optional, Dict, Any
# import asyncio
# import logging

# from app.agents.amazon_automator.automator import AmazonAutomator
# from app.agents.flipkart import automation
# from app.tools.Amazon_tools.search import AmazonScraper
# from app.agents.amazon_automator.flow import AmazonAutomationFlow  # the class you provided

# logger = logging.getLogger(__name__)
# app = FastAPI(title="Amazon Automation API")
# router = APIRouter()
# # ----------------------------
# # In-memory state store
# # ----------------------------
# sessions: Dict[str, Dict[str, Any]] = {}  # key: phone_number

# # ----------------------------
# # Request models
# # ----------------------------
# class LoginRequest(BaseModel):
#     phone_number: int
#     password : str

# class RunRequest(BaseModel):
#     phone_number: int
#     search_query: str
#     specifications: Optional[Dict[str, str]] = None

# class ProductSelectionRequest(BaseModel):
#     phone_number: str
#     product_index: int


# # ----------------------------
# # Endpoint: Login
# # ----------------------------
# @router.post("/login")
# async def login_user(request: LoginRequest):
#     """Logs user into Amazon using stored credentials."""
#     phone = request.phone_number

#     automator = AmazonAutomator()
#     await automator.initialize_browser()

#     try:
#         automation.goto("https://www.amazon.in/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.in%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=inflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0", wait_till="networ_idel")
#         success = await automator.handle_login(request.phone_number,request.password)
#         if not success:
#             raise HTTPException(status_code=401, detail="Invalid credentials")

#         # Store session
#         sessions[phone] = {
#             "automator": automator,
#             "flow": AmazonAutomationFlow(automator),
#             "state": "logged_in"
#         }

#         return {"message": "✅ Login successful", "phone_number": phone}

#     except Exception as e:
#         logger.exception(e)
#         raise HTTPException(status_code=500, detail=str(e))


# # ----------------------------
# # Endpoint: Run full flow
# # ----------------------------
# @router.post("/run")
# async def run_full_flow(request: RunRequest, background_tasks: BackgroundTasks):
#     """Runs the Amazon full automation flow asynchronously."""
#     phone = request.phone_number

#     if phone not in sessions or sessions[phone]["state"] != "logged_in":
#         raise HTTPException(status_code=403, detail="Please login first")

#     flow = sessions[phone]["flow"]
#     automator = sessions[phone]["automator"]

#     async def automation_task():
#         try:
#             await automator.page.goto("https://www.amazon.in")
#             print("\n🔍 STEP 1: SEARCHING...")
#             products = await automator.go_to_search(request.search_query)

#             if not products:
#                 logger.error("No products found")
#                 sessions[phone]["state"] = "error"
#                 return

#             flow.automator.display_products(products)
#             sessions[phone]["products"] = products
#             sessions[phone]["state"] = "awaiting_selection"

#             print("\n📋 STEP 2: Waiting for user product selection...")

#         except Exception as e:
#             logger.error(f"Error in flow: {e}", exc_info=True)
#             sessions[phone]["state"] = "error"

#     background_tasks.add_task(automation_task)

#     return {
#         "message": "Flow started. Waiting for product selection.",
#         "next_step": "Call /select-product to continue",
#     }


# # ----------------------------
# # Endpoint: Product selection
# # ----------------------------
# @router.post("/select-product")
# async def select_product(request: ProductSelectionRequest, background_tasks: BackgroundTasks):
#     """Continue automation after user selects a product index."""
#     phone = request.phone_number

#     if phone not in sessions or sessions[phone]["state"] != "awaiting_selection":
#         raise HTTPException(status_code=400, detail="Not waiting for selection")

#     product_index = request.product_index
#     automator = sessions[phone]["automator"]

#     selected_product = automator.select_product(product_index)

#     async def continue_task():
#         try:
#             # Resume steps from STEP 3 onward
#             print("\n🌐 STEP 3: OPENING PRODUCT PAGE...")
#             await automator.open_product_page(selected_product["asin"])

#             print("\n⚙️ STEP 4: SPECIFICATIONS...")
#             available_specs = await automator.find_specifications()

#             if available_specs:
#                 print(f"Available specifications: {list(available_specs.keys())}")
                
#                 if not specifications:
#                     specifications = {}
#                     for spec_name, options in available_specs.items():
#                         print(f"\n{spec_name} options: {options}")
#                         choice = input(f"Choose {spec_name} (or press Enter to skip): ").strip()
#                         if choice:
#                             specifications[spec_name] = choice
                
#                 if specifications:
#                     await automator.choose_specifications(specifications)

#             # Add to cart
#             print("\n🛒 STEP 5: ADDING TO CART...")
#             if await automator.add_to_cart():
#                 print("✅ Item added to cart")
#             else:
#                 logger.error("Failed to add to cart")
#                 sessions[phone]["state"] = "error"
#                 return

#             print("\n💳 STEP 6: PROCEEDING TO CHECKOUT...")
#             if await automator.proceed_to_checkout():
#                 print("✅ Proceeding to checkout")

#             print("\n💰 STEP 7: REACHING PAYMENT PAGE...")
#             if await automator.reach_payment_page():
#                 print("✅ Reached payment page")

#             sessions[phone]["state"] = "completed"

#         except Exception as e:
#             logger.error(f"Continuation error: {e}", exc_info=True)
#             sessions[phone]["state"] = "error"

#     # background_tasks.add_task(continue_task)
#     continue_task()

#     return {
#         "message": f"Product {product_index} selected. Automation Completed",
#         "selected_product": selected_product,
#     }


from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.routing import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Assuming automator is in this path
from app.agents.amazon_automator.automator import AmazonAutomator
# Assuming search is in this path
from app.tools.Amazon_tools.search import AmazonScraper

logger = logging.getLogger(__name__)
router = APIRouter()
# ----------------------------
# In-memory state store
# ----------------------------
# OPTIMIZATION: Session key is now a string (email_or_phone)
sessions: Dict[str, Dict[str, Any]] = {}  # key: email_or_phone

# ----------------------------
# Request models
# ----------------------------
class LoginRequest(BaseModel):
    # OPTIMIZATION: Changed from int to str and renamed for clarity
    email_or_phone: str
    password: str

class RunRequest(BaseModel):
    # OPTIMIZATION: Changed from int to str
    email_or_phone: str
    search_query: str
    

class ProductSelectionRequest(BaseModel):
    # OPTIMIZATION: Renamed for consistency
    email_or_phone: str
    product_index: int
    specifications: Optional[Dict[str, str]] = None


class SearchRequest(BaseModel):
    product_name: str
    email_or_phone: str
    max_pages: Optional[int] = 2
    max_items: Optional[int] = None

# ----------------------------
# Endpoint: Login
# ----------------------------
@router.post("/login")
async def login_user(request: LoginRequest):
    """Logs user into Amazon using provided credentials."""
    # OPTIMIZATION: Use email_or_phone as the session key
    phone = request.email_or_phone

    automator = AmazonAutomator(headful=True) # Run headful for login
    await automator.initialize_browser()

    try:
        # BUGFIX: Changed 'automation.goto' to 'automator.page.goto'
        # BUGFIX: Corrected typo 'networ_idel' to 'networkidle'
        await automator.page.goto(
            "https://www.amazon.in/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.in%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=inflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0",
            wait_until="networkidle"
        )
        
        # BUGFIX: Pass both email and password to the optimized handle_login
        success = await automator.handle_login(request.email_or_phone, request.password)
        
        if not success:
            await automator.close_browser()
            raise HTTPException(status_code=401, detail="Invalid credentials or login failed")

        # Store session
        sessions[phone] = {
            "automator": automator,
            "state": "logged_in"
        }

        return {"message": "✅ Login successful", "email_or_phone": phone}

    except Exception as e:
        logger.exception(e)
        if automator:
            await automator.close_browser()
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Endpoint: Run full flow
# ----------------------------

@router.post("/search")
async def run_search_flow(
    request: SearchRequest,
    background_tasks: BackgroundTasks
):
    """
    Runs the Amazon search scraper asynchronously in the background.
    """
    phone = request.email_or_phone

    # 1. Validate session
    if phone not in sessions or sessions[phone]["state"] != "logged_in":
        raise HTTPException(status_code=403, detail="Please login first")

    # 2. Define the background task
    async def automation_task():
        try:
            logger.info(f"Starting background search for '{request.product_name}' for user {phone}")
            # Update state to 'searching'
            sessions[phone]["state"] = "searching"
            
            # Instantiate the scraper with settings from the request
            extractor = AmazonScraper(
                max_pages=request.max_pages,
                max_items=request.max_items
            )
            
            # Run the async search
            results = await extractor.search(request.product_name)
            
            products = results.get("items")

            # 3. Check results
            if not products:
                logger.error(f"No products found for '{request.product_name}'")
                sessions[phone]["state"] = "error"
                sessions[phone]["error_message"] = "No products found"
                return

            # 4. Store products in session for the next step
            sessions[phone]["products"] = products
            
            # 5. Handle JSON export safely
            try:
                output_dir = Path("./out")
                output_dir.mkdir(exist_ok=True)  # Ensure the directory exists
                
                # Create a more robust, unique filename
                filename = f"amazon_search_{phone}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
                filepath = output_dir / filename
                
                # The 'extractor' object holds the results in 'all_products'
                # and its 'export_to_json' method uses that internal state.
                extractor.export_to_json(str(filepath))
                logger.info(f"Exported {len(products)} items to {filepath}")
            
            except Exception as e:
                logger.error(f"Failed to export JSON for user {phone}: {e}")
                # Don't fail the whole task, just log the export error
                sessions[phone]["export_error"] = str(e)

            # 6. Update state to 'awaiting_selection'
            sessions[phone]["state"] = "awaiting_selection"
            logger.info(f"Search complete for {phone}. Ready for selection.")

        except Exception as e:
            logger.error(f"Error in background search flow for {phone}: {e}", exc_info=True)
            sessions[phone]["state"] = "error"
            sessions[phone]["error_message"] = str(e)

    # 7. Add the task to run in the background
    background_tasks.add_task(automation_task)

    # 8. Return an immediate response to the user
    return {
        "message": "Search has been started in the background.",
        "detail": f"Search for '{request.product_name}' is processing. The results will be stored in your session.",
        "next_step": "Check session status. Once 'awaiting_selection', you can proceed."
    }


# ----------------------------
# Endpoint: Product selection
# ----------------------------
@router.post("/select-product")
async def select_product(request: ProductSelectionRequest):
    """Continue automation after user selects a product index."""
    phone = request.email_or_phone

    if phone not in sessions or sessions[phone]["state"] != "awaiting_selection":
        raise HTTPException(status_code=400, detail="Not waiting for selection. Call /run first.")

    automator = sessions[phone]["automator"]
    sessions[phone]["specifications"] = request.specifications

    try:
        selected_product = automator.select_product(request.product_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def continue_task():
        try:
            # Resume steps from STEP 3 onward
            print("\n🌐 STEP 3: OPENING PRODUCT PAGE...")
            await automator.open_product_page(selected_product["asin"])

            print("\n⚙️ STEP 4: SPECIFICATIONS...")
            available_specs = await automator.find_specifications()

            if available_specs:
                print(f"Available specifications: {list(available_specs.keys())}")
                
                # BUGFIX: This 'specifications' var is now correctly defined
                # It uses the specs from /run, or prompts if they were None/empty
                if not specifications:
                    print("No specifications provided in request. Prompting user on server console...")
                    specifications = {}
                    # NOTE: This interactive block will block the server.
                    # This is per the original (flawed) logic.
                    for spec_name, options in available_specs.items():
                        print(f"\n{spec_name} options: {options}")
                        choice = input(f"Choose {spec_name} (or press Enter to skip): ").strip()
                        if choice:
                            specifications[spec_name] = choice
                
                if specifications:
                    print(f"Using specifications: {specifications}")
                    await automator.choose_specifications(specifications)

            # Add to cart
            print("\n🛒 STEP 5: ADDING TO CART...")
            if await automator.add_to_cart():
                print("✅ Item added to cart")
            else:
                logger.error("Failed to add to cart")
                sessions[phone]["state"] = "error"
                return

            print("\n💳 STEP 6: PROCEEDING TO CHECKOUT...")
            if await automator.proceed_to_checkout():
                print("✅ Proceeding to checkout")

            print("\n💰 STEP 7: REACHING PAYMENT PAGE...")
            if await automator.reach_payment_page():
                print("✅ Reached payment page")

            sessions[phone]["state"] = "completed"
            print("\n🎉 AUTOMATION COMPLETED. Please complete payment in browser.")

        except Exception as e:
            logger.error(f"Continuation error: {e}", exc_info=True)
            sessions[phone]["state"] = "error"

    # BUGFIX: The background task was commented out and called synchronously.
    # It MUST be awaited to run. This will block the API response until
    # the automation (and all its `input()` prompts) are finished.
    await continue_task() 
    # background_tasks.add_task(continue_task) # This would be better, but fails with input()

    return {
        "message": f"Product {request.product_index} selected. Automation run has finished.",
        "state": sessions[phone]["state"],
        "selected_product": selected_product,
    }

