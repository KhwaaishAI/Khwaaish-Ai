from playwright.sync_api import sync_playwright
import json
import time


def scrape_swiggy_restaurants_for_food(lat, lng, area_name, food_item):
    """
    Scrape Swiggy restaurants that sell a given food item.
    Navigates to search page, clicks Restaurant tab, scrolls, and extracts restaurant info.
    """

    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(headless=False)

        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            geolocation={'latitude': lat, 'longitude': lng},
            permissions=['geolocation']
        )

        page = context.new_page()

        try:
            print("Navigating to Swiggy homepage...")
            page.goto('https://www.swiggy.com/', timeout=60000)
            page.wait_for_timeout(2000)
            # Enter location
            print("Setting location...")
            location_input = None
            for selector in ['input[placeholder*="location"]', 'input[placeholder*="Enter"]', 'input[placeholder*="area"]', 'input[type="text"]']:
                try:
                    location_input = page.wait_for_selector(selector, timeout=4000)
                    if location_input:
                        break
                except:
                    continue

            if location_input:
                location_input.click()
                page.fill(selector, area_name)
                page.wait_for_timeout(20)
                try:
                    suggestion = page.wait_for_selector('div[class*="suggestion"], li[class*="suggestion"], button[class*="suggestion"]', timeout=3000)
                    suggestion.click()
                except:
                    page.keyboard.press('Enter')
                page.wait_for_timeout(400)

            # Go to search page for food
            print(f"\nSearching for: {food_item}")
            page.goto(f'https://www.swiggy.com/search?query={food_item}', timeout=60000)
            page.wait_for_timeout(3000)

            # Click the "Restaurant" tab using provided XPath
            restaurant_tab_xpath = '/html/body/div[1]/div/div[1]/div/div[2]/div/div/div[2]/div[1]/span[1]/span'
            try:
                tab = page.wait_for_selector(f'xpath={restaurant_tab_xpath}', timeout=10000)
                tab.click()
                print("✓ Clicked on Restaurant tab.")
                page.wait_for_timeout(200)
            except Exception as e:
                print(f"⚠ Could not click Restaurant tab: {e}")
                page.screenshot(path="restaurant_tab_error.png")

            # Scroll for dynamic loading
            print("Scrolling to load all restaurant cards...")
            for i in range(5):
                print(f"Scroll {i+1}/5")
                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                page.wait_for_timeout(300)

            print("Extracting restaurant cards...")

            restaurants = page.evaluate('''() => {
                const data = [];
                const cards = document.querySelectorAll('a[data-testid="resturant-card-anchor-container"]');

                cards.forEach(card => {
                    const name = card.querySelector('[data-testid="resturant-card-name"]')?.textContent?.trim() || 'N/A';
                    const rating = card.querySelector('[data-testid="restaurant-meta-rating"]')?.textContent?.trim() || 'N/A';
                    const time = card.querySelector('[data-testid="restaurant-card-time"]')?.textContent?.trim() || 'N/A';
                    const price = card.querySelector('[data-testid="restaurant-card-cost"]')?.textContent?.trim() || 'N/A';
                    const cuisines = card.querySelector('[data-testid="restaurant-card-cuisines"]')?.textContent?.trim() || 'N/A';
                    const offer = card.querySelector('._1MZsI')?.textContent?.trim() ||
                                  card.querySelector('._1HVP_')?.textContent?.trim() || 'N/A';
                    const href = card.getAttribute('href');
                    const url = href ? `https://www.swiggy.com${href}` : 'N/A';

                    data.push({
                        restaurant_name: name,
                        rating: rating,
                        estimate_arrival_time: time,
                        avg_price_for_two: price,
                        cuisine_served: cuisines,
                        offer_or_type: offer,
                        url: url
                    });
                });

                return data;
            }''')

            print(f"✓ Extracted {len(restaurants)} restaurants offering '{food_item}'.")

            # Save results
            if restaurants:
                file_name = f"swiggy_{food_item}_restaurants.json".replace(" ", "_")
                with open(file_name, "w", encoding="utf-8") as f:
                    json.dump(restaurants, f, indent=2, ensure_ascii=False)
                print(f"✓ Data saved to {file_name}")
            else:
                print("✗ No restaurant data found.")

            return restaurants

        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="swiggy_error.png")
            return []

        finally:
            print("\nClosing browser in 3 seconds...")
            time.sleep(3)
            browser.close()


# Example run
if __name__ == "__main__":
    LOCATIONS = {
        'andheri-west': {'lat': 19.1136, 'lng': 72.8697, 'name': 'Andheri West, Mumbai'},
    }

    loc = LOCATIONS['andheri-west']
    food_item = "Burger"

    print(f"\n{'='*60}")
    print(f"Scraping restaurants offering '{food_item}' in {loc['name']}")
    print(f"{'='*60}\n")

    data = scrape_swiggy_restaurants_for_food(loc['lat'], loc['lng'], loc['name'], food_item)
    print(f"\n✓ Found {len(data)} restaurants for '{food_item}'.")
