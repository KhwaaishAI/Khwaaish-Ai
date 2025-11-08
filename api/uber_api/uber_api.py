import asyncio
import uuid
import os
import shutil
from fastapi import FastAPI, HTTPException, APIRouter
import uvicorn
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from app.agents.ride_booking.uber.core import UberAutomation
from app.agents.ride_booking.utills.logger import setup_logger
from app.agents.ride_booking.config import Config

# --- FastAPI App Setup ---
app = FastAPI(title="Uber Automation API")
logger = setup_logger("uber-api")

# In-memory storage for active automation sessions.
# In a production scenario, you might replace this with Redis or another persistent store.
active_sessions: Dict[str, UberAutomation] = {}

# --- Pydantic Models ---

class UberSessionRequest(BaseModel):
    """Defines the data to start a new Uber automation session."""
    session_name: str = "default_uber_session"
    start_from_login: bool = False

class UberSessionResponse(BaseModel):
    """The response containing the new session ID."""
    session_id: str
    message: str

class RideSearchRequest(BaseModel):
    """Defines the data needed to perform a ride search within a session."""
    pickup_location: str
    destination_location: str

class Ride(BaseModel):
    """A structured model for a single ride option."""
    platform: str = "Uber"
    session_id: str # Added to return the session_id with the ride
    name: str
    price: Optional[str] = None
    raw_details: Dict[str, Any]

class RideSearchResponse(BaseModel):
    """The response containing all found ride options for a session."""
    session_id: str
    rides: List[Ride]

class RideBookingRequest(BaseModel):
    """The request to book a specific ride, using its raw details."""
    session_id: str
    ride_details: Dict[str, Any]

class BookingResponse(BaseModel):
    """The response after a booking attempt."""
    status: str
    message: str

class LoginStartRequest(BaseModel):
    """Defines the data to start the login process."""
    # The only required field is the credential. The API will handle session creation.
    credential: str  # Can be an email or a phone number

class LoginStartResponse(BaseModel):
    """The response after starting the login process."""
    session_id: str
    status: str
    message: str

class LoginOtpRequest(BaseModel):
    """Defines the data for submitting the OTP."""
    session_id: str
    otp: str

# --- API Endpoints ---
@app.post("/login-start", response_model=LoginStartResponse)
async def login_start(request: LoginStartRequest):
    """
    Initializes a new session, navigates to the login page, enters the credential,
    and clicks continue. This prepares the session for OTP entry.
    """
    # Generate a unique session_id and a corresponding session_name for the browser profile.
    session_id = str(uuid.uuid4()) # A unique ID for this specific API job.
    session_name = "default_uber_session" # Use a fixed name to save the authenticated session.
    logger.info(f"Starting login process for job ID: {session_id} using profile name: {session_name}")

    automation = UberAutomation()

    # This is a fresh login, so we delete any old default session to start clean.
    config = Config()
    session_path = os.path.join(config.SESSIONS_DIR, f"uber_profile_{session_name}")
    if os.path.exists(session_path):
        shutil.rmtree(session_path)
        logger.info(f"Removed old default Uber session profile to ensure a fresh login: {session_path}")

    try:
        await automation.initialize(session_name)
        active_sessions[session_id] = automation
    except Exception as e:
        logger.error(f"Initialization failed for session {session_id}: {e}", exc_info=True)
        await automation.stop() # Ensure cleanup on failure
        raise HTTPException(status_code=500, detail=f"Browser initialization failed: {e}")
    steps = automation.steps

    try:
        logger.info(f"Session {session_id}: Starting login flow.")
        await steps.navigate_to_uber()
        await steps.click_login_link()
        login_input_selector = "input[placeholder='Enter phone number or email']"
        await automation.page.locator(login_input_selector).wait_for(state="visible", timeout=15000)
        await steps.enter_login_credential_api(request.credential)

        # After submitting the credential, intelligently determine the next step.
        # This handles cases where Uber asks for a password vs. going directly to OTP.
        await steps.handle_post_credential_step()

        logger.info(f"Session {session_id}: Credential entered. Ready for next login step (e.g., OTP).")
        return LoginStartResponse(session_id=session_id, status="credential_submitted", message="Login credential submitted. Please proceed with the next step (e.g., OTP verification).")
    except Exception as e:
        logger.error(f"Login start failed for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred during the login process: {e}")

@app.post("/login-otp", response_model=BookingResponse)
async def login_otp(request: LoginOtpRequest):
    """
    Submits the OTP for a given session, completes the login, and navigates to the ride booking page.
    """
    if request.session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please start a login first.")

    automation = active_sessions[request.session_id]
    steps = automation.steps

    try:
        logger.info(f"Session {request.session_id}: Submitting OTP.")
        await steps.enter_otp_code_api(request.otp)

        # After submitting the OTP, check if another OTP is needed or if login is complete.
        await asyncio.sleep(5)
        login_status = await steps.check_for_second_otp_or_login()

        if login_status == "SECOND_OTP_REQUIRED":
            logger.info(f"Session {request.session_id}: Second OTP (email) is required.")
            return BookingResponse(status="otp_email_required", message="First OTP submitted. Please provide the OTP sent to your email using this same endpoint.")
        elif login_status == "LOGIN_SUCCESS":
            # If login is successful, stop the automation. This saves the authenticated session to disk.
            logger.info(f"Session {request.session_id}: Login successful. Closing browser and saving session.")
            await automation.stop()
            # Remove the session from active memory as its job is done.
            active_sessions.pop(request.session_id, None)
            logger.info(f"Session {request.session_id} has been saved and cleaned up.")
            return BookingResponse(status="login_successful", message="Login successful and session saved. You can now use the /search endpoint.")
        else:
            raise HTTPException(status_code=500, detail="Could not determine login status after OTP submission.")
    except Exception as e:
        logger.error(f"OTP submission failed for session {request.session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred during OTP submission: {e}")

@app.post("/search", response_model=RideSearchResponse)
async def search_for_rides(request: RideSearchRequest):
    """
    Searches for rides using a default saved session. If no session is found,
    it prompts the user to log in first.
    """
    session_name = "default_uber_session"
    config = Config()
    session_path = os.path.join(config.SESSIONS_DIR, f"uber_profile_{session_name}")

    # Check if a saved session exists. If not, instruct the user to log in.
    if not os.path.exists(session_path):
        logger.warning("Search attempted but no default session found.")
        raise HTTPException(
            status_code=404,
            detail="No saved session found. Please log in first using the /login-start endpoint to create a session."
        )

    # If a session exists, create a new job to use it.
    session_id = str(uuid.uuid4())
    logger.info(f"Creating new search job with ID: {session_id} using saved session profile: {session_name}")

    automation = UberAutomation()
    try:
        await automation.initialize(session_name)
        active_sessions[session_id] = automation
    except Exception as e:
        logger.error(f"Initialization of saved session failed for job {session_id}: {e}", exc_info=True)
        await automation.stop()
        raise HTTPException(status_code=500, detail=f"Failed to load the saved browser session: {e}")

    uber_results = await automation.search_rides(request.pickup_location, request.destination_location)

    api_response_rides = []
    if isinstance(uber_results, list):
        logger.info(f"Session {session_id}: Found {len(uber_results)} rides on Uber.")
        for ride in uber_results:
            api_response_rides.append(Ride(session_id=session_id, name=ride['name'], price=ride.get('price'), raw_details=ride.copy()))
    else:
        logger.error(f"Session {session_id}: Failed to get Uber rides: {uber_results}")

    return RideSearchResponse(session_id=session_id, rides=api_response_rides)

@app.post("/book", response_model=BookingResponse)
async def book_a_ride(request: RideBookingRequest):
    """
    Books the selected ride for a given session and then stops the automation.
    """
    if request.session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found.")

    automation = active_sessions.pop(request.session_id) # Remove session from active list
    booking_successful = await automation.book_ride(request.ride_details)

    if booking_successful:
        logger.info(f"Session {request.session_id}: Booking successful. Stopping automation.")
        await automation.stop()
        logger.info(f"Session {request.session_id} stopped and cleaned up successfully.")
        return BookingResponse(status="booking_initiated", message=f"Booking process for '{request.ride_details.get('name')}' has started.")
    else:
        # If booking fails, put the session back in the active list so the user can try again.
        active_sessions[request.session_id] = automation
        error_message = f"Booking failed: {automation.message}. Please select another ride."
        raise HTTPException(status_code=409, detail=error_message)

if __name__ == "__main__":
    # Allows running this API independently for testing or as a microservice.
    uvicorn.run(app, host="127.0.0.1", port=8002)