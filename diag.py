from db_engine import get_db
with get_db() as conn:
    # Interventions de 2026
    rows = conn.execute("""
        SELECT id, statut, machine, technicien, date
        FROM interventions
        WHERE EXTRACT(YEAR FROM date) = 2026
        ORDER BY id DESC
    """).fetchall()
    print(f"=== Interventions 2026 ({len(rows)} total) ===")
    for r in rows:
        print(f"  #{r['id']} | {r['statut']:15} | {r['machine'][:25]:25} | {str(r['technicien'])[:15]:15} | {str(r['date'])[:10]}")

    # Interventions Ali Dridi 2026
    rows2 = conn.execute("""
        SELECT id, statut, machine, date
        FROM interventions
        WHERE technicien ILIKE '%ali%dridi%'
        AND EXTRACT(YEAR FROM date) = 2026
        ORDER BY id DESC
    """).fetchall()
    print(f"\n=== Ali Dridi 2026 ({len(rows2)} interventions) ===")
    for r in rows2:
        print(dict(r))
