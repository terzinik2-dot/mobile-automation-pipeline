"""
Data models for the orchestration layer.

All models use Pydantic v2 for validation and serialization.
These models are shared between the orchestrator, API server, and dashboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunStatus(str, Enum):
    """Top-level pipeline run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Individual step status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


class ProviderType(str, Enum):
    """Supported device farm providers."""
    BROWSERSTACK = "browserstack"
    AWS_DEVICE_FARM = "aws_device_farm"
    LOCAL = "local"


class LocatorLayer(str, Enum):
    """Which locator strategy resolved an element."""
    RESOURCE_ID = "resource_id"
    TEXT = "text"
    CONTENT_DESC = "content_desc"
    ACCESSIBILITY_ID = "accessibility_id"
    XPATH = "xpath"
    CV_TEMPLATE = "cv_template"
    OCR = "ocr"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------


class DeviceConfig(BaseModel):
    """Configuration for a specific device."""
    provider: ProviderType = ProviderType.LOCAL
    device_name: str = "Android Emulator"
    platform_version: str = "13.0"
    udid: Optional[str] = None
    # BrowserStack-specific
    browserstack_device: Optional[str] = None
    # AWS-specific
    aws_device_arn: Optional[str] = None


class ProviderConfig(BaseModel):
    """Provider authentication and connection settings."""
    provider_type: ProviderType
    # BrowserStack
    bs_username: Optional[str] = None
    bs_access_key: Optional[str] = None
    # AWS
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-west-2"
    aws_project_arn: Optional[str] = None
    aws_device_pool_arn: Optional[str] = None
    # Local
    appium_host: str = "127.0.0.1"
    appium_port: int = 4723


class RunConfig(BaseModel):
    """Full configuration for a pipeline run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    provider: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(provider_type=ProviderType.LOCAL)
    )
    google_email: str = ""
    google_password: str = ""
    google_pay_test_mode: bool = True
    total_budget_seconds: int = 180
    step_retry_count: int = 3
    screenshot_on_failure: bool = True
    video_recording: bool = True
    artifacts_dir: str = "./artifacts"
    # Which scenarios to run (can run subset for testing)
    scenarios: list[str] = Field(
        default_factory=lambda: [
            "google_login",
            "play_store_install",
            "mlbb_registration",
            "google_pay_purchase",
        ]
    )


# ---------------------------------------------------------------------------
# Step-level result models
# ---------------------------------------------------------------------------


class LocatorAttempt(BaseModel):
    """Records a single locator attempt in the cascade."""
    layer: LocatorLayer
    strategy_value: str
    succeeded: bool
    duration_ms: float
    error: Optional[str] = None
    confidence: Optional[float] = None  # For CV/OCR layers


class StepArtifact(BaseModel):
    """An artifact produced during a step."""
    artifact_type: str  # "screenshot" | "log_snippet" | "video_clip"
    file_path: str
    description: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StepResult(BaseModel):
    """Result for a single automation step within a scenario."""
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_name: str
    scenario_name: str
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    attempt_number: int = 1
    max_attempts: int = 3
    locator_attempts: list[LocatorAttempt] = Field(default_factory=list)
    artifacts: list[StepArtifact] = Field(default_factory=list)
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_started(self) -> None:
        self.started_at = datetime.now(timezone.utc)
        self.status = StepStatus.RUNNING

    def mark_completed(self) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.status = StepStatus.COMPLETED
        if self.started_at:
            self.duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000

    def mark_failed(self, error: str, traceback: Optional[str] = None) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.status = StepStatus.FAILED
        self.error_message = error
        self.error_traceback = traceback
        if self.started_at:
            self.duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000

    def mark_timeout(self) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.status = StepStatus.TIMEOUT
        if self.started_at:
            self.duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000


class ScenarioResult(BaseModel):
    """Result for a complete scenario (collection of steps)."""
    scenario_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: str
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    steps: list[StepResult] = Field(default_factory=list)
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def failed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.FAILED)

    def mark_started(self) -> None:
        self.started_at = datetime.now(timezone.utc)
        self.status = StepStatus.RUNNING

    def mark_completed(self) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.status = StepStatus.COMPLETED
        if self.started_at:
            self.duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000

    def mark_failed(self, error: str) -> None:
        self.completed_at = datetime.now(timezone.utc)
        self.status = StepStatus.FAILED
        self.error_message = error
        if self.started_at:
            self.duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000


# ---------------------------------------------------------------------------
# Top-level run result
# ---------------------------------------------------------------------------


class TimingBreakdown(BaseModel):
    """Per-phase timing breakdown for the full run."""
    device_connect_ms: Optional[float] = None
    google_login_ms: Optional[float] = None
    play_store_install_ms: Optional[float] = None
    mlbb_registration_ms: Optional[float] = None
    google_pay_purchase_ms: Optional[float] = None
    cleanup_ms: Optional[float] = None
    total_ms: Optional[float] = None

    @property
    def total_seconds(self) -> Optional[float]:
        if self.total_ms is not None:
            return self.total_ms / 1000
        return None


class RunResult(BaseModel):
    """Complete result for a full pipeline run."""
    run_id: str
    config: RunConfig
    status: RunStatus = RunStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    timing: TimingBreakdown = Field(default_factory=TimingBreakdown)
    device_info: dict[str, Any] = Field(default_factory=dict)
    appium_session_id: Optional[str] = None
    video_url: Optional[str] = None
    logs_url: Optional[str] = None
    error_message: Optional[str] = None
    budget_exceeded: bool = False
    # Locator analytics
    locator_success_by_layer: dict[str, int] = Field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.status in (
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.TIMEOUT,
            RunStatus.CANCELLED,
        )

    @property
    def success_rate(self) -> float:
        """Fraction of scenarios that completed successfully."""
        if not self.scenarios:
            return 0.0
        completed = sum(
            1 for s in self.scenarios if s.status == StepStatus.COMPLETED
        )
        return completed / len(self.scenarios)

    def all_artifacts(self) -> list[StepArtifact]:
        """Flatten all artifacts from all scenarios/steps."""
        artifacts: list[StepArtifact] = []
        for scenario in self.scenarios:
            for step in scenario.steps:
                artifacts.extend(step.artifacts)
        return artifacts

    def to_summary_dict(self) -> dict[str, Any]:
        """Compact summary for list endpoints."""
        return {
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_seconds": self.timing.total_seconds,
            "success_rate": self.success_rate,
            "budget_exceeded": self.budget_exceeded,
            "provider": self.config.provider.provider_type,
            "error": self.error_message,
        }
