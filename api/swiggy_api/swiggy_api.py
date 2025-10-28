from fastapi import FastAPI
from pydantic import BaseModel
from app.agents.swiggy.swiggy_automation import run_agent
import asyncio

app = FastAPI()

class OrderRequest(BaseModel):
    item: str
    restaurant: str
    location: str
    phone_number: str

@app.post("/order")
async def create_order(order: OrderRequest):
    result = await run_agent(
        item=order.item,
        restaurant=order.restaurant,
        location=order.location,
        phone_number=order.phone_number
    )
    return {"message": result}
