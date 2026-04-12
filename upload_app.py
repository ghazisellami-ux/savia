"""Upload all modified files to VPS via SFTP."""
import paramiko
import os, sys, glob

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

host = "51.91.124.49"
username = "ubuntu"
remote_app = "/home/ubuntu/app"
local_app = os.path.dirname(os.path.abspath(__file__))

# Files to upload (relative paths)
files = [
    "db_engine.py",
    "db_sqlite.py",
    "db_postgres.py",
    "auth.py",
    "ai_engine.py",
    "app.py",
    "config.py",
    "database.py",
    "data_sync.py",
    "api_server.py",
    "reports.py",
    "pdf_generator.py",
    "predictive_stock.py",
    "license_manager.py",
    "iot_integration.py",
    "anomaly_detector.py",
    "migrate_sqlite_to_postgres.py",
    "deploy_vps.py",
    ".env.example",
    "Dockerfile",
    "requirements-api.txt",
]

# Add all views
for f in glob.glob(os.path.join(local_app, "views", "*.py")):
    files.append("views/" + os.path.basename(f))

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, username=username)
sftp = client.open_sftp()

# Ensure views dir exists
try:
    sftp.mkdir(f"{remote_app}/views")
except:
    pass

uploaded = 0
for f in files:
    local = os.path.join(local_app, f.replace("/", os.sep))
    remote = f"{remote_app}/{f}"
    if os.path.exists(local):
        try:
            sftp.put(local, remote)
            size = os.path.getsize(local)
            print(f"  [OK] {f} ({size:,} bytes)")
            uploaded += 1
        except Exception as e:
            print(f"  [FAIL] {f}: {e}")
    else:
        print(f"  [SKIP] {f} (not found locally)")

sftp.close()

# Restart service and verify
print(f"\n{uploaded} files uploaded. Restarting services...")
cmds = [
    "sudo systemctl restart sic-api",
    "sleep 2 && sudo systemctl status sic-api --no-pager | tail -5",
    "cd /home/ubuntu/app && ./venv/bin/python3 -c 'from db_engine import USE_PG; print(\"PostgreSQL:\", USE_PG)'",
]
for cmd in cmds:
    print(f"> {cmd[:70]}...")
    _, o, e = client.exec_command(cmd)
    o.channel.recv_exit_status()
    out = o.read().decode('utf-8', errors='replace').strip()
    err = e.read().decode('utf-8', errors='replace').strip()
    if out: print(f"  {out}")
    if 'error' in err.lower() or 'traceback' in err.lower():
        print(f"  ERR: {err[-300:]}")

client.close()
print("\nUpload complete!")
