"""Pure business rules for billing-case progress and lead-time metrics."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


STEP_TYPES = ("quote", "purchase_order", "delivery_note", "invoice")

STATUS_LABELS = {
    "quote_pending": "Devis à renseigner",
    "purchase_order_pending": "En attente du bon de commande",
    "ready_for_intervention": "Prêt pour intervention",
    "intervention_in_progress": "Intervention en cours",
    "delivery_note_pending": "Bon de livraison à valider",
    "invoice_pending": "Prêt à facturer",
    "payment_pending": "Facture envoyée — paiement attendu",
    "partial_payment": "Paiement partiel",
    "paid": "Payé",
    "covered_by_contract": "Couvert par contrat",
    "coverage_review": "Couverture à vérifier",
    "blocked": "Bloqué",
    "cancelled": "Annulé",
}

NEXT_STEP = {
    "quote_pending": "quote",
    "purchase_order_pending": "purchase_order",
    "ready_for_intervention": "intervention",
    "intervention_in_progress": "intervention_close",
    "delivery_note_pending": "delivery_note",
    "invoice_pending": "invoice",
    "payment_pending": "payment",
    "partial_payment": "payment",
    "paid": None,
    "covered_by_contract": None,
    "coverage_review": None,
    "blocked": None,
    "cancelled": None,
}


def _as_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def step_is_complete(step: dict[str, Any] | None) -> bool:
    """A legacy invoice without an effective date still represents a reached step."""
    return bool(step and (step.get("not_required") or step.get("id")))


def compute_case_status(
    *,
    case_state: str,
    steps: dict[str, dict[str, Any]],
    paid_amount: Any,
    intervention_started_at: Any,
    intervention_closed_at: Any,
    intervention_status: str,
    has_parts: bool,
    coverage_status: str = "unassessed",
    delivery_complete: bool | None = None,
    invoice_complete: bool | None = None,
    contract_billing: bool = False,
) -> str:
    """Return the furthest reliable business state without trusting UI input."""
    if case_state == "blocked":
        return "blocked"
    if case_state == "cancelled":
        return "cancelled"

    invoice = steps.get("invoice")
    invoice_complete = step_is_complete(invoice) if invoice_complete is None else invoice_complete
    delivery_complete = step_is_complete(steps.get("delivery_note")) if delivery_complete is None else delivery_complete
    if invoice_complete and invoice:
        invoice_amount = _as_decimal(invoice.get("amount")) if invoice else Decimal("0")
        paid = _as_decimal(paid_amount)
        if invoice_amount > 0 and paid >= invoice_amount:
            return "paid"
        if paid > 0:
            return "partial_payment"
        return "payment_pending"

    if coverage_status == "covered" and not contract_billing:
        return "covered_by_contract"
    if coverage_status == "review":
        return "coverage_review"

    closed = bool(_as_date(intervention_closed_at)) or any(
        token in str(intervention_status or "").casefold()
        for token in ("clotur", "clôtur", "termin")
    )
    if closed:
        if has_parts and not delivery_complete:
            return "delivery_note_pending"
        return "invoice_pending"

    if _as_date(intervention_started_at) or "cours" in str(intervention_status or "").casefold():
        return "intervention_in_progress"
    if step_is_complete(steps.get("purchase_order")):
        return "ready_for_intervention"
    if step_is_complete(steps.get("quote")):
        return "purchase_order_pending"
    return "quote_pending"


def days_between(start: Any, end: Any) -> int | None:
    start_date = _as_date(start)
    end_date = _as_date(end)
    if not start_date or not end_date:
        return None
    return (end_date - start_date).days


def compute_lead_times(
    steps: dict[str, dict[str, Any]],
    payments: list[dict[str, Any]],
    intervention_started_at: Any,
    intervention_closed_at: Any,
) -> dict[str, int | None]:
    quote_date = (steps.get("quote") or {}).get("effective_date")
    order_date = (steps.get("purchase_order") or {}).get("effective_date")
    invoice_date = (steps.get("invoice") or {}).get("effective_date")
    final_payment_date = None
    if payments:
        final_payment_date = max(
            (_as_date(item.get("effective_date")) for item in payments),
            default=None,
        )
    return {
        "quote_to_order": days_between(quote_date, order_date),
        "order_to_start": days_between(order_date, intervention_started_at),
        "start_to_close": days_between(intervention_started_at, intervention_closed_at),
        "close_to_invoice": days_between(intervention_closed_at, invoice_date),
        "invoice_to_last_payment": days_between(invoice_date, final_payment_date),
        "quote_to_last_payment": days_between(quote_date, final_payment_date),
    }


def invoice_is_overdue(invoice: dict[str, Any] | None, remaining_amount: Any, today: date | None = None) -> bool:
    due_date = _as_date((invoice or {}).get("due_date"))
    return bool(due_date and _as_decimal(remaining_amount) > 0 and due_date < (today or date.today()))


def current_stage_age_days(
    status: str,
    *,
    steps: dict[str, dict[str, Any]],
    created_at: Any,
    intervention_started_at: Any,
    intervention_closed_at: Any,
    today: date | None = None,
) -> int | None:
    """Measure how long the dossier has been waiting in its current stage."""
    anchors = {
        "quote_pending": created_at,
        "purchase_order_pending": (steps.get("quote") or {}).get("effective_date"),
        "ready_for_intervention": (steps.get("purchase_order") or {}).get("effective_date"),
        "intervention_in_progress": intervention_started_at,
        "delivery_note_pending": intervention_closed_at,
        "invoice_pending": (steps.get("delivery_note") or {}).get("effective_date") or intervention_closed_at,
        "payment_pending": (steps.get("invoice") or {}).get("effective_date"),
        "partial_payment": (steps.get("invoice") or {}).get("effective_date"),
    }
    anchor = _as_date(anchors.get(status))
    if not anchor:
        return None
    return max(0, ((today or date.today()) - anchor).days)
