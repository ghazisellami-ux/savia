from db_engine import get_db
with get_db() as conn:
    try:
        conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_photo_nom TEXT DEFAULT ''")
        print('fiche_photo_nom: OK')
    except Exception as e:
        print(f'fiche_photo_nom: {e}')
    try:
        conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_photo_data BYTEA")
        print('fiche_photo_data: OK')
    except Exception as e:
        print(f'fiche_photo_data: {e}')
print('Done')
