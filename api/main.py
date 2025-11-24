from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.amazon_api import amazon_api_main  
from api.flipkart_api import Flipkart_API_main 
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.ride_booking_api import api
from api.blinkit_api.blinkit_api import router as blinkit_router
from api.zepto_api.zepto_api import router as zepto_router
from api.swiggy_api.swiggy_api import router as swiggy_router
from api.myntra_api.myntra_api import router as myntra_router
import uvicorn

# -------------------------------------------------
# Initialize app once
# -------------------------------------------------
app = FastAPI(
    title="Khwaaish API",
    description="A single API to rule them all.",
    version="1.0.0",
)

# -------------------------------------------------
# CORS middleware
# -------------------------------------------------
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins="*",  # update with frontend origins in production
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://khwaaish.com",
        "https://www.khwaaish.com",
        "https://api.khwaaish.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Routers
# -------------------------------------------------
# app.include_router(Flipkart_API_main.router, prefix="/flipkart_automation", tags=["Flipkart_Automation"])
app.include_router(amazon_api_main.router, prefix="/amazon_aitomation", tags=["Amazon_Automation"])
app.include_router(api.router, prefix="/ride-booking", tags=["ride-booking"])
app.include_router(blinkit_router, prefix="/api", tags=["blinkit"])
app.include_router(zepto_router, prefix="/api", tags=["zepto"])
app.include_router(swiggy_router, prefix="/api", tags=["swiggy"])
app.include_router(myntra_router, prefix="/api", tags=["myntra"])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)