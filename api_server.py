"""
FastAPI Server — Bridge between Next.js dashboard and the Python orchestrator.

Endpoints:
  POST /api/v1/scenarios/run           Start a new scenario run
  GET  /api/v1/runs                    List all runs (paginated)
  GET  /api/v1/runs/{id}              Get run details
  GET  /api/v1/runs/{id}/artifacts     List run artifacts
  GET  /api/v1/providers               List available providers
  WS   /ws/runs/{id}                   Real-time status via WebSocket

Data store: SQLite via SQLAlchemy (aiosqlite for async).
Runs are stored in JSON columns for schema flexibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import uvicorn
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String, Text, select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from orchestrator.config import get_settings
from orchestrator.models import (
    DeviceConfig,
    ProviderConfig,
    ProviderType,
    RunConfig,
    RunResult,
    RunStatus,
)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

settings = get_settings()


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    """SQLAlchemy ORM model for persisting run data."""
    __tablename__ = "runs"

    run_id = Column(String, primary_key=True)
    status = Column(String, default=RunStatus.PENDING.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    config_json = Column(Text)    # RunConfig serialized
    result_json = Column(Text)    # RunResult serialized (null until complete)
    error = Column(Text, nullable=True)


# Force SQLite — ignore any DATABASE_URL env var that may point to PostgreSQL
_db_url = "sqlite+aiosqlite:///./pipeline.db"
engine = create_async_engine(
    _db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"Database ready: {settings.database_url}")
    yield
    await engine.dispose()


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages active WebSocket connections, keyed by run_id."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(run_id, None)

    async def broadcast(self, run_id: str, message: dict) -> None:
        conns = self._connections.get(run_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(run_id, ws)


ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------

class StartRunRequest(BaseModel):
    provider: str = "local"
    google_email: str = ""
    google_password: str = ""
    google_pay_test_mode: bool = True
    device_name: str = "Android Emulator"
    platform_version: str = "13.0"
    udid: Optional[str] = None
    browserstack_username: Optional[str] = None
    browserstack_access_key: Optional[str] = None
    scenarios: list[str] = [
        "google_login",
        "play_store_install",
        "mlbb_registration",
        "google_pay_purchase",
    ]
    total_budget_seconds: int = 180


class RunSummary(BaseModel):
    run_id: str
    status: str
    created_at: str
    provider: str
    scenarios: list[str]
    error: Optional[str] = None
    timing_total_ms: Optional[float] = None


class ProviderInfo(BaseModel):
    provider_id: str
    name: str
    description: str
    configured: bool
    required_env_vars: list[str]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mobile Automation Pipeline API",
    description="REST API and WebSocket bridge for the mobile automation pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Background task: run the automation pipeline
# ---------------------------------------------------------------------------

async def run_pipeline_task(run_id: str, config: RunConfig) -> None:
    """Background task that executes the scenario orchestrator."""
    from orchestrator.engine import ScenarioOrchestrator

    async with AsyncSessionLocal() as db:
        # Update status to RUNNING
        record = await db.get(RunRecord, run_id)
        if record:
            record.status = RunStatus.RUNNING.value
            record.updated_at = datetime.utcnow()
            await db.commit()

    # Notify connected WebSocket clients
    await ws_manager.broadcast(run_id, {
        "event": "status_change",
        "run_id": run_id,
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    try:
        orchestrator = ScenarioOrchestrator(config)

        # Patch broadcast into orchestrator for real-time updates
        # (In production, use a proper event bus)
        loop = asyncio.get_event_loop()

        def on_step_update(step_data: dict) -> None:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(run_id, {
                    "event": "step_update",
                    "run_id": run_id,
                    **step_data,
                }),
                loop,
            )

        result: RunResult = await orchestrator.run_async()

        # Persist result
        async with AsyncSessionLocal() as db:
            record = await db.get(RunRecord, run_id)
            if record:
                record.status = result.status.value
                record.result_json = result.model_dump_json()
                record.updated_at = datetime.utcnow()
                record.error = result.error_message
                await db.commit()

        # Notify completion
        await ws_manager.broadcast(run_id, {
            "event": "run_complete",
            "run_id": run_id,
            "status": result.status.value,
            "timing_total_ms": result.timing.total_ms,
            "success_rate": result.success_rate,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as e:
        logger.exception(f"[API] Pipeline task failed for run {run_id}: {e}")
        async with AsyncSessionLocal() as db:
            record = await db.get(RunRecord, run_id)
            if record:
                record.status = RunStatus.FAILED.value
                record.error = str(e)
                record.updated_at = datetime.utcnow()
                await db.commit()
        await ws_manager.broadcast(run_id, {
            "event": "run_failed",
            "run_id": run_id,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/v1/scenarios/run", status_code=202, response_model=None)
async def start_run(
    request: StartRunRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Start a new pipeline run asynchronously.
    Returns immediately with a run_id for polling/WebSocket.
    """
    async with AsyncSessionLocal() as session:
        run_id = str(uuid.uuid4())

        # Build RunConfig from request
        try:
            provider_type = ProviderType(request.provider)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider: {request.provider}. "
                       f"Valid: {[p.value for p in ProviderType]}",
            )

        config = RunConfig(
            run_id=run_id,
            device=DeviceConfig(
                provider=provider_type,
                device_name=request.device_name,
                platform_version=request.platform_version,
                udid=request.udid,
            ),
            provider=ProviderConfig(
                provider_type=provider_type,
                bs_username=request.browserstack_username,
                bs_access_key=request.browserstack_access_key,
            ),
            google_email=request.google_email,
            google_password=request.google_password,
            google_pay_test_mode=request.google_pay_test_mode,
            scenarios=request.scenarios,
            total_budget_seconds=request.total_budget_seconds,
        )

        # Persist initial record
        record = RunRecord(
            run_id=run_id,
            status=RunStatus.PENDING.value,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            config_json=config.model_dump_json(),
        )
        session.add(record)
        await session.commit()

    # Schedule background task
    background_tasks.add_task(run_pipeline_task, run_id, config)

    return {
        "run_id": run_id,
        "status": "pending",
        "message": "Run scheduled",
        "ws_url": f"/ws/runs/{run_id}",
    }


@app.get("/api/v1/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
) -> dict:
    """List all pipeline runs with pagination."""
    async with AsyncSessionLocal() as session:
        stmt = select(RunRecord).order_by(RunRecord.created_at.desc())
        if status:
            stmt = stmt.where(RunRecord.status == status)

        count_stmt = select(func.count()).select_from(RunRecord)
        if status:
            count_stmt = count_stmt.where(RunRecord.status == status)

        total = (await session.execute(count_stmt)).scalar_one()
        result = await session.execute(stmt.offset(offset).limit(limit))
        records = result.scalars().all()

    runs = []
    for r in records:
        config_data = json.loads(r.config_json) if r.config_json else {}
        timing = None
        if r.result_json:
            try:
                result_data = json.loads(r.result_json)
                timing = result_data.get("timing", {}).get("total_ms")
            except Exception:
                pass

        runs.append({
            "run_id": r.run_id,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "provider": config_data.get("provider", {}).get("provider_type", "unknown"),
            "scenarios": config_data.get("scenarios", []),
            "error": r.error,
            "timing_total_ms": timing,
        })

    return {"total": total, "offset": offset, "limit": limit, "runs": runs}


@app.get("/api/v1/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """Get full details for a specific run."""
    async with AsyncSessionLocal() as session:
        record = await session.get(RunRecord, run_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    config_data = json.loads(record.config_json) if record.config_json else {}
    result_data = json.loads(record.result_json) if record.result_json else None

    return {
        "run_id": record.run_id,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "config": config_data,
        "result": result_data,
        "error": record.error,
    }


@app.get("/api/v1/runs/{run_id}/artifacts")
async def get_run_artifacts(run_id: str) -> dict:
    """List artifacts produced by a run."""
    async with AsyncSessionLocal() as session:
        record = await session.get(RunRecord, run_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if not record.result_json:
        return {"run_id": run_id, "artifacts": []}

    try:
        result_data = json.loads(record.result_json)
        artifacts = []
        for scenario in result_data.get("scenarios", []):
            for step in scenario.get("steps", []):
                for artifact in step.get("artifacts", []):
                    # Check file still exists
                    file_path = artifact.get("file_path", "")
                    exists = Path(file_path).exists() if file_path else False
                    artifacts.append({
                        **artifact,
                        "exists": exists,
                        "download_url": f"/api/v1/artifacts/download?path={file_path}" if exists else None,
                    })
        # Also add video/logs from run level
        if result_data.get("video_url"):
            artifacts.append({
                "artifact_type": "video",
                "file_path": result_data["video_url"],
                "description": "Session recording",
                "exists": Path(result_data["video_url"]).exists(),
            })
    except Exception as e:
        logger.error(f"[API] Error parsing artifacts for {run_id}: {e}")
        artifacts = []

    return {"run_id": run_id, "artifacts": artifacts}


@app.get("/api/v1/artifacts/download")
async def download_artifact(path: str) -> FileResponse:
    """Download an artifact file."""
    artifact_path = Path(path)
    # Security: only allow files within the artifacts directory
    artifacts_root = Path(settings.artifacts_dir).resolve()
    try:
        resolved = artifact_path.resolve()
        resolved.relative_to(artifacts_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(str(artifact_path))


@app.get("/api/v1/providers")
async def list_providers() -> dict:
    """List available device farm providers and their configuration status."""
    providers = [
        ProviderInfo(
            provider_id="local",
            name="Local ADB Device",
            description="Connect to a local Android device or emulator via ADB",
            configured=True,  # Always available
            required_env_vars=["ADB_PATH", "LOCAL_APPIUM_PORT"],
        ),
        ProviderInfo(
            provider_id="browserstack",
            name="BrowserStack App Automate",
            description="Cloud-based real device testing via BrowserStack",
            configured=bool(
                os.environ.get("BROWSERSTACK_USERNAME")
                and os.environ.get("BROWSERSTACK_ACCESS_KEY")
            ),
            required_env_vars=["BROWSERSTACK_USERNAME", "BROWSERSTACK_ACCESS_KEY"],
        ),
        ProviderInfo(
            provider_id="aws_device_farm",
            name="AWS Device Farm",
            description="AWS cloud device testing with real Android devices",
            configured=bool(
                os.environ.get("AWS_ACCESS_KEY_ID")
                and os.environ.get("AWS_SECRET_ACCESS_KEY")
                and os.environ.get("AWS_DEVICE_FARM_PROJECT_ARN")
            ),
            required_env_vars=[
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_DEVICE_FARM_PROJECT_ARN",
                "AWS_DEVICE_FARM_DEVICE_POOL_ARN",
            ],
        ),
    ]
    return {"providers": [p.model_dump() for p in providers]}


@app.delete("/api/v1/runs/{run_id}")
async def delete_run(run_id: str) -> dict:
    """Delete a run record (does not delete artifact files)."""
    async with AsyncSessionLocal() as session:
        record = await session.get(RunRecord, run_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        await session.delete(record)
        await session.commit()
    return {"deleted": run_id}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/runs/{run_id}")
async def websocket_run_status(websocket: WebSocket, run_id: str):
    """
    WebSocket for real-time run status updates.

    Clients receive:
    - status_change: run status changed
    - step_update: individual step completed
    - run_complete: run finished
    - run_failed: run failed with error

    Also sends the current run state immediately on connect.
    """
    await ws_manager.connect(run_id, websocket)
    try:
        # Send current state on connect
        async with AsyncSessionLocal() as session:
            record = await session.get(RunRecord, run_id)
        if record:
            await websocket.send_json({
                "event": "initial_state",
                "run_id": run_id,
                "status": record.status,
                "config": json.loads(record.config_json) if record.config_json else {},
                "result": json.loads(record.result_json) if record.result_json else None,
            })
        else:
            await websocket.send_json({
                "event": "error",
                "message": f"Run {run_id} not found",
            })
            return

        # Keep connection alive and handle client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(run_id, websocket)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info",
    )
