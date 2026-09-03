"""Knowledge-base, technician, and log-analysis routes."""

from api.runtime import (
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    _parse_text_to_rows,
    _extract_docx_structured_rows,
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
    require_roles,
    get_db,
)
from services.file_security import read_validated_upload, validate_log_upload
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

KNOWLEDGE_READ_ROLES = ("Admin", "Manager", "Responsable Technique", "Technicien")
KNOWLEDGE_WRITE_ROLES = ("Admin", "Manager", "Responsable Technique")

@app.get("/api/knowledge")
def get_knowledge(user: dict = Depends(_verify_token)):
    require_roles(user, *KNOWLEDGE_READ_ROLES)
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
            "source_document": sol.get("Source_Document") or info.get("Source_Document", ""),
            "source_page": sol.get("Source_Page") or info.get("Source_Page"),
            "extraction_method": sol.get("Extraction_Method") or info.get("Extraction_Method", "manual"),
            "confidence_score": sol.get("Confidence_Score") or info.get("Confidence_Score"),
        })
    return results


@app.post("/api/knowledge")
def save_confirmed_knowledge(body: dict, user: dict = Depends(_verify_token)):
    """Save an explicitly confirmed cause and applied solution from supervision."""
    require_roles(user, *KNOWLEDGE_WRITE_ROLES)

    code = str(body.get("code") or "").strip()
    cause = str(body.get("cause") or "").strip()
    solution = str(body.get("solution") or "").strip()
    if not code or not cause or not solution:
        raise HTTPException(status_code=400, detail="Le code, la cause confirmée et la solution appliquée sont requis.")

    message = str(body.get("message") or "").strip()
    error_type = str(body.get("type") or "Hardware").strip()[:80] or "Hardware"
    priority = str(body.get("priorite") or "MOYENNE").strip().upper()
    if priority not in {"HAUTE", "MOYENNE", "BASSE"}:
        priority = "MOYENNE"
    validated_by = str(user.get("username") or user.get("sub") or "Utilisateur SAVIA")[:120]

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO codes_erreurs (code, message, type, source_document, source_page, extraction_method, confidence_score) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (code) DO UPDATE SET message=EXCLUDED.message, type=EXCLUDED.type, "
                "source_document='', source_page=NULL, extraction_method=EXCLUDED.extraction_method, confidence_score=EXCLUDED.confidence_score",
                (code[:120], message[:500], error_type, "", None, "manual", 100),
            )
            conn.execute(
                "INSERT INTO solutions (mot_cle, type, priorite, cause, solution, validated_by, source_document, source_page, extraction_method, confidence_score, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP) "
                "ON CONFLICT (mot_cle) DO UPDATE SET "
                "type=EXCLUDED.type, priorite=EXCLUDED.priorite, cause=EXCLUDED.cause, "
                "solution=EXCLUDED.solution, validated_by=EXCLUDED.validated_by, "
                "source_document='', source_page=NULL, "
                "extraction_method=EXCLUDED.extraction_method, confidence_score=EXCLUDED.confidence_score, "
                "updated_at=CURRENT_TIMESTAMP",
                (code[:120], error_type, priority, cause[:4000], solution[:8000], validated_by, "", None, "manual", 100),
            )
        return {"ok": True, "message": "Cause et solution confirmées enregistrées dans la base de connaissances."}
    except Exception as exc:
        logger.exception("Impossible d'enregistrer la connaissance confirmée")
        raise HTTPException(status_code=500, detail=f"Erreur d'enregistrement: {exc}")


# Parsing and encoding are implemented in services.knowledge_import.


@app.post("/api/knowledge/import")
async def import_knowledge(
    file: UploadFile = File(...),
    preview: bool = False,
    preview_rows: str | None = Form(None),
    user: dict = Depends(_verify_token),
):
    require_roles(user, *KNOWLEDGE_WRITE_ROLES)
    """Preview or import validated error records from a technical document."""
    import io
    import json
    import unicodedata
    import re
    
    def fix_mojibake(text: str) -> str:
        """
        Répare la mojibake (texte cassé dû à mauvais encodage).
        Utilise plusieurs stratégies pour détecter et réparer.
        """
        if not text:
            return text
        
        # Stratégie 1: réparer les séquences UTF-8 décodées en CP1252.
        # Exemple : ``â€‘`` représente le tiret insécable U+2011 et
        # ``â€¯`` représente l'espace étroit insécable U+202F. Cette étape
        # doit précéder le fallback Latin-1, sinon le caractère ``€`` est
        # ignoré et le texte devient encore plus corrompu.
        mojibake_markers = ("\u00e2\u20ac", "\u00c2")
        if any(marker in text for marker in mojibake_markers):
            try:
                fixed = text.encode("cp1252").decode("utf-8")
                if sum(fixed.count(marker) for marker in mojibake_markers) < sum(text.count(marker) for marker in mojibake_markers):
                    logger.info("✓ fix_mojibake: réparation UTF-8/CP1252 réussie")
                    return fixed
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # Stratégie 2: Détecter UTF-8 mal interprété en Latin-1
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
        
        # Stratégie 3: Remplacer les caractères connus corrompus
        corruption_map = {
            'ƒ': '',  # U+0192 - suppression
            'Ô': 'O',  # U+00D4 - confusion
            'ô': 'o',  # U+00F4 - confusion
            'Õ': 'O',  # U+00D5 - confusion
            'õ': 'o',  # U+00F5 - confusion
            '\ufffd': '',  # caractère de remplacement déjà irréversible
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
        text = re.sub(r'[\u00A0\u2000-\u200B\u2028\u2029\u202F\u3000]', ' ', text)
        
        # ÉTAPE 1: Remplacer les caractères de typographie spéciaux par ASCII
        char_map = {
            ''': "'",           # apostrophe courbe
            ''': "'",           # autre apostrophe
            '"': '"',           # guillemet ouvrant courbe
            '"': '"',           # guillemet fermant courbe
            '–': '-',           # tiret court
            '—': '--',          # tiret long
            '\u2011': '-',      # tiret insécable
            '\u00AD': '',       # trait d'union conditionnel
            '−': '-',           # signe moins Unicode
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
    
    validated_upload = await read_validated_upload(file, "knowledge_import")
    filename = validated_upload.display_name
    content = validated_upload.data

    try:
        filename_lower = filename.lower()
        extraction_method = "structured_import"
        parsed_preview_rows = None
        if preview_rows:
            try:
                parsed_preview_rows = json.loads(preview_rows)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Prévisualisation invalide : {exc}")
            if not isinstance(parsed_preview_rows, list):
                raise HTTPException(status_code=400, detail="Prévisualisation invalide : tableau attendu.")
            rows = parsed_preview_rows
            extraction_method = "validated_preview"
        elif filename_lower.endswith(".csv"):
            import csv
            # Utiliser la détection d'encodage universelle
            text = detect_and_fix_encoding(content)
            text = sanitize_text(text)
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            rows = list(reader)
            extraction_method = "csv"
        
        elif filename_lower.endswith((".xlsx", ".xls")):
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
            extraction_method = "xlsx"
        
        elif filename_lower.endswith(".pdf"):
            pdf_has_text = False
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                page_texts = []
                for page_number, page in enumerate(doc, start=1):
                    page_text = sanitize_text(page.get_text())
                    if page_text.strip():
                        pdf_has_text = True
                        page_texts.append((page_number, page_text))
                # One AI pass over bounded, line-preserving chunks avoids a request storm on large PDFs.
                full_text = "\n\n".join(f"[PAGE {page_number}]\n{page_text}" for page_number, page_text in page_texts)
                rows = _parse_text_to_rows(full_text)
                # Recover the source page from the code (or message) without another AI call.
                for row in rows:
                    code = str(row.get("code") or "").casefold()
                    message = str(row.get("message") or "").casefold()
                    code_tokens = [
                        re.sub(r"\s+", "", token)
                        for token in re.findall(r"\b\d{2}-\s*[0-9a-f]{3,4}h\b|\b\d{3,5}d\b", code, re.IGNORECASE)
                    ]
                    for page_number, page_text in page_texts:
                        page_lower = page_text.casefold()
                        page_compact = re.sub(r"\s+", "", page_lower)
                        if (
                            (code and code in page_lower)
                            or any(token in page_compact for token in code_tokens)
                            or (message and message[:40] in page_lower)
                        ):
                            row["source_page"] = page_number
                            break
                extraction_method = "pdf-text-ai-regex"
            except Exception:
                # Fallback: décoder les bytes directement
                full_text = detect_and_fix_encoding(content)
                full_text = sanitize_text(full_text)
                pdf_has_text = bool(full_text.strip())
                rows = _parse_text_to_rows(full_text)
                extraction_method = "pdf-decoded-ai-regex"
            if not rows and not pdf_has_text:
                raise HTTPException(status_code=422, detail="PDF scanné ou sans texte exploitable : OCR requis avant import.")
        
        elif filename_lower.endswith((".docx", ".doc")):
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
                        cells = [sanitize_text(cell.text) for cell in row.cells if cell.text and cell.text.strip()]
                        if cells:
                            # Keep column boundaries visible to the extractor.
                            full_text += " | ".join(cells) + "\n"
                
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
            
            # Word alarm cards may live in embedded text boxes, which are not
            # exposed by python-docx paragraphs. Extract them structurally so
            # each ALARM/CAUSE/REMEDY card remains one row; Remedy is mapped to
            # the canonical Solution column automatically.
            structured_rows = _extract_docx_structured_rows(content)
            ai_rows = _parse_text_to_rows(full_text)
            if structured_rows:
                # Do not import headings from the table of contents as error
                # records. AI rows are useful only when they enrich a card
                # that was actually found with CAUSE/REMEDY content.
                structured_codes = {str(row.get("code", "")).casefold() for row in structured_rows}
                ai_rows = [row for row in ai_rows if str(row.get("code", "")).casefold() in structured_codes]
            rows = structured_rows + ai_rows
            logger.info("DOCX structured extraction: %s card(s), AI supplement: %s row(s)", len(structured_rows), len(ai_rows))
            extraction_method = "docx-ai-regex"

        
        else:
            raise HTTPException(status_code=400, detail="Format non supporté. Utilisez CSV, XLSX, PDF ou DOCX.")

        if not rows:
            raise HTTPException(status_code=422, detail="Aucune fiche d'erreur structurée n'a été trouvée dans le document.")

        # Auto-detect column mapping
        col_map = {}
        for h in (rows[0].keys() if rows else []):
            hl = h.lower().strip()
            if "code" in hl or "mot_cle" in hl or "mot clé" in hl: col_map["code"] = h
            elif "message" in hl or "msg" in hl: col_map["message"] = h
            elif "type" in hl: col_map["type"] = h
            elif "cause" in hl: col_map["cause"] = h
            elif "solution" in hl: col_map["solution"] = h
            elif "priorit" in hl: col_map["priorite"] = h

        if "code" not in col_map:
            raise HTTPException(status_code=400, detail="Colonne 'Code' non trouvée dans le fichier.")

        # Normalize and merge records found on several pages/chunks before writing.
        normalized_rows = {}
        for row in rows:
            code = sanitize_text(str(row.get(col_map.get("code", ""), "") or "").strip())
            if not code:
                continue
            normalized = {
                "code": code[:120],
                "message": sanitize_text(str(row.get(col_map.get("message", ""), "") or ""))[:500],
                "type": sanitize_text(str(row.get(col_map.get("type", ""), "Hardware") or "Hardware"))[:80] or "Hardware",
                "cause": sanitize_text(str(row.get(col_map.get("cause", ""), "") or ""))[:4000],
                "solution": sanitize_text(str(row.get(col_map.get("solution", ""), "") or ""))[:8000],
                "priorite": sanitize_text(str(row.get(col_map.get("priorite", ""), "MOYENNE") or "MOYENNE")).upper(),
                "source_page": row.get("source_page"),
                "extraction_method": row.get("extraction_method") or extraction_method,
                "confidence_score": row.get("confidence"),
            }
            if normalized["priorite"] not in {"HAUTE", "MOYENNE", "BASSE"}:
                normalized["priorite"] = "MOYENNE"
            try:
                normalized["confidence_score"] = max(0, min(100, int(float(normalized["confidence_score"]))))
            except (TypeError, ValueError):
                normalized["confidence_score"] = 100 if extraction_method in {"csv", "xlsx"} else 35
            key = code.casefold()
            existing = normalized_rows.get(key)
            if not existing:
                normalized_rows[key] = normalized
            else:
                # Prefer the structured/document row over a low-confidence
                # regex/AI fallback, regardless of extraction order.
                if normalized["confidence_score"] > existing["confidence_score"]:
                    previous = existing
                    normalized_rows[key] = normalized
                    existing = normalized
                    normalized = previous
                for field in ("message", "type", "cause", "solution"):
                    if not existing[field] and normalized[field]:
                        existing[field] = normalized[field]
                existing["confidence_score"] = max(existing["confidence_score"], normalized["confidence_score"])

        if not normalized_rows:
            raise HTTPException(status_code=422, detail="Aucune ligne avec un code d'erreur exploitable n'a été trouvée.")

        if preview:
            return {
                "ok": True,
                "preview": True,
                "filename": filename,
                "rows": [
                    {
                        **row,
                        "source_document": filename,
                        "source_page": row["source_page"] if str(row["source_page"] or "").isdigit() else None,
                        "confidence_score": row["confidence_score"],
                    }
                    for row in normalized_rows.values()
                ],
                "imported": len(normalized_rows),
            }

        imported = 0
        with get_db() as conn:
            for row in normalized_rows.values():
                source_page = row["source_page"] if str(row["source_page"] or "").isdigit() else None
                conn.execute(
                    "INSERT INTO codes_erreurs (code, message, type, source_document, source_page, extraction_method, confidence_score) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (code) DO UPDATE SET message=EXCLUDED.message, type=EXCLUDED.type, "
                    "source_document=EXCLUDED.source_document, source_page=EXCLUDED.source_page, "
                    "extraction_method=EXCLUDED.extraction_method, confidence_score=EXCLUDED.confidence_score",
                    (row["code"], row["message"], row["type"], filename, source_page, row["extraction_method"], row["confidence_score"])
                )
                conn.execute(
                    "INSERT INTO solutions (mot_cle, type, cause, solution, priorite, source_document, source_page, extraction_method, confidence_score) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (mot_cle) DO UPDATE SET type=EXCLUDED.type, cause=EXCLUDED.cause, "
                    "solution=EXCLUDED.solution, priorite=EXCLUDED.priorite, source_document=EXCLUDED.source_document, "
                    "source_page=EXCLUDED.source_page, extraction_method=EXCLUDED.extraction_method, "
                    "confidence_score=EXCLUDED.confidence_score, updated_at=CURRENT_TIMESTAMP",
                    (row["code"], row["type"], row["cause"], row["solution"], row["priorite"], filename, source_page, row["extraction_method"], row["confidence_score"])
                )
                imported += 1

        return {"ok": True, "imported": imported, "message": f"{imported} codes importés avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Knowledge import failed for %s", filename)
        raise HTTPException(status_code=500, detail=f"Erreur d'import: {str(e)}")


@app.delete("/api/knowledge/{code}")
def delete_knowledge_code(code: str, user: dict = Depends(_verify_token)):
    require_roles(user, *KNOWLEDGE_WRITE_ROLES)
    """Supprimer un code d'erreur spécifique et ses solutions."""
    try:
        with get_db() as conn:
            # Supprimer la solution d'abord (FK contraint) - utiliser mot_cle
            conn.execute("DELETE FROM solutions WHERE mot_cle = %s", (code,))
            # Puis le code d'erreur - utiliser code
            conn.execute("DELETE FROM codes_erreurs WHERE code = %s", (code,))
        return {"ok": True, "message": f"Code {code} supprimé avec succès."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de suppression: {str(e)}")


# ==========================================
# TECHNICIENS
# ==========================================

@app.get("/api/techniciens")
def get_techniciens(user: dict = Depends(_verify_token)):
    require_roles(user, *KNOWLEDGE_READ_ROLES)
    return _df_to_records(lire_techniciens())


@app.post("/api/techniciens")
def create_technicien(body: dict, user: dict = Depends(_verify_token)):
    require_roles(user, *KNOWLEDGE_WRITE_ROLES)
    # Validate username uniqueness if provided
    username = body.get("username", "").strip()
    if username:
        with get_db() as conn:
            # Check in utilisateurs
            existing_user = conn.execute(
                "SELECT id FROM utilisateurs WHERE username = %s",
                (username,)
            ).fetchone()
            
            if existing_user:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ce nom d'utilisateur '{username}' est déjà utilisé dans le système utilisateurs. Veuillez choisir un autre."
                )
            
            # Check in techniciens
            existing_tech = conn.execute(
                "SELECT id FROM techniciens WHERE username = %s",
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
    require_roles(user, *KNOWLEDGE_WRITE_ROLES)
    update_technicien(tech_id, body)
    return {"ok": True}


@app.delete("/api/techniciens/{tech_id}")
def delete_technicien(tech_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, *KNOWLEDGE_WRITE_ROLES)
    supprimer_technicien(tech_id)
    return {"ok": True}


# ==========================================
# LOGS UPLOAD (Supervision) — S3/MinIO + PostgreSQL
# ==========================================

@app.post("/api/logs/upload")
def upload_log(body: dict, user: dict = Depends(_verify_token)):
    require_roles(user, *KNOWLEDGE_READ_ROLES)
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
    filename, content = validate_log_upload(filename, content)

    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    username = user.get("sub", "system") if user else "system"

    try:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM logs_uploaded WHERE content_hash = %s AND equipement = %s",
                (content_hash, equipement)
            ).fetchone()
            if existing:
                eid = existing.get("id") if isinstance(existing, dict) else existing[0]
                # Update parsed_errors on duplicate if not already stored
                if parsed_errors_str:
                    conn.execute(
                        "UPDATE logs_uploaded SET parsed_errors = %s WHERE id = %s AND (parsed_errors IS NULL OR parsed_errors = '')",
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
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (equipement, filename, s3_key, content_hash, size_bytes, nb_errors, nb_critiques, username, parsed_errors_str)
            )
            new_row = cursor.fetchone()
            new_id = (new_row["id"] if isinstance(new_row, dict) else new_row[0]) if new_row else None
            conn.execute(
                "INSERT INTO audit_log (username, action, details) VALUES (%s, %s, %s)",
                (username, "Upload Log", f"Log '{filename}' S3:{s3_key or 'N/A'} ({nb_errors} erreurs)")
            )
            return {"ok": True, "id": new_id, "s3_key": s3_key,
                    "message": f"Log enregistré — {size_bytes} octets, {nb_errors} erreur(s), S3: {'ok' if s3_key else 'fallback'}"}
    except Exception as e:
        logger.error(f"Log upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
def list_logs(equipement: str = None, user: dict = Depends(_verify_token)):
    require_roles(user, *KNOWLEDGE_READ_ROLES)
    """Liste les logs uploadés (métadonnées depuis PostgreSQL)."""
    try:
        with get_db() as conn:
            if equipement:
                rows = conn.execute(
                    "SELECT id, equipement, filename, s3_key, size_bytes, nb_errors, nb_critiques, uploaded_by, uploaded_at FROM logs_uploaded WHERE equipement = %s ORDER BY uploaded_at DESC",
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
    require_roles(user, *KNOWLEDGE_READ_ROLES)
    """Récupère le contenu d'un log depuis S3/MinIO."""
    try:
        with get_db() as conn:
            row = conn.execute("SELECT s3_key, equipement, filename, parsed_errors FROM logs_uploaded WHERE id = %s", (log_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Log non trouvé")
            # Les curseurs PostgreSQL du projet retournent des dictionnaires.
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
