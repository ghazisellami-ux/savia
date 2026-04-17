import psycopg2
import psycopg2.extras
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Simuler exactement ce que fait le filtre backend pour Ali Dridi
nom_complet = "Dridi Ali"  # c'est ce que contient le JWT
name_words = [w.lower() for w in nom_complet.split() if len(w) > 1]
print("Mots recherches:", name_words)  # ['dridi', 'ali']

cur.execute("SELECT id, statut, machine, technicien FROM interventions WHERE statut = 'En cours'")
rows = cur.fetchall()
print(f"\nInterventions 'En cours' ({len(rows)}):")
for r in rows:
    tech = (r['technicien'] or "").lower()
    matches = all(word in tech for word in name_words)
    print(f"  #{r['id']} technicien='{r['technicien']}' → match={matches}")

print("\nResultat attendu pour Ali Dridi: verra intervention(s) avec match=True")

cur.close()
conn.close()
