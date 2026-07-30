"""Small, dependency-free migration runner.

The existing application creates its baseline schema for backwards
compatibility.  Every schema change from this point on is recorded here and is
applied exactly once to each PostgreSQL database.
"""

from datetime import datetime, timezone
from typing import Callable


Migration = tuple[str, str, Callable]


def _constraint_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = %s",
            (name,),
        ).fetchone()
    )


def _add_check_constraint(conn, name: str, sql: str) -> None:
    if not _constraint_exists(conn, name):
        conn.execute(sql)


def _migration_001_integrity_and_indexes(conn) -> None:
    """Add query indexes and enforce safe values for new/updated rows."""
    # Interventions historically derived their client from the equipment name.
    # Persist it now so a duplicate equipment name can never weaken tenant
    # isolation. Existing rows are backfilled only when the match is unique.
    conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS client TEXT DEFAULT ''")
    conn.execute(
        """UPDATE interventions
           SET client = substring(notes FROM '^\\[([^]]+)\\]')
           WHERE NULLIF(BTRIM(client), '') IS NULL
             AND notes ~ '^\\[[^]]+\\]'"""
    )
    conn.execute(
        """WITH unique_equipment_clients AS (
               SELECT LOWER(nom) AS machine_key, MIN(client) AS client
               FROM equipements
               WHERE NULLIF(BTRIM(client), '') IS NOT NULL
               GROUP BY LOWER(nom)
               HAVING COUNT(DISTINCT LOWER(client)) = 1
           )
           UPDATE interventions i
           SET client = u.client
           FROM unique_equipment_clients u
           WHERE NULLIF(BTRIM(i.client), '') IS NULL
             AND LOWER(i.machine) = u.machine_key"""
    )
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_utilisateurs_client ON utilisateurs(client)",
        "CREATE INDEX IF NOT EXISTS idx_demandes_client_statut ON demandes_intervention(client, statut)",
        "CREATE INDEX IF NOT EXISTS idx_contrats_client ON contrats(client)",
        "CREATE INDEX IF NOT EXISTS idx_conformite_client_expiration ON conformite(client, date_expiration)",
        "CREATE INDEX IF NOT EXISTS idx_planning_client_date ON planning_maintenance(client, date_prevue DESC)",
        "CREATE INDEX IF NOT EXISTS idx_interventions_technicien_date ON interventions(technicien, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_interventions_client_date ON interventions(client, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_interventions_parent ON interventions(parent_intervention_id)",
        "CREATE INDEX IF NOT EXISTS idx_interventions_techniciens_intervention ON interventions_techniciens(intervention_id)",
        "CREATE INDEX IF NOT EXISTS idx_documents_techniques_equipement ON documents_techniques(equipement_id)",
    )
    for statement in indexes:
        conn.execute(statement)

    # NOT VALID keeps deployment safe for legacy data while enforcing the rule
    # for every new or updated row. It can be validated later after data cleanup.
    _add_check_constraint(
        conn,
        "utilisateurs_lecteur_client_check",
        """ALTER TABLE utilisateurs
           ADD CONSTRAINT utilisateurs_lecteur_client_check
           CHECK (role <> 'Lecteur' OR NULLIF(BTRIM(client), '') IS NOT NULL) NOT VALID""",
    )
    _add_check_constraint(
        conn,
        "pieces_rechange_stock_nonnegative_check",
        """ALTER TABLE pieces_rechange
           ADD CONSTRAINT pieces_rechange_stock_nonnegative_check
           CHECK (stock_actuel >= 0 AND stock_minimum >= 0) NOT VALID""",
    )
    _add_check_constraint(
        conn,
        "interventions_values_nonnegative_check",
        """ALTER TABLE interventions
           ADD CONSTRAINT interventions_values_nonnegative_check
           CHECK (duree_minutes >= 0 AND cout >= 0 AND cout_pieces >= 0) NOT VALID""",
    )
    _add_check_constraint(
        conn,
        "contrats_dates_check",
        """ALTER TABLE contrats
           ADD CONSTRAINT contrats_dates_check
           CHECK (date_fin >= date_debut) NOT VALID""",
    )


MIGRATIONS: tuple[Migration, ...] = (
    ("001", "integrity and client-scope indexes", _migration_001_integrity_and_indexes),
)


def run_migrations(conn) -> list[str]:
    """Apply pending migrations and return their versions."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version TEXT PRIMARY KEY,
               description TEXT NOT NULL,
               applied_at TIMESTAMP NOT NULL
           )"""
    )
    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    completed: list[str] = []
    for version, description, migration in MIGRATIONS:
        if version in applied:
            continue
        migration(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, description, applied_at) VALUES (%s, %s, %s)",
            (version, description, datetime.now(timezone.utc)),
        )
        completed.append(version)
    return completed
