import asyncio
import uuid
import asyncio
import traceback
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import shutil
from typing import Dict, Any, List, Optional
import re
from fastapi import APIRouter

# from app.agents.ride_booking.ola.core import OlaAutomation
from app.agents.ride_booking.uber.core import UberAutomation
from app.agents.ride_booking.rapido.core import RapidoAutomation
from app.agents.ride_booking.utills.logger import setup_logger
from app.agents.ride_booking.config import Config

# --- Pydantic Models for API Request/Response ---

class RideSearchRequest(BaseModel):
    """Defines the data needed to perform a ride search."""
    pickup_location: str
    destination_location: str
    start_from_login: bool = False
    

class Ride(BaseModel):
    """A structured model for a single ride option."""
    platform: str
    name: str
    price: Optional[str] = None
    raw_details: Dict[str, Any]

class RideSearchResponse(BaseModel):
    """The response containing the job ID and all found ride options."""
    job_id: str
    rides: List[Ride]

class RideBookingRequest(BaseModel):
    """The request to book a specific ride, using its raw details."""
    job_id: str
    ride_details: Dict[str, Any]

class BookingResponse(BaseModel):
    """The response after a booking attempt."""
    status: str
    message: str

# --- API Setup ---

app = FastAPI(
    title="Ride Booking Aggregator API",
    description="An API to automate searching and booking rides on Ola and Uber.",
)

router = APIRouter()

logger = setup_logger()

# In-memory storage for active automation jobs.
# In a production scenario, you might replace this with Redis or another persistent store.
active_jobs: Dict[str, Dict[str, Any]] = {}

@app.on_event("shutdown")
async def shutdown_event():
    """
    This function is called when the FastAPI application is shutting down.
    It cleans up any active automation jobs to prevent zombie browser processes.
    """
    logger.info("FastAPI server is shutting down. Cleaning up active ride-booking jobs...")
    
    if not active_jobs:
        logger.info("No active ride-booking jobs to clean up.")
        return

    # Create a list of 'stop' tasks to run in parallel for all active jobs
    shutdown_tasks = []
    # Use list(active_jobs.items()) to avoid "dictionary changed size during iteration" error
    for job_id, job_data in list(active_jobs.items()):
        logger.info(f"Scheduling cleanup for job_id: {job_id}")
        if job_data.get("uber"):
            shutdown_tasks.append(job_data["uber"].stop())
        if job_data.get("rapido"):
            shutdown_tasks.append(job_data["rapido"].stop())
    
    await asyncio.gather(*shutdown_tasks)
    logger.info(f"Cleaned up {len(active_jobs)} active job(s). Shutdown complete.")

def _parse_price(price_str: Optional[str]) -> float:
    """Helper function to parse price strings like '₹1,234' into a float."""
    if price_str is None:
        return float('inf')
    # Remove currency symbols, commas, and whitespace, then convert to float
    cleaned_price = re.sub(r'[^\d.]', '', price_str)
    return float(cleaned_price) if cleaned_price else float('inf')


# --- API Endpoints ---

@router.post("/search", response_model=RideSearchResponse)
async def search_for_rides(request: RideSearchRequest):
    """
    Initializes a new automation job, searches for rides on both platforms,
    and returns the combined, sorted results.

    Note: This is a long-running endpoint and may take 30-60 seconds to respond.
    """
    job_id = str(uuid.uuid4())
    logger.info(f"Creating new job with ID: {job_id}")
    
    # --- New Session Logic ---
    # We will use a fixed default session name internally.
    default_session_name = "default_session"
    
    uber_automation = UberAutomation()
    rapido_automation = RapidoAutomation()

    if request.start_from_login:
        logger.info(f"Job {job_id}: 'start_from_login' is true. Deleting old default session data to force a new login.")
        config = Config()
        uber_session_path = os.path.join(config.SESSIONS_DIR, f"uber_profile_{default_session_name}")
        rapido_session_path = os.path.join(config.SESSIONS_DIR, f"rapido_profile_{default_session_name}")
        
        if os.path.exists(uber_session_path):
            shutil.rmtree(uber_session_path)
            logger.info(f"Removed old Uber session: {uber_session_path}")
        if os.path.exists(rapido_session_path):
            shutil.rmtree(rapido_session_path)
            logger.info(f"Removed old Rapido session: {rapido_session_path}")
    else:
        logger.info(f"Job {job_id}: 'start_from_login' is false. Using default saved session.")
    try:
        # --- 1. Initialize Browsers ---
        logger.info(f"Job {job_id}: Initializing browsers and sessions...")
        await asyncio.gather(
            uber_automation.initialize(default_session_name),
            rapido_automation.initialize(default_session_name)
        )
        logger.info(f"Job {job_id}: Browsers are ready.")

    except Exception as e:
        error_message = f"Initialization failed for job {job_id}: {e}\n{traceback.format_exc()}"
        logger.error(error_message)
        # Ensure cleanup even on initialization failure
        await asyncio.gather(uber_automation.stop(), rapido_automation.stop())
        raise HTTPException(status_code=500, detail=f"Browser initialization failed: {e}")

    # --- 5. Search for Rides in Parallel (from aggregator.py) ---
    # ola_task = ola_automation.search_rides(request.pickup_location, request.destination_location)
    uber_task = uber_automation.search_rides(request.pickup_location, request.destination_location)
    rapido_task = rapido_automation.search_rides(request.pickup_location, request.destination_location)
    # return_exceptions=True prevents one failure from stopping the other.
    uber_results, rapido_results = await asyncio.gather(uber_task, rapido_task, return_exceptions=True)

    # --- 6. Combine and Process Results (from aggregator.py) ---
    all_rides = []
    api_response_rides = []

    # if isinstance(ola_results, list):
    #     logger.info(f"Job {job_id}: Found {len(ola_results)} rides on Ola.")
    #     for ride in ola_results:
    #         ride['platform'] = 'Ola' # Add platform to the original ride object for matching
    #         # The original 'ride' object contains the non-serializable Playwright locator.
    #         # We store it in 'all_rides' for the booking step.
    #         all_rides.append(ride)
            
    #         # For the API response, we create a serializable copy and remove the locator.
    #         serializable_details = ride.copy()
    #         serializable_details.pop('locator', None) # Safely remove the locator
    #         serializable_details['platform'] = 'Ola' # Ensure platform is in details
    #         api_response_rides.append(Ride(platform='Ola', name=ride['name'], price=ride.get('price'), raw_details=serializable_details))
    # else:
    #     logger.error(f"Job {job_id}: Failed to get Ola rides: {ola_results}")

    if isinstance(uber_results, list):
        logger.info(f"Job {job_id}: Found {len(uber_results)} rides on Uber.")
        for ride in uber_results:
            ride['platform'] = 'Uber' # Add platform to the original ride object for matching
            # Uber results are already JSON-friendly.
            all_rides.append(ride)
            serializable_details = ride.copy()
            serializable_details['platform'] = 'Uber' # Ensure platform is in details
            api_response_rides.append(Ride(platform='Uber', name=ride['name'], price=ride.get('price'), raw_details=serializable_details))
    else:
        logger.error(f"Job {job_id}: Failed to get Uber rides: {uber_results}")

    if isinstance(rapido_results, list):
        logger.info(f"Job {job_id}: Found {len(rapido_results)} rides on Rapido.")
        for ride in rapido_results:
            ride['platform'] = 'Rapido' # Add platform to the original ride object for matching
            all_rides.append(ride)
            
            # For the API response, create a serializable copy and remove the locator.
            serializable_details = ride.copy()
            serializable_details.pop('locator', None) # Safely remove the locator
            serializable_details['platform'] = 'Rapido' # Ensure platform is in details
            api_response_rides.append(Ride(platform='Rapido', name=ride['name'], price=ride.get('price'), raw_details=serializable_details))
    else:
        logger.error(f"Job {job_id}: Failed to get Rapido rides: {rapido_results}")

    # Store the necessary objects for the booking step
    active_jobs[job_id] = {
        # "ola": ola_automation,
        "uber": uber_automation,
        "rapido": rapido_automation,
        "all_rides": all_rides
    }

    # Sort the rides by price before returning them
    sorted_api_rides = sorted(api_response_rides, key=lambda r: _parse_price(r.price))

    return RideSearchResponse(job_id=job_id, rides=sorted_api_rides)


@router.post("/book", response_model=BookingResponse)
async def book_a_ride(request: RideBookingRequest):
    """
    Books the selected ride for a given job and then cleans up the browser sessions.
    """
    job_id = request.job_id
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found.")

    job = active_jobs[job_id]
    # ola_automation = job["ola"]
    uber_automation = job["uber"]
    rapido_automation = job["rapido"]

    # --- FIX: Make the endpoint robust to handle nested raw_details ---
    # If the user sends the whole Ride object, we extract the inner raw_details.
    # Otherwise, we assume the user sent the raw_details object directly.
    selected_ride = request.ride_details.get('raw_details', request.ride_details)

    # Now, 'selected_ride' is guaranteed to be the dictionary with product_id, name, etc.
    platform = selected_ride.get('platform')

    if not platform:
        raise HTTPException(status_code=400, detail="Ride details must include a 'platform' (Ola or Uber).")

    # --- Find the original ride object from the server's stored list ---
    # This is crucial because the original object has the Playwright locator for Ola.
    ride_to_book = None
    for original_ride in job["all_rides"]:
        # Match based on platform and a unique identifier (product_id for Uber, name for Ola)
        if original_ride.get('platform') == platform:
            if platform == 'Uber' and original_ride.get('product_id') == selected_ride.get('product_id'):
                ride_to_book = original_ride
                break
            elif platform == 'Rapido' and original_ride.get('name') == selected_ride.get('name'):
                ride_to_book = original_ride
                break
    
    if not ride_to_book:
        raise HTTPException(status_code=404, detail="The selected ride could not be found in the last search results. Please search again.")

    logger.info(f"Job {job_id}: Attempting to book '{selected_ride.get('name')}' on {platform}.")
    booking_successful = False # Initialize to False
    
    # The book_ride methods in UberAutomation and RapidoAutomation now return a boolean
    # indicating success or failure, and handle their own internal exceptions for unavailability.
    # Only truly unexpected system-level errors should propagate here.
    if platform == 'Uber':
        booking_successful = await uber_automation.book_ride(ride_to_book)
    elif platform == 'Rapido':
        booking_successful = await rapido_automation.book_ride(ride_to_book)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    if booking_successful:
        logger.info(f"Job {job_id}: Booking for '{selected_ride.get('name')}' on {platform} successful. Shutting down automations...")
        # Stop both automations, even if only one was used for booking, to ensure all browser contexts are closed.
        await asyncio.gather(uber_automation.stop(), rapido_automation.stop())
        del active_jobs[job_id]
        logger.info(f"Job {job_id} stopped and cleaned up successfully.")
        return BookingResponse(status="booking_initiated", message=f"Booking process for '{selected_ride.get('name')}' on {platform} has started.")
    else:
        # If booking was not successful (e.g., ride unavailable or button not found)
        # The automations are NOT stopped, allowing the user to select another ride.
        # The status and message from the automation object will contain details.
        automation_instance = uber_automation if platform == 'Uber' else rapido_automation
        error_message = f"Booking for '{selected_ride.get('name')}' on {platform} failed: {automation_instance.message}. Please select another ride."
        logger.warning(f"Job {job_id}: {error_message}")
        raise HTTPException(status_code=409, detail=error_message)