import os
import re
import sqlite3
import logging
import pandas as pd
from datetime import datetime
from contextlib import contextmanager
from config import BASE_DIR

# --- Configuration du Logging (Audit Trail - Pillier 3) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("db_engine")

DB_PATH = os.path.join(BASE_DIR, "sic_radiologie.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

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
            notes TEXT DEFAULT ''
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
            role TEXT DEFAULT 'Lecteur' CHECK(role IN ('Admin', 'Technicien', 'Lecteur')),
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
            statut TEXT DEFAULT 'Planifiée' CHECK(statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard')),
            rappel_envoye INTEGER DEFAULT 0,
            recurrence TEXT DEFAULT '',
            notes TEXT DEFAULT ''
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
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
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

        # Migration : recréer la table avec UNIQUE(nom, client)
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
                    cur.execute(
                        f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {col_type} DEFAULT {default}"
                    )
                    conn._conn.commit()
                except Exception as e:
                    try:
                        conn._conn.rollback()
                    except Exception:
                        pass
                    logger.debug(f"Col {col} déjà présente sur {tbl} (PG)")
            else:
                try:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type} DEFAULT {default}")
                    logger.info(f"Colonne {col} ajoutée à {tbl}")
                except Exception:
                    pass  # Attendu si déjà là en SQLite


        # Migrations : colonnes ajoutées progressivement
        _safe_add_column("equipements", "matricule_fiscale")
        _safe_add_column("interventions", "date_debut_intervention", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "date_cloture", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "type_erreur")
        _safe_add_column("interventions", "priorite")
        _safe_add_column("contrats", "equipement")
        _safe_add_column("contrats", "fichier_contrat")
        _safe_add_column("equipements", "document_technique")

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
            type_contrat TEXT DEFAULT 'Standard',
            date_debut DATE NOT NULL,
            date_fin DATE NOT NULL,
            sla_temps_reponse_h INTEGER DEFAULT 24,
            interventions_incluses INTEGER DEFAULT -1,
            montant REAL DEFAULT 0.0,
            conditions TEXT DEFAULT '',
            statut TEXT DEFAULT 'Actif',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            statut TEXT DEFAULT 'non_lu',
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_lecture TIMESTAMP,
            date_traitement TIMESTAMP
        )
        """)

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
            conn.execute("""
                INSERT OR IGNORE INTO technicien_pii (tech_id, nom_complet, email, telegram_id)
                SELECT id, (IFNULL(nom, '') || ' ' || IFNULL(prenom, '')), email, telegram_id FROM techniciens
                WHERE nom != '' OR email != ''
            """)
            logger.info("Audit Trail: Migration PII effectuée avec succès.")
        except Exception as e:
            logger.debug(f"Migration PII ignorée (Pillar 2): {e}")


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
            df = read_sql("SELECT * FROM equipements ORDER BY client, nom", conn)
        if not df.empty:
            rename_map = {
                "nom": "Nom", "type": "Type", "fabricant": "Fabricant",
                "modele": "Modele", "num_serie": "NumSerie",
                "date_installation": "DateInstallation",
                "derniere_maintenance": "DernieresMaintenance",
                "statut": "Statut", "notes": "Notes",
                "client": "Client",
            }
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
            if "Client" in df.columns:
                df["Client"] = df["Client"].fillna("Centre Principal")
            df = _fix_df_text(df)
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
                                     date_installation, derniere_maintenance, statut, notes, client, matricule_fiscale, document_technique)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nom, client) DO UPDATE SET
                type=excluded.type, fabricant=excluded.fabricant, modele=excluded.modele,
                num_serie=excluded.num_serie, date_installation=excluded.date_installation,
                derniere_maintenance=excluded.derniere_maintenance, statut=excluded.statut,
                notes=excluded.notes, matricule_fiscale=excluded.matricule_fiscale,
                document_technique=excluded.document_technique
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
                notes = ?, client = ?, matricule_fiscale = ?, document_technique = ?
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
            equip_id,
        ))
    _trigger_backup()
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
    """Lit les interventions, optionnellement filtrées par machine."""
    with get_db() as conn:
        if machine:
            df = read_sql(
                "SELECT * FROM interventions WHERE machine = ? ORDER BY date DESC",
                conn, params=(machine,))
        else:
            df = read_sql("SELECT * FROM interventions ORDER BY date DESC", conn)
    df = _fix_df_text(df)
    # Normaliser le statut (gère TOUTE corruption d'encodage)
    if not df.empty and "statut" in df.columns:
        df["statut"] = df["statut"].apply(
            lambda s: "Cloturee" if "tur" in str(s).lower() else str(s)
        )
    return df


def ajouter_intervention(intervention_dict):
    """Ajoute une intervention."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO interventions (date, machine, technicien, type_intervention,
                                       description, probleme, cause, solution,
                                       pieces_utilisees, cout, duree_minutes,
                                       code_erreur, statut, notes, type_erreur, priorite)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ))
    _trigger_backup()
    return True


# ==========================================
# FONCTIONS CRUD — PLANNING MAINTENANCE
# ==========================================

def lire_planning(machine=None, statut=None):
    """Lit le planning de maintenance."""
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
        return read_sql(query, conn, params=params)


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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'non_lu')
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
    query = "SELECT * FROM notifications_pieces WHERE 1=1"
    params = []
    if destination:
        query += " AND destination = ?"
        params.append(destination)
    if statut:
        query += " AND statut = ?"
        params.append(statut)
    if technicien:
        query += " AND LOWER(technicien) = LOWER(?)"
        params.append(technicien)
    query += " ORDER BY date_creation DESC"
    with get_db() as conn:
        return read_sql(query, conn, params=params)


def compter_notifications_non_lues(destination, technicien=None):
    """Compte les notifications non lues pour une destination (et optionnellement un technicien)."""
    query = "SELECT COUNT(*) as cnt FROM notifications_pieces WHERE destination = ? AND statut = 'non_lu'"
    params = [destination]
    if technicien:
        query += " AND LOWER(technicien) = LOWER(?)"
        params.append(technicien)
    with get_db() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
        return row["cnt"] if row else 0


def marquer_notification_lue(notif_id):
    """Marque une notification comme lue."""
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications_pieces SET statut = 'lu', date_lecture = CURRENT_TIMESTAMP WHERE id = ?",
            (notif_id,)
        )
    return True


def marquer_notification_traitee(notif_id):
    """Marque une notification comme traitée."""
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications_pieces SET statut = 'traite', date_traitement = CURRENT_TIMESTAMP WHERE id = ?",
            (notif_id,)
        )
    return True


def notifications_rupture_pour_piece(piece_reference):
    """Retourne les notifications de rupture non traitées pour une pièce donnée."""
    with get_db() as conn:
        return read_sql(
            "SELECT * FROM notifications_pieces WHERE type = 'piece_rupture' AND piece_reference = ? AND statut != 'traite'",
            conn, params=(piece_reference,)
        )


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
    init_db()
    with get_db() as conn:
        # Vérifier colonnes table interventions
        cursor = conn.execute("PRAGMA table_info(interventions)")
        columns = [row["name"] for row in cursor.fetchall()]

        missing_cols = {
            "probleme": "TEXT DEFAULT ''",
            "cause": "TEXT DEFAULT ''",
            "solution": "TEXT DEFAULT ''",
            "cout_pieces": "REAL DEFAULT 0.0",
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
    Lit la liste des techniciens avec leurs PII jointes.
    
    Returns:
        pd.DataFrame: Liste des techniciens.
    """
    try:
        with get_db() as conn:
            return read_sql("""
                SELECT 
                    t.id, t.username, t.nom, t.prenom, t.specialite, 
                    t.qualification, t.dispo, t.notes,
                    p.nom_complet, 
                    COALESCE(p.email, t.email) as email, 
                    COALESCE(p.telephone, t.telephone) as telephone, 
                    COALESCE(p.telegram_id, t.telegram_id) as telegram_id
                FROM techniciens t
                LEFT JOIN technicien_pii p ON t.id = p.tech_id
                ORDER BY t.nom
            """, conn)
    except Exception as e:
        logger.error(f"Erreur lire_techniciens: {e}")
        return pd.DataFrame()

def ajouter_technicien(tech_dict):
    """
    Ajoute un technicien avec isolation PII.
    """
    try:
        with get_db() as conn:
            # 1. Info fonctionnelle
            res = conn.execute("""
                INSERT INTO techniciens (nom, prenom, specialite, qualification, dispo, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                tech_dict.get("nom", ""),
                tech_dict.get("prenom", ""),
                tech_dict.get("specialite", "Généraliste"),
                tech_dict.get("qualification", ""),
                tech_dict.get("dispo", 1),
                tech_dict.get("notes", "")
            ))
            tech_id = res.lastrowid
            
            # 2. Info PII (Pillier 2)
            nom_comp = f"{tech_dict.get('nom', '')} {tech_dict.get('prenom', '')}".strip()
            conn.execute("""
                INSERT INTO technicien_pii (tech_id, nom_complet, email, telephone, telegram_id)
                VALUES (?, ?, ?, ?, ?)
            """, (tech_id, nom_comp, tech_dict.get("email", ""), 
                  tech_dict.get("telephone", ""), tech_dict.get("telegram_id", "")))
        
        logger.info(f"Audit Trail: Nouveau technicien {nom_comp} ajouté (ID: {tech_id})")
        return True
    except Exception as e:
        logger.error(f"Erreur ajouter_technicien: {e}")
        return False

def update_technicien(tech_id, tech_dict):
    """
    Met à jour un technicien et ses PII.
    """
    try:
        with get_db() as conn:
            # Update functional data
            conn.execute("""
                UPDATE techniciens
                SET nom=?, prenom=?, specialite=?, qualification=?, dispo=?, notes=?
                WHERE id=?
            """, (
                tech_dict.get("nom", ""),
                tech_dict.get("prenom", ""),
                tech_dict.get("specialite", ""),
                tech_dict.get("qualification", ""),
                tech_dict.get("dispo", 1),
                tech_dict.get("notes", ""),
                tech_id
            ))
            
            # Update PII (Pillier 2)
            nom_comp = f"{tech_dict.get('nom', '')} {tech_dict.get('prenom', '')}".strip()
            exist = conn.execute("SELECT 1 FROM technicien_pii WHERE tech_id=?", (tech_id,)).fetchone()
            if not exist:
                conn.execute("""
                    INSERT INTO technicien_pii (tech_id, nom_complet, email, telephone, telegram_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (tech_id, nom_comp, tech_dict.get("email", ""), 
                      tech_dict.get("telephone", ""), tech_dict.get("telegram_id", "")))
            else:
                conn.execute("""
                    UPDATE technicien_pii 
                    SET nom_complet=?, email=?, telephone=?, telegram_id=?
                    WHERE tech_id=?
                """, (nom_comp, tech_dict.get("email", ""), 
                      tech_dict.get("telephone", ""), tech_dict.get("telegram_id", ""), tech_id))
        
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
    """Lit les contrats, optionnellement filtr\u00e9s par client."""
    with get_db() as conn:
        if client:
            return read_sql("SELECT * FROM contrats WHERE client=? ORDER BY date_fin DESC", conn, params=(client,))
        return read_sql("SELECT * FROM contrats ORDER BY date_fin DESC", conn)

def ajouter_contrat(contrat_dict):
    """Ajoute un contrat."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO contrats (client, type_contrat, date_debut, date_fin,
                sla_temps_reponse_h, interventions_incluses, montant, conditions, notes, fichier_contrat, equipement)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            contrat_dict.get("equipement", ""),
        ))
    _trigger_backup()

def modifier_contrat(contrat_id, contrat_dict):
    """Modifie un contrat existant."""
    with get_db() as conn:
        conn.execute("""
            UPDATE contrats SET client=?, type_contrat=?, date_debut=?, date_fin=?,
                sla_temps_reponse_h=?, interventions_incluses=?, montant=?, conditions=?, notes=?, statut=?,
                fichier_contrat=?, equipement=?
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
            contrat_dict.get("equipement", ""),
            contrat_id,
        ))
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

def cloturer_intervention(intervention_id, probleme, cause, solution, pieces_a_deduire=None, duree_minutes=None):
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
                ref = p['ref']
                qty = p['qty']
                prix = float(p.get('prix_unitaire', 0) or 0)
                if qty > 0:
                    print(f"[CLOTURE] Déduction stock: ref={ref}, qty={qty}, prix={prix}")
                    conn.execute("""
                        UPDATE pieces_rechange
                        SET stock_actuel = stock_actuel - ?
                        WHERE reference = ?
                    """, (qty, ref))
                    cout_piece = prix * qty
                    total_cout_pieces += cout_piece
                    synthese_pieces.append(f"{p['designation']} (x{qty} @ {prix:.0f})")
        else:
            print(f"[CLOTURE] Aucune pièce à déduire (pieces_a_deduire={pieces_a_deduire})")
        
        pieces_str = ", ".join(synthese_pieces)

        # Calculer le coût (taux_horaire × durée)
        duree_val = duree_minutes if duree_minutes is not None else 0
        cout_total = 0.0
        try:
            config_row = conn.execute("SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'").fetchone()
            taux_horaire = float(config_row["valeur"]) if config_row else 0.0
        except Exception:
            taux_horaire = 0.0
        cout_total = round((duree_val / 60) * taux_horaire, 2) + total_cout_pieces

        # 2. Mettre à jour l'intervention (date = date de clôture)
        date_cloture = datetime.now().isoformat()
        if pieces_str:
            # Utiliser COALESCE pour éviter le problème NULL || text = NULL en PostgreSQL
            conn.execute("""
                UPDATE interventions
                SET statut='Cloturee', probleme=?, cause=?, solution=?,
                    pieces_utilisees=COALESCE(pieces_utilisees, '') || ?, duree_minutes=?,
                    cout_pieces=?, cout=?, date=?
                WHERE id=?
            """, (probleme, cause, solution, f" | {pieces_str}", duree_val, total_cout_pieces, cout_total, date_cloture, intervention_id))
        else:
            conn.execute("""
                UPDATE interventions
                SET statut='Cloturee', probleme=?, cause=?, solution=?, duree_minutes=?, cout=?, date=?
                WHERE id=?
            """, (probleme, cause, solution, duree_val, cout_total, date_cloture, intervention_id))

        # 3. Récupérer le code erreur associé pour l'auto-apprentissage
        row = conn.execute("SELECT code_erreur, type_intervention, type_erreur FROM interventions WHERE id=?", (intervention_id,)).fetchone()
        code_erreur = row["code_erreur"] if row else ""

        # 4. Auto-Learning : Alimenter la table solutions si un code erreur existe
        # (sauf pour les Formations qui n'ont pas de diagnostic technique)
        type_intervention = row["type_intervention"] if row else ""
        type_erreur_val = row["type_erreur"] if row else "Hardware"
        if code_erreur and type_intervention != "Formation":
            conn.execute("""
                INSERT INTO solutions (mot_cle, type, priorite, cause, solution, validated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
