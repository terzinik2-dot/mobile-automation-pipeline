"""
Multi-Layer Locator Engine — the crown jewel of this pipeline.

Implements a self-healing element location cascade that tries progressively
less-stable locator strategies in order, gracefully degrading from fast DOM
lookups to computer vision when the UI changes under you.

LOCATOR CASCADE (ordered by speed and stability):
  1. resource-id       — most stable, fastest. Breaks only on major refactors.
  2. text              — stable for user-visible labels. Breaks on i18n/copy changes.
  3. content-desc      — accessibility description. Good for icon buttons.
  4. accessibility-id  — Appium's dedicated accessibility locator.
  5. XPath (semantic)  — flexible tree queries. Slow but expressive.
  6. CV template match — OpenCV image comparison. Works even without DOM access.
  7. OCR text detect   — Tesseract on screenshot. Last resort for text elements.

The engine records which layer succeeded for each lookup so we can:
  - Alert on cascade depth (deep fallbacks = fragile UI)
  - Auto-update preferred strategies when ROI drops
  - Build locator health reports per scenario
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Tuple

from appium.webdriver.common.appiumby import AppiumBy
from loguru import logger
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from orchestrator.models import LocatorAttempt, LocatorLayer


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class StrategyType(str, Enum):
    RESOURCE_ID = "resource_id"
    TEXT = "text"
    CONTENT_DESC = "content_desc"
    ACCESSIBILITY_ID = "accessibility_id"
    XPATH = "xpath"
    CV_TEMPLATE = "cv_template"
    OCR = "ocr"


@dataclass
class LocatorStrategy:
    """
    A single element location strategy.

    Args:
        strategy: Which locator type to use.
        value: The locator value (resource-id, text, file path for CV, etc.).
        partial_match: For text/OCR, allow substring matching.
        confidence_threshold: For CV/OCR, minimum confidence to accept.
        description: Human-readable description for logging.
    """
    strategy: StrategyType
    value: str
    partial_match: bool = False
    confidence_threshold: float = 0.80
    description: str = ""

    # Convenience constructors
    @classmethod
    def by_id(cls, resource_id: str, **kwargs) -> "LocatorStrategy":
        return cls(StrategyType.RESOURCE_ID, resource_id, **kwargs)

    @classmethod
    def by_text(cls, text: str, partial: bool = False, **kwargs) -> "LocatorStrategy":
        return cls(StrategyType.TEXT, text, partial_match=partial, **kwargs)

    @classmethod
    def by_content_desc(cls, desc: str, partial: bool = False, **kwargs) -> "LocatorStrategy":
        return cls(StrategyType.CONTENT_DESC, desc, partial_match=partial, **kwargs)

    @classmethod
    def by_accessibility(cls, aid: str, **kwargs) -> "LocatorStrategy":
        return cls(StrategyType.ACCESSIBILITY_ID, aid, **kwargs)

    @classmethod
    def by_xpath(cls, xpath: str, **kwargs) -> "LocatorStrategy":
        return cls(StrategyType.XPATH, xpath, **kwargs)

    @classmethod
    def by_template(cls, template_path: str, confidence: float = 0.85, **kwargs) -> "LocatorStrategy":
        return cls(
            StrategyType.CV_TEMPLATE,
            template_path,
            confidence_threshold=confidence,
            **kwargs,
        )

    @classmethod
    def by_ocr(cls, text: str, partial: bool = True, **kwargs) -> "LocatorStrategy":
        return cls(StrategyType.OCR, text, partial_match=partial, **kwargs)


@dataclass
class LocatedElement:
    """Result of a successful element location."""
    element: Optional[WebElement]        # None for CV/OCR results
    strategy: LocatorStrategy
    layer: LocatorLayer
    confidence: Optional[float] = None  # For CV/OCR
    # Screen coordinates (always populated, even for DOM elements)
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: float = 0.0

    @property
    def center(self) -> Tuple[int, int]:
        """Center point for tapping."""
        if self.x is not None and self.y is not None:
            cx = self.x + (self.width or 0) // 2
            cy = self.y + (self.height or 0) // 2
            return cx, cy
        return 0, 0

    def tap(self) -> None:
        """Tap the element (works for both DOM and CV results)."""
        if self.element is not None:
            try:
                self.element.click()
                return
            except StaleElementReferenceException:
                pass
        # Fall back to coordinate tap — caller must have a driver reference
        raise RuntimeError(
            "DOM element tap failed and no driver reference available for coordinate tap. "
            "Use GestureEngine.tap_at(x, y) with element.center instead."
        )


# ---------------------------------------------------------------------------
# Main locator engine
# ---------------------------------------------------------------------------


class MultiLayerLocator:
    """
    Self-healing multi-layer element locator.

    Tries each LocatorStrategy in order, falling back to the next
    when a strategy fails. Records attempt metadata for analytics.

    Usage:
        locator = MultiLayerLocator(driver=appium_driver)

        element = locator.find_element([
            LocatorStrategy.by_id("com.mobile.legends:id/btn_start"),
            LocatorStrategy.by_text("START GAME"),
            LocatorStrategy.by_template("templates/btn_start.png"),
            LocatorStrategy.by_ocr("START GAME"),
        ], timeout=10.0)

        if element:
            gestures.tap(element)
    """

    def __init__(
        self,
        driver,                          # AppiumDriver instance
        cv_engine: Optional[Any] = None, # CVEngine instance (lazy import)
        default_timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> None:
        self._driver = driver
        self._cv_engine = cv_engine
        self.default_timeout = default_timeout
        self.poll_interval = poll_interval
        self._attempt_log: list[LocatorAttempt] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_element(
        self,
        strategies: list[LocatorStrategy],
        timeout: Optional[float] = None,
        required: bool = False,
    ) -> Optional[LocatedElement]:
        """
        Try each strategy in order until one succeeds.

        Args:
            strategies: Ordered list of locator strategies to try.
            timeout: Per-strategy timeout (defaults to self.default_timeout).
            required: If True, raise NoSuchElementException on total failure.

        Returns:
            LocatedElement on success, None on failure.
        """
        per_strategy_timeout = timeout or self.default_timeout
        self._attempt_log = []

        for strategy in strategies:
            start_ts = time.monotonic()
            logger.debug(
                f"[Locator] Trying {strategy.strategy.value}: {strategy.value[:60]}"
            )

            try:
                result = self._try_strategy(strategy, per_strategy_timeout)
                if result is not None:
                    duration_ms = (time.monotonic() - start_ts) * 1000
                    result.duration_ms = duration_ms
                    layer = self._strategy_to_layer(strategy.strategy)
                    self._log_attempt(strategy, layer, True, duration_ms, result.confidence)
                    logger.info(
                        f"[Locator] Found via {strategy.strategy.value} "
                        f"in {duration_ms:.0f}ms"
                    )
                    return result
                else:
                    duration_ms = (time.monotonic() - start_ts) * 1000
                    layer = self._strategy_to_layer(strategy.strategy)
                    self._log_attempt(strategy, layer, False, duration_ms)
                    logger.debug(
                        f"[Locator] {strategy.strategy.value} failed "
                        f"in {duration_ms:.0f}ms"
                    )

            except Exception as e:
                duration_ms = (time.monotonic() - start_ts) * 1000
                layer = self._strategy_to_layer(strategy.strategy)
                self._log_attempt(strategy, layer, False, duration_ms, error=str(e))
                logger.debug(
                    f"[Locator] {strategy.strategy.value} error: {type(e).__name__}: {e}"
                )

        # All strategies exhausted
        strategy_names = [s.strategy.value for s in strategies]
        logger.warning(
            f"[Locator] All {len(strategies)} strategies failed: {strategy_names}"
        )
        if required:
            raise NoSuchElementException(
                f"Element not found after trying: {strategy_names}"
            )
        return None

    def find_elements(
        self,
        strategies: list[LocatorStrategy],
        timeout: Optional[float] = None,
    ) -> list[LocatedElement]:
        """
        Find all matching elements using the first successful strategy.
        Only DOM strategies support multiple results.
        """
        per_strategy_timeout = timeout or self.default_timeout
        dom_strategies = [
            s for s in strategies
            if s.strategy not in (StrategyType.CV_TEMPLATE, StrategyType.OCR)
        ]
        for strategy in dom_strategies:
            elements = self._try_strategy_multiple(strategy, per_strategy_timeout)
            if elements:
                return elements
        return []

    def wait_for_element(
        self,
        strategies: list[LocatorStrategy],
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> Optional[LocatedElement]:
        """
        Repeatedly try all strategies until success or timeout.

        Unlike find_element (which gives each strategy `timeout` seconds),
        this polls ALL strategies together for up to `timeout` seconds.
        """
        deadline = time.monotonic() + timeout
        attempt = 0
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            per_try_timeout = min(poll_interval * 2, remaining)
            result = self.find_element(strategies, timeout=per_try_timeout)
            if result is not None:
                return result
            attempt += 1
            wait_time = min(poll_interval, deadline - time.monotonic())
            if wait_time > 0:
                time.sleep(wait_time)

        logger.warning(f"[Locator] wait_for_element timed out after {timeout}s")
        return None

    def wait_for_gone(
        self,
        strategies: list[LocatorStrategy],
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait until ALL strategies fail (element disappears)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.find_element(strategies, timeout=1.0)
            if result is None:
                return True
            time.sleep(poll_interval)
        return False

    @property
    def attempt_log(self) -> list[LocatorAttempt]:
        """Return the recorded locator attempts from the last find_element call."""
        return list(self._attempt_log)

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _try_strategy(
        self, strategy: LocatorStrategy, timeout: float
    ) -> Optional[LocatedElement]:
        """Dispatch to the appropriate strategy implementation."""
        if strategy.strategy == StrategyType.RESOURCE_ID:
            return self._by_resource_id(strategy, timeout)
        elif strategy.strategy == StrategyType.TEXT:
            return self._by_text(strategy, timeout)
        elif strategy.strategy == StrategyType.CONTENT_DESC:
            return self._by_content_desc(strategy, timeout)
        elif strategy.strategy == StrategyType.ACCESSIBILITY_ID:
            return self._by_accessibility_id(strategy, timeout)
        elif strategy.strategy == StrategyType.XPATH:
            return self._by_xpath(strategy, timeout)
        elif strategy.strategy == StrategyType.CV_TEMPLATE:
            return self._by_cv_template(strategy)
        elif strategy.strategy == StrategyType.OCR:
            return self._by_ocr(strategy)
        return None

    def _by_resource_id(
        self, strategy: LocatorStrategy, timeout: float
    ) -> Optional[LocatedElement]:
        """Find by Android resource-id (most stable locator)."""
        driver = self._driver.driver
        try:
            wait = WebDriverWait(driver, timeout)
            elem = wait.until(
                EC.presence_of_element_located(
                    (AppiumBy.ID, strategy.value)
                )
            )
            return self._wrap_element(elem, strategy, LocatorLayer.RESOURCE_ID)
        except (TimeoutException, NoSuchElementException):
            return None

    def _by_text(
        self, strategy: LocatorStrategy, timeout: float
    ) -> Optional[LocatedElement]:
        """Find by visible text (exact or partial)."""
        driver = self._driver.driver
        if strategy.partial_match:
            xpath = f'//*[contains(@text, "{strategy.value}")]'
        else:
            xpath = f'//*[@text="{strategy.value}"]'
        try:
            wait = WebDriverWait(driver, timeout)
            elem = wait.until(
                EC.presence_of_element_located((AppiumBy.XPATH, xpath))
            )
            return self._wrap_element(elem, strategy, LocatorLayer.TEXT)
        except (TimeoutException, NoSuchElementException):
            return None

    def _by_content_desc(
        self, strategy: LocatorStrategy, timeout: float
    ) -> Optional[LocatedElement]:
        """Find by content-description (accessibility text)."""
        driver = self._driver.driver
        if strategy.partial_match:
            xpath = f'//*[contains(@content-desc, "{strategy.value}")]'
        else:
            xpath = f'//*[@content-desc="{strategy.value}"]'
        try:
            wait = WebDriverWait(driver, timeout)
            elem = wait.until(
                EC.presence_of_element_located((AppiumBy.XPATH, xpath))
            )
            return self._wrap_element(elem, strategy, LocatorLayer.CONTENT_DESC)
        except (TimeoutException, NoSuchElementException):
            return None

    def _by_accessibility_id(
        self, strategy: LocatorStrategy, timeout: float
    ) -> Optional[LocatedElement]:
        """Find by Appium accessibility ID."""
        driver = self._driver.driver
        try:
            wait = WebDriverWait(driver, timeout)
            elem = wait.until(
                EC.presence_of_element_located(
                    (AppiumBy.ACCESSIBILITY_ID, strategy.value)
                )
            )
            return self._wrap_element(elem, strategy, LocatorLayer.ACCESSIBILITY_ID)
        except (TimeoutException, NoSuchElementException):
            return None

    def _by_xpath(
        self, strategy: LocatorStrategy, timeout: float
    ) -> Optional[LocatedElement]:
        """Find by XPath expression."""
        driver = self._driver.driver
        try:
            wait = WebDriverWait(driver, timeout)
            elem = wait.until(
                EC.presence_of_element_located(
                    (AppiumBy.XPATH, strategy.value)
                )
            )
            return self._wrap_element(elem, strategy, LocatorLayer.XPATH)
        except (TimeoutException, NoSuchElementException):
            return None

    def _by_cv_template(
        self, strategy: LocatorStrategy
    ) -> Optional[LocatedElement]:
        """Find element by OpenCV template matching on the current screenshot."""
        cv_engine = self._get_cv_engine()
        screenshot = self._driver.screenshot_as_numpy()
        result = cv_engine.find_on_screen(strategy.value, screenshot)
        if result is None:
            return None
        x, y, confidence = result
        if confidence < strategy.confidence_threshold:
            logger.debug(
                f"[Locator] CV template confidence too low: "
                f"{confidence:.3f} < {strategy.confidence_threshold}"
            )
            return None
        return LocatedElement(
            element=None,
            strategy=strategy,
            layer=LocatorLayer.CV_TEMPLATE,
            confidence=confidence,
            x=x,
            y=y,
            width=50,   # Approximate — template matching gives center point
            height=30,
        )

    def _by_ocr(self, strategy: LocatorStrategy) -> Optional[LocatedElement]:
        """Find element using Tesseract OCR on the current screenshot."""
        cv_engine = self._get_cv_engine()
        screenshot = self._driver.screenshot_as_numpy()
        result = cv_engine.find_text_on_screen(
            strategy.value,
            screenshot,
            partial_match=strategy.partial_match,
        )
        if result is None:
            return None
        x, y, confidence = result
        if confidence < strategy.confidence_threshold:
            return None
        return LocatedElement(
            element=None,
            strategy=strategy,
            layer=LocatorLayer.OCR,
            confidence=confidence,
            x=x,
            y=y,
            width=100,  # Approximate
            height=30,
        )

    def _try_strategy_multiple(
        self, strategy: LocatorStrategy, timeout: float
    ) -> list[LocatedElement]:
        """Try a strategy and return all matching elements."""
        driver = self._driver.driver
        by, value = self._strategy_to_appium_by(strategy)
        if by is None:
            return []
        try:
            wait = WebDriverWait(driver, timeout)
            wait.until(EC.presence_of_element_located((by, value)))
            elements = driver.find_elements(by, value)
            return [
                self._wrap_element(e, strategy, self._strategy_to_layer(strategy.strategy))
                for e in elements
            ]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wrap_element(
        self,
        elem: WebElement,
        strategy: LocatorStrategy,
        layer: LocatorLayer,
    ) -> LocatedElement:
        """Wrap a Selenium WebElement into a LocatedElement."""
        try:
            loc = elem.location
            size = elem.size
            return LocatedElement(
                element=elem,
                strategy=strategy,
                layer=layer,
                x=loc.get("x", 0),
                y=loc.get("y", 0),
                width=size.get("width", 0),
                height=size.get("height", 0),
            )
        except StaleElementReferenceException:
            return LocatedElement(element=elem, strategy=strategy, layer=layer)

    def _strategy_to_appium_by(
        self, strategy: LocatorStrategy
    ) -> Tuple[Optional[str], str]:
        """Map a StrategyType to an AppiumBy constant."""
        mapping = {
            StrategyType.RESOURCE_ID: AppiumBy.ID,
            StrategyType.TEXT: AppiumBy.XPATH,
            StrategyType.CONTENT_DESC: AppiumBy.XPATH,
            StrategyType.ACCESSIBILITY_ID: AppiumBy.ACCESSIBILITY_ID,
            StrategyType.XPATH: AppiumBy.XPATH,
        }
        by = mapping.get(strategy.strategy)
        value = strategy.value
        if strategy.strategy == StrategyType.TEXT:
            value = f'//*[@text="{strategy.value}"]'
        elif strategy.strategy == StrategyType.CONTENT_DESC:
            value = f'//*[@content-desc="{strategy.value}"]'
        return by, value

    def _strategy_to_layer(self, strategy_type: StrategyType) -> LocatorLayer:
        """Convert StrategyType to LocatorLayer enum."""
        mapping = {
            StrategyType.RESOURCE_ID: LocatorLayer.RESOURCE_ID,
            StrategyType.TEXT: LocatorLayer.TEXT,
            StrategyType.CONTENT_DESC: LocatorLayer.CONTENT_DESC,
            StrategyType.ACCESSIBILITY_ID: LocatorLayer.ACCESSIBILITY_ID,
            StrategyType.XPATH: LocatorLayer.XPATH,
            StrategyType.CV_TEMPLATE: LocatorLayer.CV_TEMPLATE,
            StrategyType.OCR: LocatorLayer.OCR,
        }
        return mapping.get(strategy_type, LocatorLayer.UNKNOWN)

    def _log_attempt(
        self,
        strategy: LocatorStrategy,
        layer: LocatorLayer,
        succeeded: bool,
        duration_ms: float,
        confidence: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record a locator attempt for analytics."""
        self._attempt_log.append(
            LocatorAttempt(
                layer=layer,
                strategy_value=strategy.value[:100],
                succeeded=succeeded,
                duration_ms=duration_ms,
                confidence=confidence,
                error=error,
            )
        )

    def _get_cv_engine(self):
        """Lazy-load the CV engine."""
        if self._cv_engine is None:
            from executors.cv_engine import CVEngine
            from orchestrator.config import get_settings
            self._cv_engine = CVEngine(settings=get_settings())
        return self._cv_engine
