import sqlite3, bcrypt
conn = sqlite3.connect("sic_radiologie.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, username, role, actif FROM utilisateurs").fetchall()
for r in rows:
    print(dict(r))

# Create/reset admin user with known password
hashed = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode("utf-8")
existing = conn.execute("SELECT id FROM utilisateurs WHERE username='admin'").fetchone()
if existing:
    conn.execute("UPDATE utilisateurs SET password_hash=?, actif=1 WHERE username='admin'", (hashed,))
    print("Updated admin password to admin123")
else:
    conn.execute("INSERT INTO utilisateurs (username, password_hash, nom_complet, role, actif) VALUES (?,?,?,?,1)",
                 ("admin", hashed, "Administrateur", "Admin"))
    print("Created admin user with password admin123")
conn.commit()
conn.close()
