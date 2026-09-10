from datetime import date

from services.spare_parts_prediction_engine import _future_contract_demand, _prediction_for_piece


PIECE = {
    "id": 1,
    "reference": "TUBE-RX",
    "designation": "Tube radiogène",
    "equipement_type": "Scanner CT",
}


def test_contract_quota_is_reduced_by_used_parts_and_distributed_over_future_visits():
    as_of = date(2026, 9, 10)
    interventions = [
        {
            "date": date(2026, 8, 1),
            "machine": "Scanner 1",
            "planning_id": 11,
            "pieces_utilisees": '[{"ref":"TUBE-RX", "quota": 1}]',
            "type_intervention": "Préventive",
        }
    ]
    contracts = [{
        "id": 7,
        "client": "Clinique A",
        "type_contrat": "Maintenance Préventive",
        "avec_pieces": 1,
        "pieces_incluses": '[{"ref":"TUBE-RX", "quota": 4}]',
        "date_fin": date(2027, 1, 1),
    }]
    planning = [
        {"id": 11, "contrat_id": 7, "machine": "Scanner 1", "client": "Clinique A", "date_prevue": date(2026, 8, 1), "statut": "Cloturee", "is_ghost": False},
        {"id": 12, "contrat_id": 7, "machine": "Scanner 1", "client": "Clinique A", "date_prevue": date(2026, 10, 1), "statut": "Planifiée", "is_ghost": False},
        {"id": 13, "contrat_id": 7, "machine": "Scanner 1", "client": "Clinique A", "date_prevue": date(2026, 11, 1), "statut": "Planifiée", "is_ghost": False},
    ]

    demand = _future_contract_demand(
        PIECE, interventions, contracts, planning, {"scanner1": "scannerct"}, as_of,
    )

    assert demand["interventions_planifiees"] == 2
    assert demand["quantite_quota_contrat"] == 3
    assert demand["quantite_estimee_historique"] == 0
    assert demand["prochaine_intervention"] == "2026-10-01"
    assert [event["quantity"] for event in demand["events"]] == [1.5, 1.5]


def test_contract_visit_without_part_quota_uses_observed_preventive_consumption_only():
    as_of = date(2026, 9, 10)
    interventions = [
        {
            "date": date(2026, 7, 1),
            "machine": "Scanner 1",
            "planning_id": None,
            "pieces_utilisees": '[{"ref":"TUBE-RX", "quantity": 2}]',
            "type_intervention": "Préventive",
        },
        {
            "date": date(2026, 8, 1),
            "machine": "Scanner 1",
            "planning_id": None,
            "pieces_utilisees": "",
            "type_intervention": "Préventive",
        },
    ]
    contracts = [{
        "id": 8,
        "client": "Clinique A",
        "type_contrat": "Maintenance Préventive",
        "avec_pieces": 0,
        "pieces_incluses": "",
        "date_fin": date(2027, 1, 1),
    }]
    planning = [{
        "id": 20, "contrat_id": 8, "machine": "Scanner 1", "client": "Clinique A", "date_prevue": date(2026, 10, 1), "statut": "Planifiée", "is_ghost": False,
    }]

    demand = _future_contract_demand(
        PIECE, interventions, contracts, planning, {"scanner1": "scannerct"}, as_of,
    )

    assert demand["interventions_planifiees"] == 1
    assert demand["quantite_quota_contrat"] == 0
    assert demand["quantite_estimee_historique"] == 1
    assert demand["events"][0]["source"] == "historique_preventif"


def test_open_technician_requests_reserve_stock_before_calculating_order_date():
    as_of = date(2026, 9, 10)
    piece = {**PIECE, "stock_actuel": 1, "stock_minimum": 1, "prix_unitaire": 500, "delai_fournisseur_jours": 10}
    interventions = [{
        "date": date(2026, 8, 1), "machine": "Scanner 1", "planning_id": None,
        "pieces_utilisees": '[{"ref":"TUBE-RX", "quantity": 1}]', "type_intervention": "Corrective",
    }]

    prediction = _prediction_for_piece(
        piece,
        interventions,
        [],
        [],
        [{"reference": "TUBE-RX", "client": "Clinique A"}],
        {"scanner1": "scannerct"},
        as_of,
    )

    assert prediction["demandes_pieces_en_attente"] == 1
    assert prediction["stock_disponible_apres_demandes"] == 0
    assert prediction["date_commande"] == "2026-09-10"
    assert prediction["urgence"] == "CRITIQUE"
