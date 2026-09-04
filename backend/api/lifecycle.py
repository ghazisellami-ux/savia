"""FastAPI startup lifecycle wiring."""

from api.runtime import (
    _ensure_dejavu_font,
    _ensure_fa_font,
    app,
    auth,
    get_db,
    init_db,
    logger,
    migrer_clients_depuis_equipements,
)
from database.migrations import run_migrations
from services.timezone import configure_process_timezone

@app.on_event("startup")
def startup():
    init_db()
    configure_process_timezone()
    with get_db() as conn:
        applied = run_migrations(conn)
    if applied:
        logger.info("Migrations PostgreSQL appliquées : %s", ", ".join(applied))
    auth.creer_admin_defaut()
    _ensure_dejavu_font()
    _ensure_fa_font()
    # Migration: colonnes fiche signée
    try:
        with get_db() as conn:
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_photo_nom TEXT DEFAULT ''")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_photo_data BYTEA")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_validation TEXT DEFAULT 'En attente'")
        logger.info("✅ Migration fiche_photo: colonnes OK")
    except Exception as e:
        logger.error(f"❌ Migration fiche_photo échouée: {e}")
    
    # Vérifier et ajouter colonnes time persistence
    try:
        from db_engine import verifier_et_migrer_schema
        verifier_et_migrer_schema()
        logger.info("✅ Migration schema (time persistence): OK")
    except Exception as e:
        logger.error(f"❌ Migration schema échouée: {e}")
    except Exception as e:
        logger.info(f"Migration fiche_photo (déjà faite ou erreur): {e}")
    # Migration: planning_id + facture_envoyee on interventions
    try:
        with get_db() as conn:
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS planning_id INTEGER")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS facture_envoyee BOOLEAN DEFAULT FALSE")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS rappel_facture_envoye INTEGER DEFAULT 0")
        logger.info("✅ Migration planning_id + facture: colonnes OK")
    except Exception as e:
        logger.info(f"Migration planning_id/facture (déjà faite ou erreur): {e}")
    # Auto-migrate existing clients from equipements table
    try:
        migrer_clients_depuis_equipements()
    except Exception as e:
        logger.warning(f"Client migration skipped: {e}")
    logger.info("✅ SAVIA FastAPI started — DB initialized")


# ==========================================
# HELPERS
# ==========================================

__all__ = [
    "startup",
]
