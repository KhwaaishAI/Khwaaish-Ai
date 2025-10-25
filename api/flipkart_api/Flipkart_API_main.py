#!/usr/bin/env python3
import asyncio
import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# --- Import your existing modules ---
from app.agents.flipkart.automation.core import FlipkartAutomation
from app.agents.flipkart.automation.steps import FlipkartSteps

# --- Import product configs ---
from app.agents.flipkart.main import PRODUCT_CONFIGS, DEFAULT_SHIPPING_INFO, SmartProductAutomation  # adjust import path if needed

app = FastAPI(title="Flipkart Smart Automation API", version="1.0")

# ---------------------------
# Request Models
# ---------------------------
class ShippingInfo(BaseModel):
    name: str = Field(default="John Doe")
    mobile: str = Field(default="9876543210")
    pincode: str = Field(default="110001")
    address: str = Field(default="123 Main Street, Connaught Place")
    locality: str = Field(default="Connaught Place")
    city: str = Field(default="New Delhi")
    state: str = Field(default="Delhi")
    landmark: Optional[str] = Field(default="Near Metro Station")
    address_type: str = Field(default="Home")

class RunRequest(BaseModel):
    product_key: str = Field(..., description="Key from PRODUCT_CONFIGS, e.g., 'iphone_15_pro'")
    shipping_info: Optional[ShippingInfo] = None

# ---------------------------
# Main Endpoint
# ---------------------------
@app.post("/run_automation")
async def run_automation(req: RunRequest):
    if req.product_key not in PRODUCT_CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid product key")

    product_info = PRODUCT_CONFIGS[req.product_key]
    shipping_info = req.shipping_info.dict() if req.shipping_info else DEFAULT_SHIPPING_INFO

    automation = FlipkartAutomation()
    try:
        automation.logger.info(f"🚀 Starting automation for {product_info['name']}")

        if not await automation.initialize_browser():
            raise HTTPException(status_code=500, detail="Failed to initialize browser")

        smart_automation = SmartProductAutomation(automation)
        await smart_automation.execute_direct_cart_flow(product_info, shipping_info)

        return {
            "status": "success",
            "product": product_info["name"],
            "shipping_city": shipping_info["city"],
            "message": "Automation completed successfully. Proceed to payment manually."
        }

    except Exception as e:
        automation.logger.error(f"❌ Automation failed: {e}")
        return {"status": "error", "message": str(e)}

    finally:
        await automation.close()

# ---------------------------
# Health Check
# ---------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Flipkart Automation API running"}

if __name__ == "__main__":
    import uvicorn
    os.makedirs("debug_screenshots", exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8000)
