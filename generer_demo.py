"""
Génère des données de démonstration pour tester le moteur prédictif.
Crée un historique de pannes sur 90 jours dans le fichier Excel.
"""
import os
import sys
import random
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import EXCEL_PATH, SHEET_HISTORIQUE, SHEET_EQUIPEMENTS, SHEET_CODES, SHEET_SOLUTIONS

def generer_demo():
    machines = [
        "Scanner_CT_01.log",
        "IRM_Salle1.log",
        "Radio_DR_02.log",
        "Mammo_01.log",
        "Echo_Salle3.log",
    ]
    codes = ["4A01", "4B02", "7F03", "3C04", "5A01", "5B02", "6C03", "8D01"]
    types = ["Hardware", "Software", "Power", "Calibration", "Tube RX", "Détecteur", "Network"]
    severites = ["HAUTE", "MOYENNE", "BASSE", "CRITIQUE"]

    # Historique sur 90 jours
    now = datetime.now()
    rows = []
    for _ in range(150):
        machine = random.choice(machines)
        date = now - timedelta(
            days=random.randint(0, 90),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        rows.append({
            "Date": date.strftime("%Y-%m-%d %H:%M:%S"),
            "Machine": machine,
            "Code": random.choice(codes),
            "Type": random.choice(types),
            "Severite": random.choice(severites),
            "Resolu": random.choice(["Oui", "Non"]),
        })

    df_hist = pd.DataFrame(rows)

    # Équipements
    equipements = [
        {"Nom": "Scanner_CT_01.log", "Type": "Scanner CT", "Fabricant": "Siemens",
         "Modele": "SOMATOM go.Up", "NumSerie": "SN-2024-001",
         "DateInstallation": "2022-03-15", "DernieresMaintenance": "2025-12-01",
         "Statut": "Opérationnel", "Notes": "Scanner principal salle 2"},
        {"Nom": "IRM_Salle1.log", "Type": "IRM", "Fabricant": "GE Healthcare",
         "Modele": "SIGNA Explorer", "NumSerie": "SN-2024-002",
         "DateInstallation": "2021-06-20", "DernieresMaintenance": "2026-01-15",
         "Statut": "Opérationnel", "Notes": "IRM 1.5T salle 1"},
        {"Nom": "Radio_DR_02.log", "Type": "Radiographie Numérique (DR)", "Fabricant": "Philips",
         "Modele": "DigitalDiagnost C90", "NumSerie": "SN-2024-003",
         "DateInstallation": "2023-01-10", "DernieresMaintenance": "2025-11-20",
         "Statut": "Opérationnel", "Notes": "Radio numérique salle urgences"},
        {"Nom": "Mammo_01.log", "Type": "Mammographe", "Fabricant": "Hologic",
         "Modele": "Selenia Dimensions", "NumSerie": "SN-2024-004",
         "DateInstallation": "2022-09-05", "DernieresMaintenance": "2025-10-15",
         "Statut": "En maintenance", "Notes": "Mammographe numérique 3D"},
        {"Nom": "Echo_Salle3.log", "Type": "Échographe", "Fabricant": "Samsung",
         "Modele": "RS85 Prestige", "NumSerie": "SN-2024-005",
         "DateInstallation": "2024-02-28", "DernieresMaintenance": "2026-01-20",
         "Statut": "Opérationnel", "Notes": "Échographe polyvalent salle 3"},
    ]
    df_equip = pd.DataFrame(equipements)

    # Codes connus
    codes_data = [
        {"Code": "4A01", "Message": "Température tube élevée", "Niveau": "ATTENTION", "Type": "Thermal"},
        {"Code": "4B02", "Message": "Erreur rotation gantry", "Niveau": "ERREUR", "Type": "Hardware"},
        {"Code": "7F03", "Message": "Défaillance alimentation HT", "Niveau": "CRITIQUE", "Type": "Power"},
        {"Code": "3C04", "Message": "Calibration détecteur requise", "Niveau": "ATTENTION", "Type": "Calibration"},
        {"Code": "5A01", "Message": "Vibration bobine gradient", "Niveau": "ATTENTION", "Type": "Hardware"},
        {"Code": "5B02", "Message": "Perte signal RF intermittente", "Niveau": "ERREUR", "Type": "Hardware"},
        {"Code": "6C03", "Message": "Erreur communication console", "Niveau": "ERREUR", "Type": "Network"},
        {"Code": "8D01", "Message": "Usure tube RX détectée", "Niveau": "ATTENTION", "Type": "Tube RX"},
    ]
    df_codes = pd.DataFrame(codes_data)

    # Solutions
    solutions_data = [
        {"Mot_Cle": "4A01", "Type": "Thermal", "Priorite": "MOYENNE",
         "Cause": "Système de refroidissement insuffisant ou filtre encrassé",
         "Solution": "1. Vérifier ventilation salle 2. Nettoyer filtres 3. Contrôler liquide de refroidissement"},
        {"Mot_Cle": "4B02", "Type": "Hardware", "Priorite": "HAUTE",
         "Cause": "Usure roulement gantry ou déséquilibre mécanique",
         "Solution": "1. Arrêter acquisitions 2. Inspecter roulements 3. Recalibrer vitesse rotation"},
        {"Mot_Cle": "7F03", "Type": "Power", "Priorite": "HAUTE",
         "Cause": "Défaillance module alimentation haute tension",
         "Solution": "1. Arrêt immédiat 2. Vérifier fusibles HT 3. Tester condensateurs 4. Appeler SAV constructeur"},
        {"Mot_Cle": "3C04", "Type": "Calibration", "Priorite": "MOYENNE",
         "Cause": "Dérive des paramètres détecteur après usage prolongé",
         "Solution": "1. Lancer séquence calibration constructeur 2. Vérifier fantôme QC 3. Documenter résultats"},
        {"Mot_Cle": "5A01", "Type": "Hardware", "Priorite": "MOYENNE",
         "Cause": "Fixation bobine gradient desserrée ou amortisseur usé",
         "Solution": "1. Vérifier serrage fixations 2. Inspecter amortisseurs 3. Planifier maintenance si récurrent"},
        {"Mot_Cle": "5B02", "Type": "Hardware", "Priorite": "HAUTE",
         "Cause": "Connecteur RF dégradé ou interférence électromagnétique",
         "Solution": "1. Inspecter connecteurs RF 2. Vérifier blindage cage Faraday 3. Recalibrer chaîne RF"},
        {"Mot_Cle": "6C03", "Type": "Network", "Priorite": "MOYENNE",
         "Cause": "Câble réseau défectueux ou surcharge réseau DICOM",
         "Solution": "1. Tester câble Ethernet 2. Vérifier switch réseau 3. Redémarrer service DICOM"},
        {"Mot_Cle": "8D01", "Type": "Tube RX", "Priorite": "HAUTE",
         "Cause": "Tube radiogène en fin de vie (heures d'utilisation élevées)",
         "Solution": "1. Vérifier compteur heures tube 2. Commander tube de remplacement 3. Planifier changement"},
    ]
    df_solutions = pd.DataFrame(solutions_data)

    # Écriture
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl", mode="w") as writer:
        df_codes.to_excel(writer, sheet_name=SHEET_CODES, index=False)
        df_solutions.to_excel(writer, sheet_name=SHEET_SOLUTIONS, index=False)
        df_hist.to_excel(writer, sheet_name=SHEET_HISTORIQUE, index=False)
        df_equip.to_excel(writer, sheet_name=SHEET_EQUIPEMENTS, index=False)

    print(f"[OK] Donnees de demo generees dans {EXCEL_PATH}")
    print(f"   - {len(df_hist)} evenements historiques")
    print(f"   - {len(df_equip)} equipements")
    print(f"   - {len(df_codes)} codes d erreur")
    print(f"   - {len(df_solutions)} solutions")

if __name__ == "__main__":
    generer_demo()
