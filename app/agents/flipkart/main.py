#!/usr/bin/env python3
import asyncio
import sys
import os
from typing import Dict, List, Any

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from automation.core import FlipkartAutomation
from automation.steps import FlipkartSteps

class SmartProductAutomation:
    def __init__(self, automation: FlipkartAutomation):
        self.automation = automation
        self.steps = FlipkartSteps(automation)
        self.logger = automation.logger

    async def execute_direct_cart_flow(self, product_info: Dict[str, Any], shipping_info: Dict[str, Any]):
        """Direct flow: add to cart -> place order -> login -> shipping -> payment"""
        self.steps.current_product = product_info
        self.steps.shipping_info = shipping_info

        self.logger.info(f"🚀 Starting direct cart flow for: {product_info['name']}")

        # 1️⃣ Generate search URL
        await self.steps.step_0_generate_search_url()

        # 2️⃣ Launch search URL
        if await self.steps.step_1_launch_search_url():

            # 4️⃣ Handle options (size, color, storage)
            await self.steps.step_3_handle_product_options()

            # 5️⃣ Add to cart first (without login)
            await self.steps.step_4_add_to_cart_without_login()

            # 6️⃣ Click Place Order, then login if redirected
            await self.steps.step_6_proceed_to_shipping()
            # await self.steps.step_5_handle_login_at_checkout()  # Login happens only after Place Order

            # 7️⃣ Fill shipping information
            await self.steps.step_7_fill_shipping_info()

            # 8️⃣ Proceed to payment (stop for manual completion)
            await self.steps.step_8_proceed_to_payment()

            self.logger.info("✅ Direct cart workflow completed!")
        else:
            self.logger.info("Search for another item !!!!!")
            return 


# Product configs
PRODUCT_CONFIGS = {
    "samsung_s24_ultra": {
        "name": "Samsung Galaxy S24 Ultra",
        "category": "electronics",
        "specifications": {
            "brand": "Samsung",
            "model": "Galaxy S24 Ultra",
            "ram": "12GB",
            "storage": "256GB",
            "color": "Titanium Gray"
        },
        "quantity": 1
    },
    "iphone_15_pro": {
        "name": "Apple iPhone 15 Pro",
        "category": "electronics",
        "specifications": {
            "brand": "Apple",
            "model": "iPhone 15 Pro",
            "storage": "128GB",
            "color": "Natural Titanium"
        },
        "quantity": 1
    },
    "oneplus_12": {
        "name": "OnePlus 12",
        "category": "electronics",
        "specifications": {
            "brand": "OnePlus",
            "model": "12",
            "ram": "16GB",
            "storage": "256GB",
            "color": "Midnight Black"
        },
        "quantity": 1
    },
    "macbook_pro_16": {
        "name": "Apple MacBook Pro 16-inch",
        "category": "electronics",
        "specifications": {
            "brand": "Apple",
            "model": "MacBook Pro 16",
            "ram": "32GB",
            "storage": "1TB SSD",
            "color": "Space Gray"
        },
        "quantity": 1
    },
    "sony_wh1000xm5": {
        "name": "Sony WH-1000XM5 Headphones",
        "category": "electronics",
        "specifications": {
            "brand": "Sony",
            "type": "Over-Ear",
            "color": "Black",
            "features": "Noise Cancelling"
        },
        "quantity": 1
    },
    "atomic_habits": {
        "name": "Atomic Habits",
        "category": "books",
        "specifications": {
            "title": "Atomic Habits",
            "author": "James Clear",
            "type": "Self-help Book"
        },
        "quantity": 1
    },
    "nike_air_max": {
        "name": "Nike Air Max Shoes",
        "category": "fashion",
        "specifications": {
            "brand": "Nike",
            "type": "Running Shoes",
            "series": "Air Max"
        },
        "options": {
            "size": "10",
            "color": "Black"
        },
        "quantity": 1
    },
    "adidas_ultraboost": {
        "name": "Adidas Ultraboost 22",
        "category": "fashion",
        "specifications": {
            "brand": "Adidas",
            "type": "Running Shoes",
            "series": "Ultraboost"
        },
        "options": {
            "size": "9",
            "color": "White"
        },
        "quantity": 1
    },
    "fitbit_charge_6": {
        "name": "Fitbit Charge 6",
        "category": "electronics",
        "specifications": {
            "brand": "Fitbit",
            "type": "Smart Band",
            "color": "Graphite",
            "features": "Heart Rate, Sleep Tracking"
        },
        "quantity": 1
    },
    "kindle_paperwhite": {
        "name": "Amazon Kindle Paperwhite",
        "category": "electronics",
        "specifications": {
            "brand": "Amazon",
            "type": "E-Reader",
            "storage": "32GB",
            "color": "Black"
        },
        "quantity": 1
    },
    "hp_laserjet_pro": {
        "name": "HP LaserJet Pro M404dn Printer",
        "category": "electronics",
        "specifications": {
            "brand": "HP",
            "type": "Laser Printer",
            "features": "Duplex Printing, Ethernet"
        },
        "quantity": 1
    },
    "rayban_aviator": {
        "name": "Ray-Ban Aviator Sunglasses",
        "category": "fashion",
        "specifications": {
            "brand": "Ray-Ban",
            "type": "Sunglasses",
            "frame_color": "Gold",
            "lens_color": "Green"
        },
        "quantity": 1
    },
    "anker_usb_c_cable": {
        "name": "Anker USB C Fast Charging Cable",
        "category": "electronics",
        "specifications": {
            "type": "USB-C",
            "length": "1.5 meters",
            "charging": "Fast Charging"
        },
        "quantity": 1
    }
}


# Shipping info
DEFAULT_SHIPPING_INFO = {
    "name": "John Doe",
    "mobile": "9876543210",
    "pincode": "110001",
    "address": "123 Main Street, Connaught Place",
    "locality": "Connaught Place",
    "city": "New Delhi",
    "state": "Delhi",
    "landmark": "Near Metro Station",
    "address_type": "Home"
}

def auto_select_product():
    """Let user see and select a product from PRODUCT_CONFIGS."""
    print("\n" + "="*60)
    print("🛒 Available Products")
    print("="*60)
    keys = list(PRODUCT_CONFIGS.keys())
    for idx, key in enumerate(keys, 1):
        prod = PRODUCT_CONFIGS[key]
        print(f"{idx}. {prod['name']}  (Category: {prod.get('category', 'N/A')})")
        specs = prod.get("specifications", {})
        print("   Specs:", ", ".join(f"{k}: {v}" for k, v in specs.items()))
        print("-" * 40)
    # Selection loop
    while True:
        try:
            choice = input(f"Select product [1-{len(keys)}]: ").strip()
            if not choice: choice = "1"
            idx = int(choice)
            if 1 <= idx <= len(keys):
                selected_product = PRODUCT_CONFIGS[keys[idx-1]]
                print(f"👉 Selected: {selected_product['name']}\n")
                return selected_product
            else:
                print(f"Please enter a number between 1 and {len(keys)}.")
        except (ValueError, IndexError):
            print("Invalid input. Try again.")

import json

def get_quick_shipping_info():
    """Get essential shipping info and save to session (JSON)"""
    shipping_info = DEFAULT_SHIPPING_INFO.copy()
    name = input(f"Your Name [{shipping_info['name']}]: ").strip()
    if name: shipping_info['name'] = name
    mobile = input(f"Mobile Number [{shipping_info['mobile']}]: ").strip()
    if mobile: shipping_info['mobile'] = mobile
    pincode = input(f"Delivery Pincode [{shipping_info['pincode']}]: ").strip()
    if pincode: shipping_info['pincode'] = pincode

    # Save to session JSON file
    try:
        with open("user_shipping_session.json", "w") as f:
            json.dump(shipping_info, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save shipping info session: {str(e)}")

    return shipping_info

async def main():
    automation = FlipkartAutomation()
    try:
        automation.logger.info("🚀 Initializing Flipkart Automation...")
        if not await automation.initialize_browser():
            automation.logger.error("❌ Failed to initialize browser")
            return

        smart_automation = SmartProductAutomation(automation)

        # Select product and shipping info (reuse last shipping info if available, else prompt for new)
        selected_product = auto_select_product()

        import os
        SHIPPING_SESSION_FILE = "user_shipping_session.json"

        def load_saved_shipping_info():
            if os.path.exists(SHIPPING_SESSION_FILE):
                try:
                    with open(SHIPPING_SESSION_FILE, "r") as f:
                        return json.load(f)
                except Exception:
                    return None
            return None

        saved_shipping = load_saved_shipping_info()
        shipping_info = None
        if saved_shipping:
            print("\n📦 Previous shipping info found:")
            preview = f"{saved_shipping.get('name','')} - {saved_shipping.get('address','')}, {saved_shipping.get('city','')}, {saved_shipping.get('state','')} {saved_shipping.get('pincode','')}"
            print(preview)
            use_prev = input("Use previous shipping info? [Y/n]: ").strip().lower()
            if use_prev in ("y", "yes", ""):
                shipping_info = saved_shipping

        if not shipping_info:
            shipping_info = get_quick_shipping_info()

        automation.logger.info(f"🛍️ Selected product: {selected_product['name']}")
        automation.logger.info(f"🏠 Shipping: {shipping_info['city']}, {shipping_info['state']} - {shipping_info['pincode']}")

        # Start the direct cart workflow
        await smart_automation.execute_direct_cart_flow(selected_product, shipping_info)

        print("\n✅ AUTOMATION COMPLETED! Please complete payment manually.")
        print("⏳ Browser will remain open for manual completion (Ctrl+C to exit).")
        import sys
        import threading

        # Helper to wait for user input with timeout
        def get_input_timeout(prompt, timeout):
            user_input = [None]
            def timed_input():
                user_input[0] = input(prompt)
            thread = threading.Thread(target=timed_input)
            thread.daemon = True
            thread.start()
            thread.join(timeout)
            if thread.is_alive():
                return None
            return user_input[0]

        # Ask user what to do based on inactivity
        answer = get_input_timeout(
            "\n⏳ Do you want to keep the browser open? [C]lose now / [K]eep open: ",
            10
        )
        if answer is None:
            print("\n⌛ No user interaction for 10 seconds. Closing browser...")
        else:
            answer = answer.strip().lower()
            if answer and answer[0] == "k":
                print("\n🔄 Keeping browser open. Press Ctrl+C or close browser window to exit...")
                try:
                    while True:
                        # Check every second if the browser is closed externally, if possible
                        if hasattr(automation, "browser") and automation.browser:
                            try:
                                # For playwright's browser, check if it is closed
                                if automation.browser.is_closed():
                                    print("\n👋 Browser closed by user. Exiting...")
                                    break
                            except Exception:
                                # Fallback: exit if any error occurs (probably closed)
                                break
                        await asyncio.sleep(1)

                except KeyboardInterrupt:
                    print("\n👋 Closing browser...")
            else:
                print("\n👋 Closing browser...")

    except Exception as e:
        automation.logger.error(f"❌ Automation failed: {str(e)}")
        import traceback
        automation.logger.error(traceback.format_exc())
    finally:
        await automation.close()

if __name__ == "__main__":
    os.makedirs("debug_screenshots", exist_ok=True)
    print("\n🤖 FLIPKART AUTOMATION - DIRECT CART FLOW")
    print("Flow: add to cart -> Place Order -> Login -> Shipping -> Payment\n")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Automation interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
