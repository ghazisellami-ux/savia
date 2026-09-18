from contextlib import nullcontext

import pytest
from fastapi import HTTPException

from controllers import interventions


def test_technician_cannot_create_an_intervention_directly():
    with pytest.raises(HTTPException):
        interventions.create_intervention(
            {"client": "Clinique A", "machine": "Scanner 1"},
            user={"role": "Technicien", "sub": "tech-connecte", "nom": "Tech Connecté"},
        )


def test_responsable_can_create_and_assign_an_intervention(monkeypatch):
    saved = {}

    class FakeResult:
        def fetchone(self):
            return {"id": 7, "nom": "Scanner 1", "client": "Clinique A"}

    class FakeConnection:
        def execute(self, *_args, **_kwargs):
            return FakeResult()

    monkeypatch.setattr(interventions, "get_db", lambda: nullcontext(FakeConnection()))

    monkeypatch.setattr(interventions, "ajouter_intervention", lambda body: saved.update(body) or 42)
    monkeypatch.setattr(interventions, "_get_technician_fullname", lambda username: f"Nom de {username}")
    monkeypatch.setattr(interventions, "log_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(interventions, "_send_telegram_bot", lambda *args, **kwargs: None)

    result = interventions.create_intervention(
        {
            "client": "Clinique A",
            "machine": "Scanner 1",
            "equipement_id": 7,
            "technicien": "tech-assigne",
            "statut": "Assignée",
            "type_intervention": "Corrective",
        },
        user={"role": "Responsable Technique", "sub": "responsable"},
    )

    assert result == {"ok": True, "id": 42}
    assert saved["equipement_id"] == 7
    assert saved["technicien"] == "Nom de tech-assigne"
    assert saved["statut"] == "Assignée"
