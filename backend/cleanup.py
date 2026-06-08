#!/usr/bin/env python3
import os
import psycopg2

conn = psycopg2.connect(
    dbname=os.environ.get('POSTGRES_DB', 'savia'),
    user=os.environ.get('POSTGRES_USER', 'postgres'),
    password=os.environ.get('POSTGRES_PASSWORD', 'postgres'),
    host=os.environ.get('POSTGRES_HOST', 'postgres')
)
conn.autocommit = True
cur = conn.cursor()

cur.execute('DELETE FROM contrats')
cur.execute('DELETE FROM planning_maintenance')
cur.execute('DELETE FROM interventions')
cur.execute('DELETE FROM techniciens')
cur.execute('DELETE FROM pieces_rechange')
cur.execute('DELETE FROM equipements')
cur.execute('DELETE FROM clients')
cur.execute("DELETE FROM utilisateurs WHERE role != 'Admin'")

cur.close()
conn.close()
print('✅ Cleanup done')
