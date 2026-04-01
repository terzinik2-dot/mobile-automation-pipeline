"""
MLBB Registration Scenario

Launches Mobile Legends: Bang Bang and completes initial registration.

Strategy:
- Launch MLBB
- Wait through loading/splash screens
- Select registration method (Google account preferred, Guest fallback)
- Handle permission dialogs
- Complete any tutorial/onboarding
- Verify we're in the main game lobby

MLBB screens to handle:
1. Splash/loading screens (30-60s on first run)
2. Service agreement dialog
3. Age verification
4. "Quick Start" vs "Google Account" choice
5. Permission dialogs (storage, phone, microphone)
6. Character creation / tutorial intro
"""

from __future__ import annotations

import time

from loguru import logger

from executors.locator_engine import LocatorStrategy
from scenarios.base_scenario import BaseScenario

MLBB_PACKAGE = "com.mobile.legends"


class MLBBRegistrationScenario(BaseScenario):
    """Scenario: Launch MLBB and complete initial game registration."""

    SCENARIO_NAME = "mlbb_registration"
    BUDGET_KEY = "mlbb_registration"

    def run_steps(self) -> None:
        self._execute_step("launch_mlbb", self._launch_mlbb, max_retries=2)
        self._execute_step("wait_through_loading", self._wait_through_loading, max_retries=1)
        self._execute_step("accept_service_agreement", self._accept_service_agreement, max_retries=2, screenshot_on_failure=False)
        self._execute_step("handle_age_verification", self._handle_age_verification, max_retries=2, screenshot_on_failure=False)
        self._execute_step("select_registration_method", self._select_registration_method, max_retries=3)
        self._execute_step("handle_permissions", self._handle_permissions, max_retries=2, screenshot_on_failure=False)
        self._execute_step("complete_initial_download", self._complete_initial_download, max_retries=1)
        self._execute_step("handle_onboarding", self._handle_onboarding, max_retries=2, screenshot_on_failure=False)
        self._execute_step("verify_in_lobby", self._verify_in_lobby, max_retries=3)

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _launch_mlbb(self) -> None:
        """Launch MLBB app."""
        self.driver.launch_app(MLBB_PACKAGE)
        time.sleep(3.0)

        # Verify MLBB is the foreground app
        current = self.driver.get_current_package()
        if MLBB_PACKAGE not in current:
            # Try alternate launch method
            self.driver.execute_script("mobile: shell", {
                "command": "monkey",
                "args": ["-p", MLBB_PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"]
            })
            time.sleep(3.0)
            current = self.driver.get_current_package()
            if MLBB_PACKAGE not in current:
                raise RuntimeError(f"MLBB ({MLBB_PACKAGE}) did not launch")

        logger.info(f"[mlbb_reg] MLBB launched — current package: {current}")

    def _wait_through_loading(self) -> None:
        """
        Wait for MLBB to finish its initial loading sequence.

        MLBB has multiple loading phases:
        - Logo splash (2-3s)
        - Engine initialization (5-10s)
        - Asset loading (10-30s)
        - Network check (3-5s)
        """
        max_wait = min(60.0, self.budget.step_remaining(self.BUDGET_KEY) - 5)
        logger.info(f"[mlbb_reg] Waiting up to {max_wait:.0f}s for MLBB to load...")

        # These indicate loading is complete
        post_load_indicators = [
            # Service agreement screen
            LocatorStrategy.by_text("User Agreement"),
            LocatorStrategy.by_text("Service Agreement"),
            LocatorStrategy.by_text("Terms of Service"),
            # Login screen
            LocatorStrategy.by_text("Quick Start"),
            LocatorStrategy.by_text("Log In"),
            LocatorStrategy.by_text("Sign Up"),
            # Age verification
            LocatorStrategy.by_text("Age Verification"),
            # Already logged in — lobby
            LocatorStrategy.by_template("templates/mlbb_lobby.png"),
            LocatorStrategy.by_template("templates/mlbb_battle_button.png"),
        ]

        # Active loading indicators
        loading_indicators = [
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/loading_bar"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/progress_bar"),
            LocatorStrategy.by_template("templates/mlbb_loading_bar.png"),
        ]

        baseline = self.driver.screenshot_as_numpy()
        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            # Check if loading is done
            ready = self.locator.find_element(post_load_indicators, timeout=2.0)
            if ready:
                logger.info("[mlbb_reg] MLBB loading complete")
                return

            # Check for crashes or error dialogs
            self._handle_crash_or_error()

            # Wait and check for screen change
            time.sleep(3.0)
            new_screenshot = self.driver.screenshot_as_numpy()
            if self.cv.screens_are_different(baseline, new_screenshot, threshold=0.90):
                baseline = new_screenshot
                logger.debug("[mlbb_reg] Screen changed — loading in progress")

        raise RuntimeError(f"MLBB did not finish loading within {max_wait:.0f}s")

    def _accept_service_agreement(self) -> None:
        """Accept MLBB's user/service agreement."""
        agreement_indicators = [
            LocatorStrategy.by_text("User Agreement"),
            LocatorStrategy.by_text("Service Agreement"),
            LocatorStrategy.by_text("Terms of Service"),
            LocatorStrategy.by_text("Privacy Policy"),
        ]
        agreement = self.locator.find_element(agreement_indicators, timeout=5.0)
        if not agreement:
            logger.debug("[mlbb_reg] No service agreement dialog — skipping")
            return

        # Check/tap the agreement checkbox if present
        checkbox_strategies = [
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/agree_checkbox"),
            LocatorStrategy.by_xpath('//android.widget.CheckBox'),
            LocatorStrategy.by_template("templates/mlbb_agree_checkbox.png"),
        ]
        checkbox = self.locator.find_element(checkbox_strategies, timeout=3.0)
        if checkbox:
            # Only check if not already checked
            if checkbox.element and checkbox.element.get_attribute("checked") == "false":
                self.gestures.tap(checkbox)
                time.sleep(0.3)

        # Tap the agree/confirm button
        confirm_strategies = [
            LocatorStrategy.by_text("Agree"),
            LocatorStrategy.by_text("I Agree"),
            LocatorStrategy.by_text("AGREE"),
            LocatorStrategy.by_text("Accept"),
            LocatorStrategy.by_text("OK"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/btn_agree"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/btn_confirm"),
        ]
        confirm = self.locator.find_element(confirm_strategies, timeout=5.0)
        if confirm:
            self.gestures.tap(confirm)
            logger.info("[mlbb_reg] Service agreement accepted")
            time.sleep(1.5)

    def _handle_age_verification(self) -> None:
        """Handle MLBB's age verification dialog (if present)."""
        age_indicators = [
            LocatorStrategy.by_text("Age Verification"),
            LocatorStrategy.by_text("Verify Your Age"),
            LocatorStrategy.by_text("Enter your birthday"),
        ]
        dialog = self.locator.find_element(age_indicators, timeout=5.0)
        if not dialog:
            return

        logger.info("[mlbb_reg] Age verification dialog detected")

        # Try to enter a birthdate (18+ years ago)
        year_strategies = [
            LocatorStrategy.by_xpath('//android.widget.NumberPicker[@content-desc="Year"]'),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/year_picker"),
        ]
        year_elem = self.locator.find_element(year_strategies, timeout=3.0)
        if year_elem:
            self.gestures.type_text(year_elem, "1990")

        # Confirm
        confirm_strategies = [
            LocatorStrategy.by_text("Confirm"),
            LocatorStrategy.by_text("OK"),
            LocatorStrategy.by_text("Continue"),
        ]
        confirm = self.locator.find_element(confirm_strategies, timeout=3.0)
        if confirm:
            self.gestures.tap(confirm)
            time.sleep(1.0)

    def _select_registration_method(self) -> None:
        """
        Select the registration/login method.

        Priority:
        1. Google (uses pre-configured account)
        2. Facebook (skip)
        3. Quick Start (guest account — fallback)
        """
        login_screen_indicators = [
            LocatorStrategy.by_text("Quick Start"),
            LocatorStrategy.by_text("Log In"),
            LocatorStrategy.by_text("Login"),
            LocatorStrategy.by_text("Google"),
        ]
        login_screen = self.locator.wait_for_element(login_screen_indicators, timeout=10.0)
        if login_screen is None:
            # Maybe already logged in
            lobby_check = self.locator.find_element([
                LocatorStrategy.by_template("templates/mlbb_lobby.png"),
            ], timeout=5.0)
            if lobby_check:
                logger.info("[mlbb_reg] Already in lobby — skipping registration")
                return
            raise RuntimeError("Login/registration screen not found after loading")

        # Try Google login first
        google_strategies = [
            LocatorStrategy.by_text("Google"),
            LocatorStrategy.by_content_desc("Google"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/btn_google"),
            LocatorStrategy.by_template("templates/mlbb_google_btn.png"),
        ]
        google_btn = self.locator.find_element(google_strategies, timeout=5.0)
        if google_btn:
            self.gestures.tap(google_btn)
            logger.info("[mlbb_reg] Tapped Google login")
            time.sleep(2.0)
            # Handle "Choose an account" dialog
            self._handle_choose_account_dialog()
            return

        # Fallback: Quick Start (guest)
        quick_start_strategies = [
            LocatorStrategy.by_text("Quick Start"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/btn_quick_start"),
            LocatorStrategy.by_template("templates/mlbb_quick_start_btn.png"),
        ]
        quick_start = self.locator.find_element(quick_start_strategies, timeout=5.0)
        if quick_start:
            self.gestures.tap(quick_start)
            logger.info("[mlbb_reg] Using Quick Start (guest) — Google not available")
            time.sleep(2.0)
            return

        raise RuntimeError("Could not find Google or Quick Start registration option")

    def _handle_choose_account_dialog(self) -> None:
        """
        Handle the Android system "Choose an account" dialog that appears
        when an app requests Google sign-in via OAuth.
        """
        choose_indicators = [
            LocatorStrategy.by_text("Choose an account"),
            LocatorStrategy.by_text("Select an account"),
        ]
        dialog = self.locator.find_element(choose_indicators, timeout=5.0)
        if not dialog:
            return

        # Find and tap our configured email
        email = self.config.google_email
        if email:
            account_strategies = [
                LocatorStrategy.by_text(email),
                LocatorStrategy.by_content_desc(email),
            ]
            account = self.locator.find_element(account_strategies, timeout=5.0)
            if account:
                self.gestures.tap(account)
                logger.info(f"[mlbb_reg] Selected account: {email}")
                time.sleep(1.5)
                return

        # Fallback: tap first account
        first_account = self.locator.find_element([
            LocatorStrategy.by_xpath(
                '//android.widget.TextView[@resource-id="com.google.android.gms:id/account_name"]'
            ),
        ], timeout=5.0)
        if first_account:
            self.gestures.tap(first_account)
            time.sleep(1.5)

    def _handle_permissions(self) -> None:
        """Handle all permission dialogs MLBB may request."""
        # MLBB commonly requests: storage, microphone, phone state
        self.handle_permission_dialogs(max_dismissals=6)
        time.sleep(1.0)

    def _complete_initial_download(self) -> None:
        """
        MLBB has in-game resource downloads on first launch.
        Wait for them to complete.
        """
        in_game_download_indicators = [
            LocatorStrategy.by_text("Downloading"),
            LocatorStrategy.by_text("Updating"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/download_progress"),
            LocatorStrategy.by_template("templates/mlbb_download_progress.png"),
        ]
        download = self.locator.find_element(in_game_download_indicators, timeout=5.0)
        if not download:
            logger.debug("[mlbb_reg] No in-game download detected")
            return

        logger.info("[mlbb_reg] In-game resource download detected, waiting...")
        max_wait = min(30.0, self.budget.step_remaining(self.BUDGET_KEY) - 10)
        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            still_downloading = self.locator.find_element(
                in_game_download_indicators, timeout=2.0
            )
            if not still_downloading:
                logger.info("[mlbb_reg] In-game download complete")
                return
            time.sleep(3.0)

    def _handle_onboarding(self) -> None:
        """
        Skip through MLBB's onboarding/tutorial screens.

        MLBB has various intro screens:
        - Welcome screen
        - Server selection
        - Username creation (for new accounts)
        - Tutorial battle (can often be skipped)
        """
        # Server selection
        server_ok = [
            LocatorStrategy.by_text("Confirm"),
            LocatorStrategy.by_text("OK"),
            LocatorStrategy.by_text("Continue"),
        ]
        time.sleep(2.0)

        # Skip tutorial if offered
        skip_strategies = [
            LocatorStrategy.by_text("Skip"),
            LocatorStrategy.by_text("Skip Tutorial"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/btn_skip"),
            LocatorStrategy.by_template("templates/mlbb_skip_btn.png"),
        ]

        for _ in range(8):
            # Try various dismiss/skip actions
            elem = self.locator.find_element(skip_strategies + server_ok, timeout=3.0)
            if elem:
                self.gestures.tap(elem)
                time.sleep(1.5)
                continue

            # Handle tapping to advance dialogue
            tap_to_continue = self.locator.find_element([
                LocatorStrategy.by_text("Tap to continue"),
                LocatorStrategy.by_template("templates/mlbb_tap_continue.png"),
            ], timeout=2.0)
            if tap_to_continue:
                self.gestures.tap(tap_to_continue)
                time.sleep(1.0)
                continue

            # No more prompts found
            break

        # Handle username creation for guest accounts
        username_strategies = [
            LocatorStrategy.by_text("Enter Nickname"),
            LocatorStrategy.by_text("Create Username"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/nickname_input"),
        ]
        username_field = self.locator.find_element(username_strategies, timeout=5.0)
        if username_field:
            import random
            import string
            nickname = "Player" + "".join(random.choices(string.digits, k=6))
            self.gestures.type_text(username_field, nickname)
            time.sleep(0.5)
            confirm = self.locator.find_element([
                LocatorStrategy.by_text("Confirm"),
                LocatorStrategy.by_text("OK"),
            ], timeout=3.0)
            if confirm:
                self.gestures.tap(confirm)
                time.sleep(1.5)

    def _verify_in_lobby(self) -> None:
        """Verify we're in the MLBB main lobby."""
        lobby_indicators = [
            LocatorStrategy.by_template("templates/mlbb_lobby.png"),
            LocatorStrategy.by_template("templates/mlbb_battle_button.png"),
            LocatorStrategy.by_text("Battle"),
            LocatorStrategy.by_text("Classic"),
            LocatorStrategy.by_text("Rank"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/battle_btn"),
            LocatorStrategy.by_id(f"{MLBB_PACKAGE}:id/main_battle"),
        ]
        lobby = self.locator.wait_for_element(lobby_indicators, timeout=20.0)
        if lobby is None:
            current_pkg = self.driver.get_current_package()
            current_act = self.driver.get_current_activity()
            raise RuntimeError(
                f"MLBB lobby not found after registration. "
                f"Current: {current_pkg}/{current_act}"
            )
        logger.info("[mlbb_reg] Successfully in MLBB lobby — registration complete")
        self._capture_screenshot(self._steps[-1], "lobby_verified")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _handle_crash_or_error(self) -> None:
        """Detect and recover from common MLBB crashes or error dialogs."""
        error_strategies = [
            LocatorStrategy.by_text("Network Error"),
            LocatorStrategy.by_text("Connection failed"),
            LocatorStrategy.by_text("Unable to connect"),
        ]
        retry_strategies = [
            LocatorStrategy.by_text("Retry"),
            LocatorStrategy.by_text("OK"),
            LocatorStrategy.by_text("Reconnect"),
        ]
        error = self.locator.find_element(error_strategies, timeout=1.0)
        if error:
            logger.warning("[mlbb_reg] Network error dialog detected — retrying")
            retry_btn = self.locator.find_element(retry_strategies, timeout=3.0)
            if retry_btn:
                self.gestures.tap(retry_btn)
                time.sleep(2.0)
