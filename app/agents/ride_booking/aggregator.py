import asyncio
import sys
import os

# --- Setup Project Path ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from app.agents.ride_booking.ola.core import OlaAutomation
from app.agents.ride_booking.uber.core import UberAutomation
from app.agents.ride_booking.config import Config
from app.agents.ride_booking.utills.common import select_session

async def main():
    """
    An aggregator that runs Ola and Uber automations in parallel,
    combines the results, and allows the user to book a ride.
    """
    config = Config()
    sessions_dir = config.SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)

    print("--- Ride Aggregator ---")

    # --- 1. Select Sessions ---
    ola_session_name = select_session(sessions_dir, "Ola", "ola_profile_")
    uber_session_name = select_session(sessions_dir, "Uber", "uber_profile_")

    # --- 2. Get User Input ---
    pickup_location = input("\nPlease enter your pickup location: ")
    destination_location = input("Please enter your destination location: ")

    # --- 3. Initialize Automations ---
    ola_automation = OlaAutomation()
    uber_automation = UberAutomation()

    try:
        # --- 4. Initialize Browsers (Login if necessary) ---
        print("\n🚀 Initializing browsers and sessions...")
        await asyncio.gather(
            ola_automation.initialize(ola_session_name),
            uber_automation.initialize(uber_session_name)
        )

        # --- 5. Search for Rides in Parallel ---
        print("🔍 Searching for rides on Ola and Uber simultaneously...")
        ola_task = ola_automation.search_rides(pickup_location, destination_location)
        uber_task = uber_automation.search_rides(pickup_location, destination_location)
        # return_exceptions=True prevents one failure from stopping the other.
        ola_results, uber_results = await asyncio.gather(ola_task, uber_task, return_exceptions=True)

        # --- 6. Combine and Display Results ---
        all_rides = []
        if isinstance(ola_results, list):
            for ride in ola_results:
                ride['platform'] = 'Ola'
                all_rides.append(ride)
        else:
            print(f"❌ Failed to get Ola rides: {ola_results}")

        if isinstance(uber_results, list):
            for ride in uber_results:
                ride['platform'] = 'Uber'
                all_rides.append(ride)
        else:
            print(f"❌ Failed to get Uber rides: {uber_results}")

        if not all_rides:
            print("\nNo rides found on either platform. Exiting.")
            return

        # Sort by price, removing currency symbols and commas before converting to float.
        all_rides.sort(key=lambda r: float(r.get('price', 'inf').replace('₹', '').replace(',', '').strip()))

        print("\n--- Combined Ride Options (Sorted by Price) ---")
        for i, ride in enumerate(all_rides):
            print(f"  {i + 1}: [{ride['platform']}] {ride['name']} - {ride.get('price', 'N/A')}")
        print("-------------------------------------------------")

        # --- 7. User Selection and Booking ---
        try:
            choice_index = int(input("Select a ride to book (or 0 to cancel): ")) - 1
            if choice_index < 0:
                print("Booking cancelled.")
                return
            selected_ride = all_rides[choice_index]

            print(f"\nBooking '{selected_ride['name']}' on {selected_ride['platform']}...")
            if selected_ride['platform'] == 'Ola':
                await ola_automation.book_ride(selected_ride)
            elif selected_ride['platform'] == 'Uber':
                await uber_automation.book_ride(selected_ride)
        except (ValueError, IndexError):
            print("Invalid selection. Booking cancelled.")

    except Exception as e:
        print(f"\n❌ An unexpected error occurred in the aggregator: {e}")
    finally:
        print("\nShutting down automations...")
        await asyncio.gather(ola_automation.stop(), uber_automation.stop())

if __name__ == "__main__":
    asyncio.run(main())
    print("✅ Aggregator script finished.")