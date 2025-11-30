from app.agents.oyo.oyo_session_manager import session_manager

async def oyo_login(phone_number: str):
    """
    Automates login on OYO and returns session cookies.
    Browser instance is managed by session manager.
    """
    try:
        # Get playwright instance from session manager
        p = await session_manager.get_playwright()
        
        # Launch browser with persistent context
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding"
            ]
        )
        
        context = await browser.new_context()
        page = await context.new_page()

        # Set a longer timeout for the context
        context.set_default_timeout(30000)

        try:
            # Navigate to OYO Login page
            await page.goto("https://www.oyorooms.com/login?country=&retUrl=/", wait_until="networkidle")
            print("Navigated to login page")

            # Wait for phone input
            await page.wait_for_selector("div.textTelInput__container", timeout=10000)
            print("Phone input container found")

            # Fill phone number
            phone_input = page.locator("input.textTelInput__input")
            await phone_input.fill(phone_number)
            await page.wait_for_timeout(1000)
            print(f"Filled phone number: {phone_number}")

            # Click login button
            login_button = page.locator("button.loginCard__button")
            await login_button.click()
            print("Clicked login button")

            # Wait for OTP screen to appear
            try:
                await page.wait_for_selector(
                    "input[placeholder*='OTP'], input[placeholder*='otp'], input[type='tel'], input[data-testid*='otp']", 
                    timeout=15000
                )
                print("OTP screen loaded successfully")
                
                # Wait a bit more for any session cookies to be set
                await page.wait_for_timeout(2000)
                
            except Exception as e:
                print(f"OTP screen not loaded: {e}")
                # Take screenshot for debugging
                await page.screenshot(path="otp_screen_error.png")
                # Check if there's an error message
                error_elements = await page.query_selector_all(".error, .error-message, .loginCard__error")
                for error in error_elements:
                    error_text = await error.text_content()
                    print(f"Error message: {error_text}")
                raise

            # Get all cookies
            cookies = await context.cookies()
            print(f"Found {len(cookies)} cookies")
            
            # Log all cookie names for debugging
            cookie_names = [c["name"] for c in cookies]
            print(f"Cookie names: {cookie_names}")

            # Look for session cookies
            session_cookies = []
            possible_session_names = ["sid", "sessionid", "SESSION", "SESSION_ID", "session", "auth_token", "token", "user_token"]
            
            for cookie in cookies:
                if cookie["name"].lower() in [name.lower() for name in possible_session_names]:
                    session_cookies.append(cookie)
                    print(f"Found potential session cookie: {cookie['name']} = {cookie['value'][:50]}...")

            # Store the browser instance in session manager
            session_id = session_manager.create_session({
                "browser": browser,
                "context": context,
                "page": page,
                "playwright": p
            })

            return {
                "session_id": session_id,
                "cookies": cookies,
                "session_cookies": session_cookies,
                "status": "otp_sent",
                "message": "Browser is kept open for OTP verification"
            }

        except Exception as e:
            print(f"Error during login process: {e}")
            # Clean up on error
            await browser.close()
            raise

    except Exception as e:
        print(f"Error initializing browser: {e}")
        raise