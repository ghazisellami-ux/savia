import psycopg2
import psycopg2.extras
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# 1. Toutes les interventions Ali Dridi du 17/04/2026
print("=== Interventions Ali Dridi aujourd'hui ===")
cur.execute("""
    SELECT id, statut, machine, technicien, description, notes, date
    FROM interventions
    WHERE technicien ILIKE '%ali%dridi%'
    ORDER BY id DESC
""")
for r in cur.fetchall():
    print(dict(r))

# 2. Compter les doublons "Scanner CT Philips"
print("\n=== Doublons Scanner CT Philips ===")
cur.execute("""
    SELECT id, date, machine, technicien, statut, notes
    FROM interventions
    WHERE machine ILIKE '%scanner ct philips%'
    ORDER BY id DESC
""")
for r in cur.fetchall():
    print(dict(r))

# 3. Etat demandes_intervention et leurs intervention_id
print("\n=== Demandes et leurs intervention_id ===")
cur.execute("""
    SELECT id, client, equipement, technicien_assigne, statut, intervention_id
    FROM demandes_intervention
    WHERE technicien_assigne ILIKE '%ali%dridi%'
    ORDER BY id DESC
""")
for r in cur.fetchall():
    print(dict(r))

cur.close()
conn.close()
