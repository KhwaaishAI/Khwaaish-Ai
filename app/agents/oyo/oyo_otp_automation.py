async def verify_otp_automation(session_data: dict, otp: str):
    """
    Handles the OTP verification automation process
    """
    page = session_data["page"]
    browser = session_data["browser"]
    context = session_data["context"]
    
    # Check if browser is still connected
    if not browser.is_connected():
        raise Exception("Browser connection lost")

    print("Browser session found and connected")

    # Enter OTP in 4 different cells
    await fill_otp_in_cells(page, otp)
    print(f"Filled OTP: {otp}")

    # Wait a moment before submitting
    await page.wait_for_timeout(1000)

    # Try to find and click verify/submit button
    submitted = await click_submit_button(page)
    if not submitted:
        print("No submit button found, trying Enter key")
        await page.keyboard.press("Enter")

    # Wait for verification and navigation
    await wait_for_verification(page)

    # Get updated cookies after OTP verification
    cookies = await context.cookies()
    
    # Look for session cookies again (they might be different after login)
    session_cookies = await find_session_cookies(cookies)

    # Find the actual session ID
    final_session_id = await extract_session_id(session_cookies)

    return {
        "session_id": final_session_id,
        "session_cookies": session_cookies
    }


async def fill_otp_in_cells(page, otp: str):
    """
    Fill OTP in 4 different input cells
    """
    if len(otp) != 4:
        raise Exception(f"OTP must be 4 digits, got {len(otp)} digits")

    # Try multiple selectors for OTP cells
    otp_cell_selectors = [
        "input.otpCard__input",
        "input[data-id]",
        "input[inputmode='numeric']",
        "input[type='tel']",
        ".otpCard__inputContainer input"
    ]
    
    otp_inputs = []
    
    for selector in otp_cell_selectors:
        elements = await page.query_selector_all(selector)
        if elements and len(elements) >= 4:
            otp_inputs = elements
            print(f"Found {len(elements)} OTP inputs with selector: {selector}")
            break
    
    # If no inputs found with specific selectors, try to find by container
    if not otp_inputs:
        containers = await page.query_selector_all(".otpCard__inputContainer")
        if containers and len(containers) >= 4:
            for container in containers:
                input_element = await container.query_selector("input")
                if input_element:
                    otp_inputs.append(input_element)
            print(f"Found {len(otp_inputs)} OTP inputs through containers")
    
    if len(otp_inputs) < 4:
        raise Exception(f"Expected 4 OTP input cells, found {len(otp_inputs)}")

    # Fill each OTP digit in respective cell
    for i, digit in enumerate(otp):
        if i < len(otp_inputs):
            await otp_inputs[i].fill(digit)
            print(f"Filled digit {digit} in cell {i+1}")
            await page.wait_for_timeout(200)  # Small delay between inputs
    
    print("Successfully filled all OTP cells")


async def click_submit_button(page):
    """
    Find and click submit/verify button
    """
    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Verify')",
        "button:has-text('Submit')",
        "button.otpCard__button",
        "button.loginCard__button"
    ]
    
    for selector in submit_selectors:
        buttons = await page.query_selector_all(selector)
        for button in buttons:
            if await button.is_visible():
                await button.click()
                print(f"Clicked submit button: {selector}")
                return True
    return False


async def wait_for_verification(page):
    """
    Wait for successful verification or handle errors
    """
    try:
        # Wait for either success or error with multiple possible outcomes
        await page.wait_for_function(
            """
            () => {
                return window.location.href.includes('/profile') || 
                       window.location.href.includes('/account') ||
                       window.location.href.includes('/dashboard') ||
                       document.body.innerText.includes('Welcome') ||
                       document.body.innerText.includes('Profile') ||
                       document.body.innerText.includes('Logged in');
            }
            """,
            timeout=15000
        )
        print("Login successful - detected successful navigation")
        
    except Exception as nav_error:
        print(f"Navigation detection timeout: {nav_error}")
        # Check if we're still on OTP page or if there's an error
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # Check for error messages
        error_found = await check_for_errors(page)
        if error_found:
            raise Exception(f"OTP verification error: {error_found}")
        
        # If no error found but navigation didn't happen, wait a bit more
        await page.wait_for_timeout(2000)
        print("No errors detected, proceeding with verification")


async def check_for_errors(page):
    """
    Check for any error messages on the page
    """
    error_selectors = [
        ".error",
        ".error-message", 
        ".loginCard__error",
        "[data-testid*='error']",
        ".Toastify__toast--error",
        ".otpCard__error"
    ]
    
    for selector in error_selectors:
        error_elements = await page.query_selector_all(selector)
        for error_element in error_elements:
            if await error_element.is_visible():
                error_text = await error_element.text_content()
                if error_text and len(error_text.strip()) > 0:
                    return error_text.strip()
    return None


async def find_session_cookies(cookies):
    """
    Extract session cookies from all cookies
    """
    session_cookies = []
    possible_session_names = [
        "sid", "sessionid", "SESSION", "SESSION_ID", 
        "session", "auth_token", "token", "user_token"
    ]
    
    for cookie in cookies:
        if cookie["name"].lower() in [name.lower() for name in possible_session_names]:
            session_cookies.append(cookie)
            print(f"Found session cookie: {cookie['name']} = {cookie['value'][:50]}...")
    
    return session_cookies


async def extract_session_id(session_cookies):
    """
    Extract the most likely session ID from session cookies
    """
    preferred_names = ["sessionid", "SESSION", "sid", "auth_token"]
    
    for name in preferred_names:
        for cookie in session_cookies:
            if cookie["name"].lower() == name.lower():
                return cookie["value"]
    return None