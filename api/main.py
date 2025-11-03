from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.amazon_api import amazon_api_main  
from api.flipkart_api import Flipkart_API_main 

# -------------------------------------------------
# Initialize app once
# -------------------------------------------------
app = FastAPI(title="My API")

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
# app.include_router(Flipkart_API_main.router, prefix="/flipkart_automation", tags=["Flipkart-Automation"])
app.include_router(amazon_api_main.router, prefix="/amazon_aitomation", tags=["Amazon-Automation"])