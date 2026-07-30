"""Equipment, catalogue, and technical-document routes."""

from api.runtime import (
    Body,
    Depends,
    HTTPException,
    Optional,
    Query,
    ajouter_equipement,
    ajouter_fabricant,
    ajouter_type_equipement_custom,
    ajouter_type_intervention_custom,
    app,
    db_lire_clients,
    get_db,
    lire_equipements,
    lire_fabricants,
    lire_types_equipement_custom,
    lire_types_intervention_custom,
    log_audit,
    logger,
    modifier_equipement,
    supprimer_equipement,
)
from api.security import (
    Depends,
    HTTPException,
    Optional,
    _check_create_permission,
    _verify_token,
    assert_resource_client_access,
    get_client_scope,
    resolve_client_scope,
    get_db,
)
from services.scheduled_jobs import (
    _df_to_records,
    get_db,
    lire_equipements,
    logger,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    Optional,
    _get_client_filter,
    _verify_token,
    app,
    db_lire_clients,
    get_db,
    lire_equipements,
    log_audit,
    logger,
)

@app.get("/api/equipements")
def get_equipements(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    df = lire_equipements()
    # Priority: explicit ?client= param, then user's client filter
    client_filter = resolve_client_scope(user, client)
    if client_filter and not df.empty and "Client" in df.columns:
        df = df[df["Client"].astype(str).str.lower() == client_filter.lower()]
    return _df_to_records(df)


@app.post("/api/equipements")
def create_equipement(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    ajouter_equipement(body)
    # Return the ID of the created/upserted equipment
    nom = body.get("Nom", "")
    client = body.get("Client", "Centre Principal")
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM equipements WHERE nom = %s AND client = %s",
            (nom, client)
        ).fetchone()
    equip_id = dict(row)["id"] if row else None
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement": nom, "client": client, "id": equip_id}, ensure_ascii=False)
    log_audit(username, "CREATE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True, "id": equip_id}


@app.put("/api/equipements/{equip_id}")
def update_equipement(equip_id: int, body: dict, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    modifier_equipement(equip_id, body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement_id": equip_id, "changes": body}, ensure_ascii=False)
    log_audit(username, "UPDATE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True}


@app.delete("/api/equipements/{equip_id}")
def delete_equipement(equip_id: int, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    # Get equipment name before deleting for logging
    try:
        with get_db() as conn:
            row = conn.execute("SELECT nom, client FROM equipements WHERE id = %s", (equip_id,)).fetchone()
            equip_name = dict(row)["nom"] if row else "Unknown"
    except:
        equip_name = "Unknown"
    
    supprimer_equipement(equip_id)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement_id": equip_id, "equipement": equip_name}, ensure_ascii=False)
    log_audit(username, "DELETE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True}


@app.post("/api/equipements/sync-region-ville")
def sync_region_ville(user: dict = Depends(_verify_token)):
    """Sync region and ville from clients to equipements based on client name. Admin operation."""
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    try:
        from db_engine import _trigger_backup
        
        df_clients = db_lire_clients()
        df_eq = lire_equipements()
        
        if df_clients.empty or df_eq.empty:
            return {"ok": True, "updated": 0}
        
        logger.info(f"Starting sync: {len(df_clients)} clients, {len(df_eq)} equipements")
        
        # Use SQL UPDATE with JOIN to sync region/ville from clients to equipements (PostgreSQL)
        with get_db() as conn:
            cur = conn.cursor()
            
            # Update equipements where client name matches exactly
            cur.execute("""
                UPDATE equipements e
                SET region = c.region, ville = c.ville
                FROM clients c
                WHERE LOWER(e.client) = LOWER(c.nom)
            """)
            exact_matches = cur.rowcount
            conn.commit()
            
            logger.info(f"Exact matches: {exact_matches}")
            
            # For remaining equipements, try fuzzy matching
            # Get equipements that still have region='Nord' but don't have exact client match
            cur.execute("""
                SELECT e.id, e.client
                FROM equipements e
                LEFT JOIN clients c ON LOWER(e.client) = LOWER(c.nom)
                WHERE c.id IS NULL
            """)
            unmatched_equips = cur.fetchall()
            logger.info(f"Unmatched equipements: {len(unmatched_equips)}")
            
            # Try fuzzy matching for unmatched equipements
            fuzzy_matches = 0
            for equip_id, equip_client in unmatched_equips:
                # Find best match in clients table
                best_match = None
                best_score = 0
                
                for _, client_row in df_clients.iterrows():
                    client_nom = str(client_row.get("nom", "")).lower()
                    equip_client_lower = str(equip_client).lower()
                    
                    # Simple fuzzy match: check if one contains the other
                    if equip_client_lower in client_nom or client_nom in equip_client_lower:
                        best_match = client_row
                        break
                
                if best_match is not None:
                    region = str(best_match.get("region", "")).strip()
                    ville = str(best_match.get("ville", "")).strip()
                    
                    cur.execute(
                        "UPDATE equipements SET region = %s, ville = %s WHERE id = %s",
                        (region, ville, equip_id)
                    )
                    fuzzy_matches += 1
            
            conn.commit()
            logger.info(f"Fuzzy matches: {fuzzy_matches}")
            
            total_updated = exact_matches + fuzzy_matches
        
        logger.info(f"Sync completed: {total_updated} equipements updated")
        _trigger_backup()
        return {"ok": True, "updated": total_updated}
    except Exception as e:
        logger.error(f"Sync region/ville error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fabricants")
def get_fabricants(user: dict = Depends(_verify_token)):
    return lire_fabricants()


@app.post("/api/fabricants")
def post_fabricant(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = payload.get("nom", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_fabricant(nom)
    return {"ok": True}


@app.get("/api/types-equipement-custom")
def get_types_equipement_custom(domaine: str = Query(""), user: dict = Depends(_verify_token)):
    return lire_types_equipement_custom(domaine)


@app.post("/api/types-equipement-custom")
def post_type_equipement_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = payload.get("nom", "").strip()
    domaine = payload.get("domaine", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_type_equipement_custom(nom, domaine)
    return {"ok": True}


@app.get("/api/types-intervention-custom")
def get_types_intervention_custom(user: dict = Depends(_verify_token)):
    return lire_types_intervention_custom()


@app.post("/api/types-intervention-custom")
def post_type_intervention_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = payload.get("nom", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_type_intervention_custom(nom)
    return {"ok": True}


@app.get("/api/domaines-custom")
def get_domaines_custom(user: dict = Depends(_verify_token)):
    from db_engine import lire_domaines_custom
    return lire_domaines_custom()


@app.post("/api/domaines-custom")
def post_domaine_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import ajouter_domaine_custom
    nom = str(payload.get("nom") or "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    try:
        domaine = ajouter_domaine_custom(nom)
        return {"ok": True, "domaine": domaine}
    except Exception as exc:
        logger.error(f"Erreur sauvegarde domaine personnalisé: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Impossible d'enregistrer le domaine")


@app.delete("/api/domaines-custom/{nom}")
def delete_domaine_custom(nom: str, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import supprimer_domaine_custom
    if not nom.strip():
        raise HTTPException(400, "Nom requis")
    supprimer_domaine_custom(nom)
    return {"ok": True}


# ==========================================
# DOCUMENTS TECHNIQUES
# ==========================================

@app.post("/api/documents-techniques/upload")
def upload_document(body: dict, user: dict = Depends(_verify_token)):
    """Upload a technical document (base64 encoded) for an equipment."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import ajouter_document_technique
    equip_id = body.get("equipement_id")
    nom_fichier = body.get("nom_fichier", "")
    contenu_base64 = body.get("contenu_base64", "")
    if not equip_id or not nom_fichier or not contenu_base64:
        raise HTTPException(status_code=400, detail="equipement_id, nom_fichier et contenu_base64 requis")
    with get_db() as conn:
        assert_resource_client_access(conn, "equipement", int(equip_id), user)
    ajouter_document_technique(equip_id, nom_fichier, contenu_base64)
    return {"ok": True}


@app.get("/api/documents-techniques")
def get_all_documents(user: dict = Depends(_verify_token)):
    """List all technical documents with associated equipment info."""
    from db_engine import lire_tous_documents_techniques
    documents = lire_tous_documents_techniques()
    client_scope = get_client_scope(user)
    if client_scope:
        documents = [
            doc for doc in documents
            if str(doc.get("client") or "").strip().casefold() == client_scope.casefold()
        ]
    return documents


@app.get("/api/documents-techniques/{equip_id}")
def get_documents_by_equipment(equip_id: int, user: dict = Depends(_verify_token)):
    """List technical documents for a specific equipment."""
    from db_engine import lire_documents_techniques
    with get_db() as conn:
        assert_resource_client_access(conn, "equipement", equip_id, user)
    return lire_documents_techniques(equip_id)


@app.get("/api/documents-techniques/download/{doc_id}")
def download_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Download a specific technical document (returns base64 content)."""
    from db_engine import lire_document_technique_contenu
    with get_db() as conn:
        assert_resource_client_access(conn, "document_technique", doc_id, user)
    doc = lire_document_technique_contenu(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")
    return doc


@app.delete("/api/documents-techniques/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Delete a technical document."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import supprimer_document_technique
    with get_db() as conn:
        assert_resource_client_access(conn, "document_technique", doc_id, user)
    supprimer_document_technique(doc_id)
    return {"ok": True}


# ==========================================
# INTERVENTIONS / SAV
# ==========================================

__all__ = [
    "get_equipements",
    "create_equipement",
    "update_equipement",
    "delete_equipement",
    "sync_region_ville",
    "get_fabricants",
    "post_fabricant",
    "get_types_equipement_custom",
    "post_type_equipement_custom",
    "get_types_intervention_custom",
    "post_type_intervention_custom",
    "get_domaines_custom",
    "post_domaine_custom",
    "delete_domaine_custom",
    "upload_document",
    "get_all_documents",
    "get_documents_by_equipment",
    "download_document",
    "delete_document",
]
