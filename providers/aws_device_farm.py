"""
AWS Device Farm Provider

Integrates with AWS Device Farm for cloud-based Android testing.
Uses boto3 for all API calls.

Key AWS Device Farm concepts:
- Project: groups tests
- Device Pool: defines which devices to use
- Upload: APK/test package upload
- Run: a test execution
- Job: a run on a specific device
- Suite/Test: finer-grained within a job

For Appium, we use the "APPIUM_PYTHON" test type with a remote connection.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from loguru import logger

from providers.base import DeviceProvider


class AWSDeviceFarmProvider(DeviceProvider):
    """
    AWS Device Farm device provider.

    Note: AWS Device Farm Appium tests run as self-contained test packages.
    For interactive Appium access (our use case), we use the
    'REMOTE_ACCESS_RECORDING' feature and the generated WebSocket URL.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self._client = None
        self._run_arn: Optional[str] = None
        self._job_arn: Optional[str] = None
        self._remote_access_session_arn: Optional[str] = None
        self._appium_endpoint: Optional[str] = None
        self._device_arn: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Initialize boto3 client and validate credentials."""
        import boto3
        from botocore.exceptions import NoCredentialsError, ClientError

        pc = self.config.provider
        if not pc.aws_access_key_id or not pc.aws_secret_access_key:
            raise ConnectionError(
                "AWS Device Farm requires aws_access_key_id and aws_secret_access_key"
            )

        session = boto3.Session(
            aws_access_key_id=pc.aws_access_key_id,
            aws_secret_access_key=pc.aws_secret_access_key,
            region_name=pc.aws_region or "us-west-2",
        )

        # Device Farm is a global service but only available in us-west-2
        self._client = session.client("devicefarm", region_name="us-west-2")

        try:
            # Validate credentials by listing projects
            response = self._client.list_projects()
            projects = response.get("projects", [])
            logger.info(
                f"[AWSDeviceFarm] Connected. Projects available: {len(projects)}"
            )
        except NoCredentialsError as e:
            raise ConnectionError(f"AWS credentials invalid: {e}") from e
        except ClientError as e:
            raise ConnectionError(f"AWS Device Farm API error: {e}") from e

        # Start a remote access session for interactive Appium
        self._start_remote_access_session()
        self._connected = True

    def disconnect(self) -> None:
        """Stop the remote access session."""
        if not self._connected:
            return
        if self._remote_access_session_arn and self._client:
            try:
                self._client.stop_remote_access_session(
                    arn=self._remote_access_session_arn
                )
                logger.info("[AWSDeviceFarm] Remote access session stopped")
            except Exception as e:
                logger.warning(f"[AWSDeviceFarm] Error stopping session: {e}")
        self._connected = False

    # ------------------------------------------------------------------
    # Appium integration
    # ------------------------------------------------------------------

    def get_appium_url(self) -> str:
        """Return the Appium endpoint for the remote access session."""
        if self._appium_endpoint:
            return self._appium_endpoint
        # Fallback: construct from known pattern
        return "https://devicefarm.us-west-2.amazonaws.com/wd/hub"

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    def get_device_info(self) -> dict[str, Any]:
        if not self._device_arn or not self._client:
            return {"provider_name": "AWS Device Farm"}
        try:
            response = self._client.get_device(arn=self._device_arn)
            device = response.get("device", {})
            return {
                "provider_name": "AWS Device Farm",
                "model": device.get("name", "Unknown"),
                "manufacturer": device.get("manufacturer", "Unknown"),
                "os_version": device.get("os", "Unknown"),
                "screen_resolution": (
                    f"{device.get('resolution', {}).get('width', '?')}x"
                    f"{device.get('resolution', {}).get('height', '?')}"
                ),
                "device_arn": self._device_arn,
                "session_arn": self._remote_access_session_arn,
            }
        except Exception as e:
            logger.warning(f"[AWSDeviceFarm] Could not fetch device info: {e}")
            return {"provider_name": "AWS Device Farm"}

    # ------------------------------------------------------------------
    # App management
    # ------------------------------------------------------------------

    def install_app(self, apk_path: str) -> bool:
        """Upload an APK to AWS Device Farm."""
        if not self._client:
            return False
        pc = self.config.provider
        if not pc.aws_project_arn:
            logger.warning("[AWSDeviceFarm] No project ARN configured — cannot upload APK")
            return False

        try:
            apk_name = Path(apk_path).name
            logger.info(f"[AWSDeviceFarm] Creating upload slot for {apk_name}")

            # Step 1: Create upload
            response = self._client.create_upload(
                projectArn=pc.aws_project_arn,
                name=apk_name,
                type="ANDROID_APP",
            )
            upload = response["upload"]
            upload_url = upload["url"]
            upload_arn = upload["arn"]

            # Step 2: PUT file to the pre-signed URL
            import requests
            with open(apk_path, "rb") as f:
                put_resp = requests.put(
                    upload_url,
                    data=f,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=120,
                )
            put_resp.raise_for_status()

            # Step 3: Wait for processing
            self._wait_for_upload(upload_arn)
            logger.info(f"[AWSDeviceFarm] APK uploaded: {upload_arn}")
            return True
        except Exception as e:
            logger.error(f"[AWSDeviceFarm] APK upload failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Artifact retrieval
    # ------------------------------------------------------------------

    def get_video(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """Download session video from AWS Device Farm."""
        if not self._remote_access_session_arn or not self._client:
            return None
        try:
            response = self._client.list_artifacts(
                arn=self._remote_access_session_arn,
                type="FILE",
            )
            artifacts = response.get("artifacts", [])
            video = next(
                (a for a in artifacts if a.get("type") == "VIDEO"), None
            )
            if not video:
                logger.info("[AWSDeviceFarm] No video artifact found")
                return None

            video_url = video.get("url")
            output_path = Path(output_dir) / f"aws_session_recording.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            import requests
            resp = requests.get(video_url, stream=True, timeout=120)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return str(output_path)
        except Exception as e:
            logger.error(f"[AWSDeviceFarm] Video download failed: {e}")
            return None

    def get_logs(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "./artifacts",
    ) -> Optional[str]:
        """Download device logs from AWS Device Farm."""
        if not self._remote_access_session_arn or not self._client:
            return None
        try:
            response = self._client.list_artifacts(
                arn=self._remote_access_session_arn,
                type="LOG",
            )
            artifacts = response.get("artifacts", [])
            log = next(
                (a for a in artifacts if "LOGCAT" in a.get("type", "").upper()), None
            )
            if not log:
                return None

            log_url = log.get("url")
            output_path = Path(output_dir) / "aws_device.log"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            import requests
            resp = requests.get(log_url, stream=True, timeout=30)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=4096):
                    f.write(chunk)
            return str(output_path)
        except Exception as e:
            logger.error(f"[AWSDeviceFarm] Logs download failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_remote_access_session(self) -> None:
        """Create a remote access session to get an interactive Appium URL."""
        pc = self.config.provider
        if not pc.aws_project_arn:
            raise ConnectionError(
                "aws_project_arn is required for AWS Device Farm"
            )

        device_pool_arn = pc.aws_device_pool_arn
        if not device_pool_arn:
            # Auto-select: use first compatible device pool
            device_pool_arn = self._find_android_device_pool(pc.aws_project_arn)

        logger.info(f"[AWSDeviceFarm] Starting remote access session ...")
        response = self._client.create_remote_access_session(
            projectArn=pc.aws_project_arn,
            deviceArn=device_pool_arn,
            instanceArn=None,
            configuration={
                "billingMethod": "METERED",
            },
        )
        session = response["remoteAccessSession"]
        self._remote_access_session_arn = session["arn"]
        self._device_arn = session.get("device", {}).get("arn")

        # Wait for the session to become available
        endpoint = self._wait_for_session(self._remote_access_session_arn)
        if endpoint:
            self._appium_endpoint = endpoint
            logger.info(f"[AWSDeviceFarm] Session ready: {endpoint}")
        else:
            raise ConnectionError("Remote access session did not start in time")

    def _wait_for_session(self, session_arn: str, timeout: int = 120) -> Optional[str]:
        """Poll until the remote access session is RUNNING."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = self._client.get_remote_access_session(arn=session_arn)
            session = resp["remoteAccessSession"]
            status = session.get("status", "")
            logger.debug(f"[AWSDeviceFarm] Session status: {status}")

            if status == "RUNNING":
                endpoint = session.get("endpoint", "")
                return endpoint or None
            elif status in ("ERRORED", "FAILED", "STOPPED"):
                raise ConnectionError(
                    f"Remote access session entered terminal state: {status}"
                )
            time.sleep(5)
        return None

    def _wait_for_upload(self, upload_arn: str, timeout: int = 120) -> None:
        """Poll until an upload is in SUCCEEDED state."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = self._client.get_upload(arn=upload_arn)
            status = resp["upload"].get("status", "")
            if status == "SUCCEEDED":
                return
            elif status in ("FAILED",):
                raise RuntimeError(f"Upload failed: {resp['upload'].get('message', '')}")
            time.sleep(3)
        raise TimeoutError(f"Upload {upload_arn} did not complete within {timeout}s")

    def _find_android_device_pool(self, project_arn: str) -> str:
        """Find the first available Android device pool for a project."""
        response = self._client.list_device_pools(arn=project_arn, type="PRIVATE")
        pools = response.get("devicePools", [])
        android_pool = next(
            (p for p in pools if "Android" in p.get("name", "")), None
        )
        if android_pool:
            return android_pool["arn"]
        if pools:
            return pools[0]["arn"]
        raise ConnectionError("No device pools found in AWS Device Farm project")
