from unittest.mock import patch

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


class _ModelConnection:
    def __init__(self, models):
        self.models = models
        self.inserted = False

    def execute(self, query, params=None):
        if query.startswith("SELECT id, nom, domaine, type_equipement, fabricant"):
            return _Result(many=self.models)
        if query.lstrip().startswith("INSERT INTO modeles_equipement"):
            self.inserted = True
            return _Result(one={
                "id": 99,
                "nom": params[0],
                "domaine": params[1],
                "type_equipement": params[2],
                "fabricant": params[3],
            })
        raise AssertionError(f"Unexpected query: {query}")


def test_existing_model_is_not_created_again_after_label_normalization():
    connection = _ModelConnection([{
        "id": 7,
        "nom": "WATO\u00a0EX-55  Pro ",
        "domaine": "POC / Soins Intensifs",
        "type_equipement": "Ventilateur",
        "fabricant": "Mindray",
    }])

    with patch.object(assets, "get_db", return_value=_ConnectionContext(connection)):
        model = assets.ajouter_modele_equipement(
            " WATO EX-55 Pro ",
            "POC / Soins Intensifs",
            "Ventilateur",
            "MINDRAY",
        )

    assert model["id"] == 7
    assert model["nom"] == "WATO EX-55 Pro"
    assert model["created"] is False
    assert connection.inserted is False


def test_model_list_hides_visually_identical_legacy_duplicates():
    connection = _ModelConnection([
        {"id": 7, "nom": "WATO EX-55 Pro", "domaine": "POC", "type_equipement": "Ventilateur", "fabricant": "Mindray"},
        {"id": 8, "nom": "WATO\u00a0EX-55  Pro ", "domaine": "POC", "type_equipement": "Ventilateur", "fabricant": "MINDRAY"},
    ])

    with patch.object(assets, "get_db", return_value=_ConnectionContext(connection)):
        models = assets.lire_modeles_equipement("POC", "Ventilateur", "Mindray")

    assert [model["nom"] for model in models] == ["WATO EX-55 Pro"]
