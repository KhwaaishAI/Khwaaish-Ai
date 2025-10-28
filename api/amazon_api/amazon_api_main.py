from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket
from pydantic import BaseModel
from typing import Optional, Dict
import logging
import asyncio
import json
from app.agents.amazon_automator.automator import AmazonAutomator

app = FastAPI()
logger = logging.getLogger(__name__)

class LoginRequest(BaseModel):
    email: str
    password: str

class SearchRequest(BaseModel):
    search_query: str
    
class ProductSelectionRequest(BaseModel):
    product_index: int
    specifications: Optional[Dict[str, str]] = None

class OrderResponse(BaseModel):
    status: str
    message: str
    data: Optional[Dict] = None

# Session storage
sessions = {}

@app.post("/api/login")
async def login(req: LoginRequest):
    """Step 1: User login - returns session ID."""
    try:
        automator = AmazonAutomator()
        await automator.initialize_browser()
        await automator.page.goto("https://www.amazon.in")
        
        session_id = f"sess-{hash(req.email) % 1000000}"
        sessions[session_id] = {"automator": automator, "email": req.email}

        # Use AmazonAutomator.handle_login for interactive login flow
        login_success = await automator.handle_login(email=req.email)
        if not login_success:
            raise HTTPException(status_code=401, detail="Login failed. Please check credentials or try again.")
        
        return OrderResponse(
            status="logged_in",
            message="Login successful",
            data={"session_id": session_id}
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/search")
async def search(req: SearchRequest, session_id: str):
    """Step 2: Search and display products."""
    if session_id not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    try:
        automator = sessions[session_id]["automator"]
        products = await automator.go_to_search(req.search_query)
        
        if not products:
            raise HTTPException(status_code=404, detail="No products found")
        
        # Format products for display
        product_list = [
            {
                "index": i+1,
                "name": p.get("name", "N/A"),
                "price": p.get("price", "N/A"),
                "asin": p.get("asin")
            }
            for i, p in enumerate(products[:10])
        ]
        
        sessions[session_id]["products"] = products
        
        return OrderResponse(
            status="products_found",
            message="Select a product",
            data={"products": product_list}
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/select-product")
async def select_product(req: ProductSelectionRequest, session_id: str):
    """Step 3-7: Select product, add specs, checkout."""
    if session_id not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    try:
        automator = sessions[session_id]["automator"]
        products = sessions[session_id].get("products", [])
        
        if not products or req.product_index < 1 or req.product_index > len(products):
            raise HTTPException(status_code=400, detail="Invalid product index")
        
        # Select & open product
        selected = automator.select_product(req.product_index)
        await automator.open_product_page(selected['asin'])
        
        # Specs
        specs = await automator.find_specifications()
        if specs and req.specifications:
            await automator.choose_specifications(req.specifications)
        
        # Cart
        if not await automator.add_to_cart():
            raise HTTPException(status_code=400, detail="Failed to add to cart")
        
        # Checkout
        if not await automator.proceed_to_checkout():
            raise HTTPException(status_code=400, detail="Checkout failed")
        
        if not await automator.reach_payment_page():
            raise HTTPException(status_code=400, detail="Payment page failed")
        
        await automator.display_checkout_summary()
        sessions[session_id]["order_ready"] = True
        
        return OrderResponse(
            status="ready_for_payment",
            message="Review payment page in browser. Complete payment manually.",
            data={
                "product": selected['name'],
                "next": "Complete payment and click 'Place Order'"
            }
        )
    except Exception as e:
        logger.error(f"Selection error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/cleanup/{session_id}")
async def cleanup(session_id: str):
    """Cleanup session and close browser."""
    if session_id in sessions:
        try:
            await sessions[session_id]["automator"].close_browser()
            del sessions[session_id]
        except:
            pass
    
    return OrderResponse(status="cleaned_up", message="Session closed")

@app.get("/api/session-status/{session_id}")
async def session_status(session_id: str):
    """Check current session status."""
    if session_id not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    return {
        "session_id": session_id,
        "email": sessions[session_id].get("email"),
        "order_ready": sessions[session_id].get("order_ready", False)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)