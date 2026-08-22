import pytest
from fastapi import HTTPException

from api.security import (
    INTERNAL_WRITE_ROLES,
    _check_create_demande_permission,
    _check_create_permission,
    _check_create_piece_permission,
    assert_client_access,
    get_client_scope,
    require_roles,
    resolve_client_scope,
)
from controllers.requests import _INTERVENTION_ACTION_ROLES


ALL_ROLES = (
    "Admin",
    "Manager",
    "Responsable Technique",
    "Technicien",
    "Gestionnaire",
    "Lecteur",
)


ROLE_POLICY_MATRIX = {
    "intervention_status_actions": set(_INTERVENTION_ACTION_ROLES),
    "map_coordinate_update": {"Admin", "Manager", "Responsable Technique"},
    "create_operational_resource": set(INTERNAL_WRITE_ROLES),
    "create_demande": {"Admin", "Manager", "Responsable Technique", "Lecteur"},
    "read_stock": {"Admin", "Manager", "Responsable Technique", "Technicien", "Gestionnaire"},
    "create_piece": {"Admin", "Manager", "Responsable Technique", "Gestionnaire"},
}


def user_for(role: str) -> dict:
    return {
        "role": role,
        "client": "Clinique A" if role == "Lecteur" else "",
    }


@pytest.mark.parametrize(
    "policy,allowed_roles",
    ROLE_POLICY_MATRIX.items(),
)
def test_role_policy_matrix(policy, allowed_roles):
    assert allowed_roles <= set(ALL_ROLES), f"{policy} contient un rôle inconnu"
    for role in ALL_ROLES:
        user = user_for(role)
        if role in allowed_roles:
            require_roles(user, *allowed_roles)
        else:
            with pytest.raises(HTTPException, match="rôle"):
                require_roles(user, *allowed_roles)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_creation_policies_match_the_role_matrix(role):
    user = user_for(role)
    assert _check_create_permission(user) is (role in ROLE_POLICY_MATRIX["create_operational_resource"])
    assert _check_create_demande_permission(user) is (role in ROLE_POLICY_MATRIX["create_demande"])
    assert _check_create_piece_permission(user) is (role in ROLE_POLICY_MATRIX["create_piece"])


@pytest.mark.parametrize("role", ALL_ROLES)
def test_client_scope_matrix_is_fail_closed_for_reader(role):
    user = user_for(role)
    if role == "Lecteur":
        assert get_client_scope(user) == "Clinique A"
        assert resolve_client_scope(user, "clinique a") == "Clinique A"
        with pytest.raises(HTTPException, match="autre client"):
            resolve_client_scope(user, "Clinique B")
        with pytest.raises(HTTPException, match="ressource"):
            assert_client_access(user, "Clinique B")
    else:
        assert get_client_scope(user) is None
        assert resolve_client_scope(user, "Clinique B") == "Clinique B"
        assert_client_access(user, "Clinique B") is None
