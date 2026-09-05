from types import SimpleNamespace

from controllers import auth_dashboard


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _LoginDb:
    def __init__(self, user):
        self.user = user

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, _params=None):
        if "SELECT * FROM utilisateurs" in query:
            return _Result(self.user)
        return _Result()


class _Response:
    def __init__(self):
        self.cookies = []

    def set_cookie(self, **kwargs):
        self.cookies.append(kwargs)


def test_pwa_login_does_not_overwrite_dashboard_cookie(monkeypatch):
    user = {
        "id": 1,
        "username": "tech",
        "nom_complet": "Technicien Test",
        "role": "Technicien",
        "client": "",
        "pages_autorisees": "",
        "password_hash": "unused",
        "password_changed_at": None,
        "must_change_password": False,
    }
    monkeypatch.setattr(auth_dashboard, "get_db", lambda: _LoginDb(user))
    monkeypatch.setattr(auth_dashboard, "_consume_login_attempts", lambda *_keys: False)
    monkeypatch.setattr(auth_dashboard, "_clear_login_attempts", lambda *_keys: None)
    monkeypatch.setattr(auth_dashboard, "_verify_password", lambda *_args: True)
    monkeypatch.setattr(auth_dashboard, "_password_rotation_due", lambda _value: False)
    monkeypatch.setattr(auth_dashboard, "_issue_access_token", lambda _user: "pwa-token")
    monkeypatch.setattr(auth_dashboard, "log_audit", lambda *_args, **_kwargs: None)

    request = SimpleNamespace(
        headers={"X-SAVIA-Client": "pwa"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )
    response = _Response()
    result = auth_dashboard.login(
        auth_dashboard.LoginRequest(username="tech", password="password"),
        request,
        response,
    )

    assert result["token"] == "pwa-token"
    assert response.cookies == []
