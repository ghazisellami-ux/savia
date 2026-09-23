from datetime import date

from database.migrations.runner import MIGRATIONS
from services.billing_tracking import (
    compute_case_status,
    compute_lead_times,
    current_stage_age_days,
    invoice_is_overdue,
)


def status(**overrides):
    values = {
        "case_state": "active",
        "steps": {},
        "paid_amount": 0,
        "intervention_started_at": None,
        "intervention_closed_at": None,
        "intervention_status": "",
        "has_parts": False,
        "coverage_status": "unassessed",
    }
    values.update(overrides)
    return compute_case_status(**values)


def test_billing_status_follows_the_furthest_reliable_milestone():
    assert status() == "quote_pending"
    assert status(steps={"quote": {"id": 1}}) == "purchase_order_pending"
    assert status(steps={"purchase_order": {"id": 2}}) == "ready_for_intervention"
    assert status(steps={"purchase_order": {"not_required": True}}) == "ready_for_intervention"
    assert status(intervention_started_at="2026-08-01") == "intervention_in_progress"
    assert status(intervention_closed_at="2026-08-03", has_parts=True) == "delivery_note_pending"
    assert status(intervention_closed_at="2026-08-03", has_parts=False) == "invoice_pending"


def test_invoice_and_payments_take_priority_over_missing_legacy_steps():
    invoice = {"id": 3, "amount": 1000}
    assert status(steps={"invoice": invoice}) == "payment_pending"
    assert status(steps={"invoice": invoice}, paid_amount=400) == "partial_payment"
    assert status(steps={"invoice": invoice}, paid_amount=1000) == "paid"


def test_blocked_and_cancelled_cases_override_progress():
    invoice = {"id": 3, "amount": 1000}
    assert status(case_state="blocked", steps={"invoice": invoice}, paid_amount=1000) == "blocked"
    assert status(case_state="cancelled") == "cancelled"


def test_contract_coverage_stops_the_invoice_workflow_until_resolved():
    assert status(intervention_closed_at="2026-08-03", coverage_status="covered") == "covered_by_contract"
    assert status(intervention_closed_at="2026-08-03", coverage_status="review") == "coverage_review"
    assert status(intervention_closed_at="2026-08-03", coverage_status="partial") == "invoice_pending"


def test_lead_times_cover_the_full_quote_to_payment_cycle():
    steps = {
        "quote": {"effective_date": "2026-08-01"},
        "purchase_order": {"effective_date": "2026-08-04"},
        "invoice": {"effective_date": "2026-08-12"},
    }
    payments = [{"effective_date": "2026-08-20"}, {"effective_date": "2026-08-25"}]
    metrics = compute_lead_times(steps, payments, "2026-08-05", "2026-08-10")
    assert metrics == {
        "quote_to_order": 3,
        "order_to_start": 1,
        "start_to_close": 5,
        "close_to_invoice": 2,
        "invoice_to_last_payment": 13,
        "quote_to_last_payment": 24,
    }


def test_overdue_depends_on_invoice_due_date_and_remaining_balance():
    invoice = {"due_date": "2026-08-15"}
    assert invoice_is_overdue(invoice, 1, today=date(2026, 8, 16)) is True
    assert invoice_is_overdue(invoice, 0, today=date(2026, 8, 16)) is False
    assert invoice_is_overdue(invoice, 1, today=date(2026, 8, 15)) is False


def test_current_stage_age_uses_the_milestone_that_opened_the_stage():
    assert current_stage_age_days(
        "purchase_order_pending",
        steps={"quote": {"effective_date": "2026-08-20"}},
        created_at="2026-08-19T08:00:00",
        intervention_started_at=None,
        intervention_closed_at=None,
        today=date(2026, 8, 27),
    ) == 7


def test_billing_schema_migration_is_registered():
    billing_migrations = [migration for migration in MIGRATIONS if migration[0] == "010"]

    assert len(billing_migrations) == 1
    assert "billing" in billing_migrations[0][1]


def test_billing_request_uniqueness_migration_is_registered():
    request_link_migrations = [migration for migration in MIGRATIONS if migration[0] == "012"]

    assert len(request_link_migrations) == 1
    assert "billing case" in request_link_migrations[0][1]


def test_merged_billing_cases_migration_is_registered():
    merged_case_migrations = [migration for migration in MIGRATIONS if migration[0] == "013"]

    assert len(merged_case_migrations) == 1
    assert "merged billing cases" in merged_case_migrations[0][1]


def test_contract_billing_coverage_migration_is_registered():
    coverage_migrations = [migration for migration in MIGRATIONS if migration[0] == "019"]

    assert len(coverage_migrations) == 1
    assert "contract billing coverage" in coverage_migrations[0][1]


def test_contract_cycle_billing_migration_is_registered():
    cycle_migrations = [migration for migration in MIGRATIONS if migration[0] == "034"]

    assert len(cycle_migrations) == 1
    assert "contract cycle" in cycle_migrations[0][1]
