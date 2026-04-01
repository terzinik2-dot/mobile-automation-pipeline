"""
BrowserStack App Automate Provider

Wraps the BrowserStack REST API for:
- Uploading APK files
- Starting/stopping sessions
- Fetching video recordings, device logs, and network logs

API reference: https://www.browserstack.com/app-automate/rest-api
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

import requests
from loguru import logger
from requests.auth import HTTPBasicAuth

from providers.base import DeviceProvider


BROWSERSTACK_UPLOAD_URL = "https://api-cloud.browserstack.com/app-automate/upload"
BROWSERSTACK_HUB_URL = "https://hub-cloud.browserstack.com/wd/hub"
BROWSERSTACK_SESSION_BASE = "https://api.browserstack.com/app-automate/sessions"
BROWSERSTACK_BUILDS_URL = "https://api.browserstack.com/app-automate/builds.json"


class BrowserStackProvider(DeviceProvider):
    """
    BrowserStack App Automate device provider.

    Authentication is via HTTP Basic Auth using username + access key.
    The Appium session capabilities include bstack:options with auth details.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self._session_id: Optional[str] = None
        self._app_url: Optional[str] = None
        self._auth: Optional[HTTPBasicAuth] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Validate BrowserStack credentials by hitting the plans API."""
        pc = self.config.provider
        if not pc.bs_username or not pc.bs_access_key:
            raise ConnectionError(
                "BrowserStack requires bs_username and bs_access_key in ProviderConfig"
            )

        self._auth = HTTPBasicAuth(pc.bs_username, pc.bs_access_key)

        # Validate credentials with a lightweight API call
        resp = requests.get(
            "https://api.browserstack.com/app-automate/plan.json",
            auth=self._auth,
            timeout=15,
        )
        if resp.status_code == 401:
            raise ConnectionError(
                "BrowserStack authentication failed — check username/access key"
            )
        resp.raise_for_status()

        plan = resp.json()
        logger.info(
            f"[BrowserStack] Connected. Plan: {plan.get('automate_plan', 'unknown')}, "
            f"queued: {plan.get('queued_sessions', 0)}, "
            f"max parallel: {plan.get('parallel_sessions_max_allowed', 0)}"
        )

        # Pre-upload app if we have a local APK path
        local_apk = getattr(self.config, "local_apk_path", None)
        existing_url = self.config.provider.bs_username and getattr(
            self.config, "browserstack_app_url", None
        )
        if local_apk and not existing_url:
            self._app_url = self._upload_app(local_apk)
        elif existing_url:
            self._app_url = existing_url
            logger.info(f"[BrowserStack] Using existing app URL: {self._app_url}")

        self._connected = True

    def disconnect(self) -> None:
        """Mark BrowserStack session as complete (session auto-closes when driver quits)."""
        if not self._connected:
            return
        if self._session_id:
            try:
                self._update_session_status("passed", "Pipeline completed")
            except Exception as e:
                logger.warning(f"[BrowserStack] Could not update session status: {e}")
        self._connected = False
        logger.info("[BrowserStack] Disconnected")

    # ------------------------------------------------------------------
    # Appium integration
    # ------------------------------------------------------------------

    def get_appium_url(self) -> str:
        return BROWSERSTACK_HUB_URL

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    def get_device_info(self) -> dict[str, Any]:
        device_name = (
            self.config.device.browserstack_device
            or self.config.device.device_name
        )
        return {
            "provider_name": "BrowserStack",
            "model": device_name,
            "os_version": self.config.device.platform_version,
            "session_url": (
                f"https://app-automate.browserstack.com/builds/"
                f"(session: {self._session_id or 'unknown'})"
            ),
        }

    # ------------------------------------------------------------------
    # App management
    # ------------------------------------------------------------------

    def install_app(self, apk_path: str) -> bool:
        """Upload APK to BrowserStack and store the app URL in capabilities."""
        self._app_url = self._upload_app(apk_path)
        return True

    def _upload_app(self, apk_path: str) -> str:
        """Upload an APK and return the bs:// app URL."""
        self._require_connected()
        if not Path(apk_path).exists():
            raise FileNotFoundError(f"APK not found: {apk_path}")

        logger.info(f"[BrowserStack] Uploading APK: {apk_path}")
        with open(apk_path, "rb") as f:
            resp = requests.post(
                BROWSERSTACK_UPLOAD_URL,
                files={"file": (Path(apk_path).name, f, "application/vnd.android.package-archive")},
                auth=self._auth,
                timeout=120,
            )
        resp.raise_for_status()
        data = resp.json()
        app_url = data["app_url"]
        logger.info(f"[BrowserStack] APK uploaded: {app_url}")
        return app_url

    # ------------------------------------------------------------------
    # Artifact retrieval
    # ------------------------------------------------------------------

    def get_video(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """Download session video recording."""
        sid = session_id or self._session_id
        if not sid:
            logger.warning("[BrowserStack] No session ID — cannot fetch video")
            return None
        self._require_connected()

        try:
            # Poll for video to become available (BrowserStack processes it async)
            video_url = self._poll_for_video(sid, max_wait=60)
            if not video_url:
                return None

            output_path = Path(output_dir) / f"session_{sid[:8]}_recording.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info(f"[BrowserStack] Downloading video to {output_path}")
            resp = requests.get(video_url, stream=True, timeout=120)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"[BrowserStack] Video saved: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"[BrowserStack] Video download failed: {e}")
            return None

    def get_logs(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """Download device logs."""
        sid = session_id or self._session_id
        if not sid:
            return None
        self._require_connected()

        try:
            resp = requests.get(
                f"{BROWSERSTACK_SESSION_BASE}/{sid}/devicelogs",
                auth=self._auth,
                timeout=30,
            )
            resp.raise_for_status()
            output_path = Path(output_dir) / f"session_{sid[:8]}_device.log"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(resp.text, encoding="utf-8")
            return str(output_path)
        except Exception as e:
            logger.error(f"[BrowserStack] Logs download failed: {e}")
            return None

    def get_network_logs(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """Download network HAR logs."""
        sid = session_id or self._session_id
        if not sid:
            return None
        self._require_connected()

        try:
            resp = requests.get(
                f"{BROWSERSTACK_SESSION_BASE}/{sid}/networklogs",
                auth=self._auth,
                timeout=30,
            )
            resp.raise_for_status()
            output_path = Path(output_dir) / f"session_{sid[:8]}_network.har"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(resp.text, encoding="utf-8")
            return str(output_path)
        except Exception as e:
            logger.error(f"[BrowserStack] Network logs download failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Session management helpers
    # ------------------------------------------------------------------

    def set_session_id(self, session_id: str) -> None:
        """Called by the Appium driver once the session is created."""
        self._session_id = session_id
        logger.info(f"[BrowserStack] Session ID: {session_id}")

    def _update_session_status(self, status: str, reason: str = "") -> None:
        """Mark the BrowserStack session as passed/failed."""
        if not self._session_id:
            return
        payload = {"status": status, "reason": reason}
        requests.put(
            f"{BROWSERSTACK_SESSION_BASE}/{self._session_id}.json",
            json=payload,
            auth=self._auth,
            timeout=10,
        )

    def _poll_for_video(self, session_id: str, max_wait: int = 60) -> Optional[str]:
        """Poll until session video URL becomes available."""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            try:
                resp = requests.get(
                    f"{BROWSERSTACK_SESSION_BASE}/{session_id}.json",
                    auth=self._auth,
                    timeout=10,
                )
                resp.raise_for_status()
                session_data = resp.json().get("automation_session", {})
                video_url = session_data.get("video_url")
                if video_url:
                    return video_url
            except Exception as e:
                logger.debug(f"[BrowserStack] Polling video: {e}")
            time.sleep(3)
        logger.warning(f"[BrowserStack] Video not available after {max_wait}s")
        return None
