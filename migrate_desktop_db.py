"""
Migration script: Import data from Desktop sic_radiologie.db (SQLite) into PostgreSQL.
Handles: interventions, equipements, techniciens, planning_maintenance, pieces_rechange
"""
import sqlite3
import os
import sys

# Add project to path for db_engine import
sys.path.insert(0, os.path.dirname(__file__))

DESKTOP_DB = r'C:\Users\ACER\Desktop\sic_radiologie.db'

def get_sqlite_data(table):
    conn = sqlite3.connect(DESKTOP_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM [{table}]").fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result

def migrate():
    from db_engine import get_db

    print("=" * 60)
    print("MIGRATION: Desktop sic_radiologie.db -> PostgreSQL")
    print("=" * 60)

    with get_db() as conn:
        # 1. Interventions
        existing = conn.execute("SELECT COUNT(*) as c FROM interventions").fetchone()['c']
        desktop_interventions = get_sqlite_data("interventions")
        print(f"\n[interventions] Desktop: {len(desktop_interventions)} | PostgreSQL: {existing}")

        if len(desktop_interventions) > existing:
            # Clear and re-import
            conn.execute("DELETE FROM interventions")
            inserted = 0
            for row in desktop_interventions:
                try:
                    conn.execute("""
                        INSERT INTO interventions (date, machine, technicien, type_intervention, description,
                            probleme, cause, solution, pieces_utilisees, cout, duree_minutes,
                            code_erreur, statut, notes, date_debut_intervention, date_cloture,
                            type_erreur, priorite)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        row.get('date', ''), row.get('machine', ''), row.get('technicien', ''),
                        row.get('type_intervention', ''), row.get('description', ''),
                        row.get('probleme', ''), row.get('cause', ''), row.get('solution', ''),
                        row.get('pieces_utilisees', ''), row.get('cout', 0), row.get('duree_minutes', 0),
                        row.get('code_erreur', ''), row.get('statut', ''), row.get('notes', ''),
                        row.get('date_debut_intervention'), row.get('date_cloture'),
                        row.get('type_erreur', ''), row.get('priorite', '')
                    ))
                    inserted += 1
                except Exception as e:
                    print(f"  SKIP intervention #{row.get('id')}: {e}")
            print(f"  -> {inserted} interventions importées ✓")
        else:
            print("  -> Déjà à jour, skip")

        # 2. Techniciens
        existing_tech = conn.execute("SELECT COUNT(*) as c FROM techniciens").fetchone()['c']
        desktop_tech = get_sqlite_data("techniciens")
        print(f"\n[techniciens] Desktop: {len(desktop_tech)} | PostgreSQL: {existing_tech}")

        if len(desktop_tech) > 0:
            for row in desktop_tech:
                try:
                    conn.execute("""
                        INSERT INTO techniciens (nom, specialite, telephone, email, statut_disponibilite)
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT (nom) DO UPDATE SET
                            specialite=EXCLUDED.specialite, telephone=EXCLUDED.telephone,
                            email=EXCLUDED.email, statut_disponibilite=EXCLUDED.statut_disponibilite
                    """, (
                        row.get('nom', ''), row.get('specialite', ''),
                        row.get('telephone', ''), row.get('email', ''),
                        row.get('statut_disponibilite', 'Disponible')
                    ))
                except Exception as e:
                    print(f"  SKIP technicien {row.get('nom')}: {e}")
            print(f"  -> {len(desktop_tech)} techniciens synchronisés ✓")

        # 3. Planning maintenance
        existing_plan = conn.execute("SELECT COUNT(*) as c FROM planning_maintenance").fetchone()['c']
        desktop_plan = get_sqlite_data("planning_maintenance")
        print(f"\n[planning] Desktop: {len(desktop_plan)} | PostgreSQL: {existing_plan}")

        if len(desktop_plan) > existing_plan:
            conn.execute("DELETE FROM planning_maintenance")
            inserted = 0
            for row in desktop_plan:
                try:
                    conn.execute("""
                        INSERT INTO planning_maintenance (machine, type_maintenance, date_prevue,
                            technicien, statut, notes, recurrence, client)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        row.get('machine', ''), row.get('type_maintenance', ''),
                        row.get('date_prevue', ''), row.get('technicien', ''),
                        row.get('statut', 'Planifiée'), row.get('notes', ''),
                        row.get('recurrence', ''), row.get('client', '')
                    ))
                    inserted += 1
                except Exception as e:
                    print(f"  SKIP planning: {e}")
            print(f"  -> {inserted} plannings importés ✓")

        # 4. Pieces rechange
        existing_pieces = conn.execute("SELECT COUNT(*) as c FROM pieces_rechange").fetchone()['c']
        desktop_pieces = get_sqlite_data("pieces_rechange")
        print(f"\n[pieces_rechange] Desktop: {len(desktop_pieces)} | PostgreSQL: {existing_pieces}")

        if len(desktop_pieces) > 0:
            for row in desktop_pieces:
                try:
                    conn.execute("""
                        INSERT INTO pieces_rechange (reference, nom, equipement_compatible,
                            quantite_stock, seuil_alerte, prix_unitaire, fournisseur)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (reference) DO UPDATE SET
                            nom=EXCLUDED.nom, quantite_stock=EXCLUDED.quantite_stock,
                            prix_unitaire=EXCLUDED.prix_unitaire
                    """, (
                        row.get('reference', ''), row.get('nom', ''),
                        row.get('equipement_compatible', ''),
                        row.get('quantite_stock', 0), row.get('seuil_alerte', 5),
                        row.get('prix_unitaire', 0), row.get('fournisseur', '')
                    ))
                except Exception as e:
                    print(f"  SKIP piece {row.get('reference')}: {e}")
            print(f"  -> {len(desktop_pieces)} pièces synchronisées ✓")

    # Verify
    print("\n" + "=" * 60)
    print("VÉRIFICATION FINALE")
    print("=" * 60)
    with get_db() as conn:
        for table in ['interventions', 'techniciens', 'equipements', 'planning_maintenance', 'pieces_rechange']:
            cnt = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()['c']
            print(f"  {table}: {cnt} lignes")

if __name__ == "__main__":
    migrate()
