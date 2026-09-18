"""Public-market tracking routes."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from api.runtime import Body, Depends, HTTPException, Optional, app, get_db, log_audit
from api.security import _verify_token, require_roles
from services.public_market_tracking import (
    NEXT_STEP,
    STATUS_LABELS,
    compute_alert,
    compute_status,
    deadline_from,
    has_total_delivery,
    progress_count,
)


PUBLIC_MARKET_ROLES = ("Admin", "Manager", "Responsable Technique", "Gestionnaire")

DATE_FIELDS = (
    "signature_date",
    "equipment_reception_date",
    "delivery_note_date",
    "invoice_date",
    "provisional_acceptance_date",
    "final_acceptance_date",
)
TEXT_FIELDS = (
    "client",
    "market_number",
    "market_object",
    "owner_username",
    "equipment_reception_note",
    "delivery_note_reference",
    "invoice_reference",
    "provisional_acceptance_reference",
    "final_acceptance_reference",
    "case_state",
    "block_reason",
    "notes",
)


def _username(user: dict) -> str:
    return str(user.get("sub") or user.get("nom") or "unknown")


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _row_dict(row: Any) -> dict[str, Any]:
    return _serialize(dict(row)) if row else {}


def _delivery_notes(conn, case_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, delivery_note_date, delivery_note_reference,
                  is_total_delivery, created_at
           FROM public_market_delivery_notes
           WHERE case_id=%s
           ORDER BY delivery_note_date, id""",
        (case_id,),
    ).fetchall()
    return [_row_dict(row) for row in rows]


def _replace_delivery_notes(conn, case_id: int, notes: list[dict[str, Any]]) -> None:
    conn.execute("DELETE FROM public_market_delivery_notes WHERE case_id=%s", (case_id,))
    for note in notes:
        conn.execute(
            """INSERT INTO public_market_delivery_notes (
                   case_id, delivery_note_date, delivery_note_reference, is_total_delivery
               ) VALUES (%s, %s, %s, %s)""",
            (
                case_id,
                note["delivery_note_date"],
                note["delivery_note_reference"],
                note["is_total_delivery"],
            ),
        )


def _parse_date(value: Any, label: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{label} doit être une date valide")


def _parse_days(value: Any, label: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{label} doit être un nombre de jours valide")
    if parsed < 0:
        raise HTTPException(status_code=422, detail=f"{label} ne peut pas être négatif")
    return parsed


def _validate_owner(conn, username: str) -> None:
    if not username:
        return
    row = conn.execute(
        """SELECT username FROM utilisateurs
           WHERE username=%s AND actif=1 AND role IN (%s, %s, %s, %s)""",
        (username, *PUBLIC_MARKET_ROLES),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=422, detail="Le responsable sélectionné n’est pas autorisé")


def _history(
    conn,
    case_id: int,
    action: str,
    actor: str,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """INSERT INTO public_market_history (
               case_id, action, before_data, after_data, actor_username
           ) VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)""",
        (
            case_id,
            action,
            json.dumps(_serialize(before), ensure_ascii=False) if before is not None else None,
            json.dumps(_serialize(after), ensure_ascii=False) if after is not None else None,
            actor,
        ),
    )


def _update_action(before: dict[str, Any], values: dict[str, Any], changed_fields: list[str]) -> str:
    """Choose a concise audit action for common one-step updates."""
    if "case_state" in changed_fields:
        if values["case_state"] == "blocked":
            return "BLOCK_CASE"
        if values["case_state"] == "cancelled":
            return "CANCEL_CASE"
        if before.get("case_state") in {"blocked", "cancelled"}:
            return "REACTIVATE_CASE"
    actions = {
        "signature_date": "SIGNATURE",
        "equipment_reception_date": "EQUIPMENT_RECEPTION",
        "delivery_note_date": "DELIVERY_NOTE",
        "invoice_date": "INVOICE",
        "provisional_acceptance_date": "PROVISIONAL_ACCEPTANCE",
        "final_acceptance_date": "FINAL_ACCEPTANCE",
    }
    changed_steps = [field for field in changed_fields if field in actions]
    if len(changed_steps) == 1:
        field = changed_steps[0]
        if values[field] and not before.get(field):
            return f"SET_{actions[field]}"
        if not values[field] and before.get(field):
            return f"CLEAR_{actions[field]}"
        return f"UPDATE_{actions[field]}"
    return "UPDATE_CASE"


def _hydrate(raw: Any, delivery_note_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    item = _row_dict(raw)
    notes = delivery_note_rows if delivery_note_rows is not None else []
    if not notes and item.get("delivery_note_date"):
        # Defensive fallback for databases upgraded before migration 029 was
        # applied: keep the former single-BL milestone usable.
        notes = [{
            "delivery_note_date": item["delivery_note_date"],
            "delivery_note_reference": item.get("delivery_note_reference") or "",
            "is_total_delivery": True,
        }]
    if notes:
        # Keep the legacy fields populated for old consumers while exposing
        # the complete list to the new tracking UI.
        latest = notes[-1]
        item["delivery_note_date"] = latest.get("delivery_note_date")
        item["delivery_note_reference"] = latest.get("delivery_note_reference") or ""
    item["delivery_notes"] = notes
    item["delivery_note_complete"] = has_total_delivery(item)
    item["delivery_note_status"] = (
        "complete" if item["delivery_note_complete"]
        else "partial" if notes
        else "pending"
    )
    status = compute_status(item)
    execution_deadline = deadline_from(item.get("signature_date"), item.get("execution_delay_days"))
    warranty_deadline = deadline_from(
        item.get("provisional_acceptance_date"), item.get("warranty_retention_days")
    )
    item.update({
        "status": status,
        "status_label": STATUS_LABELS[status],
        "next_step": NEXT_STEP[status],
        "progress_completed": progress_count(item),
        "progress_total": 6,
        "execution_deadline": execution_deadline.isoformat() if execution_deadline else None,
        "warranty_deadline": warranty_deadline.isoformat() if warranty_deadline else None,
        "alert": compute_alert(item),
    })
    return item


def _get_case(conn, case_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM public_market_cases WHERE id=%s", (case_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Dossier de marché introuvable")
    return _hydrate(row, _delivery_notes(conn, case_id))


def _validated_values(body: dict, previous: dict | None = None) -> dict[str, Any]:
    previous = previous or {}
    values = {
        field: str(body.get(field, previous.get(field, "")) or "").strip()
        for field in TEXT_FIELDS
    }
    for field in DATE_FIELDS:
        values[field] = _parse_date(body.get(field, previous.get(field)), field.replace("_", " "))
    values["execution_delay_days"] = _parse_days(
        body.get("execution_delay_days", previous.get("execution_delay_days")),
        "Le délai d’exécution",
    )
    values["warranty_retention_days"] = _parse_days(
        body.get("warranty_retention_days", previous.get("warranty_retention_days")),
        "La retenue de garantie",
    )
    raw_delivery_notes = body.get("delivery_notes")
    if raw_delivery_notes is None:
        raw_delivery_notes = previous.get("delivery_notes")
    if raw_delivery_notes is None:
        legacy_date = values["delivery_note_date"]
        raw_delivery_notes = ([{
            "delivery_note_date": legacy_date,
            "delivery_note_reference": values["delivery_note_reference"],
            "is_total_delivery": True,
        }] if legacy_date else [])
    if not isinstance(raw_delivery_notes, list):
        raise HTTPException(status_code=422, detail="La liste des BL est invalide")
    parsed_delivery_notes = []
    for index, note in enumerate(raw_delivery_notes, start=1):
        if not isinstance(note, dict):
            raise HTTPException(status_code=422, detail=f"Le BL n°{index} est invalide")
        note_date = _parse_date(note.get("delivery_note_date"), f"la date du BL n°{index}")
        if not note_date:
            raise HTTPException(status_code=422, detail=f"La date du BL n°{index} est obligatoire")
        parsed_delivery_notes.append({
            "delivery_note_date": note_date,
            "delivery_note_reference": str(note.get("delivery_note_reference") or "").strip(),
            "is_total_delivery": note.get("is_total_delivery") in (True, 1, "1", "true", "True"),
        })
    parsed_delivery_notes.sort(key=lambda note: note["delivery_note_date"])
    values["delivery_notes"] = parsed_delivery_notes
    if parsed_delivery_notes:
        values["delivery_note_date"] = parsed_delivery_notes[-1]["delivery_note_date"]
        values["delivery_note_reference"] = parsed_delivery_notes[-1]["delivery_note_reference"]
    else:
        values["delivery_note_date"] = None
        values["delivery_note_reference"] = ""
    values["case_state"] = values["case_state"] or "active"
    if not values["client"]:
        raise HTTPException(status_code=422, detail="Le client est obligatoire")
    if not values["market_number"]:
        raise HTTPException(status_code=422, detail="Le numéro du marché est obligatoire")
    if values["case_state"] not in {"active", "blocked", "cancelled"}:
        raise HTTPException(status_code=422, detail="État de dossier invalide")
    if values["case_state"] in {"blocked", "cancelled"} and not values["block_reason"]:
        raise HTTPException(status_code=422, detail="Un motif est obligatoire pour bloquer ou annuler")

    if values["invoice_date"] and parsed_delivery_notes and not any(
        note["is_total_delivery"] for note in parsed_delivery_notes
    ):
        raise HTTPException(status_code=422, detail="La facture ne peut être renseignée qu’après la livraison totale")

    chronological = [values[field] for field in DATE_FIELDS if values[field]]
    if chronological != sorted(chronological):
        raise HTTPException(status_code=422, detail="Les dates des étapes doivent respecter leur ordre chronologique")
    return values


@app.get("/api/public-markets/responsibles")
def list_public_market_responsibles(user: dict = Depends(_verify_token)):
    require_roles(user, *PUBLIC_MARKET_ROLES)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT username,
                      COALESCE(NULLIF(BTRIM(nom_complet), ''), username) AS display_name,
                      role
               FROM utilisateurs
               WHERE actif=1 AND role IN (%s, %s, %s, %s)
               ORDER BY LOWER(COALESCE(NULLIF(BTRIM(nom_complet), ''), username))""",
            PUBLIC_MARKET_ROLES,
        ).fetchall()
    return [_row_dict(row) for row in rows]


@app.get("/api/public-markets/cases")
def list_public_market_cases(
    status: Optional[str] = None,
    client: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    require_roles(user, *PUBLIC_MARKET_ROLES)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM public_market_cases ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        note_rows = conn.execute(
            """SELECT id, case_id, delivery_note_date, delivery_note_reference,
                      is_total_delivery, created_at
               FROM public_market_delivery_notes
               ORDER BY delivery_note_date, id"""
        ).fetchall()
    notes_by_case: dict[int, list[dict[str, Any]]] = {}
    for note_row in note_rows:
        note = _row_dict(note_row)
        notes_by_case.setdefault(int(note["case_id"]), []).append(note)
    cases = [_hydrate(row, notes_by_case.get(int(row["id"]), [])) for row in rows]
    if status == "alert":
        cases = [item for item in cases if item.get("alert")]
    elif status:
        cases = [item for item in cases if item["status"] == status]
    if client:
        wanted = client.strip().casefold()
        cases = [item for item in cases if item["client"].strip().casefold() == wanted]
    if search:
        needle = search.strip().casefold()
        cases = [item for item in cases if needle in " ".join((
            str(item["id"]), item.get("client", ""), item.get("market_number", ""),
            item.get("market_object", ""), item.get("owner_username", ""),
            item.get("delivery_note_reference", ""),
        )).casefold()]
    return cases


@app.get("/api/public-markets/cases/{case_id}")
def get_public_market_case(case_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, *PUBLIC_MARKET_ROLES)
    with get_db() as conn:
        return _get_case(conn, case_id)


@app.post("/api/public-markets/cases")
def create_public_market_case(body: dict = Body(...), user: dict = Depends(_verify_token)):
    require_roles(user, *PUBLIC_MARKET_ROLES)
    actor = _username(user)
    values = _validated_values(body)
    values["owner_username"] = values["owner_username"] or actor
    with get_db() as conn:
        _validate_owner(conn, values["owner_username"])
        duplicate = conn.execute(
            "SELECT id FROM public_market_cases WHERE LOWER(BTRIM(market_number))=LOWER(BTRIM(%s))",
            (values["market_number"],),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="Ce numéro de marché existe déjà")
        row = conn.execute(
            """INSERT INTO public_market_cases (
                   client, market_number, market_object, owner_username,
                   signature_date, execution_delay_days,
                   equipment_reception_date, equipment_reception_note,
                   delivery_note_date, delivery_note_reference,
                   invoice_date, invoice_reference,
                   provisional_acceptance_date, provisional_acceptance_reference,
                   warranty_retention_days, final_acceptance_date,
                   final_acceptance_reference, case_state, block_reason, notes,
                   created_by, updated_by
               ) VALUES (
                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s
               ) RETURNING id""",
            tuple(values[field] for field in (
                "client", "market_number", "market_object", "owner_username",
                "signature_date", "execution_delay_days", "equipment_reception_date",
                "equipment_reception_note", "delivery_note_date", "delivery_note_reference",
                "invoice_date", "invoice_reference",
                "provisional_acceptance_date", "provisional_acceptance_reference",
                "warranty_retention_days", "final_acceptance_date",
                "final_acceptance_reference", "case_state", "block_reason", "notes",
            )) + (actor, actor),
        ).fetchone()
        _replace_delivery_notes(conn, row["id"], values["delivery_notes"])
        created = _get_case(conn, row["id"])
        _history(conn, created["id"], "CREATE_CASE", actor, after=created)
    log_audit(actor, "CREATE_PUBLIC_MARKET", json.dumps({"case_id": created["id"], "market_number": created["market_number"]}, ensure_ascii=False), "marches")
    return created


@app.patch("/api/public-markets/cases/{case_id}")
def update_public_market_case(case_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    require_roles(user, *PUBLIC_MARKET_ROLES)
    actor = _username(user)
    with get_db() as conn:
        before = _get_case(conn, case_id)
        values = _validated_values(body, before)
        _validate_owner(conn, values["owner_username"])
        duplicate = conn.execute(
            """SELECT id FROM public_market_cases
               WHERE LOWER(BTRIM(market_number))=LOWER(BTRIM(%s)) AND id<>%s""",
            (values["market_number"], case_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="Ce numéro de marché existe déjà")
        changed_fields = [
            field for field, value in values.items()
            if _serialize(value) != before.get(field)
        ]
        conn.execute(
            """UPDATE public_market_cases SET
                   client=%s, market_number=%s, market_object=%s, owner_username=%s,
                   signature_date=%s, execution_delay_days=%s,
                   equipment_reception_date=%s, equipment_reception_note=%s,
                   delivery_note_date=%s, delivery_note_reference=%s,
                   invoice_date=%s, invoice_reference=%s,
                   provisional_acceptance_date=%s, provisional_acceptance_reference=%s,
                   warranty_retention_days=%s, final_acceptance_date=%s,
                   final_acceptance_reference=%s, case_state=%s, block_reason=%s,
                   notes=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP
               WHERE id=%s""",
            tuple(values[field] for field in (
                "client", "market_number", "market_object", "owner_username",
                "signature_date", "execution_delay_days", "equipment_reception_date",
                "equipment_reception_note", "delivery_note_date", "delivery_note_reference",
                "invoice_date", "invoice_reference",
                "provisional_acceptance_date", "provisional_acceptance_reference",
                "warranty_retention_days", "final_acceptance_date",
                "final_acceptance_reference", "case_state", "block_reason", "notes",
            )) + (actor, case_id),
        )
        _replace_delivery_notes(conn, case_id, values["delivery_notes"])
        updated = _get_case(conn, case_id)
        if changed_fields:
            history_after = dict(updated)
            history_after["changed_fields"] = changed_fields
            _history(
                conn,
                case_id,
                _update_action(before, values, changed_fields),
                actor,
                before=before,
                after=history_after,
            )
    log_audit(actor, "UPDATE_PUBLIC_MARKET", json.dumps({"case_id": case_id, "status": updated["status"]}, ensure_ascii=False), "marches")
    return updated


@app.get("/api/public-markets/cases/{case_id}/history")
def get_public_market_history(case_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, *PUBLIC_MARKET_ROLES)
    with get_db() as conn:
        _get_case(conn, case_id)
        rows = conn.execute(
            """SELECT id, case_id, action, before_data, after_data,
                      actor_username, occurred_at
               FROM public_market_history
               WHERE case_id=%s
               ORDER BY occurred_at DESC, id DESC""",
            (case_id,),
        ).fetchall()
    return [_row_dict(row) for row in rows]
