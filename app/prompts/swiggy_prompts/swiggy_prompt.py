def create_swiggy_automation_prompt(item: str, restaurant: str, location: str, phone_number: str) -> str:
    """Create automation prompt with your exact HTML selectors"""
    
    prompt = f"""
You are a web automation agent for Swiggy food ordering. Follow each step carefully.

TASK PARAMETERS:
- Location: {location}
- Restaurant: {restaurant}
- Item to order: {item}
- Phone number: {phone_number}

STEP 1: NAVIGATE AND LOAD
- Navigate to https://www.swiggy.com
- Wait 2 seconds for page to fully render
- Take page snapshot

STEP 2: SET DELIVERY LOCATION
- Find input element:
  * type="text"
  * class="_5ZhdF _3GoNS _1LZf8"
  * name="location"
  * placeholder="Enter your delivery location"
- Click on this input field
- Type "{location}"
- Wait 1 seconds
- Look for suggestions in <div class="kuQWc"> elements
- Click the first suggestion
- Wait 2 seconds for page to reload with location set
- Take page snapshot

STEP 3: SEARCH FOR RESTAURANT
- Navigate to https://www.swiggy.com/search
- Wait 1 seconds
- Find input element:
  * type="text"
  * class="ssM7E"
  * placeholder="Search for restaurants and food"
- Click the search input
- Type "{restaurant}"
- Wait 1 seconds for suggestions to appear
- Look for suggestion items with:
  * tag: <button class="xN32R" data-testid="autosuggest-item">
  * Inside: <div class="_38J4H"> contains restaurant name
  * Inside: <div class="_2B_8A"> contains type (should say "Restaurant", not "Dish")
- Find the FIRST suggestion where:
  * Restaurant name matches or contains "{restaurant}"
  * Type is "Restaurant" (not "Dish")
- Click on this suggestion button
- Wait 1 seconds
- Now look for and click the restaurant card:
  * Find: <div data-testid="resturant-card-name" class="_1XaJt">
  * This div contains the restaurant name "{restaurant}"
  * Click on this div to open the restaurant page
- Wait 1 seconds for menu to load completely
- Take page snapshot


STEP 4: SEARCH AND ADD ITEM TO CART
- Find the search input with:
  * type="text"
  * class="_2cVkR"
  * placeholder="Search in La Pino'z Pizza"
  * data-cy="menu-search-header"
- Click on this search input
- Type "{item}"
- Wait 2 seconds for item suggestions to load
- Look for item suggestions in divs with:
  * aria-hidden="true"
  * class contains "sc-aXZVg eqSzsP sc-bmzYkS dnFQDN"
  * Text content contains "{item}" name
- Find the FIRST matching item suggestion with name "{item}"
- Click on this item suggestion div
- Wait 1 second
- Look for the ADD button with:
  * class contains "sc-ggpjZQ sc-cmaqmh jTEuJQ fcfoYo add-button-center-container"
  * Inside: <div class="sc-aXZVg biMKCZ">Add</div>
- Click the ADD button (item is now added to cart)
- Wait 1 second
- Take page snapshot

STEP 5: VIEW CART AND PROCEED TO CHECKOUT
- Look for the cart display with:
  * class="_1JiK6"
  * Contains text showing item count and price (e.g., "1 Item | ₹269")
  * Inside: <span class="ZVNHp"><span>View Cart</span>
- Click on the "View Cart" section to open cart
- Wait 3 seconds for cart page to load
- Take page snapshot

STEP 6: LOGIN - CLICK LOGIN BUTTON
- Look for login option with:
  * class="WO7LQ _2ThIK"
  * Inside: <div class="_2UOuf">LOG IN</div>
- Click on the "LOG IN" button/div
- Wait 2 seconds for login form to appear
- Take page snapshot

STEP 7: LOGIN - ENTER PHONE NUMBER
- Find phone input with:
  * class="_5ZhdF"
  * type="tel"
  * name="mobile"
  * id="mobile"
  * maxlength="10"
- Click on this input field
- Type "{phone_number}" (10 digits only, without country code)
- Wait 1 second
- "class="ApfF7"" find this and click on login button
- Take page snapshot


STEP 9: WAIT FOR OTP ENTRY (USER MANUAL)
- Wait for OTP input field with:
  * class="_5ZhdF"
  * type="text"
  * name="otp"
  * id="otp"
  * maxlength="6"
- Wait 20 seconds for user to manually enter OTP in this field
- Do NOT attempt to auto-fill OTP
- Take page snapshot after user enters OTP

STEP 10: VERIFY OTP
- Find  the class="ApfF7" and click the verify button with:
- Wait 5 seconds for login to complete
- Take page snapshot

STEP 10: SELECT ADDRESS
- Find and click first address or Home address
- Wait 2 seconds
- Take page snapshot

STEP 11: PROCEED TO PAYMENT
- Click Proceed/Continue button
- Wait 5 seconds
- Take page snapshot

STEP 12: FINAL
- Take screenshot of payment page
- Report completion
"""
    
    return prompt
