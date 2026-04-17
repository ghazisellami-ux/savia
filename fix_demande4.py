import psycopg2
import psycopg2.extras
import os
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Verifier colonnes
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='interventions' ORDER BY ordinal_position")
cols = [r['column_name'] for r in cur.fetchall()]
print('Colonnes interventions:', cols)

try:
    today = datetime.now().strftime('%Y-%m-%d')
    # Sans colonne client
    cur.execute("""
        INSERT INTO interventions
          (date, machine, technicien, type_intervention, description,
           probleme, code_erreur, statut, priorite, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        today, 'Scanner CT Philips', 'Ali Dridi',
        'Corrective', 'Visite du site pas de rayon', 'Visite du site pas de rayon',
        '', 'En cours', 'Moyenne',
        '[Cabinet Medical El El Manar] Demande #4'
    ))
    new_row = cur.fetchone()
    new_id = new_row['id']
    print('Nouvelle intervention creee, id:', new_id)

    cur.execute(
        'UPDATE demandes_intervention SET intervention_id = %s WHERE id = 4',
        (new_id,)
    )
    conn.commit()
    print('OK - Intervention #{} liee a demande #4 pour Ali Dridi'.format(new_id))

    cur.execute('SELECT id, statut, machine, technicien FROM interventions WHERE id = %s', (new_id,))
    print('Intervention:', dict(cur.fetchone()))

except Exception as e:
    conn.rollback()
    print('ERREUR:', e)
finally:
    cur.close()
    conn.close()
