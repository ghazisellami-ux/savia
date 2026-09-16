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
                  i.date, i.planning_id, i.pieces_utilisees, i.type_intervention,
                  i.probleme, i.cause, i.solution, i.description, i.statut
           FROM interventions i
           LEFT JOIN equipements e ON e.id = i.equipement_id
           WHERE COALESCE(i.is_temporary, 0) = 0
           ORDER BY i.date"""
    ).fetchall()
    return [dict(row) for row in rows]


def _contract_rows(conn: Any) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            """SELECT id, client, equipement, type_contrat, avec_pieces,
                      pieces_incluses, statut, date_debut, date_fin
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


def _contract_planning_rows(conn: Any) -> list[dict[str, Any]]:
    """Return contract-generated visits, including rescheduled dates.

    ``date_prevue`` is updated when a visit is postponed, therefore it is the
    authoritative date for the stock forecast. Ghost rows are audit history and
    must never create a second demand signal.
    """
    try:
        rows = conn.execute(
            """SELECT id, contrat_id, machine, client, type_maintenance,
                      date_prevue, statut, COALESCE(is_ghost, false) AS is_ghost
               FROM planning_maintenance
               WHERE contrat_id IS NOT NULL
               ORDER BY date_prevue, id"""
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _pending_part_request_rows(conn: Any) -> list[dict[str, Any]]:
    """Open technician part requests reserve stock immediately.

    The request table has no quantity column: one open request is therefore a
    documented minimum demand of one unit, exposed as such in the result.
    """
    try:
        rows = conn.execute(
            """SELECT reference, designation, intervention_id, equipement, client,
                      date_creation
               FROM pieces_demandees
               WHERE statut = 'en_attente'
               ORDER BY date_creation, id"""
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _is_preventive(value: Any) -> bool:
    text = _norm(value)
    return any(token in text for token in ("prevent", "inspection", "controle", "calibr"))


def _contract_part_entries(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the explicitly selected contract parts and their total quotas."""
    entries = []
    for item in _json_piece_entries(contract.get("pieces_incluses")):
        reference = str(item.get("ref") or item.get("reference") or "").strip()
        quota = _number(item.get("quota"), 0) or 0
        if reference and quota > 0:
            entries.append({"reference": reference, "quota": quota})
    return entries


def _contract_covers_reference(contract: dict[str, Any], reference: str) -> bool:
    """Whether a contract explicitly covers this reference.

    A selected quota is intentionally narrower than the old ``avec_pieces``
    boolean: selecting only two references must not mark every catalogue part
    as covered.
    """
    contract_type = _norm(contract.get("type_contrat"))
    entries = _contract_part_entries(contract)
    if entries:
        return any(_norm(item["reference"]) == _norm(reference) for item in entries)
    return bool(contract.get("avec_pieces")) or "fullservice" in contract_type


def _client_contract(client: str, reference: str, contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    client_key = _norm(client)
    reference_key = _norm(reference)
    for contract in contracts:
        if client_key and _norm(contract.get("client")) != client_key:
            continue
        covered = _contract_covers_reference(contract, reference_key)
        return {
            "id": contract.get("id"),
            "client": contract.get("client") or "",
            "type": contract.get("type_contrat") or "",
            "pieces_couvertes": covered,
            "source": "contrat actif explicite",
        }
    return None


def _is_open_planning_status(value: Any) -> bool:
    return _norm(value) not in {"cloturee", "realisee", "terminee", "annulee", "decale"}


def _visit_matches_piece(
    visit: dict[str, Any],
    piece: dict[str, Any],
    equipment_types: dict[str, str],
    used_machines: set[str],
) -> bool:
    """Restrict a visit to equipment compatible with the spare part."""
    machine_key = _norm(visit.get("machine"))
    expected_type = _norm(piece.get("equipement_type"))
    if expected_type:
        return equipment_types.get(machine_key) == expected_type
    return bool(machine_key and machine_key in used_machines)


def _future_contract_demand(
    piece: dict[str, Any],
    interventions: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    planning_rows: list[dict[str, Any]],
    equipment_types: dict[str, str],
    as_of: date,
) -> dict[str, Any]:
    """Build auditable demand signals from future contract-maintenance visits.

    Explicit contract quotas are allocated across the remaining scheduled
    visits.  Contracts without an explicit part quota never fabricate demand:
    they only receive an estimate when this exact part has already been used
    during comparable preventive work.
    """
    reference = str(piece.get("reference") or "")
    contracts_by_id = {
        int(contract["id"]): contract
        for contract in contracts
        if contract.get("id") is not None
    }
    planning_by_id = {
        int(row["id"]): row
        for row in planning_rows
        if row.get("id") is not None
    }
    used_machines: set[str] = set()
    for intervention in interventions:
        intervention_date = _as_date(intervention.get("date"))
        if intervention_date and intervention_date <= as_of and _usage_quantity(intervention.get("pieces_utilisees"), reference) > 0:
            used_machines.add(_norm(intervention.get("machine")))
    future_by_contract: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for visit in planning_rows:
        contract_id = visit.get("contrat_id")
        visit_date = _as_date(visit.get("date_prevue"))
        if contract_id is None or not visit_date or visit_date <= as_of:
            continue
        try:
            contract_id = int(contract_id)
        except (TypeError, ValueError):
            continue
        contract = contracts_by_id.get(contract_id)
        if not contract or visit.get("is_ghost") or not _is_open_planning_status(visit.get("statut")):
            continue
        contract_end = _as_date(contract.get("date_fin"))
        if contract_end and visit_date > contract_end:
            continue
        if _visit_matches_piece(visit, piece, equipment_types, used_machines):
            future_by_contract[contract_id].append({**visit, "date": visit_date})

    all_future_visits = [visit for visits in future_by_contract.values() for visit in visits]

    scheduled_events: list[dict[str, Any]] = []
    explicit_contracts: list[dict[str, Any]] = []
    explicit_visit_ids: set[int] = set()
    for contract_id, visits in future_by_contract.items():
        contract = contracts_by_id[contract_id]
        entry = next(
            (item for item in _contract_part_entries(contract) if _norm(item["reference"]) == _norm(reference)),
            None,
        )
        if not entry:
            continue
        used_quota = 0.0
        for intervention in interventions:
            intervention_date = _as_date(intervention.get("date"))
            try:
                planning_id = int(intervention.get("planning_id") or 0)
                linked_contract = int((planning_by_id.get(planning_id) or {}).get("contrat_id") or 0)
            except (TypeError, ValueError):
                linked_contract = 0
            if intervention_date and intervention_date <= as_of and linked_contract == contract_id:
                used_quota += _usage_quantity(intervention.get("pieces_utilisees"), reference)
        remaining_quota = max(0.0, float(entry["quota"]) - used_quota)
        if remaining_quota <= 0:
            continue
        quantity_per_visit = remaining_quota / len(visits)
        for visit in visits:
            scheduled_events.append({
                "date": visit["date"],
                "quantity": quantity_per_visit,
                "source": "quota_contrat",
                "contrat_id": contract_id,
            })
            if visit.get("id") is not None:
                explicit_visit_ids.add(int(visit["id"]))
        explicit_contracts.append({
            "id": contract_id,
            "client": contract.get("client") or "",
            "type": contract.get("type_contrat") or "",
            "quota_restant": round(remaining_quota, 2),
            "interventions_planifiees": len(visits),
        })

    # For contracts without a declared part, use only observed preventive use
    # of this same reference on compatible equipment.
    comparable_preventive = []
    for intervention in interventions:
        intervention_date = _as_date(intervention.get("date"))
        if (
            intervention_date
            and intervention_date <= as_of
            and _is_preventive(intervention.get("type_intervention"))
            and _visit_matches_piece(intervention, piece, equipment_types, used_machines)
        ):
            comparable_preventive.append(intervention)
    historical_preventive_quantity = sum(
        _usage_quantity(intervention.get("pieces_utilisees"), reference)
        for intervention in comparable_preventive
    )
    estimated_per_visit = (
        historical_preventive_quantity / len(comparable_preventive)
        if comparable_preventive else 0.0
    )
    estimated_visits = 0
    if estimated_per_visit > 0:
        for visits in future_by_contract.values():
            for visit in visits:
                if visit.get("id") is not None and int(visit["id"]) in explicit_visit_ids:
                    continue
                scheduled_events.append({
                    "date": visit["date"],
                    "quantity": estimated_per_visit,
                    "source": "historique_preventif",
                    "contrat_id": visit.get("contrat_id"),
                })
                estimated_visits += 1

    scheduled_events.sort(key=lambda item: item["date"])
    explicit_quantity = sum(item["quantity"] for item in scheduled_events if item["source"] == "quota_contrat")
    estimated_quantity = sum(item["quantity"] for item in scheduled_events if item["source"] == "historique_preventif")
    return {
        "events": scheduled_events,
        "interventions_planifiees": len(all_future_visits),
        "prochaine_intervention": min((visit["date"] for visit in all_future_visits), default=None).isoformat() if all_future_visits else None,
        "quantite_quota_contrat": round(explicit_quantity, 2),
        "quantite_estimee_historique": round(estimated_quantity, 2),
        "quantite_totale": round(explicit_quantity + estimated_quantity, 2),
        "contrats_quota": explicit_contracts,
        "estimation_par_visite": round(estimated_per_visit, 3) if estimated_per_visit else 0.0,
        "visites_estimees": estimated_visits,
        "clients": sorted({str(visit.get("client") or "") for visit in all_future_visits if str(visit.get("client") or "")}),
    }


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
    planning_rows: list[dict[str, Any]],
    pending_requests: list[dict[str, Any]],
    equipment_types: dict[str, str],
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

    contract_demand = _future_contract_demand(
        piece, interventions, contracts, planning_rows, equipment_types, as_of,
    )
    scheduled_events = contract_demand["events"]

    stock = max(0, int(_number(piece.get("stock_actuel"), 0) or 0))
    pending_for_piece = [
        request for request in pending_requests
        if _norm(request.get("reference")) == _norm(reference)
    ]
    pending_quantity = len(pending_for_piece)
    # Pending technician requests are reservations, not historical usage.
    # Reserve the documented minimum of one unit per open request before
    # calculating the stock available to future maintenance.
    available_stock = max(0, stock - pending_quantity)
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
    stockout_days = available_stock / daily_rate if daily_rate > 0 else None
    threshold_days = max(0, available_stock - (reorder_point or minimum)) / daily_rate if daily_rate > 0 and reorder_point is not None else None
    reorder_trigger_date = as_of + timedelta(days=max(0, math.floor(threshold_days))) if threshold_days is not None else None
    contract_reorder_date = None
    contract_stockout_date = None
    cumulative_contract_demand = 0.0
    for scheduled in scheduled_events:
        days_until_visit = max(0, (scheduled["date"] - as_of).days)
        cumulative_contract_demand += scheduled["quantity"]
        projected_stock = available_stock - daily_rate * days_until_visit - cumulative_contract_demand
        if reorder_point is not None and projected_stock <= reorder_point and contract_reorder_date is None:
            contract_reorder_date = scheduled["date"]
        if projected_stock <= 0 and contract_stockout_date is None:
            contract_stockout_date = scheduled["date"]
    reorder_trigger_date = min(
        (candidate for candidate in (reorder_trigger_date, contract_reorder_date) if candidate is not None),
        default=None,
    )
    order_date = reorder_trigger_date - timedelta(days=lead_time or 0) if reorder_trigger_date else None
    if available_stock == 0:
        order_date = as_of
    elif reorder_point is not None and available_stock <= reorder_point:
        order_date = as_of
    elif order_date is not None and order_date < as_of:
        order_date = as_of
    forecast_window_start = order_date or as_of
    forecast_window_end = forecast_window_start + timedelta(days=max(30, math.ceil(lead_time or 0)))
    scheduled_demand_in_window = sum(
        scheduled["quantity"] for scheduled in scheduled_events
        if scheduled["date"] <= forecast_window_end
    )
    if reorder_point is not None:
        order_quantity = math.ceil(max(0, reorder_point + (monthly_rate if monthly_rate > 0 else 0) + scheduled_demand_in_window - available_stock))
    elif available_stock == 0 and minimum > 0:
        # Recompléter le seuil configuré est une action de stock certaine,
        # même lorsque la prévision de consommation n'est pas calculable.
        order_quantity = minimum
    else:
        order_quantity = None
    baseline_stockout_date = as_of + timedelta(days=max(0, math.floor(stockout_days))) if stockout_days is not None else None
    stockout_date = min(
        (candidate for candidate in (baseline_stockout_date, contract_stockout_date) if candidate is not None),
        default=None,
    )
    scheduled_demand_30 = sum(
        scheduled["quantity"] for scheduled in scheduled_events
        if scheduled["date"] <= as_of + timedelta(days=30)
    )
    probability_30 = _poisson_tail_at_least(monthly_rate + scheduled_demand_30, max(0, available_stock - minimum)) if (monthly_rate > 0 or scheduled_demand_30 > 0) else (1.0 if available_stock <= minimum else None)

    history_months = min(12.0, months_observed) if events else 0.0
    confidence = min(100, round(25 + min(35, len(events) * 5) + min(25, history_months / 12 * 25) + (15 if lead_time is not None else 0) + (10 if unit_price and unit_price > 0 else 0)))
    if not events and contract_demand["quantite_quota_contrat"] > 0:
        confidence = max(confidence, 55)
    elif not events and available_stock > 0:
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
    if available_stock == 0:
        urgency = "CRITIQUE"
    elif reorder_point is not None and available_stock <= reorder_point:
        urgency = "HAUTE" if lead_time and lead_time > 0 else "CRITIQUE"
    elif contract_stockout_date is not None and (contract_stockout_date - as_of).days <= (lead_time or 0):
        urgency = "CRITIQUE"
    elif contract_reorder_date is not None and order_date == as_of:
        urgency = "HAUTE"
    elif stockout_date is not None and lead_time is not None and (stockout_date - as_of).days <= lead_time:
        urgency = "HAUTE"
    elif probability_30 is not None and probability_30 >= 0.5:
        urgency = "NORMALE"
    else:
        urgency = "BASSE" if events else "UNKNOWN"

    # Un stock nul est une urgence connue, mais il ne suffit pas à fabriquer
    # une prévision de quantité/date sans consommation et délai documentés.
    prediction_available = bool(
        lead_time is not None
        and (monthly_rate > 0 or contract_demand["quantite_totale"] > 0)
        and (events or contract_demand["quantite_totale"] > 0)
    )
    reason = (
        "Stock réservé par des demandes de techniciens en attente" if pending_quantity >= stock and pending_quantity > 0 else
        "Stock épuisé" if stock == 0 else
        "Stock sous le point de commande calculé" if reorder_point is not None and available_stock <= reorder_point else
        f"{contract_demand['interventions_planifiees']} maintenance(s) contractuelle(s) à venir, {contract_demand['quantite_totale']:.2f} unité(s) intégrée(s)" if contract_demand["quantite_totale"] > 0 else
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
        "stock_disponible_apres_demandes": available_stock,
        "demandes_pieces_en_attente": pending_quantity,
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
        "jours_avant_rupture": round((stockout_date - as_of).days, 1) if stockout_date is not None else None,
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
        "demande_contrats_futurs": {
            **contract_demand,
            "events": [
                {**event, "date": event["date"].isoformat()}
                for event in scheduled_events
            ],
        },
        "diagnostics": diagnostics,
        "historique": {"evenements": len(events), "mois_observes": round(history_months, 1)},
        "modele": "weighted_poisson_reorder_point-contracts-v2",
    }


def predict_spare_parts(conn: Any, piece_id: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    pieces = _piece_rows(conn)
    if piece_id is not None:
        pieces = [piece for piece in pieces if int(piece.get("id") or 0) == int(piece_id)]
    if not pieces:
        return []
    interventions = _intervention_rows(conn)
    contracts = _contract_rows(conn)
    planning_rows = _contract_planning_rows(conn)
    pending_requests = _pending_part_request_rows(conn)
    equipment_rows = _equipment_client_rows(conn)
    clients_by_type: dict[str, set[str]] = defaultdict(set)
    equipment_types = {
        _norm(equipment.get("nom")): _norm(equipment.get("type"))
        for equipment in equipment_rows
        if _norm(equipment.get("nom")) and _norm(equipment.get("type"))
    }
    for equipment in equipment_rows:
        equipment_type = _norm(equipment.get("type"))
        client = str(equipment.get("client") or "").strip()
        if equipment_type and client:
            clients_by_type[equipment_type].add(client)
    predictions = []
    for piece in pieces:
        prediction = _prediction_for_piece(
            piece, interventions, contracts, planning_rows, pending_requests, equipment_types, date.today(),
        )
        fleet_clients = clients_by_type.get(_norm(piece.get("equipement_type")), set())
        contract_clients = set(prediction.get("demande_contrats_futurs", {}).get("clients") or [])
        prediction["clients_utilisateurs"] = sorted(
            set(prediction.get("clients_utilisateurs") or []).union(fleet_clients, contract_clients),
        )
        contract_coverage = [
            item for client in prediction["clients_utilisateurs"]
            for item in [_client_contract(client, prediction.get("reference"), contracts)]
            if item
        ]
        seen_contracts = set()
        prediction["contrats"] = [
            item for item in contract_coverage
            if not (item.get("id") in seen_contracts or seen_contracts.add(item.get("id")))
        ]
        predictions.append(prediction)
    priority = {"CRITIQUE": 0, "HAUTE": 1, "NORMALE": 2, "BASSE": 3, "UNKNOWN": 4}
    predictions.sort(key=lambda item: (priority.get(item["urgence"], 9), item["jours_jusqua_commande"] if item["jours_jusqua_commande"] is not None else 99999, item["designation"]))
    return predictions[:limit] if limit else predictions


def predict_piece_order_date(conn: Any, piece_id: int) -> dict[str, Any] | None:
    predictions = predict_spare_parts(conn, piece_id=piece_id)
    return predictions[0] if predictions else None
