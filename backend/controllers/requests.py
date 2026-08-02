"""Intervention-request and multi-technician routes."""

from api.runtime import (
    Body,
    Depends,
    HTTPException,
    Optional,
    _get_technician_fullname,
    _tech_name_or_username_matches,
    _trigger_backup,
    ajouter_notification_piece,
    ajouter_piece_demandee,
    app,
    datetime,
    lire_demandes_intervention,
    log_audit,
    logger,
)
from api.security import (
    Depends,
    HTTPException,
    Optional,
    _check_create_demande_permission,
    _check_create_permission,
    _verify_token,
    assert_resource_client_access,
    resolve_client_scope,
)
from services.scheduled_jobs import (
    _df_to_records,
    _send_telegram,
    _send_telegram_bot,
    logger,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    Optional,
    _get_client_filter,
    _verify_token,
    app,
    datetime,
    log_audit,
    logger,
)

@app.get("/api/demandes")
def get_demandes(
    statuts: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    client_filter = _get_client_filter(user)
    df = lire_demandes_intervention(client=client_filter)
    # Lecteur : ne voit que les demandes de son client
    if client_filter and not df.empty and "client" in df.columns:
        df = df[df["client"].astype(str).str.lower() == client_filter.lower()]
    if statuts and not df.empty and "statut" in df.columns:
        lst = [s.strip() for s in statuts.split(",")]
        df = df[df["statut"].isin(lst)]
    return _df_to_records(df)


@app.post("/api/demandes")
def create_demande(body: dict, user: dict = Depends(_verify_token)):
    """
    Crée une demande d'intervention avec support multi-techniciens.
    Crée 1 intervention PARENT visible + N interventions ENFANTS temporaires (1 par technicien).
    """
    # Check permission - Lecteurs (clients) peuvent créer des demandes
    if not _check_create_demande_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas le droit de créer une demande d'intervention"
        )
    
    from db_engine import get_db
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    demandeur          = body.get("demandeur") or user.get("username", "")
    client             = resolve_client_scope(user, body.get("client") or "") or ""
    equipement         = body.get("equipement") or ""
    priorite           = body.get("priorite") or body.get("urgence") or "Moyenne"
    urgence            = priorite
    description        = body.get("description") or ""
    code_erreur        = body.get("code_erreur") or ""
    contact_nom        = body.get("contact_nom") or ""
    contact_tel        = body.get("contact_tel") or ""
    
    # Support for multiple technicians: can be string (single/comma-separated) or list (multiple)
    techniciens_input = body.get("technicien_assigne") or body.get("techniciens") or []
    if isinstance(techniciens_input, str):
        # If it's a comma-separated string, split it
        techniciens_input = [t.strip() for t in techniciens_input.split(",")] if techniciens_input else []
    
    # Convert all to full names
    techniciens_fullnames = []
    for tech_username in techniciens_input:
        if tech_username:
            tech_fullname = _get_technician_fullname(tech_username)
            techniciens_fullnames.append(tech_fullname)
    
    # First tech (for parent intervention)
    first_tech = techniciens_fullnames[0] if techniciens_fullnames else ""
    statut = "Assignée" if first_tech else "En attente"
    
    # Use PostgreSQL placeholder
    ph = "%s"

    demande_id = None
    parent_intervention_id = None

    with get_db() as conn:
        # Create the DEMAND
        conn.execute(f"""
            INSERT INTO demandes_intervention
              (date_demande, demandeur, client, equipement, urgence, priorite,
               description, code_erreur, contact_nom, contact_tel,
               statut, technicien_assigne)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (
            body.get("date_demande") or now_str,
            demandeur, client, equipement, urgence, priorite,
            description, code_erreur, contact_nom, contact_tel,
            statut, ", ".join(techniciens_fullnames),  # All techs in the demand
        ))
        
        # Get the newly created demand ID
        new_demande = conn.execute(
            "SELECT id FROM demandes_intervention ORDER BY id DESC LIMIT 1"
        ).fetchone()
        demande_id = new_demande["id"] if new_demande else None

        # --- Create SINGLE SHARED intervention (visible to all assigned technicians) ---
        # NEW APPROACH: One intervention for ALL technicians instead of N children
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notes_intervention = f"[{client}] Demande #{demande_id}"
        
        # Store all technicians in technicien field (comma-separated for reference)
        # Each tech will update their own row in interventions_techniciens
        all_techs_str = ", ".join(techniciens_fullnames)
        
        conn.execute(f"""
            INSERT INTO interventions
              (date, machine, technicien, type_intervention, description,
               probleme, code_erreur, statut, priorite, notes,
               is_temporary, parent_intervention_id, client)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (
            now,
            equipement,
            all_techs_str,  # Store all technician names
            "Corrective",
            description[:500],
            description[:500],
            code_erreur,
            "Assignée",  # Always "Assignée" for multi-tech shared intervention
            urgence,
            notes_intervention,
            0,  # is_temporary = FALSE (visible to all technicians)
            None,  # No parent - this is a standalone intervention
            client,
        ))
        
        intervention = conn.execute(
            "SELECT id FROM interventions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        intervention_id = intervention["id"] if intervention else None
        
        # Link demand to intervention
        if intervention_id:
            conn.execute(
                f"UPDATE demandes_intervention SET intervention_id = {ph} WHERE id = {ph}",
                (intervention_id, demande_id)
            )
        
        # --- Populate interventions_techniciens table: one row per technician ---
        # This table tracks per-technician data (hours, solution, statut)
        if intervention_id:
            for tech_fullname in techniciens_fullnames:
                conn.execute(f"""
                    INSERT INTO interventions_techniciens 
                    (intervention_id, technicien_nom, statut)
                    VALUES ({ph}, {ph}, 'Assigné')
                """, (intervention_id, tech_fullname))
                logger.info(f"[MULTI-TECH] Technician '{tech_fullname}' assigned to intervention #{intervention_id}")
            
            logger.info(f"[MULTI-TECH] Intervention #{intervention_id} created as SHARED with {len(techniciens_fullnames)} technicians: {all_techs_str}")
        
        _trigger_backup()

    # --- Telegram notifications ---
    urg_icon = "\U0001f534" if urgence in ("Haute", "Critique") else "\U0001f7e1" if urgence == "Moyenne" else "\U0001f7e2"
    contact_line = f"\n\U0001f4de Contact : <b>{contact_nom}</b>" + (f" — {contact_tel}" if contact_tel else "") if contact_nom else ""
    code_line    = f"\n\U0001f522 Code erreur : <code>{code_erreur}</code>" if code_erreur else ""
    techs_line   = f"\n\U0001f477 Assigné à : <b>{', '.join(techniciens_fullnames)}</b>" if techniciens_fullnames else ""
    msg = (
        f"\U0001f4cb <b>NOUVELLE DEMANDE D'INTERVENTION</b>\n\n"
        f"\U0001f3e2 Client : <b>{client}</b>\n"
        f"\U0001f3e5 Équipement : <b>{equipement}</b>\n"
        f"{urg_icon} Priorité : <b>{priorite}</b>\n"
        f"\U0001f4dd Problème : {description[:300]}"
        f"{code_line}"
        f"{contact_line}"
        f"{techs_line}\n"
        f"\U0001f464 Demandeur : <b>{demandeur}</b>\n"
        f"\U0001f550 Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"\U0001f449 Connectez-vous à <b>SAVIA</b> pour traiter cette demande."
    )
    _send_telegram(msg)
    
    # Log audit
    username = user.get("sub", "unknown")
    log_audit(username, "CREATE_DEMANDE", f"{{\"client\": \"{client}\", \"demande_id\": {demande_id}}}", "demandes")
    
    logger.info(f"Demande #{demande_id} créée avec {len(techniciens_fullnames)} techniciens → Intervention PARTAGÉE #{intervention_id}")
    
    return {"success": True, "demande_id": demande_id, "intervention_id": intervention_id}


@app.delete("/api/demandes/{demande_id}")
def delete_demande(demande_id: int, user: dict = Depends(_verify_token)):
    """Supprime une demande d'intervention (Admin et Manager uniquement)."""
    if user.get("role") not in {"Admin", "Manager"}:
        raise HTTPException(status_code=403, detail="Seuls les Admins et Managers peuvent supprimer une demande")

    from db_engine import get_db
    with get_db() as conn:
        assert_resource_client_access(conn, "demande", demande_id, user)
        row = conn.execute(
            "SELECT id, client, equipement FROM demandes_intervention WHERE id = %s",
            (demande_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Demande introuvable")
        conn.execute("DELETE FROM demandes_intervention WHERE id = %s", (demande_id,))

    _trigger_backup()
    import json
    log_audit(
        user.get("sub", "unknown"),
        "DELETE_DEMANDE",
        json.dumps({
            "demande_id": demande_id,
            "client": row.get("client", ""),
            "equipement": row.get("equipement", ""),
        }, ensure_ascii=False),
        "demandes",
    )
    return {"success": True}


@app.put("/api/demandes/{demande_id}/statut")
def update_demande_statut(demande_id: int, body: dict, user: dict = Depends(_verify_token)):
    # Check permission - only Admin, Manager, Responsable Technique can update status
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Seuls les Managers, Responsables et Admins peuvent mettre à jour le statut des demandes"
        )
    
    from db_engine import get_db
    with get_db() as conn:
        assert_resource_client_access(conn, "demande", demande_id, user)
    nouveau_statut      = body.get("statut") or "En cours"
    technicien_assigne  = body.get("technicien_assigne") or ""
    # Convert technicien username to full name
    if technicien_assigne:
        technicien_assigne = _get_technician_fullname(technicien_assigne)
    notes_traitement    = body.get("notes_traitement") or ""

    # Récupérer les données de la demande AVANT mise à jour pour le message
    demande_info = {}
    with get_db() as conn:
        row = conn.execute(
            "SELECT client, equipement, priorite, urgence, description, demandeur, contact_nom, contact_tel FROM demandes_intervention WHERE id = %s",
            (demande_id,)
        ).fetchone()
        if row:
            demande_info = dict(row)
        conn.execute("""
            UPDATE demandes_intervention
            SET statut = %s, technicien_assigne = %s, notes_traitement = %s,
                date_traitement = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (nouveau_statut, technicien_assigne, notes_traitement, demande_id))

    # --- Notification Telegram (tous les changements de statut) ---
    statut_icons = {
        "En attente": "\u23f3",
        "En cours":   "\U0001f527",
        "Assign\u00e9e": "\U0001f477",
        "R\u00e9solue":  "\u2705",
        "Cl\u00f4tur\u00e9e": "\U0001f3c1",
        "Plan\u00e0fi\u00e9e": "\U0001f4c5",
        "Planifi\u00e9e":  "\U0001f4c5",
        "Rejet\u00e9e":    "\u274c",
        "Accept\u00e9e":  "\u2705",
    }
    icon = statut_icons.get(nouveau_statut, "\U0001f4cb")
    client     = demande_info.get("client", "")
    equipement = demande_info.get("equipement", "")
    priorite   = demande_info.get("priorite") or demande_info.get("urgence", "")
    description = str(demande_info.get("description", ""))[:300]
    demandeur  = demande_info.get("demandeur", "")
    contact_nom = demande_info.get("contact_nom", "")
    contact_tel = demande_info.get("contact_tel", "")

    urg_icon     = "\U0001f534" if priorite in ("Haute", "Critique") else "\U0001f7e1" if priorite == "Moyenne" else "\U0001f7e2"
    tech_line    = f"\n\U0001f477 Technicien : <b>{technicien_assigne}</b>" if technicien_assigne else ""
    notes_line   = f"\n\U0001f4cc Notes : {notes_traitement}" if notes_traitement else ""
    contact_line = f"\n\U0001f4de Contact : <b>{contact_nom}</b>" + (f" — {contact_tel}" if contact_tel else "") if contact_nom else ""
    demandeur_line = f"\n\U0001f464 Demandeur : <b>{demandeur}</b>" if demandeur else ""

    msg = (
        f"{icon} <b>DEMANDE #{demande_id} \u2014 MISE \u00c0 JOUR STATUT</b>\n\n"
        f"\U0001f3e2 Client : <b>{client}</b>\n"
        f"\U0001f3e5 \u00c9quipement : <b>{equipement}</b>\n"
        f"{urg_icon} Priorité : <b>{priorite}</b>\n"
        f"\U0001f4ca Statut : <b>{nouveau_statut}</b>\n"
        f"\U0001f4dd Probl\u00e8me : {description}"
        f"{tech_line}"
        f"{notes_line}"
        f"{contact_line}"
        f"{demandeur_line}\n"
        f"\U0001f550 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_telegram(msg)

    # --- Auto-créer une intervention si technicien assigné et pas déjà liée ---
    if technicien_assigne:
        try:
            with get_db() as conn:
                # Vérifier si une intervention existe déjà pour cette demande
                existing = conn.execute(
                    "SELECT intervention_id FROM demandes_intervention WHERE id = %s",
                    (demande_id,)
                ).fetchone()
                already_linked = existing and existing["intervention_id"]

                if not already_linked:
                    # Créer l'intervention
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    notes_interv = f"[{client}] Demande #{demande_id}"
                    if notes_traitement:
                        notes_interv += f" — {notes_traitement}"
                    conn.execute("""
                        INSERT INTO interventions
                          (date, machine, technicien, type_intervention, description,
                           probleme, code_erreur, statut, priorite, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        now,
                        equipement,
                        technicien_assigne,
                        "Corrective",
                        description[:500],
                        description[:500],
                        demande_info.get("code_erreur", "") or "",
                        "Assignée",
                        priorite,
                        notes_interv,
                    ))
                    # Récupérer l'id de l'intervention créée
                    new_interv = conn.execute(
                        "SELECT id FROM interventions ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if new_interv:
                        conn.execute(
                            "UPDATE demandes_intervention SET intervention_id = %s WHERE id = %s",
                            (new_interv["id"], demande_id)
                        )
                        logger.info(f"Intervention #{new_interv['id']} auto-créée pour demande #{demande_id} → {technicien_assigne}")
                else:
                    # Intervention déjà liée → mettre à jour technicien + statut (ex: réassignation après refus)
                    interv_id = existing["intervention_id"]
                    conn.execute(
                        "UPDATE interventions SET technicien = %s, statut = %s WHERE id = %s",
                        (technicien_assigne, "Assignée", interv_id)
                    )
                    logger.info(f"Intervention #{interv_id} réassignée à {technicien_assigne} (demande #{demande_id})")
        except Exception as e:
            logger.error(f"Erreur auto-création intervention: {e}")

    return {"success": True}


# ------ Technicien Update Per-Technician Data ------

@app.put("/api/interventions/{intervention_id}/technicien-data")
def update_technicien_data(intervention_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    """
    Updates per-technician data in interventions_techniciens table.
    When technician marks their work as Cloturee, check if all are complete.
    Only then finalize the parent intervention.
    
    Expected body:
    {
        "probleme_tech": "...",
        "cause_tech": "...",
        "solution_tech": "...",
        "heure_debut_tech": "HH:MM",
        "heure_fin_tech": "HH:MM",
        "duree_minutes_tech": 60,
        "duree_deplacement_tech": 30,
        "notes_tech": "...",
        "statut": "Cloturee" (marks this tech as done)
    }
    """
    from db_engine import (
        get_db, update_interventions_techniciens, 
        get_or_create_interventions_techniciens, get_techniciens_status,
        finalize_intervention_from_techniciens, consolidate_technician_duplicates,
        update_intervention_statut,
    )
    
    logger.info(f"🔵 PUT /api/interventions/{intervention_id}/technicien-data CALLED")
    logger.info(f"   User: {user.get('nom')} (role: {user.get('role')})")
    logger.info(f"   Body: {body}")
    
    try:
        # Get intervention to verify it exists
        machine = None
        client = None
        technicien = None
        
        with get_db() as conn:
            intervention = conn.execute(
                "SELECT id, machine, technicien FROM interventions WHERE id = %s",
                (intervention_id,)
            ).fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            # Extract intervention data
            machine = intervention.get("machine", "")
            technicien = intervention.get("technicien", "")
            
            # Get client from equipements table (joined by machine name)
            try:
                eq_row = conn.execute(
                    "SELECT client FROM equipements WHERE nom = %s LIMIT 1",
                    (machine,)
                ).fetchone()
                if eq_row:
                    client = dict(eq_row).get('client', '') or ''
            except Exception:
                client = ''
            
            # Verify technician permissions
            if user.get("role") == "Technicien":
                current_tech = str(intervention.get("technicien") or "").strip()
                user_nom_complet = (user.get("nom") or "").strip()
                user_username = (user.get("sub") or "").strip()
                
                is_assigned = False
                
                # Cas 1: Vérifier d'abord dans interventions_techniciens (priorité multi-tech)
                logger.info(f"🔐 Permission check: checking interventions_techniciens table first (multi-tech priority)")
                tech_rows = conn.execute(
                    "SELECT technicien_nom FROM interventions_techniciens WHERE intervention_id = %s",
                    (intervention_id,)
                ).fetchall()
                
                if tech_rows:
                    # Vérifier si le technicien actuel est dans la liste
                    for row_tech in tech_rows:
                        stored_tech_nom = str(row_tech.get("technicien_nom") or "").strip()
                        if (stored_tech_nom and 
                            (_tech_name_or_username_matches(user_nom_complet, stored_tech_nom) or
                             _tech_name_or_username_matches(user_username, stored_tech_nom))):
                            is_assigned = True
                            logger.info(f"🔐 Technicien '{user_nom_complet}' (username={user_username}) found in interventions_techniciens")
                            break
                
                # Cas 2: Si pas trouvé en multi-tech, vérifier le champ technicien (single-tech)
                if not is_assigned and current_tech:
                    logger.info(f"🔐 Not in interventions_techniciens, checking single-tech column: technicien='{current_tech}'")
                    is_assigned = (
                        _tech_name_or_username_matches(user_nom_complet, current_tech) or
                        _tech_name_or_username_matches(user_username, current_tech)
                    )
                    logger.info(f"🔐 Permission check (single-tech): user='{user_nom_complet}' (username={user_username}) vs tech='{current_tech}' → assigned={is_assigned}")
                
                if not is_assigned:
                    logger.warning(f"🔐 Technicien '{user_nom_complet}' (username={user_username}) not authorized for intervention #{intervention_id}")
                    raise HTTPException(
                        status_code=403,
                        detail="Vous ne pouvez éditer que vos propres interventions"
                    )
        
        # Get or create entry for this technician
        tech_nom = body.get("technicien_nom") or user.get("nom", "Unknown")
        logger.info(f"   ✓ Tech name: {tech_nom}")
        
        get_or_create_interventions_techniciens(intervention_id, tech_nom)
        
        # Update the per-technician data
        success = update_interventions_techniciens(intervention_id, tech_nom, body)
        logger.info(f"   ✓ Update result: {success}")
        
        if not success:
            raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")
        
        if body.get("statut") == "En cours":
            # Starting any technician's work starts the shared intervention
            # and synchronises the equipment to "En maintenance".
            update_intervention_statut(intervention_id, "En cours")

        # Deduct stock if technician marked as Cloturee and pieces are provided
        if body.get("statut") == "Cloturee" and body.get("pieces_a_deduire"):
            try:
                pieces_list = body.get("pieces_a_deduire", [])
                logger.info(f"   📦 Deducting stock for {len(pieces_list)} pieces...")
                
                with get_db() as conn:
                    for piece in pieces_list:
                        if not isinstance(piece, dict):
                            continue
                        ref = piece.get('ref') or piece.get('reference') or ''
                        qty = int(piece.get('qty') or piece.get('quantite') or 0)
                        
                        if qty > 0 and ref:
                            logger.info(f"      Deducting: {ref} qty={qty}")
                            conn.execute("""
                                UPDATE pieces_rechange
                                SET stock_actuel = stock_actuel - %s
                                WHERE reference = %s
                            """, (qty, ref))
                
                logger.info(f"   ✅ Stock deducted successfully")
            except Exception as e:
                logger.warning(f"   ⚠️ Error deducting stock: {e}")
                # Don't fail the whole request if stock deduction fails

        # Handle pieces_rupture if technician marked as "En attente de piece"
        if body.get("statut") == "En attente de piece" and (body.get("pieces_rupture") or body.get("pieces_a_deduire")):
            try:
                pieces_rupture_list = body.get("pieces_rupture") or body.get("pieces_a_deduire") or []
                logger.info(f"   🔴 Creating rupture badges for {len(pieces_rupture_list)} pieces...")
                
                with get_db() as conn:
                    for piece in pieces_rupture_list:
                        if not isinstance(piece, dict):
                            continue
                        ref = piece.get('reference') or piece.get('ref') or ''
                        designation = piece.get('designation') or piece.get('nom') or ''
                        if not ref and piece.get('id'):
                            piece_row = conn.execute(
                                "SELECT reference, designation FROM pieces_rechange WHERE id = %s",
                                (piece.get('id'),),
                            ).fetchone()
                            if piece_row:
                                ref = piece_row.get('reference') or ''
                                designation = designation or piece_row.get('designation') or ''
                        
                        if ref:
                            # Create the same notification record consumed by
                            # the web application and the PWA.
                            ajouter_notification_piece({
                                "type": "piece_rupture",
                                "intervention_id": intervention_id,
                                "piece_reference": ref,
                                "piece_nom": designation or ref,
                                "intervention_ref": f"#{intervention_id}",
                                "equipement": machine or "",
                                "client": client or "",
                                "technicien": tech_nom,
                                "message": f"⚠️ Intervention #{intervention_id} en attente de la pièce {ref} ({designation or ref}) — rupture de stock",
                                "source": "sav",
                                "destination": "gestionnaire",
                            })
                            logger.info(f"      Created rupture badge: {ref} - {designation}")
                
                logger.info(f"   ✅ Rupture badges created successfully")
                
                # Send Telegram notification
                try:
                    pieces_txt = ""
                    if pieces_rupture_list:
                        pieces_txt = "\n".join([f"  • {p.get('reference', '')} — {p.get('designation', '')}" for p in pieces_rupture_list if p.get("reference")])
                    
                    if pieces_txt:
                        msg_tg = (
                            f"🔴 <b>Pièce(s) en rupture — #{intervention_id}</b>\n\n"
                            f"⚠️ Pièces manquantes :\n{pieces_txt}\n\n"
                            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                        )
                        _send_telegram_bot("telegram_stock", msg_tg)
                        _send_telegram("📬 " + msg_tg)
                        logger.info(f"📬 Rupture notification sent")
                except Exception as tg_err:
                    logger.warning(f"   ⚠️ Telegram rupture notification failed: {tg_err}")
            except Exception as e:
                logger.warning(f"   ⚠️ Error handling rupture pieces: {e}")
                # Don't fail the whole request if rupture handling fails

        # Handle pieces_manuelles (manual/non-referenced pieces) - multi-tech mode
        if body.get("pieces_manuelles"):
            try:
                pieces_manuelles_list = body.get("pieces_manuelles", [])
                logger.info(f"   📋 Creating manual piece requests for {len(pieces_manuelles_list)} pieces...")
                
                for piece in pieces_manuelles_list:
                    if not isinstance(piece, dict):
                        continue
                    ref = piece.get('reference', '').strip()
                    designation = piece.get('designation', '').strip()
                    
                    if ref:
                        # Create manual piece request (same as mode single tech, using same function)
                        # Use tech_nom (current technician) instead of original technicien
                        ajouter_piece_demandee({
                            "reference": ref,
                            "designation": designation,
                            "intervention_id": intervention_id,
                            "equipement": machine,
                            "client": client,
                            "technicien": tech_nom,  # Use current tech submitting, not original
                            "probleme": "",
                        })
                        # Notification gestionnaire (same as single-tech mode)
                        ajouter_notification_piece({
                            "type": "piece_rupture",
                            "intervention_id": intervention_id,
                            "piece_reference": ref,
                            "piece_nom": designation,
                            "intervention_ref": f"#{intervention_id}",
                            "equipement": machine,
                            "client": client,
                            "technicien": tech_nom,  # Use current tech submitting
                            "message": f"🆕 Pièce non référencée demandée: {ref} ({designation}) "
                                       f"pour intervention #{intervention_id} sur {machine}",
                            "source": "sav",
                            "destination": "gestionnaire",
                        })
                        logger.info(f"      Created manual piece request: {ref} - {designation}")
                
                logger.info(f"   ✅ Manual piece requests created successfully")
                
                # Send Telegram notification (same format as single-tech mode)
                try:
                    pm_list = [f"  • {p.get('reference','')} — {p.get('designation','')}" for p in pieces_manuelles_list if p.get("reference")]
                    if pm_list:
                        client_line_m = f"\n👤 Client : <b>{client}</b>" if client else ""
                        msg_tg_m = (
                            f"🆕 <b>DEMANDE PIÈCE NON RÉFÉRENCÉE — #{intervention_id}</b>\n\n"
                            f"🏥 Machine : <b>{machine}</b>"
                            f"{client_line_m}\n"
                            f"👷 Technicien : <b>{tech_nom}</b>\n"
                            f"🔩 Pièces demandées :\n" + "\n".join(pm_list) + "\n\n"
                            f"⚠️ Ces pièces ne sont pas dans le stock — à commander\n"
                            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                        )
                        # Send to both stock bot and tech bot (same as single-tech mode)
                        _send_telegram_bot("telegram_stock", msg_tg_m)
                        _send_telegram_bot("telegram", msg_tg_m)
                        logger.info(f"📋 Manual piece notifications sent to both bots")
                except Exception as tg_err:
                    logger.warning(f"   ⚠️ Telegram manual piece notification failed: {tg_err}")
            except Exception as e:
                logger.warning(f"   ⚠️ Error handling manual pieces: {e}")
                # Don't fail the whole request if manual piece handling fails
                # Don't fail the whole request if manual piece handling fails
        
        # Consolidate any duplicate technician records (with reversed names)
        consolidate_technician_duplicates(intervention_id)
        
        # Get current status
        status_info = get_techniciens_status(intervention_id)
        
        # Check if all technicians are now completed
        if status_info['is_all_completed']:
            # All done - aggregate data AND automatically close the parent intervention
            finalize_result = finalize_intervention_from_techniciens(intervention_id)
            
            if finalize_result.get('success'):
                logger.info(f"✅ Intervention #{intervention_id} AUTOMATICALLY CLOSED after all {status_info['total']} technicians completed")
                
                # Send Telegram: INTERVENTION CLOSED - À FACTURER
                try:
                    # Fetch updated intervention data with pieces_utilisees
                    with get_db() as conn:
                        updated_row = conn.execute(
                            "SELECT machine, technicien, probleme, cause, solution, duree_minutes, notes, pieces_utilisees FROM interventions WHERE id = %s",
                            (intervention_id,)
                        ).fetchone()
                    
                    if updated_row:
                        d = dict(updated_row)
                    else:
                        d = {'machine': machine, 'pieces_utilisees': ''}
                    
                    machine = d.get('machine', '')
                    total_duree_h = round(finalize_result.get('total_duree_minutes', 0) / 60, 1)
                    total_deplacement_h = round(finalize_result.get('total_duree_deplacement', 0) / 60, 1)
                    solutions = finalize_result.get('combined_solution', '')
                    pieces = str(d.get('pieces_utilisees', '') or '').strip()
                    
                    # Get client info from notes or equipement
                    notes_raw = str(d.get('notes', '') or intervention.get('notes', '') or '')
                    client_name = notes_raw[1:notes_raw.index(']')] if notes_raw.startswith('[') and ']' in notes_raw else ''
                    client_line = f"\n👤 Client : <b>{client_name}</b>" if client_name else ""
                    pieces_line = f"\n🔩 Pièces : {pieces}" if pieces else ""
                    
                    # Message for SAV team: À facturer
                    msg_sav = (
                        f"📋 <b>Intervention À facturer — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>"
                        f"{client_line}\n"
                        f"👷 Tous les techniciens : <b>{status_info['total']}/{status_info['total']}</b>\n"
                        f"⏱️ Durée totale : <b>{total_duree_h}h</b>\n"
                        f"🚗 Déplacement total : <b>{total_deplacement_h}h</b>\n"
                        f"🔧 Solutions : {solutions}"
                        f"{pieces_line}\n"
                        f"✅ Intervention fermée automatiquement\n"
                        f"💰 <i>Délai de facturation : 10 jours</i>\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    _send_telegram_bot("telegram_sav", msg_sav)
                    logger.info(f"✅ Telegram SAV message sent: Intervention #{intervention_id} à facturer")
                    
                    # Message for technicians: INTERVENTION CLÔTURÉE
                    msg_tech = (
                        f"✅ <b>INTERVENTION CLÔTURÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>"
                        f"{client_line}\n"
                        f"👷 Tous les techniciens : <b>{status_info['total']}/{status_info['total']}</b>\n"
                        f"⏱️ Durée totale : <b>{total_duree_h}h</b>\n"
                        f"🚗 Déplacement total : <b>{total_deplacement_h}h</b>\n"
                        f"🔧 Solutions : {solutions}"
                        f"{pieces_line}\n"
                        f"✅ Intervention fermée automatiquement\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    _send_telegram(msg_tech)
                    logger.info(f"✅ Telegram TECH message sent: Intervention #{intervention_id} clôturée")
                except Exception as te:
                    logger.warning(f"⚠️ Closing telegram notifications failed: {te}")
                
                return {
                    "success": True,
                    "message": f"✅ Tous les techniciens ont complété! Intervention #{intervention_id} clôturée automatiquement.",
                    "intervention_finalized": True,
                    "status": "CLOSED",
                    "completed": status_info['completed'],
                    "total": status_info['total']
                }
            else:
                logger.error(f"❌ Finalization failed: {finalize_result}")
                return HTTPException(status_code=500, detail="Erreur lors de la finalisation")
        else:
            logger.info(f"   ✓ Partial completion: {status_info['completed']}/{status_info['total']}")
            # Partial completion - still waiting for others
            pending_list = ", ".join(status_info['pending_names'])
            logger.info(f"⏳ Intervention #{intervention_id} partially complete: {status_info['completed']}/{status_info['total']} (pending: {pending_list})")
            
            # Send Telegram: PARTIALLY CLOSED - but only if this technician marked as "Cloturee"
            # Don't send if technician marked as "En attente de piece"
            if body.get("statut") == "Cloturee":
                try:
                    machine = intervention.get('machine', '')
                    msg_tg = (
                        f"⏳ <b>INTERVENTION PARTIELLEMENT CLÔTURÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>\n"
                        f"✅ Techniciens complétés : <b>{status_info['completed']}/{status_info['total']}</b>\n"
                        f"⏳ Techniciens restants :\n"
                    )
                    for pending_tech in status_info['pending_names']:
                        msg_tg += f"  • {pending_tech}\n"
                    
                    msg_tg += f"\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    _send_telegram(msg_tg)
                    logger.info(f"✅ Partial closure telegram sent: Intervention #{intervention_id} ({status_info['completed']}/{status_info['total']} completed)")
                except Exception as te:
                    logger.warning(f"⚠️ Partial closure telegram notification failed (will retry later): {te}")
            else:
                logger.info(f"   ✓ Technician marked as '{body.get('statut')}' - no partial closure telegram sent")
            
            logger.info(f"   ✓ Returning PARTIAL response with {len(status_info['pending_names'])} pending: {status_info['pending_names']}")
            return {
                "success": True,
                "message": f"Données sauvegardées ({status_info['completed']}/{status_info['total']} techniciens complétés)",
                "intervention_finalized": False,
                "status": "PARTIAL",
                "completed": status_info['completed'],
                "total": status_info['total'],
                "pending_technicians": status_info['pending_names']
            }
        
    except HTTPException:
        logger.error(f"❌ HTTPException in update_technicien_data")
        raise
    except Exception as e:
        logger.error(f"❌ Erreur update_technicien_data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/interventions/{intervention_id}/techniciens")
def get_intervention_techniciens(intervention_id: int, user: dict = Depends(_verify_token)):
    """
    Récupère tous les enregistrements de techniciens pour une intervention.
    Retourne les données per-technician depuis interventions_techniciens table.
    """
    from db_engine import get_db, get_interventions_techniciens
    
    try:
        # Verify intervention exists
        with get_db() as conn:
            intervention = conn.execute(
                "SELECT id FROM interventions WHERE id = %s",
                (intervention_id,)
            ).fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
        
        # Get technician records
        tech_records = get_interventions_techniciens(intervention_id)
        
        # Convert to list of dicts for JSON serialization
        result = []
        for record in tech_records:
            result.append(dict(record) if hasattr(record, 'keys') else record)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur get_intervention_techniciens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/interventions/{intervention_id}/techniciens-aggregated")
def get_intervention_techniciens_aggregated(intervention_id: int, user: dict = Depends(_verify_token)):
    """
    Retourne les données agrégées de tous les techniciens pour une intervention.
    Utilisé pour afficher un tableau récapitulatif et générer les PDFs multi-tech.
    
    Retourne:
    {
        "intervention_id": int,
        "total_duree_minutes": int (somme de tous),
        "total_duree_deplacement": int (somme de tous),
        "tous_solutions": [{"technicien": str, "solution": str}],
        "statut_completion": bool (tous complétés?),
        "techniciens": [
            {
                "nom": str,
                "probleme": str,
                "cause": str,
                "solution": str,
                "heure_debut": str (HH:MM),
                "heure_fin": str (HH:MM),
                "duree_minutes": int,
                "duree_deplacement": int,
                "statut": str
            }
        ]
    }
    """
    from db_engine import get_db, get_interventions_techniciens
    
    try:
        # Verify intervention exists
        with get_db() as conn:
            intervention = conn.execute(
                "SELECT id, statut FROM interventions WHERE id = %s",
                (intervention_id,)
            ).fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
        
        # Get all technician records
        tech_records = get_interventions_techniciens(intervention_id)
        
        # Aggregate data
        total_duree = 0
        total_deplacement = 0
        solutions_list = []
        all_completed = True
        techniciens_data = []
        
        for record in tech_records:
            rec_dict = dict(record) if hasattr(record, 'keys') else record
            
            duree = int(rec_dict.get('duree_minutes_tech') or 0)
            deplacement = int(rec_dict.get('duree_deplacement_tech') or 0)
            
            total_duree += duree
            total_deplacement += deplacement
            
            statut = str(rec_dict.get('statut') or 'En cours')
            if statut != 'Cloturee':
                all_completed = False
            
            solution = str(rec_dict.get('solution_tech') or '')
            if solution.strip():
                solutions_list.append({
                    "technicien": rec_dict.get('technicien_nom', 'Unknown'),
                    "solution": solution
                })
            
            # Build tech data entry
            techniciens_data.append({
                "nom": rec_dict.get('technicien_nom', 'Unknown'),
                "probleme": str(rec_dict.get('probleme_tech') or ''),
                "cause": str(rec_dict.get('cause_tech') or ''),
                "solution": solution,
                "heure_debut": str(rec_dict.get('heure_debut_tech') or ''),
                "heure_fin": str(rec_dict.get('heure_fin_tech') or ''),
                "duree_minutes": duree,
                "duree_deplacement": deplacement,
                "statut": statut
            })
        
        return {
            "intervention_id": intervention_id,
            "total_duree_minutes": total_duree,
            "total_duree_deplacement": total_deplacement,
            "tous_solutions": solutions_list,
            "statut_completion": all_completed,
            "techniciens": techniciens_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur get_intervention_techniciens_aggregated: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------ Technicien Accept / Refuse intervention ------

@app.put("/api/interventions/{intervention_id}/accept")
def accept_intervention(intervention_id: int, user: dict = Depends(_verify_token)):
    from db_engine import get_db, update_intervention_statut
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, machine, technicien, statut FROM interventions WHERE id = %s",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention introuvable")

    update_intervention_statut(intervention_id, "En cours")

    tech_name = user.get("nom") or user.get("username") or "?"
    machine = row["machine"] if row else ""
    msg = (
        f"\u2705 <b>INTERVENTION #{intervention_id} — ACCEPTÉE</b>\n\n"
        f"\U0001f477 Technicien : <b>{tech_name}</b>\n"
        f"\U0001f3e5 Équipement : <b>{machine}</b>\n"
        f"\U0001f4ca Statut : <b>En cours</b>\n"
        f"\U0001f550 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_telegram(msg)

    return {"success": True, "statut": "En cours"}


@app.put("/api/interventions/{intervention_id}/refuse")
def refuse_intervention(intervention_id: int, body: dict, user: dict = Depends(_verify_token)):
    from db_engine import get_db
    raison = body.get("raison", "").strip()
    if not raison:
        raise HTTPException(status_code=400, detail="La raison du refus est obligatoire")

    with get_db() as conn:
        row = conn.execute(
            """SELECT id, machine, technicien, statut, notes,
                      (SELECT e.client FROM equipements e WHERE LOWER(e.nom) = LOWER(interventions.machine) LIMIT 1) AS client
               FROM interventions WHERE id = %s""",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention introuvable")

        tech_name = user.get("nom") or user.get("username") or row.get("technicien", "?")
        machine = row["machine"] if row else ""
        client = row.get("client", "") or ""

        # Mark intervention back to "En attente" and clear technician
        conn.execute(
            "UPDATE interventions SET statut = %s, technicien = %s, notes = COALESCE(notes, '') || %s WHERE id = %s",
            ("En attente", "", f"\n[REFUS par {tech_name}] {raison}", intervention_id)
        )

        # Also update the linked demande if it exists
        conn.execute("""
            UPDATE demandes_intervention
            SET statut = 'En attente', technicien_assigne = '',
                notes_traitement = COALESCE(notes_traitement, '') || %s
            WHERE intervention_id = %s
        """, (f"\n[REFUS par {tech_name}] {raison}", intervention_id))

    # Send Telegram notification
    msg = (
        f"\u274c <b>INTERVENTION #{intervention_id} — REFUSÉE</b>\n\n"
        f"\U0001f477 Technicien : <b>{tech_name}</b>\n"
        f"\U0001f3e5 Équipement : <b>{machine}</b>\n"
        f"\U0001f3e2 Client : <b>{client}</b>\n"
        f"\U0001f4ac Raison : <i>{raison}</i>\n\n"
        f"\u23f3 Statut : <b>En attente</b> — à réassigner\n"
        f"\U0001f550 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_telegram(msg)

    return {"success": True, "statut": "En attente"}


# ==========================================
# PIÈCES DE RECHANGE
# ==========================================

__all__ = [
    "get_demandes",
    "create_demande",
    "update_demande_statut",
    "update_technicien_data",
    "get_intervention_techniciens",
    "get_intervention_techniciens_aggregated",
    "accept_intervention",
    "refuse_intervention",
]
