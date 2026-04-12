import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('51.91.124.49', username='ubuntu')
_, stdout, stderr = client.exec_command("cd /home/ubuntu/app && source .env && venv/bin/python -c 'from db_engine import init_db; init_db()'")
print(stdout.read().decode())
print(stderr.read().decode())
client.close()
