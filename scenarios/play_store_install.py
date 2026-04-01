"""
Play Store Install Scenario

Searches for and installs Mobile Legends: Bang Bang from the Google Play Store.

Steps:
1. open_play_store          — launch Play Store app
2. dismiss_promos           — dismiss any promotional banners
3. tap_search               — tap the search bar
4. type_search_query        — type "Mobile Legends Bang Bang"
5. select_correct_result    — identify the correct MLBB result
6. tap_install              — tap Install button
7. accept_permissions       — accept app permissions dialog
8. wait_for_download        — wait until download completes
9. verify_installation      — confirm MLBB is installed
"""

from __future__ import annotations

import time

from loguru import logger

from executors.locator_engine import LocatorStrategy
from scenarios.base_scenario import BaseScenario

PLAY_STORE_PACKAGE = "com.android.vending"
MLBB_PACKAGE = "com.mobile.legends"
MLBB_DEVELOPER = "Moonton"
MLBB_TITLE = "Mobile Legends: Bang Bang"


class PlayStoreInstallScenario(BaseScenario):
    """Scenario: Find and install MLBB from the Play Store."""

    SCENARIO_NAME = "play_store_install"
    BUDGET_KEY = "play_store_install"

    def run_steps(self) -> None:
        # Fast-path: check if already installed
        is_installed = self._execute_step(
            "check_if_already_installed",
            self._check_if_already_installed,
            max_retries=1,
            screenshot_on_failure=False,
        )
        if is_installed.metadata.get("return_value") == "True":
            logger.info("[play_store] MLBB already installed — skipping install")
            return

        self._execute_step("open_play_store", self._open_play_store, max_retries=2)
        self._execute_step("dismiss_promos", self._dismiss_promos, max_retries=1, screenshot_on_failure=False)
        self._execute_step("tap_search", self._tap_search, max_retries=3)
        self._execute_step("type_search_query", self._type_search_query, max_retries=2)
        self._execute_step("select_mlbb_result", self._select_mlbb_result, max_retries=3)
        self._execute_step("tap_install", self._tap_install, max_retries=3)
        self._execute_step("accept_permissions", self._accept_permissions, max_retries=2, screenshot_on_failure=False)
        self._execute_step("wait_for_download", self._wait_for_download, max_retries=1)
        self._execute_step("verify_installation", self._verify_installation, max_retries=2)

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _check_if_already_installed(self) -> bool:
        """Check if MLBB is already installed on the device."""
        try:
            result = self.driver.execute_script(
                "mobile: shell",
                {"command": "pm", "args": ["list", "packages", MLBB_PACKAGE]}
            )
            if result and MLBB_PACKAGE in result:
                logger.info(f"[play_store] {MLBB_PACKAGE} already installed")
                return True
        except Exception as e:
            logger.debug(f"[play_store] Package check failed: {e}")
        return False

    def _open_play_store(self) -> None:
        """Launch the Play Store app."""
        self.driver.launch_app(
            PLAY_STORE_PACKAGE,
            "com.google.android.finsky.activities.MainActivity",
        )
        time.sleep(2.5)

        # Verify Play Store opened
        store_indicators = [
            LocatorStrategy.by_id("com.android.vending:id/search_bar_hint"),
            LocatorStrategy.by_text("Search for apps & games"),
            LocatorStrategy.by_content_desc("Search for apps & games"),
            LocatorStrategy.by_text("For you"),
        ]
        elem = self.locator.wait_for_element(store_indicators, timeout=15.0)
        if elem is None:
            # Maybe there's a login prompt
            login_prompt = self.locator.find_element([
                LocatorStrategy.by_text("Sign in")
            ], timeout=3.0)
            if login_prompt:
                raise RuntimeError("Play Store requires sign-in — run google_login first")
            raise RuntimeError("Play Store did not open successfully")
        logger.info("[play_store] Play Store opened")

    def _dismiss_promos(self) -> None:
        """Dismiss any promotional overlays or update prompts."""
        dismiss_strategies = [
            LocatorStrategy.by_text("Skip"),
            LocatorStrategy.by_text("Not now"),
            LocatorStrategy.by_text("Later"),
            LocatorStrategy.by_content_desc("Close"),
            LocatorStrategy.by_id("com.android.vending:id/close_button"),
        ]
        for _ in range(3):
            elem = self.locator.find_element(dismiss_strategies, timeout=2.0)
            if elem:
                self.gestures.tap(elem)
                time.sleep(0.5)
            else:
                break

    def _tap_search(self) -> None:
        """Tap the Play Store search bar."""
        search_strategies = [
            LocatorStrategy.by_id("com.android.vending:id/search_bar_hint"),
            LocatorStrategy.by_content_desc("Search for apps & games"),
            LocatorStrategy.by_text("Search for apps & games"),
            LocatorStrategy.by_id("com.android.vending:id/search_button"),
            # Newer Play Store versions
            LocatorStrategy.by_accessibility("Search"),
            LocatorStrategy.by_template("templates/play_store_search_bar.png"),
        ]
        elem = self.locator.find_element(search_strategies, timeout=10.0)
        if elem is None:
            raise RuntimeError("Play Store search bar not found")
        self.gestures.tap(elem)
        time.sleep(1.0)

    def _type_search_query(self) -> None:
        """Type the MLBB search query."""
        # The search field should be active after tapping
        search_input_strategies = [
            LocatorStrategy.by_id("com.android.vending:id/search_bar_text"),
            LocatorStrategy.by_xpath('//android.widget.EditText'),
            LocatorStrategy.by_accessibility("Search"),
        ]
        elem = self.locator.find_element(search_input_strategies, timeout=8.0)
        if elem is None:
            raise RuntimeError("Search input field not found")

        self.gestures.type_text(elem, "Mobile Legends Bang Bang")
        time.sleep(0.5)
        self.driver.press_enter()
        time.sleep(2.0)

        # Verify search results appeared
        results_indicators = [
            LocatorStrategy.by_text("Mobile Legends"),
            LocatorStrategy.by_id("com.android.vending:id/bucket_title"),
            LocatorStrategy.by_xpath('//android.widget.TextView[contains(@text, "Mobile Legends")]'),
        ]
        results = self.locator.wait_for_element(results_indicators, timeout=15.0)
        if results is None:
            raise RuntimeError("Search results did not appear after searching")

    def _select_mlbb_result(self) -> None:
        """
        Identify and tap the correct MLBB result.

        MLBB-specific identifiers:
        - Package: com.mobile.legends
        - Developer: Moonton
        - Title contains "Mobile Legends"
        """
        # Strategy 1: exact title match
        mlbb_strategies = [
            LocatorStrategy.by_text(MLBB_TITLE),
            LocatorStrategy.by_text("Mobile Legends: Bang Bang"),
            # Partial match for layout variations
            LocatorStrategy.by_xpath(
                '//android.widget.TextView[contains(@text, "Mobile Legends")]'
                '/following-sibling::android.widget.TextView[contains(@text, "Moonton")]'
                '/ancestor::android.view.ViewGroup[1]'
            ),
            # Template fallback
            LocatorStrategy.by_template("templates/mlbb_icon.png", confidence=0.75),
        ]

        # May need to scroll through results
        for scroll_attempt in range(3):
            elem = self.locator.find_element(mlbb_strategies, timeout=5.0)
            if elem:
                # Verify this is the right app (check for Moonton developer nearby)
                self.gestures.tap(elem)
                time.sleep(2.0)

                # Verify we're on the correct app page
                verify_strategies = [
                    LocatorStrategy.by_text(MLBB_TITLE),
                    LocatorStrategy.by_text("Moonton"),
                    LocatorStrategy.by_text("4+"),  # Age rating
                ]
                on_correct_page = self.locator.find_element(verify_strategies, timeout=5.0)
                if on_correct_page:
                    logger.info("[play_store] Navigated to MLBB app page")
                    return
                # Wrong app — go back
                self.driver.press_back()
                time.sleep(1.0)

            # Scroll down to see more results
            self.gestures.scroll_down(amount=0.3)
            time.sleep(0.5)

        raise RuntimeError("Could not find/select MLBB in search results")

    def _tap_install(self) -> None:
        """Tap the Install button on the MLBB app page."""
        install_strategies = [
            LocatorStrategy.by_text("Install"),
            LocatorStrategy.by_accessibility("Install"),
            LocatorStrategy.by_id("com.android.vending:id/install"),
            LocatorStrategy.by_id("com.android.vending:id/buy_button"),
            LocatorStrategy.by_template("templates/play_store_install_btn.png"),
        ]
        elem = self.locator.find_element(install_strategies, timeout=10.0)
        if elem is None:
            # Check if "Open" button is shown (already installed)
            open_btn = self.locator.find_element(
                [LocatorStrategy.by_text("Open"), LocatorStrategy.by_text("Update")],
                timeout=3.0
            )
            if open_btn:
                logger.info("[play_store] App already installed (Open button visible)")
                return
            raise RuntimeError("Install button not found")

        self.gestures.tap(elem)
        logger.info("[play_store] Install tapped")
        time.sleep(1.5)

    def _accept_permissions(self) -> None:
        """Accept any app permission dialogs that appear after tapping Install."""
        # Modern Play Store (API 26+) doesn't show individual permissions,
        # but some flows still show a storage permission dialog
        permission_strategies = [
            LocatorStrategy.by_text("Accept"),
            LocatorStrategy.by_text("Allow"),
            LocatorStrategy.by_id("com.android.vending:id/continue_button"),
        ]
        time.sleep(1.5)
        elem = self.locator.find_element(permission_strategies, timeout=5.0)
        if elem:
            self.gestures.tap(elem)
            logger.info("[play_store] Accepted permission dialog")

    def _wait_for_download(self) -> None:
        """
        Wait for MLBB to finish downloading and installing.
        MLBB is ~2GB, but on a fast connection we check for completion.
        We wait up to 120 seconds (or remaining budget).
        """
        max_wait = min(120.0, self.budget.step_remaining(self.BUDGET_KEY))
        logger.info(f"[play_store] Waiting up to {max_wait:.0f}s for download...")

        # Progress indicators
        downloading_indicators = [
            LocatorStrategy.by_text("Downloading"),
            LocatorStrategy.by_text("Installing"),
            LocatorStrategy.by_id("com.android.vending:id/download_progress"),
        ]
        # Completion indicators
        complete_indicators = [
            LocatorStrategy.by_text("Open"),
            LocatorStrategy.by_text("Uninstall"),
            LocatorStrategy.by_accessibility("Open"),
            LocatorStrategy.by_id("com.android.vending:id/open_button"),
        ]

        deadline = time.monotonic() + max_wait
        phase = "waiting"

        while time.monotonic() < deadline:
            # Check for completion first
            done = self.locator.find_element(complete_indicators, timeout=2.0)
            if done:
                logger.info("[play_store] App installed — 'Open' button visible")
                return

            # Check if still downloading
            in_progress = self.locator.find_element(downloading_indicators, timeout=1.0)
            if in_progress and phase != "downloading":
                phase = "downloading"
                logger.info("[play_store] Download in progress...")

            # Check for errors
            error_strategies = [
                LocatorStrategy.by_text("Retry"),
                LocatorStrategy.by_text("Try again"),
                LocatorStrategy.by_text("Error"),
            ]
            error = self.locator.find_element(error_strategies, timeout=1.0)
            if error:
                error_text = error.element.text if error.element else "Unknown error"
                raise RuntimeError(f"Play Store download error: {error_text}")

            time.sleep(3.0)

        # Check one more time after timeout
        done = self.locator.find_element(complete_indicators, timeout=5.0)
        if done:
            return

        raise RuntimeError(f"App installation did not complete within {max_wait:.0f}s")

    def _verify_installation(self) -> None:
        """Verify MLBB is installed by checking the package list."""
        try:
            result = self.driver.execute_script(
                "mobile: shell",
                {"command": "pm", "args": ["list", "packages", MLBB_PACKAGE]}
            )
            if result and MLBB_PACKAGE in result:
                logger.info(f"[play_store] Verified: {MLBB_PACKAGE} is installed")
                return
        except Exception as e:
            logger.debug(f"[play_store] Package verification via shell failed: {e}")

        # Fallback: check Play Store shows "Open" button
        open_strategies = [
            LocatorStrategy.by_text("Open"),
            LocatorStrategy.by_accessibility("Open"),
        ]
        elem = self.locator.find_element(open_strategies, timeout=5.0)
        if elem:
            logger.info("[play_store] Verified: MLBB app page shows 'Open' button")
            return

        raise RuntimeError("Could not verify MLBB installation")
