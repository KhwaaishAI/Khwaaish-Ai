from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import logging

from app.agents.amazon_automator.automator import AmazonAutomator
from app.tools.Amazon_tools.search import AmazonScraper
from app.agents.amazon_automator.flow import AmazonAutomationFlow  # the class you provided

logger = logging.getLogger(__name__)
app = FastAPI(title="Amazon Automation API")

# ----------------------------
# In-memory state store
# ----------------------------
sessions: Dict[str, Dict[str, Any]] = {}  # key: phone_number

# ----------------------------
# Request models
# ----------------------------
class LoginRequest(BaseModel):
    phone_number: str
    password: str

class RunRequest(BaseModel):
    phone_number: str
    search_query: str
    specifications: Optional[Dict[str, str]] = None

class ProductSelectionRequest(BaseModel):
    phone_number: str
    product_index: int


# ----------------------------
# Endpoint: Login
# ----------------------------
@app.post("/login")
async def login_user(request: LoginRequest):
    """Logs user into Amazon using stored credentials."""
    phone = request.phone_number

    automator = AmazonAutomator()
    await automator.initialize_browser()

    try:
        success = await automator.login(request.phone_number, request.password)
        if not success:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Store session
        sessions[phone] = {
            "automator": automator,
            "flow": AmazonAutomationFlow(automator),
            "state": "logged_in"
        }

        return {"message": "✅ Login successful", "phone_number": phone}

    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# Endpoint: Run full flow
# ----------------------------
@app.post("/run")
async def run_full_flow(request: RunRequest, background_tasks: BackgroundTasks):
    """Runs the Amazon full automation flow asynchronously."""
    phone = request.phone_number

    if phone not in sessions or sessions[phone]["state"] != "logged_in":
        raise HTTPException(status_code=403, detail="Please login first")

    flow = sessions[phone]["flow"]
    automator = sessions[phone]["automator"]

    async def automation_task():
        try:
            await automator.page.goto("https://www.amazon.in")
            print("\n🔍 STEP 1: SEARCHING...")
            products = await automator.go_to_search(request.search_query)

            if not products:
                logger.error("No products found")
                sessions[phone]["state"] = "error"
                return

            flow.automator.display_products(products)
            sessions[phone]["products"] = products
            sessions[phone]["state"] = "awaiting_selection"

            print("\n📋 STEP 2: Waiting for user product selection...")

        except Exception as e:
            logger.error(f"Error in flow: {e}", exc_info=True)
            sessions[phone]["state"] = "error"

    background_tasks.add_task(automation_task)

    return {
        "message": "Flow started. Waiting for product selection.",
        "next_step": "Call /select-product to continue",
    }


# ----------------------------
# Endpoint: Product selection
# ----------------------------
@app.post("/select-product")
async def select_product(request: ProductSelectionRequest, background_tasks: BackgroundTasks):
    """Continue automation after user selects a product index."""
    phone = request.phone_number

    if phone not in sessions or sessions[phone]["state"] != "awaiting_selection":
        raise HTTPException(status_code=400, detail="Not waiting for selection")

    product_index = request.product_index
    flow = sessions[phone]["flow"]
    automator = sessions[phone]["automator"]
    products = sessions[phone]["products"]

    selected_product = automator.select_product(product_index)

    async def continue_task():
        try:
            # Resume steps from STEP 3 onward
            print("\n🌐 STEP 3: OPENING PRODUCT PAGE...")
            await automator.open_product_page(selected_product["asin"])

            print("\n⚙️ STEP 4: SPECIFICATIONS...")
            available_specs = await automator.find_specifications()

            if available_specs:
                print(f"Available specs: {list(available_specs.keys())}")

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

        except Exception as e:
            logger.error(f"Continuation error: {e}", exc_info=True)
            sessions[phone]["state"] = "error"

    background_tasks.add_task(continue_task)

    return {
        "message": f"Product {product_index} selected. Continuing automation...",
        "selected_product": selected_product,
    }
