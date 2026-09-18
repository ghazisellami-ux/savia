"""Intervention-request and multi-technician routes."""

from api.runtime import (
    Body,
    Depends,
    HTTPException,
    Optional,
    Request,
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
    assert_intervention_write_access,
    require_roles,
    resolve_client_scope,
)
from services.scheduled_jobs import (
    _df_to_records,
    _send_telegram,
    _send_telegram_bot,
    send_telegram_reliably,
    notify_workshop_transfer,
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
from db_engine import get_db
from services.idempotency import (
    get_idempotent_response,
    operation_id_from_request,
    save_idempotent_response,
)
from repositories.equipment_status import retour_site_confirmation_requise
from repositories.interventions import find_open_intervention, lock_equipment_intervention_key


_INTERVENTION_ACTION_ROLES = (
    "Admin",
    "Manager",
    "Responsable Technique",
    "Technicien",
)


def _assert_intervention_action_access(conn, intervention_id: int, user: dict) -> None:
    """Authorize status actions before any intervention mutation is performed."""
    require_roles(user, *_INTERVENTION_ACTION_ROLES)
    assert_intervention_write_access(conn, intervention_id, user)


def _synchroniser_statut_parent_multi_tech(intervention_id, statut_technicien, update_status):
    """Synchronise le statut parent lorsqu'un technicien change son statut partagé.

    Cette fonction est dédiée au flux multi-techniciens. La clôture reste gérée
    plus bas par la consolidation lorsque tous les techniciens ont terminé.
    """
    if statut_technicien == "En cours":
        parent_status = "En cours"
    elif statut_technicien == "Transfert vers l'atelier":
        parent_status = "Transfert vers l'atelier"
    elif statut_technicien in ("En attente de piece", "En attente de pièce"):
        parent_status = "En attente de piece"
    else:
        return None
    update_status(intervention_id, parent_status)
    return parent_status

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
    records = _df_to_records(df)
    request_ids = [record.get("id") for record in records if record.get("id") is not None]
    if request_ids:
        with get_db() as conn:
            case_rows = conn.execute(
                """SELECT d.id AS request_id,
                          COALESCE(
                              (SELECT bc.id FROM billing_cases bc
                               WHERE bc.request_id = d.id ORDER BY bc.id LIMIT 1),
                              (SELECT bc.id FROM billing_cases bc
                               WHERE bc.intervention_id = d.intervention_id ORDER BY bc.id LIMIT 1)
                          ) AS billing_case_id
                   FROM demandes_intervention d
                   WHERE d.id = ANY(%s)""",
                (request_ids,),
            ).fetchall()
        case_by_request = {row["request_id"]: row.get("billing_case_id") for row in case_rows}
        for record in records:
            record["billing_case_id"] = case_by_request.get(record.get("id"))
    return records


@app.post("/api/demandes")
def create_demande(body: dict, user: dict = Depends(_verify_token)):
    """
    Crée une demande d'intervention avec support multi-techniciens.
    Crée 1 intervention PARENT visible + N interventions ENFANTS temporaires (1 par technicien).
    """
    billing_case_id = None
    if body.get("billing_case_id") not in (None, ""):
        try:
            billing_case_id = int(body["billing_case_id"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Identifiant de dossier de facturation invalide")
        if billing_case_id <= 0:
            raise HTTPException(status_code=422, detail="Identifiant de dossier de facturation invalide")

    # Les gestionnaires peuvent initier une demande uniquement depuis un
    # dossier de facturation existant. Les autres règles restent inchangées.
    normalized_role = " ".join(str(user.get("role") or "").split()).casefold()
    can_create_from_billing = billing_case_id is not None and normalized_role == "gestionnaire"
    if not (_check_create_demande_permission(user) or can_create_from_billing):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas le droit de créer une demande d'intervention"
        )
    
    from db_engine import get_db
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    demandeur          = body.get("demandeur") or user.get("username", "")
    client             = resolve_client_scope(user, body.get("client") or "") or ""
    equipement         = body.get("equipement") or ""
    equipement_id      = body.get("equipement_id")
    if equipement_id in (None, ""):
        equipement_id = None
    else:
        try:
            equipement_id = int(equipement_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Identifiant d'équipement invalide")
    priorite           = body.get("priorite") or body.get("urgence") or "Moyenne"
    urgence            = priorite
    description        = body.get("description") or ""
    type_intervention  = str(body.get("type_intervention") or "Corrective").strip()
    if type_intervention not in {"Corrective", "Installation"}:
        raise HTTPException(status_code=422, detail="Type d'intervention invalide")
    code_erreur        = body.get("code_erreur") or ""
    contact_nom        = body.get("contact_nom") or ""
    contact_tel        = body.get("contact_tel") or ""
    date_planifiee     = str(body.get("date_planifiee") or datetime.now().date().isoformat())[:10]
    if date_planifiee < datetime.now().date().isoformat():
        raise HTTPException(
            status_code=422,
            detail="La date prévue d'intervention doit être aujourd'hui ou une date future",
        )
    
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
        billing_case = None
        if billing_case_id is not None:
            billing_case = conn.execute(
                """SELECT id, request_id, intervention_id, client, equipment, case_state
                   FROM billing_cases
                   WHERE id = %s
                   FOR UPDATE""",
                (billing_case_id,),
            ).fetchone()
            if not billing_case:
                raise HTTPException(status_code=404, detail="Dossier de facturation introuvable")
            if billing_case.get("case_state") != "active":
                raise HTTPException(status_code=409, detail="Le dossier de facturation n'est pas actif")
            if billing_case.get("request_id") or billing_case.get("intervention_id"):
                raise HTTPException(
                    status_code=409,
                    detail="Ce dossier possède déjà une demande ou une intervention",
                )

            case_client = str(billing_case.get("client") or "").strip()
            case_equipment = str(billing_case.get("equipment") or "").strip()
            client = client or case_client
            equipement = equipement or case_equipment
            if case_client and client.casefold() != case_client.casefold():
                raise HTTPException(
                    status_code=409,
                    detail="Le client de la demande doit correspondre au dossier de facturation",
                )
            if case_equipment and equipement.casefold() != case_equipment.casefold():
                raise HTTPException(
                    status_code=409,
                    detail="L'équipement de la demande doit correspondre au dossier de facturation",
                )

        if equipement_id is not None:
            equipment_row = conn.execute(
                "SELECT id, nom, client FROM equipements WHERE id = %s",
                (equipement_id,),
            ).fetchone()
            if not equipment_row:
                raise HTTPException(status_code=404, detail="Équipement introuvable")
            equipment_client = str(equipment_row.get("client") or "").strip()
            if client and equipment_client and client.casefold() != equipment_client.casefold():
                raise HTTPException(status_code=409, detail="L'équipement ne correspond pas au client sélectionné")
            equipement = str(equipment_row.get("nom") or equipement).strip()
            client = client or equipment_client
        elif client.strip() and equipement.strip():
            # Compatibility with older clients: resolve the name once and
            # persist the selected ID so subsequent reads never join by name.
            # Never choose arbitrarily when duplicate names exist.
            equipment_rows = conn.execute(
                """SELECT id, nom, client FROM equipements
                   WHERE LOWER(BTRIM(nom)) = LOWER(BTRIM(%s))
                     AND LOWER(BTRIM(COALESCE(client, ''))) = LOWER(BTRIM(%s))
                   ORDER BY id""",
                (equipement, client),
            ).fetchall()
            if len(equipment_rows) > 1:
                raise HTTPException(
                    status_code=422,
                    detail="Plusieurs équipements portent ce nom pour ce client. Sélectionnez l'équipement par son identifiant.",
                )
            if len(equipment_rows) == 1:
                equipement_id = equipment_rows[0]["id"]

        # One equipment cannot have two simultaneous intervention requests.
        # The transaction-scoped advisory lock also closes the race between
        # two users submitting the same request at nearly the same time.
        if client.strip() and equipement.strip():
            if equipement_id is not None:
                lock_equipment_intervention_key(conn, equipement_id)
                existing_intervention = find_open_intervention(conn, equipement_id, client)
                if existing_intervention:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Une intervention est déjà ouverte #{existing_intervention['id']} "
                            "pour cet équipement. Utilisez l'intervention existante."
                        ),
                    )

            duplicate_key = (
                f"equipment::{equipement_id}"
                if equipement_id is not None
                else f"name::{client.strip().casefold()}::{equipement.strip().casefold()}"
            )
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (duplicate_key,))
            equipment_match = "d.equipement_id = %s" if equipement_id is not None else (
                "LOWER(BTRIM(d.client)) = LOWER(BTRIM(%s)) "
                "AND LOWER(BTRIM(d.equipement)) = LOWER(BTRIM(%s))"
            )
            equipment_params = (equipement_id,) if equipement_id is not None else (client, equipement)
            existing_request = conn.execute(
                f"""SELECT d.id, d.intervention_id, d.statut,
                          COALESCE(
                              (SELECT bc.id FROM billing_cases bc
                               WHERE bc.request_id = d.id ORDER BY bc.id LIMIT 1),
                              (SELECT bc.id FROM billing_cases bc
                               WHERE bc.intervention_id = d.intervention_id ORDER BY bc.id LIMIT 1)
                          ) AS billing_case_id
                   FROM demandes_intervention d
                   LEFT JOIN interventions i ON i.id = d.intervention_id
                   WHERE {equipment_match}
                     AND COALESCE(d.statut, '') !~* '(résol|resol|réalis|realis|clôt|clot|termin|annul)'
                     AND COALESCE(i.statut, '') !~* '(résol|resol|réalis|realis|clôt|clot|termin|annul)'
                   ORDER BY d.id DESC
                   LIMIT 1""",
                equipment_params,
            ).fetchone()
            if existing_request:
                existing_case = existing_request.get("billing_case_id")
                case_suffix = f" dans le dossier #{existing_case}" if existing_case else ""
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Une demande active #{existing_request['id']} existe déjà pour cet équipement"
                        f"{case_suffix}. Utilisez la demande existante pour éviter un doublon."
                    ),
                )

        # Create the DEMAND
        new_demande = conn.execute(f"""
            INSERT INTO demandes_intervention
              (date_demande, demandeur, client, equipement, equipement_id, urgence, priorite,
               description, code_erreur, contact_nom, contact_tel,
               statut, technicien_assigne, date_planifiee, notes_traitement, type_intervention)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            RETURNING id
        """, (
            body.get("date_demande") or now_str,
            demandeur, client, equipement, equipement_id, urgence, priorite,
            description, code_erreur, contact_nom, contact_tel,
            statut, ", ".join(techniciens_fullnames), date_planifiee,  # All techs in the demand
            body.get("notes_traitement") or "",
            type_intervention,
        )).fetchone()

        demande_id = new_demande["id"] if new_demande else None

        # A demand is visible in the maintenance planning as soon as it is
        # created. It remains "Planifiée", including on the scheduled day,
        # until one of the assigned technicians explicitly accepts it.
        planning_id = None
        if demande_id:
            planning = conn.execute(
                """INSERT INTO planning_maintenance
                   (machine, equipement_id, client, type_maintenance, description, date_prevue,
                    technicien_assigne, recurrence, statut, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    equipement, equipement_id,
                    client,
                    type_intervention,
                    description,
                    date_planifiee,
                    ", ".join(techniciens_fullnames),
                    "Aucune",
                    "Planifiée",
                    f"Demande #{demande_id}",
                ),
            ).fetchone()
            planning_id = planning["id"] if planning else None

        # --- Create SINGLE SHARED intervention (visible to all assigned technicians) ---
        # NEW APPROACH: One intervention for ALL technicians instead of N children
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notes_intervention = f"[{client}] Demande #{demande_id}"
        
        # Store all technicians in technicien field (comma-separated for reference)
        # Each tech will update their own row in interventions_techniciens
        all_techs_str = ", ".join(techniciens_fullnames)
        
        conn.execute(f"""
            INSERT INTO interventions
              (date, machine, equipement_id, technicien, type_intervention, description,
               probleme, code_erreur, statut, priorite, notes,
               is_temporary, parent_intervention_id, client, planning_id)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (
            now,
            equipement,
            equipement_id,
            all_techs_str,  # Store all technician names
            type_intervention,
            description[:500],
            description[:500],
            code_erreur,
            "Assignée",  # Always "Assignée" for multi-tech shared intervention
            urgence,
            notes_intervention,
            0,  # is_temporary = FALSE (visible to all technicians)
            None,  # No parent - this is a standalone intervention
            client,
            planning_id,
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

            # The intervention trigger creates a traceability case immediately.
            # When the request originates from a manual billing case, discard
            # that brand-new empty shell and attach the intervention to the
            # original case so its quote/order history and identifier survive.
            automatic_case = conn.execute(
                "SELECT id FROM billing_cases WHERE intervention_id = %s FOR UPDATE",
                (intervention_id,),
            ).fetchone()
            if billing_case_id is not None:
                if automatic_case and automatic_case["id"] != billing_case_id:
                    conn.execute("DELETE FROM billing_cases WHERE id = %s", (automatic_case["id"],))
                conn.execute(
                    """UPDATE billing_cases
                       SET request_id = %s, intervention_id = %s,
                           client = %s, equipment = %s,
                           updated_by = %s, updated_at = CURRENT_TIMESTAMP
                       WHERE id = %s""",
                    (
                        demande_id,
                        intervention_id,
                        client,
                        equipement,
                        user.get("sub") or user.get("nom") or "unknown",
                        billing_case_id,
                    ),
                )
                conn.execute(
                    """INSERT INTO billing_history (
                           case_id, action, entity_type, entity_id, after_data, actor_username
                       ) VALUES (
                           %s, 'LINK_REQUEST_AND_INTERVENTION', 'case', %s,
                           jsonb_build_object('request_id', %s, 'intervention_id', %s), %s
                       )""",
                    (
                        billing_case_id,
                        billing_case_id,
                        demande_id,
                        intervention_id,
                        user.get("sub") or user.get("nom") or "unknown",
                    ),
                )
            elif automatic_case:
                conn.execute(
                    """UPDATE billing_cases
                       SET request_id = %s, updated_at = CURRENT_TIMESTAMP
                       WHERE id = %s""",
                    (demande_id, automatic_case["id"]),
                )
                billing_case_id = automatic_case["id"]
        
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
    planned_date_display = date_planifiee
    try:
        planned_date_display = datetime.strptime(date_planifiee, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        pass
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
        f"\U0001f550 Date d'émission : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"\U0001f4c5 Date prévue d'intervention : <b>{planned_date_display}</b>\n\n"
        f"\U0001f449 Connectez-vous à <b>SAVIA</b> pour traiter cette demande."
    )
    _send_telegram(msg)
    
    # Log audit
    username = user.get("sub", "unknown")
    log_audit(username, "CREATE_DEMANDE", f"{{\"client\": \"{client}\", \"demande_id\": {demande_id}}}", "demandes")
    
    logger.info(f"Demande #{demande_id} créée avec {len(techniciens_fullnames)} techniciens → Intervention PARTAGÉE #{intervention_id}")
    
    return {
        "success": True,
        "demande_id": demande_id,
        "intervention_id": intervention_id,
        "billing_case_id": billing_case_id,
    }


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
                          (date, machine, client, technicien, type_intervention, description,
                           probleme, code_erreur, statut, priorite, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        now,
                        equipement,
                        client,
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
def update_technicien_data(intervention_id: int, request: Request, body: dict = Body(...), user: dict = Depends(_verify_token)):
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
    endpoint = f"/api/interventions/{intervention_id}/technicien-data"
    operation_id = operation_id_from_request(request)
    with get_db() as conn:
        assert_intervention_write_access(conn, intervention_id, user)
        cached_response = get_idempotent_response(operation_id, user.get("sub", ""), endpoint)
        if cached_response is not None:
            return cached_response

    from db_engine import (
        update_interventions_techniciens,
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
        current_tech_status = None
        retour_site_requis = False
        
        with get_db() as conn:
            intervention = conn.execute(
                """SELECT id, machine, technicien, statut,
                          date_transfert_atelier, retour_site_confirme
                   FROM interventions WHERE id = %s""",
                (intervention_id,)
            ).fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            # Extract intervention data
            machine = intervention.get("machine", "")
            technicien = intervention.get("technicien", "")
            retour_site_requis = retour_site_confirmation_requise(
                intervention.get("statut"),
                intervention.get("retour_site_confirme"),
            )
            
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
                    "SELECT technicien_nom, statut FROM interventions_techniciens WHERE intervention_id = %s",
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
                            current_tech_status = row_tech.get("statut")
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

                # A technician cannot reopen or move a completed assignment
                # from the PWA. Other technicians in a multi-tech intervention
                # keep their own status workflow unchanged.
                requested_status = body.get("statut")
                if current_tech_status == "Cloturee" and requested_status:
                    raise HTTPException(
                        status_code=409,
                        detail="Cette affectation est déjà clôturée. Aucune nouvelle mise à jour de statut n'est autorisée depuis le PWA."
                    )

                # In multi-technician mode, the transition source is the
                # current technician assignment rather than a historical
                # transfer date on the shared parent intervention.
                if current_tech_status:
                    retour_site_requis = retour_site_confirmation_requise(
                        current_tech_status,
                        intervention.get("retour_site_confirme"),
                    )

                requested_fiche_validation = body.get("fiche_validation")
                if requested_fiche_validation:
                    if requested_fiche_validation not in {"En attente", "Validée"}:
                        raise HTTPException(status_code=400, detail="Statut de fiche invalide")
                    fiche_row = conn.execute(
                        "SELECT fiche_validation FROM interventions WHERE id = %s",
                        (intervention_id,),
                    ).fetchone()
                    current_fiche_validation = (fiche_row.get("fiche_validation") or "En attente").strip() if fiche_row else "En attente"
                    if current_fiche_validation == "Validée" and requested_fiche_validation != current_fiche_validation:
                        raise HTTPException(
                            status_code=403,
                            detail="Fiche déjà validée — aucune modification possible"
                        )

            if (
                body.get("statut") == "Cloturee"
                and retour_site_requis
                and body.get("retour_site_confirme") is not True
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Confirmez que l'équipement a bien été transféré sur site avant de clôturer l'intervention.",
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

        # The diagnosis belongs to the intervention, not to an individual
        # technician. Keep accepting the legacy *_tech fields above for old
        # clients, while new PWA clients write these shared parent fields.
        shared_field_mapping = {
            "probleme": "probleme",
            "cause": "cause",
            "solution": "solution",
            "type_erreur": "type_erreur",
        }
        shared_updates = []
        shared_params = []
        for body_field, db_column in shared_field_mapping.items():
            if body_field in body:
                shared_updates.append(f"{db_column} = %s")
                shared_params.append(body.get(body_field) or "")
        if shared_updates:
            shared_params.append(intervention_id)
            with get_db() as conn:
                conn.execute(
                    f"UPDATE interventions SET {', '.join(shared_updates)} WHERE id = %s",
                    shared_params,
                )

        if body.get("statut") == "Cloturee" and retour_site_requis:
            with get_db() as conn:
                conn.execute(
                    """UPDATE interventions
                       SET retour_site_confirme = true,
                           date_retour_site = %s,
                           retour_site_confirme_par = %s
                       WHERE id = %s""",
                    (
                        datetime.now().isoformat(),
                        user.get("nom") or user.get("sub") or tech_nom,
                        intervention_id,
                    ),
                )

        if body.get("fiche_validation"):
            with get_db() as conn:
                conn.execute(
                    "UPDATE interventions SET fiche_validation = %s WHERE id = %s",
                    (body["fiche_validation"], intervention_id),
                )
        
        # Keep the shared parent intervention aligned with the technician's
        # active status. This is intentionally limited to the multi-tech flow.
        # Once one technician has sent the equipment to the workshop, another
        # technician saving "En cours" must not silently move the shared
        # equipment back to maintenance. The workshop state remains authoritative
        # until a technician explicitly confirms the return while closing.
        if not (
            retour_site_requis
            and body.get("statut") not in {"Transfert vers l'atelier", "Cloturee"}
        ):
            _synchroniser_statut_parent_multi_tech(
                intervention_id,
                body.get("statut"),
                update_intervention_statut,
            )

        if (
            body.get("statut") == "Transfert vers l'atelier"
            and current_tech_status != "Transfert vers l'atelier"
        ):
            notify_workshop_transfer(
                intervention_id,
                operation_id,
                {
                    "technicien_declarant": tech_nom,
                    "probleme": body.get("probleme_tech") or "",
                    "cause": body.get("cause_tech") or "",
                    "notes": body.get("notes_tech") or "",
                    "type_erreur": body.get("type_erreur_tech") or "",
                },
            )

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
                        send_telegram_reliably("telegram_stock", msg_tg, f"{operation_id}:stock")
                        send_telegram_reliably("telegram", "📬 " + msg_tg, f"{operation_id}:tech")
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
                        send_telegram_reliably("telegram_stock", msg_tg_m, f"{operation_id}:manual-stock")
                        send_telegram_reliably("telegram", msg_tg_m, f"{operation_id}:manual-tech")
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
                    send_telegram_reliably("telegram_sav", msg_sav, operation_id)
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
                    send_telegram_reliably("telegram", msg_tech, operation_id)
                    logger.info(f"✅ Telegram TECH message sent: Intervention #{intervention_id} clôturée")
                except Exception as te:
                    logger.warning(f"⚠️ Closing telegram notifications failed: {te}")
                
                response = {
                    "success": True,
                    "message": f"✅ Tous les techniciens ont complété! Intervention #{intervention_id} clôturée automatiquement.",
                    "intervention_finalized": True,
                    "status": "CLOSED",
                    "completed": status_info['completed'],
                    "total": status_info['total']
                }
                save_idempotent_response(operation_id, user.get("sub", ""), endpoint, response)
                return response
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
                    send_telegram_reliably("telegram", msg_tg, operation_id)
                    logger.info(f"✅ Partial closure telegram sent: Intervention #{intervention_id} ({status_info['completed']}/{status_info['total']} completed)")
                except Exception as te:
                    logger.warning(f"⚠️ Partial closure telegram notification failed (will retry later): {te}")
            else:
                logger.info(f"   ✓ Technician marked as '{body.get('statut')}' - no partial closure telegram sent")
            
            logger.info(f"   ✓ Returning PARTIAL response with {len(status_info['pending_names'])} pending: {status_info['pending_names']}")
            response = {
                "success": True,
                "message": f"Données sauvegardées ({status_info['completed']}/{status_info['total']} techniciens complétés)",
                "intervention_finalized": False,
                "status": "PARTIAL",
                "completed": status_info['completed'],
                "total": status_info['total'],
                "pending_technicians": status_info['pending_names']
            }
            save_idempotent_response(operation_id, user.get("sub", ""), endpoint, response)
            return response
        
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
            assert_resource_client_access(conn, "intervention", intervention_id, user)
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


def _current_technician_assignment(intervention_id: int, user: dict) -> dict:
    """Resolve the authenticated technician's stable assignment row."""
    from db_engine import get_or_create_interventions_techniciens

    technician_name = str(user.get("nom") or user.get("sub") or "").strip()
    if not technician_name:
        raise HTTPException(status_code=403, detail="Technicien non identifiable")
    get_or_create_interventions_techniciens(intervention_id, technician_name)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, technicien_nom FROM interventions_techniciens WHERE intervention_id = %s",
            (intervention_id,),
        ).fetchall()
    for row in rows:
        if _tech_name_or_username_matches(technician_name, row.get("technicien_nom") or ""):
            return dict(row)
    raise HTTPException(status_code=403, detail="Cette intervention ne vous est pas assignée")


@app.get("/api/interventions/{intervention_id}/work-sessions")
def get_intervention_work_sessions(intervention_id: int, user: dict = Depends(_verify_token)):
    """Return the dated work log used by the PWA and intervention sheet."""
    from db_engine import list_work_sessions

    with get_db() as conn:
        assert_resource_client_access(conn, "intervention", intervention_id, user)
    return list_work_sessions(intervention_id)


@app.put("/api/interventions/{intervention_id}/work-sessions")
def put_intervention_work_sessions(
    intervention_id: int,
    request: Request,
    body: dict = Body(...),
    user: dict = Depends(_verify_token),
):
    """Replace the authenticated technician's active work log, auditably."""
    from db_engine import replace_technician_work_sessions

    require_roles(user, "Technicien")
    endpoint = f"/api/interventions/{intervention_id}/work-sessions"
    operation_id = operation_id_from_request(request)
    username = str(user.get("sub") or "")
    with get_db() as conn:
        assert_intervention_write_access(conn, intervention_id, user)
        cached = get_idempotent_response(operation_id, username, endpoint)
        if cached is not None:
            return cached
    assignment = _current_technician_assignment(intervention_id, user)
    try:
        sessions = replace_technician_work_sessions(
            intervention_id,
            int(assignment["id"]),
            str(assignment["technicien_nom"]),
            body.get("sessions"),
            username or str(user.get("nom") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response = {"ok": True, "sessions": sessions}
    save_idempotent_response(operation_id, username, endpoint, response)
    return response


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
            assert_resource_client_access(conn, "intervention", intervention_id, user)
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
def accept_intervention(intervention_id: int, request: Request, user: dict = Depends(_verify_token)):
    from db_engine import get_db
    endpoint = f"/api/interventions/{intervention_id}/accept"
    operation_id = operation_id_from_request(request)
    with get_db() as conn:
        _assert_intervention_action_access(conn, intervention_id, user)
        row = conn.execute(
            """SELECT i.id, i.machine, i.client AS intervention_client, pm.client AS planning_client,
                      i.technicien, i.statut, i.planning_id,
                      d.id AS demande_id, d.client AS demande_client,
                      d.description AS demande_description, d.code_erreur AS demande_code_erreur,
                      d.date_planifiee
               FROM interventions i
               LEFT JOIN demandes_intervention d ON d.intervention_id = i.id
               LEFT JOIN planning_maintenance pm ON pm.id = i.planning_id
               WHERE i.id = %s""",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention introuvable")
        cached_response = get_idempotent_response(operation_id, user.get("sub", ""), endpoint)
        if cached_response is not None:
            return cached_response
        client = str(
            row.get("demande_client") or row.get("intervention_client") or row.get("planning_client") or ""
        ).strip()
        if client and not str(row.get("intervention_client") or "").strip():
            conn.execute("UPDATE interventions SET client = %s WHERE id = %s", (client, intervention_id))

        # L'entrée du planning existe dès la création de la demande. Le
        # technicien peut toutefois l'accepter uniquement le jour prévu.
        if row.get("demande_id"):
            today_str = datetime.now().date().isoformat()
            planned_date = str(row.get("date_planifiee") or today_str)[:10]
            if planned_date != today_str:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cette intervention peut être acceptée uniquement le {planned_date}"
                    ),
                )
            planning_status = "En cours" if planned_date <= today_str else "Planifiée"
            technician = str(row.get("technicien") or user.get("nom") or user.get("username") or "").strip()
            planning_id = row.get("planning_id")

            if not planning_id:
                existing_planning = conn.execute(
                    """SELECT id FROM planning_maintenance
                       WHERE notes = %s ORDER BY id DESC LIMIT 1""",
                    (f"Demande #{row['demande_id']}",),
                ).fetchone()
                planning_id = existing_planning["id"] if existing_planning else None

            if planning_id:
                conn.execute(
                    """UPDATE planning_maintenance
                       SET machine = %s, client = %s, type_maintenance = %s,
                           description = %s, date_prevue = %s,
                           technicien_assigne = %s, statut = %s
                       WHERE id = %s""",
                    (
                        row.get("machine") or "",
                        row.get("demande_client") or "",
                        "Corrective",
                        row.get("demande_description") or "",
                        planned_date,
                        technician,
                        planning_status,
                        planning_id,
                    ),
                )
            else:
                planning = conn.execute(
                    """INSERT INTO planning_maintenance
                       (machine, client, type_maintenance, description, date_prevue,
                        technicien_assigne, recurrence, statut, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        row.get("machine") or "",
                        row.get("demande_client") or "",
                        "Corrective",
                        row.get("demande_description") or "",
                        planned_date,
                        technician,
                        "Aucune",
                        planning_status,
                        f"Demande #{row['demande_id']}",
                    ),
                ).fetchone()
                planning_id = planning["id"] if planning else None

            # Le lien permet au planning et aux listes d'interventions de
            # rester synchronisés sans recréer une intervention.
            if planning_status == "En cours":
                conn.execute(
                    """UPDATE interventions
                       SET date = %s, statut = %s, planning_id = %s,
                           date_debut_intervention = COALESCE(date_debut_intervention, CURRENT_TIMESTAMP)
                       WHERE id = %s""",
                    (planned_date, planning_status, planning_id, intervention_id),
                )
            else:
                conn.execute(
                    """UPDATE interventions
                       SET date = %s, statut = %s, planning_id = %s
                       WHERE id = %s""",
                    (planned_date, planning_status, planning_id, intervention_id),
                )
            conn.execute(
                """UPDATE demandes_intervention
                   SET statut = 'En cours', date_planifiee = %s,
                       date_traitement = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (planned_date, row["demande_id"]),
            )
        else:
            # Les interventions créées hors demande gardent le comportement
            # historique : l'acceptation les démarre immédiatement.
            conn.execute(
                """UPDATE interventions
                   SET statut = 'En cours',
                       date_debut_intervention = COALESCE(date_debut_intervention, CURRENT_TIMESTAMP)
                   WHERE id = %s""",
                (intervention_id,),
            )

        # A multi-technician intervention is shared: the first acceptance
        # starts the parent and releases every assigned technician's work form.
        conn.execute(
            """UPDATE interventions_techniciens
               SET statut = 'En cours', updated_at = CURRENT_TIMESTAMP
               WHERE intervention_id = %s AND statut = 'Assigné'""",
            (intervention_id,),
        )

    tech_name = user.get("nom") or user.get("username") or "?"
    machine = row["machine"] if row else ""
    client = client or "Non renseigné"
    accepted_status = "En cours"
    if row and row.get("demande_id"):
        accepted_status = "En cours" if str(row.get("date_planifiee") or datetime.now().date().isoformat())[:10] <= datetime.now().date().isoformat() else "Planifiée"
    msg = (
        f"\u2705 <b>INTERVENTION #{intervention_id} — ACCEPTÉE</b>\n\n"
        f"\U0001f477 Technicien : <b>{tech_name}</b>\n"
        f"🏢 Client : <b>{client}</b>\n"
        f"\U0001f3e5 Équipement : <b>{machine}</b>\n"
        f"\U0001f4ca Statut : <b>{accepted_status}</b>\n"
        f"\U0001f550 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_telegram(msg)

    response = {"success": True, "statut": accepted_status}
    save_idempotent_response(operation_id, user.get("sub", ""), endpoint, response)
    return response


@app.put("/api/interventions/{intervention_id}/refuse")
def refuse_intervention(intervention_id: int, request: Request, body: dict, user: dict = Depends(_verify_token)):
    from db_engine import get_db
    endpoint = f"/api/interventions/{intervention_id}/refuse"
    operation_id = operation_id_from_request(request)
    raison = body.get("raison", "").strip()
    if not raison:
        raise HTTPException(status_code=400, detail="La raison du refus est obligatoire")

    with get_db() as conn:
        _assert_intervention_action_access(conn, intervention_id, user)
        row = conn.execute(
            """SELECT id, machine, technicien, statut, notes,
                      COALESCE(NULLIF(interventions.client, ''), e.client, '') AS client
               FROM interventions
               LEFT JOIN equipements e ON e.id = interventions.equipement_id
               WHERE interventions.id = %s""",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention introuvable")
        cached_response = get_idempotent_response(operation_id, user.get("sub", ""), endpoint)
        if cached_response is not None:
            return cached_response

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

    response = {"success": True, "statut": "En attente"}
    save_idempotent_response(operation_id, user.get("sub", ""), endpoint, response)
    return response


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
