"""Contract and compliance routes."""

import json

from api.runtime import (
    Depends,
    File,
    HTTPException,
    Optional,
    UploadFile,
    ajouter_conformite,
    ajouter_contrat,
    app,
    generer_planning_from_contrat,
    get_contract_equipements,
    get_db,
    lire_conformite,
    lire_contrats,
    log_audit,
    logger,
    modifier_contrat,
    supprimer_conformite,
    supprimer_contrat,
)
from api.security import (
    _check_create_permission,
    Depends,
    Optional,
    _verify_token,
    assert_resource_client_access,
    resolve_client_scope,
    get_db,
)
from services.scheduled_jobs import (
    _df_to_records,
    _send_telegram_bot,
    get_db,
    lire_contrats,
    logger,
)
from services.file_security import read_validated_upload
from controllers.auth_dashboard import (
    Depends,
    Optional,
    _get_client_filter,
    _verify_token,
    app,
    get_db,
    log_audit,
    logger,
)

@app.get("/api/contrats")
def get_contrats(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    # Pour Lecteur : forcer le filtre par son client
    effective_client = resolve_client_scope(user, client)
    df = lire_contrats(client=effective_client)
    records = _df_to_records(df)
    
    # Enrich each contract with its equipements array
    for record in records:
        contrat_id = record.get("id")
        record["has_fichier"] = bool(record.get("fichier_storage_key"))
        # Never expose private object-storage keys or file hashes to clients.
        record.pop("fichier_storage_key", None)
        record.pop("fichier_sha256", None)
        if contrat_id:
            try:
                equipements = get_contract_equipements(contrat_id)
                record["equipements"] = equipements if equipements else []
            except Exception as e:
                logger.debug(f"Could not get equipements for contract {contrat_id}: {e}")
                record["equipements"] = []
    
    return records


@app.post("/api/contrats")
def create_contrat(body: dict, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    contrat_id = ajouter_contrat(body)
    if not contrat_id:
        raise HTTPException(status_code=500, detail="Le contrat n'a pas pu être sauvegardé")
    
    # Log audit
    username = user.get("sub", "unknown")
    details = json.dumps({
        "client": body.get("client", ""),
        "equipements": body.get("equipements", []),
        "recurrence": body.get("recurrence_maintenance", ""),
        "contrat_id": contrat_id,
    }, ensure_ascii=False)
    log_audit(username, "CREATE_CONTRAT", details, "contrats")
    
    nb_plannings = 0
    if contrat_id:
        try:
            nb_plannings = generer_planning_from_contrat(contrat_id)
            if nb_plannings > 0:
                logger.info(f"✅ Contrat #{contrat_id}: {nb_plannings} maintenance(s) préventive(s) planifiées")
                # Notification Telegram - Send in background (non-blocking)
                def send_telegram_async():
                    try:
                        recurrence = body.get("recurrence_maintenance", "")
                        equipements = body.get("equipements", [])
                        if isinstance(equipements, str):
                            equipements = [equipements] if equipements else []
                        if not equipements:
                            single_eq = body.get("equipement", "")
                            if single_eq:
                                equipements = [single_eq]
                        equipement_str = ", ".join(equipements) if equipements else "— Non spécifié —"
                        client = body.get("client", "")
                        date_fin = body.get("date_fin", "")
                        rappel_avant_jours = body.get("rappel_avant_jours", 14) or 14
                        msg = (
                            f"📋 <b>Nouveau Contrat #{contrat_id}</b>\n\n"
                            f"👤 Client : <b>{client}</b>\n"
                            f"🏥 Équipement(s) : <b>{equipement_str}</b>\n"
                            f"🔄 Récurrence : <b>{recurrence}</b>\n"
                            f"📅 Jusqu'au : {date_fin}\n"
                            f"🔔 Rappel configuré : <b>{rappel_avant_jours} jours</b> avant chaque date\n\n"
                            f"✅ <b>{nb_plannings} maintenance(s) préventive(s)</b> planifiées automatiquement\n"
                            f"⚠️ <i>Techniciens non assignés — vous serez notifié {rappel_avant_jours} jours avant chaque date</i>"
                        )
                        _send_telegram_bot("telegram_sav", msg)
                        _send_telegram_bot("telegram_manager", msg)
                        logger.info(f"📨 Telegram notifications sent for contrat #{contrat_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to send Telegram for contrat #{contrat_id}: {e}")
                
                import threading
                telegram_thread = threading.Thread(target=send_telegram_async, daemon=True)
                telegram_thread.start()
        except Exception as e:
            logger.error(f"Erreur génération planning pour contrat #{contrat_id}: {e}")
    return {"ok": True, "contrat_id": contrat_id, "nb_plannings": nb_plannings}


@app.post("/api/contrats/{contrat_id}/fichier")
async def upload_contrat_file(
    contrat_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(_verify_token),
):
    """Attach a validated image or PDF to a contract."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")

    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        previous = conn.execute(
            """SELECT fichier_contrat, fichier_storage_key, fichier_content_type,
                      fichier_size_bytes, fichier_sha256
               FROM contrats WHERE id = %s""",
            (contrat_id,),
        ).fetchone()
    if not previous:
        raise HTTPException(status_code=404, detail="Contrat non trouvé")

    validated = await read_validated_upload(file, "contrat")
    # A retry after a lost HTTP response must be idempotent. If the exact
    # content is already attached, do not create a second private object.
    if previous.get("fichier_storage_key") and previous.get("fichier_sha256") == validated.sha256:
        return {
            "ok": True,
            "filename": previous.get("fichier_contrat") or validated.display_name,
            "content_type": previous.get("fichier_content_type") or validated.content_type,
            "size_bytes": previous.get("fichier_size_bytes") or len(validated.data),
            "already_attached": True,
        }

    from s3_storage import upload_private_file

    stored = upload_private_file(
        validated.data,
        category="contrats",
        extension=validated.extension,
        content_type=validated.content_type,
        original_name=validated.display_name,
        content_hash=validated.sha256,
        metadata={"contract-id": contrat_id, "uploaded-by": user.get("sub", "unknown")},
    )
    if not stored:
        raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")

    old_key = previous.get("fichier_storage_key") if previous else None
    try:
        with get_db() as conn:
            conn.execute(
                """UPDATE contrats
                   SET fichier_contrat = %s,
                       fichier_storage_key = %s,
                       fichier_content_type = %s,
                       fichier_size_bytes = %s,
                       fichier_sha256 = %s
                   WHERE id = %s""",
                (
                    validated.display_name,
                    stored["s3_key"],
                    validated.content_type,
                    stored["size_bytes"],
                    validated.sha256,
                    contrat_id,
                ),
            )
    except Exception:
        from s3_storage import delete_file
        delete_file(stored["s3_key"])
        raise

    if old_key and old_key != stored["s3_key"]:
        from s3_storage import delete_file
        if not delete_file(old_key):
            logger.warning("Ancienne pièce jointe du contrat #%s non supprimée du stockage", contrat_id)

    return {
        "ok": True,
        "filename": validated.display_name,
        "content_type": validated.content_type,
        "size_bytes": stored["size_bytes"],
    }


@app.get("/api/contrats/{contrat_id}/fichier")
def download_contrat_file(contrat_id: int, user: dict = Depends(_verify_token)):
    """Download a contract attachment after client-scope authorization."""
    from fastapi.responses import Response

    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        row = conn.execute(
            """SELECT fichier_contrat, fichier_storage_key, fichier_content_type
               FROM contrats WHERE id = %s""",
            (contrat_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contrat non trouvé")
    if not row.get("fichier_storage_key"):
        raise HTTPException(status_code=404, detail="Aucune pièce jointe pour ce contrat")

    from s3_storage import download_private_file
    stored = download_private_file(row["fichier_storage_key"])
    if not stored:
        raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
    content, detected_content_type = stored
    filename = row.get("fichier_contrat") or f"contrat_{contrat_id}"
    content_type = row.get("fichier_content_type") or detected_content_type
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.delete("/api/contrats/{contrat_id}/fichier")
def delete_contrat_file(contrat_id: int, user: dict = Depends(_verify_token)):
    """Delete a private contract attachment after RBAC and client-scope checks."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")

    with get_db() as conn:
        # This check must happen before reading or deleting the private object.
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        row = conn.execute(
            """SELECT fichier_storage_key FROM contrats WHERE id = %s""",
            (contrat_id,),
        ).fetchone()

    storage_key = row.get("fichier_storage_key") if row else None
    if not storage_key:
        raise HTTPException(status_code=404, detail="Aucune pièce jointe pour ce contrat")

    from s3_storage import delete_file
    if not delete_file(storage_key):
        raise HTTPException(status_code=503, detail="La suppression du fichier privé a échoué. Réessayez.")

    try:
        with get_db() as conn:
            conn.execute(
                """UPDATE contrats
                   SET fichier_contrat = NULL,
                       fichier_storage_key = NULL,
                       fichier_content_type = NULL,
                       fichier_size_bytes = NULL,
                       fichier_sha256 = NULL
                   WHERE id = %s""",
                (contrat_id,),
            )
    except Exception:
        # The object has already been removed. Keep the failure explicit so an
        # operator can reconcile the metadata instead of reporting success.
        logger.exception("Pièce jointe du contrat #%s supprimée mais métadonnées non mises à jour", contrat_id)
        raise HTTPException(status_code=503, detail="Le fichier a été supprimé mais la mise à jour du contrat a échoué")

    log_audit(
        user.get("sub", "unknown"),
        "DELETE_CONTRAT_FILE",
        json.dumps({"contrat_id": contrat_id}, ensure_ascii=False),
        "contrats",
    )
    return {"ok": True, "contrat_id": contrat_id}


@app.put("/api/contrats/{contrat_id}")
def update_contrat(contrat_id: int, body: dict, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
    modifier_contrat(contrat_id, body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "contrat_id": contrat_id,
        "changes": body,
    }, ensure_ascii=False)
    log_audit(username, "UPDATE_CONTRAT", details, "contrats")
    
    return {"ok": True}


@app.delete("/api/contrats/{contrat_id}")
def delete_contrat(contrat_id: int, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
    # Get contrat info before deleting
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT client FROM contrats WHERE id = %s",
                (contrat_id,)
            ).fetchone()
            client = dict(row)["client"] if row else "Unknown"
    except:
        client = "Unknown"
    
    supprimer_contrat(contrat_id)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "contrat_id": contrat_id,
        "client": client,
    }, ensure_ascii=False)
    log_audit(username, "DELETE_CONTRAT", details, "contrats")
    
    return {"ok": True}


# ==========================================
# CONFORMITÉ
# ==========================================

@app.get("/api/conformite")
def get_conformite(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    return _df_to_records(lire_conformite(client=resolve_client_scope(user, client)))


@app.post("/api/conformite")
def create_conformite(body: dict, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    ajouter_conformite(body)
    return {"ok": True}


@app.delete("/api/conformite/{conformite_id}")
def delete_conformite(conformite_id: int, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    with get_db() as conn:
        assert_resource_client_access(conn, "conformite", conformite_id, user)
    supprimer_conformite(conformite_id)
    return {"ok": True}


# ==========================================
# PLANNING
# ==========================================

__all__ = [
    "get_contrats",
    "create_contrat",
    "upload_contrat_file",
    "download_contrat_file",
    "delete_contrat_file",
    "update_contrat",
    "delete_contrat",
    "get_conformite",
    "create_conformite",
    "delete_conformite",
]
