import sys; sys.path.insert(0,'/app')
from db_engine import get_db
with get_db() as conn:
    row = conn.execute('SELECT * FROM equipements LIMIT 1').fetchone()
    if row:
        print('COLUMNS:', list(dict(row).keys()))
    rows = conn.execute('SELECT statut, COUNT(*) as cnt FROM equipements GROUP BY statut').fetchall()
    print('STATUTS:')
    for r in rows:
        print(f'  [{dict(r).get("statut")}] = {dict(r)["cnt"]}')
