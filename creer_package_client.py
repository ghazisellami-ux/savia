import os
import secrets
import shutil
import getpass

# Template Nginx Moderne
NGINX_TEMPLATE = """server {
    listen 80;
    server_name {DOMAIN_NAME};
    client_max_body_size 50M;

    # API Backend PWA (SIC Terrain)
    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 50M;
    }

    # Frontend PWA (SIC Terrain)
    location /terrain/ {
        alias /home/ubuntu/{APP_DIR}/pwa-terrain/;
        index index.html;
        try_files $uri $uri/ /terrain/index.html;
        
        # Ignorer le cache pour les fichiers vitaux de la PWA
        location ~ /(sw\.js|manifest\.json)$ {
            alias /home/ubuntu/{APP_DIR}/pwa-terrain/$1;
            add_header Cache-Control "no-cache, no-store, must-revalidate";
            add_header Pragma "no-cache";
            add_header Expires "0";
        }
    }

    # Serveur de Photos locales (si non-S3)
    location /photos/ {
        alias /home/ubuntu/{APP_DIR}/photos/;
        autoindex off;
    }

    # Backend Streamlit (SAVIA Web App)
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
"""

# Template Systemd Service Streamlit
SYSTEMD_WEB_TEMPLATE = """[Unit]
Description=SAVIA Web App - {CLIENT_NAME}
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/{APP_DIR}
EnvironmentFile=/home/ubuntu/{APP_DIR}/.env
ExecStart=/home/ubuntu/{APP_DIR}/venv/bin/streamlit run master_app.py --server.port 8501
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

# Template Systemd Service API
SYSTEMD_API_TEMPLATE = """[Unit]
Description=SAVIA API App - {CLIENT_NAME}
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/{APP_DIR}
EnvironmentFile=/home/ubuntu/{APP_DIR}/.env
ExecStart=/home/ubuntu/{APP_DIR}/venv/bin/python api_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

# Template Install Script
INSTALL_SH_TEMPLATE = """#!/bin/bash
exec > >(tee -i install_log.txt)
exec 2>&1

echo "======================================================"
echo " 🚀 INSTALLATION SAVIA -> Client : {CLIENT_NAME}"
echo "======================================================"

APP_DIR="/home/ubuntu/{APP_DIR}"

echo "[1/6] Mise à jour du système..."
sudo apt update -y
sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx zip unzip libpq-dev python3-dev

{PG_INSTALL_BLOCK}

echo "[2/6] Configuration Python & Dépendances..."
cd $APP_DIR
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install pyOpenSSL cryptography --upgrade
pip install -r requirements.txt
if [ "{DB_TYPE}" == "postgres" ]; then
    pip install psycopg2-binary
fi

echo "[3/6] Configuration des dossiers..."
mkdir -p photos tmp logs contrats_files documents_techniques
chmod -R 777 photos tmp logs contrats_files documents_techniques

echo "[4/6] Installation des services Systemd..."
sudo cp sic-web.service /etc/systemd/system/sic-web.service
sudo cp sic-api.service /etc/systemd/system/sic-api.service
sudo systemctl daemon-reload
sudo systemctl enable sic-web.service sic-api.service
sudo systemctl restart sic-web.service sic-api.service

echo "[5/6] Configuration Nginx..."
sudo cp nginx.conf /etc/nginx/sites-available/{APP_DIR}
sudo ln -sf /etc/nginx/sites-available/{APP_DIR} /etc/nginx/sites-enabled/
# Remove default nginx config if exists
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo "[6/6] Initialisation de la configuration par défaut..."
source venv/bin/activate
python3 init_config.py

echo ""
echo "======================================================"
echo " ✅ DÉPLOIEMENT TERMINÉ EN LOCAL !                    "
echo " L'application est disponible en HTTP pour le moment. "
echo " POUR ACTIVER HTTPS (RECOMMANDÉ) :                   "
echo " sudo certbot --nginx -d {DOMAIN_NAME}               "
echo "======================================================"
"""

PG_INSTALL_BLOCK_TEMPLATE = """
echo "[-] Installation et Configuration de PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib
sudo -i -u postgres psql -c "CREATE DATABASE {PG_DB};"
sudo -i -u postgres psql -c "CREATE USER {PG_USER} WITH ENCRYPTED PASSWORD '{PG_PASS}';"
sudo -i -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE {PG_DB} TO {PG_USER};"
# Pour Postgres 15+
sudo -i -u postgres psql -d {PG_DB} -c "GRANT ALL ON SCHEMA public TO {PG_USER};"
"""


def generate_package():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 60)
    print(" 📦 GÉNÉRATEUR DE PACKAGE CLIENT SAVIA (PRO) 📦 ")
    print("=" * 60)

    client_name = input("Nom du client (ex: Clinique Pasteur) : ").strip()
    domain_name = input("Nom de domaine (ex: sav.cliniquepasteur.com) : ").strip()
    
    print("\n[Base de Données]")
    print("1: SQLite (Démos, petits clients)")
    print("2: PostgreSQL (Recommandé, Production)")
    choice = input("Choix (1 ou 2) [2 par défaut] : ").strip()
    db_type = "sqlite" if choice == "1" else "postgres"

    # ID unique
    safe_name = "".join(c if c.isalnum() else "_" for c in client_name).lower()
    app_dir_name = f"savia_{safe_name}"
    out_dir = f"package_{app_dir_name}"
    
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    pg_install_script = ""
    pg_db = f"db_{safe_name}"
    pg_user = f"user_{safe_name}"
    pg_pass = secrets.token_urlsafe(16)
    
    jwt_secret = secrets.token_hex(32)
    
    # Construction du .env
    env_content = f"# Configurations SAVIA - {client_name}\n"
    env_content += f"JWT_SECRET={jwt_secret}\n"
    
    if db_type == "postgres":
        pg_install_script = PG_INSTALL_BLOCK_TEMPLATE.format(PG_DB=pg_db, PG_USER=pg_user, PG_PASS=pg_pass)
        env_content += f"DATABASE_URL=postgresql://{pg_user}:{pg_pass}@localhost:5432/{pg_db}\n"

    # Save .env
    with open(os.path.join(out_dir, ".env"), "w", encoding="utf-8") as f:
        f.write(env_content)

    # Nginx
    nginx_content = NGINX_TEMPLATE.replace("{DOMAIN_NAME}", domain_name).replace("{APP_DIR}", app_dir_name)
    with open(os.path.join(out_dir, "nginx.conf"), "w", encoding="utf-8") as f:
        f.write(nginx_content)

    # SystemD Web
    systemd_web = SYSTEMD_WEB_TEMPLATE.replace("{CLIENT_NAME}", client_name).replace("{APP_DIR}", app_dir_name)
    with open(os.path.join(out_dir, "sic-web.service"), "w", encoding="utf-8") as f:
        f.write(systemd_web)

    # SystemD API
    systemd_api = SYSTEMD_API_TEMPLATE.replace("{CLIENT_NAME}", client_name).replace("{APP_DIR}", app_dir_name)
    with open(os.path.join(out_dir, "sic-api.service"), "w", encoding="utf-8") as f:
        f.write(systemd_api)

    # Shell
    install_script = INSTALL_SH_TEMPLATE \
        .replace("{CLIENT_NAME}", client_name) \
        .replace("{APP_DIR}", app_dir_name) \
        .replace("{DOMAIN_NAME}", domain_name) \
        .replace("{PG_INSTALL_BLOCK}", pg_install_script) \
        .replace("{DB_TYPE}", db_type)
        
    with open(os.path.join(out_dir, "install.sh"), "w", encoding="utf-8", newline='\n') as f:
        f.write(install_script)

    # Config init via app db_engine pour assurer SQLite OU Postgres !
    config_py = f"""import os
from db_engine import get_db, init_db
from dotenv import load_dotenv

# Charger l'environnement généré (incluant DATABASE_URL si postgres)
load_dotenv('.env')

# 1. Créer les tables via le dual-mode engine
init_db()

# 2. Injecter la configuration du nom de l'entreprise
try:
    with get_db() as conn:
        conn.execute("INSERT INTO config_client (cle, valeur) VALUES ('nom_organisation', '{client_name}') ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur")
    print("Base initialisée avec le nom d'organisation : {client_name}")
except Exception as e:
    print("Erreur initialisation :", e)
"""
    with open(os.path.join(out_dir, "init_config.py"), "w", encoding="utf-8") as f:
        f.write(config_py)

    print(f"\n✅ Package généré avec succès dans le dossier : {out_dir}")
    print("\n--- 🛠️  PROCÉDURE DE DÉPLOIEMENT  🛠️ ---")
    print(f"1. Créez un VPS Ubuntu et configurez un DNS pointant sur {domain_name}")
    print(f"2. Sur le VPS, créez le dossier : mkdir /home/ubuntu/{app_dir_name}")
    print(f"3. Uploadez TOUT votre code source vers /home/ubuntu/{app_dir_name}")
    print(f"   (Ne transférez PAS sic_radiologie.db, NI generer_licence.py, NI .env actuel !)")
    print(f"4. Uploadez les fichiers de '{out_dir}' dans /home/ubuntu/{app_dir_name}")
    print(f"5. Connectez-vous en SSH au VPS, allez dans le dossier : cd /home/ubuntu/{app_dir_name}")
    print(f"6. Lancez l'installation : sudo bash install.sh")
    print(f"   -> Le script s'occupera d'installer {'PostgreSQL' if db_type=='postgres' else 'SQLite'}, Python, Nginx")
    print("   -> Il lancera Streamlit et l'API Flask sur leurs ports")
    print(f"7. Exécutez : sudo certbot --nginx -d {domain_name}")
    print("⚡ Vous êtes prêt à vendre !")

if __name__ == "__main__":
    generate_package()
