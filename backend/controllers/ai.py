"""AI analysis and chat routes."""

import json
import math
import re
import unicodedata
from datetime import date

from api.runtime import (
    Depends,
    HTTPException,
    Header,
    Optional,
    _ai_language_instruction,
    _fallback_translate_payload_for_lang,
    _force_ai_payload_language,
    _get_app_language,
    _normalize_lang,
    app,
    datetime,
    get_config,
    get_db,
    lire_contrats,
    lire_equipements,
    lire_interventions,
    lire_pieces,
    lire_planning,
    log_audit,
    logger,
)
from api.security import (
    _verify_token,
    require_roles,
)
from services.ai_governance import governed_ai_endpoint


_AI_COUNTRY_NAMES = {
    "TN": "Tunisie",
    "DZ": "Algérie",
    "MA": "Maroc",
    "SN": "Sénégal",
    "FR": "France",
    "US": "États-Unis",
    "QA": "Qatar",
    "SA": "Arabie saoudite",
}


def _configured_country_names():
    """Return the countries selected in Administration > Settings for AI prompts."""
    raw_selection = str(get_config("pays", "TN") or "TN")
    selected_values = [
        value.strip()
        for value in re.split(r"[,;]", raw_selection)
        if value.strip()
    ]
    if not selected_values:
        selected_values = ["TN"]

    custom_names = {}
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT code, nom FROM pays_custom").fetchall()
            custom_names = {
                str(row.get("code") or "").strip().upper(): str(row.get("nom") or "").strip()
                for row in rows
                if row.get("code") and row.get("nom")
            }
    except Exception as country_error:
        # A missing optional custom-country table must not prevent an AI report.
        logger.debug("Impossible de charger les noms de pays personnalisés: %s", country_error)

    names = []
    seen = set()
    for value in selected_values:
        normalized = unicodedata.normalize("NFKD", value)
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        key = normalized.strip().upper()
        name = custom_names.get(key) or _AI_COUNTRY_NAMES.get(key) or value
        dedupe_key = name.casefold()
        if dedupe_key not in seen:
            seen.add(dedupe_key)
            names.append(name)
    return ", ".join(names)


def _cost_number(value):
    """Return a finite numeric value, or None for missing/invalid AI output."""
    try:
        if isinstance(value, str):
            text = value.strip().replace("\u00a0", "").replace(" ", "")
            text = re.sub(r"[^0-9,.-]", "", text)
            if "," in text and "." in text:
                text = text.replace(".", "") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
            text = text.replace(",", ".")
            value = text
        number = float(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def _cost_normalize(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _same_equipment_family(part_type, equipment_type):
    part_norm = _cost_normalize(part_type)
    equipment_norm = _cost_normalize(equipment_type)
    if not part_norm or not equipment_norm:
        return True
    if part_norm in equipment_norm or equipment_norm in part_norm:
        return True
    families = (
        ("mammo", "mammographe", "mammographie"),
        ("scanner", "ct"),
        ("irm", "resonance", "magnetique"),
        ("echo", "echographe", "echographie"),
        ("radio", "radiographie", "rayon"),
    )
    return any(any(token in part_norm for token in family) and any(token in equipment_norm for token in family) for family in families)


def _find_catalog_part(text, parts_catalog, equipment_type=None):
    """Match an AI action to a catalogue reference/designation without guessing."""
    normalized_text = _cost_normalize(text)
    if not normalized_text:
        return None

    # References are the strongest match (for example: "Ref: TUBE RX MAMMO").
    compatible_parts = [part for part in parts_catalog if _same_equipment_family(part.get("equipement_type"), equipment_type)]
    for part in compatible_parts:
        reference = _cost_normalize(part.get("reference"))
        if reference and reference in normalized_text:
            return part

    # Only accept a full designation match; partial names are too ambiguous.
    for part in compatible_parts:
        designation = _cost_normalize(part.get("designation"))
        if designation and len(designation) >= 6 and designation in normalized_text:
            return part
    return None


def _machine_key(value):
    """Normalize a machine label, ignoring the client suffix when present."""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", str(value or ""))
    return _cost_normalize(base)


def _contract_for_machine(machine, contracts):
    client_match = re.search(r"\(([^()]*)\)\s*$", str(machine or ""))
    client_key = _cost_normalize(client_match.group(1) if client_match else "")
    machine_key = _machine_key(machine)
    for contract in contracts:
        if client_key and client_key != _cost_normalize(contract.get("client")):
            continue
        linked_equipment = _machine_key(contract.get("equipement"))
        if linked_equipment and linked_equipment not in machine_key and machine_key not in linked_equipment:
            continue
        return contract
    return None


def _contract_coverage(contract):
    """Return only coverage that can be inferred explicitly from the contract."""
    if not contract:
        return {"parts": None, "labor": None, "label": "Contrat introuvable"}
    contract_type = str(contract.get("type_contrat") or "").lower()
    has_parts = (
        ("pièces uniquement" in contract_type or "pieces uniquement" in contract_type)
        or bool(contract.get("avec_pieces"))
        or bool(str(contract.get("pieces_incluses") or "").strip())
    )
    if "full service" in contract_type:
        has_parts = True
        has_labor = True
    elif "main" in contract_type and "oeuvre" in contract_type:
        has_labor = True
    else:
        has_labor = None
    return {"parts": has_parts, "labor": has_labor, "label": contract.get("type_contrat") or "Contrat actif"}


def _ai_json_safe(value):
    """Convert database/DataFrame values to JSON-safe values for the AI prompt."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _ai_json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if str(value) in {"<NA>", "NaT", "nan", "NaN"}:
        return None
    if isinstance(value, dict):
        return {str(key): _ai_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_ai_json_safe(item) for item in value]
    return value


def _ai_records(df, fields, client_scope=None, client_field=None, machine_clients=None):
    """Return relevant, non-binary database rows while preserving real values."""
    if df is None or getattr(df, "empty", True):
        return []
    available = [field for field in fields if field in df.columns]
    rows = []
    for raw in df.to_dict(orient="records"):
        client = raw.get(client_field) if client_field else None
        if not client and machine_clients and raw.get("machine"):
            client = machine_clients.get(str(raw.get("machine")).strip().lower(), "")
        if client_scope and str(client or "") not in client_scope:
            continue
        row = {field: _ai_json_safe(raw.get(field)) for field in available}
        if client_field and client_field not in row:
            row[client_field] = _ai_json_safe(client)
        elif client_field and not row.get(client_field) and client:
            row[client_field] = _ai_json_safe(client)
        rows.append(row)
    return rows


def _build_financial_ai_context(clients_data, tco_data):
    """Build the complete financial context from authoritative server data."""
    df_contracts = lire_contrats()
    df_interv = lire_interventions()
    df_equip = lire_equipements()
    df_planning = lire_planning()
    df_pieces = lire_pieces()

    client_scope = {
        str(row.get("client") or "").strip()
        for row in clients_data
        if str(row.get("client") or "").strip()
    }
    equipment_clients = {}
    if df_equip is not None and not df_equip.empty:
        for row in df_equip.to_dict(orient="records"):
            machine = str(row.get("Nom") or row.get("nom") or "").strip().lower()
            if machine:
                equipment_clients[machine] = str(row.get("Client") or row.get("client") or "").strip()

    # The dashboard payload is enriched with counts calculated from the real
    # intervention rows, instead of relying on fields supplied by the browser.
    client_rows = []
    for client_row in clients_data:
        enriched = dict(client_row)
        name = str(enriched.get("client") or "").strip()
        rows = []
        if df_interv is not None and not df_interv.empty:
            for raw in df_interv.to_dict(orient="records"):
                raw_client = str(raw.get("client") or "").strip()
                machine_client = equipment_clients.get(str(raw.get("machine") or "").strip().lower(), "")
                if name and (raw_client == name or (not raw_client and machine_client == name)):
                    rows.append(raw)
        types = [str(row.get("type_intervention") or "").lower() for row in rows]
        enriched["nb_correctives"] = sum("correct" in value for value in types)
        enriched["nb_preventives"] = sum("correct" not in value for value in types)
        enriched["interventions_avec_cause_confirmee"] = sum(bool(str(row.get("cause") or "").strip()) for row in rows)
        enriched["interventions_avec_solution_confirmee"] = sum(bool(str(row.get("solution") or "").strip()) for row in rows)
        client_rows.append(_ai_json_safe(enriched))

    contract_fields = [
        "id", "client", "type_contrat", "montant", "date_debut", "date_fin",
        "equipement", "equipement_id", "pieces_incluses", "avec_pieces", "rappel_avant_jours",
    ]
    equipment_fields = [
        "id", "Nom", "Client", "Type", "Fabricant", "Modele", "DateInstallation",
        "DernieresMaintenance", "Statut", "Domaine", "Ville", "Region", "service",
        "garantie_debut", "garantie_duree", "Notes",
    ]
    intervention_fields = [
        "id", "date", "client", "machine", "technicien", "type_intervention", "statut",
        "description", "probleme", "cause", "solution", "code_erreur", "type_erreur", "priorite",
        "cout", "cout_pieces", "duree_minutes", "duree_deplacement", "pieces_utilisees",
        "date_debut_intervention", "date_cloture", "fiche_validation", "planning_id", "notes",
    ]
    planning_fields = [
        "id", "client", "machine", "type_maintenance", "date_prevue", "date_realisee",
        "statut", "technicien_assigne", "description", "notes", "priorite",
    ]
    piece_fields = [
        "id", "reference", "designation", "domaine", "equipement_type", "stock_actuel",
        "stock_minimum", "fournisseur", "prix_unitaire", "consommation_moyenne_mois",
        "delai_fournisseur_jours", "criticite", "nombre_equipements_relies", "utilisation_recente_30j",
        "data_confidence", "notes",
    ]

    contracts = _ai_records(df_contracts, contract_fields, client_scope, "client")
    equipment = _ai_records(df_equip, equipment_fields, client_scope, "Client")
    interventions = _ai_records(
        df_interv,
        intervention_fields,
        client_scope,
        "client",
        machine_clients=equipment_clients,
    )
    planning = _ai_records(
        df_planning,
        planning_fields,
        client_scope,
        "client",
        machine_clients=equipment_clients,
    )
    # Stock has no client foreign key. It is still relevant to profitability
    # because parts costs and shortages affect service margin globally.
    pieces = _ai_records(df_pieces, piece_fields)

    scoped_tco = [
        row for row in (tco_data or [])
        if not client_scope or str(row.get("client") or "").strip() in client_scope
    ]
    coverage = {
        "clients": len(client_rows),
        "contrats": len(contracts),
        "equipements": len(equipment),
        "interventions": len(interventions),
        "maintenances_planifiees": len(planning),
        "pieces_stock": len(pieces),
        "equipements_tco_transmis": len(scoped_tco),
        "tco_complet": True,
        "detail_interventions_transmis": True,
    }
    return {
        "couverture": coverage,
        "clients": client_rows,
        "contrats": contracts,
        "equipements": equipment,
        "interventions": interventions,
        "maintenances_planifiees": planning,
        "pieces_stock": pieces,
        "tco_equipements": _ai_json_safe(scoped_tco),
    }


def _apply_verified_costs(result, parts_catalog, historical_corrective_costs, cost_context, sym):
    """Replace unsupported AI cost claims with auditable catalogue/history values."""
    if not isinstance(result, dict):
        return result

    recommendations = result.get("recommandations_prioritaires") or []
    alerts = result.get("alertes_critiques") or []
    all_actions = [(item, "recommandation") for item in recommendations if isinstance(item, dict)]
    all_actions += [(item, "action_immediate") for item in alerts if isinstance(item, dict)]

    hourly_rate = _cost_number(cost_context.get("hourly_rate"))
    machine_mttr_minutes = cost_context.get("machine_mttr_minutes") or {}
    equipment_types = cost_context.get("equipment_types") or {}
    historical_component_costs = cost_context.get("historical_component_costs") or {}
    protected_components_by_machine = cost_context.get("protected_components_by_machine") or {}
    contracts = cost_context.get("contracts") or []
    for item, action_key in all_actions:
        action_text = " ".join(str(item.get(key) or "") for key in (action_key, "cause", "facteurs", "recommandations"))
        machine_key = _machine_key(item.get("machine"))
        protected_components = protected_components_by_machine.get(machine_key) or []
        action_norm = _cost_normalize(action_text)
        replacement_request = "remplac" in action_norm or "chang" in action_norm
        protected_match = any(
            _cost_normalize(component) in action_norm
            or any(token in action_norm for token in ("tube", "rayon", "rx") if token in _cost_normalize(component))
            for component in protected_components
        )
        if protected_match and replacement_request:
            item[action_key] = "Inspection du composant remplacé récemment, vérification de l'alimentation et recherche de cause racine; aucun nouveau remplacement sans diagnostic postérieur confirmant la défaillance."
            action_text = item[action_key]
        part = None if protected_match and replacement_request else _find_catalog_part(action_text, parts_catalog, equipment_types.get(machine_key))
        if part:
            component_history = None
            for component_label in (part.get("reference"), part.get("designation")):
                candidate = historical_component_costs.get((machine_key, _cost_normalize(component_label)))
                if candidate is not None:
                    component_history = candidate
                    break
            machine_cost = component_history
        if not part:
            machine_cost = historical_corrective_costs.get(machine_key)
        contract = _contract_for_machine(item.get("machine"), contracts)
        coverage = _contract_coverage(contract)
        duration_minutes = _cost_number(machine_mttr_minutes.get(machine_key))
        quantity_match = re.search(r"(?:qty|quantit[eé]|x)\s*[:=]?\s*(\d+)", action_text, re.IGNORECASE)
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        unit_price = _cost_number(part.get("prix_unitaire")) if part else None
        part_cost = round(unit_price * quantity, 2) if unit_price is not None and unit_price > 0 else None
        labor_cost = round((duration_minutes / 60.0) * hourly_rate, 2) if duration_minutes is not None and hourly_rate is not None else None
        internal_total = round(part_cost + labor_cost, 2) if part_cost is not None and labor_cost is not None else None
        billable_total = None
        if internal_total is not None and contract:
            covered_parts = coverage["parts"] is True
            covered_labor = coverage["labor"] is True
            billable_total = round((0 if covered_parts else part_cost) + (0 if covered_labor else labor_cost), 2)

        if part_cost is not None:
            item["cout_piece_reel"] = part_cost
            item["prix_verifie"] = True
            item["source_prix"] = f"Catalogue pièces : {part.get('reference') or part.get('designation')}"
            item["quantite_piece"] = quantity
            item["cout_action_minimum"] = part_cost
        else:
            item["prix_verifie"] = False
            item["source_prix"] = "Prix catalogue introuvable : validation requise"
            item["cout_piece_reel"] = None
            item["cout_action_minimum"] = None

        item["cout_main_oeuvre"] = labor_cost
        item["taux_horaire"] = hourly_rate
        item["duree_estimee_minutes"] = duration_minutes
        item["cout_action_total"] = internal_total
        item["cout_total_action"] = internal_total
        item["cout_estime"] = internal_total
        item["cout_facturable_contrat"] = billable_total
        item["contrat_type"] = coverage["label"]
        item["source_cout"] = "Catalogue pièce + MTTR correctif + taux horaire configuré" if internal_total is not None else "Montant incomplet : prix pièce, durée MTTR ou taux horaire manquant"

        # A gain is only calculable from an actual corrective-cost history and a complete action cost.
        if machine_cost is not None and machine_cost > 0 and internal_total is not None:
            avoided = round(machine_cost, 2)
            net_gain = round(avoided - internal_total, 2)
            item["cout_panne_evite"] = avoided
            item["gain_brut"] = avoided
            item["gain_net"] = net_gain
            item["gain_estime"] = net_gain
            item["gain_potentiel"] = net_gain
            item["source_gain"] = "Coût correctif moyen historique de cette machine"
        else:
            item["cout_panne_evite"] = None
            item["gain_brut"] = None
            item["gain_net"] = None
            item["gain_estime"] = None
            item["gain_potentiel"] = None
            item["source_gain"] = "Non calculable : coût correctif historique absent"

    estimation = result.get("estimation_couts")
    if isinstance(estimation, dict):
        action_items = [item for item, _ in all_actions]
        totals = [float(item["cout_total_action"]) for item in action_items if item.get("cout_total_action") is not None]
        avoided_totals = [float(item["cout_panne_evite"]) for item in action_items if item.get("cout_panne_evite") is not None]
        priced_parts = sum(1 for part in parts_catalog if (_cost_number(part.get("prix_unitaire")) or 0) > 0)
        matched_parts = sum(1 for item in action_items if item.get("prix_verifie") is True)
        estimation["cout_preventif_propose"] = round(sum(totals), 2) if totals else None
        estimation["cout_pannes_evitees"] = round(sum(avoided_totals), 2) if avoided_totals else None
        estimation["gain_potentiel"] = round(sum(avoided_totals) - sum(totals), 2) if totals and avoided_totals else None
        estimation["gain_net"] = estimation["gain_potentiel"]
        estimation["source_prix"] = f"Catalogue : {priced_parts} piece(s) avec prix; {matched_parts} action(s) rattachee(s) a une reference. Taux horaire : {hourly_rate if hourly_rate is not None else 'non configure'} {sym}/h."
        missing = []
        if hourly_rate is None:
            missing.append("taux horaire")
        if priced_parts == 0:
            missing.append("prix unitaires du catalogue")
        if not matched_parts and action_items:
            missing.append("reference de piece correspondant a l'action")
        if missing:
            estimation["detail_preventif"] = "Calcul partiel uniquement : " + ", ".join(missing) + "."
            estimation["hypotheses"] = "Donnees manquantes : " + ", ".join(missing) + ". Les montants doivent etre confirmes avant decision."
            estimation["ratio"] = f"Ratio non calculable : {', '.join(missing)}."
        elif not totals:
            estimation["detail_preventif"] = "Prix et taux disponibles, mais aucune duree MTTR corrective exploitable pour calculer un total."
            estimation["hypotheses"] = "Le cout total sera calcule apres rattachement de l'action a une machine et a son MTTR correctif historique."
            estimation["ratio"] = "Ratio non calculable : duree corrective historique manquante."
        else:
            estimation["detail_preventif"] = "Cout technique calcule avec prix catalogue, MTTR correctif historique et taux horaire configure."
            estimation["hypotheses"] = "Le montant exclut les frais de deplacement non configures et distingue la couverture contractuelle du cout technique interne."
            estimation["ratio"] = "Ratio calcule uniquement lorsque le cout correctif historique et le cout d'action sont disponibles."
        estimation["hypotheses"] = f"{estimation.get('hypotheses', '')} Sources lues par le serveur : {priced_parts} piece(s) avec prix, taux horaire={'oui' if hourly_rate is not None else 'non'}, {matched_parts} action(s) rattachee(s) a une reference."
        estimation["source_prix"] = "Catalogue pièces vérifié; main-d'œuvre/déplacement inclus seulement s'ils sont documentés"
        if False and not totals:
            estimation["hypotheses"] = "Prix de pièce non trouvé dans le catalogue : coût et gain à confirmer avant décision."
        estimation["source_prix"] = f"Catalogue : {priced_parts} piece(s) avec prix; {matched_parts} action(s) rattachee(s) a une reference. Taux horaire : {hourly_rate if hourly_rate is not None else 'non configure'} {sym}/h."
    return result


def _apply_spare_parts_ai_guardrails(result, forecasts, sym):
    """Keep AI purchase recommendations aligned with deterministic forecasts."""
    if not isinstance(result, dict):
        return result
    by_reference = {_cost_normalize(item.get("reference")): item for item in forecasts if item.get("reference")}
    by_designation = {_cost_normalize(item.get("designation")): item for item in forecasts if item.get("designation")}
    verified = []
    for recommendation in result.get("recommandations") or []:
        if not isinstance(recommendation, dict):
            continue
        forecast = by_reference.get(_cost_normalize(recommendation.get("reference")))
        if not forecast:
            forecast = by_designation.get(_cost_normalize(recommendation.get("piece")))
        if not forecast or not (forecast.get("prediction_available") or forecast.get("recommandation_actionnable")):
            continue
        recommendation["piece"] = forecast.get("designation")
        recommendation["reference"] = forecast.get("reference")
        recommendation["quantite"] = forecast.get("quantite_recommandee")
        recommendation["date_achat"] = forecast.get("date_commande")
        recommendation["urgence"] = str(forecast.get("urgence") or "UNKNOWN").lower()
        recommendation["cout_estime"] = forecast.get("cout_estime")
        recommendation["delai_fournisseur"] = forecast.get("delai_fournisseur_jours")
        recommendation["action"] = "Commander immédiatement" if recommendation["urgence"] == "critique" else "Planifier la commande selon la date calculée"
        recommendation["source_calcul"] = "Prévision serveur : consommation réelle, maintenances contractuelles planifiées, stock, délai fournisseur et prix catalogue"
        recommendation["fiabilite_donnees_pct"] = forecast.get("fiabilite_donnees_pct")
        recommendation["raison"] = forecast.get("raison")
        recommendation["prediction_available"] = forecast.get("prediction_available")
        recommendation["recommandation_actionnable"] = forecast.get("recommandation_actionnable")
        recommendation["consommation_mensuelle"] = forecast.get("consommation_mensuelle")
        recommendation["risque_rupture_30j_pct"] = forecast.get("risque_rupture_30j_pct")
        recommendation["demandes_pieces_en_attente"] = forecast.get("demandes_pieces_en_attente", 0)
        recommendation["stock_disponible_apres_demandes"] = forecast.get("stock_disponible_apres_demandes")
        recommendation["clients_utilisateurs"] = forecast.get("clients_utilisateurs") or []
        recommendation["contrats"] = forecast.get("contrats") or []
        recommendation["demande_contrats_futurs"] = forecast.get("demande_contrats_futurs") or {}
        recommendation["diagnostics"] = forecast.get("diagnostics") or []
        verified.append(recommendation)
    # Une rupture effective ne doit pas disparaître parce que le modèle IA
    # n'a pas repris la ligne dans sa réponse JSON.
    represented = {_cost_normalize(item.get("reference")) for item in verified}
    for forecast in forecasts:
        reference_key = _cost_normalize(forecast.get("reference"))
        if not reference_key or reference_key in represented or forecast.get("stock_actuel") != 0:
            continue
        verified.append({
            "piece": forecast.get("designation"),
            "reference": forecast.get("reference"),
            "raison": forecast.get("raison"),
            "action": "Commander immédiatement",
            "quantite": forecast.get("quantite_recommandee"),
            "date_achat": forecast.get("date_commande"),
            "urgence": "critique",
            "cout_estime": forecast.get("cout_estime"),
            "delai_fournisseur": forecast.get("delai_fournisseur_jours"),
            "source_calcul": "Rupture effective, contrats planifiés et stock minimum configuré",
            "fiabilite_donnees_pct": forecast.get("fiabilite_donnees_pct"),
            "prediction_available": forecast.get("prediction_available"),
            "recommandation_actionnable": True,
            "consommation_mensuelle": forecast.get("consommation_mensuelle"),
            "risque_rupture_30j_pct": forecast.get("risque_rupture_30j_pct"),
            "demandes_pieces_en_attente": forecast.get("demandes_pieces_en_attente", 0),
            "stock_disponible_apres_demandes": forecast.get("stock_disponible_apres_demandes"),
            "clients_utilisateurs": forecast.get("clients_utilisateurs") or [],
            "contrats": forecast.get("contrats") or [],
            "demande_contrats_futurs": forecast.get("demande_contrats_futurs") or {},
            "diagnostics": forecast.get("diagnostics") or [],
        })
    result["recommandations"] = verified
    # Expose deterministic calculation data independently of generated prose.
    detailed_forecasts = []
    validation_alerts = []
    for forecast in forecasts:
        missing_data = []
        if not forecast.get("historique", {}).get("evenements"):
            missing_data.append("aucune consommation issue des interventions sur 12 mois")
        if forecast.get("delai_fournisseur_jours") is None:
            missing_data.append("délai fournisseur non renseigné")
        if forecast.get("prix_unitaire") is None:
            missing_data.append("prix unitaire non renseigné")
        if not forecast.get("clients_utilisateurs"):
            missing_data.append("équipement/client utilisateur non identifié")
        detailed_forecasts.append({
            "piece": forecast.get("designation"),
            "reference": forecast.get("reference"),
            "equipement_type": forecast.get("equipement_type"),
            "domaine": forecast.get("domaine"),
            "fournisseur": forecast.get("fournisseur"),
            "clients": forecast.get("clients_utilisateurs") or [],
            "stock_actuel": forecast.get("stock_actuel"),
            "stock_disponible_apres_demandes": forecast.get("stock_disponible_apres_demandes"),
            "demandes_pieces_en_attente": forecast.get("demandes_pieces_en_attente", 0),
            "stock_minimum": forecast.get("stock_minimum"),
            "prix_unitaire": forecast.get("prix_unitaire"),
            "consommation_mensuelle": forecast.get("consommation_mensuelle"),
            "consommation_30j": forecast.get("consommation_30j"),
            "consommation_90j": forecast.get("consommation_90j"),
            "utilisations_total_365j": forecast.get("utilisations_total_365j"),
            "risque_rupture_30j_pct": forecast.get("risque_rupture_30j_pct"),
            "date_commande": forecast.get("date_commande"),
            "date_rupture_prevue": forecast.get("date_rupture_prevue"),
            "quantite_recommandee": forecast.get("quantite_recommandee"),
            "cout_estime": forecast.get("cout_estime"),
            "fiabilite_donnees_pct": forecast.get("fiabilite_donnees_pct"),
            "urgence": forecast.get("urgence"),
            "prediction_available": forecast.get("prediction_available"),
            "recommandation_actionnable": forecast.get("recommandation_actionnable"),
            "raison": forecast.get("raison"),
            "delai_fournisseur_jours": forecast.get("delai_fournisseur_jours"),
            "point_commande": forecast.get("point_commande"),
            "stock_securite": forecast.get("stock_securite"),
            "historique": forecast.get("historique") or {},
            "diagnostics": forecast.get("diagnostics") or [],
            "contrats": forecast.get("contrats") or [],
            "demande_contrats_futurs": forecast.get("demande_contrats_futurs") or {},
            "donnees_manquantes": missing_data,
        })
        if (
            forecast.get("stock_actuel", 0) <= forecast.get("stock_minimum", 0)
            and not forecast.get("prediction_available")
        ):
            validation_alerts.append({
                "reference": forecast.get("reference"),
                "piece": forecast.get("designation"),
                "raison": forecast.get("raison"),
                "action": "Confirmer la consommation, le délai fournisseur et le prix avant de compléter la prévision.",
            })
    result["previsions_detaillees"] = detailed_forecasts
    result["couverture_donnees"] = {
        "references_analysees": len(forecasts),
        "ruptures_effectives": sum(1 for item in forecasts if item.get("stock_actuel") == 0),
        "stocks_sous_seuil": sum(1 for item in forecasts if item.get("stock_actuel", 0) <= item.get("stock_minimum", 0)),
        "predictions_calculables": sum(1 for item in forecasts if item.get("prediction_available")),
        "avec_historique": sum(1 for item in forecasts if item.get("historique", {}).get("evenements")),
        "avec_delai_fournisseur": sum(1 for item in forecasts if item.get("delai_fournisseur_jours") is not None),
        "avec_prix": sum(1 for item in forecasts if item.get("prix_unitaire") is not None),
        "interventions_liees": sum(int(item.get("historique", {}).get("evenements") or 0) for item in forecasts),
    }
    result["points_a_completer"] = validation_alerts
    # Le plan et le budget sont reconstruits depuis les prévisions serveur.
    # Un budget partiel est volontairement affiché comme non calculable.
    plan_by_date = {}
    for item in verified:
        forecast_date = item.get("date_achat")
        if not forecast_date:
            continue
        bucket = plan_by_date.setdefault(forecast_date, {"pieces": [], "budget_values": [], "priorite": item.get("urgence")})
        bucket["pieces"].append(item.get("reference"))
        if item.get("cout_estime") is not None:
            bucket["budget_values"].append(float(item["cout_estime"]))
    result["plan_achat"] = [
        {
            "semaine": f"Commande prévue le {forecast_date}",
            "pieces": bucket["pieces"],
            "budget": round(sum(bucket["budget_values"]), 2) if len(bucket["budget_values"]) == len(bucket["pieces"]) else None,
            "priorite": bucket["priorite"],
            "raison": "Date et quantité issues du moteur déterministe de stock",
        }
        for forecast_date, bucket in sorted(plan_by_date.items())
    ]
    priced_items = [item for item in verified if item.get("cout_estime") is not None]
    total_cost = sum(float(item.get("cout_estime")) for item in priced_items)
    complete_costs = bool(verified) and len(priced_items) == len(verified)
    missing_price_count = len(verified) - len(priced_items)
    result["impact_budget"] = {
        "cout_total_commande": round(total_cost, 2) if priced_items else None,
        "cout_total_commande_complet": round(total_cost, 2) if complete_costs else None,
        "calcul_complet": complete_costs,
        "articles_sans_prix": missing_price_count,
        "gain_potentiel": None,
        "ratio": "Non calculable : coût d'indisponibilité et économies contractuelles non configurés",
        "cout_indisponibilite_estime": None,
        "calcul_methode": "Quantités et dates reprises des prévisions serveur; aucun montant inventé",
        "source_prix": "Prix unitaires du catalogue pièces",
    }
    return result

def _diagnostic_list(value):
    """Normalise les listes retournées par le modèle sans perdre un texte unique."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if value and str(value).strip() else []


@app.post("/api/ai/analyze-diagnostic")
@governed_ai_endpoint("diagnostic", ("Admin", "Manager", "Responsable Technique", "Technicien"))
def analyze_diagnostic(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
    """Calls Gemini to diagnose a machine error code and log contexts."""
    try:
        from ai_engine import get_ai_suggestion, _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible. Vérifiez la configuration du fournisseur IA.")

    machine = body.get("machine", "Équipement inconnu")
    code_erreur = body.get("code_erreur", "")
    message_erreur = body.get("message_erreur", "")
    log_context = body.get("log_context", "")
    equipment_type = body.get("equipment_type", "")
    lang = _get_app_language(x_savia_lang, body)
    try:
        result = get_ai_suggestion(code_erreur, message_erreur, machine, log_context=log_context, equipment_type=equipment_type, response_language=lang)
        import json
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except:
                return {"ok": True, "result": _force_ai_payload_language(result, lang, _call_ia, clean_json_response)}
        
        if result and isinstance(result, dict):
            result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
            # Map uppercase keys from ai_engine to lowercase keys expected by frontend
            return {"ok": True, "result": {
                "probleme": result.get("Probleme", result.get("probleme", "Non identifié")),
                "cause": result.get("Cause", result.get("cause", "À déterminer")),
                "solution": result.get("Solution", result.get("solution", "Analyse manuelle requise")),
                "prevention": result.get("Prevention", result.get("prevention", "Maintenance préventive recommandée")),
                "urgence": result.get("Urgence", result.get("urgence", "À évaluer")),
                "type": result.get("Type", result.get("type", "?")),
                "priorite": result.get("Priorite", result.get("priorite", "MOYENNE")),
                "confidence": result.get("Confidence_Score", result.get("confidence", 0)),
                "chronologie": _diagnostic_list(result.get("Chronologie_Causale", result.get("chronologie"))),
                "controles": _diagnostic_list(result.get("Controles_Immediats", result.get("controles"))),
                "securite": result.get("Risques_Securite", result.get("securite", "")),
                "pieces_outils": _diagnostic_list(result.get("Pieces_Outils", result.get("pieces_outils"))),
                "validation": _diagnostic_list(result.get("Criteres_Validation", result.get("validation"))),
                "escalade": result.get("Escalade", result.get("escalade", "")),
            }}
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostic IA échoué: {e}")

def _build_predictive_fallback(kpis, sym, reason):
    """Construit un rapport détaillé auditable si l'IA ne renvoie pas son JSON."""
    risks = kpis.get("top_risques") or []
    alerts = []
    recommendations = []
    plans = []
    trends = []
    seen_trends = set()

    def number(value, default=0):
        parsed = _cost_number(value)
        return parsed if parsed is not None else default

    def text_list(value):
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return [str(value)] if value else []

    for item in risks[:8]:
        machine = str(item.get("machine") or "Equipement non renseigne")
        risk = number(item.get("risque_panne_pct"))
        horizon = int(number(item.get("horizon_jours"), 30))
        score = number(item.get("score_sante"))
        factors = text_list(item.get("facteurs"))
        diagnostics = item.get("diagnostics") or []
        diagnostic_causes = []
        for diagnostic in diagnostics[:3] if isinstance(diagnostics, list) else []:
            if isinstance(diagnostic, dict):
                for key in ("cause", "probleme", "description", "solution"):
                    value = str(diagnostic.get(key) or "").strip()
                    if value and value not in diagnostic_causes:
                        diagnostic_causes.append(value)
        cause = "; ".join(diagnostic_causes[:2]) if diagnostic_causes else (
            " et ".join(factors[:2]) if factors else "Historique technique insuffisant pour préciser la cause"
        )
        preventive_late = any("retard" in factor.lower() for factor in factors)
        action = (
            "Réaliser immédiatement la maintenance préventive en retard et effectuer une inspection ciblée"
            if preventive_late
            else "Planifier une inspection préventive ciblée et confirmer la cause par un diagnostic technicien"
        )
        recommendations_for_machine = [
            "Vérifier les diagnostics et les interventions récentes",
            "Contrôler le composant identifié avant tout remplacement",
        ]
        if preventive_late:
            recommendations_for_machine.insert(0, "Réaliser la maintenance préventive en retard")
        alert = {
            "machine": machine,
            "score_sante": score,
            "horizon_jours": horizon,
            "nb_interventions": None,
            "risque_panne_pct": risk,
            "risque": f"{'Élevé' if risk >= 50 else 'Modéré'} ({risk:g}%)",
            "action_immediate": action,
            "cause": cause,
            "facteurs": factors,
            "recommandations": recommendations_for_machine,
            "gain_potentiel": None,
            "cout_panne_evite": None,
        }
        if risk >= 50:
            alerts.append(alert)
        recommendations.append({
            "priorite": len(recommendations) + 1,
            "machine": machine,
            "cause": cause,
            "recommandation": action,
            "cout_estime": None,
            "cout_piece_reel": None,
            "cout_main_oeuvre": None,
            "cout_action_total": None,
            "cout_facturable_contrat": None,
            "prix_verifie": False,
            "contrat_type": "A confirmer",
            "gain_estime": None,
            "delai": f"Sous {7 if risk >= 50 else 30} jours",
            "impact": "Réduction du risque sous réserve de validation technique",
        })
        plans.append({
            "jour": ["Lundi", "Mardi", "Mercredi"][min(len(plans), 2)],
            "cibles": machine,
            "action": action,
        })
        for factor in factors:
            if factor not in seen_trends:
                seen_trends.add(factor)
                trends.append(factor)

    if not alerts and risks:
        alerts = [
            dict(
                recommendations[0],
                risque_panne_pct=number(risks[0].get("risque_panne_pct")),
                horizon_jours=number(risks[0].get("horizon_jours"), 30),
                score_sante=number(risks[0].get("score_sante")),
                risque="À surveiller",
                action_immediate="Planifier une vérification préventive",
                facteurs=text_list(risks[0].get("facteurs")),
            )
        ]
    trends = trends[:5] or ["Aucun facteur récurrent supplémentaire identifié"]
    total_cost = number(kpis.get("cout_total"))
    return {
        "_fallback": True,
        "_fallback_reason": reason,
        "alertes_critiques": alerts[:5],
        "machines_stables": [],
        "recommandations_prioritaires": recommendations[:5],
        "plan_maintenance": plans[:3],
        "estimation_couts": {
            "cout_curatif_historique": total_cost,
            "cout_preventif_propose": None,
            "cout_pannes_evitees": None,
            "detail_preventif": "Coût préventif non calculable sans action et prix validés dans le catalogue.",
            "gain_potentiel": None,
            "gain_net": None,
            "source_prix": "Catalogue serveur",
            "hypotheses": "Aucun montant n'est inventé lorsque le prix de la pièce ou la durée d'intervention manque.",
            "ratio": "Ratio non calculable avec les données disponibles.",
        },
        "tendances": trends,
        "conclusion": "Priorité aux équipements présentant le risque le plus élevé et aux maintenances préventives en retard. Validation par un technicien requise.",
    }


@app.post("/api/ai/analyze-performance")
@governed_ai_endpoint("performance", ("Admin", "Manager", "Responsable Technique"))
def analyze_performance(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """Calls Gemini to produce a detailed predictive maintenance report (v2)."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    kpis = body.get("kpis", {})
    sym = body.get("sym", "TND")
    lang = _get_app_language(x_savia_lang, body)
    if not AI_AVAILABLE:
        # Le moteur prédictif a déjà calculé les risques et les facteurs. Même
        # sans fournisseur IA disponible, renvoyer un rapport structuré évite
        # que le frontend retombe sur une synthèse de quatre lignes.
        fallback = _build_predictive_fallback(
            kpis,
            sym,
            "Le fournisseur IA n'est pas disponible dans le backend.",
        )
        return {"ok": True, "result": fallback}

    # --- Fetch real per-machine data from DB ---
    machine_details = ""
    equip_detail = ""
    parts_catalog = []
    historical_corrective_costs = {}
    historical_component_costs = {}
    machine_mttr_minutes = {}
    hourly_rate = None
    contracts_detail = []
    equipment_types = {}
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT machine, COUNT(*) as nb, "
                "SUM(CASE WHEN type_intervention='Corrective' THEN 1 ELSE 0 END) as corr, "
                "SUM(CASE WHEN type_intervention ILIKE '%%r\u00e9ventive%%' THEN 1 ELSE 0 END) as prev, "
                "ROUND(AVG(duree_minutes)::numeric,1) as mttr_m, "
                "ROUND(SUM(cout)::numeric,0) as cout, "
                "ROUND(SUM(cout_pieces)::numeric,0) as cout_pieces, "
                "ROUND(AVG(CASE WHEN type_intervention='Corrective' THEN (COALESCE(cout,0)+COALESCE(cout_pieces,0)) END)::numeric,2) as cout_correctif_moyen, "
                "ROUND(AVG(CASE WHEN type_intervention='Corrective' THEN duree_minutes END)::numeric,1) as mttr_correctif_m "
                "FROM interventions GROUP BY machine ORDER BY nb DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                machine = r['machine']
                machine_key = _machine_key(machine)
                corrective_cost = _cost_number(r.get('cout_correctif_moyen'))
                corrective_mttr = _cost_number(r.get('mttr_correctif_m'))
                if corrective_cost is not None:
                    historical_corrective_costs[machine_key] = corrective_cost
                if corrective_mttr is not None:
                    machine_mttr_minutes[machine_key] = corrective_mttr
                machine_details += f"  - {machine}: {r['nb']} int ({r['corr']} corr, {r['prev']} prev), MTTR={r['mttr_m']}min, MTTR correctif={r.get('mttr_correctif_m','?')}min, co\u00fbt MO={r['cout']} {sym}, co\u00fbt pi\u00e8ces={r.get('cout_pieces',0)} {sym}, co\u00fbt correctif moyen={r.get('cout_correctif_moyen','?')} {sym}\n"
            component_rows = conn.execute(
                "SELECT machine, pieces_utilisees, cout, cout_pieces FROM interventions "
                "WHERE type_intervention = 'Corrective'"
            ).fetchall()
            component_samples = {}
            for row in component_rows:
                row_total = (_cost_number(row.get('cout')) or 0) + (_cost_number(row.get('cout_pieces')) or 0)
                for component_name in re.split(r"[,;]", str(row.get('pieces_utilisees') or "")):
                    component_key = _cost_normalize(component_name)
                    if component_key:
                        component_samples.setdefault((_machine_key(row.get('machine')), component_key), []).append(row_total)
            historical_component_costs = {
                key: round(sum(values) / len(values), 2)
                for key, values in component_samples.items()
                if values
            }
            eqs = conn.execute("SELECT nom, client, type, statut, date_installation FROM equipements ORDER BY nom LIMIT 25").fetchall()
            for eq in eqs:
                equipment_types[_machine_key(eq.get('nom'))] = eq.get('type') or ''
                # La table PostgreSQL utilise des colonnes minuscules; les
                # clés historiques sont conservées uniquement pour le texte
                # de contexte déjà construit ci-dessous.
                eq['Nom'] = eq.get('nom') or '?'
                eq['Type'] = eq.get('type') or '?'
                eq['Client'] = eq.get('client') or '?'
                eq['DateInstallation'] = eq.get('date_installation') or '?'
                eq['Statut'] = eq.get('statut') or '?'
                equip_detail += f"  - {eq['Nom']} ({eq.get('Type','?')}) — {eq.get('Client','?')}, install\u00e9: {eq.get('DateInstallation','?')}, statut: {eq.get('Statut','?')}\n"
            part_rows = conn.execute(
                "SELECT reference, designation, equipement_type, prix_unitaire, fournisseur, stock_actuel "
                "FROM pieces_rechange ORDER BY designation LIMIT 500"
            ).fetchall()
            parts_catalog = [dict(part) for part in part_rows]
            rate_row = conn.execute("SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'").fetchone()
            if rate_row:
                hourly_rate = _cost_number(rate_row.get('valeur'))
            contract_rows = conn.execute(
                "SELECT client, equipement, type_contrat, avec_pieces, pieces_incluses, "
                "interventions_incluses, montant, statut, date_fin "
                "FROM contrats WHERE statut = 'Actif' ORDER BY date_fin DESC"
            ).fetchall()
            contracts_detail = [dict(contract) for contract in contract_rows]
    except Exception as db_err:
        logger.warning(f"DB fetch for AI failed: {db_err}")

    # Les donnees financieres ne doivent pas disparaitre parce qu'une requete
    # d'historique ou de contrat a echoue (schema ancien, colonne optionnelle...).
    # On les relit independamment afin que Gemini ne conclue pas a tort qu'elles
    # ne sont pas configurees.
    if hourly_rate is None or not parts_catalog or not contracts_detail:
        try:
            with get_db() as conn:
                # Load the essential financial sources first. Optional historical
                # component analysis below must not mask these values.
                if hourly_rate is None:
                    rate_row = conn.execute("SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'").fetchone()
                    if rate_row:
                        hourly_rate = _cost_number(rate_row.get('valeur'))
                if not parts_catalog:
                    part_rows = conn.execute(
                        "SELECT reference, designation, equipement_type, prix_unitaire, fournisseur, stock_actuel "
                        "FROM pieces_rechange ORDER BY designation LIMIT 500"
                    ).fetchall()
                    parts_catalog = [dict(part) for part in part_rows]
                if not contracts_detail:
                    contract_rows = conn.execute(
                        "SELECT client, equipement, type_contrat, avec_pieces, pieces_incluses, "
                        "interventions_incluses, montant, statut, date_fin "
                        "FROM contrats WHERE statut = 'Actif' ORDER BY date_fin DESC"
                    ).fetchall()
                    contracts_detail = [dict(contract) for contract in contract_rows]
                if not equipment_types:
                    eq_rows = conn.execute('SELECT nom, type FROM equipements ORDER BY nom LIMIT 500').fetchall()
                    equipment_types = {_machine_key(eq.get('nom')): eq.get('type') or '' for eq in eq_rows}
                if not historical_component_costs:
                    component_rows = conn.execute(
                        "SELECT machine, pieces_utilisees, cout, cout_pieces FROM interventions "
                        "WHERE type_intervention = 'Corrective'"
                    ).fetchall()
                    component_samples = {}
                    for row in component_rows:
                        row_total = (_cost_number(row.get('cout')) or 0) + (_cost_number(row.get('cout_pieces')) or 0)
                        for component_name in re.split(r"[,;]", str(row.get('pieces_utilisees') or "")):
                            component_key = _cost_normalize(component_name)
                            if component_key:
                                component_samples.setdefault((_machine_key(row.get('machine')), component_key), []).append(row_total)
                    historical_component_costs = {
                        key: round(sum(values) / len(values), 2)
                        for key, values in component_samples.items()
                        if values
                    }
                if hourly_rate is None:
                    rate_row = conn.execute("SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'").fetchone()
                    if rate_row:
                        hourly_rate = _cost_number(rate_row.get('valeur'))
                if not parts_catalog:
                    part_rows = conn.execute(
                        "SELECT reference, designation, equipement_type, prix_unitaire, fournisseur, stock_actuel "
                        "FROM pieces_rechange ORDER BY designation LIMIT 500"
                    ).fetchall()
                    parts_catalog = [dict(part) for part in part_rows]
                if not contracts_detail:
                    contract_rows = conn.execute(
                        "SELECT client, equipement, type_contrat, avec_pieces, pieces_incluses, "
                        "interventions_incluses, montant, statut, date_fin "
                        "FROM contrats WHERE statut = 'Actif' ORDER BY date_fin DESC"
                    ).fetchall()
                    contracts_detail = [dict(contract) for contract in contract_rows]
        except Exception as financial_db_err:
            logger.warning(f"Financial data fetch for AI failed: {financial_db_err}")

    parts_detail = ""
    for part in parts_catalog:
        parts_detail += (
            f"  - Ref={part.get('reference','?')} | {part.get('designation','?')} | "
            f"type={part.get('equipement_type','?')} | prix unitaire={part.get('prix_unitaire','?')} {sym} | "
            f"fournisseur={part.get('fournisseur','?')} | stock={part.get('stock_actuel','?')}\n"
        )
    contracts_detail_text = ""
    for contract in contracts_detail:
        contracts_detail_text += (
            f"  - client={contract.get('client','?')} | equipement={contract.get('equipement','tous')} | "
            f"type={contract.get('type_contrat','?')} | pieces_incluses={contract.get('avec_pieces',0)} | "
            f"references_incluses={contract.get('pieces_incluses','')} | "
            f"interventions_incluses={contract.get('interventions_incluses','?')} | "
            f"statut={contract.get('statut','?')} | fin={contract.get('date_fin','?')}\n"
        )

    risk_detail = ""
    for r in kpis.get("top_risques", []):
        risk_detail += f"  - {r.get('machine','?')}: risque={r.get('risque_panne_pct',0)}%, horizon={r.get('horizon_jours', r.get('jours_avant_panne','?'))}j, pi\u00e8ce={r.get('composant_a_risque','?')}, fiabilit\u00e9_donn\u00e9es={r.get('fiabilite_donnees_pct', r.get('confiance_ia_pct',0))}%, sant\u00e9={r.get('score_sante',0)}%, facteurs={r.get('facteurs','')}, diagnostics={r.get('diagnostics','')}\n"

    for r in kpis.get("top_risques", []):
        protected = r.get("composants_proteges") or []
        if protected:
            risk_detail += f"    PROTECTION OBLIGATOIRE : composant(s) remplacé(s) récemment, ne pas recommander un remplacement sans nouveau diagnostic : {protected}\n"

    import datetime
    today = datetime.date.today()

    configured_countries = _configured_country_names()
    prompt = f"""{_ai_language_instruction(lang)}
Tu es Directeur du Service Technique d'une entreprise de maintenance d'\u00e9quipements d'imagerie m\u00e9dicale opérant dans les pays suivants : {configured_countries}.
Analyse ces donn\u00e9es R\u00c9ELLES et produis un rapport pr\u00e9dictif d\u00e9taill\u00e9.

=== CHIFFRES DU PARC ===
- \u00c9quipements : {kpis.get('nb_equipements', 0)} | Interventions : {kpis.get('nb_interventions', 0)}
- Correctives : {kpis.get('interventions_correctives', 0)} | Pr\u00e9ventives : {kpis.get('interventions_preventives', 0)} | Calibrations : {kpis.get('interventions_calibration', 0)}
- Disponibilit\u00e9 : {kpis.get('disponibilite', 0)}% | MTBF : {kpis.get('mtbf', 0)}h | MTTR : {kpis.get('mttr', 0)}h
- Co\u00fbt total : {kpis.get('cout_total', 0)} {sym}

=== HISTORIQUE PAR MACHINE ===
{machine_details if machine_details else 'Non disponible'}

=== PR\u00c9DICTIONS IA ===
{risk_detail if risk_detail else 'Aucune'}

=== \u00c9QUIPEMENTS ===
{equip_detail if equip_detail else 'Non disponible'}

=== SOURCES FINANCIERES VERIFIEES ===
- Taux horaire technicien configure : {hourly_rate if hourly_rate is not None else 'NON CONFIGURE'} {sym}/h
- Catalogue des pieces (prix unitaires reels) :
{parts_detail if parts_detail else '  - Aucun prix de piece disponible'}
- Contrats actifs et couverture :
{contracts_detail_text if contracts_detail_text else '  - Aucun contrat actif disponible'}

PRODUIS un rapport JSON STRICT :
Le rapport doit expliquer les causes et facteurs disponibles dans les diagnostics techniciens (probleme, cause, solution, code erreur, piece et priorite), puis proposer des actions concretes avec cout estime, cout de panne evite et gain potentiel. Toute economie est une estimation a valider, jamais une garantie. Utilise les chiffres reels; indique explicitement les donnees manquantes.
RÈGLES DE COHÉRENCE OBLIGATOIRES :
- Les équipements des alertes critiques doivent être choisis uniquement dans PRÉDICTIONS IA.
- Recopie exactement le libellé fourni dans PRÉDICTIONS IA (Nom (Client)); n'invente aucun équipement.
- Tout champ qui nomme un équipement doit toujours conserver le client entre parenthèses.
- Ne fabrique jamais un prix, un taux horaire, une duree ou un gain. Si une donnee manque, retourne null et ecris "A confirmer" dans les hypotheses.
- Si PRÉDICTIONS IA indique qu'un composant a été remplacé récemment, ne recommande pas son remplacement sous 7 jours. Recommande d'abord une vérification, une recherche de cause racine et une surveillance; ne propose un nouveau remplacement que si un diagnostic postérieur confirme sa défaillance.
- La pièce doit être compatible avec le type exact de l'équipement. Ne choisis jamais le prix d'une pièce de scanner pour un mammographe, même si les désignations se ressemblent; utilise la référence liée à l'équipement ou retourne "prix à confirmer".
- Le cout technique total est calcule ainsi : (prix unitaire catalogue x quantite) + (MTTR correctif historique en heures x taux horaire configure). N'utilise pas un montant inferieur au prix de la piece.
- Distingue toujours cout_piece_reel, cout_main_oeuvre, cout_action_total, cout_facturable_contrat et gain_net.
- Pour une pièce, le gain net n'est calculable qu'avec le coût historique de cette même pièce sur cette même machine. N'utilise jamais la moyenne de toutes les pannes de la machine pour justifier le remplacement d'une pièce; sinon gain_net=null.
- Le contrat actif determine la partie facturable : "Full Service" couvre pieces et main-d'oeuvre; "Pieces incluses"/avec_pieces couvre les pieces; "Main d'oeuvre uniquement" couvre la main-d'oeuvre. Si la couverture n'est pas explicite, cout_facturable_contrat=null.
- Le gain net est calculable seulement si le cout correctif moyen historique de la machine et le cout action complet sont disponibles : cout correctif moyen historique - cout action total. Sinon gain_net=null.
{{
  "alertes_critiques": [
    {{
      "machine": "Nom (Client)",
      "score_sante": 41,
      "horizon_jours": 30,
      "nb_interventions": 19,
      "risque": "Risque concret",
      "action_immediate": "Action + pi\u00e8ces",
      "cause": "Cause issue des diagnostics techniciens",
      "facteurs": ["Facteur historique 1", "Facteur historique 2"],
      "recommandations": ["Recommandation ciblée"],
      "gain_potentiel": 0,
      "cout_panne_evite": 0
    }}
  ],
  "machines_stables": [
    {{
      "machine": "Nom (Client)",
      "score_sante": 84,
      "commentaire": "Pourquoi fiable"
    }}
  ],
  "recommandations_prioritaires": [
    {{
      "priorite": 1,
      "machine": "Nom (Client)",
      "cause": "Cause racine",
      "recommandation": "Action préventive détaillée",
      "cout_estime": 0,
      "cout_piece_reel": null,
      "cout_main_oeuvre": null,
      "cout_action_total": null,
      "cout_facturable_contrat": null,
      "prix_verifie": false,
      "contrat_type": "A confirmer",
      "gain_estime": null,
      "delai": "Sous 7 jours",
      "impact": "Réduction du risque et maintien de la disponibilité"
    }}
  ],
  "plan_maintenance": [
    {{
      "jour": "Lundi {today.strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }},
    {{
      "jour": "Mardi {(today + datetime.timedelta(days=1)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }},
    {{
      "jour": "Mercredi {(today + datetime.timedelta(days=2)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}
  ],
  "estimation_couts": {{
    "cout_curatif_historique": {int(kpis.get('cout_total', 0))},
    "cout_preventif_propose": null,
    "cout_pannes_evitees": null,
    "detail_preventif": "D\u00e9tail calcul",
    "gain_potentiel": null,
    "gain_net": null,
    "source_prix": "Catalogue et configuration serveur",
    "hypotheses": "Hypothèses et méthode d'estimation",
    "ratio": "Pour 1 {sym} investi, X {sym} \u00e9conomis\u00e9s"
  }},
  "tendances": ["Tendance 1", "Tendance 2", "Tendance 3"],
  "conclusion": "Priorit\u00e9 absolue \u00e0..."
}}"""

    raw = _call_ia(prompt, timeout=180, is_json=True)
    result = clean_json_response(raw) if raw else None
    if not isinstance(result, dict):
        fallback = _build_predictive_fallback(
            kpis,
            sym,
            "La réponse IA n'était pas disponible ou ne contenait pas un JSON exploitable.",
        )
        result = _apply_verified_costs(
            fallback,
            parts_catalog,
            historical_corrective_costs,
            {
                "hourly_rate": hourly_rate,
                "machine_mttr_minutes": machine_mttr_minutes,
                "equipment_types": equipment_types,
                "historical_component_costs": historical_component_costs,
                "protected_components_by_machine": {
                    _machine_key(r.get("machine")): r.get("composants_proteges", [])
                    for r in kpis.get("top_risques", [])
                },
                "contracts": contracts_detail,
            },
            sym,
        )
        return {"ok": True, "result": result}
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    if not isinstance(result, dict):
        result = _build_predictive_fallback(kpis, sym, "La traduction du rapport IA a échoué.")
    result = _apply_verified_costs(
        result,
        parts_catalog,
        historical_corrective_costs,
        {
            "hourly_rate": hourly_rate,
            "machine_mttr_minutes": machine_mttr_minutes,
            "equipment_types": equipment_types,
            "historical_component_costs": historical_component_costs,
            "protected_components_by_machine": {
                _machine_key(r.get("machine")): r.get("composants_proteges", [])
                for r in kpis.get("top_risques", [])
            },
            "contracts": contracts_detail,
        },
        sym,
    )
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-pieces")
@governed_ai_endpoint("pieces", ("Admin", "Manager", "Responsable Technique", "Gestionnaire", "Gestionnaire de stock"))
def analyze_pieces(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Gestionnaire", "Gestionnaire de stock")
    """
    Advanced AI analysis of spare parts with historical usage and predictions.
    Uses calculated consumption, data confidence, and intervention history.
    Generates buying recommendations and purchase planning.
    """
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        from db_engine import get_ai_pieces_context
        from services.spare_parts_prediction_engine import predict_spare_parts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI engine is not available.")

    # Get domain and equipment type from request (or use defaults)
    domaine = body.get("domain", "")
    equipment_type = body.get("equipment_type", "")
    sym = body.get("sym", "USD")  # Default to USD for universality
    lang = _get_app_language(x_savia_lang, body)

    # Get comprehensive context from database
    context = get_ai_pieces_context(domaine, equipment_type)
    pieces_data = context.get('pieces', [])
    stats = context.get('statistics', {})
    try:
        with get_db() as conn:
            forecasts = predict_spare_parts(conn)
    except Exception as forecast_error:
        logger.warning(f"Spare-parts forecast unavailable for AI: {forecast_error}")
        forecasts = []
    forecast_by_ref = {_cost_normalize(item.get('reference')): item for item in forecasts}
    
    if not pieces_data:
        raise HTTPException(status_code=400, detail="No spare parts data available for analysis.")

    import datetime
    today = datetime.date.today()
    def fmt(d): return d.strftime("%d/%m/%Y")

    # Build detailed inventory report with predictions
    inventory_lines = ""
    critical_pieces = []
    for p in pieces_data:
        ref = p['reference']
        nom = p['designation']
        stock = p['current_stock']
        mini = p['minimum_stock']
        prix = p['unit_price']
        four = p['supplier']
        consomm = p['monthly_consumption']
        confiance = p['data_confidence']
        urgency = p['urgency']
        jours_rupture = p['days_until_rupture']
        recent_use = p['recent_usage_30d']
        forecast = forecast_by_ref.get(_cost_normalize(ref), {})
        consomm = forecast.get('consommation_mensuelle', consomm)
        confiance = forecast.get('fiabilite_donnees_pct', confiance)
        urgency = forecast.get('urgence', urgency)
        jours_rupture = forecast.get('jours_avant_rupture')
        recent_use = forecast.get('consommation_30j', recent_use)
        prediction_available = bool(forecast.get('prediction_available'))
        date_commande = forecast.get('date_commande') or 'NON CALCULABLE'
        quantite_recommandee = forecast.get('quantite_recommandee')
        cout_estime = forecast.get('cout_estime')
        risque_30j = forecast.get('risque_rupture_30j_pct')
        clients = ', '.join(forecast.get('clients_utilisateurs') or []) or 'Non documenté'
        diagnostic = (forecast.get('diagnostics') or [{}])[0]
        contract_demand = forecast.get('demande_contrats_futurs') or {}
        
        # Format stock status with prediction (in French)
        if stock == 0:
            status = "EN RUPTURE - CRITIQUE"
        elif stock <= mini:
            status = f"STOCK BAS (besoin {mini - stock + 1})"
        elif jours_rupture is not None and jours_rupture <= 7:
            status = f"CORRECT mais RUPTURE en {jours_rupture:.0f} jours"
        else:
            status = f"ADAPTÉ (marge {stock - mini})"
        
        # Consumption info (in French)
        consump_info = f"Consommation: {consomm:.2f}/mois | Usage récent (30j): {recent_use}x | Confiance: {confiance}"
        
        line = f"  • {nom} ({ref}) | Équip: {p['equipment_type']} | Stock: {stock}/{mini} [{status}] | {consump_info} | Fournisseur: {four} | Prix: {prix:.2f} {sym}\n"
        inventory_lines += line
        inventory_lines += (
            f"    DONNEES_DETERMINISTES: disponible={prediction_available}; commande={date_commande}; "
            f"quantite={quantite_recommandee if quantite_recommandee is not None else 'NON CALCULABLE'}; "
            f"cout_catalogue={cout_estime if cout_estime is not None else 'NON CALCULABLE'} {sym}; "
            f"risque_rupture_30j={risque_30j if risque_30j is not None else 'NON CALCULABLE'}%; "
            f"delai_fournisseur={forecast.get('delai_fournisseur_jours') if forecast.get('delai_fournisseur_jours') is not None else 'NON RENSEIGNE'} jours; "
            f"demandes_techniciens_en_attente={forecast.get('demandes_pieces_en_attente', 0)}; "
            f"stock_disponible_apres_demandes={forecast.get('stock_disponible_apres_demandes', stock)}; "
            f"maintenances_contrat_a_venir={contract_demand.get('interventions_planifiees', 0)}; "
            f"prochaine_maintenance={contract_demand.get('prochaine_intervention') or 'NON PLANIFIEE'}; "
            f"demande_quota_contrat={contract_demand.get('quantite_quota_contrat', 0)}; "
            f"demande_estimee_preventif={contract_demand.get('quantite_estimee_historique', 0)}; "
            f"clients={clients}; diagnostic_cause={diagnostic.get('cause') or 'NON RENSEIGNE'}; "
            f"diagnostic_type={diagnostic.get('type') or 'NON RENSEIGNE'}; "
            f"diagnostic_probleme={diagnostic.get('probleme') or 'NON RENSEIGNE'}; "
            f"diagnostic_solution={diagnostic.get('solution') or 'NON RENSEIGNE'}\n"
        )
        
        # Track critical items
        if str(urgency).upper() in ('CRITIQUE', 'CRITICAL'):
            critical_pieces.append((ref, nom, urgency))
    
    # Timeline weeks
    s1 = f"{fmt(today)} - {fmt(today+datetime.timedelta(days=6))}"
    s2 = f"{fmt(today+datetime.timedelta(days=7))} - {fmt(today+datetime.timedelta(days=13))}"
    s3 = f"{fmt(today+datetime.timedelta(days=14))} - {fmt(today+datetime.timedelta(days=20))}"
    d0 = fmt(today)
    d3 = fmt(today+datetime.timedelta(days=3))
    d7 = fmt(today+datetime.timedelta(days=7))
    d14 = fmt(today+datetime.timedelta(days=14))
    
    # Contextualize for domain if provided (in French)
    domain_context = ""
    if domaine:
        domain_context = f"\nDomaine: {domaine}"
        if equipment_type:
            domain_context += f" | Équipement principal: {equipment_type}"
    
    prompt = f"""{_ai_language_instruction(lang)}
Tu es un expert en gestion de stock et approvisionnement pour équipements médicaux critiques.
Analyse cet inventaire de pièces de rechange avec prédictions et génère un plan d'achat stratégique.

=== CONTEXTE INSTALLATION ===
Aujourd'hui: {fmt(today)}{domain_context}
Total pièces: {stats['total_pieces']} références
Valeur stock: {stats['total_stock_value']:,.0f} {sym}
Articles urgence CRITIQUE: {stats['critical_urgency_count']}
Articles urgence HAUTE: {stats['high_urgency_count']}

=== INVENTAIRE PIÈCES AVEC PRÉDICTIONS ===
{inventory_lines}

=== DIRECTIVES D'ANALYSE ===
1. Exploiter toutes les valeurs déterministes disponibles pour chaque référence : stock, demandes de techniciens en attente, seuil, prix, consommation 30/90/365 jours, historique d'interventions, diagnostics, clients, contrats, maintenances contractuelles à venir, quotas restants, fournisseur, délai, point de commande et stock de sécurité.
2. L'analyse_risque doit être détaillée (6-8 phrases) et citer les références concernées, leur stock, leur coût connu et le motif calculé. Ne conclus jamais qu'une donnée est absente si elle apparaît dans INVENTAIRE.
3. Data_confidence / fiabilite_donnees_pct indique la fiabilité : distingue données calculées, données de stock certaines et hypothèses à confirmer.
4. days_until_rupture = jours avant rupture de stock; les usages 30/90/365 jours permettent de commenter la tendance réelle sans inventer une consommation.
5. Les quantités, dates, coûts et priorités de recommandations seront corrigés par le serveur à partir des prévisions déterministes; explique donc leurs causes et impacts sans les modifier.
6. Pour chaque rupture ou stock sous seuil, indique l'équipement/client concerné, la couverture contractuelle si présente, les maintenances planifiées et leurs quotas quand ils existent, le dernier diagnostic lié et les données qui restent à compléter.

RÈGLES FINANCIÈRES ET DE COHÉRENCE :
- Utilise uniquement les quantités, dates, urgences et coûts présents dans INVENTAIRE PIÈCES AVEC PRÉDICTIONS.
- N'invente jamais une quantité, une date de commande, un prix ou un gain. Si prediction_available=false et que le stock est supérieur à zéro, ne recommande pas l'achat. Une rupture effective peut toutefois générer une commande immédiate basée uniquement sur le stock minimum configuré; la prévision de consommation doit alors rester explicitement indisponible.
- Le gain potentiel et le coût d'indisponibilité doivent être null tant qu'un coût documenté d'indisponibilité ou une économie contractuelle n'est pas fourni.
- Ne mélange jamais deux références, même si leurs désignations sont proches.

=== FORMAT RÉPONSE ===
RÉPONDS UNIQUEMENT en JSON valide (pas de markdown, texte avant/après):
{{
  "analyse_risque": "Résumé exécutif détaillé (6-8 phrases) fondé sur les références, stocks, coûts, historiques, équipements, clients, fournisseurs et délais réellement fournis",
  "recommandations": [
    {{"piece": "Nom pièce", "reference": "REF", "raison": "Impact opérationnel si non commandé (ex: arrêt équipement = X patients)", "action": "Commander immédiatement", "quantite": 2, "date_achat": "{d0}", "urgence": "critique", "cout_estime": 500, "delai_fournisseur": 14}},
    {{"piece": "Nom pièce 2", "reference": "REF2", "raison": "Raison opérationnelle basée pattern consommation", "action": "Commander rapidement", "quantite": 1, "date_achat": "{d7}", "urgence": "haute", "cout_estime": 300, "delai_fournisseur": 14}}
  ],
  "plan_achat": [
    {{"semaine": "Semaine 1 ({s1})", "pieces": ["reference_1"], "budget": 1200, "priorite": "Critique", "raison": "Besoins immédiats"}},
    {{"semaine": "Semaine 2 ({s2})", "pieces": ["reference_2"], "budget": 800, "priorite": "Haute", "raison": "Prévenir rupture"}},
    {{"semaine": "Semaine 3 ({s3})", "pieces": ["reference_3"], "budget": 500, "priorite": "Normale", "raison": "Maintenir stock minimum"}}
  ],
  "impact_budget": {{
    "cout_total_commande": 2500,
    "gain_potentiel": 8000,
    "ratio": "Pour chaque 1 {sym} investi, X {sym} d'économie sur indisponibilité",
    "cout_indisponibilite_estime": 3000,
    "calcul_methode": "Basé sur nombre équipements critiques et consommation mensuelle"
  }},
  "tendances": ["Tendance 1 avec données concrètes", "Tendance 2", "Tendance 3"]
}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="AI did not respond.")
    result = clean_json_response(raw)
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    result = _apply_spare_parts_ai_guardrails(result, forecasts, sym)
    
    # Log the analysis
    username = user.get("sub", "unknown")
    log_audit(username, "AI_ANALYZE_PIECES", f"Analyzed {len(pieces_data)} spare parts", "pieces")
    
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-sav")
@governed_ai_endpoint("sav", ("Admin", "Manager", "Responsable Technique"))
def analyze_sav(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """Comprehensive SAV/Interventions analysis using Gemini."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    sav_data = body.get("sav_data", {})
    sym = body.get("sym", "TND")
    lang = _get_app_language(x_savia_lang, body)
    nb_total = sav_data.get("nb_total", sav_data.get("nb_interventions", 0))
    nb_cloturees = sav_data.get("nb_cloturees", sav_data.get("nb_cloturees", 0))
    cout_main_oeuvre = sav_data.get("cout_main_oeuvre", 0)
    cout_pieces = sav_data.get("cout_pieces", 0)
    cout_total = sav_data.get("cout_total", sav_data.get("cout_total_tnd", 0))
    interventions_detail = sav_data.get("interventions_detail", [])
    machines_detail = sav_data.get("machines_detail", [])
    errors_detail = sav_data.get("erreurs_recurrentes", [])
    causes_detail = sav_data.get("causes_recurrentes", [])
    tech_detail = sav_data.get("tech_details", sav_data.get("performance_equipe", []))
    equipment_detail = sav_data.get("equipements_detail", [])
    contracts_detail = sav_data.get("contrats_detail", [])
    stock_detail = sav_data.get("stock_detail", [])
    try:
        interventions_json = json.dumps(interventions_detail[:50], ensure_ascii=False, default=str)
        machines_json = json.dumps(machines_detail[:30], ensure_ascii=False, default=str)
        errors_json = json.dumps(errors_detail[:10], ensure_ascii=False, default=str)
        causes_json = json.dumps(causes_detail[:10], ensure_ascii=False, default=str)
        tech_json = json.dumps(tech_detail[:20] if isinstance(tech_detail, list) else tech_detail, ensure_ascii=False, default=str)
        equipment_json = json.dumps(equipment_detail[:50], ensure_ascii=False, default=str)
        contracts_json = json.dumps(contracts_detail[:30], ensure_ascii=False, default=str)
        stock_json = json.dumps(stock_detail[:50], ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        interventions_json = machines_json = errors_json = causes_json = "[]"
        tech_json = equipment_json = contracts_json = stock_json = "[]"

    configured_countries = _configured_country_names()
    prompt = f"""{_ai_language_instruction(lang)}
Tu es un expert en gestion de maintenance SAV pour équipements d'imagerie médicale opérant dans les pays suivants : {configured_countries}.
Analyse ces données SAV RÉELLES et produis un rapport COMPLET et DÉTAILLÉ.

=== STATISTIQUES GLOBALES ===
- Total interventions : {nb_total}
- Clôturées : {nb_cloturees}
- En cours : {sav_data.get('nb_en_cours', 0)}
- Taux résolution : {sav_data.get('taux_resolution', 0)}%
- MTTR moyen : {sav_data.get('mttr_h', 0)}h
- Durée totale : {sav_data.get('duree_totale_h', 0)}h

=== RÉPARTITION PAR TYPE ===
- Correctives : {sav_data.get('nb_correctives', 0)}
- Préventives : {sav_data.get('nb_preventives', 0)}  
- Installations : {sav_data.get('nb_installations', 0)}
- Ratio correctif : {sav_data.get('ratio_correctif_pct', 0)}%

=== COÛTS (sans double comptage) ===
- Coût de service additionnel, hors main-d'œuvre et pièces : {sav_data.get('cout_interventions', 0)} {sym}
- Coût main-d'œuvre : {cout_main_oeuvre} {sym}
- Coût pièces : {cout_pieces} {sym}
- Coût total calculé (main-d'œuvre + pièces) : {cout_total} {sym}
- Coût moyen/intervention : {sav_data.get('cout_moyen', 0)} {sym}
Règle de lecture : un coût de service additionnel à 0 est normal lorsqu'aucune ligne distincte de service n'est suivie. Ne signale pas d'incohérence si le coût total correspond au coût main-d'œuvre + coût pièces.

=== PERFORMANCE ÉQUIPE (par technicien) ===
{tech_json}

=== DÉTAIL DES INTERVENTIONS DE LA PÉRIODE ===
{interventions_json}

=== MACHINES, SANTÉ ET COÛTS DE LA PÉRIODE ===
{machines_json}

=== CODES ERREURS ET CAUSES RÉCURRENTES ===
Codes : {errors_json}
Causes : {causes_json}

=== PARC, CONTRATS ET STOCK DISPONIBLE ===
Équipements : {equipment_json}
Contrats : {contracts_json}
Stock : {stock_json}

IMPORTANT: Analyse en profondeur et produis un JSON STRICT avec cette structure exacte :
{{{{
  "analyse": "Résumé exécutif complet (6-8 phrases) citant uniquement les chiffres, machines, coûts et tendances réellement fournis",
  "score_global": 75,
  "points_forts": [
    "Point fort 1 détaillé avec chiffres",
    "Point fort 2 détaillé avec chiffres",
    "Point fort 3 détaillé avec chiffres"
  ],
  "points_faibles": [
    "Point faible 1 détaillé avec chiffres",
    "Point faible 2 détaillé avec chiffres", 
    "Point faible 3 détaillé avec chiffres"
  ],
  "recommandations": [
    {{{{
      "titre": "Titre recommandation",
      "description": "Description détaillée de l'action à entreprendre",
      "impact": "HAUT"
    }}}},
    {{{{
      "titre": "Titre recommandation 2",
      "description": "Description détaillée",
      "impact": "MOYEN"
    }}}},
    {{{{
      "titre": "Titre recommandation 3",
      "description": "Description détaillée",
      "impact": "BAS"
    }}}}
  ],
  "performance_equipe": [
    {{{{
      "technicien": "Nom",
      "evaluation": "Excellent/Bon/À améliorer",
      "commentaire": "Commentaire détaillé sur ses performances"
    }}}}
  ],
  "analyse_couts": {{{{
    "verdict": "Maîtrisés/Élevés/Critiques",
    "detail": "Analyse détaillée des coûts",
    "economie_possible": "Estimation d'économie possible et comment"
  }}}},
  "tendances": [
    "Tendance 1 observée",
    "Tendance 2 observée",
    "Tendance 3 observée"
  ],
  "priorites_immediates": [
    "Action prioritaire 1",
    "Action prioritaire 2"
  ],
  "analyse_parc": [
    {{"machine": "Machine réellement fournie", "constat": "Interventions, santé, coûts ou diagnostic observé", "action": "Action fondée sur les données", "priorite": "HAUTE"}}
  ],
  "risques_stock": [
    {{"reference": "Référence réelle", "constat": "Stock/seuil/prix observé", "action": "Action d'achat ou de vérification", "urgence": "HAUTE"}}
  ],
  "donnees_a_completer": ["Donnée absente qui empêcherait une conclusion précise"]
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
    result = clean_json_response(raw)
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    if isinstance(result, dict):
        result["donnees_exploitees"] = {
            "interventions": nb_total,
            "equipements": sav_data.get("nb_equipements", len(equipment_detail)),
            "interventions_detaillees": len(interventions_detail),
            "machines_analysees": len(machines_detail),
            "techniciens_analyses": len(tech_detail) if isinstance(tech_detail, list) else 0,
            "codes_erreurs": len(errors_detail),
            "causes_recurrentes": len(causes_detail),
            "contrats": len(contracts_detail),
            "references_stock": len(stock_detail),
        }
    return {"ok": True, "result": result}


# ==========================================
# AI — Analyse des coûts (cartes structurées)
# ==========================================

@app.post("/api/ai/analyze-costs")
@governed_ai_endpoint("costs", ("Admin", "Manager"))
def ai_analyze_costs(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager")
    """Analyse IA structurée des coûts clients — retourne des cartes comme le diagnostic IA."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    clients_data = body.get("clients", [])
    kpis = body.get("kpis", {})
    lang = _get_app_language(x_savia_lang, body)
    sym = str(body.get("sym") or "TND").strip() or "TND"
    if not clients_data:
        raise HTTPException(status_code=400, detail="Aucune donnée client.")

    # ── Fetch TCO data server-side ──
    tco_data = []
    try:
        tco_data = finances_tco(client=None, user=user)
    except Exception:
        pass

    # Rebuild the context from authoritative server-side tables. The browser
    # only provides the current view; it must not be the source of truth for
    # a financial analysis.
    financial_context = _build_financial_ai_context(clients_data, tco_data)
    clients_data = financial_context["clients"]
    tco_data = financial_context["tco_equipements"]

    # Build compact summary from the enriched real data.
    avg_cout = sum(c.get('cout_total', 0) for c in clients_data) / max(len(clients_data), 1)
    client_lines = []
    for c in clients_data:
        ecart = round(((c.get('cout_total', 0) - avg_cout) / avg_cout * 100)) if avg_cout > 0 else 0
        nb_interv = c.get('nb_interventions', 0)
        nb_equip = c.get('nb_equipements', 0)
        ratio_interv = round(nb_interv / nb_equip, 1) if nb_equip > 0 else 0
        client_lines.append(
            f"{c.get('client','?')}: "
            f"revenu={c.get('revenu_contrats',0)} {sym}, "
            f"coûts_total={c.get('cout_total',0)} {sym}, "
            f"coût_interventions={c.get('cout_interventions',0)} {sym}, "
            f"coût_pièces={c.get('cout_pieces',0)} {sym}, "
            f"coût_main_oeuvre={c.get('cout_main_oeuvre',0)} {sym}, "
            f"marge={c.get('marge_pct',0)}%, "
            f"interventions={nb_interv} (correctives={c.get('nb_correctives',0)}, préventives={c.get('nb_preventives',0)}), "
            f"causes_confirmees={c.get('interventions_avec_cause_confirmee',0)}, "
            f"solutions_confirmees={c.get('interventions_avec_solution_confirmee',0)}, "
            f"equipements={nb_equip}, "
            f"ratio_interv/equip={ratio_interv}, "
            f"ratio_préventif={round(c.get('nb_preventives',0)/nb_interv*100) if nb_interv>0 else 0}%, "
            f"écart_vs_moy={'+' if ecart>0 else ''}{ecart}%"
        )
    summary = "\n".join(client_lines)

    # ── TCO summary (top 15 by cost) ──
    tco_summary = ""
    if tco_data:
        top_tco = sorted(tco_data, key=lambda x: x.get('tco_total', 0), reverse=True)[:15]
        tco_total_global = sum(t.get('tco_total', 0) for t in tco_data)
        tco_lines = []
        for t in top_tco:
            age_ans = round(t.get('age_jours', 0) / 365, 1)
            tco_lines.append(
                f"  {t.get('equipement','?')} ({t.get('client','')}): "
                f"TCO={t.get('tco_total',0)} {sym}, "
                f"pièces={t.get('cout_pieces',0)} {sym}, MO={t.get('cout_main_oeuvre',0)} {sym}, interv={t.get('cout_interventions',0)} {sym}, "
                f"nb_interv={t.get('nb_interventions',0)} (corr={t.get('nb_correctives',0)}/prev={t.get('nb_preventives',0)}), "
                f"âge={age_ans}ans, TCO/mois={t.get('tco_mensuel',0)} {sym}"
            )
        tco_summary = f"""
═══ TCO — TOTAL COST OF OWNERSHIP (Top 15 équipements) ═══
TCO global parc: {round(tco_total_global)} {sym} | Nb équipements: {len(tco_data)} | TCO moyen/équipement: {round(tco_total_global/max(len(tco_data),1))} {sym}
{chr(10).join(tco_lines)}"""

    output_guidance = ""
    if _normalize_lang(lang) == "en":
        output_guidance = f"""
ENGLISH OUTPUT REQUIREMENTS:
- Write every value in natural professional English only.
- Do not use French words or mixed expressions such as Couteux, Coûteux, Identifiees, Identifiées, Proposees, Proposées, Cout, Coût, de Possession, preventif, préventif, pieces, pièces, main d'oeuvre, main d'œuvre, rentables, recommandations, Analyse From, Risk de, Action immédiate, Curatif historique, Préventif proposé, or Cibles.
- Use these English section concepts in the generated text: High-cost clients, Identified causes, Proposed optimizations, TCO analysis - Total Cost of Ownership, High-performing clients, Strategic recommendations.
- Use {sym} as the currency everywhere. Do not write TND unless {sym} is TND.
"""

    prompt = f"""{_ai_language_instruction(lang)}
Tu es un expert en gestion financière de maintenance biomédicale (GMAO). Analyse ces données financières SAVIA en profondeur.

═══ INDICATEURS GLOBAUX ═══
• Coût moyen par client: {round(avg_cout)} {sym}
• Marge globale: {kpis.get('marge_pct',0)}%
• Marge brute: {kpis.get('marge_globale',0)} {sym}
• Revenu total contrats: {kpis.get('revenu_total',0)} {sym}
• Coût total: {kpis.get('cout_total',0)} {sym}
• Clients rentables: {kpis.get('nb_rentables',0)} / {kpis.get('nb_clients',0)}
• Clients déficitaires: {kpis.get('nb_deficitaires',0)}

═══ DONNÉES DÉTAILLÉES PAR CLIENT ═══
{summary}
{tco_summary}
â•â•â• CONTEXTE COMPLET ISSU DES DONNÃ‰ES RÃ‰ELLES DU SERVEUR â•â•â•
Le JSON ci-dessous contient toutes les lignes exploitables disponibles pour le pÃ©rimÃ¨tre analysÃ© : contrats, parc, interventions dÃ©taillÃ©es, maintenances planifiÃ©es, stock de piÃ¨ces et TCO. Utilise ces lignes comme source de vÃ©ritÃ©. Ne crÃ©e aucun montant, diagnostic, contrat ou Ã©quipement absent des donnÃ©es.
{json.dumps(financial_context, ensure_ascii=False, separators=(',', ':'), default=str)}
{output_guidance}

═══ CONSIGNES D'ANALYSE ═══
Retourne UNIQUEMENT un JSON valide avec cette structure exacte:
{{
  "clients_couteux": "Pour chaque client dont le coût dépasse la moyenne: nomme-le, donne son écart en % et en {sym} vs la moyenne, son ratio interventions/équipement, la répartition de ses coûts (pièces vs MO vs interventions). Indique le coût par équipement. Utilise • pour chaque client. Sois PRÉCIS avec tous les chiffres.",

  "causes": "Analyse technique des causes racines: taux de maintenance corrective vs préventive par client (un ratio préventif <30% est problématique), coût moyen par intervention, concentration des coûts pièces ou main d'œuvre, équipements vieillissants potentiels, fréquence d'interventions anormale (>4 interv/équipement/an = critique). Utilise • pour chaque cause identifiée avec les chiffres.",

  "optimisations": "Propositions concrètes avec estimation d'impact financier: ex. 'Augmenter le préventif de X à Y% pour [client] → économie estimée de Z {sym}/an', 'Négocier un contrat pièces forfaitaire pour [client]', 'Former les techniciens sur [type d'équipement] pour réduire le taux de rappel'. Chiffre chaque recommandation. Utilise • pour chaque proposition.",

  "clients_performants": "Pour chaque client rentable: nomme-le, donne sa marge en % et {sym}, son ratio préventif/correctif, son coût par équipement. Explique POURQUOI il performe (bon ratio préventif, peu de pannes, contrat bien dimensionné...). Identifie les bonnes pratiques réplicables. Utilise • pour chaque client.",

  "tco_analyse": "Analyse TCO du parc équipement: identifie les 3-5 équipements avec le TCO le plus élevé, calcule le TCO/mois et compare-le à la moyenne du parc. Pour chaque équipement critique: donne le TCO total, la ventilation pièces/MO/interventions, l'âge, le ratio correctif/préventif. Indique si le TCO justifie un remplacement (seuil: TCO > 60% du prix neuf estimé ou TCO/mois en hausse). Propose un plan de renouvellement priorisé. Utilise • pour chaque équipement.",

  "recommandations": "Actions stratégiques prioritaires classées par impact: renégociation tarifaire avec montants suggérés, plan de transition corrective→préventive avec calendrier, optimisation stock pièces de rechange (quelles pièces, quel fournisseur), seuils d'alerte à mettre en place (coût/équipement max, ratio correctif max), KPIs de suivi mensuel à implémenter. Utilise • pour chaque recommandation.",

  "tags": ["3-5 tags pertinents parmi: Surcoût Pièces, Ratio Correctif Élevé, Marge Négative, Contrat Sous-dimensionné, Maintenance Préventive Insuffisante, Optimisation Stock, Renégociation Contrat, Performance Élevée, Équipements Critiques, TCO Élevé, Renouvellement Requis"],
  "confiance": 85
}}

IMPORTANT: Sois un consultant expert. Chaque section doit faire 4-8 lignes avec des données chiffrées précises. Retourne UNIQUEMENT le JSON, rien d'autre."""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
    result = clean_json_response(raw)
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-costs/pdf")
@governed_ai_endpoint("costs_pdf", ("Admin", "Manager"))
def ai_analyze_costs_pdf(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager")
    """Genere un PDF a partir du resultat d'analyse IA des couts."""
    from io import BytesIO
    from starlette.responses import StreamingResponse
    import base64 as _b64
    import urllib.request as _ur

    data = body.get("result", {})
    kpis = body.get("kpis", {})
    lang = _get_app_language(x_savia_lang, body)
    sym = str(body.get("sym") or "TND").strip() or "TND"
    is_en = _normalize_lang(lang) == "en"
    try:
        from ai_engine import _call_ia, clean_json_response
        data = _force_ai_payload_language(data, lang, _call_ia, clean_json_response)
    except Exception:
        data = _fallback_translate_payload_for_lang(data, lang)
    company_name = body.get("company_name", "")
    company_logo = body.get("company_logo", "")
    if not data:
        raise HTTPException(status_code=400, detail="Aucune donnee d'analyse.")

    SAVIA_LOGO = "/app/logo-savia.png"

    # Client logo
    _client_logo_io = None
    if company_logo:
        try:
            clogo = company_logo.strip()
            if clogo.startswith("data:"):
                _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                _client_logo_io = BytesIO(_b64.b64decode(_b64_part))
            elif clogo.startswith("http"):
                req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                with _ur.urlopen(req_, timeout=6) as _r:
                    _client_logo_io = BytesIO(_r.read())
        except Exception:
            pass

    pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
    pdf.set_header_data(
        SAVIA_LOGO, _client_logo_io,
        company_name if company_name and company_name != "SAVIA" else "",
        "",
        report_title="AI FINANCIAL ANALYSIS" if is_en else "ANALYSE FINANCIERE IA"
    )
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_top_margin(pdf.HEADER_H + 10)
    pdf.add_page()

    # KPIs summary bar
    ky = pdf.get_y() + 2
    pdf.set_fill_color(238, 243, 246)
    pdf.rect(8, ky, pdf.w - 16, 12, 'F')
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(47, 65, 86)
    if is_en:
        kpi_items = [
            f"Revenue: {_fmt_number(kpis.get('revenu_total', 0))} {sym}",
            f"Costs: {_fmt_number(kpis.get('cout_total', 0))} {sym}",
            f"Margin: {kpis.get('marge_pct', 0)}%",
            f"Profitable: {kpis.get('nb_rentables', 0)}/{kpis.get('nb_clients', 0)}",
        ]
    else:
        kpi_items = [
            f"Revenu: {_fmt_number(kpis.get('revenu_total', 0))} {sym}",
            f"Couts: {_fmt_number(kpis.get('cout_total', 0))} {sym}",
            f"Marge: {kpis.get('marge_pct', 0)}%",
            f"Rentables: {kpis.get('nb_rentables', 0)}/{kpis.get('nb_clients', 0)}",
        ]
    pdf.set_xy(10, ky + 2)
    pdf.cell(pdf.w - 20, 8, _sanitize("   |   ".join(kpi_items)), align="C")
    pdf.ln(16)

    # Section card renderer with bullet support
    def render_card(title, content, color_rgb):
        # White titles need a darker accent than the bright UI palette.
        # This keeps every financial-analysis PDF heading legible.
        accessible_colors = {
            (220, 53, 53): (180, 38, 42),
            (234, 88, 12): (154, 52, 0),
            (22, 163, 74): (22, 116, 71),
            (13, 148, 136): (15, 94, 99),
            (37, 99, 235): (29, 78, 216),
            (124, 58, 237): (91, 33, 182),
        }
        r, g, b = accessible_colors.get(tuple(color_rgb), (47, 65, 86))
        W = pdf.w - 20  # usable width

        if pdf.get_y() > 250:
            pdf.add_page()

        # Colored section header
        pdf.set_fill_color(r, g, b)
        pdf.rect(10, pdf.get_y(), W, 7, 'F')
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_x(12)
        pdf.cell(W - 4, 7, _sanitize(title.upper()), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(1)

        # Content: split by bullet markers
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(50, 50, 50)
        raw = content or "-"
        bullets = [b.strip() for b in raw.replace('\n', ' ').split(chr(0x2022)) if b.strip()]
        if not bullets:
            bullets = [b.strip() for b in raw.split('\n') if b.strip()]

        for bullet in bullets:
            if not bullet:
                continue
            if pdf.get_y() > 270:
                pdf.add_page()
            cy = pdf.get_y()
            # Small black bullet dot
            pdf.set_fill_color(50, 50, 50)
            pdf.ellipse(12, cy + 1.2, 2, 2, 'F')
            pdf.set_x(16)
            pdf.multi_cell(pdf.w - 28, 4.2, _sanitize(bullet))
            pdf.ln(0.8)

        pdf.ln(3)

    # Render all cards
    cards = [
        (("High-cost Clients" if is_en else "Clients Couteux"), data.get("clients_couteux", ""), (220, 53, 53)),
        (("Identified Causes" if is_en else "Causes Identifiees"), data.get("causes", ""), (234, 88, 12)),
        (("Proposed Optimizations" if is_en else "Optimisations Proposees"), data.get("optimisations", ""), (22, 163, 74)),
        (("TCO Analysis - Total Cost of Ownership" if is_en else "Analyse TCO - Cout Total de Possession"), data.get("tco_analyse", ""), (13, 148, 136)),
        (("High-performing Clients" if is_en else "Clients Performants"), data.get("clients_performants", ""), (37, 99, 235)),
        (("Strategic Recommendations" if is_en else "Recommandations Strategiques"), data.get("recommandations", ""), (124, 58, 237)),
    ]
    for title, content, color in cards:
        render_card(title, content, color)

    # Footer info
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(150, 150, 150)
    generated_at = datetime.now().strftime('%d/%m/%Y a %H:%M')
    footer = (
        f"Generated on {generated_at} | SAVIA Maintenance - Confidential"
        if is_en
        else f"Genere le {generated_at} | SAVIA Maintenance - Confidentiel"
    )
    pdf.cell(0, 4, _sanitize(footer), align="C")

    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=SAVIA_Analyse_Couts_IA.pdf"}
    )


# ==========================================
# AI CHATBOT — Assistant conversationnel
# ==========================================

@app.post("/api/ai/chat")
@governed_ai_endpoint("chat", ("Admin", "Manager", "Responsable Technique", "Technicien"))
def ai_chat(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
    """Assistant IA conversationnel — répond aux questions en langage naturel sur les données SAVIA."""
    from datetime import date, timedelta
    try:
        from ai_engine import _call_ia, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    message = body.get("message", "").strip()
    history = body.get("history", [])
    lang = _get_app_language(x_savia_lang, body)
    if not message:
        raise HTTPException(status_code=400, detail="Message vide.")

    # ── Aggregate compact data context ──
    today = date.today()
    ctx_parts = []
    try:
        df_interv = lire_interventions()
        if not df_interv.empty:
            total = len(df_interv)
            by_statut = df_interv['statut'].value_counts().to_dict() if 'statut' in df_interv.columns else {}
            by_type = df_interv['type_intervention'].value_counts().head(5).to_dict() if 'type_intervention' in df_interv.columns else {}
            by_tech = df_interv['technicien'].value_counts().head(5).to_dict() if 'technicien' in df_interv.columns else {}
            by_machine = df_interv['machine'].value_counts().head(5).to_dict() if 'machine' in df_interv.columns else {}
            by_client = df_interv['client'].value_counts().head(5).to_dict() if 'client' in df_interv.columns else {}
            # This month
            mois = 0
            if 'date' in df_interv.columns:
                month_str = today.strftime('%Y-%m')
                mois = int(df_interv['date'].astype(str).str[:7].eq(month_str).sum())
            ctx_parts.append(f"INTERVENTIONS: {total} total, {mois} ce mois. Statuts: {by_statut}. Types(top5): {by_type}. Techniciens(top5): {by_tech}. Machines(top5): {by_machine}. Clients(top5): {by_client}.")
    except Exception:
        pass
    try:
        df_equip = lire_equipements()
        if not df_equip.empty:
            n = len(df_equip)
            by_dom = df_equip['domaine'].value_counts().to_dict() if 'domaine' in df_equip.columns else {}
            by_st = df_equip['Statut'].value_counts().to_dict() if 'Statut' in df_equip.columns else {}
            by_cl = df_equip['Client'].value_counts().head(5).to_dict() if 'Client' in df_equip.columns else {}
            ctx_parts.append(f"EQUIPEMENTS: {n} total. Domaines: {by_dom}. Statuts: {by_st}. Clients(top5): {by_cl}.")
    except Exception:
        pass
    try:
        df_pieces = lire_pieces()
        if not df_pieces.empty:
            n = len(df_pieces)
            rupture = []
            if 'stock_actuel' in df_pieces.columns and 'stock_minimum' in df_pieces.columns:
                low = df_pieces[df_pieces['stock_actuel'] <= df_pieces['stock_minimum']]
                rupture = low['nom'].head(5).tolist() if 'nom' in low.columns else []
            ctx_parts.append(f"PIECES: {n} références. En rupture/stock bas: {rupture if rupture else 'aucune'}.")
    except Exception:
        pass
    try:
        df_plan = lire_planning()
        if not df_plan.empty:
            upcoming = df_plan[df_plan['date_prevue'].astype(str).str[:10] >= str(today)]
            n_upcoming = len(upcoming) if not upcoming.empty else 0
            ctx_parts.append(f"PLANNING: {n_upcoming} maintenances à venir.")
    except Exception:
        pass
    try:
        df_contrats = lire_contrats()
        if not df_contrats.empty:
            n = len(df_contrats)
            ctx_parts.append(f"CONTRATS: {n} contrats.")
    except Exception:
        pass

    data_context = "\n".join(ctx_parts) if ctx_parts else "Données non disponibles."

    # ── Build conversation ──
    hist_text = ""
    for h in history[-6:]:
        role = "Utilisateur" if h.get("role") == "user" else "Assistant"
        hist_text += f"{role}: {h.get('content','')}\n"

    prompt = f"""{_ai_language_instruction(lang)}
Tu es SAVIA Assistant, l'assistant IA intelligent de la plateforme SAVIA de gestion de maintenance d'équipements médicaux.

RÔLE: Tu aides les responsables techniques, managers et techniciens à comprendre leurs données, prendre des décisions et obtenir des insights sur leur parc d'équipements.

DONNÉES EN TEMPS RÉEL DE LA PLATEFORME:
{data_context}

DATE DU JOUR: {today.strftime('%d/%m/%Y')}

RÈGLES:
- {"Answer in English, concisely and professionally" if lang == "en" else "Réponds en français, de manière concise et professionnelle"}
- Utilise les données ci-dessus pour répondre avec des chiffres précis
- Si la question ne concerne pas les données, réponds quand même de manière utile (conseils maintenance, bonnes pratiques...)
- Formate ta réponse en texte simple (pas de markdown complexe), utilise des puces • pour les listes
- À la fin de ta réponse, sur une ligne séparée commençant par SUGGESTIONS:, propose 2-3 questions de suivi pertinentes séparées par |

{f"HISTORIQUE DE CONVERSATION:{chr(10)}{hist_text}" if hist_text else ""}

QUESTION DE L'UTILISATEUR: {message}"""

    raw = _call_ia(prompt, timeout=60)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")

    # Parse suggestions from response
    response_text = raw.strip()
    suggestions = []
    if "SUGGESTIONS:" in response_text:
        parts = response_text.split("SUGGESTIONS:")
        response_text = parts[0].strip()
        if len(parts) > 1:
            suggestions = [s.strip() for s in parts[1].strip().split("|") if s.strip()]

    chat_payload = _force_ai_payload_language(
        {"response": response_text, "suggestions": suggestions[:3]},
        lang,
        _call_ia,
        clean_json_response,
    )
    chat_response = chat_payload.get("response", response_text) if isinstance(chat_payload, dict) else response_text
    chat_suggestions = chat_payload.get("suggestions", suggestions[:3]) if isinstance(chat_payload, dict) else suggestions[:3]
    if not isinstance(chat_suggestions, list):
        chat_suggestions = suggestions[:3]
    return {
        "response": chat_response,
        "suggestions": chat_suggestions[:3],
    }


# ==========================================
# ADMIN — Utilisateurs
# ==========================================

__all__ = [
    "analyze_diagnostic",
    "analyze_performance",
    "analyze_pieces",
    "analyze_sav",
    "ai_analyze_costs",
    "ai_analyze_costs_pdf",
    "ai_chat",
]
