"""Intervention lifecycle and signed-file routes."""

from api.runtime import (
    Body,
    Depends,
    File,
    HTTPException,
    JWT_SECRET,
    Optional,
    Query,
    Request,
    UploadFile,
    _get_technician_fullname,
    _tech_name_or_username_matches,
    ajouter_intervention,
    ajouter_notification_piece,
    ajouter_piece_demandee,
    app,
    cloturer_intervention,
    datetime,
    get_db,
    jwt,
    lire_equipements,
    lire_interventions,
    log_audit,
    logger,
    update_intervention_statut,
)
from api.security import (
    Depends,
    HTTPException,
    JWT_SECRET,
    Optional,
    _verify_token,
    assert_resource_client_access,
    assert_intervention_write_access,
    require_roles,
    resolve_client_scope,
    get_db,
    jwt,
)
from services.scheduled_jobs import (
    _df_to_records,
    _send_telegram,
    _send_telegram_bot,
    send_telegram_reliably,
    notify_workshop_transfer,
    get_db,
    lire_equipements,
    lire_interventions,
    logger,
    sync_planning_to_interventions,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    JWT_SECRET,
    Optional,
    _get_client_filter,
    _verify_token,
    app,
    datetime,
    get_db,
    jwt,
    lire_equipements,
    lire_interventions,
    log_audit,
    logger,
)
from services.file_security import read_validated_upload
from services.idempotency import (
    get_idempotent_response,
    operation_id_from_request,
    save_idempotent_response,
)
from repositories.interventions import (
    InterventionAlreadyOpenError,
)


async def _store_fiche(upload: UploadFile, intervention_id: int, username: str) -> dict:
    """Validate then store a fiche under a server-generated private object key."""
    validated = await read_validated_upload(upload, "fiche")
    from s3_storage import upload_private_file

    stored = upload_private_file(
        validated.data,
        category="fiches",
        extension=validated.extension,
        content_type=validated.content_type,
        original_name=validated.display_name,
        content_hash=validated.sha256,
        metadata={"intervention-id": intervention_id, "uploaded-by": username},
    )
    if not stored:
        raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
    with get_db() as conn:
        previous = conn.execute(
            "SELECT fiche_storage_key FROM interventions WHERE id = %s", (intervention_id,)
        ).fetchone()
        old_key = previous.get("fiche_storage_key") if previous else None
        conn.execute(
            """UPDATE interventions
               SET fiche_photo_nom = %s, fiche_photo_data = NULL,
                   fiche_storage_key = %s, fiche_content_type = %s,
                   fiche_size_bytes = %s, fiche_sha256 = %s
               WHERE id = %s""",
            (validated.display_name, stored["s3_key"], validated.content_type,
             stored["size_bytes"], validated.sha256, intervention_id),
        )
    if old_key and old_key != stored["s3_key"]:
        try:
            from s3_storage import delete_file
            delete_file(old_key)
        except Exception:
            logger.warning("Unable to remove replaced fiche object for intervention %s", intervention_id)
    return {"ok": True, "filename": validated.display_name}


def _planning_id_in_set(value, planning_ids):
    """Compare dataframe identifiers without leaking NaN/string type issues."""
    try:
        return int(value) in {int(planning_id) for planning_id in planning_ids}
    except (TypeError, ValueError):
        return False

@app.get("/api/interventions")
def get_interventions(
    machine: Optional[str] = None,
    technicien: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
    user: dict = Depends(_verify_token),
):
    from db_engine import lire_child_interventions_for_technician, get_db

    # Filet de sécurité : si le worker n'a pas tourné à l'heure prévue,
    # rattraper les maintenances échues avant de construire les listes web/PWA.
    try:
        sync_planning_to_interventions(notify=False)
    except Exception as exc:
        logger.warning("Planning sync before intervention listing failed: %s", exc)
    
    df = lire_interventions(machine=machine)
    
    # Si le user est un Technicien → filtrer automatiquement ses interventions
    # ET inclure ses interventions enfants (temporary child interventions)
    # ET inclure les interventions assignées via interventions_techniciens (multi-tech mode)
    if user.get("role") == "Technicien":
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
            logger.warning("Unable to resolve technician ID for %s: %s", user_username, exc)
        # Filter by name (primary) or username (secondary)
        if not df.empty:
            if technician_id is not None and "technicien_id" in df.columns:
                id_matches = df["technicien_id"].apply(lambda value: str(value).isdigit() and int(value) == technician_id)
                name_matches = df["technicien"].astype(str).apply(
                    lambda t: _tech_name_or_username_matches(user_nom_complet, t) or _tech_name_or_username_matches(user_username, t)
                ) if "technicien" in df.columns else False
                df = df[id_matches | name_matches]
            elif user_nom_complet and "technicien" in df.columns:
                df = df[df["technicien"].astype(str).apply(
                    lambda t: _tech_name_or_username_matches(user_nom_complet, t) or _tech_name_or_username_matches(user_username, t)
                )]
        
        # Also fetch child interventions assigned to this technician
        try:
            df_children = lire_child_interventions_for_technician(user_nom_complet)
            if not df_children.empty:
                # Combine parent and child interventions
                import pandas as pd
                df = pd.concat([df, df_children], ignore_index=True)
                logger.info(f"Technician {user_nom_complet}: {len(df)} total interventions (parents + children)")
        except Exception as e:
            logger.warning(f"Error fetching child interventions for {user_nom_complet}: {e}")
            # Continue with just parent interventions if children fetch fails
            pass
        
        # Also fetch interventions assigned via interventions_techniciens table (multi-tech mode from Planning)
        try:
            with get_db() as conn:
                # Find intervention IDs where this technician is assigned
                tech_intervention_ids = conn.execute(
                    """SELECT DISTINCT intervention_id FROM interventions_techniciens
                       WHERE (%s IS NOT NULL AND technicien_id = %s)
                          OR (%s IS NULL AND (technicien_nom ILIKE %s OR technicien_nom ILIKE %s))""",
                    (technician_id, technician_id, technician_id, f"%{user_nom_complet}%", f"%{user_username}%")
                ).fetchall()
                
                if tech_intervention_ids:
                    ids_list = [str(row['intervention_id']) for row in tech_intervention_ids]
                    # Fetch full intervention records for these IDs
                    if ids_list:
                        id_placeholders = ",".join(["%s"] * len(ids_list))
                        multi_tech_rows = conn.execute(
                            f"""SELECT * FROM interventions WHERE id IN ({id_placeholders})""",
                            ids_list
                        ).fetchall()
                        
                        if multi_tech_rows:
                            import pandas as pd
                            df_multi_tech = pd.DataFrame([dict(r) for r in multi_tech_rows])
                            # Merge with existing dataframe, avoiding duplicates
                            df = pd.concat([df, df_multi_tech], ignore_index=True).drop_duplicates(subset=['id'], keep='first')
                            logger.info(f"Technician {user_nom_complet}: added {len(df_multi_tech)} multi-tech interventions")
        except Exception as e:
            logger.warning(f"Error fetching multi-tech interventions for {user_nom_complet}: {e}")
            # Continue with previous results if this fetch fails
            pass

    elif technicien and not df.empty and "technicien" in df.columns:
        df = df[df["technicien"].astype(str).apply(
            lambda t: _tech_name_or_username_matches(technicien, t)
        )]

    # A maintenance planned for a future date must not appear in any
    # intervention queue before its planned day. This keeps the SAV table
    # consistent with the technician PWA while leaving the planning page as
    # the source of truth for future scheduled work.
    if not df.empty and "planning_id" in df.columns:
        try:
            with get_db() as conn:
                future_planning_rows = conn.execute(
                    """
                    SELECT id
                    FROM planning_maintenance
                    WHERE date_prevue > CURRENT_DATE
                      AND statut NOT IN ('Cloturee', 'Réalisée', 'Terminée', 'Annulée')
                    """
                ).fetchall()
            future_planning_ids = {
                row.get("id")
                for row in future_planning_rows
                if row.get("id") is not None
            }
            if future_planning_ids:
                df = df[~df["planning_id"].apply(
                    lambda value: _planning_id_in_set(value, future_planning_ids)
                )]
        except Exception as e:
            logger.warning(f"Error filtering future planned interventions: {e}")
    
    # Filtrage par client pour Lecteur
    client_filter = _get_client_filter(user)
    if client_filter and not df.empty and "client" in df.columns:
        df = df[df["client"].astype(str).str.casefold() == client_filter.casefold()]
    
    # Apply pagination (offset + limit)
    if not df.empty:
        total = len(df)
        df = df.iloc[offset:offset + limit]
    else:
        total = 0
    
    # Enrich technicien field with multi-tech assignments for display
    records = _df_to_records(df)
    try:
        with get_db() as conn:
            for record in records:
                intervention_id = record.get('id')
                if intervention_id:
                    # Get all technicians assigned via interventions_techniciens
                    multi_tech_rows = conn.execute(
                        """SELECT DISTINCT technicien_nom, duree_minutes_tech, statut FROM interventions_techniciens
                           WHERE intervention_id = %s ORDER BY technicien_nom""",
                        (intervention_id,)
                    ).fetchall()
                    
                    if multi_tech_rows:
                        # Multiple technicians assigned via planning
                        tech_names = [row['technicien_nom'] for row in multi_tech_rows]
                        record['techniciens_detail'] = [
                            {
                                'nom': row.get('technicien_nom', ''),
                                'duree_minutes': row.get('duree_minutes_tech', 0) or 0,
                                'statut': row.get('statut', ''),
                            }
                            for row in multi_tech_rows
                        ]
                        # Update technicien field to show comma-separated list of all assigned techs
                        record['technicien'] = ", ".join(tech_names) if tech_names else record.get('technicien', 'Non assigné')
                    elif not record.get('technicien') or record.get('technicien') == 'Non assigné':
                        # No direct assignment and no multi-tech assignment
                        record['technicien'] = 'Non assigné'
    except Exception as e:
        logger.warning(f"Error enriching technicien field: {e}")
        # Continue with un-enriched records if this step fails
    
    return records


@app.get("/api/interventions/filter-options")
def get_intervention_filter_options(
    year: Optional[int] = None,
    month: Optional[int] = None,
    client: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Return filter values from all interventions in the selected period."""
    import pandas as pd

    try:
        sync_planning_to_interventions(notify=False)
    except Exception as exc:
        logger.warning("Planning sync before intervention filter options failed: %s", exc)

    df = lire_interventions()
    if df is None or df.empty:
        return {"types": [], "equipements": [], "clients": [], "statuts": [], "annees": []}

    # Keep the options identical to the SAV table: future planned work is
    # visible in Planning first, not in the intervention queue.
    if "planning_id" in df.columns:
        try:
            with get_db() as conn:
                future_planning_rows = conn.execute(
                    """
                    SELECT id
                    FROM planning_maintenance
                    WHERE date_prevue > CURRENT_DATE
                      AND statut NOT IN ('Cloturee', 'Réalisée', 'Terminée', 'Annulée')
                    """
                ).fetchall()
            future_planning_ids = {
                row.get("id")
                for row in future_planning_rows
                if row.get("id") is not None
            }
            if future_planning_ids:
                df = df[~df["planning_id"].apply(
                    lambda value: _planning_id_in_set(value, future_planning_ids)
                )]
        except Exception as exc:
            logger.warning("Future planning filter options check failed: %s", exc)

    dates = pd.to_datetime(df.get("date"), errors="coerce")
    all_years = sorted({int(value.year) for value in dates.dropna()}, reverse=True)
    period_mask = dates.notna()
    if year is not None:
        period_mask &= dates.dt.year.eq(year)
    if month is not None and 1 <= month <= 12:
        period_mask &= dates.dt.month.eq(month)

    client_filter = _get_client_filter(user)
    if client_filter and "client" in df.columns:
        period_mask &= df["client"].astype(str).str.casefold().eq(client_filter.casefold())

    period_df = df.loc[period_mask].copy()
    if client and "client" in period_df.columns:
        equipment_df = period_df[period_df["client"].astype(str).str.casefold().eq(client.casefold())]
    else:
        equipment_df = period_df

    def values(frame, column):
        if frame.empty or column not in frame.columns:
            return []
        return sorted({str(value).strip() for value in frame[column].dropna() if str(value).strip()})

    types = values(period_df, "type_intervention")
    statuses = values(period_df, "statut")
    if statuses:
        normalized_statuses = set()
        for status in statuses:
            low = status.lower()
            if "atelier" in low or "transfert" in low:
                normalized_statuses.add("Transfert vers l'atelier")
            elif "tur" in low or "termin" in low or "clotur" in low:
                normalized_statuses.add("Cloturee")
            elif "attente" in low and "pi" in low:
                normalized_statuses.add("En attente de piece")
            elif "cours" in low:
                normalized_statuses.add("En cours")
            elif "planif" in low:
                normalized_statuses.add("Planifiee")
            else:
                normalized_statuses.add(status)
        statuses = sorted(normalized_statuses)

    return {
        "types": types,
        "equipements": values(equipment_df, "machine"),
        "clients": values(period_df, "client"),
        "statuts": statuses,
        "annees": all_years,
    }


@app.get("/api/interventions/{parent_id}/children")
def get_child_interventions_endpoint(
    parent_id: int,
    user: dict = Depends(_verify_token),
):
    """
    Récupère les interventions enfants d'une intervention parent.
    Utilisé par PWA pour afficher les technicians assignés à une demande.
    """
    from db_engine import get_child_interventions
    
    try:
        with get_db() as conn:
            assert_resource_client_access(conn, "intervention", parent_id, user)
        children = get_child_interventions(parent_id)
        return {
            "success": True,
            "parent_id": parent_id,
            "children": children,
            "count": len(children)
        }
    except Exception as e:
        logger.error(f"Error fetching child interventions for parent {parent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des enfants: {str(e)}")


@app.post("/api/interventions")
def create_intervention(body: dict, user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    body["client"] = resolve_client_scope(user, body.get("client")) or ""
    equipment_id = body.get("equipement_id")
    if equipment_id not in (None, ""):
        with get_db() as conn:
            try:
                equipment_id = int(equipment_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Identifiant d'équipement invalide")
            equipment = conn.execute(
                "SELECT id, nom, client FROM equipements WHERE id = %s",
                (equipment_id,),
            ).fetchone()
            if not equipment:
                raise HTTPException(status_code=404, detail="Équipement introuvable")
            if body.get("client") and equipment.get("client") and body["client"].casefold() != str(equipment["client"]).casefold():
                raise HTTPException(status_code=409, detail="L'équipement ne correspond pas au client sélectionné")
            body["machine"] = equipment["nom"]
            body["client"] = body["client"] or equipment["client"] or ""
        body["equipement_id"] = equipment_id
    elif not body["client"] and body.get("machine"):
        with get_db() as conn:
            equipment = conn.execute(
                """SELECT id, nom, client FROM equipements
                   WHERE LOWER(BTRIM(nom)) = LOWER(BTRIM(%s))
                     AND NULLIF(BTRIM(client), '') IS NOT NULL
                   ORDER BY id""",
                (body["machine"],),
            ).fetchall()
        if len(equipment) > 1:
            raise HTTPException(
                status_code=422,
                detail="Plusieurs équipements portent ce nom. Sélectionnez l'équipement par son identifiant.",
            )
        if len(equipment) == 1:
            body["equipement_id"] = equipment[0]["id"]
            body["client"] = equipment[0]["client"] or ""
    elif body.get("client") and body.get("machine"):
        # Legacy callers may still send a name. Resolve it only when that
        # name identifies one equipment for this client; never guess between
        # duplicate equipment names.
        with get_db() as conn:
            equipment = conn.execute(
                """
                SELECT id, nom, client
                FROM equipements
                WHERE LOWER(BTRIM(nom)) = LOWER(BTRIM(%s))
                  AND LOWER(BTRIM(COALESCE(client, ''))) = LOWER(BTRIM(%s))
                ORDER BY id
                """,
                (body["machine"], body["client"]),
            ).fetchall()
        if len(equipment) > 1:
            raise HTTPException(
                status_code=422,
                detail="Plusieurs équipements portent ce nom pour ce client. Sélectionnez l'équipement par son identifiant.",
            )
        if len(equipment) == 1:
            body["equipement_id"] = equipment[0]["id"]
            body["machine"] = equipment[0]["nom"]

    if body.get("equipement_id") not in (None, ""):
        try:
            body["equipement_id"] = int(body["equipement_id"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Identifiant d'équipement invalide")
    
    # Convert technicien username to full name (nom + prenom)
    technicien_username = body.get("technicien", "")
    if technicien_username:
        body["technicien"] = _get_technician_fullname(technicien_username)
    
    try:
        intervention_id = ajouter_intervention(body)
    except InterventionAlreadyOpenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "machine": body.get("machine", ""),
        "type": body.get("type_intervention", ""),
        "technicien": body.get("technicien", ""),
        "priorite": body.get("priorite", ""),
    }, ensure_ascii=False)
    log_audit(username, "CREATE_INTERVENTION", details, "interventions")
    
    # Notification Telegram au bot technique
    try:
        machine = body.get("machine", "N/A")
        technicien = body.get("technicien", "N/A")
        type_interv = body.get("type_intervention", "N/A")
        priorite = body.get("priorite", "Moyenne")
        description = body.get("description", "") or body.get("probleme", "")
        client = body.get("client", "")
        msg = (
            f"🔧 <b>Nouvelle Intervention</b>\n"
            f"📋 Machine : <b>{machine}</b>\n"
            f"{'🏢 Client : ' + client + chr(10) if client else ''}"
            f"👨‍🔧 Technicien : {technicien}\n"
            f"🔹 Type : {type_interv}\n"
            f"⚡ Priorité : {priorite}\n"
            f"{'📝 ' + description[:200] + chr(10) if description else ''}"
            f"📅 Date : {body.get('date', 'N/A')}"
        )
        _send_telegram_bot("telegram", msg)
    except Exception as e:
        logger.warning(f"Notification Telegram nouvelle intervention échouée: {e}")
    return {"ok": True, "id": intervention_id}


@app.put("/api/interventions/{intervention_id}")
def update_intervention(intervention_id: int, request: Request, body: dict = Body(...), user: dict = Depends(_verify_token)):
    endpoint = f"/api/interventions/{intervention_id}"
    operation_id = operation_id_from_request(request)
    with get_db() as conn:
        require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
        assert_intervention_write_access(conn, intervention_id, user)
        cached_response = get_idempotent_response(operation_id, user.get("sub", ""), endpoint)
        if cached_response is not None:
            return cached_response
        intervention_state = conn.execute(
            """SELECT statut, date_transfert_atelier, retour_site_confirme
               FROM interventions WHERE id = %s""",
            (intervention_id,),
        ).fetchone()
        previous_status = str(intervention_state.get("statut") or "").strip() if intervention_state else ""
    logger.info(f"📥 update_intervention #{intervention_id} received: {body}")
    
    # Vérifier les permissions : un technicien ne peut éditer que ses interventions
    if user.get("role") == "Technicien":
        with get_db() as conn:
            row = conn.execute(
                "SELECT technicien, statut FROM interventions WHERE id = %s",
                (intervention_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            current_tech = str(row.get("technicien") or "").strip()
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

            requested_status = body.get("statut")
            current_status = str(row.get("statut") or "").strip()
            if current_status == "Cloturee" and requested_status:
                raise HTTPException(
                    status_code=409,
                    detail="Cette intervention est déjà clôturée. Aucune nouvelle mise à jour de statut n'est autorisée depuis le PWA."
                )
    
    new_statut = body.get("statut")

    # A manager/admin reopening a multi-tech parent must also reopen each
    # technician assignment. Otherwise the PWA correctly keeps the assignment
    # locked at Cloturee even though the parent displays En cours.
    if (
        user.get("role") in {"Admin", "Manager", "Responsable Technique"}
        and previous_status == "Cloturee"
        and new_statut
        and "tur" not in str(new_statut).lower()
        and (
            "cours" in str(new_statut).lower()
            or "attente" in str(new_statut).lower()
            or "atelier" in str(new_statut).lower()
        )
    ):
        if "attente" in str(new_statut).lower():
            reopened_tech_status = "En attente de piece"
        elif "atelier" in str(new_statut).lower():
            reopened_tech_status = "Transfert vers l'atelier"
        else:
            reopened_tech_status = "En cours"
        with get_db() as conn:
            result = conn.execute(
                "UPDATE interventions_techniciens SET statut = %s, updated_at = CURRENT_TIMESTAMP WHERE intervention_id = %s AND statut = 'Cloturee'",
                (reopened_tech_status, intervention_id),
            )
            logger.info(
                f"🔓 Intervention #{intervention_id} rouverte par {user.get('nom') or user.get('sub')}: "
                f"affectations techniciens synchronisées vers {reopened_tech_status}"
            )

    if new_statut and "tur" in new_statut.lower():
        # Normaliser pieces_a_deduire : s'assurer que c'est une liste de dicts avec clé 'ref' ou 'reference'
        raw_pieces = body.get("pieces_a_deduire") or []
        if not isinstance(raw_pieces, list):
            raw_pieces = []
        # Accepter 'ref' ou 'reference', 'qty' ou 'quantite'
        pieces_valides = []
        for p in raw_pieces:
            if isinstance(p, dict):
                ref = p.get("ref") or p.get("reference")
                if ref:
                    pieces_valides.append({
                        'ref': ref,
                        'reference': ref,
                        'qty': p.get("qty") or p.get("quantite") or 0,
                        'quantite': p.get("qty") or p.get("quantite") or 0,
                        'designation': p.get("designation", ""),
                        'prix_unitaire': p.get("prix_unitaire", 0),
                    })

        try:
            ok, msg = cloturer_intervention(
                intervention_id,
                body.get("probleme", ""),
                body.get("cause", ""),
                body.get("solution", ""),
                pieces_a_deduire=pieces_valides if pieces_valides else None,
                duree_minutes=body.get("duree_minutes", 0),
                start_time=body.get("start_time"),
                end_time=body.get("end_time"),
                duree_deplacement=body.get("deplacement"),  # PWA sends "deplacement"
                retour_site_confirme=body.get("retour_site_confirme") is True,
                retour_site_confirme_par=user.get("nom") or user.get("sub") or "",
            )
            if not ok:
                raise HTTPException(status_code=400, detail=msg)

            # --- Update type_erreur if provided ---
            if body.get("type_erreur"):
                with get_db() as conn:
                    conn.execute(
                        "UPDATE interventions SET type_erreur = %s WHERE id = %s",
                        (body.get("type_erreur"), intervention_id)
                    )

            # --- Telegram notification clôture ---
            try:
                with get_db() as conn:
                    row = conn.execute(
                        """SELECT i.machine, i.technicien, i.probleme, i.cause, i.solution,
                                  i.duree_minutes, i.duree_deplacement, i.notes, i.pieces_utilisees,
                                  bc.coverage_status, bc.coverage_reason,
                                  bc.contract_id
                           FROM interventions i
                           LEFT JOIN billing_cases bc ON bc.intervention_id=i.id
                           WHERE i.id = %s""",
                        (intervention_id,)
                    ).fetchone()
                if row:
                    d = dict(row)
                    # Convert technicien username to full name
                    if d.get('technicien'):
                        d['technicien'] = _get_technician_fullname(d['technicien'])
                    else:
                        # Si pas de technicien principal, récupérer depuis interventions_techniciens
                        tech_rows = conn.execute(
                            "SELECT technicien_nom FROM interventions_techniciens WHERE intervention_id = %s ORDER BY technicien_nom",
                            (intervention_id,)
                        ).fetchall()
                        if tech_rows:
                            tech_names = [str(row.get('technicien_nom', '')).strip() for row in tech_rows]
                            d['technicien'] = ', '.join(tech_names)
                    duree_h = round((d.get('duree_minutes') or 0) / 60, 1)
                    deplacement_h = round((d.get('duree_deplacement') or 0) / 60, 1)
                    notes_raw = str(d.get('notes', '') or '')
                    # Extraire client depuis notes [Client]
                    client_name = notes_raw[1:notes_raw.index(']')] if notes_raw.startswith('[') and ']' in notes_raw else ''
                    # Si pas de client dans notes, chercher via equipement
                    if not client_name:
                        try:
                            eq_row = conn.execute(
                                "SELECT \"Client\" FROM equipements WHERE \"Nom\" = %s LIMIT 1",
                                (d.get('machine', ''),)
                            ).fetchone()
                            if eq_row:
                                client_name = eq_row['Client'] or ''
                        except Exception:
                            pass
                    pieces = str(d.get('pieces_utilisees', '') or '').strip()
                    notes_line = f"\n📌 Notes : {notes_raw}" if notes_raw and not notes_raw.startswith('[') else ""
                    client_line = f"\n👤 Client : <b>{client_name}</b>" if client_name else ""
                    pieces_line = f"\n🔩 Pièces : {pieces}" if pieces else ""
                    deplacement_line = f"\n\U0001f697 D\u00e9placement : <b>{deplacement_h}h</b>"
                    msg_tg = (
                        f"✅ <b>INTERVENTION CLÔTURÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{d.get('machine', '')}</b>"
                        f"{client_line}\n"
                        f"👷 Technicien : <b>{d.get('technicien', '')}</b>\n"
                        f"🔴 Problème : {str(d.get('probleme', ''))[:200]}\n"
                        f"🔍 Cause : {str(d.get('cause', ''))[:200]}\n"
                        f"🟢 Solution : {str(d.get('solution', ''))[:200]}\n"
                        f"⏱️ Durée : <b>{duree_h}h</b>"
                        f"{deplacement_line}"
                        f"{pieces_line}"
                        f"{notes_line}\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    send_telegram_reliably("telegram", msg_tg, operation_id)
                    coverage_status = str(d.get('coverage_status') or 'unassessed')
                    coverage_meta = {
                        'covered': ('Couvert par contrat — aucune facture', '✅'),
                        'partial': ('Partiellement facturable', '🟠'),
                        'billable': ('À facturer', '📋'),
                        'review': ('Couverture contractuelle à vérifier', '⚠️'),
                        'unassessed': ('Couverture à évaluer', '⚠️'),
                    }
                    coverage_label, coverage_icon = coverage_meta.get(coverage_status, coverage_meta['unassessed'])
                    contract_line = f"\n📄 Contrat : <b>#{d.get('contract_id')}</b>" if d.get('contract_id') else ""
                    # Notification SAV alignée sur la décision contractuelle.
                    msg_sav = (
                        f"{coverage_icon} <b>Intervention clôturée — {coverage_label}</b>\n\n"
                        f"🔧 Intervention <b>#{intervention_id}</b>\n"
                        f"🏥 Machine : <b>{d.get('machine', '')}</b>"
                        f"{client_line}\n"
                        f"👷 Technicien : {d.get('technicien', '')}\n"
                        f"⏱️ Durée : {duree_h}h"
                        f"\n\U0001f697 D\u00e9placement : {deplacement_h}h"
                        f"{pieces_line}"
                        f"{contract_line}\n"
                        f"ℹ️ <i>{d.get('coverage_reason') or 'Dossier disponible dans le module Suivi Facturation'}</i>\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    send_telegram_reliably("telegram_sav", msg_sav, operation_id)
            except Exception as te:
                logger.error(f"Telegram clôture erreur: {te}")

            # --- Mettre à jour la demande liée (si elle existe) → statut "Résolue" ---
            try:
                with get_db() as conn:
                    conn.execute(
                        """UPDATE demandes_intervention
                           SET statut = 'Résolue',
                               date_traitement = %s
                         WHERE intervention_id = %s
                           AND statut != 'Résolue'""",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), intervention_id)
                    )
                    logger.info(f"Demande liée à l'intervention #{intervention_id} marquée Résolue")
            except Exception as de:
                logger.error(f"Erreur mise à jour demande liée: {de}")

            # --- Mettre à jour le planning lié et son historique décalé ---
            try:
                with get_db() as conn:
                    prow = conn.execute(
                        "SELECT planning_id FROM interventions WHERE id = %s",
                        (intervention_id,)
                    ).fetchone()
                    if prow and prow['planning_id']:
                        pm_id = prow['planning_id']
                        conn.execute(
                            """UPDATE planning_maintenance
                               SET statut = 'Cloturee',
                                   date_realisee = %s
                             WHERE id = %s AND statut != 'Cloturee'""",
                            (datetime.now().strftime("%Y-%m-%d"), pm_id)
                        )
                        logger.info(f"Planning #{pm_id} marqué Cloturee (intervention #{intervention_id} clôturée)")
            except Exception as pe:
                logger.error(f"Erreur mise à jour planning lié: {pe}")

            # cloturer_intervention returns above the generic field-update
            # block. Persist the signed-fiche status here as well so a PWA
            # closure does not silently discard the technician's selection.
            if "fiche_validation" in body:
                fiche_validation = str(body.get("fiche_validation") or "").strip()
                if fiche_validation not in {"En attente", "Validée"}:
                    raise HTTPException(status_code=400, detail="Statut de fiche invalide")
                with get_db() as conn:
                    conn.execute(
                        "UPDATE interventions SET fiche_validation = %s WHERE id = %s",
                        (fiche_validation, intervention_id),
                    )

            response = {"ok": True, "message": msg}
            save_idempotent_response(operation_id, user.get("sub", ""), endpoint, response)
            return response
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erreur clôture intervention #{intervention_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erreur lors de la clôture: {str(e)}")
    if new_statut and "attente" in new_statut.lower() and "pi" in new_statut.lower():
        # Statut = "En attente de pièce" → notification rupture pour gestionnaires
        # The PWA may send the selected stock parts as pieces_a_deduire when
        # the technician does not explicitly reselect them in the rupture
        # section. Reuse that list so the notification is never empty.
        pieces_attente = body.get("pieces_rupture") or body.get("pieces_a_deduire") or []
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT machine, technicien, notes, probleme FROM interventions WHERE id = %s",
                    (intervention_id,)
                ).fetchone()
            if row:
                machine = row["machine"] or ""
                technicien = row["technicien"] or ""
                # Convert technicien username to full name
                if technicien:
                    technicien = _get_technician_fullname(technicien)
                # Extraire client depuis notes [Client]
                notes = str(row.get("notes") or "")
                client = notes[1:notes.index("]")] if notes.startswith("[") and "]" in notes else ""
                # Si pas de client dans notes, chercher via equipement
                if not client:
                    try:
                        with get_db() as conn2:
                            eq_row = conn2.execute(
                                'SELECT client FROM equipements WHERE nom = %s LIMIT 1',
                                (machine,)
                            ).fetchone()
                            if eq_row:
                                client = dict(eq_row).get('client', '') or ''
                    except Exception:
                        pass
                for piece in pieces_attente:
                    if not isinstance(piece, dict):
                        continue
                    ref = piece.get("reference") or piece.get("ref") or ""
                    if not ref and piece.get("id"):
                        try:
                            with get_db() as conn_piece:
                                piece_row = conn_piece.execute(
                                    "SELECT reference, designation FROM pieces_rechange WHERE id = %s",
                                    (piece.get("id"),),
                                ).fetchone()
                            if piece_row:
                                ref = piece_row.get("reference") or ""
                                piece = {**piece, "designation": piece.get("designation") or piece_row.get("designation")}
                        except Exception:
                            pass
                    nom = piece.get("designation") or piece.get("nom") or ref
                    if not ref:
                        continue
                    ajouter_notification_piece({
                        "type": "piece_rupture",
                        "intervention_id": intervention_id,
                        "piece_reference": ref,
                        "piece_nom": nom,
                        "intervention_ref": f"#{intervention_id}",
                        "equipement": machine,
                        "client": client,
                        "technicien": technicien,
                        "message": f"⚠️ Intervention #{intervention_id} sur {machine} en attente de la pièce "
                                   f"{ref} ({nom}) — rupture de stock",
                        "source": "sav",
                        "destination": "gestionnaire",
                    })
                    logger.info(f"Notif rupture créée: pièce {ref} pour intervention #{intervention_id}")

                # ── Envoi Telegram immédiat ──
                pieces_txt = ""
                if pieces_attente:
                    pieces_list = [f"  • {p.get('reference') or p.get('ref','')} — {p.get('designation') or p.get('nom','')}" for p in pieces_attente]
                    pieces_txt = "\n🔩 Pièces demandées :\n" + "\n".join(pieces_list)
                client_line = f"\n👤 Client : <b>{client}</b>" if client else ""
                msg_tg = (
                    f"⏳ <b>INTERVENTION EN ATTENTE DE PIÈCE — #{intervention_id}</b>\n\n"
                    f"🏥 Machine : <b>{machine}</b>"
                    f"{client_line}\n"
                    f"👷 Technicien : <b>{technicien}</b>"
                    f"{pieces_txt}\n\n"
                    f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )
                send_telegram_reliably("telegram_stock", msg_tg, f"{operation_id}:stock")
                send_telegram_reliably("telegram", msg_tg, f"{operation_id}:tech")
        except Exception as ne:
            logger.error(f"Erreur création notif rupture: {ne}")

        # ── Pièces manuelles (non référencées dans le stock) ──
        pieces_manuelles = body.get("pieces_manuelles") or []
        if pieces_manuelles:
            try:
                for pm in pieces_manuelles:
                    ref = pm.get("reference") or ""
                    designation = pm.get("designation") or ref
                    if not ref:
                        continue
                    # Enregistrer la demande
                    ajouter_piece_demandee({
                        "reference": ref,
                        "designation": designation,
                        "intervention_id": intervention_id,
                        "equipement": machine,
                        "client": client,
                        "technicien": technicien,
                        "probleme": row.get("probleme", "") if row else "",
                    })
                    # Notification gestionnaire
                    ajouter_notification_piece({
                        "type": "piece_rupture",
                        "intervention_id": intervention_id,
                        "piece_reference": ref,
                        "piece_nom": designation,
                        "intervention_ref": f"#{intervention_id}",
                        "equipement": machine,
                        "client": client,
                        "technicien": technicien,
                        "message": f"🆕 Pièce non référencée demandée: {ref} ({designation}) "
                                   f"pour intervention #{intervention_id} sur {machine}",
                        "source": "sav",
                        "destination": "gestionnaire",
                    })
                    logger.info(f"Demande pièce manuelle créée: {ref} pour intervention #{intervention_id}")

                # Telegram pour pièces manuelles
                pm_list = [f"  • {p.get('reference','')} — {p.get('designation','')}" for p in pieces_manuelles if p.get("reference")]
                if pm_list:
                    client_line_m = f"\n👤 Client : <b>{client}</b>" if client else ""
                    msg_tg_m = (
                        f"🆕 <b>DEMANDE PIÈCE NON RÉFÉRENCÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>"
                        f"{client_line_m}\n"
                        f"👷 Technicien : <b>{technicien}</b>\n"
                        f"🔩 Pièces demandées :\n" + "\n".join(pm_list) + "\n\n"
                        f"⚠️ Ces pièces ne sont pas dans le stock — à commander\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    send_telegram_reliably("telegram_stock", msg_tg_m, f"{operation_id}:manual-stock")
                    send_telegram_reliably("telegram", msg_tg_m, f"{operation_id}:manual-tech")
            except Exception as pe:
                logger.error(f"Erreur pièces manuelles: {pe}")

    if new_statut:
        update_intervention_statut(intervention_id, new_statut)
    
    # Update other fields
    fields = []
    params = []
    
    # Map of field names in request body to database column names
    field_mapping = {
        "technicien": "technicien",
        "probleme": "probleme",
        "cause": "cause",
        "solution": "solution",
        "pieces_utilisees": "pieces_utilisees",
        "cout": "cout",
        "duree_minutes": "duree_minutes",
        "description": "description",
        "notes": "notes",
        "type_erreur": "type_erreur",
        "priorite": "priorite",
        "fiche_validation": "fiche_validation",
        "start_time": "start_time",
        "end_time": "end_time",
        "deplacement": "duree_deplacement",  # PWA sends "deplacement", map to "duree_deplacement"
    }
    
    for body_field, db_column in field_mapping.items():
        if user.get("role") == "Technicien" and body_field == "priorite":
            # Priority belongs to the intervention request and is read-only
            # for technicians in the PWA.
            continue
        if body_field in body:
            value = body[body_field]
            fields.append(f"{db_column} = %s")
            params.append(value)
            logger.info(f"  ✓ {db_column} = {value}")
    
    if fields:
        params.append(intervention_id)
        logger.info(f"update_intervention #{intervention_id}: fields={fields}, params={params}")
        try:
            with get_db() as conn:
                conn.execute(f"UPDATE interventions SET {', '.join(fields)} WHERE id = %s", params)
            logger.info(f"✅ update_intervention #{intervention_id}: SUCCESS - Updated {len(fields)} fields")
            
            # If technicien field was updated, also update interventions_techniciens table
            if "technicien" in body:
                new_technicien = body.get("technicien", "").strip()
                logger.info(f"📍 Technicien field updated: {new_technicien}")
                
                if new_technicien and new_technicien != "Non assigné":
                    try:
                        with get_db() as conn:
                            # Handle multiple technicians separated by commas
                            techs = [t.strip() for t in new_technicien.split(",") if t.strip()]
                            
                            for tech_name in techs:
                                # Check if this technician is already in interventions_techniciens
                                existing = conn.execute(
                                    """SELECT id FROM interventions_techniciens 
                                       WHERE intervention_id = %s AND technicien_nom ILIKE %s""",
                                    (intervention_id, f"%{tech_name}%")
                                ).fetchone()
                                
                                if not existing:
                                    # Insert new assignment
                                    conn.execute(
                                        """INSERT INTO interventions_techniciens 
                                           (intervention_id, technicien_nom, statut) 
                                           VALUES (%s, %s, %s)""",
                                        (intervention_id, tech_name, "Assigné")
                                    )
                                    logger.info(f"✅ Added technician '{tech_name}' to interventions_techniciens for #{intervention_id}")
                                else:
                                    logger.info(f"ℹ️ Technician '{tech_name}' already in interventions_techniciens for #{intervention_id}")
                    except Exception as te:
                        logger.warning(f"⚠️ Error updating interventions_techniciens: {te}")
                        # Continue - don't fail the whole request
        except Exception as e:
            logger.error(f"❌ update_intervention #{intervention_id} FAILED: {e}")
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

    if new_statut == "Transfert vers l'atelier" and previous_status != new_statut:
        notify_workshop_transfer(
            intervention_id,
            operation_id,
            {
                "technicien_declarant": user.get("nom") or user.get("sub") or "",
            },
        )

    response = {"ok": True}
    save_idempotent_response(operation_id, user.get("sub", ""), endpoint, response)
    return response


@app.delete("/api/interventions/{intervention_id}")
def delete_intervention(intervention_id: int, user: dict = Depends(_verify_token)):
    with get_db() as conn:
        assert_resource_client_access(conn, "intervention", intervention_id, user)
    """Supprime une intervention (Admin/Manager uniquement)."""
    # Vérifier les permissions
    if user.get("role") not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Seuls les Admin/Manager peuvent supprimer une intervention")
    
    try:
        with get_db() as conn:
            # Vérifier que l'intervention existe et récupérer ses infos
            row = conn.execute(
                "SELECT id, machine, type_intervention, planning_id FROM interventions WHERE id = %s",
                (intervention_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            row_dict = dict(row)
            machine = row_dict.get("machine", "Unknown")
            type_intervention = row_dict.get("type_intervention", "Unknown")
            planning_id = row_dict.get("planning_id")
            normalized_type = str(type_intervention or "").casefold()
            is_preventive = "prévent" in normalized_type or "prevent" in normalized_type

            # Une maintenance préventive est pilotée depuis le planning.
            # La suppression directe laisserait sa ligne active et le worker
            # pourrait recréer une nouvelle intervention avec un nouvel ID.
            if is_preventive:
                raise HTTPException(
                    status_code=409,
                    detail="Cette intervention est préventive. Supprimez-la depuis la page Planning ou en supprimant le contrat associé.",
                )

            # Une corrective peut aussi avoir été créée depuis une demande et
            # être liée au planning. Supprimer ses lignes de planning empêche
            # le worker de la recréer et retire la maintenance de l'affichage.
            if planning_id:
                conn.execute(
                    """DELETE FROM planning_maintenance
                       WHERE id = %s OR original_planning_id = %s""",
                    (planning_id, planning_id),
                )
            
            # Les dossiers créés automatiquement suivent l'intervention.
            # Un dossier créé manuellement depuis la facturation est conservé
            # mais détaché afin de ne pas perdre son historique financier.
            conn.execute(
                """DELETE FROM billing_cases
                   WHERE intervention_id = %s
                     AND created_by IN ('system', 'system-migration')""",
                (intervention_id, ),
            )
            conn.execute(
                """UPDATE billing_cases
                   SET intervention_id = NULL, updated_at = CURRENT_TIMESTAMP
                   WHERE intervention_id = %s""",
                (intervention_id,),
            )

            # Supprimer l'intervention
            conn.execute("DELETE FROM interventions WHERE id = %s", (intervention_id,))
            
            # Log audit
            username = user.get("sub", "unknown")
            import json
            details = json.dumps({
                "intervention_id": intervention_id,
                "machine": machine,
                "type": type_intervention,
            }, ensure_ascii=False)
            log_audit(username, "DELETE_INTERVENTION", details, "interventions")
            
        return {"ok": True, "message": f"Intervention #{intervention_id} supprimée"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression intervention #{intervention_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")


@app.post("/api/interventions/{intervention_id}/fiche")
async def upload_fiche(intervention_id: int, file: UploadFile = File(...), user: dict = Depends(_verify_token)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
    with get_db() as conn:
        assert_intervention_write_access(conn, intervention_id, user)
    return await _store_fiche(file, intervention_id, user.get("sub", "unknown"))


@app.post("/api/interventions/{intervention_id}/photo")
async def upload_photo_alias(intervention_id: int,
                             request: Request,
                             photo: UploadFile = File(None),
                             file: UploadFile = File(None),
                             user: dict = Depends(_verify_token)):
    endpoint = f"/api/interventions/{intervention_id}/photo"
    operation_id = operation_id_from_request(request)
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
    with get_db() as conn:
        assert_intervention_write_access(conn, intervention_id, user)
        cached_response = get_idempotent_response(operation_id, user.get("sub", ""), endpoint)
        if cached_response is not None:
            return cached_response
    """Alias /photo → /fiche pour compatibilité avec l'ancien api_server.py (Streamlit).
    Accepte le champ 'photo' ou 'file'."""
    upload = photo or file
    if not upload:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni")
    result = await _store_fiche(upload, intervention_id, user.get("sub", "unknown"))
    response = {**result, "message": "Photo enregistrée"}
    save_idempotent_response(operation_id, user.get("sub", ""), endpoint, response)
    return response


@app.get("/api/interventions/{intervention_id}/fiche")
def download_fiche(intervention_id: int, user: dict = Depends(_verify_token)):
    """Télécharge une fiche après vérification du JWT Bearer."""
    from fastapi.responses import Response
    with get_db() as conn:
        assert_resource_client_access(conn, "intervention", intervention_id, user)
        try:
            row = conn.execute(
                """SELECT fiche_photo_nom, fiche_photo_data, fiche_storage_key,
                          fiche_content_type
                   FROM interventions WHERE id = %s""",
                (intervention_id,)
            ).fetchone()
        except Exception:
            raise HTTPException(status_code=404, detail="Colonne fiche non trouvée")
    if not row:
        raise HTTPException(status_code=404, detail="Aucune fiche pour cette intervention")
    nom = row["fiche_photo_nom"] or f"fiche_{intervention_id}.jpg"
    if row.get("fiche_storage_key"):
        from s3_storage import download_private_file
        stored = download_private_file(row["fiche_storage_key"])
        if not stored:
            raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
        data, mime = stored
    elif row.get("fiche_photo_data"):
        data = bytes(row["fiche_photo_data"])
        ext = nom.rsplit('.', 1)[-1].lower() if '.' in nom else 'jpg'
        mime_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                    'pdf': 'application/pdf', 'webp': 'image/webp'}
        mime = mime_map.get(ext, 'application/octet-stream')
    else:
        raise HTTPException(status_code=404, detail="Aucune fiche pour cette intervention")
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{nom}"'})



@app.get("/api/interventions/fiches")
def list_fiches(user: dict = Depends(_verify_token)):
    client_scope = _get_client_filter(user)
    """List every intervention with a signed fiche attached.

    A PWA technician can submit a fiche while a multi-technician intervention
    is still awaiting the final aggregate closure, so closure status must not
    hide a file that was successfully stored.
    """
    with get_db() as conn:
        try:
            rows = conn.execute("""
                SELECT id, date, machine, technicien, statut, probleme, solution,
                       duree_minutes,
                       COALESCE(fiche_photo_nom, '') AS fiche_photo_nom,
                       (NULLIF(fiche_storage_key, '') IS NOT NULL OR
                        (fiche_photo_data IS NOT NULL AND octet_length(fiche_photo_data) > 0)) AS has_fiche,
                       COALESCE(fiche_validation, 'En attente') AS fiche_validation
                FROM interventions
                WHERE (NULLIF(fiche_storage_key, '') IS NOT NULL OR
                       (fiche_photo_data IS NOT NULL AND octet_length(fiche_photo_data) > 0))
                  AND (%s = '' OR LOWER(client) = LOWER(%s))
                ORDER BY id DESC
                LIMIT 200
            """, (client_scope or "", client_scope or "")).fetchall()
        except Exception as e:
            logger.error(f"Erreur list_fiches: {e}")
            return []
    result = []
    for r in rows:
        d = dict(r)
        if hasattr(d.get('date'), 'isoformat'):
            d['date'] = d['date'].isoformat()
        d['has_fiche'] = bool(d.get('has_fiche'))
        d['fiche_validation'] = d.get('fiche_validation') or 'En attente'
        result.append(d)
    return result


@app.patch("/api/interventions/{intervention_id}/fiche-validation")
def update_fiche_validation(intervention_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Met à jour le statut de validation client d'une fiche.
    Une fois 'Validée', aucune modification n'est plus possible."""
    if user.get("role") not in {"Admin", "Manager"}:
        raise HTTPException(status_code=403, detail="Seuls les Managers et Admins peuvent valider une fiche")
    nouveau_statut = body.get("validation", "").strip()
    valeurs_autorisees = {"En attente", "Validée"}
    if nouveau_statut not in valeurs_autorisees:
        raise HTTPException(status_code=400, detail=f"Valeur invalide: {nouveau_statut}. Valeurs autorisées: {valeurs_autorisees}")

    with get_db() as conn:
        assert_resource_client_access(conn, "intervention", intervention_id, user)
        # Vérifier le statut actuel
        row = conn.execute(
            "SELECT fiche_validation FROM interventions WHERE id = %s",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention non trouvée")
        statut_actuel = (row["fiche_validation"] or "En attente").strip()
        if statut_actuel == "Validée":
            raise HTTPException(status_code=403, detail="Fiche déjà validée — aucune modification possible")
        conn.execute(
            "UPDATE interventions SET fiche_validation = %s WHERE id = %s",
            (nouveau_statut, intervention_id)
        )
    logger.info(f"Fiche #{intervention_id}: validation mise à jour → '{nouveau_statut}' par {user.get('nom', '?')}")
    return {"ok": True, "validation": nouveau_statut}


@app.delete("/api/interventions/{intervention_id}/fiche")
def delete_fiche(intervention_id: int, user: dict = Depends(_verify_token)):
    """Supprime la photo de fiche d'une intervention (Manager/Admin uniquement).
    Impossible si la fiche est validée."""
    # Vérifier les permissions
    user_role = user.get("role", "").strip()
    if user_role not in {"Admin", "Manager"}:
        raise HTTPException(status_code=403, detail="Seuls les Managers et Admins peuvent supprimer une fiche")
    
    with get_db() as conn:
        assert_resource_client_access(conn, "intervention", intervention_id, user)
        # Vérifier le statut de validation
        row = conn.execute(
            "SELECT fiche_validation, fiche_photo_nom, fiche_storage_key FROM interventions WHERE id = %s",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention non trouvée")
        
        statut_validation = (row["fiche_validation"] or "En attente").strip()
        if statut_validation == "Validée":
            raise HTTPException(status_code=403, detail="Impossible de supprimer une fiche validée")
        
        # Remove the object first. If object storage is temporarily unavailable,
        # keep the database reference instead of creating a broken attachment.
        storage_key = row.get("fiche_storage_key")
        if storage_key:
            from s3_storage import delete_file
            if not delete_file(storage_key):
                raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
        conn.execute(
            """UPDATE interventions SET fiche_photo_nom = '', fiche_photo_data = NULL,
                   fiche_storage_key = NULL, fiche_content_type = NULL,
                   fiche_size_bytes = NULL, fiche_sha256 = NULL,
                   fiche_validation = 'En attente' WHERE id = %s""",
            (intervention_id,)
        )
    
    logger.info(f"Fiche #{intervention_id} supprimée par {user.get('nom', '?')} ({user_role})")
    return {"ok": True, "message": "Fiche supprimée avec succès"}


# ==========================================
# DEMANDES D'INTERVENTION
# ==========================================

__all__ = [
    "get_interventions",
    "get_child_interventions_endpoint",
    "create_intervention",
    "update_intervention",
    "delete_intervention",
    "upload_fiche",
    "upload_photo_alias",
    "download_fiche",
    "list_fiches",
    "update_fiche_validation",
    "delete_fiche",
]
