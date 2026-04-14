import sqlite3

conn = sqlite3.connect(r'C:\Users\ACER\Desktop\sic_radiologie.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== DESKTOP sic_radiologie.db ===")
for t in tables:
    name = t[0]
    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
    marker = " <<<" if count > 10 else ""
    print(f"  {name}: {count} lignes{marker}")

# Interventions details
print("\n=== INTERVENTIONS ===")
cols = conn.execute("PRAGMA table_info(interventions)").fetchall()
print("Colonnes:", [c[1] for c in cols])
cnt = conn.execute("SELECT COUNT(*) FROM interventions").fetchone()[0]
print(f"Total: {cnt}")
if cnt > 0:
    print("\nDernières 5:")
    rows = conn.execute("SELECT id, date, machine, technicien, type_intervention, statut FROM interventions ORDER BY id DESC LIMIT 5").fetchall()
    for r in rows:
        print(f"  #{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]}")

conn.close()
