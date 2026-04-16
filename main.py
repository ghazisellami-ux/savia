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
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Query, Header, status, UploadFile, File
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
def get_dashboard_kpis(
    client: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compute real KPIs from the database, optionally filtered by client and date range."""
    try:
        df_eq = lire_equipements()
        df_int = lire_interventions()

        # Filter equipements by client
        if client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"] == client]

        # Filter interventions by client (via matching machines)
        if client and not df_eq.empty and not df_int.empty and "machine" in df_int.columns:
            machines_client = df_eq["Nom"].tolist() if "Nom" in df_eq.columns else []
            df_int = df_int[df_int["machine"].isin(machines_client)]

        # Filter interventions by date range
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
            if date_start:
                df_int = df_int[df_int["date"] >= pd.to_datetime(date_start)]
            if date_end:
                df_int = df_int[df_int["date"] <= pd.to_datetime(date_end)]

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
def get_health_scores(
    client: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compute health scores per equipment based on intervention history."""
    try:
        df_eq = lire_equipements()
        df_int = lire_interventions()

        # Filter equipements by client
        if client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"] == client]

        # Filter interventions by date range
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
            if date_start:
                df_int = df_int[df_int["date"] >= pd.to_datetime(date_start)]
            if date_end:
                df_int = df_int[df_int["date"] <= pd.to_datetime(date_end)]

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
    # Return the ID of the created/upserted equipment
    nom = body.get("Nom", "")
    client = body.get("Client", "Centre Principal")
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM equipements WHERE nom = ? AND client = ?",
            (nom, client)
        ).fetchone()
    equip_id = dict(row)["id"] if row else None
    return {"ok": True, "id": equip_id}


@app.put("/api/equipements/{equip_id}")
def update_equipement(equip_id: int, body: dict, user: dict = Depends(_verify_token)):
    modifier_equipement(equip_id, body)
    return {"ok": True}


@app.delete("/api/equipements/{equip_id}")
def delete_equipement(equip_id: int, user: dict = Depends(_verify_token)):
    supprimer_equipement(equip_id)
    return {"ok": True}


# ==========================================
# DOCUMENTS TECHNIQUES
# ==========================================

@app.post("/api/documents-techniques/upload")
def upload_document(body: dict, user: dict = Depends(_verify_token)):
    """Upload a technical document (base64 encoded) for an equipment."""
    from db_engine import ajouter_document_technique
    equip_id = body.get("equipement_id")
    nom_fichier = body.get("nom_fichier", "")
    contenu_base64 = body.get("contenu_base64", "")
    if not equip_id or not nom_fichier or not contenu_base64:
        raise HTTPException(status_code=400, detail="equipement_id, nom_fichier et contenu_base64 requis")
    ajouter_document_technique(equip_id, nom_fichier, contenu_base64)
    return {"ok": True}


@app.get("/api/documents-techniques")
def get_all_documents(user: dict = Depends(_verify_token)):
    """List all technical documents with associated equipment info."""
    from db_engine import lire_tous_documents_techniques
    return lire_tous_documents_techniques()


@app.get("/api/documents-techniques/{equip_id}")
def get_documents_by_equipment(equip_id: int, user: dict = Depends(_verify_token)):
    """List technical documents for a specific equipment."""
    from db_engine import lire_documents_techniques
    return lire_documents_techniques(equip_id)


@app.get("/api/documents-techniques/download/{doc_id}")
def download_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Download a specific technical document (returns base64 content)."""
    from db_engine import lire_document_technique_contenu
    doc = lire_document_technique_contenu(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")
    return doc


@app.delete("/api/documents-techniques/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Delete a technical document."""
    from db_engine import supprimer_document_technique
    supprimer_document_technique(doc_id)
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


@app.post("/api/demandes")
def create_demande(body: dict, user: dict = Depends(_verify_token)):
    from db_engine import get_db
    with get_db() as conn:
        conn.execute("""
            INSERT INTO demandes_intervention
              (date_demande, demandeur, client, equipement, urgence,
               description, code_erreur, contact_nom, contact_tel, statut)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            body.get("date_demande") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            body.get("demandeur") or "",
            body.get("client") or "",
            body.get("equipement") or "",
            body.get("urgence") or "Moyenne",
            body.get("description") or "",
            body.get("code_erreur") or "",
            body.get("contact_nom") or "",
            body.get("contact_tel") or "",
            body.get("statut") or "En attente",
        ))
    return {"success": True}


@app.put("/api/demandes/{demande_id}/statut")
def update_demande_statut(demande_id: int, body: dict, user: dict = Depends(_verify_token)):
    from db_engine import get_db
    with get_db() as conn:
        conn.execute("""
            UPDATE demandes_intervention
            SET statut = %s, technicien_assigne = %s, notes_traitement = %s,
                date_traitement = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            body.get("statut") or "En cours",
            body.get("technicien_assigne") or "",
            body.get("notes_traitement") or "",
            demande_id,
        ))
    return {"success": True}


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


def _parse_text_to_rows(text: str) -> list:
    """Parse unstructured text (from PDF/Word) into error code rows using AI or regex."""
    import re
    rows = []

    # Try AI extraction first
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        if AI_AVAILABLE and len(text) > 50:
            prompt = f"""Extrais les codes d'erreur de ce texte technique. 
Pour chaque code trouvé, donne: code, message, type (Hardware/Software/Network), cause, solution, priorite (HAUTE/MOYENNE/BASSE).
Texte (extrait): {text[:4000]}

Réponds en JSON: [{{"code":"ERR001","message":"...","type":"Hardware","cause":"...","solution":"...","priorite":"MOYENNE"}}]"""
            raw = _call_ia(prompt, timeout=30, is_json=True)
            if raw:
                result = clean_json_response(raw)
                if isinstance(result, list) and len(result) > 0:
                    return result
    except Exception:
        pass

    # Fallback: regex-based extraction
    # Common patterns: "ERR-001", "E001", "0x1234", "ERROR 001"
    patterns = [
        r'((?:ERR|ERROR|E|WARN|W|FAULT|F|CODE)[_\-\s]?\d{2,5})',
        r'(0x[0-9A-Fa-f]{4,8})',
        r'((?:H|S|N)\d{4})',
    ]
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            code = match.group(1).strip()
            # Get surrounding context (100 chars)
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 200)
            context = text[start:end].replace('\n', ' ').strip()
            if code not in [r.get('code') for r in rows]:
                rows.append({
                    "code": code,
                    "message": context[:120],
                    "type": "Hardware",
                    "cause": "",
                    "solution": "",
                    "priorite": "MOYENNE",
                })

    if not rows:
        # If no codes found, store the document text as a single entry
        lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 10]
        for i, line in enumerate(lines[:50]):
            rows.append({
                "code": f"DOC-{i+1:03d}",
                "message": line[:200],
                "type": "Documentation",
                "cause": "",
                "solution": "",
                "priorite": "BASSE",
            })

    return rows


@app.post("/api/knowledge/import")
async def import_knowledge(file: UploadFile = File(...), user: dict = Depends(_verify_token)):
    """Import error codes from an uploaded Excel/CSV file."""
    import io
    filename = file.filename or ""
    content = await file.read()

    try:
        if filename.endswith(".csv"):
            import csv
            text = content.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        elif filename.endswith((".xlsx", ".xls")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active
            headers = [str(c.value or "").strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]
            rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                rows.append({headers[i]: (str(v) if v else "") for i, v in enumerate(row) if i < len(headers)})
        elif filename.endswith(".pdf"):
            # Parse PDF text using PyMuPDF (fitz)
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                full_text = "\n".join(page.get_text() for page in doc)
            except Exception:
                full_text = content.decode("utf-8", errors="replace")
            rows = _parse_text_to_rows(full_text)
        elif filename.endswith((".docx", ".doc")):
            # Parse Word text
            try:
                import docx
                doc = docx.Document(io.BytesIO(content))
                full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                # Also check tables
                for table in doc.tables:
                    for row in table.rows:
                        full_text += "\n" + " | ".join(cell.text for cell in row.cells)
            except Exception:
                full_text = content.decode("utf-8", errors="replace")
            rows = _parse_text_to_rows(full_text)
        else:
            raise HTTPException(status_code=400, detail="Format non supporté. Utilisez CSV, XLSX, PDF ou DOCX.")

        # Auto-detect column mapping
        col_map = {}
        for h in (rows[0].keys() if rows else []):
            hl = h.lower().strip()
            if "code" in hl: col_map["code"] = h
            elif "message" in hl or "msg" in hl: col_map["message"] = h
            elif "type" in hl: col_map["type"] = h
            elif "cause" in hl: col_map["cause"] = h
            elif "solution" in hl: col_map["solution"] = h
            elif "priorit" in hl: col_map["priorite"] = h

        if "code" not in col_map:
            raise HTTPException(status_code=400, detail="Colonne 'Code' non trouvée dans le fichier.")

        imported = 0
        with get_db() as conn:
            for row in rows:
                code = row.get(col_map.get("code", ""), "").strip()
                if not code:
                    continue
                msg = row.get(col_map.get("message", ""), "")
                typ = row.get(col_map.get("type", ""), "Hardware")
                cause = row.get(col_map.get("cause", ""), "")
                solution = row.get(col_map.get("solution", ""), "")
                priorite = row.get(col_map.get("priorite", ""), "MOYENNE")

                # Insert or update codes_erreurs
                conn.execute(
                    "INSERT INTO codes_erreurs (code, message, type) VALUES (%s, %s, %s) "
                    "ON CONFLICT (code) DO UPDATE SET message=EXCLUDED.message, type=EXCLUDED.type",
                    (code, msg, typ)
                )
                # Insert or update solutions
                conn.execute(
                    "INSERT INTO solutions (code, cause, solution, priorite) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (code) DO UPDATE SET cause=EXCLUDED.cause, solution=EXCLUDED.solution, priorite=EXCLUDED.priorite",
                    (code, cause, solution, priorite)
                )
                imported += 1

        return {"ok": True, "imported": imported, "message": f"{imported} codes importés avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'import: {str(e)}")


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
# LOGS UPLOAD (Supervision) — S3/MinIO + PostgreSQL
# ==========================================

@app.post("/api/logs/upload")
def upload_log(body: dict, user: dict = Depends(_verify_token)):
    """Upload un fichier log : contenu vers S3/MinIO, métadonnées vers PostgreSQL."""
    import hashlib
    equipement = body.get("equipement", "")
    filename = body.get("filename", "unknown.log")
    content = body.get("content", "")
    nb_errors = body.get("nb_errors", 0)
    nb_critiques = body.get("nb_critiques", 0)

    if not equipement or not content:
        raise HTTPException(status_code=400, detail="Équipement et contenu requis")

    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    username = user.get("sub", "system") if user else "system"

    try:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM logs_uploaded WHERE content_hash = ? AND equipement = ?",
                (content_hash, equipement)
            ).fetchone()
            if existing:
                eid = existing.get("id") if isinstance(existing, dict) else existing[0]
                return {"ok": True, "message": "Ce log a déjà été enregistré", "id": eid, "duplicate": True}

            # Upload contenu vers S3/MinIO
            s3_key = ""
            size_bytes = len(content.encode('utf-8'))
            try:
                from s3_storage import upload_file as s3_upload
                s3_result = s3_upload(content, filename, equipement, {
                    "nb_errors": str(nb_errors), "uploaded_by": username,
                })
                if s3_result:
                    s3_key = s3_result["s3_key"]
                    size_bytes = s3_result["size_bytes"]
            except Exception as s3_err:
                logger.warning(f"S3 upload failed (non-blocking): {s3_err}")

            # Métadonnées en PostgreSQL
            cursor = conn.execute(
                """INSERT INTO logs_uploaded (equipement, filename, s3_key, content_hash, size_bytes, nb_errors, nb_critiques, uploaded_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (equipement, filename, s3_key, content_hash, size_bytes, nb_errors, nb_critiques, username)
            )
            conn.execute(
                "INSERT INTO audit_log (username, action, details) VALUES (?, ?, ?)",
                (username, "Upload Log", f"Log '{filename}' S3:{s3_key or 'N/A'} ({nb_errors} erreurs)")
            )
            return {"ok": True, "id": cursor.lastrowid, "s3_key": s3_key,
                    "message": f"Log enregistré — {size_bytes} octets, {nb_errors} erreur(s), S3: {'ok' if s3_key else 'fallback'}"}
    except Exception as e:
        logger.error(f"Log upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
def list_logs(equipement: str = None, user: dict = Depends(_verify_token)):
    """Liste les logs uploadés (métadonnées depuis PostgreSQL)."""
    try:
        with get_db() as conn:
            if equipement:
                rows = conn.execute(
                    "SELECT id, equipement, filename, s3_key, size_bytes, nb_errors, nb_critiques, uploaded_by, uploaded_at FROM logs_uploaded WHERE equipement = ? ORDER BY uploaded_at DESC",
                    (equipement,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, equipement, filename, s3_key, size_bytes, nb_errors, nb_critiques, uploaded_by, uploaded_at FROM logs_uploaded ORDER BY uploaded_at DESC"
                ).fetchall()
            def _row(r):
                if isinstance(r, dict):
                    return {"id": r.get("id"), "equipement": r.get("equipement"), "filename": r.get("filename"), "s3_key": r.get("s3_key"), "size_bytes": r.get("size_bytes"), "nb_errors": r.get("nb_errors"), "nb_critiques": r.get("nb_critiques"), "uploaded_by": r.get("uploaded_by"), "uploaded_at": str(r.get("uploaded_at", ""))}
                return {"id": r[0], "equipement": r[1], "filename": r[2], "s3_key": r[3], "size_bytes": r[4], "nb_errors": r[5], "nb_critiques": r[6], "uploaded_by": r[7], "uploaded_at": str(r[8])}
            return [_row(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs/{log_id}")
def get_log(log_id: int, user: dict = Depends(_verify_token)):
    """Récupère le contenu d'un log depuis S3/MinIO."""
    try:
        with get_db() as conn:
            row = conn.execute("SELECT s3_key, equipement, filename FROM logs_uploaded WHERE id = ?", (log_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Log non trouvé")
            # Support both dict (PG) and tuple (SQLite) rows
            if isinstance(row, dict):
                s3_key = row.get("s3_key", "")
                equipement = row.get("equipement", "")
                filename = row.get("filename", "")
            else:
                s3_key, equipement, filename = row[0], row[1], row[2]
            if not s3_key:
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": ""}
            try:
                from s3_storage import download_file
                content = download_file(s3_key)
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": content or "", "s3_key": s3_key}
            except Exception:
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": ""}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# AI INTEGRATION
# ==========================================

@app.post("/api/ai/analyze-diagnostic")
def analyze_diagnostic(body: dict, user: dict = Depends(_verify_token)):
    """Calls Gemini to diagnose a machine error code and log contexts."""
    try:
        from ai_engine import get_ai_suggestion, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible. (Vérifiez GOOGLE_API_KEY).")

    machine = body.get("machine", "Équipement inconnu")
    code_erreur = body.get("code_erreur", "")
    message_erreur = body.get("message_erreur", "")
    log_context = body.get("log_context", "")

    try:
        result = get_ai_suggestion(code_erreur, message_erreur, machine, log_context=log_context)
        import json
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except:
                return {"ok": True, "result": result}
        
        if result and isinstance(result, dict):
            # Map uppercase keys from ai_engine to lowercase keys expected by frontend
            return {"ok": True, "result": {
                "probleme": result.get("Probleme", result.get("probleme", "Non identifié")),
                "cause": result.get("Cause", result.get("cause", "À déterminer")),
                "solution": result.get("Solution", result.get("solution", "Analyse manuelle requise")),
                "prevention": result.get("Prevention", result.get("prevention", "Maintenance préventive recommandée")),
                "urgence": result.get("Urgence", result.get("urgence", "À évaluer")),
                "type": result.get("Type", result.get("type", "?")),
                "priorite": result.get("Priorite", result.get("priorite", "MOYENNE")),
                "confidence": result.get("Confidence_Score", result.get("confidence", 0)),
            }}
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostic IA échoué: {e}")

@app.post("/api/ai/analyze-performance")
def analyze_performance(body: dict, user: dict = Depends(_verify_token)):
    """Calls Gemini to produce a detailed predictive maintenance report (v2)."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    kpis = body.get("kpis", {})
    sym = body.get("sym", "TND")

    # --- Fetch real per-machine data from DB ---
    machine_details = ""
    equip_detail = ""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT machine, COUNT(*) as nb, "
                "SUM(CASE WHEN type_intervention='Corrective' THEN 1 ELSE 0 END) as corr, "
                "SUM(CASE WHEN type_intervention ILIKE '%%r\u00e9ventive%%' THEN 1 ELSE 0 END) as prev, "
                "ROUND(AVG(duree_minutes)::numeric,1) as mttr_m, "
                "ROUND(SUM(cout)::numeric,0) as cout "
                "FROM interventions GROUP BY machine ORDER BY nb DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                machine_details += f"  - {r['machine']}: {r['nb']} int ({r['corr']} corr, {r['prev']} prev), MTTR={r['mttr_m']}min, co\u00fbt={r['cout']} {sym}\n"
            eqs = conn.execute('SELECT "Nom","Client","Type","Statut","DateInstallation" FROM equipements ORDER BY "Nom" LIMIT 25').fetchall()
            for eq in eqs:
                equip_detail += f"  - {eq['Nom']} ({eq.get('Type','?')}) — {eq.get('Client','?')}, install\u00e9: {eq.get('DateInstallation','?')}, statut: {eq.get('Statut','?')}\n"
    except Exception as db_err:
        logger.warning(f"DB fetch for AI failed: {db_err}")

    risk_detail = ""
    for r in kpis.get("top_risques", []):
        risk_detail += f"  - {r.get('machine','?')}: risque={r.get('risque_panne_pct',0)}%, pi\u00e8ce={r.get('composant_a_risque','?')}, panne_dans={r.get('jours_avant_panne','?')}j, sant\u00e9={r.get('score_sante',0)}%\n"

    import datetime
    today = datetime.date.today()

    prompt = f"""Tu es Directeur du Service Technique d'une entreprise de maintenance d'\u00e9quipements d'imagerie m\u00e9dicale en Tunisie.
Analyse ces donn\u00e9es R\u00c9ELLES et produis un rapport pr\u00e9dictif d\u00e9taill\u00e9.

=== CHIFFRES DU PARC ===
- \u00c9quipements : {kpis.get('nb_equipements', 0)} | Interventions : {kpis.get('nb_interventions', 0)}
- Correctives : {kpis.get('interventions_correctives', 0)} | Pr\u00e9ventives : {kpis.get('interventions_preventives', 0)} | Calibrations : {kpis.get('interventions_calibration', 0)}
- Disponibilit\u00e9 : {kpis.get('disponibilite', 0)}% | MTBF : {kpis.get('mtbf', 0)}h | MTTR : {kpis.get('mttr', 0)}h
- Co\u00fbt total : {kpis.get('cout_total', 0)} {sym}

=== HISTORIQUE PAR MACHINE ===
{machine_details if machine_details else 'Non disponible'}

=== PR\u00c9DICTIONS IA ===
{risk_detail if risk_detail else 'Aucune'}

=== \u00c9QUIPEMENTS ===
{equip_detail if equip_detail else 'Non disponible'}

PRODUIS un rapport JSON STRICT :
{{{{
  "alertes_critiques": [
    {{{{
      "machine": "Nom (Client)",
      "score_sante": 41,
      "jours_avant_panne": 2,
      "nb_interventions": 19,
      "risque": "Risque concret",
      "action_immediate": "Action + pi\u00e8ces"
    }}}}
  ],
  "machines_stables": [
    {{{{
      "machine": "Nom (Client)",
      "score_sante": 84,
      "commentaire": "Pourquoi fiable"
    }}}}
  ],
  "plan_maintenance": [
    {{{{
      "jour": "Lundi {today.strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}},
    {{{{
      "jour": "Mardi {(today + datetime.timedelta(days=1)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}},
    {{{{
      "jour": "Mercredi {(today + datetime.timedelta(days=2)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}}
  ],
  "estimation_couts": {{{{
    "cout_curatif_historique": {int(kpis.get('cout_total', 0))},
    "cout_preventif_propose": 0,
    "detail_preventif": "D\u00e9tail calcul",
    "gain_potentiel": 0,
    "ratio": "Pour 1 TND investi, X TND \u00e9conomis\u00e9s"
  }}}},
  "tendances": ["Tendance 1", "Tendance 2", "Tendance 3"],
  "conclusion": "Priorit\u00e9 absolue \u00e0..."
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas r\u00e9pondu.")
    result = clean_json_response(raw)
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-pieces")
def analyze_pieces(body: dict, user: dict = Depends(_verify_token)):
    """Calls Gemini to produce a spare parts purchase prediction report with dates and reasons."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    pieces_data = body.get("pieces", [])
    sym = body.get("sym", "TND")

    import datetime
    today = datetime.date.today()
    def fmt(d): return d.strftime("%d/%m/%Y")

    inventory_lines = ""
    for p in pieces_data:
        nom = p.get("designation","?"); ref = p.get("reference","?")
        stock = p.get("stock_actuel", 0); mini = p.get("stock_minimum", 1)
        prix = p.get("prix_unitaire", 0); four = p.get("fournisseur","N/A")
        equip = p.get("equipement_type","?")
        manquant = max(0, mini - stock + 1)
        if stock == 0: statut = "RUPTURE TOTALE"
        elif stock <= mini: statut = f"STOCK BAS (manque {manquant})"
        else: statut = f"OK (marge={stock-mini})"
        inventory_lines += f"  - {nom} ({ref}) | Equip: {equip} | Stock: {stock}/{mini} [{statut}] | {four} | {prix} {sym}\n"

    total_val = sum(p.get("stock_actuel",0)*p.get("prix_unitaire",0) for p in pieces_data)
    ruptures = sum(1 for p in pieces_data if p.get("stock_actuel",0)==0)
    bas = sum(1 for p in pieces_data if 0 < p.get("stock_actuel",0) <= p.get("stock_minimum",1))
    s1 = f"{fmt(today)} - {fmt(today+datetime.timedelta(days=6))}"
    s2 = f"{fmt(today+datetime.timedelta(days=7))} - {fmt(today+datetime.timedelta(days=13))}"
    s3 = f"{fmt(today+datetime.timedelta(days=14))} - {fmt(today+datetime.timedelta(days=20))}"
    d0=fmt(today); d3=fmt(today+datetime.timedelta(days=3)); d7=fmt(today+datetime.timedelta(days=7)); d14=fmt(today+datetime.timedelta(days=14))

    prompt = f"""Tu es Supply Chain Manager expert en pièces de rechange pour équipements de radiologie médicale (Tunisie).
Date du jour : {fmt(today)} | Inventaire : {len(pieces_data)} réf. | Valeur : {total_val:,.0f} {sym} | RUPTURES : {ruptures} | STOCK BAS : {bas}

INVENTAIRE :
{inventory_lines}

Génère un plan d'achat prévisionnel avec dates précises et raisons médicales/opérationnelles.
Réponds UNIQUEMENT en JSON valide (sans markdown, sans texte avant/après) :
{{
  "analyse_risque": "Synthèse 3-4 phrases sur pièces critiques, impact soins, capital immobilisé",
  "recommandations": [
    {{"piece": "Nom pièce", "reference": "REF", "raison": "Impact médical concret si non commandée (ex: arrêt scanner CT = patients sans diagnostic)", "action": "Commander immédiatement", "quantite": 2, "date_achat": "{d0}", "urgence": "critique", "cout_estime": 500}},
    {{"piece": "Nom pièce 2", "reference": "REF2", "raison": "Raison opérationnelle spécifique", "action": "Commander bientôt", "quantite": 1, "date_achat": "{d7}", "urgence": "haute", "cout_estime": 300}}
  ],
  "plan_achat": [
    {{"semaine": "S1 ({s1})", "pieces": ["pièce1"], "budget": 1200, "priorite": "Critique"}},
    {{"semaine": "S2 ({s2})", "pieces": ["pièce2"], "budget": 800, "priorite": "Haute"}},
    {{"semaine": "S3 ({s3})", "pieces": ["pièce3"], "budget": 500, "priorite": "Normale"}}
  ],
  "impact_budget": {{
    "cout_total_commande": 2500,
    "gain_potentiel": 8000,
    "ratio": "Pour 1 {sym} investi, 3.2 {sym} économisés en arrêts",
    "cout_indisponibilite_estime": 3000
  }},
  "tendances": ["Tendance 1 avec données concrètes", "Tendance 2", "Tendance 3"]
}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
    result = clean_json_response(raw)
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-sav")
def analyze_sav(body: dict, user: dict = Depends(_verify_token)):
    """Comprehensive SAV/Interventions analysis using Gemini."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    sav_data = body.get("sav_data", {})
    sym = body.get("sym", "TND")

    prompt = f"""Tu es un expert en gestion de maintenance SAV pour équipements d'imagerie médicale en Tunisie.
Analyse ces données SAV RÉELLES et produis un rapport COMPLET et DÉTAILLÉ.

=== STATISTIQUES GLOBALES ===
- Total interventions : {sav_data.get('nb_total', 0)}
- Clôturées : {sav_data.get('nb_cloturees', 0)}
- En cours : {sav_data.get('nb_en_cours', 0)}
- Taux résolution : {sav_data.get('taux_resolution', 0)}%
- MTTR moyen : {sav_data.get('mttr_h', 0)}h
- Durée totale : {sav_data.get('duree_totale_h', 0)}h

=== RÉPARTITION PAR TYPE ===
- Correctives : {sav_data.get('nb_correctives', 0)}
- Préventives : {sav_data.get('nb_preventives', 0)}  
- Installations : {sav_data.get('nb_installations', 0)}
- Ratio correctif : {sav_data.get('ratio_correctif_pct', 0)}%

=== COÛTS ===
- Coût total interventions : {sav_data.get('cout_interventions', 0)} {sym}
- Coût pièces : {sav_data.get('cout_pieces', 0)} {sym}
- Coût total : {sav_data.get('cout_total', 0)} {sym}
- Coût moyen/intervention : {sav_data.get('cout_moyen', 0)} {sym}

=== PERFORMANCE ÉQUIPE (par technicien) ===
{sav_data.get('tech_details', 'Non disponible')}

=== DÉTAIL DES INTERVENTIONS RÉCENTES ===
{sav_data.get('interventions_detail', 'Non disponible')}

=== MACHINES LES PLUS INTERVENUES ===
{sav_data.get('machines_detail', 'Non disponible')}

=== CLIENTS ===
{sav_data.get('clients_detail', 'Non disponible')}

IMPORTANT: Analyse en profondeur et produis un JSON STRICT avec cette structure exacte :
{{{{
  "analyse": "Résumé exécutif complet de la situation SAV (3-5 phrases détaillées)",
  "score_global": 75,
  "points_forts": [
    "Point fort 1 détaillé avec chiffres",
    "Point fort 2 détaillé avec chiffres",
    "Point fort 3 détaillé avec chiffres"
  ],
  "points_faibles": [
    "Point faible 1 détaillé avec chiffres",
    "Point faible 2 détaillé avec chiffres", 
    "Point faible 3 détaillé avec chiffres"
  ],
  "recommandations": [
    {{{{
      "titre": "Titre recommandation",
      "description": "Description détaillée de l'action à entreprendre",
      "impact": "HAUT"
    }}}},
    {{{{
      "titre": "Titre recommandation 2",
      "description": "Description détaillée",
      "impact": "MOYEN"
    }}}},
    {{{{
      "titre": "Titre recommandation 3",
      "description": "Description détaillée",
      "impact": "BAS"
    }}}}
  ],
  "performance_equipe": [
    {{{{
      "technicien": "Nom",
      "evaluation": "Excellent/Bon/À améliorer",
      "commentaire": "Commentaire détaillé sur ses performances"
    }}}}
  ],
  "analyse_couts": {{{{
    "verdict": "Maîtrisés/Élevés/Critiques",
    "detail": "Analyse détaillée des coûts",
    "economie_possible": "Estimation d'économie possible et comment"
  }}}},
  "tendances": [
    "Tendance 1 observée",
    "Tendance 2 observée",
    "Tendance 3 observée"
  ],
  "priorites_immediates": [
    "Action prioritaire 1",
    "Action prioritaire 2"
  ]
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
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
        "gemini_api_key", "role_permissions",
    ]
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT cle, valeur FROM config_client WHERE cle = ANY(%s)",
                (keys,)
            ).fetchall()
            result = {k: "" for k in keys}
            for row in rows:
                result[row["cle"]] = row["valeur"] or ""
            return result
    except Exception:
        # Fallback: chercher clé par clé
        result = {}
        for k in keys:
            result[k] = get_config(k, "")
        return result


@app.put("/api/settings")
def update_settings(body: dict, user: dict = Depends(_verify_token)):
    try:
        with get_db() as conn:
            for k, v in body.items():
                conn.execute(
                    """
                    INSERT INTO config_client (cle, valeur) VALUES (%s, %s)
                    ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur
                    """,
                    (k, str(v))
                )
        return {"ok": True}
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Erreur sauvegarde config: {e}\n{traceback.format_exc()}")


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
# LOGS / S3 MANAGEMENT
# ==========================================

try:
    import s3_storage
except ImportError:
    s3_storage = None


@app.get("/api/logs")
def api_list_logs(machine: Optional[str] = None, user=Depends(_verify_token)):
    """List all logs from S3, optionally filtered by machine name."""
    if not s3_storage or not s3_storage.S3_AVAILABLE:
        s3_storage and s3_storage._init_s3()
    if not s3_storage or not s3_storage.S3_AVAILABLE:
        return []

    prefix = "logs/"
    if machine:
        # Search across all date folders for this machine
        all_files = s3_storage.list_files(prefix)
        return [f for f in all_files if f"/{machine.replace(' ', '_')}/" in f["key"] or machine.replace(' ', '_') in f["key"]]
    return s3_storage.list_files(prefix)


@app.delete("/api/logs")
def api_delete_log(key: str = Query(..., description="S3 key of the log to delete"), user=Depends(_verify_token)):
    """Delete a specific log file from S3 by its key."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not available")
    s3_storage._init_s3()
    if not s3_storage.S3_AVAILABLE:
        raise HTTPException(status_code=503, detail="S3 storage not connected")

    success = s3_storage.delete_file(key)
    if success:
        return {"ok": True, "message": f"Log supprimé: {key}"}
    raise HTTPException(status_code=500, detail="Échec de la suppression du log")


@app.delete("/api/logs/machine/{machine_name}")
def api_delete_machine_logs(machine_name: str, user=Depends(_verify_token)):
    """Delete ALL log files for a given machine from S3."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not available")
    s3_storage._init_s3()
    if not s3_storage.S3_AVAILABLE:
        raise HTTPException(status_code=503, detail="S3 storage not connected")

    # Find all logs matching this machine
    all_files = s3_storage.list_files("logs/")
    machine_key = machine_name.replace(' ', '_')
    to_delete = [f for f in all_files if f"/{machine_key}/" in f["key"] or machine_key in f["key"]]

    deleted = 0
    for f in to_delete:
        if s3_storage.delete_file(f["key"]):
            deleted += 1

    return {"ok": True, "deleted": deleted, "message": f"{deleted} log(s) supprimé(s) pour {machine_name}"}


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
