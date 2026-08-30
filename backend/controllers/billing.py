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


BILLING_ROLES = ("Admin", "Manager", "Responsable Technique", "Gestionnaire")


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
    where = ""
    if case_id is not None:
        where = "WHERE bc.id = %s"
        params = (case_id,)
    rows = conn.execute(
        f"""SELECT bc.id, bc.intervention_id, bc.request_id,
                   COALESCE(NULLIF(bc.client, ''), NULLIF(i.client, ''), e.client, '') AS client,
                   COALESCE(NULLIF(bc.equipment, ''), i.machine, '') AS equipment,
                   bc.owner_username, bc.currency, bc.case_state, bc.block_reason,
                   bc.created_by, bc.created_at, bc.updated_by, bc.updated_at,
                   i.statut AS intervention_status, i.technicien,
                   i.date AS intervention_date,
                   i.date_debut_intervention AS intervention_started_at,
                   i.date_cloture AS intervention_closed_at,
                   i.pieces_utilisees, COALESCE(i.cout_pieces, 0) AS parts_amount,
                   (COALESCE(i.cout_pieces, 0) > 0 OR
                    NULLIF(BTRIM(COALESCE(i.pieces_utilisees, '')), '') IS NOT NULL) AS has_parts
            FROM billing_cases bc
            LEFT JOIN interventions i ON i.id = bc.intervention_id
            LEFT JOIN equipements e
              ON LOWER(e.nom) = LOWER(i.machine) AND LOWER(e.client) = LOWER(i.client)
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


def _sync_missing_intervention_cases(conn) -> None:
    conn.execute(
        """WITH inserted AS (
               INSERT INTO billing_cases (
                   intervention_id, request_id, client, equipment, created_by, updated_by
               )
               SELECT i.id, d.id, COALESCE(NULLIF(i.client, ''), e.client, ''), i.machine,
                      'system', 'system'
               FROM interventions i
               LEFT JOIN equipements e
                 ON LOWER(e.nom) = LOWER(i.machine) AND LOWER(e.client) = LOWER(i.client)
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
        return _load_case(conn, case_id)


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
                   LEFT JOIN equipements e
                     ON LOWER(e.nom) = LOWER(i.machine) AND LOWER(e.client) = LOWER(i.client)
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
                              i.machine
                       FROM interventions i
                       LEFT JOIN equipements e
                         ON LOWER(e.nom) = LOWER(i.machine)
                        AND LOWER(e.client) = LOWER(i.client)
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
                   client=%s, equipment=%s, intervention_id=%s, owner_username=%s, currency=%s,
                   case_state=%s, block_reason=%s, updated_by=%s,
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=%s""",
            (*values.values(), actor, case_id),
        )
        after = _load_case(conn, case_id)
        if changed:
            _history(conn, case_id, "UPDATE_CASE", "case", case_id, actor, before=before, after=after, reason=reason)
    return after


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
        _load_case(conn, case_id)
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
    "create_billing_case",
    "update_billing_case",
    "upsert_billing_step",
    "add_billing_payment",
    "update_billing_payment",
    "get_billing_history",
]
