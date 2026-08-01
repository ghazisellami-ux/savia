"""Data-driven equipment failure prediction.

The prediction page must not present deterministic UI values as probabilities.
This module builds machine-level features from the maintenance history and
predicts the probability of at least one corrective failure in a fixed horizon.

The engine deliberately has a transparent fallback:
* with enough historical snapshots it fits a small regularised logistic model;
* otherwise it uses a Bayesian Poisson hazard estimate from real failure rates.

Both paths return the features, data quality, horizon and temporal validation
metadata so consumers can explain when a result is not reliable enough.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import numpy as np


HORIZON_DAYS = 30
MODEL_VERSION = "equipment-risk-v2"
TUBE_REPLACEMENT_PROTECTION_DAYS = 730
DEFAULT_COMPONENT_REPLACEMENT_PROTECTION_DAYS = 365

FEATURE_NAMES = (
    "failures_30d",
    "failures_90d",
    "failures_365d",
    "failures_total",
    "open_failures",
    "days_since_failure",
    "preventive_180d",
    "preventive_overdue",
    "days_since_maintenance",
    "age_years",
    "mttr_hours",
    "error_events_90d",
    "high_priority_events_90d",
    "parts_events_365d",
    "diagnostic_events_365d",
    "recurring_causes_365d",
    "diagnostic_severity_365d",
    "status_risk",
    "warranty_active",
    "observed_years",
)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().casefold())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _key(machine: Any, client: Any) -> tuple[str, str]:
    return _norm(machine), _norm(client)


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None


def _days_since(value: date | None, as_of: date, default: int = 9999) -> int:
    return max(0, (as_of - value).days) if value else default


def _is_cancelled(value: Any) -> bool:
    return any(token in _norm(value) for token in ("annule", "refuse", "cancelled", "canceled"))


def _is_traceability(value: Any) -> bool:
    return any(token in _norm(value) for token in ("installation", "formation"))


def _is_preventive(value: Any) -> bool:
    value = _norm(value)
    return any(token in value for token in ("prevent", "preven", "controle", "inspection"))


def _is_non_failure_maintenance(value: Any) -> bool:
    value = _norm(value)
    return _is_preventive(value) or any(
        token in value for token in ("calibr", "installation", "formation", "inspection")
    )


def _is_closed(value: Any) -> bool:
    return any(token in _norm(value) for token in ("cloture", "termine", "complete", "closed", "resolved"))


def _priority_is_high(value: Any) -> bool:
    value = _norm(value)
    return any(token in value for token in ("haute", "urgent", "critique", "high"))


def _status_risk(value: Any) -> float:
    value = _norm(value)
    if value in {"hors service", "en panne"}:
        return 1.0
    if value == "critique":
        return 0.85
    if value == "en atelier":
        return 0.65
    if value in {"en cours", "a surveiller"}:
        return 0.35
    return 0.0


def _split_parts(value: Any) -> list[str]:
    return [part.strip() for part in re.split(r"[,;]", str(value or "")) if part.strip()]


def _mentions_component(text: Any, component: str) -> bool:
    text_norm = _norm(text)
    component_norm = _norm(component)
    if not text_norm or not component_norm:
        return False
    if component_norm in text_norm:
        return True
    tokens = [token for token in re.split(r"[^a-z0-9]+", component_norm) if len(token) >= 4]
    return bool(tokens and sum(token in text_norm for token in tokens) >= max(1, len(tokens) // 2))


def _is_replacement_event(item: dict[str, Any], component: str) -> bool:
    text = _diagnostic_text(item)
    replacement_terms = ("remplac", "change", "install", "neuf", "monte", "pose")
    return _mentions_component(item.get("pieces_utilisees"), component) and any(
        term in _norm(text) for term in replacement_terms
    )


def _component_selection(
    failures: list[dict[str, Any]],
    components: Counter[str],
    as_of: date,
    all_items: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    """Avoid recommending a recently replaced part unless a later fault confirms it."""
    latest_replacements: dict[str, date] = {}
    for item in all_items or failures:
        event_date = _date(item.get("date"))
        if not event_date:
            continue
        for component in components:
            if _is_replacement_event(item, component):
                latest_replacements[component] = max(latest_replacements.get(component, date.min), event_date)

    protected: list[str] = []
    for component, replacement_date in latest_replacements.items():
        protection_days = (
            TUBE_REPLACEMENT_PROTECTION_DAYS
            if any(token in _norm(component) for token in ("tube", "rayon", "rx"))
            else DEFAULT_COMPONENT_REPLACEMENT_PROTECTION_DAYS
        )
        if (as_of - replacement_date).days > protection_days:
            continue
        later_fault = any(
            (_date(item.get("date")) or date.min) > replacement_date
            and _mentions_component(_diagnostic_text(item), component)
            and any(term in _norm(_diagnostic_text(item)) for term in ("defaill", "panne", "anomal", "erreur", "surtension", "casse", "brule", "hs"))
            for item in failures
        )
        if not later_fault:
            protected.append(component)

    for component, _count in components.most_common():
        if component not in protected:
            return component, protected
    if protected:
        return "Composant remplacé récemment — confirmer avant remplacement", protected
    return "Pièce à déterminer", []


def _diagnostic_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(field) or "").strip()
        for field in ("probleme", "cause", "solution", "description")
        if str(item.get(field) or "").strip()
    )


def _diagnostic_severity(item: dict[str, Any]) -> int:
    text = _norm(_diagnostic_text(item))
    severe_terms = (
        "critique", "urgent", "arret", "immobil", "rayonnement", "surchauff",
        "incend", "fumee", "electrique", "patient", "securite", "danger",
    )
    return sum(1 for term in severe_terms if term in text)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _row_dicts(conn: Any, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query).fetchall()]


def _equipment_rows(conn: Any) -> list[dict[str, Any]]:
    return _row_dicts(
        conn,
        """
        SELECT id, nom, type, fabricant, modele, num_serie, date_installation,
               derniere_maintenance, statut, client, domaine,
               garantie_debut, garantie_duree
        FROM equipements
        ORDER BY nom, client
        """,
    )


def _intervention_rows(conn: Any) -> list[dict[str, Any]]:
    return _row_dicts(
        conn,
        """
        SELECT id, machine, client, date, date_cloture, type_intervention,
               statut, description, probleme, cause, solution,
               pieces_utilisees, code_erreur, type_erreur,
               priorite, duree_minutes
        FROM interventions
        ORDER BY date
        """,
    )


def _planning_rows(conn: Any) -> list[dict[str, Any]]:
    return _row_dicts(
        conn,
        """
        SELECT machine, client, date_prevue, date_realisee,
               type_maintenance, statut
        FROM planning_maintenance
        ORDER BY date_prevue
        """,
    )


def _feedback_rows(conn: Any) -> list[dict[str, Any]]:
    try:
        return _row_dicts(conn, "SELECT machine, client, resultat FROM prediction_feedback")
    except Exception:
        # Older installations are migrated at startup, but prediction loading
        # must remain available during a rolling deployment.
        return _row_dicts(conn, "SELECT machine, '' AS client, resultat FROM prediction_feedback")


def _assign_interventions(
    equipments: list[dict[str, Any]], interventions: list[dict[str, Any]]
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], int]:
    by_name: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for equipment in equipments:
        eq_key = _key(equipment.get("nom"), equipment.get("client"))
        by_name[eq_key[0]].append(eq_key)

    assigned: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    ambiguous = 0
    for intervention in interventions:
        machine_key = _norm(intervention.get("machine"))
        candidates = by_name.get(machine_key, [])
        if not candidates:
            continue
        client_key = _norm(intervention.get("client"))
        if client_key:
            matches = [candidate for candidate in candidates if candidate[1] == client_key]
        else:
            # Never merge a client-less intervention into duplicate equipment
            # names. It is safer to mark it ambiguous than contaminate a risk.
            matches = candidates if len(candidates) == 1 else []
            if len(candidates) > 1:
                ambiguous += 1
        if len(matches) == 1:
            assigned[matches[0]].append(intervention)
    return assigned, ambiguous


def _assign_planning(
    equipments: list[dict[str, Any]], planning: list[dict[str, Any]]
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    by_name: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for equipment in equipments:
        eq_key = _key(equipment.get("nom"), equipment.get("client"))
        by_name[eq_key[0]].append(eq_key)
    assigned: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in planning:
        candidates = by_name.get(_norm(item.get("machine")), [])
        client_key = _norm(item.get("client"))
        matches = [candidate for candidate in candidates if candidate[1] == client_key] if client_key else (
            candidates if len(candidates) == 1 else []
        )
        if len(matches) == 1:
            assigned[matches[0]].append(item)
    return assigned


def _failure_events(items: Iterable[dict[str, Any]], as_of: date | None = None) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for item in items:
        event_date = _date(item.get("date"))
        if not event_date or (as_of and event_date > as_of):
            continue
        if _is_cancelled(item.get("statut")) or _is_traceability(item.get("type_intervention")):
            continue
        if _is_non_failure_maintenance(item.get("type_intervention")):
            continue
        failures.append(item)
    return failures


def _preventive_events(items: Iterable[dict[str, Any]], as_of: date | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in items:
        event_date = _date(item.get("date"))
        if event_date and (not as_of or event_date <= as_of) and _is_preventive(item.get("type_intervention")):
            if not _is_cancelled(item.get("statut")):
                events.append(item)
    return events


def _feature_vector(
    equipment: dict[str, Any],
    interventions: list[dict[str, Any]],
    planning: list[dict[str, Any]],
    as_of: date,
) -> tuple[np.ndarray, dict[str, Any]]:
    failures = _failure_events(interventions, as_of)
    preventive = _preventive_events(interventions, as_of)
    failure_dates = [_date(item.get("date")) for item in failures]
    failure_dates = [item for item in failure_dates if item]
    preventive_dates = [_date(item.get("date")) for item in preventive]
    preventive_dates = [item for item in preventive_dates if item]

    install_date = _date(equipment.get("date_installation"))
    first_event = min(failure_dates + preventive_dates, default=None)
    observation_start = min(item for item in (install_date, first_event) if item) if (install_date or first_event) else as_of - timedelta(days=365)
    observed_days = max(30, (as_of - observation_start).days)
    days_since_failure = _days_since(max(failure_dates) if failure_dates else None, as_of)
    latest_maintenance = max(
        [item for item in preventive_dates if item] + [_date(equipment.get("derniere_maintenance")) or date.min]
    )

    recent_failures = lambda days: sum(1 for item in failure_dates if (as_of - item).days <= days)
    relevant_plans = [
        item for item in planning
        if _date(item.get("date_prevue")) and _date(item.get("date_prevue")) <= as_of
        and not _is_closed(item.get("statut"))
        and not _date(item.get("date_realisee"))
    ]
    age_years = max(0.0, (as_of - install_date).days / 365.25) if install_date else 0.0
    warranty_end = None
    warranty_start = _date(equipment.get("garantie_debut"))
    warranty_days = _safe_float(equipment.get("garantie_duree"), 0)
    if warranty_start and warranty_days > 0:
        warranty_end = warranty_start + timedelta(days=int(warranty_days))

    mttr_hours = (
        sum(_safe_float(item.get("duree_minutes")) for item in failures) / len(failures) / 60
        if failures else 0.0
    )
    error_events = sum(
        1 for item in failures
        if _days_since(_date(item.get("date")), as_of) <= 90
        and (str(item.get("code_erreur") or "").strip() or str(item.get("type_erreur") or "").strip())
    )
    high_priority_events = sum(
        1 for item in failures
        if _days_since(_date(item.get("date")), as_of) <= 90 and _priority_is_high(item.get("priorite"))
    )
    parts_events = sum(
        len(_split_parts(item.get("pieces_utilisees")))
        for item in failures
        if _days_since(_date(item.get("date")), as_of) <= 365
    )
    diagnostic_items = [
        item for item in failures
        if _days_since(_date(item.get("date")), as_of) <= 365 and _diagnostic_text(item)
    ]
    causes = [
        _norm(item.get("cause"))
        for item in diagnostic_items
        if _norm(item.get("cause"))
    ]
    cause_counts = Counter(causes)
    recurring_causes = sum(count - 1 for count in cause_counts.values() if count > 1)
    diagnostic_severity = sum(_diagnostic_severity(item) for item in diagnostic_items)
    open_failures = sum(1 for item in failures if not _is_closed(item.get("statut")))
    status_risk = _status_risk(equipment.get("statut"))
    warranty_active = bool(warranty_end and warranty_start <= as_of <= warranty_end)
    days_since_maintenance = _days_since(latest_maintenance if latest_maintenance != date.min else None, as_of)

    values = {
        "failures_30d": recent_failures(30),
        "failures_90d": recent_failures(90),
        "failures_365d": recent_failures(365),
        "failures_total": len(failures),
        "open_failures": open_failures,
        "days_since_failure": min(days_since_failure, 730),
        "preventive_180d": sum(1 for item in preventive_dates if (as_of - item).days <= 180),
        "preventive_overdue": len(relevant_plans),
        "days_since_maintenance": min(days_since_maintenance, 730),
        "age_years": min(age_years, 30),
        "mttr_hours": min(mttr_hours, 100),
        "error_events_90d": error_events,
        "high_priority_events_90d": high_priority_events,
        "parts_events_365d": parts_events,
        "diagnostic_events_365d": len(diagnostic_items),
        "recurring_causes_365d": recurring_causes,
        "diagnostic_severity_365d": diagnostic_severity,
        "status_risk": status_risk,
        "warranty_active": 1.0 if warranty_active else 0.0,
        "observed_years": min(observed_days / 365.25, 10),
    }
    vector = np.array([float(values[name]) for name in FEATURE_NAMES], dtype=float)
    components = Counter()
    for item in failures:
        for part in _split_parts(item.get("pieces_utilisees")):
            components[part] += 1
    for item in interventions:
        for part in _split_parts(item.get("pieces_utilisees")):
            components.setdefault(part, 0)
    component, protected_components = _component_selection(failures, components, as_of, interventions)
    details = {
        **values,
        "failure_dates": failure_dates,
        "failures": failures,
        "preventive": preventive,
        "diagnostics": [
            {
                "date": str(item.get("date") or "")[:10],
                "type": str(item.get("type_intervention") or ""),
                "probleme": str(item.get("probleme") or ""),
                "cause": str(item.get("cause") or ""),
                "solution": str(item.get("solution") or ""),
                "code_erreur": str(item.get("code_erreur") or ""),
            }
            for item in sorted(diagnostic_items, key=lambda value: _date(value.get("date")) or date.min, reverse=True)[:5]
        ],
        "component": component,
        "protected_components": protected_components,
        "observed_days": observed_days,
        "data_events": len(failures) + len(preventive),
    }
    return vector, details


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -35, 35)))


def _fit_logistic(samples: list[tuple[date, np.ndarray, int]]) -> dict[str, Any] | None:
    if len(samples) < 30 or len({sample[2] for sample in samples}) < 2 or sum(sample[2] for sample in samples) < 5:
        return None
    samples = sorted(samples, key=lambda item: item[0])
    x = np.vstack([sample[1] for sample in samples])
    y = np.array([sample[2] for sample in samples], dtype=float)
    split = max(1, int(len(samples) * 0.7))
    if split >= len(samples):
        return None
    mean = x[:split].mean(axis=0)
    std = x[:split].std(axis=0)
    std[std < 1e-6] = 1.0
    x_scaled = (x - mean) / std
    x_train = np.column_stack([np.ones(split), x_scaled[:split]])
    weights = np.zeros(x_train.shape[1], dtype=float)
    l2 = 0.1
    for _ in range(450):
        probabilities = _sigmoid(x_train @ weights)
        gradient = (x_train.T @ (probabilities - y[:split])) / split
        gradient[1:] += l2 * weights[1:]
        weights -= 0.12 * gradient
    validation_probabilities = _sigmoid(np.column_stack([np.ones(len(samples) - split), x_scaled[split:]]) @ weights)
    validation_y = y[split:]
    brier = float(np.mean((validation_probabilities - validation_y) ** 2))
    predictions = validation_probabilities >= 0.5
    true_positive = int(np.sum(predictions & (validation_y == 1)))
    predicted_positive = int(np.sum(predictions))
    actual_positive = int(np.sum(validation_y == 1))
    validation = {
        "n": len(validation_y),
        "positifs": actual_positive,
        "precision": round(true_positive / predicted_positive * 100) if predicted_positive else 0,
        "rappel": round(true_positive / actual_positive * 100) if actual_positive else 0,
        "brier": round(brier, 4),
        "split": "temporel 70/30",
    }
    # Refit with all available historical snapshots for current predictions.
    x_all = np.column_stack([np.ones(len(samples)), x_scaled])
    for _ in range(450):
        probabilities = _sigmoid(x_all @ weights)
        gradient = (x_all.T @ (probabilities - y)) / len(samples)
        gradient[1:] += l2 * weights[1:]
        weights -= 0.12 * gradient
    return {"weights": weights, "mean": mean, "std": std, "validation": validation}


def _empirical_probability(
    details: dict[str, Any], cohort_failures: int, cohort_days: int, horizon_days: int
) -> float:
    # Gamma-Poisson smoothing: machines with little history borrow strength
    # from their equipment cohort instead of receiving a fake confidence.
    cohort_rate = cohort_failures / max(cohort_days, 365)
    prior_exposure = 180.0
    hazard = (details["failures_total"] + prior_exposure * cohort_rate) / (
        max(details["observed_days"], 30) + prior_exposure
    )
    probability = 1.0 - math.exp(-max(0.0, hazard) * horizon_days)
    if details["open_failures"]:
        probability = max(probability, 0.65)
    if details["preventive_overdue"]:
        probability = min(0.99, probability * 1.2)
    if details["status_risk"] >= 0.65:
        probability = max(probability, details["status_risk"] * 0.9)
    return min(0.99, max(0.001, probability))


def _cohort_statistics(
    equipments: dict[tuple[str, str], dict[str, Any]],
    details_by_key: dict[tuple[str, str], tuple[np.ndarray, dict[str, Any]]],
) -> dict[str, dict[str, tuple[int, int, int]]]:
    """Aggregate real failure exposure by type, domain, manufacturer and model."""
    groups: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    for eq_key, equipment in equipments.items():
        details = details_by_key[eq_key][1]
        group_values = {
            "type": _norm(equipment.get("type")),
            "domaine": _norm(equipment.get("domaine")),
            "fabricant": _norm(equipment.get("fabricant")),
            "modele": _norm(equipment.get("modele")),
            "fabricant_modele": f"{_norm(equipment.get('fabricant'))}|{_norm(equipment.get('modele'))}",
        }
        for group_name, group_value in group_values.items():
            if not group_value or group_value == "|":
                continue
            bucket = groups[group_name][group_value]
            bucket[0] += details["failures_total"]
            bucket[1] += details["observed_days"]
            bucket[2] += 1
    return {
        group_name: {
            group_value: (values[0], values[1], values[2])
            for group_value, values in group_values.items()
        }
        for group_name, group_values in groups.items()
    }


def _equipment_cohort(
    equipment: dict[str, Any],
    statistics: dict[str, dict[str, tuple[int, int, int]]],
) -> tuple[str, int, int, int]:
    """Select the most specific cohort with at least two observed machines."""
    candidates = [
        ("fabricant_modele", f"{_norm(equipment.get('fabricant'))}|{_norm(equipment.get('modele'))}"),
        ("modele", _norm(equipment.get("modele"))),
        ("type", _norm(equipment.get("type"))),
        ("domaine", _norm(equipment.get("domaine"))),
    ]
    for group_name, group_value in candidates:
        values = statistics.get(group_name, {}).get(group_value)
        if values and values[2] >= 2:
            return f"{group_name}:{group_value}", values[0], values[1], values[2]
    return "global", 0, 0, 0


def _drivers(details: dict[str, Any]) -> list[str]:
    drivers: list[str] = []
    if details["open_failures"]:
        drivers.append(f"{details['open_failures']} panne(s) corrective(s) ouverte(s)")
    if details["failures_90d"]:
        drivers.append(f"{details['failures_90d']} panne(s) sur les 90 derniers jours")
    if details["preventive_overdue"]:
        drivers.append(f"{details['preventive_overdue']} maintenance(s) préventive(s) en retard")
    if details["high_priority_events_90d"]:
        drivers.append("événement(s) de priorité haute récent(s)")
    if details["recurring_causes_365d"]:
        drivers.append(f"{details['recurring_causes_365d']} cause(s) récurrente(s) dans les diagnostics")
    if details["diagnostic_severity_365d"]:
        drivers.append("diagnostic(s) contenant un signal de gravité ou de sécurité")
    if details.get("protected_components"):
        drivers.append("composant remplacé récemment : remplacement à confirmer avant action")
    if details["days_since_maintenance"] > 365:
        drivers.append("plus d'un an depuis la dernière maintenance préventive connue")
    if details["age_years"]:
        drivers.append(f"âge estimé : {details['age_years']:.1f} an(s)")
    return drivers[:4] or ["historique de panne limité ou absent"]


def _data_quality(details: dict[str, Any], training_size: int, ambiguous: int) -> int:
    event_score = min(1.0, details["data_events"] / 8)
    coverage_score = min(1.0, details["observed_days"] / 365)
    training_score = min(1.0, training_size / 60)
    ambiguity_penalty = 0.15 if ambiguous else 0.0
    return max(0, min(100, round(35 + 30 * event_score + 25 * coverage_score + 10 * training_score - ambiguity_penalty * 100)))


def predict_equipment_risks(
    conn: Any,
    *,
    client: str | None = None,
    equipment_type: str | None = None,
    horizon_days: int = HORIZON_DAYS,
) -> dict[str, Any]:
    """Return transparent 30-day risk predictions for the equipment fleet."""
    as_of = date.today()
    horizon_days = max(7, min(int(horizon_days), 90))
    equipments = _equipment_rows(conn)
    normalized_client = _norm(client)
    normalized_type = _norm(equipment_type)
    equipments = [
        equipment for equipment in equipments
        if (not normalized_client or _norm(equipment.get("client")) == normalized_client)
        and (not normalized_type or _norm(equipment.get("type")) == normalized_type)
    ]
    interventions = _intervention_rows(conn)
    planning = _planning_rows(conn)
    assigned_interventions, ambiguous = _assign_interventions(equipments, interventions)
    assigned_planning = _assign_planning(equipments, planning)

    by_key = {_key(equipment.get("nom"), equipment.get("client")): equipment for equipment in equipments}
    details_by_key: dict[tuple[str, str], tuple[np.ndarray, dict[str, Any]]] = {}
    for eq_key, equipment in by_key.items():
        details_by_key[eq_key] = _feature_vector(
            equipment,
            assigned_interventions.get(eq_key, []),
            assigned_planning.get(eq_key, []),
            as_of,
        )
    cohort_statistics = _cohort_statistics(by_key, details_by_key)

    # Historical monthly snapshots create a temporal holdout instead of a
    # random split, which is appropriate for forecasting future breakdowns.
    samples: list[tuple[date, np.ndarray, int]] = []
    history_start = min(
        [event_date for _, details in details_by_key.values() for event_date in details["failure_dates"]],
        default=as_of - timedelta(days=365),
    )
    for eq_key, equipment in by_key.items():
        events = assigned_interventions.get(eq_key, [])
        start = max(_date(equipment.get("date_installation")) or history_start, history_start)
        snapshot = start
        while snapshot <= as_of - timedelta(days=horizon_days):
            vector, _ = _feature_vector(
                equipment, events, assigned_planning.get(eq_key, []), snapshot
            )
            future_failures = [
                event for event in _failure_events(events)
                if snapshot < (_date(event.get("date")) or snapshot) <= snapshot + timedelta(days=horizon_days)
            ]
            samples.append((snapshot, vector, 1 if future_failures else 0))
            snapshot += timedelta(days=30)

    model = _fit_logistic(samples)
    feedback = _feedback_rows(conn)
    feedback_by_key: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in feedback:
        feedback_by_key[_key(row.get("machine"), row.get("client"))][str(row.get("resultat") or "")] += 1

    global_failures = sum(details["failures_total"] for _, details in details_by_key.values())
    global_days = sum(details["observed_days"] for _, details in details_by_key.values())
    output: list[dict[str, Any]] = []
    for eq_key, equipment in by_key.items():
        vector, details = details_by_key[eq_key]
        cohort_name, local_failures, local_days, cohort_size = _equipment_cohort(equipment, cohort_statistics)
        if cohort_size < 2:
            local_failures, local_days, cohort_size = global_failures, global_days, 0
        details["cohorte"] = cohort_name
        if model:
            scaled = (vector - model["mean"]) / model["std"]
            model_probability = float(_sigmoid(np.array([1.0, *scaled]) @ model["weights"]))
            cohort_probability = _empirical_probability(
                details,
                local_failures,
                local_days,
                horizon_days,
            )
            probability = 0.75 * model_probability + 0.25 * cohort_probability
            model_source = "logistic_temporal"
        else:
            probability = _empirical_probability(
                details,
                local_failures,
                local_days,
                horizon_days,
            )
            model_source = "bayesian_hazard"

        feedback_counts = feedback_by_key.get(eq_key, Counter())
        feedback_total = sum(feedback_counts.values())
        feedback_resolved = feedback_counts["correct"] + feedback_counts["faux_positif"]
        feedback_precision = (
            feedback_counts["correct"] / feedback_resolved if feedback_resolved else None
        )
        if feedback_precision is not None and feedback_resolved >= 3:
            # Conservative post-deployment calibration: repeated false positives
            # reduce the forecast until enough new outcomes are observed.
            probability *= 0.8 + 0.2 * feedback_precision

        status = _norm(equipment.get("statut"))
        if status == "hors service":
            probability = max(probability, 0.99)
        elif status in {"critique", "en panne"}:
            probability = max(probability, 0.75)

        probability = min(0.99, max(0.001, probability))
        quality = _data_quality(details, len(samples), ambiguous)
        output.append({
            "equipment_id": equipment.get("id"),
            "machine": equipment.get("nom", ""),
            "client": equipment.get("client", ""),
            "type": equipment.get("type", ""),
            "fabricant": equipment.get("fabricant", ""),
            "modele": equipment.get("modele", ""),
            "statut": equipment.get("statut", ""),
            "domaine": equipment.get("domaine", ""),
            "cohorte": cohort_name,
            "horizon_jours": horizon_days,
            "date_calcul": as_of.isoformat(),
            "risque_pct": round(probability * 100, 1),
            "score_sante": round((1 - probability) * 100),
            "fiabilite_donnees_pct": quality,
            "modele": model_source,
            "composant_a_risque": details["component"],
            "composants_proteges": details.get("protected_components", []),
            "facteurs": _drivers(details),
            "diagnostics": details["diagnostics"],
            "features": {name: round(float(details[name]), 3) for name in FEATURE_NAMES},
            "feedback": {
                "total": feedback_total,
                "correct": feedback_counts["correct"],
                "faux_positif": feedback_counts["faux_positif"],
                "decale": feedback_counts["decale"],
                "precision": round(feedback_precision * 100) if feedback_precision is not None else None,
            },
        })

    output.sort(key=lambda item: item["risque_pct"], reverse=True)
    return {
        "items": output,
        "meta": {
            "model_version": MODEL_VERSION,
            "model": "logistic_temporal" if model else "bayesian_hazard",
            "horizon_jours": horizon_days,
            "date_calcul": as_of.isoformat(),
            "training_snapshots": len(samples),
            "ambiguous_interventions": ambiguous,
            "validation": model["validation"] if model else {
                "n": 0,
                "message": "Historique insuffisant pour une validation temporelle; estimation bayésienne utilisée.",
            },
            "interpretation": "Probabilité d'au moins une panne corrective dans l'horizon indiqué; ce n'est pas une date exacte de panne.",
        },
    }
