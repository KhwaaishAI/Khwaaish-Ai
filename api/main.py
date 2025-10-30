from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from api.ride_booking_api import api

# -------------------------------------------------
# Initialize app once
# -------------------------------------------------
app = FastAPI(title="Khwaaish-api")

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
app.include_router(api.router, prefix="/ride-booking", tags=["ride-booking"])

