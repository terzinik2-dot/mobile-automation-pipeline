"""
Local ADB Device Provider

Connects to a local Android device or emulator via ADB.
Starts and manages a local Appium server process.

Ideal for:
- Development and debugging
- Demo recordings
- CI with emulators

Prerequisites:
- Android SDK / ADB installed
- Appium 2.x installed globally (npm install -g appium)
- appium driver install uiautomator2
- Physical device in developer mode OR running emulator
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from providers.base import DeviceProvider


class LocalDeviceProvider(DeviceProvider):
    """
    Local Android device provider.

    Manages a local Appium server process and connects via ADB.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self._appium_process: Optional[subprocess.Popen] = None
        self._appium_host: str = "127.0.0.1"
        self._appium_port: int = 4723
        self._device_serial: Optional[str] = None
        self._device_info_cache: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Detect connected device and start Appium server."""
        pc = self.config.provider
        self._appium_host = pc.appium_host or "127.0.0.1"
        self._appium_port = pc.appium_port or 4723

        # 1. Find ADB
        adb = self._find_adb()
        if not adb:
            raise ConnectionError(
                "ADB not found. Install Android SDK or set ADB_PATH env var."
            )

        # 2. Find connected device
        self._device_serial = (
            self.config.device.udid
            or os.environ.get("LOCAL_DEVICE_UDID")
            or self._detect_device(adb)
        )
        if not self._device_serial:
            raise ConnectionError(
                "No Android device detected. Connect a device or start an emulator."
            )

        logger.info(f"[LocalDevice] Using device: {self._device_serial}")

        # 3. Start Appium server if not already running
        if not self._is_appium_running():
            self._start_appium(adb)
        else:
            logger.info(
                f"[LocalDevice] Appium already running on "
                f"{self._appium_host}:{self._appium_port}"
            )

        self._connected = True
        logger.info("[LocalDevice] Connected")

    def disconnect(self) -> None:
        """Stop the Appium server if we started it."""
        if not self._connected:
            return
        if self._appium_process and self._appium_process.poll() is None:
            logger.info("[LocalDevice] Stopping Appium server")
            try:
                self._appium_process.send_signal(signal.SIGTERM)
                self._appium_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._appium_process.kill()
            except Exception as e:
                logger.warning(f"[LocalDevice] Error stopping Appium: {e}")
        self._connected = False

    # ------------------------------------------------------------------
    # Appium integration
    # ------------------------------------------------------------------

    def get_appium_url(self) -> str:
        return f"http://{self._appium_host}:{self._appium_port}"

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    def get_device_info(self) -> dict[str, Any]:
        if self._device_info_cache:
            return self._device_info_cache

        adb = self._find_adb()
        if not adb or not self._device_serial:
            return {"provider_name": "Local ADB", "udid": self._device_serial}

        def adb_getprop(prop: str) -> str:
            try:
                result = subprocess.run(
                    [adb, "-s", self._device_serial, "shell", "getprop", prop],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return result.stdout.strip()
            except Exception:
                return "unknown"

        info = {
            "provider_name": "Local ADB",
            "udid": self._device_serial,
            "model": adb_getprop("ro.product.model"),
            "manufacturer": adb_getprop("ro.product.manufacturer"),
            "os_version": adb_getprop("ro.build.version.release"),
            "api_level": adb_getprop("ro.build.version.sdk"),
            "screen_resolution": self._get_screen_resolution(adb),
            "appium_url": self.get_appium_url(),
        }
        self._device_info_cache = info
        return info

    # ------------------------------------------------------------------
    # App management
    # ------------------------------------------------------------------

    def install_app(self, apk_path: str) -> bool:
        """Install APK directly via ADB."""
        adb = self._find_adb()
        if not adb:
            return False
        if not Path(apk_path).exists():
            logger.error(f"[LocalDevice] APK not found: {apk_path}")
            return False

        logger.info(f"[LocalDevice] Installing APK: {apk_path}")
        result = subprocess.run(
            [adb, "-s", self._device_serial, "install", "-r", "-g", apk_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("[LocalDevice] APK installed successfully")
            return True
        else:
            logger.error(
                f"[LocalDevice] APK install failed: {result.stderr}"
            )
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
        For local devices, video is recorded via screenrecord or Appium's
        built-in recording (started/stopped by the Appium driver layer).
        This returns the path if a recording exists.
        """
        expected = Path(output_dir) / "session_recording.mp4"
        if expected.exists():
            return str(expected)
        return None

    def get_logs(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """Save logcat output to file."""
        adb = self._find_adb()
        if not adb or not self._device_serial:
            return None
        try:
            output_path = Path(output_dir) / "logcat.log"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [adb, "-s", self._device_serial, "logcat", "-d", "-v", "threadtime"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output_path.write_text(result.stdout, encoding="utf-8")
            return str(output_path)
        except Exception as e:
            logger.error(f"[LocalDevice] Could not capture logcat: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_adb(self) -> Optional[str]:
        """Locate the ADB binary."""
        env_adb = os.environ.get("ADB_PATH")
        if env_adb and Path(env_adb).exists():
            return env_adb
        # Check common locations
        for candidate in ["adb", "/usr/local/bin/adb", "/opt/android-sdk/platform-tools/adb"]:
            found = shutil.which(candidate)
            if found:
                return found
        return None

    def _detect_device(self, adb: str) -> Optional[str]:
        """Return serial of first connected/online device."""
        try:
            result = subprocess.run(
                [adb, "devices"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = result.stdout.strip().splitlines()
            for line in lines[1:]:  # Skip "List of devices attached"
                parts = line.split("\t")
                if len(parts) >= 2 and parts[1].strip() == "device":
                    return parts[0].strip()
        except Exception as e:
            logger.error(f"[LocalDevice] ADB device detection failed: {e}")
        return None

    def _is_appium_running(self) -> bool:
        """Check if an Appium server is already listening on the port."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            return s.connect_ex((self._appium_host, self._appium_port)) == 0

    def _start_appium(self, adb: str) -> None:
        """Start a local Appium server process."""
        appium_bin = shutil.which("appium")
        if not appium_bin:
            raise ConnectionError(
                "Appium not found. Install with: npm install -g appium && "
                "appium driver install uiautomator2"
            )

        log_path = Path("./artifacts/appium_server.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            appium_bin,
            "--address", self._appium_host,
            "--port", str(self._appium_port),
            "--log", str(log_path),
            "--log-timestamp",
            "--log-no-colors",
        ]

        logger.info(f"[LocalDevice] Starting Appium: {' '.join(cmd)}")
        self._appium_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait for Appium to be ready
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._is_appium_running():
                logger.info(
                    f"[LocalDevice] Appium started on "
                    f"{self._appium_host}:{self._appium_port}"
                )
                return
            time.sleep(0.5)

        raise ConnectionError(
            f"Appium did not start within 30s on {self._appium_host}:{self._appium_port}"
        )

    def _get_screen_resolution(self, adb: str) -> str:
        """Get device screen resolution via wm size."""
        try:
            result = subprocess.run(
                [adb, "-s", self._device_serial, "shell", "wm", "size"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Output: "Physical size: 1080x2400"
            output = result.stdout.strip()
            if ":" in output:
                return output.split(":", 1)[1].strip()
        except Exception:
            pass
        return "unknown"
