import pytest
from fastapi import HTTPException

from controllers import admin, auth_dashboard
from repositories import parts


def test_notification_scope_is_limited_to_the_role_destination():
    assert admin._resolve_notification_scope({"role": "Manager"}) == ("gestionnaire", None)
    assert admin._resolve_notification_scope(
        {"role": "Technicien", "nom": "Sellami Ghazi"}
    ) == ("technicien", "Sellami Ghazi")

    with pytest.raises(HTTPException, match="destination"):
        admin._resolve_notification_scope({"role": "Manager"}, "technicien")
    with pytest.raises(HTTPException, match="notifications"):
        admin._resolve_notification_scope({"role": "Lecteur"})


def test_technician_without_identity_cannot_read_all_notifications():
    with pytest.raises(HTTPException, match="associé"):
        admin._resolve_notification_scope({"role": "Technicien", "nom": ""})


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _RateLimitDb:
    def __init__(self, attempts):
        self.attempts = iter(attempts)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))
        return _Result({"attempts": next(self.attempts)})


def test_login_rate_limit_uses_atomic_shared_database_upsert(monkeypatch):
    db = _RateLimitDb([1, 1, 6, 1])
    monkeypatch.setattr(auth_dashboard, "get_db", lambda: db)

    assert auth_dashboard._consume_login_attempts("ip:test", "account:test") is False
    assert auth_dashboard._consume_login_attempts("ip:test", "account:test") is True
    assert all("login_rate_limits" in query for query, _ in db.queries)
    assert all("ON CONFLICT" in query for query, _ in db.queries)


def test_browser_login_response_keeps_jwt_out_of_json_and_sets_secure_cookie(monkeypatch):
    user = {
        "username": "alice",
        "nom_complet": "Alice",
        "role": "Manager",
        "client": "",
        "pages_autorisees": "",
        "must_change_password": False,
    }
    assert "token" not in auth_dashboard._login_response(user)
    assert auth_dashboard._login_response(user, "secret-jwt")["token"] == "secret-jwt"

    class _Response:
        def __init__(self):
            self.cookies = []

        def set_cookie(self, **kwargs):
            self.cookies.append(kwargs)

    monkeypatch.setenv("NODE_ENV", "production")
    response = _Response()
    auth_dashboard._set_auth_cookie(response, "secret-jwt")
    assert response.cookies == [{
        "key": "savia_access",
        "value": "secret-jwt",
        "max_age": auth_dashboard.JWT_EXPIRY_HOURS * 3600,
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "path": "/",
    }]


class _NotificationDb:
    def __init__(self, row):
        self.row = row
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        return _Result(self.row)


@pytest.mark.parametrize("function_name", ["marquer_notification_lue", "marquer_notification_traitee"])
def test_notification_update_is_scoped_to_destination_and_technician(monkeypatch, function_name):
    db = _NotificationDb({"id": 42})
    monkeypatch.setattr(parts, "get_db", lambda: db)

    assert getattr(parts, function_name)(42, destination="technicien", technicien="Sellami Ghazi") is True
    assert "destination = %s" in db.query
    assert "LOWER(technicien) LIKE LOWER(%s)" in db.query
    assert db.params == (42, "technicien", "%Sellami Ghazi%")
