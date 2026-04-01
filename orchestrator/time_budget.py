"""
Time Budget Manager

Enforces the 3-minute (180-second) total time budget across all pipeline steps.
Each phase has a pre-allocated budget; overruns steal from a shared reserve pool.
The manager provides per-step deadlines, elapsed tracking, and a final report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Default per-step budgets (seconds)
# These sum to 180s with a small reserve for overhead.
# ---------------------------------------------------------------------------
DEFAULT_STEP_BUDGETS: dict[str, float] = {
    "device_connect":    30.0,
    "google_login":      30.0,
    "play_store_install": 40.0,
    "mlbb_registration": 40.0,
    "google_pay_purchase": 30.0,
    "cleanup":           10.0,
    # Reserve: 180 - 180 = 0 explicit, but we cap total at 180
}

TOTAL_BUDGET_SECONDS = 180.0


@dataclass
class StepTimingRecord:
    """Timing record for one step."""
    name: str
    allocated_seconds: float
    started_at: Optional[float] = None   # time.monotonic()
    ended_at: Optional[float] = None
    status: str = "pending"              # pending | running | completed | failed | timeout

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return end - self.started_at

    @property
    def used_fraction(self) -> float:
        if self.allocated_seconds <= 0:
            return 1.0
        return self.elapsed_seconds / self.allocated_seconds

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.allocated_seconds - self.elapsed_seconds)

    @property
    def overrun_seconds(self) -> float:
        return max(0.0, self.elapsed_seconds - self.allocated_seconds)


class TimeBudgetManager:
    """
    Central time budget manager for the full pipeline run.

    Usage:
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()

        budget.start_step("google_login")
        # ... do work ...
        if budget.is_step_expired("google_login"):
            raise TimeoutError("google_login timed out")
        budget.end_step("google_login", status="completed")

        report = budget.get_report()
    """

    def __init__(
        self,
        total_seconds: float = TOTAL_BUDGET_SECONDS,
        step_budgets: Optional[dict[str, float]] = None,
    ) -> None:
        self.total_seconds = total_seconds
        self._step_budgets: dict[str, float] = dict(
            step_budgets or DEFAULT_STEP_BUDGETS
        )
        self._run_start: Optional[float] = None
        self._step_records: dict[str, StepTimingRecord] = {}
        self._current_step: Optional[str] = None

    # ------------------------------------------------------------------
    # Run-level controls
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the overall run clock. Idempotent — first call wins."""
        if self._run_start is None:
            self._run_start = time.monotonic()
        logger.info(
            f"TimeBudgetManager started — total budget: {self.total_seconds}s"
        )

    def is_expired(self) -> bool:
        """Return True if the total run budget has been exhausted."""
        return self.elapsed_seconds >= self.total_seconds

    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since run started."""
        if self._run_start is None:
            return 0.0
        return time.monotonic() - self._run_start

    @property
    def remaining_seconds(self) -> float:
        """Seconds remaining in the total budget."""
        return max(0.0, self.total_seconds - self.elapsed_seconds)

    def check_remaining(self) -> float:
        """
        Check remaining time and log a warning if under 20% of total budget.
        Returns remaining seconds.
        """
        remaining = self.remaining_seconds
        fraction_left = remaining / self.total_seconds
        if fraction_left < 0.1:
            logger.error(
                f"CRITICAL: Only {remaining:.1f}s remaining "
                f"({fraction_left*100:.0f}% of budget)"
            )
        elif fraction_left < 0.2:
            logger.warning(
                f"Low time budget: {remaining:.1f}s remaining "
                f"({fraction_left*100:.0f}% of budget)"
            )
        else:
            logger.debug(f"Time remaining: {remaining:.1f}s")
        return remaining

    # ------------------------------------------------------------------
    # Step-level controls
    # ------------------------------------------------------------------

    def start_step(self, step_name: str) -> float:
        """
        Mark the start of a step.

        Returns the allocated budget for this step in seconds.
        Raises RuntimeError if the total budget is already exhausted.
        """
        if self._run_start is None:
            self.start()

        if self.is_expired():
            raise RuntimeError(
                f"Cannot start step '{step_name}' — total budget exhausted "
                f"({self.elapsed_seconds:.1f}s / {self.total_seconds}s)"
            )

        # Determine how much time to give this step
        requested = self._step_budgets.get(step_name, 30.0)
        available = self.remaining_seconds
        allocated = min(requested, available)

        record = StepTimingRecord(
            name=step_name,
            allocated_seconds=allocated,
            started_at=time.monotonic(),
            status="running",
        )
        self._step_records[step_name] = record
        self._current_step = step_name

        logger.info(
            f"[STEP START] {step_name} — "
            f"allocated: {allocated:.1f}s, "
            f"total remaining: {available:.1f}s"
        )
        return allocated

    def end_step(self, step_name: str, status: str = "completed") -> StepTimingRecord:
        """Mark the end of a step and record its status."""
        record = self._step_records.get(step_name)
        if record is None:
            logger.warning(f"end_step called for unknown step '{step_name}'")
            return StepTimingRecord(
                name=step_name, allocated_seconds=0.0, status=status
            )

        record.ended_at = time.monotonic()
        record.status = status
        self._current_step = None

        overrun = record.overrun_seconds
        if overrun > 0:
            logger.warning(
                f"[STEP END] {step_name} ({status}) — "
                f"elapsed: {record.elapsed_seconds:.1f}s, "
                f"overrun: {overrun:.1f}s"
            )
        else:
            logger.info(
                f"[STEP END] {step_name} ({status}) — "
                f"elapsed: {record.elapsed_seconds:.1f}s / {record.allocated_seconds:.1f}s"
            )
        return record

    def is_step_expired(self, step_name: str) -> bool:
        """Return True if the named step has exceeded its allocated budget."""
        record = self._step_records.get(step_name)
        if record is None or record.started_at is None:
            return False
        return record.elapsed_seconds >= record.allocated_seconds

    def step_remaining(self, step_name: str) -> float:
        """
        Return seconds remaining for the given step.
        Returns 0.0 if the step is expired or unknown.
        """
        record = self._step_records.get(step_name)
        if record is None:
            # Fall back to total remaining
            return self.remaining_seconds
        # The step timeout is the min of its own budget and the total remaining
        step_left = record.remaining_seconds
        total_left = self.remaining_seconds
        return min(step_left, total_left)

    def assert_step_alive(self, step_name: str) -> None:
        """
        Raise TimeoutError if the step budget or total budget is exhausted.
        Call this inside tight loops during element polling.
        """
        if self.is_expired():
            raise TimeoutError(
                f"Total run budget exhausted during step '{step_name}'"
            )
        if self.is_step_expired(step_name):
            raise TimeoutError(
                f"Step '{step_name}' exceeded its {self._step_budgets.get(step_name, '?')}s budget"
            )

    # ------------------------------------------------------------------
    # Dynamic reallocation
    # ------------------------------------------------------------------

    def borrow_time(self, from_step: str, to_step: str, seconds: float) -> bool:
        """
        Move `seconds` from one step's budget to another.
        Only works if `from_step` hasn't started yet.
        Returns True if successful.
        """
        from_record = self._step_records.get(from_step)
        if from_record and from_record.started_at is not None:
            logger.warning(
                f"Cannot borrow time from already-started step '{from_step}'"
            )
            return False

        if from_step in self._step_budgets:
            if seconds > self._step_budgets[from_step]:
                logger.warning(
                    f"Cannot borrow {seconds}s from '{from_step}' "
                    f"(only has {self._step_budgets[from_step]}s)"
                )
                return False
            self._step_budgets[from_step] -= seconds
            self._step_budgets[to_step] = self._step_budgets.get(to_step, 0.0) + seconds
            logger.info(
                f"Borrowed {seconds}s from '{from_step}' → '{to_step}'"
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_report(self) -> dict:
        """
        Return a structured timing report for the full run.
        """
        total_elapsed = self.elapsed_seconds
        step_reports = []
        for name, record in self._step_records.items():
            step_reports.append({
                "step": name,
                "status": record.status,
                "allocated_s": round(record.allocated_seconds, 2),
                "elapsed_s": round(record.elapsed_seconds, 2),
                "overrun_s": round(record.overrun_seconds, 2),
                "used_pct": round(record.used_fraction * 100, 1),
            })

        return {
            "total_budget_s": self.total_seconds,
            "total_elapsed_s": round(total_elapsed, 2),
            "total_remaining_s": round(self.remaining_seconds, 2),
            "budget_exhausted": self.is_expired(),
            "steps": step_reports,
            "under_budget": total_elapsed <= self.total_seconds,
        }

    def log_report(self) -> None:
        """Log the timing report in a human-readable format."""
        report = self.get_report()
        logger.info("=" * 60)
        logger.info("TIMING REPORT")
        logger.info(
            f"Total: {report['total_elapsed_s']:.2f}s / {report['total_budget_s']}s "
            f"({'OVER BUDGET' if not report['under_budget'] else 'under budget'})"
        )
        logger.info("-" * 60)
        for step in report["steps"]:
            overrun_str = (
                f" [OVERRUN +{step['overrun_s']}s]" if step["overrun_s"] > 0 else ""
            )
            logger.info(
                f"  {step['step']:30s} {step['status']:12s} "
                f"{step['elapsed_s']:6.2f}s / {step['allocated_s']:6.2f}s "
                f"({step['used_pct']:5.1f}%){overrun_str}"
            )
        logger.info("=" * 60)
