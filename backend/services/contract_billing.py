"""Deterministic contract coverage assessment for closed interventions.

The billing case remains the audit container for every intervention.  This
module decides which part of the technical cost is actually chargeable to the
customer; it never changes the internal intervention cost.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


COVERAGE_LABELS = {
    "unassessed": "Couverture non évaluée",
    "covered": "Couvert par contrat",
    "partial": "Partiellement facturable",
    "billable": "À facturer",
    "review": "Couverture à vérifier",
}


def _money(value: Any) -> Decimal:
    try:
        return max(Decimal("0"), Decimal(str(value or 0))).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
    except Exception:
        return Decimal("0.000")


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold().strip()


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


def parse_used_parts(value: Any) -> list[dict[str, Any]]:
    """Parse the canonical intervention part summary and common legacy forms."""
    text = str(value or "").strip()
    if not text:
        return []
    result: list[dict[str, Any]] = []
    for line in text.splitlines():
        ref_match = re.search(r"\b(?:ref(?:erence)?)[\s.:=-]*([^|;,]+)", line, re.IGNORECASE)
        qty_match = re.search(r"\b(?:qty|quantit[eé])[\s.:=x-]*(\d+)", line, re.IGNORECASE)
        if ref_match:
            reference = ref_match.group(1).strip()
            if reference:
                result.append({"ref": reference, "qty": max(1, int(qty_match.group(1))) if qty_match else 1})
    if result:
        return result
    # Legacy rows sometimes contain only comma-separated references.
    return [
        {"ref": token.strip(), "qty": 1}
        for token in re.split(r"[,;]", text)
        if token.strip()
    ]


def parse_included_parts(value: Any) -> dict[str, dict[str, Any]]:
    """Return included references keyed by a normalized reference."""
    if not value:
        return {}
    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        payload = [token.strip() for token in re.split(r"[,;]", str(value)) if token.strip()]
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in payload:
        if isinstance(item, str):
            reference, quota, designation = item, None, ""
        elif isinstance(item, dict):
            reference = item.get("ref") or item.get("reference") or ""
            designation = item.get("designation") or ""
            raw_quota = item.get("quota")
            try:
                quota = int(raw_quota) if raw_quota not in (None, "", -1, "-1") else None
            except (TypeError, ValueError):
                quota = None
        else:
            continue
        if reference:
            result[_key(reference)] = {
                "ref": str(reference).strip(),
                "designation": str(designation).strip(),
                "quota": quota,
            }
    return result


def infer_contract_scope(
    contract: dict[str, Any], *, linked_from_planning: bool, intervention_type: str = ""
) -> dict[str, Any]:
    """Infer coverage from explicit contract data and the scheduled link."""
    contract_type = _key(contract.get("type_contrat"))
    # « Premium » is kept as a legacy synonym for old contracts. New contracts
    # use one of the explicit billing scopes exposed by the UI.
    full_service = any(token in contract_type for token in ("full service", "full risk", "premium"))
    labor_only = "main" in contract_type and "oeuvre" in contract_type
    parts_only = "pieces uniquement" in contract_type
    corrective_match = "corrective" in contract_type and "corrective" in _key(intervention_type)
    included_parts = parse_included_parts(contract.get("pieces_incluses"))
    parts_enabled = full_service or parts_only or bool(contract.get("avec_pieces")) or bool(included_parts)
    # A preventive recurrence covers the generated planning occurrences, not
    # arbitrary extra visits on the same equipment. Corrective/full-service
    # contracts may cover an ad-hoc corrective intervention.
    labor_covered = full_service or labor_only or linked_from_planning or corrective_match
    return {
        "labor": labor_covered,
        "parts": parts_enabled,
        "all_parts": full_service or (parts_enabled and not included_parts),
        "included_parts": included_parts,
    }


def assess_contract_coverage(
    *,
    labor_amount: Any,
    parts_amount: Any,
    used_parts: list[dict[str, Any]],
    contract: dict[str, Any] | None,
    linked_from_planning: bool = False,
    previous_part_usage: dict[str, int] | None = None,
    part_prices: dict[str, Any] | None = None,
    contract_valid: bool = True,
    equipment_covered: bool = True,
    intervention_limit_reached: bool = False,
    ambiguity_reason: str = "",
    intervention_type: str = "",
) -> dict[str, Any]:
    """Calculate covered and billable amounts without accessing the database."""
    labor = _money(labor_amount)
    parts = _money(parts_amount)
    previous_part_usage = {_key(key): int(value or 0) for key, value in (previous_part_usage or {}).items()}
    part_prices = {_key(key): _money(value) for key, value in (part_prices or {}).items()}

    if ambiguity_reason:
        return _result("review", None, labor, parts, labor, parts, ambiguity_reason, {})
    if not contract:
        return _result("billable", None, labor, parts, labor, parts, "Aucun contrat applicable à la date de l’intervention.", {})
    contract_id = contract.get("id")
    if not contract_valid:
        return _result("billable", contract_id, labor, parts, labor, parts, "Le contrat est inactif ou hors de sa période de validité.", {})
    if not equipment_covered:
        return _result("billable", contract_id, labor, parts, labor, parts, "L’équipement n’est pas couvert par ce contrat.", {})
    if intervention_limit_reached:
        return _result("billable", contract_id, labor, parts, labor, parts, "Le nombre d’interventions incluses est dépassé.", {})

    scope = infer_contract_scope(
        contract,
        linked_from_planning=linked_from_planning,
        intervention_type=intervention_type,
    )
    uncovered_labor_cost = Decimal("0") if scope["labor"] else labor
    uncovered_parts_cost = parts
    part_details: list[dict[str, Any]] = []
    has_parts_component = bool(used_parts) or parts > 0
    any_parts_covered = False
    all_parts_covered = not has_parts_component
    cost_allocation_incomplete = False

    if scope["parts"] and has_parts_component:
        if scope["all_parts"]:
            uncovered_parts_cost = Decimal("0")
            any_parts_covered = True
            all_parts_covered = True
            part_details = [
                {"ref": item.get("ref", ""), "qty": int(item.get("qty") or 1), "covered_qty": int(item.get("qty") or 1)}
                for item in used_parts
            ]
        elif used_parts:
            all_parts_covered = True
            covered_value = Decimal("0")
            covered_price_missing = False
            for item in used_parts:
                reference = str(item.get("ref") or "").strip()
                ref_key = _key(reference)
                qty = max(1, int(item.get("qty") or 1))
                included = scope["included_parts"].get(ref_key)
                covered_qty = 0
                if included:
                    quota = included.get("quota")
                    remaining = qty if quota is None else max(0, int(quota) - previous_part_usage.get(ref_key, 0))
                    covered_qty = min(qty, remaining)
                any_parts_covered = any_parts_covered or covered_qty > 0
                all_parts_covered = all_parts_covered and covered_qty == qty
                price = part_prices.get(ref_key)
                if covered_qty and price is not None:
                    covered_value += price * covered_qty
                elif covered_qty:
                    covered_price_missing = True
                part_details.append({
                    "ref": reference,
                    "qty": qty,
                    "covered_qty": covered_qty,
                    "quota": included.get("quota") if included else None,
                    "used_before": previous_part_usage.get(ref_key, 0),
                })
            if all_parts_covered:
                uncovered_parts_cost = Decimal("0")
            elif any_parts_covered and covered_price_missing:
                # Eligibility is still known from references and quantities.
                # Only the internal-cost split remains conservative.
                cost_allocation_incomplete = True
            elif any_parts_covered:
                uncovered_parts_cost = max(Decimal("0"), parts - covered_value)
    elif has_parts_component:
        part_details = [
            {"ref": item.get("ref", ""), "qty": int(item.get("qty") or 1), "covered_qty": 0}
            for item in used_parts
        ]

    uncovered_total_cost = uncovered_labor_cost + uncovered_parts_cost
    any_component_covered = bool(scope["labor"]) or any_parts_covered
    any_component_uncovered = (not bool(scope["labor"])) or (has_parts_component and not all_parts_covered)
    if not any_component_uncovered:
        status = "covered"
        reason = "La main-d’œuvre et les pièces utilisées sont couvertes par le contrat."
    elif any_component_covered:
        status = "partial"
        reason = "Seuls les éléments hors couverture contractuelle sont facturables."
    else:
        status = "billable"
        reason = "Aucun composant de l’intervention n’est couvert par le contrat."
    return _result(
        status, contract_id, labor, parts, uncovered_labor_cost, uncovered_parts_cost, reason,
        {"parts": part_details, "cost_allocation_incomplete": cost_allocation_incomplete},
    )


def _result(
    status: str,
    contract_id: Any,
    labor: Decimal,
    parts: Decimal,
    uncovered_labor_cost: Decimal,
    uncovered_parts_cost: Decimal,
    reason: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "coverage_status": status,
        "coverage_status_label": COVERAGE_LABELS[status],
        "contract_id": contract_id,
        "labor_amount": float(labor),
        "parts_amount": float(parts),
        # These values remain cost-of-service figures.  They identify the
        # internal cost exposed outside the contract, never a customer price.
        "uncovered_labor_cost": float(_money(uncovered_labor_cost)),
        "uncovered_parts_cost": float(_money(uncovered_parts_cost)),
        "uncovered_total_cost": float(_money(uncovered_labor_cost) + _money(uncovered_parts_cost)),
        "coverage_reason": reason,
        "coverage_details": details,
    }


def _contract_row(conn: Any, contract_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM contrats WHERE id=%s", (contract_id,)).fetchone()
    return dict(row) if row else None


def _equipment_is_covered(
    conn: Any,
    contract: dict[str, Any],
    equipment_id: Any,
    machine: str,
    client: str,
) -> bool:
    if equipment_id is not None:
        row = conn.execute(
            "SELECT 1 FROM contrats_equipements WHERE contrat_id = %s AND equipement_id = %s",
            (contract["id"], equipment_id),
        ).fetchone()
        if row:
            return True
        linked_equipment = conn.execute(
            "SELECT 1 FROM contrats_equipements WHERE contrat_id = %s LIMIT 1",
            (contract["id"],),
        ).fetchone()
        if linked_equipment:
            return False
        # A legacy single-equipment contract has no junction row, so its text
        # fallback remains necessary until that contract is migrated.
        legacy_equipment = str(contract.get("equipement") or "").strip()
        return bool(legacy_equipment and _key(legacy_equipment) == _key(machine))
    row = conn.execute(
        """SELECT 1
           FROM contrats_equipements ce
           JOIN equipements e ON e.id=ce.equipement_id
           WHERE ce.contrat_id=%s
             AND LOWER(BTRIM(e.nom))=LOWER(BTRIM(%s))
             AND (NULLIF(BTRIM(%s), '') IS NULL OR LOWER(BTRIM(e.client))=LOWER(BTRIM(%s)))
           LIMIT 1""",
        (contract["id"], machine, client, client),
    ).fetchone()
    if row:
        return True
    legacy_equipment = str(contract.get("equipement") or "").strip()
    return bool(legacy_equipment and _key(legacy_equipment) == _key(machine))


def _candidate_contracts(conn: Any, intervention: dict[str, Any], service_date: date) -> list[dict[str, Any]]:
    equipment_id = intervention.get("equipement_id")
    if equipment_id is not None:
        rows = conn.execute(
            """SELECT DISTINCT c.*
               FROM contrats c
               JOIN contrats_equipements ce ON ce.contrat_id = c.id
               WHERE LOWER(BTRIM(c.client)) = LOWER(BTRIM(%s))
                 AND %s BETWEEN c.date_debut AND c.date_fin
                 AND LOWER(BTRIM(c.statut)) IN ('actif', 'active')
                 AND ce.equipement_id = %s
               ORDER BY c.date_fin DESC, c.id DESC""",
            (intervention.get("client") or "", service_date, equipment_id),
        ).fetchall()
        return [dict(row) for row in rows]
    rows = conn.execute(
        """SELECT DISTINCT c.*
           FROM contrats c
           LEFT JOIN contrats_equipements ce ON ce.contrat_id=c.id
           LEFT JOIN equipements e ON e.id=ce.equipement_id
           WHERE LOWER(BTRIM(c.client))=LOWER(BTRIM(%s))
             AND %s BETWEEN c.date_debut AND c.date_fin
             AND LOWER(BTRIM(c.statut)) IN ('actif', 'active')
             AND (
                 (LOWER(BTRIM(e.nom))=LOWER(BTRIM(%s)) AND LOWER(BTRIM(e.client))=LOWER(BTRIM(%s)))
                 OR LOWER(BTRIM(COALESCE(c.equipement, '')))=LOWER(BTRIM(%s))
             )
           ORDER BY c.date_fin DESC, c.id DESC""",
        (intervention.get("client") or "", service_date, intervention.get("machine") or "", intervention.get("client") or "", intervention.get("machine") or ""),
    ).fetchall()
    return [dict(row) for row in rows]


def assess_intervention_contract_coverage(conn: Any, intervention_id: int, *, actor: str = "system") -> dict[str, Any]:
    """Resolve the applicable contract, assess coverage, and persist a snapshot."""
    row = conn.execute(
        """SELECT i.id, i.client, i.machine, i.equipement_id, i.type_intervention, i.date,
                  i.date_cloture, i.planning_id, COALESCE(i.cout, 0) AS labor_amount,
                  COALESCE(i.cout_pieces, 0) AS parts_amount, i.pieces_utilisees,
                  COALESCE(pm.contrat_id, original_pm.contrat_id) AS planning_contract_id
           FROM interventions i
           LEFT JOIN planning_maintenance pm ON pm.id=i.planning_id
           LEFT JOIN planning_maintenance original_pm ON original_pm.id=pm.original_planning_id
           WHERE i.id=%s""",
        (intervention_id,),
    ).fetchone()
    if not row:
        raise ValueError("Intervention introuvable")
    intervention = dict(row)
    service_date = _as_date(intervention.get("date_cloture")) or _as_date(intervention.get("date")) or date.today()
    linked_from_planning = bool(intervention.get("planning_contract_id"))
    ambiguity_reason = ""
    contract = None
    if linked_from_planning:
        contract = _contract_row(conn, int(intervention["planning_contract_id"]))
    else:
        candidates = _candidate_contracts(conn, intervention, service_date)
        if len(candidates) == 1:
            contract = candidates[0]
        elif len(candidates) > 1:
            ambiguity_reason = "Plusieurs contrats valides couvrent cet équipement; sélection manuelle requise."

    contract_valid = True
    equipment_covered = True
    limit_reached = False
    previous_usage: dict[str, int] = {}
    part_prices: dict[str, Any] = {}
    used_parts = parse_used_parts(intervention.get("pieces_utilisees"))
    if used_parts:
        refs = [item["ref"] for item in used_parts]
        price_rows = conn.execute(
            "SELECT reference, prix_unitaire FROM pieces_rechange WHERE LOWER(reference)=ANY(%s)",
            ([_key(ref) for ref in refs],),
        ).fetchall()
        part_prices = {str(item["reference"]): item.get("prix_unitaire") for item in price_rows}

    if contract:
        start = _as_date(contract.get("date_debut"))
        end = _as_date(contract.get("date_fin"))
        contract_valid = (
            _key(contract.get("statut")) in {"actif", "active"}
            and (start is None or service_date >= start)
            and (end is None or service_date <= end)
        )
        equipment_covered = _equipment_is_covered(
            conn,
            contract,
            intervention.get("equipement_id"),
            str(intervention.get("machine") or ""),
            str(intervention.get("client") or ""),
        )
        raw_limit = contract.get("interventions_incluses")
        included_limit = int(raw_limit) if raw_limit not in (None, "") else -1
        if included_limit >= 0:
            count_row = conn.execute(
                """SELECT COUNT(DISTINCT i.id) AS used
                   FROM interventions i
                   LEFT JOIN planning_maintenance pm ON pm.id=i.planning_id
                   LEFT JOIN planning_maintenance original_pm ON original_pm.id=pm.original_planning_id
                   LEFT JOIN billing_cases bc ON bc.intervention_id=i.id
                   WHERE i.id<>%s AND i.statut IN ('Cloturee', 'Clôturée')
                     AND (bc.contract_id=%s OR COALESCE(pm.contrat_id, original_pm.contrat_id)=%s)""",
                (intervention_id, contract["id"], contract["id"]),
            ).fetchone()
            limit_reached = int(count_row.get("used") or 0) >= included_limit
        usage_rows = conn.execute(
            """SELECT i.pieces_utilisees
               FROM interventions i
               LEFT JOIN planning_maintenance pm ON pm.id=i.planning_id
               LEFT JOIN planning_maintenance original_pm ON original_pm.id=pm.original_planning_id
               LEFT JOIN billing_cases bc ON bc.intervention_id=i.id
               WHERE i.id<>%s AND i.statut IN ('Cloturee', 'Clôturée')
                 AND (bc.contract_id=%s OR COALESCE(pm.contrat_id, original_pm.contrat_id)=%s)""",
            (intervention_id, contract["id"], contract["id"]),
        ).fetchall()
        for usage_row in usage_rows:
            for item in parse_used_parts(usage_row.get("pieces_utilisees")):
                ref_key = _key(item.get("ref"))
                previous_usage[ref_key] = previous_usage.get(ref_key, 0) + int(item.get("qty") or 1)

    result = assess_contract_coverage(
        labor_amount=intervention.get("labor_amount"),
        parts_amount=intervention.get("parts_amount"),
        used_parts=used_parts,
        contract=contract,
        linked_from_planning=linked_from_planning,
        previous_part_usage=previous_usage,
        part_prices=part_prices,
        contract_valid=contract_valid,
        equipment_covered=equipment_covered,
        intervention_limit_reached=limit_reached,
        ambiguity_reason=ambiguity_reason,
        intervention_type=str(intervention.get("type_intervention") or ""),
    )
    result["contract_type"] = contract.get("type_contrat") if contract else ""
    result["service_date"] = service_date.isoformat()

    case_row = conn.execute(
        "SELECT id, coverage_status, contract_id, uncovered_total_cost FROM billing_cases WHERE intervention_id=%s",
        (intervention_id,),
    ).fetchone()
    if not case_row:
        case_row = conn.execute(
            """INSERT INTO billing_cases (intervention_id, client, equipment, created_by, updated_by)
               VALUES (%s, %s, %s, %s, %s) RETURNING id, coverage_status, contract_id, uncovered_total_cost""",
            (intervention_id, intervention.get("client") or "", intervention.get("machine") or "", actor, actor),
        ).fetchone()
    before = dict(case_row)
    conn.execute(
        """UPDATE billing_cases SET
               contract_id=%s, coverage_status=%s, coverage_reason=%s,
               uncovered_labor_cost=%s, uncovered_parts_cost=%s,
               uncovered_total_cost=%s, coverage_details=%s::jsonb,
               coverage_assessed_at=CURRENT_TIMESTAMP, updated_by=%s,
               updated_at=CURRENT_TIMESTAMP
           WHERE id=%s""",
        (
            result.get("contract_id"), result["coverage_status"], result["coverage_reason"],
            result["uncovered_labor_cost"], result["uncovered_parts_cost"],
            result["uncovered_total_cost"], json.dumps(result, ensure_ascii=False), actor,
            case_row["id"],
        ),
    )
    changed = (
        before.get("coverage_status") != result["coverage_status"]
        or before.get("contract_id") != result.get("contract_id")
        or _money(before.get("uncovered_total_cost")) != _money(result["uncovered_total_cost"])
    )
    if changed:
        conn.execute(
            """INSERT INTO billing_history (
                   case_id, action, entity_type, entity_id, before_data, after_data, actor_username
               ) VALUES (%s, 'ASSESS_CONTRACT_COVERAGE', 'case', %s, %s::jsonb, %s::jsonb, %s)""",
            (case_row["id"], case_row["id"], json.dumps(before, default=str), json.dumps(result, ensure_ascii=False), actor),
        )
    return result


def assess_intervention_contract_coverage_in_savepoint(
    conn: Any,
    intervention_id: int,
    *,
    actor: str = "system",
) -> dict[str, Any]:
    """Assess coverage without leaving the caller transaction aborted on failure.

    Operational closure and stock updates must remain valid even if the optional
    billing assessment encounters bad contract data or a future SQL regression.
    The caller may log the raised exception and continue using the transaction.
    """
    savepoint = "contract_coverage_assessment"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        result = assess_intervention_contract_coverage(conn, intervention_id, actor=actor)
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
    return result
