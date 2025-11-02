from fastapi import APIRouter
from app.agents.swiggy.swiggy_automation import run_agent
import asyncio

router = APIRouter()

@router.post("/swiggy")
async def swiggy_endpoint(query: str, location: str, phone_number: str):
    loop = asyncio.get_event_loop()
    result = await loop.create_task(run_agent(query, location, phone_number))
    return {"status": "success", "result": result}
