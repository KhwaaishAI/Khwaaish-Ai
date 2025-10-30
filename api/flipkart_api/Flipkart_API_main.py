#!/usr/bin/env python3
import asyncio, json, os
import asyncio
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.agents.flipkart.automation.core import FlipkartAutomation
from app.agents.flipkart.automation.steps import FlipkartSteps
from app.agents.flipkart.main import FlipkartFlow  # use your existing class

app = FastAPI(title="Flipkart Automation API")

# ---- Data Models ----
class LoginRequest(BaseModel):
    phone: str

class ShippingInfo(BaseModel):
    name: str
    mobile: str
    address: str
    city: str
    state: str
    pincode: str

class RunRequest(BaseModel):
    product: str
    use_saved_shipping: bool = True
    shipping: ShippingInfo


# ---- Globals ----
automation: Optional[FlipkartAutomation] = None


# ---- Utils ----
def load_shipping(use_saved=True, override=None) -> Dict[str, Any]:
    session_file = "user_shipping_session.json"
    if use_saved and os.path.exists(session_file):
        try:
            with open(session_file) as f:
                return json.load(f)
        except:
            pass
    if override:
        with open(session_file, "w") as f:
            json.dump(override, f)
        return override
    raise ValueError("Shipping info not found or provided.")


# ---- Endpoints ----
# @app.on_event("startup")
# async def startup():
#     global automation
#     automation = FlipkartAutomation()
#     await automation.initialize_browser()


@app.post("/login")
async def login(req: LoginRequest):
    """Launch Flipkart login page and handle OTP input."""
    global automation
    if not automation:
        return {"error": "Automation not initialized."}
    try:
        steps = FlipkartSteps(automation)
        await steps._login_with_phone()

        return {"status": "✅ Logged in successfully"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/run")
async def run_automation(req: RunRequest, background_tasks: BackgroundTasks):
    """Run full Flipkart automation: search → cart → checkout → payment."""
    global automation
    if not automation:
        return {"error": "Automation not initialized."}
    try:
        shipping_data = req.shipping.dict() if req.shipping else None
        shipping = load_shipping(req.use_saved_shipping, shipping_data)
        flow = FlipkartFlow(automation, FlipkartSteps(automation))
        product = {"name": req.product, "options": {}}

        async def execute_flow():
            success = await flow.execute(product, shipping)
            if success:
                print("✅ Ready for payment — keep browser open until user confirms.")
                while hasattr(automation, "browser") and not automation.browser.is_closed():
                    await asyncio.sleep(2)

        background_tasks.add_task(execute_flow)
        return {"status": "🚀 Flow started", "product": req.product}

    except Exception as e:
        return {"error": str(e)}


@app.on_event("shutdown")
async def shutdown():
    global automation
    if automation:
        await automation.close()
