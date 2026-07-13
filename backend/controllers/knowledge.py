"""Knowledge-base, technician, and log-analysis routes."""

from api.runtime import (
    Depends,
    File,
    HTTPException,
    UploadFile,
    _parse_text_to_rows,
    ajouter_technicien,
    app,
    detect_and_fix_encoding,
    get_db,
    lire_base,
    lire_techniciens,
    logger,
    supprimer_technicien,
    update_technicien,
)
from api.security import (
    Depends,
    HTTPException,
    _verify_token,
    get_db,
)
from services.scheduled_jobs import (
    _df_to_records,
    get_db,
    logger,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    _verify_token,
    app,
    get_db,
    logger,
)

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


# Parsing and encoding are implemented in services.knowledge_import.


@app.post("/api/knowledge/import")
async def import_knowledge(file: UploadFile = File(...), user: dict = Depends(_verify_token)):
    """Import error codes from an uploaded Excel/CSV file."""
    import io
    import unicodedata
    import re
    
    def fix_mojibake(text: str) -> str:
        """
        Répare la mojibake (texte cassé dû à mauvais encodage).
        Utilise plusieurs stratégies pour détecter et réparer.
        """
        if not text:
            return text
        
        # Stratégie 1: Détecter UTF-8 mal interprété en Latin-1
        # Caractères typiques: ƒ (U+0192), ö (U+00F6), etc.
        # Motif: si on voit trop de caractères accidentels, essayer de ré-encoder
        suspect_pattern = re.compile(r'[\u0192\u00C0-\u00FF\u0100-\u017F]')
        suspect_count = len(suspect_pattern.findall(text))
        
        if suspect_count > len(text) * 0.01:  # Plus de 1% de caractères suspects
            try:
                # Essayer UTF-8 -> Latin-1 -> UTF-8
                fixed = text.encode('latin-1', errors='ignore').decode('utf-8', errors='replace')
                # Vérifier si ça s'est amélioré
                fixed_suspects = len(suspect_pattern.findall(fixed))
                if fixed_suspects < suspect_count:
                    logger.info(f"✓ fix_mojibake: Réparation UTF-8→Latin-1→UTF-8 réussie ({suspect_count} → {fixed_suspects})")
                    return fixed
            except Exception as e:
                logger.warning(f"⚠️ fix_mojibake: Tentative UTF-8→Latin-1 échouée: {e}")
        
        # Stratégie 2: Remplacer les caractères connus corrompus
        corruption_map = {
            'ƒ': '',  # U+0192 - suppression
            'Ô': 'O',  # U+00D4 - confusion
            'ô': 'o',  # U+00F4 - confusion
            'Õ': 'O',  # U+00D5 - confusion
            'õ': 'o',  # U+00F5 - confusion
        }
        for wrong, correct in corruption_map.items():
            if wrong in text:
                text = text.replace(wrong, correct)
        
        return text
    
    def sanitize_text(text: str) -> str:
        """Nettoie le texte en fixant les problèmes de mojibake et caractères corrompus."""
        if not text:
            return text
        
        # ÉTAPE 0: Réparer la mojibake
        text = fix_mojibake(text)
        
        # ÉTAPE 0.5: Convertir les espaces non-ASCII en espaces normaux AVANT toute autre chose
        # Cela évite les problèmes avec les patterns regex
        text = re.sub(r'[\u00A0\u2000-\u200B\u2028\u2029\u3000]', ' ', text)
        
        # ÉTAPE 1: Remplacer les caractères de typographie spéciaux par ASCII
        char_map = {
            ''': "'",           # apostrophe courbe
            ''': "'",           # autre apostrophe
            '"': '"',           # guillemet ouvrant courbe
            '"': '"',           # guillemet fermant courbe
            '–': '-',           # tiret court
            '—': '--',          # tiret long
            '«': '"',           # guillemet français
            '»': '"',           # guillemet français
            '‹': '<',           # chevron ouvrant
            '›': '>',           # chevron fermant
            '\u00A0': ' ',      # espace insécable
            '\u2000': ' ',      # en quad
            '\u2001': ' ',      # em quad
            '\u2002': ' ',      # en space
            '\u2003': ' ',      # em space
            '\u2004': ' ',      # three-per-em space
            '\u2005': ' ',      # four-per-em space
            '\u2006': ' ',      # six-per-em space
            '\u2007': ' ',      # figure space
            '\u2008': ' ',      # punctuation space
            '\u2009': ' ',      # thin space
            '\u200A': ' ',      # hair space
            '\u200B': '',       # zero-width space
            '\u200C': '',       # zero-width non-joiner
            '\u200D': '',       # zero-width joiner
            '\u3000': ' ',      # ideographic space
            '\ufeff': '',       # BOM
        }
        
        for old_char, new_char in char_map.items():
            text = text.replace(old_char, new_char)
        
        # ÉTAPE 2: Supprimer les caractères de contrôle sauf newline, tab, CR
        # But: garder newlines pour les patterns regex
        text = ''.join(c if (ord(c) >= 32 or c in '\n\t\r') else '' for c in text)
        
        # ÉTAPE 3: Convertir en NFD (décomposé) puis en NFC (composé) pour normaliser
        text = unicodedata.normalize('NFC', text)
        
        # ÉTAPE 4: Nettoyer les espaces multiples (mais garder les newlines)
        lines = text.split('\n')
        lines = [' '.join(line.split()) for line in lines]
        text = '\n'.join(lines)
        
        return text
    
    filename = file.filename or ""
    content = await file.read()

    try:
        if filename.endswith(".csv"):
            import csv
            # Utiliser la détection d'encodage universelle
            text = detect_and_fix_encoding(content)
            text = sanitize_text(text)
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        
        elif filename.endswith((".xlsx", ".xls")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active
            headers = [sanitize_text(str(c.value or "").strip()) for c in next(ws.iter_rows(min_row=1, max_row=1))]
            rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for i, v in enumerate(row):
                    if i < len(headers):
                        val = str(v) if v else ""
                        row_dict[headers[i]] = sanitize_text(val)
                rows.append(row_dict)
        
        elif filename.endswith(".pdf"):
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                full_text = "\n".join(sanitize_text(page.get_text()) for page in doc)
            except Exception:
                # Fallback: décoder les bytes directement
                full_text = detect_and_fix_encoding(content)
            full_text = sanitize_text(full_text)
            rows = _parse_text_to_rows(full_text)
        
        elif filename.endswith((".docx", ".doc")):
            import zipfile
            
            full_text = ""
            
            # Simple approach: Extract ALL text from document
            try:
                import docx
                doc = docx.Document(io.BytesIO(content))
                
                # Extract paragraphs
                for p in doc.paragraphs:
                    if p.text and p.text.strip():
                        full_text += sanitize_text(p.text) + "\n"
                
                # Extract table content
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            if cell.text and cell.text.strip():
                                full_text += sanitize_text(cell.text) + " "
                    full_text += "\n"
                
                logger.info(f"✓ DOCX extraction OK: {len(full_text)} chars extracted")
                    
            except Exception as e1:
                logger.warning(f"⚠️ DOCX extraction failed: {e1}, trying XML fallback...")
                full_text = ""
                
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as doczip:
                        xml_bytes = doczip.read('word/document.xml')
                        xml_text = detect_and_fix_encoding(xml_bytes)
                        
                        text_elements = re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml_text, re.DOTALL)
                        for elem in text_elements:
                            elem = elem.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'")
                            full_text += sanitize_text(elem) + " "
                        
                        logger.info(f"✓ XML extraction OK: {len(full_text)} chars")
                            
                except Exception as e2:
                    logger.warning(f"⚠️ XML extraction failed: {e2}")
                    full_text = detect_and_fix_encoding(content)
            
            full_text = sanitize_text(full_text) if full_text else ""
            logger.info(f"🔍 DEBUG - Total extracted: {len(full_text)} chars")
            
            # Use AI-based parsing
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
                code = sanitize_text(row.get(col_map.get("code", ""), "").strip())
                if not code:
                    continue
                msg = sanitize_text(row.get(col_map.get("message", ""), ""))
                typ = sanitize_text(row.get(col_map.get("type", ""), "Hardware"))
                cause = sanitize_text(row.get(col_map.get("cause", ""), ""))
                solution = sanitize_text(row.get(col_map.get("solution", ""), ""))
                priorite = sanitize_text(row.get(col_map.get("priorite", ""), "MOYENNE"))

                # Insert or update codes_erreurs
                conn.execute(
                    "INSERT INTO codes_erreurs (code, message, type) VALUES (?, ?, ?) "
                    "ON CONFLICT (code) DO UPDATE SET message=EXCLUDED.message, type=EXCLUDED.type",
                    (code, msg, typ)
                )
                # Insert or update solutions
                conn.execute(
                    "INSERT INTO solutions (mot_cle, cause, solution, priorite) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (mot_cle) DO UPDATE SET cause=EXCLUDED.cause, solution=EXCLUDED.solution, priorite=EXCLUDED.priorite",
                    (code, cause, solution, priorite)
                )
                imported += 1

        return {"ok": True, "imported": imported, "message": f"{imported} codes importés avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'import: {str(e)}")


@app.delete("/api/knowledge/{code}")
def delete_knowledge_code(code: str, user: dict = Depends(_verify_token)):
    """Supprimer un code d'erreur spécifique et ses solutions."""
    try:
        with get_db() as conn:
            # Supprimer la solution d'abord (FK contraint) - utiliser mot_cle
            conn.execute("DELETE FROM solutions WHERE mot_cle = ?", (code,))
            # Puis le code d'erreur - utiliser code
            conn.execute("DELETE FROM codes_erreurs WHERE code = ?", (code,))
        return {"ok": True, "message": f"Code {code} supprimé avec succès."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de suppression: {str(e)}")


# ==========================================
# TECHNICIENS
# ==========================================

@app.get("/api/techniciens")
def get_techniciens(user: dict = Depends(_verify_token)):
    return _df_to_records(lire_techniciens())


@app.post("/api/techniciens")
def create_technicien(body: dict, user: dict = Depends(_verify_token)):
    # Validate username uniqueness if provided
    username = body.get("username", "").strip()
    if username:
        with get_db() as conn:
            # Check in utilisateurs
            existing_user = conn.execute(
                "SELECT id FROM utilisateurs WHERE username = ?",
                (username,)
            ).fetchone()
            
            if existing_user:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ce nom d'utilisateur '{username}' est déjà utilisé dans le système utilisateurs. Veuillez choisir un autre."
                )
            
            # Check in techniciens
            existing_tech = conn.execute(
                "SELECT id FROM techniciens WHERE username = ?",
                (username,)
            ).fetchone()
            
            if existing_tech:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ce nom d'utilisateur '{username}' est déjà utilisé par un autre technicien. Veuillez choisir un autre."
                )
    
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
    import json as _json_import
    parsed_errors_raw = body.get("parsed_errors", None)
    parsed_errors_str = _json_import.dumps(parsed_errors_raw) if parsed_errors_raw is not None else None

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
                # Update parsed_errors on duplicate if not already stored
                if parsed_errors_str:
                    conn.execute(
                        "UPDATE logs_uploaded SET parsed_errors = ? WHERE id = ? AND (parsed_errors IS NULL OR parsed_errors = '')",
                        (parsed_errors_str, eid)
                    )
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
                """INSERT INTO logs_uploaded (equipement, filename, s3_key, content_hash, size_bytes, nb_errors, nb_critiques, uploaded_by, parsed_errors)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (equipement, filename, s3_key, content_hash, size_bytes, nb_errors, nb_critiques, username, parsed_errors_str)
            )
            new_row = cursor.fetchone()
            new_id = (new_row["id"] if isinstance(new_row, dict) else new_row[0]) if new_row else None
            conn.execute(
                "INSERT INTO audit_log (username, action, details) VALUES (?, ?, ?)",
                (username, "Upload Log", f"Log '{filename}' S3:{s3_key or 'N/A'} ({nb_errors} erreurs)")
            )
            return {"ok": True, "id": new_id, "s3_key": s3_key,
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
            row = conn.execute("SELECT s3_key, equipement, filename, parsed_errors FROM logs_uploaded WHERE id = ?", (log_id,)).fetchone()
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
                import json as _json_nk
                _pe_nk = None
                if (isinstance(row, dict) and row.get("parsed_errors")) or (not isinstance(row, dict) and len(row) > 3 and row[3]):
                    _pe_nk_raw = row.get("parsed_errors") if isinstance(row, dict) else row[3]
                    try: _pe_nk = _json_nk.loads(_pe_nk_raw)
                    except: _pe_nk = None
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": "", "parsed_errors": _pe_nk}
            try:
                from s3_storage import download_file
                content = download_file(s3_key)
                import json as _json_ret
                _pe = None
                if (isinstance(row, dict) and row.get("parsed_errors")) or (not isinstance(row, dict) and len(row) > 3 and row[3]):
                    _pe_raw = row.get("parsed_errors") if isinstance(row, dict) else row[3]
                    try: _pe = _json_ret.loads(_pe_raw)
                    except: _pe = None
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": content or "", "s3_key": s3_key, "parsed_errors": _pe}
            except Exception:
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": ""}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# AI INTEGRATION
# ==========================================

__all__ = [
    "get_knowledge",
    "import_knowledge",
    "delete_knowledge_code",
    "get_techniciens",
    "create_technicien",
    "modifier_techniciens_route",
    "delete_technicien",
    "upload_log",
    "list_logs",
    "get_log",
]

