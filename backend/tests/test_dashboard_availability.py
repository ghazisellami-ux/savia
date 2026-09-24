from controllers.clients_dashboard import _is_terminal_intervention_status


def test_availability_trend_recognizes_all_closed_intervention_statuses():
    for status in ("Cloturee", "Clôturée", "Terminée", "Réalisée", "Annulée"):
        assert _is_terminal_intervention_status(status) is True

    assert _is_terminal_intervention_status("En cours") is False
