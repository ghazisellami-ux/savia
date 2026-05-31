#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌱 SAVIA Data Seeding Script
Génère des données de test réalistes pour le système SAVIA.

Génère:
  • 50 clients (avec données complètes)
  • 100 équipements médicaux (tous domaines)
  • 10 techniciens + comptes utilisateurs
  • 1 compte manager
  • 200+ interventions simulées
  • 50+ plannings de maintenance
  • 100+ pièces de rechange
  • 20+ contrats de maintenance
"""

import os
import sys
import random
import bcrypt
import logging
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from db_engine import get_db, init_db
from config import BASE_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("seed_data")

# ==========================================
# DATA GENERATORS
# ==========================================

MEDICAL_DOMAINS = [
    "Radiologie", "Cardiologie", "Laboratoire", "Chirurgie",
    "Urgences", "Réanimation", "Pédiatrie", "Maternité",
    "Ophtalmologie", "ORL", "Orthopédie", "Neurologie",
    "Gastroentérologie", "Pneumologie", "Dermatologie", "Oncologie"
]

EQUIPMENT_TYPES_BY_DOMAIN = {
    "Radiologie": ["Radiographe", "Scanner", "IRM", "Échographe", "Mammographe", "Fluoroscope"],
    "Cardiologie": ["ECG", "Défibrillateur", "Moniteur cardiaque", "Échographe cardiaque", "Holter"],
    "Laboratoire": ["Analyseur hématologie", "Analyseur chimie", "Centrifugeuse", "Microscope", "Incubateur"],
    "Chirurgie": ["Bistouri électrique", "Aspirateur", "Moniteur anesthésie", "Lampe scialytique", "Table opératoire"],
    "Urgences": ["Moniteur multiparamétrique", "Défibrillateur", "Ventilateur", "Pompe infusion", "Oxymètre"],
    "Réanimation": ["Ventilateur", "Moniteur multiparamétrique", "Pompe infusion", "Dialyseur", "Incubateur"],
    "Pédiatrie": ["Incubateur", "Photothérapie", "Moniteur pédiatrique", "Pompe infusion pédiatrique"],
    "Maternité": ["Moniteur fœtal", "Incubateur", "Photothérapie", "Pompe infusion"],
    "Ophtalmologie": ["Lampe à fente", "Réfractomètre", "Ophtalmoscope", "Tonométre"],
    "ORL": ["Otoscope", "Laryngoscope", "Audiomètre", "Tympanomètre"],
    "Orthopédie": ["Radiographe portable", "Arthroscope", "Microscope opératoire"],
    "Neurologie": ["EEG", "EMG", "Stimulateur électrique", "Microscope opératoire"],
    "Gastroentérologie": ["Endoscope", "Échographe", "Bistouri électrique"],
    "Pneumologie": ["Spiromètre", "Bronchoscope", "Ventilateur", "Oxymètre"],
    "Dermatologie": ["Dermatoscope", "Laser", "Microscope"],
    "Oncologie": ["Accélérateur linéaire", "Simulateur", "Système de planification"]
}

MANUFACTURERS = [
    "Siemens", "Philips", "GE Healthcare", "Canon", "Hitachi",
    "Mindray", "Medtronic", "Stryker", "Zimmer Biomet", "Olympus",
    "Pentax", "Fujifilm", "Toshiba", "Aloka", "Esaote",
    "Sonosite", "BioRad", "Roche", "Abbott", "Sysmex"
]

SPARE_PARTS_GENERIC = [
    ("TUBE-X-RAY-001", "Tube radiogène 150kV", 2500.00),
    ("DETECTOR-FLAT-001", "Détecteur plan numérique", 8000.00),
    ("PUMP-INFUSION-001", "Pompe infusion 8 canaux", 1200.00),
    ("MONITOR-DISPLAY-001", "Écran moniteur 24\" médical", 3500.00),
    ("BATTERY-BACKUP-001", "Batterie UPS 10kVA", 5000.00),
    ("CABLE-ECG-001", "Câble ECG 5 dérivations", 450.00),
    ("ELECTRODE-ECG-001", "Électrodes ECG (boîte 50)", 120.00),
    ("TRANSDUCER-US-001", "Sonde échographe 3.5MHz", 2800.00),
    ("FILTER-HEPA-001", "Filtre HEPA remplacement", 350.00),
    ("LAMP-SCIALYTIC-001", "Lampe scialytique LED", 1800.00),
    ("MOTOR-PUMP-001", "Moteur pompe aspiration", 800.00),
    ("VALVE-SOLENOID-001", "Vanne solénoïde", 250.00),
    ("CIRCUIT-BOARD-001", "Carte mère remplacement", 1500.00),
    ("POWER-SUPPLY-001", "Alimentation électrique 500W", 600.00),
    ("FAN-COOLING-001", "Ventilateur refroidissement", 180.00),
]

INTERVENTION_TYPES = ["Corrective", "Préventive", "Installation", "Formation", "Dépannage"]
INTERVENTION_STATUSES = ["Terminée", "En cours", "Planifiée", "En attente de piece", "Cloturee"]
PRIORITIES = ["Basse", "Moyenne", "Haute", "Critique"]

TECHNICIEN_SPECIALITES = [
    "Radiologie", "Cardiologie", "Électronique", "Mécanique",
    "Informatique", "Généraliste", "Électricité", "Hydraulique"
]

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def hash_password(password: str) -> str:
    """Hash une password avec bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def random_date(start_days_ago=365, end_days_ago=0):
    """Génère une date aléatoire entre start_days_ago et end_days_ago (gère les plages inversées)."""
    min_days = min(start_days_ago, end_days_ago)
    max_days = max(start_days_ago, end_days_ago)
    days_offset = random.randint(min_days, max_days)
    return (datetime.now() - timedelta(days=days_offset)).date()

def random_datetime(start_days_ago=365, end_days_ago=0):
    """Génère un datetime aléatoire."""
    date = random_date(start_days_ago, end_days_ago)
    hour = random.randint(8, 18)
    minute = random.randint(0, 59)
    return datetime.combine(date, datetime.min.time().replace(hour=hour, minute=minute))

# ==========================================
# SEED FUNCTIONS
# ==========================================

def seed_clients(conn, count=50):
    """Crée 50 clients avec données réalistes."""
    logger.info(f"🏥 Création de {count} clients...")
    
    regions = ["Tunis", "Sfax", "Sousse", "Kairouan", "Gafsa", "Tozeur", "Djerba", "Bizerte", "Nabeul", "Monastir"]
    types_client = ["Hôpital Public", "Hôpital Privé", "Clinique", "Centre Médical", "Laboratoire"]
    
    clients = []
    for i in range(1, count + 1):
        nom = f"Client_{i:03d}"
        if i % 3 == 0:
            nom = f"Hôpital {random.choice(['Central', 'Régional', 'Universitaire', 'Privé'])} {i}"
        elif i % 3 == 1:
            nom = f"Clinique {random.choice(['Al-Amal', 'Essafa', 'Ennasr', 'Zitouna'])} {i}"
        else:
            nom = f"Centre Médical {random.choice(['Nord', 'Sud', 'Est', 'Ouest'])} {i}"
        
        clients.append({
            'nom': nom,
            'matricule_fiscale': f"1{random.randint(100000, 999999)}{i:03d}",
            'ville': random.choice(regions),
            'contact': f"Dr. {random.choice(['Ahmed', 'Fatima', 'Mohamed', 'Leila', 'Karim'])} {random.choice(['Ben', 'El', 'Al'])} {random.choice(['Salah', 'Mansour', 'Karim', 'Nour'])}",
            'telephone': f"+216 {random.randint(20, 99)} {random.randint(100000, 999999)}",
            'adresse': f"{random.randint(1, 500)} Rue {random.choice(['de la Paix', 'de la Liberté', 'de l\'Indépendance', 'Principale'])}",
            'type_client': random.choice(types_client),
            'code_client': f"CLI{i:05d}",
            'region': random.choice(regions),
            'international': random.choice([True, False])
        })
    
    for client in clients:
        try:
            conn.execute(
                """INSERT INTO clients (nom, matricule_fiscale, ville, contact, telephone, adresse, type_client, code_client, region, international)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (client['nom'], client['matricule_fiscale'], client['ville'], client['contact'],
                 client['telephone'], client['adresse'], client['type_client'], client['code_client'],
                 client['region'], client['international'])
            )
        except Exception as e:
            logger.debug(f"Client {client['nom']} déjà existant: {e}")
    
    logger.info(f"✅ {count} clients créés")
    return clients

def seed_equipements(conn, clients, count=100):
    """Crée 100 équipements médicaux."""
    logger.info(f"🏥 Création de {count} équipements...")
    
    equipements = []
    client_names = [c['nom'] for c in clients]
    
    for i in range(1, count + 1):
        domain = random.choice(MEDICAL_DOMAINS)
        equipment_type = random.choice(EQUIPMENT_TYPES_BY_DOMAIN[domain])
        client = random.choice(client_names)
        
        equip = {
            'nom': f"{equipment_type}_{i:03d}",
            'type': equipment_type,
            'fabricant': random.choice(MANUFACTURERS),
            'modele': f"Model-{random.randint(2000, 2024)}-{random.randint(100, 999)}",
            'num_serie': f"SN{random.randint(100000, 999999)}",
            'date_installation': random_date(start_days_ago=1095).isoformat(),
            'derniere_maintenance': random_date(start_days_ago=180).isoformat(),
            'statut': random.choice(['Actif', 'Maintenance', 'Hors service']),
            'client': client,
            'domaine': domain,
            'service': random.choice(['Urgences', 'Chirurgie', 'Consultation', 'Diagnostic']),
            'garantie_debut': random_date(start_days_ago=365).isoformat(),
            'garantie_duree': random.choice([1, 2, 3, 5]),
            'latitude': round(random.uniform(33.0, 37.5), 4),
            'longitude': round(random.uniform(8.0, 11.5), 4),
            'adresse': f"{random.randint(1, 500)} Rue {random.choice(['Principale', 'Médicale', 'de la Santé'])}",
            'ville': random.choice(['Tunis', 'Sfax', 'Sousse', 'Kairouan']),
            'region': random.choice(['Nord', 'Centre', 'Sud']),
        }
        
        equipements.append(equip)
        try:
            conn.execute(
                """INSERT INTO equipements 
                   (nom, type, fabricant, modele, num_serie, date_installation, derniere_maintenance,
                    statut, client, domaine, service, garantie_debut, garantie_duree, latitude, longitude,
                    adresse, ville, region)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (equip['nom'], equip['type'], equip['fabricant'], equip['modele'], equip['num_serie'],
                 equip['date_installation'], equip['derniere_maintenance'], equip['statut'], equip['client'],
                 equip['domaine'], equip['service'], equip['garantie_debut'], equip['garantie_duree'],
                 equip['latitude'], equip['longitude'], equip['adresse'], equip['ville'], equip['region'])
            )
        except Exception as e:
            logger.debug(f"Équipement {equip['nom']} déjà existant: {e}")
    
    logger.info(f"✅ {count} équipements créés")
    return equipements

def seed_techniciens(conn, count=10):
    """Crée 10 techniciens avec comptes utilisateurs."""
    logger.info(f"👨‍🔧 Création de {count} techniciens...")
    
    prenoms = ["Ahmed", "Mohamed", "Karim", "Fatima", "Leila", "Nour", "Salah", "Amira", "Riad", "Zaineb"]
    noms = ["Ben Salah", "El Mansour", "Al Karim", "Ben Nour", "El Amir", "Ben Karim", "Al Salah", "Ben Amir", "El Nour", "Al Mansour"]
    
    techniciens = []
    for i in range(1, count + 1):
        prenom = prenoms[i - 1]
        nom = noms[i - 1]
        username = f"tech_{i:02d}"
        email = f"{username}@savia.local"
        specialite = random.choice(TECHNICIEN_SPECIALITES)
        
        tech = {
            'username': username,
            'nom': nom,
            'prenom': prenom,
            'specialite': specialite,
            'qualification': f"Cert. {specialite}",
            'telephone': f"+216 {random.randint(20, 99)} {random.randint(100000, 999999)}",
            'email': email,
            'dispo': 1,
            'notes': f"Technicien spécialisé en {specialite}",
            'niveau_competence': random.choice(['Junior', 'Confirmé', 'Expert'])
        }
        
        techniciens.append(tech)
        
        # Créer le technicien
        try:
            conn.execute(
                """INSERT INTO techniciens 
                   (username, nom, prenom, specialite, qualification, telephone, email, dispo, notes, niveau_competence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (tech['username'], tech['nom'], tech['prenom'], tech['specialite'], tech['qualification'],
                 tech['telephone'], tech['email'], tech['dispo'], tech['notes'], tech['niveau_competence'])
            )
        except Exception as e:
            logger.debug(f"Technicien {username} déjà existant: {e}")
        
        # Créer le compte utilisateur
        password_hash = hash_password(f"tech_{i:02d}@2026")
        try:
            conn.execute(
                """INSERT INTO utilisateurs 
                   (username, password_hash, nom_complet, role, email, actif)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (username, password_hash, f"{prenom} {nom}", "Technicien", email, 1)
            )
        except Exception as e:
            logger.debug(f"Utilisateur {username} déjà existant: {e}")
    
    logger.info(f"✅ {count} techniciens créés avec comptes utilisateurs")
    return techniciens

def seed_manager(conn):
    """Crée un compte manager."""
    logger.info("👔 Création du compte manager...")
    
    username = "manager"
    email = "manager@savia.local"
    password_hash = hash_password("manager@2026")
    
    try:
        conn.execute(
            """INSERT INTO utilisateurs 
               (username, password_hash, nom_complet, role, email, actif)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (username, password_hash, "Manager SAVIA", "Manager", email, 1)
        )
        logger.info("✅ Compte manager créé (manager / manager@2026)")
    except Exception as e:
        logger.debug(f"Manager déjà existant: {e}")

def seed_interventions(conn, equipements, techniciens, count=200):
    """Crée 200+ interventions simulées."""
    logger.info(f"🔧 Création de {count} interventions...")
    
    equip_names = [e['nom'] for e in equipements]
    tech_usernames = [t['username'] for t in techniciens]
    
    for i in range(1, count + 1):
        intervention = {
            'date': random_datetime(start_days_ago=365),
            'machine': random.choice(equip_names),
            'technicien': random.choice(tech_usernames),
            'type_intervention': random.choice(INTERVENTION_TYPES),
            'description': random.choice([
                "Maintenance préventive régulière",
                "Remplacement de pièces usées",
                "Calibrage et vérification",
                "Nettoyage et désinfection",
                "Réparation suite à panne",
                "Mise à jour logicielle",
                "Formation utilisateur",
                "Inspection de sécurité"
            ]),
            'statut': random.choice(INTERVENTION_STATUSES),
            'priorite': random.choice(PRIORITIES),
            'duree_minutes': random.randint(30, 480),
            'cout': round(random.uniform(100, 2000), 2),
            'cout_pieces': round(random.uniform(0, 1500), 2),
            'notes': f"Intervention #{i:05d}",
        }
        
        try:
            conn.execute(
                """INSERT INTO interventions 
                   (date, machine, technicien, type_intervention, description, statut, priorite, duree_minutes, cout, cout_pieces, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (intervention['date'], intervention['machine'], intervention['technicien'],
                 intervention['type_intervention'], intervention['description'], intervention['statut'],
                 intervention['priorite'], intervention['duree_minutes'], intervention['cout'],
                 intervention['cout_pieces'], intervention['notes'])
            )
        except Exception as e:
            logger.debug(f"Intervention {i} erreur: {e}")
    
    logger.info(f"✅ {count} interventions créées")

def seed_planning(conn, equipements, techniciens, count=50):
    """Crée 50+ plannings de maintenance."""
    logger.info(f"📅 Création de {count} plannings de maintenance...")
    
    equip_names = [e['nom'] for e in equipements]
    tech_usernames = [t['username'] for t in techniciens]
    
    for i in range(1, count + 1):
        date_prevue = random_date(start_days_ago=-180, end_days_ago=-1)  # Futures dates
        
        planning = {
            'machine': random.choice(equip_names),
            'type_maintenance': random.choice(['Préventive', 'Corrective']),
            'description': f"Maintenance planifiée #{i:03d}",
            'date_prevue': date_prevue,
            'technicien_assigne': random.choice(tech_usernames),
            'statut': random.choice(['Planifiée', 'En cours', 'Terminée']),
            'recurrence': random.choice(['Mensuelle', 'Trimestrielle', 'Semestrielle', 'Annuelle']),
        }
        
        try:
            conn.execute(
                """INSERT INTO planning_maintenance 
                   (machine, type_maintenance, description, date_prevue, technicien_assigne, statut, recurrence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (planning['machine'], planning['type_maintenance'], planning['description'],
                 planning['date_prevue'], planning['technicien_assigne'], planning['statut'],
                 planning['recurrence'])
            )
        except Exception as e:
            logger.debug(f"Planning {i} erreur: {e}")
    
    logger.info(f"✅ {count} plannings créés")

def seed_pieces(conn, count=100):
    """Crée 100+ pièces de rechange."""
    logger.info(f"📦 Création de {count} pièces de rechange...")
    
    pieces = []
    for i, (ref, designation, prix) in enumerate(SPARE_PARTS_GENERIC * (count // len(SPARE_PARTS_GENERIC) + 1)):
        if i >= count:
            break
        
        piece = {
            'reference': f"{ref}_{i:03d}",
            'designation': f"{designation} (Var. {i})",
            'equipement_type': random.choice(list(EQUIPMENT_TYPES_BY_DOMAIN.values())[0]),
            'stock_actuel': random.randint(0, 50),
            'stock_minimum': random.randint(2, 10),
            'fournisseur': random.choice(MANUFACTURERS),
            'prix_unitaire': prix + random.uniform(-100, 100),
            'domaine': random.choice(MEDICAL_DOMAINS),
        }
        
        pieces.append(piece)
        try:
            conn.execute(
                """INSERT INTO pieces_rechange 
                   (reference, designation, equipement_type, stock_actuel, stock_minimum, fournisseur, prix_unitaire, domaine)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (piece['reference'], piece['designation'], piece['equipement_type'],
                 piece['stock_actuel'], piece['stock_minimum'], piece['fournisseur'],
                 piece['prix_unitaire'], piece['domaine'])
            )
        except Exception as e:
            logger.debug(f"Pièce {piece['reference']} déjà existante: {e}")
    
    logger.info(f"✅ {count} pièces créées")
    return pieces

def seed_contrats(conn, clients, equipements, count=20):
    """Crée 20+ contrats de maintenance."""
    logger.info(f"📋 Création de {count} contrats de maintenance...")
    
    client_names = [c['nom'] for c in clients]
    equip_names = [e['nom'] for e in equipements]
    
    for i in range(1, count + 1):
        date_debut = random_date(start_days_ago=365)
        date_fin = date_debut + timedelta(days=365)
        
        contrat = {
            'client': random.choice(client_names),
            'equipement': random.choice(equip_names),
            'type_contrat': random.choice(['Maintenance', 'Support', 'Garantie étendue']),
            'date_debut': date_debut,
            'date_fin': date_fin,
            'montant': round(random.uniform(1000, 10000), 2),
            'statut': random.choice(['Actif', 'Expiré', 'Suspendu']),
            'sla_temps_reponse_h': random.choice([4, 8, 24, 48]),
            'recurrence_maintenance': random.choice(['Mensuelle', 'Trimestrielle', 'Semestrielle']),
        }
        
        try:
            conn.execute(
                """INSERT INTO contrats 
                   (client, equipement, type_contrat, date_debut, date_fin, montant, statut, sla_temps_reponse_h, recurrence_maintenance)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (contrat['client'], contrat['equipement'], contrat['type_contrat'],
                 contrat['date_debut'], contrat['date_fin'], contrat['montant'],
                 contrat['statut'], contrat['sla_temps_reponse_h'], contrat['recurrence_maintenance'])
            )
        except Exception as e:
            logger.debug(f"Contrat {i} erreur: {e}")
    
    logger.info(f"✅ {count} contrats créés")

def seed_fabricants(conn):
    """Crée les fabricants."""
    logger.info("🏭 Création des fabricants...")
    
    for fabricant in MANUFACTURERS:
        try:
            conn.execute(
                "INSERT INTO fabricants (nom) VALUES (%s)",
                (fabricant,)
            )
        except Exception as e:
            logger.debug(f"Fabricant {fabricant} déjà existant: {e}")
    
    logger.info(f"✅ {len(MANUFACTURERS)} fabricants créés")

# ==========================================
# MAIN SEEDING FUNCTION
# ==========================================

def seed_all():
    """Lance le seeding complet."""
    logger.info("=" * 60)
    logger.info("🌱 SAVIA DATA SEEDING — Démarrage")
    logger.info("=" * 60)
    
    try:
        # Initialiser la DB
        init_db()
        logger.info("✅ Base de données initialisée")
        
        with get_db() as conn:
            # Seed dans l'ordre des dépendances
            seed_fabricants(conn)
            clients = seed_clients(conn, count=50)
            equipements = seed_equipements(conn, clients, count=100)
            techniciens = seed_techniciens(conn, count=10)
            seed_manager(conn)
            seed_interventions(conn, equipements, techniciens, count=200)
            seed_planning(conn, equipements, techniciens, count=50)
            seed_pieces(conn, count=100)
            seed_contrats(conn, clients, equipements, count=20)
        
        logger.info("=" * 60)
        logger.info("✅ SEEDING COMPLET — Succès!")
        logger.info("=" * 60)
        logger.info("\n📊 Résumé des données créées:")
        logger.info("  • 50 clients")
        logger.info("  • 100 équipements médicaux")
        logger.info("  • 10 techniciens + comptes utilisateurs")
        logger.info("  • 1 compte manager")
        logger.info("  • 200 interventions")
        logger.info("  • 50 plannings de maintenance")
        logger.info("  • 100 pièces de rechange")
        logger.info("  • 20 contrats de maintenance")
        logger.info("\n🔐 Comptes de test:")
        logger.info("  • Manager: manager / manager@2026")
        logger.info("  • Techniciens: tech_01 à tech_10 / tech_XX@2026")
        logger.info("\n🚀 Prêt pour le déploiement!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du seeding: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = seed_all()
    sys.exit(0 if success else 1)