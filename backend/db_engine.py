import os
import re
import sqlite3
import logging
import pandas as pd
from datetime import datetime
from contextlib import contextmanager
from urllib.parse import quote
from config import BASE_DIR

# --- Configuration du Logging (Audit Trail - Pillier 3) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("db_engine")

DB_PATH = os.path.join(BASE_DIR, "sic_radiologie.db")

# Construct DATABASE_URL from environment variables with proper URL encoding
# This handles special characters in passwords correctly
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    # Try to construct from individual environment variables
    pg_user = os.environ.get("POSTGRES_USER", "")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_db = os.environ.get("POSTGRES_DB", "")
    
    if pg_user and pg_password and pg_db:
        # URL-encode the password to handle special characters
        encoded_password = quote(pg_password, safe='')
        DATABASE_URL = f"postgresql://{pg_user}:{encoded_password}@{pg_host}:{pg_port}/{pg_db}"
        logger.info(f"Constructed DATABASE_URL from environment variables: postgresql://{pg_user}:***@{pg_host}:{pg_port}/{pg_db}")

# Détecter le mode (Dual-Mode - Pillier 1)
USE_PG = bool(DATABASE_URL)

if USE_PG:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logger.error("psycopg2 non trouvé. Le mode PostgreSQL ne fonctionnera pas.")


def _trigger_backup():
    """
    Déclenche un backup GitHub automatique après chaque écriture.
    
    Logic:
        Vérifie si le mode PostgreSQL est actif (pas de backup fichier).
        Tente d'importer et d'exécuter la fonction d'auto-backup.
    """
    if USE_PG:
        return
    try:
        from data_sync import auto_backup_si_necessaire
        auto_backup_si_necessaire()
    except Exception as e:
        # Logging non critique car data_sync est optionnel
        logger.debug(f"Backup non disponible: {e}")


# ---- Wrapper PostgreSQL pour compatibilité SQLite (Pattern Proxy - Pillier 1) ----

class PgCursorWrapper:
    """
    Wraps a psycopg2 cursor to accept SQLite-style `?` placeholders.
    
    Logic:
        Traduit les requêtes SQL à la volée pour supporter les spécificités 
        de PostgreSQL (SERIAL vs AUTOINCREMENT, %s vs ?).
    """

    def __init__(self, cursor):
        self._cursor = cursor
        self._last_sql_was_skipped = False

    def _translate(self, sql, params=None):
        """Traduit SQL SQLite vers PostgreSQL."""
        sql = sql.replace("?", "%s")
        sql = sql.replace("AUTOINCREMENT", "")
        sql = sql.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
        sql = re.sub(r'\bBLOB\b', 'BYTEA', sql)
        if sql.strip().upper().startswith("PRAGMA"):
            return None, None
        sql = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", sql, flags=re.IGNORECASE)
        return sql, params

    def execute(self, sql, params=None):
        """Exécute une commande avec traduction automatique et SAVEPOINT."""
        sql, params = self._translate(sql, params)
        if sql is None:
            self._last_sql_was_skipped = True
            return self
        
        self._last_sql_was_skipped = False
        # Use SAVEPOINT for DDL/DML that might fail benignly (migrations)
        sql_upper = sql.strip().upper()
        use_savepoint = sql_upper.startswith(("ALTER", "INSERT", "CREATE"))
        
        try:
            if use_savepoint:
                self._cursor.execute("SAVEPOINT exec_sp")
            self._cursor.execute(sql, params)
            if use_savepoint:
                self._cursor.execute("RELEASE SAVEPOINT exec_sp")
        except Exception as e:
            err_str = str(e).lower()
            benign = ("duplicate key", "unique", "already exists",
                      "does not exist", "duplicate column")
            if use_savepoint and any(msg in err_str for msg in benign):
                try:
                    self._cursor.execute("ROLLBACK TO SAVEPOINT exec_sp")
                except Exception:
                    pass
                logger.debug(f"[PG] Benign error ignored: {str(e)[:80]}")
            else:
                logger.error(f"[PG] SQL Execution Error: {e} | SQL: {sql[:100]}...")
                raise
        return self

    def executescript(self, sql):
        """Exécute un script multi-statements avec SAVEPOINTs pour isolation."""
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        logger.info(f"[PG] executescript: {len(statements)} statements to execute")
        success_count = 0
        for i, stmt in enumerate(statements):
            translated, _ = self._translate(stmt)
            if translated:
                try:
                    self._cursor.execute(f"SAVEPOINT sp_{i}")
                    self._cursor.execute(translated)
                    self._cursor.execute(f"RELEASE SAVEPOINT sp_{i}")
                    success_count += 1
                except Exception as e:
                    try:
                        self._cursor.execute(f"ROLLBACK TO SAVEPOINT sp_{i}")
                    except Exception:
                        pass
                    logger.warning(f"[PG] Stmt {i} FAILED: {str(e)[:120]}")
                    logger.debug(f"[PG] Failed SQL: {translated[:150]}")
        logger.info(f"[PG] executescript done: {success_count}/{len(statements)} succeeded")
        self._last_sql_was_skipped = False
        return self

    def executemany(self, sql, seq_of_params):
        """Exécute une commande pour plusieurs séquences de paramètres."""
        sql, _ = self._translate(sql)
        if sql is None:
            self._last_sql_was_skipped = True
            return self
        
        self._last_sql_was_skipped = False
        for params in seq_of_params:
            try:
                self._cursor.execute(sql, params)
            except Exception as e:
                logger.error(f"[PG] executemany error: {e}")
        return self

    def fetchone(self):
        """Récupère une seule ligne du résultat."""
        if self._last_sql_was_skipped:
            return None
        try:
            return self._cursor.fetchone()
        except Exception:
            return None

    def fetchall(self):
        """Récupère toutes les lignes du résultat."""
        if self._last_sql_was_skipped:
            return []
        try:
            return self._cursor.fetchall()
        except Exception:
            return []

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        """Retourne le dernier ID inséré."""
        try:
            self._cursor.execute("SELECT lastval()")
            row = self._cursor.fetchone()
            if row:
                return list(row.values())[0]
            return None
        except Exception:
            return None


class PgConnectionWrapper:
    """Wraps a psycopg2 connection to mimic sqlite3.Connection API."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        wrapper = PgCursorWrapper(cursor)
        return wrapper.execute(sql, params)

    def executescript(self, sql):
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        wrapper = PgCursorWrapper(cursor)
        return wrapper.executescript(sql)

    def executemany(self, sql, seq_of_params):
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        wrapper = PgCursorWrapper(cursor)
        return wrapper.executemany(sql, seq_of_params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    @property
    def _raw(self):
        return self._conn


def read_sql(query, conn, params=None):
    """
    Lecture SQL compatible SQLite et PostgreSQL.
    
    Args:
        query (str): Requête SQL (avec placeholders ?).
        conn (sqlite3.Connection | PgConnectionWrapper): Connexion active.
        params (tuple, optional): Paramètres de la requête.
        
    Returns:
        pd.DataFrame: Résultats sous forme de DataFrame.
    """
    if USE_PG:
        raw_conn = conn._raw if hasattr(conn, '_raw') else conn
        pg_query = query.replace("?", "%s")
        try:
            return pd.read_sql_query(pg_query, raw_conn, params=params)
        except Exception as e:
            logger.error(f"Erreur read_sql (PG): {e}")
            return pd.DataFrame()
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        logger.error(f"Erreur read_sql (SQLite): {e}")
        return pd.DataFrame()


@contextmanager
def get_db():
    """
    Context manager pour les connexions DB (SQLite ou PostgreSQL).
    
    Logic:
        Initialise la connexion, définit le mode journalier (WAL pour SQLite),
        et gère le commit/rollback automatique en cas d'erreur.
        Gère l'encodage client UTF8 pour PostgreSQL.
    
    Yields:
        sqlite3.Connection | PgConnectionWrapper: La connexion active.
    """
    if USE_PG:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.set_client_encoding('UTF8')
            wrapped = PgConnectionWrapper(conn)
            try:
                yield wrapped
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction DB échouée (PG): {e}")
                raise
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Impossible de se connecter à PostgreSQL: {e}")
            raise
    else:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction DB échouée (SQLite): {e}")
                raise
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Impossible de se connecter à SQLite: {e}")
            raise


def init_db():
    """Crée toutes les tables si elles n'existent pas."""
    with get_db() as conn:
        conn.executescript("""
        -- Codes d'erreurs hexadécimaux
        CREATE TABLE IF NOT EXISTS codes_erreurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            message TEXT DEFAULT '',
            niveau TEXT DEFAULT 'ATTENTION',
            type TEXT DEFAULT 'Hardware',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Solutions associées aux erreurs
        CREATE TABLE IF NOT EXISTS solutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mot_cle TEXT NOT NULL UNIQUE,
            type TEXT DEFAULT 'Hardware',
            priorite TEXT DEFAULT 'MOYENNE',
            cause TEXT DEFAULT '',
            solution TEXT DEFAULT '',
            validated_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Historique des événements (table supprimée, redondant avec 'interventions')

        -- Clients (table dédiée)
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL UNIQUE,
            matricule_fiscale TEXT DEFAULT '',
            ville TEXT DEFAULT '',
            contact TEXT DEFAULT '',
            telephone TEXT DEFAULT '',
            adresse TEXT DEFAULT '',
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Parc d'équipements
        CREATE TABLE IF NOT EXISTS equipements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            type TEXT DEFAULT '',
            fabricant TEXT DEFAULT '',
            modele TEXT DEFAULT '',
            num_serie TEXT DEFAULT '',
            date_installation TEXT DEFAULT '',
            derniere_maintenance TEXT DEFAULT '',
            statut TEXT DEFAULT 'Actif',
            notes TEXT DEFAULT '',
            client TEXT DEFAULT 'Centre Principal',
            UNIQUE(nom, client)
        );

        -- Interventions de maintenance
        CREATE TABLE IF NOT EXISTS interventions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            machine TEXT NOT NULL,
            technicien TEXT DEFAULT '',
            type_intervention TEXT DEFAULT 'Corrective',
            description TEXT DEFAULT '',
            probleme TEXT DEFAULT '',      -- NOUVEAU
            cause TEXT DEFAULT '',         -- NOUVEAU
            solution TEXT DEFAULT '',      -- NOUVEAU
            pieces_utilisees TEXT DEFAULT '',
            cout REAL DEFAULT 0.0,
            cout_pieces REAL DEFAULT 0.0,
            duree_minutes INTEGER DEFAULT 0,
            code_erreur TEXT DEFAULT '',
            statut TEXT DEFAULT 'Terminée',
            notes TEXT DEFAULT '',
            is_temporary INTEGER DEFAULT 0,           -- 1 = intervention enfant temporaire
            parent_intervention_id INTEGER DEFAULT NULL -- ID de l'intervention parent (NULL si parent)
        );

        -- Techniciens (détails étendus)
        CREATE TABLE IF NOT EXISTS techniciens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,  -- Lien optionnel vers utilisateurs
            nom TEXT NOT NULL,
            prenom TEXT NOT NULL,
            specialite TEXT DEFAULT 'Généraliste',
            qualification TEXT DEFAULT '',
            telephone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            dispo INTEGER DEFAULT 1,
            notes TEXT DEFAULT ''
        );

        -- Utilisateurs
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            nom_complet TEXT DEFAULT '',
            role TEXT DEFAULT 'Technicien' CHECK(role IN ('Admin', 'Technicien', 'Lecteur', 'Manager', 'Responsable Technique', 'Gestionnaire')),
            client TEXT DEFAULT '',
            email TEXT DEFAULT '',
            actif INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        -- Journal d'audit
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            username TEXT DEFAULT 'system',
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            page TEXT DEFAULT '',
            ip_address TEXT DEFAULT ''
        );

        -- Audit Trail IA (EU AI Act Article 12)
        CREATE TABLE IF NOT EXISTS ai_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model_version TEXT NOT NULL,
            prompt_hash TEXT DEFAULT '',
            confidence_score INTEGER DEFAULT 0,
            outcome TEXT DEFAULT ''
        );

        -- Feedback sur les prédictions (HITL — Human-in-the-Loop)
        CREATE TABLE IF NOT EXISTS prediction_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            machine TEXT NOT NULL,
            date_predite TEXT NOT NULL,
            resultat TEXT NOT NULL CHECK(resultat IN ('correct', 'faux_positif', 'decale')),
            date_reelle TEXT DEFAULT '',
            note_technicien TEXT DEFAULT '',
            username TEXT DEFAULT 'system'
        );

        -- Planning de maintenance préventive
        CREATE TABLE IF NOT EXISTS planning_maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine TEXT NOT NULL,
            client TEXT DEFAULT '',
            type_maintenance TEXT DEFAULT 'Préventive',
            description TEXT DEFAULT '',
            date_prevue DATE NOT NULL,
            date_realisee DATE,
            technicien_assigne TEXT DEFAULT '',
            statut TEXT DEFAULT 'Planifiée' CHECK(statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard', 'Décalé')),
            rappel_envoye INTEGER DEFAULT 0,
            recurrence TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            is_ghost BOOLEAN DEFAULT false
        );

        -- Pièces de rechange
        CREATE TABLE IF NOT EXISTS pieces_rechange (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL UNIQUE,
            designation TEXT NOT NULL,
            equipement_type TEXT DEFAULT '',
            stock_actuel INTEGER DEFAULT 0,
            stock_minimum INTEGER DEFAULT 1,
            fournisseur TEXT DEFAULT '',
            prix_unitaire REAL DEFAULT 0.0,
            derniere_commande DATE,
            notes TEXT DEFAULT ''
        );

        -- Configuration client (branding)
        CREATE TABLE IF NOT EXISTS config_client (
            cle TEXT PRIMARY KEY,
            valeur TEXT DEFAULT ''
        );

        -- Insérer config par défaut si absente
        INSERT OR IGNORE INTO config_client (cle, valeur) VALUES
            ('nom_organisation', 'SIC Radiologie'),
            ('logo_path', ''),
            ('langue', 'fr'),
            ('theme', 'dark');

        -- Télémétrie IoT
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            machine TEXT NOT NULL,
            sensor_type TEXT NOT NULL,
            value REAL NOT NULL
        );

        -- === PI Isolation (Pillier 2: Data Governance) ===
        -- Table pour les informations personnelles des utilisateurs
        CREATE TABLE IF NOT EXISTS user_pii (
            user_id INTEGER PRIMARY KEY,
            nom_complet TEXT DEFAULT '',
            email TEXT DEFAULT '',
            telephone TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
        );

        -- Table pour les informations personnelles des techniciens
        CREATE TABLE IF NOT EXISTS technicien_pii (
            tech_id INTEGER PRIMARY KEY,
            nom_complet TEXT DEFAULT '',
            email TEXT DEFAULT '',
            telephone TEXT DEFAULT '',
            telegram_id TEXT DEFAULT '',
            FOREIGN KEY (tech_id) REFERENCES techniciens(id) ON DELETE CASCADE
        );

        -- Logs uploadés (Supervision) — content stocké dans S3/MinIO
        CREATE TABLE IF NOT EXISTS logs_uploaded (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipement TEXT NOT NULL,
            filename TEXT NOT NULL,
            s3_key TEXT DEFAULT '',
            content_hash TEXT DEFAULT '',
            size_bytes INTEGER DEFAULT 0,
            nb_errors INTEGER DEFAULT 0,
            nb_critiques INTEGER DEFAULT 0,
            uploaded_by TEXT DEFAULT 'system',
            parsed_errors TEXT DEFAULT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Horaires de notification pour les bots Telegram
        CREATE TABLE IF NOT EXISTS notification_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_key TEXT NOT NULL UNIQUE,
            enabled INTEGER DEFAULT 1,
            hour INTEGER DEFAULT 8,
            minute INTEGER DEFAULT 30,
            days_of_week TEXT DEFAULT '1,2,3,4,5,6,7',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Techniciens assignés à une intervention (junction table pour per-tech data)
        CREATE TABLE IF NOT EXISTS interventions_techniciens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            intervention_id INTEGER NOT NULL,
            technicien_id INTEGER,
            technicien_nom TEXT NOT NULL,
            statut TEXT DEFAULT 'Assigné' CHECK(statut IN ('Assigné', 'En cours', 'Cloturee', 'Refusé')),
            probleme_tech TEXT DEFAULT '',
            cause_tech TEXT DEFAULT '',
            solution_tech TEXT DEFAULT '',
            heure_debut_tech TIME,
            heure_fin_tech TIME,
            duree_minutes_tech INTEGER DEFAULT 0,
            duree_deplacement_tech INTEGER DEFAULT 0,
            notes_tech TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (intervention_id) REFERENCES interventions(id) ON DELETE CASCADE
        );
        """)
        
        # Ajouter les indexes pour améliorer les performances
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_uploaded_equipement ON logs_uploaded(equipement);
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_uploaded_uploaded_at ON logs_uploaded(uploaded_at DESC);
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_uploaded_content_hash ON logs_uploaded(content_hash);
        """)
        
        # Indexes pour la table equipements (améliore les performances de filtrage)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_equipements_client ON equipements(client);
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_equipements_type ON equipements(type);
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_equipements_statut ON equipements(statut);
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_equipements_nom ON equipements(nom);
        """)
        
        # Indexes pour la table interventions (améliore les JOINs)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_interventions_machine ON interventions(machine);
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_interventions_date ON interventions(date DESC);
        """)

        # --- Migrations pour bases existantes (Pillier 3: Logging des migrations) ---
        def _run_migration(sql, description):
            try:
                conn.execute(sql)
                logger.info(f"Migration réussie: {description}")
            except Exception as e:
                # On logue l'erreur mais on continue (souvent dû à une colonne déjà existante)
                logger.debug(f"Migration ignorée ({description}): {e}")

        _run_migration("ALTER TABLE equipements ADD COLUMN client TEXT DEFAULT 'Centre Principal'", "client sur equipements")
        _run_migration("ALTER TABLE techniciens ADD COLUMN telegram_id TEXT DEFAULT ''", "telegram_id sur techniciens")
        _run_migration("ALTER TABLE planning_maintenance ADD COLUMN client TEXT DEFAULT ''", "client sur planning")
        _run_migration("ALTER TABLE utilisateurs ADD COLUMN client TEXT DEFAULT ''", "client sur utilisateurs")
        _run_migration("ALTER TABLE equipements ADD COLUMN domaine TEXT DEFAULT 'Radiologie'", "domaine sur equipements")
        _run_migration("ALTER TABLE equipements ADD COLUMN est_annexe BOOLEAN DEFAULT false", "est_annexe sur equipements")
        _run_migration("ALTER TABLE equipements ADD COLUMN garantie_debut TEXT DEFAULT ''", "garantie_debut sur equipements")
        _run_migration("ALTER TABLE equipements ADD COLUMN garantie_duree INTEGER DEFAULT 0", "garantie_duree sur equipements")
        _run_migration("ALTER TABLE pieces_rechange ADD COLUMN domaine TEXT DEFAULT 'Radiologie'", "domaine sur pieces_rechange")
        _run_migration("ALTER TABLE pieces_rechange ADD COLUMN est_annexe BOOLEAN DEFAULT false", "est_annexe sur pieces_rechange")
        _run_migration("ALTER TABLE logs_uploaded ADD COLUMN parsed_errors TEXT DEFAULT NULL", "parsed_errors sur logs_uploaded")
        
        # Migration: Ghost entry tracking for reschedule feature
        _run_migration("ALTER TABLE planning_maintenance ADD COLUMN is_ghost BOOLEAN DEFAULT false", "is_ghost sur planning_maintenance")

        # Migration : recréer la table avec UNIQUE(nom, client)
        # NOTE: PRAGMA is SQLite-specific, skip for PostgreSQL
        if not USE_PG:
            try:
                indexes = conn.execute("PRAGMA index_list(equipements)").fetchall()
                needs_migration = False
                for idx in indexes:
                    idx_info = conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()
                    if len(idx_info) == 1 and any(col[2] == 'nom' for col in idx_info):
                        needs_migration = True
                        break
                if needs_migration:
                    logger.info("Début migration de la table équipements pour contrainte UNIQUE(nom, client)")
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS equipements_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nom TEXT NOT NULL,
                            type TEXT DEFAULT '',
                            fabricant TEXT DEFAULT '',
                            modele TEXT DEFAULT '',
                            num_serie TEXT DEFAULT '',
                            date_installation TEXT DEFAULT '',
                            derniere_maintenance TEXT DEFAULT '',
                            statut TEXT DEFAULT 'Actif',
                            notes TEXT DEFAULT '',
                            client TEXT DEFAULT 'Centre Principal',
                            UNIQUE(nom, client)
                        );
                        INSERT OR IGNORE INTO equipements_new
                            SELECT id, nom, type, fabricant, modele, num_serie,
                                   date_installation, derniere_maintenance, statut, notes, client
                            FROM equipements;
                        DROP TABLE equipements;
                        ALTER TABLE equipements_new RENAME TO equipements;
                    """)
            except Exception as e:
                logger.error(f"Erreur lors de la migration complexe des équipements: {e}")

        # Migration helper: ajouter colonne si elle n'existe pas (compatible PG + SQLite)
        def _safe_add_column(tbl, col, col_type="TEXT", default="''"):
            """Ajoute une colonne de manière sécurisée sans interrompre le flux."""
            if USE_PG:
                try:
                    cur = conn._conn.cursor()
                    # First check if column already exists
                    cur.execute("""
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = %s
                    """, (tbl, col))
                    column_exists = cur.fetchone() is not None
                    
                    if not column_exists:
                        # Column doesn't exist, add it
                        cur.execute(
                            f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type} DEFAULT {default}"
                        )
                        conn._conn.commit()
                        logger.info(f"✅ Colonne {col} ajoutée à {tbl}")
                    else:
                        logger.debug(f"ℹ️  Colonne {col} déjà présente sur {tbl}")
                except Exception as e:
                    try:
                        conn._conn.rollback()
                    except Exception:
                        pass
                    logger.debug(f"⚠️  Erreur lors de l'ajout de {col} à {tbl}: {e}")
            else:
                try:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type} DEFAULT {default}")
                    logger.info(f"✅ Colonne {col} ajoutée à {tbl}")
                except Exception as e:
                    logger.debug(f"ℹ️  Colonne {col} déjà présente sur {tbl} (SQLite)")  # Attendu si déjà là


        # Migrations : colonnes ajoutées progressivement
        _safe_add_column("equipements", "matricule_fiscale")
        _safe_add_column("interventions", "date_debut_intervention", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "date_cloture", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "type_erreur")
        _safe_add_column("interventions", "priorite")
        _safe_add_column("contrats", "equipement")
        _safe_add_column("contrats", "fichier_contrat")
        _safe_add_column("equipements", "document_technique")
        # Geographic coordinates for map feature
        _safe_add_column("equipements", "latitude", "REAL", "NULL")
        _safe_add_column("equipements", "longitude", "REAL", "NULL")
        _safe_add_column("equipements", "adresse")
        _safe_add_column("equipements", "ville")
        _safe_add_column("equipements", "region")

        # Client enrichment columns
        _safe_add_column("clients", "code_client")
        _safe_add_column("clients", "region")
        _safe_add_column("clients", "type_client")
        _safe_add_column("clients", "international", "BOOLEAN", "false")

        # Service column on equipements
        _safe_add_column("equipements", "service")

        # Contract → Planning auto-generation columns
        _safe_add_column("contrats", "recurrence_maintenance")
        _safe_add_column("contrats", "date_premiere_maintenance")
        _safe_add_column("planning_maintenance", "contrat_id", "INTEGER", "NULL")

        # Ghost entry tracking for reschedule feature (prevent duplicates on multiple reschedules)
        _safe_add_column("planning_maintenance", "original_planning_id", "INTEGER", "NULL")

        # User profile & page permissions (used by admin panel)
        _safe_add_column("utilisateurs", "profil")
        _safe_add_column("utilisateurs", "pages_autorisees")

        # Notification schedules table migration (create if not exists)
        try:
            if USE_PG:
                # PostgreSQL syntax with SERIAL PRIMARY KEY
                conn.execute("""
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
            else:
                # SQLite syntax
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS notification_schedules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            logger.info("✅ Table notification_schedules créée ou déjà existante")
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.debug(f"⚠️  Erreur lors de la création de notification_schedules: {e}")


        # Technicien enrichment columns
        _safe_add_column("techniciens", "niveau_competence")

        # Travel time column on interventions
        _safe_add_column("interventions", "duree_deplacement", "INTEGER", "0")
        _safe_add_column("interventions", "is_temporary", "INTEGER", "0")
        _safe_add_column("interventions", "parent_intervention_id", "INTEGER", "NULL")

        # Interventions_techniciens table migration (per-technician tracking)
        try:
            if USE_PG:
                # PostgreSQL syntax
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS interventions_techniciens (
                        id SERIAL PRIMARY KEY,
                        intervention_id INTEGER NOT NULL,
                        technicien_id INTEGER,
                        technicien_nom TEXT NOT NULL,
                        statut TEXT DEFAULT 'Assigné' CHECK(statut IN ('Assigné', 'En cours', 'Cloturee', 'Refusé')),
                        probleme_tech TEXT DEFAULT '',
                        cause_tech TEXT DEFAULT '',
                        solution_tech TEXT DEFAULT '',
                        heure_debut_tech TIME,
                        heure_fin_tech TIME,
                        duree_minutes_tech INTEGER DEFAULT 0,
                        duree_deplacement_tech INTEGER DEFAULT 0,
                        notes_tech TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (intervention_id) REFERENCES interventions(id) ON DELETE CASCADE
                    )
                """)
            else:
                # SQLite syntax
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS interventions_techniciens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        intervention_id INTEGER NOT NULL,
                        technicien_id INTEGER,
                        technicien_nom TEXT NOT NULL,
                        statut TEXT DEFAULT 'Assigné' CHECK(statut IN ('Assigné', 'En cours', 'Cloturee', 'Refusé')),
                        probleme_tech TEXT DEFAULT '',
                        cause_tech TEXT DEFAULT '',
                        solution_tech TEXT DEFAULT '',
                        heure_debut_tech TIME,
                        heure_fin_tech TIME,
                        duree_minutes_tech INTEGER DEFAULT 0,
                        duree_deplacement_tech INTEGER DEFAULT 0,
                        notes_tech TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (intervention_id) REFERENCES interventions(id) ON DELETE CASCADE
                    )
                """)
            # Create index for faster queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_int_tech_intervention_id ON interventions_techniciens(intervention_id)")
            conn.commit()
            logger.info("✅ Table interventions_techniciens créée ou déjà existante")
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.debug(f"⚠️  Erreur lors de la création de interventions_techniciens: {e}")

        # Ensure commit after all _safe_add_column migrations
        try:
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass



        # Fabricants table
        if USE_PG:
            try:
                cur = conn._conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fabricants (
                        id SERIAL PRIMARY KEY,
                        nom TEXT UNIQUE NOT NULL
                    )
                """)
                conn._conn.commit()
            except Exception:
                try: conn._conn.rollback()
                except Exception: pass
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS fabricants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT UNIQUE NOT NULL
            )
            """)

        # Custom equipment types table (per domain)
        if USE_PG:
            try:
                cur = conn._conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS types_equipement_custom (
                        id SERIAL PRIMARY KEY,
                        nom TEXT NOT NULL,
                        domaine TEXT NOT NULL DEFAULT '',
                        UNIQUE(nom, domaine)
                    )
                """)
                conn._conn.commit()
            except Exception:
                try: conn._conn.rollback()
                except Exception: pass
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS types_equipement_custom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                domaine TEXT NOT NULL DEFAULT '',
                UNIQUE(nom, domaine)
            )
            """)

        # Custom intervention types table
        if USE_PG:
            try:
                cur = conn._conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS types_intervention_custom (
                        id SERIAL PRIMARY KEY,
                        nom TEXT UNIQUE NOT NULL
                    )
                """)
                conn._conn.commit()
            except Exception:
                try: conn._conn.rollback()
                except Exception: pass
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS types_intervention_custom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT UNIQUE NOT NULL
            )
            """)

        # Table Domaines Personnalisés (Médical)
        if USE_PG:
            try:
                cur = conn._conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS domaines_custom (
                        id SERIAL PRIMARY KEY,
                        nom TEXT UNIQUE NOT NULL,
                        date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn._conn.commit()
            except Exception:
                try:
                    conn._conn.rollback()
                except Exception:
                    pass
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS domaines_custom (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT UNIQUE NOT NULL,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

        # Table Documents Techniques (séparée pour éviter les timeouts sur gros fichiers)
        if USE_PG:
            try:
                cur = conn._conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS documents_techniques (
                        id SERIAL PRIMARY KEY,
                        equipement_id INTEGER NOT NULL,
                        nom_fichier TEXT NOT NULL,
                        contenu_base64 TEXT NOT NULL,
                        date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (equipement_id) REFERENCES equipements(id)
                    )
                """)
                conn._conn.commit()
            except Exception:
                try:
                    conn._conn.rollback()
                except Exception:
                    pass
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS documents_techniques (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipement_id INTEGER NOT NULL,
                nom_fichier TEXT NOT NULL,
                contenu_base64 TEXT NOT NULL,
                date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (equipement_id) REFERENCES equipements(id)
            )
            """)

        # Table Contrats / SLA
        conn.execute("""
        CREATE TABLE IF NOT EXISTS contrats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client TEXT NOT NULL,
            equipement TEXT,
            type_contrat TEXT DEFAULT 'Standard',
            date_debut DATE NOT NULL,
            date_fin DATE NOT NULL,
            sla_temps_reponse_h INTEGER DEFAULT 24,
            interventions_incluses INTEGER DEFAULT -1,
            montant REAL DEFAULT 0.0,
            conditions TEXT DEFAULT '',
            statut TEXT DEFAULT 'Actif',
            notes TEXT DEFAULT '',
            pieces_incluses TEXT DEFAULT '',
            avec_pieces INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Junction Table: Contrats ↔ Equipements (multi-equipment support)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS contrats_equipements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contrat_id INTEGER NOT NULL,
            equipement_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contrat_id) REFERENCES contrats(id) ON DELETE CASCADE,
            FOREIGN KEY (equipement_id) REFERENCES equipements(id) ON DELETE RESTRICT,
            UNIQUE(contrat_id, equipement_id)
        )
        """)

        # Table Conformité / QHSE
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conformite (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipement TEXT NOT NULL,
            client TEXT DEFAULT '',
            type_controle TEXT NOT NULL,
            description TEXT DEFAULT '',
            date_controle DATE NOT NULL,
            date_expiration DATE NOT NULL,
            fichier_nom TEXT DEFAULT '',
            fichier_data BLOB,
            statut TEXT DEFAULT 'Conforme',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Table Demandes d'intervention
        conn.execute("""
        CREATE TABLE IF NOT EXISTS demandes_intervention (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            intervention_id INTEGER
        )
        """)

        # Table Notifications pièces (cross-app SIC Terrain ↔ SIC Radiologie)
        if USE_PG:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications_pieces (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                intervention_id INTEGER,
                piece_reference TEXT,
                piece_nom TEXT,
                intervention_ref TEXT,
                equipement TEXT,
                client TEXT,
                technicien TEXT,
                message TEXT,
                source TEXT NOT NULL DEFAULT '',
                destination TEXT NOT NULL,
                statut TEXT DEFAULT 'non_lu',
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_lecture TIMESTAMP,
                date_traitement TIMESTAMP
            )
            """)
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications_pieces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                intervention_id INTEGER,
                piece_reference TEXT,
                piece_nom TEXT,
                intervention_ref TEXT,
                equipement TEXT,
                client TEXT,
                technicien TEXT,
                message TEXT,
                source TEXT NOT NULL DEFAULT '',
                destination TEXT NOT NULL,
                statut TEXT DEFAULT 'non_lu',
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_lecture TIMESTAMP,
                date_traitement TIMESTAMP
            )
            """)

        # Table Pièces demandées (non référencées) par les techniciens
        if USE_PG:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS pieces_demandees (
                id SERIAL PRIMARY KEY,
                reference TEXT NOT NULL,
                designation TEXT NOT NULL DEFAULT '',
                intervention_id INTEGER,
                equipement TEXT DEFAULT '',
                client TEXT DEFAULT '',
                technicien TEXT DEFAULT '',
                probleme TEXT DEFAULT '',
                statut TEXT DEFAULT 'en_attente',
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_resolution TIMESTAMP
            )
            """)
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS pieces_demandees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL,
                designation TEXT NOT NULL DEFAULT '',
                intervention_id INTEGER,
                equipement TEXT DEFAULT '',
                client TEXT DEFAULT '',
                technicien TEXT DEFAULT '',
                probleme TEXT DEFAULT '',
                statut TEXT DEFAULT 'en_attente',
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_resolution TIMESTAMP
            )
            """)
        # Migration: ajouter colonne probleme si elle n'existe pas
        try:
            conn.execute("ALTER TABLE pieces_demandees ADD COLUMN IF NOT EXISTS probleme TEXT DEFAULT ''")
        except Exception:
            pass

        # --- Migration PII (Pillier 2: Privacy by Design) ---
        try:
            # Transférer nom_complet et email de utilisateurs vers user_pii
            conn.execute("""
                INSERT OR IGNORE INTO user_pii (user_id, nom_complet, email)
                SELECT id, nom_complet, email FROM utilisateurs
                WHERE nom_complet != '' OR email != ''
            """)
            # Transférer nom, prenom, email de techniciens vers technicien_pii
            # Note: on concatène nom et prenom pour nom_complet si besoin
            # Use COALESCE for PostgreSQL compatibility (IFNULL is SQLite-only)
            if USE_PG:
                conn.execute("""
                    INSERT INTO technicien_pii (tech_id, nom_complet, email, telegram_id)
                    SELECT id, (COALESCE(nom, '') || ' ' || COALESCE(prenom, '')), email, telegram_id FROM techniciens
                    WHERE nom != '' OR email != ''
                    ON CONFLICT DO NOTHING
                """)
            else:
                conn.execute("""
                    INSERT OR IGNORE INTO technicien_pii (tech_id, nom_complet, email, telegram_id)
                    SELECT id, (IFNULL(nom, '') || ' ' || IFNULL(prenom, '')), email, telegram_id FROM techniciens
                    WHERE nom != '' OR email != ''
                """)
            logger.info("Audit Trail: Migration PII effectuée avec succès.")
        except Exception as e:
            logger.debug(f"Migration PII ignorée (Pillar 2): {e}")

        # --- Migration: Update CHECK constraint for utilisateurs.role ---
        # Add new roles: 'Responsable Technique' and 'Gestionnaire'
        if USE_PG:
            try:
                # Drop old constraint if exists
                conn.execute("ALTER TABLE utilisateurs DROP CONSTRAINT IF EXISTS utilisateurs_role_check")
                # Add new constraint with all roles
                conn.execute("""
                    ALTER TABLE utilisateurs ADD CONSTRAINT utilisateurs_role_check 
                    CHECK(role IN ('Admin', 'Technicien', 'Lecteur', 'Manager', 'Responsable Technique', 'Gestionnaire'))
                """)
                conn.commit()
                logger.info("✅ Migration réussie: utilisateurs role constraint updated with Responsable Technique + Gestionnaire roles")
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.info(f"Migration ignorée (utilisateurs role check): {e}")

        # --- Migration: Update CHECK constraint for planning_maintenance.statut to include "Décalé" ---
        # This allows reschedule feature to mark original date entries as "Décalé" (ghosted)
        if USE_PG:
            try:
                # Check if "Décalé" is already in the constraint
                cur = conn._conn.cursor()
                cur.execute("""
                    SELECT check_clause FROM information_schema.check_constraints 
                    WHERE constraint_name LIKE 'planning_maintenance%'
                """)
                result = cur.fetchone()
                
                if result:
                    check_clause = result[0]
                    if check_clause and 'Décalé' not in check_clause:
                        # "Décalé" not in constraint, need to update it
                        cur.execute("SELECT constraint_name FROM information_schema.check_constraints WHERE constraint_name LIKE 'planning_maintenance%'")
                        constraint_name = cur.fetchone()[0]
                        conn.execute(f"ALTER TABLE planning_maintenance DROP CONSTRAINT {constraint_name}")
                        conn.execute("""
                            ALTER TABLE planning_maintenance 
                            ADD CONSTRAINT planning_maintenance_statut_check 
                            CHECK (statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard', 'Décalé'))
                        """)
                        conn.commit()
                        logger.info("✅ Migration réussie: planning_maintenance statut constraint updated with 'Décalé' status")
                    elif check_clause and 'Décalé' in check_clause:
                        logger.info("ℹ️  'Décalé' already in planning_maintenance statut constraint")
                else:
                    # No constraint found, create it
                    conn.execute("""
                        ALTER TABLE planning_maintenance 
                        ADD CONSTRAINT planning_maintenance_statut_check 
                        CHECK (statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard', 'Décalé'))
                    """)
                    conn.commit()
                    logger.info("✅ Migration réussie: planning_maintenance statut constraint created with 'Décalé' status")
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.debug(f"⚠️  Migration planning_maintenance statut check: {e}")


        # --- Migration: Populate contrats_equipements from existing contrats.equipement ---
        # This is a one-time migration that safely populates the junction table from legacy data
        try:
            if USE_PG:
                # PostgreSQL version - join with equipements table to get the ID
                conn.execute("""
                    INSERT INTO contrats_equipements (contrat_id, equipement_id, created_at)
                    SELECT c.id, e.id, c.created_at FROM contrats c
                    LEFT JOIN equipements e ON e.nom = c.equipement
                    WHERE c.equipement IS NOT NULL AND c.equipement != ''
                    ON CONFLICT (contrat_id, equipement_id) DO NOTHING
                """)
            else:
                # SQLite version
                conn.execute("""
                    INSERT OR IGNORE INTO contrats_equipements (contrat_id, equipement_id, created_at)
                    SELECT c.id, e.id, c.created_at FROM contrats c
                    LEFT JOIN equipements e ON e.nom = c.equipement
                    WHERE c.equipement IS NOT NULL AND c.equipement != ''
                """)
            logger.info("✅ Migration réussie: contrats_equipements peuplée depuis contrats.equipement")
        except Exception as e:
            logger.debug(f"Migration contrats_equipements ignorée: {e}")

        # --- Migration: Add pieces_incluses and avec_pieces columns to contrats if not exist ---
        try:
            if USE_PG:
                # PostgreSQL: Try to add columns if they don't exist
                conn.execute("ALTER TABLE contrats ADD COLUMN IF NOT EXISTS pieces_incluses TEXT DEFAULT ''")
                conn.execute("ALTER TABLE contrats ADD COLUMN IF NOT EXISTS avec_pieces INTEGER DEFAULT 0")
            else:
                # SQLite: Check if columns exist, add if not
                cursor = conn.execute("PRAGMA table_info(contrats)")
                existing_cols = {row[1] for row in cursor.fetchall()}
                if "pieces_incluses" not in existing_cols:
                    conn.execute("ALTER TABLE contrats ADD COLUMN pieces_incluses TEXT DEFAULT ''")
                if "avec_pieces" not in existing_cols:
                    conn.execute("ALTER TABLE contrats ADD COLUMN avec_pieces INTEGER DEFAULT 0")
            logger.info("✅ Migration réussie: colonnes pieces_incluses et avec_pieces ajoutées à contrats")
        except Exception as e:
            logger.debug(f"Migration colonnes pièces ignorée: {e}")


# ---- Nettoyage texte double-encodé UTF-8 (à la lecture) ----

_ENCODING_MAP = {
    "Ã©": "é", "Ã¨": "è", "Ãª": "ê", "Ã«": "ë",
    "Ã ": "à", "Ã¢": "â", "Ã¤": "ä",
    "Ã¹": "ù", "Ã»": "û", "Ã¼": "ü",
    "Ã®": "î", "Ã¯": "ï", "Ã´": "ô", "Ã¶": "ö",
    "Ã§": "ç", "Ã‰": "É", "Ãˆ": "È", "Ã€": "À",
    "\u00c3\u0094": "Ô", "\u00c3\u009b": "Û",
}

def _fix_text(val):
    """Corrige un texte double-encodé UTF-8 → UTF-8 correct."""
    if not isinstance(val, str):
        return val
    for broken, correct in _ENCODING_MAP.items():
        if broken in val:
            val = val.replace(broken, correct)
    # Fallback: essayer decode latin1 → utf8
    try:
        val_bytes = val.encode('latin-1')
        decoded = val_bytes.decode('utf-8')
        if decoded != val:
            return decoded
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return val

def _fix_df_text(df, columns=None):
    """Applique _fix_text sur les colonnes texte d'un DataFrame."""
    if df.empty:
        return df
    cols = columns or [c for c in df.columns if df[c].dtype == 'object']
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: _fix_text(v) if isinstance(v, str) else v)
    return df


def lire_historique():
    """
    Lit l'historique complet des pannes.
    
    Returns:
        pd.DataFrame: DataFrame contenant l'historique avec colonnes renommées.
    """
    try:
        with get_db() as conn:
            df = read_sql("SELECT * FROM historique ORDER BY date DESC", conn)
        if not df.empty:
            rename_map = {
                "machine": "Machine", "code": "Code", "type": "Type",
                "severite": "Severite", "resolu": "Resolu",
            }
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
            if "date" in df.columns:
                df["Date"] = pd.to_datetime(df["date"], errors="coerce")
            df = _fix_df_text(df)
        return df
    except Exception as e:
        logger.error(f"Erreur lire_historique: {e}")
        return pd.DataFrame()


# ==========================================
# FONCTIONS CRUD — CODES & SOLUTIONS
# ==========================================

def lire_base():
    """Lit les codes et solutions. Retourne (hex_db, sol_db) — même format qu'avant."""
    hex_db = {}
    sol_db = {}

    with get_db() as conn:
        # Codes
        for row in conn.execute("SELECT code, message, niveau, type FROM codes_erreurs").fetchall():
            hex_db[row["code"]] = {
                "Msg": row["message"],
                "Level": row["niveau"],
                "Type": row["type"],
            }

        # Solutions
        for row in conn.execute("SELECT mot_cle, type, priorite, cause, solution FROM solutions").fetchall():
            sol_db[row["mot_cle"]] = {
                "Type": row["type"],
                "Priorité": row["priorite"],
                "Cause": row["cause"],
                "Solution": row["solution"],
            }

    return hex_db, sol_db


def ajouter_code(code, message, cause, solution, type_err, priorite, username="system"):
    """Ajoute ou met à jour un code d'erreur et sa solution."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO codes_erreurs (code, message, type)
            VALUES (?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET message=excluded.message, type=excluded.type
        """, (code, message[:200], type_err))

        conn.execute("""
            INSERT INTO solutions (mot_cle, type, priorite, cause, solution, validated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mot_cle) DO UPDATE SET
                type=excluded.type, priorite=excluded.priorite,
                cause=excluded.cause, solution=excluded.solution,
                validated_by=excluded.validated_by, updated_at=excluded.updated_at
        """, (code, type_err, priorite, cause, solution, username, datetime.now().isoformat()))

    return True


def ajouter_codes_batch(rows_hex, rows_txt):
    """Ajoute des codes en lot."""
    with get_db() as conn:
        for row in rows_hex:
            conn.execute("""
                INSERT INTO codes_erreurs (code, message, niveau, type)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET message=excluded.message, niveau=excluded.niveau, type=excluded.type
            """, (row.get("Code", ""), row.get("Message", ""), row.get("Niveau", "ATTENTION"), row.get("Type", "")))

        for row in rows_txt:
            conn.execute("""
                INSERT INTO solutions (mot_cle, type, priorite, cause, solution)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(mot_cle) DO UPDATE SET
                    type=excluded.type, priorite=excluded.priorite,
                    cause=excluded.cause, solution=excluded.solution
            """, (row.get("Mot_Cle", ""), row.get("Type", ""), row.get("Priorite", "MOYENNE"),
                  row.get("Cause", ""), row.get("Solution", "")))

    return True


# Historique supprimé au profit de la table interventions.


# ==========================================
# FONCTIONS CRUD — CLIENTS
# ==========================================

def lire_clients():
    """Récupère la liste des clients."""
    try:
        with get_db() as conn:
            df = read_sql("SELECT * FROM clients ORDER BY nom", conn)
        if not df.empty:
            df = _fix_df_text(df)
        return df
    except Exception as e:
        logger.error(f"Erreur lire_clients: {e}")
        return pd.DataFrame()


def ajouter_client(client_dict):
    """Ajoute un nouveau client."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO clients (nom, matricule_fiscale, ville, contact, telephone, adresse,
                                code_client, region, type_client, international)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nom) DO UPDATE SET
                matricule_fiscale=excluded.matricule_fiscale,
                ville=excluded.ville,
                contact=excluded.contact,
                telephone=excluded.telephone,
                adresse=excluded.adresse,
                code_client=excluded.code_client,
                region=excluded.region,
                type_client=excluded.type_client,
                international=excluded.international
        """, (
            client_dict.get("nom", ""),
            client_dict.get("matricule_fiscale", ""),
            client_dict.get("ville", ""),
            client_dict.get("contact", ""),
            client_dict.get("telephone", ""),
            client_dict.get("adresse", ""),
            client_dict.get("code_client", ""),
            client_dict.get("region", ""),
            client_dict.get("type_client", ""),
            bool(client_dict.get("international", False)),
        ))
    _trigger_backup()
    return True


def modifier_client(client_id, client_dict):
    """Modifie un client existant."""
    with get_db() as conn:
        conn.execute("""
            UPDATE clients SET
                nom = ?, matricule_fiscale = ?, ville = ?,
                contact = ?, telephone = ?, adresse = ?,
                code_client = ?, region = ?, type_client = ?, international = ?
            WHERE id = ?
        """, (
            client_dict.get("nom", ""),
            client_dict.get("matricule_fiscale", ""),
            client_dict.get("ville", ""),
            client_dict.get("contact", ""),
            client_dict.get("telephone", ""),
            client_dict.get("adresse", ""),
            client_dict.get("code_client", ""),
            client_dict.get("region", ""),
            client_dict.get("type_client", ""),
            bool(client_dict.get("international", False)),
            client_id,
        ))
    _trigger_backup()
    return True


def supprimer_client(client_id):
    """Supprime un client par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    _trigger_backup()
    return True


def migrer_clients_depuis_equipements():
    """Auto-import existing clients from equipements table into the clients table."""
    try:
        with get_db() as conn:
            existing = conn.execute("SELECT COUNT(*) as cnt FROM clients").fetchone()
            if existing and dict(existing).get("cnt", 0) > 0:
                return  # Already migrated
            rows = conn.execute("""
                SELECT DISTINCT client, matricule_fiscale, ville
                FROM equipements
                WHERE client IS NOT NULL AND client != ''
            """).fetchall()
            for row in rows:
                r = dict(row)
                nom = r.get("client", "")
                if not nom:
                    continue
                conn.execute("""
                    INSERT OR IGNORE INTO clients (nom, matricule_fiscale, ville)
                    VALUES (?, ?, ?)
                """, (nom, r.get("matricule_fiscale", ""), r.get("ville", "")))
            logger.info(f"Migré {len(rows)} clients depuis equipements")
    except Exception as e:
        logger.error(f"Migration clients: {e}")


# ==========================================
# FONCTIONS CRUD — ÉQUIPEMENTS
# ==========================================

def lire_equipements():
    """
    Récupère la liste complète des équipements du parc.
    
    Logic:
        Exécute SELECT, renomme les colonnes pour la compatibilité UI,
        gère la valeur par défaut pour le client et nettoie l'encodage texte.
        
    Returns:
        pd.DataFrame: Liste des équipements.
    """
    try:
        with get_db() as conn:
            # Select only necessary columns to reduce data transfer and processing
            df = read_sql("""
                SELECT id, nom, type, fabricant, modele, num_serie, 
                       date_installation, derniere_maintenance, statut, notes, 
                       client, domaine, est_annexe, garantie_debut, garantie_duree
                FROM equipements 
                ORDER BY client, nom
            """, conn)
        if not df.empty:
            rename_map = {
                "nom": "Nom", "type": "Type", "fabricant": "Fabricant",
                "modele": "Modele", "num_serie": "NumSerie",
                "date_installation": "DateInstallation",
                "derniere_maintenance": "DernieresMaintenance",
                "statut": "Statut", "notes": "Notes",
                "client": "Client", "ville": "Ville", "region": "Region",
            }
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
            if "Client" in df.columns:
                df["Client"] = df["Client"].fillna("Centre Principal")
            # Only fix text on columns that are likely to have encoding issues
            text_columns = ["Nom", "Type", "Fabricant", "Modele", "Notes", "Client"]
            df = _fix_df_text(df, columns=text_columns)
        return df
    except Exception as e:
        logger.error(f"Erreur lire_equipements: {e}")
        return pd.DataFrame()


def chercher_client_par_matricule(matricule_fiscale):
    """Cherche un client existant par sa matricule fiscale. Retourne le nom du client ou None."""
    if not matricule_fiscale or not matricule_fiscale.strip():
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT client FROM equipements WHERE matricule_fiscale = ? LIMIT 1",
            (matricule_fiscale.strip(),)
        ).fetchone()
        if row:
            return row["client"]
    return None


def ajouter_equipement(equipement_dict):
    """Ajoute un équipement au parc. Unique par combinaison (nom + client)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO equipements (nom, type, fabricant, modele, num_serie,
                                     date_installation, derniere_maintenance, statut, notes,
                                     client, matricule_fiscale, document_technique,
                                     domaine, est_annexe, garantie_debut, garantie_duree, ville, region, service)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nom, client) DO UPDATE SET
                type=excluded.type, fabricant=excluded.fabricant, modele=excluded.modele,
                num_serie=excluded.num_serie, date_installation=excluded.date_installation,
                derniere_maintenance=excluded.derniere_maintenance, statut=excluded.statut,
                notes=excluded.notes, matricule_fiscale=excluded.matricule_fiscale,
                document_technique=excluded.document_technique,
                domaine=excluded.domaine, est_annexe=excluded.est_annexe,
                garantie_debut=excluded.garantie_debut, garantie_duree=excluded.garantie_duree,
                ville=excluded.ville, region=excluded.region, service=excluded.service
        """, (
            equipement_dict.get("Nom", ""),
            equipement_dict.get("Type", ""),
            equipement_dict.get("Fabricant", ""),
            equipement_dict.get("Modele", ""),
            equipement_dict.get("NumSerie", ""),
            equipement_dict.get("DateInstallation", ""),
            equipement_dict.get("DernieresMaintenance", ""),
            equipement_dict.get("Statut", "Actif"),
            equipement_dict.get("Notes", ""),
            equipement_dict.get("Client", "Centre Principal"),
            equipement_dict.get("MatriculeFiscale", ""),
            equipement_dict.get("DocumentTechnique", ""),
            equipement_dict.get("Domaine", "Radiologie"),
            bool(equipement_dict.get("EstAnnexe", False)),
            equipement_dict.get("GarantieDebut", ""),
            int(equipement_dict.get("GarantieDuree", 0) or 0),
            equipement_dict.get("Ville", ""),
            equipement_dict.get("Region", ""),
            equipement_dict.get("Service", ""),
        ))
    _trigger_backup()
    return True


def supprimer_equipement(equip_id):
    """Supprime un équipement par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM equipements WHERE id = ?", (equip_id,))
    _trigger_backup()
    return True


def modifier_equipement(equip_id, equipement_dict):
    """Modifie un équipement existant par son ID."""
    with get_db() as conn:
        conn.execute("""
            UPDATE equipements SET
                nom = ?, type = ?, fabricant = ?, modele = ?, num_serie = ?,
                date_installation = ?, derniere_maintenance = ?, statut = ?,
                notes = ?, client = ?, matricule_fiscale = ?, document_technique = ?,
                domaine = ?, est_annexe = ?, garantie_debut = ?, garantie_duree = ?,
                ville = ?, region = ?, service = ?
            WHERE id = ?
        """, (
            equipement_dict.get("Nom", ""),
            equipement_dict.get("Type", ""),
            equipement_dict.get("Fabricant", ""),
            equipement_dict.get("Modele", ""),
            equipement_dict.get("NumSerie", ""),
            equipement_dict.get("DateInstallation", ""),
            equipement_dict.get("DernieresMaintenance", ""),
            equipement_dict.get("Statut", "Actif"),
            equipement_dict.get("Notes", ""),
            equipement_dict.get("Client", "Centre Principal"),
            equipement_dict.get("MatriculeFiscale", ""),
            equipement_dict.get("DocumentTechnique", ""),
            equipement_dict.get("Domaine", "Radiologie"),
            bool(equipement_dict.get("EstAnnexe", False)),
            equipement_dict.get("GarantieDebut", ""),
            int(equipement_dict.get("GarantieDuree", 0) or 0),
            equipement_dict.get("Ville", ""),
            equipement_dict.get("Region", ""),
            equipement_dict.get("Service", ""),
            equip_id,
        ))
    _trigger_backup()
    return True


def lire_fabricants():
    """Retourne la liste des fabricants enregistrés."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, nom FROM fabricants ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_fabricant(nom):
    """Ajoute un fabricant. Ignore si déjà existant."""
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO fabricants (nom) VALUES (?)", (nom.strip(),))
    return True


def lire_types_equipement_custom(domaine=""):
    """Retourne la liste des types d'équipement personnalisés pour un domaine."""
    with get_db() as conn:
        ph = "%s" if USE_PG else "?"
        rows = conn.execute(
            f"SELECT id, nom, domaine FROM types_equipement_custom WHERE domaine = {ph} ORDER BY nom",
            (domaine,)
        ).fetchall()
        return [dict(r) for r in rows]


def ajouter_type_equipement_custom(nom, domaine=""):
    """Ajoute un type d'équipement personnalisé. Ignore si déjà existant pour ce domaine."""
    with get_db() as conn:
        if USE_PG:
            conn.execute(
                "INSERT INTO types_equipement_custom (nom, domaine) VALUES (%s, %s) ON CONFLICT (nom, domaine) DO NOTHING",
                (nom.strip(), domaine)
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO types_equipement_custom (nom, domaine) VALUES (?, ?)",
                (nom.strip(), domaine)
            )
    return True


def lire_types_intervention_custom():
    """Retourne la liste des types d'intervention personnalisés."""
    with get_db() as conn:
        ph = "%s" if USE_PG else "?"
        rows = conn.execute("SELECT id, nom FROM types_intervention_custom ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_type_intervention_custom(nom):
    """Ajoute un type d'intervention personnalisé. Ignore si déjà existant."""
    ph = "%s" if USE_PG else "?"
    with get_db() as conn:
        if USE_PG:
            conn.execute(f"INSERT INTO types_intervention_custom (nom) VALUES ({ph}) ON CONFLICT (nom) DO NOTHING", (nom.strip(),))
        else:
            conn.execute(f"INSERT OR IGNORE INTO types_intervention_custom (nom) VALUES ({ph})", (nom.strip(),))
    return True


def lire_domaines_custom():
    """Retourne la liste des domaines médicaux personnalisés."""
    with get_db() as conn:
        ph = "%s" if USE_PG else "?"
        rows = conn.execute("SELECT id, nom FROM domaines_custom ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_domaine_custom(nom):
    """Ajoute un domaine médical personnalisé. Ignore si déjà existant."""
    ph = "%s" if USE_PG else "?"
    with get_db() as conn:
        if USE_PG:
            conn.execute(f"INSERT INTO domaines_custom (nom) VALUES ({ph}) ON CONFLICT (nom) DO NOTHING", (nom.strip(),))
        else:
            conn.execute(f"INSERT OR IGNORE INTO domaines_custom (nom) VALUES ({ph})", (nom.strip(),))
    return True


def supprimer_domaine_custom(nom):
    """Supprime un domaine médical personnalisé et ses types associés."""
    with get_db() as conn:
        # Supprimer les types d'équipement associés au domaine
        conn.execute("DELETE FROM types_equipement_custom WHERE domaine = ?", (nom.strip(),))
        # Supprimer le domaine
        conn.execute("DELETE FROM domaines_custom WHERE nom = ?", (nom.strip(),))
    return True


def lire_equipement_par_id(equip_id):
    """Lit un équipement par son ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM equipements WHERE id = ?", (equip_id,)).fetchone()
        if row:
            return dict(row)
    return None


# ==========================================
# FONCTIONS CRUD — DOCUMENTS TECHNIQUES
# ==========================================

def ajouter_document_technique(equipement_id, nom_fichier, contenu_base64):
    """Ajoute un document technique pour un équipement (un par un pour éviter les timeouts)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO documents_techniques (equipement_id, nom_fichier, contenu_base64)
            VALUES (?, ?, ?)
        """, (equipement_id, nom_fichier, contenu_base64))
    return True


def lire_documents_techniques(equipement_id):
    """Lit les documents techniques d'un équipement (métadonnées sans contenu pour la perf)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nom_fichier, date_ajout FROM documents_techniques WHERE equipement_id = ? ORDER BY date_ajout DESC",
            (equipement_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def lire_document_technique_contenu(doc_id):
    """Lit le contenu base64 d'un document technique par son ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT contenu_base64, nom_fichier FROM documents_techniques WHERE id = ?",
            (doc_id,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def supprimer_document_technique(doc_id):
    """Supprime un document technique par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM documents_techniques WHERE id = ?", (doc_id,))
    return True


def lire_tous_documents_techniques():
    """Lit tous les documents techniques avec les infos de l'équipement associé."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT d.id, d.nom_fichier, d.date_ajout, d.equipement_id,
                   e.nom AS equipement_nom, e.fabricant, e.modele, e.type AS equipement_type,
                   e.client
            FROM documents_techniques d
            JOIN equipements e ON d.equipement_id = e.id
            ORDER BY d.date_ajout DESC
        """).fetchall()
        return [dict(r) for r in rows]


# ==========================================
# FONCTIONS CRUD — INTERVENTIONS
# ==========================================

def lire_interventions(machine=None):
    """Lit les interventions, optionnellement filtrées par machine. Inclut le client via JOIN.
    Note: fiche_photo_data (BYTEA) est exclu intentionnellement pour éviter les erreurs de sérialisation JSON.
    Utiliser GET /api/interventions/{id}/fiche pour télécharger la photo."""
    with get_db() as conn:
        # Use JOIN instead of subquery to avoid N+1 pattern
        # Select only necessary columns to reduce data transfer
        # Note: start_time, end_time are TIME columns for shift tracking
        base_query = """
            SELECT i.id, i.date, i.machine, i.technicien, i.type_intervention,
                   i.description, i.probleme, i.cause, i.solution,
                   i.pieces_utilisees, i.cout, i.cout_pieces, i.duree_minutes,
                   i.duree_deplacement,
                   i.code_erreur, i.statut, i.notes,
                   i.date_debut_intervention, i.date_cloture,
                   i.type_erreur, i.priorite,
                   i.start_time, i.end_time,
                   COALESCE(i.fiche_photo_nom, '') AS fiche_photo_nom,
                   COALESCE(i.fiche_validation, 'En attente') AS fiche_validation,
                   (i.fiche_photo_data IS NOT NULL AND octet_length(i.fiche_photo_data) > 0) AS has_fiche,
                   COALESCE(e.client, '') AS client
            FROM interventions i
            LEFT JOIN equipements e ON LOWER(e.nom) = LOWER(i.machine)
            WHERE i.is_temporary = 0
        """
        if machine:
            df = read_sql(
                base_query + " AND i.machine = ? ORDER BY i.date DESC",
                conn, params=(machine,))
        else:
            df = read_sql(base_query + " ORDER BY i.date DESC", conn)
    
    # Only apply text fixes to text columns that need it
    text_columns = ["machine", "description", "probleme", "cause", "solution", "notes", "client"]
    if not df.empty:
        df = _fix_df_text(df, columns=text_columns)
    
    # Fill remaining NaN with empty string
    if "client" in df.columns:
        df["client"] = df["client"].fillna("")
    
    # Normaliser le statut
    if not df.empty and "statut" in df.columns:
        df["statut"] = df["statut"].apply(
            lambda s: "Cloturee" if "tur" in str(s).lower() else str(s)
        )
    
    # Convert technicien username to full name (nom + prenom) if it looks like a username
    # BUT: Cache the lookups to avoid N+1 queries
    if not df.empty and "technicien" in df.columns:
        tech_cache = {}
        
        def convert_technicien(tech_str):
            if not tech_str or not isinstance(tech_str, str):
                return tech_str
            
            # Check cache first
            if tech_str in tech_cache:
                return tech_cache[tech_str]
            
            # Try to get full name from techniciens table
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT nom, prenom FROM techniciens WHERE username = ?",
                        (tech_str,)
                    ).fetchone()
                    if row:
                        nom = row.get("nom", "").strip() if hasattr(row, 'get') else (row[0] or "").strip()
                        prenom = row.get("prenom", "").strip() if hasattr(row, 'get') else (row[1] or "").strip()
                        result = f"{prenom} {nom}".strip() if prenom else nom
                        tech_cache[tech_str] = result
                        return result
            except Exception:
                pass
            
            tech_cache[tech_str] = tech_str
            return tech_str
        
        df["technicien"] = df["technicien"].apply(convert_technicien)
    
    return df



def ajouter_intervention(intervention_dict):
    """Ajoute une intervention."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO interventions (date, machine, technicien, type_intervention,
                                       description, probleme, cause, solution,
                                       pieces_utilisees, cout, duree_minutes,
                                       code_erreur, statut, notes, type_erreur, priorite,
                                       duree_deplacement, start_time, end_time, fiche_validation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            intervention_dict.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            intervention_dict.get("machine") or "",
            intervention_dict.get("technicien") or "",
            intervention_dict.get("type_intervention", "Corrective"),
            intervention_dict.get("description") or "",
            intervention_dict.get("probleme") or "",
            intervention_dict.get("cause") or "",
            intervention_dict.get("solution") or "",
            intervention_dict.get("pieces_utilisees") or "",
            intervention_dict.get("cout", 0.0),
            intervention_dict.get("duree_minutes", 0),
            intervention_dict.get("code_erreur") or "",
            intervention_dict.get("statut", "Terminée"),
            intervention_dict.get("notes") or "",
            intervention_dict.get("type_erreur") or "",
            intervention_dict.get("priorite") or "",
            intervention_dict.get("duree_deplacement", 0),
            intervention_dict.get("start_time") or None,
            intervention_dict.get("end_time") or None,
            intervention_dict.get("fiche_validation", "En attente"),
        ))
    _trigger_backup()
    return True


# ==========================================
# FONCTIONS CRUD — PLANNING MAINTENANCE
# ==========================================

def lire_planning(machine=None, statut=None, region=None, ville=None):
    """Lit le planning de maintenance avec filtres optionnels."""
    query = "SELECT * FROM planning_maintenance WHERE 1=1"
    params = []
    if machine:
        query += " AND machine = ?"
        params.append(machine)
    if statut:
        query += " AND statut = ?"
        params.append(statut)
    query += " ORDER BY date_prevue ASC"

    with get_db() as conn:
        df = read_sql(query, conn, params=params)
    
    # Apply region and ville filters if provided
    if (region or ville) and not df.empty:
        # Get clients with their region/ville info
        with get_db() as conn:
            clients_df = read_sql(
                "SELECT nom, region, ville FROM clients WHERE 1=1",
                conn
            )
        
        if not clients_df.empty:
            # Create a mapping of client name to region/ville
            client_info = {}
            for _, row in clients_df.iterrows():
                client_name = str(row.get('nom', '')).lower()
                client_info[client_name] = {
                    'region': str(row.get('region', '')).lower(),
                    'ville': str(row.get('ville', '')).lower()
                }
            
            # Filter planning by region/ville
            def matches_filters(client_name):
                if not client_name:
                    return False
                client_lower = str(client_name).lower()
                info = client_info.get(client_lower, {})
                
                if region and region.lower() != 'tous':
                    if info.get('region', '').lower() != region.lower():
                        return False
                if ville and ville.lower() != 'tous':
                    if info.get('ville', '').lower() != ville.lower():
                        return False
                return True
            
            if 'client' in df.columns:
                df = df[df['client'].apply(matches_filters)]
    
    # Convert technicien_assigne username to full name
    if not df.empty and "technicien_assigne" in df.columns:
        def convert_technicien(tech_str):
            if not tech_str or not isinstance(tech_str, str):
                return tech_str
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT nom, prenom FROM techniciens WHERE username = ?",
                        (tech_str,)
                    ).fetchone()
                    if row:
                        nom = row.get("nom", "").strip() if hasattr(row, 'get') else (row[0] or "").strip()
                        prenom = row.get("prenom", "").strip() if hasattr(row, 'get') else (row[1] or "").strip()
                        return f"{prenom} {nom}".strip() if prenom else nom
            except Exception:
                pass
            return tech_str
        
        df["technicien_assigne"] = df["technicien_assigne"].apply(convert_technicien)
    
    return df


def ajouter_planning(planning_dict):
    """Ajoute une maintenance planifiée."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO planning_maintenance (machine, client, type_maintenance, description,
                                              date_prevue, technicien_assigne, recurrence, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            planning_dict.get("machine", ""),
            planning_dict.get("client", ""),
            planning_dict.get("type_maintenance", "Préventive"),
            planning_dict.get("description", ""),
            planning_dict.get("date_prevue", ""),
            planning_dict.get("technicien_assigne", ""),
            planning_dict.get("recurrence", ""),
            planning_dict.get("notes", ""),
        ))
    _trigger_backup()
    return True


def update_planning_statut(planning_id, statut, date_realisee=None):
    """Met à jour le statut d'une maintenance planifiée."""
    with get_db() as conn:
        if date_realisee:
            conn.execute(
                "UPDATE planning_maintenance SET statut=?, date_realisee=? WHERE id=?",
                (statut, date_realisee, planning_id))
        else:
            conn.execute(
                "UPDATE planning_maintenance SET statut=? WHERE id=?",
                (statut, planning_id))
    _trigger_backup()
    return True


# ==========================================
# SUPPRIMER PLANNING
# ==========================================

def supprimer_planning(planning_id):
    """Supprime une maintenance planifiée."""
    with get_db() as conn:
        conn.execute("DELETE FROM planning_maintenance WHERE id=?", (planning_id,))
    _trigger_backup()
    return True


def reprogrammer_planning(planning_id, nouvelle_date):
    """Reprogramme une maintenance à une nouvelle date et remet le statut à Planifiée."""
    with get_db() as conn:
        conn.execute(
            "UPDATE planning_maintenance SET date_prevue=?, statut='Planifiée' WHERE id=?",
            (nouvelle_date, planning_id))
    _trigger_backup()
    return True


# ==========================================
# FONCTIONS CRUD — PIÈCES DE RECHANGE
# ==========================================

def lire_pieces():
    """Lit le stock de pièces de rechange."""
    with get_db() as conn:
        return read_sql("SELECT * FROM pieces_rechange ORDER BY designation", conn)


def ajouter_piece(piece_dict):
    """Ajoute une pièce de rechange."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO pieces_rechange (reference, designation, equipement_type,
                                         stock_actuel, stock_minimum, fournisseur, prix_unitaire, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(reference) DO UPDATE SET
                stock_actuel=excluded.stock_actuel, prix_unitaire=excluded.prix_unitaire
        """, (
            piece_dict.get("reference", ""),
            piece_dict.get("designation", ""),
            piece_dict.get("equipement_type", ""),
            piece_dict.get("stock_actuel", 0),
            piece_dict.get("stock_minimum", 1),
            piece_dict.get("fournisseur", ""),
            piece_dict.get("prix_unitaire", 0.0),
            piece_dict.get("notes", ""),
        ))
    _trigger_backup()
    return True


def update_stock_piece(reference, nouveau_stock):
    """Met à jour le stock d'une pièce."""
    with get_db() as conn:
        conn.execute(
            "UPDATE pieces_rechange SET stock_actuel=? WHERE reference=?",
            (nouveau_stock, reference))
    _trigger_backup()
    return True


def modifier_piece(piece_id, piece_dict):
    """Modifie une pièce de rechange par son ID."""
    with get_db() as conn:
        conn.execute("""
            UPDATE pieces_rechange SET
                reference=?, designation=?, equipement_type=?,
                stock_actuel=?, stock_minimum=?, fournisseur=?,
                prix_unitaire=?, notes=?
            WHERE id=?
        """, (
            piece_dict.get("reference", ""),
            piece_dict.get("designation", ""),
            piece_dict.get("equipement_type", ""),
            piece_dict.get("stock_actuel", 0),
            piece_dict.get("stock_minimum", 1),
            piece_dict.get("fournisseur", ""),
            piece_dict.get("prix_unitaire", 0.0),
            piece_dict.get("notes", ""),
            piece_id,
        ))
    _trigger_backup()
    return True


def supprimer_piece(piece_id):
    """Supprime une pièce de rechange par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM pieces_rechange WHERE id=?", (piece_id,))
    _trigger_backup()
    return True


# ==========================================
# FONCTIONS CRUD — NOTIFICATIONS PIÈCES
# ==========================================

def ajouter_notification_piece(notif_dict):
    """Ajoute une notification pièce (rupture ou arrivée)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO notifications_pieces
            (type, intervention_id, piece_reference, piece_nom, intervention_ref,
             equipement, client, technicien, message, source, destination, statut)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'non_lu')
        """, (
            notif_dict.get("type", ""),
            notif_dict.get("intervention_id"),
            notif_dict.get("piece_reference", ""),
            notif_dict.get("piece_nom", ""),
            notif_dict.get("intervention_ref", ""),
            notif_dict.get("equipement", ""),
            notif_dict.get("client", ""),
            notif_dict.get("technicien", ""),
            notif_dict.get("message", ""),
            notif_dict.get("source", ""),
            notif_dict.get("destination", ""),
        ))
    return True


def lire_notifications_pieces(destination=None, statut=None, technicien=None):
    """Lit les notifications pièces, filtrées par destination, statut et/ou technicien."""
    _ensure_notifications_pieces_exists()
    query = "SELECT * FROM notifications_pieces WHERE 1=1"
    params = []
    if destination:
        query += " AND destination = %s"
        params.append(destination)
    if statut:
        query += " AND statut = %s"
        params.append(statut)
    if technicien:
        query += " AND LOWER(technicien) LIKE LOWER(%s)"
        params.append(f"%{technicien}%")
    query += " ORDER BY date_creation DESC LIMIT 200"
    with get_db() as conn:
        return read_sql(query, conn, params=params)


def _ensure_notifications_pieces_exists():
    """Crée la table notifications_pieces si elle n'existe pas (defensive initialization)."""
    with get_db() as conn:
        try:
            if USE_PG:
                cur = conn._conn.cursor()
                cur.execute("""
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'notifications_pieces'
                """)
                if not cur.fetchone():
                    # Table doesn't exist, create it
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS notifications_pieces (
                            id SERIAL PRIMARY KEY,
                            type TEXT NOT NULL,
                            intervention_id INTEGER,
                            piece_reference TEXT,
                            piece_nom TEXT,
                            intervention_ref TEXT,
                            equipement TEXT,
                            client TEXT,
                            technicien TEXT,
                            message TEXT,
                            source TEXT NOT NULL DEFAULT '',
                            destination TEXT NOT NULL,
                            statut TEXT DEFAULT 'non_lu',
                            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            date_lecture TIMESTAMP,
                            date_traitement TIMESTAMP
                        )
                    """)
                    conn._conn.commit()
                    logger.info("⚠️  Table notifications_pieces created dynamically (defensive)")
            else:
                # SQLite
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS notifications_pieces (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        type TEXT NOT NULL,
                        intervention_id INTEGER,
                        piece_reference TEXT,
                        piece_nom TEXT,
                        intervention_ref TEXT,
                        equipement TEXT,
                        client TEXT,
                        technicien TEXT,
                        message TEXT,
                        source TEXT NOT NULL DEFAULT '',
                        destination TEXT NOT NULL,
                        statut TEXT DEFAULT 'non_lu',
                        date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        date_lecture TIMESTAMP,
                        date_traitement TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.debug(f"_ensure_notifications_pieces_exists: {e}")


def compter_notifications_non_lues(destination, technicien=None):
    """Compte les notifications non lues pour une destination (et optionnellement un technicien)."""
    _ensure_notifications_pieces_exists()
    query = "SELECT COUNT(*) as cnt FROM notifications_pieces WHERE destination = %s AND statut = 'non_lu'"
    params = [destination]
    if technicien:
        query += " AND LOWER(technicien) LIKE LOWER(%s)"
        params.append(f"%{technicien}%")
    with get_db() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
        return int(row["cnt"]) if row else 0


def marquer_notification_lue(notif_id):
    """Marque une notification comme lue."""
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications_pieces SET statut = 'lu', date_lecture = CURRENT_TIMESTAMP WHERE id = %s",
            (notif_id,)
        )
    return True


def marquer_notification_traitee(notif_id):
    """Marque une notification comme traitée."""
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications_pieces SET statut = 'traite', date_traitement = CURRENT_TIMESTAMP WHERE id = %s",
            (notif_id,)
        )
    return True


def notifications_rupture_pour_piece(piece_reference):
    """Retourne les notifications de rupture non traitées pour une pièce donnée."""
    with get_db() as conn:
        return read_sql(
            "SELECT * FROM notifications_pieces WHERE type = 'piece_rupture' AND piece_reference = %s AND statut != 'traite'",
            conn, params=(piece_reference,)
        )


# ==========================================
# FONCTIONS CRUD — PIÈCES DEMANDÉES (NON RÉFÉRENCÉES)
# ==========================================

def ajouter_piece_demandee(demande_dict):
    """Ajoute une demande de pièce non référencée."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO pieces_demandees
            (reference, designation, intervention_id, equipement, client, technicien, probleme, statut)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'en_attente')
        """, (
            demande_dict.get("reference", ""),
            demande_dict.get("designation", ""),
            demande_dict.get("intervention_id"),
            demande_dict.get("equipement", ""),
            demande_dict.get("client", ""),
            demande_dict.get("technicien", ""),
            demande_dict.get("probleme", ""),
        ))
    return True


def lire_pieces_demandees_en_attente(reference=None):
    """Lit les demandes de pièces en attente, optionnellement filtrées par référence (ILIKE)."""
    query = "SELECT * FROM pieces_demandees WHERE statut = 'en_attente'"
    params = []
    if reference:
        query += " AND LOWER(reference) = LOWER(%s)"
        params.append(reference)
    query += " ORDER BY date_creation DESC"
    with get_db() as conn:
        return read_sql(query, conn, params=params)


def resoudre_piece_demandee(demande_id):
    """Marque une demande de pièce comme disponible."""
    with get_db() as conn:
        conn.execute(
            "UPDATE pieces_demandees SET statut = 'disponible', date_resolution = CURRENT_TIMESTAMP WHERE id = %s",
            (demande_id,)
        )
    return True


def lire_toutes_pieces_demandees(statut=None):
    """Lit toutes les demandes de pièces, optionnellement filtrées par statut."""
    query = "SELECT * FROM pieces_demandees WHERE 1=1"
    params = []
    if statut:
        query += " AND statut = %s"
        params.append(statut)
    query += " ORDER BY date_creation DESC"
    with get_db() as conn:
        return read_sql(query, conn, params=params)


# ==========================================
# FONCTIONS CRUD — AUDIT LOG
# ==========================================

def log_audit(username, action, details="", page=""):
    """Enregistre une action dans le journal d'audit."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO audit_log (username, action, details, page)
            VALUES (?, ?, ?, ?)
        """, (username, action, details, page))


def lire_audit(limit=100):
    """Lit le journal d'audit."""
    with get_db() as conn:
        return read_sql(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
            conn, params=(limit,))


def log_ai_inference(model_version, prompt_hash, confidence_score, outcome):
    """Enregistre une inference IA dans le journal d'audit (EU AI Act)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO ai_audit_log (model_version, prompt_hash, confidence_score, outcome)
            VALUES (?, ?, ?, ?)
        """, (model_version, prompt_hash, confidence_score, outcome))


# ==========================================
# FONCTIONS — PREDICTION FEEDBACK (HITL)
# ==========================================

def save_prediction_feedback(machine, date_predite, resultat, date_reelle="", note="", username="system"):
    """Enregistre le feedback d'un technicien sur une prédiction."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO prediction_feedback (machine, date_predite, resultat, date_reelle, note_technicien, username)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (machine, date_predite, resultat, date_reelle, note, username))


def lire_prediction_feedback(machine=None, limit=50):
    """Lit les feedbacks de prédictions, optionnellement filtrés par machine."""
    with get_db() as conn:
        if machine:
            return read_sql(
                "SELECT * FROM prediction_feedback WHERE machine = ? ORDER BY timestamp DESC LIMIT ?",
                conn, params=(machine, limit))
        return read_sql(
            "SELECT * FROM prediction_feedback ORDER BY timestamp DESC LIMIT ?",
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
        row = conn.execute("SELECT valeur FROM config_client WHERE cle = ?", (cle,)).fetchone()
        return row["valeur"] if row else default


def set_config(cle, valeur):
    """Définit une valeur de configuration."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO config_client (cle, valeur) VALUES (?, ?)
            ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur
        """, (cle, valeur))


# ==========================================
# MIGRATION EXCEL → SQLITE
# ==========================================

def migrer_depuis_excel(excel_path):
    """Migre les données existantes depuis Excel vers SQLite/PostgreSQL."""
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
                                INSERT OR IGNORE INTO codes_erreurs (code, message, niveau, type)
                                VALUES (?, ?, ?, ?)
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
                                INSERT OR IGNORE INTO solutions (mot_cle, type, priorite, cause, solution)
                                VALUES (?, ?, ?, ?, ?)
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

    if not USE_PG:
        # Mode SQLite : utiliser la migration classique
        with get_db() as conn:
            conn.execute("DELETE FROM codes_erreurs")
            conn.execute("DELETE FROM solutions")
        return migrer_depuis_excel(excel_path)

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
            "INSERT INTO telemetry (machine, sensor_type, value) VALUES (?, ?, ?)",
            (machine, sensor_type, float(value)))
    return True


def lire_telemetry(machine, sensor_type=None, hours=24):
    """Lit l'historique de télémétrie pour une machine."""
    if "%" in machine:
        query = """
            SELECT timestamp, machine, sensor_type, value FROM telemetry
            WHERE machine LIKE ?
            AND timestamp > datetime('now', ?)
        """
    else:
        query = """
            SELECT timestamp, machine, sensor_type, value FROM telemetry
            WHERE machine = ?
            AND timestamp > datetime('now', ?)
        """
    params = [machine, f"-{hours} hours"]
    
    if sensor_type:
        query += " AND sensor_type = ?"
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
    
    if USE_PG:
        # Mode PostgreSQL - utiliser psycopg2
        import psycopg2
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.set_client_encoding('UTF8')
            cur = conn.cursor()
            
            # Colonnes à vérifier/ajouter
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
            
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Erreur migration PostgreSQL: {e}")
        return
    
    # Mode SQLite - utiliser la migration classique
    with get_db() as conn:
        # Vérifier colonnes table interventions
        cursor = conn.execute("PRAGMA table_info(interventions)")
        columns = [row["name"] for row in cursor.fetchall()]

        missing_cols = {
            "probleme": "TEXT DEFAULT ''",
            "cause": "TEXT DEFAULT ''",
            "solution": "TEXT DEFAULT ''",
            "cout_pieces": "REAL DEFAULT 0.0",
            "start_time": "TIME",
            "end_time": "TIME",
            "duree_deplacement": "INTEGER DEFAULT 0",
            "type_erreur": "TEXT DEFAULT ''",
            "priorite": "TEXT DEFAULT ''",
            "fiche_validation": "TEXT DEFAULT 'En attente'",
            "date_debut_intervention": "TIMESTAMP",
            "date_cloture": "TIMESTAMP",
        }

        for col, type_def in missing_cols.items():
            if col not in columns:
                try:
                    conn.execute(f"ALTER TABLE interventions ADD COLUMN {col} {type_def}")
                    print(f"Migration: Ajout de la colonne '{col}' à la table 'interventions'.")
                except Exception as e:
                    print(f"Erreur migration colonne {col}: {e}")

        # Vérifier colonnes table techniciens
        cursor = conn.execute("PRAGMA table_info(techniciens)")
        tech_cols = [row["name"] for row in cursor.fetchall()]
        if "telegram_id" not in tech_cols:
            try:
                conn.execute("ALTER TABLE techniciens ADD COLUMN telegram_id TEXT DEFAULT ''")
                print("Migration: Ajout de la colonne 'telegram_id' à la table 'techniciens'.")
            except Exception as e:
                print(f"Erreur migration techniciens: {e}")

        # Vérifier colonnes table equipements (Ajout Client)
        cursor = conn.execute("PRAGMA table_info(equipements)")
        eq_cols = [row["name"] for row in cursor.fetchall()]
        if "client" not in eq_cols:
            try:
                conn.execute("ALTER TABLE equipements ADD COLUMN client TEXT DEFAULT 'Centre Principal'")
                print("Migration: Ajout de la colonne 'client' à la table 'equipements'.")
            except Exception as e:
                print(f"Erreur migration equipements: {e}")

        # Normaliser les statuts corrompus (encodage UTF-8/Latin-1)
        try:
            conn.execute("""
                UPDATE interventions SET statut='Cloturee'
                WHERE statut != 'Cloturee'
                AND (statut LIKE '%lotur%' OR statut LIKE '%Cl%tur%')
            """)
        except Exception:
            pass

# ==========================================
# FONCTIONS CRUD — TECHNICIENS
# ==========================================

def lire_techniciens():
    """
    Lit la liste des techniciens.
    
    Returns:
        pd.DataFrame: Liste des techniciens.
    """
    try:
        with get_db() as conn:
            return read_sql("""
                SELECT 
                    id, username, nom, prenom, specialite, 
                    qualification, niveau_competence, dispo, notes,
                    email, telephone, telegram_id
                FROM techniciens
                ORDER BY nom
            """, conn)
    except Exception as e:
        logger.error(f"Erreur lire_techniciens: {e}")
        return pd.DataFrame()

def ajouter_technicien(tech_dict):
    """
    Ajoute un technicien.
    """
    try:
        with get_db() as conn:
            res = conn.execute("""
                INSERT INTO techniciens (nom, prenom, specialite, qualification, niveau_competence, dispo, notes, email, telephone, telegram_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tech_dict.get("nom", ""),
                tech_dict.get("prenom", ""),
                tech_dict.get("specialite", "Généraliste"),
                tech_dict.get("qualification", ""),
                tech_dict.get("niveau_competence", "Junior"),
                tech_dict.get("dispo", 1),
                tech_dict.get("notes", ""),
                tech_dict.get("email", ""),
                tech_dict.get("telephone", ""),
                tech_dict.get("telegram_id", ""),
            ))
            tech_id = res.lastrowid
        
        nom_comp = f"{tech_dict.get('nom', '')} {tech_dict.get('prenom', '')}".strip()
        logger.info(f"Audit Trail: Nouveau technicien {nom_comp} ajouté (ID: {tech_id})")
        return True
    except Exception as e:
        logger.error(f"Erreur ajouter_technicien: {e}")
        return False

def update_technicien(tech_id, tech_dict):
    """
    Met à jour un technicien.
    """
    try:
        with get_db() as conn:
            conn.execute("""
                UPDATE techniciens
                SET nom=?, prenom=?, specialite=?, qualification=?, niveau_competence=?, dispo=?, notes=?,
                    email=?, telephone=?, telegram_id=?
                WHERE id=?
            """, (
                tech_dict.get("nom", ""),
                tech_dict.get("prenom", ""),
                tech_dict.get("specialite", ""),
                tech_dict.get("qualification", ""),
                tech_dict.get("niveau_competence", "Junior"),
                tech_dict.get("dispo", 1),
                tech_dict.get("notes", ""),
                tech_dict.get("email", ""),
                tech_dict.get("telephone", ""),
                tech_dict.get("telegram_id", ""),
                tech_id
            ))
        
        logger.info(f"Audit Trail: Technicien ID {tech_id} mis à jour.")
        return True
    except Exception as e:
        logger.error(f"Erreur update_technicien ID {tech_id}: {e}")
        return False

def supprimer_technicien(tech_id):
    """Supprime un technicien."""
    with get_db() as conn:
        conn.execute("DELETE FROM techniciens WHERE id = ?", (tech_id,))
    return True


# ==========================================

# ==========================================
# FONCTIONS CRUD — CONTRATS / SLA
# ==========================================

def lire_contrats(client=None):
    """Lit les contrats, optionnellement filtrés par client."""
    with get_db() as conn:
        if client:
            df = read_sql("SELECT * FROM contrats WHERE client=? ORDER BY date_fin DESC", conn, params=(client,))
        else:
            df = read_sql("SELECT * FROM contrats ORDER BY date_fin DESC", conn)
    return df

def get_contract_equipements(contrat_id):
    """Récupère tous les équipements d'un contrat."""
    with get_db() as conn:
        ph = "%s" if USE_PG else "?"
        rows = conn.execute(
            f"""SELECT e.nom as equipement_nom FROM contrats_equipements ce
                LEFT JOIN equipements e ON ce.equipement_id = e.id
                WHERE ce.contrat_id = {ph} ORDER BY ce.id""",
            (contrat_id,)
        ).fetchall()
        return [dict(row)["equipement_nom"] for row in rows if dict(row).get("equipement_nom")]

def ajouter_contrat(contrat_dict):
    """
    Ajoute un contrat et ses équipements, retourne son ID.
    
    Supporte deux formats:
    - equipement (str): rétrocompatibilité - sera converti en array
    - equipements (list): array d'équipements
    
    Stocke aussi les pièces incluses en JSON si avec_pieces=true
    """
    with get_db() as conn:
        # Extract equipments (support both single and multiple)
        equipements = contrat_dict.get("equipements", [])
        if isinstance(equipements, str):
            equipements = [equipements] if equipements else []
        elif not isinstance(equipements, list):
            equipements = []
        
        # For backward compatibility, also check for singular "equipement"
        if not equipements:
            single_eq = contrat_dict.get("equipement", "")
            if single_eq:
                equipements = [single_eq]
        
        # Store first equipment in main table for backward compatibility
        first_equipment = equipements[0] if equipements else ""
        
        # Handle pieces_incluses - convert list to JSON string
        pieces_incluses = contrat_dict.get("pieces_incluses", "")
        if isinstance(pieces_incluses, (list, dict)):
            import json
            pieces_incluses = json.dumps(pieces_incluses)
        
        # Insert and retrieve ID in a single operation - works for both SQLite and PostgreSQL
        ph = "%s" if USE_PG else "?"
        result = conn.execute(f"""
            INSERT INTO contrats (client, type_contrat, date_debut, date_fin,
                sla_temps_reponse_h, interventions_incluses, montant, conditions, notes,
                fichier_contrat, equipement, recurrence_maintenance, date_premiere_maintenance, statut,
                pieces_incluses, avec_pieces)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (
            contrat_dict.get("client", ""),
            contrat_dict.get("type_contrat", "Standard"),
            contrat_dict.get("date_debut", ""),
            contrat_dict.get("date_fin", ""),
            contrat_dict.get("sla_temps_reponse_h", 24),
            contrat_dict.get("interventions_incluses", -1),
            contrat_dict.get("montant", 0.0),
            contrat_dict.get("conditions", ""),
            contrat_dict.get("notes", ""),
            contrat_dict.get("fichier_contrat", ""),
            first_equipment,
            contrat_dict.get("recurrence_maintenance", ""),
            contrat_dict.get("date_premiere_maintenance", ""),
            contrat_dict.get("statut", "Actif"),
            pieces_incluses,
            1 if contrat_dict.get("avec_pieces") else 0,
        ))
        # Retrieve the newly created contrat ID - PostgreSQL RealDictCursor returns dict-like rows
        row = conn.execute("SELECT MAX(id) as id FROM contrats").fetchone()
        contrat_id = row["id"] if row else None
        
        # Insert equipments into junction table
        for eq in equipements:
            if eq:  # Only insert non-empty equipments
                try:
                    # Get equipement ID from equipements table
                    eq_row = conn.execute(
                        f"SELECT id FROM equipements WHERE nom = {('%s' if USE_PG else '?')} LIMIT 1",
                        (eq,)
                    ).fetchone()
                    eq_id = eq_row["id"] if eq_row else None
                    
                    if eq_id:
                        ph = "%s" if USE_PG else "?"
                        if USE_PG:
                            conn.execute(
                                f"INSERT INTO contrats_equipements (contrat_id, equipement_id) VALUES ({ph}, {ph}) ON CONFLICT DO NOTHING",
                                (contrat_id, eq_id)
                            )
                        else:
                            conn.execute(
                                f"INSERT OR IGNORE INTO contrats_equipements (contrat_id, equipement_id) VALUES ({ph}, {ph})",
                                (contrat_id, eq_id)
                            )
                except Exception as e:
                    logger.debug(f"Could not insert equipment {eq} for contract {contrat_id}: {e}")
    
    _trigger_backup()
    return contrat_id


def generer_planning_from_contrat(contrat_id):
    """
    Génère automatiquement les entrées de planning de maintenance préventive
    à partir d'un contrat, selon sa récurrence et ses dates.
    
    Supporte les équipements multiples: génère une entrée de planning pour 
    CHAQUE équipement du contrat.
    
    Retourne le nombre d'entrées créées.
    """
    from dateutil.relativedelta import relativedelta

    RECURRENCE_DELTAS = {
        "Hebdomadaire": relativedelta(weeks=1),
        "Mensuelle": relativedelta(months=1),
        "Trimestrielle": relativedelta(months=3),
        "Semestrielle": relativedelta(months=6),
        "Annuelle": relativedelta(years=1),
    }

    with get_db() as conn:
        ph = "%s" if USE_PG else "?"
        
        row = conn.execute(
            f"SELECT * FROM contrats WHERE id = {ph}", (contrat_id,)
        ).fetchone()
        if not row:
            return 0

        contrat = dict(row)
        recurrence = (contrat.get("recurrence_maintenance") or "").strip()
        if not recurrence or recurrence not in RECURRENCE_DELTAS:
            return 0

        date_fin_str = str(contrat.get("date_fin", "") or "")[:10]
        date_premiere_str = str(contrat.get("date_premiere_maintenance", "") or "")[:10]
        client = contrat.get("client", "")

        if not date_fin_str or not date_premiere_str:
            return 0

        try:
            from datetime import date as _date
            date_premiere = _date.fromisoformat(date_premiere_str)
            date_fin = _date.fromisoformat(date_fin_str)
        except ValueError:
            return 0

        # Récupérer tous les équipements du contrat
        equipements_rows = conn.execute(
            f"""SELECT e.nom as equipement_nom FROM contrats_equipements ce
                LEFT JOIN equipements e ON ce.equipement_id = e.id
                WHERE ce.contrat_id = {ph} ORDER BY ce.id""",
            (contrat_id,)
        ).fetchall()
        
        if equipements_rows:
            equipements = [dict(row)["equipement_nom"] for row in equipements_rows]
        else:
            # Fallback: utiliser l'équipement du contrat (pour rétrocompatibilité)
            equipements = [contrat.get("equipement", "")] if contrat.get("equipement") else []
        
        if not equipements:
            return 0  # Aucun équipement à planifier

        delta = RECURRENCE_DELTAS[recurrence]
        count = 0

        # Générer planning pour CHAQUE équipement
        for equipement in equipements:
            current_date = date_premiere
            while current_date <= date_fin:
                conn.execute(f"""
                    INSERT INTO planning_maintenance
                        (machine, client, type_maintenance, description,
                         date_prevue, technicien_assigne, recurrence, contrat_id, statut, notes)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """, (
                    equipement,
                    client,
                    "Préventive",
                    f"MP Contrat #{contrat_id} — {equipement}",
                    current_date.isoformat(),
                    "",  # Technicien non assigné — sera assigné via rappel 2 semaines avant
                    recurrence,
                    contrat_id,
                    "Planifiée",
                    f"[{client}] Généré automatiquement depuis contrat #{contrat_id}",
                ))
                count += 1
                current_date = current_date + delta

    return count


def modifier_contrat(contrat_id, contrat_dict):
    """Modifie un contrat existant et ses équipements."""
    with get_db() as conn:
        # Extract equipments (support both single and multiple)
        equipements = contrat_dict.get("equipements", [])
        if isinstance(equipements, str):
            equipements = [equipements] if equipements else []
        elif not isinstance(equipements, list):
            equipements = []
        
        # For backward compatibility, also check for singular "equipement"
        if not equipements:
            single_eq = contrat_dict.get("equipement", "")
            if single_eq:
                equipements = [single_eq]
        
        # Store first equipment in main table for backward compatibility
        first_equipment = equipements[0] if equipements else ""
        
        # Handle pieces_incluses - convert list to JSON string
        pieces_incluses = contrat_dict.get("pieces_incluses", "")
        if isinstance(pieces_incluses, (list, dict)):
            import json
            pieces_incluses = json.dumps(pieces_incluses)
        
        conn.execute("""
            UPDATE contrats SET client=?, type_contrat=?, date_debut=?, date_fin=?,
                sla_temps_reponse_h=?, interventions_incluses=?, montant=?, conditions=?, notes=?, statut=?,
                fichier_contrat=?, equipement=?, pieces_incluses=?, avec_pieces=?
            WHERE id=?
        """, (
            contrat_dict.get("client", ""),
            contrat_dict.get("type_contrat", "Standard"),
            contrat_dict.get("date_debut", ""),
            contrat_dict.get("date_fin", ""),
            contrat_dict.get("sla_temps_reponse_h", 24),
            contrat_dict.get("interventions_incluses", -1),
            contrat_dict.get("montant", 0.0),
            contrat_dict.get("conditions", ""),
            contrat_dict.get("notes", ""),
            contrat_dict.get("statut", "Actif"),
            contrat_dict.get("fichier_contrat", ""),
            first_equipment,
            pieces_incluses,
            1 if contrat_dict.get("avec_pieces") else 0,
            contrat_id,
        ))
        
        # Delete existing equipments for this contract
        conn.execute("DELETE FROM contrats_equipements WHERE contrat_id=?", (contrat_id,))
        
        # Insert new equipments into junction table
        for eq in equipements:
            if eq:  # Only insert non-empty equipments
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO contrats_equipements (contrat_id, equipement_nom) VALUES (?, ?)",
                        (contrat_id, eq)
                    )
                except Exception as e:
                    logger.debug(f"Could not insert equipment {eq} for contract {contrat_id}: {e}")
    
    _trigger_backup()

def supprimer_contrat(contrat_id):
    """Supprime un contrat."""
    with get_db() as conn:
        conn.execute("DELETE FROM contrats WHERE id=?", (contrat_id,))
    _trigger_backup()

def update_intervention_statut(intervention_id, nouveau_statut):
    """Met a jour le statut d'une intervention avec horodatage."""
    with get_db() as conn:
        now = datetime.now().isoformat()
        if nouveau_statut == "En cours":
            conn.execute("UPDATE interventions SET statut=?, date_debut_intervention=? WHERE id=?",
                         (nouveau_statut, now, intervention_id))
        elif nouveau_statut in ("Cloturee", "Cl\u00f4tur\u00e9e"):
            conn.execute("UPDATE interventions SET statut='Cloturee', date_cloture=? WHERE id=?",
                         (now, intervention_id))
        else:
            conn.execute("UPDATE interventions SET statut=? WHERE id=?",
                         (nouveau_statut, intervention_id))
    _trigger_backup()


# FONCTIONS SPÉCIALES — WORKFLOW SAV
# ==========================================

def cloturer_intervention(intervention_id, probleme, cause, solution, pieces_a_deduire=None, duree_minutes=None, start_time=None, end_time=None, duree_deplacement=None):
    """
    Clôture une intervention, déduit le stock et alimente la base de connaissances.
    pieces_a_deduire: liste de dict {'ref': str, 'qty': int, 'designation': str}
    duree_minutes: durée de l'intervention en minutes
    """
    if not solution:
        return False, "La Solution (ou Actions réalisées) est obligatoire pour clôturer."

    print(f"[CLOTURE] intervention_id={intervention_id}, pieces_a_deduire={pieces_a_deduire}")

    with get_db() as conn:
        # NOTE: La migration cout_pieces est dans verifier_et_migrer_schema(), PAS ici.
        # Un ALTER TABLE échoué invalide la transaction PostgreSQL !

        # 1. Gestion du Stock + calcul coût pièces
        synthese_pieces = []
        total_cout_pieces = 0.0
        if pieces_a_deduire:
            for p in pieces_a_deduire:
                if not isinstance(p, dict):
                    continue
                ref = p.get('ref') or p.get('reference') or ''
                qty = int(p.get('qty') or p.get('quantite') or 0)
                prix = float(p.get('prix_unitaire', 0) or 0)
                designation = p.get('designation', ref)
                fournisseur = p.get('fournisseur', '')
                
                if qty > 0 and ref:
                    print(f"[CLOTURE] Déduction stock: ref={ref}, qty={qty}, prix={prix}, designation={designation}")
                    
                    # Chercher la pièce dans la base de données pour obtenir les infos complètes
                    piece_row = conn.execute(
                        "SELECT prix_unitaire, designation, fournisseur FROM pieces_rechange WHERE reference = %s LIMIT 1",
                        (ref,)
                    ).fetchone()
                    
                    if piece_row:
                        # Utiliser les infos de la base de données
                        prix = float(piece_row.get('prix_unitaire', 0) or prix or 0)
                        designation = piece_row.get('designation', designation)
                        fournisseur = piece_row.get('fournisseur', fournisseur)
                    
                    # Déduire le stock
                    conn.execute("""
                        UPDATE pieces_rechange
                        SET stock_actuel = stock_actuel - %s
                        WHERE reference = %s
                    """, (qty, ref))
                    
                    cout_piece = prix * qty
                    total_cout_pieces += cout_piece
                    
                    # Format: Désignation | Ref: XXX | Fournisseur: YYY | Qty: Z (sans prix)
                    piece_line = f"{designation} | Ref: {ref} | Fournisseur: {fournisseur} | Qty: {qty}"
                    synthese_pieces.append(piece_line)
        else:
            print(f"[CLOTURE] Aucune pièce à déduire (pieces_a_deduire={pieces_a_deduire})")

        pieces_str = "\n".join(synthese_pieces)

        # Calculer le coût main d'oeuvre (taux_horaire × durée)
        # NOTE: cout = main d'oeuvre ONLY (NOT including pieces)
        # cout_pieces = pieces cost ONLY (stored separately)
        duree_val = duree_minutes if duree_minutes is not None else 0
        cout_main_oeuvre = 0.0
        try:
            config_row = conn.execute("SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'").fetchone()
            if not config_row or not config_row["valeur"]:
                raise ValueError("Taux horaire technicien non configuré dans les paramètres")
            taux_horaire = float(config_row["valeur"])
        except (ValueError, TypeError) as e:
            raise Exception(f"Erreur configuration: {str(e)}")
        cout_main_oeuvre = round((duree_val / 60) * taux_horaire, 2)

        # 2. Mettre à jour l'intervention (date = date de clôture)
        date_cloture = datetime.now().isoformat()
        
        # Préparer l'UPDATE avec un dictionnaire pour éviter les décalages
        # IMPORTANT: cout = main d'oeuvre ONLY (NOT including pieces)
        # cout_pieces = pieces cost (stored separately)
        # Dashboard calculates total cost as: cout + cout_pieces
        update_data = {
            "statut": "Cloturee",
            "probleme": probleme,
            "cause": cause,
            "solution": solution,
            "duree_minutes": duree_val,
            "cout": cout_main_oeuvre,  # ← Main d'oeuvre ONLY
            "date": date_cloture,
            "date_cloture": date_cloture
        }
        
        # Ajouter les champs optionnels s'ils sont fournis
        if start_time is not None:
            update_data["start_time"] = start_time
        if end_time is not None:
            update_data["end_time"] = end_time
        if duree_deplacement is not None:
            update_data["duree_deplacement"] = duree_deplacement
        if pieces_str:
            update_data["pieces_utilisees"] = pieces_str
            update_data["cout_pieces"] = total_cout_pieces  # ← Pièces ONLY
        
        # Construire l'UPDATE dynamiquement
        set_clauses = [f"{k}=%s" for k in update_data.keys()]
        update_values = list(update_data.values())
        update_values.append(intervention_id)
        
        sql = f"""
            UPDATE interventions
            SET {", ".join(set_clauses)}
            WHERE id=%s
        """
        conn.execute(sql, update_values)

        # 3. Récupérer le code erreur associé pour l'auto-apprentissage
        row = conn.execute("SELECT code_erreur, type_intervention, type_erreur FROM interventions WHERE id=%s", (intervention_id,)).fetchone()
        code_erreur = row["code_erreur"] if row else ""

        # 4. Auto-Learning : Alimenter la table solutions si un code erreur existe
        # (sauf pour les Formations qui n'ont pas de diagnostic technique)
        type_intervention = row["type_intervention"] if row else ""
        type_erreur_val = row["type_erreur"] if row else "Hardware"
        if code_erreur and type_intervention != "Formation":
            conn.execute("""
                INSERT INTO solutions (mot_cle, type, priorite, cause, solution, validated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(mot_cle) DO UPDATE SET
                    cause=excluded.cause,
                    solution=excluded.solution,
                    updated_at=excluded.updated_at,
                    validated_by='Auto-Learning'
            """, (code_erreur, type_erreur_val or "Hardware", "MOYENNE", cause, solution, "SAV-Auto", datetime.now().isoformat()))

    return True, "Intervention clôturée, stock mis à jour et connaissances sauvegardées !"



# ==========================================
# FONCTIONS CRUD — CONFORMITÉ / QHSE
# ==========================================

def lire_conformite(client=None):
    """Lit les contrôles de conformité, optionnellement filtrés par client."""
    query = "SELECT id, equipement, client, type_controle, description, date_controle, date_expiration, fichier_nom, statut, notes, created_by, created_at FROM conformite"
    params = []
    if client:
        query += " WHERE client = ?"
        params.append(client)
    query += " ORDER BY date_expiration ASC"
    with get_db() as conn:
        return read_sql(query, conn, params=params)


def ajouter_conformite(data, fichier_bytes=None):
    """Ajoute un contrôle de conformité avec fichier PDF optionnel."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO conformite (equipement, client, type_controle, description,
                                     date_controle, date_expiration, fichier_nom, fichier_data,
                                     statut, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("equipement", ""),
            data.get("client", ""),
            data.get("type_controle", ""),
            data.get("description", ""),
            data.get("date_controle", ""),
            data.get("date_expiration", ""),
            data.get("fichier_nom", ""),
            fichier_bytes,
            data.get("statut", "Conforme"),
            data.get("notes", ""),
            data.get("created_by", ""),
        ))
    return True


def supprimer_conformite(conformite_id):
    """Supprime un contrôle de conformité."""
    with get_db() as conn:
        conn.execute("DELETE FROM conformite WHERE id = ?", (conformite_id,))
    return True


def lire_fichier_conformite(conformite_id):
    """Récupère le fichier PDF d'un contrôle de conformité."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT fichier_nom, fichier_data FROM conformite WHERE id = ?",
            (conformite_id,)
        ).fetchone()
        if row and row["fichier_data"]:
            return row["fichier_nom"], bytes(row["fichier_data"])
    return None, None


# ==========================================
# FONCTIONS CRUD — DEMANDES D'INTERVENTION
# ==========================================

def _ensure_demandes_table():
    """Crée la table demandes_intervention si elle n'existe pas (PostgreSQL safe)."""
    with get_db() as conn:
        if USE_PG:
            # Exécuter directement sur la connexion brute pour éviter
            # que PgCursorWrapper avale les erreurs silencieusement
            raw = conn._raw if hasattr(conn, '_raw') else conn
            cur = raw.cursor()
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
            raw.commit()
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS demandes_intervention (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        # Migration: ajouter date_planifiee si absente
        try:
            if USE_PG:
                raw = conn._raw if hasattr(conn, '_raw') else conn
                cur = raw.cursor()
                cur.execute("ALTER TABLE demandes_intervention ADD COLUMN IF NOT EXISTS date_planifiee DATE")
                raw.commit()
            else:
                conn.execute("ALTER TABLE demandes_intervention ADD COLUMN date_planifiee DATE")
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            if USE_PG:
                cur = conn._conn.cursor()
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
                    conn._conn.commit()
                    logger.info("⚠️  Table notification_schedules created dynamically (defensive)")
            else:
                # SQLite: Just try to create, it will silently succeed if exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS notification_schedules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                VALUES (?, ?, ?, ?, ?)
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
                    VALUES (?, ?, ?, ?, ?)
                """, (bot_key, enabled, hour, minute, days_of_week))
    
    _trigger_backup()
    return True


# ==========================================
# INTERVENTIONS_TECHNICIENS — Per-Technician Tracking
# ==========================================

def get_or_create_interventions_techniciens(intervention_id, technicien_nom):
    """
    Récupère ou crée un enregistrement interventions_techniciens pour un technicien.
    Uses robust name matching to handle reversed name orders (e.g., "Ghazi Sellami" vs "Sellami Ghazi").
    
    Args:
        intervention_id: ID de l'intervention
        technicien_nom: Nom complet du technicien (e.g., "Jean Dupont")
    
    Returns:
        dict: Enregistrement with id, intervention_id, technicien_nom, statut, etc.
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = str(name1).lower().strip()
        n2 = str(name2).lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    # Use correct placeholder based on database type
    ph = "%s" if USE_PG else "?"
    
    with get_db() as conn:
        # Get ALL records for this intervention
        rows = conn.execute(f"""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = {ph}
        """, (intervention_id,)).fetchall()
        
        # Check if entry exists (using robust name matching)
        for row in rows:
            if names_match(row['technicien_nom'], technicien_nom):
                return dict(row)
        
        # Create new entry if not found
        conn.execute(f"""
            INSERT INTO interventions_techniciens 
            (intervention_id, technicien_nom, statut)
            VALUES ({ph}, {ph}, 'Assigné')
        """, (intervention_id, technicien_nom))
        
        # Fetch and return the new entry
        row = conn.execute(f"""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = {ph} AND technicien_nom = {ph}
        """, (intervention_id, technicien_nom)).fetchone()
        
        _trigger_backup()
        return dict(row) if row else None


def update_interventions_techniciens(intervention_id, technicien_nom, data):
    """
    Met à jour les données per-technician pour une intervention.
    Now uses ID-based lookup instead of name matching for reliability.
    
    Args:
        intervention_id: ID de l'intervention
        technicien_nom: Nom complet du technicien (used to find the ID)
        data: Dict with keys like probleme_tech, solution_tech, duree_minutes_tech, etc.
              Can optionally include 'technicien_id' to bypass name matching
    
    Returns:
        bool: Success
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = str(name1).lower().strip()
        n2 = str(name2).lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    ph = "%s" if USE_PG else "?"
    
    with get_db() as conn:
        # Ensure the record exists
        get_or_create_interventions_techniciens(intervention_id, technicien_nom)
        
        # Try to find the record ID first - use the ID if provided in data
        record_id = data.get('technicien_id')
        logger.info(f"🔍 update_interventions_techniciens: looking for tech '{technicien_nom}' (provided ID: {record_id})")
        
        if not record_id:
            # Find matching technician using fuzzy matching by name
            rows = conn.execute(f"""
                SELECT id, technicien_nom FROM interventions_techniciens 
                WHERE intervention_id = {ph}
            """, (intervention_id,)).fetchall()
            
            logger.info(f"  📋 Found {len(rows)} technician records for intervention {intervention_id}")
            
            for row in rows:
                row_dict = dict(row)
                tech_name_in_db = row_dict.get('technicien_nom')
                logger.info(f"    Checking: '{tech_name_in_db}' vs '{technicien_nom}' -> {names_match(tech_name_in_db, technicien_nom)}")
                
                if tech_name_in_db and names_match(tech_name_in_db, technicien_nom):
                    record_id = row_dict['id']
                    logger.info(f"    ✅ MATCHED! Using record ID: {record_id}")
                    break
        
        if not record_id:
            logger.warning(f"❌ No matching technician record found for '{technicien_nom}' in intervention {intervention_id}")
            return False
        
        # Build update query using ID (most reliable)
        updates = []
        params = []
        
        allowed_fields = [
            'statut', 'probleme_tech', 'cause_tech', 'solution_tech',
            'heure_debut_tech', 'heure_fin_tech', 'duree_minutes_tech',
            'duree_deplacement_tech', 'notes_tech'
        ]
        
        for field in allowed_fields:
            if field in data and field != 'technicien_id':
                updates.append(f"{field} = {ph}")
                params.append(data[field])
                logger.debug(f"    {field}: {data[field]}")
        
        if not updates:
            logger.warning(f"  ⚠️ No fields to update!")
            return False
        
        params.append(record_id)
        
        query = f"""
            UPDATE interventions_techniciens 
            SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        
        logger.info(f"  🔄 Executing UPDATE for record ID {record_id}")
        logger.debug(f"     Query: {query}")
        logger.debug(f"     Params: {params}")
        
        result = conn.execute(query, params)
        logger.info(f"  ✅ Updated technician record ID {record_id} in intervention {intervention_id}")
        _trigger_backup()
        return True


def get_interventions_techniciens(intervention_id):
    """
    Récupère tous les enregistrements pour une intervention.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        list: Liste des techniciens assignés avec leurs données
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = ?
            ORDER BY created_at ASC
        """, (intervention_id,)).fetchall()
        return [dict(r) for r in rows]


def all_techniciens_completed(intervention_id):
    """
    Checks if all technicians have marked as Cloturee.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        bool: True if all techniciens have statut='Cloturee'
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN statut = 'Cloturee' THEN 1 ELSE 0 END) as completed
            FROM interventions_techniciens 
            WHERE intervention_id = ?
        """, (intervention_id,)).fetchone()
        
        if not row:
            return False
        
        total = row['total'] or 0
        completed = row['completed'] or 0
        
        return total > 0 and total == completed


def calculate_intervention_totals(intervention_id):
    """
    Calcule les totaux pour une intervention à partir des données per-technician.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        dict: {total_duree_minutes, total_duree_deplacement}
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT 
                COALESCE(SUM(duree_minutes_tech), 0) as total_duree,
                COALESCE(SUM(duree_deplacement_tech), 0) as total_deplacement
            FROM interventions_techniciens 
            WHERE intervention_id = ? AND statut = 'Terminé'
        """, (intervention_id,)).fetchone()
        
        if row:
            return {
                'total_duree_minutes': row['total_duree'] or 0,
                'total_duree_deplacement': row['total_deplacement'] or 0
            }
        
        return {'total_duree_minutes': 0, 'total_duree_deplacement': 0}


def consolidate_technician_duplicates(intervention_id):
    """
    Consolidates duplicate technician records (with reversed names) into one.
    When Sellami Ghazi and Ghazi Sellami exist, keeps one and merges data from both.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        int: Number of duplicates consolidated
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = str(name1).lower().strip()
        n2 = str(name2).lower().strip()
        
        if n1 == n2:
            return True
        
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    ph = "%s" if USE_PG else "?"
    consolidated = 0
    
    with get_db() as conn:
        # Get all records for this intervention
        rows = conn.execute(f"""
            SELECT id, technicien_nom, statut FROM interventions_techniciens 
            WHERE intervention_id = {ph}
            ORDER BY id ASC
        """, (intervention_id,)).fetchall()
        
        techs = [dict(r) for r in rows]
        processed = set()
        
        for i, tech1 in enumerate(techs):
            if tech1['id'] in processed:
                continue
            
            tech1_id = tech1['id']
            tech1_name = tech1['technicien_nom']
            tech1_status = tech1['statut']
            
            # Find all duplicates of this technician
            duplicates = []
            for j, tech2 in enumerate(techs):
                if i == j or tech2['id'] in processed:
                    continue
                
                if names_match(tech1_name, tech2['technicien_nom']):
                    duplicates.append(tech2)
            
            # If duplicates found, consolidate
            if duplicates:
                logger.info(f"  🔄 Consolidating {tech1_name}: found {len(duplicates)} duplicate(s)")
                
                # If primary is not Cloturee but a duplicate is, promote the duplicate
                if tech1_status != 'Cloturee':
                    for dup in duplicates:
                        if dup['statut'] == 'Cloturee':
                            # Copy Cloturee status to primary
                            conn.execute(f"""
                                UPDATE interventions_techniciens 
                                SET statut = 'Cloturee'
                                WHERE id = {ph}
                            """, (tech1_id,))
                            tech1_status = 'Cloturee'
                            logger.info(f"    ✅ Promoted primary record to Cloturee")
                            break
                
                # Delete duplicate records
                for dup in duplicates:
                    conn.execute(f"""
                        DELETE FROM interventions_techniciens 
                        WHERE id = {ph}
                    """, (dup['id'],))
                    processed.add(dup['id'])
                    consolidated += 1
                    logger.info(f"    🗑️ Deleted duplicate record ID {dup['id']}: {dup['technicien_nom']}")
        
        if consolidated > 0:
            _trigger_backup()
            logger.info(f"  ✅ Consolidated {consolidated} duplicate technician records for intervention {intervention_id}")
        
        return consolidated


def get_techniciens_status(intervention_id):
    """
    Gets the status of all technicians for an intervention.
    Returns completed count, total count, and list of pending technicians.
    Deduplicates technician names with reversed word order (e.g., "Ghazi Sellami" vs "Sellami Ghazi").
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        dict: {
            'total': total number of unique technicians,
            'completed': number completed (statut='Cloturee'),
            'pending_names': list of unique technician names not yet completed,
            'is_all_completed': bool
        }
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    with get_db() as conn:
        rows = conn.execute("""
            SELECT technicien_nom, statut FROM interventions_techniciens 
            WHERE intervention_id = ?
            ORDER BY technicien_nom
        """, (intervention_id,)).fetchall()
        
        techs = [dict(r) for r in rows]
        
        # Deduplicate technicians with reversed names
        unique_techs = []
        for tech in techs:
            tech_name = tech['technicien_nom']
            # Check if this technician already exists in unique list
            is_duplicate = any(names_match(unique['technicien_nom'], tech_name) 
                             for unique in unique_techs)
            if not is_duplicate:
                unique_techs.append(tech)
        
        total = len(unique_techs)
        completed = sum(1 for t in unique_techs if t.get('statut') == 'Cloturee')
        pending = [t['technicien_nom'] for t in unique_techs if t.get('statut') != 'Cloturee']
        
        return {
            'total': total,
            'completed': completed,
            'pending_names': pending,
            'is_all_completed': total > 0 and completed == total
        }


def get_child_interventions(parent_intervention_id):
    """
    Récupère toutes les interventions enfants d'une intervention parent.
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, technicien, statut FROM interventions 
            WHERE parent_intervention_id = ? AND is_temporary = 1
            ORDER BY technicien
        """, (parent_intervention_id,)).fetchall()
        return [dict(r) for r in rows]


def lire_child_interventions_for_technician(technician_name):
    """
    Récupère toutes les interventions enfants assignées à un technicien spécifique.
    Utilisé par les techniciens sur PWA pour voir leurs interventions enfants.
    """
    with get_db() as conn:
        # Query child interventions assigned to this technician
        base_query = """
            SELECT i.id, i.date, i.machine, i.technicien, i.type_intervention,
                   i.description, i.probleme, i.cause, i.solution,
                   i.pieces_utilisees, i.cout, i.cout_pieces, i.duree_minutes,
                   i.duree_deplacement,
                   i.code_erreur, i.statut, i.notes,
                   i.date_debut_intervention, i.date_cloture,
                   i.type_erreur, i.priorite,
                   i.start_time, i.end_time,
                   COALESCE(i.fiche_photo_nom, '') AS fiche_photo_nom,
                   COALESCE(i.fiche_validation, 'En attente') AS fiche_validation,
                   (i.fiche_photo_data IS NOT NULL AND octet_length(i.fiche_photo_data) > 0) AS has_fiche,
                   COALESCE(e.client, '') AS client,
                   i.parent_intervention_id
            FROM interventions i
            LEFT JOIN equipements e ON LOWER(e.nom) = LOWER(i.machine)
            WHERE i.is_temporary = 1 AND i.technicien LIKE ?
            ORDER BY i.date DESC
        """
        
        # Use wildcard matching for flexible tech name matching
        search_pattern = f"%{technician_name}%"
        df = read_sql(base_query, conn, params=(search_pattern,))
    
    # Apply text fixes
    text_columns = ["machine", "description", "probleme", "cause", "solution", "notes", "client"]
    if not df.empty:
        df = _fix_df_text(df, columns=text_columns)
    
    # Fill remaining NaN with empty string
    if "client" in df.columns:
        df["client"] = df["client"].fillna("")
    
    # Normalize statut
    if not df.empty and "statut" in df.columns:
        df["statut"] = df["statut"].apply(
            lambda s: "Cloturee" if "tur" in str(s).lower() else str(s)
        )
    
    return df


def finalize_intervention_from_techniciens(intervention_id):
    """
    Finalizes an intervention by aggregating all technician data.
    When ALL technicians mark as Cloturee, AUTOMATICALLY closes the parent intervention.
    Deduplicates technician names with reversed word order.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        dict: {
            'success': bool,
            'total_duree_minutes': int,
            'total_duree_deplacement': int,
            'combined_solution': str,
            'completed': int,
            'total': int
        }
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    with get_db() as conn:
        # Get ALL technician records (only aggregate Cloturee ones)
        rows = conn.execute("""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = ?
            ORDER BY technicien_nom
        """, (intervention_id,)).fetchall()
        
        if not rows:
            logger.warning(f"No technicians for intervention {intervention_id}")
            return {'success': False, 'error': 'No technicians found'}
        
        techs = [dict(r) for r in rows]
        
        # Deduplicate technicians with reversed names
        unique_techs = []
        for tech in techs:
            tech_name = tech['technicien_nom']
            # Check if this technician already exists in unique list
            is_duplicate = any(names_match(unique['technicien_nom'], tech_name) 
                             for unique in unique_techs)
            if not is_duplicate:
                unique_techs.append(tech)
        
        # Check if ALL are completed (using deduplicated count)
        completed_count = sum(1 for t in unique_techs if t.get('statut') == 'Cloturee')
        total_count = len(unique_techs)
        
        if completed_count != total_count:
            logger.info(f"Intervention {intervention_id}: Only {completed_count}/{total_count} completed, not finalizing yet")
            return {
                'success': False,
                'reason': 'not_all_completed',
                'completed': completed_count,
                'total': total_count
            }
        
        # Aggregate data from completed technicians
        completed_techs = [t for t in unique_techs if t.get('statut') == 'Cloturee']
        total_duree = sum(t.get('duree_minutes_tech') or 0 for t in completed_techs)
        total_deplacement = sum(t.get('duree_deplacement_tech') or 0 for t in completed_techs)
        
        # Combine technical notes
        solutions = [t.get('solution_tech', '').strip() for t in completed_techs if t.get('solution_tech', '').strip()]
        combined_solution = " | ".join(solutions) if solutions else ""
        
        # ✅ AUTOMATICALLY CLOSE the parent intervention (statut = 'Cloturee')
        # This is the key change - we now close it instead of leaving it "En cours"
        date_cloture = datetime.now().isoformat()
        
        conn.execute("""
            UPDATE interventions 
            SET statut = 'Cloturee',
                duree_minutes = ?,
                duree_deplacement = ?,
                solution = CASE WHEN solution = '' THEN ? ELSE solution END,
                date_cloture = ?
            WHERE id = ?
        """, (total_duree, total_deplacement, combined_solution, date_cloture, intervention_id))
        
        logger.info(f"✅ Intervention #{intervention_id} AUTOMATICALLY CLOSED after all {total_count} technicians completed")
        
        conn.commit()
        _trigger_backup()
        
        return {
            'success': True,
            'total_duree_minutes': total_duree,
            'total_duree_deplacement': total_deplacement,
            'combined_solution': combined_solution,
            'completed': completed_count,
            'total': total_count
        }
        
        _trigger_backup()
        logger.info(f"✅ Intervention {intervention_id} fully finalized: {total_count} technicians, {total_duree} minutes total")
        
        return {
            'success': True,
            'completed': completed_count,
            'total': total_count,
            'total_duree_minutes': total_duree,
            'total_duree_deplacement': total_deplacement,
            'combined_solution': combined_solution
        }
