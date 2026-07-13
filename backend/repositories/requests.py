"""Intervention-request and notification-schedule persistence."""

from datetime import datetime

from database.core import _trigger_backup, get_db, logger, read_sql
from repositories.knowledge import _fix_df_text

__all__ = [
    "_ensure_demandes_table",
    "lire_demandes_intervention",
    "ajouter_demande_intervention",
    "traiter_demande_intervention",
    "modifier_demande_intervention",
    "supprimer_demande_intervention",
    "_ensure_notification_schedules_exists",
    "lire_notification_schedules",
    "lire_notification_schedule",
    "sauvegarder_notification_schedule",
    "sauvegarder_notification_schedules_batch",
]

# ==========================================
# FONCTIONS CRUD — DEMANDES D'INTERVENTION
# ==========================================

def _ensure_demandes_table():
    """Crée la table demandes_intervention si elle n'existe pas (PostgreSQL)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS demandes_intervention (
                id SERIAL PRIMARY KEY,
                date_demande TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                demandeur TEXT DEFAULT '',
                client TEXT DEFAULT '',
                equipement TEXT DEFAULT '',
                urgence TEXT DEFAULT 'Moyenne',
                description TEXT DEFAULT '',
                code_erreur TEXT DEFAULT '',
                contact_nom TEXT DEFAULT '',
                contact_tel TEXT DEFAULT '',
                statut TEXT DEFAULT 'Nouvelle',
                technicien_assigne TEXT DEFAULT '',
                notes_traitement TEXT DEFAULT '',
                date_traitement TIMESTAMP,
                date_planifiee DATE,
                intervention_id INTEGER
            )
        """)
        conn.commit()
        
        # Migration: ajouter date_planifiee si absente
        try:
            cur.execute("ALTER TABLE demandes_intervention ADD COLUMN IF NOT EXISTS date_planifiee DATE")
            conn.commit()
        except Exception:
            pass


def lire_demandes_intervention(demandeur=None, client=None):
    """Lit les demandes d'intervention, optionnellement filtrées."""
    _ensure_demandes_table()
    with get_db() as conn:
        if demandeur:
            df = read_sql(
                "SELECT * FROM demandes_intervention WHERE demandeur = ? ORDER BY date_demande DESC",
                conn, params=(demandeur,))
        elif client:
            df = read_sql(
                "SELECT * FROM demandes_intervention WHERE client = ? ORDER BY date_demande DESC",
                conn, params=(client,))
        else:
            df = read_sql("SELECT * FROM demandes_intervention ORDER BY date_demande DESC", conn)
    df = _fix_df_text(df)
    return df


def ajouter_demande_intervention(demande_dict):
    """Ajoute une demande d'intervention."""
    _ensure_demandes_table()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO demandes_intervention
                (date_demande, demandeur, client, equipement, urgence,
                 description, code_erreur, contact_nom, contact_tel, statut)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, %s)
        """, (
            demande_dict.get("date_demande", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            demande_dict.get("demandeur", ""),
            demande_dict.get("client", ""),
            demande_dict.get("equipement", ""),
            demande_dict.get("urgence", "Moyenne"),
            demande_dict.get("description", ""),
            demande_dict.get("code_erreur", ""),
            demande_dict.get("contact_nom", ""),
            demande_dict.get("contact_tel", ""),
            "Nouvelle",
        ))
    _trigger_backup()
    return True


def traiter_demande_intervention(demande_id, statut, technicien="", notes="", date_planifiee=None):
    """Met à jour le statut d'une demande d'intervention."""
    with get_db() as conn:
        conn.execute("""
            UPDATE demandes_intervention
            SET statut = ?, technicien_assigne = ?, notes_traitement = ?,
                date_traitement = ?, date_planifiee = ?
            WHERE id = ?
        """, (statut, technicien, notes,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              str(date_planifiee) if date_planifiee else None,
              demande_id))
    _trigger_backup()
    return True


def modifier_demande_intervention(demande_id, demande_dict):
    """Modifie une demande d'intervention existante."""
    with get_db() as conn:
        conn.execute("""
            UPDATE demandes_intervention
            SET client = ?, equipement = ?, urgence = ?, description = ?,
                code_erreur = ?, contact_nom = ?, contact_tel = ?
            WHERE id = ?
        """, (
            demande_dict.get("client", ""),
            demande_dict.get("equipement", ""),
            demande_dict.get("urgence", "Moyenne"),
            demande_dict.get("description", ""),
            demande_dict.get("code_erreur", ""),
            demande_dict.get("contact_nom", ""),
            demande_dict.get("contact_tel", ""),
            demande_id,
        ))
    _trigger_backup()
    return True


def supprimer_demande_intervention(demande_id):
    """Supprime une demande d'intervention."""
    with get_db() as conn:
        conn.execute("DELETE FROM demandes_intervention WHERE id = ?", (demande_id,))
    _trigger_backup()
    return True


# Note: verifier_et_migrer_schema() est appelé via init_db() dans _one_time_init() de app.py


# ==========================================
# Notification Schedules Management
# ==========================================

def _ensure_notification_schedules_exists():
    """Crée la table notification_schedules si elle n'existe pas (defensive initialization)."""
    with get_db() as conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'notification_schedules'
            """)
            if not cur.fetchone():
                # Table doesn't exist, create it
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS notification_schedules (
                        id SERIAL PRIMARY KEY,
                        bot_key TEXT NOT NULL UNIQUE,
                        enabled INTEGER DEFAULT 1,
                        hour INTEGER DEFAULT 8,
                        minute INTEGER DEFAULT 30,
                        days_of_week TEXT DEFAULT '1,2,3,4,5,6,7',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("⚠️  Table notification_schedules created dynamically (defensive)")
        except Exception as e:
            logger.debug(f"_ensure_notification_schedules_exists: {e}")


def lire_notification_schedules():
    """Lit tous les horaires de notification pour les bots Telegram."""
    _ensure_notification_schedules_exists()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, bot_key, enabled, hour, minute, days_of_week, created_at, updated_at
            FROM notification_schedules
            ORDER BY bot_key
        """).fetchall()
        return [dict(row) for row in rows]


def lire_notification_schedule(bot_key):
    """Lit l'horaire de notification pour un bot spécifique."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT id, bot_key, enabled, hour, minute, days_of_week, created_at, updated_at
            FROM notification_schedules
            WHERE bot_key = ?
        """, (bot_key,)).fetchone()
        return dict(row) if row else None


def sauvegarder_notification_schedule(bot_key, enabled, hour, minute, days_of_week):
    """Sauvegarde ou met à jour l'horaire de notification pour un bot."""
    with get_db() as conn:
        # Vérifier si le bot existe déjà
        existing = conn.execute("""
            SELECT id FROM notification_schedules WHERE bot_key = ?
        """, (bot_key,)).fetchone()
        
        if existing:
            # Mise à jour
            conn.execute("""
                UPDATE notification_schedules
                SET enabled = ?, hour = ?, minute = ?, days_of_week = ?, updated_at = CURRENT_TIMESTAMP
                WHERE bot_key = ?
            """, (enabled, hour, minute, days_of_week, bot_key))
        else:
            # Insertion
            conn.execute("""
                INSERT INTO notification_schedules (bot_key, enabled, hour, minute, days_of_week)
                VALUES (?, ?, ?, ?, %s)
            """, (bot_key, enabled, hour, minute, days_of_week))
    
    _trigger_backup()
    return True


def sauvegarder_notification_schedules_batch(schedules):
    """Sauvegarde plusieurs horaires de notification en une seule opération.
    
    Args:
        schedules: Dict avec bot_key comme clé et dict {enabled, hour, minute, days_of_week} comme valeur
    """
    with get_db() as conn:
        for bot_key, schedule_data in schedules.items():
            enabled = schedule_data.get('enabled', 1)
            hour = schedule_data.get('hour', 8)
            minute = schedule_data.get('minute', 30)
            days_of_week = schedule_data.get('days_of_week', '1,2,3,4,5,6,7')
            
            # Vérifier si le bot existe déjà
            existing = conn.execute("""
                SELECT id FROM notification_schedules WHERE bot_key = ?
            """, (bot_key,)).fetchone()
            
            if existing:
                # Mise à jour
                conn.execute("""
                    UPDATE notification_schedules
                    SET enabled = ?, hour = ?, minute = ?, days_of_week = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE bot_key = ?
                """, (enabled, hour, minute, days_of_week, bot_key))
            else:
                # Insertion
                conn.execute("""
                    INSERT INTO notification_schedules (bot_key, enabled, hour, minute, days_of_week)
                    VALUES (?, ?, ?, ?, %s)
                """, (bot_key, enabled, hour, minute, days_of_week))
    
    _trigger_backup()
    return True

