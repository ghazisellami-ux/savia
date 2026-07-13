"""Contract and compliance routes."""

from api.runtime import (
    Depends,
    Optional,
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
    Depends,
    Optional,
    _verify_token,
    get_db,
)
from services.scheduled_jobs import (
    _df_to_records,
    _send_telegram_bot,
    get_db,
    lire_contrats,
    logger,
)
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
    effective_client = _get_client_filter(user) or client
    df = lire_contrats(client=effective_client)
    records = _df_to_records(df)
    
    # Enrich each contract with its equipements array
    for record in records:
        contrat_id = record.get("id")
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
    contrat_id = ajouter_contrat(body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
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


@app.put("/api/contrats/{contrat_id}")
def update_contrat(contrat_id: int, body: dict, user: dict = Depends(_verify_token)):
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
    # Get contrat info before deleting
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT client FROM contrats WHERE id = ?",
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

__all__ = [
    "get_contrats",
    "create_contrat",
    "update_contrat",
    "delete_contrat",
    "get_conformite",
    "create_conformite",
    "delete_conformite",
]

