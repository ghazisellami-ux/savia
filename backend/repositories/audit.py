"""Audit, configuration, telemetry, import, and schema-maintenance persistence."""

import os

import pandas as pd
import psycopg2

from database.core import DATABASE_URL, get_db, init_db, logger, read_sql

__all__ = [
    "log_audit",
    "lire_audit",
    "log_ai_inference",
    "save_prediction_feedback",
    "lire_prediction_feedback",
    "get_prediction_accuracy",
    "get_config",
    "set_config",
    "migrer_depuis_excel",
    "purger_et_reimporter_excel",
    "log_telemetry",
    "lire_telemetry",
    "verifier_et_migrer_schema",
]

# ==========================================
# FONCTIONS CRUD — AUDIT LOG
# ==========================================

def log_audit(username, action, details="", page="", ip_address=""):
    """
    Enregistre une action dans le journal d'audit.
    
    Args:
        username (str): Nom d'utilisateur effectuant l'action
        action (str): Type d'action (LOGIN, CREATE_EQUIPEMENT, UPDATE_INTERVENTION, etc.)
        details (str): Détails de l'action (JSON ou texte libre)
        page (str): Page/module concerné (equipements, interventions, etc.)
        ip_address (str): Adresse IP du client
    """
    with get_db() as conn:
        conn.execute("""
            INSERT INTO audit_log (username, action, details, page, ip_address)
            VALUES (%s, %s, %s, %s, %s)
        """, (username, action, details, page, ip_address))


def lire_audit(limit=1000, username="", action="", date_from="", date_to=""):
    """
    Lit le journal d'audit avec filtrage.
    
    Args:
        limit (int): Nombre maximum de logs à retourner (défaut 1000)
        username (str): Filtrer par utilisateur (optionnel)
        action (str): Filtrer par type d'action (optionnel)
        date_from (str): Date de début au format YYYY-MM-DD (optionnel)
        date_to (str): Date de fin au format YYYY-MM-DD (optionnel)
    
    Returns:
        pd.DataFrame: Les logs filtrés triés par timestamp décroissant
    """
    with get_db() as conn:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        
        if username:
            query += " AND username = %s"
            params.append(username)
        
        if action:
            query += " AND action = %s"
            params.append(action)
        
        if date_from:
            query += " AND DATE(timestamp) >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND DATE(timestamp) <= %s"
            params.append(date_to)
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        return read_sql(query, conn, params=tuple(params))


def log_ai_inference(model_version, prompt_hash, confidence_score, outcome):
    """Enregistre une inference IA dans le journal d'audit (EU AI Act)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO ai_audit_log (model_version, prompt_hash, confidence_score, outcome)
            VALUES (%s, %s, %s, %s)
        """, (model_version, prompt_hash, confidence_score, outcome))


# ==========================================
# FONCTIONS — PREDICTION FEEDBACK (HITL)
# ==========================================

def save_prediction_feedback(
    machine,
    date_predite,
    resultat,
    date_reelle="",
    note="",
    username="system",
    *,
    equipment_id=None,
    client="",
    horizon_jours=30,
    risque_pct=None,
    modele_version="",
    date_calcul="",
    features_json=None,
):
    """Enregistre le feedback d'un technicien sur une prédiction."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO prediction_feedback (
                machine, date_predite, resultat, date_reelle, note_technicien, username,
                equipment_id, client, horizon_jours, risque_pct, modele_version,
                date_calcul, features_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            machine, date_predite, resultat, date_reelle, note, username,
            equipment_id, client, horizon_jours, risque_pct, modele_version,
            date_calcul, features_json,
        ))


def lire_prediction_feedback(machine=None, limit=50):
    """Lit les feedbacks de prédictions, optionnellement filtrés par machine."""
    with get_db() as conn:
        if machine:
            return read_sql(
                "SELECT * FROM prediction_feedback WHERE machine = %s ORDER BY timestamp DESC LIMIT %s",
                conn, params=(machine, limit))
        return read_sql(
            "SELECT * FROM prediction_feedback ORDER BY timestamp DESC LIMIT %s",
            conn, params=(limit,))


def get_prediction_accuracy(machine=None):
    """Calcule le taux de précision des prédictions par machine."""
    df = lire_prediction_feedback(machine, limit=200)
    if df.empty:
        return {} if not machine else {"total": 0, "correct": 0, "precision": 0}
    
    if machine:
        total = len(df)
        correct = len(df[df["resultat"] == "correct"])
        return {
            "total": total,
            "correct": correct,
            "faux_positif": len(df[df["resultat"] == "faux_positif"]),
            "decale": len(df[df["resultat"] == "decale"]),
            "precision": round((correct / total) * 100) if total > 0 else 0
        }
    
    # Par machine
    result = {}
    for m in df["machine"].unique():
        df_m = df[df["machine"] == m]
        total = len(df_m)
        correct = len(df_m[df_m["resultat"] == "correct"])
        result[m] = {
            "total": total,
            "correct": correct,
            "precision": round((correct / total) * 100) if total > 0 else 0
        }
    return result


# ==========================================
# FONCTIONS — CONFIG CLIENT
# ==========================================

def get_config(cle, default=""):
    """Récupère une valeur de configuration."""
    with get_db() as conn:
        row = conn.execute("SELECT valeur FROM config_client WHERE cle = %s", (cle,)).fetchone()
        return row["valeur"] if row else default


def set_config(cle, valeur):
    """Définit une valeur de configuration."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO config_client (cle, valeur) VALUES (%s, %s)
            ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur
        """, (cle, valeur))


# ==========================================
# IMPORT INITIAL EXCEL → POSTGRESQL
# ==========================================

def migrer_depuis_excel(excel_path):
    """Importe les données Excel historiques dans PostgreSQL."""
    if not os.path.exists(excel_path):
        return False

    init_db()
    migrated = 0

    try:
        # Migrer CODES_HEXA
        try:
            df_codes = pd.read_excel(excel_path, sheet_name="CODES_HEXA", dtype=str).fillna("")
            print(f"[MIGRATION] CODES_HEXA: {len(df_codes)} lignes trouvees")
            with get_db() as conn:
                for _, row in df_codes.iterrows():
                    code = str(row.get("Code", "")).strip()
                    if code:
                        try:
                            conn.execute("""
                                INSERT INTO codes_erreurs (code, message, niveau, type) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
                            """, (code, row.get("Message", ""), row.get("Niveau", "ATTENTION"), row.get("Type", "")))
                            migrated += 1
                        except Exception as e:
                            print(f"[MIGRATION] Erreur code {code}: {e}")
            print(f"[MIGRATION] {migrated} codes migres")
        except Exception as e:
            print(f"[MIGRATION] Erreur CODES_HEXA: {e}")

        # Migrer SOLUTIONS_TEXTE
        sol_count = 0
        try:
            df_sol = pd.read_excel(excel_path, sheet_name="SOLUTIONS_TEXTE", dtype=str).fillna("")
            print(f"[MIGRATION] SOLUTIONS_TEXTE: {len(df_sol)} lignes trouvees")
            with get_db() as conn:
                for _, row in df_sol.iterrows():
                    mot_cle = str(row.get("Mot_Cle", "")).strip()
                    if mot_cle:
                        try:
                            conn.execute("""
                                INSERT INTO solutions (mot_cle, type, priorite, cause, solution) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
                            """, (mot_cle, row.get("Type", ""), row.get("Priorite", "MOYENNE"),
                                  row.get("Cause", ""), row.get("Solution", "")))
                            sol_count += 1
                        except Exception as e:
                            print(f"[MIGRATION] Erreur solution {mot_cle}: {e}")
            migrated += sol_count
            print(f"[MIGRATION] {sol_count} solutions migrees")
        except Exception as e:
            print(f"[MIGRATION] Erreur SOLUTIONS_TEXTE: {e}")

    except Exception as e:
        print(f"[MIGRATION] Erreur generale: {e}")
        return False

    return migrated

def purger_et_reimporter_excel(excel_path):
    """Purge les tables codes/solutions et réimporte depuis Excel (raw PG)."""
    if not os.path.exists(excel_path):
        print(f"[PURGE] Fichier introuvable: {excel_path}")
        return 0

    # Mode PostgreSQL : utiliser psycopg2 directement
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.set_client_encoding('UTF8')
    cur = conn.cursor()
    total = 0

    try:
        # Purger les tables
        cur.execute("DELETE FROM codes_erreurs")
        cur.execute("DELETE FROM solutions")
        conn.commit()
        print("[PURGE] Tables codes_erreurs et solutions videes")

        # Réimporter CODES_HEXA
        try:
            df_codes = pd.read_excel(excel_path, sheet_name="CODES_HEXA", dtype=str).fillna("")
            print(f"[PURGE] CODES_HEXA: {len(df_codes)} lignes")
            for _, row in df_codes.iterrows():
                code = str(row.get("Code", "")).strip()
                if code:
                    cur.execute("""
                        INSERT INTO codes_erreurs (code, message, niveau, type)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (code) DO UPDATE SET
                            message = EXCLUDED.message,
                            niveau = EXCLUDED.niveau,
                            type = EXCLUDED.type
                    """, (code, str(row.get("Message", "")),
                          str(row.get("Niveau", "ATTENTION")),
                          str(row.get("Type", ""))))
                    total += 1
            conn.commit()
            print(f"[PURGE] {total} codes importes")
        except Exception as e:
            print(f"[PURGE] ERREUR CODES: {e}")
            conn.rollback()

        # Réimporter SOLUTIONS_TEXTE
        sol_count = 0
        try:
            df_sol = pd.read_excel(excel_path, sheet_name="SOLUTIONS_TEXTE", dtype=str).fillna("")
            print(f"[PURGE] SOLUTIONS_TEXTE: {len(df_sol)} lignes")
            for _, row in df_sol.iterrows():
                mot_cle = str(row.get("Mot_Cle", "")).strip()
                if mot_cle:
                    cur.execute("""
                        INSERT INTO solutions (mot_cle, type, priorite, cause, solution)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (mot_cle) DO UPDATE SET
                            type = EXCLUDED.type,
                            priorite = EXCLUDED.priorite,
                            cause = EXCLUDED.cause,
                            solution = EXCLUDED.solution
                    """, (mot_cle, str(row.get("Type", "")),
                          str(row.get("Priorite", "MOYENNE")),
                          str(row.get("Cause", "")),
                          str(row.get("Solution", ""))))
                    sol_count += 1
            conn.commit()
            total += sol_count
            print(f"[PURGE] {sol_count} solutions importees")
        except Exception as e:
            print(f"[PURGE] ERREUR SOLUTIONS: {e}")
            conn.rollback()

    finally:
        cur.close()
        conn.close()

    print(f"[PURGE] Total: {total} entrees importees")
    return total





# ==========================================
# FONCTIONS — IOT & TELEMETRY
# ==========================================

def log_telemetry(machine, sensor_type, value):
    """Enregistre une donnée télémétrique."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO telemetry (machine, sensor_type, value) VALUES (%s, %s, %s)",
            (machine, sensor_type, float(value)))
    return True


def lire_telemetry(machine, sensor_type=None, hours=24):
    """Lit l'historique de télémétrie pour une machine."""
    if "%" in machine:
        query = """
            SELECT timestamp, machine, sensor_type, value FROM telemetry
            WHERE machine LIKE %s
            AND timestamp > CURRENT_TIMESTAMP - (%s * INTERVAL '1 hour')
        """
    else:
        query = """
            SELECT timestamp, machine, sensor_type, value FROM telemetry
            WHERE machine = %s
            AND timestamp > CURRENT_TIMESTAMP - (%s * INTERVAL '1 hour')
        """
    params = [machine, hours]
    
    if sensor_type:
        query += " AND sensor_type = %s"
        params.append(sensor_type)
        
    query += " ORDER BY timestamp ASC"
    
    with get_db() as conn:
        df = read_sql(query, conn, params=params)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df


def verifier_et_migrer_schema():
    """Vérifie et migre le schéma si nécessaire (ajout colonnes manquantes)."""
    # NOTE: init_db() est déjà appelée dans @app.on_event("startup")
    # Ne pas l'appeler ici pour éviter une boucle infinie!
    
    # Mode PostgreSQL - utiliser psycopg2
    import psycopg2
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_client_encoding('UTF8')
        cur = conn.cursor()
            
        # Colonnes à vérifier/ajouter (interventions table)
        missing_cols = [
            ("start_time", "TIME"),
            ("end_time", "TIME"),
            ("duree_deplacement", "INTEGER DEFAULT 0"),
            ("fiche_validation", "TEXT DEFAULT 'En attente'"),
        ]
            
        for col, type_def in missing_cols:
            try:
                cur.execute(f"ALTER TABLE interventions ADD COLUMN IF NOT EXISTS {col} {type_def}")
                conn.commit()
                logger.info(f"Migration PostgreSQL: Colonne '{col}' ajoutée/vérifiée.")
            except psycopg2.Error as e:
                logger.debug(f"Migration PostgreSQL colonne {col}: {e}")
                conn.rollback()
            
        # Colonnes à vérifier/ajouter (interventions_techniciens table)
        tech_cols = [
            ("type_erreur_tech", "TEXT DEFAULT ''"),
            ("pieces_a_deduire", "TEXT DEFAULT ''"),  # JSON array of pieces
        ]
            
        for col, type_def in tech_cols:
            try:
                cur.execute(f"ALTER TABLE interventions_techniciens ADD COLUMN IF NOT EXISTS {col} {type_def}")
                conn.commit()
                logger.info(f"Migration PostgreSQL: Colonne '{col}' ajoutée/vérifiée à interventions_techniciens.")
            except psycopg2.Error as e:
                logger.debug(f"Migration PostgreSQL colonne {col} interventions_techniciens: {e}")
                conn.rollback()
            
        # Migration: Update CHECK constraint for interventions_techniciens.statut to include "En attente de piece"
        try:
            cur.execute("""
                SELECT constraint_name FROM information_schema.table_constraints 
                WHERE table_name = 'interventions_techniciens' AND constraint_type = 'CHECK'
            """)
            constraint_result = cur.fetchone()
            if constraint_result:
                constraint_name = constraint_result[0]
                # Drop old constraint
                cur.execute(f"ALTER TABLE interventions_techniciens DROP CONSTRAINT {constraint_name}")
                conn.commit()
                logger.info(f"Migration PostgreSQL: Ancien CHECK constraint '{constraint_name}' supprimé.")
                
            # Add new constraint with "En attente de piece"
            cur.execute("""
                ALTER TABLE interventions_techniciens 
                ADD CONSTRAINT interventions_techniciens_statut_check 
                CHECK (statut IN ('Assigné', 'En cours', 'Cloturee', 'Refusé', 'En attente de piece'))
            """)
            conn.commit()
            logger.info("Migration PostgreSQL: CHECK constraint mis à jour pour interventions_techniciens.statut")
        except psycopg2.Error as e:
            logger.debug(f"Migration PostgreSQL CHECK constraint: {e}")
            try:
                conn.rollback()
            except:
                pass
            
        # Migration: Add rappel_avant_jours column to contrats table
        try:
            cur.execute("""
                ALTER TABLE contrats ADD COLUMN IF NOT EXISTS rappel_avant_jours INTEGER DEFAULT 14
            """)
            conn.commit()
            logger.info("Migration PostgreSQL: Colonne 'rappel_avant_jours' ajoutée/vérifiée à contrats.")
        except psycopg2.Error as e:
            logger.debug(f"Migration PostgreSQL rappel_avant_jours: {e}")
            try:
                conn.rollback()
            except:
                pass
            
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Erreur migration PostgreSQL: {e}")
    return
