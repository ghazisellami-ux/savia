from datetime import date

from dateutil.relativedelta import relativedelta

from repositories.contracts import _next_contract_maintenance_date, _should_display_historical_anchor


def test_contract_update_controller_imports_the_replanning_service():
    # The update route invokes this symbol when an historical maintenance
    # anchor is supplied.  Importing the real controller catches a missing
    # runtime import before it can turn a successful update into HTTP 500.
    from controllers import contracts as contract_controller

    assert callable(contract_controller.replanifier_contrat)


def test_future_first_maintenance_is_not_replaced_by_today():
    result = _next_contract_maintenance_date(
        date(2026, 10, 1),
        date(2027, 9, 30),
        relativedelta(months=6),
        today=date(2026, 9, 8),
    )

    assert result == date(2026, 10, 1)


def test_historical_contract_starts_after_the_last_maintenance():
    result = _next_contract_maintenance_date(
        date(2025, 11, 1),
        date(2027, 9, 30),
        relativedelta(months=3),
        date_derniere=date(2026, 6, 1),
        today=date(2026, 9, 8),
    )

    assert result == date(2026, 12, 1)


def test_recent_historical_anchor_is_shown_as_completed_visit():
    assert _should_display_historical_anchor(
        date(2026, 8, 23),
        today=date(2026, 9, 8),
    )


def test_old_historical_anchor_is_not_added_to_the_planning():
    assert not _should_display_historical_anchor(
        date(2026, 8, 7),
        today=date(2026, 9, 8),
    )


def test_past_automatic_visits_are_not_generated_without_an_anchor():
    result = _next_contract_maintenance_date(
        date(2025, 11, 1),
        date(2027, 9, 30),
        relativedelta(months=6),
        today=date(2026, 9, 8),
    )

    assert result == date(2026, 11, 1)
