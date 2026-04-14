import sqlite3

conn = sqlite3.connect(r'c:\Users\ACER\.gemini\antigravity\scratch\sic_radiology\sic_radiology\sic_radiologie.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== TABLES IN SQLite ===")
for t in tables:
    name = t[0]
    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
    print(f"  {name}: {count} lignes")

# Check for interventions
for t in tables:
    name = t[0]
    if 'intervention' in name.lower() or 'sav' in name.lower():
        print(f"\n=== SAMPLE FROM {name} ===")
        cols = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
        print("  Colonnes:", [c[1] for c in cols])
        rows = conn.execute(f"SELECT * FROM [{name}] LIMIT 3").fetchall()
        for r in rows:
            print(f"  -> {r}")

conn.close()
