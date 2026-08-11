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


def _migration_002_private_file_metadata(conn) -> None:
    """Keep new uploads in object storage while retaining legacy blobs safely."""
    statements = (
        "ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_storage_key TEXT",
        "ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_content_type TEXT",
        "ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_size_bytes BIGINT",
        "ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_sha256 TEXT",
        "ALTER TABLE documents_techniques ADD COLUMN IF NOT EXISTS storage_key TEXT",
        "ALTER TABLE documents_techniques ADD COLUMN IF NOT EXISTS content_type TEXT",
        "ALTER TABLE documents_techniques ADD COLUMN IF NOT EXISTS size_bytes BIGINT",
        "ALTER TABLE documents_techniques ADD COLUMN IF NOT EXISTS sha256 TEXT",
    )
    for statement in statements:
        conn.execute(statement)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_interventions_fiche_storage_key ON interventions(fiche_storage_key) WHERE fiche_storage_key IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_techniques_storage_key ON documents_techniques(storage_key) WHERE storage_key IS NOT NULL")


def _migration_003_ai_governance(conn) -> None:
    """Add consent, per-user plans, monthly limits, and content-free AI audit."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_offers (
               code TEXT PRIMARY KEY,
               label TEXT NOT NULL,
               monthly_quota INTEGER NULL CHECK (monthly_quota IS NULL OR monthly_quota >= 0),
               sort_order INTEGER NOT NULL DEFAULT 0,
               active BOOLEAN NOT NULL DEFAULT TRUE,
               updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    for code, label, quota, sort_order in (
        ("starter", "Starter", 30, 1),
        ("business", "Business", 300, 2),
        ("enterprise", "Entreprise", None, 3),
    ):
        conn.execute(
            """INSERT INTO ai_offers(code, label, monthly_quota, sort_order)
               VALUES (%s, %s, %s, %s) ON CONFLICT (code) DO NOTHING""",
            (code, label, quota, sort_order),
        )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_user_entitlements (
               user_id INTEGER PRIMARY KEY REFERENCES utilisateurs(id) ON DELETE CASCADE,
               offer_code TEXT NOT NULL DEFAULT 'starter' REFERENCES ai_offers(code),
               quota_override INTEGER NULL CHECK (quota_override IS NULL OR quota_override >= 0),
               ai_enabled BOOLEAN NOT NULL DEFAULT TRUE,
               consent_version TEXT NOT NULL DEFAULT '',
               consented_at TIMESTAMP NULL,
               consent_revoked_at TIMESTAMP NULL,
               updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_monthly_usage (
               user_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
               period_start DATE NOT NULL,
               request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
               updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               PRIMARY KEY (user_id, period_start)
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_usage_audit (
               id BIGSERIAL PRIMARY KEY,
               occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               user_id INTEGER NULL REFERENCES utilisateurs(id) ON DELETE SET NULL,
               username TEXT NOT NULL,
               client TEXT DEFAULT '',
               feature TEXT NOT NULL,
               provider TEXT NOT NULL DEFAULT 'Google Gemini',
               model TEXT NOT NULL DEFAULT 'gemini-auto',
               offer_code TEXT DEFAULT '',
               outcome TEXT NOT NULL,
               error_code TEXT DEFAULT ''
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_audit_occurred_at ON ai_usage_audit(occurred_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_audit_user_date ON ai_usage_audit(user_id, occurred_at DESC)")
    conn.execute(
        """INSERT INTO config_client(cle, valeur) VALUES
               ('ai_data_location', 'À confirmer dans le contrat Google applicable'),
               ('ai_active_offer_code', 'starter')
           ON CONFLICT (cle) DO NOTHING"""
    )


def _migration_004_global_ai_offer(conn) -> None:
    """One commercial AI offer applies to the whole customer deployment."""
    conn.execute(
        """INSERT INTO config_client(cle, valeur) VALUES ('ai_active_offer_code', 'starter')
           ON CONFLICT (cle) DO NOTHING"""
    )


def _migration_005_equipment_lifecycle_and_request_priority(conn) -> None:
    """Normalize request priority and keep an auditable equipment lifecycle."""
    conn.execute(
        "ALTER TABLE demandes_intervention ADD COLUMN IF NOT EXISTS priorite TEXT DEFAULT 'Moyenne'"
    )
    conn.execute(
        """UPDATE demandes_intervention
           SET priorite = CASE
               WHEN NULLIF(BTRIM(urgence), '') IS NOT NULL
                    AND (NULLIF(BTRIM(priorite), '') IS NULL OR BTRIM(priorite) = 'Moyenne')
                 THEN BTRIM(urgence)
               ELSE COALESCE(NULLIF(BTRIM(priorite), ''), 'Moyenne')
           END
           WHERE NULLIF(BTRIM(priorite), '') IS NULL
              OR (BTRIM(priorite) = 'Moyenne' AND NULLIF(BTRIM(urgence), '') IS NOT NULL
                  AND BTRIM(urgence) <> 'Moyenne')"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS equipement_statut_historique (
               id BIGSERIAL PRIMARY KEY,
               equipement_id INTEGER NOT NULL REFERENCES equipements(id) ON DELETE CASCADE,
               ancien_statut TEXT NOT NULL DEFAULT '',
               nouveau_statut TEXT NOT NULL,
               source TEXT NOT NULL DEFAULT 'systeme',
               intervention_id INTEGER NULL REFERENCES interventions(id) ON DELETE SET NULL,
               raison TEXT NOT NULL DEFAULT '',
               change_par TEXT NOT NULL DEFAULT '',
               change_le TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_equipement_statut_historique_equipement "
        "ON equipement_statut_historique(equipement_id, change_le DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_demandes_priorite ON demandes_intervention(priorite)"
    )
    # Legacy installations used Actif. Convert only this legacy operational
    # value; manually declared statuses remain untouched.
    conn.execute(
        "UPDATE equipements SET statut = 'Op' || chr(195) || chr(169) || 'rationnel' WHERE statut = 'Actif'"
    )
    conn.execute(
        "UPDATE equipements SET statut = 'OpÃ©rationnel' WHERE statut = 'Actif'"
    )


def _migration_006_offline_idempotency(conn) -> None:
    """Store successful mutation responses so offline retries are harmless."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS api_idempotency_keys (
               operation_id TEXT NOT NULL,
               username TEXT NOT NULL,
               endpoint TEXT NOT NULL,
               response_body JSONB NOT NULL,
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               PRIMARY KEY (operation_id, endpoint)
           )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_api_idempotency_created_at
           ON api_idempotency_keys(created_at)"""
    )


def _migration_007_telegram_outbox(conn) -> None:
    """Retry Telegram notifications without replaying intervention mutations."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS telegram_outbox (
               id BIGSERIAL PRIMARY KEY,
               dedupe_key TEXT NOT NULL,
               bot_key TEXT NOT NULL,
               message TEXT NOT NULL,
               attempts INTEGER NOT NULL DEFAULT 0,
               last_error TEXT NOT NULL DEFAULT '',
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               sent_at TIMESTAMP NULL,
               UNIQUE (dedupe_key, bot_key)
           )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_telegram_outbox_pending
           ON telegram_outbox(sent_at, created_at)"""
    )


def _migration_008_contract_private_file_metadata(conn) -> None:
    """Store contract attachments in private object storage."""
    statements = (
        "ALTER TABLE contrats ADD COLUMN IF NOT EXISTS fichier_storage_key TEXT",
        "ALTER TABLE contrats ADD COLUMN IF NOT EXISTS fichier_content_type TEXT",
        "ALTER TABLE contrats ADD COLUMN IF NOT EXISTS fichier_size_bytes BIGINT",
        "ALTER TABLE contrats ADD COLUMN IF NOT EXISTS fichier_sha256 TEXT",
    )
    for statement in statements:
        conn.execute(statement)
    # The legacy column helper initializes TEXT columns with ''. Normalize
    # empty values so the partial unique index only covers real object keys.
    conn.execute(
        "UPDATE contrats SET fichier_storage_key = NULL "
        "WHERE BTRIM(COALESCE(fichier_storage_key, '')) = ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_contrats_fichier_storage_key "
        "ON contrats(fichier_storage_key) WHERE fichier_storage_key IS NOT NULL"
    )


MIGRATIONS: tuple[Migration, ...] = (
    ("001", "integrity and client-scope indexes", _migration_001_integrity_and_indexes),
    ("002", "private object-storage file metadata", _migration_002_private_file_metadata),
    ("003", "AI consent, quotas, and content-free usage audit", _migration_003_ai_governance),
    ("004", "one active AI offer per deployment", _migration_004_global_ai_offer),
    ("005", "equipment lifecycle and request priority", _migration_005_equipment_lifecycle_and_request_priority),
    ("006", "offline mutation idempotency", _migration_006_offline_idempotency),
    ("007", "reliable Telegram notification outbox", _migration_007_telegram_outbox),
    ("008", "private contract attachment metadata", _migration_008_contract_private_file_metadata),
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
