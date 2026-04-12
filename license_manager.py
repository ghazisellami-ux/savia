# ==========================================
# VERIFICATION DE LICENCE
# ==========================================
import os
import json
from datetime import datetime
from cryptography.fernet import Fernet
from config import MASTER_KEY


def _get_license_data():
    """
    Recupere et dechiffre les donnees de licence.
    Cherche d'abord dans la config DB, puis dans le fichier license.key.
    Retourne dict ou None.
    """
    if not MASTER_KEY:
        return None

    fernet = Fernet(MASTER_KEY)

    # 1. Essayer depuis la base de donnees (cle collee par le client)
    try:
        from db_engine import get_config
        cle_db = get_config("license_key", "")
        if cle_db:
            contenu_clair = fernet.decrypt(cle_db.encode())
            return json.loads(contenu_clair.decode())
    except Exception:
        pass

    # 2. Fallback : fichier license.key
    license_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license.key")
    if os.path.exists(license_path):
        try:
            with open(license_path, "rb") as f:
                contenu_crypte = f.read()
            contenu_clair = fernet.decrypt(contenu_crypte)
            return json.loads(contenu_clair.decode())
        except Exception:
            pass

    return None


def verifier_licence():
    """
    Verifie la licence et retourne un dict de statut :
    {
        "valide": bool,
        "client": str,
        "jours_restants": int,
        "date_expiration": str,
        "alerte_15j": bool,
        "expiree": bool,
        "erreur": str ou None,
    }
    """
    if not MASTER_KEY:
        return {
            "valide": False,
            "client": "",
            "jours_restants": 0,
            "date_expiration": "",
            "alerte_15j": False,
            "expiree": True,
            "erreur": "MASTER_KEY non configuree",
        }

    infos = _get_license_data()
    if infos is None:
        return {
            "valide": False,
            "client": "",
            "jours_restants": 0,
            "date_expiration": "",
            "alerte_15j": False,
            "expiree": True,
            "erreur": "Aucune licence trouvee",
        }

    try:
        date_exp = datetime.strptime(infos["date_expiration"], "%Y-%m-%d")
        jours_restants = (date_exp - datetime.now()).days

        return {
            "valide": jours_restants >= 0,
            "client": infos.get("client", "Client"),
            "jours_restants": jours_restants,
            "date_expiration": infos["date_expiration"],
            "alerte_15j": 0 <= jours_restants <= 15,
            "expiree": jours_restants < 0,
            "erreur": None,
        }
    except Exception as e:
        return {
            "valide": False,
            "client": "",
            "jours_restants": 0,
            "date_expiration": "",
            "alerte_15j": False,
            "expiree": True,
            "erreur": str(e),
        }


def enregistrer_cle_licence(cle_texte):
    """
    Enregistre une cle de licence (texte colle par le client) dans la DB.
    Retourne (bool succes, str message).
    """
    if not MASTER_KEY:
        return False, "MASTER_KEY non configuree sur le serveur"

    if not cle_texte or not cle_texte.strip():
        return False, "Cle vide"

    cle_texte = cle_texte.strip()

    # Valider que la cle est dechiffrable
    try:
        fernet = Fernet(MASTER_KEY)
        contenu_clair = fernet.decrypt(cle_texte.encode())
        infos = json.loads(contenu_clair.decode())

        # Verifier les champs obligatoires
        if "date_expiration" not in infos or "client" not in infos:
            return False, "Cle invalide : champs manquants"

        # Verifier que la date est parseable
        datetime.strptime(infos["date_expiration"], "%Y-%m-%d")

    except Exception:
        return False, "Cle d'acces invalide ou corrompue"

    # Sauvegarder dans la DB
    try:
        from db_engine import set_config
        set_config("license_key", cle_texte)

        # Aussi ecrire dans le fichier license.key pour compatibilite
        license_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license.key")
        with open(license_path, "wb") as f:
            f.write(cle_texte.encode())

        return True, f"Licence activee pour {infos['client']} (expire le {infos['date_expiration']})"
    except Exception as e:
        return False, f"Erreur d'enregistrement : {e}"


# Compatibilite avec l'ancien code
def verifier_acces():
    """Ancien point d'entree. Retourne (client, jours_restants) ou st.stop()."""
    import streamlit as st

    statut = verifier_licence()

    if statut["expiree"]:
        st.error("Licence expiree. Veuillez renouveler votre licence.")
        st.stop()

    if statut["erreur"]:
        st.error(f"Erreur licence : {statut['erreur']}")
        st.stop()

    return statut["client"], statut["jours_restants"]
