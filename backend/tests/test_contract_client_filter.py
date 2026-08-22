from repositories import contracts


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_contracts_filter_normalizes_client_name(monkeypatch):
    captured = {}

    def fake_read_sql(query, _connection, params=None):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr(contracts, "get_db", lambda: _Connection())
    monkeypatch.setattr(contracts, "read_sql", fake_read_sql)

    assert contracts.lire_contrats(" client1 ") == []
    assert "LOWER(TRIM(client)) = LOWER(TRIM(%s))" in captured["query"]
    assert captured["params"] == (" client1 ",)
