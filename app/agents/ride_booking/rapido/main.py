import asyncio
import sys
import os
import uuid

# Add project root to Python's path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, project_root)

from app.agents.ride_booking.rapido.core import RapidoAutomation
from app.agents.ride_booking.config import Config
from app.agents.ride_booking.utills.common import select_session

async def main():
    """The main entry point for the Rapido automation script."""
    config = Config()
    sessions_dir = config.SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)
    
    session_name = None
    start_fresh_input = input("Start with a fresh login? (yes/no) [default: no]: ").lower().strip()
    
    if start_fresh_input == 'yes':
        # Generate a random name for the new session.
        session_name = str(uuid.uuid4().hex[:8])
        print(f"Starting a fresh login. The new session will be saved as '{session_name}'.")
    else:
        # List existing sessions for the user to choose from.
        print("Using an existing session.")
        session_name = select_session(
            sessions_dir=sessions_dir,
            platform_name="Rapido",
            profile_prefix="rapido_profile_"
        )
        if not session_name:
            print("No session selected. Exiting.")
            return

    pickup_location = input("Please enter your pickup location: ")
    destination_location = input("Please enter your destination location: ")

    automation = RapidoAutomation()
    try:
        await automation.initialize(session_name)
        ride_options = await automation.search_rides(pickup_location, destination_location)

        if not ride_options:
            print("\n❌ No ride options found on Rapido.")
        else:
            print("\n--- Available Rapido Rides ---")
            for i, ride in enumerate(ride_options):
                print(f"  {i + 1}: {ride['name']} - {ride.get('price', 'N/A')} ({ride.get('eta', 'N/A')})")

            # --- Wait for user to select a ride ---
            try:
                choice_input = input("\nEnter the number of the ride you want to select (or press Enter to skip): ").strip()
                if choice_input:
                    choice = int(choice_input) - 1
                    if 0 <= choice < len(ride_options):
                        selected_ride = ride_options[choice]
                        print(f"\nSelecting '{selected_ride['name']}'...")
                        await automation.book_ride(selected_ride)
                        print("✅ Ride selected in the browser. The script will now finish.")
                        # Add a final pause so you can see the result in the browser
                        await asyncio.sleep(10)
                    else:
                        print("Invalid selection. Finishing script.")
                else:
                    print("No ride selected. Finishing script.")
            except (ValueError, IndexError):
                print("Invalid input. Please enter a number from the list. Finishing script.")

    except Exception as e:
        print(f"\n❌ An unexpected error occurred during automation: {e}")
    finally:
        await automation.stop()

if __name__ == "__main__":
    print("🚀 Starting Rapido Automation Test Script...")
    asyncio.run(main())
    print("✅ Script finished.")