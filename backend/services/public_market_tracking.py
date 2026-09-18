"""Business rules for public-market progress, deadlines, and reminders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


STATUS_LABELS = {
    "signature_pending": "Signature à renseigner",
    "equipment_reception_pending": "Réception du matériel attendue",
    "delivery_note_pending": "Bon de livraison attendu",
    "delivery_note_partial": "Livraison partielle — BL total attendu",
    "invoice_pending": "Facture attendue",
    "provisional_acceptance_pending": "PV provisoire attendu",
    "warranty_in_progress": "Marché en cours — PV définitif attendu",
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
    "delivery_note_partial": "delivery_note",
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


def delivery_notes(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return delivery notes, with the legacy single-BL fields as a fallback."""
    notes = case.get("delivery_notes")
    if isinstance(notes, list):
        return [note for note in notes if isinstance(note, dict)]
    legacy_date = as_date(case.get("delivery_note_date"))
    if not legacy_date:
        return []
    return [{
        "delivery_note_date": legacy_date,
        "delivery_note_reference": case.get("delivery_note_reference") or "",
        # A legacy BL was already considered a completed milestone.
        "is_total_delivery": True,
    }]


def has_delivery_note(case: dict[str, Any]) -> bool:
    return bool(delivery_notes(case))


def has_total_delivery(case: dict[str, Any]) -> bool:
    return any(bool(note.get("is_total_delivery")) for note in delivery_notes(case))


def compute_status(case: dict[str, Any], today: date | None = None) -> str:
    """Return the furthest reliable market stage."""
    state = str(case.get("case_state") or "active")
    if state in {"blocked", "cancelled"}:
        return state
    if as_date(case.get("final_acceptance_date")):
        return "completed"
    if as_date(case.get("provisional_acceptance_date")):
        # The provisional acceptance keeps the market active. It is completed
        # only when the final acceptance is recorded.
        return "warranty_in_progress"
    if has_delivery_note(case) and not has_total_delivery(case):
        return "delivery_note_partial"
    if as_date(case.get("invoice_date")):
        return "provisional_acceptance_pending"
    if has_total_delivery(case):
        return "invoice_pending"
    if as_date(case.get("equipment_reception_date")):
        return "delivery_note_pending"
    if as_date(case.get("signature_date")):
        return "equipment_reception_pending"
    return "signature_pending"


def compute_alert(case: dict[str, Any], today: date | None = None) -> dict[str, Any] | None:
    """Return the most urgent open deadline alert for one market."""
    current = today or date.today()
    if (case.get("case_state") in {"blocked", "cancelled"}
            or as_date(case.get("final_acceptance_date"))
            or as_date(case.get("provisional_acceptance_date"))):
        return None

    candidates: list[tuple[str, date, str]] = []
    execution_deadline = deadline_from(case.get("signature_date"), case.get("execution_delay_days"))
    if execution_deadline:
        candidates.append(("execution", execution_deadline, "Délai d’exécution"))

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
    completed_fields = (
        "signature_date",
        "equipment_reception_date",
        "invoice_date",
        "provisional_acceptance_date",
        "final_acceptance_date",
    )
    completed = sum(bool(as_date(case.get(field))) for field in completed_fields)
    # A partial delivery is displayed as an orange, unfinished BL step.
    if has_total_delivery(case):
        completed += 1
    return completed
