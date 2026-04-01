"""
Configuration management for the Mobile Automation Pipeline.

Loads settings from environment variables (via .env file) and provides
a typed, validated configuration object to all pipeline components.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from orchestrator.models import ProviderType


class Settings(BaseSettings):
    """
    Central configuration object.

    All values can be overridden via environment variables.
    Prefix: none (direct env var name matching).
    """

    # --- Provider ------------------------------------------------------------
    device_provider: ProviderType = ProviderType.LOCAL

    # --- BrowserStack --------------------------------------------------------
    browserstack_username: Optional[str] = None
    browserstack_access_key: Optional[str] = None
    browserstack_app_url: Optional[str] = None
    browserstack_device: str = "Google Pixel 7"
    browserstack_os_version: str = "13.0"

    # --- AWS Device Farm -----------------------------------------------------
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-west-2"
    aws_device_farm_project_arn: Optional[str] = None
    aws_device_farm_device_pool_arn: Optional[str] = None

    # --- Local Device --------------------------------------------------------
    local_device_udid: Optional[str] = None
    local_appium_host: str = "127.0.0.1"
    local_appium_port: int = 4723
    adb_path: str = "adb"

    # --- Google Account ------------------------------------------------------
    google_account_email: str = ""
    google_account_password: str = ""
    google_account_recovery_email: Optional[str] = None

    # --- Google Pay ----------------------------------------------------------
    google_pay_test_mode: bool = True
    google_play_test_card_number: Optional[str] = None

    # --- MLBB ----------------------------------------------------------------
    mlbb_package_name: str = "com.mobile.legends"
    mlbb_play_store_url: str = (
        "https://play.google.com/store/apps/details?id=com.mobile.legends"
    )

    # --- Appium --------------------------------------------------------------
    appium_version: str = "2.0"
    appium_server_timeout: int = 60
    appium_implicit_wait: int = 5
    appium_new_command_timeout: int = 300

    # --- Orchestrator --------------------------------------------------------
    total_time_budget: int = 180
    step_retry_count: int = 3
    screenshot_on_failure: bool = True
    video_recording: bool = True

    # --- CV / OCR ------------------------------------------------------------
    tesseract_cmd: str = "/usr/bin/tesseract"
    template_dir: str = "./templates"
    cv_confidence_threshold: float = 0.8
    ocr_language: str = "eng"

    # --- Artifacts -----------------------------------------------------------
    artifacts_dir: str = "./artifacts"
    artifacts_retention_days: int = 30

    # --- FastAPI Server ------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change-this-in-production"
    database_url: str = "sqlite+aiosqlite:///./pipeline.db"

    # --- Next.js Dashboard ---------------------------------------------------
    next_public_api_url: str = "http://localhost:8000"
    next_public_clerk_publishable_key: Optional[str] = None
    clerk_secret_key: Optional[str] = None

    @field_validator("artifacts_dir", "template_dir", mode="before")
    @classmethod
    def expand_paths(cls, v: str) -> str:
        """Expand relative paths relative to the project root."""
        path = Path(v)
        if not path.is_absolute():
            # Resolve relative to the file's grandparent (project root)
            root = Path(__file__).parent.parent
            return str(root / path)
        return v

    @field_validator("cv_confidence_threshold", mode="before")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"cv_confidence_threshold must be in [0, 1], got {v}")
        return v

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        for path_str in [self.artifacts_dir, self.template_dir]:
            Path(path_str).mkdir(parents=True, exist_ok=True)

    def get_appium_url(self, host: Optional[str] = None, port: Optional[int] = None) -> str:
        """Build Appium server URL."""
        h = host or self.local_appium_host
        p = port or self.local_appium_port
        return f"http://{h}:{p}"

    def has_browserstack_credentials(self) -> bool:
        return bool(self.browserstack_username and self.browserstack_access_key)

    def has_aws_credentials(self) -> bool:
        return bool(
            self.aws_access_key_id
            and self.aws_secret_access_key
            and self.aws_device_farm_project_arn
        )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton settings instance.

    The lru_cache ensures we only parse env vars once.
    Use get_settings.cache_clear() in tests to reset.
    """
    settings = Settings()
    settings.ensure_dirs()
    return settings
