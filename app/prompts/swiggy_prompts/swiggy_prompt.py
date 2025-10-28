def create_swiggy_prompt(item: str, restaurant: str, location: str, phone_number: str) -> str:
    """Creates the prompt for the Swiggy agent."""
    
    return f"""Order {item} from {restaurant} on Swiggy.

Steps:
1.at each steps you need to wait for page content to load properly
1. Navigate to https://www.swiggy.com
2. Set location: Click location field find for this "<input type="text" class="_5ZhdF _3GoNS _1LZf8" ", type "{location}", wait for suggestions generally each suggestions is there in this "<div class="kuQWc">" find the most valid suggestion and click it quick generally the first one is most valid
3. Now go to the url "https://www.swiggy.com/search" find this selector "<input type="text" class="ssM7E" placeholder="Search for restaurants and food" value="" autofocus="" maxlength="200">"
   Search "{restaurant}", click restaurant from results, select the most valid restaurant (first one)
4. Find "{item}", click ADD item to cart even if item is present in cart repeat and add it into cart
5. View cart and click checkout or proceed

LOGIN FLOW:
6. On the login page, find the phone number input field and enter "{phone_number}"
7. Click the button to send OTP (usually says "SEND OTP" or "GET OTP")
8. Wait 15 seconds for user to manually enter OTP
9. After OTP is entered, click login/verify button
10. Wait 5 seconds for login to complete

ADDRESS SELECTION:
11. Look for saved addresses or home address option
12. Select the first/home address from the list
13. Click proceed or continue to payment

PAYMENT:
14. Stop at payment page, take screenshot

Be direct. Execute each step sequentially. Wait appropriately between actions."""
