"""Finance, TCO, map, and SLA routes."""

from api.runtime import (
    Depends,
    HTTPException,
    Optional,
    app,
    datetime,
    db_lire_clients,
    get_config,
    get_db,
    lire_contrats,
    lire_demandes_intervention,
    lire_equipements,
    lire_interventions,
    lire_pieces,
    lire_planning,
    logger,
    pd,
)
from api.security import (
    Depends,
    HTTPException,
    Optional,
    _verify_token,
    get_db,
)
from services.scheduled_jobs import (
    get_db,
    lire_contrats,
    lire_equipements,
    lire_interventions,
    lire_planning,
    logger,
    pd,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    Optional,
    _verify_token,
    app,
    datetime,
    db_lire_clients,
    get_db,
    lire_equipements,
    lire_interventions,
    logger,
    pd,
)

@app.get("/api/finances/dashboard")
def finances_dashboard(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Dashboard financier : rentabilité par client, marges, TCO."""
    try:
        df_contrats = lire_contrats()
        df_interv = lire_interventions()
        df_equip = lire_equipements()
        df_pieces = lire_pieces()

        # --- Client profitability ---
        clients_profit = []
        all_clients = []
        # Only include clients that have a maintenance contract
        contrat_clients = set()
        if not df_contrats.empty and "client" in df_contrats.columns:
            contrat_clients = set(df_contrats["client"].dropna().unique().tolist())
        if not df_equip.empty and "Client" in df_equip.columns:
            all_clients = sorted([c for c in df_equip["Client"].dropna().unique().tolist() if c in contrat_clients])

        for cl in all_clients:
            if client and cl != client:
                continue
            # Revenue from contracts
            revenu = 0
            if not df_contrats.empty and "client" in df_contrats.columns:
                cl_contrats = df_contrats[df_contrats["client"] == cl]
                revenu = cl_contrats["montant"].sum() if "montant" in cl_contrats.columns else 0

            # Costs from interventions
            cout_interv = 0
            cout_pieces = 0
            nb_interv = 0
            duree_totale = 0
            cl_machines = df_equip[df_equip["Client"] == cl]["Nom"].tolist() if "Nom" in df_equip.columns else []
            if not df_interv.empty and "machine" in df_interv.columns and cl_machines:
                cl_interventions = df_interv[df_interv["machine"].isin(cl_machines)]
                nb_interv = len(cl_interventions)
                cout_interv = cl_interventions["cout"].sum() if "cout" in cl_interventions.columns else 0
                cout_pieces = cl_interventions["cout_pieces"].sum() if "cout_pieces" in cl_interventions.columns else 0
                duree_totale = cl_interventions["duree_minutes"].sum() if "duree_minutes" in cl_interventions.columns else 0

            # Get taux horaire from config (required, no default)
            try:
                taux_str = get_config("taux_horaire_technicien", "")
                if not taux_str:
                    raise ValueError("Taux horaire technicien non configuré dans les paramètres")
                taux = float(taux_str)
            except (ValueError, TypeError) as e:
                raise HTTPException(400, f"Erreur: {str(e)}")
            
            # Calculate labor cost from duration (for recalculation with current rate)
            cout_mo_recalculated = float((duree_totale / 60.0) * taux)
            
            # Service cost = Total intervention cost - Labor cost - Parts cost
            cout_service = max(0, float(cout_interv) - cout_mo_recalculated - float(cout_pieces))

            # Total cost remains the same
            cout_total_final = cout_service + cout_mo_recalculated + float(cout_pieces)
            marge = float(revenu) - cout_total_final
            marge_pct = round((marge / float(revenu) * 100), 1) if float(revenu) > 0 else 0.0

            nb_equip = int(len(df_equip[df_equip["Client"] == cl])) if not df_equip.empty else 0

            clients_profit.append({
                "client": cl,
                "nb_equipements": int(nb_equip),
                "revenu_contrats": round(float(revenu), 0),
                "cout_interventions": round(float(cout_service), 0),
                "cout_pieces": round(float(cout_pieces), 0),
                "cout_main_oeuvre": round(float(cout_mo_recalculated), 0),
                "cout_total": round(float(cout_total_final), 0),
                "marge": round(float(marge), 0),
                "marge_pct": float(marge_pct),
                "nb_interventions": int(nb_interv),
                "duree_totale_h": round(float(duree_totale) / 60.0, 1),
                "rentable": bool(marge >= 0),
            })

        # --- Global KPIs ---
        total_revenu = sum(c["revenu_contrats"] for c in clients_profit)
        total_cout = sum(c["cout_total"] for c in clients_profit)
        total_marge = total_revenu - total_cout
        nb_rentables = sum(1 for c in clients_profit if c["rentable"])
        nb_deficitaires = len(clients_profit) - nb_rentables

        # Sort by margin (worst first for alerts)
        clients_profit.sort(key=lambda x: x["marge"])

        return {
            "kpis": {
                "revenu_total": round(float(total_revenu), 0),
                "cout_total": round(float(total_cout), 0),
                "marge_globale": round(float(total_marge), 0),
                "marge_pct": round(float(total_marge / total_revenu * 100), 1) if total_revenu > 0 else 0.0,
                "nb_clients": int(len(clients_profit)),
                "nb_rentables": int(nb_rentables),
                "nb_deficitaires": int(nb_deficitaires),
            },
            "clients": clients_profit,
        }
    except Exception as e:
        logger.error(f"Finances dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/finances/tco")
def finances_tco(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Total Cost of Ownership par équipement."""
    try:
        df_equip = lire_equipements()
        df_interv = lire_interventions()

        tco_list = []
        if df_equip.empty:
            return tco_list

        try:
            taux_str = get_config("taux_horaire_technicien", "")
            if not taux_str:
                raise ValueError("Taux horaire technicien non configuré dans les paramètres")
            taux = float(taux_str)
        except (ValueError, TypeError) as e:
            raise HTTPException(400, f"Erreur: {str(e)}")

        for _, eq in df_equip.iterrows():
            nom = eq.get("Nom", "")
            cl = eq.get("Client", "")
            if client and cl != client:
                continue

            cout_interv = 0
            cout_pieces = 0
            nb_interv = 0
            nb_correctives = 0
            nb_preventives = 0
            duree = 0
            if not df_interv.empty and "machine" in df_interv.columns:
                eq_interv = df_interv[df_interv["machine"] == nom]
                nb_interv = len(eq_interv)
                cout_interv = eq_interv["cout"].sum() if "cout" in eq_interv.columns else 0
                cout_pieces = eq_interv["cout_pieces"].sum() if "cout_pieces" in eq_interv.columns else 0
                duree = eq_interv["duree_minutes"].sum() if "duree_minutes" in eq_interv.columns else 0
                nb_correctives = len(eq_interv[eq_interv["type_intervention"].str.lower().str.contains("correct", na=False)]) if "type_intervention" in eq_interv.columns else 0
                nb_preventives = nb_interv - nb_correctives

            cout_mo = (duree / 60.0) * taux
            # Extract service cost (intervention cost - labor - parts)
            cout_service = max(0, float(cout_interv) - cout_mo - float(cout_pieces))
            tco_total = float(cout_service) + float(cout_pieces) + cout_mo

            # Installation age (days)
            age_jours = 0
            date_install = eq.get("DateInstallation", eq.get("date_installation", ""))
            if date_install:
                try:
                    d = pd.to_datetime(str(date_install), errors="coerce")
                    if pd.notna(d):
                        age_jours = (datetime.now() - d).days
                except Exception:
                    pass

            tco_mensuel = round(tco_total / max(age_jours / 30.0, 1), 0) if age_jours > 0 else 0

            tco_list.append({
                "equipement": str(nom),
                "client": str(cl),
                "type": str(eq.get("Type", eq.get("type", ""))),
                "statut": str(eq.get("Statut", eq.get("statut", ""))),
                "age_jours": int(age_jours),
                "nb_interventions": int(nb_interv),
                "nb_correctives": int(nb_correctives),
                "nb_preventives": int(nb_preventives),
                "cout_interventions": round(float(cout_service), 0),
                "cout_pieces": round(float(cout_pieces), 0),
                "cout_main_oeuvre": round(float(cout_mo), 0),
                "tco_total": round(float(tco_total), 0),
                "tco_mensuel": round(float(tco_mensuel), 0),
                "duree_totale_h": round(float(duree) / 60.0, 1),
            })

        tco_list.sort(key=lambda x: x["tco_total"], reverse=True)
        return tco_list
    except Exception as e:
        logger.error(f"TCO error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 🗺️ CARTE GÉOGRAPHIQUE
# ==========================================

@app.get("/api/map/sites")
def map_sites(user: dict = Depends(_verify_token)):
    """Retourne les sites clients avec coordonnées GPS et score de santé."""
    import random, hashlib

    # Tunisian cities with GPS coordinates
    TUNISIAN_CITIES = {
        'tunis': (36.8065, 10.1815), 'ariana': (36.8601, 10.1956), 'ben arous': (36.7533, 10.2281),
        'manouba': (36.8100, 10.0987), 'nabeul': (36.4561, 10.7376), 'zaghouan': (36.4028, 10.1428),
        'bizerte': (37.2744, 9.8739), 'beja': (36.7256, 9.1817), 'jendouba': (36.5011, 8.7803),
        'kef': (36.1676, 8.7049), 'siliana': (36.0847, 9.3711), 'sousse': (35.8254, 10.6369),
        'monastir': (35.7643, 10.8113), 'mahdia': (35.5047, 11.0622), 'sfax': (34.7404, 10.7602),
        'kairouan': (35.6804, 10.0963), 'kasserine': (35.1672, 8.8365), 'sidi bouzid': (35.0380, 9.4849),
        'gabes': (33.8819, 10.0982), 'gabès': (33.8819, 10.0982), 'medenine': (33.3540, 10.5050),
        'tataouine': (32.9297, 10.4518), 'gafsa': (34.4250, 8.7842), 'tozeur': (33.9197, 8.1339),
        'kebili': (33.7041, 8.9711), 'kébili': (33.7041, 8.9711),
        'hammamet': (36.4000, 10.6167), 'tabarka': (36.9541, 8.7580), 'djerba': (33.8076, 10.8451),
        'grombalia': (36.6017, 10.5042), 'la marsa': (36.8783, 10.3252), 'carthage': (36.8528, 10.3233),
        'omrane': (36.8300, 10.1600), 'el omrane': (36.8300, 10.1600),
    }
    CITY_LIST = list(TUNISIAN_CITIES.values())

    def _guess_city_coords(client_name: str, ville: str):
        """Try to guess coordinates from client name or ville field."""
        for text in [ville, client_name]:
            if not text:
                continue
            lower = text.lower()
            for city, coords in TUNISIAN_CITIES.items():
                if city in lower:
                    return coords
        return None

    def _deterministic_random_coords(client_name: str):
        """Assign a deterministic 'random' city based on client name hash, with slight jitter."""
        h = int(hashlib.md5(client_name.encode()).hexdigest(), 16)
        city_coords = CITY_LIST[h % len(CITY_LIST)]
        # Add slight jitter (±0.01 degrees ≈ ±1km) so markers don't overlap
        jitter_lat = ((h >> 8) % 200 - 100) / 10000.0
        jitter_lng = ((h >> 16) % 200 - 100) / 10000.0
        return (city_coords[0] + jitter_lat, city_coords[1] + jitter_lng)

    try:
        df_equip = lire_equipements()
        df_interv = lire_interventions()
        df_plan = lire_planning()  # ← Load ONCE before the loop
        
        # Load clients to get ville and region info
        try:
            df_clients = db_lire_clients()
        except:
            df_clients = None

        sites = {}
        if df_equip.empty:
            return []

        for _, eq in df_equip.iterrows():
            cl = eq.get("Client", "")
            if not cl:
                continue
            if cl not in sites:
                # Get ville and region from clients table if available
                ville = ""
                if df_clients is not None and not df_clients.empty:
                    client_row = df_clients[df_clients["nom"] == cl]
                    if not client_row.empty:
                        ville = client_row.iloc[0].get("ville", "") or ""
                
                # Fallback to equipment ville if client ville not found
                if not ville:
                    ville = eq.get("Ville", eq.get("ville", ""))
                
                sites[cl] = {
                    "client": cl,
                    "equipements": [],
                    "nb_equipements": 0,
                    "latitude": eq.get("latitude", None),
                    "longitude": eq.get("longitude", None),
                    "adresse": eq.get("adresse", ""),
                    "ville": ville,
                }
            nom = eq.get("Nom", "")
            statut = eq.get("Statut", eq.get("statut", "Actif"))
            sites[cl]["equipements"].append({"nom": nom, "type": eq.get("Type", ""), "statut": statut})
            sites[cl]["nb_equipements"] += 1

        # Compute health scores per site + auto-assign coordinates
        result = []
        for cl, site in sites.items():
            nb = site["nb_equipements"]
            nb_hs = sum(1 for e in site["equipements"] if e["statut"] in ("Hors Service", "Critique", "En panne"))
            score = max(0, round(((nb - nb_hs) / nb) * 100)) if nb > 0 else 100

            # Auto-assign coordinates if missing
            lat, lng = site["latitude"], site["longitude"]
            assigned_ville = site.get("ville", "") or ""
            if not lat or not lng:
                guessed = _guess_city_coords(cl, assigned_ville)
                if guessed:
                    lat, lng = guessed
                    # Extract the matched city name for the ville field
                    if not assigned_ville:
                        lower = cl.lower()
                        for city_name in TUNISIAN_CITIES:
                            if city_name in lower:
                                assigned_ville = city_name.capitalize()
                                break
                else:
                    lat, lng = _deterministic_random_coords(cl)
                    if not assigned_ville:
                        # Find the closest city name for display
                        h = int(hashlib.md5(cl.encode()).hexdigest(), 16)
                        city_names = list(TUNISIAN_CITIES.keys())
                        assigned_ville = city_names[h % len(city_names)].capitalize()

            # Count interventions
            machines = [e["nom"] for e in site["equipements"]]
            nb_interv = 0
            if not df_interv.empty and "machine" in df_interv.columns:
                nb_interv = len(df_interv[df_interv["machine"].isin(machines)])

            # Next planned maintenance
            prochaine_maintenance = None
            try:
                if not df_plan.empty and "machine" in df_plan.columns:
                    today = datetime.now().strftime("%Y-%m-%d")
                    planned = df_plan[(df_plan["machine"].isin(machines)) & 
                                     (df_plan["date_prevue"] >= today) &
                                     (df_plan["statut"].isin(["Planifiée", "En cours"]))]
                    if not planned.empty:
                        prochaine_maintenance = planned["date_prevue"].min()
                        if hasattr(prochaine_maintenance, 'strftime'):
                            prochaine_maintenance = prochaine_maintenance.strftime("%Y-%m-%d")
                        else:
                            prochaine_maintenance = str(prochaine_maintenance)[:10]
            except Exception:
                pass

            result.append({
                **site,
                "latitude": float(lat) if lat and lat == lat else None,  # Check for NaN
                "longitude": float(lng) if lng and lng == lng else None,  # Check for NaN
                "ville": assigned_ville,
                "equipements": site["equipements"][:20],  # Limit for performance
                "score_sante": score,
                "nb_interventions": nb_interv,
                "prochaine_maintenance": prochaine_maintenance,
            })

        return result
    except Exception as e:
        logger.error(f"Map sites error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/map/sites/{client_name}/coordinates")
def update_site_coordinates(client_name: str, body: dict, user: dict = Depends(_verify_token)):
    """Met à jour les coordonnées GPS d'un site client (sur tous ses équipements)."""
    lat = body.get("latitude")
    lng = body.get("longitude")
    adresse = body.get("adresse", "")

    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="latitude et longitude requis")

    try:
        with get_db() as conn:
            # Update all equipments for this client
            conn.execute(
                "UPDATE equipements SET latitude = ?, longitude = ?, adresse = ? WHERE client = ?",
                (float(lat), float(lng), adresse, client_name)
            )
        return {"ok": True, "message": f"Coordonnées mises à jour pour {client_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 📅 SLA TRACKING
# ==========================================

@app.get("/api/sla/status")
def sla_status(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Suivi SLA temps réel : interventions ouvertes vs engagements contractuels."""
    try:
        df_contrats = lire_contrats()
        df_interv = lire_interventions()
        df_equip = lire_equipements()
        df_demandes = lire_demandes_intervention()

        # Build client → SLA mapping from contracts
        client_sla = {}
        if not df_contrats.empty:
            for _, c in df_contrats.iterrows():
                cl = c.get("client", "")
                sla_h_raw = c.get("sla_temps_reponse_h", 0)
                try:
                    sla_h = max(0, int(sla_h_raw)) if pd.notna(sla_h_raw) else 0
                except (TypeError, ValueError):
                    sla_h = 0
                statut = str(c.get("statut", "")).lower()
                if cl and "actif" in statut:
                    # Un SLA à 0 désactive le suivi pour ce client.
                    if cl not in client_sla or (client_sla[cl] > 0 and (sla_h == 0 or sla_h < client_sla[cl])):
                        client_sla[cl] = int(sla_h)

        # Build machine → client mapping
        machine_client = {}
        if not df_equip.empty:
            for _, eq in df_equip.iterrows():
                machine_client[eq.get("Nom", "")] = eq.get("Client", "")

        now = datetime.now()
        sla_items = []

        # Active interventions (not clôturées)
        if not df_interv.empty:
            active = df_interv[~df_interv["statut"].str.lower().str.contains("termin|clotur|clôtur", na=False)]
            if client:
                machines_client = [m for m, c in machine_client.items() if c == client]
                active = active[active["machine"].isin(machines_client)]

            for _, interv in active.iterrows():
                machine = interv.get("machine", "")
                cl = machine_client.get(machine, "")
                sla_h = client_sla[cl] if cl in client_sla else 24
                if sla_h <= 0:
                    continue

                # Start time: date_debut_intervention or date (creation)
                start_str = interv.get("date_debut_intervention") or interv.get("date", "")
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = round((now - start).total_seconds() / 3600, 1)
                remaining_h = round(sla_h - elapsed_h, 1)
                pct = min(100, round((elapsed_h / sla_h) * 100, 1)) if sla_h > 0 else 100
                breached = elapsed_h > sla_h

                sla_items.append({
                    "id": interv.get("id"),
                    "machine": machine,
                    "client": cl,
                    "technicien": interv.get("technicien", ""),
                    "type_intervention": interv.get("type_intervention", ""),
                    "statut": interv.get("statut", ""),
                    "date_debut": str(start_str)[:16],
                    "sla_h": sla_h,
                    "elapsed_h": elapsed_h,
                    "remaining_h": max(0, remaining_h),
                    "pct_used": pct,
                    "breached": breached,
                    "priorite": interv.get("priorite", ""),
                })

        # Active demandes (waiting response)
        if not df_demandes.empty:
            active_dem = df_demandes[df_demandes["statut"].isin(["Nouvelle", "En attente"])]
            if client:
                active_dem = active_dem[active_dem["client"] == client]

            for _, dem in active_dem.iterrows():
                cl = dem.get("client", "")
                sla_h = client_sla[cl] if cl in client_sla else 24
                if sla_h <= 0:
                    continue
                start_str = dem.get("date_demande", "")
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = round((now - start).total_seconds() / 3600, 1)
                remaining_h = round(sla_h - elapsed_h, 1)
                pct = min(100, round((elapsed_h / sla_h) * 100, 1)) if sla_h > 0 else 100
                breached = elapsed_h > sla_h

                sla_items.append({
                    "id": f"DEM-{dem.get('id', '')}",
                    "machine": dem.get("equipement", ""),
                    "client": cl,
                    "technicien": dem.get("technicien_assigne", ""),
                    "type_intervention": "Demande",
                    "statut": dem.get("statut", ""),
                    "date_debut": str(start_str)[:16],
                    "sla_h": sla_h,
                    "elapsed_h": elapsed_h,
                    "remaining_h": max(0, remaining_h),
                    "pct_used": pct,
                    "breached": breached,
                    "priorite": dem.get("urgence", ""),
                })

        # Sort by remaining time (most urgent first)
        sla_items.sort(key=lambda x: x["remaining_h"])

        # Compute KPIs
        total_active = len(sla_items)
        nb_breached = sum(1 for s in sla_items if s["breached"])
        nb_danger = sum(1 for s in sla_items if not s["breached"] and s["pct_used"] >= 75)
        nb_ok = total_active - nb_breached - nb_danger

        # Historical compliance (closed interventions)
        compliance_pct = 100
        if not df_interv.empty:
            closed = df_interv[df_interv["statut"].str.lower().str.contains("termin|clotur|clôtur", na=False)]
            if not closed.empty and "date_debut_intervention" in closed.columns and "date_cloture" in closed.columns:
                compliant = 0
                total_measured = 0
                for _, ci in closed.iterrows():
                    try:
                        start = pd.to_datetime(ci.get("date_debut_intervention"))
                        end = pd.to_datetime(ci.get("date_cloture"))
                        if pd.isna(start) or pd.isna(end):
                            continue
                        cl_name = machine_client.get(ci.get("machine", ""), "")
                        sla = client_sla[cl_name] if cl_name in client_sla else 24
                        if sla <= 0:
                            continue
                        duration_h = (end - start).total_seconds() / 3600
                        total_measured += 1
                        if duration_h <= sla:
                            compliant += 1
                    except Exception:
                        continue
                if total_measured > 0:
                    compliance_pct = round((compliant / total_measured) * 100, 1)

        return {
            "kpis": {
                "total_active": total_active,
                "nb_breached": nb_breached,
                "nb_danger": nb_danger,
                "nb_ok": nb_ok,
                "compliance_pct": compliance_pct,
            },
            "items": sla_items,
        }
    except Exception as e:
        logger.error(f"SLA status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)

__all__ = [
    "finances_dashboard",
    "finances_tco",
    "map_sites",
    "update_site_coordinates",
    "sla_status",
]
