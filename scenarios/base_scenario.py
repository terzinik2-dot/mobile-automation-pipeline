"""
Base Scenario — Abstract base class for all automation scenarios.

Provides:
- Step decorator for automatic tracking, timing, screenshots, and retry
- Structured step result list building
- Budget-aware execution with per-step timeout
- Screenshot capture on success and failure
"""

from __future__ import annotations

import functools
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from loguru import logger

from executors.appium_driver import AppiumDriver
from executors.cv_engine import CVEngine
from executors.gesture_engine import GestureEngine
from executors.locator_engine import MultiLayerLocator
from orchestrator.models import LocatorAttempt, StepArtifact, StepResult, StepStatus
from orchestrator.time_budget import TimeBudgetManager


F = TypeVar("F", bound=Callable)


class BaseScenario(ABC):
    """
    Abstract base class for all automation scenarios.

    Subclasses implement run_steps() and use the @step() decorator
    (or call _run_step() manually) to structure their automation.
    """

    SCENARIO_NAME: str = "base"
    BUDGET_KEY: str = "base"  # Key for time budget allocation

    def __init__(
        self,
        driver: AppiumDriver,
        locator: MultiLayerLocator,
        cv_engine: CVEngine,
        gestures: GestureEngine,
        budget: TimeBudgetManager,
        config: Any,
        artifacts_dir: Path,
    ) -> None:
        self.driver = driver
        self.locator = locator
        self.cv = cv_engine
        self.gestures = gestures
        self.budget = budget
        self.config = config
        self.artifacts_dir = artifacts_dir
        self._steps: list[StepResult] = []
        self._current_step_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> list[StepResult]:
        """
        Execute all steps and return results.
        Calls the abstract run_steps() method implemented by each scenario.
        """
        logger.info(f"[{self.SCENARIO_NAME}] Starting scenario")
        self._steps = []
        try:
            self.run_steps()
        except TimeoutError as e:
            logger.error(f"[{self.SCENARIO_NAME}] Scenario timeout: {e}")
            if self._current_step_name:
                self._fail_current_step(str(e))
        except Exception as e:
            logger.exception(f"[{self.SCENARIO_NAME}] Scenario error: {e}")
            if self._current_step_name:
                self._fail_current_step(str(e))
        logger.info(
            f"[{self.SCENARIO_NAME}] Scenario finished: "
            f"{sum(1 for s in self._steps if s.status == StepStatus.COMPLETED)}/"
            f"{len(self._steps)} steps completed"
        )
        return self._steps

    @abstractmethod
    def run_steps(self) -> None:
        """
        Implement this method in subclasses.
        Call self._execute_step() or use self.step() context manager.
        """
        ...

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        name: str,
        fn: Callable,
        max_retries: int = 3,
        screenshot_on_success: bool = False,
        screenshot_on_failure: bool = True,
    ) -> StepResult:
        """
        Execute a callable as a named step with retry and artifact capture.

        Args:
            name: Human-readable step name.
            fn: The step implementation callable.
            max_retries: Number of attempts before marking as failed.
            screenshot_on_success: Save screenshot after successful step.
            screenshot_on_failure: Save screenshot after failed step.

        Returns:
            StepResult with status, timing, and artifacts.
        """
        step = StepResult(
            step_name=name,
            scenario_name=self.SCENARIO_NAME,
            max_attempts=max_retries,
        )
        self._steps.append(step)
        self._current_step_name = name

        for attempt in range(1, max_retries + 1):
            step.attempt_number = attempt
            step.mark_started()

            logger.info(f"[{self.SCENARIO_NAME}] Step '{name}' attempt {attempt}/{max_retries}")

            # Check budget before each attempt
            try:
                self.budget.assert_step_alive(self.BUDGET_KEY)
            except TimeoutError as e:
                step.mark_timeout()
                step.error_message = str(e)
                logger.warning(f"[{self.SCENARIO_NAME}] Step '{name}' budget exhausted")
                self._capture_screenshot(step, label="timeout")
                break

            try:
                result = fn()
                step.mark_completed()
                step.metadata["return_value"] = str(result) if result is not None else None

                # Attach locator attempts from this step
                step.locator_attempts = list(self.locator.attempt_log)

                if screenshot_on_success or self.config.screenshot_on_failure:
                    self._capture_screenshot(step, label="success")

                logger.info(
                    f"[{self.SCENARIO_NAME}] Step '{name}' DONE "
                    f"in {(step.duration_ms or 0):.0f}ms"
                )
                self._current_step_name = None
                return step

            except Exception as e:
                tb = traceback.format_exc()
                is_last_attempt = attempt >= max_retries

                if is_last_attempt:
                    step.mark_failed(str(e), tb)
                    logger.error(
                        f"[{self.SCENARIO_NAME}] Step '{name}' FAILED after "
                        f"{max_retries} attempts: {e}"
                    )
                    if screenshot_on_failure:
                        self._capture_screenshot(step, label="failure")
                else:
                    step.status = StepStatus.RETRYING
                    logger.warning(
                        f"[{self.SCENARIO_NAME}] Step '{name}' attempt {attempt} failed: {e}"
                        f" — retrying in 2s"
                    )
                    time.sleep(2)

        self._current_step_name = None
        return step

    def _fail_current_step(self, error: str) -> None:
        """Mark the most recent step as failed (for exception handlers)."""
        if self._steps:
            last = self._steps[-1]
            if last.status in (StepStatus.RUNNING, StepStatus.RETRYING):
                last.mark_failed(error)

    # ------------------------------------------------------------------
    # Screenshot helpers
    # ------------------------------------------------------------------

    def _capture_screenshot(
        self,
        step: StepResult,
        label: str = "screenshot",
    ) -> Optional[str]:
        """Capture a screenshot and attach it to the step's artifacts."""
        try:
            ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
            filename = f"{self.SCENARIO_NAME}_{step.step_name}_{label}_{ts}.png"
            path = self.artifacts_dir / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            self.driver.save_screenshot(str(path))
            step.artifacts.append(
                StepArtifact(
                    artifact_type="screenshot",
                    file_path=str(path),
                    description=f"{step.step_name} — {label}",
                )
            )
            return str(path)
        except Exception as e:
            logger.debug(f"[{self.SCENARIO_NAME}] Screenshot capture failed: {e}")
            return None

    def screenshot(self, label: str = "manual") -> Optional[str]:
        """Convenience method to capture a screenshot at any point."""
        if self._steps:
            return self._capture_screenshot(self._steps[-1], label)
        return None

    # ------------------------------------------------------------------
    # Polling helpers
    # ------------------------------------------------------------------

    def wait_for_condition(
        self,
        condition_fn: Callable[[], bool],
        timeout: float = 15.0,
        poll_interval: float = 0.5,
        description: str = "condition",
    ) -> bool:
        """
        Poll until condition_fn() returns True or timeout is reached.

        Budget-aware: checks budget before each poll iteration.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.budget.assert_step_alive(self.BUDGET_KEY)
            except TimeoutError:
                return False
            if condition_fn():
                return True
            time.sleep(poll_interval)
        logger.warning(f"[{self.SCENARIO_NAME}] Timed out waiting for: {description}")
        return False

    def wait_seconds(self, seconds: float, reason: str = "") -> None:
        """
        Wait for a fixed duration, checking budget on each tick.
        Prefers checking budget every 0.5s rather than sleeping blindly.
        """
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                self.budget.assert_step_alive(self.BUDGET_KEY)
            except TimeoutError:
                return
            time.sleep(min(0.5, deadline - time.monotonic()))

    # ------------------------------------------------------------------
    # Common dialog handling
    # ------------------------------------------------------------------

    def dismiss_system_dialog(self, timeout: float = 3.0) -> bool:
        """
        Dismiss common Android system dialogs (permission prompts, update dialogs).
        Returns True if a dialog was found and dismissed.
        """
        from executors.locator_engine import LocatorStrategy

        dismiss_strategies = [
            # Android 12+ permission dialogs
            LocatorStrategy.by_id("com.android.permissioncontroller:id/permission_allow_button"),
            LocatorStrategy.by_id("com.android.permissioncontroller:id/permission_allow_foreground_only_button"),
            # Generic "Allow" text
            LocatorStrategy.by_text("Allow"),
            LocatorStrategy.by_text("OK"),
            LocatorStrategy.by_text("ALLOW"),
            LocatorStrategy.by_text("Accept"),
            # Google "Continue" dialog
            LocatorStrategy.by_text("Continue"),
            # App update dialog
            LocatorStrategy.by_text("Not now"),
            LocatorStrategy.by_text("Skip"),
        ]

        for strategy in dismiss_strategies:
            elem = self.locator.find_element([strategy], timeout=timeout / len(dismiss_strategies))
            if elem is not None:
                self.gestures.tap(elem)
                logger.info(f"[{self.SCENARIO_NAME}] Dismissed dialog: {strategy.value}")
                return True
        return False

    def handle_permission_dialogs(self, max_dismissals: int = 5) -> int:
        """Dismiss up to max_dismissals system permission dialogs."""
        count = 0
        for _ in range(max_dismissals):
            if self.dismiss_system_dialog(timeout=2.0):
                count += 1
                time.sleep(0.5)
            else:
                break
        return count
