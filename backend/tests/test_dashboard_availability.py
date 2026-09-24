import pandas as pd

from controllers.auth_dashboard import _filter_interventions_for_equipments
from controllers.clients_dashboard import _is_terminal_intervention_status
from database.migrations.runner import MIGRATIONS


def test_availability_trend_recognizes_all_closed_intervention_statuses():
    for status in ("Cloturee", "Clôturée", "Terminée", "Réalisée", "Annulée"):
        assert _is_terminal_intervention_status(status) is True

    assert _is_terminal_intervention_status("En cours") is False


def test_dashboard_equipment_scope_uses_ids_before_machine_names():
    equipments = pd.DataFrame([
        {"id": 10, "Nom": "Respirateur"},
    ])
    interventions = pd.DataFrame([
        {"equipement_id": 10, "machine": "Respirateur"},
        {"equipement_id": 11, "machine": "Respirateur"},
        {"equipement_id": None, "machine": "Respirateur"},
    ])

    scoped = _filter_interventions_for_equipments(interventions, equipments)

    # The first row is the selected equipment; the third is a legacy record
    # without an ID. The same-name equipment with ID 11 must be excluded.
    assert scoped.index.tolist() == [0, 2]


def test_technician_id_refresh_migration_is_registered():
    migrations = [migration for migration in MIGRATIONS if migration[0] == "037"]

    assert len(migrations) == 1
    assert "technician assignment" in migrations[0][1]
