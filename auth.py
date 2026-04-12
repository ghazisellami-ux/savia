# ==========================================
# 🔐 AUTHENTIFICATION & GESTION UTILISATEURS
# ==========================================
"""
Système d'authentification avec hash bcrypt et gestion des rôles.
Rôles : Admin, Manager, Responsable Technique, Gestionnaire de stock, Technicien, Lecteur
"""
import bcrypt
import logging
import streamlit as st
from db_engine import get_db, log_audit

logger = logging.getLogger("auth")


def hash_password(password: str) -> str:
    """Hash un mot de passe avec bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def creer_admin_defaut():
    """
    Initialise le compte administrateur racine si la base est vide.
    
    Logic:
        Vérifie le nombre d'utilisateurs. Si 0, insère 'admin/admin'
        dans la table utilisateurs et l'entrée correspondante dans user_pii.
    """
    try:
        with get_db() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM utilisateurs").fetchone()
            if row and row["cnt"] == 0:
                # Créer l'entrée auth
                res = conn.execute("""
                    INSERT INTO utilisateurs (username, password_hash, role, actif)
                    VALUES (?, ?, ?, ?)
                """, ("admin", hash_password("admin"), "Admin", 1))
                admin_id = res.lastrowid
                
                # Créer l'entrée PII (Pillier 2)
                conn.execute("""
                    INSERT INTO user_pii (user_id, nom_complet, email)
                    VALUES (?, ?, ?)
                """, (admin_id, "Administrateur Système", "admin@sic-radiologie.tn"))
                
                logger.info("Audit Trail: Compte Admin par défaut créé.")
                return True
    except Exception as e:
        logger.error(f"Erreur creer_admin_defaut: {e}")
    return False


def authentifier(username: str, password: str):
    """
    Vérifie les identifiants et retourne les données complètes (Auth + PII).
    
    Args:
        username (str): Identifiant technique.
        password (str): Mot de passe brut.
        
    Returns:
        dict: Profil utilisateur enrichi ou None si échec.
    """
    user_data = None
    try:
        with get_db() as conn:
            # Jointure entre AUTH et PII (Pillier 2 Isolation)
            row = conn.execute("""
                SELECT u.*, p.nom_complet, p.email, p.telephone
                FROM utilisateurs u
                LEFT JOIN user_pii p ON u.id = p.user_id
                WHERE u.username = ? AND u.actif = 1
            """, (username,)).fetchone()

            if row and verify_password(password, row["password_hash"]):
                conn.execute(
                    "UPDATE utilisateurs SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (row["id"],))
                user_data = dict(row)
                # Sécurité: Ne jamais faire circuler le hash du mot de passe en session
                if "password_hash" in user_data:
                    del user_data["password_hash"]

        if user_data:
            log_audit(username, "LOGIN", "Succès")
            return user_data

    except Exception as e:
        logger.error(f"Erreur critique lors de l'authentification {username}: {e}")

    if username:
        log_audit(username, "LOGIN_FAILED", f"Tentative échouée")
    return None


def authentifier_par_username(username: str):
    """Restaure un utilisateur par username (sans mot de passe).
    Utilisé uniquement pour la restauration de session à partir d'un token persisté."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM utilisateurs WHERE username = ? AND actif = 1",
            (username,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def deconnecter():
    """Déconnecte l'utilisateur actuel."""
    if "user" in st.session_state:
        username = st.session_state["user"].get("username", "?")
        log_audit(username, "LOGOUT", "Déconnexion")
        del st.session_state["user"]


def get_current_user():
    """Retourne l'utilisateur connecté ou None."""
    return st.session_state.get("user")


def require_role(*roles):
    """Vérifie que l'utilisateur a un des rôles requis."""
    user = get_current_user()
    if not user:
        return False
    return user.get("role", "") in roles


def get_user_client():
    """Retourne le client associé à l'utilisateur connecté.
    Si Admin, Manager ou Technicien → None (voit tout).
    Si Lecteur → retourne le nom du client."""
    user = get_current_user()
    if not user:
        return None
    if user.get("role") == "Lecteur":
        return user.get("client", "") or None
    return None


import json

# Permissions par défaut pour chaque rôle
DEFAULT_PERMISSIONS = {
    "Admin": {
        "dashboard": True, "supervision": True, "equipements": True,
        "doc_technique": True,
        "predictions": True, "base_connaissances": True, "sav": True,
        "demandes": True, "planning": True, "pieces": True, "reports": True,
        "contrats": True, "conformite": True, "admin": True, "settings": True,
    },
    "Manager": {
        "dashboard": True, "supervision": True, "equipements": True,
        "doc_technique": True,
        "predictions": True, "base_connaissances": True, "sav": True,
        "demandes": True, "planning": True, "pieces": True, "reports": True,
        "contrats": True, "conformite": True, "admin": True, "settings": False,
    },
    "Technicien": {
        "dashboard": True, "supervision": True, "equipements": True,
        "doc_technique": True,
        "predictions": True, "base_connaissances": True, "sav": True,
        "demandes": True, "planning": True, "pieces": True, "reports": True,
        "contrats": True, "conformite": True, "admin": False, "settings": False,
    },
    "Responsable Technique": {
        "dashboard": True, "supervision": True, "equipements": True,
        "doc_technique": True,
        "predictions": True, "base_connaissances": True, "sav": True,
        "demandes": True, "planning": True, "pieces": True, "reports": True,
        "contrats": True, "conformite": True, "admin": False, "settings": False,
    },
    "Gestionnaire de stock": {
        "dashboard": True, "supervision": False, "equipements": True,
        "doc_technique": True,
        "predictions": False, "base_connaissances": True, "sav": False,
        "demandes": False, "planning": False, "pieces": True, "reports": True,
        "contrats": False, "conformite": False, "admin": False, "settings": False,
    },
    "Lecteur": {
        "dashboard": True, "supervision": True, "equipements": True,
        "doc_technique": True,
        "predictions": True, "base_connaissances": True, "sav": False,
        "demandes": True, "planning": False, "pieces": False, "reports": True,
        "contrats": False, "conformite": True, "admin": False, "settings": False,
    },
}


def get_permissions():
    """Retourne les permissions de tous les rôles depuis la config DB."""
    from db_engine import get_config
    raw = get_config("role_permissions", "")
    if raw:
        try:
            perms = json.loads(raw)
            # Fusionner avec les défauts pour les nouvelles pages
            for role in DEFAULT_PERMISSIONS:
                if role not in perms:
                    perms[role] = DEFAULT_PERMISSIONS[role].copy()
                else:
                    for page in DEFAULT_PERMISSIONS[role]:
                        if page not in perms[role]:
                            perms[role][page] = DEFAULT_PERMISSIONS[role][page]
            return perms
        except (json.JSONDecodeError, TypeError):
            pass
    return {r: dict(p) for r, p in DEFAULT_PERMISSIONS.items()}


def save_permissions(perms):
    """Sauvegarde les permissions dans la config DB."""
    from db_engine import set_config
    set_config("role_permissions", json.dumps(perms))


def has_page_access(page_key):
    """Vérifie si l'utilisateur actuel a accès à une page donnée."""
    user = get_current_user()
    if not user:
        return False
    role = user.get("role", "")
    # Admin a toujours accès à tout
    if role == "Admin":
        return True
    perms = get_permissions()
    role_perms = perms.get(role, {})
    return role_perms.get(page_key, False)


# ==========================================
# GESTION UTILISATEURS (Admin seulement)
# ==========================================

def lister_utilisateurs():
    """
    Récupère la liste des utilisateurs avec leurs informations personnelles.
    
    Returns:
        list[dict]: Liste des profils complets (Auth + PII joint).
    """
    try:
        with get_db() as conn:
            # Jointure pour récupérer les infos complètes
            rows = conn.execute("""
                SELECT u.*, p.nom_complet, p.email, p.telephone
                FROM utilisateurs u
                LEFT JOIN user_pii p ON u.id = p.user_id
                ORDER BY u.username
            """).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Erreur lister_utilisateurs: {e}")
        return []


def creer_utilisateur(username, password, nom_complet, role, email="", client=""):
    """
    Crée un nouvel utilisateur avec isolation physique des PII.
    
    Returns:
        bool: Succès de l'opération complète.
    """
    try:
        with get_db() as conn:
            # 1. Insertion technique
            res = conn.execute("""
                INSERT INTO utilisateurs (username, password_hash, role, client)
                VALUES (?, ?, ?, ?)
            """, (username, hash_password(password), role, client))
            user_id = res.lastrowid
            
            # 2. Insertion PII (Pillier 2)
            conn.execute("""
                INSERT INTO user_pii (user_id, nom_complet, email)
                VALUES (?, ?, ?)
            """, (user_id, nom_complet, email))
            
        logger.info(f"Audit Trail: Nouvel utilisateur {username} créé (ID: {user_id})")
        return True
    except Exception as e:
        logger.error(f"Erreur creation utilisateur {username}: {e}")
        return False


def modifier_utilisateur(user_id, nom_complet=None, role=None, email=None, actif=None):
    """
    Met à jour les informations d'un utilisateur dans les tables respectives.
    """
    try:
        with get_db() as conn:
            # Update AUTH
            if role is not None:
                conn.execute("UPDATE utilisateurs SET role=? WHERE id=?", (role, user_id))
            if actif is not None:
                conn.execute("UPDATE utilisateurs SET actif=? WHERE id=?", (actif, user_id))
            
            # Update PII (Pillier 2)
            if nom_complet is not None or email is not None:
                # Vérifier si l'entrée PII existe déjà
                exist = conn.execute("SELECT 1 FROM user_pii WHERE user_id=?", (user_id,)).fetchone()
                if not exist:
                    conn.execute("INSERT INTO user_pii (user_id, nom_complet, email) VALUES (?, ?, ?)", 
                                 (user_id, nom_complet or "", email or ""))
                else:
                    if nom_complet is not None:
                        conn.execute("UPDATE user_pii SET nom_complet=? WHERE user_id=?", (nom_complet, user_id))
                    if email is not None:
                        conn.execute("UPDATE user_pii SET email=? WHERE user_id=?", (email, user_id))
        return True
    except Exception as e:
        logger.error(f"Erreur modifier_utilisateur ID {user_id}: {e}")
        return False


def changer_mot_de_passe(user_id, nouveau_mdp):
    """Change le mot de passe d'un utilisateur."""
    with get_db() as conn:
        conn.execute(
            "UPDATE utilisateurs SET password_hash=? WHERE id=?",
            (hash_password(nouveau_mdp), user_id))
    return True


def supprimer_utilisateur(user_id):
    """Supprime un utilisateur (sauf le dernier admin)."""
    with get_db() as conn:
        user = conn.execute("SELECT role FROM utilisateurs WHERE id=?", (user_id,)).fetchone()
        if user and user["role"] == "Admin":
            row_admin = conn.execute("SELECT COUNT(*) as cnt FROM utilisateurs WHERE role='Admin' AND actif=1").fetchone()
            admin_count = row_admin["cnt"] if row_admin else 0
            if admin_count <= 1:
                return False  # Ne pas supprimer le dernier admin
        conn.execute("DELETE FROM utilisateurs WHERE id=?", (user_id,))
    return True


# Créer l'admin par défaut au premier lancement
creer_admin_defaut()
