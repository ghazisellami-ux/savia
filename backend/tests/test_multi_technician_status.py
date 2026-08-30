from controllers.requests import _synchroniser_statut_parent_multi_tech


def test_multi_tech_waiting_for_part_updates_parent_status():
    calls = []

    result = _synchroniser_statut_parent_multi_tech(
        27,
        "En attente de piece",
        lambda intervention_id, status: calls.append((intervention_id, status)),
    )

    assert result == "En attente de piece"
    assert calls == [(27, "En attente de piece")]


def test_multi_tech_in_progress_keeps_parent_status_synchronised():
    calls = []

    result = _synchroniser_statut_parent_multi_tech(
        27,
        "En cours",
        lambda intervention_id, status: calls.append((intervention_id, status)),
    )

    assert result == "En cours"
    assert calls == [(27, "En cours")]


def test_multi_tech_workshop_transfer_updates_parent_status():
    calls = []

    result = _synchroniser_statut_parent_multi_tech(
        27,
        "Transfert vers l'atelier",
        lambda intervention_id, status: calls.append((intervention_id, status)),
    )

    assert result == "Transfert vers l'atelier"
    assert calls == [(27, "Transfert vers l'atelier")]


def test_multi_tech_unrelated_status_does_not_override_parent_status():
    calls = []

    result = _synchroniser_statut_parent_multi_tech(
        27,
        "Cloturee",
        lambda intervention_id, status: calls.append((intervention_id, status)),
    )

    assert result is None
    assert calls == []
