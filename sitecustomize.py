import sys
import asyncio

# Ensure Playwright can spawn subprocesses on Windows by using the Proactor loop
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass
