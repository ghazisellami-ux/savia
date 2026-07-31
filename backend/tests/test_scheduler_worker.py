from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import services.scheduled_jobs as jobs


def test_scheduler_is_due_only_at_configured_time_and_day():
    schedule = {"enabled": 1, "hour": 8, "minute": 30, "days_of_week": "1,3,5"}

    assert jobs._is_scheduler_due(schedule, datetime(2026, 7, 31, 8, 30, tzinfo=timezone.utc))
    assert not jobs._is_scheduler_due(schedule, datetime(2026, 7, 31, 8, 31, tzinfo=timezone.utc))
    assert not jobs._is_scheduler_due(schedule, datetime(2026, 8, 1, 8, 30, tzinfo=timezone.utc))


def test_scheduler_cycle_marks_the_day_only_after_running(monkeypatch):
    calls = []
    now = datetime(2026, 7, 31, 8, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(jobs, "_get_scheduler_schedule", lambda: {"enabled": 1, "hour": 8, "minute": 30, "days_of_week": "5"})
    monkeypatch.setattr(jobs, "_scheduler_already_ran", lambda _date: False)
    monkeypatch.setattr(jobs, "run_scheduled_cycle", lambda: calls.append("cycle"))
    monkeypatch.setattr(jobs, "_mark_scheduler_ran", lambda date: calls.append(date))

    @contextmanager
    def leader():
        yield True

    monkeypatch.setattr(jobs, "scheduler_leader_lock", leader)

    assert jobs.run_scheduler_once(now) == "completed"
    assert calls == ["cycle", "2026-07-31"]


def test_scheduler_standby_does_not_execute_jobs(monkeypatch):
    now = datetime(2026, 7, 31, 8, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(jobs, "_get_scheduler_schedule", lambda: {"enabled": 1, "hour": 8, "minute": 30, "days_of_week": "5"})
    monkeypatch.setattr(jobs, "run_scheduled_cycle", lambda: (_ for _ in ()).throw(AssertionError("must not run")))

    @contextmanager
    def standby():
        yield False

    monkeypatch.setattr(jobs, "scheduler_leader_lock", standby)

    assert jobs.run_scheduler_once(now) == "standby"


def test_api_startup_no_longer_starts_a_scheduler_thread():
    lifecycle = Path(__file__).parents[1] / "api" / "lifecycle.py"
    assert "_start_garantie_daemon" not in lifecycle.read_text(encoding="utf-8")
