"""Command-line interface for Amazon Automator."""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from amazon_automator.automator import AmazonAutomator, AmazonAutomationFlow
from amazon_automator.config import Config


def setup_logging(log_level: str):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('amazon_automator.log'),
        ]
    )


async def cmd_search_and_select(args):
    """Search and interactively select product."""
    
    # Import here to avoid circular dependency
    try:
        from amazon_automator.Amazon_tools.search import AmazonScraper
    except ImportError:
        print("❌ Error: AmazonScraper not found. Ensure it's in PYTHONPATH")
        return
    
    automator = AmazonAutomator(
        scraper=AmazonScraper(max_pages=args.max_pages),
        headful=args.headful,
        session_store_path=args.session_path,
        proxy=args.proxy,
        throttle=args.throttle,
        dry_run=args.dry_run,
    )
    
    flow = AmazonAutomationFlow(automator)
    
    specifications = {}
    if args.color:
        specifications['Color'] = args.color
    if args.storage:
        specifications['Storage'] = args.storage
    if args.size:
        specifications['Size'] = args.size
    
    await flow.run_full_flow(
        search_query=args.query,
        product_index=args.product_index,
        specifications=specifications if specifications else None,
    )


async def cmd_dry_run(args):
    """Dry run: search and open product without making changes."""
    
    try:
        from amazon_automator.Amazon_tools.search import AmazonScraper
    except ImportError:
        print("❌ Error: AmazonScraper not found")
        return
    
    print("\n" + "="*70)
    print("DRY RUN MODE - No cart/payment changes will be made")
    print("="*70)
    
    automator = AmazonAutomator(
        scraper=AmazonScraper(max_pages=1),
        headful=args.headful,
        dry_run=True,
        throttle=args.throttle,
    )
    
    try:
        await automator.initialize_browser()
        
        # Search
        products = await automator.go_to_search(args.query)
        
        if not products:
            print("No products found")
            return
        
        automator.display_products(products)
        
        # Select first or specified
        product_index = args.product_index or 1
        selected = automator.select_product(product_index)
        
        # Open product
        print("\n🌐 Opening product page (no cart/payment will be modified)...")
        await automator.open_product_page(selected['url'])
        
        print("✅ Dry run complete. Product page opened successfully.")
        
        input("\nPress ENTER to close browser and exit...")
    
    finally:
        await automator.close_browser()


async def cmd_test_session(args):
    """Test if saved session is valid."""
    
    automator = AmazonAutomator(
        session_store_path=args.session_path,
        headful=args.headful,
    )
    
    try:
        await automator.initialize_browser()
        
        # Try to access account page
        await automator.page.goto('https://www.amazon.in/ap/signin', wait_until='networkidle')
        
        # Check if already logged in
        try:
            await automator.page.wait_for_selector('[data-feature-name="account"]', timeout=2000)
            print("✅ Session is valid - you appear to be logged in")
        except:
            print("⚠️  Session may be expired or invalid")
            input("Press ENTER to close browser...")
    
    finally:
        await automator.close_browser()


def main():
    """Main CLI entry point."""
    
    setup_logging(Config.LOG_LEVEL)
    
    parser = argparse.ArgumentParser(
        description='Amazon Checkout Automation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
⚠️  LEGAL WARNING ⚠️
===================
This tool is for automating YOUR OWN Amazon account only.
Unauthorized use may violate Amazon's ToS and result in:
  - Account suspension
  - Legal action
  - Fraud charges

Use responsibly at your own risk.

EXAMPLES:
  # Interactive search and checkout
  python cli.py search --query "wireless mouse"
  
  # With specifications
  python cli.py search --query "laptop" --color "Black" --storage "256GB"
  
  # Dry run (no cart changes)
  python cli.py dry-run --query "keyboard"
  
  # Test saved session
  python cli.py test-session
        """
    )
    
    # Global arguments
    parser.add_argument('--headful', action='store_true', help='Show browser window')
    parser.add_argument('--proxy', default=Config.PROXY, help='Proxy URL')
    parser.add_argument('--throttle', type=float, default=Config.THROTTLE, help='Delay between actions (seconds)')
    parser.add_argument('--session-path', default=Config.SESSION_STORE_PATH, help='Session storage path')
    parser.add_argument('--log-level', default=Config.LOG_LEVEL, help='Logging level')
    
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search and checkout')
    search_parser.add_argument('--query', required=True, help='Search query')
    search_parser.add_argument('--product-index', type=int, default=0, help='1-based product index (0 = interactive)')
    search_parser.add_argument('--color', help='Preferred color')
    search_parser.add_argument('--storage', help='Preferred storage')
    search_parser.add_argument('--size', help='Preferred size')
    search_parser.add_argument('--max-pages', type=int, default=1, help='Max search pages')
    search_parser.add_argument('--dry-run', action='store_true', help='Simulate without changes')
    search_parser.set_defaults(func=cmd_search_and_select)
    
    # Dry run command
    dryrun_parser = subparsers.add_parser('dry-run', help='Dry run (no changes)')
    dryrun_parser.add_argument('--query', required=True, help='Search query')
    dryrun_parser.add_argument('--product-index', type=int, default=1, help='Product index')
    dryrun_parser.set_defaults(func=cmd_dry_run)
    
    # Test session command
    test_parser = subparsers.add_parser('test-session', help='Test saved session')
    test_parser.set_defaults(func=cmd_test_session)
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

