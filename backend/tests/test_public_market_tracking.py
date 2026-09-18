from datetime import date

from database.migrations.runner import MIGRATIONS
from services.public_market_tracking import (
    compute_alert,
    compute_status,
    deadline_from,
    progress_count,
)


def market(**overrides):
    values = {
        "case_state": "active",
        "signature_date": None,
        "execution_delay_days": None,
        "equipment_reception_date": None,
        "delivery_note_date": None,
        "invoice_date": None,
        "provisional_acceptance_date": None,
        "warranty_retention_days": None,
        "final_acceptance_date": None,
    }
    values.update(overrides)
    return values


def test_market_status_follows_documentary_progress():
    assert compute_status(market(), today=date(2026, 8, 31)) == "signature_pending"
    assert compute_status(market(signature_date="2026-01-01"), today=date(2026, 8, 31)) == "equipment_reception_pending"
    assert compute_status(market(equipment_reception_date="2026-01-02"), today=date(2026, 8, 31)) == "delivery_note_pending"
    assert compute_status(market(delivery_note_date="2026-01-03"), today=date(2026, 8, 31)) == "invoice_pending"
    assert compute_status(market(invoice_date="2026-01-04"), today=date(2026, 8, 31)) == "provisional_acceptance_pending"
    assert compute_status(market(provisional_acceptance_date="2026-08-20", warranty_retention_days=60), today=date(2026, 8, 31)) == "warranty_in_progress"
    assert compute_status(market(provisional_acceptance_date="2026-08-20", warranty_retention_days=20), today=date(2026, 8, 31)) == "warranty_in_progress"
    assert compute_status(market(final_acceptance_date="2026-08-30"), today=date(2026, 8, 31)) == "completed"


def test_provisional_acceptance_stays_active_without_alert_until_final_acceptance():
    case = market(
        signature_date="2026-01-01",
        execution_delay_days=30,
        provisional_acceptance_date="2026-02-01",
        warranty_retention_days=1,
    )
    assert compute_status(case, today=date(2026, 8, 31)) == "warranty_in_progress"
    assert compute_alert(case, today=date(2026, 8, 31)) is None


def test_partial_delivery_keeps_the_delivery_step_open():
    case = market(delivery_notes=[
        {"delivery_note_date": "2026-01-03", "is_total_delivery": False},
        {"delivery_note_date": "2026-01-10", "is_total_delivery": False},
    ])
    assert compute_status(case, today=date(2026, 8, 31)) == "delivery_note_partial"
    assert progress_count(case) == 0


def test_total_delivery_turns_the_delivery_step_green():
    case = market(delivery_notes=[
        {"delivery_note_date": "2026-01-03", "is_total_delivery": False},
        {"delivery_note_date": "2026-01-10", "is_total_delivery": True},
    ])
    assert compute_status(case, today=date(2026, 8, 31)) == "invoice_pending"
    assert progress_count(case) == 1


def test_blocked_and_cancelled_market_states_override_progress():
    assert compute_status(market(case_state="blocked", final_acceptance_date="2026-08-30")) == "blocked"
    assert compute_status(market(case_state="cancelled")) == "cancelled"


def test_deadlines_are_calculated_in_days():
    assert deadline_from("2026-08-01", 45) == date(2026, 9, 15)
    assert deadline_from(None, 45) is None


def test_execution_alerts_change_at_thirty_and_fifteen_days():
    case = market(signature_date="2026-08-01", execution_delay_days=60)
    warning = compute_alert(case, today=date(2026, 9, 1))
    critical = compute_alert(case, today=date(2026, 9, 16))
    overdue = compute_alert(case, today=date(2026, 10, 2))

    assert warning and warning["severity"] == "warning" and warning["days_remaining"] == 29
    assert critical and critical["severity"] == "critical" and critical["days_remaining"] == 14
    assert overdue and overdue["severity"] == "overdue" and overdue["days_remaining"] == -2


def test_provisional_acceptance_does_not_create_a_warranty_alert():
    case = market(
        provisional_acceptance_date="2026-08-01",
        warranty_retention_days=60,
    )
    assert compute_alert(case, today=date(2026, 9, 1)) is None


def test_progress_counts_the_six_expected_milestones():
    assert progress_count(market(signature_date="2026-01-01", delivery_note_date="2026-01-03", invoice_date="2026-01-04")) == 3


def test_public_market_schema_migration_is_registered():
    migrations = [migration for migration in MIGRATIONS if migration[0] == "014"]
    assert len(migrations) == 1
    assert "public market" in migrations[0][1]


def test_public_market_history_migration_is_registered():
    migrations = [migration for migration in MIGRATIONS if migration[0] == "015"]
    assert len(migrations) == 1
    assert "history" in migrations[0][1]


def test_duplicate_equipment_names_migration_is_registered():
    migrations = [migration for migration in MIGRATIONS if migration[0] == "016"]
    assert len(migrations) == 1
    assert "duplicate equipment names" in migrations[0][1]


def test_public_market_invoice_migration_is_registered():
    migrations = [migration for migration in MIGRATIONS if migration[0] == "021"]
    assert len(migrations) == 1
    assert "invoice" in migrations[0][1]


def test_public_market_multiple_delivery_notes_migration_is_registered():
    migrations = [migration for migration in MIGRATIONS if migration[0] == "029"]
    assert len(migrations) == 1
    assert "delivery notes" in migrations[0][1]
