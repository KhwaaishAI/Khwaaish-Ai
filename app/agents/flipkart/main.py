#!/usr/bin/env python3
import asyncio
import json
import os
import urllib.parse
from typing import Dict, Any

class FlipkartFlow:
    def __init__(self, automation, steps):
        self.automation = automation
        self.steps = steps
        self.logger = automation.logger

    async def execute(self, product: Dict[str, Any], shipping: Dict[str, Any]) -> bool:
        try:
            self.steps.current_product = product
            self.steps.shipping_info = shipping
            
            flow_steps = [
                (self.steps.step_0_generate_search_url, "Search URL"),
                (self.steps.step_1_launch_search_url, "Search & Select"),
                (self.steps.step_3_handle_product_options, "Product Options"),
                (self.steps.step_4_add_to_cart_without_login, "Add to Cart"),
                (self.steps.step_6_proceed_to_shipping, "Shipping Checkout"),
                (self.steps.step_7_fill_shipping_info, "Fill Shipping"),
                (self.steps.step_8_proceed_to_payment, "Payment"),
            ]
            
            for idx, (step_fn, name) in enumerate(flow_steps, 1):
                try:
                    self.logger.info(f"[{idx}/7] {name}...")
                    await step_fn()
                except Exception as e:
                    self.logger.error(f"[{idx}/7] {name} failed: {e}")
                    raise
            
            self.logger.info("✅ Flow completed")
            return True
        except Exception as e:
            self.logger.error(f"❌ Flow failed: {e}")
            return False


def load_shipping() -> Dict[str, str]:
    session_file = "user_shipping_session.json"
    if os.path.exists(session_file):
        try:
            with open(session_file) as f:
                saved = json.load(f)
            if input(f"\n📦 Use saved: {saved['city']}, {saved['state']}? [Y/n]: ").lower() != 'n':
                return saved
        except: pass
    
    shipping = {
        'name': input("Name: "),
        'mobile': input("Mobile: "),
        'address': input("Address: "),
        'city': input("City: "),
        'state': input("State: "),
        'pincode': input("Pincode: ")
    }
    
    with open(session_file, 'w') as f:
        json.dump(shipping, f)
    return shipping


async def main():
    from app.agents.flipkart.automation.core import FlipkartAutomation
    from app.agents.flipkart.automation.steps import FlipkartSteps
    
    automation = FlipkartAutomation()
    if not await automation.initialize_browser():
        print("❌ Browser init failed")
        return

    flow = FlipkartFlow(automation, FlipkartSteps(automation))
    
    product = {'name': input("Product: "), 'options': {}}
    shipping = load_shipping()
    
    success = await flow.execute(product, shipping)
    
    if success:
        print("\n✅ Ready for payment (Ctrl+C to exit)")
        try:
            while True:
                if hasattr(automation, 'browser') and automation.browser.is_closed():
                    break
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
    
    await automation.close()


if __name__ == "__main__":
    os.makedirs("debug_screenshots", exist_ok=True)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Interrupted")