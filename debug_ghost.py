from db_engine import get_db

db = get_db()
conn = db.__enter__()

# Check for entries on 2026-10-08
print("=== Entries on 2026-10-08 ===")
rows = conn.execute("SELECT id, machine, date_prevue, statut, is_ghost FROM planning_maintenance WHERE date_prevue='2026-10-08' ORDER BY id").fetchall()
for r in rows:
    print(dict(r))

# Check for ghosts
print("\n=== All ghosts ===")
rows = conn.execute("SELECT id, machine, date_prevue, statut, is_ghost FROM planning_maintenance WHERE is_ghost=true ORDER BY date_prevue").fetchall()
for r in rows:
    print(dict(r))
