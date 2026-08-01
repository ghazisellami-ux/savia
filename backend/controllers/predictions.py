"""Equipment risk prediction and human feedback routes."""

from __future__ import annotations

import json
from datetime import date, datetime

from api.runtime import Body, Depends, HTTPException, app, get_db
from api.security import _verify_token, resolve_client_scope
from repositories.audit import save_prediction_feedback
from services.prediction_engine import predict_equipment_risks


@app.get("/api/dashboard/predictions")
def get_equipment_predictions(
    client: str | None = None,
    equipment_type: str | None = None,
    horizon_days: int = 30,
    user: dict = Depends(_verify_token),
):
    """Predict corrective-failure probability for each equipment in a horizon."""
    effective_client = resolve_client_scope(user, client)
    with get_db() as conn:
        return predict_equipment_risks(
            conn,
            client=effective_client,
            equipment_type=equipment_type,
            horizon_days=horizon_days,
        )


@app.post("/api/predictions/feedback")
def create_prediction_feedback(body: dict = Body(...), user: dict = Depends(_verify_token)):
    """Persist an outcome so forecasts can be validated and recalibrated."""
    outcome = str(body.get("resultat") or body.get("type") or "").strip().lower()
    if outcome not in {"correct", "faux_positif", "decale"}:
        raise HTTPException(status_code=422, detail="Résultat de feedback invalide")
    machine = str(body.get("machine") or "").strip()
    if not machine:
        raise HTTPException(status_code=422, detail="Équipement obligatoire")

    requested_client = str(body.get("client") or "").strip()
    effective_client = resolve_client_scope(user, requested_client or None) or requested_client
    date_predite = str(body.get("date_predite") or date.today().isoformat())
    date_reelle = str(body.get("date_reelle") or body.get("vraiDate") or "")
    try:
        equipment_id = int(body["equipment_id"]) if body.get("equipment_id") is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Identifiant équipement invalide")

    save_prediction_feedback(
        machine,
        date_predite,
        outcome,
        date_reelle,
        str(body.get("note") or ""),
        str(user.get("sub") or "system"),
        equipment_id=equipment_id,
        client=effective_client,
        horizon_jours=int(body.get("horizon_jours") or 30),
        risque_pct=body.get("risque_pct"),
        modele_version=str(body.get("modele_version") or ""),
        date_calcul=str(body.get("date_calcul") or ""),
        features_json=json.dumps(body.get("features") or {}, ensure_ascii=False),
    )
    return {"ok": True}


@app.get("/api/predictions/feedback")
def list_prediction_feedback(
    limit: int = 100,
    user: dict = Depends(_verify_token),
):
    """Return persisted prediction outcomes for the current access scope."""
    limit = max(1, min(limit, 500))
    effective_client = resolve_client_scope(user, None)
    with get_db() as conn:
        if effective_client:
            rows = conn.execute(
                """SELECT * FROM prediction_feedback
                   WHERE LOWER(COALESCE(client, '')) = LOWER(%s)
                   ORDER BY timestamp DESC LIMIT %s""",
                (effective_client, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM prediction_feedback ORDER BY timestamp DESC LIMIT %s",
                (limit,),
            ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key, value in list(item.items()):
            if isinstance(value, (datetime, date)):
                item[key] = value.isoformat()
        result.append(item)
    return result


__all__ = [
    "get_equipment_predictions",
    "create_prediction_feedback",
    "list_prediction_feedback",
]
