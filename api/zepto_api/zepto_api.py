from fastapi import FastAPI
from pydantic import BaseModel
from playwright.async_api import async_playwright
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agents.zepto.zepto_automation import automate_zepto
from app.prompts.zepto_prompts.zepto_prompts import analyze_query

app = FastAPI()

class OrderRequest(BaseModel):
    query: str
    location: str
    mobile_number: str

@app.post("/zepto")
async def create_order(request: OrderRequest):
    shopping_list = analyze_query(request.query)
    if shopping_list:
        async with async_playwright() as p:
            await automate_zepto(shopping_list, request.location, request.mobile_number, p)
        return {"status": "success", "shopping_list": shopping_list}
    else:
        return {"status": "error", "message": "Could not create a shopping list."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1")
