import asyncio
import sys
import os

# This is a crucial step to ensure that the script can find the other modules
# in your project when you run it directly. It adds the project's root directory
# to Python's path.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from app.agents.ride_booking.ola.core import OlaAutomation
from app.agents.ride_booking.config import Config
from app.agents.ride_booking.utills.common import select_session

async def main():
    """The main entry point for the Ola automation script."""
    config = Config()
    sessions_dir = config.SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)
    
    # Use the common utility to select a session
    session_name = select_session(
        sessions_dir=sessions_dir,
        platform_name="Ola",
        profile_prefix="ola_profile_"
    )

    pickup_location = input("Please enter your pickup location: ")
    destination_location = input("Please enter your destination location: ")

    automation = OlaAutomation(job_id="local-ola-test")
    try:
        # This will start the browser and the automation flow defined in core.py
        await automation.start(session_name, pickup_location, destination_location)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred during automation: {e}")
    finally:
        # The stop() method is already called inside start()'s finally block,
        # but calling it here ensures cleanup even if start() itself fails early.
        await automation.stop()

if __name__ == "__main__":
    print("🚀 Starting Ola Automation Test Script...")
    asyncio.run(main())
    print("✅ Script finished.")