import os

def select_session(sessions_dir: str, platform_name: str, profile_prefix: str) -> str:
    """
    Lists available sessions for a platform and prompts the user to select one or create a new one.

    Args:
        sessions_dir: The root directory where session profiles are stored.
        platform_name: The name of the platform (e.g., "Ola", "Uber").
        profile_prefix: The prefix used for the platform's session folders (e.g., "ola_profile_").

    Returns:
        The chosen or newly created session name.
    """
    sessions = []
    if os.path.exists(sessions_dir):
        for item in os.listdir(sessions_dir):
            if os.path.isdir(os.path.join(sessions_dir, item)) and item.startswith(profile_prefix):
                session_name = item[len(profile_prefix):]
                sessions.append(session_name)

    print(f"\n--- Available {platform_name} Sessions ---")
    if not sessions:
        print("No saved sessions found.")
    else:
        for i, name in enumerate(sessions):
            print(f"  {i + 1}: {name}")
    print(f"  {len(sessions) + 1}: Create a new session")
    print("-" * (len(platform_name) + 24))

    while True:
        try:
            choice = int(input(f"Select a {platform_name} session or create a new one: "))
            if 1 <= choice <= len(sessions):
                return sessions[choice - 1]
            elif choice == len(sessions) + 1:
                return input("Enter a name for the new session: ")
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")