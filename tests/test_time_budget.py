"""
Tests for the TimeBudgetManager.

Covers:
- Normal step lifecycle (start → end)
- Total budget expiration
- Step budget expiration
- Budget borrowing
- Report structure
- assert_step_alive guard
"""

import time
import pytest
from orchestrator.time_budget import TimeBudgetManager


class TestTimeBudgetManagerBasics:
    """Basic lifecycle tests."""

    def test_starts_with_full_budget(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        assert budget.remaining_seconds > 179

    def test_elapsed_increases_over_time(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        time.sleep(0.05)
        assert budget.elapsed_seconds > 0.04

    def test_is_not_expired_immediately(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        assert not budget.is_expired()

    def test_is_expired_when_budget_exhausted(self):
        budget = TimeBudgetManager(total_seconds=0.05)
        budget.start()
        time.sleep(0.1)
        assert budget.is_expired()

    def test_start_is_idempotent_when_called_twice(self):
        """start() called twice should not reset clock."""
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        time.sleep(0.05)
        budget.start()  # Second call should not reset
        # remaining should still have been reduced by the initial sleep
        assert budget.elapsed_seconds >= 0.04


class TestStepLifecycle:
    """Step start/end tracking tests."""

    def test_start_step_returns_allocated_seconds(self):
        budget = TimeBudgetManager(
            total_seconds=180,
            step_budgets={"my_step": 30.0},
        )
        budget.start()
        allocated = budget.start_step("my_step")
        assert 0 < allocated <= 30.0

    def test_end_step_returns_record(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        budget.start_step("step_a")
        record = budget.end_step("step_a", status="completed")
        assert record.status == "completed"
        assert record.elapsed_seconds > 0

    def test_step_elapsed_time_tracked(self):
        budget = TimeBudgetManager(total_seconds=180, step_budgets={"step_a": 30.0})
        budget.start()
        budget.start_step("step_a")
        time.sleep(0.05)
        record = budget.end_step("step_a", "completed")
        assert record.elapsed_seconds >= 0.04

    def test_step_not_expired_before_limit(self):
        budget = TimeBudgetManager(total_seconds=180, step_budgets={"quick": 30.0})
        budget.start()
        budget.start_step("quick")
        assert not budget.is_step_expired("quick")

    def test_step_expired_after_limit(self):
        budget = TimeBudgetManager(total_seconds=180, step_budgets={"tiny": 0.05})
        budget.start()
        budget.start_step("tiny")
        time.sleep(0.1)
        assert budget.is_step_expired("tiny")

    def test_step_remaining_decreases(self):
        budget = TimeBudgetManager(total_seconds=180, step_budgets={"step_x": 30.0})
        budget.start()
        budget.start_step("step_x")
        r1 = budget.step_remaining("step_x")
        time.sleep(0.05)
        r2 = budget.step_remaining("step_x")
        assert r2 < r1

    def test_unknown_step_end_returns_record(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        # Should not raise even for unknown step
        record = budget.end_step("nonexistent_step", "completed")
        assert record is not None


class TestBudgetGuards:
    """Tests for assert_step_alive and check_remaining."""

    def test_assert_step_alive_passes_when_within_budget(self):
        budget = TimeBudgetManager(total_seconds=180, step_budgets={"s": 60.0})
        budget.start()
        budget.start_step("s")
        # Should not raise
        budget.assert_step_alive("s")

    def test_assert_step_alive_raises_on_total_expiry(self):
        budget = TimeBudgetManager(total_seconds=0.05)
        budget.start()
        time.sleep(0.1)
        with pytest.raises(TimeoutError, match="Total run budget"):
            budget.assert_step_alive("any_step")

    def test_assert_step_alive_raises_on_step_expiry(self):
        budget = TimeBudgetManager(total_seconds=180, step_budgets={"s": 0.05})
        budget.start()
        budget.start_step("s")
        time.sleep(0.1)
        with pytest.raises(TimeoutError, match="s"):
            budget.assert_step_alive("s")

    def test_start_step_raises_if_budget_exhausted(self):
        budget = TimeBudgetManager(total_seconds=0.05)
        budget.start()
        time.sleep(0.1)
        with pytest.raises(RuntimeError, match="budget exhausted"):
            budget.start_step("some_step")

    def test_check_remaining_returns_float(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        remaining = budget.check_remaining()
        assert isinstance(remaining, float)
        assert remaining > 0


class TestBudgetBorrowing:
    """Tests for dynamic time reallocation."""

    def test_borrow_time_succeeds_for_unstarted_step(self):
        budget = TimeBudgetManager(
            total_seconds=180,
            step_budgets={"donor": 40.0, "recipient": 20.0},
        )
        budget.start()
        result = budget.borrow_time("donor", "recipient", 10.0)
        assert result is True
        assert budget._step_budgets["donor"] == 30.0
        assert budget._step_budgets["recipient"] == 30.0

    def test_borrow_time_fails_for_started_step(self):
        budget = TimeBudgetManager(
            total_seconds=180,
            step_budgets={"donor": 40.0, "recipient": 20.0},
        )
        budget.start()
        budget.start_step("donor")
        result = budget.borrow_time("donor", "recipient", 10.0)
        assert result is False  # Can't borrow from a running step

    def test_borrow_more_than_available_fails(self):
        budget = TimeBudgetManager(
            total_seconds=180,
            step_budgets={"small": 5.0},
        )
        budget.start()
        result = budget.borrow_time("small", "other", 20.0)
        assert result is False


class TestReport:
    """Tests for timing report structure."""

    def test_report_has_required_keys(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        budget.start_step("step1")
        budget.end_step("step1", "completed")
        report = budget.get_report()

        assert "total_budget_s" in report
        assert "total_elapsed_s" in report
        assert "total_remaining_s" in report
        assert "budget_exhausted" in report
        assert "steps" in report
        assert "under_budget" in report

    def test_report_steps_list_accurate(self):
        budget = TimeBudgetManager(total_seconds=180, step_budgets={"a": 30.0, "b": 30.0})
        budget.start()
        budget.start_step("a")
        budget.end_step("a", "completed")
        budget.start_step("b")
        budget.end_step("b", "failed")
        report = budget.get_report()

        step_names = [s["step"] for s in report["steps"]]
        assert "a" in step_names
        assert "b" in step_names

        step_a = next(s for s in report["steps"] if s["step"] == "a")
        assert step_a["status"] == "completed"
        step_b = next(s for s in report["steps"] if s["step"] == "b")
        assert step_b["status"] == "failed"

    def test_report_under_budget_is_true_when_fast(self):
        budget = TimeBudgetManager(total_seconds=180)
        budget.start()
        report = budget.get_report()
        assert report["under_budget"] is True

    def test_report_under_budget_is_false_when_exceeded(self):
        budget = TimeBudgetManager(total_seconds=0.05)
        budget.start()
        time.sleep(0.1)
        report = budget.get_report()
        assert report["under_budget"] is False
