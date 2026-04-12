# ==========================================
# 🔑 GÉNÉRATEUR DE LICENCE CLIENT
# Usage : python generer_licence.py
# ==========================================
import json
import uuid
import sys
import os
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

# Charger la MASTER_KEY depuis .env ou en argument
from dotenv import load_dotenv
load_dotenv()

MASTER_KEY = os.getenv("MASTER_KEY", "EjoEM28PNJHXPBRgb1bXgZTZp_HGWS8wgjSxcuu6AfE=")


def generer_licence(nom_client: str, jours: int, dossier_sortie: str = "."):
    """
    Génère un fichier license.key chiffré pour un client.

    Args:
        nom_client: Nom du client (ex: "Clinique El Azhar")
        jours: Nombre de jours d'abonnement
        dossier_sortie: Dossier où sauvegarder le fichier license.key
    """
    if not MASTER_KEY:
        print("[ERREUR] MASTER_KEY non configuree dans .env")
        print("         Generez-en une avec :")
        print("         python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
        return None

    # Générer un identifiant unique pour cette licence
    licence_id = str(uuid.uuid4())[:8].upper()

    # Calculer la date d'expiration
    date_creation = datetime.now()
    date_expiration = date_creation + timedelta(days=jours)

    # Données de la licence
    licence_data = {
        "client": nom_client,
        "licence_id": licence_id,
        "date_creation": date_creation.strftime("%Y-%m-%d %H:%M:%S"),
        "date_expiration": date_expiration.strftime("%Y-%m-%d"),
        "jours_abonnement": jours,
        "version": "2.0",
        "produit": "SIC Radiologie - Maintenance Predictive"
    }

    # Chiffrer avec Fernet
    try:
        fernet = Fernet(MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY)
        contenu_json = json.dumps(licence_data, ensure_ascii=False).encode("utf-8")
        contenu_crypte = fernet.encrypt(contenu_json)

        # Sauvegarder le fichier
        chemin_fichier = os.path.join(dossier_sortie, "license.key")
        with open(chemin_fichier, "wb") as f:
            f.write(contenu_crypte)

        return licence_data, chemin_fichier

    except Exception as e:
        print(f"[ERREUR] Impossible de generer la licence : {e}")
        return None


def afficher_recap(licence_data, chemin):
    """Affiche le récapitulatif de la licence générée."""
    print("")
    print("=" * 55)
    print("   LICENCE GENEREE AVEC SUCCES")
    print("=" * 55)
    print(f"   Client       : {licence_data['client']}")
    print(f"   ID Licence   : {licence_data['licence_id']}")
    print(f"   Creee le     : {licence_data['date_creation']}")
    print(f"   Expire le    : {licence_data['date_expiration']}")
    print(f"   Duree        : {licence_data['jours_abonnement']} jours")
    print(f"   Fichier      : {os.path.abspath(chemin)}")
    print("=" * 55)
    print("")
    print("   Envoyez le fichier 'license.key' au client.")
    print("   Il doit le placer a la racine de l'application.")
    print("")


def mode_interactif():
    """Mode interactif avec saisie au clavier."""
    print("")
    print("=" * 55)
    print("   SIC RADIOLOGIE - Generateur de Licence")
    print("=" * 55)
    print("")

    nom = input("   Nom du client : ").strip()
    if not nom:
        print("[ERREUR] Le nom du client est obligatoire.")
        return

    try:
        jours_str = input("   Nombre de jours d'abonnement : ").strip()
        jours = int(jours_str)
        if jours <= 0:
            print("[ERREUR] Le nombre de jours doit etre positif.")
            return
    except ValueError:
        print("[ERREUR] Entrez un nombre entier valide.")
        return

    dossier = input("   Dossier de sortie (Enter = dossier courant) : ").strip()
    if not dossier:
        dossier = "."

    if not os.path.exists(dossier):
        os.makedirs(dossier, exist_ok=True)

    result = generer_licence(nom, jours, dossier)
    if result:
        licence_data, chemin = result
        afficher_recap(licence_data, chemin)


def mode_arguments():
    """Mode avec arguments en ligne de commande."""
    if len(sys.argv) < 3:
        print("Usage : python generer_licence.py <nom_client> <jours>")
        print("        python generer_licence.py \"Clinique El Azhar\" 365")
        print("")
        print("Ou lancez sans arguments pour le mode interactif :")
        print("        python generer_licence.py")
        return

    nom = sys.argv[1]
    try:
        jours = int(sys.argv[2])
    except ValueError:
        print(f"[ERREUR] '{sys.argv[2]}' n'est pas un nombre valide.")
        return

    dossier = sys.argv[3] if len(sys.argv) > 3 else "."

    result = generer_licence(nom, jours, dossier)
    if result:
        licence_data, chemin = result
        afficher_recap(licence_data, chemin)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode_arguments()
    else:
        mode_interactif()
