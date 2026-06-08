#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple seed script with realistic names."""

import os
import sys
import random
import bcrypt
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("seed")

# ==========================================
# REALISTIC TUNISIAN CLINICS & HOSPITALS
# ==========================================
CLINICS_TUNISIA = [
    "Clinique Al Amal", "Clinique du Lac", "Clinique La Marsa",
    "Clinique Avicenne", "Clinique Aziza Othmana", "Clinique Essafa",
    "Clinique Ennasr", "Clinique Zitouna", "Hôpital Central de Tunis",
    "Hôpital Régional de Sousse", "Hôpital Ibn Jazzar", "Hôpital Béchir Hamza",
    "Clinique du Dey", "Clinique Khiar", "Hôpital Fattouma Bourguiba",
    "Clinique Tunisie Santé", "Clinique Medcom", "Hôpital La Rabta",
    "Hôpital Universitaire de Sfax", "Clinique Sfax", "Hôpital Gafsa",
    "Clinique Kairouan", "Hôpital Gabès", "Clinique Médenine",
    "Hôpital Tozeur", "Clinique Kébili", "Hôpital Bizerte",
    "Clinique Nabeul", "Hôpital Hammamet", "Clinique Ariana",
    "Hôpital Ben Arous", "Clinique Manouba", "Hôpital Monastir",
    "Clinique Mahdia", "Hôpital Kasserine", "Clinique Sidi Bouzid",
    "Hôpital Kef", "Clinique Siliana", "Hôpital Béja",
    "Clinique Jendouba", "Hôpital Zaghouan", "Clinique Grombalia",
    "Hôpital Djerba", "Clinique Ben Gardane", "Hôpital Gafsa",
    "Clinique Tataouine", "Hôpital Djerba", "Clinique Sfax Privée",
    "Hôpital Sousse Privé", "Clinique Tunis Premium"
]

# ==========================================
# REALISTIC EQUIPMENT NAMES BY MANUFACTURER & TYPE
# ==========================================
REALISTIC_EQUIPMENT = [
    # Siemens
    ("Siemens", "SOMATOM Confidence CT Scanner", "Scanner CT"),
    ("Siemens", "Magnetom Avanto 1.5T IRM", "IRM"),
    ("Siemens", "Mammomat Inspiration Mammographe", "Mammographie"),
    ("Siemens", "Artis Q Fluoroscope", "Fluoroscopie"),
    ("Siemens", "AXIOM Artis dBA Angiographe", "Angiographie"),
    
    # Philips
    ("Philips", "Ingenia 3.0T IRM", "IRM"),
    ("Philips", "iU22 Écographe Couleur", "Échographie"),
    ("Philips", "Allura Xper FD20 Angiographe", "Angiographie"),
    ("Philips", "DigitalDiagnost C90 Radiographe", "Radiographie numérique"),
    ("Philips", "MicroDose Mammographe", "Mammographie"),
    
    # GE Healthcare
    ("GE Healthcare", "Optima CT660 Scanner CT", "Scanner CT"),
    ("GE Healthcare", "Signa 3.0T Premier IRM", "IRM"),
    ("GE Healthcare", "Senographe Pristina Mammographe", "Mammographie"),
    ("GE Healthcare", "Innova IGT Fluoroscope", "Fluoroscopie"),
    ("GE Healthcare", "Logiq E10 Écographe", "Échographie"),
    
    # Canon
    ("Canon", "GENESIS Xtream CT Scanner", "Scanner CT"),
    ("Canon", "APLIO 500 Écographe Premium", "Échographie"),
    ("Canon", "Radiforce GX540 Moniteur DICOM", "Radiographie numérique"),
    
    # Hitachi
    ("Hitachi", "ECLOS CT Scanner", "Scanner CT"),
    ("Hitachi", "Avius Écographe", "Échographie"),
    
    # Giotto
    ("Giotto", "Mammographe Giotto Class", "Mammographie"),
    ("Giotto", "Mammographe Giotto Image", "Mammographie"),
    
    # Additional realistic equipment
    ("Toshiba", "Aquilion LB CT Scanner", "Scanner CT"),
    ("Toshiba", "Nemio MX Écographe", "Échographie"),
    ("Fujifilm", "Aplio i-series Écographe", "Échographie"),
    ("Pentax", "Endoscope EG-580V", "Radiographie numérique"),
    ("Shimadzu", "Unidose X Radiographe", "Radiographie numérique"),
    ("Carestream", "DRX-Evolution Radiographe Numérique", "Radiographie numérique"),
    ("Samsung", "Ultrasound WS80A Elite", "Échographie"),
    ("Aloka", "Arietta 850 Écographe", "Échographie"),
    ("Esaote", "MyLab Eight Écographe", "Échographie"),
    
    # CBCT & Dental
    ("Vatech", "OP300 CBCT Maxillo-dentaire", "CBCT"),
    ("Sirona", "Orthophos XG 5 Radiographe Dentaire", "Radiographie numérique"),
    ("Planmeca", "ProOne X3 CBCT Dentaire", "CBCT"),
    
    # Amplificateur de brillance & Fluoroscope
    ("OEC", "9900 Elite Amplificateur Brillance", "Fluoroscopie"),
    ("Ziehm", "ICON-X-Ray Système Fluoroscopie", "Fluoroscopie"),
    
    # Systèmes de stockage DICOM
    ("Agfa", "IMPAX Web Enterprise DICOM", "Radiographie numérique"),
    ("Sectra", "PACS Platform Enterprise", "Radiographie numérique"),
]

# Distribute equipment realistically across types
EQUIPMENT_BY_TYPE = {
    "Scanner CT": [e for e in REALISTIC_EQUIPMENT if "CT" in e[1] or "Scanner" in e[1]],
    "IRM": [e for e in REALISTIC_EQUIPMENT if "IRM" in e[1] or "Signa" in e[1] or "Magnetom" in e[1] or "Ingenia" in e[1]],
    "Radiographie numérique": [e for e in REALISTIC_EQUIPMENT if "Radiographe" in e[1] or "DRX" in e[1]],
    "Mammographie": [e for e in REALISTIC_EQUIPMENT if "Mammo" in e[1] or "Giotto" in e[1]],
    "Fluoroscopie": [e for e in REALISTIC_EQUIPMENT if "Fluoroscope" in e[1] or "Fluoroscopie" in e[1] or "Amplificateur" in e[1]],
    "Angiographie": [e for e in REALISTIC_EQUIPMENT if "Angio" in e[1]],
    "Écographe": [e for e in REALISTIC_EQUIPMENT if "Écographe" in e[1] or "Ultrasound" in e[1]],
    "CBCT": [e for e in REALISTIC_EQUIPMENT if "CBCT" in e[1]],
}

def get_connection():
    """Get a direct database connection."""
    try:
        import psycopg2
        import os
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "postgres"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            user=os.environ.get("POSTGRES_USER", "savia_user"),
            password=os.environ.get("POSTGRES_PASSWORD", "savia_password_secure_2026"),
            database=os.environ.get("POSTGRES_DB", "savia_db")
        )
        conn.autocommit = True
        return conn
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return None

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def seed():
    conn = get_connection()
    if not conn:
        logger.error("Cannot connect to database")
        return False
    
    try:
        cur = conn.cursor()
        
        # 1. Create 50 clients with REAL clinic names
        logger.info("🏥 Creating 50 Tunisian clinics and hospitals...")
        clinics = CLINICS_TUNISIA[:50]  # Take first 50
        clinic_names = []
        
        for i, clinic_name in enumerate(clinics, 1):
            regions = ["Nord", "Centre", "Sud"]
            region = random.choice(regions)
            cities = ["Tunis", "Sousse", "Sfax", "Kairouan", "Bizerte", "Ariana", "Ben Arous"]
            city = random.choice(cities)
            clinic_names.append(clinic_name)
            
            cur.execute(
                "INSERT INTO clients (nom, matricule_fiscale, ville, region, contact, telephone, adresse, type_client, code_client, international) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (clinic_name, f"1{random.randint(100000, 999999)}{i:06d}", 
                 city, region, f"Dr. Directeur {i}", f"+216 {random.randint(20, 99)} {random.randint(100000, 999999)}",
                 f"Rue Médicale {i}", random.choice(["Hôpital Public", "Hôpital Privé", "Clinique"]), 
                 f"CLI{i:05d}", False)
            )
        
        # 2. Create 150 equipment with REAL names
        logger.info("🩻 Creating 150 realistic radiology equipment...")
        equip_names = []
        
        for i in range(1, 151):
            equipment = random.choice(REALISTIC_EQUIPMENT)
            manufacturer, equipment_name, equip_type = equipment
            clinic_name = clinic_names[i % len(clinic_names)]
            
            equip_names.append(equipment_name)
            
            cur.execute(
                "INSERT INTO equipements (nom, type, domaine, fabricant, modele, num_serie, client, service, statut, date_installation, derniere_maintenance, garantie_debut, garantie_duree) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (equipment_name, equip_type, "Radiologie",  # Use equip_type from the tuple, not hardcoded "Radiographie"
                 manufacturer, f"Series {random.randint(2020, 2024)}", f"SN{random.randint(10000000, 99999999)}",
                 clinic_name, "Radiologie", random.choice(["Opérationnel", "Hors Service", "En atelier"]),
                 (datetime.now() - timedelta(days=random.randint(100, 1000))).date(),
                 (datetime.now() - timedelta(days=random.randint(10, 200))).date(),
                 (datetime.now() - timedelta(days=random.randint(100, 700))).date(),
                 random.choice([1, 2, 3, 5]))
            )
        
        # 3. Create users and technicians
        logger.info("👥 Creating users and technicians...")
        users = [
            ("manager", "Manager SAVIA", "Manager", "manager@savia.local", "manager@2026"),
            ("tech_01", "Ahmed Ben Salah", "Technicien", "tech01@savia.local", "tech_01@2026"),
            ("tech_02", "Mohamed El Mansour", "Technicien", "tech02@savia.local", "tech_02@2026"),
            ("tech_03", "Karim Ben Nour", "Technicien", "tech03@savia.local", "tech_03@2026"),
            ("tech_04", "Fatima Leila", "Technicien", "tech04@savia.local", "tech_04@2026"),
            ("tech_05", "Nour El Amir", "Technicien", "tech05@savia.local", "tech_05@2026"),
        ]
        
        technician_usernames = []
        for username, nom_complet, role, email, password in users:
            password_hash = hash_password(password)
            cur.execute(
                "INSERT INTO utilisateurs (username, password_hash, nom_complet, role, email, actif) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (username, password_hash, nom_complet, role, email, 1)
            )
            
            # Also create technician records if it's a technician
            if role == "Technicien":
                technician_usernames.append(username)
                nom_parts = nom_complet.split()
                prenom = nom_parts[0]
                nom = " ".join(nom_parts[1:]) if len(nom_parts) > 1 else nom_parts[0]
                
                cur.execute(
                    "INSERT INTO techniciens (username, nom, prenom, specialite, telephone, email, dispo) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (username, nom, prenom, "Radiologie", f"+216 {random.randint(20, 99)} {random.randint(100000, 999999)}", email, 1)
                )
        
        # 4. Create interventions with proper technician distribution
        logger.info("🔧 Creating 200 interventions...")
        interventions_per_tech = [60, 50, 40, 30, 20]  # Unequal distribution
        
        # Create type distribution: 10 Installation, 5 Formation, rest Preventive & Corrective
        intervention_types_dist = []
        intervention_types_dist.extend(["Installation"] * 10)
        intervention_types_dist.extend(["Formation"] * 5)
        # Remaining 185: 65% Corrective, 35% Preventive
        remaining = 200 - 15
        num_corrective = int(remaining * 0.65)
        num_preventive = remaining - num_corrective
        intervention_types_dist.extend(["Corrective"] * num_corrective)
        intervention_types_dist.extend(["Preventive"] * num_preventive)
        random.shuffle(intervention_types_dist)
        
        # Statuses: 10 "En cours", rest "Terminée"
        intervention_statuses = []
        intervention_statuses.extend(["En cours"] * 10)
        intervention_statuses.extend(["Terminée"] * (200 - 10))
        random.shuffle(intervention_statuses)
        
        intervention_counter = 0
        for tech_idx, count_per_tech in enumerate(interventions_per_tech):
            tech = technician_usernames[tech_idx]
            for _ in range(count_per_tech):
                intervention_counter += 1
                
                # Use shuffled type and status
                intervention_type = intervention_types_dist[intervention_counter - 1]
                intervention_status = intervention_statuses[intervention_counter - 1]
                
                # Past dates for all interventions
                days_ago = random.randint(1, 365)
                
                cur.execute(
                    "INSERT INTO interventions (date, machine, technicien, type_intervention, description, statut, priorite, duree_minutes, cout, cout_pieces) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (datetime.now() - timedelta(days=days_ago),
                     random.choice(equip_names), tech,
                     intervention_type,
                     f"Intervention {intervention_counter}", intervention_status,
                     random.choice(["Basse", "Moyenne", "Haute"]),
                     random.randint(30, 360), round(random.uniform(200, 2500), 2),
                     round(random.uniform(0, 1500), 2))
                )
        
        # 5. Create planning_maintenance (preventive maintenance schedules)
        logger.info("📅 Creating preventive maintenance plans...")
        for i in range(1, 81):  # 80 maintenance plans
            equip = random.choice(equip_names)
            tech = random.choice(technician_usernames)
            date_prevue = datetime.now() + timedelta(days=random.randint(1, 180))
            
            # Future maintenances should be "Planifiée" or "En cours", not "Cloturée"
            status = random.choice(["Planifiée", "En cours"])
            
            cur.execute(
                "INSERT INTO planning_maintenance (machine, type_maintenance, description, date_prevue, technicien_assigne, statut, recurrence) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (equip, "Preventive", f"Maintenance planifiée {i}", date_prevue.date(), tech,
                 status, random.choice(["Mensuelle", "Trimestrielle", "Semestrielle"]))
            )
        
        # 6. Create spare parts
        logger.info("📦 Creating 120 spare parts...")
        parts = [
            ("TUBE-RX", "Tube radiogène haute tension", 8500),
            ("DETECTOR-FPD", "Détecteur plan numérique", 15000),
            ("MONITOR", "Écran médical DICOM", 2800),
            ("FILTER", "Filtre X-ray protection", 350),
            ("COLLIMATOR", "Collimateur automatique", 2200),
            ("MOTOR", "Moteur gantry", 5500),
        ]
        
        equip_types_list = ["Scanner CT", "IRM", "Radiographie numérique", "Mammographie", "Fluoroscopie", "Écographe"]
        manufacturers_list = ["Siemens", "Philips", "GE Healthcare", "Canon", "Hitachi", "Giotto"]
        
        for i in range(1, 121):
            part = random.choice(parts)
            cur.execute(
                "INSERT INTO pieces_rechange (reference, designation, equipement_type, stock_actuel, stock_minimum, fournisseur, prix_unitaire, domaine) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (f"{part[0]}_{i:03d}", f"{part[1]} v{i}", random.choice(equip_types_list),
                 random.randint(0, 20), random.randint(1, 5), random.choice(manufacturers_list),
                 part[2], "Radiologie")
            )
        
        # 7. Create contracts - PROPERLY LINKED TO ACTUAL CLIENTS AND EQUIPMENT
        logger.info("📋 Creating 40 contracts...")
        for i in range(1, 41):
            date_debut = datetime.now() - timedelta(days=random.randint(100, 365))
            client_name = clinic_names[i % len(clinic_names)]
            equip_name = equip_names[i % len(equip_names)]
            
            cur.execute(
                "INSERT INTO contrats (client, equipement, type_contrat, date_debut, date_fin, montant, statut, sla_temps_reponse_h, recurrence_maintenance) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (client_name, equip_name,
                 "Maintenance Annuelle", date_debut.date(), (date_debut + timedelta(days=365)).date(),
                 round(random.uniform(2000, 15000), 2), random.choice(["Actif", "Expiré"]),
                 random.choice([4, 8, 24]), random.choice(["Mensuelle", "Trimestrielle", "Semestrielle"]))
            )
        
        cur.close()
        conn.close()
        
        logger.info("=" * 70)
        logger.info("✅ SEEDING COMPLETE!")
        logger.info("=" * 70)
        logger.info("📊 Created with REALISTIC DATA:")
        logger.info("  • 50 Tunisian clinics & hospitals (Al Amal, Essafa, Aziza Othmana, etc.)")
        logger.info("  • 150 real medical equipment (SOMATOM, Ingenia, Senographe, Giotto, etc.)")
        logger.info("  • 6 users + 5 technician records")
        logger.info("  • 200 interventions (60-50-40-30-20 distribution)")
        logger.info("  • 80 preventive maintenance schedules")
        logger.info("  • 120 spare parts")
        logger.info("  • 40 maintenance contracts")
        logger.info("\n🔐 Login: manager / manager@2026")
        logger.info("🔐 Technicians: tech_01 to tech_05 / tech_XX@2026")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = seed()
    sys.exit(0 if success else 1)
