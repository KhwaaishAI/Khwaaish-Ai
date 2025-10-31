from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from amazon_api import amazon_api_main  
from flipkart_api import Flipkart_API_main 
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ride_booking_api import api
from blinkit_api.blinkit_api import router as blinkit_router
from zepto_api.zepto_api import router as zepto_router
from swiggy_api.swiggy_api import router as swiggy_router

# -------------------------------------------------
# Initialize app once
# -------------------------------------------------
app = FastAPI(
    title="Khwaaish API",
    description="A single API to rule them all.",
    version="1.0.0",
)

origins = [
    "http://127.0.0.1:3000",
    "http://localhost:3000"
]
# -------------------------------------------------
# CORS middleware
# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # update with frontend origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Routers
# -------------------------------------------------
app.include_router(Flipkart_API_main.router, prefix="/flipkart_automation", tags=["Flipkart_Automation"])
app.include_router(amazon_api_main.router, prefix="/amazon_aitomation", tags=["Amazon_Automation"])
app.include_router(api.router, prefix="/ride-booking", tags=["ride-booking"])
app.include_router(blinkit_router, prefix="/api", tags=["blinkit"])
app.include_router(zepto_router, prefix="/api", tags=["zepto"])
app.include_router(swiggy_router, prefix="/api", tags=["swiggy"])
