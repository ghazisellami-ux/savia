"""Finance, TCO, map, and SLA routes."""

from api.runtime import (
    Depends,
    HTTPException,
    Optional,
    app,
    datetime,
    db_lire_clients,
    lire_villes_custom,
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
    require_roles,
    get_db,
    resolve_client_scope,
)
from repositories.contracts import get_contract_equipements
from services.sla_tracking import (
    active_sla_contracts, compliance_percentage, elapsed_hours, sla_contract_for,
    sla_start_at, sla_start_value,
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
    require_roles(user, "Admin", "Manager")
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
            nb_correctives = 0
            nb_preventives = 0
            duree_totale = 0
            cl_machines = df_equip[df_equip["Client"] == cl]["Nom"].tolist() if "Nom" in df_equip.columns else []
            if not df_interv.empty and "machine" in df_interv.columns and cl_machines:
                cl_interventions = df_interv[df_interv["machine"].isin(cl_machines)]
                nb_interv = len(cl_interventions)
                cout_interv = cl_interventions["cout"].sum() if "cout" in cl_interventions.columns else 0
                cout_pieces = cl_interventions["cout_pieces"].sum() if "cout_pieces" in cl_interventions.columns else 0
                duree_totale = cl_interventions["duree_minutes"].sum() if "duree_minutes" in cl_interventions.columns else 0
                if "type_intervention" in cl_interventions.columns:
                    is_corrective = cl_interventions["type_intervention"].fillna("").astype(str).str.lower().str.contains("correct")
                    nb_correctives = int(is_corrective.sum())
                    nb_preventives = int(nb_interv - nb_correctives)

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
                "cout_interventions_brut": round(float(cout_interv), 0),
                "cout_pieces": round(float(cout_pieces), 0),
                "cout_main_oeuvre": round(float(cout_mo_recalculated), 0),
                "cout_total": round(float(cout_total_final), 0),
                "marge": round(float(marge), 0),
                "marge_pct": float(marge_pct),
                "nb_interventions": int(nb_interv),
                "nb_correctives": int(nb_correctives),
                "nb_preventives": int(nb_preventives),
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
    require_roles(user, "Admin", "Manager")
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

def _map_health_key(value):
    return str(value or "").strip().casefold()


def _map_client_key(value):
    """Normalize client names so map records cannot split one client in two sites."""
    return " ".join(str(value or "").split()).casefold()


def _map_status_score(status):
    """Fallback score when the dashboard health scorer has no row."""
    status_key = _map_health_key(status)
    if status_key == "hors service":
        return 25
    if status_key in {"critique", "en panne"}:
        return 45
    if status_key == "en atelier":
        return 60
    if status_key == "en maintenance":
        return 75
    return 100


def _map_site_score(client, equipements, health_scores_by_equipment):
    equipment_scores = [
        health_scores_by_equipment.get(
            (_map_health_key(equipement["nom"]), _map_health_key(client)),
            _map_status_score(equipement["statut"]),
        )
        for equipement in equipements
    ]
    return round(sum(equipment_scores) / len(equipment_scores)) if equipment_scores else 100


@app.get("/api/map/sites")
def map_sites(country: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Retourne les sites clients avec coordonnées GPS et score de santé."""
    import random, hashlib

    effective_client = resolve_client_scope(user, None)

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
    COUNTRY_CITIES = {
        'DZ': {'alger': (36.7538, 3.0588), 'oran': (35.6971, -0.6308), 'constantine': (36.365, 6.6147), 'annaba': (36.9, 7.7667), 'blida': (36.47, 2.83), 'setif': (36.19, 5.41), 'tlemcen': (34.88, -1.32), 'bejaia': (36.75, 5.06), 'batna': (35.56, 6.17), 'ouargla': (31.95, 5.33)},
        'MA': {'rabat': (34.0209, -6.8416), 'casablanca': (33.5731, -7.5898), 'marrakech': (31.6295, -7.9811), 'fes': (34.0331, -5.0003), 'tanger': (35.7595, -5.834), 'agadir': (30.4278, -9.5981), 'oujda': (34.6814, -1.9086), 'meknes': (33.8935, -5.5473), 'tetouan': (35.5889, -5.3626), 'safi': (32.2994, -9.2372)},
        'SN': {'dakar': (14.7167, -17.4677), 'thies': (14.7886, -16.926), 'saint-louis': (16.0326, -16.4818), 'kaolack': (14.151, -16.0726), 'ziguinchor': (12.5833, -16.2719), 'touba': (14.85, -15.8833)},
        'FR': {'paris': (48.8566, 2.3522), 'marseille': (43.2965, 5.3698), 'lyon': (45.764, 4.8357), 'toulouse': (43.6047, 1.4442), 'nice': (43.7102, 7.262), 'nantes': (47.2184, -1.5536), 'strasbourg': (48.5734, 7.7521), 'bordeaux': (44.8378, -0.5792), 'lille': (50.6292, 3.0573), 'montpellier': (43.6108, 3.8767)},
        'US': {'new york': (40.7128, -74.006), 'los angeles': (34.0522, -118.2437), 'chicago': (41.8781, -87.6298), 'houston': (29.7604, -95.3698), 'miami': (25.7617, -80.1918), 'boston': (42.3601, -71.0589), 'atlanta': (33.749, -84.388), 'dallas': (32.7767, -96.797)},
        'QA': {'doha': (25.2854, 51.531), 'al rayyan': (25.2919, 51.4244), 'al wakrah': (25.1659, 51.5976), 'al khor': (25.6804, 51.5058)},
        'SA': {'riyad': (24.7136, 46.6753), 'jeddah': (21.5433, 39.1728), 'dammam': (26.4207, 50.0888), 'medine': (24.5247, 39.5692), 'la mecque': (21.3891, 39.8579), 'abha': (18.2465, 42.5117)},
    }
    country_aliases = {'TUNISIE': 'TN', 'TUNISIA': 'TN', 'ALGÉRIE': 'DZ', 'ALGERIE': 'DZ', 'MAROC': 'MA', 'SÉNÉGAL': 'SN', 'SENEGAL': 'SN', 'FRANCE': 'FR', 'ÉTATS-UNIS': 'US', 'ETATS-UNIS': 'US', 'QATAR': 'QA', 'ARABIE SAOUDITE': 'SA'}
    configured_countries = str(country or get_config('pays', 'TN')).replace(';', ',').split(',')
    requested_countries = []
    for raw_country in configured_countries:
        raw_key = str(raw_country).strip().upper()
        if not raw_key:
            continue
        normalized_key = country_aliases.get(raw_key, raw_key)
        if normalized_key not in requested_countries:
            requested_countries.append(normalized_key)
    if not requested_countries:
        requested_countries = ['TN']
    country_key = requested_countries[0]
    active_cities = {}
    for selected_key in requested_countries:
        active_cities.update(TUNISIAN_CITIES if selected_key == 'TN' else COUNTRY_CITIES.get(selected_key, {}))
    try:
        for selected_key in requested_countries:
            for custom_city in lire_villes_custom(selected_key):
                if custom_city.get("latitude") is not None and custom_city.get("longitude") is not None:
                    active_cities[str(custom_city.get("nom", "")).strip().lower()] = (
                        float(custom_city["latitude"]), float(custom_city["longitude"])
                    )
    except Exception as exc:
        logger.warning("Impossible de charger les villes personnalisées pour la carte: %s", exc)
    CITY_LIST = list(active_cities.values())

    def _guess_city_coords(client_name: str, ville: str):
        """Try to guess coordinates from client name or ville field."""
        for text in [ville, client_name]:
            if not text:
                continue
            lower = text.lower()
            for city, coords in active_cities.items():
                if city in lower:
                    return coords
        return None

    def _deterministic_random_coords(client_name: str):
        """Assign a deterministic 'random' city based on client name hash, with slight jitter."""
        if not CITY_LIST:
            return None
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

        # Keep the map score aligned with the dashboard score, which accounts
        # for intervention history and the current equipment status.
        health_scores_by_equipment = {}
        try:
            from controllers.auth_dashboard import get_health_scores

            for health_row in get_health_scores(user=user):
                key = (_map_health_key(health_row.get("machine")), _map_health_key(health_row.get("client")))
                health_scores_by_equipment[key] = int(health_row.get("score", 100))
        except Exception as exc:
            logger.warning("Impossible de charger les scores santé détaillés pour la carte: %s", exc)
        
        # Load clients to get ville and region info
        try:
            df_clients = db_lire_clients()
        except:
            df_clients = None

        # The clients registry is the only source of truth for map sites and
        # the site counter. Equipment records can contain legacy names, so
        # they enrich a registered client but must never create an extra site.
        sites = {}
        client_site_keys = {}
        if df_clients is not None and not df_clients.empty:
            for _, client_row in df_clients.iterrows():
                cl = str(client_row.get("nom", "") or "").strip()
                if not cl:
                    continue
                client_country_raw = str(client_row.get("country_code", "TN") or "TN").strip().upper()
                client_country = country_aliases.get(client_country_raw, client_country_raw)
                if client_country not in requested_countries:
                    continue
                sites[cl] = {
                    "client": cl,
                    "country_code": client_country,
                    "equipements": [],
                    "nb_equipements": 0,
                    "latitude": client_row.get("latitude", None),
                    "longitude": client_row.get("longitude", None),
                    "adresse": client_row.get("adresse", "") or "",
                    "ville": client_row.get("ville", "") or "",
                }
                client_site_keys[_map_client_key(cl)] = cl

        for _, eq in df_equip.iterrows():
            raw_client = str(eq.get("Client", "") or "").strip()
            if not raw_client:
                continue
            canonical_client = client_site_keys.get(_map_client_key(raw_client))
            if not canonical_client:
                logger.warning(
                    "Équipement %r ignoré sur la carte : client %r absent du registre clients",
                    eq.get("Nom", ""), raw_client,
                )
                continue

            site = sites[canonical_client]
            if not site.get("ville"):
                site["ville"] = eq.get("Ville", eq.get("ville", "")) or ""
            if not site.get("adresse"):
                site["adresse"] = eq.get("adresse", "") or ""
            if not site.get("latitude") and eq.get("latitude"):
                site["latitude"] = eq.get("latitude")
                site["longitude"] = eq.get("longitude")
            nom = eq.get("Nom", "")
            statut = eq.get("Statut", eq.get("statut", "Actif"))
            site["equipements"].append({"nom": nom, "type": eq.get("Type", ""), "statut": statut})
            site["nb_equipements"] += 1

        # Compute health scores per site + auto-assign coordinates
        result = []
        for cl, site in sites.items():
            if effective_client and str(cl).strip().casefold() != effective_client.strip().casefold():
                continue
            score = _map_site_score(cl, site["equipements"], health_scores_by_equipment)

            # Auto-assign coordinates if missing
            lat, lng = site["latitude"], site["longitude"]
            assigned_ville = site.get("ville", "") or ""
            if not lat or not lng:
                guessed = _guess_city_coords(cl, assigned_ville)
                if guessed:
                    lat, lng = guessed
                    if not assigned_ville:
                        lower = cl.lower()
                        for city_name in active_cities:
                            if city_name in lower:
                                assigned_ville = city_name.capitalize()
                                break
                else:
                    fallback = _deterministic_random_coords(cl)
                    if fallback:
                        lat, lng = fallback
                        if not assigned_ville:
                            h = int(hashlib.md5(cl.encode()).hexdigest(), 16)
                            city_names = list(active_cities.keys())
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
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    lat = body.get("latitude")
    lng = body.get("longitude")
    adresse = body.get("adresse", "")

    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="latitude et longitude requis")

    try:
        latitude = float(lat)
        longitude = float(lng)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Coordonnées GPS invalides") from None
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Coordonnées GPS hors limites")

    try:
        with get_db() as conn:
            # Update all equipments for this client
            conn.execute(
                "UPDATE equipements SET latitude = %s, longitude = %s, adresse = %s WHERE client = %s",
                (latitude, longitude, adresse, client_name)
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
    effective_client = resolve_client_scope(user, client)
    try:
        df_contrats = lire_contrats()
        df_interv = lire_interventions()
        df_equip = lire_equipements()
        df_demandes = lire_demandes_intervention()

        contractual_slas = active_sla_contracts(
            df_contrats.to_dict("records") if not df_contrats.empty else [],
            get_contract_equipements,
        )

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
            if effective_client:
                target_client = effective_client.strip().casefold()
                machines_client = [
                    m for m, c in machine_client.items()
                    if str(c or "").strip().casefold() == target_client
                ]
                active = active[active["machine"].isin(machines_client)]

            for _, interv in active.iterrows():
                machine = interv.get("machine", "")
                cl = interv.get("client", "") or machine_client.get(machine, "")
                contract = sla_contract_for(
                    contractual_slas, cl, machine, interv.get("type_intervention", ""),
                )
                if not contract:
                    continue
                sla_h = contract["sla_h"]

                # The planning's current date wins after every reschedule.
                # Technician start timestamps must not postpone the SLA.
                start_str = sla_start_value(interv)
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = elapsed_hours(start_str, now, business_day_start_hour=8)
                if elapsed_h is None:
                    continue
                sla_start = sla_start_at(start_str, business_day_start_hour=8)
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
                    "date_debut": str(sla_start)[:16] if sla_start else str(start_str)[:16],
                    "sla_h": sla_h,
                    "contract_id": contract["id"],
                    "contract_type": contract["type_contrat"],
                    "elapsed_h": elapsed_h,
                    "remaining_h": max(0, remaining_h),
                    "pct_used": pct,
                    "breached": breached,
                    "priorite": interv.get("priorite", ""),
                })

        # Active demandes (waiting response)
        if not df_demandes.empty:
            active_dem = df_demandes[df_demandes["statut"].isin(["Nouvelle", "En attente"])]
            if effective_client:
                active_dem = active_dem[
                    active_dem["client"].astype(str).str.strip().str.casefold()
                    == effective_client.strip().casefold()
                ]

            for _, dem in active_dem.iterrows():
                cl = dem.get("client", "")
                machine = dem.get("equipement", "")
                contract = sla_contract_for(
                    contractual_slas, cl, machine, dem.get("type_intervention", "Corrective"),
                )
                if not contract:
                    continue
                sla_h = contract["sla_h"]
                start_str = dem.get("date_demande", "")
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = elapsed_hours(start, now)
                if elapsed_h is None:
                    continue
                remaining_h = round(sla_h - elapsed_h, 1)
                pct = min(100, round((elapsed_h / sla_h) * 100, 1)) if sla_h > 0 else 100
                breached = elapsed_h > sla_h

                sla_items.append({
                    "id": f"DEM-{dem.get('id', '')}",
                    "machine": machine,
                    "client": cl,
                    "technicien": dem.get("technicien_assigne", ""),
                    "type_intervention": "Demande",
                    "statut": dem.get("statut", ""),
                    "date_debut": str(start_str)[:16],
                    "sla_h": sla_h,
                    "contract_id": contract["id"],
                    "contract_type": contract["type_contrat"],
                    "elapsed_h": elapsed_h,
                    "remaining_h": max(0, remaining_h),
                    "pct_used": pct,
                    "breached": breached,
                    "priorite": dem.get("priorite") or dem.get("urgence", ""),
                })

        # Sort by remaining time (most urgent first)
        sla_items.sort(key=lambda x: x["remaining_h"])

        # Compute KPIs
        total_active = len(sla_items)
        nb_breached = sum(1 for s in sla_items if s["breached"])
        nb_danger = sum(1 for s in sla_items if not s["breached"] and s["pct_used"] >= 75)
        nb_ok = total_active - nb_breached - nb_danger

        # Historical compliance plus currently open commitments.  A breached
        # item must lower the global rate immediately, not only at closure.
        historical_compliant = 0
        historical_total = 0
        if not df_interv.empty:
            closed = df_interv[df_interv["statut"].str.lower().str.contains("termin|clotur|clôtur", na=False)]
            if not closed.empty and "date_debut_intervention" in closed.columns and "date_cloture" in closed.columns:
                for _, ci in closed.iterrows():
                    try:
                        start = pd.to_datetime(ci.get("date_debut_intervention"))
                        end = pd.to_datetime(ci.get("date_cloture"))
                        if pd.isna(start) or pd.isna(end):
                            continue
                        cl_name = ci.get("client", "") or machine_client.get(ci.get("machine", ""), "")
                        if effective_client and str(cl_name).strip().casefold() != effective_client.strip().casefold():
                            continue
                        contract = sla_contract_for(
                            contractual_slas, cl_name, ci.get("machine", ""), ci.get("type_intervention", ""),
                        )
                        if not contract:
                            continue
                        sla = contract["sla_h"]
                        duration_h = (end - start).total_seconds() / 3600
                        historical_total += 1
                        if duration_h <= sla:
                            historical_compliant += 1
                    except Exception:
                        continue
        compliance_pct = compliance_percentage(historical_compliant, historical_total, sla_items)

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
