from repositories.contracts import _resolve_contract_equipment_rows


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def execute(self, query, params):
        assert "id = ANY(%s)" in query
        assert params == ([101, 102, 103], "Clinique Avicenne")
        return _Rows([
            {"id": 101, "nom": "Respirateur d'anesthésie"},
            {"id": 102, "nom": "Respirateur d'anesthésie"},
            {"id": 103, "nom": "Respirateur d'anesthésie"},
        ])


def test_contract_keeps_distinct_equipment_ids_when_names_match():
    rows = _resolve_contract_equipment_rows(
        _Connection(),
        {
            "client": "Clinique Avicenne",
            "equipements": [
                "Respirateur d'anesthésie",
                "Respirateur d'anesthésie",
                "Respirateur d'anesthésie",
            ],
            "equipement_ids": [101, 102, 103],
        },
    )

    assert rows == [
        (101, "Respirateur d'anesthésie"),
        (102, "Respirateur d'anesthésie"),
        (103, "Respirateur d'anesthésie"),
    ]
