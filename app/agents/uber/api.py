import asyncio
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.agents.uber.core import UberAutomation

# --- API Data Models ---

class RideRequest(BaseModel):
    pickup_location: str
    destination_location: str
    preferred_ride_type: str
    session_name: Optional[str] = None

class JobResponse(BaseModel):
    job_id: str
    message: str

class StatusResponse(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

class RideSelection(BaseModel):
    ride_index: int

class LoginCredentials(BaseModel):
    login_type: str # 'P' for Phone, 'E' for Email
    credential: str

class OtpCode(BaseModel):
    otp: str
    session_name_to_save: Optional[str] = None # Optional: name to save the new session as


# --- FastAPI Application ---

app = FastAPI(
    title="Uber Automation API",
    description="An API to automate booking Uber rides.",
    version="1.0.0"
)

# In-memory storage for automation jobs. For production, use Redis or a database.
jobs: Dict[str, UberAutomation] = {}


@app.post("/book-ride", response_model=JobResponse, summary="Start a new Uber booking job")
async def create_booking_job(request: RideRequest, background_tasks: BackgroundTasks):
    """
    Initiates an Uber booking automation task.

    This endpoint starts the process in the background. Use the returned `job_id`
    to check the status and provide further input.
    """
    job_id = str(uuid.uuid4())
    automation = UberAutomation(job_id=job_id)
    jobs[job_id] = automation

    # Run the main automation task in the background
    background_tasks.add_task(
        automation.start,
        session_name=request.session_name,
        pickup_location=request.pickup_location,
        destination_location=request.destination_location,
        preferred_ride_choice=request.preferred_ride_type
    )

    return {"job_id": job_id, "message": "Uber booking job started."}


@app.get("/status/{job_id}", response_model=StatusResponse, summary="Get the status of a booking job")
async def get_job_status(job_id: str):
    """
    Poll this endpoint to get the current status of the automation job.

    - **status**: `running`, `waiting_for_ride_choice`, `completed`, `error`
    - **data**: Contains ride options when status is `waiting_for_ride_choice`.
    """
    automation = jobs.get(job_id)
    if not automation:
        raise HTTPException(status_code=404, detail="Job not found.")

    return {
        "job_id": job_id,
        "status": automation.status,
        "message": automation.message,
        "data": {"ride_options": automation.ride_data} if automation.ride_data else None
    }


@app.post("/provide-credentials/{job_id}", response_model=JobResponse, summary="Provide login credentials for a job")
async def provide_credentials(job_id: str, credentials: LoginCredentials):
    """
    If a job's status is `waiting_for_credentials`, use this endpoint to provide
    the phone number or email to log in.
    """
    automation = jobs.get(job_id)
    if not automation:
        raise HTTPException(status_code=404, detail="Job not found.")

    if automation.status != "waiting_for_credentials":
        raise HTTPException(status_code=400, detail=f"Job is not waiting for credentials. Current status: {automation.status}")

    if credentials.login_type.upper() not in ['P', 'E']:
        raise HTTPException(status_code=400, detail="Invalid login_type. Must be 'P' for phone or 'E' for email.")

    if not automation.login_credential_event:
         raise HTTPException(status_code=500, detail="Internal error: Job is not ready for credential input.")

    automation.login_credential = {"type": credentials.login_type.upper(), "value": credentials.credential}
    automation.login_credential_event.set() # Resume the background task

    return {"job_id": job_id, "message": "Credentials received. Resuming login."}


@app.post("/provide-otp/{job_id}", response_model=JobResponse, summary="Provide OTP for a job")
async def provide_otp(job_id: str, otp_data: OtpCode):
    """
    If a job's status is `waiting_for_otp`, use this endpoint to provide the 4-digit
    code and optionally a name to save the new session.
    """
    automation = jobs.get(job_id)
    if not automation:
        raise HTTPException(status_code=404, detail="Job not found.")

    if automation.status != "waiting_for_otp":
        raise HTTPException(status_code=400, detail=f"Job is not waiting for OTP. Current status: {automation.status}")

    if not (otp_data.otp.isdigit() and len(otp_data.otp) == 4):
        raise HTTPException(status_code=400, detail="Invalid OTP format. Must be a 4-digit number.")

    if not automation.otp_event:
         raise HTTPException(status_code=500, detail="Internal error: Job is not ready for OTP input.")

    automation.otp_code = otp_data.otp
    automation.session_name_to_save = otp_data.session_name_to_save
    automation.otp_event.set() # Resume the background task

    return {"job_id": job_id, "message": "OTP received. Resuming login."}


@app.post("/select-ride/{job_id}", response_model=JobResponse, summary="Select a ride for a waiting job")
async def select_ride(job_id: str, selection: RideSelection):
    """
    If a job's status is `waiting_for_ride_choice`, use this endpoint
    to provide the index of the desired ride from the status data.
    """
    automation = jobs.get(job_id)
    if not automation:
        raise HTTPException(status_code=404, detail="Job not found.")

    if automation.status != "waiting_for_ride_choice":
        raise HTTPException(status_code=400, detail=f"Job is not waiting for ride selection. Current status: {automation.status}")

    # The selection is handled by setting an event that the background task is waiting for.
    if not automation.user_choice_event or not automation.ride_data:
         raise HTTPException(status_code=500, detail="Internal error: Job is not ready for input.")

    if not (0 <= selection.ride_index < len(automation.ride_data)):
        raise HTTPException(status_code=400, detail="Invalid ride index provided.")

    automation.user_choice = selection.ride_index
    automation.user_choice_event.set() # Resume the background task

    return {"job_id": job_id, "message": f"Ride selection {selection.ride_index} received. Resuming job."}


# To run this API:
# 1. Install FastAPI and Uvicorn: pip install fastapi "uvicorn[standard]"
# 2. Run the server: uvicorn api:app --reload
# 3. Access the interactive documentation at http://127.0.0.1:8000/docs