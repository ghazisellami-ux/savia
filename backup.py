# ==========================================
# 💾 SYSTÈME DE SAUVEGARDE AUTOMATIQUE
# ==========================================
"""
Sauvegarde quotidienne de la base SQLite.
Rotation automatique : conserve les 30 derniers jours.
"""
import os
import shutil
from datetime import datetime, timedelta
from config import BASE_DIR

BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DB_PATH = os.path.join(BASE_DIR, "sic_radiologie.db")
MAX_BACKUPS = 30

os.makedirs(BACKUP_DIR, exist_ok=True)


def creer_backup():
    """Crée une copie horodatée de la base de données."""
    if not os.path.exists(DB_PATH):
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_name = f"sic_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    try:
        shutil.copy2(DB_PATH, backup_path)
        rotation_backups()
        return backup_path
    except Exception:
        return None


def rotation_backups():
    """Supprime les anciens backups au-delà de MAX_BACKUPS."""
    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("sic_backup_") and f.endswith(".db")],
        reverse=True,
    )
    for old_backup in backups[MAX_BACKUPS:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old_backup))
        except Exception:
            pass


def lister_backups():
    """Retourne la liste des backups disponibles (nom, taille, date)."""
    backups = []
    if not os.path.exists(BACKUP_DIR):
        return backups

    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if f.startswith("sic_backup_") and f.endswith(".db"):
            path = os.path.join(BACKUP_DIR, f)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            backups.append({
                "nom": f,
                "taille": f"{size_mb:.2f} MB",
                "date": mtime.strftime("%Y-%m-%d %H:%M"),
                "path": path,
            })
    return backups


def restaurer_backup(backup_path):
    """Restaure la base depuis un backup."""
    if not os.path.exists(backup_path):
        return False

    try:
        # Sauvegarder l'état actuel avant restauration
        safety = os.path.join(BACKUP_DIR, f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, safety)

        shutil.copy2(backup_path, DB_PATH)
        return True
    except Exception:
        return False


def backup_quotidien():
    """Vérifie si un backup a été fait aujourd'hui, sinon en crée un."""
    today = datetime.now().strftime("%Y-%m-%d")
    for f in os.listdir(BACKUP_DIR):
        if f.startswith(f"sic_backup_{today}"):
            return None  # Déjà fait aujourd'hui

    return creer_backup()
