#!/usr/bin/env python3
import asyncio
import sys
import os
from typing import Dict, List, Any

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from automation.core import UberAutomation
from automation.steps import UberSteps

class SmartProductAutomation:
    def __init__(self, automation: UberAutomation):
        self.automation = automation
        self.steps = UberSteps(automation)
        self.logger = automation.logger

async def main():
    automation = UberAutomation()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Automation interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")