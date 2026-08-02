from repositories.equipment_status import (
    EQUIPMENT_MAINTENANCE,
    EQUIPMENT_OPERATIONAL,
    calculer_nouveau_statut_equipement,
)


def test_starting_an_intervention_puts_equipment_in_maintenance():
    assert (
        calculer_nouveau_statut_equipement(EQUIPMENT_OPERATIONAL, "En cours")
        == EQUIPMENT_MAINTENANCE
    )


def test_waiting_for_a_part_remains_an_active_equipment_state():
    assert (
        calculer_nouveau_statut_equipement(EQUIPMENT_OPERATIONAL, "En attente de piece")
        == EQUIPMENT_MAINTENANCE
    )


def test_closing_returns_to_operational_when_no_other_intervention_is_active():
    assert (
        calculer_nouveau_statut_equipement(EQUIPMENT_MAINTENANCE, "Cloturee")
        == EQUIPMENT_OPERATIONAL
    )


def test_closing_keeps_equipment_in_maintenance_when_another_intervention_is_active():
    assert (
        calculer_nouveau_statut_equipement(
            EQUIPMENT_MAINTENANCE,
            "Cloturee",
            has_other_active_intervention=True,
        )
        == EQUIPMENT_MAINTENANCE
    )


def test_manual_out_of_service_status_is_never_overridden_automatically():
    assert (
        calculer_nouveau_statut_equipement("Hors Service", "Cloturee")
        == "Hors Service"
    )
