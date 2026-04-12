import os
import json
import paramiko
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# CONFIGURATION DES SERVEURS CLIENTS
# ==========================================
# Vous pouvez ajouter autant de clients que vous voulez ici.
# Si vous utilisez une clé SSH au lieu d'un mot de passe (recommandé), 
# laissez 'password' vide ou retirez la ligne.
CLIENTS = [
    {
        "name": "VPS de Test (Votre Serveur Actuel)",
        "ip": "51.91.124.49",
        "user": "ubuntu",
        "app_dir": "/home/ubuntu/app",
        "service_web": "sic-radiologie", # Remplacez par sic-web si vous utilisez le nouveau package
        "service_api": "sic-api",
        "password": "" # Laissez vide si authentification par clé SSH
    },
    # Exemple pour un vrai client (retirez le # pour l'activer plus tard)
    # {
    #     "name": "Clinique Pasteur",
    #     "ip": "1.2.3.4",
    #     "user": "ubuntu",
    #     "app_dir": "/home/ubuntu/savia_cliniquepasteur",
    #     "service_web": "sic-web.service",
    #     "service_api": "sic-api.service",
    #     "password": "mot_de_passe_secret"
    # }
]

# Les dossiers et fichiers à NE SURTOUT PAS envoyer
IGNORE_DIRS = {
    "__pycache__", "venv", ".venv", ".git", ".streamlit", "photos", 
    "contrats_files", "documents_techniques", "logs", "tmp", "package_*", "backups"
}

IGNORE_FILES = {
    "sic_radiologie.db", ".env", "update_all_clients.py", 
    "creer_package_client.py", "*.db-wal", "*.db-shm", "knowledge_base.xlsx",
    "generer_licence.py", "deploy_key.py", "license.key"
}

# ==========================================
# LOGIQUE DE MISE À JOUR
# ==========================================

def is_ignored(item_name, is_dir=False):
    """Vérifie si un fichier ou dossier doit être ignoré."""
    if is_dir and item_name in IGNORE_DIRS:
        return True
    if not is_dir:
        # Match exact
        if item_name in IGNORE_FILES:
            return True
        # Match wildcard *.db-wal etc.
        for ig in IGNORE_FILES:
            if ig.startswith("*") and item_name.endswith(ig[1:]):
                return True
            if ig.startswith("package_") and item_name.startswith("package_"): # Cas du dossier généré
                return True
    return False

def upload_folder(sftp, local_dir, remote_dir):
    """Parcourt un dossier local et uploade son contenu."""
    try:
        sftp.stat(remote_dir)
    except IOError:
        sftp.mkdir(remote_dir)

    for item in os.listdir(local_dir):
        local_path = os.path.join(local_dir, item)
        remote_path = f"{remote_dir}/{item}"

        if os.path.isdir(local_path):
            if not is_ignored(item, is_dir=True):
                if item.startswith("package_"): continue # ignore package clients
                upload_folder(sftp, local_path, remote_path)
        else:
            if not is_ignored(item, is_dir=False):
                try:
                    sftp.put(local_path, remote_path)
                except Exception as e:
                    print(f"    ⚠️ Erreur upload {item} : {e}")

def update_client(client):
    """Mise à jour pour UN client spécifique."""
    print(f"\n🔄 Début mise à jour pour : {client['name']} ({client['ip']})")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Connexion SSH (avec ou sans mot de passe)
        if client.get("password"):
            ssh.connect(client['ip'], username=client['user'], password=client['password'], timeout=10)
        else:
            # Cherchera automatiquement les clés .ssh locales
            ssh.connect(client['ip'], username=client['user'], timeout=10)
            
        sftp = ssh.open_sftp()
        local_root = os.path.abspath(os.path.dirname(__file__))
        remote_root = client['app_dir']
        
        print(f"  Uploading fichiers vers {remote_root}...")
        upload_folder(sftp, local_root, remote_root)
        sftp.close()
        
        print("  Redémarrage des services pour appliquer la mise à jour...")
        cmd = f"sudo systemctl restart {client['service_web']} {client['service_api']}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.recv_exit_status() # Attendre la fin
        
        err = stderr.read().decode('utf-8')
        if err and "Failed" in err:
            print(f"  ❌ Erreur de redémarrage : {err.strip()}")
        else:
            print(f"  ✅ Mise à jour réussie pour {client['name']} !")
            
    except Exception as e:
        print(f"  ❌ ÉCHEC connexion/mise à jour pour {client['name']} : {str(e)}")
    finally:
        ssh.close()

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 60)
    print(" 🚀 SAVIA - SYSTÈME DE MISE À JOUR DE MASSE (FLEET UPDATE)")
    print("=" * 60)
    print(f"Clients détectés : {len(CLIENTS)}")
    print("Attention: Les bases de données (.db) et secrets (.env) ne seront PAS écrasés.")
    
    confirm = input("Voulez-vous lancer le déploiement sur tous vos serveurs ? (O/N) : ")
    if confirm.lower() != 'o':
        print("Mise à jour annulée.")
        return

    # Utilisation du multithreading pour MAJ en parallèle (très rapide)
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(update_client, CLIENTS)

    print("\n=======================================================")
    print(" 🎉 TOUS LES SERVEURS ONT ÉTÉ TRAITÉS !")
    print("=======================================================")

if __name__ == "__main__":
    main()
