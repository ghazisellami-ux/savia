"""Planning, comparison, rescheduling, and planning-PDF routes."""

from html import escape

from api.runtime import (
    Depends,
    HTTPException,
    Optional,
    Query,
    _tech_name_or_username_matches,
    ajouter_planning,
    app,
    base64,
    datetime,
    get_db,
    lire_equipements,
    lire_planning,
    log_audit,
    logger,
    os,
    status,
    supprimer_planning,
    tempfile,
    update_planning_statut,
)
from api.security import (
    Depends,
    HTTPException,
    Optional,
    _check_create_permission,
    _verify_token,
    require_roles,
    get_db,
)
from services.scheduled_jobs import (
    _df_to_records,
    _send_telegram_bot,
    get_db,
    lire_equipements,
    lire_planning,
    logger,
    send_telegram_reliably,
    sync_planning_to_interventions,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    Optional,
    _get_client_filter,
    _verify_token,
    app,
    datetime,
    get_db,
    lire_equipements,
    log_audit,
    logger,
)

@app.get("/api/planning")
def get_planning(
    machine: Optional[str] = None,
    statut: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    # Garantit que le planning et les listes d'interventions sont cohérents
    # même si le worker quotidien a été indisponible le jour J.
    try:
        sync_planning_to_interventions(notify=False)
    except Exception as exc:
        logger.warning("Planning sync before planning listing failed: %s", exc)

    df = lire_planning(machine=machine, statut=statut)
    
    # Si le user est un Technicien → filtrer automatiquement ses plannings
    if user.get("role") == "Technicien" and not df.empty:
        user_nom_complet = (user.get("nom") or "").strip()
        user_username = (user.get("sub") or "").strip()
        technician_id = None
        try:
            with get_db() as conn:
                tech_row = conn.execute(
                    """SELECT id FROM techniciens
                       WHERE LOWER(BTRIM(COALESCE(username, ''))) = LOWER(BTRIM(%s))
                          OR LOWER(BTRIM(CONCAT(prenom, ' ', nom))) = LOWER(BTRIM(%s))
                          OR LOWER(BTRIM(CONCAT(nom, ' ', prenom))) = LOWER(BTRIM(%s))
                       ORDER BY id LIMIT 1""",
                    (user_username, user_nom_complet, user_nom_complet),
                ).fetchone()
                technician_id = int(tech_row["id"]) if tech_row else None
        except Exception as exc:
            logger.warning("Unable to resolve planning technician ID for %s: %s", user_username, exc)
        # Filter by name (primary) or username (secondary)
        if technician_id is not None and "technicien_ids" in df.columns:
            def contains_technician(value):
                try:
                    import json
                    values = json.loads(value) if isinstance(value, str) else value
                    return technician_id in [int(item) for item in (values or [])]
                except (TypeError, ValueError, json.JSONDecodeError):
                    return False
            id_matches = df["technicien_ids"].apply(contains_technician)
            name_matches = df["technicien_assigne"].astype(str).apply(
                lambda t: _tech_name_or_username_matches(user_nom_complet, t) or _tech_name_or_username_matches(user_username, t)
            ) if "technicien_assigne" in df.columns else False
            df = df[id_matches | name_matches]
        elif user_nom_complet and "technicien_assigne" in df.columns:
            df = df[df["technicien_assigne"].astype(str).apply(
                lambda t: _tech_name_or_username_matches(user_nom_complet, t) or _tech_name_or_username_matches(user_username, t)
            )]
    
    # Pour Lecteur : filtrer par les machines de son client
    client_filter = _get_client_filter(user)
    if client_filter and not df.empty:
        df_eq = lire_equipements()
        if not df_eq.empty and "Client" in df_eq.columns and "Nom" in df_eq.columns:
            machines_client = set(
                df_eq[df_eq["Client"].astype(str).str.lower() == client_filter.lower()]["Nom"].tolist()
            )
            if "machine" in df.columns:
                df = df[df["machine"].isin(machines_client)]
    return _df_to_records(df)


@app.post("/api/planning")
def create_planning(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    try:
        planning_id = ajouter_planning(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def notification_value(key: str, fallback: str = "", *, limit: int = 800) -> str:
        raw_value = str(body.get(key, fallback) or "").strip()
        return escape(raw_value[:limit]) if raw_value else "Non renseigné"

    raw_date = str(body.get("date_prevue", "") or "").strip()
    try:
        scheduled_date = datetime.fromisoformat(raw_date[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        scheduled_date = notification_value("date_prevue")

    notification_lines = [
        f"📅 <b>INTERVENTION PLANIFIÉE — #{planning_id}</b>",
        "",
        f"🔹 Type : <b>{notification_value('type_maintenance', 'Préventive')}</b>",
        f"🔧 Équipement : <b>{notification_value('machine')}</b>",
        f"🏥 Client / site : <b>{notification_value('client')}</b>",
        f"📆 Date prévue : <b>{scheduled_date}</b>",
        f"👷 Technicien(s) : {notification_value('technicien_assigne')}",
        f"🔁 Récurrence : {notification_value('recurrence')}",
    ]
    if str(body.get("description") or "").strip():
        notification_lines.append(f"📝 Description : {notification_value('description')}")
    if str(body.get("notes") or "").strip():
        notification_lines.append(f"📌 Notes : {notification_value('notes')}")
    notification_lines.extend(("", f"🕐 Planifiée le {datetime.now().strftime('%d/%m/%Y %H:%M')}"))

    # This immediate message complements, rather than replaces, the daily
    # reminder emitted by the scheduler. The outbox retries a failed send.
    telegram_sent = send_telegram_reliably(
        "telegram",
        "\n".join(notification_lines),
        f"planning:{planning_id}:created",
    )
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "machine": body.get("machine", ""),
        "type": body.get("type_maintenance", ""),
        "date": body.get("date_prevue", ""),
    }, ensure_ascii=False)
    log_audit(username, "CREATE_PLANNING", details, "planning")
    
    return {"ok": True, "id": planning_id, "telegram_sent": telegram_sent}


@app.post("/api/planning/sync")
def force_planning_sync(user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """Force la synchronisation planning -> interventions pour aujourd'hui."""
    created = sync_planning_to_interventions()
    return {"ok": True, "created": len(created), "interventions": created}


@app.post("/api/planning/pdf")
def generate_planning_pdf(body: dict = {}, user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
    """Generate a maintenance planning PDF using FPDF with proper header.
    Supports date range filtering. Uses landscape orientation for better column visibility."""
    from io import BytesIO
    from fastapi.responses import Response
    from datetime import datetime
    from fpdf import FPDF

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        rows = body.get("rows", [])
        logger.info(f"[PDF] Received {len(rows)} rows from frontend")
        filter_label = body.get("filter_label", "Tous les clients")
        company_name = body.get("company_name", "SAVIA")
        company_logo = body.get("company_logo", "")

        # Use landscape orientation (L) instead of portrait
        pdf = FPDF(orientation='L')
        pdf.set_auto_page_break(auto=True, margin=10)

        # Page 1: Header with logo
        pdf.add_page()
        # Use built-in Arial font instead of DejaVu
        pdf.set_font("Arial", size=10)

        # Left: SAVIA logo
        if os.path.exists(SAVIA_LOGO):
            pdf.image(SAVIA_LOGO, x=10, y=10, w=30)
        
        # Right: Company logo (uploaded in admin)
        if company_logo:
            try:
                # company_logo is base64 data URL: "data:image/png;base64,..."
                if company_logo.startswith('data:'):
                    # Extract base64 part
                    base64_data = company_logo.split(',')[1]
                    image_bytes = base64.b64decode(base64_data)
                    
                    # Create temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                        tmp.write(image_bytes)
                        tmp_path = tmp.name
                    
                    # Add company logo to top right (adjusted for landscape page width ~277mm)
                    # x=240 aligns it to right of landscape page, y=10, w=35 for width
                    pdf.image(tmp_path, x=240, y=10, w=35)
                    
                    # Clean up temp file
                    os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to add company logo: {e}")
        
        # Right: Company info (below logo, adjusted for landscape)
        pdf.set_xy(210, 50)
        pdf.set_font("Arial", 'B', size=12)
        pdf.cell(0, 5, company_name, ln=True, align='R')
        pdf.set_xy(210, 55)
        pdf.set_font("Arial", size=9)
        pdf.cell(0, 4, f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='R')
        
        # Title
        pdf.set_xy(10, 50)
        pdf.set_font("Arial", 'B', size=16)
        pdf.cell(0, 10, "PLANNING MAINTENANCE", ln=True)
        
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 5, f"Filtre: {filter_label}", ln=True)
        pdf.cell(0, 3, f"Nombre d'interventions: {len(rows)}", ln=True)
        pdf.ln(5)

        # Table header - optimized for landscape width
        # Landscape page width is approximately 277mm, with 10mm margins = 257mm available
        pdf.set_font("Arial", 'B', size=9)
        col_widths = [30, 38, 28, 38, 38, 28, 78]  # Notes: 78mm
        headers = ["Date", "Machine", "Type", "Technicien", "Client", "Statut", "Notes"]
        
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 7, header, border=1, align='C')
        pdf.ln()

        # Table data - Using multi_cell for notes to support line wrapping
        pdf.set_font("Arial", size=8)
        
        for row in rows:
            # Extract data
            date_str = row.get("date_planifiee", "")[:10] if row.get("date_planifiee") else ""
            machine = str(row.get("machine", ""))[:25]
            type_maint = str(row.get("type_maintenance", ""))[:15]
            tech = str(row.get("technicien", ""))[:20]
            client = str(row.get("client", ""))[:20]
            statut = str(row.get("statut", ""))[:12]
            notes_full = str(row.get("notes", ""))
            
            # For notes with potential line breaks, we need multi-line support
            # Calculate how many lines the notes will need (approximately 11 chars per line at this width and font size)
            line_width_mm = 78  # col_widths[6]
            chars_per_line = 45  # approximate for Arial 8pt at 78mm
            
            # Split notes into lines
            notes_lines = []
            remaining = notes_full
            while remaining:
                if len(remaining) <= chars_per_line:
                    notes_lines.append(remaining)
                    break
                else:
                    split_pos = remaining.rfind(' ', 0, chars_per_line)
                    if split_pos == -1:
                        split_pos = chars_per_line
                    notes_lines.append(remaining[:split_pos])
                    remaining = remaining[split_pos:].lstrip()
            
            # Limit to max 3 lines to avoid oversized rows
            if len(notes_lines) > 3:
                notes_lines = notes_lines[:3]
                notes_lines[-1] = notes_lines[-1][:chars_per_line-3] + "..."
            
            # Ensure at least one line
            if not notes_lines:
                notes_lines = [""]
            
            # Row height depends on number of notes lines (5mm per line)
            num_lines = len(notes_lines)
            row_height = 5 * num_lines
            
            # Get current Y position
            current_y = pdf.get_y()
            # Page bottom is around 190mm with 10mm margin
            if current_y + row_height > 190:
                # Add new page and re-draw header
                pdf.add_page()
                pdf.set_font("Arial", 'B', size=9)
                for i, header in enumerate(headers):
                    pdf.cell(col_widths[i], 7, header, border=1, align='C')
                pdf.ln()
                pdf.set_font("Arial", size=8)
            
            # Draw row cells - use manual positioning for multi-line notes
            y_start = pdf.get_y()
            
            # Draw all columns except notes first
            pdf.set_xy(10, y_start)
            pdf.cell(col_widths[0], row_height, date_str, border=1, align='C')
            
            pdf.set_xy(10 + col_widths[0], y_start)
            pdf.cell(col_widths[1], row_height, machine, border=1, align='L')
            
            pdf.set_xy(10 + col_widths[0] + col_widths[1], y_start)
            pdf.cell(col_widths[2], row_height, type_maint, border=1, align='L')
            
            pdf.set_xy(10 + col_widths[0] + col_widths[1] + col_widths[2], y_start)
            pdf.cell(col_widths[3], row_height, tech, border=1, align='L')
            
            x_pos = 10 + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3]
            pdf.set_xy(x_pos, y_start)
            pdf.cell(col_widths[4], row_height, client, border=1, align='L')
            
            x_pos += col_widths[4]
            pdf.set_xy(x_pos, y_start)
            pdf.cell(col_widths[5], row_height, statut, border=1, align='C')
            
            # Draw notes cell with border and multi-line content
            x_pos += col_widths[5]
            pdf.set_xy(x_pos, y_start)
            pdf.rect(x_pos, y_start, col_widths[6], row_height, 'D')
            
            # Draw each line of notes
            for line_num, notes_line in enumerate(notes_lines):
                line_y = y_start + (line_num * 5) + 1
                pdf.set_xy(x_pos + 1, line_y)
                pdf.cell(col_widths[6] - 2, 4.5, notes_line, border=0, align='L')
            
            # Move to next row
            pdf.set_y(y_start + row_height)

        # Footer
        pdf.set_y(-15)
        pdf.set_font("Arial", size=8)
        pdf.cell(0, 5, f"Page {pdf.page_no()}", align='C')

        pdf_output = pdf.output(dest='S')
        # pdf.output(dest='S') returns bytearray in FPDF2
        if isinstance(pdf_output, bytearray):
            pdf_bytes = bytes(pdf_output)
        elif isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=planning.pdf"}
        )
    except Exception as e:
        logger.error(f"Error generating planning PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF: {str(e)}"
        )


@app.post("/api/planning/comparateur/pdf")
def export_comparateur_pdf(body: dict, user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """
    Generate PDF from comparateur data.
    Input: comparateur data from GET /api/planning/{id}/comparateur
    Output: PDF file
    """
    try:
        from fpdf import FPDF
        from datetime import datetime
        
        # Get comparateur data from body
        data = body
        
        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("DejaVu", size=12)
        
        # Title
        pdf.set_font("DejaVu", 'B', size=16)
        pdf.cell(0, 10, "RAPPORT COMPARATEUR PLANNING", ln=True, align='C')
        pdf.ln(5)
        
        # Timestamp
        pdf.set_font("DejaVu", size=9)
        pdf.cell(0, 8, f"Généré le: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
        pdf.ln(3)
        
        # Equipment info
        pdf.set_font("DejaVu", 'B', size=11)
        pdf.cell(0, 8, "INFORMATIONS ÉQUIPEMENT", ln=True)
        pdf.set_font("DejaVu", size=10)
        pdf.cell(0, 7, f"Machine: {data.get('machine', '')}", ln=True)
        pdf.cell(0, 7, f"Client: {data.get('client', '')}", ln=True)
        pdf.cell(0, 7, f"Type: {data.get('type_maintenance', '')}", ln=True)
        pdf.cell(0, 7, f"Description: {data.get('description', '')}", ln=True)
        pdf.ln(3)
        
        # Real planning
        pdf.set_font("DejaVu", 'B', size=11)
        pdf.cell(0, 8, "PLANNING RÉEL (Nouvelle date)", ln=True)
        pdf.set_font("DejaVu", size=10)
        real = data.get('real', {})
        pdf.cell(0, 7, f"Date: {real.get('date', '')}", ln=True)
        pdf.cell(0, 7, f"Technicien: {real.get('technicien', '')}", ln=True)
        pdf.cell(0, 7, f"Statut: {real.get('statut', '')}", ln=True)
        pdf.ln(3)
        
        # Ghost planning
        if data.get('has_ghost'):
            pdf.set_font("DejaVu", 'B', size=11)
            pdf.cell(0, 8, "PLANNING DÉCALÉ (Date originale)", ln=True)
            pdf.set_font("DejaVu", size=10)
            ghost = data.get('ghost', {})
            pdf.cell(0, 7, f"Date: {ghost.get('date', '')}", ln=True)
            pdf.cell(0, 7, f"Technicien: {ghost.get('technicien', '')}", ln=True)
            pdf.cell(0, 7, f"Statut: {ghost.get('statut', '')}", ln=True)
            pdf.ln(3)
        
        # Differences
        pdf.set_font("DejaVu", 'B', size=11)
        pdf.cell(0, 8, "CHANGEMENTS", ln=True)
        pdf.set_font("DejaVu", size=10)
        diff = data.get('differences', {})
        if diff.get('date_changed'):
            old_date = diff.get('old_date', '')
            new_date = diff.get('new_date', '')
            pdf.cell(0, 7, f"Date modifiée: {old_date} → {new_date}", ln=True)
        if diff.get('technicien_changed'):
            old_tech = diff.get('old_technicien', 'Non assigné')
            new_tech = diff.get('new_technicien', 'Non assigné')
            pdf.cell(0, 7, f"Technicien modifié: {old_tech} → {new_tech}", ln=True)
        pdf.ln(3)
        
        # Reasons
        reasons = data.get('reasons', [])
        if reasons:
            pdf.set_font("DejaVu", 'B', size=11)
            pdf.cell(0, 8, "RAISONS DU DÉCALAGE", ln=True)
            pdf.set_font("DejaVu", size=10)
            for idx, reason in enumerate(reasons, 1):
                # Use multi_cell for text wrapping
                pdf.multi_cell(0, 5, f"{idx}. {reason}")
            pdf.ln(2)
        
        # Footer
        pdf.set_font("DejaVu", size=8)
        pdf.ln(5)
        pdf.cell(0, 5, "---", ln=True)
        pdf.cell(0, 5, "Rapport généré automatiquement par SAVIA", align='C')
        
        # Return PDF as blob
        from io import BytesIO
        pdf_output = pdf.output(dest='S')
        # pdf.output(dest='S') returns bytearray in FPDF2
        if isinstance(pdf_output, bytearray):
            pdf_bytes = bytes(pdf_output)
        elif isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename=comparateur.pdf'}
        )
    except Exception as e:
        logger.error(f"Error generating comparateur PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF: {str(e)}"
        )


@app.get("/api/planning/{planning_id}/comparateur")
def get_planning_comparateur(planning_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """
    Get comparison between real planning and ghost (décalé) entry.
    Returns data for generating comparateur export (planning réel vs planning décalé).
    Accepts either the real planning ID or the ghost planning ID.
    """
    try:
        with get_db() as conn:
            # Check if the provided ID is a ghost entry
            test_entry = conn.execute(
                "SELECT * FROM planning_maintenance WHERE id = %s",
                (planning_id,)
            ).fetchone()
            
            if not test_entry:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Planning entry not found"
                )
            
            # If the provided ID is a ghost entry, use its original_planning_id as the real ID
            test_dict = dict(test_entry)
            if test_dict.get("is_ghost"):
                real_planning_id = test_dict.get("original_planning_id")
                if not real_planning_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Ghost entry has no associated original planning"
                    )
            else:
                real_planning_id = planning_id
            
            # Get the real planning entry
            real = conn.execute(
                "SELECT * FROM planning_maintenance WHERE id = %s AND is_ghost = false",
                (real_planning_id,)
            ).fetchone()
            
            if not real:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Real planning entry not found"
                )
            
            # Get the ghost entry associated with this planning
            ghost = conn.execute(
                "SELECT * FROM planning_maintenance WHERE original_planning_id = %s AND is_ghost = true",
                (real_planning_id,)
            ).fetchone()
            
            # Extract reason from notes (format: "[Raison décalage] text")
            reason_lines = []
            if ghost:
                ghost_notes = ghost.get("notes", "") or ""
                # Extract all "[Raison décalage]" lines
                for line in ghost_notes.split("|"):
                    line = line.strip()
                    if line.startswith("[Raison décalage]"):
                        reason = line.replace("[Raison décalage]", "").strip()
                        reason_lines.append(reason)
            
            # Build comparison data
            real_dict = dict(real) if real else {}
            ghost_dict = dict(ghost) if ghost else {}
            
            comparison = {
                "planning_id": real_planning_id,
                "machine": real_dict.get("machine", ""),
                "client": real_dict.get("client", ""),
                "type_maintenance": real_dict.get("type_maintenance", ""),
                "description": real_dict.get("description", ""),
                
                # Real planning (new date after reschedule)
                "real": {
                    "date": real_dict.get("date_prevue", ""),
                    "technicien": real_dict.get("technicien_assigne", ""),
                    "statut": real_dict.get("statut", ""),
                },
                
                # Ghost planning (original date - décalé)
                "ghost": {
                    "date": ghost_dict.get("date_prevue", "") if ghost else None,
                    "technicien": ghost_dict.get("technicien_assigne", "") if ghost else None,
                    "statut": ghost_dict.get("statut", "") if ghost else None,
                } if ghost else None,
                
                # Differences
                "differences": {
                    "date_changed": real_dict.get("date_prevue") != ghost_dict.get("date_prevue") if ghost else False,
                    "technicien_changed": real_dict.get("technicien_assigne") != ghost_dict.get("technicien_assigne") if ghost else False,
                    "old_date": ghost_dict.get("date_prevue") if ghost else None,
                    "new_date": real_dict.get("date_prevue"),
                    "old_technicien": ghost_dict.get("technicien_assigne") if ghost else None,
                    "new_technicien": real_dict.get("technicien_assigne"),
                },
                
                # Reschedule reasons (accumulated)
                "reasons": reason_lines if reason_lines else [],
                
                # Meta
                "has_ghost": ghost is not None,
            }
            
            return comparison
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting planning comparateur for {planning_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching comparateur data: {str(e)}"
        )


@app.get("/api/planning/comparateur-periode")
def get_planning_comparateur_periode(
    date_debut: str = Query(..., description="Start date (YYYY-MM-DD)"),
    date_fin: str = Query(..., description="End date (YYYY-MM-DD)"),
    user: dict = Depends(_verify_token)
):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """
    Get all reschedules (comparisons) within a date range.
    Returns all ghost entries (décalés) between date_debut and date_fin.
    """
    try:
        # Validate dates
        try:
            from datetime import datetime
            d_debut = datetime.strptime(date_debut, "%Y-%m-%d")
            d_fin = datetime.strptime(date_fin, "%Y-%m-%d")
            if d_debut > d_fin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="date_debut must be before date_fin"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        with get_db() as conn:
            # Get all ghost entries (décalés) with their original entries
            # Filter by ghost entry's date_prevue (the rescheduled date)
            ghosts = conn.execute(
                """SELECT * FROM planning_maintenance 
                   WHERE is_ghost = true 
                   AND date_prevue BETWEEN %s AND %s
                   ORDER BY date_prevue ASC""",
                (date_debut, date_fin)
            ).fetchall()
            
            comparisons = []
            for ghost_row in ghosts:
                ghost_dict = dict(ghost_row)
                original_planning_id = ghost_dict.get("original_planning_id")
                
                if not original_planning_id:
                    continue  # Skip if no original planning
                
                # Get the real planning entry
                real = conn.execute(
                    "SELECT * FROM planning_maintenance WHERE id = %s AND is_ghost = false",
                    (original_planning_id,)
                ).fetchone()
                
                if not real:
                    continue
                
                real_dict = dict(real)
                
                # Extract reason from notes of the REAL entry (not the ghost)
                # The reschedule reason is stored in the real entry's notes
                reason_lines = []
                real_notes = real_dict.get("notes", "") or ""
                for line in real_notes.split("|"):
                    line = line.strip()
                    if line.startswith("[Raison décalage]"):
                        reason = line.replace("[Raison décalage]", "").strip()
                        reason_lines.append(reason)
                
                # For clarity: ghost = original date, real = rescheduled date
                # Calculate days difference (rescheduled - original)
                try:
                    from datetime import datetime, date
                    ghost_date = ghost_dict.get("date_prevue")
                    real_date = real_dict.get("date_prevue")
                    
                    # Convert to date objects if they're strings
                    if isinstance(ghost_date, str):
                        ghost_date = datetime.strptime(ghost_date, "%Y-%m-%d").date()
                    if isinstance(real_date, str):
                        real_date = datetime.strptime(real_date, "%Y-%m-%d").date()
                    
                    if ghost_date and real_date:
                        days_diff = (real_date - ghost_date).days
                    else:
                        days_diff = 0
                except Exception as e:
                    logger.error(f"Error calculating days diff: {e}, ghost_date={ghost_dict.get('date_prevue')}, real_date={real_dict.get('date_prevue')}")
                    days_diff = 0
                
                comparison = {
                    "planning_id": original_planning_id,
                    "ghost_id": ghost_dict.get("id"),
                    "machine": real_dict.get("machine", ""),
                    "client": real_dict.get("client", ""),
                    "type_maintenance": real_dict.get("type_maintenance", ""),
                    "old_date": ghost_dict.get("date_prevue"),  # Original date (ghost entry)
                    "new_date": real_dict.get("date_prevue"),   # Rescheduled date (real entry)
                    "days_difference": days_diff,  # This is now (real - ghost) = newer - older
                    "old_technicien": ghost_dict.get("technicien_assigne", ""),
                    "new_technicien": real_dict.get("technicien_assigne", ""),
                    "statut": real_dict.get("statut", ""),
                    "reasons": reason_lines if reason_lines else [],
                }
                comparisons.append(comparison)
            
            return {
                "total": len(comparisons),
                "period": {"debut": date_debut, "fin": date_fin},
                "comparisons": comparisons
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting planning comparateur-periode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching comparateur data: {str(e)}"
        )


@app.put("/api/planning/{planning_id}")
def update_planning_status(planning_id: int, body: dict, user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    update_planning_statut(planning_id, body.get("statut", ""), body.get("date_realisee"))
    return {"ok": True}


@app.put("/api/planning/{planning_id}/reschedule")
def reschedule_planning(planning_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Reschedule an intervention (change date and/or technicians).
    Admin, Manager, and Responsable Technique can perform this action.
    Creates a greyed-out "Décalé" entry at the old date for audit trail.
    """
    import json

    # Check authorization for planning assignment and rescheduling.
    if user.get("role") not in ["Admin", "Manager", "Responsable Technique"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les Admins, Managers et Responsables Techniques peuvent assigner ou décaler une intervention"
        )
    
    ph = "%s"  # PostgreSQL placeholder

    def date_only(value):
        """Normalise une date SQL ou une date ISO pour comparer uniquement le jour."""
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()[:10]
        return str(value).strip()[:10]

    def is_true(value):
        """Accepte les booléens PostgreSQL et leurs éventuelles formes texte."""
        return value is True or str(value).strip().lower() in {"1", "true", "t", "yes"}
    
    new_date = body.get("date_planifiee")
    new_equipment_id = body.get("equipement_id")
    if new_equipment_id not in (None, ""):
        try:
            new_equipment_id = int(new_equipment_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Identifiant d'équipement invalide")
    new_technicians = body.get("technicien_assigne")
    new_technician_ids = body.get("technicien_ids") or []
    if isinstance(new_technician_ids, str):
        try:
            new_technician_ids = json.loads(new_technician_ids)
        except (TypeError, ValueError):
            new_technician_ids = []
    new_technician_ids = [int(value) for value in new_technician_ids if str(value).isdigit() and int(value) > 0]
    reason = body.get("reason", "").strip()  # ← Add reason support
    
    if not new_date and new_technicians is None and new_equipment_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least date_planifiee or technicien_assigne must be provided"
        )
    
    try:
        with get_db() as conn:
            # Get current planning item
            current = conn.execute(
                f"SELECT * FROM planning_maintenance WHERE id = {ph}",
                (planning_id,)
            ).fetchone()
            
            if not current:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Planning item not found"
                )

            if new_equipment_id is not None:
                equipment_row = conn.execute(
                    "SELECT id, nom, client FROM equipements WHERE id = %s",
                    (new_equipment_id,),
                ).fetchone()
                if not equipment_row:
                    raise HTTPException(status_code=404, detail="Équipement introuvable")
                equipment_client = str(equipment_row.get("client") or "").strip()
                current_client = str(current.get("client") or "").strip()
                if equipment_client and current_client and equipment_client.casefold() != current_client.casefold():
                    raise HTTPException(status_code=409, detail="L'équipement ne correspond pas au client du planning")

            import unicodedata

            def normalized_status(value):
                return unicodedata.normalize("NFKD", str(value or "")).encode(
                    "ascii", "ignore"
                ).decode().lower().strip()

            def is_closed_status(value):
                return normalized_status(value) in {
                    "cloturee", "terminee", "realisee", "annulee"
                }

            if current.get("is_ghost"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Une entrée historique décalée ne peut pas être reportée"
                )

            if is_closed_status(current.get("statut")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Une intervention clôturée ne peut pas être reportée"
                )

            linked_interventions = conn.execute(
                "SELECT id, statut FROM interventions WHERE planning_id = %s",
                (planning_id,)
            ).fetchall()
            if any(is_closed_status(row.get("statut")) for row in linked_interventions):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Une intervention déjà clôturée ne peut pas être reportée"
                )

            # Legacy rows created before planning_id was populated can still
            # be matched by machine/date. Protect those closed interventions
            # before changing the planning entry.
            if not linked_interventions and current.get("machine") and current.get("date_prevue"):
                legacy_intervention = conn.execute(
                    """
                    SELECT statut
                    FROM interventions
                    WHERE machine = %s AND date = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (current.get("machine"), str(current.get("date_prevue"))[:10])
                ).fetchone()
                if legacy_intervention and is_closed_status(legacy_intervention.get("statut")):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Une intervention déjà clôturée ne peut pas être reportée"
                    )
            
            old_date = current.get("date_prevue")
            old_date_iso = date_only(old_date)
            target_date = date_only(new_date or old_date)
            today_iso = datetime.now().date().isoformat()
            
            # Update the main planning entry
            update_data = {}
            if new_date:
                update_data["date_prevue"] = new_date
            if new_technicians is not None:
                update_data["technicien_assigne"] = new_technicians
                update_data["technicien_id"] = new_technician_ids[0] if new_technician_ids else None
                update_data["technicien_ids"] = json.dumps(new_technician_ids)
            if new_equipment_id is not None:
                update_data["equipement_id"] = new_equipment_id
            
            # ← Add reason to notes if provided
            if reason:
                old_notes = current.get("notes", "")
                new_notes = f"[Raison décalage] {reason}"
                if old_notes:
                    new_notes = f"{old_notes} | {new_notes}"
                update_data["notes"] = new_notes
            
            if update_data:
                set_clause = ", ".join([f"{k} = {ph}" for k in update_data.keys()])
                values = list(update_data.values()) + [planning_id]
                conn.execute(
                    f"UPDATE planning_maintenance SET {set_clause} WHERE id = {ph}",
                    values
                )
                conn.commit()
                logger.info(f"Planning {planning_id} updated: {update_data}")
            
            # Create a greyed-out "Décalé" entry at the old date AFTER updating (separate transaction)
            # BUT: Only if the DATE ACTUALLY CHANGED (not if only technicien changed)
            # AND only if this is NOT already a ghost entry
            is_current_ghost = is_true(current.get("is_ghost", False))
            
            # Check if date actually changed (compare as strings for consistency)
            date_has_changed = bool(new_date) and date_only(new_date) != old_date_iso
            
            if date_has_changed and not is_current_ghost:
                try:
                    old_machine = current.get("machine", "")
                    old_client = current.get("client", "")
                    old_description = current.get("description", "")
                    old_notes = current.get("notes", "")
                    old_type = current.get("type_maintenance", "Préventive")
                    
                    # Check if a ghost ALREADY EXISTS for this ORIGINAL planning
                    # Using original_planning_id to link ghost to its source intervention
                    # This prevents duplicate ghosts when same intervention is rescheduled multiple times
                    existing_ghost = conn.execute(
                        f"SELECT id FROM planning_maintenance WHERE original_planning_id = {ph} AND is_ghost = true",
                        (planning_id,)
                    ).fetchone()
                    
                    if not existing_ghost:
                        # Create a ghost from the ORIGINAL intervention at the old date
                        # Set original_planning_id to track that this ghost belongs to planning_id
                        insert_sql = f"""INSERT INTO planning_maintenance 
                               (machine, client, date_prevue, technicien_assigne, type_maintenance, 
                                recurrence, statut, description, notes, is_ghost, original_planning_id)
                               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"""
                        conn.execute(
                            insert_sql,
                            (old_machine, old_client, old_date_iso, "", old_type,
                             "Aucune", "Décalé", f"[DÉCALÉ] {old_description}", old_notes, True, planning_id)
                        )
                        conn.commit()
                        logger.info(f"✅ Ghost entry created for planning {planning_id}: {old_machine} on {old_date}")
                    else:
                        # Ghost already exists - update its notes to accumulate all reschedule reasons
                        ghost_id = existing_ghost.get("id")
                        ghost_current = conn.execute(
                            f"SELECT notes FROM planning_maintenance WHERE id = {ph}",
                            (ghost_id,)
                        ).fetchone()
                        ghost_notes = ghost_current.get("notes", "") if ghost_current else ""
                        
                        # Append reason if provided and not already there
                        if reason:
                            new_reason_line = f"[Raison décalage] {reason}"
                            if new_reason_line not in ghost_notes:
                                if ghost_notes:
                                    updated_notes = f"{ghost_notes} | {new_reason_line}"
                                else:
                                    updated_notes = new_reason_line
                                conn.execute(
                                    f"UPDATE planning_maintenance SET notes = {ph} WHERE id = {ph}",
                                    (updated_notes, ghost_id)
                                )
                                conn.commit()
                                logger.info(f"Ghost {ghost_id} notes updated with reschedule reason")
                        logger.info(f"Ghost already exists for planning {planning_id}, notes accumulated")
                except Exception as e:
                    logger.warning(f"Could not create ghost entry for planning {planning_id}: {e}")
                    # Don't fail if ghost entry creation fails - main update already succeeded
            
            # Log audit
            log_audit(
                user.get("sub", "unknown"),
                "RESCHEDULE_PLANNING",
                f"Planning {planning_id}: {update_data}"
            )
            
            # Notify the technician bot about assignment and/or rescheduling.
            if date_has_changed or new_technicians or new_equipment_id is not None:
                try:
                    machine = current.get("machine", "?")
                    client = current.get("client", "")
                    tech_list = [t.strip() for t in (new_technicians or "").split(",") if t.strip()]

                    if date_has_changed:
                        title = "Intervention décalée"
                        msg = f"🔄 <b>{title}</b>\n"
                        msg += f"<i>Nouvelle date prévue : {target_date}</i>\n"
                    else:
                        title = "Technicien(s) assigné(s)"
                        msg = f"🔧 <b>{title}</b>\n"

                    if tech_list:
                        msg += f"<i>{len(tech_list)} technicien(s) assigné(s) :</i>\n"
                        for tech in tech_list:
                            msg += f"  • <b>{tech}</b>\n"

                    msg += f"\n<b>Détails :</b>\n  📦 Équipement : {machine}\n"
                    if client:
                        msg += f"  🏢 Client : {client}\n"
                    msg += f"  📅 Date : {target_date}\n"
                    if reason:
                        msg += f"  💬 Raison : {reason}\n"
                    
                    msg += f"\n📱 Consultez le PWA pour plus de détails."
                    
                    # Send to general telegram bot (technicien will receive it)
                    _send_telegram_bot("telegram", msg)
                    logger.info(
                        f"Telegram planning notification sent for planning {planning_id}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send Telegram notification for planning {planning_id}: {e}")
            
            # Keep a linked intervention aligned with the new planning date.
            # Future interventions are created only when their planned day is reached.
            if date_has_changed or new_technicians is not None or new_equipment_id is not None:
                logger.info(f"🔧 Processing technician assignment: {new_technicians} for planning #{planning_id}")
                try:
                    machine = current.get("machine", "")
                    date_prevue = target_date or datetime.now().isoformat()[:10]
                    
                    # Find the intervention linked to this planning via planning_id
                    linked_intervention = conn.execute(
                        "SELECT id, planning_id FROM interventions WHERE planning_id = %s ORDER BY id DESC LIMIT 1",
                        (planning_id,)
                    ).fetchone()
                    
                    # Do not fall back to machine + date: duplicate equipment
                    # names can point to another serial number. Legacy rows
                    # without planning_id are repaired only explicitly.
                    
                    # Existing interventions follow the new planning date.
                    if linked_intervention:
                        intervention_id = linked_intervention['id']
                        intervention_updates = []
                        intervention_values = []
                        if date_has_changed:
                            intervention_updates.append("date = %s")
                            intervention_values.append(date_prevue)
                        if new_technicians is not None:
                            intervention_updates.append("technicien = %s")
                            intervention_values.append(new_technicians)
                            intervention_updates.append("technicien_id = %s")
                            intervention_values.append(new_technician_ids[0] if new_technician_ids else None)
                        if new_equipment_id is not None:
                            intervention_updates.append("equipement_id = %s")
                            intervention_values.append(new_equipment_id)
                            intervention_updates.append("machine = %s")
                            intervention_values.append(equipment_row["nom"])
                        if linked_intervention.get("planning_id") != planning_id:
                            intervention_updates.append("planning_id = %s")
                            intervention_values.append(planning_id)
                        if intervention_updates:
                            conn.execute(
                                f"UPDATE interventions SET {', '.join(intervention_updates)} WHERE id = %s",
                                intervention_values + [intervention_id]
                            )
                        logger.info(f"  ✅ Found existing intervention #{intervention_id}")

                    # Create an intervention immediately only for today or a
                    # past date. Future items wait for the daily synchronizer.
                    elif date_prevue <= today_iso:
                        logger.info(f"  ❌ No intervention found, creating one...")
                        
                        client = current.get("client", "")
                        description = current.get("description", "") or f"Maintenance préventive — {machine}"
                        type_maintenance = current.get("type_maintenance", "Préventive")
                        notes = f"[{client}] Maintenance planifiée #{planning_id}" if client else f"Maintenance planifiée #{planning_id}"
                        
                        logger.info(f"  Inserting intervention: date={date_prevue}, machine={machine}, technicien={new_technicians}")
                        
                        conn.execute(
                            """INSERT INTO interventions
                               (date, machine, equipement_id, technicien_id, technicien, type_intervention, description,
                                statut, priorite, notes, planning_id)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                            (date_prevue, equipment_row["nom"] if new_equipment_id is not None else machine, new_equipment_id if new_equipment_id is not None else current.get("equipement_id"), new_technician_ids[0] if new_technician_ids else None, new_technicians, type_maintenance, description,
                             "En cours", "Moyenne", notes, planning_id)
                        )
                        
                        # Get the newly created intervention ID
                        new_intervention = conn.execute(
                            "SELECT id FROM interventions WHERE planning_id = %s ORDER BY id DESC LIMIT 1",
                            (planning_id,)
                        ).fetchone()
                        
                        if new_intervention:
                            intervention_id = new_intervention['id']
                            logger.info(f"  ✅ Created intervention #{intervention_id} from planning #{planning_id}")
                        else:
                            logger.warning(f"  ❌ Could not retrieve newly created intervention")
                            intervention_id = None
                    else:
                        intervention_id = None
                        logger.info(
                            f"  ⏳ Future planning #{planning_id}: intervention creation deferred to {date_prevue}"
                        )
                    
                    # Now add technicians to interventions_techniciens
                    if intervention_id and new_technicians:
                        tech_list = [t.strip() for t in new_technicians.split(",") if t.strip()]
                        logger.info(f"  Adding {len(tech_list)} technician(s) to interventions_techniciens: {tech_list}")
                        
                        for index, tech_name in enumerate(tech_list):
                            tech_id = new_technician_ids[index] if index < len(new_technician_ids) else None
                            # Check if technician is already assigned
                            existing = conn.execute(
                                """SELECT id FROM interventions_techniciens 
                                   WHERE intervention_id = %s
                                     AND ((%s IS NOT NULL AND technicien_id = %s)
                                          OR (%s IS NULL AND technicien_nom ILIKE %s))""",
                                (intervention_id, tech_id, tech_id, tech_id, f"%{tech_name}%")
                            ).fetchone()
                            
                            if not existing:
                                # Create new assignment
                                conn.execute(
                                    """INSERT INTO interventions_techniciens 
                                       (intervention_id, technicien_id, technicien_nom, statut)
                                       VALUES (%s, %s, %s, %s)""",
                                    (intervention_id, tech_id, tech_name, "Assigné")
                                )
                                logger.info(f"    ✅ Added '{tech_name}' to interventions_techniciens")
                            else:
                                logger.info(f"    ℹ️ '{tech_name}' already assigned")
                        
                        conn.commit()
                        logger.info(f"  ✅ All technician assignments committed")
                except Exception as e:
                    logger.error(f"❌ Error in technician assignment: {e}", exc_info=True)
                    # Don't fail the whole request - continue
            
            # Auto-sync planning to interventions (create intervention if date is today)
            try:
                sync_planning_to_interventions()
            except Exception as e:
                logger.warning(f"Planning sync after reschedule failed: {e}")
            
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rescheduling planning {planning_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rescheduling intervention: {str(e)}"
        )

@app.delete("/api/planning/{planning_id}")
def delete_planning(planning_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    try:
        deleted = supprimer_planning(planning_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning introuvable")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    log_audit(
        user.get("sub", "unknown"),
        "DELETE_PLANNING",
        f"Planning #{planning_id} supprimé : {deleted['deleted_planning']} occurrence(s), "
        f"{deleted['deleted_interventions']} intervention(s) liée(s)",
        "planning",
    )
    return {"ok": True, **deleted}


# ==========================================
# PLANNING SYNC + FACTURATION
# ==========================================

@app.post("/api/planning/sync")
def force_planning_sync(user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """Force la synchronisation planning -> interventions pour aujourd'hui."""
    created = sync_planning_to_interventions()
    return {"ok": True, "created": len(created), "interventions": created}


@app.post("/api/interventions/{intervention_id}/factured")

def mark_intervention_factured(intervention_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager")
    """Compatibilité : convertit l'ancien marqueur en étape à confirmer."""
    actor = user.get("sub", "unknown")
    with get_db() as conn:
        conn.execute(
            "UPDATE interventions SET facture_envoyee = TRUE WHERE id = %s",
            (intervention_id,)
        )
        conn.execute(
            """INSERT INTO billing_cases (
                   intervention_id, client, equipment, created_by, updated_by
               )
               SELECT id, COALESCE(client, ''), machine, %s, %s
               FROM interventions WHERE id=%s
               ON CONFLICT (intervention_id) DO NOTHING""",
            (actor, actor, intervention_id),
        )
        conn.execute(
            """INSERT INTO billing_steps (
                   case_id, step_type, effective_date, note, created_by, updated_by
               )
               SELECT id, 'invoice', CURRENT_DATE,
                      'Créé depuis l''ancienne action : référence, montant et échéance à confirmer',
                      %s, %s
               FROM billing_cases WHERE intervention_id=%s
               ON CONFLICT (case_id, step_type) DO NOTHING""",
            (actor, actor, intervention_id),
        )
    log_audit(actor, "LEGACY_MARK_FACTURED", f'{{"intervention_id": {intervention_id}}}', "facturation")
    return {"ok": True}



# ==========================================
# KNOWLEDGE BASE
# ==========================================

__all__ = [
    "get_planning",
    "create_planning",
    "force_planning_sync",
    "generate_planning_pdf",
    "export_comparateur_pdf",
    "get_planning_comparateur",
    "get_planning_comparateur_periode",
    "update_planning_status",
    "reschedule_planning",
    "delete_planning",
    "force_planning_sync",
    "mark_intervention_factured",
]
