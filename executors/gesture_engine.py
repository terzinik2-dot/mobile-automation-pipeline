"""
Gesture Engine — Tap, swipe, scroll, long-press, pinch, and text input.

All gestures take screen coordinates. Works with both DOM elements
(LocatedElement.element is set) and pure-coordinate targets from CV/OCR.

Uses Appium's W3C Actions API for precise gesture control.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple, Union

from appium.webdriver.common.action_chains import ActionChains
from appium.webdriver.common.appiumby import AppiumBy
from loguru import logger
from selenium.webdriver.remote.webelement import WebElement

# Import LocatedElement without creating circular dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from executors.locator_engine import LocatedElement
    from executors.appium_driver import AppiumDriver


class GestureEngine:
    """
    High-level gesture engine wrapping Appium's Actions API.

    All coordinate-based methods accept (x, y) tuples representing
    pixel positions on the device screen.
    """

    def __init__(self, driver: "AppiumDriver") -> None:
        self._driver = driver
        self._screen_size: Optional[Tuple[int, int]] = None

    # ------------------------------------------------------------------
    # Basic taps
    # ------------------------------------------------------------------

    def tap(self, element: "LocatedElement") -> None:
        """
        Tap on a located element.

        If the element has a WebElement reference, uses .click() for reliability.
        Falls back to coordinate tap if the DOM reference is stale.
        """
        if element.element is not None:
            try:
                element.element.click()
                logger.debug(
                    f"[Gesture] tap via DOM element at "
                    f"({element.x}, {element.y})"
                )
                return
            except Exception as e:
                logger.debug(f"[Gesture] DOM tap failed ({e}), falling back to coordinates")

        # Coordinate tap
        cx, cy = element.center
        self.tap_at(cx, cy)

    def tap_at(self, x: int, y: int) -> None:
        """Tap at absolute screen coordinates."""
        driver = self._driver.driver
        driver.tap([(x, y)])
        logger.debug(f"[Gesture] tap_at ({x}, {y})")

    def double_tap(self, element: "LocatedElement") -> None:
        """Double-tap on an element."""
        cx, cy = element.center
        self.double_tap_at(cx, cy)

    def double_tap_at(self, x: int, y: int) -> None:
        """Double-tap at coordinates."""
        driver = self._driver.driver
        action = ActionChains(driver)
        action.w3c_actions.pointer_action.move_to_location(x, y)
        action.w3c_actions.pointer_action.click()
        action.w3c_actions.pointer_action.pause(0.1)
        action.w3c_actions.pointer_action.click()
        action.perform()
        logger.debug(f"[Gesture] double_tap_at ({x}, {y})")

    def long_press(
        self,
        element: "LocatedElement",
        duration_ms: int = 1500,
    ) -> None:
        """Long-press on an element."""
        cx, cy = element.center
        self.long_press_at(cx, cy, duration_ms)

    def long_press_at(self, x: int, y: int, duration_ms: int = 1500) -> None:
        """Long-press at coordinates for the specified duration."""
        driver = self._driver.driver
        action = ActionChains(driver)
        action.w3c_actions.pointer_action.move_to_location(x, y)
        action.w3c_actions.pointer_action.pointer_down()
        action.w3c_actions.pointer_action.pause(duration_ms / 1000.0)
        action.w3c_actions.pointer_action.release()
        action.perform()
        logger.debug(f"[Gesture] long_press_at ({x}, {y}) {duration_ms}ms")

    # ------------------------------------------------------------------
    # Text input
    # ------------------------------------------------------------------

    def type_text(self, element: "LocatedElement", text: str) -> None:
        """Tap on an element and type text."""
        self.tap(element)
        time.sleep(0.3)
        if element.element is not None:
            try:
                element.element.send_keys(text)
                logger.debug(f"[Gesture] type_text (DOM) '{text[:20]}...'")
                return
            except Exception:
                pass
        # Fallback: use driver.execute_script to send keys
        self._driver.set_clipboard(text)
        self._paste_from_clipboard()

    def clear_and_type(self, element: "LocatedElement", text: str) -> None:
        """Clear an input field and type new text."""
        self.tap(element)
        time.sleep(0.2)
        if element.element is not None:
            try:
                element.element.clear()
                element.element.send_keys(text)
                return
            except Exception:
                pass
        # Fallback: select-all + delete + type
        self._select_all_and_delete()
        self.type_text(element, text)

    def _paste_from_clipboard(self) -> None:
        """Trigger paste via key combo (Ctrl+V / long press)."""
        driver = self._driver.driver
        driver.press_keycode(50, metastate=0x02)  # Ctrl+V

    def _select_all_and_delete(self) -> None:
        """Select all text and delete it."""
        driver = self._driver.driver
        # Select all: Ctrl+A
        driver.press_keycode(29, metastate=0x02)
        time.sleep(0.1)
        # Delete
        driver.press_keycode(67)  # KEYCODE_DEL

    # ------------------------------------------------------------------
    # Swipe and scroll
    # ------------------------------------------------------------------

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int = 500,
    ) -> None:
        """Swipe from (start_x, start_y) to (end_x, end_y)."""
        driver = self._driver.driver
        driver.swipe(start_x, start_y, end_x, end_y, duration_ms)
        logger.debug(
            f"[Gesture] swipe ({start_x},{start_y}) → ({end_x},{end_y}) {duration_ms}ms"
        )

    def scroll_up(self, amount: float = 0.4) -> None:
        """Scroll up by `amount` fraction of screen height."""
        size = self._get_screen_size()
        w, h = size
        cx = w // 2
        start_y = int(h * (0.5 + amount / 2))
        end_y = int(h * (0.5 - amount / 2))
        self.swipe(cx, start_y, cx, end_y, duration_ms=600)

    def scroll_down(self, amount: float = 0.4) -> None:
        """Scroll down by `amount` fraction of screen height."""
        size = self._get_screen_size()
        w, h = size
        cx = w // 2
        start_y = int(h * (0.5 - amount / 2))
        end_y = int(h * (0.5 + amount / 2))
        self.swipe(cx, start_y, cx, end_y, duration_ms=600)

    def scroll_to_text(
        self,
        text: str,
        max_scrolls: int = 5,
        direction: str = "down",
    ) -> bool:
        """
        Scroll until text is visible on screen.

        Uses UiScrollable for efficient on-device scrolling.
        Returns True if text was found, False if max scrolls reached.
        """
        driver = self._driver.driver
        try:
            # UiScrollable is the fastest way to scroll to a specific text
            uia_selector = (
                f'new UiScrollable(new UiSelector().scrollable(true))'
                f'.scrollIntoView(new UiSelector().text("{text}"))'
            )
            driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, uia_selector)
            logger.debug(f"[Gesture] scrolled to text: '{text}'")
            return True
        except Exception:
            pass

        # Fallback: manual scroll loop
        for _ in range(max_scrolls):
            if direction == "down":
                self.scroll_down()
            else:
                self.scroll_up()
            time.sleep(0.5)
            # Check if text is now visible via page source
            try:
                source = self._driver.get_page_source()
                if text in source:
                    return True
            except Exception:
                pass
        return False

    def scroll_element(
        self,
        element: "LocatedElement",
        direction: str = "up",
        amount: float = 0.3,
    ) -> None:
        """Scroll within a specific element (e.g., a scrollable container)."""
        if element.x is None or element.y is None:
            return
        w = element.width or 200
        h = element.height or 400
        cx = element.x + w // 2
        # Scroll within the element
        if direction == "up":
            start_y = element.y + int(h * 0.3)
            end_y = element.y + int(h * 0.7)
        else:
            start_y = element.y + int(h * 0.7)
            end_y = element.y + int(h * 0.3)
        self.swipe(cx, start_y, cx, end_y, duration_ms=600)

    # ------------------------------------------------------------------
    # Pinch and zoom
    # ------------------------------------------------------------------

    def pinch_open(self, cx: int, cy: int, offset: int = 200) -> None:
        """Pinch-open (zoom in) gesture centered at (cx, cy)."""
        driver = self._driver.driver
        action1 = ActionChains(driver)
        action2 = ActionChains(driver)
        # Two-finger spread
        driver.execute_script("mobile: pinchOpenGesture", {
            "left": cx - offset,
            "top": cy - offset,
            "width": offset * 2,
            "height": offset * 2,
            "percent": 0.75,
            "speed": 2500,
        })

    def pinch_close(self, cx: int, cy: int, offset: int = 200) -> None:
        """Pinch-close (zoom out) gesture centered at (cx, cy)."""
        driver = self._driver.driver
        driver.execute_script("mobile: pinchCloseGesture", {
            "left": cx - offset,
            "top": cy - offset,
            "width": offset * 2,
            "height": offset * 2,
            "percent": 0.75,
            "speed": 2500,
        })

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------

    def drag_and_drop(
        self,
        from_element: "LocatedElement",
        to_element: "LocatedElement",
        hold_ms: int = 1000,
    ) -> None:
        """Drag from one element to another."""
        fx, fy = from_element.center
        tx, ty = to_element.center
        driver = self._driver.driver
        driver.execute_script("mobile: dragGesture", {
            "startX": fx,
            "startY": fy,
            "endX": tx,
            "endY": ty,
            "speed": 2000,
        })

    # ------------------------------------------------------------------
    # Screen utilities
    # ------------------------------------------------------------------

    def _get_screen_size(self) -> Tuple[int, int]:
        """Return (width, height) of the device screen."""
        if self._screen_size is None:
            size = self._driver.driver.get_window_size()
            self._screen_size = (size["width"], size["height"])
        return self._screen_size

    def get_screen_center(self) -> Tuple[int, int]:
        """Return the center pixel of the screen."""
        w, h = self._get_screen_size()
        return w // 2, h // 2

    def dismiss_keyboard(self) -> None:
        """Hide the soft keyboard if visible."""
        try:
            if self._driver.driver.is_keyboard_shown():
                self._driver.driver.hide_keyboard()
        except Exception:
            pass
