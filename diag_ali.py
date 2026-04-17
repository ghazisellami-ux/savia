import psycopg2
import psycopg2.extras
import os
import json

DATABASE_URL = os.environ.get("DATABASE_URL", "")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Tester la sous-requete exacte
cur.execute("""
    SELECT i.*,
           (SELECT e.client FROM equipements e
            WHERE LOWER(e.nom) = LOWER(i.machine)
            LIMIT 1) AS client
    FROM interventions i
    ORDER BY i.date DESC LIMIT 3
""")
rows = cur.fetchall()
print(f"Rows count: {len(rows)}")
if rows:
    r = dict(rows[0])
    print("Colonnes:", list(r.keys()))
    for k, v in r.items():
        t = type(v).__name__
        print(f"  {k}: type={t}, val={repr(v)[:60]}")
        # Test JSON
        try:
            json.dumps(v, default=str)
        except Exception as e:
            print(f"    !! JSON ERROR: {e}")

cur.close()
conn.close()
