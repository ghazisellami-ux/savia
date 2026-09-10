from datetime import date, datetime, timedelta

import services.scheduled_jobs as jobs
from services.sla_tracking import (
    active_sla_contracts, compliance_percentage, elapsed_hours, sla_contract_for,
    sla_start_at, sla_start_value,
)


def _contract(contract_id, client, equipment, sla_h, **extra):
    return {
        "id": contract_id,
        "client": client,
        "equipement": equipment,
        "sla_temps_reponse_h": sla_h,
        "statut": "Actif",
        "date_debut": (date.today() - timedelta(days=1)).isoformat(),
        "date_fin": (date.today() + timedelta(days=30)).isoformat(),
        **extra,
    }


def test_sla_uses_the_contract_covering_the_equipment_not_another_client_contract():
    contracts = active_sla_contracts([
        _contract(1, "Clinique A", "Scanner", 4),
        _contract(2, "Clinique A", "IRM", 12),
        _contract(3, "Clinique A", "Radiographie", 1, statut="Inactif"),
        _contract(4, "Clinique A", "Echographe", 1, date_fin=(date.today() - timedelta(days=1)).isoformat()),
    ])

    scanner = sla_contract_for(contracts, " clinique  a ", "SCANNER")

    assert scanner is not None
    assert scanner["id"] == 1
    assert scanner["sla_h"] == 4
    assert sla_contract_for(contracts, "Clinique A", "Échographe") is None


def test_preventive_contract_does_not_apply_a_sla_to_corrective_work():
    contracts = active_sla_contracts([
        _contract(1, "Clinique A", "Scanner", 4, type_contrat="Maintenance Préventive"),
    ])

    assert sla_contract_for(contracts, "Clinique A", "Scanner", "Corrective") is None
    assert sla_contract_for(contracts, "Clinique A", "Scanner", "Préventive")["id"] == 1


def test_sla_day_without_a_time_starts_at_eight_am():
    now = datetime(2026, 9, 4, 10, 0)

    assert elapsed_hours("2026-09-04", now, business_day_start_hour=8) == 2
    assert sla_start_at("2026-09-04", business_day_start_hour=8) == datetime(2026, 9, 4, 8, 0)


def test_sla_follows_the_latest_planning_date_after_multiple_reschedules():
    intervention = {
        "date": "2026-09-04",
        "date_debut_intervention": "2026-09-07T19:11:00",
        "planning_date": "2026-09-12",
    }

    assert sla_start_value(intervention) == "2026-09-12"
    intervention["planning_date"] = "2026-09-18"
    assert sla_start_value(intervention) == "2026-09-18"


def test_active_sla_breach_lowers_global_compliance_immediately():
    assert compliance_percentage(0, 0, [{"breached": True}]) == 0
    assert compliance_percentage(1, 1, [{"breached": True}]) == 50


def test_sla_alerts_include_overdue_unanswered_requests(monkeypatch):
    now = datetime.now()
    monkeypatch.setattr(jobs, "lire_contrats", lambda: jobs.pd.DataFrame([
        _contract(9, "Clinique A", "Scanner", 2),
    ]))
    monkeypatch.setattr(jobs, "lire_interventions", lambda: jobs.pd.DataFrame())
    monkeypatch.setattr(jobs, "lire_equipements", lambda: jobs.pd.DataFrame())
    monkeypatch.setattr(jobs, "lire_demandes_intervention", lambda: jobs.pd.DataFrame([
        {
            "id": 45,
            "statut": "Nouvelle",
            "client": "Clinique A",
            "equipement": "Scanner",
            "date_demande": now - timedelta(hours=3),
            "technicien_assigne": "",
        },
    ]))
    monkeypatch.setattr(jobs, "get_contract_equipements", lambda contract_id: [])
    messages = []
    monkeypatch.setattr(jobs, "_send_telegram_bot", lambda destination, message: messages.append((destination, message)))

    result = jobs.check_sla_alerts()

    assert result == {"danger": 0, "breached": 1}
    assert len(messages) == 1
    assert messages[0][0] == "telegram_manager"
    assert "DEM-45" in messages[0][1]
    assert "Contrat #9" in messages[0][1]
