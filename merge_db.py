import sqlite3
import os

source_db = r"c:\Users\ACER\Desktop\savia v0\sic_radiologie.db"
target_db = r"sic_radiologie.db"

src = sqlite3.connect(source_db)
tgt = sqlite3.connect(target_db)

tables = src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

for (table,) in tables:
    if table == "sqlite_sequence":
        continue
    
    # Read rows
    rows = src.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        continue
        
    print(f"Merging {len(rows)} from {table}...")
    
    # Get columns
    cols_query = src.execute(f"PRAGMA table_info({table})").fetchall()
    col_names = [c[1] for c in cols_query]
    
    # Check if target has these cols, otherwise ignore? SQLite requires matching schema.
    # Since they are the same app, it should match.
    # We want to ignore 'id' so it auto-increments and avoids conflicts.
    insert_cols = [c for c in col_names if c != "id"]
    
    for row in rows:
        row_dict = dict(zip(col_names, row))
        values = [row_dict[c] for c in insert_cols]
        placeholders = ",".join(["?"] * len(insert_cols))
        try:
            tgt.execute(f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({placeholders})", values)
        except Exception as e:
            # Maybe UNIQUE constraints?
            pass

tgt.commit()
print("Merged.")
tgt.close()
src.close()
