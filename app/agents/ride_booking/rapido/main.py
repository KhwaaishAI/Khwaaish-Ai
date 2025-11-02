import asyncio
import sys
import os

# Add project root to Python's path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from app.agents.ride_booking.rapido.core import RapidoAutomation
from app.agents.ride_booking.config import Config
from app.agents.ride_booking.utills.common import select_session

async def main():
    """The main entry point for the Rapido automation script."""
    config = Config()
    sessions_dir = config.SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)

    session_name = select_session(
        sessions_dir=sessions_dir,
        platform_name="Rapido",
        profile_prefix="rapido_profile_"
    )

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

            # --- Add ride selection logic ---
            try:
                choice_str = input("\nEnter the number of the ride you want to select (or press Enter to skip): ")
                if choice_str.strip():  # Check if user entered something
                    choice = int(choice_str) - 1
                    if 0 <= choice < len(ride_options):
                        selected_ride = ride_options[choice]
                        print(f"\nSelecting ride: {selected_ride['name']}...")
                        await automation.book_ride(selected_ride)
                    else:
                        print("Invalid selection. Exiting.")
            except (ValueError, IndexError):
                print("Invalid input. Exiting.")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred during automation: {e}")
    finally:
        await automation.stop()

if __name__ == "__main__":
    print("🚀 Starting Rapido Automation Test Script...")
    asyncio.run(main())
    print("✅ Script finished.")
