from controllers.clients_dashboard import _is_terminal_intervention_status
from database.migrations.runner import MIGRATIONS


def test_availability_trend_recognizes_all_closed_intervention_statuses():
    for status in ("Cloturee", "Clôturée", "Terminée", "Réalisée", "Annulée"):
        assert _is_terminal_intervention_status(status) is True

    assert _is_terminal_intervention_status("En cours") is False


def test_technician_id_refresh_migration_is_registered():
    migrations = [migration for migration in MIGRATIONS if migration[0] == "037"]

    assert len(migrations) == 1
    assert "technician assignment" in migrations[0][1]
