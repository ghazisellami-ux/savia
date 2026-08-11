"""Auditable spare-parts demand and replenishment predictions."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _quantity_from_text(text: str) -> float:
    match = re.search(r"(?:qty|qte|quantite|quantity)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", text, re.IGNORECASE)
    if match:
        return max(1.0, float(match.group(1).replace(",", ".")))
    return 1.0


def _json_piece_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (list, dict)):
        payload = value if isinstance(value, list) else [value]
    else:
        try:
            payload = json.loads(str(value or ""))
            payload = payload if isinstance(payload, list) else [payload]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    entries: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _usage_quantity(text: Any, reference: str) -> float:
    """Extract the quantity of one exact reference from legacy or JSON formats."""
    if isinstance(text, (dict, list)) or str(text or "").lstrip().startswith(("[", "{")):
        for entry in _json_piece_entries(text):
            ref = entry.get("reference") or entry.get("ref") or entry.get("Reference")
            if _norm(ref) == _norm(reference):
                return max(1.0, _number(entry.get("qty") or entry.get("quantity") or entry.get("quantite"), 1.0) or 1.0)
    raw = str(text or "")
    reference_key = _norm(reference)
    if reference_key not in _norm(raw):
        return 0.0
    # Les interventions historiques stockent parfois plusieurs lignes
    # "Désignation | Ref: ... | Qty: ..." dans un seul champ. On isole la
    # ligne de la référence pour ne pas reprendre la quantité d'une autre pièce.
    segments = re.split(r"\n+|(?=\b(?:ref|reference)\s*:)", raw, flags=re.IGNORECASE)
    for segment in segments:
        if reference_key in _norm(segment):
            return _quantity_from_text(segment)
    return _quantity_from_text(raw)


def _piece_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, reference, designation, equipement_type, domaine,
                  stock_actuel, stock_minimum, prix_unitaire, fournisseur,
                  consommation_moyenne_mois, delai_fournisseur_jours, criticite,
                  data_confidence
           FROM pieces_rechange ORDER BY designation"""
    ).fetchall()
    return [dict(row) for row in rows]


def _intervention_rows(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT i.machine,
                  COALESCE(NULLIF(i.client, ''), e.client, '') AS client,
                  i.date, i.pieces_utilisees, i.type_intervention,
                  i.probleme, i.cause, i.solution, i.description, i.statut
           FROM interventions i
           LEFT JOIN equipements e ON LOWER(e.nom) = LOWER(i.machine)
           WHERE COALESCE(i.is_temporary, 0) = 0
           ORDER BY i.date"""
    ).fetchall()
    return [dict(row) for row in rows]


def _contract_rows(conn: Any) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """SELECT client, equipement, type_contrat, avec_pieces,
                      pieces_incluses, statut, date_fin
               FROM contrats WHERE statut = 'Actif' ORDER BY date_fin DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _equipment_client_rows(conn: Any) -> list[dict[str, Any]]:
    """Return the installed equipment fleet used to identify client scope."""
    try:
        rows = conn.execute("SELECT nom, type, client FROM equipements ORDER BY client, nom").fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _is_preventive(value: Any) -> bool:
    text = _norm(value)
    return any(token in text for token in ("prevent", "inspection", "controle", "calibr"))


def _client_contract(client: str, reference: str, contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    client_key = _norm(client)
    reference_key = _norm(reference)
    for contract in contracts:
        if client_key and _norm(contract.get("client")) != client_key:
            continue
        contract_type = _norm(contract.get("type_contrat"))
        included = _norm(contract.get("pieces_incluses"))
        covered = bool(contract.get("avec_pieces")) or "fullservice" in contract_type or reference_key in included
        return {
            "client": contract.get("client") or "",
            "type": contract.get("type_contrat") or "",
            "pieces_couvertes": covered,
            "source": "contrat actif explicite",
        }
    return None


def _poisson_tail_at_least(demand: float, stock: int) -> float:
    if stock <= 0:
        return 1.0
    if demand <= 0:
        return 0.0
    probability = math.exp(-demand)
    cumulative = probability
    for k in range(1, max(1, stock)):
        probability *= demand / k
        cumulative += probability
    return max(0.0, min(1.0, 1.0 - cumulative))


def _prediction_for_piece(
    piece: dict[str, Any],
    interventions: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    as_of: date,
) -> dict[str, Any]:
    reference = str(piece.get("reference") or "")
    events: list[dict[str, Any]] = []
    for intervention in interventions:
        event_date = _as_date(intervention.get("date"))
        quantity = _usage_quantity(intervention.get("pieces_utilisees"), reference)
        if event_date and quantity > 0 and event_date <= as_of:
            # `intervention` contient une date datetime PostgreSQL. Elle ne doit
            # pas écraser la date normalisée, sinon les comparaisons date/date
            # échouent et toute la prévision devient indisponible.
            events.append({**intervention, "date": event_date, "quantity": quantity})

    stock = max(0, int(_number(piece.get("stock_actuel"), 0) or 0))
    minimum = max(0, int(_number(piece.get("stock_minimum"), 0) or 0))
    unit_price = _number(piece.get("prix_unitaire"), None)
    lead_time = _number(piece.get("delai_fournisseur_jours"), None)
    lead_time = max(0.0, lead_time) if lead_time is not None else None
    lookback_start = as_of - timedelta(days=365)
    recent_events = [event for event in events if event["date"] >= lookback_start]
    usage_total = sum(event["quantity"] for event in recent_events)
    usage_30 = sum(event["quantity"] for event in recent_events if event["date"] >= as_of - timedelta(days=30))
    usage_90 = sum(event["quantity"] for event in recent_events if event["date"] >= as_of - timedelta(days=90))
    usage_180 = sum(event["quantity"] for event in recent_events if event["date"] >= as_of - timedelta(days=180))
    months_observed = max(1.0, min(12.0, ((as_of - min((event["date"] for event in recent_events), default=as_of)).days + 1) / 30.0))
    rate_365 = usage_total / 12.0
    rate_180 = usage_180 / max(1.0, months_observed if months_observed <= 6 else 6.0)
    rate_90 = usage_90 / 3.0
    rate_30 = usage_30
    rates = [rate for rate in (rate_365, rate_180, rate_90, rate_30) if rate > 0]
    monthly_rate = (0.2 * rate_365 + 0.3 * rate_180 + 0.3 * rate_90 + 0.2 * rate_30) / sum((0.2, 0.3, 0.3, 0.2)[index] for index, rate in enumerate((rate_365, rate_180, rate_90, rate_30)) if rate > 0) if rates else 0.0

    monthly_buckets = []
    for month_index in range(12):
        end = as_of - timedelta(days=30 * month_index)
        start = end - timedelta(days=30)
        monthly_buckets.append(sum(event["quantity"] for event in recent_events if start < event["date"] <= end))
    mean_bucket = sum(monthly_buckets) / len(monthly_buckets) if monthly_buckets else 0.0
    variance = sum((value - mean_bucket) ** 2 for value in monthly_buckets) / len(monthly_buckets) if monthly_buckets else 0.0
    demand_std = math.sqrt(variance)
    lead_demand = monthly_rate * (lead_time / 30.0) if lead_time is not None else None
    safety_stock = 1.65 * demand_std * math.sqrt(max(lead_time, 1.0) / 30.0) if lead_time is not None else None
    reorder_point = math.ceil(minimum + lead_demand + safety_stock) if lead_demand is not None and safety_stock is not None else None
    daily_rate = monthly_rate / 30.0
    stockout_days = stock / daily_rate if daily_rate > 0 else None
    threshold_days = max(0, stock - (reorder_point or minimum)) / daily_rate if daily_rate > 0 and reorder_point is not None else None
    order_date = as_of + timedelta(days=max(0, math.floor(threshold_days))) if threshold_days is not None else None
    if stock == 0:
        order_date = as_of
    elif reorder_point is not None and stock <= reorder_point:
        order_date = as_of
    if reorder_point is not None:
        order_quantity = math.ceil(max(0, reorder_point + (monthly_rate if monthly_rate > 0 else 0) - stock))
    elif stock == 0 and minimum > 0:
        # Recompléter le seuil configuré est une action de stock certaine,
        # même lorsque la prévision de consommation n'est pas calculable.
        order_quantity = minimum
    else:
        order_quantity = None
    stockout_date = as_of + timedelta(days=max(0, math.floor(stockout_days))) if stockout_days is not None else None
    probability_30 = _poisson_tail_at_least(monthly_rate, max(0, stock - minimum)) if monthly_rate > 0 else (1.0 if stock <= minimum else None)

    history_months = min(12.0, months_observed) if events else 0.0
    confidence = min(100, round(25 + min(35, len(events) * 5) + min(25, history_months / 12 * 25) + (15 if lead_time is not None else 0) + (10 if unit_price and unit_price > 0 else 0)))
    if not events and stock > 0:
        confidence = 0
    clients = sorted({str(event.get("client") or "") for event in events if str(event.get("client") or "")})
    contract_coverage = [_client_contract(client, reference, contracts) for client in clients]
    contract_coverage = [item for item in contract_coverage if item]
    diagnostics = [
        {
            "date": event["date"].isoformat(),
            "machine": event.get("machine") or "",
            "client": event.get("client") or "",
            "type": event.get("type_intervention") or "",
            "probleme": event.get("probleme") or "",
            "cause": event.get("cause") or "",
            "solution": event.get("solution") or "",
        }
        for event in sorted(events, key=lambda item: item["date"], reverse=True)[:5]
        if any(str(event.get(field) or "").strip() for field in ("probleme", "cause", "solution"))
    ]
    if stock == 0:
        urgency = "CRITIQUE"
    elif reorder_point is not None and stock <= reorder_point:
        urgency = "HAUTE" if lead_time and lead_time > 0 else "CRITIQUE"
    elif stockout_days is not None and lead_time is not None and stockout_days <= lead_time:
        urgency = "HAUTE"
    elif probability_30 is not None and probability_30 >= 0.5:
        urgency = "NORMALE"
    else:
        urgency = "BASSE" if events else "UNKNOWN"

    # Un stock nul est une urgence connue, mais il ne suffit pas à fabriquer
    # une prévision de quantité/date sans consommation et délai documentés.
    prediction_available = bool(events and lead_time is not None and monthly_rate > 0)
    reason = (
        "Stock épuisé" if stock == 0 else
        "Stock sous le point de commande calculé" if reorder_point is not None and stock <= reorder_point else
        "Demande historique insuffisante" if not events else
        "Délai fournisseur non renseigné" if lead_time is None else
        "Consommation historique et variabilité observées"
    )
    return {
        "piece_id": piece.get("id"),
        "reference": reference,
        "designation": piece.get("designation") or "",
        "equipement_type": piece.get("equipement_type") or "",
        "domaine": piece.get("domaine") or "",
        "fournisseur": piece.get("fournisseur") or "",
        "stock_actuel": stock,
        "stock_minimum": minimum,
        "prix_unitaire": unit_price,
        "date_commande": order_date.isoformat() if order_date else None,
        "date_rupture_prevue": stockout_date.isoformat() if stockout_date else None,
        "urgence": urgency,
        "prediction_available": prediction_available,
        "recommandation_actionnable": bool(prediction_available or stock == 0),
        "raison": reason,
        "quantite_recommandee": order_quantity,
        "cout_estime": round(order_quantity * unit_price, 2) if order_quantity is not None and unit_price is not None and unit_price > 0 else None,
        "jours_avant_rupture": round(stockout_days, 1) if stockout_days is not None else None,
        "jours_jusqua_commande": (order_date - as_of).days if order_date else None,
        "risque_rupture_30j_pct": round(probability_30 * 100, 1) if probability_30 is not None else None,
        "fiabilite_donnees_pct": confidence,
        "consommation_mensuelle": round(monthly_rate, 3),
        "consommation_30j": round(usage_30, 2),
        "consommation_90j": round(usage_90, 2),
        "utilisations_total_365j": round(usage_total, 2),
        "delai_fournisseur_jours": lead_time,
        "point_commande": reorder_point,
        "stock_securite": round(safety_stock, 2) if safety_stock is not None else None,
        "clients_utilisateurs": clients,
        "contrats": contract_coverage,
        "diagnostics": diagnostics,
        "historique": {"evenements": len(events), "mois_observes": round(history_months, 1)},
        "modele": "weighted_poisson_reorder_point-v1",
    }


def predict_spare_parts(conn: Any, piece_id: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    pieces = _piece_rows(conn)
    if piece_id is not None:
        pieces = [piece for piece in pieces if int(piece.get("id") or 0) == int(piece_id)]
    if not pieces:
        return []
    interventions = _intervention_rows(conn)
    contracts = _contract_rows(conn)
    equipment_rows = _equipment_client_rows(conn)
    clients_by_type: dict[str, set[str]] = defaultdict(set)
    for equipment in equipment_rows:
        equipment_type = _norm(equipment.get("type"))
        client = str(equipment.get("client") or "").strip()
        if equipment_type and client:
            clients_by_type[equipment_type].add(client)
    predictions = []
    for piece in pieces:
        prediction = _prediction_for_piece(piece, interventions, contracts, date.today())
        fleet_clients = clients_by_type.get(_norm(piece.get("equipement_type")), set())
        prediction["clients_utilisateurs"] = sorted(set(prediction.get("clients_utilisateurs") or []).union(fleet_clients))
        prediction["contrats"] = [
            item for client in prediction["clients_utilisateurs"]
            for item in [_client_contract(client, prediction.get("reference"), contracts)]
            if item
        ]
        predictions.append(prediction)
    priority = {"CRITIQUE": 0, "HAUTE": 1, "NORMALE": 2, "BASSE": 3, "UNKNOWN": 4}
    predictions.sort(key=lambda item: (priority.get(item["urgence"], 9), item["jours_jusqua_commande"] if item["jours_jusqua_commande"] is not None else 99999, item["designation"]))
    return predictions[:limit] if limit else predictions


def predict_piece_order_date(conn: Any, piece_id: int) -> dict[str, Any] | None:
    predictions = predict_spare_parts(conn, piece_id=piece_id)
    return predictions[0] if predictions else None
