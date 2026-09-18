"""Operational quote-to-payment tracking routes."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from api.runtime import Body, Depends, HTTPException, Optional, app, get_db, log_audit
from api.security import _verify_token, require_roles
from services.billing_tracking import (
    NEXT_STEP,
    STATUS_LABELS,
    STEP_TYPES,
    compute_case_status,
    compute_lead_times,
    current_stage_age_days,
    invoice_is_overdue,
)
from services.contract_billing import (
    COVERAGE_LABELS,
    assess_intervention_contract_coverage,
)


BILLING_ROLES = ("Admin", "Manager", "Responsable Technique", "Gestionnaire")
AUTOMATIC_CASE_CREATORS = ("system", "system-migration")


@app.get("/api/billing/responsibles")
def list_billing_responsibles(user: dict = Depends(_verify_token)):
    """Return active users allowed to own a billing case."""
    require_roles(user, *BILLING_ROLES)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT username, COALESCE(NULLIF(BTRIM(nom_complet), ''), username) AS display_name, role
               FROM utilisateurs
               WHERE actif = 1 AND role IN (%s, %s, %s, %s)
               ORDER BY LOWER(COALESCE(NULLIF(BTRIM(nom_complet), ''), username)), username""",
            BILLING_ROLES,
        ).fetchall()
    return [_dict(row) for row in rows]


def _username(user: dict) -> str:
    return str(user.get("sub") or user.get("nom") or "unknown")


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _dict(row: Any) -> dict[str, Any]:
    return _json_value(dict(row)) if row else {}


def _parse_date(value: Any, field: str, *, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise HTTPException(status_code=422, detail=f"{field} est obligatoire")
        return None
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} doit être une date valide")
    return parsed


def _parse_amount(value: Any, field: str, *, required: bool = False) -> Decimal | None:
    if value in (None, ""):
        if required:
            raise HTTPException(status_code=422, detail=f"{field} est obligatoire")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail=f"{field} doit être un montant valide")
    if parsed < 0:
        raise HTTPException(status_code=422, detail=f"{field} ne peut pas être négatif")
    return parsed


def _validate_owner(conn, username: str) -> None:
    if not username:
        return
    row = conn.execute(
        """SELECT username FROM utilisateurs
           WHERE username=%s AND actif=1 AND role IN (%s, %s, %s, %s)""",
        (username, *BILLING_ROLES),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=422, detail="Le responsable doit être un utilisateur actif autorisé")


def _history(
    conn,
    case_id: int,
    action: str,
    entity_type: str,
    entity_id: int | None,
    actor: str,
    *,
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
) -> None:
    conn.execute(
        """INSERT INTO billing_history (
               case_id, action, entity_type, entity_id, before_data, after_data,
               change_reason, actor_username
           ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)""",
        (
            case_id,
            action,
            entity_type,
            entity_id,
            json.dumps(_json_value(before), ensure_ascii=False) if before is not None else None,
            json.dumps(_json_value(after), ensure_ascii=False) if after is not None else None,
            reason,
            actor,
        ),
    )


def _load_rows(conn, case_id: int | None = None) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = ()
    where = "WHERE bc.merged_into_case_id IS NULL"
    if case_id is not None:
        where = "WHERE bc.id = %s"
        params = (case_id,)
    rows = conn.execute(
        f"""SELECT bc.id, bc.intervention_id, bc.request_id, bc.merged_into_case_id,
                   COALESCE(NULLIF(bc.client, ''), NULLIF(i.client, ''), NULLIF(d.client, ''), NULLIF(pm.client, ''), e.client, '') AS client,
                   COALESCE(NULLIF(bc.equipment, ''), i.machine, '') AS equipment,
                   bc.owner_username, bc.currency, bc.case_state, bc.block_reason,
                   bc.contract_id, bc.coverage_status, bc.coverage_reason,
                   COALESCE(bc.uncovered_labor_cost, 0) AS uncovered_labor_cost,
                   COALESCE(bc.uncovered_parts_cost, 0) AS uncovered_parts_cost,
                   COALESCE(bc.uncovered_total_cost, 0) AS uncovered_total_cost,
                   bc.coverage_details, bc.coverage_assessed_at,
                   bc.created_by, bc.created_at, bc.updated_by, bc.updated_at,
                   i.statut AS intervention_status, i.technicien,
                   i.date AS intervention_date,
                   i.date_debut_intervention AS intervention_started_at,
                   i.date_cloture AS intervention_closed_at,
                   i.type_intervention AS intervention_type,
                   i.description AS intervention_description,
                   i.probleme AS intervention_problem,
                   i.cause AS intervention_cause,
                   i.solution AS intervention_solution,
                   i.code_erreur AS intervention_error_code,
                   i.type_erreur AS intervention_error_type,
                   i.priorite AS intervention_priority,
                   i.notes AS intervention_notes,
                   COALESCE(i.duree_minutes, 0) AS intervention_duration_minutes,
                   COALESCE(i.duree_deplacement, 0) AS intervention_travel_minutes,
                   i.start_time::text AS intervention_start_time,
                   i.end_time::text AS intervention_end_time,
                   i.pieces_utilisees, COALESCE(i.cout_pieces, 0) AS parts_amount,
                   COALESCE(i.cout, 0) AS labor_amount,
                   c.type_contrat AS contract_type,
                   COALESCE((
                       SELECT jsonb_agg(
                           jsonb_build_object(
                               'name', it.technicien_nom,
                               'duration_minutes', COALESCE(it.duree_minutes_tech, 0),
                               'travel_minutes', COALESCE(it.duree_deplacement_tech, 0),
                               'status', it.statut
                           ) ORDER BY it.technicien_nom
                       )
                       FROM interventions_techniciens it
                       WHERE it.intervention_id = i.id
                   ), '[]'::jsonb) AS intervention_technicians,
                   (COALESCE(i.cout_pieces, 0) > 0 OR
                    NULLIF(BTRIM(COALESCE(i.pieces_utilisees, '')), '') IS NOT NULL) AS has_parts
            FROM billing_cases bc
            LEFT JOIN interventions i ON i.id = bc.intervention_id
            LEFT JOIN LATERAL (
                SELECT di.client
                FROM demandes_intervention di
                WHERE di.id = bc.request_id OR di.intervention_id = bc.intervention_id
                ORDER BY CASE WHEN di.id = bc.request_id THEN 0 ELSE 1 END, di.id DESC
                LIMIT 1
            ) d ON TRUE
            LEFT JOIN planning_maintenance pm ON pm.id = i.planning_id
            LEFT JOIN equipements e ON e.id = i.equipement_id
            LEFT JOIN contrats c ON c.id=bc.contract_id
            {where}
            ORDER BY bc.updated_at DESC, bc.id DESC""",
        params,
    ).fetchall()
    if case_id is not None and not rows:
        raise HTTPException(status_code=404, detail="Dossier de facturation introuvable")
    return [_dict(row) for row in rows]


def _hydrate_cases(conn, base_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not base_rows:
        return []
    case_ids = [row["id"] for row in base_rows]
    step_rows = conn.execute(
        """SELECT * FROM billing_steps
           WHERE case_id = ANY(%s)
           ORDER BY effective_date NULLS LAST, id""",
        (case_ids,),
    ).fetchall()
    payment_rows = conn.execute(
        """SELECT * FROM billing_payments
           WHERE case_id = ANY(%s)
           ORDER BY effective_date, id""",
        (case_ids,),
    ).fetchall()
    steps_by_case: dict[int, dict[str, dict[str, Any]]] = {case_id: {} for case_id in case_ids}
    payments_by_case: dict[int, list[dict[str, Any]]] = {case_id: [] for case_id in case_ids}
    for raw in step_rows:
        item = _dict(raw)
        steps_by_case[item["case_id"]][item["step_type"]] = item
    for raw in payment_rows:
        item = _dict(raw)
        payments_by_case[item["case_id"]].append(item)

    result = []
    today = date.today()
    for item in base_rows:
        steps = steps_by_case[item["id"]]
        payments = payments_by_case[item["id"]]
        paid_amount = sum(Decimal(str(payment["amount"])) for payment in payments)
        invoice = steps.get("invoice")
        invoice_amount = Decimal(str(invoice["amount"])) if invoice and invoice.get("amount") is not None else Decimal("0")
        remaining = max(Decimal("0"), invoice_amount - paid_amount)
        status = compute_case_status(
            case_state=item["case_state"],
            steps=steps,
            paid_amount=paid_amount,
            intervention_started_at=item.get("intervention_started_at"),
            intervention_closed_at=item.get("intervention_closed_at"),
            intervention_status=item.get("intervention_status") or "",
            has_parts=bool(item.get("has_parts")),
            coverage_status=item.get("coverage_status") or "unassessed",
        )
        overdue = invoice_is_overdue(invoice, remaining, today)
        due_date = _parse_date((invoice or {}).get("due_date"), "date d'échéance")
        item.update({
            "steps": steps,
            "payments": payments,
            "paid_amount": float(paid_amount),
            "invoice_amount": float(invoice_amount),
            "remaining_amount": float(remaining),
            "status": status,
            "status_label": STATUS_LABELS[status],
            "coverage_status_label": COVERAGE_LABELS.get(
                item.get("coverage_status") or "unassessed",
                COVERAGE_LABELS["unassessed"],
            ),
            "next_step": NEXT_STEP[status],
            "overdue": overdue,
            "overdue_days": (today - due_date).days if overdue and due_date else 0,
            "stage_age_days": current_stage_age_days(
                status,
                steps=steps,
                created_at=item.get("created_at"),
                intervention_started_at=item.get("intervention_started_at"),
                intervention_closed_at=item.get("intervention_closed_at"),
                today=today,
            ),
            "lead_times": compute_lead_times(
                steps,
                payments,
                item.get("intervention_started_at"),
                item.get("intervention_closed_at"),
            ),
            "data_incomplete": bool(invoice and (
                not invoice.get("effective_date")
                or not invoice.get("due_date")
                or invoice.get("amount") is None
                or not str(invoice.get("reference") or "").strip()
            )),
        })
        result.append(item)
    return result


def _load_case(conn, case_id: int) -> dict[str, Any]:
    return _hydrate_cases(conn, _load_rows(conn, case_id))[0]


def _cleanup_orphan_automatic_cases(conn) -> None:
    """Delete traceability cases whose source intervention no longer exists."""
    conn.execute(
        """DELETE FROM billing_cases
           WHERE intervention_id IS NULL
             AND created_by IN (%s, %s)""",
        AUTOMATIC_CASE_CREATORS,
    )


def _sync_missing_intervention_cases(conn) -> None:
    _cleanup_orphan_automatic_cases(conn)
    conn.execute(
        """UPDATE billing_cases bc
           SET request_id = d.id, updated_at = CURRENT_TIMESTAMP
           FROM demandes_intervention d
           WHERE d.intervention_id = bc.intervention_id
             AND bc.request_id IS NULL
             AND NOT EXISTS (
                 SELECT 1 FROM billing_cases other
                 WHERE other.request_id = d.id AND other.id <> bc.id
             )"""
    )
    conn.execute(
        """WITH inserted AS (
               INSERT INTO billing_cases (
                   intervention_id, request_id, client, equipment, created_by, updated_by
               )
               SELECT i.id, d.id, COALESCE(NULLIF(i.client, ''), e.client, ''), i.machine,
                      'system', 'system'
               FROM interventions i
               LEFT JOIN equipements e ON e.id = i.equipement_id
               LEFT JOIN demandes_intervention d ON d.intervention_id = i.id
               WHERE COALESCE(i.is_temporary, 0) = 0
               ON CONFLICT (intervention_id) DO NOTHING
               RETURNING id, intervention_id, client, equipment
           )
           INSERT INTO billing_history (
               case_id, action, entity_type, entity_id, after_data, actor_username
           )
           SELECT id, 'SYNC_MISSING_CASE', 'case', id,
                  jsonb_build_object(
                      'intervention_id', intervention_id,
                      'client', client,
                      'equipment', equipment
                  ),
                  'system'
           FROM inserted"""
    )


def _sync_contract_coverage(conn) -> None:
    """Assess legacy and unresolved closed interventions lazily and safely."""
    rows = conn.execute(
        """SELECT bc.intervention_id
           FROM billing_cases bc
           JOIN interventions i ON i.id=bc.intervention_id
           WHERE i.statut IN ('Cloturee', 'Clôturée')
             AND bc.merged_into_case_id IS NULL
             AND (bc.coverage_assessed_at IS NULL OR bc.coverage_status IN ('unassessed', 'review'))
           ORDER BY i.date_cloture DESC NULLS LAST
           LIMIT 500"""
    ).fetchall()
    for row in rows:
        assess_intervention_contract_coverage(conn, int(row["intervention_id"]))


@app.get("/api/billing/cases")
def list_billing_cases(
    status: Optional[str] = None,
    client: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    require_roles(user, *BILLING_ROLES)
    with get_db() as conn:
        _sync_missing_intervention_cases(conn)
        _sync_contract_coverage(conn)
        cases = _hydrate_cases(conn, _load_rows(conn))
    if status:
        cases = [item for item in cases if item["status"] == status]
    if client:
        wanted = client.strip().casefold()
        cases = [item for item in cases if str(item["client"]).strip().casefold() == wanted]
    if search:
        needle = search.strip().casefold()
        cases = [
            item for item in cases
            if needle in " ".join((
                str(item["id"]), str(item.get("client") or ""),
                str(item.get("equipment") or ""), str(item.get("technicien") or ""),
                str((item.get("steps", {}).get("invoice") or {}).get("reference") or ""),
            )).casefold()
        ]
    return cases


@app.get("/api/billing/cases/{case_id}")
def get_billing_case(case_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, *BILLING_ROLES)
    with get_db() as conn:
        _cleanup_orphan_automatic_cases(conn)
        return _load_case(conn, case_id)


@app.delete("/api/billing/cases/{case_id}")
def delete_billing_case(case_id: int, user: dict = Depends(_verify_token)):
    """Delete a billing-only case created manually from the billing page."""
    require_roles(user, "Admin", "Manager")
    actor = _username(user)
    with get_db() as conn:
        case = conn.execute(
            """SELECT id, intervention_id, created_by, client, equipment
               FROM billing_cases
               WHERE id = %s
               FOR UPDATE""",
            (case_id,),
        ).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail="Dossier de facturation introuvable")
        if case["created_by"] in AUTOMATIC_CASE_CREATORS:
            raise HTTPException(
                status_code=409,
                detail="Ce dossier est automatique. Supprimez l'intervention ou le contrat associé.",
            )
        replacement_case_id = None
        intervention_id = case["intervention_id"]
        if intervention_id:
            intervention = conn.execute(
                """SELECT i.id,
                          COALESCE(NULLIF(i.client, ''), e.client, %s) AS client,
                          i.machine,
                          (SELECT d.id
                           FROM demandes_intervention d
                           WHERE d.intervention_id = i.id
                           ORDER BY d.id DESC
                           LIMIT 1) AS request_id
                   FROM interventions i
                   LEFT JOIN equipements e ON e.id = i.equipement_id
                   WHERE i.id = %s""",
                (case["client"] or "", intervention_id),
            ).fetchone()
        else:
            intervention = None
        replacement_request_id = intervention["request_id"] if intervention else None
        if replacement_request_id:
            request_owner = conn.execute(
                """SELECT id
                   FROM billing_cases
                   WHERE request_id = %s AND id <> %s
                   LIMIT 1""",
                (replacement_request_id, case_id),
            ).fetchone()
            if request_owner:
                replacement_request_id = None
        conn.execute("DELETE FROM billing_cases WHERE id = %s", (case_id,))
        if intervention:
            replacement = conn.execute(
                """INSERT INTO billing_cases (
                       intervention_id, request_id, client, equipment, created_by, updated_by
                   ) VALUES (%s, %s, %s, %s, 'system', 'system')
                   ON CONFLICT (intervention_id) DO UPDATE SET
                       request_id = COALESCE(billing_cases.request_id, EXCLUDED.request_id),
                       client = CASE WHEN NULLIF(BTRIM(billing_cases.client), '') IS NULL
                                     THEN EXCLUDED.client ELSE billing_cases.client END,
                       equipment = CASE WHEN NULLIF(BTRIM(billing_cases.equipment), '') IS NULL
                                        THEN EXCLUDED.equipment ELSE billing_cases.equipment END,
                       updated_at = CURRENT_TIMESTAMP
                   RETURNING id""",
                (intervention["id"], replacement_request_id, intervention["client"], intervention["machine"]),
            ).fetchone()
            replacement_case_id = replacement["id"] if replacement else None
            if replacement_case_id:
                conn.execute(
                    """INSERT INTO billing_history (
                           case_id, action, entity_type, entity_id, after_data, actor_username
                       ) VALUES (
                           %s, 'RECREATE_AUTOMATIC_CASE', 'case', %s,
                           jsonb_build_object('intervention_id', %s, 'source_case_id', %s), %s
                       )""",
                    (replacement_case_id, replacement_case_id, intervention["id"], case_id, actor),
                )
    log_audit(actor, "DELETE_BILLING_CASE", json.dumps({"case_id": case_id}), "facturation")
    return {"ok": True, "case_id": case_id, "replacement_case_id": replacement_case_id}


@app.post("/api/billing/cases/{case_id}/reassess-coverage")
def reassess_billing_coverage(case_id: int, user: dict = Depends(_verify_token)):
    """Recalculate coverage after a contract or intervention correction."""
    require_roles(user, *BILLING_ROLES)
    actor = _username(user)
    with get_db() as conn:
        case = _load_case(conn, case_id)
        if not case.get("intervention_id"):
            raise HTTPException(status_code=409, detail="Associez d'abord une intervention au dossier")
        assess_intervention_contract_coverage(conn, int(case["intervention_id"]), actor=actor)
        result = _load_case(conn, case_id)
    log_audit(actor, "REASSESS_CONTRACT_COVERAGE", json.dumps({"case_id": case_id}), "facturation")
    return result


@app.post("/api/billing/cases")
def create_billing_case(body: dict = Body(...), user: dict = Depends(_verify_token)):
    require_roles(user, *BILLING_ROLES)
    actor = _username(user)
    client = str(body.get("client") or "").strip()
    equipment = str(body.get("equipment") or "").strip()
    intervention_id = body.get("intervention_id") or None
    request_id = body.get("request_id") or None
    currency = str(body.get("currency") or "TND").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(status_code=422, detail="La devise doit contenir trois lettres")
    with get_db() as conn:
        if intervention_id:
            intervention = conn.execute(
                """SELECT i.id, COALESCE(NULLIF(i.client, ''), e.client, '') AS client,
                          i.machine
                   FROM interventions i
                   LEFT JOIN equipements e ON e.id = i.equipement_id
                   WHERE i.id = %s""",
                (intervention_id,),
            ).fetchone()
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention introuvable")
            existing = conn.execute(
                "SELECT id FROM billing_cases WHERE intervention_id = %s",
                (intervention_id,),
            ).fetchone()
            if existing:
                return _load_case(conn, existing["id"])
            client = client or intervention["client"]
            equipment = equipment or intervention["machine"]
        if not client:
            raise HTTPException(status_code=422, detail="Le client est obligatoire")
        if equipment:
            duplicate_key = f"{client.casefold()}::{equipment.casefold()}"
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (duplicate_key,))
            existing_open_case = conn.execute(
                """SELECT bc.id
                   FROM billing_cases bc
                   LEFT JOIN interventions i ON i.id = bc.intervention_id
                   WHERE LOWER(BTRIM(bc.client)) = LOWER(BTRIM(%s))
                     AND LOWER(BTRIM(bc.equipment)) = LOWER(BTRIM(%s))
                     AND bc.merged_into_case_id IS NULL
                     AND bc.case_state <> 'cancelled'
                     AND (
                         (
                             bc.intervention_id IS NOT NULL
                             AND i.date_cloture IS NULL
                             AND COALESCE(i.statut, '') !~* '(résol|resol|réalis|realis|clôt|clot|termin|annul)'
                         )
                         OR (
                             bc.intervention_id IS NULL
                             AND NOT EXISTS (
                                 SELECT 1 FROM billing_steps bs
                                 WHERE bs.case_id = bc.id AND bs.step_type = 'invoice'
                             )
                         )
                     )
                   ORDER BY bc.updated_at DESC, bc.id DESC
                   LIMIT 1
                   FOR UPDATE OF bc""",
                (client, equipment),
            ).fetchone()
            if existing_open_case:
                existing = _load_case(conn, existing_open_case["id"])
                existing["reused_existing_case"] = True
                return existing
        owner_username = str(body.get("owner_username") or actor).strip()
        _validate_owner(conn, owner_username)
        row = conn.execute(
            """INSERT INTO billing_cases (
                   intervention_id, request_id, client, equipment, owner_username,
                   currency, created_by, updated_by
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                intervention_id, request_id, client, equipment,
                owner_username, currency, actor, actor,
            ),
        ).fetchone()
        case = _load_case(conn, row["id"])
        _history(conn, row["id"], "CREATE_CASE", "case", row["id"], actor, after=case)
    log_audit(actor, "CREATE_BILLING_CASE", json.dumps({"case_id": row["id"], "client": client}, ensure_ascii=False), "facturation")
    return case


@app.patch("/api/billing/cases/{case_id}")
def update_billing_case(case_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    require_roles(user, *BILLING_ROLES)
    actor = _username(user)
    reason = str(body.get("change_reason") or "").strip()
    with get_db() as conn:
        before = _load_case(conn, case_id)
        intervention_id = before.get("intervention_id")
        intervention_details = None
        if "intervention_id" in body:
            intervention_id = body.get("intervention_id") or None
            if intervention_id:
                intervention_details = conn.execute(
                    """SELECT i.id, COALESCE(NULLIF(i.client, ''), e.client, '') AS client,
                              i.machine, d.id AS request_id
                       FROM interventions i
                       LEFT JOIN equipements e ON e.id = i.equipement_id
                       LEFT JOIN demandes_intervention d ON d.intervention_id = i.id
                       WHERE i.id=%s""",
                    (intervention_id,),
                ).fetchone()
                if not intervention_details:
                    raise HTTPException(status_code=404, detail="Intervention introuvable")
                other_case = conn.execute(
                    "SELECT id FROM billing_cases WHERE intervention_id=%s AND id<>%s",
                    (intervention_id, case_id),
                ).fetchone()
                if other_case:
                    activity = conn.execute(
                        """SELECT
                               (SELECT COUNT(*) FROM billing_steps WHERE case_id=%s) +
                               (SELECT COUNT(*) FROM billing_payments WHERE case_id=%s) AS count""",
                        (other_case["id"], other_case["id"]),
                    ).fetchone()
                    if activity["count"]:
                        raise HTTPException(
                            status_code=409,
                            detail="L'intervention possède déjà un dossier renseigné",
                        )
                    conn.execute("DELETE FROM billing_cases WHERE id=%s", (other_case["id"],))
        values = {
            "client": str(body.get("client", intervention_details["client"] if intervention_details else before["client"])).strip(),
            "equipment": str(body.get("equipment", intervention_details["machine"] if intervention_details else before["equipment"])).strip(),
            "intervention_id": intervention_id,
            "request_id": intervention_details["request_id"] if intervention_details else (before.get("request_id") if intervention_id else None),
            "owner_username": str(body.get("owner_username", before["owner_username"])).strip(),
            "currency": str(body.get("currency", before["currency"])).strip().upper(),
            "case_state": str(body.get("case_state", before["case_state"])).strip(),
            "block_reason": str(body.get("block_reason", before["block_reason"])).strip(),
        }
        if values["case_state"] not in {"active", "blocked", "cancelled"}:
            raise HTTPException(status_code=422, detail="État de dossier invalide")
        if values["case_state"] in {"blocked", "cancelled"} and not values["block_reason"]:
            raise HTTPException(status_code=422, detail="Un motif est obligatoire")
        if not values["client"]:
            raise HTTPException(status_code=422, detail="Le client est obligatoire")
        _validate_owner(conn, values["owner_username"])
        if len(values["currency"]) != 3 or not values["currency"].isalpha():
            raise HTTPException(status_code=422, detail="La devise doit contenir trois lettres")
        changed = any(values[key] != before.get(key) for key in values)
        if changed and not reason:
            raise HTTPException(status_code=422, detail="Le motif de modification est obligatoire")
        conn.execute(
            """UPDATE billing_cases SET
                   client=%s, equipment=%s, intervention_id=%s, request_id=%s, owner_username=%s, currency=%s,
                   case_state=%s, block_reason=%s, updated_by=%s,
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=%s""",
            (*values.values(), actor, case_id),
        )
        after = _load_case(conn, case_id)
        if changed:
            _history(conn, case_id, "UPDATE_CASE", "case", case_id, actor, before=before, after=after, reason=reason)
    return after


@app.post("/api/billing/cases/resolve-duplicate")
def resolve_duplicate_billing_case(body: dict = Body(...), user: dict = Depends(_verify_token)):
    """Archive an empty duplicate case and cancel its accidental intervention."""
    require_roles(user, "Admin", "Manager")
    actor = _username(user)
    try:
        keep_case_id = int(body.get("keep_case_id"))
        duplicate_case_id = int(body.get("duplicate_case_id"))
        intervention_case_id = int(body.get("intervention_case_id") or keep_case_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Identifiants de dossiers invalides")
    if keep_case_id <= 0 or duplicate_case_id <= 0 or keep_case_id == duplicate_case_id:
        raise HTTPException(status_code=422, detail="Deux dossiers distincts sont obligatoires")
    if intervention_case_id not in {keep_case_id, duplicate_case_id}:
        raise HTTPException(status_code=422, detail="L'intervention à conserver doit appartenir à l'un des dossiers")

    reason = str(body.get("reason") or "Doublon confirmé").strip()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, request_id, intervention_id, client, equipment, case_state,
                      merged_into_case_id
               FROM billing_cases
               WHERE id = ANY(%s)
               ORDER BY id
               FOR UPDATE""",
            ([keep_case_id, duplicate_case_id],),
        ).fetchall()
        cases = {row["id"]: row for row in rows}
        if len(cases) != 2:
            raise HTTPException(status_code=404, detail="Un des dossiers est introuvable")
        keep_case = cases[keep_case_id]
        duplicate_case = cases[duplicate_case_id]
        if keep_case.get("merged_into_case_id") or duplicate_case.get("merged_into_case_id"):
            raise HTTPException(status_code=409, detail="Un des dossiers a déjà été fusionné")
        if str(keep_case.get("client") or "").strip().casefold() != str(duplicate_case.get("client") or "").strip().casefold():
            raise HTTPException(status_code=409, detail="Les dossiers ne concernent pas le même client")
        if str(keep_case.get("equipment") or "").strip().casefold() != str(duplicate_case.get("equipment") or "").strip().casefold():
            raise HTTPException(status_code=409, detail="Les dossiers ne concernent pas le même équipement")

        duplicate_activity = conn.execute(
            """SELECT
                   (SELECT COUNT(*) FROM billing_steps WHERE case_id = %s) AS steps,
                   (SELECT COUNT(*) FROM billing_payments WHERE case_id = %s) AS payments""",
            (duplicate_case_id, duplicate_case_id),
        ).fetchone()
        if duplicate_activity["steps"] or duplicate_activity["payments"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Le dossier à archiver contient des documents ou paiements. "
                    "Choisissez-le comme dossier à conserver pour éviter toute perte."
                ),
            )

        intervention_source = cases[intervention_case_id]
        retained_request_id = intervention_source.get("request_id")
        retained_intervention_id = intervention_source.get("intervention_id")
        cancelled_source = duplicate_case if intervention_case_id == keep_case_id else keep_case
        cancelled_request_id = cancelled_source.get("request_id")
        cancelled_intervention_id = cancelled_source.get("intervention_id")

        cancelled_intervention = None
        if cancelled_intervention_id:
            cancelled_intervention = conn.execute(
                """SELECT id, statut, planning_id, date_debut_intervention, date_cloture,
                          duree_minutes, duree_deplacement, cause, solution, pieces_utilisees,
                          (SELECT COUNT(*) FROM interventions_techniciens it
                           WHERE it.intervention_id = i.id
                             AND (
                                 COALESCE(it.duree_minutes_tech, 0) > 0
                                 OR COALESCE(it.duree_deplacement_tech, 0) > 0
                                 OR NULLIF(BTRIM(COALESCE(it.probleme_tech, '')), '') IS NOT NULL
                                 OR NULLIF(BTRIM(COALESCE(it.cause_tech, '')), '') IS NOT NULL
                                 OR NULLIF(BTRIM(COALESCE(it.solution_tech, '')), '') IS NOT NULL
                             )) AS technician_work_count
                   FROM interventions i
                   WHERE i.id = %s
                   FOR UPDATE""",
                (cancelled_intervention_id,),
            ).fetchone()
            has_work = bool(cancelled_intervention and (
                cancelled_intervention.get("date_debut_intervention")
                or cancelled_intervention.get("date_cloture")
                or int(cancelled_intervention.get("duree_minutes") or 0) > 0
                or int(cancelled_intervention.get("duree_deplacement") or 0) > 0
                or str(cancelled_intervention.get("cause") or "").strip()
                or str(cancelled_intervention.get("solution") or "").strip()
                or str(cancelled_intervention.get("pieces_utilisees") or "").strip()
                or int(cancelled_intervention.get("technician_work_count") or 0) > 0
                or any(token in str(cancelled_intervention.get("statut") or "").casefold()
                       for token in ("cours", "atelier", "clot", "clôt", "termin"))
            ))
            if has_work:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "L'intervention qui serait annulée contient déjà du travail technicien. "
                        "Sélectionnez cette intervention comme intervention à conserver."
                    ),
                )

        before_keep = _load_case(conn, keep_case_id)
        before_duplicate = _load_case(conn, duplicate_case_id)

        # Clear both unique links first, then assign the retained pair to the
        # master case and the cancelled pair to the archived case.
        conn.execute(
            "UPDATE billing_cases SET request_id = NULL, intervention_id = NULL WHERE id = ANY(%s)",
            ([keep_case_id, duplicate_case_id],),
        )
        conn.execute(
            """UPDATE billing_cases
               SET request_id = %s, intervention_id = %s,
                   updated_by = %s, updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (retained_request_id, retained_intervention_id, actor, keep_case_id),
        )
        conn.execute(
            """UPDATE billing_cases
               SET request_id = %s, intervention_id = %s,
                   case_state = 'cancelled', block_reason = %s,
                   merged_into_case_id = %s,
                   updated_by = %s, updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (
                cancelled_request_id,
                cancelled_intervention_id,
                f"Doublon résolu dans le dossier #{keep_case_id}",
                keep_case_id,
                actor,
                duplicate_case_id,
            ),
        )

        if cancelled_request_id:
            conn.execute(
                """UPDATE demandes_intervention
                   SET statut = 'Annulée', date_traitement = CURRENT_TIMESTAMP,
                       notes_traitement = CONCAT(COALESCE(notes_traitement, ''), %s)
                   WHERE id = %s""",
                (f"\n[DOUBLON] Regroupée dans le dossier #{keep_case_id}", cancelled_request_id),
            )
        if cancelled_intervention_id:
            conn.execute(
                """UPDATE interventions
                   SET statut = 'Annulée',
                       notes = CONCAT(COALESCE(notes, ''), %s)
                   WHERE id = %s""",
                (f"\n[DOUBLON] Regroupée dans le dossier #{keep_case_id}", cancelled_intervention_id),
            )
            conn.execute(
                """UPDATE interventions_techniciens
                   SET statut = 'Refusé', updated_at = CURRENT_TIMESTAMP
                   WHERE intervention_id = %s""",
                (cancelled_intervention_id,),
            )
            planning_id = cancelled_intervention.get("planning_id") if cancelled_intervention else None
            if planning_id:
                conn.execute(
                    # planning_maintenance currently permits only its
                    # historical terminal value "Cloturee" (not "Annulée").
                    "UPDATE planning_maintenance SET statut = 'Cloturee', notes = CONCAT(COALESCE(notes, ''), %s) WHERE id = %s",
                    (f"\n[DOUBLON] Intervention annulée et regroupée dans le dossier #{keep_case_id}", planning_id),
                )

        after_keep = _load_case(conn, keep_case_id)
        after_duplicate = _load_case(conn, duplicate_case_id)
        _history(
            conn, keep_case_id, "RESOLVE_DUPLICATE", "case", duplicate_case_id, actor,
            before=before_keep, after=after_keep, reason=reason,
        )
        _history(
            conn, duplicate_case_id, "MERGED_AS_DUPLICATE", "case", duplicate_case_id, actor,
            before=before_duplicate, after=after_duplicate, reason=reason,
        )

    log_audit(
        actor,
        "RESOLVE_BILLING_DUPLICATE",
        json.dumps({
            "keep_case_id": keep_case_id,
            "duplicate_case_id": duplicate_case_id,
            "retained_intervention_id": retained_intervention_id,
            "cancelled_intervention_id": cancelled_intervention_id,
        }, ensure_ascii=False),
        "facturation",
    )
    return after_keep


def _validate_step_dates(conn, case_id: int, step_type: str, effective_date: date | None, due_date: date | None) -> None:
    if effective_date and effective_date > date.today():
        raise HTTPException(status_code=422, detail="La date effective ne peut pas être future")
    case = _load_case(conn, case_id)
    quote_date = _parse_date((case["steps"].get("quote") or {}).get("effective_date"), "date du devis")
    order_date = _parse_date((case["steps"].get("purchase_order") or {}).get("effective_date"), "date du bon de commande")
    delivery_date = _parse_date((case["steps"].get("delivery_note") or {}).get("effective_date"), "date du bon de livraison")
    invoice_date = _parse_date((case["steps"].get("invoice") or {}).get("effective_date"), "date de facture")
    if step_type == "quote" and effective_date and order_date and effective_date > order_date:
        raise HTTPException(status_code=422, detail="Le devis ne peut pas être postérieur au bon de commande")
    if step_type == "purchase_order" and effective_date and quote_date and effective_date < quote_date:
        raise HTTPException(status_code=422, detail="Le bon de commande ne peut pas précéder le devis")
    started = _parse_date(case.get("intervention_started_at"), "date de début")
    closed = _parse_date(case.get("intervention_closed_at"), "date de clôture")
    if step_type == "purchase_order" and effective_date and started and effective_date > started:
        raise HTTPException(status_code=422, detail="Le bon de commande ne peut pas être postérieur au début de l'intervention")
    if step_type == "delivery_note" and effective_date and started and effective_date < started:
        raise HTTPException(status_code=422, detail="Le bon de livraison ne peut pas précéder l'intervention")
    if step_type == "delivery_note" and effective_date and invoice_date and effective_date > invoice_date:
        raise HTTPException(status_code=422, detail="Le bon de livraison ne peut pas être postérieur à la facture")
    if step_type == "invoice" and effective_date and closed and effective_date < closed:
        raise HTTPException(status_code=422, detail="La facture ne peut pas précéder la clôture")
    if step_type == "invoice" and effective_date and delivery_date and effective_date < delivery_date:
        raise HTTPException(status_code=422, detail="La facture ne peut pas précéder le bon de livraison")
    if step_type == "invoice" and effective_date:
        first_payment = min(
            (_parse_date(payment.get("effective_date"), "date de paiement") for payment in case["payments"]),
            default=None,
        )
        if first_payment and effective_date > first_payment:
            raise HTTPException(status_code=422, detail="La facture ne peut pas être postérieure à un paiement enregistré")
    if step_type == "invoice" and due_date and effective_date and due_date < effective_date:
        raise HTTPException(status_code=422, detail="L'échéance ne peut pas précéder la facture")


@app.put("/api/billing/cases/{case_id}/steps/{step_type}")
def upsert_billing_step(case_id: int, step_type: str, body: dict = Body(...), user: dict = Depends(_verify_token)):
    require_roles(user, *BILLING_ROLES)
    if step_type not in STEP_TYPES:
        raise HTTPException(status_code=404, detail="Étape inconnue")
    actor = _username(user)
    not_required = bool(body.get("not_required", False))
    note = str(body.get("note") or "").strip()
    if not_required and step_type not in {"purchase_order", "delivery_note"}:
        raise HTTPException(status_code=422, detail="Cette étape ne peut pas être ignorée")
    if not_required and not note:
        note = "Non applicable pour ce dossier"
    effective_date = _parse_date(body.get("effective_date"), "La date effective", required=not not_required)
    due_date = _parse_date(body.get("due_date"), "La date d'échéance", required=step_type == "invoice" and not not_required)
    amount = _parse_amount(
        body.get("amount"),
        "Le montant",
        required=step_type in {"quote", "purchase_order", "invoice"} and not not_required,
    )
    reference = str(body.get("reference") or "").strip()
    reason = str(body.get("change_reason") or "").strip()
    with get_db() as conn:
        case = _load_case(conn, case_id)
        if step_type == "invoice" and case.get("coverage_status") == "covered":
            raise HTTPException(status_code=409, detail="Cette intervention est entièrement couverte par le contrat")
        if step_type == "invoice" and case.get("coverage_status") == "review":
            raise HTTPException(status_code=409, detail="Vérifiez la couverture contractuelle avant de facturer")
        _validate_step_dates(conn, case_id, step_type, effective_date, due_date)
        existing_row = conn.execute(
            "SELECT * FROM billing_steps WHERE case_id=%s AND step_type=%s",
            (case_id, step_type),
        ).fetchone()
        before = _dict(existing_row) if existing_row else None
        is_unconfirmed_legacy = bool(
            existing_row
            and existing_row.get("created_by") == "system-migration"
            and existing_row.get("effective_date") is None
        )
        if existing_row and not is_unconfirmed_legacy and not reason:
            raise HTTPException(status_code=422, detail="Le motif de correction est obligatoire")
        if step_type == "invoice" and amount is not None:
            paid_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM billing_payments WHERE case_id=%s",
                (case_id,),
            ).fetchone()
            if Decimal(str(paid_row["total"])) > amount:
                raise HTTPException(status_code=422, detail="Le montant de facture est inférieur aux paiements déjà enregistrés")
        row = conn.execute(
            """INSERT INTO billing_steps (
                   case_id, step_type, effective_date, due_date, reference, amount,
                   not_required, note, created_by, updated_by
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (case_id, step_type) DO UPDATE SET
                   effective_date=EXCLUDED.effective_date, due_date=EXCLUDED.due_date,
                   reference=EXCLUDED.reference, amount=EXCLUDED.amount,
                   not_required=EXCLUDED.not_required, note=EXCLUDED.note,
                   created_by=CASE
                       WHEN billing_steps.created_by='system-migration'
                        AND billing_steps.effective_date IS NULL
                       THEN EXCLUDED.created_by ELSE billing_steps.created_by END,
                   updated_by=EXCLUDED.updated_by, updated_at=CURRENT_TIMESTAMP
               RETURNING *""",
            (case_id, step_type, effective_date, due_date, reference, amount, not_required, note, actor, actor),
        ).fetchone()
        after = _dict(row)
        _history(
            conn, case_id, "UPDATE_STEP" if before else "CREATE_STEP", "step", row["id"], actor,
            before=before, after=after, reason=reason,
        )
        conn.execute(
            "UPDATE billing_cases SET updated_by=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (actor, case_id),
        )
        if step_type == "invoice":
            conn.execute(
                """UPDATE interventions SET facture_envoyee=TRUE
                   WHERE id=(SELECT intervention_id FROM billing_cases WHERE id=%s)""",
                (case_id,),
            )
        result = _load_case(conn, case_id)
    log_audit(actor, f"BILLING_{step_type.upper()}", json.dumps({"case_id": case_id}, ensure_ascii=False), "facturation")
    return result


def _validate_payment(conn, case_id: int, payment_date: date, amount: Decimal, *, exclude_payment_id: int | None = None) -> None:
    case = _load_case(conn, case_id)
    invoice = case["steps"].get("invoice")
    if not invoice or invoice.get("amount") is None or not invoice.get("effective_date"):
        raise HTTPException(status_code=422, detail="Confirmez d'abord la date et le montant de la facture")
    invoice_date = _parse_date(invoice["effective_date"], "date de facture", required=True)
    if payment_date < invoice_date:
        raise HTTPException(status_code=422, detail="Le paiement ne peut pas précéder la facture")
    if payment_date > date.today():
        raise HTTPException(status_code=422, detail="La date de paiement ne peut pas être future")
    params: list[Any] = [case_id]
    query = "SELECT COALESCE(SUM(amount), 0) AS total FROM billing_payments WHERE case_id=%s"
    if exclude_payment_id is not None:
        query += " AND id<>%s"
        params.append(exclude_payment_id)
    paid = Decimal(str(conn.execute(query, tuple(params)).fetchone()["total"]))
    invoice_amount = Decimal(str(invoice["amount"]))
    if paid + amount > invoice_amount:
        raise HTTPException(status_code=422, detail="Le total payé dépasserait le montant de la facture")


@app.post("/api/billing/cases/{case_id}/payments")
def add_billing_payment(case_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    require_roles(user, *BILLING_ROLES)
    actor = _username(user)
    payment_date = _parse_date(body.get("effective_date"), "La date de paiement", required=True)
    amount = _parse_amount(body.get("amount"), "Le montant", required=True)
    if amount == 0:
        raise HTTPException(status_code=422, detail="Le paiement doit être supérieur à zéro")
    with get_db() as conn:
        _validate_payment(conn, case_id, payment_date, amount)
        row = conn.execute(
            """INSERT INTO billing_payments (
                   case_id, effective_date, amount, reference, payment_method,
                   note, created_by, updated_by
               ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (
                case_id, payment_date, amount, str(body.get("reference") or "").strip(),
                str(body.get("payment_method") or "").strip(), str(body.get("note") or "").strip(),
                actor, actor,
            ),
        ).fetchone()
        after = _dict(row)
        _history(conn, case_id, "CREATE_PAYMENT", "payment", row["id"], actor, after=after)
        conn.execute(
            "UPDATE billing_cases SET updated_by=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (actor, case_id),
        )
        result = _load_case(conn, case_id)
    log_audit(actor, "CREATE_BILLING_PAYMENT", json.dumps({"case_id": case_id, "amount": float(amount)}, ensure_ascii=False), "facturation")
    return result


@app.put("/api/billing/cases/{case_id}/payments/{payment_id}")
def update_billing_payment(case_id: int, payment_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    require_roles(user, *BILLING_ROLES)
    actor = _username(user)
    reason = str(body.get("change_reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Le motif de correction est obligatoire")
    payment_date = _parse_date(body.get("effective_date"), "La date de paiement", required=True)
    amount = _parse_amount(body.get("amount"), "Le montant", required=True)
    if amount == 0:
        raise HTTPException(status_code=422, detail="Le paiement doit être supérieur à zéro")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM billing_payments WHERE id=%s AND case_id=%s",
            (payment_id, case_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Paiement introuvable")
        before = _dict(existing)
        _validate_payment(conn, case_id, payment_date, amount, exclude_payment_id=payment_id)
        row = conn.execute(
            """UPDATE billing_payments SET
                   effective_date=%s, amount=%s, reference=%s, payment_method=%s,
                   note=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP
               WHERE id=%s AND case_id=%s RETURNING *""",
            (
                payment_date, amount, str(body.get("reference") or "").strip(),
                str(body.get("payment_method") or "").strip(), str(body.get("note") or "").strip(),
                actor, payment_id, case_id,
            ),
        ).fetchone()
        after = _dict(row)
        _history(conn, case_id, "UPDATE_PAYMENT", "payment", payment_id, actor, before=before, after=after, reason=reason)
        conn.execute(
            "UPDATE billing_cases SET updated_by=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
            (actor, case_id),
        )
        result = _load_case(conn, case_id)
    return result


@app.get("/api/billing/cases/{case_id}/history")
def get_billing_history(case_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, *BILLING_ROLES)
    with get_db() as conn:
        _load_rows(conn, case_id)
        rows = conn.execute(
            """SELECT id, case_id, action, entity_type, entity_id, before_data,
                      after_data, change_reason, actor_username, occurred_at
               FROM billing_history WHERE case_id=%s
               ORDER BY occurred_at DESC, id DESC""",
            (case_id,),
        ).fetchall()
    return [_dict(row) for row in rows]


__all__ = [
    "list_billing_responsibles",
    "list_billing_cases",
    "get_billing_case",
    "reassess_billing_coverage",
    "create_billing_case",
    "update_billing_case",
    "upsert_billing_step",
    "add_billing_payment",
    "update_billing_payment",
    "get_billing_history",
]
