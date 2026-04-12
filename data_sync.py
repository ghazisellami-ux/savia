# ==========================================
# 🔄 SYNCHRONISATION DONNÉES — GITHUB BACKUP
# ==========================================
"""
Sauvegarde et restauration automatique des données via l'API GitHub.
Les données sont stockées en JSON dans le dossier `data/` du repo,
sur la branche `data-backup` (PAS `main`) pour éviter de déclencher
un redéploiement Streamlit Cloud à chaque sauvegarde.
"""
import json
import base64
import os
import traceback
import pandas as pd
import requests
from datetime import datetime

# NOTE: On n'importe PAS streamlit au niveau module pour éviter les
# problèmes quand ce module est importé depuis db_engine.py (qui est
# lui-même importé très tôt, avant le contexte Streamlit).


# --- Configuration GitHub ---
GITHUB_OWNER = "ghazisellami-ux"
GITHUB_REPO = "sic_radiology"
GITHUB_DATA_BRANCH = "data-backup"    # Branche séparée pour les données
GITHUB_DATA_FOLDER = "data"


def _get_token():
    """Récupère le GITHUB_TOKEN depuis Streamlit secrets ou l'environnement."""
    # 1. Essayer Streamlit secrets
    try:
        import streamlit as st
        token = st.secrets.get("GITHUB_TOKEN", "")
        if token:
            return token
    except Exception:
        pass

    # 2. Essayer les variables d'environnement
    return os.environ.get("GITHUB_TOKEN", "")


def _github_headers():
    token = _get_token()
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _github_api_url(path):
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_DATA_FOLDER}/{path}"


def _ensure_data_branch():
    """Crée la branche data-backup si elle n'existe pas."""
    token = _get_token()
    if not token:
        return False

    headers = _github_headers()
    branch_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs/heads/{GITHUB_DATA_BRANCH}"

    try:
        resp = requests.get(branch_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return True  # La branche existe déjà

        # La branche n'existe pas — la créer à partir de main
        main_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs/heads/main"
        resp_main = requests.get(main_url, headers=headers, timeout=10)
        if resp_main.status_code != 200:
            print(f"[DATA_SYNC] Impossible de lire la branche main: {resp_main.status_code}")
            return False

        sha_main = resp_main.json()["object"]["sha"]

        create_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/git/refs"
        payload = {
            "ref": f"refs/heads/{GITHUB_DATA_BRANCH}",
            "sha": sha_main,
        }
        resp_create = requests.post(create_url, headers=headers, json=payload, timeout=10)
        if resp_create.status_code in (200, 201):
            print(f"[DATA_SYNC] Branche '{GITHUB_DATA_BRANCH}' creee avec succes")
            return True
        else:
            print(f"[DATA_SYNC] Erreur creation branche: {resp_create.status_code} {resp_create.text[:100]}")
            return False
    except Exception as e:
        print(f"[DATA_SYNC] Erreur branche: {e}")
        return False


# ==========================================
# EXPORT (DB → JSON → GitHub)
# ==========================================

TABLES_TO_BACKUP = [
    "equipements",
    "interventions",
    "planning_maintenance",
    "codes_erreurs",
    "solutions",
    "techniciens",
    "pieces_rechange",
    "contrats",           # ← ÉTAIT MANQUANT — cause de la perte de contrats !
    "audit_log",
    "config_client",
    "utilisateurs",
    "telemetry",
]


def exporter_table_json(table_name):
    """Exporte une table SQLite en liste de dicts."""
    try:
        from db_engine import get_db
        with get_db() as conn:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
            return df.to_dict(orient="records")
    except Exception:
        return []


def exporter_toutes_tables():
    """Exporte toutes les tables en un dict global."""
    backup = {
        "timestamp": datetime.now().isoformat(),
        "tables": {}
    }
    for table in TABLES_TO_BACKUP:
        data = exporter_table_json(table)
        if data:
            backup["tables"][table] = data
    return backup


def _upload_to_github(filename, content_str):
    """Upload un fichier vers GitHub via l'API (branche data-backup)."""
    token = _get_token()
    if not token:
        return False, "GITHUB_TOKEN non configure"

    # S'assurer que la branche existe
    _ensure_data_branch()

    url = _github_api_url(filename)
    headers = _github_headers()

    # Vérifier si le fichier existe (pour obtenir le SHA)
    sha = None
    try:
        resp = requests.get(url, headers=headers, params={"ref": GITHUB_DATA_BRANCH}, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
    except Exception:
        pass

    # Encoder en base64
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"backup: {filename} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content_b64,
        "branch": GITHUB_DATA_BRANCH,   # Branche SEPAREE
    }
    if sha:
        payload["sha"] = sha

    try:
        resp = requests.put(url, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            return True, "Sauvegarde sur GitHub OK"
        else:
            return False, f"Erreur GitHub: {resp.status_code} - {resp.text[:200]}"
    except Exception as e:
        return False, f"Erreur reseau: {str(e)}"


def sauvegarder_sur_github():
    """Sauvegarde complète de toutes les tables vers GitHub."""
    backup = exporter_toutes_tables()
    content = json.dumps(backup, ensure_ascii=False, indent=2, default=str)
    return _upload_to_github("backup_complet.json", content)


def sauvegarder_table_github(table_name):
    """Sauvegarde une table spécifique vers GitHub."""
    data = exporter_table_json(table_name)
    content = json.dumps({
        "timestamp": datetime.now().isoformat(),
        "table": table_name,
        "data": data
    }, ensure_ascii=False, indent=2, default=str)
    return _upload_to_github(f"{table_name}.json", content)


# ==========================================
# IMPORT (GitHub → JSON → DB)
# ==========================================

def _download_from_github(filename):
    """Télécharge un fichier depuis GitHub (branche data-backup)."""
    token = _get_token()
    if not token:
        return None

    url = _github_api_url(filename)
    headers = _github_headers()

    try:
        resp = requests.get(url, headers=headers, params={"ref": GITHUB_DATA_BRANCH}, timeout=10)
        if resp.status_code == 200:
            content_b64 = resp.json().get("content", "")
            content = base64.b64decode(content_b64).decode("utf-8")
            return json.loads(content)
    except Exception:
        pass

    return None


def restaurer_depuis_github():
    """Restaure toutes les tables depuis le backup GitHub."""
    backup = _download_from_github("backup_complet.json")
    if not backup:
        return False, "Aucun backup trouve sur GitHub"

    tables = backup.get("tables", {})
    if not tables:
        return False, "Backup vide"

    from db_engine import get_db
    restored = []

    with get_db() as conn:
        for table_name, rows in tables.items():
            if not rows:
                continue
            try:
                # Vider la table existante
                conn.execute(f"DELETE FROM {table_name}")

                # Insérer les données
                cols = list(rows[0].keys())
                placeholders = ", ".join(["?" for _ in cols])
                cols_str = ", ".join(cols)

                for row in rows:
                    values = [row.get(c) for c in cols]
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table_name} ({cols_str}) VALUES ({placeholders})",
                        values
                    )
                restored.append(f"{table_name} ({len(rows)})")
            except Exception as e:
                restored.append(f"{table_name} (ERREUR: {str(e)[:50]})")

    timestamp = backup.get("timestamp", "?")
    return True, f"Restaure depuis backup du {timestamp}\n" + "\n".join(restored)


def auto_restore_si_vide():
    """Appelé au démarrage : restaure depuis GitHub si la DB est vide."""
    try:
        from db_engine import get_db
        with get_db() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM equipements").fetchone()
            count = row["cnt"] if row else 0
            if count == 0:
                ok, msg = restaurer_depuis_github()
                if ok:
                    print(f"[DATA_SYNC] Auto-restore: {msg}")
                else:
                    print(f"[DATA_SYNC] Pas de backup: {msg}")
                return ok
    except Exception as e:
        print(f"[DATA_SYNC] Erreur auto-restore: {e}")
    return False


# ==========================================
# BACKUP AUTOMATIQUE (après écriture)
# ==========================================

_last_backup_time = None


def _backup_local():
    """Crée une copie locale de la DB comme filet de sécurité."""
    import shutil
    from config import BASE_DIR
    db_path = os.path.join(BASE_DIR, "sic_radiologie.db")
    backup_dir = os.path.join(BASE_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    if os.path.exists(db_path):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(backup_dir, f"sic_radiologie_{ts}.db")
        try:
            shutil.copy2(db_path, dest)
            # Garder max 10 backups locaux
            backups = sorted(
                [f for f in os.listdir(backup_dir) if f.endswith(".db")],
                reverse=True
            )
            for old in backups[10:]:
                os.remove(os.path.join(backup_dir, old))
        except Exception as e:
            print(f"[DATA_SYNC] Local backup error: {e}")


def auto_backup_si_necessaire():
    """Sauvegarde automatique si la dernière sauvegarde date de plus de 10 secondes."""
    global _last_backup_time
    now = datetime.now()

    if _last_backup_time and (now - _last_backup_time).total_seconds() < 10:
        return  # Déjà sauvegardé récemment

    _last_backup_time = now

    # 1. Backup local (toujours)
    _backup_local()

    # 2. Backup GitHub
    try:
        ok, msg = sauvegarder_sur_github()
        if ok:
            print(f"[DATA_SYNC] Auto-backup OK (GitHub + local)")
        else:
            print(f"[DATA_SYNC] Auto-backup GitHub: {msg} (local OK)")
    except Exception as e:
        print(f"[DATA_SYNC] Auto-backup GitHub error: {e} (local OK)")


def backup_table_apres_ecriture(table_name):
    """Déclenche un backup de la table après une écriture."""
    try:
        auto_backup_si_necessaire()
    except Exception:
        pass
