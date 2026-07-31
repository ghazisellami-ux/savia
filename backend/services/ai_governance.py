"""Server-side governance for Gemini usage without retaining prompts or replies."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import date
from functools import wraps
from typing import Callable, Iterable

from fastapi import HTTPException

from db_engine import get_db


AI_CONSENT_VERSION = "2026-07-31"
AI_PROVIDER = "Google Gemini"
AI_MODEL_LABEL = "gemini-auto"


@dataclass(frozen=True)
class AiUsageReservation:
    audit_id: int


def _month_start() -> date:
    today = date.today()
    return today.replace(day=1)


def _governance_row(conn, username: str, *, lock_user: bool = False) -> dict:
    lock_clause = " FOR UPDATE OF u" if lock_user else ""
    row = conn.execute(
        f"""SELECT u.id, u.username, u.client,
                   COALESCE(e.ai_enabled, TRUE) AS ai_enabled,
                   COALESCE(e.consent_version, '') AS consent_version,
                   e.consented_at, e.consent_revoked_at,
                   o.code AS offer_code, o.monthly_quota
            FROM utilisateurs u
            LEFT JOIN ai_user_entitlements e ON e.user_id = u.id
            LEFT JOIN config_client cfg ON cfg.cle = 'ai_active_offer_code'
            LEFT JOIN ai_offers o ON o.code = COALESCE(cfg.valeur, 'starter')
            WHERE u.username = %s{lock_clause}""",
        (username,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Compte indisponible")
    result = dict(row)
    result["offer_code"] = result["offer_code"] or "starter"
    result["effective_quota"] = result["monthly_quota"]
    return result


def _audit(conn, state: dict, feature: str, outcome: str, error_code: str = "") -> int:
    row = conn.execute(
        """INSERT INTO ai_usage_audit
           (user_id, username, client, feature, provider, model, offer_code, outcome, error_code)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            state["id"], state["username"], state.get("client") or "", feature,
            AI_PROVIDER, AI_MODEL_LABEL, state.get("offer_code") or "", outcome, error_code,
        ),
    ).fetchone()
    return int(row["id"])


def get_my_ai_governance(username: str) -> dict:
    with get_db() as conn:
        state = _governance_row(conn, username)
        used_row = conn.execute(
            "SELECT request_count FROM ai_monthly_usage WHERE user_id = %s AND period_start = %s",
            (state["id"], _month_start()),
        ).fetchone()
    used = int(used_row["request_count"]) if used_row else 0
    quota = state["effective_quota"]
    return {
        "provider": AI_PROVIDER,
        "model": AI_MODEL_LABEL,
        "consent_required": not (
            state["consented_at"] and state["consent_revoked_at"] is None
            and state["consent_version"] == AI_CONSENT_VERSION
        ),
        "ai_enabled": bool(state["ai_enabled"]),
        "offer_code": state["offer_code"],
        "monthly_quota": quota,
        "used_this_month": used,
        "remaining": None if quota is None else max(0, int(quota) - used),
        "data_location": _read_data_location(),
        "policy_version": AI_CONSENT_VERSION,
    }


def _read_data_location() -> str:
    with get_db() as conn:
        row = conn.execute("SELECT valeur FROM config_client WHERE cle = %s", ("ai_data_location",)).fetchone()
    return (row["valeur"] if row else "") or "À confirmer dans le contrat Google applicable"


def set_ai_consent(username: str, accepted: bool) -> dict:
    with get_db() as conn:
        state = _governance_row(conn, username, lock_user=True)
        if accepted:
            conn.execute(
                """INSERT INTO ai_user_entitlements(user_id, consent_version, consented_at, consent_revoked_at)
                   VALUES (%s, %s, CURRENT_TIMESTAMP, NULL)
                   ON CONFLICT (user_id) DO UPDATE SET
                     consent_version = EXCLUDED.consent_version,
                     consented_at = CURRENT_TIMESTAMP,
                     consent_revoked_at = NULL,
                     updated_at = CURRENT_TIMESTAMP""",
                (state["id"], AI_CONSENT_VERSION),
            )
            _audit(conn, state, "consent", "accepted")
        else:
            conn.execute(
                """INSERT INTO ai_user_entitlements(user_id, consent_revoked_at)
                   VALUES (%s, CURRENT_TIMESTAMP)
                   ON CONFLICT (user_id) DO UPDATE SET
                     consent_version = '', consented_at = NULL,
                     consent_revoked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP""",
                (state["id"],),
            )
            _audit(conn, state, "consent", "revoked")
    return get_my_ai_governance(username)


def reserve_ai_usage(username: str, feature: str) -> AiUsageReservation:
    """Atomically enforce consent and a monthly per-user quota before Gemini."""
    with get_db() as conn:
        state = _governance_row(conn, username, lock_user=True)
        if not state["ai_enabled"]:
            _audit(conn, state, feature, "denied", "ai_disabled")
            raise HTTPException(status_code=403, detail="L'accès IA est désactivé pour ce compte.")
        consent_valid = (
            state["consented_at"] and state["consent_revoked_at"] is None
            and state["consent_version"] == AI_CONSENT_VERSION
        )
        if not consent_valid:
            _audit(conn, state, feature, "denied", "consent_required")
            raise HTTPException(
                status_code=428,
                detail="Consentement IA requis avant l'envoi de données à Gemini.",
                headers={"X-SAVIA-AI-Consent": "required"},
            )

        quota = state["effective_quota"]
        period = _month_start()
        usage = conn.execute(
            "SELECT request_count FROM ai_monthly_usage WHERE user_id = %s AND period_start = %s",
            (state["id"], period),
        ).fetchone()
        used = int(usage["request_count"]) if usage else 0
        if quota is not None and used >= int(quota):
            _audit(conn, state, feature, "denied", "quota_exceeded")
            raise HTTPException(status_code=429, detail="Quota IA mensuel atteint pour ce compte.")
        conn.execute(
            """INSERT INTO ai_monthly_usage(user_id, period_start, request_count, updated_at)
               VALUES (%s, %s, 1, CURRENT_TIMESTAMP)
               ON CONFLICT (user_id, period_start) DO UPDATE SET
                 request_count = ai_monthly_usage.request_count + 1,
                 updated_at = CURRENT_TIMESTAMP""",
            (state["id"], period),
        )
        return AiUsageReservation(_audit(conn, state, feature, "started"))


def finish_ai_usage(reservation: AiUsageReservation, *, success: bool, error_code: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE ai_usage_audit SET outcome = %s, error_code = %s WHERE id = %s",
            ("success" if success else "failed", error_code[:80], reservation.audit_id),
        )


def governed_ai_endpoint(feature: str, roles: Iterable[str]) -> Callable:
    """Decorate an AI route with server-side role, consent, and quota controls."""
    allowed = set(roles)

    def decorator(fn: Callable) -> Callable:
        signature = inspect.signature(fn)

        @wraps(fn)
        def wrapped(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            user = bound.arguments.get("user")
            if not isinstance(user, dict) or user.get("role") not in allowed:
                raise HTTPException(status_code=403, detail="Accès IA non autorisé pour ce rôle.")
            reservation = reserve_ai_usage(str(user.get("sub") or ""), feature)
            try:
                result = fn(*args, **kwargs)
            except HTTPException as exc:
                finish_ai_usage(reservation, success=False, error_code=f"http_{exc.status_code}")
                raise
            except Exception:
                finish_ai_usage(reservation, success=False, error_code="internal_error")
                raise
            finish_ai_usage(reservation, success=True)
            if isinstance(result, dict):
                result.setdefault("ai_governance", {
                    "human_validation_required": True,
                    "notice": "Analyse indicative : validation humaine obligatoire avant toute décision.",
                })
            return result

        return wrapped

    return decorator


def get_admin_ai_governance() -> dict:
    with get_db() as conn:
        offers = [dict(row) for row in conn.execute(
            "SELECT code, label, monthly_quota, sort_order, active FROM ai_offers ORDER BY sort_order, code"
        ).fetchall()]
        users = [dict(row) for row in conn.execute(
            """SELECT u.id, u.username, u.nom_complet, u.role, u.actif,
                       COALESCE(e.ai_enabled, TRUE) AS ai_enabled,
                       e.consented_at, e.consent_revoked_at,
                       COALESCE(m.request_count, 0) AS used_this_month
                FROM utilisateurs u
                LEFT JOIN ai_user_entitlements e ON e.user_id = u.id
                LEFT JOIN ai_monthly_usage m ON m.user_id = u.id AND m.period_start = %s
                ORDER BY u.username""",
            (_month_start(),),
        ).fetchall()]
        usage = [dict(row) for row in conn.execute(
            """SELECT occurred_at, username, feature, provider, model, offer_code, outcome, error_code
                FROM ai_usage_audit ORDER BY id DESC LIMIT 100"""
        ).fetchall()]
    with get_db() as conn:
        active_offer = conn.execute(
            "SELECT valeur FROM config_client WHERE cle = 'ai_active_offer_code'"
        ).fetchone()
    return {
        "provider": AI_PROVIDER, "model": AI_MODEL_LABEL,
        "data_location": _read_data_location(),
        "active_offer_code": (active_offer["valeur"] if active_offer else "starter") or "starter",
        "offers": offers, "users": users, "usage": usage,
    }


def update_ai_offer(code: str, payload: dict) -> None:
    if code not in {"starter", "business", "enterprise"}:
        raise HTTPException(status_code=400, detail="Offre IA inconnue")
    quota = payload.get("monthly_quota")
    if quota in ("", None, "unlimited"):
        quota = None
    elif not isinstance(quota, int) or quota < 0:
        raise HTTPException(status_code=400, detail="Le quota doit être un nombre positif ou illimité")
    label = str(payload.get("label") or code.title()).strip()[:80]
    active = bool(payload.get("active", True))
    with get_db() as conn:
        conn.execute(
            """UPDATE ai_offers SET label = %s, monthly_quota = %s, active = %s,
               updated_at = CURRENT_TIMESTAMP WHERE code = %s""",
            (label, quota, active, code),
        )


def update_ai_user_entitlement(user_id: int, payload: dict) -> None:
    with get_db() as conn:
        exists = conn.execute("SELECT 1 FROM utilisateurs WHERE id = %s", (user_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        conn.execute(
            """INSERT INTO ai_user_entitlements(user_id, ai_enabled)
               VALUES (%s, %s)
               ON CONFLICT (user_id) DO UPDATE SET ai_enabled = EXCLUDED.ai_enabled,
                 updated_at = CURRENT_TIMESTAMP""",
            (user_id, bool(payload.get("ai_enabled", True))),
        )


def update_ai_active_offer(code: str) -> None:
    with get_db() as conn:
        offer = conn.execute("SELECT 1 FROM ai_offers WHERE code = %s AND active = TRUE", (code,)).fetchone()
        if not offer:
            raise HTTPException(status_code=404, detail="Offre IA active introuvable")
        conn.execute(
            """INSERT INTO config_client(cle, valeur) VALUES ('ai_active_offer_code', %s)
               ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur""",
            (code,),
        )


def update_ai_data_location(value: str) -> None:
    cleaned = str(value or "").strip()[:500]
    if not cleaned:
        raise HTTPException(status_code=400, detail="La localisation des données est requise")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO config_client(cle, valeur) VALUES ('ai_data_location', %s)
               ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur""",
            (cleaned,),
        )
