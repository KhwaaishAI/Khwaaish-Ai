#!/usr/bin/env python3
import asyncio
import sys
import os
from typing import Dict, List, Any

# --- Set the correct working directory ---
# This ensures that all relative paths for configs, logs, and session files work correctly.
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.append(script_dir)

from automation.core import UberAutomation
from automation.steps import UberSteps

class SmartProductAutomation:
    def __init__(self, automation: UberAutomation):
        self.automation = automation
        self.steps = UberSteps(automation)
        self.logger = automation.logger

async def main():
    """The main entry point for the Uber automation script."""
    automation = UberAutomation()
    try:
        await automation.start()
        # Keep the browser open for a moment to observe the result if not in headless mode
        await asyncio.sleep(5)
    finally:
        await automation.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Automation interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")