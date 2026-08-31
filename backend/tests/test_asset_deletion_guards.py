import pytest

from repositories import assets


class _Result:
    def __init__(self, *, one=None, many=None):
        self._one = one
        self._many = many or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class _ClientDeletionConnection:
    def __init__(self, equipment_count):
        self.equipment_count = equipment_count
        self.deleted = False

    def execute(self, query, params):
        if "FROM clients" in query and "FOR UPDATE" in query:
            return _Result(one={"id": params[0], "nom": "Clinique A"})
        if "SELECT COUNT(*) AS cnt" in query and "FROM equipements" in query:
            assert params == ("Clinique A",)
            return _Result(one={"cnt": self.equipment_count})
        if query.startswith("DELETE FROM clients"):
            self.deleted = True
            return _Result()
        raise AssertionError(f"Unexpected query: {query}")


def test_client_with_equipment_cannot_be_deleted(monkeypatch):
    connection = _ClientDeletionConnection(equipment_count=2)
    monkeypatch.setattr(assets, "get_db", lambda: _ConnectionContext(connection))

    with pytest.raises(assets.ClientHasEquipmentsError) as error:
        assets.supprimer_client(7)

    assert error.value.equipment_count == 2
    assert not connection.deleted


def test_client_without_equipment_can_be_deleted(monkeypatch):
    connection = _ClientDeletionConnection(equipment_count=0)
    backups = []
    monkeypatch.setattr(assets, "get_db", lambda: _ConnectionContext(connection))
    monkeypatch.setattr(assets, "_trigger_backup", lambda: backups.append(True))

    assert assets.supprimer_client(7) is True
    assert connection.deleted
    assert backups == [True]


class _EquipmentDeletionConnection:
    def __init__(self, contract_count=0, document_count=0):
        self.contract_count = contract_count
        self.document_count = document_count
        self.queries = []

    def execute(self, query, params):
        self.queries.append(query)
        if "FROM equipements" in query and "FOR UPDATE" in query:
            return _Result(one={"id": params[0], "nom": "Scanner A"})
        if "FROM documents_techniques" in query:
            return _Result(one={"cnt": self.document_count})
        if "FROM contrats_equipements" in query:
            return _Result(one={"cnt": self.contract_count})
        if query.startswith("DELETE FROM equipements"):
            return _Result()
        raise AssertionError(f"Unexpected query: {query}")


def test_equipment_without_dependencies_can_be_deleted(monkeypatch):
    connection = _EquipmentDeletionConnection()
    monkeypatch.setattr(assets, "get_db", lambda: _ConnectionContext(connection))
    monkeypatch.setattr(assets, "_trigger_backup", lambda: None)

    deleted = assets.supprimer_equipement(12)

    assert deleted is True
    assert any(query.startswith("DELETE FROM equipements") for query in connection.queries)


def test_equipment_with_technical_documents_cannot_be_deleted(monkeypatch):
    connection = _EquipmentDeletionConnection(document_count=2)
    monkeypatch.setattr(assets, "get_db", lambda: _ConnectionContext(connection))

    with pytest.raises(assets.EquipmentHasTechnicalDocumentsError) as error:
        assets.supprimer_equipement(12)

    assert error.value.document_count == 2
    assert not any(query.startswith("DELETE FROM equipements") for query in connection.queries)


def test_equipment_covered_by_contract_cannot_be_deleted(monkeypatch):
    connection = _EquipmentDeletionConnection(contract_count=1)
    monkeypatch.setattr(assets, "get_db", lambda: _ConnectionContext(connection))

    with pytest.raises(assets.EquipmentLinkedToContractsError) as error:
        assets.supprimer_equipement(12)

    assert error.value.contract_count == 1
    assert not any(query.startswith("DELETE FROM equipements") for query in connection.queries)
