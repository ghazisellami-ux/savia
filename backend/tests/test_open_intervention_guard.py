from repositories.interventions import (
    CLOSED_INTERVENTION_STATUSES,
    InterventionAlreadyOpenError,
    find_open_intervention,
    is_preventive_intervention,
    is_urgent_corrective,
    lock_equipment_intervention_key,
)


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        if "SELECT i.id" in query:
            return _Result({"id": 91, "statut": "En cours"})
        return _Result()


def test_open_intervention_lookup_is_scoped_to_equipment_id_and_client():
    connection = _Connection()

    lock_equipment_intervention_key(connection, 17)
    result = find_open_intervention(connection, 17, "Clinique A")

    assert result["id"] == 91
    assert connection.calls[0][1] == ("open-intervention-equipment::17",)
    assert connection.calls[1][1][0:2] == (17, "Clinique A")
    assert "i.equipement_id = %s" in connection.calls[1][0]
    assert "Cloturee" in connection.calls[1][1]
    assert CLOSED_INTERVENTION_STATUSES


def test_duplicate_error_contains_existing_intervention_number():
    error = InterventionAlreadyOpenError(91)

    assert error.intervention_id == 91
    assert str(error) == "Une intervention est déjà ouverte #91 pour cet équipement."


def test_only_high_or_critical_corrective_work_can_coexist_with_preventive_work():
    assert is_preventive_intervention("Maintenance Préventive") is True
    assert is_urgent_corrective("Corrective", "Haute") is True
    assert is_urgent_corrective("Corrective", "Critique") is True
    assert is_urgent_corrective("Corrective", "Moyenne") is False
    assert is_urgent_corrective("Préventive", "Critique") is False
