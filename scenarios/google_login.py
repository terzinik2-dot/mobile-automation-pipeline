"""
Google Login Scenario

Signs in to a Google account on the device.

Strategy (in priority order):
1. Check if account already configured on device (fastest — no UI needed)
2. Use Google's built-in Add Account flow via Android Settings
3. Handle 2FA prompts, "Choose an account" dialogs, and CAPTCHA fallbacks

The goal is a Google-authenticated device session so Play Store and
Google Pay work without re-authentication per scenario.
"""

from __future__ import annotations

import time

from loguru import logger

from executors.locator_engine import LocatorStrategy
from scenarios.base_scenario import BaseScenario


# Android package constants
SETTINGS_PACKAGE = "com.android.settings"
GMSCORE_PACKAGE = "com.google.android.gms"
PLAY_STORE_PACKAGE = "com.android.vending"


class GoogleLoginScenario(BaseScenario):
    """
    Scenario: Authenticate with a Google account on the device.

    Steps:
    1. check_existing_account    — fast path: verify account already present
    2. open_account_settings     — navigate to Settings > Accounts
    3. add_google_account        — initiate Add Account flow
    4. enter_email               — type email address
    5. enter_password            — type password
    6. handle_2fa                — handle 2FA / verification prompts
    7. accept_terms              — accept Google ToS if prompted
    8. verify_login              — confirm account is active
    """

    SCENARIO_NAME = "google_login"
    BUDGET_KEY = "google_login"

    def run_steps(self) -> None:
        # Step 1: Try fast path first
        already_logged_in = self._execute_step(
            "check_existing_account",
            self._check_existing_account,
            max_retries=1,
            screenshot_on_failure=False,
        )
        if already_logged_in.status.value == "completed" and already_logged_in.metadata.get("return_value") == "True":
            logger.info("[google_login] Account already configured — skipping login flow")
            return

        # Step 2: Navigate to account settings
        self._execute_step(
            "open_settings",
            self._open_settings,
            max_retries=2,
        )

        # Step 3: Navigate to Accounts
        self._execute_step(
            "navigate_to_accounts",
            self._navigate_to_accounts,
            max_retries=2,
        )

        # Step 4: Tap "Add Account"
        self._execute_step(
            "tap_add_account",
            self._tap_add_account,
            max_retries=2,
        )

        # Step 5: Select Google
        self._execute_step(
            "select_google",
            self._select_google_account_type,
            max_retries=2,
        )

        # Step 6: Enter email
        self._execute_step(
            "enter_email",
            self._enter_email,
            max_retries=3,
        )

        # Step 7: Enter password
        self._execute_step(
            "enter_password",
            self._enter_password,
            max_retries=3,
        )

        # Step 8: Handle 2FA (best effort — don't fail the whole scenario)
        self._execute_step(
            "handle_post_login_prompts",
            self._handle_post_login_prompts,
            max_retries=2,
            screenshot_on_failure=False,
        )

        # Step 9: Accept Terms of Service if shown
        self._execute_step(
            "accept_terms",
            self._accept_terms_if_shown,
            max_retries=2,
            screenshot_on_failure=False,
        )

        # Step 10: Verify login completed
        self._execute_step(
            "verify_login",
            self._verify_login,
            max_retries=3,
        )

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _check_existing_account(self) -> bool:
        """
        Fast-path: check if a Google account is already signed in on the device.

        Verifies by querying AccountManager via Appium shell command.
        """
        try:
            result = self.driver.execute_script(
                "mobile: shell",
                {"command": "content", "args": [
                    "query", "--uri",
                    "content://com.google.android.gms.auth.accounts/accounts"
                ]}
            )
            if result and isinstance(result, str):
                email = self.config.google_email
                if email and email.lower() in result.lower():
                    logger.info(f"[google_login] Account {email} already present")
                    return True
        except Exception as e:
            logger.debug(f"[google_login] AccountManager check failed: {e}")

        # Secondary check: Play Store is accessible with account
        self.driver.launch_app(PLAY_STORE_PACKAGE)
        time.sleep(2)

        signed_in_indicators = [
            LocatorStrategy.by_id("com.android.vending:id/profile_photo"),
            LocatorStrategy.by_content_desc("Account"),
            LocatorStrategy.by_text("Your apps"),
        ]
        result = self.locator.find_element(signed_in_indicators, timeout=5.0)
        if result is not None:
            logger.info("[google_login] Play Store accessible — account already configured")
            self.driver.press_home()
            return True

        self.driver.press_home()
        return False

    def _open_settings(self) -> None:
        """Open Android Settings."""
        self.driver.launch_app(SETTINGS_PACKAGE, ".Settings")
        time.sleep(1.5)
        # Verify settings opened
        settings_indicators = [
            LocatorStrategy.by_id("com.android.settings:id/search_bar"),
            LocatorStrategy.by_text("Settings"),
            LocatorStrategy.by_content_desc("Search settings"),
        ]
        elem = self.locator.find_element(settings_indicators, timeout=8.0)
        if elem is None:
            raise RuntimeError("Settings app did not open")

    def _navigate_to_accounts(self) -> None:
        """Navigate to Settings > Accounts & Backup > Manage accounts."""
        # Try scrolling to "Accounts" in settings list
        accounts_strategies = [
            LocatorStrategy.by_text("Accounts and backup"),
            LocatorStrategy.by_text("Accounts & Backup"),
            LocatorStrategy.by_text("Accounts"),
            LocatorStrategy.by_text("Users & accounts"),
            LocatorStrategy.by_content_desc("Accounts"),
        ]

        # Scroll to find
        found = False
        for _ in range(4):
            elem = self.locator.find_element(accounts_strategies, timeout=3.0)
            if elem:
                self.gestures.tap(elem)
                found = True
                break
            self.gestures.scroll_down(amount=0.4)
            time.sleep(0.5)

        if not found:
            raise RuntimeError("Could not find Accounts menu in Settings")

        time.sleep(1.0)

        # On some Samsung devices there's a sub-menu
        manage_accounts = [
            LocatorStrategy.by_text("Manage accounts"),
            LocatorStrategy.by_text("Add account"),
            LocatorStrategy.by_text("Google"),
        ]
        elem = self.locator.find_element(manage_accounts, timeout=5.0)
        if elem and "Manage" in (elem.element.text if elem.element else ""):
            self.gestures.tap(elem)
            time.sleep(1.0)

    def _tap_add_account(self) -> None:
        """Tap the 'Add Account' button."""
        strategies = [
            LocatorStrategy.by_text("Add account"),
            LocatorStrategy.by_text("+ Add account"),
            LocatorStrategy.by_content_desc("Add account"),
            LocatorStrategy.by_id("com.android.settings:id/add_account"),
        ]
        elem = self.locator.find_element(strategies, timeout=10.0)
        if elem is None:
            raise RuntimeError("'Add Account' button not found")
        self.gestures.tap(elem)
        time.sleep(1.0)

    def _select_google_account_type(self) -> None:
        """Select 'Google' from the list of account types."""
        strategies = [
            LocatorStrategy.by_text("Google"),
            LocatorStrategy.by_xpath('//android.widget.TextView[@text="Google"]'),
        ]
        self.gestures.scroll_to_text("Google", max_scrolls=3)
        elem = self.locator.find_element(strategies, timeout=8.0)
        if elem is None:
            raise RuntimeError("'Google' account type not found")
        self.gestures.tap(elem)
        time.sleep(2.0)
        # Handle security prompt (screen lock required)
        self._handle_security_prompt()

    def _enter_email(self) -> None:
        """Enter the Google email address."""
        email = self.config.google_email
        if not email:
            raise ValueError("google_email not configured")

        email_strategies = [
            LocatorStrategy.by_id("identifierId"),
            LocatorStrategy.by_accessibility("Email or phone"),
            LocatorStrategy.by_text("Email or phone"),
            LocatorStrategy.by_xpath('//android.widget.EditText'),
            LocatorStrategy.by_template("templates/google_email_field.png"),
        ]
        elem = self.locator.wait_for_element(email_strategies, timeout=15.0)
        if elem is None:
            raise RuntimeError("Email input field not found")

        self.gestures.tap(elem)
        time.sleep(0.5)
        self.gestures.type_text(elem, email)
        self.gestures.dismiss_keyboard()

        # Tap Next
        self._tap_next()
        time.sleep(1.5)

    def _enter_password(self) -> None:
        """Enter the Google account password."""
        password = self.config.google_password
        if not password:
            raise ValueError("google_password not configured")

        password_strategies = [
            LocatorStrategy.by_id("password"),
            LocatorStrategy.by_accessibility("Enter your password"),
            LocatorStrategy.by_xpath('//android.widget.EditText[@password="true"]'),
            LocatorStrategy.by_xpath('//android.widget.EditText[@inputType="129"]'),
        ]
        elem = self.locator.wait_for_element(password_strategies, timeout=15.0)
        if elem is None:
            raise RuntimeError("Password field not found")

        self.gestures.tap(elem)
        time.sleep(0.5)
        self.gestures.type_text(elem, password)
        self.gestures.dismiss_keyboard()

        # Tap Next
        self._tap_next()
        time.sleep(2.0)

    def _handle_post_login_prompts(self) -> None:
        """
        Handle various post-login prompts:
        - 2FA via phone notification
        - "Confirm your email recovery address"
        - "Enable backup"
        - "Welcome to your Pixel" setup wizard
        """
        time.sleep(2.0)

        # Check for 2FA prompt
        two_fa_strategies = [
            LocatorStrategy.by_text("2-Step Verification"),
            LocatorStrategy.by_text("Verify it's you"),
            LocatorStrategy.by_text("Check your phone"),
            LocatorStrategy.by_text("Google prompt"),
        ]
        two_fa = self.locator.find_element(two_fa_strategies, timeout=5.0)
        if two_fa:
            logger.warning("[google_login] 2FA prompt detected — attempting notification approval")
            self._handle_2fa()
            return

        # Handle "More" / "Not now" / "Skip" prompts
        skip_strategies = [
            LocatorStrategy.by_text("Not now"),
            LocatorStrategy.by_text("No thanks"),
            LocatorStrategy.by_text("Skip"),
            LocatorStrategy.by_text("More"),
        ]
        for _ in range(3):
            elem = self.locator.find_element(skip_strategies, timeout=3.0)
            if elem:
                self.gestures.tap(elem)
                time.sleep(1.0)
            else:
                break

    def _handle_2fa(self) -> None:
        """
        Handle 2FA: open notification shade to tap approval notification,
        or guide the user to approve on trusted device.
        """
        # Try: open notifications and look for Google sign-in notification
        self.driver.open_notifications()
        time.sleep(1.5)

        approve_strategies = [
            LocatorStrategy.by_text("Yes, it's me"),
            LocatorStrategy.by_text("It's me"),
            LocatorStrategy.by_text("YES"),
            LocatorStrategy.by_content_desc("Yes", partial=True),
        ]
        elem = self.locator.find_element(approve_strategies, timeout=5.0)
        if elem:
            self.gestures.tap(elem)
            logger.info("[google_login] 2FA approved via notification")
        else:
            # Close notifications
            self.driver.press_back()
            # Wait up to 30s for user to approve on another device
            logger.info("[google_login] Waiting for external 2FA approval...")
            self.wait_seconds(15.0, "2FA approval wait")

    def _accept_terms_if_shown(self) -> None:
        """Accept Google Terms of Service if displayed."""
        tos_strategies = [
            LocatorStrategy.by_text("I agree"),
            LocatorStrategy.by_text("Accept"),
            LocatorStrategy.by_text("Agree"),
        ]
        elem = self.locator.find_element(tos_strategies, timeout=5.0)
        if elem:
            self.gestures.tap(elem)
            time.sleep(1.0)
            logger.info("[google_login] Accepted Terms of Service")

    def _verify_login(self) -> None:
        """Verify the account is now active on the device."""
        time.sleep(2.0)

        # Navigate to Play Store to verify
        self.driver.launch_app(PLAY_STORE_PACKAGE)
        time.sleep(3.0)

        signed_in_indicators = [
            LocatorStrategy.by_id("com.android.vending:id/profile_photo"),
            LocatorStrategy.by_content_desc("Account"),
            LocatorStrategy.by_text("For you"),
            LocatorStrategy.by_text("Games"),
            LocatorStrategy.by_text("Apps"),
        ]
        elem = self.locator.wait_for_element(signed_in_indicators, timeout=15.0)
        if elem is None:
            # Check if we're on an "add account" prompt (sign-in failed)
            error_indicators = [
                LocatorStrategy.by_text("Sign in"),
                LocatorStrategy.by_text("Add a Google Account"),
            ]
            error = self.locator.find_element(error_indicators, timeout=3.0)
            if error:
                raise RuntimeError("Play Store shows sign-in prompt — login failed")
            raise RuntimeError("Could not verify Play Store is accessible after login")

        logger.info("[google_login] Google login verified — Play Store accessible")
        self.driver.press_home()

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _tap_next(self) -> None:
        """Tap the Next button in Google account flows."""
        next_strategies = [
            LocatorStrategy.by_id("identifierNext"),
            LocatorStrategy.by_id("passwordNext"),
            LocatorStrategy.by_text("Next"),
            LocatorStrategy.by_accessibility("Next"),
        ]
        elem = self.locator.find_element(next_strategies, timeout=5.0)
        if elem:
            self.gestures.tap(elem)
        else:
            # Fallback: press Enter
            self.driver.press_enter()

    def _handle_security_prompt(self) -> None:
        """Dismiss security/lock screen prompts during account setup."""
        security_strategies = [
            LocatorStrategy.by_text("Confirm your PIN"),
            LocatorStrategy.by_text("Confirm pattern"),
            LocatorStrategy.by_text("Enter PIN"),
            LocatorStrategy.by_text("OK"),
        ]
        elem = self.locator.find_element(security_strategies, timeout=3.0)
        if elem and "OK" in (elem.element.text if elem.element else ""):
            self.gestures.tap(elem)
