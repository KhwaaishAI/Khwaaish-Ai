#!/usr/bin/env python3
import asyncio
import sys
import os

# --- Set the correct working directory ---
# This ensures that all relative paths for configs, logs, and session files work correctly.
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
project_root = os.path.abspath(os.path.join(script_dir, '..', '..', '..'))
sys.path.insert(0, project_root)

from app.agents.ride_booking.uber.core import UberAutomation
from app.agents.ride_booking.config import Config
from app.agents.ride_booking.utills.common import select_session

async def main():
    """The main entry point for the Uber automation script."""
    config = Config()
    sessions_dir = config.SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)
    
    # Use the common utility to select a session
    session_name = select_session(
        sessions_dir=sessions_dir,
        platform_name="Uber",
        profile_prefix="uber_profile_"
    )

    pickup_location = input("Please enter your pickup location: ")
    destination_location = input("Please enter your destination location: ")
    preferred_ride_choice = input("Enter preferred ride choice (e.g., 'UberGo', or leave blank): ")

    # Initialize the automation class.
    automation = UberAutomation()
    try:
        await automation.initialize(session_name)
        ride_options = await automation.search_rides(pickup_location, destination_location)

        if not ride_options:
            print("\n❌ No ride options found.")
            return

        # --- Terminal-based ride selection ---
        print("\n--- Available Uber Rides ---")
        for i, ride in enumerate(ride_options):
            seats_info = f"({ride['seats']} seats)" if ride.get('seats') else ""
            print(f"  {i + 1}: {ride['name']} {seats_info} - {ride['price']} - ETA: {ride['eta_and_time']}")
        print("--------------------------")

        try:
            choice = int(input("Select a ride to book (or 0 to cancel): ")) - 1
            if choice < 0:
                print("Booking cancelled.")
            else:
                selected_ride = ride_options[choice]
                await automation.book_ride(selected_ride)
        except (ValueError, IndexError):
            print("Invalid selection. Booking cancelled.")

    except Exception as e:
        print(f"\n❌ An unexpected error occurred during automation: {e}")
    finally:
        await automation.stop()