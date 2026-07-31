from pathlib import Path

import pytest
from fastapi import HTTPException

import services.ai_governance as governance


def test_governed_endpoint_rejects_role_before_reserving_quota(monkeypatch):
    monkeypatch.setattr(
        governance,
        "reserve_ai_usage",
        lambda *_args: (_ for _ in ()).throw(AssertionError("quota must not be reserved")),
    )

    @governance.governed_ai_endpoint("diagnostic", ("Admin",))
    def endpoint(user: dict):
        return {"ok": True}

    with pytest.raises(HTTPException) as error:
        endpoint({"sub": "tech", "role": "Technicien"})
    assert error.value.status_code == 403


def test_governed_endpoint_logs_outcome_and_marks_human_validation(monkeypatch):
    reservation = governance.AiUsageReservation(17)
    outcomes = []
    monkeypatch.setattr(governance, "reserve_ai_usage", lambda *_args: reservation)
    monkeypatch.setattr(governance, "finish_ai_usage", lambda _reservation, **kwargs: outcomes.append(kwargs))

    @governance.governed_ai_endpoint("sav", ("Admin",))
    def endpoint(user: dict):
        return {"ok": True, "result": {"recommendation": "inspecter"}}

    result = endpoint({"sub": "admin", "role": "Admin"})
    assert outcomes == [{"success": True}]
    assert result["ai_governance"]["human_validation_required"] is True


def test_governed_endpoint_marks_failed_ai_calls(monkeypatch):
    reservation = governance.AiUsageReservation(23)
    outcomes = []
    monkeypatch.setattr(governance, "reserve_ai_usage", lambda *_args: reservation)
    monkeypatch.setattr(governance, "finish_ai_usage", lambda _reservation, **kwargs: outcomes.append(kwargs))

    @governance.governed_ai_endpoint("chat", ("Admin",))
    def endpoint(user: dict):
        raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError):
        endpoint({"sub": "admin", "role": "Admin"})
    assert outcomes == [{"success": False, "error_code": "internal_error"}]


def test_ai_policy_and_new_audit_schema_do_not_store_prompt_or_response_content():
    backend_root = Path(__file__).parents[1]
    migration = (backend_root / "database" / "migrations" / "runner.py").read_text(encoding="utf-8")
    audit_table = migration.split("CREATE TABLE IF NOT EXISTS ai_usage_audit", 1)[1].split(')"""', 1)[0].lower()

    assert "prompt" not in audit_table
    assert "response" not in audit_table
