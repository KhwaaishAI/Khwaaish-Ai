import logging
from app.agents.amazon_automator.automator import AmazonAutomator
from typing import Optional,Dict

logger = logging.getLogger(__name__)

class AmazonAutomationFlow:
    """High-level workflow orchestrator."""
    
    def __init__(self, automator: AmazonAutomator):
        self.automator = automator
    
    async def run_full_flow(
        self,
        search_query: str,
        product_index: int = 1,
        specifications: Optional[Dict[str, str]] = None,
        ):
        """
        Execute full search -> select -> specs -> cart -> checkout flow.
        Args:
            search_query: What to search for
            product_index: 1-based index from results
            specifications: Dict like {'Color': 'Black', 'Storage': '256GB'}
        """
        try:
            await self.automator.initialize_browser()
            await self.automator.page.goto("https://www.amazon.in")
            
            # Search
            print("\n🔍 STEP 1: SEARCHING...")
            await self.automator.page.goto(f"https://www.amazon.in/s?k={search_query}")
            products = await self.automator.go_to_search(search_query)
            
            if not products:
                logger.error("No products found")
                return
            
            # Display and select
            print("\n📋 STEP 2: DISPLAYING RESULTS...")
            self.automator.display_products(products)
            
            if product_index == 0:
                product_index = int(input("Select product number: "))
            
            selected_product = self.automator.select_product(product_index)
            
            # Open product page
            print("\n🌐 STEP 3: OPENING PRODUCT PAGE...")
            await self.automator.open_product_page(selected_product['asin'])
            
            # Find and choose specs
            print("\n⚙️  STEP 4: SPECIFICATIONS...")
            available_specs = await self.automator.find_specifications()
            
            if available_specs:
                print(f"Available specifications: {list(available_specs.keys())}")
                
                if not specifications:
                    specifications = {}
                    for spec_name, options in available_specs.items():
                        print(f"\n{spec_name} options: {options}")
                        choice = input(f"Choose {spec_name} (or press Enter to skip): ").strip()
                        if choice:
                            specifications[spec_name] = choice
                
                if specifications:
                    await self.automator.choose_specifications(specifications)
            
            # Add to cart
            print("\n🛒 STEP 5: ADDING TO CART...")
            if await self.automator.add_to_cart():
                print("✅ Item added to cart")
            else:
                logger.error("Failed to add to cart")
                return
            
            # Proceed to checkout
            print("\n💳 STEP 6: PROCEEDING TO CHECKOUT...")
            if await self.automator.proceed_to_checkout():
                print("✅ Proceeding to checkout")
            else:
                logger.error("Failed to proceed to checkout")
                return
            
            # Reach payment page
            print("\n💰 STEP 7: REACHING PAYMENT PAGE...")
            if await self.automator.reach_payment_page():
                print("✅ Reached payment page")
            else:
                logger.error("Failed to reach payment page")
                return
            
            payment_done = input("\n📝 STEP 8: Once the payment is done, press ENTER to continue...")
        finally:
            if payment_done:
                await self.automator.close_browser()

if __name__ == "__main__":
    import asyncio
    # Directly run the automation flow with example parameters
    async def main():
        automator = AmazonAutomator()
        flow = AmazonAutomationFlow(automator)
        await flow.run_full_flow("Samsung S23 Ultra", 0)

    asyncio.run(main())
