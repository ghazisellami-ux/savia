"""Database connection, compatibility wrapper, and schema initialization."""

import os
import re
import logging
import pandas as pd
from datetime import datetime
from contextlib import contextmanager
from functools import lru_cache
from urllib.parse import quote
from config import BASE_DIR
from sqlalchemy import create_engine

# --- Configuration du Logging (Audit Trail - Pillier 3) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("db_engine")

# PostgreSQL Configuration (required for operation)
# Construct DATABASE_URL from environment variables with proper URL encoding
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
        logger.info(f"Constructed DATABASE_URL: postgresql://{pg_user}:***@{pg_host}:{pg_port}/{pg_db}")
    else:
        logger.error("DATABASE_URL not set and cannot be constructed from environment variables")

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    logger.error("psycopg2 not found. Application requires psycopg2 to connect to PostgreSQL.")


# ---- PostgreSQL connection helper ----
class PostgresConnection:
    """Expose convenient execute helpers while keeping native PostgreSQL SQL."""
    
    def __init__(self, pg_conn):
        self._conn = pg_conn
    
    def execute(self, sql, params=None):
        """Execute one PostgreSQL statement and return a dictionary cursor."""
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur
    
    def executescript(self, sql):
        """Execute multiple statements separated by semicolons with SAVEPOINT isolation."""
        # Split by semicolons and execute each statement
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        
        for i, stmt in enumerate(statements):
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                # Use SAVEPOINT for each statement to allow failures without aborting transaction
                sp_name = f"sp_{i}"
                cur.execute(f"SAVEPOINT {sp_name}")
                cur.execute(stmt)
                cur.execute(f"RELEASE SAVEPOINT {sp_name}")
            except Exception as e:
                try:
                    # Rollback the savepoint if statement failed
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                except Exception:
                    pass
                
                # Log but continue (benign errors like "already exists")
                err_msg = str(e).lower()
                if any(x in err_msg for x in ["already exists", "duplicate", "does not exist"]):
                    logger.debug(f"[executescript] Benign error ignored: {e}")
                else:
                    logger.debug(f"[executescript] Statement {i} failed: {e}")
        
        return self._conn.cursor()
    
    def executemany(self, sql, seq_of_params):
        """Execute statement multiple times."""
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.executemany(sql, seq_of_params)
        return cur
    
    def cursor(self):
        """Return a psycopg2 cursor."""
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    def commit(self):
        """Commit transaction."""
        self._conn.commit()
    
    def rollback(self):
        """Rollback transaction."""
        self._conn.rollback()
    
    def close(self):
        """Close connection."""
        self._conn.close()
    
    @property
    def _raw(self):
        """Raw connection for direct access."""
        return self._conn


def _trigger_backup():
    """
    Backup n'est pas nécessaire en mode PostgreSQL (géré par le serveur).
    Cette fonction est conservée pour compatibilité mais est un no-op.
    """
    pass


def _auto_migrate_vps_schema(conn):
    """
    Auto-migration: Converts VPS schema (equipement_nom) to standard schema (equipement_id).
    
    Runs automatically on app startup - idempotent and safe.
    If schema is already standard, does nothing.
    If schema needs migration, converts it transparently.
    
    This allows seamless deployment to both new and legacy VPS instances.
    """
    try:
        cursor = conn.cursor()
        
        # Check if contrats_equipements table exists
        try:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'contrats_equipements'
                    AND table_schema = current_schema()
                ) AS table_exists
            """)
            result = cursor.fetchone()
            table_exists = bool(result and result["table_exists"])
        except Exception as table_check_error:
            logger.debug(f"Could not check if contrats_equipements exists: {table_check_error}")
            return
        
        if not table_exists:
            logger.debug("contrats_equipements table does not exist yet - will be created by init_db")
            return
        
        # Check current schema
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'contrats_equipements'
                AND table_schema = current_schema()
            """)
            columns = {row["column_name"] for row in cursor.fetchall()}
        except Exception as schema_check_error:
            logger.debug(f"Could not check contrats_equipements schema: {schema_check_error}")
            return
        
        has_equipement_id = 'equipement_id' in columns
        has_equipement_nom = 'equipement_nom' in columns
        
        # Already migrated - nothing to do
        if has_equipement_id and not has_equipement_nom:
            logger.debug("✅ VPS schema already migrated (equipement_id exists, equipement_nom removed)")
            return
        
        # If only equipement_nom exists (need migration)
        if has_equipement_nom and not has_equipement_id:
            logger.info("⚠️  VPS legacy schema detected (equipement_nom exists) - starting auto-migration...")
            
            # Step 1: Add equipement_id column
            try:
                cursor.execute("""
                    ALTER TABLE contrats_equipements 
                    ADD COLUMN equipement_id INTEGER
                """)
                conn.commit()
                logger.info("✅ Added equipement_id column")
            except Exception as add_col_error:
                logger.warning(f"Could not add equipement_id column: {add_col_error}")
                try:
                    conn.rollback()
                except:
                    pass
                return
            
            # Step 2: Populate equipement_id from equipement_nom via FK join
            try:
                cursor.execute("""
                    UPDATE contrats_equipements ce
                    SET equipement_id = e.id
                    FROM equipements e
                    WHERE ce.equipement_nom = e.nom
                    AND ce.equipement_id IS NULL
                """)
                rows_updated = cursor.rowcount
                conn.commit()
                logger.info(f"✅ Populated {rows_updated} rows with equipement_id from equipement_nom")
            except Exception as populate_error:
                logger.warning(f"Could not populate equipement_id: {populate_error}")
                try:
                    conn.rollback()
                except:
                    pass
                return
            
            # Step 3: Add FK constraint if it doesn't exist
            try:
                cursor.execute("""
                    SELECT constraint_name FROM information_schema.table_constraints 
                    WHERE table_name = 'contrats_equipements' 
                    AND constraint_type = 'FOREIGN KEY'
                    AND constraint_name LIKE '%equipement_id%'
                """)
                fk_result = cursor.fetchone()
                fk_exists = fk_result is not None
                
                if not fk_exists:
                    cursor.execute("""
                        ALTER TABLE contrats_equipements
                        ADD CONSTRAINT contrats_equipements_equipement_id_fkey
                        FOREIGN KEY (equipement_id) REFERENCES equipements(id) ON DELETE RESTRICT
                    """)
                    conn.commit()
                    logger.info("✅ Added FK constraint on equipement_id")
            except Exception as fk_error:
                logger.warning(f"Could not add FK constraint: {fk_error}")
                try:
                    conn.rollback()
                except:
                    pass
                return
            
            # Step 4: Remove equipement_nom column (cleanup)
            try:
                cursor.execute("ALTER TABLE contrats_equipements DROP COLUMN equipement_nom")
                conn.commit()
                logger.info("✅ Removed equipement_nom column - migration complete!")
            except Exception as drop_col_error:
                logger.warning(f"Could not drop equipement_nom column: {drop_col_error}")
                try:
                    conn.rollback()
                except:
                    pass
                return
            
            return
        
        # Both columns exist (partial migration state) - finish it
        if has_equipement_id and has_equipement_nom:
            logger.info("⚠️  Partial migration detected (both columns exist) - completing...")
            
            # Populate any remaining empty equipement_id values
            try:
                cursor.execute("""
                    UPDATE contrats_equipements ce
                    SET equipement_id = e.id
                    FROM equipements e
                    WHERE ce.equipement_nom = e.nom
                    AND ce.equipement_id IS NULL
                """)
                rows_updated = cursor.rowcount
                if rows_updated > 0:
                    conn.commit()
                    logger.info(f"✅ Populated {rows_updated} remaining rows")
            except Exception as partial_populate_error:
                logger.warning(f"Could not populate remaining equipement_id: {partial_populate_error}")
                try:
                    conn.rollback()
                except:
                    pass
                return
            
            # Add FK constraint if missing
            try:
                cursor.execute("""
                    SELECT constraint_name FROM information_schema.table_constraints 
                    WHERE table_name = 'contrats_equipements' 
                    AND constraint_type = 'FOREIGN KEY'
                    AND constraint_name LIKE '%equipement_id%'
                """)
                fk_result = cursor.fetchone()
                fk_exists = fk_result is not None
                
                if not fk_exists:
                    cursor.execute("""
                        ALTER TABLE contrats_equipements
                        ADD CONSTRAINT contrats_equipements_equipement_id_fkey
                        FOREIGN KEY (equipement_id) REFERENCES equipements(id) ON DELETE RESTRICT
                    """)
                    conn.commit()
                    logger.info("✅ Added missing FK constraint")
            except Exception as partial_fk_error:
                logger.warning(f"Could not add missing FK constraint: {partial_fk_error}")
                try:
                    conn.rollback()
                except:
                    pass
                return
            
            # Remove equipement_nom column
            try:
                cursor.execute("ALTER TABLE contrats_equipements DROP COLUMN equipement_nom")
                conn.commit()
                logger.info("✅ Removed equipement_nom column - migration complete!")
            except Exception as partial_drop_error:
                logger.warning(f"Could not drop equipement_nom column in partial migration: {partial_drop_error}")
                try:
                    conn.rollback()
                except:
                    pass
                return
            
            return
    
    except Exception as e:
        logger.warning(f"Auto-migration encountered unexpected issue: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        # Don't fail startup - log warning but continue
        # The app will still work, just with the old schema if migration failed





@lru_cache(maxsize=1)
def _get_pandas_engine():
    """Return the shared SQLAlchemy engine used by pandas reads."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    # Some VPS providers still expose the legacy postgres:// scheme.
    # SQLAlchemy expects the explicit postgresql:// dialect name.
    sqlalchemy_url = DATABASE_URL
    if sqlalchemy_url.startswith("postgres://"):
        sqlalchemy_url = "postgresql://" + sqlalchemy_url[len("postgres://"):]
    return create_engine(sqlalchemy_url, pool_pre_ping=True)


def read_sql(query, conn, params=None):
    """
    Lecture SQL compatible PostgreSQL.
    
    Args:
        query (str): Requête SQL PostgreSQL (placeholders %s).
        conn (PostgresConnection): Connexion PostgreSQL.
        params (tuple, optional): Paramètres de la requête.
        
    Returns:
        pd.DataFrame: Résultats sous forme de DataFrame.
    """
    try:
        # pandas officially supports SQLAlchemy connections, not the custom
        # PostgresConnection object used by the rest of the application.
        with _get_pandas_engine().connect() as pandas_conn:
            return pd.read_sql_query(query, pandas_conn, params=params)
    except Exception as e:
        logger.error(f"Erreur read_sql: {e}")
        return pd.DataFrame()


_PIECE_REF_RE = re.compile(r"\bRef(?:erence)?\s*[:#-]\s*([^|\n;,]+)", re.IGNORECASE)
_PIECE_QTY_RE = re.compile(r"\b(?:Qty|Qte|Quantite|Quantité)\s*[:#-]\s*(\d+)", re.IGNORECASE)
_PIECE_PAREN_REF_RE = re.compile(r"\(([^()]+)\)")


def _extract_piece_refs_from_text(pieces_text):
    refs = []
    text = str(pieces_text or "")
    for line in re.split(r"[\n;]+", text):
        ref_match = _PIECE_REF_RE.search(line)
        if ref_match:
            refs.append(ref_match.group(1).strip())
            continue

        for ref in _PIECE_PAREN_REF_RE.findall(line):
            clean_ref = ref.strip()
            if clean_ref:
                refs.append(clean_ref)
    return refs


def _pieces_cost_from_text(pieces_text, price_by_ref):
    total = 0.0
    text = str(pieces_text or "")
    for line in re.split(r"[\n;]+", text):
        ref_match = _PIECE_REF_RE.search(line)
        if ref_match:
            ref = ref_match.group(1).strip()
            qty_match = _PIECE_QTY_RE.search(line)
            qty = int(qty_match.group(1)) if qty_match else 1
            total += float(price_by_ref.get(ref.lower(), 0) or 0) * qty
            continue

        for ref in _PIECE_PAREN_REF_RE.findall(line):
            clean_ref = ref.strip()
            if clean_ref:
                total += float(price_by_ref.get(clean_ref.lower(), 0) or 0)
    return round(total, 2)


def _fill_missing_cout_pieces(df, conn):
    """Backfill display/API cost for legacy rows with pieces_utilisees but cout_pieces=0."""
    if df.empty or "pieces_utilisees" not in df.columns:
        return df

    if "cout_pieces" not in df.columns:
        df["cout_pieces"] = 0.0

    current_costs = pd.to_numeric(df["cout_pieces"], errors="coerce").fillna(0)
    pieces_text = df["pieces_utilisees"].fillna("").astype(str)
    missing_mask = current_costs.le(0) & pieces_text.str.strip().ne("")
    if not missing_mask.any():
        return df

    refs = set()
    for text in pieces_text[missing_mask]:
        refs.update(ref.lower() for ref in _extract_piece_refs_from_text(text) if ref)
    if not refs:
        return df

    try:
        placeholders = ", ".join(["%s"] * len(refs))
        rows = conn.execute(
            f"SELECT reference, prix_unitaire FROM pieces_rechange WHERE LOWER(reference) IN ({placeholders})",
            tuple(refs)
        ).fetchall()
        price_by_ref = {
            str(row.get("reference") or "").strip().lower(): float(row.get("prix_unitaire") or 0)
            for row in rows
        }
    except Exception as e:
        logger.warning(f"Unable to backfill cout_pieces from pieces_utilisees: {e}")
        return df

    for idx in df.index[missing_mask]:
        cost = _pieces_cost_from_text(df.at[idx, "pieces_utilisees"], price_by_ref)
        if cost > 0:
            df.at[idx, "cout_pieces"] = cost
    return df


@contextmanager
def get_db():
    """
    Context manager pour les connexions DB (PostgreSQL uniquement).
    
    Logic:
        Initialise la connexion PostgreSQL, gère l'encodage client UTF8,
        et gère le commit/rollback automatique en cas d'erreur.
    
    Yields:
        PostgresConnection: Connexion PostgreSQL avec curseurs dictionnaires.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_client_encoding('UTF8')
        wrapped = PostgresConnection(conn)
        try:
            yield wrapped
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction DB échouée: {e}")
            raise
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Impossible de se connecter à PostgreSQL: {e}")
        raise


def init_db():
    """Crée toutes les tables si elles n'existent pas."""
    with get_db() as conn:
        conn.executescript("""
        -- Codes d'erreurs hexadécimaux
        CREATE TABLE IF NOT EXISTS codes_erreurs (
            id SERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            message TEXT DEFAULT '',
            niveau TEXT DEFAULT 'ATTENTION',
            type TEXT DEFAULT 'Hardware',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Solutions associées aux erreurs
        CREATE TABLE IF NOT EXISTS solutions (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL UNIQUE,
            matricule_fiscale TEXT DEFAULT '',
            country_code TEXT DEFAULT 'TN',
            ville TEXT DEFAULT '',
            contact TEXT DEFAULT '',
            telephone TEXT DEFAULT '',
            adresse TEXT DEFAULT '',
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Types de clients personnalisés
        CREATE TABLE IF NOT EXISTS types_client_custom (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL UNIQUE,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Villes ajoutées par l'administrateur, réutilisables par pays
        CREATE TABLE IF NOT EXISTS villes_custom (
            id SERIAL PRIMARY KEY,
            country_code TEXT NOT NULL,
            nom TEXT NOT NULL,
            latitude REAL NULL,
            longitude REAL NULL,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(country_code, nom)
        );

        -- Pays ajoutés manuellement dans les paramètres
        CREATE TABLE IF NOT EXISTS pays_custom (
            id SERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            nom TEXT NOT NULL UNIQUE,
            flag TEXT DEFAULT '🌍',
            latitude REAL NULL,
            longitude REAL NULL,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Parc d'équipements
        CREATE TABLE IF NOT EXISTS equipements (
            id SERIAL PRIMARY KEY,
            nom TEXT NOT NULL,
            type TEXT DEFAULT '',
            fabricant TEXT DEFAULT '',
            modele TEXT DEFAULT '',
            num_serie TEXT DEFAULT '',
            date_installation TEXT DEFAULT '',
            derniere_maintenance TEXT DEFAULT '',
            statut TEXT DEFAULT 'Opérationnel',
            notes TEXT DEFAULT '',
            client TEXT DEFAULT 'Centre Principal'
        );

        -- Interventions de maintenance
        CREATE TABLE IF NOT EXISTS interventions (
            id SERIAL PRIMARY KEY,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            machine TEXT NOT NULL,
            equipement_id INTEGER,
            technicien_id INTEGER,
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
            date_transfert_atelier TIMESTAMP DEFAULT NULL,
            retour_site_confirme BOOLEAN DEFAULT false,
            date_retour_site TIMESTAMP DEFAULT NULL,
            retour_site_confirme_par TEXT DEFAULT '',
            is_temporary INTEGER DEFAULT 0,           -- 1 = intervention enfant temporaire
            parent_intervention_id INTEGER DEFAULT NULL -- ID de l'intervention parent (NULL si parent)
        );

        -- Techniciens (détails étendus)
        CREATE TABLE IF NOT EXISTS techniciens (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            nom_complet TEXT DEFAULT '',
            role TEXT DEFAULT 'Technicien' CHECK(role IN ('Admin', 'Technicien', 'Lecteur', 'Manager', 'Responsable Technique', 'Gestionnaire', 'Gestionnaire de stock')),
            client TEXT DEFAULT '',
            email TEXT DEFAULT '',
            actif INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            must_change_password BOOLEAN DEFAULT false,
            password_version INTEGER DEFAULT 1
        );

        -- Journal d'audit
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            username TEXT DEFAULT 'system',
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            page TEXT DEFAULT '',
            ip_address TEXT DEFAULT ''
        );

        -- Audit Trail IA (EU AI Act Article 12)
        CREATE TABLE IF NOT EXISTS ai_audit_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model_version TEXT NOT NULL,
            prompt_hash TEXT DEFAULT '',
            confidence_score INTEGER DEFAULT 0,
            outcome TEXT DEFAULT ''
        );

        -- Feedback sur les prédictions (HITL — Human-in-the-Loop)
        CREATE TABLE IF NOT EXISTS prediction_feedback (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            machine TEXT NOT NULL,
            equipement_id INTEGER,
            technicien_id INTEGER,
            technicien_ids TEXT DEFAULT '[]',
            client TEXT DEFAULT '',
            type_maintenance TEXT DEFAULT 'Préventive',
            description TEXT DEFAULT '',
            date_prevue DATE NOT NULL,
            date_realisee DATE,
            technicien_assigne TEXT DEFAULT '',
            statut TEXT DEFAULT 'Planifiée' CHECK(statut IN ('Planifiée', 'En cours', 'Cloturee', 'En retard', 'Décalé')),
            rappel_envoye INTEGER DEFAULT 0,
            recurrence TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            is_ghost BOOLEAN DEFAULT false
        );

        -- Pièces de rechange
        CREATE TABLE IF NOT EXISTS pieces_rechange (
            id SERIAL PRIMARY KEY,
            reference TEXT NOT NULL UNIQUE,
            designation TEXT NOT NULL,
            equipement_type TEXT DEFAULT '',
            stock_actuel INTEGER DEFAULT 0,
            stock_minimum INTEGER DEFAULT 1,
            fournisseur TEXT DEFAULT '',
            prix_unitaire REAL DEFAULT 0.0,
            prix_usd REAL DEFAULT 0.0,
            prix_eur REAL DEFAULT 0.0,
            derniere_commande DATE,
            notes TEXT DEFAULT ''
        );

        -- Configuration client (branding)
        CREATE TABLE IF NOT EXISTS config_client (
            cle TEXT PRIMARY KEY,
            valeur TEXT DEFAULT ''
        );

        -- Insérer config par défaut si absente
        INSERT INTO config_client (cle, valeur) VALUES
            ('nom_organisation', 'SIC Radiologie'),
            ('logo_path', ''),
            ('langue', 'fr'),
            ('theme', 'dark')
        ON CONFLICT (cle) DO NOTHING;

        -- Télémétrie IoT
        CREATE TABLE IF NOT EXISTS telemetry (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            equipement TEXT NOT NULL,
            equipement_id INTEGER,
            client TEXT DEFAULT '',
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            intervention_id INTEGER NOT NULL,
            technicien_id INTEGER,
            technicien_nom TEXT NOT NULL,
            statut TEXT DEFAULT 'Assigné' CHECK(statut IN ('Assigné', 'En cours', 'Transfert vers l''atelier', 'Cloturee', 'Refusé', 'En attente de piece', 'En attente de pièce')),
            probleme_tech TEXT DEFAULT '',
            cause_tech TEXT DEFAULT '',
            solution_tech TEXT DEFAULT '',
            heure_debut_tech TIME,
            heure_fin_tech TIME,
            duree_minutes_tech INTEGER DEFAULT 0,
            duree_deplacement_tech INTEGER DEFAULT 0,
            notes_tech TEXT DEFAULT '',
            type_erreur_tech TEXT DEFAULT '',
            pieces_a_deduire TEXT DEFAULT '',
            stock_deducted BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (intervention_id) REFERENCES interventions(id) ON DELETE CASCADE
        );
        """)
        
        # These columns must exist before creating their index on databases
        # created by an earlier SAVIA release.
        conn.execute("ALTER TABLE logs_uploaded ADD COLUMN IF NOT EXISTS equipement_id INTEGER")
        conn.execute("ALTER TABLE logs_uploaded ADD COLUMN IF NOT EXISTS client TEXT DEFAULT ''")

        # Ajouter les indexes pour améliorer les performances
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_uploaded_equipement ON logs_uploaded(equipement);
        """)
        conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_uploaded_equipement_id ON logs_uploaded(equipement_id);
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
            savepoint = "migration_statement"
            try:
                conn.execute(f"SAVEPOINT {savepoint}")
                conn.execute(sql)
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                logger.info(f"Migration réussie: {description}")
            except Exception as e:
                # Une migration déjà appliquée ne doit pas annuler ni bloquer les suivantes.
                try:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                except Exception:
                    conn.rollback()
                logger.debug(f"Migration ignorée ({description}): {e}")

        # Migration helper PostgreSQL: ajouter une colonne si elle n'existe pas.
        def _safe_add_column(tbl, col, col_type="TEXT", default="''"):
            """Ajoute une colonne de manière sécurisée sans interrompre le flux."""
            try:
                cur = conn.cursor()
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
                    conn.commit()
                    logger.info(f"✅ Colonne {col} ajoutée à {tbl}")
                else:
                    logger.debug(f"ℹ️  Colonne {col} déjà présente sur {tbl}")
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.debug(f"⚠️  Erreur lors de l'ajout de {col} à {tbl}: {e}")

        _safe_add_column("equipements", "client", "TEXT", "'Centre Principal'")
        _safe_add_column("techniciens", "telegram_id")
        _safe_add_column("planning_maintenance", "client")
        _safe_add_column("utilisateurs", "client")
        _safe_add_column("utilisateurs", "password_changed_at", "TIMESTAMP", "CURRENT_TIMESTAMP")
        _safe_add_column("utilisateurs", "must_change_password", "BOOLEAN", "false")
        _safe_add_column("utilisateurs", "password_version", "INTEGER", "1")
        conn.execute("""
            UPDATE utilisateurs
            SET password_changed_at = COALESCE(password_changed_at, last_login, created_at, CURRENT_TIMESTAMP),
                password_version = COALESCE(password_version, 1),
                must_change_password = COALESCE(must_change_password, false)
        """)
        _safe_add_column("equipements", "domaine", "TEXT", "'Radiologie'")
        _safe_add_column("equipements", "est_annexe", "BOOLEAN", "false")
        _safe_add_column("equipements", "garantie_debut")
        _safe_add_column("equipements", "garantie_duree", "INTEGER", "0")
        _safe_add_column("pieces_rechange", "domaine", "TEXT", "'Radiologie'")
        _safe_add_column("pieces_rechange", "est_annexe", "BOOLEAN", "false")
        _safe_add_column("pieces_rechange", "prix_usd", "REAL", "0.0")
        _safe_add_column("pieces_rechange", "prix_eur", "REAL", "0.0")
        
        # --- NEW MIGRATIONS: Advanced prediction parameters (using safe add for PostgreSQL compatibility) ---
        _safe_add_column("pieces_rechange", "consommation_moyenne_mois", "REAL", "1.0")
        _safe_add_column("pieces_rechange", "delai_fournisseur_jours", "INTEGER", "14")
        _safe_add_column("pieces_rechange", "criticite", "VARCHAR(20)", "'NORMAL'")
        _safe_add_column("pieces_rechange", "nombre_equipements_relies", "INTEGER", "1")
        _safe_add_column("pieces_rechange", "utilisation_recente_30j", "INTEGER", "0")
        _safe_add_column("pieces_rechange", "data_confidence", "VARCHAR(20)", "'INSUFFICIENT'")
        
        _safe_add_column("logs_uploaded", "parsed_errors", "TEXT", "NULL")
        _safe_add_column("logs_uploaded", "equipement_id", "INTEGER", "NULL")
        _safe_add_column("logs_uploaded", "client", "TEXT", "''")
        
        # Migration: Ghost entry tracking for reschedule feature
        _safe_add_column("planning_maintenance", "is_ghost", "BOOLEAN", "false")

        # Migrations : colonnes ajoutées progressivement
        _safe_add_column("equipements", "matricule_fiscale")
        _safe_add_column("interventions", "date_debut_intervention", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "date_cloture", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "date_transfert_atelier", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "retour_site_confirme", "BOOLEAN", "false")
        _safe_add_column("interventions", "date_retour_site", "TIMESTAMP", "NULL")
        _safe_add_column("interventions", "retour_site_confirme_par", "TEXT", "''")
        _safe_add_column("interventions", "type_erreur")
        _safe_add_column("interventions", "priorite")
        _safe_add_column("contrats", "equipement")
        _safe_add_column("contrats", "fichier_contrat")
        _safe_add_column("contrats", "fichier_storage_key", "TEXT", "NULL")
        _safe_add_column("contrats", "fichier_content_type", "TEXT", "NULL")
        _safe_add_column("contrats", "fichier_size_bytes", "BIGINT", "NULL")
        _safe_add_column("contrats", "fichier_sha256", "TEXT", "NULL")
        # Empty storage keys are not attachments. Normalize legacy rows and
        # remove the empty-string default so the partial unique index remains
        # compatible with contracts created after migration 008.
        try:
            conn.execute(
                "UPDATE contrats SET fichier_storage_key = NULL "
                "WHERE BTRIM(COALESCE(fichier_storage_key, '')) = ''"
            )
            conn.execute("ALTER TABLE contrats ALTER COLUMN fichier_storage_key DROP DEFAULT")
        except Exception as e:
            logger.debug(f"Migration clé stockage contrats ignorée: {e}")
        _safe_add_column("equipements", "document_technique")
        # Prediction feedback needs the equipment identity and forecast context
        # to support honest temporal validation and post-deployment calibration.
        _safe_add_column("prediction_feedback", "equipment_id", "INTEGER", "NULL")
        _safe_add_column("prediction_feedback", "client", "TEXT", "''")
        _safe_add_column("prediction_feedback", "horizon_jours", "INTEGER", "30")
        _safe_add_column("prediction_feedback", "risque_pct", "REAL", "NULL")
        _safe_add_column("prediction_feedback", "modele_version", "TEXT", "''")
        _safe_add_column("prediction_feedback", "date_calcul", "TEXT", "''")
        _safe_add_column("prediction_feedback", "features_json", "TEXT", "NULL")
        _run_migration(
            "CREATE INDEX IF NOT EXISTS idx_prediction_feedback_equipment "
            "ON prediction_feedback(equipment_id, timestamp DESC)",
            "index feedback prédictions par équipement",
        )
        # Feedback dédié aux prévisions de réapprovisionnement des pièces.
        # Les valeurs calculées sont conservées pour mesurer la qualité du moteur.
        _run_migration(
            """
            CREATE TABLE IF NOT EXISTS spare_parts_prediction_feedback (
                id SERIAL PRIMARY KEY,
                reference TEXT NOT NULL,
                designation TEXT DEFAULT '',
                resultat TEXT NOT NULL CHECK(resultat IN ('correct', 'faux_positif', 'decale')),
                date_calcul TEXT DEFAULT '',
                date_predite TEXT DEFAULT '',
                date_reelle TEXT DEFAULT '',
                quantite INTEGER NULL,
                risque_rupture_pct REAL NULL,
                modele_version TEXT DEFAULT '',
                features_json TEXT NULL,
                username TEXT DEFAULT 'system',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "feedback previsions pieces",
        )
        _run_migration(
            "CREATE INDEX IF NOT EXISTS idx_spare_parts_feedback_reference "
            "ON spare_parts_prediction_feedback(reference, timestamp DESC)",
            "index feedback previsions pieces",
        )

        # Geographic coordinates for map feature
        _safe_add_column("equipements", "latitude", "REAL", "NULL")
        _safe_add_column("equipements", "longitude", "REAL", "NULL")
        _safe_add_column("equipements", "adresse")
        _safe_add_column("equipements", "ville")
        _safe_add_column("equipements", "region")

        # Client enrichment columns
        _safe_add_column("clients", "code_client")
        _safe_add_column("clients", "country_code", "TEXT", "'TN'")
        _safe_add_column("clients", "region")
        _safe_add_column("clients", "type_client")
        _safe_add_column("clients", "international", "BOOLEAN", "false")
        _safe_add_column("clients", "latitude", "REAL", "NULL")
        _safe_add_column("clients", "longitude", "REAL", "NULL")
        _safe_add_column("villes_custom", "latitude", "REAL", "NULL")
        _safe_add_column("villes_custom", "longitude", "REAL", "NULL")
        _safe_add_column("pays_custom", "latitude", "REAL", "NULL")
        _safe_add_column("pays_custom", "longitude", "REAL", "NULL")

        # Service column on equipements
        _safe_add_column("equipements", "service")

        # Contract → Planning auto-generation columns
        _safe_add_column("contrats", "recurrence_maintenance")
        _safe_add_column("contrats", "date_premiere_maintenance")
        _safe_add_column("contrats", "date_derniere_maintenance", "DATE", "NULL")
        _safe_add_column("contrats", "date_signature", "DATE", "NULL")
        _safe_add_column("planning_maintenance", "contrat_id", "INTEGER", "NULL")

        # Ghost entry tracking for reschedule feature (prevent duplicates on multiple reschedules)
        _safe_add_column("planning_maintenance", "original_planning_id", "INTEGER", "NULL")

        # User profile & page permissions (used by admin panel)
        _safe_add_column("utilisateurs", "profil")
        _safe_add_column("utilisateurs", "pages_autorisees")

        # Notification schedules table migration (create if not exists)
        try:
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
        _safe_add_column("interventions", "technicien_id", "INTEGER", "NULL")
        _safe_add_column("planning_maintenance", "technicien_id", "INTEGER", "NULL")
        _safe_add_column("planning_maintenance", "technicien_ids", "TEXT", "'[]'")

        # Interventions_techniciens table migration (per-technician tracking)
        try:
            # PostgreSQL syntax
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interventions_techniciens (
                    id SERIAL PRIMARY KEY,
                    intervention_id INTEGER NOT NULL,
                    technicien_id INTEGER,
                    technicien_nom TEXT NOT NULL,
                    statut TEXT DEFAULT 'Assigné' CHECK(statut IN ('Assigné', 'En cours', 'Transfert vers l''atelier', 'Cloturee', 'Refusé', 'En attente de piece', 'En attente de pièce')),
                    probleme_tech TEXT DEFAULT '',
                    cause_tech TEXT DEFAULT '',
                    solution_tech TEXT DEFAULT '',
                    heure_debut_tech TIME,
                    heure_fin_tech TIME,
                    duree_minutes_tech INTEGER DEFAULT 0,
                    duree_deplacement_tech INTEGER DEFAULT 0,
                    notes_tech TEXT DEFAULT '',
                    type_erreur_tech TEXT DEFAULT '',
                    pieces_a_deduire TEXT DEFAULT '',
                    stock_deducted BOOLEAN NOT NULL DEFAULT FALSE,
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

        _safe_add_column("interventions_techniciens", "type_erreur_tech", "TEXT", "''")
        _safe_add_column("interventions_techniciens", "pieces_a_deduire", "TEXT", "''")
        _safe_add_column("interventions_techniciens", "stock_deducted", "BOOLEAN", "FALSE")

        # Backfill technician identifiers for legacy name-based assignments.
        # Keep the text columns for display and backwards compatibility.
        try:
            conn.execute("""
                WITH unique_matches AS (
                    SELECT pm0.id, MIN(t.id) AS technician_id
                    FROM planning_maintenance pm0
                    JOIN techniciens t ON (
                        LOWER(BTRIM(pm0.technicien_assigne)) = LOWER(BTRIM(CONCAT(t.prenom, ' ', t.nom)))
                        OR LOWER(BTRIM(pm0.technicien_assigne)) = LOWER(BTRIM(CONCAT(t.nom, ' ', t.prenom)))
                        OR LOWER(BTRIM(pm0.technicien_assigne)) = LOWER(BTRIM(t.username))
                    )
                    WHERE pm0.technicien_id IS NULL
                      AND pm0.technicien_assigne NOT LIKE '%,%'
                    GROUP BY pm0.id HAVING COUNT(DISTINCT t.id) = 1
                )
                UPDATE planning_maintenance pm
                   SET technicien_id = m.technician_id,
                       technicien_ids = CASE WHEN pm.technicien_ids IS NULL OR pm.technicien_ids = '[]'
                                             THEN '[' || m.technician_id::text || ']' ELSE pm.technicien_ids END
                  FROM unique_matches m WHERE pm.id = m.id
            """)
            conn.execute("""
                WITH unique_matches AS (
                    SELECT i0.id, MIN(t.id) AS technician_id
                    FROM interventions i0
                    JOIN techniciens t ON (
                        LOWER(BTRIM(i0.technicien)) = LOWER(BTRIM(CONCAT(t.prenom, ' ', t.nom)))
                        OR LOWER(BTRIM(i0.technicien)) = LOWER(BTRIM(CONCAT(t.nom, ' ', t.prenom)))
                        OR LOWER(BTRIM(i0.technicien)) = LOWER(BTRIM(t.username))
                    )
                    WHERE i0.technicien_id IS NULL AND i0.technicien NOT LIKE '%,%'
                    GROUP BY i0.id HAVING COUNT(DISTINCT t.id) = 1
                )
                UPDATE interventions i SET technicien_id = m.technician_id
                FROM unique_matches m WHERE i.id = m.id
            """)
            conn.execute("""
                WITH unique_matches AS (
                    SELECT it0.id, MIN(t.id) AS technician_id
                    FROM interventions_techniciens it0
                    JOIN techniciens t ON (
                        LOWER(BTRIM(it0.technicien_nom)) = LOWER(BTRIM(CONCAT(t.prenom, ' ', t.nom)))
                        OR LOWER(BTRIM(it0.technicien_nom)) = LOWER(BTRIM(CONCAT(t.nom, ' ', t.prenom)))
                        OR LOWER(BTRIM(it0.technicien_nom)) = LOWER(BTRIM(t.username))
                    )
                    WHERE it0.technicien_id IS NULL
                    GROUP BY it0.id HAVING COUNT(DISTINCT t.id) = 1
                )
                UPDATE interventions_techniciens it SET technicien_id = m.technician_id
                FROM unique_matches m WHERE it.id = m.id
            """)
        except Exception as e:
            logger.debug(f"Technician ID backfill skipped: {e}")

        # Ensure commit after all _safe_add_column migrations
        try:
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass



        # Fabricants table
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fabricants (
                    id SERIAL PRIMARY KEY,
                    nom TEXT UNIQUE NOT NULL
                )
            """)
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
        # Suppliers used by spare parts. Keep this catalog separate from
        # equipment manufacturers so each form can offer the right choices.
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fournisseurs (
                    id SERIAL PRIMARY KEY,
                    nom TEXT UNIQUE NOT NULL
                )
            """)
            cur.execute("""
                INSERT INTO fournisseurs (nom)
                SELECT DISTINCT BTRIM(fournisseur)
                FROM pieces_rechange
                WHERE fournisseur IS NOT NULL AND BTRIM(fournisseur) <> ''
                ON CONFLICT DO NOTHING
            """)
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
        # Custom equipment types table (per domain)
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS types_equipement_custom (
                    id SERIAL PRIMARY KEY,
                    nom TEXT NOT NULL,
                    domaine TEXT NOT NULL DEFAULT '',
                    UNIQUE(nom, domaine)
                )
            """)
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
        # Custom intervention types table
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS types_intervention_custom (
                    id SERIAL PRIMARY KEY,
                    nom TEXT UNIQUE NOT NULL
                )
            """)
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
        # Table Domaines Personnalisés (Médical)
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS domaines_custom (
                    id SERIAL PRIMARY KEY,
                    nom TEXT UNIQUE NOT NULL,
                    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        # Table Documents Techniques (séparée pour éviter les timeouts sur gros fichiers)
        try:
            cur = conn.cursor()
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
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        # Table Contrats / SLA
        conn.execute("""
        CREATE TABLE IF NOT EXISTS contrats (
            id SERIAL PRIMARY KEY,
            client TEXT NOT NULL,
            equipement TEXT,
            type_contrat TEXT DEFAULT 'Maintenance Préventive',
            date_debut DATE NOT NULL,
            date_fin DATE NOT NULL,
            sla_temps_reponse_h INTEGER DEFAULT 0,
            interventions_incluses INTEGER DEFAULT -1,
            montant REAL DEFAULT 0.0,
            conditions TEXT DEFAULT '',
            statut TEXT DEFAULT 'Actif',
            notes TEXT DEFAULT '',
            pieces_incluses TEXT DEFAULT '',
            avec_pieces INTEGER DEFAULT 0,
            rappel_avant_jours INTEGER DEFAULT 14,
            date_derniere_maintenance DATE,
            date_signature DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Junction Table: Contrats ↔ Equipements (multi-equipment support)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS contrats_equipements (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            equipement TEXT NOT NULL,
            client TEXT DEFAULT '',
            type_controle TEXT NOT NULL,
            description TEXT DEFAULT '',
            date_controle DATE NOT NULL,
            date_expiration DATE NOT NULL,
            fichier_nom TEXT DEFAULT '',
            fichier_data BYTEA,
            statut TEXT DEFAULT 'Conforme',
            notes TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Table Demandes d'intervention
        conn.execute("""
        CREATE TABLE IF NOT EXISTS demandes_intervention (
            id SERIAL PRIMARY KEY,
            date_demande TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            demandeur TEXT DEFAULT '',
            client TEXT DEFAULT '',
            equipement TEXT DEFAULT '',
            equipement_id INTEGER,
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
            intervention_id INTEGER,
            type_intervention TEXT DEFAULT 'Corrective'
        )
        """)
        conn.execute("ALTER TABLE demandes_intervention ADD COLUMN IF NOT EXISTS type_intervention TEXT DEFAULT 'Corrective'")

        # Table Notifications pièces (cross-app SIC Terrain ↔ SIC Radiologie)
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
            technicien_id INTEGER,
            message TEXT,
            source TEXT NOT NULL DEFAULT '',
            destination TEXT NOT NULL,
            statut TEXT DEFAULT 'non_lu',
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_lecture TIMESTAMP,
            date_traitement TIMESTAMP
        )
        """)
        conn.execute("ALTER TABLE notifications_pieces ADD COLUMN IF NOT EXISTS technicien_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_pieces_technicien_id ON notifications_pieces(technicien_id)")
        # Table Pièces demandées (non référencées) par les techniciens
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pieces_demandees (
            id SERIAL PRIMARY KEY,
            reference TEXT NOT NULL,
            designation TEXT NOT NULL DEFAULT '',
            intervention_id INTEGER,
            equipement TEXT DEFAULT '',
            client TEXT DEFAULT '',
            technicien TEXT DEFAULT '',
            technicien_id INTEGER,
            probleme TEXT DEFAULT '',
            statut TEXT DEFAULT 'en_attente',
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_resolution TIMESTAMP
        )
        """)
        # Migration: ajouter colonne probleme si elle n'existe pas
        try:
            conn.execute("ALTER TABLE pieces_demandees ADD COLUMN IF NOT EXISTS probleme TEXT DEFAULT ''")
            conn.execute("ALTER TABLE pieces_demandees ADD COLUMN IF NOT EXISTS technicien_id INTEGER")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pieces_demandees_technicien_id ON pieces_demandees(technicien_id)")
        except Exception:
            pass

        # --- Migration PII (Pillier 2: Privacy by Design) ---
        try:
            # Transférer nom_complet et email de utilisateurs vers user_pii
            conn.execute("""
                INSERT INTO user_pii (user_id, nom_complet, email)
                SELECT id, nom_complet, email FROM utilisateurs
                WHERE nom_complet != '' OR email != ''
                ON CONFLICT (user_id) DO NOTHING
            """)
            # Transférer nom, prenom, email de techniciens vers technicien_pii
            # Note: on concatène nom et prenom pour nom_complet si besoin
            # COALESCE est la fonction PostgreSQL standard pour les valeurs NULL.
            conn.execute("""
                INSERT INTO technicien_pii (tech_id, nom_complet, email, telegram_id)
                SELECT id, (COALESCE(nom, '') || ' ' || COALESCE(prenom, '')), email, telegram_id FROM techniciens
                WHERE nom != '' OR email != ''
                ON CONFLICT DO NOTHING
            """)
            logger.info("Audit Trail: Migration PII effectuée avec succès.")
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.debug(f"Migration PII ignorée (Pillar 2): {e}")

        # --- Migration: Update CHECK constraint for utilisateurs.role ---
        # Keep the database constraint aligned with all application roles.
        try:
            # Drop old constraint if exists
            conn.execute("ALTER TABLE utilisateurs DROP CONSTRAINT IF EXISTS utilisateurs_role_check")
            # Add new constraint with all roles
            conn.execute("""
                ALTER TABLE utilisateurs ADD CONSTRAINT utilisateurs_role_check 
                CHECK(role IN ('Admin', 'Technicien', 'Lecteur', 'Manager', 'Responsable Technique', 'Gestionnaire', 'Gestionnaire de stock'))
            """)
            conn.commit()
            logger.info("✅ Migration réussie: utilisateurs role constraint updated with all application roles")
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.info(f"Migration ignorée (utilisateurs role check): {e}")

        # --- Migration: Update CHECK constraint for planning_maintenance.statut to include "Décalé" ---
        # This allows reschedule feature to mark original date entries as "Décalé" (ghosted)
        try:
            # Check if "Décalé" is already in the constraint
            cur = conn.cursor()
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
                        CHECK (statut IN ('Planifiée', 'En cours', 'Cloturee', 'En retard', 'Décalé'))
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
                    CHECK (statut IN ('Planifiée', 'En cours', 'Cloturee', 'En retard', 'Décalé'))
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
            # PostgreSQL version - join with equipements table to get the ID
            conn.execute("""
                INSERT INTO contrats_equipements (contrat_id, equipement_id, created_at)
                SELECT c.id, e.id, c.created_at FROM contrats c
                LEFT JOIN equipements e ON e.nom = c.equipement
                WHERE c.equipement IS NOT NULL AND c.equipement != ''
                ON CONFLICT (contrat_id, equipement_id) DO NOTHING
            """)
            logger.info("✅ Migration réussie: contrats_equipements peuplée depuis contrats.equipement")
        except Exception as e:
            logger.debug(f"Migration contrats_equipements ignorée: {e}")

        # --- Migration: Fix CHECK constraint and link closed interventions to planning ---
        # The constraint in the database may still have old values (Terminée instead of Cloturee)
        # This migration fixes the constraint and updates related planning entries
        try:
            from datetime import datetime
            cur = conn.cursor()
            
            logger.info("🔧 Starting planning_maintenance constraint and data migration...")
            
            # Step 0: FIRST - Convert any existing 'Réalisée' or 'Terminée' to 'Cloturee' BEFORE touching the constraint
            try:
                cur.execute("""
                    UPDATE planning_maintenance 
                    SET statut = 'Cloturee'
                    WHERE statut IN ('Réalisée', 'Terminée')
                """)
                rows_changed = cur.rowcount
                if rows_changed > 0:
                    conn.commit()
                    logger.info(f"✅ Converted {rows_changed} old planning entries from 'Réalisée'/'Terminée' to 'Cloturee'")
            except Exception as e:
                logger.debug(f"Could not convert old statuses: {e}")
                try:
                    conn.rollback()
                except:
                    pass
            
            # Step 1: Drop the old CHECK constraint if it exists
            try:
                cur.execute("""
                    ALTER TABLE planning_maintenance DROP CONSTRAINT IF EXISTS planning_maintenance_statut_check
                """)
                conn.commit()
                logger.info("✅ Dropped old planning_maintenance_statut_check constraint")
            except Exception as e:
                logger.debug(f"Could not drop constraint: {e}")
                try:
                    conn.rollback()
                except:
                    pass
            
            # Step 2: Add the new CHECK constraint with correct values
            try:
                cur.execute("""
                    ALTER TABLE planning_maintenance 
                    ADD CONSTRAINT planning_maintenance_statut_check 
                    CHECK (statut IN ('Planifiée', 'En cours', 'Cloturee', 'En retard', 'Décalé'))
                """)
                conn.commit()
                logger.info("✅ Added new planning_maintenance_statut_check constraint with 'Cloturee'")
            except Exception as e:
                logger.debug(f"Could not add constraint: {e}")
                try:
                    conn.rollback()
                except:
                    pass
            
            # Step 3: Update plannings that have closed interventions
            cur.execute("""
                UPDATE planning_maintenance 
                SET statut = 'Cloturee', date_realisee = CURRENT_DATE
                WHERE id IN (
                    SELECT DISTINCT planning_id FROM interventions 
                    WHERE planning_id IS NOT NULL AND statut = 'Cloturee'
                )
                AND statut != 'Cloturee'
            """)
            rows_updated = cur.rowcount
            if rows_updated > 0:
                conn.commit()
                logger.info(f"✅ Migration réussie: {rows_updated} planning_maintenance entries linked to closed interventions and marked as 'Cloturee'")
                
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.debug(f"Migration planning_maintenance constraint/data ignorée: {e}")

        # --- Migration: Add pieces_incluses and avec_pieces columns to contrats if not exist ---
        try:
            # PostgreSQL: Try to add columns if they don't exist
            conn.execute("ALTER TABLE contrats ADD COLUMN IF NOT EXISTS pieces_incluses TEXT DEFAULT ''")
            conn.execute("ALTER TABLE contrats ADD COLUMN IF NOT EXISTS avec_pieces INTEGER DEFAULT 0")
            logger.info("✅ Migration réussie: colonnes pieces_incluses et avec_pieces ajoutées à contrats")
        except Exception as e:
            logger.debug(f"Migration colonnes pièces ignorée: {e}")

        # Align the database default with the contract models available in the UI.
        # Existing Standard/Premium contracts are intentionally preserved.
        try:
            conn.execute("ALTER TABLE contrats ALTER COLUMN type_contrat SET DEFAULT 'Maintenance Préventive'")
        except Exception as e:
            logger.debug(f"Migration défaut type de contrat ignorée: {e}")
        
        # --- Auto-Migration: VPS Schema (equipement_nom → equipement_id) ---
        # This migration runs automatically on every startup
        # It safely converts legacy VPS schema to standard schema if needed
        try:
            _auto_migrate_vps_schema(conn)
        except Exception as e:
            logger.warning(f"Auto-migration VPS schema failed: {e}")
