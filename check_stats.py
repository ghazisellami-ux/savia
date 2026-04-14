from db_engine import get_db

with get_db() as conn:
    total = conn.execute("SELECT COUNT(*) as c FROM interventions").fetchone()['c']
    correctives = conn.execute("SELECT COUNT(*) as c FROM interventions WHERE type_intervention='Corrective'").fetchone()['c']
    preventives = conn.execute("SELECT COUNT(*) as c FROM interventions WHERE type_intervention ILIKE '%réventive%'").fetchone()['c']
    calibration = conn.execute("SELECT COUNT(*) as c FROM interventions WHERE type_intervention='Calibration'").fetchone()['c']
    formation = conn.execute("SELECT COUNT(*) as c FROM interventions WHERE type_intervention='Formation'").fetchone()['c']
    print(f"Total interventions: {total}")
    print(f"Correctives: {correctives}")
    print(f"Préventives: {preventives}")
    print(f"Calibration: {calibration}")
    print(f"Formation: {formation}")

    # Check what dashboard/kpis actually returns
    types = conn.execute("SELECT DISTINCT type_intervention, COUNT(*) as c FROM interventions GROUP BY type_intervention ORDER BY c DESC").fetchall()
    print("\n=== Répartition par type ===")
    for t in types:
        print(f"  {t['type_intervention']}: {t['c']}")

    # Also check what the KPI endpoint computes
    equip = conn.execute("SELECT COUNT(*) as c FROM equipements").fetchone()['c']
    print(f"\nTotal équipements: {equip}")
