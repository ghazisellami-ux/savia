import pytest
from fastapi import HTTPException

from api.security import assert_client_access, get_client_scope, resolve_client_scope


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
