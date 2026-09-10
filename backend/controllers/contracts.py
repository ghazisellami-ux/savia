"""Contract and compliance routes."""

import json
from urllib.parse import quote

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
    replanifier_contrat,
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
from repositories.contracts import contract_planning_settings_changed
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

MAX_CONTRACT_ATTACHMENTS = 10


def _contract_attachment_records(conn, contrat_id: int) -> list[dict]:
    """Return public metadata only; never expose the private storage key."""
    rows = conn.execute(
        """SELECT id, filename, content_type, size_bytes, created_at
           FROM contrat_fichiers
           WHERE contrat_id = %s
           ORDER BY created_at, id""",
        (contrat_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _attachment_response(content: bytes, content_type: str, filename: str):
    from fastapi.responses import Response

    # RFC 5987 preserves accented filenames while keeping the header ASCII.
    encoded_name = quote(filename, safe="")
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}"},
    )


async def _store_contrat_attachment(contrat_id: int, file: UploadFile, user: dict) -> dict:
    """Validate, store and register one attachment without replacing others."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")

    validated = await read_validated_upload(file, "contrat")
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        duplicate = conn.execute(
            """SELECT id, filename, content_type, size_bytes
               FROM contrat_fichiers WHERE contrat_id = %s AND sha256 = %s""",
            (contrat_id, validated.sha256),
        ).fetchone()
        if duplicate:
            return {"ok": True, **dict(duplicate), "already_attached": True}
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM contrat_fichiers WHERE contrat_id = %s",
            (contrat_id,),
        ).fetchone()["count"]
        if count >= MAX_CONTRACT_ATTACHMENTS:
            raise HTTPException(
                status_code=400,
                detail=f"Un contrat ne peut pas contenir plus de {MAX_CONTRACT_ATTACHMENTS} pièces jointes",
            )

    from s3_storage import delete_file, upload_private_file

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

    try:
        with get_db() as conn:
            row = conn.execute(
                """INSERT INTO contrat_fichiers
                       (contrat_id, filename, storage_key, content_type, size_bytes, sha256, uploaded_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, filename, content_type, size_bytes""",
                (
                    contrat_id,
                    validated.display_name,
                    stored["s3_key"],
                    validated.content_type,
                    stored["size_bytes"],
                    validated.sha256,
                    user.get("sub", "unknown"),
                ),
            ).fetchone()
            # Keep the historical columns as a pointer to the first attachment
            # for clients that still use the old singular endpoint.
            conn.execute(
                """UPDATE contrats
                   SET fichier_contrat = CASE WHEN fichier_storage_key IS NULL THEN %s ELSE fichier_contrat END,
                       fichier_storage_key = CASE WHEN fichier_storage_key IS NULL THEN %s ELSE fichier_storage_key END,
                       fichier_content_type = CASE WHEN fichier_storage_key IS NULL THEN %s ELSE fichier_content_type END,
                       fichier_size_bytes = CASE WHEN fichier_storage_key IS NULL THEN %s ELSE fichier_size_bytes END,
                       fichier_sha256 = CASE WHEN fichier_storage_key IS NULL THEN %s ELSE fichier_sha256 END
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
        return {"ok": True, **dict(row), "already_attached": False}
    except Exception:
        delete_file(stored["s3_key"])
        raise


@app.get("/api/contrats")
def get_contrats(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    # Pour Lecteur : forcer le filtre par son client
    effective_client = resolve_client_scope(user, client)
    df = lire_contrats(client=effective_client)
    records = _df_to_records(df)
    
    # Enrich each contract with its equipements array
    for record in records:
        contrat_id = record.get("id")
        record["fichiers"] = []
        if contrat_id:
            with get_db() as conn:
                record["fichiers"] = _contract_attachment_records(conn, contrat_id)
        record["has_fichier"] = bool(record["fichiers"])
        # Never expose private object-storage keys or file hashes to clients.
        record.pop("fichier_storage_key", None)
        record.pop("fichier_sha256", None)
        if contrat_id:
            try:
                equipements = get_contract_equipements(contrat_id)
                record["equipements"] = equipements if equipements else []
                record["equipement_ids"] = [equipment["id"] for equipment in equipements]
            except Exception as e:
                logger.debug(f"Could not get equipements for contract {contrat_id}: {e}")
                record["equipements"] = []
                record["equipement_ids"] = []
    
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
    """Legacy singular endpoint; it now adds a file instead of replacing one."""
    return await _store_contrat_attachment(contrat_id, file, user)


@app.post("/api/contrats/{contrat_id}/fichiers")
async def upload_contrat_attachment(
    contrat_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(_verify_token),
):
    """Add one validated image or PDF to a contract."""
    return await _store_contrat_attachment(contrat_id, file, user)


@app.get("/api/contrats/{contrat_id}/fichiers")
def list_contrat_attachments(contrat_id: int, user: dict = Depends(_verify_token)):
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        return _contract_attachment_records(conn, contrat_id)


@app.get("/api/contrats/{contrat_id}/fichiers/{fichier_id}")
def download_contrat_attachment(contrat_id: int, fichier_id: int, user: dict = Depends(_verify_token)):
    """Download one private contract attachment after authorization."""
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        row = conn.execute(
            """SELECT filename, storage_key, content_type
               FROM contrat_fichiers WHERE id = %s AND contrat_id = %s""",
            (fichier_id, contrat_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pièce jointe introuvable")

    from s3_storage import download_private_file
    stored = download_private_file(row["storage_key"])
    if not stored:
        raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
    content, detected_content_type = stored
    return _attachment_response(
        content,
        row.get("content_type") or detected_content_type,
        row.get("filename") or f"contrat_{contrat_id}",
    )


@app.get("/api/contrats/{contrat_id}/fichier")
def download_contrat_file(contrat_id: int, user: dict = Depends(_verify_token)):
    """Legacy singular download endpoint, serving the first attachment."""
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        row = conn.execute(
            "SELECT id FROM contrat_fichiers WHERE contrat_id = %s ORDER BY created_at, id LIMIT 1",
            (contrat_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Aucune pièce jointe pour ce contrat")
    return download_contrat_attachment(contrat_id, row["id"], user)


@app.delete("/api/contrats/{contrat_id}/fichiers/{fichier_id}")
def delete_contrat_attachment(contrat_id: int, fichier_id: int, user: dict = Depends(_verify_token)):
    """Delete exactly one attachment while leaving the other files intact."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")

    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        row = conn.execute(
            "SELECT storage_key FROM contrat_fichiers WHERE id = %s AND contrat_id = %s",
            (fichier_id, contrat_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pièce jointe introuvable")

    from s3_storage import delete_file
    if not delete_file(row["storage_key"]):
        raise HTTPException(status_code=503, detail="La suppression du fichier privé a échoué. Réessayez.")

    with get_db() as conn:
        conn.execute("DELETE FROM contrat_fichiers WHERE id = %s AND contrat_id = %s", (fichier_id, contrat_id))
        next_file = conn.execute(
            """SELECT filename, storage_key, content_type, size_bytes, sha256
               FROM contrat_fichiers WHERE contrat_id = %s ORDER BY created_at, id LIMIT 1""",
            (contrat_id,),
        ).fetchone()
        conn.execute(
            """UPDATE contrats
               SET fichier_contrat = %s, fichier_storage_key = %s,
                   fichier_content_type = %s, fichier_size_bytes = %s, fichier_sha256 = %s
               WHERE id = %s""",
            (
                next_file.get("filename") if next_file else None,
                next_file.get("storage_key") if next_file else None,
                next_file.get("content_type") if next_file else None,
                next_file.get("size_bytes") if next_file else None,
                next_file.get("sha256") if next_file else None,
                contrat_id,
            ),
        )

    log_audit(
        user.get("sub", "unknown"),
        "DELETE_CONTRAT_FILE",
        json.dumps({"contrat_id": contrat_id, "fichier_id": fichier_id}, ensure_ascii=False),
        "contrats",
    )
    return {"ok": True, "contrat_id": contrat_id, "fichier_id": fichier_id}


@app.delete("/api/contrats/{contrat_id}/fichier")
def delete_contrat_file(contrat_id: int, user: dict = Depends(_verify_token)):
    """Legacy singular deletion endpoint, deleting the first attachment."""
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        row = conn.execute(
            "SELECT id FROM contrat_fichiers WHERE contrat_id = %s ORDER BY created_at, id LIMIT 1",
            (contrat_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Aucune pièce jointe pour ce contrat")
    return delete_contrat_attachment(contrat_id, row["id"], user)


@app.put("/api/contrats/{contrat_id}")
def update_contrat(contrat_id: int, body: dict, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    with get_db() as conn:
        assert_resource_client_access(conn, "contrat", contrat_id, user)
        contract_row = conn.execute("SELECT * FROM contrats WHERE id = %s", (contrat_id,)).fetchone()
        equipment_rows = conn.execute(
            """SELECT e.nom
               FROM contrats_equipements ce
               JOIN equipements e ON e.id = ce.equipement_id
               WHERE ce.contrat_id = %s""",
            (contrat_id,),
        ).fetchall()

    existing_contract = dict(contract_row) if contract_row else None
    existing_equipments = [row["nom"] for row in equipment_rows]
    if existing_contract and not existing_equipments:
        existing_equipments = [existing_contract.get("equipement", "")]
    planning_changed = bool(body.get("force_replan")) or (
        bool(existing_contract) and contract_planning_settings_changed(
            existing_contract,
            existing_equipments,
            body,
        )
    )
    modifier_contrat(contrat_id, body)
    # Rebuild only when the calendar itself changed.  Closed visits are
    # deliberately preserved by replanifier_contrat.
    planning_result = None
    if planning_changed:
        planning_result = replanifier_contrat(contrat_id)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "contrat_id": contrat_id,
        "changes": body,
    }, ensure_ascii=False)
    log_audit(username, "UPDATE_CONTRAT", details, "contrats")
    
    return {"ok": True, "planning": planning_result}


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
            attachment_rows = conn.execute(
                "SELECT storage_key FROM contrat_fichiers WHERE contrat_id = %s",
                (contrat_id,),
            ).fetchall()
    except:
        client = "Unknown"
        attachment_rows = []

    # Delete private objects before removing their database references. A retry
    # is safe if a transient database error follows an object deletion.
    if attachment_rows:
        from s3_storage import delete_file
        failed_deletions = [
            row["storage_key"] for row in attachment_rows if not delete_file(row["storage_key"])
        ]
        if failed_deletions:
            raise HTTPException(status_code=503, detail="Impossible de supprimer toutes les pièces jointes du contrat")
    
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
    "upload_contrat_attachment",
    "list_contrat_attachments",
    "download_contrat_file",
    "download_contrat_attachment",
    "delete_contrat_file",
    "delete_contrat_attachment",
    "update_contrat",
    "delete_contrat",
    "get_conformite",
    "create_conformite",
    "delete_conformite",
]
