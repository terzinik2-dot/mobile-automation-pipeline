"""
ScenarioOrchestrator — Main orchestration engine.

Manages the full pipeline lifecycle:
1. Connect to device farm provider
2. Create Appium WebDriver session
3. Run scenarios in sequence with time budget enforcement
4. Collect artifacts (screenshots, video, logs)
5. Return a structured RunResult

Design principles:
- Fail fast on total budget expiry
- Each scenario runs in an isolated try/except
- Always attempt cleanup even if scenarios fail
- Artifacts are saved incrementally (not just at the end)
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Type

from loguru import logger

from orchestrator.config import get_settings
from orchestrator.models import (
    ProviderType,
    RunConfig,
    RunResult,
    RunStatus,
    ScenarioResult,
    StepStatus,
    TimingBreakdown,
)
from orchestrator.time_budget import TimeBudgetManager


# We import lazily to avoid circular imports and allow optional components
def _import_provider(provider_type: ProviderType):
    """Dynamically import the correct provider class."""
    if provider_type == ProviderType.BROWSERSTACK:
        from providers.browserstack import BrowserStackProvider
        return BrowserStackProvider
    elif provider_type == ProviderType.AWS_DEVICE_FARM:
        from providers.aws_device_farm import AWSDeviceFarmProvider
        return AWSDeviceFarmProvider
    else:
        from providers.local_device import LocalDeviceProvider
        return LocalDeviceProvider


def _import_scenario(scenario_name: str):
    """Dynamically import the correct scenario class."""
    mapping = {
        "google_login": ("scenarios.google_login", "GoogleLoginScenario"),
        "play_store_install": ("scenarios.play_store_install", "PlayStoreInstallScenario"),
        "mlbb_registration": ("scenarios.mlbb_registration", "MLBBRegistrationScenario"),
        "google_pay_purchase": ("scenarios.google_pay_purchase", "GooglePayPurchaseScenario"),
    }
    if scenario_name not in mapping:
        raise ValueError(f"Unknown scenario: {scenario_name}")
    module_path, class_name = mapping[scenario_name]
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class ScenarioOrchestrator:
    """
    Top-level orchestration engine for the mobile automation pipeline.

    This class is the single entry point for running the complete
    Google Login → Play Store Install → MLBB Registration → Google Pay
    pipeline, or any subset of those scenarios.
    """

    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.settings = get_settings()
        self.budget = TimeBudgetManager(total_seconds=config.total_budget_seconds)
        self._provider = None
        self._driver = None
        self._artifacts_dir = Path(config.artifacts_dir) / config.run_id
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> RunResult:
        """
        Execute the full pipeline synchronously.

        Returns a RunResult regardless of success/failure.
        All exceptions are caught and recorded.
        """
        result = RunResult(
            run_id=self.config.run_id,
            config=self.config,
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        self.budget.start()
        logger.info(f"[ORCHESTRATOR] Starting run {self.config.run_id}")
        logger.info(f"[ORCHESTRATOR] Provider: {self.config.provider.provider_type}")
        logger.info(f"[ORCHESTRATOR] Scenarios: {self.config.scenarios}")
        logger.info(f"[ORCHESTRATOR] Budget: {self.config.total_budget_seconds}s")

        try:
            # Phase 1: Connect to device farm
            self._connect_provider(result)

            # Phase 2: Create Appium session
            self._create_appium_session(result)

            # Phase 3: Run scenarios in sequence
            self._run_scenarios(result)

        except TimeoutError as e:
            result.status = RunStatus.TIMEOUT
            result.error_message = str(e)
            result.budget_exceeded = True
            logger.error(f"[ORCHESTRATOR] Run TIMEOUT: {e}")

        except Exception as e:
            result.status = RunStatus.FAILED
            result.error_message = str(e)
            logger.exception(f"[ORCHESTRATOR] Run FAILED: {e}")

        finally:
            # Always attempt cleanup
            self._cleanup(result)

        # Final status resolution
        if result.status == RunStatus.RUNNING:
            all_done = all(
                s.status in (StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.SKIPPED)
                for s in result.scenarios
            )
            any_failed = any(
                s.status == StepStatus.FAILED for s in result.scenarios
            )
            if all_done:
                result.status = RunStatus.FAILED if any_failed else RunStatus.COMPLETED
            else:
                result.status = RunStatus.FAILED

        result.completed_at = datetime.now(timezone.utc)
        result.budget_exceeded = self.budget.is_expired()

        # Build timing breakdown
        timing_report = self.budget.get_report()
        result.timing = self._build_timing(timing_report)

        # Build locator analytics
        result.locator_success_by_layer = self._collect_locator_stats(result)

        self.budget.log_report()
        logger.info(
            f"[ORCHESTRATOR] Run {self.config.run_id} finished: "
            f"{result.status} in {result.timing.total_seconds:.1f}s"
        )
        return result

    async def run_async(self) -> RunResult:
        """Async wrapper — runs the synchronous pipeline in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run)

    # ------------------------------------------------------------------
    # Internal phases
    # ------------------------------------------------------------------

    def _connect_provider(self, result: RunResult) -> None:
        """Connect to the device farm provider."""
        step_name = "device_connect"
        self.budget.start_step(step_name)
        try:
            ProviderClass = _import_provider(self.config.provider.provider_type)
            self._provider = ProviderClass(self.config)
            self._provider.connect()
            result.device_info = self._provider.get_device_info()
            logger.info(f"[ORCHESTRATOR] Connected to provider: {result.device_info}")
            self.budget.end_step(step_name, "completed")
        except Exception as e:
            self.budget.end_step(step_name, "failed")
            raise RuntimeError(f"Failed to connect to provider: {e}") from e

    def _create_appium_session(self, result: RunResult) -> None:
        """Create the Appium WebDriver session."""
        from executors.appium_driver import AppiumDriver
        try:
            appium_url = self._provider.get_appium_url()
            capabilities = self._build_capabilities()
            self._driver = AppiumDriver(
                appium_url=appium_url,
                capabilities=capabilities,
                timeout=min(30, self.budget.remaining_seconds),
            )
            self._driver.start_session()
            result.appium_session_id = self._driver.session_id
            logger.info(f"[ORCHESTRATOR] Appium session: {result.appium_session_id}")
        except Exception as e:
            raise RuntimeError(f"Failed to create Appium session: {e}") from e

    def _run_scenarios(self, result: RunResult) -> None:
        """Run each scenario in sequence."""
        for scenario_name in self.config.scenarios:
            if self.budget.is_expired():
                logger.warning(
                    f"[ORCHESTRATOR] Skipping '{scenario_name}' — budget exhausted"
                )
                skipped = ScenarioResult(
                    scenario_name=scenario_name,
                    status=StepStatus.SKIPPED,
                )
                result.scenarios.append(skipped)
                continue

            scenario_result = self._run_single_scenario(scenario_name)
            result.scenarios.append(scenario_result)

            # If a critical scenario failed, decide whether to continue
            if scenario_result.status == StepStatus.FAILED:
                if scenario_name in ("google_login", "play_store_install"):
                    # Can't proceed without login or app installed
                    logger.error(
                        f"[ORCHESTRATOR] Critical scenario '{scenario_name}' failed — "
                        "aborting remaining scenarios"
                    )
                    break

    def _run_single_scenario(self, scenario_name: str) -> ScenarioResult:
        """Run a single scenario with full error handling."""
        logger.info(f"[ORCHESTRATOR] Starting scenario: {scenario_name}")
        scenario_result = ScenarioResult(scenario_name=scenario_name)
        scenario_result.mark_started()

        # Map scenario name to time budget step name
        budget_step_name = scenario_name  # names match by convention

        try:
            self.budget.start_step(budget_step_name)
            ScenarioClass = _import_scenario(scenario_name)

            from executors.locator_engine import MultiLayerLocator
            from executors.cv_engine import CVEngine
            from executors.gesture_engine import GestureEngine

            locator = MultiLayerLocator(driver=self._driver)
            cv_engine = CVEngine(settings=self.settings)
            gestures = GestureEngine(driver=self._driver)

            scenario = ScenarioClass(
                driver=self._driver,
                locator=locator,
                cv_engine=cv_engine,
                gestures=gestures,
                budget=self.budget,
                config=self.config,
                artifacts_dir=self._artifacts_dir,
            )

            steps = scenario.run()
            scenario_result.steps = steps

            # Determine scenario outcome from step results
            failed_steps = [s for s in steps if s.status == StepStatus.FAILED]
            timeout_steps = [s for s in steps if s.status == StepStatus.TIMEOUT]

            if timeout_steps:
                scenario_result.mark_failed(
                    f"Timeout in steps: {[s.step_name for s in timeout_steps]}"
                )
            elif failed_steps:
                scenario_result.mark_failed(
                    f"Failed steps: {[s.step_name for s in failed_steps]}"
                )
            else:
                scenario_result.mark_completed()

            self.budget.end_step(budget_step_name, scenario_result.status.value)

        except TimeoutError as e:
            scenario_result.mark_failed(str(e))
            self.budget.end_step(budget_step_name, "timeout")
            # Re-raise total budget timeout; step timeout is just a failure
            if "Total run budget" in str(e):
                raise

        except Exception as e:
            tb = traceback.format_exc()
            scenario_result.mark_failed(str(e))
            scenario_result.metadata["traceback"] = tb
            self.budget.end_step(budget_step_name, "failed")
            logger.exception(f"[ORCHESTRATOR] Scenario '{scenario_name}' error: {e}")

            # Save error screenshot
            self._save_error_screenshot(scenario_name)

        logger.info(
            f"[ORCHESTRATOR] Scenario '{scenario_name}' finished: "
            f"{scenario_result.status} in "
            f"{(scenario_result.duration_ms or 0) / 1000:.1f}s"
        )
        return scenario_result

    def _cleanup(self, result: RunResult) -> None:
        """Gracefully shut down Appium session and provider."""
        self.budget.start_step("cleanup")
        try:
            if self._driver:
                try:
                    # Fetch video/logs before closing session
                    if self.config.video_recording and self._provider:
                        video_path = self._provider.get_video(
                            session_id=result.appium_session_id,
                            output_dir=str(self._artifacts_dir),
                        )
                        if video_path:
                            result.video_url = video_path
                    logs_path = self._collect_logs(result)
                    if logs_path:
                        result.logs_url = logs_path
                except Exception as e:
                    logger.warning(f"Error collecting artifacts: {e}")

                try:
                    self._driver.quit()
                except Exception as e:
                    logger.warning(f"Error quitting driver: {e}")

            if self._provider:
                try:
                    self._provider.disconnect()
                except Exception as e:
                    logger.warning(f"Error disconnecting provider: {e}")

        finally:
            self.budget.end_step("cleanup", "completed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_capabilities(self) -> dict:
        """Build Appium desired capabilities from config."""
        cfg = self.config
        caps: dict = {
            "platformName": "Android",
            "appium:automationName": "UiAutomator2",
            "appium:deviceName": cfg.device.device_name,
            "appium:platformVersion": cfg.device.platform_version,
            "appium:noReset": False,
            "appium:fullReset": False,
            "appium:newCommandTimeout": self.settings.appium_new_command_timeout,
        }
        if cfg.device.udid:
            caps["appium:udid"] = cfg.device.udid

        # Provider-specific capabilities
        provider_type = cfg.provider.provider_type
        if provider_type == ProviderType.BROWSERSTACK:
            caps["bstack:options"] = {
                "userName": cfg.provider.bs_username,
                "accessKey": cfg.provider.bs_access_key,
                "deviceName": cfg.device.browserstack_device or cfg.device.device_name,
                "osVersion": cfg.device.platform_version,
                "projectName": "MobileAutomationPipeline",
                "buildName": f"run-{cfg.run_id[:8]}",
                "sessionName": "Full Pipeline Run",
                "video": str(cfg.video_recording).lower(),
                "networkLogs": "true",
                "deviceLogs": "true",
            }
        elif provider_type == ProviderType.AWS_DEVICE_FARM:
            if self.settings.aws_device_farm_project_arn:
                caps["appium:projectArn"] = self.settings.aws_device_farm_project_arn

        if cfg.video_recording:
            caps["appium:recordVideo"] = True

        return caps

    def _save_error_screenshot(self, context: str) -> Optional[str]:
        """Save a screenshot for debugging on error."""
        if not self.config.screenshot_on_failure or not self._driver:
            return None
        try:
            ts = datetime.now(timezone.utc).strftime("%H%M%S")
            path = self._artifacts_dir / f"error_{context}_{ts}.png"
            self._driver.save_screenshot(str(path))
            logger.info(f"Error screenshot saved: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"Could not save error screenshot: {e}")
            return None

    def _collect_logs(self, result: RunResult) -> Optional[str]:
        """Collect device/Appium logs and save to artifacts."""
        if not self._driver:
            return None
        try:
            logs_path = self._artifacts_dir / "device_logs.txt"
            logs = self._driver.get_log("logcat")
            with open(logs_path, "w", encoding="utf-8") as f:
                for entry in logs:
                    f.write(f"{entry.get('timestamp', '')} "
                            f"[{entry.get('level', '')}] "
                            f"{entry.get('message', '')}\n")
            return str(logs_path)
        except Exception as e:
            logger.warning(f"Could not collect logs: {e}")
            return None

    def _build_timing(self, report: dict) -> TimingBreakdown:
        """Build TimingBreakdown from budget report."""
        step_map = {s["step"]: s["elapsed_s"] * 1000 for s in report["steps"]}
        return TimingBreakdown(
            device_connect_ms=step_map.get("device_connect"),
            google_login_ms=step_map.get("google_login"),
            play_store_install_ms=step_map.get("play_store_install"),
            mlbb_registration_ms=step_map.get("mlbb_registration"),
            google_pay_purchase_ms=step_map.get("google_pay_purchase"),
            cleanup_ms=step_map.get("cleanup"),
            total_ms=report["total_elapsed_s"] * 1000,
        )

    def _collect_locator_stats(self, result: RunResult) -> dict[str, int]:
        """Count locator layer successes across all steps."""
        stats: dict[str, int] = {}
        for scenario in result.scenarios:
            for step in scenario.steps:
                for attempt in step.locator_attempts:
                    if attempt.succeeded:
                        key = attempt.layer.value
                        stats[key] = stats.get(key, 0) + 1
        return stats
