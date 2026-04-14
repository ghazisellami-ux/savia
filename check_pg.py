from db_engine import get_db

with get_db() as conn:
    tables = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
    print("=== PostgreSQL Tables ===")
    for t in tables:
        name = t['tablename']
        cnt = conn.execute(f"SELECT COUNT(*) as c FROM {name}").fetchone()['c']
        print(f"  {name}: {cnt} lignes")
