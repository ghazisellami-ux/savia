import paramiko

host = "51.91.124.49"
username = "ubuntu"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, username=username)

script = '''
import sys
sys.path.insert(0, "/home/ubuntu/app")
from db_engine import get_config
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv("/home/ubuntu/app/.env")
DATABASE_URL = os.environ.get("DATABASE_URL")
taux = float(get_config("taux_horaire_technicien", "90") or "90")

print(f"Taux horaire: {taux} TND/h")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("UPDATE interventions SET cout = ROUND((COALESCE(duree_minutes, 0) / 60.0) * %s, 0)", (taux,))
updated = cur.rowcount
conn.commit()

cur.execute("SELECT id, duree_minutes, cout FROM interventions ORDER BY id LIMIT 5")
print(f"Updated {updated} interventions")
for row in cur.fetchall():
    print(f"  ID={row[0]} | duree={row[1]}min | cout={row[2]} TND")

cur.close()
conn.close()
print("Done!")
'''

sftp = client.open_sftp()
with sftp.file("/tmp/recalc.py", "w") as f:
    f.write(script)
sftp.close()

stdin, stdout, stderr = client.exec_command("cd /home/ubuntu/app && ./venv/bin/python3 /tmp/recalc.py")
print(stdout.read().decode('utf-8', errors='ignore'))
err = stderr.read().decode('utf-8', errors='ignore')
if 'traceback' in err.lower():
    print("ERR:", err[-500:])

client.close()
