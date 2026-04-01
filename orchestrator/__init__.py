"""
Mobile Automation Pipeline — Orchestrator Package

Manages scenario runs end-to-end: provider connection, Appium session lifecycle,
scenario sequencing, time budgeting, and artifact collection.
"""

from orchestrator.engine import ScenarioOrchestrator
from orchestrator.models import (
    RunConfig,
    RunResult,
    StepResult,
    RunStatus,
    StepStatus,
)
from orchestrator.time_budget import TimeBudgetManager

__all__ = [
    "ScenarioOrchestrator",
    "RunConfig",
    "RunResult",
    "StepResult",
    "RunStatus",
    "StepStatus",
    "TimeBudgetManager",
]
