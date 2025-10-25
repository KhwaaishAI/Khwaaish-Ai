"""
Minimal dry-run test to validate environment without making changes.

Run with: python amazon_automator/test_dry_run.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from amazon_automator.automator import AmazonAutomator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_dry_run():
    """
    Minimal dry-run: Initialize browser, open page, close.
    
    This validates that:
    1. Playwright is installed
    2. Browser can launch
    3. Page can navigate
    4. No actual changes are made
    """
    
    print("\n" + "="*70)
    print("🧪 AMAZON AUTOMATOR DRY-RUN TEST")
    print("="*70)
    print("\nThis test validates your setup without making any changes.\n")
    
    automator = AmazonAutomator(
        headful=False,
        dry_run=True,
        throttle=0.5,
        timeout=15000,
    )
    
    try:
        print("1️⃣  Initializing browser...")
        await automator.initialize_browser()
        print("   ✅ Browser initialized\n")
        
        print("2️⃣  Opening Amazon homepage...")
        await automator.page.goto('https://www.amazon.in', wait_until='domcontentloaded')
        print("   ✅ Homepage loaded\n")
        
        print("3️⃣  Testing element detection...")
        search_box = await automator.find_element_safely(
            ['#twotabsearchtextbox', 'input[placeholder*="Search"]'],
            timeout=3000
        )
        if search_box:
            print("   ✅ Search box found\n")
        else:
            print("   ⚠️  Search box not found (may be okay)\n")
        
        print("4️⃣  Testing dry-run mode (no clicks)...")
        if search_box:
            await automator.safe_click(search_box, dry_run=True)
            print("   ✅ Dry-run click executed (no actual click)\n")
        
        print("5️⃣  Closing browser...")
        await automator.close_browser()
        print("   ✅ Browser closed\n")
        
        print("="*70)
        print("✅ DRY-RUN TEST PASSED")
        print("="*70)
        print("\nYour environment is set up correctly!")
        print("\nNext steps:")
        print("  1. Install AmazonScraper in your PYTHONPATH")
        print("  2. Run: python run_automator.py search --query 'test'")
        print("  3. Review the prompt warnings and confirm before proceeding")
        
        return True
    
    except Exception as e:
        print("\n" + "="*70)
        print("❌ DRY-RUN TEST FAILED")
        print("="*70)
        logger.error(f"Test error: {e}", exc_info=True)
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("  1. Ensure Playwright is installed: pip install playwright")
        print("  2. Install browsers: playwright install chromium")
        print("  3. Check internet connection")
        print("  4. Try with --headful: export AMAZON_AUTOMATOR_HEADFUL=true")
        
        return False
    
    finally:
        try:
            await automator.close_browser()
        except:
            pass


if __name__ == '__main__':
    success = asyncio.run(test_dry_run())
    sys.exit(0 if success else 1)