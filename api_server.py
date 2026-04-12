# ==========================================
# 🌐 API REST — Serveur Flask pour PWA Terrain
# ==========================================
"""
Expose la base SQLite via des endpoints REST.
Authentification JWT. Sert aussi les fichiers de la PWA.
"""
import os
import json
import jwt
import bcrypt
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from db_engine import (
    init_db, get_db,
    lire_interventions, ajouter_intervention, update_intervention_statut,
    cloturer_intervention,
    lire_equipements, lire_techniciens, lire_pieces,
    lire_demandes_intervention,
    ajouter_notification_piece, lire_notifications_pieces,
    compter_notifications_non_lues, marquer_notification_lue,
    marquer_notification_traitee,
)

def _is_cloture(statut):
    """Vérifie si un statut représente une clôture."""
    return 'tur' in str(statut).lower()

def _send_telegram_cloture(intervention_id, machine, technicien, probleme, solution, client="", date_str=""):
    """Envoie une notification Telegram de clôture (best-effort)."""
    try:
        from notifications import get_notifier
        notifier = get_notifier()
        if notifier.telegram_ok:
            if not date_str:
                date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
            msg = (
                f"✅ *Intervention Clôturée (SIC Terrain)*\n\n"
                f"🏥 Machine : *{machine}*\n"
            )
            if client:
                msg += f"🏢 Client : {client}\n"
            msg += (
                f"📅 Date : {date_str}\n"
                f"👨‍🔧 Technicien : {technicien}\n"
            )
            if probleme and probleme != "RAS":
                msg += f"🔴 Problème : {str(probleme)[:100]}\n"
            if solution:
                msg += f"💡 Solution : {str(solution)[:100]}\n"
            notifier.envoyer_telegram(msg)
            logger.info(f"Telegram cloture envoyé pour intervention #{intervention_id}")
        else:
            logger.warning(f"Telegram NON configuré: token={'OUI' if notifier.telegram_token else 'NON'}, chat_id={'OUI' if notifier.telegram_chat_id else 'NON'}")
    except Exception as e:
        logger.warning(f"Telegram notification échouée: {e}")

def _sync_to_pg(intervention_id, data, pieces_a_deduire=None, new_statut=None):
    """Synchronise le statut, le stock et la demande liée vers PostgreSQL (SIC Radiologie)."""
    try:
        db_url = os.environ.get("PG_SYNC_URL", "")
        if not db_url:
            logger.info("[PG Sync] PG_SYNC_URL non défini — sync ignoré")
            return
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        machine = data.get("machine", "")
        technicien = data.get("technicien", "")
        statut = new_statut or data.get("statut", "")

        # 1. Mettre à jour le statut de l'intervention dans PostgreSQL
        if _is_cloture(statut):
            cur.execute(
                """UPDATE interventions SET statut = %s, probleme = %s, cause = %s,
                   solution = %s, duree_minutes = %s, date_cloture = NOW()
                   WHERE machine = %s AND technicien = %s AND statut NOT LIKE '%%lotur%%'""",
                (
                    "Cloturee",
                    data.get("probleme", ""),
                    data.get("cause", ""),
                    data.get("solution", ""),
                    data.get("duree_minutes", 0),
                    machine, technicien,
                )
            )
            logger.info(f"[PG Sync] Intervention clôturée: {machine} / {technicien}")
        elif statut:
            cur.execute(
                """UPDATE interventions SET statut = %s
                   WHERE machine = %s AND technicien = %s
                   AND statut NOT LIKE '%%lotur%%'""",
                (statut, machine, technicien)
            )
            logger.info(f"[PG Sync] Statut mis à jour: {machine} → {statut}")

        # 2. Déduire le stock des pièces utilisées (clôture uniquement)
        if pieces_a_deduire and _is_cloture(statut):
            for piece in pieces_a_deduire:
                ref = piece.get("ref", "")
                qty = piece.get("qty", 1)
                if ref:
                    cur.execute(
                        "UPDATE pieces_rechange SET stock_actuel = GREATEST(stock_actuel - %s, 0) WHERE reference = %s",
                        (qty, ref)
                    )
                    logger.info(f"[PG Sync] Stock déduit: {ref} x{qty}")

        # 3. Mettre à jour la demande liée (si Demande #X dans les notes)
        notes = data.get("notes", "")
        if notes:
            import re
            demande_match = re.search(r'Demande #(\d+)', notes)
            if demande_match:
                demande_id = int(demande_match.group(1))
                if _is_cloture(statut):
                    demande_statut = "Clôturée"
                elif statut == "En cours":
                    demande_statut = "En cours"
                elif statut == "Assignee":
                    demande_statut = "Planifiée"
                else:
                    demande_statut = None
                if demande_statut:
                    cur.execute(
                        "UPDATE demandes_intervention SET statut = %s, date_traitement = NOW() WHERE id = %s",
                        (demande_statut, demande_id)
                    )
                    logger.info(f"[PG Sync] Demande #{demande_id} → {demande_statut}")

        conn.commit()
        conn.close()
        logger.info(f"[PG Sync] Sync terminé pour intervention #{intervention_id}")
    except Exception as e:
        logger.warning(f"[PG Sync] Échec: {e}")



# Inline verify_password pour éviter d'importer auth.py (qui dépend de streamlit)
def verify_password(password: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash bcrypt."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

logger = logging.getLogger(__name__)

# ---- Config ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PWA_DIR = os.path.join(BASE_DIR, "pwa-terrain")
JWT_SECRET = os.getenv("JWT_SECRET", "sic-terrain-secret-2026")
JWT_EXPIRY_HOURS = 72  # Token valide 3 jours (terrain)

app = Flask(__name__, static_folder=None)
CORS(app)

init_db()

# Créer le compte admin par défaut si la base est vide (remplace auth.creer_admin_defaut)
def _creer_admin_defaut():
    with get_db() as conn:
        count_row = conn.execute("SELECT COUNT(*) as cnt FROM utilisateurs").fetchone()
        count = count_row["cnt"]
        if count == 0:
            hashed = bcrypt.hashpw("admin".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            conn.execute(
                "INSERT OR IGNORE INTO utilisateurs (username, password_hash, nom_complet, role, actif) VALUES (?, ?, ?, ?, ?)",
                ("admin", hashed, "Administrateur", "Admin", 1)
            )

_creer_admin_defaut()


# ==========================================
# AUTH — JWT helpers
# ==========================================

def create_token(user_data):
    """Génère un JWT pour un utilisateur authentifié."""
    payload = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "nom": user_data.get("nom_complet", ""),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def token_required(f):
    """Décorateur : vérifie le JWT dans le header Authorization."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        if not token:
            return jsonify({"error": "Token manquant"}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user = data
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expiré"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token invalide"}), 401
        return f(*args, **kwargs)
    return decorated


# ==========================================
# PWA — Servir les fichiers statiques
# ==========================================

@app.route("/")
def serve_pwa_index():
    return send_from_directory(PWA_DIR, "index.html")


@app.route("/<path:path>")
def serve_pwa_static(path):
    """Sert les fichiers PWA, fallback sur index.html pour le SPA routing."""
    file_path = os.path.join(PWA_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(PWA_DIR, path)
    return send_from_directory(PWA_DIR, "index.html")


# ==========================================
# API — Authentification
# ==========================================

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """Authentifie un technicien et retourne un JWT."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Identifiants requis"}), 400

    # Vérifier dans la base
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM utilisateurs WHERE username = ? AND actif = 1",
            (username,)
        ).fetchone()

    if not row or not verify_password(password, row["password_hash"]):
        return jsonify({"error": "Identifiants incorrects"}), 401

    user_data = dict(row)
    token = create_token(user_data)

    return jsonify({
        "token": token,
        "user": {
            "username": user_data["username"],
            "nom": user_data.get("nom_complet", ""),
            "role": user_data["role"],
        }
    })


@app.route("/api/auth/me", methods=["GET"])
@token_required
def api_me():
    """Retourne les infos de l'utilisateur connecté."""
    return jsonify({"user": request.user})


# ==========================================
# API — Interventions
# ==========================================

@app.route("/api/interventions", methods=["GET"])
@token_required
def api_list_interventions():
    """Liste les interventions (filtrable par machine et technicien)."""
    try:
        machine = request.args.get("machine")
        technicien = request.args.get("technicien")
        df = lire_interventions(machine=machine)
        if df.empty:
            return jsonify([])
        # Filtrer par technicien si demandé (match flexible : tous les mots doivent être présents)
        if technicien and not df.empty and "technicien" in df.columns:
            tech_words = technicien.lower().split()
            df = df[df["technicien"].astype(str).apply(
                lambda t: all(w in t.lower() for w in tech_words)
            )]
        records = df.to_dict(orient="records")
        # Convertir les valeurs NaN en None pour JSON
        for r in records:
            for k, v in r.items():
                if isinstance(v, float) and (v != v):  # NaN check
                    r[k] = None
                elif hasattr(v, 'isoformat'):  # datetime/date objects
                    r[k] = v.isoformat()
        return jsonify(records)
    except Exception as e:
        logger.error(f"Erreur GET /api/interventions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/interventions", methods=["POST"])
@token_required
def api_create_intervention():
    """Crée une nouvelle intervention."""
    data = request.get_json(silent=True) or {}
    required = ["machine", "type_intervention"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Champ '{field}' requis"}), 400

    intervention = {
        "machine": data["machine"],
        "technicien": data.get("technicien", request.user.get("nom", "")),
        "type_intervention": data["type_intervention"],
        "description": data.get("description", ""),
        "probleme": data.get("probleme", ""),
        "cause": data.get("cause", ""),
        "solution": data.get("solution", ""),
        "pieces_utilisees": data.get("pieces_utilisees", ""),
        "cout": data.get("cout", 0.0),
        "duree_minutes": data.get("duree_minutes", 0),
        "code_erreur": data.get("code_erreur", ""),
        "statut": data.get("statut", "En cours"),
        "notes": data.get("notes", ""),
        "type_erreur": data.get("type_erreur", ""),
        "priorite": data.get("priorite", ""),
    }
    ajouter_intervention(intervention)

    # Envoyer notification Telegram
    try:
        from notifications import get_notifier
        notifier = get_notifier()
        if notifier.telegram_ok:
            machine = intervention["machine"]
            type_interv = intervention["type_intervention"]
            technicien = intervention.get("technicien", "")
            description = intervention.get("description", "")[:200]
            code_err = intervention.get("code_erreur", "")
            notes = intervention.get("notes", "")

            # Résoudre le client : champ direct > notes > table équipements
            client = data.get("client", "")
            if not client and notes and "[" in notes:
                import re
                m = re.search(r'\[(.+?)\]', notes)
                if m:
                    client = m.group(1)
            if not client:
                try:
                    from db_engine import lire_equipements
                    df_eq = lire_equipements()
                    if not df_eq.empty:
                        match = df_eq[df_eq["Nom"] == machine]
                        if not match.empty:
                            client = str(match.iloc[0].get("Client", ""))
                except Exception:
                    pass

            msg = (
                f"📋 *Nouvelle Intervention (SIC Terrain)*\n\n"
                f"🏥 Machine : *{machine}*\n"
            )
            if client:
                msg += f"🏢 Client : {client}\n"
            msg += f"📅 Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            msg += (
                f"🔧 Type : {type_interv}\n"
                f"👨‍🔧 Technicien : {technicien}\n"
            )
            if code_err:
                msg += f"🔴 Code erreur : `{code_err}`\n"
            if description:
                msg += f"📝 Description : {description}\n"
            notifier.envoyer_telegram(msg)
    except Exception as e:
        print(f"[WARN] Notification Telegram échouée: {e}")

    return jsonify({"ok": True, "message": "Intervention créée"}), 201


@app.route("/api/interventions/<int:intervention_id>", methods=["PUT"])
@token_required
def api_update_intervention(intervention_id):
    """Met à jour une intervention (statut, clôture, etc.)."""
    data = request.get_json(silent=True) or {}
    new_statut = data.get("statut")

    # --- Validation serveur: obliger mise à jour statut + heures ---
    # Lire le statut actuel de l'intervention
    with get_db() as conn:
        current = conn.execute(
            "SELECT statut, duree_minutes FROM interventions WHERE id = ?",
            (intervention_id,)
        ).fetchone()
    if current:
        errors = []
        # 1. Les heures de travail doivent être > 0
        duree = data.get("duree_minutes", 0)
        try:
            duree = int(duree)
        except (ValueError, TypeError):
            duree = 0
        if duree <= 0:
            errors.append("Veuillez remplir le nombre d'heures de travail")
        # 2. Le statut doit être modifié (comparaison normalisée)
        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFKD", (s or "").strip().lower()).encode("ascii", "ignore").decode()
        old_statut = current["statut"] or "En cours"
        logger.info(f"[VALIDATION] interv#{intervention_id}: old_statut='{old_statut}' new_statut='{new_statut}' norm_old='{_norm(old_statut)}' norm_new='{_norm(new_statut)}'")
        # Rejeter si pas de nouveau statut OU si identique
        if not new_statut or _norm(new_statut) == _norm(old_statut):
            errors.append("Veuillez mettre à jour le statut avant d'enregistrer")
        if errors:
            return jsonify({"ok": False, "error": " | ".join(errors)}), 400

    # Si clôture → utiliser cloturer_intervention (gère stock + connaissances)
    if new_statut and _is_cloture(new_statut):
        ok, msg = cloturer_intervention(
            intervention_id,
            data.get("probleme", "RAS"),
            data.get("cause", "N/A"),
            data.get("solution", "Clôturé depuis SIC Terrain"),
            pieces_a_deduire=data.get("pieces_a_deduire", []),
            duree_minutes=data.get("duree_minutes", 0),
        )
        if ok:
            # Sauvegarder type_erreur et priorite (non gérés par cloturer_intervention)
            extra_fields = []
            extra_params = []
            for f in ["type_erreur", "priorite"]:
                if data.get(f):
                    extra_fields.append(f"{f} = ?")
                    extra_params.append(data[f])
            if extra_fields:
                extra_params.append(intervention_id)
                with get_db() as conn:
                    conn.execute(
                        f"UPDATE interventions SET {', '.join(extra_fields)} WHERE id = ?",
                        extra_params
                    )
            # Résoudre le client pour la notif
            cloture_client = data.get("client", "")
            if not cloture_client:
                notes = data.get("notes", "")
                if notes and "[" in notes:
                    import re
                    m = re.search(r'\[(.+?)\]', notes)
                    if m:
                        cloture_client = m.group(1)
            _send_telegram_cloture(
                intervention_id,
                data.get("machine", "?"),
                data.get("technicien", request.user.get("nom", "")),
                data.get("probleme", ""),
                data.get("solution", ""),
                client=cloture_client,
            )
            # Sync stock + statut + demande vers PostgreSQL (SIC Radiologie)
            _sync_to_pg(
                intervention_id, data,
                pieces_a_deduire=data.get("pieces_a_deduire", []),
                new_statut="Cloturee",
            )
            # Remettre l'équipement en Opérationnel si plus aucune En cours
            try:
                machine_name = data.get("machine", "")
                if machine_name:
                    with get_db() as conn:
                        remaining = conn.execute(
                            "SELECT COUNT(*) as cnt FROM interventions WHERE machine = ? AND statut = 'En cours'",
                            (machine_name,)
                        ).fetchone()
                        if remaining and remaining["cnt"] == 0:
                            conn.execute("UPDATE equipements SET statut = ? WHERE nom = ?", ("Opérationnel", machine_name))
                    logger.info(f"Équipement '{machine_name}' → Opérationnel (si plus d'En cours)")
            except Exception as eq_err:
                logger.warning(f"Mise à jour statut équipement échouée: {eq_err}")
        return jsonify({"ok": ok, "message": msg})

    if new_statut:
        update_intervention_statut(intervention_id, new_statut)
        # Sync statut + demande vers PostgreSQL (SIC Radiologie)
        _sync_to_pg(intervention_id, data, new_statut=new_statut)

        # === NOTIFICATION RUPTURE DE STOCK ===
        # Si statut = "En attente de piece", vérifier les pièces sélectionnées
        if "attente" in new_statut.lower() and "piece" in new_statut.lower():
            pieces_str = data.get("pieces_utilisees", "")
            if pieces_str:
                pieces_names = [p.strip() for p in pieces_str.replace(";", ",").split(",") if p.strip()]
                # Vérifier le stock de chaque pièce
                df_pieces = lire_pieces()
                if not df_pieces.empty:
                    # Résoudre le client
                    notif_client = data.get("client", "")
                    if not notif_client:
                        notes = data.get("notes", "")
                        if notes and "[" in notes:
                            import re
                            m = re.search(r'\[(.+?)\]', notes)
                            if m:
                                notif_client = m.group(1)
                    for piece_name in pieces_names:
                        # Chercher la pièce par désignation ou référence
                        match = df_pieces[
                            (df_pieces["designation"].str.lower() == piece_name.lower()) |
                            (df_pieces["reference"].str.lower() == piece_name.lower())
                        ]
                        if not match.empty:
                            row = match.iloc[0]
                            stock = int(row.get("stock_actuel", 0) or 0)
                            if stock == 0:
                                ref = row.get("reference", "")
                                desig = row.get("designation", piece_name)
                                machine = data.get("machine", "?")
                                technicien = data.get("technicien", request.user.get("nom", ""))
                                msg_notif = (
                                    f"🔴 Pièce '{desig}' ({ref}) en RUPTURE DE STOCK. "
                                    f"Intervention sur {machine} pour {notif_client} bloquée. "
                                    f"Technicien: {technicien}"
                                )
                                # Insérer la notification en base
                                ajouter_notification_piece({
                                    "type": "piece_rupture",
                                    "intervention_id": intervention_id,
                                    "piece_reference": ref,
                                    "piece_nom": desig,
                                    "intervention_ref": f"INT-{intervention_id}",
                                    "equipement": machine,
                                    "client": notif_client,
                                    "technicien": technicien,
                                    "message": msg_notif,
                                    "source": "terrain",
                                    "destination": "radiologie",
                                })
                                # Envoyer Telegram
                                try:
                                    from notifications import get_notifier
                                    notifier = get_notifier()
                                    if notifier.telegram_ok:
                                        tg_msg = (
                                            f"🚨 *RUPTURE DE STOCK (SIC Terrain)*\n\n"
                                            f"📦 Pièce : *{desig}* ({ref})\n"
                                            f"🏥 Machine : *{machine}*\n"
                                        )
                                        if notif_client:
                                            tg_msg += f"🏢 Client : {notif_client}\n"
                                        tg_msg += (
                                            f"👨‍🔧 Technicien : {technicien}\n"
                                            f"📊 Statut : En attente de pièce\n"
                                            f"⚠️ Stock actuel : *0*\n\n"
                                            f"👉 Réapprovisionner sur *SIC Radiologie*"
                                        )
                                        notifier.envoyer_telegram(tg_msg)
                                except Exception as e:
                                    logger.warning(f"Telegram rupture stock échoué: {e}")
                                logger.info(f"[NOTIF] Rupture stock: {desig} ({ref}) pour intervention #{intervention_id}")

    # Mise à jour des champs détaillés
    fields_to_update = []
    params = []
    for field in ["probleme", "cause", "solution", "pieces_utilisees",
                   "cout", "duree_minutes", "description", "notes", "type_erreur", "priorite", "validation_client"]:
        if field in data:
            fields_to_update.append(f"{field} = ?")
            params.append(data[field])

    if fields_to_update:
        params.append(intervention_id)
        with get_db() as conn:
            conn.execute(
                f"UPDATE interventions SET {', '.join(fields_to_update)} WHERE id = ?",
                params
            )

    # Notification Telegram pour modification (non-clôture)
    if not _is_cloture(new_statut or ""):
        try:
            from notifications import get_notifier
            notifier = get_notifier()
            if notifier.telegram_ok:
                mod_client = data.get("client", "")
                if not mod_client:
                    notes = data.get("notes", "")
                    if notes and "[" in notes:
                        import re
                        m = re.search(r'\[(.+?)\]', notes)
                        if m:
                            mod_client = m.group(1)
                mod_msg = (
                    f"✏️ *Intervention Modifiée (SIC Terrain)*\n\n"
                    f"🏥 Machine : *{data.get('machine', '?')}*\n"
                )
                if mod_client:
                    mod_msg += f"🏢 Client : {mod_client}\n"
                mod_msg += f"📅 Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                mod_msg += f"👨‍🔧 Technicien : {data.get('technicien', request.user.get('nom', ''))}\n"
                if new_statut:
                    mod_msg += f"📊 Statut : {new_statut}\n"
                notifier.envoyer_telegram(mod_msg)
        except Exception as e:
            print(f"[WARN] Notification Telegram modification échouée: {e}")

    return jsonify({"ok": True, "message": "Intervention mise à jour"})


@app.route("/api/interventions/<int:intervention_id>/photo", methods=["POST"])
@token_required
def api_upload_intervention_photo(intervention_id):
    """Upload une photo de fiche d'intervention signée."""
    if 'photo' not in request.files:
        return jsonify({"ok": False, "error": "Aucun fichier photo"}), 400
    
    photo = request.files['photo']
    if photo.filename == '':
        return jsonify({"ok": False, "error": "Fichier vide"}), 400
    
    # Créer le dossier photos si nécessaire
    photos_dir = os.path.join(os.path.dirname(__file__), 'photos')
    os.makedirs(photos_dir, exist_ok=True)
    
    # Nom de fichier : intervention_ID_timestamp.ext
    import uuid
    ext = os.path.splitext(photo.filename)[1] or '.jpg'
    filename = f"intervention_{intervention_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
    filepath = os.path.join(photos_dir, filename)
    photo.save(filepath)
    
    # Sauvegarder le chemin en base
    with get_db() as conn:
        # Vérifier si la colonne photo_fiche existe, sinon l'ajouter
        try:
            conn.execute("SELECT photo_fiche FROM interventions LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE interventions ADD COLUMN photo_fiche TEXT DEFAULT ''")
        conn.execute(
            "UPDATE interventions SET photo_fiche = ? WHERE id = ?",
            (filename, intervention_id)
        )
    
    logger.info(f"[PHOTO] Photo uploadée pour intervention #{intervention_id}: {filename}")
    return jsonify({"ok": True, "message": "Photo enregistrée", "filename": filename})


@app.route("/api/interventions/<int:intervention_id>/photo", methods=["GET"])
@token_required
def api_get_intervention_photo(intervention_id):
    """Récupère la photo d'une fiche d'intervention."""
    with get_db() as conn:
        try:
            row = conn.execute(
                "SELECT photo_fiche FROM interventions WHERE id = ?",
                (intervention_id,)
            ).fetchone()
        except Exception:
            return jsonify({"ok": False, "error": "Pas de photo"}), 404
    
    if not row or not row["photo_fiche"]:
        return jsonify({"ok": False, "error": "Pas de photo"}), 404
    
    photos_dir = os.path.join(os.path.dirname(__file__), 'photos')
    return send_from_directory(photos_dir, row["photo_fiche"])


# ==========================================
# API — Équipements
# ==========================================

@app.route("/api/equipements", methods=["GET"])
@token_required
def api_list_equipements():
    """Liste tous les équipements."""
    df = lire_equipements()
    if df.empty:
        return jsonify([])
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and (v != v):
                r[k] = None
    return jsonify(records)


# ==========================================
# API — Techniciens
# ==========================================

@app.route("/api/techniciens", methods=["GET"])
@token_required
def api_list_techniciens():
    """Liste tous les techniciens (table techniciens + utilisateurs avec rôle Technicien/Admin)."""
    # Source 1: table techniciens
    df = lire_techniciens()
    records = []
    seen_names = set()

    if not df.empty:
        for r in df.to_dict(orient="records"):
            for k, v in r.items():
                if isinstance(v, float) and (v != v):
                    r[k] = None
            name_key = f"{(r.get('prenom') or '')} {(r.get('nom') or '')}".strip().lower()
            if name_key and name_key not in seen_names:
                seen_names.add(name_key)
                records.append(r)

    # Source 2: table utilisateurs (rôle Technicien ou Admin)
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT username, nom_complet, role FROM utilisateurs WHERE actif = 1 AND role IN ('Technicien', 'Admin')"
            ).fetchall()
            for row in rows:
                nom_complet = row["nom_complet"] or row["username"]
                name_key = nom_complet.strip().lower()
                if name_key and name_key not in seen_names:
                    seen_names.add(name_key)
                    # Split nom_complet into prenom/nom for PWA compatibility
                    parts = nom_complet.strip().split(" ", 1)
                    prenom = parts[0] if parts else ""
                    nom = parts[1] if len(parts) > 1 else ""
                    records.append({
                        "id": None,
                        "nom": nom,
                        "prenom": prenom,
                        "specialite": "",
                        "qualification": "",
                        "telephone": "",
                        "email": "",
                        "username": row["username"],
                    })
    except Exception:
        pass

    return jsonify(records)


# ==========================================
# API — Pièces de rechange
# ==========================================

@app.route("/api/pieces", methods=["GET"])
@token_required
def api_list_pieces():
    """Liste les pièces de rechange."""
    df = lire_pieces()
    if df.empty:
        return jsonify([])
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and (v != v):
                r[k] = None
    return jsonify(records)

@app.route("/api/pieces/<int:piece_id>", methods=["PUT"])
@token_required
def api_update_piece(piece_id):
    """Met à jour le stock d'une pièce."""
    data = request.get_json(silent=True) or {}
    fields = []
    params = []
    for field in ["stock_actuel", "stock_minimum", "prix_unitaire", "designation",
                   "reference", "fournisseur", "equipement_type", "notes"]:
        if field in data:
            fields.append(f"{field} = ?")
            params.append(data[field])
    if not fields:
        return jsonify({"ok": False, "message": "Aucun champ à mettre à jour"}), 400
    params.append(piece_id)
    with get_db() as conn:
        conn.execute(f"UPDATE pieces_rechange SET {', '.join(fields)} WHERE id = ?", params)
    return jsonify({"ok": True, "message": "Pièce mise à jour"})


# ==========================================
# API — Demandes d'intervention
# ==========================================

@app.route("/api/demandes", methods=["GET"])
@token_required
def api_list_demandes():
    """Liste les demandes d'intervention (Acceptées et Planifiées par défaut)."""
    try:
        statuts = request.args.get("statuts", "Acceptée,Planifiée,Nouvelle")
        statuts_list = [s.strip() for s in statuts.split(",") if s.strip()]
        df = lire_demandes_intervention()
        if df.empty:
            return jsonify([])
        # Filtrer par statuts demandés
        if statuts_list:
            df = df[df["statut"].isin(statuts_list)]
        records = df.to_dict(orient="records")
        for r in records:
            for k, v in r.items():
                if isinstance(v, float) and (v != v):
                    r[k] = None
                elif hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
        return jsonify(records)
    except Exception as e:
        logger.error(f"Erreur GET /api/demandes: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ==========================================
# API — Gestion des utilisateurs (sync)
# ==========================================

@app.route("/api/admin/users", methods=["POST"])
def api_create_user():
    """Crée ou met à jour un utilisateur (pour sync depuis SIC Radiologie)."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    nom_complet = data.get("nom_complet", "").strip()
    role = data.get("role", "Technicien")
    email = data.get("email", "")
    client = data.get("client", "")

    if not username or not password:
        return jsonify({"error": "username et password requis"}), 400

    try:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        with get_db() as conn:
            # UPSERT : créer ou mettre à jour
            existing = conn.execute(
                "SELECT id FROM utilisateurs WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE utilisateurs
                    SET password_hash = ?, nom_complet = ?, role = ?, email = ?, client = ?, actif = 1
                    WHERE username = ?
                """, (hashed, nom_complet, role, email, client, username))
                return jsonify({"ok": True, "message": f"Utilisateur '{username}' mis à jour"})
            else:
                conn.execute("""
                    INSERT INTO utilisateurs (username, password_hash, nom_complet, role, email, client, actif)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (username, hashed, nom_complet, role, email, client))
                return jsonify({"ok": True, "message": f"Utilisateur '{username}' créé"}), 201
    except Exception as e:
        logger.error(f"Erreur création utilisateur: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ==========================================
# API — Sync offline
# ==========================================

@app.route("/api/sync", methods=["POST"])
@token_required
def api_sync():
    """Reçoit un batch d'opérations offline et les applique."""
    data = request.get_json(silent=True) or {}
    operations = data.get("operations", [])
    results = []

    for op in operations:
        op_type = op.get("type")
        payload = op.get("data", {})
        try:
            if op_type == "create_intervention":
                intervention = {
                    "machine": payload.get("machine", ""),
                    "technicien": payload.get("technicien", ""),
                    "type_intervention": payload.get("type_intervention", "Corrective"),
                    "description": payload.get("description", ""),
                    "probleme": payload.get("probleme", ""),
                    "cause": payload.get("cause", ""),
                    "solution": payload.get("solution", ""),
                    "pieces_utilisees": payload.get("pieces_utilisees", ""),
                    "cout": payload.get("cout", 0.0),
                    "duree_minutes": payload.get("duree_minutes", 0),
                    "code_erreur": payload.get("code_erreur", ""),
                    "statut": payload.get("statut", "En cours"),
                    "notes": payload.get("notes", ""),
                    "date": payload.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    "type_erreur": payload.get("type_erreur", ""),
                    "priorite": payload.get("priorite", ""),
                }
                ajouter_intervention(intervention)
                results.append({"op_id": op.get("id"), "ok": True})

            elif op_type == "update_intervention":
                interv_id = payload.get("intervention_id")
                if interv_id:
                    statut = payload.get("statut", "")
                    # Si clôture → utiliser cloturer_intervention
                    if _is_cloture(statut):
                        ok, msg = cloturer_intervention(
                            interv_id,
                            payload.get("probleme", "RAS"),
                            payload.get("cause", "N/A"),
                            payload.get("solution", "Clôturé depuis SIC Terrain"),
                            pieces_a_deduire=payload.get("pieces_a_deduire", []),
                            duree_minutes=payload.get("duree_minutes", 0),
                        )
                        tg_sent = False
                        if ok:
                            # Sauvegarder type_erreur et priorite (non gérés par cloturer_intervention)
                            sync_extra_fields = []
                            sync_extra_params = []
                            for f in ["type_erreur", "priorite"]:
                                if payload.get(f):
                                    sync_extra_fields.append(f"{f} = ?")
                                    sync_extra_params.append(payload[f])
                            if sync_extra_fields:
                                sync_extra_params.append(interv_id)
                                with get_db() as conn:
                                    conn.execute(
                                        f"UPDATE interventions SET {', '.join(sync_extra_fields)} WHERE id = ?",
                                        sync_extra_params
                                    )
                            # Résoudre le client
                            sync_client = payload.get("client", "")
                            if not sync_client:
                                notes = payload.get("notes", "")
                                if notes and "[" in notes:
                                    import re
                                    m = re.search(r'\[(.+?)\]', notes)
                                    if m:
                                        sync_client = m.group(1)
                            _send_telegram_cloture(
                                interv_id,
                                payload.get("machine", "?"),
                                payload.get("technicien", ""),
                                payload.get("probleme", ""),
                                payload.get("solution", ""),
                                client=sync_client,
                            )
                            tg_sent = True
                        # Remettre l'équipement en Opérationnel si plus aucune En cours
                        try:
                            machine_name = payload.get("machine", "")
                            if machine_name:
                                with get_db() as conn:
                                    remaining = conn.execute(
                                        "SELECT COUNT(*) as cnt FROM interventions WHERE machine = ? AND statut = 'En cours'",
                                        (machine_name,)
                                    ).fetchone()
                                    if remaining and remaining["cnt"] == 0:
                                        conn.execute("UPDATE equipements SET statut = ? WHERE nom = ?", ("Opérationnel", machine_name))
                                logger.info(f"Équipement '{machine_name}' → Opérationnel (sync)")
                        except Exception as eq_err:
                            logger.warning(f"Mise à jour statut équipement échouée (sync): {eq_err}")
                        results.append({
                            "op_id": op.get("id"), "ok": ok,
                            "cloture_ok": ok, "cloture_msg": msg,
                            "telegram_sent": tg_sent
                        })
                    else:
                        if statut:
                            update_intervention_statut(interv_id, statut)
                        # Update other fields
                        fields = []
                        params = []
                        for f in ["probleme", "cause", "solution", "pieces_utilisees",
                                  "cout", "duree_minutes", "description", "notes", "type_erreur", "priorite"]:
                            if f in payload:
                                fields.append(f"{f} = ?")
                                params.append(payload[f])
                        if fields:
                            params.append(interv_id)
                            with get_db() as conn:
                                conn.execute(
                                    f"UPDATE interventions SET {', '.join(fields)} WHERE id = ?",
                                    params
                                )
                        results.append({"op_id": op.get("id"), "ok": True})
                else:
                    results.append({"op_id": op.get("id"), "ok": False, "error": "ID manquant"})
            else:
                results.append({"op_id": op.get("id"), "ok": False, "error": f"Type inconnu: {op_type}"})
        except Exception as e:
            results.append({"op_id": op.get("id"), "ok": False, "error": str(e)})

    return jsonify({"results": results, "synced": len([r for r in results if r.get("ok")])}), 200


# ==========================================
# API — Admin: Nettoyage interventions
# ==========================================

@app.route("/api/admin/clear-interventions", methods=["DELETE"])
@token_required
def api_clear_interventions():
    """Supprime toutes les interventions (admin only)."""
    if request.user.get("role") != "Admin":
        return jsonify({"error": "Admin requis"}), 403
    with get_db() as conn:
        conn.execute("DELETE FROM interventions")
    return jsonify({"ok": True, "message": "Toutes les interventions supprimées"})


# ==========================================
# API — Import de données (migration)
# ==========================================

@app.route("/api/admin/import", methods=["POST"])
@token_required
def api_admin_import():
    """Importe des données en bulk (pour migration SQLite → PostgreSQL)."""
    if request.user.get("role") != "Admin":
        return jsonify({"error": "Admin requis"}), 403

    data = request.get_json(silent=True) or {}
    table = data.get("table", "")
    rows = data.get("rows", [])

    if not table or not rows:
        return jsonify({"error": "table et rows requis"}), 400

    allowed = ["equipements", "techniciens", "interventions", "historique",
               "codes_erreurs", "solutions", "planning_maintenance",
               "pieces_rechange", "config_client", "contrats", "conformite",
               "utilisateurs", "audit_log", "telemetry"]
    if table not in allowed:
        return jsonify({"error": f"Table '{table}' non autorisée"}), 400

    imported = 0
    with get_db() as conn:
        for row in rows:
            cols = list(row.keys())
            # Exclure 'id' pour laisser PostgreSQL générer les séquences
            if "id" in cols and table != "config_client":
                cols.remove("id")
            vals = [row.get(c) for c in cols]
            placeholders = ", ".join(["?"] * len(cols))
            cols_str = ", ".join(cols)
            try:
                conn.execute(
                    f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})",
                    vals
                )
                imported += 1
            except Exception:
                pass  # Ignorer les doublons

    return jsonify({"ok": True, "table": table, "imported": imported, "total": len(rows)})


# ==========================================
# DEBUG — Vérifier config Telegram (temporaire)
# ==========================================

@app.route("/api/debug/telegram", methods=["GET"])
def api_debug_telegram():
    """Vérifie la config Telegram (debug)."""
    try:
        from notifications import get_notifier
        n = get_notifier()
        return jsonify({
            "telegram_ok": n.telegram_ok,
            "token_set": bool(n.telegram_token),
            "token_preview": n.telegram_token[:8] + "..." if n.telegram_token else "VIDE",
            "chat_id": n.telegram_chat_id or "VIDE",
            "env_token": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "env_chat_id": bool(os.environ.get("TELEGRAM_CHAT_ID")),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/debug/telegram-test", methods=["GET"])
def api_debug_telegram_test():
    """Envoie un message Telegram de test."""
    try:
        from notifications import get_notifier
        n = get_notifier()
        if not n.telegram_ok:
            return jsonify({"ok": False, "reason": "telegram_ok=False"})
        result = n.envoyer_telegram("🔧 Test SIC Terrain — Si vous voyez ce message, les notifications fonctionnent !")
        return jsonify({"ok": result, "message": "Message envoyé" if result else "Échec envoi"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ==========================================
# API — Notifications pièces (cross-app)
# ==========================================

def _resolve_tech_name(user_data):
    """Résout le nom complet du technicien depuis le JWT ou la table techniciens."""
    nom = user_data.get("nom", "") if user_data else ""
    if nom and nom.strip():
        return nom.strip()
    # Fallback: chercher dans la table techniciens par username
    username = user_data.get("sub", "") if user_data else ""
    if username:
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT prenom, nom FROM techniciens WHERE LOWER(username) = LOWER(?)",
                    (username,)
                ).fetchone()
                if row:
                    return f"{row['prenom']} {row['nom']}".strip()
        except Exception:
            pass
    # Aucun nom trouvé — retourner un placeholder impossible à matcher
    return "__NO_MATCH__"


@app.route("/api/notifications", methods=["GET"])
@token_required
def api_list_notifications():
    """Liste les notifications pour une destination donnée, filtrées par technicien connecté."""
    destination = request.args.get("destination", "terrain")
    statut = request.args.get("statut")  # optionnel
    df = lire_notifications_pieces(destination=destination, statut=statut)
    if df.empty:
        return jsonify([])
    # Filtrer par technicien connecté (comparaison par ensemble de mots)
    tech_name = _resolve_tech_name(request.user if hasattr(request, "user") else None)
    if "technicien" in df.columns:
        tech_words = set(tech_name.lower().split())
        df = df[df["technicien"].apply(
            lambda t: set(str(t or "").lower().split()) == tech_words if t else False
        )]
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and (v != v):
                r[k] = None
            elif hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
    return jsonify(records)


@app.route("/api/notifications/count", methods=["GET"])
@token_required
def api_count_notifications():
    """Compte les notifications non lues pour une destination, filtrées par technicien."""
    destination = request.args.get("destination", "terrain")
    tech_name = _resolve_tech_name(request.user if hasattr(request, "user") else None)
    df = lire_notifications_pieces(destination=destination, statut="non_lu")
    if not df.empty and "technicien" in df.columns:
        tech_words = set(tech_name.lower().split())
        df = df[df["technicien"].apply(
            lambda t: set(str(t or "").lower().split()) == tech_words if t else False
        )]
    count = len(df)
    return jsonify({"count": count})


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
@token_required
def api_read_notification(notif_id):
    """Marque une notification comme lue."""
    marquer_notification_lue(notif_id)
    return jsonify({"ok": True, "message": "Notification marquée comme lue"})


@app.route("/api/notifications/<int:notif_id>/treat", methods=["POST"])
@token_required
def api_treat_notification(notif_id):
    """Marque une notification comme traitée."""
    marquer_notification_traitee(notif_id)
    return jsonify({"ok": True, "message": "Notification traitée"})


# ==========================================
# Lancement
# ==========================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    workers = int(os.environ.get("WORKERS", 4))
    use_gunicorn = os.environ.get("USE_GUNICORN", "auto")

    # Auto-détection : gunicorn sur Linux, Flask dev server sur Windows
    can_gunicorn = False
    if use_gunicorn != "false":
        try:
            import gunicorn  # noqa: F401
            can_gunicorn = True
        except ImportError:
            can_gunicorn = False

    if can_gunicorn and (use_gunicorn == "true" or (use_gunicorn == "auto" and not os.environ.get("FLASK_DEBUG"))):
        print(f"[API] 🚀 Production mode — Gunicorn {workers} workers sur port {port}")
        print(f"[PWA] Tablette Terrain -- http://localhost:{port}/")
        import subprocess
        subprocess.run([
            "gunicorn", "api_server:app",
            "-w", str(workers),
            "-b", f"0.0.0.0:{port}",
            "--timeout", "120",
            "--access-logfile", "-",
        ])
    else:
        print(f"[API] SIC Radiologie -- http://localhost:{port} (dev mode)")
        print(f"[PWA] Tablette Terrain -- http://localhost:{port}/")
        app.run(host="0.0.0.0", port=port, debug=True)
