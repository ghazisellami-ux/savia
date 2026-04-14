import json
import sqlite3
import os

DB_PATH = "sic_radiologie.db"
BACKUP_PATH = r"..\sic_radiology_data\data\backup_complet.json"

def main():
    if not os.path.exists(BACKUP_PATH):
        print(f"Error: {BACKUP_PATH} not found.")
        return

    print("Loading backup file...")
    with open(BACKUP_PATH, 'r', encoding='utf-8') as f:
        backup = json.load(f)

    tables = backup.get("tables", {})
    if not tables:
        print("No tables found in backup.")
        return

    print(f"Backup timestamp: {backup.get('timestamp')}")
    print(f"Found tables: {', '.join(tables.keys())}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for table_name, rows in tables.items():
        if not rows:
            print(f"[{table_name}] 0 rows, skipping.")
            continue
            
        print(f"[{table_name}] Restoring {len(rows)} rows...")
        
        try:
            # Delete existing data in this table to prevent duplicates during import
            # If you want to merge, comment this out and use INSERT OR IGNORE
            cursor.execute(f"DELETE FROM {table_name}")
            
            # The columns in the JSON might not match 100% if the schema changed
            # but since we're using the same SQLite schema they should match.
            cols = list(rows[0].keys())
            placeholders = ", ".join(["?" for _ in cols])
            cols_str = ", ".join(cols)

            for row in rows:
                values = [row.get(c) for c in cols]
                cursor.execute(
                    f"INSERT OR REPLACE INTO {table_name} ({cols_str}) VALUES ({placeholders})",
                    values
                )
            
            conn.commit()
            print(f"[{table_name}] OK")
        except Exception as e:
            print(f"[{table_name}] ERROR: {str(e)}")

    print("\nRestore complete! Re-creating default admin just in case...")
    try:
        from auth import creer_admin_defaut
        creer_admin_defaut(conn)
        conn.commit()
        print("Admin user verified.")
    except Exception as e:
        print("Could not run admin defaults:", e)

    conn.close()

if __name__ == "__main__":
    main()
