import psycopg2
import psycopg2.extras
import os
import requests

DATABASE_URL = os.environ.get("DATABASE_URL", "")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Derniere intervention cloturee d'Ali Dridi
cur.execute("""
    SELECT id, statut, machine, technicien, fiche_photo_nom,
           CASE WHEN fiche_photo_data IS NOT NULL THEN length(fiche_photo_data) ELSE 0 END as photo_bytes
    FROM interventions
    WHERE (statut ILIKE '%clotur%' OR statut ILIKE '%termin%')
      AND technicien ILIKE '%ali%dridi%'
    ORDER BY id DESC LIMIT 5
""")
rows = cur.fetchall()
print("=== Interventions cloturees Ali Dridi ===")
for r in rows:
    print(dict(r))

# Tester l'api GET /api/interventions/fiches
print("\n=== Test GET /api/interventions/fiches via HTTP ===")
try:
    r = requests.get("http://localhost:8000/api/interventions/fiches", 
                     headers={"Authorization": "Bearer test"}, timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Erreur: {e}")

cur.close()
conn.close()
