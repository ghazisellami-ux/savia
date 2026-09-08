from controllers import planning
import pytest
from fastapi import HTTPException


def test_planning_creation_sends_a_complete_technical_telegram_notification(monkeypatch):
    sent = {}

    monkeypatch.setattr(planning, "ajouter_planning", lambda body: 73)
    monkeypatch.setattr(planning, "log_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        planning,
        "send_telegram_reliably",
        lambda bot_key, message, dedupe_key: sent.update(
            bot_key=bot_key, message=message, dedupe_key=dedupe_key
        ) or True,
    )

    result = planning.create_planning(
        {
            "machine": "Scanner CT 16B",
            "client": "Clinique Pasteur",
            "type_maintenance": "Installation",
            "date_prevue": "2026-09-14",
            "technicien_assigne": "Amine",
            "recurrence": "Aucune",
            "description": "Mise en service sur site",
            "notes": "Prévoir les accessoires.",
        },
        user={"role": "Manager", "sub": "manager"},
    )

    assert result == {"ok": True, "id": 73, "telegram_sent": True}
    assert sent["bot_key"] == "telegram"
    assert sent["dedupe_key"] == "planning:73:created"
    assert "INTERVENTION PLANIFIÉE — #73" in sent["message"]
    assert "Type : <b>Installation</b>" in sent["message"]
    assert "Équipement : <b>Scanner CT 16B</b>" in sent["message"]
    assert "Client / site : <b>Clinique Pasteur</b>" in sent["message"]
    assert "Date prévue : <b>14/09/2026</b>" in sent["message"]
    assert "Technicien(s) : Amine" in sent["message"]
    assert "Récurrence : Aucune" in sent["message"]
    assert "Description : Mise en service sur site" in sent["message"]
    assert "Notes : Prévoir les accessoires." in sent["message"]


@pytest.mark.parametrize("role", ["Admin", "Manager", "Responsable Technique"])
def test_authorized_roles_can_delete_a_manual_planning(monkeypatch, role):
    monkeypatch.setattr(
        planning,
        "supprimer_planning",
        lambda planning_id: {
            "deleted_planning": 1,
            "deleted_interventions": 1,
            "recurring": False,
        },
    )
    monkeypatch.setattr(planning, "log_audit", lambda *args, **kwargs: None)

    result = planning.delete_planning(73, user={"role": role, "sub": "responsable"})

    assert result == {
        "ok": True,
        "deleted_planning": 1,
        "deleted_interventions": 1,
        "recurring": False,
    }


def test_delete_planning_returns_not_found_for_a_missing_entry(monkeypatch):
    def missing_planning(_planning_id):
        raise KeyError("missing")

    monkeypatch.setattr(planning, "supprimer_planning", missing_planning)

    with pytest.raises(HTTPException) as error:
        planning.delete_planning(999, user={"role": "Admin", "sub": "admin"})

    assert error.value.status_code == 404


def test_delete_planning_rejects_a_contract_generated_entry(monkeypatch):
    def contract_planning(_planning_id):
        raise ValueError("Ce planning est généré par un contrat de maintenance")

    monkeypatch.setattr(planning, "supprimer_planning", contract_planning)

    with pytest.raises(HTTPException) as error:
        planning.delete_planning(22, user={"role": "Manager", "sub": "manager"})

    assert error.value.status_code == 400
    assert "contrat de maintenance" in error.value.detail
