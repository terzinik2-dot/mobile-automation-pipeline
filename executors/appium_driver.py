"""
Appium Driver — Session management and core driver wrapper.

Wraps appium.webdriver.Remote with:
- Session lifecycle management (start, quit, restart)
- Screenshot helpers with automatic file-naming
- Video recording controls
- Log capture
- Timeout management
"""

from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from appium import webdriver
from appium.options import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from loguru import logger
from selenium.webdriver.remote.webelement import WebElement


class AppiumDriver:
    """
    Managed Appium WebDriver session.

    Handles:
    - Session creation with exponential backoff
    - Screenshot capture (returns PIL Image or saves to file)
    - Screen recording start/stop
    - Log collection
    - Graceful session teardown
    """

    def __init__(
        self,
        appium_url: str,
        capabilities: dict[str, Any],
        timeout: float = 60.0,
        implicit_wait: float = 5.0,
    ) -> None:
        self.appium_url = appium_url
        self.capabilities = capabilities
        self.connection_timeout = timeout
        self.implicit_wait = implicit_wait

        self._driver: Optional[webdriver.Remote] = None
        self._session_id: Optional[str] = None
        self._recording: bool = False

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(self, max_retries: int = 3) -> None:
        """
        Create an Appium session with retry logic.

        Raises RuntimeError if all retries fail.
        """
        options = AppiumOptions()
        for key, value in self.capabilities.items():
            options.set_capability(key, value)

        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"[AppiumDriver] Creating session (attempt {attempt}/{max_retries}) "
                    f"at {self.appium_url}"
                )
                self._driver = webdriver.Remote(
                    command_executor=self.appium_url,
                    options=options,
                )
                self._driver.implicitly_wait(self.implicit_wait)
                self._session_id = self._driver.session_id
                logger.info(f"[AppiumDriver] Session created: {self._session_id}")
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[AppiumDriver] Session attempt {attempt} failed: {e}"
                )
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff

        raise RuntimeError(
            f"Failed to create Appium session after {max_retries} attempts: {last_error}"
        )

    def quit(self) -> None:
        """Gracefully close the Appium session."""
        if self._recording:
            self.stop_recording()
        if self._driver:
            try:
                self._driver.quit()
                logger.info(f"[AppiumDriver] Session {self._session_id} closed")
            except Exception as e:
                logger.warning(f"[AppiumDriver] Error during quit: {e}")
            finally:
                self._driver = None
                self._session_id = None

    def restart_session(self) -> None:
        """Quit and restart the session."""
        logger.info("[AppiumDriver] Restarting session")
        self.quit()
        time.sleep(2)
        self.start_session()

    @property
    def driver(self) -> webdriver.Remote:
        """Access the raw Selenium/Appium driver."""
        if self._driver is None:
            raise RuntimeError("Appium session not started. Call start_session() first.")
        return self._driver

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def is_alive(self) -> bool:
        """Check if the session is still alive."""
        if not self._driver:
            return False
        try:
            _ = self._driver.current_package
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def launch_app(self, package: str, activity: Optional[str] = None) -> None:
        """Launch an app by package name."""
        if activity:
            self._driver.start_activity(package, activity)
        else:
            self._driver.activate_app(package)
        logger.debug(f"[AppiumDriver] Launched: {package}")

    def terminate_app(self, package: str) -> None:
        """Force-stop an app."""
        self._driver.terminate_app(package)

    def open_notifications(self) -> None:
        """Open the notification shade."""
        self._driver.open_notifications()

    def press_home(self) -> None:
        """Press the Home button."""
        self._driver.press_keycode(3)  # KEYCODE_HOME

    def press_back(self) -> None:
        """Press the Back button."""
        self._driver.press_keycode(4)  # KEYCODE_BACK

    def press_enter(self) -> None:
        """Press Enter (confirm/search)."""
        self._driver.press_keycode(66)  # KEYCODE_ENTER

    def set_clipboard(self, text: str) -> None:
        """Set clipboard text (useful for filling forms)."""
        self._driver.set_clipboard(text, "plaintext")

    # ------------------------------------------------------------------
    # Element access (raw — use locator_engine for production)
    # ------------------------------------------------------------------

    def find_by_id(self, resource_id: str, timeout: float = 5.0) -> Optional[WebElement]:
        """Find element by resource ID with explicit wait."""
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:
            wait = WebDriverWait(self._driver, timeout)
            return wait.until(
                EC.presence_of_element_located((AppiumBy.ID, resource_id))
            )
        except Exception:
            return None

    def find_by_text(self, text: str, timeout: float = 5.0) -> Optional[WebElement]:
        """Find element by exact text."""
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:
            wait = WebDriverWait(self._driver, timeout)
            return wait.until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, f'//*[@text="{text}"]')
                )
            )
        except Exception:
            return None

    def find_all(self, by: str, value: str) -> list[WebElement]:
        """Find all elements matching a locator."""
        try:
            return self._driver.find_elements(by, value)
        except Exception:
            return []

    def get_page_source(self) -> str:
        """Return current page XML source."""
        return self._driver.page_source

    def get_current_package(self) -> str:
        """Return the package name of the foreground app."""
        return self._driver.current_package or ""

    def get_current_activity(self) -> str:
        """Return the current activity name."""
        return self._driver.current_activity or ""

    # ------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------

    def take_screenshot(self, output_path: Optional[str] = None) -> bytes:
        """
        Capture the current screen as PNG bytes.

        If output_path is given, also saves to that file.
        Returns the raw PNG bytes.
        """
        png_data = self._driver.get_screenshot_as_png()
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(png_data)
        return png_data

    def save_screenshot(self, output_path: str) -> bool:
        """Save screenshot to a file. Returns True on success."""
        try:
            self.take_screenshot(output_path)
            return True
        except Exception as e:
            logger.warning(f"[AppiumDriver] Screenshot failed: {e}")
            return False

    def screenshot_as_numpy(self):
        """Return screenshot as a numpy array (for OpenCV)."""
        import io
        import numpy as np
        from PIL import Image
        png_bytes = self.take_screenshot()
        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        return np.array(image)

    # ------------------------------------------------------------------
    # Screen recording
    # ------------------------------------------------------------------

    def start_recording(self, output_path: Optional[str] = None) -> None:
        """Start screen recording via Appium."""
        try:
            self._driver.start_recording_screen(
                videoType="mp4",
                videoQuality="medium",
                timeLimit=180,  # 3 min max
            )
            self._recording = True
            self._recording_output = output_path
            logger.info("[AppiumDriver] Screen recording started")
        except Exception as e:
            logger.warning(f"[AppiumDriver] Could not start recording: {e}")

    def stop_recording(self, output_path: Optional[str] = None) -> Optional[str]:
        """Stop screen recording and save to file."""
        if not self._recording:
            return None
        save_path = output_path or getattr(self, "_recording_output", None)
        try:
            video_b64 = self._driver.stop_recording_screen()
            self._recording = False
            if save_path and video_b64:
                Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(video_b64))
                logger.info(f"[AppiumDriver] Recording saved: {save_path}")
                return save_path
        except Exception as e:
            logger.warning(f"[AppiumDriver] Could not stop recording: {e}")
        return None

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def get_log(self, log_type: str = "logcat") -> list[dict]:
        """Fetch log entries of the given type."""
        try:
            return self._driver.get_log(log_type)
        except Exception as e:
            logger.debug(f"[AppiumDriver] get_log({log_type}) failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def execute_script(self, script: str, *args) -> Any:
        """Execute a mobile command or JavaScript."""
        return self._driver.execute_script(script, *args)

    def execute_mobile_command(self, command: str, args: dict = None) -> Any:
        """Execute an Appium mobile: command."""
        return self._driver.execute_script(f"mobile: {command}", args or {})

    def wait_for_package(
        self,
        package: str,
        timeout: float = 30.0,
        interval: float = 0.5,
    ) -> bool:
        """Wait until a specific app is in the foreground."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.get_current_package() == package:
                return True
            time.sleep(interval)
        return False

    def wait_for_activity(
        self,
        activity: str,
        timeout: float = 30.0,
        interval: float = 0.5,
    ) -> bool:
        """Wait until a specific activity is in the foreground."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.get_current_activity()
            if activity in current:
                return True
            time.sleep(interval)
        return False
