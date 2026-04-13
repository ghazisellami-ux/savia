# ==========================================
# 🚀 SAVIA FastAPI Backend
# ==========================================
"""
FastAPI backend for the SAVIA Next.js frontend.
Replaces Flask api_server.py with modern async endpoints.
"""
import math
import os
import jwt
import bcrypt
import logging
import auth
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Query, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from db_engine import (
    init_db, get_db, read_sql,
    lire_equipements, ajouter_equipement, modifier_equipement, supprimer_equipement,
    lire_interventions, ajouter_intervention, update_intervention_statut, cloturer_intervention,
    lire_pieces, ajouter_piece, modifier_piece, supprimer_piece,
    lire_demandes_intervention,
    lire_contrats, ajouter_contrat, modifier_contrat, supprimer_contrat,
    lire_conformite, ajouter_conformite, supprimer_conformite,
    lire_planning, ajouter_planning, update_planning_statut, supprimer_planning,
    lire_techniciens, ajouter_technicien, update_technicien, supprimer_technicien,
    lire_base,
    lire_audit, log_audit,
    get_config, set_config,
    lire_notifications_pieces, compter_notifications_non_lues,
)

logger = logging.getLogger("savia-api")
logging.basicConfig(level=logging.INFO)

# ---- Config ----
JWT_SECRET = os.getenv("JWT_SECRET", "sic-terrain-secret-2026")
JWT_EXPIRY_HOURS = 72
security = HTTPBearer(auto_error=False)

# ---- App ----
app = FastAPI(
    title="SAVIA API",
    description="Backend API for SAVIA — Superviseur Intelligent Clinique",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    auth.creer_admin_defaut()
    logger.info("✅ SAVIA FastAPI started — DB initialized")


# ==========================================
# HELPERS
# ==========================================

def _df_to_records(df) -> list:
    """Convert DataFrame to JSON-safe list of dicts."""
    if df is None or df.empty:
        return []
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
            elif hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
    return records


def _verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT and return user payload. Returns guest user if no token (allows public read)."""
    if not credentials:
        return {"sub": "guest", "role": "Lecteur", "nom": "Visiteur"}
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")


def _optional_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    """Verify JWT if present, return None if missing (allows public read access)."""
    if not credentials:
        return None
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ==========================================
# AUTH
# ==========================================

class LoginRequest(BaseModel):
    username: str
    password: str


@app.get("/")
def root():
    return {"status": "ok", "service": "SAVIA API", "version": "2.0.0"}


@app.post("/api/auth/login")
def login(body: LoginRequest):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM utilisateurs WHERE username = ? AND actif = 1",
            (body.username,)
        ).fetchone()

    if not row or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    user_data = dict(row)
    payload = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "nom": user_data.get("nom_complet", ""),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    return {
        "token": token,
        "user": {
            "username": user_data["username"],
            "nom": user_data.get("nom_complet", ""),
            "role": user_data["role"],
        }
    }


@app.get("/api/auth/me")
def me(user: dict = Depends(_verify_token)):
    return {"user": user}


# ==========================================
# DASHBOARD — Aggregated KPIs
# ==========================================

@app.get("/api/dashboard/kpis")
def get_dashboard_kpis(user: dict = Depends(_verify_token)):
    """Compute real KPIs from the database."""
    try:
        df_eq = lire_equipements()
        df_int = lire_interventions()

        nb_eq = len(df_eq) if not df_eq.empty else 0
        nb_critiques = 0
        if not df_eq.empty and "Statut" in df_eq.columns:
            nb_critiques = len(df_eq[df_eq["Statut"].isin(["Hors Service", "Critique"])])

        nb_interventions = len(df_int) if not df_int.empty else 0
        cout_total = 0.0
        mttr = 0.0
        if not df_int.empty:
            if "cout" in df_int.columns:
                cout_total = float(df_int["cout"].sum()) if df_int["cout"].notna().any() else 0
            if "duree_minutes" in df_int.columns:
                durees = df_int["duree_minutes"].dropna()
                mttr = round(float(durees.mean()) / 60, 1) if len(durees) > 0 else 0

        # Disponibilité = % équipements opérationnels
        dispo = 100.0
        if not df_eq.empty and "Statut" in df_eq.columns:
            op = len(df_eq[~df_eq["Statut"].isin(["Hors Service", "Critique"])])
            dispo = round((op / nb_eq) * 100, 1) if nb_eq > 0 else 100

        # MTBF approximation
        mtbf = 720  # default
        if nb_interventions > 0 and nb_eq > 0:
            mtbf = round((nb_eq * 30 * 24) / max(nb_interventions, 1))

        return {
            "nb_equipements": nb_eq,
            "nb_critiques": nb_critiques,
            "disponibilite": dispo,
            "mtbf": mtbf,
            "mttr": mttr,
            "cout_total": round(cout_total, 2),
            "nb_interventions": nb_interventions,
        }
    except Exception as e:
        logger.error(f"Dashboard KPIs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/health-scores")
def get_health_scores(user: dict = Depends(_verify_token)):
    """Compute health scores per equipment based on intervention history."""
    try:
        df_eq = lire_equipements()
        df_int = lire_interventions()
        scores = []

        if df_eq.empty:
            return []

        for _, eq in df_eq.iterrows():
            nom = eq.get("Nom", "")
            pannes = 0
            if not df_int.empty and "machine" in df_int.columns:
                pannes = len(df_int[df_int["machine"] == nom])
            # Simple scoring: 100 - (pannes * 8), min 5
            score = max(5, 100 - pannes * 8)
            tendance = "stable"
            if pannes > 4:
                tendance = "baisse"
            elif pannes == 0:
                tendance = "hausse"
            scores.append({
                "machine": nom,
                "score": score,
                "tendance": tendance,
                "pannes": pannes,
                "client": eq.get("Client", ""),
            })

        return sorted(scores, key=lambda x: x["score"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ÉQUIPEMENTS
# ==========================================

@app.get("/api/equipements")
def get_equipements(user: dict = Depends(_verify_token)):
    return _df_to_records(lire_equipements())


@app.post("/api/equipements")
def create_equipement(body: dict, user: dict = Depends(_verify_token)):
    ajouter_equipement(body)
    return {"ok": True}


@app.put("/api/equipements/{equip_id}")
def update_equipement(equip_id: int, body: dict, user: dict = Depends(_verify_token)):
    modifier_equipement(equip_id, body)
    return {"ok": True}


@app.delete("/api/equipements/{equip_id}")
def delete_equipement(equip_id: int, user: dict = Depends(_verify_token)):
    supprimer_equipement(equip_id)
    return {"ok": True}


# ==========================================
# INTERVENTIONS / SAV
# ==========================================

@app.get("/api/interventions")
def get_interventions(
    machine: Optional[str] = None,
    technicien: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    df = lire_interventions(machine=machine)
    if technicien and not df.empty and "technicien" in df.columns:
        words = technicien.lower().split()
        df = df[df["technicien"].astype(str).apply(
            lambda t: all(w in t.lower() for w in words)
        )]
    return _df_to_records(df)


@app.post("/api/interventions")
def create_intervention(body: dict, user: dict = Depends(_verify_token)):
    ajouter_intervention(body)
    return {"ok": True}


@app.put("/api/interventions/{intervention_id}")
def update_intervention(intervention_id: int, body: dict, user: dict = Depends(_verify_token)):
    new_statut = body.get("statut")
    if new_statut and "tur" in new_statut.lower():
        ok, msg = cloturer_intervention(
            intervention_id,
            body.get("probleme", ""),
            body.get("cause", ""),
            body.get("solution", ""),
            pieces_a_deduire=body.get("pieces_a_deduire", []),
            duree_minutes=body.get("duree_minutes", 0),
        )
        return {"ok": ok, "message": msg}
    if new_statut:
        update_intervention_statut(intervention_id, new_statut)
    # Update other fields
    fields = []
    params = []
    for f in ["probleme", "cause", "solution", "pieces_utilisees", "cout",
              "duree_minutes", "description", "notes", "type_erreur", "priorite"]:
        if f in body:
            fields.append(f"{f} = ?")
            params.append(body[f])
    if fields:
        params.append(intervention_id)
        with get_db() as conn:
            conn.execute(f"UPDATE interventions SET {', '.join(fields)} WHERE id = ?", params)
    return {"ok": True}


# ==========================================
# DEMANDES D'INTERVENTION
# ==========================================

@app.get("/api/demandes")
def get_demandes(
    statuts: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    df = lire_demandes_intervention()
    if statuts and not df.empty and "statut" in df.columns:
        lst = [s.strip() for s in statuts.split(",")]
        df = df[df["statut"].isin(lst)]
    return _df_to_records(df)


# ==========================================
# PIÈCES DE RECHANGE
# ==========================================

@app.get("/api/pieces")
def get_pieces(user: dict = Depends(_verify_token)):
    return _df_to_records(lire_pieces())


@app.post("/api/pieces")
def create_piece(body: dict, user: dict = Depends(_verify_token)):
    ajouter_piece(body)
    return {"ok": True}


@app.put("/api/pieces/{piece_id}")
def update_piece(piece_id: int, body: dict, user: dict = Depends(_verify_token)):
    modifier_piece(piece_id, body)
    return {"ok": True}


@app.delete("/api/pieces/{piece_id}")
def delete_piece(piece_id: int, user: dict = Depends(_verify_token)):
    supprimer_piece(piece_id)
    return {"ok": True}


# ==========================================
# CONTRATS
# ==========================================

@app.get("/api/contrats")
def get_contrats(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    return _df_to_records(lire_contrats(client=client))


@app.post("/api/contrats")
def create_contrat(body: dict, user: dict = Depends(_verify_token)):
    ajouter_contrat(body)
    return {"ok": True}


@app.put("/api/contrats/{contrat_id}")
def update_contrat(contrat_id: int, body: dict, user: dict = Depends(_verify_token)):
    modifier_contrat(contrat_id, body)
    return {"ok": True}


@app.delete("/api/contrats/{contrat_id}")
def delete_contrat(contrat_id: int, user: dict = Depends(_verify_token)):
    supprimer_contrat(contrat_id)
    return {"ok": True}


# ==========================================
# CONFORMITÉ
# ==========================================

@app.get("/api/conformite")
def get_conformite(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    return _df_to_records(lire_conformite(client=client))


@app.post("/api/conformite")
def create_conformite(body: dict, user: dict = Depends(_verify_token)):
    ajouter_conformite(body)
    return {"ok": True}


@app.delete("/api/conformite/{conformite_id}")
def delete_conformite(conformite_id: int, user: dict = Depends(_verify_token)):
    supprimer_conformite(conformite_id)
    return {"ok": True}


# ==========================================
# PLANNING
# ==========================================

@app.get("/api/planning")
def get_planning(
    machine: Optional[str] = None,
    statut: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    return _df_to_records(lire_planning(machine=machine, statut=statut))


@app.post("/api/planning")
def create_planning(body: dict, user: dict = Depends(_verify_token)):
    ajouter_planning(body)
    return {"ok": True}


@app.put("/api/planning/{planning_id}")
def update_planning_status(planning_id: int, body: dict, user: dict = Depends(_verify_token)):
    update_planning_statut(planning_id, body.get("statut", ""), body.get("date_realisee"))
    return {"ok": True}


@app.delete("/api/planning/{planning_id}")
def delete_planning(planning_id: int, user: dict = Depends(_verify_token)):
    supprimer_planning(planning_id)
    return {"ok": True}


# ==========================================
# KNOWLEDGE BASE
# ==========================================

@app.get("/api/knowledge")
def get_knowledge(user: dict = Depends(_verify_token)):
    """Return error codes + solutions merged."""
    hex_db, sol_db = lire_base()
    results = []
    for code, info in hex_db.items():
        sol = sol_db.get(code, {})
        results.append({
            "code": code,
            "message": info.get("Msg", ""),
            "level": info.get("Level", ""),
            "type": info.get("Type", ""),
            "cause": sol.get("Cause", ""),
            "solution": sol.get("Solution", ""),
            "priorite": sol.get("Priorité", ""),
        })
    return results


# ==========================================
# TECHNICIENS
# ==========================================

@app.get("/api/techniciens")
def get_techniciens(user: dict = Depends(_verify_token)):
    return _df_to_records(lire_techniciens())


@app.post("/api/techniciens")
def create_technicien(body: dict, user: dict = Depends(_verify_token)):
    ajouter_technicien(body)
    return {"ok": True}


@app.put("/api/techniciens/{tech_id}")
def modifier_techniciens_route(tech_id: int, body: dict, user: dict = Depends(_verify_token)):
    update_technicien(tech_id, body)
    return {"ok": True}


@app.delete("/api/techniciens/{tech_id}")
def delete_technicien(tech_id: int, user: dict = Depends(_verify_token)):
    supprimer_technicien(tech_id)
    return {"ok": True}


# ==========================================
# AI INTEGRATION
# ==========================================

@app.post("/api/ai/analyze-performance")
def analyze_performance(body: dict, user: dict = Depends(_verify_token)):
    """Calls Gemini to analyze an array of KPI metrics or intervention data."""
    # Lazy load ai_engine to avoid loading issues if no API Key
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible. (Vérifiez GOOGLE_API_KEY).")

    kpis = body.get("kpis", {})
    sym = body.get("sym", "EUR")

    tech_detail = ""
    for ts in kpis.get("tech_stats", []):
        tech_detail += (
            f"  - {ts.get('nom', '?')}: {ts.get('nb_interventions', 0)} int, "
            f"{ts.get('taux_resolution', 0)}% res, MTTR={ts.get('mttr_h', 0)}h, "
            f"cout={ts.get('cout_total', 0)}\n"
        )

    prompt = f"""Agis en tant que Directeur du Service Technique pour une entreprise d'équipements d'imagerie médicale.
Ton rôle est d'analyser ces métriques d'équipe pour le mois en cours.

KPIs de l'équipe :
- Interventions totales : {kpis.get('nb_total', 0)}
- Taux de résolution : {kpis.get('taux_resolution', 0)}%
- MTTR : {kpis.get('mttr_h', 0)}h
- Coût moyen : {kpis.get('cout_moyen', 0)} {sym}
- Coût total : {kpis.get('cout_total', 0)} {sym}
- Ratio correctif : {kpis.get('ratio_correctif_pct', 0)}%
- Score global : {kpis.get('score_global', 0)}/100

Performance par technicien :
{tech_detail if tech_detail else 'Aucune donnée par technicien'}

Donne-moi un rapport exécutif exigeant et constructif. Réponds en JSON avec cette structure EXACTE :
{{
  "analyse": "Résumé exécutif",
  "points_forts": ["pt1", "pt2"],
  "points_faibles": ["pt1", "pt2"],
  "recommandations": [
    {{
      "titre": "Directives",
      "description": "Action précise",
      "impact": "HAUT"
    }}
  ],
  "objectifs": ["objectif 1", "objectif 2"]
}}"""

    raw = _call_ia(prompt, timeout=60, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
        
    result = clean_json_response(raw)
    return {"ok": True, "result": result}


# ==========================================
# ADMIN — Utilisateurs
# ==========================================

@app.get("/api/admin/users")
def get_users(user: dict = Depends(_verify_token)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, nom_complet, role, client, actif, created_at, last_login FROM utilisateurs ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/users")
def create_user(body: dict, user: dict = Depends(_verify_token)):
    hashed = bcrypt.hashpw(body["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO utilisateurs (username, password_hash, nom_complet, role, client, actif) VALUES (?, ?, ?, ?, ?, 1)",
            (body["username"], hashed, body.get("nom_complet", ""), body.get("role", "Lecteur"), body.get("client", ""))
        )
    return {"ok": True}


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: int, body: dict, user: dict = Depends(_verify_token)):
    fields = []
    params = []
    for f in ["nom_complet", "role", "client", "actif"]:
        if f in body:
            fields.append(f"{f} = ?")
            params.append(body[f])
    if "password" in body and body["password"]:
        fields.append("password_hash = ?")
        params.append(bcrypt.hashpw(body["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8"))
    if fields:
        params.append(user_id)
        with get_db() as conn:
            conn.execute(f"UPDATE utilisateurs SET {', '.join(fields)} WHERE id = ?", params)
    return {"ok": True}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, user: dict = Depends(_verify_token)):
    with get_db() as conn:
        conn.execute("DELETE FROM utilisateurs WHERE id = ?", (user_id,))
    return {"ok": True}


# ==========================================
# AUDIT LOG
# ==========================================

@app.get("/api/audit")
def get_audit_log(limit: int = 100, user: dict = Depends(_verify_token)):
    return _df_to_records(lire_audit(limit=limit))


# ==========================================
# NOTIFICATIONS
# ==========================================

@app.get("/api/notifications")
def get_notifications(
    destination: Optional[str] = "radiologie",
    user: dict = Depends(_verify_token),
):
    return _df_to_records(lire_notifications_pieces(destination=destination))


@app.get("/api/notifications/count")
def get_notification_count(
    destination: str = "radiologie",
    user: dict = Depends(_verify_token),
):
    return {"count": compter_notifications_non_lues(destination)}


# ==========================================
# SETTINGS / CONFIG
# ==========================================

@app.get("/api/settings")
def get_settings(user: dict = Depends(_verify_token)):
    keys = [
        "nom_organisation", "logo_path", "langue", "theme",
        "taux_horaire_technicien", "telegram_token", "telegram_chat_id",
        "gemini_api_key",
    ]
    result = {}
    for k in keys:
        result[k] = get_config(k, "")
    return result


@app.put("/api/settings")
def update_settings(body: dict, user: dict = Depends(_verify_token)):
    for k, v in body.items():
        set_config(k, str(v))
    return {"ok": True}


# ==========================================
# CLIENTS (derived from equipements)
# ==========================================

@app.get("/api/clients")
def get_clients(user: dict = Depends(_verify_token)):
    """Derive client list from equipements + contrats + interventions."""
    df_eq = lire_equipements()
    df_int = lire_interventions()
    df_contrats = lire_contrats()

    clients = {}
    if not df_eq.empty and "Client" in df_eq.columns:
        for client_name in df_eq["Client"].unique():
            if not client_name:
                continue
            eq_client = df_eq[df_eq["Client"] == client_name]
            nb_eq = len(eq_client)
            # Health score
            nb_hs = len(eq_client[eq_client["Statut"].isin(["Hors Service", "Critique"])]) if "Statut" in eq_client.columns else 0
            score = max(0, round(((nb_eq - nb_hs) / nb_eq) * 100)) if nb_eq > 0 else 100
            # Interventions count
            nb_int = 0
            if not df_int.empty and "machine" in df_int.columns:
                machines = eq_client["Nom"].tolist() if "Nom" in eq_client.columns else []
                nb_int = len(df_int[df_int["machine"].isin(machines)])
            # Active contracts
            nb_contrats = 0
            if not df_contrats.empty and "client" in df_contrats.columns:
                nb_contrats = len(df_contrats[df_contrats["client"] == client_name])

            clients[client_name] = {
                "nom": client_name,
                "nb_equipements": nb_eq,
                "nb_interventions": nb_int,
                "nb_contrats": nb_contrats,
                "score_sante": score,
            }

    return list(clients.values())


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
