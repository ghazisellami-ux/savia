from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
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


def test_planning_reminder_includes_only_the_next_fifteen_days(monkeypatch):
    today = date.today()
    monkeypatch.setattr(
        jobs,
        "lire_planning",
        lambda: jobs.pd.DataFrame([
            {
                "id": 1,
                "statut": "Planifiée",
                "machine": "Dans la fenêtre",
                "date_prevue": (today + timedelta(days=15)).isoformat(),
            },
            {
                "id": 2,
                "statut": "Planifiée",
                "machine": "Hors fenêtre",
                "date_prevue": (today + timedelta(days=16)).isoformat(),
            },
        ]),
    )
    messages = []
    monkeypatch.setattr(jobs, "_send_telegram", messages.append)

    reminders = jobs.check_planning_reminder()

    assert [reminder["machine"] for reminder in reminders] == ["Dans la fenêtre"]
    assert len(messages) == 1
    assert "dans les 15 prochains jours" in messages[0]
    assert "Hors fenêtre" not in messages[0]
