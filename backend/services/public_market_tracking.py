"""Business rules for public-market progress, deadlines, and reminders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


STATUS_LABELS = {
    "signature_pending": "Signature à renseigner",
    "equipment_reception_pending": "Réception du matériel attendue",
    "delivery_note_pending": "Bon de livraison attendu",
    "invoice_pending": "Facture attendue",
    "provisional_acceptance_pending": "PV provisoire attendu",
    "warranty_in_progress": "Retenue de garantie en cours",
    "warranty_expiring": "Échéance de garantie proche",
    "final_acceptance_pending": "PV définitif attendu",
    "completed": "Marché achevé",
    "blocked": "Bloqué",
    "cancelled": "Annulé",
}

NEXT_STEP = {
    "signature_pending": "signature",
    "equipment_reception_pending": "equipment_reception",
    "delivery_note_pending": "delivery_note",
    "invoice_pending": "invoice",
    "provisional_acceptance_pending": "provisional_acceptance",
    "warranty_in_progress": "final_acceptance",
    "warranty_expiring": "final_acceptance",
    "final_acceptance_pending": "final_acceptance",
    "completed": None,
    "blocked": None,
    "cancelled": None,
}


def as_date(value: Any) -> date | None:
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


def deadline_from(start: Any, delay_days: Any) -> date | None:
    start_date = as_date(start)
    if not start_date or delay_days in (None, ""):
        return None
    try:
        days = int(delay_days)
    except (TypeError, ValueError):
        return None
    return start_date + timedelta(days=max(0, days))


def compute_status(case: dict[str, Any], today: date | None = None) -> str:
    """Return the furthest reliable market stage."""
    state = str(case.get("case_state") or "active")
    if state in {"blocked", "cancelled"}:
        return state
    if as_date(case.get("final_acceptance_date")):
        return "completed"
    if as_date(case.get("provisional_acceptance_date")):
        warranty_deadline = deadline_from(
            case.get("provisional_acceptance_date"),
            case.get("warranty_retention_days"),
        )
        if not warranty_deadline or warranty_deadline <= (today or date.today()):
            return "final_acceptance_pending"
        if (warranty_deadline - (today or date.today())).days <= 30:
            return "warranty_expiring"
        return "warranty_in_progress"
    if as_date(case.get("invoice_date")):
        return "provisional_acceptance_pending"
    if as_date(case.get("delivery_note_date")):
        return "invoice_pending"
    if as_date(case.get("equipment_reception_date")):
        return "delivery_note_pending"
    if as_date(case.get("signature_date")):
        return "equipment_reception_pending"
    return "signature_pending"


def compute_alert(case: dict[str, Any], today: date | None = None) -> dict[str, Any] | None:
    """Return the most urgent open deadline alert for one market."""
    current = today or date.today()
    if case.get("case_state") in {"blocked", "cancelled"} or as_date(case.get("final_acceptance_date")):
        return None

    candidates: list[tuple[str, date, str]] = []
    execution_deadline = deadline_from(case.get("signature_date"), case.get("execution_delay_days"))
    if execution_deadline:
        candidates.append(("execution", execution_deadline, "Délai d’exécution"))

    if as_date(case.get("provisional_acceptance_date")):
        warranty_deadline = deadline_from(
            case.get("provisional_acceptance_date"),
            case.get("warranty_retention_days"),
        )
        if warranty_deadline:
            candidates.append(("warranty", warranty_deadline, "Fin de retenue de garantie"))

    alerts = []
    for alert_type, due_date, label in candidates:
        days_remaining = (due_date - current).days
        if days_remaining <= 30:
            severity = "overdue" if days_remaining < 0 else "critical" if days_remaining <= 15 else "warning"
            alerts.append({
                "type": alert_type,
                "label": label,
                "due_date": due_date.isoformat(),
                "days_remaining": days_remaining,
                "severity": severity,
            })
    if not alerts:
        return None
    return min(alerts, key=lambda item: item["days_remaining"])


def progress_count(case: dict[str, Any]) -> int:
    return sum(bool(as_date(case.get(field))) for field in (
        "signature_date",
        "equipment_reception_date",
        "delivery_note_date",
        "invoice_date",
        "provisional_acceptance_date",
        "final_acceptance_date",
    ))
