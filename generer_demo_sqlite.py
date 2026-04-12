"""
Genere des donnees de demonstration dans la base SQLite.
Cree l'historique des pannes + des fichiers log pour le dashboard.
Assigne a chaque machine un profil de sante DIVERSIFIE.
Usage: python generer_demo_sqlite.py
"""
import os
import sys
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_engine import (
    init_db, get_db, lire_equipements,
    ajouter_codes_batch
)
from config import LOGS_DIR


# ==========================================
# CATALOGUE COMPLET DE CODES D'ERREUR
# ==========================================

CODES_HEX = [
    # Thermal
    {"Code": "4A01", "Message": "Temperature tube elevee", "Niveau": "ATTENTION", "Type": "Thermal"},
    {"Code": "4A02", "Message": "Surchauffe detecteur", "Niveau": "ERREUR", "Type": "Thermal"},
    {"Code": "4A03", "Message": "Ventilateur salle en defaut", "Niveau": "ATTENTION", "Type": "Thermal"},
    {"Code": "4A04", "Message": "Liquide de refroidissement bas", "Niveau": "ERREUR", "Type": "Thermal"},
    # Hardware
    {"Code": "4B02", "Message": "Erreur rotation gantry", "Niveau": "ERREUR", "Type": "Hardware"},
    {"Code": "4B05", "Message": "Usure courroie de transmission", "Niveau": "ATTENTION", "Type": "Hardware"},
    {"Code": "4B06", "Message": "Capteur position gantry defaillant", "Niveau": "ERREUR", "Type": "Hardware"},
    {"Code": "4B07", "Message": "Bruit anormal moteur table", "Niveau": "ATTENTION", "Type": "Hardware"},
    # Power
    {"Code": "7F03", "Message": "Defaillance alimentation HT", "Niveau": "CRITIQUE", "Type": "Power"},
    {"Code": "7F04", "Message": "Surtension detectee sur bus DC", "Niveau": "ERREUR", "Type": "Power"},
    {"Code": "7F05", "Message": "Onduleur en mode batterie", "Niveau": "ATTENTION", "Type": "Power"},
    {"Code": "7F06", "Message": "Micro-coupure electrique enregistree", "Niveau": "ATTENTION", "Type": "Power"},
    # Calibration
    {"Code": "3C04", "Message": "Calibration detecteur requise", "Niveau": "ATTENTION", "Type": "Calibration"},
    {"Code": "3C05", "Message": "Derive dose patient detectee", "Niveau": "ERREUR", "Type": "Calibration"},
    {"Code": "3C06", "Message": "Controle qualite quotidien echoue", "Niveau": "ERREUR", "Type": "Calibration"},
    {"Code": "3C07", "Message": "Fantome QC hors tolerance", "Niveau": "ATTENTION", "Type": "Calibration"},
    # RF / IRM / Cryogenie
    {"Code": "5A01", "Message": "Vibration bobine gradient", "Niveau": "ATTENTION", "Type": "Hardware"},
    {"Code": "5B02", "Message": "Perte signal RF intermittente", "Niveau": "ERREUR", "Type": "Hardware"},
    {"Code": "5B03", "Message": "Artefact de susceptibilite magnetique", "Niveau": "ATTENTION", "Type": "Hardware"},
    {"Code": "5B04", "Message": "Niveau helium critique < 60%", "Niveau": "CRITIQUE", "Type": "Cryogenie"},
    # Network
    {"Code": "6C03", "Message": "Erreur communication console DICOM", "Niveau": "ERREUR", "Type": "Network"},
    {"Code": "6C04", "Message": "Timeout transfert PACS", "Niveau": "ATTENTION", "Type": "Network"},
    {"Code": "6C05", "Message": "Certificat DICOM TLS expire", "Niveau": "ERREUR", "Type": "Network"},
    {"Code": "6C06", "Message": "Worklist DICOM non synchronisee", "Niveau": "ATTENTION", "Type": "Network"},
    # Tube RX
    {"Code": "8D01", "Message": "Usure tube RX detectee", "Niveau": "ATTENTION", "Type": "Tube RX"},
    {"Code": "8D02", "Message": "Tube RX en fin de vie (>90% usure)", "Niveau": "CRITIQUE", "Type": "Tube RX"},
    {"Code": "8D03", "Message": "Arc electrique dans le tube", "Niveau": "CRITIQUE", "Type": "Tube RX"},
    {"Code": "8D04", "Message": "Generateur HT instable", "Niveau": "ERREUR", "Type": "Tube RX"},
    # Software
    {"Code": "9E01", "Message": "Mise a jour firmware disponible", "Niveau": "ATTENTION", "Type": "Software"},
    {"Code": "9E02", "Message": "Erreur base de donnees patients", "Niveau": "ERREUR", "Type": "Software"},
    {"Code": "9E03", "Message": "Espace disque acquisition < 10%", "Niveau": "ERREUR", "Type": "Software"},
    {"Code": "9E04", "Message": "Licence logiciel expiree", "Niveau": "CRITIQUE", "Type": "Software"},
    # Detecteur
    {"Code": "2F01", "Message": "Pixel mort detecte sur matrice", "Niveau": "ATTENTION", "Type": "Detecteur"},
    {"Code": "2F02", "Message": "Uniformite image hors norme", "Niveau": "ERREUR", "Type": "Detecteur"},
    {"Code": "2F03", "Message": "Bruit image excessif", "Niveau": "ATTENTION", "Type": "Detecteur"},
    {"Code": "2F04", "Message": "Artefact annulaire detecte", "Niveau": "ERREUR", "Type": "Detecteur"},
]

SOLUTIONS_TXT = [
    {"Mot_Cle": "4A01", "Type": "Thermal", "Priorite": "MOYENNE",
     "Cause": "Systeme de refroidissement insuffisant", "Solution": "Verifier ventilation, nettoyer filtres"},
    {"Mot_Cle": "4B02", "Type": "Hardware", "Priorite": "HAUTE",
     "Cause": "Usure roulement gantry", "Solution": "Inspecter roulements, recalibrer rotation"},
    {"Mot_Cle": "7F03", "Type": "Power", "Priorite": "HAUTE",
     "Cause": "Defaillance module alimentation HT", "Solution": "Arret immediat, verifier fusibles, appeler SAV"},
    {"Mot_Cle": "3C04", "Type": "Calibration", "Priorite": "MOYENNE",
     "Cause": "Derive parametres detecteur", "Solution": "Lancer calibration constructeur"},
    {"Mot_Cle": "5B02", "Type": "Hardware", "Priorite": "HAUTE",
     "Cause": "Connecteur RF degrade", "Solution": "Inspecter connecteurs RF, verifier blindage"},
    {"Mot_Cle": "5B04", "Type": "Cryogenie", "Priorite": "HAUTE",
     "Cause": "Fuite helium ou defaillance coldhead", "Solution": "Appeler SAV URGENT, verifier niveau helium"},
    {"Mot_Cle": "6C03", "Type": "Network", "Priorite": "MOYENNE",
     "Cause": "Cable reseau defectueux", "Solution": "Tester cable Ethernet, redemarrer DICOM"},
    {"Mot_Cle": "8D01", "Type": "Tube RX", "Priorite": "HAUTE",
     "Cause": "Tube radiogene en fin de vie", "Solution": "Verifier compteur heures, commander remplacement"},
    {"Mot_Cle": "8D03", "Type": "Tube RX", "Priorite": "HAUTE",
     "Cause": "Isolation defaillante dans le tube", "Solution": "ARRET IMMEDIAT, commander remplacement urgent"},
    {"Mot_Cle": "9E03", "Type": "Software", "Priorite": "MOYENNE",
     "Cause": "Accumulation images non archivees", "Solution": "Archiver images PACS, purger temporaires"},
    {"Mot_Cle": "2F02", "Type": "Detecteur", "Priorite": "HAUTE",
     "Cause": "Degradation matrice detecteur", "Solution": "Recalibrer detecteur, verifier gain pixels"},
]


# ==========================================
# PROFILS DE SANTE DIVERSIFIES
# ==========================================
# Chaque machine recevra un profil parmi ceux-ci, de facon cyclique
# pour garantir la diversite

HEALTH_PROFILES = [
    # Profil "EXCELLENT" — Score 85-95% → 0-2 pannes sur 90j
    {
        "label": "EXCELLENT",
        "nb_pannes_90j": (0, 2),
        "severites": ["BASSE", "ATTENTION", "MOYENNE"],
        "log_error_pct": 2,   # 2% de lignes ERROR dans les logs
        "log_warn_pct": 5,    # 5% WARNING
    },
    # Profil "BON" — Score 70-85% → 3-6 pannes
    {
        "label": "BON",
        "nb_pannes_90j": (3, 6),
        "severites": ["BASSE", "ATTENTION", "MOYENNE", "ATTENTION"],
        "log_error_pct": 4,
        "log_warn_pct": 12,
    },
    # Profil "CORRECT" — Score 55-70% → 7-12 pannes
    {
        "label": "CORRECT",
        "nb_pannes_90j": (7, 12),
        "severites": ["MOYENNE", "ATTENTION", "HAUTE", "BASSE", "MOYENNE"],
        "log_error_pct": 7,
        "log_warn_pct": 18,
    },
    # Profil "MOYEN" — Score 45-60% → 10-15 pannes avec quelques HAUTE
    {
        "label": "MOYEN",
        "nb_pannes_90j": (10, 15),
        "severites": ["HAUTE", "MOYENNE", "ERREUR", "ATTENTION", "MOYENNE"],
        "log_error_pct": 10,
        "log_warn_pct": 22,
    },
    # Profil "SANS PANNE" — Score 95-100% → 0 pannes
    {
        "label": "SANS PANNE",
        "nb_pannes_90j": (0, 0),
        "severites": [],
        "log_error_pct": 0,
        "log_warn_pct": 3,
    },
]


# ==========================================
# MESSAGES LOG REALISTES
# ==========================================

LOG_INFO = [
    "Demarrage systeme normal",
    "Calibration automatique terminee - OK",
    "Acquisition patient terminee avec succes",
    "Systeme stable - verification OK",
    "Sauvegarde DICOM effectuee ({n} images)",
    "Self-test matinal passe avec succes",
    "Niveau helium OK ({pct}%)",
    "Transfert PACS termine - {n} series",
    "Mise en veille automatique",
    "Reprise apres veille - tous systemes OK",
    "Controle qualite quotidien - PASS",
    "Archivage automatique termine",
    "Patient entre - preparation acquisition",
    "Protocole {proto} charge avec succes",
    "Temperature tube : {temp}C (normal)",
    "Heures tube : {hours}h / 100000h",
    "Nettoyage cache images temporaires",
    "Connexion PACS etablie",
    "Mise a jour horloge systeme",
    "Statistiques journalieres enregistrees",
]

LOG_WARNING = [
    "Temperature ambiante elevee : {temp}C",
    "Espace disque restant : {pct}%",
    "Temps acquisition superieur a la normale (+{sec}s)",
    "Signal faible detecte - acquisition repetee",
    "Batterie onduleur a {pct}% - remplacement prevu",
    "Delai transfert PACS eleve : {sec}s",
    "Calibration recommandee dans {days} jours",
    "Compteur tube a {pct}% de la capacite",
    "Vibration detectee niveau modere ({val}G)",
    "Latence reseau DICOM elevee",
]

LOG_ERROR = [
    "Code {code} - {msg}",
    "ERREUR - Code {code} - {msg}",
    "Echec acquisition - relancer le scan",
    "Perte connexion PACS - tentative reconnexion",
    "Erreur transfert image #{n}",
    "Echec self-test composant {comp}",
    "Timeout communication avec console",
    "Arret urgence operateur",
]

PROTOCOLS = ["Thorax AP", "Crane sans injection", "Abdomen C+", "Rachis lombaire",
             "Genou face/profil", "Mammographie bilaterale", "Echo abdominale",
             "IRM cerebrale T1/T2", "Angio-scanner thoracique", "Panoramique dentaire"]
COMPONENTS = ["gantry", "detecteur", "table", "generateur HT", "alimentation", "console", "DICOM"]


def _format_log(template, code_info=None):
    msg = template
    msg = msg.replace("{n}", str(random.randint(1, 500)))
    msg = msg.replace("{pct}", str(random.randint(15, 92)))
    msg = msg.replace("{temp}", str(random.randint(22, 48)))
    msg = msg.replace("{sec}", str(random.randint(3, 90)))
    msg = msg.replace("{hours}", str(random.randint(5000, 85000)))
    msg = msg.replace("{days}", str(random.randint(2, 30)))
    msg = msg.replace("{val}", f"{random.uniform(0.3, 1.0):.2f}")
    msg = msg.replace("{proto}", random.choice(PROTOCOLS))
    msg = msg.replace("{comp}", random.choice(COMPONENTS))
    if code_info:
        msg = msg.replace("{code}", code_info["Code"])
        msg = msg.replace("{msg}", code_info["Message"])
    else:
        msg = msg.replace("{code}", "0000")
        msg = msg.replace("{msg}", "Erreur generique")
    return msg


# ==========================================
# GENERATEUR PRINCIPAL
# ==========================================

def generer_demo_sqlite():
    init_db()

    # --- Recuperer les equipements ---
    df_equip = lire_equipements()
    if df_equip.empty:
        print("[!] Aucun equipement en base. Utilisation de noms par defaut.")
        machines = ["Scanner_CT_01", "IRM_Salle1", "Radio_DR_02", "Mammo_01", "Echo_Salle3"]
    else:
        machines = df_equip["Nom"].tolist()
        print(f"[OK] {len(machines)} equipement(s) trouves")

    # --- Inserer codes et solutions ---
    ajouter_codes_batch(CODES_HEX, SOLUTIONS_TXT)
    print(f"[OK] {len(CODES_HEX)} codes + {len(SOLUTIONS_TXT)} solutions inseres")

    # --- Assigner un profil de sante a chaque machine (cyclique + shuffle) ---
    profiles_cycle = []
    while len(profiles_cycle) < len(machines):
        profiles_cycle.extend(HEALTH_PROFILES)
    random.shuffle(profiles_cycle)
    machine_profiles = {m: profiles_cycle[i] for i, m in enumerate(machines)}

    # --- Afficher les profils assignes ---
    print("\n--- Profils de sante assignes ---")
    for m, p in machine_profiles.items():
        safe = m[:25].ljust(25)
        print(f"  {safe} -> {p['label']:12s} ({p['nb_pannes_90j'][0]}-{p['nb_pannes_90j'][1]} pannes)")
    print()

    # --- Vider et regenerer l'historique ---
    all_codes = {c["Code"]: c for c in CODES_HEX}
    all_code_list = [c["Code"] for c in CODES_HEX]
    all_type_map = {c["Code"]: c["Type"] for c in CODES_HEX}
    now = datetime.now()
    nb_events_total = 0

    with get_db() as conn:
        conn.execute("DELETE FROM historique")

        for machine, profile in machine_profiles.items():
            min_p, max_p = profile["nb_pannes_90j"]
            nb_pannes = random.randint(min_p, max_p)
            severites = profile["severites"]

            for _ in range(nb_pannes):
                code = random.choice(all_code_list)
                type_err = all_type_map.get(code, "Hardware")
                severite = random.choice(severites) if severites else "BASSE"

                # Repartir les pannes dans le temps
                # Pour les profils MOYEN, concentrer plus de pannes recemment
                if profile["label"] == "MOYEN":
                    day_offset = random.choices(
                        range(90), weights=[90 - d for d in range(90)]
                    )[0]
                else:
                    day_offset = random.randint(0, 89)

                date_evt = now - timedelta(
                    days=day_offset,
                    hours=random.randint(7, 20),
                    minutes=random.randint(0, 59),
                )

                conn.execute("""
                    INSERT INTO historique (date, machine, code, type, severite)
                    VALUES (?, ?, ?, ?, ?)
                """, (date_evt.strftime("%Y-%m-%d %H:%M:%S"), machine, code, type_err, severite))
                nb_events_total += 1

    print(f"[OK] {nb_events_total} evenements historiques generes")

    # --- Generer les fichiers .log ---
    os.makedirs(LOGS_DIR, exist_ok=True)

    for machine, profile in machine_profiles.items():
        safe_name = machine.replace(" ", "_").replace("/", "-")
        if safe_name.endswith(".log"):
            safe_name = safe_name[:-4]
        log_path = os.path.join(LOGS_DIR, f"{safe_name}.log")

        lines = []
        base_date = now - timedelta(days=60)
        err_pct = profile["log_error_pct"]
        warn_pct = profile["log_warn_pct"]
        info_pct = 100 - err_pct - warn_pct

        for day in range(60):
            current_date = base_date + timedelta(days=day)
            nb_lines_day = random.randint(8, 20)

            for _ in range(nb_lines_day):
                hour = random.randint(6, 22)
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                ts = current_date.replace(hour=hour, minute=minute, second=second)

                level = random.choices(
                    ["INFO", "WARNING", "ERROR"],
                    weights=[info_pct, warn_pct, err_pct if err_pct > 0 else 0.1]
                )[0]

                if level == "ERROR":
                    code_info = random.choice(CODES_HEX)
                    message = _format_log(random.choice(LOG_ERROR), code_info)
                elif level == "WARNING":
                    message = _format_log(random.choice(LOG_WARNING))
                else:
                    message = _format_log(random.choice(LOG_INFO))

                lines.append(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {machine} - {message}")

        lines.sort()

        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        ico = {"EXCELLENT": "++", "BON": "+ ", "CORRECT": "~ ", "MOYEN": "- ", "SANS PANNE": "OK"}
        print(f"  [{ico.get(profile['label'], '??')}] {safe_name}.log  ({len(lines)} lignes, {profile['label']})")

    print(f"\n[OK] Demo complete : {len(machines)} machines, {nb_events_total} pannes")


if __name__ == "__main__":
    generer_demo_sqlite()
