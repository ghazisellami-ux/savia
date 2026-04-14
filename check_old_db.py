import sqlite3

# Check the root-level old DB
conn = sqlite3.connect(r'c:\Users\ACER\.gemini\antigravity\scratch\sic_radiology\sic_radiologie.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== OLD ROOT SQLite (sic_radiology/sic_radiologie.db) ===")
for t in tables:
    name = t[0]
    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
    print(f"  {name}: {count} lignes")
    if 'intervention' in name.lower():
        rows = conn.execute(f"SELECT * FROM [{name}] LIMIT 2").fetchall()
        for r in rows:
            print(f"    -> {r}")
conn.close()
