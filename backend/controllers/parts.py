"""Spare-parts, stock-request, and prediction routes."""

from api.runtime import (
    Body,
    Depends,
    HTTPException,
    ajouter_notification_piece,
    ajouter_piece,
    app,
    calculate_piece_parameters,
    datetime,
    get_db,
    lire_fournisseurs,
    ajouter_fournisseur,
    lire_pieces,
    lire_pieces_demandees_en_attente,
    lire_toutes_pieces_demandees,
    log_audit,
    logger,
    marquer_notification_traitee,
    modifier_piece,
    notifications_rupture_pour_piece,
    predict_commande_date,
    predict_pieces_a_commander,
    resoudre_piece_demandee,
    supprimer_piece,
    update_piece_parameters_batch,
)
from api.security import (
    Depends,
    HTTPException,
    _check_create_piece_permission,
    _verify_token,
    require_roles,
    get_db,
)
from services.scheduled_jobs import (
    _df_to_records,
    _send_telegram,
    _send_telegram_bot,
    get_db,
    logger,
    update_piece_parameters_batch,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    _verify_token,
    app,
    datetime,
    get_db,
    log_audit,
    logger,
)
from services.spare_parts_prediction_engine import predict_piece_order_date as predict_piece_order_date_v2, predict_spare_parts

STOCK_READ_ROLES = ("Admin", "Manager", "Responsable Technique", "Technicien", "Gestionnaire", "Gestionnaire de stock")


def _validate_piece_payload(body: dict) -> None:
    """Validate fields required to keep stock costs and forecasts reliable."""
    required_text = {
        "reference": "Référence",
        "designation": "Désignation",
        "domaine": "Domaine",
        "equipement_type": "Type d'équipement",
        "fournisseur": "Fournisseur",
    }
    missing = [label for field, label in required_text.items() if not str(body.get(field) or "").strip()]
    required_numbers = ("stock_actuel", "stock_minimum", "prix_unitaire")
    missing.extend(field for field in required_numbers if body.get(field) in (None, ""))
    if missing:
        raise HTTPException(status_code=422, detail=f"Champs obligatoires manquants : {', '.join(missing)}")

    import math
    try:
        stock = float(body["stock_actuel"])
        minimum = float(body["stock_minimum"])
        price = float(body["prix_unitaire"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Stock et prix doivent être des nombres valides")
    if not all(math.isfinite(value) for value in (stock, minimum, price)):
        raise HTTPException(status_code=422, detail="Stock et prix doivent être des nombres finis")
    if not stock.is_integer() or not minimum.is_integer():
        raise HTTPException(status_code=422, detail="Le stock doit être exprimé en unités entières")
    if stock < 0 or minimum < 0:
        raise HTTPException(status_code=422, detail="Le stock ne peut pas être négatif")
    if price <= 0:
        raise HTTPException(status_code=422, detail="Le prix unitaire doit être supérieur à zéro")

@app.get("/api/pieces")
def get_pieces(user: dict = Depends(_verify_token)):
    require_roles(user, *STOCK_READ_ROLES)
    return _df_to_records(lire_pieces())


@app.get("/api/fournisseurs")
def get_fournisseurs(user: dict = Depends(_verify_token)):
    """Return the supplier catalog used by spare-part forms."""
    require_roles(user, *STOCK_READ_ROLES)
    return lire_fournisseurs()


@app.post("/api/fournisseurs")
def post_fournisseur(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    """Register a supplier so it can be selected for future spare parts."""
    if not _check_create_piece_permission(user):
        raise HTTPException(status_code=403, detail="Création de fournisseur non autorisée")
    nom = str(payload.get("nom") or "").strip()
    if not nom:
        raise HTTPException(status_code=400, detail="Nom du fournisseur requis")
    ajouter_fournisseur(nom)
    return {"ok": True}


@app.get("/api/pieces/predictions/priorite")
def get_pieces_a_commander(limit: int = 10, user: dict = Depends(_verify_token)):
    require_roles(user, *STOCK_READ_ROLES)
    """
    Retourne les pièces à commander en priorité (N pièces les plus urgentes).
    Utilise la prédiction avancée multi-facteur.
    
    Query params:
        - limit: Nombre de pièces à retourner (défaut: 10)
    
    Returns:
        List of pieces ranked by urgence (CRITIQUE, HAUTE, NORMALE, BASSE)
    """
    try:
        with get_db() as conn:
            predictions = predict_spare_parts(conn, limit=limit)
        return predictions
    except Exception as e:
        logger.error(f"Erreur prédiction pièces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pieces/{piece_id}/prediction")
def predict_piece_order_date(piece_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, *STOCK_READ_ROLES)
    """
    Génère une prédiction détaillée pour une pièce spécifique.
    Utilise tous les paramètres avancés (consommation, lead time, criticité, etc).
    
    Returns:
        {
            'date_commande': ISO date,
            'urgence': 'CRITIQUE' | 'HAUTE' | 'NORMALE' | 'BASSE',
            'raison': str (explication du calcul),
            'jours_avant_rupture': float,
            'stock_previsionnel_jours': float,
            'details': {...}
        }
    """
    try:
        with get_db() as conn:
            piece = conn.execute(
                """SELECT id, reference, designation, stock_actuel, stock_minimum,
                          consommation_moyenne_mois, delai_fournisseur_jours, criticite,
                          prix_unitaire, nombre_equipements_relies, utilisation_recente_30j
                   FROM pieces_rechange WHERE id = %s""",
                (piece_id,)
            ).fetchone()
        
        if not piece:
            raise HTTPException(status_code=404, detail="Pièce non trouvée")
        
        with get_db() as conn:
            prediction = predict_piece_order_date_v2(conn, piece_id)
        if prediction is None:
            raise HTTPException(status_code=404, detail="Pièce non trouvée")
        return {
            'piece_id': piece_id,
            'reference': piece['reference'],
            'designation': piece['designation'],
            **prediction
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur prédiction pièce {piece_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pieces/prediction-feedback")
def create_spare_part_prediction_feedback(body: dict = Body(...), user: dict = Depends(_verify_token)):
    """Persist the real outcome of a spare-part replenishment forecast."""
    require_roles(user, *STOCK_READ_ROLES)
    resultat = str(body.get("resultat") or body.get("type") or "").strip().lower()
    if resultat not in {"correct", "faux_positif", "decale"}:
        raise HTTPException(status_code=422, detail="Résultat de feedback invalide")
    reference = str(body.get("reference") or "").strip()
    if not reference:
        raise HTTPException(status_code=422, detail="Référence pièce obligatoire")
    try:
        quantite = int(body["quantite"]) if body.get("quantite") is not None else None
        risque = float(body["risque_rupture_pct"]) if body.get("risque_rupture_pct") is not None else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Valeur de prévision invalide")

    import json
    with get_db() as conn:
        conn.execute(
            """INSERT INTO spare_parts_prediction_feedback (
                reference, designation, resultat, date_calcul, date_predite,
                date_reelle, quantite, risque_rupture_pct, modele_version,
                features_json, username
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                reference,
                str(body.get("designation") or ""),
                resultat,
                str(body.get("date_calcul") or ""),
                str(body.get("date_predite") or ""),
                str(body.get("date_reelle") or body.get("vraiDate") or ""),
                quantite,
                risque,
                str(body.get("modele_version") or ""),
                json.dumps(body.get("features") or {}, ensure_ascii=False),
                str(user.get("sub") or "system"),
            ),
        )
        log_audit(
            str(user.get("sub") or "system"),
            "SPARE_PART_PREDICTION_FEEDBACK",
            f"{reference}: {resultat}",
            "pieces",
        )
    return {"ok": True}


@app.get("/api/pieces/prediction-feedback")
def list_spare_part_prediction_feedback(limit: int = 100, user: dict = Depends(_verify_token)):
    """Return the server-side history of spare-parts forecast feedback."""
    require_roles(user, *STOCK_READ_ROLES)
    limit = max(1, min(limit, 500))
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM spare_parts_prediction_feedback ORDER BY timestamp DESC LIMIT %s",
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key, value in list(item.items()):
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        result.append(item)
    return result


def _normalize_ref(ref: str) -> str:
    """Normalise une référence pour matching flou: supprime tirets, espaces, points, underscores, met en minuscule."""
    import re
    return re.sub(r'[\s\-_.\\/]+', '', ref).lower().strip()


def _refs_match(ref1: str, ref2: str) -> bool:
    """Vérifie si deux références correspondent (matching strict normalisé).
    Normalise en supprimant tirets, espaces, points, underscores et compare en minuscule.
    Ex: PS-XR400 == PSXR400 == ps xr 400  ✅
    Ex: XR400 != PS-XR400  ❌ (pas de matching partiel pour éviter les faux positifs)
    """
    n1 = _normalize_ref(ref1)
    n2 = _normalize_ref(ref2)
    if not n1 or not n2:
        return False
    return n1 == n2


def _check_pieces_demandees_disponibles(reference: str, nom_piece: str, stock: int):
    """Vérifie si des demandes de pièces en attente correspondent à cette référence.
    Utilise un matching flou (normalisation des tirets, espaces, casse).
    Si oui, envoie notifications PWA + Telegram et marque les demandes comme résolues."""
    # Récupérer TOUTES les demandes en attente et filtrer par matching flou
    df_demandes = lire_pieces_demandees_en_attente()  # sans filtre ref
    if df_demandes.empty:
        return

    # Filtrer par matching flou
    matched_indices = []
    for idx, d in df_demandes.iterrows():
        demande_ref = d.get("reference") or ""
        if _refs_match(reference, demande_ref):
            matched_indices.append(idx)
    
    if not matched_indices:
        return
    
    df_matched = df_demandes.loc[matched_indices]

    # Grouper par technicien
    tech_map: dict = {}
    for _, d in df_matched.iterrows():
        t = d.get("technicien") or "inconnu"
        if t not in tech_map:
            tech_map[t] = []
        tech_map[t].append({
            "intervention_id": d.get("intervention_id") or "",
            "equipement": d.get("equipement") or "",
            "client": d.get("client") or "",
            "probleme": d.get("probleme") or "",
            "demande_id": int(d["id"]),
        })

    for tech, demandes in tech_map.items():
        machines = ", ".join(set(d["equipement"] for d in demandes if d["equipement"]))
        clients = ", ".join(set(d["client"] for d in demandes if d.get("client")))
        problemes = "; ".join(set(d["probleme"] for d in demandes if d.get("probleme")))
        inter_ids = ", ".join(f"#{d['intervention_id']}" for d in demandes if d.get("intervention_id"))
        nb = len(demandes)
        # Notification PWA → technicien
        ajouter_notification_piece({
            "type": "piece_dispo",
            "intervention_id": demandes[0].get("intervention_id") or None,
            "intervention_ref": (
                f"#{demandes[0].get('intervention_id')}"
                if demandes[0].get("intervention_id") else ""
            ),
            "piece_reference": reference,
            "piece_nom": nom_piece,
            "technicien": tech,
            "equipement": machines,
            "client": clients,
            "message": (
                f"✅ La pièce demandée {reference} ({nom_piece}) est maintenant disponible — "
                f"{nb} intervention(s) en attente : {inter_ids or 'N/A'}"
            ),
            "source": "stock",
            "destination": "technicien",
        })
        logger.info(f"Notif pièce demandée disponible pour {tech}: {reference}")

    # Telegram : pièce demandée disponible
    try:
        all_techs = ", ".join(tech_map.keys()) or "N/A"
        all_machines = ", ".join(
            set(d["equipement"] for ds in tech_map.values() for d in ds if d.get("equipement"))
        ) or "N/A"
        all_clients = ", ".join(
            set(d["client"] for ds in tech_map.values() for d in ds if d.get("client"))
        ) or "N/A"
        all_problemes = "; ".join(
            set(d["probleme"] for ds in tech_map.values() for d in ds if d.get("probleme"))
        )
        all_inter_ids = ", ".join(
            f"#{d['intervention_id']}" for ds in tech_map.values() for d in ds if d.get("intervention_id")
        ) or "N/A"
        client_line = f"\n👤 Client : <b>{all_clients}</b>" if all_clients != "N/A" else ""
        probleme_line = f"\n🔧 Problème : {all_problemes}" if all_problemes else ""
        msg_tg = (
            f"🟢 <b>PIÈCE DEMANDÉE DISPONIBLE</b>\n\n"
            f"🔩 Pièce : <b>{nom_piece}</b>\n"
            f"🏷 Référence : <b>{reference}</b>\n"
            f"📦 Stock actuel : <b>{stock}</b>\n\n"
            f"🔗 Intervention(s) : {all_inter_ids}\n"
            f"🏥 Équipement(s) : {all_machines}"
            f"{client_line}"
            f"{probleme_line}\n"
            f"👷 Technicien(s) : {all_techs}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        _send_telegram_bot("telegram", msg_tg)
        logger.info(f"Telegram pièce demandée disponible envoyé: {reference}")
    except Exception as tg_err:
        logger.error(f"Telegram pièce demandée dispo erreur: {tg_err}")

    # Marquer les demandes comme résolues
    for ds in tech_map.values():
        for d in ds:
            try:
                resoudre_piece_demandee(d["demande_id"])
            except Exception:
                pass


# ── API Pièces demandées (non référencées) ──

@app.get("/api/pieces-demandees")
def get_pieces_demandees(statut: str = None, user: dict = Depends(_verify_token)):
    require_roles(user, *STOCK_READ_ROLES)
    """Liste les demandes de pièces. ?statut=en_attente pour filtrer."""
    df = lire_toutes_pieces_demandees(statut=statut)
    return _df_to_records(df)


@app.post("/api/pieces-demandees/{demande_id}/resoudre")
def resolve_piece_demandee(demande_id: int, user: dict = Depends(_verify_token)):
    if not _check_create_piece_permission(user):
        raise HTTPException(status_code=403, detail="Votre rôle n'autorise pas cette action sur le stock")
    """Résoudre manuellement une demande de pièce (le gestionnaire confirme la disponibilité)."""
    try:
        # Récupérer la demande pour envoyer la notification
        df = lire_toutes_pieces_demandees()
        demande = None
        for _, d in df.iterrows():
            if int(d["id"]) == demande_id:
                demande = d
                break
        
        resoudre_piece_demandee(demande_id)
        
        # Envoyer notification au technicien si on a les infos
        if demande is not None:
            # L'ajout au stock peut avoir déjà résolu la demande et envoyé la notification.
            # L'endpoint doit rester idempotent pour éviter un second message Telegram.
            if str(demande.get("statut") or "").lower() != "en_attente":
                return {"ok": True, "already_resolved": True}
            tech = demande.get("technicien") or ""
            ref = demande.get("reference") or ""
            designation = demande.get("designation") or ref
            intervention_id = demande.get("intervention_id") or ""
            client = demande.get("client") or ""
            equipement = demande.get("equipement") or ""
            probleme = demande.get("probleme") or ""
            if tech:
                ajouter_notification_piece({
                    "type": "piece_dispo",
                    "piece_reference": ref,
                    "piece_nom": designation,
                    "technicien": tech,
                    "intervention_id": intervention_id,
                    "equipement": equipement,
                    "client": client,
                    "message": f"✅ La pièce demandée {ref} ({designation}) est maintenant disponible — intervention #{intervention_id}",
                    "source": "stock",
                    "destination": "technicien",
                })
                # Telegram avec détails complets
                client_line = f"\n👤 Client : <b>{client}</b>" if client else ""
                equip_line = f"\n🏥 Équipement : <b>{equipement}</b>" if equipement else ""
                probleme_line = f"\n🔧 Problème : {probleme}" if probleme else ""
                msg_tg = (
                    f"🟢 <b>PIÈCE DEMANDÉE DISPONIBLE</b>\n\n"
                    f"🔩 Pièce : <b>{designation}</b>\n"
                    f"🏷 Référence : <b>{ref}</b>\n"
                    f"🔗 Intervention : #{intervention_id}"
                    f"{client_line}"
                    f"{equip_line}"
                    f"{probleme_line}\n"
                    f"👷 Technicien : {tech}\n"
                    f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )
                _send_telegram_bot("telegram", msg_tg)
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erreur résolution pièce demandée: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pieces")
def create_piece(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_piece_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Gestionnaires de stock, Responsables, Managers et Admins"
        )
    
    # Les références sont normalisées et doivent rester uniques, sans remplacer
    # silencieusement une pièce existante.
    body = dict(body)
    body["reference"] = str(body.get("reference") or "").strip().upper()
    _validate_piece_payload(body)
    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM pieces_rechange WHERE LOWER(TRIM(reference)) = LOWER(%s) LIMIT 1",
            (body["reference"],),
        ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Cette référence existe déjà.")
    try:
        ajouter_piece(body)
    except Exception as exc:
        # Keep the uniqueness guarantee if two requests arrive at the same time.
        if any(token in str(exc).lower() for token in ("duplicate", "unique")):
            raise HTTPException(status_code=409, detail="Cette référence existe déjà.") from exc
        raise
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "reference": body.get("reference", ""),
        "designation": body.get("designation", ""),
        "stock_initial": body.get("stock_actuel", 0),
    }, ensure_ascii=False)
    log_audit(username, "CREATE_PIECE", details, "pieces")

    # Vérifier si cette pièce était demandée par un technicien (non référencée)
    reference = body.get("reference", "")
    stock = int(body.get("stock_actuel", 0) or 0)
    nom_piece = body.get("designation", "") or reference
    if reference and stock > 0:
        try:
            _check_pieces_demandees_disponibles(reference, nom_piece, stock)
        except Exception as e:
            logger.error(f"Erreur check pièces demandées (POST): {e}")

    return {"ok": True}


@app.put("/api/pieces/{piece_id}")
def update_piece(piece_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Mise à jour d'une pièce. Si stock passe de 0 → >0, déclenche notifications pour les techniciens en attente."""
    if not _check_create_piece_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Gestionnaires de stock, Responsables, Managers et Admins")
    # Récupérer le stock AVANT modification pour détecter le réapprovisionnement
    _validate_piece_payload(body)
    nouveau_stock = body.get("stock_actuel")
    try:
        with get_db() as conn:
            old = conn.execute(
                "SELECT reference, designation, stock_actuel FROM pieces_rechange WHERE id = %s",
                (piece_id,)
            ).fetchone()
        stock_avant = int(old["stock_actuel"]) if old else None
        reference = old["reference"] if old else ""
        nom_piece = old["designation"] if old else ""
    except Exception:
        stock_avant = None
        reference = ""
        nom_piece = ""

    modifier_piece(piece_id, body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "piece_id": piece_id,
        "reference": reference,
        "changes": body,
    }, ensure_ascii=False)
    log_audit(username, "UPDATE_PIECE", details, "pieces")

    # Détecter réapprovisionnement : stock passe de 0 (ou négatif) → positif
    if nouveau_stock is not None and stock_avant is not None:
        try:
            if int(stock_avant) <= 0 and int(nouveau_stock) > 0 and reference:
                # Chercher toutes les notifications rupture non traitées pour cette pièce
                df_notifs = notifications_rupture_pour_piece(reference)
                if not df_notifs.empty:
                    # Grouper par technicien
                    tech_map: dict = {}
                    for _, n in df_notifs.iterrows():
                        t = n.get("technicien") or "inconnu"
                        if t not in tech_map:
                            tech_map[t] = []
                        tech_map[t].append({
                            "machine": n.get("equipement") or "",
                            "intervention_id": n.get("intervention_id") or "",
                        })

                    for tech, interventions_list in tech_map.items():
                        machines = ", ".join(set(i["machine"] for i in interventions_list if i["machine"]))
                        nb = len(interventions_list)
                        inter_ids = ", ".join(
                            f"#{i['intervention_id']}" for i in interventions_list if i.get("intervention_id")
                        )
                        ajouter_notification_piece({
                            "type": "piece_dispo",
                            "piece_reference": reference,
                            "piece_nom": nom_piece,
                            "technicien": tech,
                            "equipement": machines,
                            "message": (
                                f"✅ La pièce {reference} ({nom_piece}) est maintenant disponible — "
                                f"{nb} intervention(s) en attente sur : {machines or 'N/A'}"
                            ),
                            "source": "stock",
                            "destination": "technicien",
                        })
                        logger.info(f"Notif piece_dispo créée pour technicien {tech}: pièce {reference}")

                    # --- Telegram : pièce à nouveau disponible ---
                    try:
                        all_techs = ", ".join(tech_map.keys()) or "N/A"
                        all_machines = ", ".join(
                            set(i["machine"] for ivs in tech_map.values() for i in ivs if i.get("machine"))
                        ) or "N/A"
                        all_inter_ids = ", ".join(
                            f"#{i['intervention_id']}"
                            for ivs in tech_map.values() for i in ivs
                            if i.get("intervention_id")
                        ) or "N/A"
                        msg_tg = (
                            f"🟢 <b>PIÈCE DISPONIBLE</b>\n\n"
                            f"🔩 Pièce : <b>{nom_piece}</b>\n"
                            f"🏷 Référence : <b>{reference}</b>\n"
                            f"📦 Stock actuel : <b>{nouveau_stock}</b>\n\n"
                            f"🔗 Intervention(s) concernée(s) : {all_inter_ids}\n"
                            f"🏥 Équipement(s) : {all_machines}\n"
                            f"👷 Technicien(s) : {all_techs}\n"
                            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                        )
                        _send_telegram(msg_tg)
                        logger.info(f"Telegram pièce disponible envoyé: {reference}")
                    except Exception as tg_err:
                        logger.error(f"Telegram pièce dispo erreur: {tg_err}")

                    # Marquer les notifications rupture comme traitées
                    for _, n in df_notifs.iterrows():
                        try:
                            marquer_notification_traitee(int(n["id"]))
                        except Exception:
                            pass
        except Exception as ne:
            logger.error(f"Erreur notif réappro pièce {piece_id}: {ne}")

    # Vérifier aussi les pièces demandées manuellement (non référencées)
    if nouveau_stock is not None and reference:
        try:
            if int(nouveau_stock) > 0:
                _check_pieces_demandees_disponibles(reference, nom_piece, int(nouveau_stock))
        except Exception as e:
            logger.error(f"Erreur check pièces demandées (PUT): {e}")

    return {"ok": True}


@app.delete("/api/pieces/{piece_id}")
def delete_piece(piece_id: int, user: dict = Depends(_verify_token)):
    if not _check_create_piece_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Gestionnaires de stock, Responsables, Managers et Admins")
    # Get piece info before deleting
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT reference, designation FROM pieces_rechange WHERE id = %s",
                (piece_id,)
            ).fetchone()
            piece_info = dict(row) if row else {"reference": "Unknown", "designation": "Unknown"}
    except:
        piece_info = {"reference": "Unknown", "designation": "Unknown"}
    
    supprimer_piece(piece_id)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "piece_id": piece_id,
        "reference": piece_info.get("reference", ""),
        "designation": piece_info.get("designation", ""),
    }, ensure_ascii=False)
    log_audit(username, "DELETE_PIECE", details, "pieces")
    
    return {"ok": True}


@app.post("/api/pieces/recalculate-parameters")
def recalculate_piece_parameters(user: dict = Depends(_verify_token)):
    if not _check_create_piece_permission(user):
        raise HTTPException(status_code=403, detail="Votre rôle n'autorise pas cette action sur le stock")
    """
    Recalculate and update all piece parameters from historical data.
    This triggers the automatic calculation of:
    - consommation_moyenne_mois
    - nombre_equipements_relies  
    - utilisation_recente_30j
    - data_confidence level
    
    Used for testing or manual refresh.
    """
    try:
        result = update_piece_parameters_batch()
        
        if result.get('success'):
            logger.info(f"Piece parameters updated: {result['updated']} pieces updated, {result['failed']} failed")
            
            # Log audit
            username = user.get("sub", "unknown")
            log_audit(username, "RECALCULATE_PIECE_PARAMETERS", 
                     f"Updated {result['updated']} pieces", "pieces")
            
            return {
                'success': True,
                'message': 'Parametres recalcules avec succes',
                'updated': result['updated'],
                'failed': result['failed'],
                'total': result['total']
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"Erreur recalculate_piece_parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pieces/{piece_id}/parameters")
def get_piece_parameters(piece_id: int, user: dict = Depends(_verify_token)):
    require_roles(user, *STOCK_READ_ROLES)
    """
    Get calculated parameters for a specific piece with confidence level.
    Shows:
    - consommation_moyenne_mois
    - data_confidence level
    - Reasoning for prediction reliability
    """
    try:
        with get_db() as conn:
            piece = conn.execute("""
                SELECT reference, designation, equipement_type,
                       consommation_moyenne_mois, delai_fournisseur_jours, criticite,
                       nombre_equipements_relies, utilisation_recente_30j
                FROM pieces_rechange WHERE id = %s
            """, (piece_id,)).fetchone()
            
            if not piece:
                raise HTTPException(status_code=404, detail="Piece not found")
            
            # Recalculate to get current confidence level
            params = calculate_piece_parameters(
                piece['reference'],
                piece['equipement_type']
            )
            
            return {
                'piece_id': piece_id,
                'reference': piece['reference'],
                'designation': piece['designation'],
                'consommation_moyenne_mois': piece['consommation_moyenne_mois'],
                'data_confidence': params['data_confidence'],
                'utilisation_recente_30j': piece['utilisation_recente_30j'],
                'nombre_equipements_relies': piece['nombre_equipements_relies'],
                'details': params['details']
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur get_piece_parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# CONTRATS
# ==========================================

__all__ = [
    "get_pieces",
    "get_pieces_a_commander",
    "predict_piece_order_date",
    "create_spare_part_prediction_feedback",
    "list_spare_part_prediction_feedback",
    "_normalize_ref",
    "_refs_match",
    "_check_pieces_demandees_disponibles",
    "get_pieces_demandees",
    "resolve_piece_demandee",
    "create_piece",
    "update_piece",
    "delete_piece",
    "recalculate_piece_parameters",
    "get_piece_parameters",
]
