"""Administration, audit, notification, and settings routes."""

from api.runtime import (
    BaseModel,
    Body,
    Depends,
    FPDF,
    HTTPException,
    Optional,
    Query,
    app,
    bcrypt,
    compter_notifications_non_lues,
    datetime,
    get_config,
    get_db,
    lire_audit,
    lire_notification_schedules,
    lire_notifications_pieces,
    logger,
    marquer_notification_lue,
    marquer_notification_traitee,
    os,
    sauvegarder_notification_schedules_batch,
)
from api.security import (
    _verify_token,
)
from services.scheduled_jobs import (
    _df_to_records,
)

@app.get("/api/admin/users")
def get_users(user: dict = Depends(_verify_token)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, nom_complet, role, client, email, actif, profil, pages_autorisees, created_at, last_login FROM utilisateurs ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/users")
def create_user(body: dict, user: dict = Depends(_verify_token)):
    # Validate role
    valid_roles = ['Admin', 'Technicien', 'Lecteur', 'Manager', 'Responsable Technique', 'Gestionnaire']
    role = body.get("role", "Lecteur")
    if role not in valid_roles:
        return {"error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}, 400
    
    username = body.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username est requis")
    
    # Check if username already exists
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM utilisateurs WHERE username = ?",
            (username,)
        ).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Ce nom d'utilisateur '{username}' est déjà utilisé. Veuillez choisir un autre."
            )
        
        hashed = bcrypt.hashpw(body["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute(
            "INSERT INTO utilisateurs (username, password_hash, nom_complet, role, client, email, actif, profil, pages_autorisees) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (username, hashed, body.get("nom_complet", ""), role, body.get("client", ""), body.get("email", ""), body.get("profil", ""), body.get("pages_autorisees", ""))
        )
    return {"ok": True}


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: int, body: dict, user: dict = Depends(_verify_token)):
    fields = []
    params = []
    for f in ["nom_complet", "role", "client", "actif", "email", "profil", "pages_autorisees"]:
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


@app.get("/api/admin/audit-logs")
def get_admin_audit_logs(
    limit: int = Query(1000, ge=1, le=5000),
    username: str = Query(""),
    action: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    user: dict = Depends(_verify_token),
):
    """
    GET /api/admin/audit-logs - Retourne les logs filtrés (ADMIN ONLY)
    
    Query Parameters:
      - limit: Nombre max de logs (1-5000, défaut 1000)
      - username: Filtrer par utilisateur (optionnel)
      - action: Filtrer par type d'action (optionnel)
      - date_from: Date début YYYY-MM-DD (optionnel)
      - date_to: Date fin YYYY-MM-DD (optionnel)
    
    Returns: Array of audit log entries
    """
    # Vérifier que l'utilisateur est ADMIN
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    try:
        df = lire_audit(
            limit=limit,
            username=username if username else "",
            action=action if action else "",
            date_from=date_from if date_from else "",
            date_to=date_to if date_to else ""
        )
        return _df_to_records(df)
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AuditExportRequest(BaseModel):
    limit: int = 1000
    username: str = ""
    action: str = ""
    date_from: str = ""
    date_to: str = ""


@app.post("/api/admin/audit-logs/export-pdf")
def export_audit_logs_pdf(
    req: AuditExportRequest,
    user: dict = Depends(_verify_token),
):
    """
    POST /api/admin/audit-logs/export-pdf - Exporte les logs en PDF (ADMIN ONLY)
    
    Body parameters:
      - limit: Nombre max de logs
      - username: Filtrer par utilisateur
      - action: Filtrer par type d'action
      - date_from: Date début YYYY-MM-DD
      - date_to: Date fin YYYY-MM-DD
    
    Returns: PDF file
    """
    # Vérifier que l'utilisateur est ADMIN
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    try:
        # Récupérer les logs avec les filtres
        df = lire_audit(
            limit=req.limit,
            username=req.username,
            action=req.action,
            date_from=req.date_from,
            date_to=req.date_to
        )
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Aucun log à exporter")
        
        # Créer le PDF en format PAYSAGE
        pdf = FPDF(orientation='L')  # L = Landscape
        pdf.add_page()
        
        # Charger la police DejaVu
        _DJVU = '/app/DejaVuSans.ttf'
        if os.path.exists(_DJVU):
            try:
                pdf.add_font('DejaVu', fname=_DJVU)
            except Exception as e:
                logger.warning(f"Could not load DejaVu font: {e}, falling back to Helvetica")
                _DJVU = None
        else:
            _DJVU = None
        
        # Utiliser Helvetica comme fallback si DejaVu n'est pas disponible
        font_name = 'DejaVu' if _DJVU else 'Helvetica'
        pdf.set_font(font_name, size=10)
        
        # En-tête
        pdf.set_font(font_name, "B", size=14)
        pdf.cell(0, 10, "Journal d'Audit SAVIA", ln=True, align="C")
        
        pdf.set_font(font_name, size=9)
        pdf.cell(0, 5, f"Généré le: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="R")
        pdf.cell(0, 5, f"Par: {user.get('nom', user.get('username', 'N/A'))}", ln=True, align="R")
        
        # Filtres appliqués
        filters_text = []
        if req.username:
            filters_text.append(f"Utilisateur: {req.username}")
        if req.action:
            filters_text.append(f"Action: {req.action}")
        if req.date_from or req.date_to:
            date_range = f"Période: {req.date_from or '...'} à {req.date_to or '...'}"
            filters_text.append(date_range)
        
        if filters_text:
            pdf.set_font(font_name, "I", size=8)
            pdf.cell(0, 4, "Filtres appliqués: " + " | ".join(filters_text), ln=True)
        
        pdf.ln(3)
        
        # Tableau des logs - colonnes plus larges pour le paysage
        pdf.set_font(font_name, "B", size=9)
        # Largeurs pour format paysage avec Action et Détails +40%
        col_widths = [30, 30, 49, 98, 25, 20]  # Total ~252mm (ajusté)
        headers = ["Date/Heure", "Utilisateur", "Action", "Détails", "Page", "IP"]
        
        # En-têtes du tableau avec couleur de fond
        pdf.set_fill_color(1, 180, 188)  # Couleur SAVIA (cyan)
        pdf.set_text_color(255, 255, 255)  # Texte blanc
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 8, header, border=1, align="C", fill=True)
        pdf.ln()
        
        # Contenu du tableau
        pdf.set_font(font_name, size=8)
        pdf.set_text_color(0, 0, 0)  # Texte noir pour le contenu
        for _, row in df.iterrows():
            timestamp = str(row.get("timestamp", ""))[:16]  # Format: YYYY-MM-DD HH:MM
            username_val = str(row.get("username", ""))[:25]
            action_val = str(row.get("action", ""))[:25]
            details_val = str(row.get("details", ""))[:50]
            page_val = str(row.get("page", ""))[:20]
            ip_val = str(row.get("ip_address", ""))[:15]
            
            # Écrire les cellules avec hauteur augmentée pour multi-ligne
            pdf.cell(col_widths[0], 7, timestamp, border=1)
            pdf.cell(col_widths[1], 7, username_val, border=1)
            pdf.cell(col_widths[2], 7, action_val, border=1)
            pdf.cell(col_widths[3], 7, details_val, border=1)
            pdf.cell(col_widths[4], 7, page_val, border=1)
            pdf.cell(col_widths[5], 7, ip_val, border=1)
            pdf.ln()
        
        # Retourner le PDF
        pdf_bytes = pdf.output(dest='S')
        # pdf.output() retourne bytes ou bytearray selon la version de fpdf
        if isinstance(pdf_bytes, (str, bytearray)):
            if isinstance(pdf_bytes, str):
                pdf_bytes = pdf_bytes.encode('latin-1')
            else:
                pdf_bytes = bytes(pdf_bytes)
        
        from fastapi.responses import Response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=audit-logs-{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting audit logs to PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# NOTIFICATIONS
# ==========================================

@app.get("/api/notifications")
def get_notifications(
    destination: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Liste les notifications. Destination auto-detectée selon le rôle."""
    role = user.get("role", "")
    nom = (user.get("nom") or "").strip()
    if destination is None:
        destination = "technicien" if role == "Technicien" else "gestionnaire"
    df = lire_notifications_pieces(destination=destination)
    # Pour les techniciens : filtrer par leur nom
    if role == "Technicien" and nom and not df.empty:
        from db_engine import read_sql
        df = df[df["technicien"].fillna("").str.lower().apply(
            lambda t: all(w in t for w in nom.lower().split() if len(w) > 1)
        )]
    return _df_to_records(df)


@app.get("/api/notifications/count")
def get_notification_count(
    destination: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compte les notifications non lues. Destination auto-detectée selon le rôle."""
    role = user.get("role", "")
    nom = (user.get("nom") or "").strip()
    if destination is None:
        destination = "technicien" if role == "Technicien" else "gestionnaire"
    count = compter_notifications_non_lues(destination, technicien=nom if role == "Technicien" else None)
    return {"count": count}


@app.patch("/api/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int, user: dict = Depends(_verify_token)):
    """Marque une notification comme lue."""
    marquer_notification_lue(notif_id)
    return {"ok": True}


@app.patch("/api/notifications/{notif_id}/done")
def mark_notification_done(notif_id: int, user: dict = Depends(_verify_token)):
    """Marque une notification comme traitée."""
    marquer_notification_traitee(notif_id)
    return {"ok": True}


# ==========================================
# SETTINGS / CONFIG
# ==========================================

@app.get("/api/settings")
def get_settings(user: dict = Depends(_verify_token)):
    keys = [
        "nom_organisation", "logo_path", "langue", "theme",
        "taux_horaire_technicien", "telegram_token", "telegram_chat_id",
        "telegram_sav_token", "telegram_sav_chat_id",
        "telegram_manager_token", "telegram_manager_chat_id",
        "telegram_stock_token", "telegram_stock_chat_id",
        "gemini_api_key", "role_permissions",
    ]
    try:
        with get_db() as conn:
            result = {k: "" for k in keys}
            for k in keys:
                row = conn.execute(
                    "SELECT valeur FROM config_client WHERE cle = ?",
                    (k,)
                ).fetchone()
                if row:
                    result[k] = row["valeur"] or ""
            return result
    except Exception as e:
        import traceback
        logger.error(f"Erreur get_settings: {e}\n{traceback.format_exc()}")
        # Fallback: chercher clé par clé
        result = {}
        for k in keys:
            result[k] = get_config(k, "")
        return result


@app.put("/api/settings")
def update_settings(body: dict = Body(...), user: dict = Depends(_verify_token)):
    try:
        logger.info(f"[UPDATE_SETTINGS] Received body: {body}")
        with get_db() as conn:
            for k, v in body.items():
                logger.info(f"[UPDATE_SETTINGS] Saving key='{k}', value_type={type(v).__name__}, value_length={len(str(v))}")
                # Use SQLite-compatible syntax with ? placeholder
                # Note: PgCursorWrapper translates ? to ? and EXCLUDED handles both SQLite and PostgreSQL
                conn.execute(
                    """
                    INSERT INTO config_client (cle, valeur) VALUES (?, ?)
                    ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur
                    """,
                    (k, str(v))
                )
                logger.info(f"[UPDATE_SETTINGS] Successfully saved key='{k}'")
        logger.info(f"[UPDATE_SETTINGS] All settings saved successfully")
        return {"ok": True}
    except Exception as e:
        import traceback
        logger.error(f"[UPDATE_SETTINGS] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur sauvegarde config: {e}")


@app.put("/api/admin/settings")
def update_admin_settings(body: dict = Body(...), user: dict = Depends(_verify_token)):
    """Update admin-only settings (hourly rate, etc). Admin and Manager only."""
    # Check permission - only Admin and Manager can modify
    if user.get("role") not in ["Admin", "Manager"]:
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux Admins et Managers"
        )
    
    try:
        logger.info(f"[UPDATE_ADMIN_SETTINGS] User {user.get('sub')} updating settings: {body}")
        with get_db() as conn:
            for k, v in body.items():
                # Only allow specific admin settings
                allowed_keys = ["taux_horaire_technicien", "langue"]
                if k not in allowed_keys:
                    logger.warning(f"[UPDATE_ADMIN_SETTINGS] Attempt to modify non-allowed key: {k}")
                    continue
                
                logger.info(f"[UPDATE_ADMIN_SETTINGS] Saving key='{k}', value='{v}'")
                conn.execute(
                    """
                    INSERT INTO config_client (cle, valeur) VALUES (?, ?)
                    ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur
                    """,
                    (k, str(v))
                )
        logger.info(f"[UPDATE_ADMIN_SETTINGS] Admin settings saved successfully")
        return {"ok": True}
    except Exception as e:
        import traceback
        logger.error(f"[UPDATE_ADMIN_SETTINGS] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur sauvegarde config admin: {e}")


# ==========================================
# NOTIFICATION SCHEDULES
# ==========================================

@app.get("/api/notification-schedules")
def get_notification_schedules(user: dict = Depends(_verify_token)):
    """Récupère tous les horaires de notification pour les bots Telegram."""
    try:
        schedules = lire_notification_schedules()
        
        # Si aucun horaire n'existe, initialiser avec les valeurs par défaut
        if not schedules:
            default_bots = ['telegram', 'telegram_sav', 'telegram_manager', 'telegram_stock']
            for bot_key in default_bots:
                sauvegarder_notification_schedule(bot_key, 1, 8, 30, '1,2,3,4,5,6,7')
            schedules = lire_notification_schedules()
        
        return {"ok": True, "schedules": schedules}
    except Exception as e:
        import traceback
        logger.error(f"Erreur get_notification_schedules: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur lecture horaires: {e}")


@app.put("/api/notification-schedules")
def update_notification_schedules(body: dict, user: dict = Depends(_verify_token)):
    """Sauvegarde les horaires de notification pour les bots Telegram.
    
    Body format:
    {
        "telegram": {"enabled": 1, "hour": 8, "minute": 30, "days_of_week": "1,2,3,4,5,6,7"},
        "telegram_sav": {...},
        ...
    }
    """
    try:
        sauvegarder_notification_schedules_batch(body)
        return {"ok": True}
    except Exception as e:
        import traceback
        logger.error(f"Erreur update_notification_schedules: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur sauvegarde horaires: {e}")


# ==========================================
# CLIENTS (derived from equipements)
# ==========================================

__all__ = [
    "get_users",
    "create_user",
    "update_user",
    "delete_user",
    "get_audit_log",
    "get_admin_audit_logs",
    "AuditExportRequest",
    "export_audit_logs_pdf",
    "get_notifications",
    "get_notification_count",
    "mark_notification_read",
    "mark_notification_done",
    "get_settings",
    "update_settings",
    "update_admin_settings",
    "get_notification_schedules",
    "update_notification_schedules",
]

