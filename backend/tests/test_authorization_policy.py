import pytest
from fastapi import HTTPException

from api.security import (
    assert_client_access,
    assert_intervention_write_access,
    get_client_scope,
    resolve_client_scope,
)


def lecteur(client="Clinique A"):
    return {"role": "Lecteur", "client": client}


def test_client_account_cannot_override_its_client_filter():
    assert resolve_client_scope(lecteur(), "clinique a") == "Clinique A"
    with pytest.raises(HTTPException, match="autre client"):
        resolve_client_scope(lecteur(), "Clinique B")


def test_client_account_without_client_is_denied_by_default():
    with pytest.raises(HTTPException, match="associé"):
        get_client_scope(lecteur(""))


def test_client_account_cannot_open_another_clients_resource():
    assert_client_access(lecteur(), "clinique a")
    with pytest.raises(HTTPException, match="ressource"):
        assert_client_access(lecteur(), "Clinique B")


def test_internal_user_keeps_cross_client_operational_access():
    manager = {"role": "Manager", "client": ""}
    assert resolve_client_scope(manager, "Clinique B") == "Clinique B"
    assert_client_access(manager, "Clinique B")


class _Result:
    def __init__(self, *, one=None, many=None):
        self._one = one
        self._many = many or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _AssignedInterventionConnection:
    def __init__(self, assignments):
        self.assignments = assignments

    def execute(self, query, _params):
        if "COALESCE(NULLIF(i.client" in query:
            return _Result(one={"client": ""})
        return _Result(many=[{"assigned_name": name} for name in self.assignments])


def test_technician_can_update_an_assignment_with_reversed_first_last_name():
    conn = _AssignedInterventionConnection(["Ghazi Sellami"])
    user = {"role": "Technicien", "nom": "Sellami Ghazi", "sub": "ghazi"}

    assert_intervention_write_access(conn, 42, user)


def test_technician_cannot_update_another_technicians_assignment():
    conn = _AssignedInterventionConnection(["Amine Ben Salah"])
    user = {"role": "Technicien", "nom": "Sellami Ghazi", "sub": "ghazi"}

    with pytest.raises(HTTPException, match="pas assignée"):
        assert_intervention_write_access(conn, 42, user)
