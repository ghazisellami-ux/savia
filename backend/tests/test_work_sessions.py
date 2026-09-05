import pytest

from repositories.work_sessions import validate_work_sessions


def _session(entry_uuid="one", work_date="2026-09-05", start="08:00", end="09:00"):
    return {
        "entry_uuid": entry_uuid,
        "work_date": work_date,
        "start_time": start,
        "end_time": end,
        "travel_minutes": 15,
    }


def test_work_sessions_calculate_actual_duration():
    result = validate_work_sessions([_session(start="08:15", end="09:45")])
    assert result[0]["duration_minutes"] == 90


def test_work_sessions_allow_multiple_periods_on_same_date():
    result = validate_work_sessions([
        _session("morning", start="08:00", end="12:00"),
        _session("afternoon", start="13:00", end="16:30"),
    ])
    assert sum(item["duration_minutes"] for item in result) == 450


def test_work_sessions_reject_overlaps_for_same_technician():
    with pytest.raises(ValueError, match="chevauchent"):
        validate_work_sessions([
            _session("first", start="08:00", end="10:00"),
            _session("second", start="09:45", end="11:00"),
        ])


def test_work_sessions_allow_same_hours_on_different_dates():
    result = validate_work_sessions([
        _session("day-one", work_date="2026-09-05"),
        _session("day-two", work_date="2026-09-06"),
    ])
    assert len(result) == 2


def test_overnight_session_rejects_overlap_on_next_date():
    with pytest.raises(ValueError, match="chevauchent"):
        validate_work_sessions([
            _session("night", work_date="2026-09-05", start="22:00", end="02:00"),
            _session("next-day", work_date="2026-09-06", start="01:00", end="03:00"),
        ])
