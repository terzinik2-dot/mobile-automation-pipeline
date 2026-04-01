"""
Abstract base class for all device farm providers.

All providers must implement this interface so the orchestrator can swap
between BrowserStack, AWS Device Farm, and local devices transparently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class DeviceProvider(ABC):
    """
    Abstract interface for a device farm provider.

    Responsibilities:
    - Allocate/release a physical or virtual Android device
    - Provide the Appium server URL for the session
    - Install APKs when needed
    - Retrieve post-session artifacts (video, logs)
    """

    def __init__(self, config: Any) -> None:
        """
        Args:
            config: RunConfig (imported lazily to avoid circular deps)
        """
        self.config = config
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """
        Establish a connection to the provider (authenticate, reserve device).

        Must set self._connected = True on success.
        Raises: ConnectionError on failure.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """
        Release the device / clean up provider resources.

        Should be idempotent (safe to call multiple times).
        """
        ...

    # ------------------------------------------------------------------
    # Appium integration
    # ------------------------------------------------------------------

    @abstractmethod
    def get_appium_url(self) -> str:
        """
        Return the Appium WebDriver server URL for this provider.

        Examples:
            Local:         "http://127.0.0.1:4723"
            BrowserStack:  "https://hub-cloud.browserstack.com/wd/hub"
            AWS:           "https://devicefarm.us-west-2.amazonaws.com/wd/hub"
        """
        ...

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    @abstractmethod
    def get_device_info(self) -> dict[str, Any]:
        """
        Return metadata about the allocated device.

        Expected keys (all optional): model, manufacturer, os_version,
        screen_resolution, udid, api_level, provider_name, session_url.
        """
        ...

    # ------------------------------------------------------------------
    # App management
    # ------------------------------------------------------------------

    def install_app(self, apk_path: str) -> bool:
        """
        Pre-install an APK on the device.

        Default implementation is a no-op (many providers install via capabilities).
        Returns True if installed, False if skipped.
        """
        return False

    # ------------------------------------------------------------------
    # Artifact retrieval
    # ------------------------------------------------------------------

    def get_video(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """
        Download session recording.

        Returns local file path if successful, None if not available.
        """
        return None

    def get_logs(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """
        Download device/Appium logs.

        Returns local file path if successful, None if not available.
        """
        return None

    def get_network_logs(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """Download network HAR logs if available."""
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _require_connected(self) -> None:
        if not self._connected:
            raise RuntimeError(
                f"{self.__class__.__name__} is not connected. Call connect() first."
            )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"connected={self._connected}, "
            f"provider={self.config.provider.provider_type})"
        )
