"""
migrate_sqlite_to_pg.py — Migration des données SQLite vers PostgreSQL
======================================================================
Transfère toutes les données de l'ancienne base SQLite vers PostgreSQL.
À exécuter une seule fois après la migration d'infrastructure.
"""
import sqlite3
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("migration")

# Chemin vers l'ancien SQLite
SQLITE_PATH = os.environ.get("SQLITE_PATH", "/app/sic_radiologie.db")

# Tables à migrer (dans l'ordre pour respecter les FK)
TABLES_ORDER = [
    "codes_erreurs",
    "solutions",
    "utilisateurs",
    "techniciens",
    "equipements",
    "contrats",
    "interventions",
    "planning_maintenance",
    "pieces_rechange",
    "telemetry",
    "audit_log",
    "ai_audit_log",
    "documents_techniques",
    "config_client",
    "conformite",
    "demandes_intervention",
    "notifications_pieces",
    "prediction_feedback",
    "logs_uploaded",
]


def migrate():
    """Migration complète SQLite → PostgreSQL."""
    if not os.path.exists(SQLITE_PATH):
        logger.error(f"❌ SQLite non trouvé: {SQLITE_PATH}")
        return False

    # Connexion SQLite (source)
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    # Connexion PostgreSQL (destination)
    import psycopg2
    import psycopg2.extras
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL non défini")
        return False

    pg_conn = psycopg2.connect(DATABASE_URL)
    pg_conn.set_client_encoding('UTF8')

    total_rows = 0
    errors = 0

    for table in TABLES_ORDER:
        try:
            # Vérifier si la table existe dans SQLite
            check = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not check:
                logger.warning(f"⚠️  [{table}] N'existe pas dans SQLite, ignorée")
                continue

            # Lire toutes les lignes depuis SQLite
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                logger.info(f"📭 [{table}] Vide, ignorée")
                continue

            # Obtenir les noms de colonnes
            columns = rows[0].keys()

            # Vérifier quelles colonnes existent dans PG
            pg_cursor = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                pg_cursor.execute(f"SELECT * FROM {table} LIMIT 0")
                pg_columns = [desc[0] for desc in pg_cursor.description]
            except Exception:
                pg_conn.rollback()
                logger.warning(f"⚠️  [{table}] N'existe pas dans PostgreSQL, ignorée")
                continue

            # Intersection des colonnes (éviter les colonnes qui n'existent pas dans PG)
            valid_columns = [c for c in columns if c in pg_columns]
            if not valid_columns:
                logger.warning(f"⚠️  [{table}] Aucune colonne commune, ignorée")
                continue

            # Préparer l'INSERT PG
            cols_str = ", ".join(valid_columns)
            placeholders = ", ".join(["%s"] * len(valid_columns))

            # Insérer ligne par ligne avec gestion des conflits
            inserted = 0
            for row in rows:
                values = []
                for col in valid_columns:
                    val = row[col]
                    # Convertir les bytes en None pour PG (ou les gérer spécialement)
                    if isinstance(val, bytes):
                        val = None
                    values.append(val)

                try:
                    pg_cursor.execute("SAVEPOINT row_sp")
                    pg_cursor.execute(
                        f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})",
                        values
                    )
                    pg_cursor.execute("RELEASE SAVEPOINT row_sp")
                    inserted += 1
                except Exception as e:
                    pg_cursor.execute("ROLLBACK TO SAVEPOINT row_sp")
                    err_str = str(e).lower()
                    if "duplicate" in err_str or "unique" in err_str:
                        pass  # Déjà existant, ignorer
                    else:
                        logger.debug(f"  Row error in {table}: {str(e)[:80]}")

            pg_conn.commit()

            # Reset les séquences SERIAL pour éviter les conflits d'ID futurs
            try:
                pg_cursor.execute(f"""
                    SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                           COALESCE((SELECT MAX(id) FROM {table}), 1))
                """)
                pg_conn.commit()
            except Exception:
                pg_conn.rollback()

            total_rows += inserted
            logger.info(f"✅ [{table}] {inserted}/{len(rows)} lignes migrées")

        except Exception as e:
            errors += 1
            pg_conn.rollback()
            logger.error(f"❌ [{table}] Erreur: {e}")

    # Tables PII (user_pii, technicien_pii)
    for pii_table in ["user_pii", "technicien_pii"]:
        try:
            check = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (pii_table,)
            ).fetchone()
            if check:
                rows = sqlite_conn.execute(f"SELECT * FROM {pii_table}").fetchall()
                if rows:
                    columns = rows[0].keys()
                    pg_cursor = pg_conn.cursor()
                    try:
                        pg_cursor.execute(f"SELECT * FROM {pii_table} LIMIT 0")
                        pg_columns = [desc[0] for desc in pg_cursor.description]
                    except Exception:
                        pg_conn.rollback()
                        continue

                    valid_columns = [c for c in columns if c in pg_columns]
                    cols_str = ", ".join(valid_columns)
                    placeholders = ", ".join(["%s"] * len(valid_columns))

                    inserted = 0
                    for row in rows:
                        values = [row[col] for col in valid_columns]
                        try:
                            pg_cursor.execute("SAVEPOINT pii_sp")
                            pg_cursor.execute(f"INSERT INTO {pii_table} ({cols_str}) VALUES ({placeholders})", values)
                            pg_cursor.execute("RELEASE SAVEPOINT pii_sp")
                            inserted += 1
                        except Exception:
                            pg_cursor.execute("ROLLBACK TO SAVEPOINT pii_sp")

                    pg_conn.commit()
                    try:
                        pg_cursor.execute(f"""
                            SELECT setval(pg_get_serial_sequence('{pii_table}', 'id'),
                                   COALESCE((SELECT MAX(id) FROM {pii_table}), 1))
                        """)
                        pg_conn.commit()
                    except Exception:
                        pg_conn.rollback()
                    logger.info(f"✅ [{pii_table}] {inserted}/{len(rows)} lignes PII migrées")
        except Exception as e:
            logger.error(f"❌ [{pii_table}] Erreur: {e}")

    sqlite_conn.close()
    pg_conn.close()

    logger.info(f"\n{'='*50}")
    logger.info(f"🎉 Migration terminée: {total_rows} lignes au total, {errors} erreur(s)")
    logger.info(f"{'='*50}")
    return errors == 0


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
