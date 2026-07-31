"""Consent, quota, and content-free audit endpoints for Gemini."""

from api.runtime import Body, Depends, HTTPException, app
from api.security import _verify_token
from controllers.admin import _require_admin
from services.ai_governance import (
    get_admin_ai_governance,
    get_my_ai_governance,
    set_ai_consent,
    update_ai_data_location,
    update_ai_active_offer,
    update_ai_offer,
    update_ai_user_entitlement,
)


@app.get("/api/ai/governance/me")
def get_my_ai_policy(user: dict = Depends(_verify_token)):
    return get_my_ai_governance(user["sub"])


@app.post("/api/ai/governance/consent")
def set_my_ai_consent(body: dict = Body(...), user: dict = Depends(_verify_token)):
    accepted = body.get("accepted")
    if not isinstance(accepted, bool):
        raise HTTPException(status_code=400, detail="La valeur accepted est requise")
    return set_ai_consent(user["sub"], accepted)


@app.get("/api/admin/ai-governance")
def get_ai_governance(user: dict = Depends(_verify_token)):
    _require_admin(user)
    return get_admin_ai_governance()


@app.put("/api/admin/ai-governance/offers/{code}")
def save_ai_offer(code: str, body: dict = Body(...), user: dict = Depends(_verify_token)):
    _require_admin(user)
    update_ai_offer(code, body)
    return {"ok": True}


@app.put("/api/admin/ai-governance/active-offer")
def save_active_ai_offer(body: dict = Body(...), user: dict = Depends(_verify_token)):
    _require_admin(user)
    update_ai_active_offer(str(body.get("offer_code") or ""))
    return {"ok": True}


@app.put("/api/admin/ai-governance/users/{user_id}")
def save_ai_user(user_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    _require_admin(user)
    update_ai_user_entitlement(user_id, body)
    return {"ok": True}


@app.put("/api/admin/ai-governance/data-location")
def save_ai_data_location(body: dict = Body(...), user: dict = Depends(_verify_token)):
    _require_admin(user)
    update_ai_data_location(body.get("data_location", ""))
    return {"ok": True}


__all__ = [
    "get_my_ai_policy",
    "set_my_ai_consent",
    "get_ai_governance",
    "save_ai_offer",
    "save_active_ai_offer",
    "save_ai_user",
    "save_ai_data_location",
]
