"""Client management and dashboard-dimension routes."""

from api.runtime import (
    Depends,
    File,
    HTTPException,
    Optional,
    UploadFile,
    ajouter_client,
    app,
    ClientHasEquipmentsError,
    db_lire_clients,
    detect_and_fix_encoding,
    get_db,
    lire_equipements,
    lire_interventions,
    lire_types_client_custom,
    lire_villes_custom,
    lire_pays_custom,
    log_audit,
    logger,
    modifier_client,
    ajouter_type_client_custom,
    ajouter_ville_custom, modifier_ville_custom,
    ajouter_pays_custom,
    supprimer_ville_custom,
    supprimer_pays_custom,
    pd,
    read_sql,
    supprimer_client,
)
from api.security import (
    Depends,
    HTTPException,
    Optional,
    _check_create_permission,
    _verify_token,
    get_client_scope,
    resolve_client_scope,
    get_db,
)
from services.file_security import read_validated_upload
from services.scheduled_jobs import (
    get_db,
    lire_equipements,
    lire_interventions,
    logger,
    pd,
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
    lire_interventions,
    log_audit,
    logger,
    pd,
    read_sql,
)

@app.get("/api/clients")
def get_clients(user: dict = Depends(_verify_token)):
    """List clients from the dedicated clients table, enriched with equipment stats using SQL aggregates."""
    try:
        with get_db() as conn:
            scoped_client = get_client_scope(user)
            # Get all clients from clients table
            df_clients = read_sql("SELECT * FROM clients ORDER BY nom", conn)
            
            if df_clients.empty:
                return []
            
            # Get equipment stats by client (using exact string match, case-insensitive)
            eq_stats_query = """
            SELECT 
                client,
                COUNT(*) as nb_eq,
                SUM(CASE WHEN statut IN ('Hors Service', 'Critique') THEN 1 ELSE 0 END) as nb_hs
            FROM equipements
            WHERE client IS NOT NULL AND client != ''
            GROUP BY client
            """
            df_eq_stats = read_sql(eq_stats_query, conn)
            
            # Get intervention stats by client
            int_stats_query = """
            SELECT 
                e.client,
                COUNT(DISTINCT i.id) as nb_int
            FROM interventions i
            JOIN equipements e ON e.nom = i.machine
            WHERE e.client IS NOT NULL AND e.client != ''
            GROUP BY e.client
            """
            df_int_stats = read_sql(int_stats_query, conn)
            
            # Build result with enriched data
            result = []

            def json_value(value):
                """Convert pandas NULL/NaN values to JSON-safe Python values."""
                if value is None:
                    return None
                try:
                    if pd.isna(value):
                        return None
                except (TypeError, ValueError):
                    pass
                return value

            for _, row in df_clients.iterrows():
                client_name = json_value(row.get("nom", "")) or ""
                if scoped_client and str(client_name).strip().casefold() != scoped_client.casefold():
                    continue
                
                # Find stats for this client (case-insensitive match)
                eq_stat = None
                if not df_eq_stats.empty:
                    eq_stat = df_eq_stats[df_eq_stats["client"].str.lower() == client_name.lower()].iloc[0] if len(df_eq_stats[df_eq_stats["client"].str.lower() == client_name.lower()]) > 0 else None
                
                int_stat = None
                if not df_int_stats.empty:
                    int_stat = df_int_stats[df_int_stats["client"].str.lower() == client_name.lower()].iloc[0] if len(df_int_stats[df_int_stats["client"].str.lower() == client_name.lower()]) > 0 else None
                
                # Calculate health score
                nb_eq = int(eq_stat.get("nb_eq", 0)) if eq_stat is not None else 0
                nb_hs = int(eq_stat.get("nb_hs", 0)) if eq_stat is not None else 0
                score_sante = max(0, round(((nb_eq - nb_hs) / nb_eq * 100))) if nb_eq > 0 else 100
                
                nb_int = int(int_stat.get("nb_int", 0)) if int_stat is not None else 0
                
                result.append({
                    "id": json_value(row.get("id")),
                    "nom": client_name,
                    "code_client": json_value(row.get("code_client", "")) or "",
                    "matricule_fiscale": json_value(row.get("matricule_fiscale", "")) or "",
                    "country_code": json_value(row.get("country_code", "TN")) or "TN",
                    "ville": json_value(row.get("ville", "")) or "",
                    "region": json_value(row.get("region", "")) or "",
                    "contact": json_value(row.get("contact", "")) or "",
                    "telephone": json_value(row.get("telephone", "")) or "",
                    "adresse": json_value(row.get("adresse", "")) or "",
                    "latitude": json_value(row.get("latitude")),
                    "longitude": json_value(row.get("longitude")),
                    "type_client": json_value(row.get("type_client", "")) or "",
                    "international": bool(json_value(row.get("international", False)) or False),
                    "nb_equipements": nb_eq,
                    "nb_interventions": nb_int,
                    "score_sante": score_sante,
                })
            
            return result
    except Exception as e:
        logger.error(f"Erreur get_clients: {e}")
        return []


@app.get("/api/dashboard/equipment-types")
def get_dashboard_equipment_types(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Get equipment types filtered by client, region, and ville."""
    try:
        df_eq = lire_equipements()
        df_clients = db_lire_clients()
        equipment_types = set()
        
        # Pour Lecteur : forcer le filtre par son client
        effective_client = resolve_client_scope(user, client)

        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]

        # Filter equipements by region (join with clients table to get region)
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                # Get international clients
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                # Get clients in this region
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]

        # Filter equipements by ville (join with clients table to get ville)
        if ville and not df_eq.empty and not df_clients.empty:
            # Get clients in this ville
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]

        # Extract equipment types from filtered equipements
        if not df_eq.empty and "Type" in df_eq.columns:
            equipment_types.update(
                df_eq["Type"]
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )
        
        # Return sorted list
        return sorted([t for t in equipment_types if t])
    except Exception as e:
        logger.error(f"Failed to get equipment types: {e}")
        return []


@app.get("/api/dashboard/regions")
def get_dashboard_regions(user: dict = Depends(_verify_token)):
    """Get all existing regions from clients table - ONLY the 4 main regions."""
    try:
        df_clients = db_lire_clients()
        scoped_client = get_client_scope(user)
        if scoped_client and not df_clients.empty and "nom" in df_clients.columns:
            df_clients = df_clients[df_clients["nom"].astype(str).str.casefold() == scoped_client.casefold()]
        regions = set()
        
        # List of valid regions
        VALID_REGIONS = {"sud", "centre", "nord"}
        
        if not df_clients.empty:
            # Add regular regions - ONLY if they match the 4 valid regions
            if "region" in df_clients.columns:
                client_regions = df_clients["region"].dropna().astype(str).str.strip().str.lower().unique().tolist()
                for r in client_regions:
                    if r in VALID_REGIONS:
                        regions.add(r.capitalize())  # Capitalize: sud → Sud
            
            # Add International if any client has international=True
            if "international" in df_clients.columns:
                if (df_clients["international"].astype(bool)).any():
                    regions.add("International")
        
        # Return sorted list - ONLY the 4 main regions
        return sorted(list(regions))
    except Exception as e:
        logger.error(f"Failed to get regions: {e}")
        return []


@app.get("/api/dashboard/villes")
def get_dashboard_villes(region: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Get all existing villes, optionally filtered by region."""
    try:
        df_clients = db_lire_clients()
        scoped_client = get_client_scope(user)
        if scoped_client and not df_clients.empty and "nom" in df_clients.columns:
            df_clients = df_clients[df_clients["nom"].astype(str).str.casefold() == scoped_client.casefold()]
        villes = set()
        
        if not df_clients.empty and region:
            # IMPORTANT: Only return villes when a region is specified
            # Filter by region
            if region.lower() == "international":
                # Get villes from international clients
                if "international" in df_clients.columns and "ville" in df_clients.columns:
                    international_clients = df_clients[
                        df_clients["international"].astype(bool) == True
                    ]
                    villes.update(
                        international_clients["ville"]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .unique()
                        .tolist()
                    )
            else:
                # Get villes from clients in this region
                if "region" in df_clients.columns and "ville" in df_clients.columns:
                    region_clients = df_clients[
                        df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip()
                    ]
                    villes.update(
                        region_clients["ville"]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .unique()
                        .tolist()
                    )
        
        # Return sorted list - ONLY villes, no regions
        return sorted([v for v in villes if v and v.lower() not in ["sud", "centre", "nord", "international"]])
    except Exception as e:
        logger.error(f"Failed to get villes: {e}")
        return []


@app.get("/api/dashboard/availability-trend")
def get_availability_trend(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    equipment_type: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Calculate real availability trend for the last 6 months based on interventions."""
    try:
        from datetime import datetime, timedelta
        import calendar
        
        df_eq = lire_equipements()
        df_int = lire_interventions()
        df_clients = db_lire_clients()
        
        # Apply same filters as KPI endpoint
        effective_client = resolve_client_scope(user, client)
        
        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]
        
        # Filter equipements by region
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]
        
        # Filter equipements by ville
        if ville and not df_eq.empty and not df_clients.empty:
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]
        
        # Filter equipements by equipment type
        if equipment_type and not df_eq.empty and "Type" in df_eq.columns:
            df_eq = df_eq[df_eq["Type"].notna() & (df_eq["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]
        
        nb_eq = len(df_eq) if not df_eq.empty else 0
        
        # If no equipment, return default data
        if nb_eq == 0:
            today = datetime.now()
            trend_data = []
            for i in range(5, -1, -1):
                month_date = today - timedelta(days=30*i)
                month_name = calendar.month_name[month_date.month][:3]
                trend_data.append({"mois": month_name, "dispo": 0})
            return {"ok": True, "trend": trend_data}
        
        # Get all machines for filtered equipements
        machines = df_eq["Nom"].tolist() if "Nom" in df_eq.columns else []
        
        # Filter interventions by machines
        if machines and not df_int.empty and "machine" in df_int.columns:
            df_int = df_int[df_int["machine"].isin(machines)]
        
        # Parse dates
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
        
        # Calculate availability for each month
        today = datetime.now()
        trend_data = []
        
        for i in range(5, -1, -1):
            month_date = today - timedelta(days=30*i)
            month_name = calendar.month_name[month_date.month][:3]
            month_start = month_date.replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            # Count interventions in this month
            if not df_int.empty:
                month_int = df_int[(df_int["date"] >= month_start) & (df_int["date"] <= month_end)]
                nb_interventions = len(month_int)
            else:
                nb_interventions = 0
            
            # Calculate availability: assume 100% if no issues, decrease by 2% per intervention as rough estimate
            # More sophisticated: count "Terminée" status as available, others as not available
            availability = 100.0
            if not df_int.empty and nb_interventions > 0:
                # Count interventions that are NOT "Terminée" (corrective or in-progress)
                if "statut" in df_int.columns:
                    unfinished = len(month_int[month_int["statut"].astype(str).str.lower() != "terminée"])
                    # Rough estimate: each unfinished intervention reduces availability by 2%
                    availability = max(0, 100.0 - (unfinished * 2.0))
                else:
                    availability = max(0, 100.0 - (nb_interventions * 2.0))
            
            trend_data.append({"mois": month_name, "dispo": round(availability, 1)})
        
        return {"ok": True, "trend": trend_data}
    except Exception as e:
        import traceback
        logger.error(f"Erreur get_availability_trend: {e}\n{traceback.format_exc()}")
        # Return default trend data on error
        today = datetime.now()
        trend_data = []
        for i in range(5, -1, -1):
            month_date = today - timedelta(days=30*i)
            month_name = calendar.month_name[month_date.month][:3]
            trend_data.append({"mois": month_name, "dispo": 0})
        return {"ok": True, "trend": trend_data}


@app.get("/api/dashboard/clients-by-region")
def get_clients_by_region(region: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Get all clients, optionally filtered by region."""
    try:
        df_clients = db_lire_clients()
        scoped_client = get_client_scope(user)
        if scoped_client and not df_clients.empty and "nom" in df_clients.columns:
            df_clients = df_clients[df_clients["nom"].astype(str).str.casefold() == scoped_client.casefold()]
        clients = set()
        
        if not df_clients.empty and "nom" in df_clients.columns:
            if region:
                # Filter by region
                if region.lower() == "international":
                    # Get international clients
                    if "international" in df_clients.columns:
                        international_clients = df_clients[
                            df_clients["international"].astype(bool) == True
                        ]
                        clients.update(
                            international_clients["nom"]
                            .dropna()
                            .astype(str)
                            .str.strip()
                            .unique()
                            .tolist()
                        )
                else:
                    # Get clients in this region
                    if "region" in df_clients.columns:
                        region_clients = df_clients[
                            df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip()
                        ]
                        clients.update(
                            region_clients["nom"]
                            .dropna()
                            .astype(str)
                            .str.strip()
                            .unique()
                            .tolist()
                        )
            else:
                # Get all clients
                clients.update(
                    df_clients["nom"]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .unique()
                    .tolist()
                )
        
        # Return sorted list
        return sorted([c for c in clients if c])
    except Exception as e:
        logger.error(f"Failed to get clients by region: {e}")
        return []


@app.post("/api/clients")
def create_client(body: dict, user: dict = Depends(_verify_token)):
    """Create a new client."""
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    ajouter_client(body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"client": body.get("nom", "")}, ensure_ascii=False)
    log_audit(username, "CREATE_CLIENT", details, "clients")
    
    return {"ok": True}


@app.get("/api/types-client-custom")
def get_types_client_custom(user: dict = Depends(_verify_token)):
    """Liste les types de clients ajoutés manuellement."""
    return lire_types_client_custom()


@app.post("/api/types-client-custom")
def create_type_client_custom(body: dict, user: dict = Depends(_verify_token)):
    """Ajoute un type de client réutilisable."""
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins",
        )
    nom = str(body.get("nom", "")).strip()
    if not nom:
        raise HTTPException(status_code=400, detail="Nom requis")
    ajouter_type_client_custom(nom)
    return {"ok": True}


@app.get("/api/villes-custom")
def get_villes_custom(country: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Liste les villes personnalisées, filtrées par pays si demandé."""
    return lire_villes_custom(country)


@app.post("/api/villes-custom")
def create_ville_custom(body: dict, user: dict = Depends(_verify_token)):
    """Ajoute une ville réutilisable pour le pays sélectionné."""
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins",
        )
    country = str(body.get("country_code", "")).strip().upper()
    nom = str(body.get("nom", "")).strip()
    if not country or not nom:
        raise HTTPException(status_code=400, detail="Pays et ville requis")
    try:
        latitude = float(body["latitude"]) if body.get("latitude") is not None else None
        longitude = float(body["longitude"]) if body.get("longitude") is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Coordonnées GPS invalides")
    city = ajouter_ville_custom(country, nom, latitude, longitude)
    return {"ok": True, "city": city}


@app.delete("/api/villes-custom/{country_code}/{nom}")
def delete_ville_custom(country_code: str, nom: str, user: dict = Depends(_verify_token)):
    """Ancienne route de suppression, conservée mais réservée aux Admins et Managers."""
    if str(user.get("role", "")).strip() not in {"Admin", "Manager"}:
        raise HTTPException(
            status_code=403,
            detail="La suppression des villes est réservée aux Admins et Managers",
        )
    supprimer_ville_custom(country_code, nom)
    return {"ok": True}


@app.put("/api/villes-custom/{country_code}/{nom}")
def update_ville_custom(country_code: str, nom: str, body: dict, user: dict = Depends(_verify_token)):
    """Modifie le nom d'une ville enregistrée; réservé aux Admins et Managers."""
    if str(user.get("role", "")).strip() not in {"Admin", "Manager"}:
        raise HTTPException(status_code=403, detail="La modification des villes est réservée aux Admins et Managers")
    nouveau_nom = str(body.get("nom", "")).strip()
    if not nouveau_nom:
        raise HTTPException(status_code=400, detail="Nouveau nom de ville requis")
    try:
        city = modifier_ville_custom(country_code, nom, nouveau_nom)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "city": city}


@app.get("/api/pays-custom")
def get_pays_custom(user: dict = Depends(_verify_token)):
    """Liste les pays ajoutés manuellement."""
    return lire_pays_custom()


@app.post("/api/pays-custom")
def create_pays_custom(body: dict, user: dict = Depends(_verify_token)):
    """Ajoute un pays réutilisable dans les paramètres et la carte."""
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins",
        )
    nom = str(body.get("nom", "")).strip()
    if not nom:
        raise HTTPException(status_code=400, detail="Nom du pays requis")
    try:
        country = ajouter_pays_custom(nom, body.get("flag", "🌍"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "country": country}


@app.delete("/api/pays-custom/{code}")
def delete_pays_custom(code: str, user: dict = Depends(_verify_token)):
    """Supprime un pays personnalisé."""
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins",
        )
    supprimer_pays_custom(code)
    return {"ok": True}


@app.post("/api/clients/import-excel")
async def import_clients_excel(file: UploadFile = File(...), user: dict = Depends(_verify_token)):
    """Import clients from an Excel or CSV file with auto-detection of columns."""
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    import io
    try:
        validated_upload = await read_validated_upload(file, "clients_import")
        content = validated_upload.data
        
        # Determine file type
        filename = validated_upload.display_name.lower()
        is_csv = filename.endswith('.csv')
        
        # Read file with universal encoding detection
        try:
            if is_csv:
                # Utiliser la fonction globale detect_and_fix_encoding
                text_content = detect_and_fix_encoding(content)
                df = pd.read_csv(io.StringIO(text_content))
            else:
                # Pour Excel
                try:
                    df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
                except Exception:
                    df = pd.read_excel(io.BytesIO(content))
        except Exception as e:
            logger.error(f"Erreur lecture fichier: {e}")
            return {"ok": False, "error": f"Erreur lecture fichier: {str(e)}", "imported": 0, "skipped": 0}

        if df.empty:
            return {"ok": False, "error": "Le fichier est vide", "imported": 0, "skipped": 0}

        # Column name mapping (lowercase, stripped)
        COLUMN_MAP = {
            "nom": ["nom", "name", "client", "raison_sociale", "raison sociale", "société", "societe", "company"],
            "code_client": ["code_client", "code client", "code", "ref", "reference", "référence", "ref_client"],
            "matricule_fiscale": ["matricule_fiscale", "matricule fiscale", "matricule", "mf", "tax_id", "identifiant fiscal"],
            "ville": ["ville", "city", "localité", "localite"],
            "region": ["region", "région", "zone", "gouvernorat"],
            "contact": ["contact", "contact_name", "responsable", "interlocuteur", "nom_contact", "nom contact"],
            "telephone": ["telephone", "tel", "phone", "téléphone", "tel_contact", "numéro"],
            "adresse": ["adresse", "address", "adr", "siege", "siège"],
            "type_client": ["type_client", "type client", "type", "secteur", "nature", "privé/public"],
            "international": ["international", "intl", "étranger", "etranger", "pays_etranger"],
        }

        # Auto-detect column mapping
        detected = {}
        excel_cols = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        original_cols = list(df.columns)

        for field, variants in COLUMN_MAP.items():
            for i, col_lower in enumerate(excel_cols):
                # Also check without underscores/spaces
                col_clean = col_lower.replace("_", "").replace(" ", "")
                for variant in variants:
                    variant_clean = variant.replace("_", "").replace(" ", "")
                    if col_lower == variant or col_clean == variant_clean:
                        detected[field] = original_cols[i]
                        break
                if field in detected:
                    break

        columns_detected = list(detected.keys())
        imported = 0
        skipped = 0

        for _, row in df.iterrows():
            client_dict = {}
            for field, excel_col in detected.items():
                val = row.get(excel_col, "")
                if pd.isna(val):
                    val = ""
                if field == "international":
                    val = str(val).strip().lower() in ("true", "1", "oui", "yes", "vrai", "o")
                else:
                    val = str(val).strip()
                client_dict[field] = val

            # Skip if no name
            nom = client_dict.get("nom", "").strip()
            if not nom:
                skipped += 1
                continue

            try:
                ajouter_client(client_dict)
                imported += 1
            except Exception as e:
                logger.warning(f"Import client skip '{nom}': {e}")
                skipped += 1

        # Log audit
        username = user.get("sub", "unknown")
        log_audit(username, "IMPORT_CLIENTS", f"{{\"imported\": {imported}, \"skipped\": {skipped}}}", "clients")

        return {
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "columns_detected": columns_detected,
            "total_rows": len(df),
        }
    except Exception as e:
        logger.error(f"Excel import error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/clients/{client_id}")
def update_client_api(client_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Update an existing client."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    modifier_client(client_id, body)
    return {"ok": True}


@app.delete("/api/clients/{client_id}")
def delete_client_api(client_id: int, user: dict = Depends(_verify_token)):
    """Delete a client after its equipment has been removed."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    try:
        deleted = supprimer_client(client_id)
    except ClientHasEquipmentsError as exc:
        plural = "s" if exc.equipment_count > 1 else ""
        equipment_reference = "ses équipements" if exc.equipment_count > 1 else "son équipement"
        raise HTTPException(
            status_code=409,
            detail=(
                f"Impossible de supprimer ce client : {exc.equipment_count} équipement{plural} "
                f"lui est encore associé. Supprimez d'abord {equipment_reference}."
            ),
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return {"ok": True}


# ==========================================
# LOGS / S3 MANAGEMENT
# ==========================================

__all__ = [
    "get_clients",
    "get_dashboard_equipment_types",
    "get_dashboard_regions",
    "get_dashboard_villes",
    "get_availability_trend",
    "get_clients_by_region",
    "create_client",
    "get_types_client_custom",
    "create_type_client_custom",
    "get_villes_custom",
    "create_ville_custom",
    "delete_ville_custom",
    "update_ville_custom",
    "get_pays_custom",
    "create_pays_custom",
    "delete_pays_custom",
    "import_clients_excel",
    "update_client_api",
    "delete_client_api",
]
