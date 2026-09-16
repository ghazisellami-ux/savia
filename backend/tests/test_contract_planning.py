from datetime import date

from dateutil.relativedelta import relativedelta

from repositories.contracts import (
    _next_contract_maintenance_date,
    _should_display_historical_anchor,
    contract_planning_settings_changed,
)


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


def test_first_maintenance_change_replans_pending_contract_visits():
    existing = {
        "date_debut": "2026-09-29",
        "date_fin": "2027-09-28",
        "date_premiere_maintenance": "2026-11-21",
        "date_derniere_maintenance": None,
        "recurrence_maintenance": "Semestrielle",
    }
    updated = {**existing, "date_premiere_maintenance": "2026-11-16", "equipements": ["Respirateur"]}

    assert contract_planning_settings_changed(existing, ["Respirateur"], updated)


def test_non_planning_change_does_not_replan_contract_visits():
    existing = {
        "date_debut": "2026-09-29",
        "date_fin": "2027-09-28",
        "date_premiere_maintenance": "2026-11-16",
        "date_derniere_maintenance": None,
        "recurrence_maintenance": "Semestrielle",
    }
    updated = {**existing, "montant": 27000, "notes": "Avenant commercial", "equipements": ["Respirateur"]}

    assert not contract_planning_settings_changed(existing, ["Respirateur"], updated)


def test_historical_contract_keeps_the_first_overdue_visit_after_last_maintenance():
    result = _next_contract_maintenance_date(
        date(2025, 11, 1),
        date(2027, 9, 30),
        relativedelta(months=3),
        date_derniere=date(2026, 6, 1),
        today=date(2026, 9, 8),
    )

    assert result == date(2026, 9, 1)


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


def test_first_overdue_automatic_visit_is_kept_in_the_planning():
    result = _next_contract_maintenance_date(
        date(2025, 11, 1),
        date(2027, 9, 30),
        relativedelta(months=6),
        today=date(2026, 9, 8),
    )

    assert result == date(2025, 11, 1)


def test_next_visit_after_last_maintenance_is_kept_when_overdue():
    result = _next_contract_maintenance_date(
        date(2026, 3, 3),
        date(2027, 1, 25),
        relativedelta(months=6),
        date_derniere=date(2026, 3, 3),
        today=date(2026, 9, 16),
    )

    assert result == date(2026, 9, 3)
