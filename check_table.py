from db_engine import get_db
with get_db() as conn:
    r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='logs_uploaded'").fetchone()
    print("Table logs_uploaded exists:", r is not None)
    if r:
        cols = conn.execute("PRAGMA table_info(logs_uploaded)").fetchall()
        for c in cols:
            print(f"  - {c[1]} ({c[2]})")
