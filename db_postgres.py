# ==========================================
# 🐘 CONNECTEUR POSTGRESQL (Production Ready)
# ==========================================
"""
Module exclusif pour la gestion de la base de données PostgreSQL.
Utilise psycopg2 avec un Pool de connexions pour les performances en production.

Piliers respectés :
- Architecture (Pilier 1) : Fichier dédié, séparation des socles DB.
- Robustesse (Pilier 6) : Connection Pooling et gestion propre des transactions.
"""

import os
import logging
from contextlib import contextmanager
import pandas as pd
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

# Configuration Logger
logger = logging.getLogger("SIC_Postgres")
logger.setLevel(logging.INFO)

# --- CONFIGURATION POSTGRESQL ---
# À configurer dans le fichier .env de production (VPS OVH)
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgres://user:password@localhost:5432/sic_radiologie"
)

# === CONNECTION POOLING ===
# Indispensable pour éviter la saturation des connexions sur PostgreSQL
pg_pool = None

def init_pool():
    """Initialise le pool de connexions (appelé au démarrage du serveur)."""
    global pg_pool
    if pg_pool is None:
        try:
            pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=DATABASE_URL
            )
            logger.info("🟢 PostgreSQL Connection Pool initialisé.")
        except Exception as e:
            logger.error(f"🔴 ERREUR CRITIQUE PostgreSQL: Impossible d'initialiser le Pool - {e}")


@contextmanager
def get_db():
    """
    Context manager pour obtenir une connexion sécurisée depuis le pool.
    Gère automatiquement les commit(), rollback() en cas d'erreur, et le retour au pool.
    
    Yields:
        psycopg2.extensions.connection: Connexion active.
    """
    if pg_pool is None:
        init_pool()
        
    conn = None
    try:
        # Récupère une connexion du pool
        conn = pg_pool.getconn()
        conn.autocommit = False # Gestion transactionnelle stricte
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"⚠️ Erreur de transaction PostgreSQL: {e}")
        raise e
    finally:
        if conn:
            # Remet la connexion dans le pool
            pg_pool.putconn(conn)


def read_sql(query: str, conn, params=None) -> pd.DataFrame:
    """
    Wrapper pour l'exécution de requêtes SELECT via Pandas.
    Pandas supporte nativement PostgreSQL.
    """
    try:
        # Pandas préfère les tuples pour le passage d'arguments psycopg2
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        logger.error(f"Erreur d'exécution read_sql: {e}")
        return pd.DataFrame()


def execute_write(query: str, params=None):
    """
    Wrapper utilitaire pour exécuter un simple INSERT/UPDATE/DELETE.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)


def init_db():
    """
    Initialise le schéma PostgreSQL avec les types propres (SERIAL, TIMESTAMP).
    Inclut l'isolation PII (Pilier 2).
    """
    init_pool()
    with get_db() as conn:
        with conn.cursor() as cur:
            logger.info("Démarrage de l'initialisation du schéma PostgreSQL...")

            # === TABLES FONCTIONNELLES ===
            cur.execute("""
                CREATE TABLE IF NOT EXISTS utilisateurs (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) DEFAULT 'Lecteur' CHECK(role IN ('Admin', 'Technicien', 'Lecteur')),
                    client VARCHAR(255) DEFAULT '',
                    actif INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS techniciens (
                    id SERIAL PRIMARY KEY,
                    nom VARCHAR(255) NOT NULL,
                    prenom VARCHAR(255) NOT NULL,
                    specialite VARCHAR(255) DEFAULT 'Généraliste',
                    qualification VARCHAR(255) DEFAULT '',
                    dispo INTEGER DEFAULT 1,
                    notes TEXT DEFAULT ''
                );
                
                CREATE TABLE IF NOT EXISTS equipements (
                    id SERIAL PRIMARY KEY,
                    nom VARCHAR(255) NOT NULL,
                    type VARCHAR(100) DEFAULT '',
                    fabricant VARCHAR(100) DEFAULT '',
                    modele VARCHAR(100) DEFAULT '',
                    num_serie VARCHAR(100) DEFAULT '',
                    date_installation DATE,
                    derniere_maintenance DATE,
                    statut VARCHAR(50) DEFAULT 'Actif',
                    notes TEXT DEFAULT '',
                    client VARCHAR(255) DEFAULT 'Centre Principal',
                    UNIQUE(nom, client)
                );
            """)

            # === PI ISOLATION (Pilier 2) ===
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_pii (
                    user_id INTEGER PRIMARY KEY REFERENCES utilisateurs(id) ON DELETE CASCADE,
                    nom_complet VARCHAR(255) DEFAULT '',
                    email VARCHAR(255) DEFAULT '',
                    telephone VARCHAR(50) DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS technicien_pii (
                    tech_id INTEGER PRIMARY KEY REFERENCES techniciens(id) ON DELETE CASCADE,
                    nom_complet VARCHAR(255) DEFAULT '',
                    email VARCHAR(255) DEFAULT '',
                    telephone VARCHAR(50) DEFAULT '',
                    telegram_id VARCHAR(100) DEFAULT ''
                );
            """)

            # === AUDIT LOG (Pilier 3) ===
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    username VARCHAR(255) DEFAULT 'system',
                    action VARCHAR(100) NOT NULL,
                    details TEXT DEFAULT '',
                    page VARCHAR(100) DEFAULT '',
                    ip_address VARCHAR(45) DEFAULT ''
                );
            """)

            logger.info("✅ Schéma PostgreSQL initialisé avec succès.")

# Note: Pour utiliser ce module, il suffira de remplacer les imports `get_db`, `read_sql`
# des autres fichiers (auth.py, views/...) pour pointer vers `db_postgres` au lieu de `db_sqlite`.
