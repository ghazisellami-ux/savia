"""Shared rules for applying contractual response-time SLAs.

Both the API view and the scheduled notifications use this module.  Keeping
the choice of a contract in one place avoids displaying a different SLA from
the one that triggers an alert.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Iterable
import unicodedata


def _text(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.split()).casefold()


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _sla_hours(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def active_sla_contracts(
    contracts: Iterable[dict[str, Any]],
    equipment_lookup: Callable[[int], Iterable[dict[str, Any]]] | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Return active, currently valid contracts that explicitly define a SLA.

    Equipment linked through ``contrats_equipements`` takes precedence over
    the legacy single ``equipement`` field.  A contract without equipment is a
    client-wide commitment.
    """
    today = today or date.today()
    result: list[dict[str, Any]] = []
    for raw in contracts:
        client = _text(raw.get("client"))
        if not client or _text(raw.get("statut")) not in {"actif", "active"}:
            continue
        sla_h = _sla_hours(raw.get("sla_temps_reponse_h"))
        if sla_h <= 0:
            continue
        start, end = _date(raw.get("date_debut")), _date(raw.get("date_fin"))
        if (start and start > today) or (end and end < today):
            continue

        equipment_names: set[str] = set()
        contract_id = raw.get("id")
        if equipment_lookup and contract_id is not None:
            try:
                for equipment in equipment_lookup(int(contract_id)) or []:
                    name = _text(equipment.get("nom") if isinstance(equipment, dict) else equipment)
                    if name:
                        equipment_names.add(name)
            except (TypeError, ValueError):
                pass
        # Old contracts have no junction-table rows.  Their legacy field still
        # needs to be honoured, rather than making them client-wide by mistake.
        if not equipment_names:
            legacy_equipment = _text(raw.get("equipement"))
            if legacy_equipment:
                equipment_names.add(legacy_equipment)

        result.append({
            "id": contract_id,
            "client": client,
            "sla_h": sla_h,
            "equipment_names": equipment_names,
            "date_fin": end,
            "type_contrat": str(raw.get("type_contrat") or "Contrat"),
            "contract_type_key": _text(raw.get("type_contrat")),
        })
    return result


def contract_covers_intervention(contract: dict[str, Any], intervention_type: Any) -> bool:
    """Return whether the contract's maintenance scope covers this work type.

    A *Maintenance Préventive* contract covers preventive work only.  It is
    not a response-time commitment for corrective incidents.  Broad support
    contracts such as Full Service and labour-only contracts retain coverage
    for both types unless a more specific contract type is introduced.
    """
    contract_type = contract.get("contract_type_key") or _text(contract.get("type_contrat"))
    work_type = _text(intervention_type)
    # The persisted labels can be accented or originate from an older import
    # with damaged accents.  ``maintenance pr`` deliberately covers both
    # while remaining specific to the preventive-maintenance label.
    if "preventive" in contract_type or "maintenance pr" in contract_type:
        return "preventive" in work_type or work_type.startswith("pr")
    if "corrective" in contract_type:
        return "corrective" in work_type
    return True


def sla_start_value(intervention: Any) -> Any:
    """Return the current contractual start value for an intervention.

    The linked planning row is the source of truth after a reschedule.  Its
    date is overwritten on every change, whereas an intervention can retain
    its original operational timestamps for audit purposes.
    """
    getter = intervention.get if hasattr(intervention, "get") else lambda _key, default="": default
    return (
        getter("planning_date", "")
        or getter("date", "")
        or getter("date_debut_intervention", "")
    )


def compliance_percentage(
    historical_compliant: int,
    historical_total: int,
    active_items: Iterable[dict[str, Any]],
) -> float:
    """Calculate global compliance, including SLA cases that are still open.

    An open case remains compliant until it breaches; once breached, it must
    immediately lower the global rate instead of waiting for closure.
    """
    active = list(active_items)
    total = max(0, historical_total) + len(active)
    if total == 0:
        return 100
    compliant = max(0, historical_compliant) + sum(
        1 for item in active if not bool(item.get("breached"))
    )
    return round((compliant / total) * 100, 1)


def sla_contract_for(
    contracts: Iterable[dict[str, Any]], client: Any, equipment: Any, intervention_type: Any = "",
) -> dict[str, Any] | None:
    """Choose the applicable SLA, preferring an equipment-specific contract.

    Overlapping commitments are resolved deterministically: equipment-specific
    before client-wide, then the stricter response time and nearest expiry.
    """
    client_key, equipment_key = _text(client), _text(equipment)
    candidates: list[tuple[int, dict[str, Any]]] = []
    for contract in contracts:
        if contract["client"] != client_key:
            continue
        if not contract_covers_intervention(contract, intervention_type):
            continue
        covered = contract["equipment_names"]
        if covered:
            if not equipment_key or equipment_key not in covered:
                continue
            specificity = 1
        else:
            specificity = 0
        candidates.append((specificity, contract))
    if not candidates:
        return None

    def sort_key(candidate: tuple[int, dict[str, Any]]) -> tuple[int, int, date]:
        specificity, contract = candidate
        return (-specificity, contract["sla_h"], contract["date_fin"] or date.max)

    return sorted(candidates, key=sort_key)[0][1]


def sla_start_at(
    start_value: Any,
    business_day_start_hour: int | None = None,
) -> datetime | None:
    """Resolve the instant at which an SLA clock starts.

    ``DATE`` values have no clock time. For an SLA tied to a planned day,
    callers set ``business_day_start_hour=8`` so the clock starts at 08:00,
    not at the database's artificial 00:00 timestamp.
    """
    if start_value is None or start_value == "":
        return None
    try:
        raw_text = str(start_value).strip()
        if isinstance(start_value, date) and not isinstance(start_value, datetime):
            start = datetime.combine(start_value, datetime.min.time())
        else:
            start = start_value.to_pydatetime() if hasattr(start_value, "to_pydatetime") else start_value
            if not isinstance(start, datetime):
                start = datetime.fromisoformat(raw_text.replace("Z", "+00:00"))
        is_date_only = len(raw_text) == 10 and raw_text[4:5] == "-" and raw_text[7:8] == "-"
        if business_day_start_hour is not None and (is_date_only or start.time() == datetime.min.time()):
            start = start.replace(hour=business_day_start_hour, minute=0, second=0, microsecond=0)
        return start
    except (TypeError, ValueError, OverflowError):
        return None


def elapsed_hours(
    start_value: Any,
    now: datetime | None = None,
    business_day_start_hour: int | None = None,
) -> float | None:
    """Calculate a non-negative elapsed duration from a persisted timestamp."""
    start = sla_start_at(start_value, business_day_start_hour)
    if start is None:
        return None
    try:
        current = now or (datetime.now(start.tzinfo) if start.tzinfo else datetime.now())
        # PostgreSQL stores naive timestamps today.  This also makes imported
        # ISO timestamps with an offset safe to process during the transition.
        if start.tzinfo and current.tzinfo is None:
            current = current.replace(tzinfo=start.tzinfo)
        elif not start.tzinfo and current.tzinfo:
            current = current.replace(tzinfo=None)
        return round(max(0, (current - start).total_seconds() / 3600), 1)
    except (TypeError, ValueError, OverflowError):
        return None
