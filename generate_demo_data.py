"""
🏗️ Générateur de données réalistes pour SAVIA SIC Radiologie
=============================================================
Simule un revendeur d'équipements de radiologie avec :
- 50 clients (cliniques, hôpitaux, cabinets)
- 10 techniciens spécialisés
- 100+ équipements de différentes modalités
- 500+ interventions (correctives + préventives)
- Planning de maintenance préventive
- Pièces de rechange avec stocks réalistes
- Contrats de maintenance
"""

import random
import string
import sys
import os
from datetime import datetime, timedelta

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_engine import get_db, init_db

# ============================================================
# 🏥 DONNÉES DE RÉFÉRENCE RÉALISTES
# ============================================================

VILLES_TUNISIE = [
    "Tunis", "Sfax", "Sousse", "Kairouan", "Bizerte", "Gabès", "Ariana",
    "Gafsa", "Monastir", "Ben Arous", "Kasserine", "Médenine", "Nabeul",
    "Tataouine", "Béja", "Jendouba", "Mahdia", "Sidi Bouzid", "Tozeur",
    "Siliana", "Kébili", "Zaghouan", "Manouba", "La Marsa", "Hammamet"
]

TYPES_STRUCTURES = [
    "Clinique", "Centre de Radiologie", "Hôpital", "Cabinet Médical",
    "Polyclinique", "Centre d'Imagerie", "CHU", "Clinique Dentaire"
]

FABRICANTS = {
    "Scanner CT": ["GE Healthcare", "Siemens Healthineers", "Philips", "Canon Medical", "United Imaging"],
    "IRM": ["Siemens Healthineers", "GE Healthcare", "Philips", "Hitachi", "Canon Medical"],
    "Radiographie Numérique (DR)": ["Carestream", "Fujifilm", "Agfa", "Konica Minolta", "Samsung"],
    "Table Télécommandée": ["Shimadzu", "Siemens Healthineers", "Philips", "Villa Sistemi"],
    "Échographe": ["GE Healthcare", "Philips", "Samsung Medison", "Mindray", "Esaote"],
    "Mammographe": ["Hologic", "GE Healthcare", "Siemens Healthineers", "Fujifilm", "Planmed"],
    "Panoramique Dentaire": ["Planmeca", "Carestream", "Vatech", "Dürr Dental", "Acteon"],
    "Cone Beam (CBCT)": ["Planmeca", "Vatech", "Carestream", "KaVo Kerr", "NewTom"],
    "Arceau Chirurgical (C-Arm)": ["Siemens Healthineers", "GE Healthcare", "Philips", "Ziehm", "Hologic"],
    "Ostéodensitomètre": ["Hologic", "GE Healthcare", "Medilink", "Osteosys"],
    "Angiographe": ["Siemens Healthineers", "GE Healthcare", "Philips", "Canon Medical"],
    "Fluoroscopie": ["Shimadzu", "Siemens Healthineers", "GE Healthcare"],
    "Développeuse": ["Kodak", "Agfa", "Konica Minolta"],
    "Imprimante DICOM": ["Sony", "Codonics", "Agfa"],
    "Station PACS/RIS": ["Agfa", "Carestream", "Fujifilm", "Philips"],
    "Injecteur de Contraste": ["Bracco", "Bayer", "Guerbet", "Nemoto"],
    "Générateur HT": ["Sedecal", "CPI", "Spellman", "EMD Technologies"],
    "Capteur Plan": ["Carestream", "Fujifilm", "Trixell", "Varex"],
}

MODELES = {
    "Scanner CT": ["Revolution CT", "SOMATOM Force", "Spectral CT 7500", "Aquilion ONE", "uCT 960+"],
    "IRM": ["MAGNETOM Vida", "SIGNA Premier", "Ingenia Ambition", "Echelon Smart", "Vantage Orian"],
    "Radiographie Numérique (DR)": ["DRX-Evolution Plus", "FDR D-EVO III", "DR 600", "AeroDR HD"],
    "Échographe": ["LOGIQ E10s", "EPIQ Elite", "HS70A", "Resona I9", "MyLab X8"],
    "Mammographe": ["Selenia Dimensions", "Senographe Pristina", "MAMMOMAT Revelation", "Amulet Innovality"],
    "Panoramique Dentaire": ["ProMax 2D", "CS 8200 3D", "PaX-i3D", "VistaPano S"],
    "Cone Beam (CBCT)": ["ProMax 3D Max", "Green CT2", "CS 9600", "OP 3D Pro"],
    "Arceau Chirurgical (C-Arm)": ["Cios Alpha", "OEC 3D", "Zenition 50", "Vision RFD"],
    "Ostéodensitomètre": ["Horizon DXA", "Prodigy Advance", "Osteosys Dexxum"],
    "Injecteur de Contraste": ["CT Expres", "MEDRAD Stellant", "OptiVantage DH"],
}

SPECIALITES_TECH = [
    "Scanner/IRM", "Radiographie Conventionnelle", "Dentaire (OPG/CBCT)",
    "Mammographie", "Échographie", "PACS/RIS/IT", "Généraliste",
    "Angiographie/Interventionnel", "Maintenance Préventive", "Électronique HT"
]

QUALIFICATIONS_TECH = [
    "Ingénieur Biomédical", "Technicien Biomédical Senior",
    "Technicien Biomédical", "Ingénieur Électronique",
    "Technicien IT Médical", "Expert Constructeur"
]

PRENOMS = [
    "Mohamed", "Ahmed", "Ali", "Youssef", "Omar", "Sami", "Karim", "Nabil",
    "Riadh", "Fathi", "Khaled", "Hichem", "Slim", "Bassem", "Walid",
    "Amine", "Bilel", "Hatem", "Taoufik", "Mourad"
]

NOMS_FAMILLE = [
    "Ben Salah", "Trabelsi", "Bouzid", "Jebali", "Gharbi", "Khelifi",
    "Mansouri", "Hammami", "Sassi", "Dridi", "Lahmar", "Mejri",
    "Chaabane", "Rezgui", "Bouazizi", "Ferchichi", "Abidi", "Maalej",
    "Sfaxi", "Tlili"
]

CODES_ERREUR = {
    "Scanner CT": ["E-CT01", "E-CT02", "E-CT03", "E-CT04", "E-CT05", "E-CT06", "E-CT07"],
    "IRM": ["E-MR01", "E-MR02", "E-MR03", "E-MR04", "E-MR05"],
    "Radiographie Numérique (DR)": ["E-DR01", "E-DR02", "E-DR03", "E-DR04"],
    "Mammographe": ["E-MG01", "E-MG02", "E-MG03"],
    "Échographe": ["E-US01", "E-US02", "E-US03"],
    "Panoramique Dentaire": ["E-OPG01", "E-OPG02", "E-OPG03"],
}

PROBLEMES_TYPES = {
    "Scanner CT": [
        ("Tube RX en fin de vie — artefacts sur images", "Usure normale du tube après 150 000 scans", "Remplacement du tube RX et calibration complète"),
        ("Erreur gantry — rotation bloquée", "Roulement principal usé", "Remplacement roulement + lubrification"),
        ("Erreur alimentation — coupure aléatoire", "Condensateur HT défaillant", "Remplacement module HT"),
        ("Bruit anormal pendant rotation", "Frein de parking défectueux", "Ajustement du frein + test rotation"),
        ("Images floues / artéfacts", "Calibration détecteur décalée", "Recalibration Air/Water + fantôme"),
    ],
    "IRM": [
        ("Perte homogénéité champ", "Courant de quench partiel", "Shimming + recalibration bobines"),
        ("Consommation hélium excessive", "Fuite circuit cryogénique", "Réparation joints + recharge hélium"),
        ("Artéfacts de susceptibilité", "Bobine de gradient défaillante", "Remplacement bobine gradient"),
        ("Bruit excessif ventilation", "Filtres ventilation encrassés", "Nettoyage + remplacement filtres"),
    ],
    "Radiographie Numérique (DR)": [
        ("Capteur plan ne démarre pas", "Carte électronique défaillante", "Remplacement carte acquisition"),
        ("Image trop sombre", "Calibration dose incorrecte", "Recalibration AEC + test fantôme"),
        ("Collimateur bloqué", "Moteur collimateur HS", "Remplacement moteur + test lamelle"),
    ],
    "Mammographe": [
        ("Compression insuffisante", "Vérin de compression usé", "Remplacement vérin + calibration force"),
        ("Image avec artefacts", "Grille anti-diffusion endommagée", "Remplacement grille + calibration"),
    ],
    "Échographe": [
        ("Sonde défaillante — image dégradée", "Éléments piézo HS", "Remplacement sonde"),
        ("Écran tactile non réactif", "Dalle tactile endommagée", "Remplacement dalle tactile"),
        ("Gel dans connecteur sonde", "Mauvais entretien", "Nettoyage connecteur + formation utilisateur"),
    ],
    "Panoramique Dentaire": [
        ("Bras panoramique bloqué", "Courroie de transmission usée", "Remplacement courroie + calibration"),
        ("Image panoramique floue", "Capteur mal positionné", "Réalignement capteur + calibration"),
    ],
}

PIECES_PAR_TYPE = {
    "Scanner CT": [
        ("TRX-001", "Tube RX Scanner", 0, 1, "GE Healthcare", 45000.0),
        ("FLT-CT01", "Filtre huile circuit refroidissement", 8, 3, "Mann Filter", 120.0),
        ("BRG-CT01", "Roulement principal gantry", 2, 1, "SKF", 3500.0),
        ("CBL-CT01", "Câble slip-ring", 3, 1, "Stemmann", 2800.0),
        ("DET-CT01", "Module détecteur CT", 1, 1, "Varex", 15000.0),
        ("CAP-CT01", "Condensateur haute tension", 4, 2, "TDK", 850.0),
        ("FAN-CT01", "Ventilateur gantry", 6, 2, "EBM-Papst", 220.0),
    ],
    "IRM": [
        ("BOB-MR01", "Bobine corps entier", 1, 1, "Siemens", 18000.0),
        ("HEL-MR01", "Recharge Hélium (500L)", 2, 1, "Air Liquide", 8500.0),
        ("GRD-MR01", "Module gradient", 1, 1, "Siemens", 25000.0),
        ("FLT-MR01", "Filtre CEM salle IRM", 4, 2, "Schaffner", 380.0),
        ("CRY-MR01", "Compresseur cryogénique", 1, 1, "Sumitomo", 32000.0),
    ],
    "Radiographie Numérique (DR)": [
        ("CPT-DR01", "Capteur plan numérique", 1, 1, "Carestream", 22000.0),
        ("GEN-DR01", "Générateur haute tension", 1, 1, "Sedecal", 8500.0),
        ("COL-DR01", "Collimateur motorisé", 2, 1, "Ralco", 3200.0),
        ("TRX-DR01", "Tube RX radiographie", 1, 1, "Dunlee", 12000.0),
        ("GRI-DR01", "Grille anti-diffusante", 3, 2, "Mitaya", 450.0),
    ],
    "Mammographe": [
        ("TRX-MG01", "Tube RX mammographie Mo/Rh", 1, 1, "Hologic", 28000.0),
        ("PAD-MG01", "Palette compression standard", 4, 2, "Hologic", 380.0),
        ("VER-MG01", "Vérin compression", 2, 1, "SMC", 1200.0),
        ("DET-MG01", "Détecteur mammographie", 1, 1, "Hologic", 35000.0),
    ],
    "Échographe": [
        ("SND-US01", "Sonde convexe C5-1", 2, 1, "Philips", 8500.0),
        ("SND-US02", "Sonde linéaire L12-3", 2, 1, "Philips", 7200.0),
        ("SND-US03", "Sonde endocavitaire", 1, 1, "Philips", 6800.0),
        ("ECR-US01", "Écran LCD 21 pouces", 1, 1, "Sony", 1800.0),
        ("IMP-US01", "Imprimante thermique", 3, 2, "Sony", 650.0),
    ],
    "Panoramique Dentaire": [
        ("CPT-OPG01", "Capteur panoramique", 1, 1, "Planmeca", 12000.0),
        ("CRR-OPG01", "Courroie transmission bras", 4, 2, "Gates", 85.0),
        ("MOT-OPG01", "Moteur pas-à-pas bras", 2, 1, "Oriental Motor", 420.0),
        ("MEN-OPG01", "Mentonnière patient", 8, 3, "Planmeca", 45.0),
    ],
    "Cone Beam (CBCT)": [
        ("CPT-CB01", "Capteur CBCT", 1, 1, "Vatech", 18000.0),
        ("TRX-CB01", "Tube RX CBCT", 1, 1, "Toshiba", 15000.0),
    ],
    "Arceau Chirurgical (C-Arm)": [
        ("TRX-CA01", "Tube RX C-Arm", 1, 1, "Thales", 18000.0),
        ("INT-CA01", "Intensificateur image", 1, 1, "Siemens", 22000.0),
        ("FRN-CA01", "Frein électromagnétique", 2, 1, "Mayr", 680.0),
    ],
    "Injecteur de Contraste": [
        ("SER-INJ01", "Seringue 200ml", 50, 20, "Bracco", 35.0),
        ("TUB-INJ01", "Tubulure haute pression", 30, 15, "Bracco", 28.0),
        ("TET-INJ01", "Tête d'injection", 2, 1, "Bracco", 4500.0),
    ],
}

FOURNISSEURS = [
    "MedTech Tunisia", "BioMed Solutions", "RadioParts SARL",
    "GE Healthcare Direct", "Siemens Service", "Philips Parts Center",
    "EuroMed Équipements", "MedEquip Maghreb", "TechnoMed Tunisie",
    "DicomParts International"
]


# ============================================================
# 🔧 FONCTIONS DE GÉNÉRATION
# ============================================================

def generate_serial():
    """Génère un numéro de série réaliste."""
    prefix = random.choice(["SN", "S/N", ""])
    numbers = ''.join(random.choices(string.digits, k=random.randint(6, 10)))
    letters = ''.join(random.choices(string.ascii_uppercase, k=2))
    return f"{prefix}{letters}{numbers}"


def generate_clients(n=50):
    """Génère n clients réalistes."""
    clients = []
    used = set()
    for i in range(n):
        ville = random.choice(VILLES_TUNISIE)
        type_struct = random.choice(TYPES_STRUCTURES)
        
        # Noms réalistes
        noms_possibles = [
            f"{type_struct} {ville}",
            f"{type_struct} El {random.choice(['Amal', 'Nour', 'Amen', 'Safa', 'Razi', 'Ibn Sina', 'Essalama', 'El Manar', 'El Omrane'])}",
            f"{type_struct} Les {random.choice(['Oliviers', 'Jasmins', 'Palmiers', 'Roses'])}",
            f"{type_struct} {random.choice(['International', 'Moderne', 'Spécialisé', 'Privé'])} {ville}",
            f"Dr. {random.choice(NOMS_FAMILLE)} — {type_struct}",
        ]
        nom = random.choice(noms_possibles)
        while nom in used:
            nom = f"{nom} {random.randint(2,5)}"
        used.add(nom)
        clients.append(nom)
    return clients


def generate_techniciens(n=10):
    """Génère n techniciens avec profils réalistes."""
    techs = []
    used_names = set()
    for i in range(n):
        prenom = random.choice(PRENOMS)
        nom = random.choice(NOMS_FAMILLE)
        while (prenom, nom) in used_names:
            prenom = random.choice(PRENOMS)
            nom = random.choice(NOMS_FAMILLE)
        used_names.add((prenom, nom))
        
        specialite = SPECIALITES_TECH[i % len(SPECIALITES_TECH)]
        qualification = random.choice(QUALIFICATIONS_TECH)
        telephone = f"+216 {random.randint(20,99)} {random.randint(100,999)} {random.randint(100,999)}"
        email = f"{prenom.lower()}.{nom.lower().replace(' ', '')}@savia-med.tn"
        username = f"{prenom.lower()}{nom.split()[0].lower()[:3]}"
        
        techs.append({
            "nom": nom,
            "prenom": prenom,
            "specialite": specialite,
            "qualification": qualification,
            "telephone": telephone,
            "email": email,
            "username": username,
        })
    return techs


def generate_equipements(clients, n=100):
    """Génère n équipements répartis sur les clients."""
    equipements = []
    used = set()
    
    # Distribution réaliste : gros clients ont plus d'équipements
    types_communs = [
        "Radiographie Numérique (DR)", "Échographe", "Panoramique Dentaire",
        "Scanner CT", "Mammographe", "Table Télécommandée"
    ]
    types_rares = [
        "IRM", "Angiographe", "Cone Beam (CBCT)", "Arceau Chirurgical (C-Arm)",
        "Ostéodensitomètre", "Fluoroscopie", "Injecteur de Contraste",
        "Imprimante DICOM", "Station PACS/RIS", "Générateur HT", "Capteur Plan"
    ]
    
    for i in range(n):
        client = random.choice(clients)
        
        # Les petits cabinets ont surtout des équipements communs
        if random.random() < 0.7:
            eq_type = random.choice(types_communs)
        else:
            eq_type = random.choice(types_rares)
        
        fabricant = random.choice(FABRICANTS.get(eq_type, ["Autre"]))
        modeles_list = MODELES.get(eq_type, [f"Model {random.randint(100,999)}"])
        modele = random.choice(modeles_list)
        
        # Nom unique par client
        base_nom = f"{eq_type.split('(')[0].strip()} {fabricant.split()[0]}"
        nom = base_nom
        suffix = 1
        while (nom, client) in used:
            suffix += 1
            nom = f"{base_nom} #{suffix}"
        used.add((nom, client))
        
        # Date d'installation : entre 2015 et 2025
        days_ago = random.randint(30, 3650)
        date_install = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        
        # Dernière maintenance : dans les 12 derniers mois
        derniere_maint = (datetime.now() - timedelta(days=random.randint(0, 365))).strftime("%Y-%m-%d")
        
        statut = random.choices(["Actif", "En panne", "En maintenance"], weights=[85, 10, 5])[0]
        
        equipements.append({
            "nom": nom,
            "type": eq_type,
            "fabricant": fabricant,
            "modele": modele,
            "num_serie": generate_serial(),
            "date_installation": date_install,
            "derniere_maintenance": derniere_maint,
            "statut": statut,
            "notes": "",
            "client": client,
        })
    
    return equipements


def generate_interventions(equipements, techniciens, n=500):
    """Génère n interventions réalistes."""
    interventions = []
    
    for i in range(n):
        equip = random.choice(equipements)
        tech = random.choice(techniciens)
        tech_name = f"{tech['prenom']} {tech['nom']}"
        
        # Type d'intervention
        type_interv = random.choices(
            ["Corrective", "Préventive", "Installation", "Calibration"],
            weights=[50, 30, 5, 15]
        )[0]
        
        # Date : sur les 2 dernières années
        days_ago = random.randint(0, 730)
        date = (datetime.now() - timedelta(days=days_ago, hours=random.randint(8, 17), minutes=random.randint(0, 59)))
        
        # Problème/cause/solution réalistes
        eq_type = equip["type"]
        problemes = PROBLEMES_TYPES.get(eq_type, [
            ("Dysfonctionnement général", "Usure composant", "Remplacement composant"),
            ("Erreur système", "Bug firmware", "Mise à jour firmware"),
            ("Bruit anormal", "Pièce mécanique usée", "Remplacement pièce"),
        ])
        probleme_data = random.choice(problemes)
        
        # Code erreur (30% des interventions correctives)
        code_erreur = ""
        if type_interv == "Corrective" and random.random() < 0.3:
            codes = CODES_ERREUR.get(eq_type, [f"E-GEN{random.randint(1,9):02d}"])
            code_erreur = random.choice(codes)
        
        # Durée réaliste (en minutes)
        if type_interv == "Préventive":
            duree = random.randint(60, 240)
            description = f"Maintenance préventive — inspection et calibration {equip['type']}"
            probleme = ""
            cause = ""
            solution = f"Contrôle complet effectué : nettoyage, calibration, test qualité image"
        elif type_interv == "Calibration":
            duree = random.randint(30, 120)
            description = f"Calibration périodique {equip['type']}"
            probleme = ""
            cause = ""
            solution = "Calibration effectuée selon protocole constructeur"
        else:
            duree = random.randint(30, 480)
            description = probleme_data[0]
            probleme = probleme_data[0]
            cause = probleme_data[1]
            solution = probleme_data[2]
        
        # Statut
        if days_ago > 7:
            statut = random.choices(["Terminée", "Clôturée"], weights=[40, 60])[0]
        else:
            statut = random.choices(["En cours", "Assignée", "Terminée", "Clôturée"], weights=[15, 10, 30, 45])[0]
        
        # Coût
        cout = round(random.uniform(50, 5000), 2) if type_interv == "Corrective" else round(random.uniform(50, 500), 2)
        
        # Pièces utilisées
        pieces_type = PIECES_PAR_TYPE.get(eq_type, [])
        pieces_used = ""
        if pieces_type and type_interv == "Corrective" and random.random() < 0.4:
            nb_pieces = random.randint(1, min(3, len(pieces_type)))
            selected = random.sample(pieces_type, nb_pieces)
            pieces_used = ", ".join([p[0] for p in selected])
        
        type_erreur = random.choice(["Hardware", "Software", "Calibration", "Power", "Thermal", ""]) if type_interv == "Corrective" else ""
        priorite = random.choice(["Haute", "Moyenne", "Basse", ""]) if type_interv == "Corrective" else ""
        
        interventions.append({
            "date": date.strftime("%Y-%m-%d %H:%M:%S"),
            "machine": equip["nom"],
            "technicien": tech_name,
            "type_intervention": type_interv,
            "description": description,
            "probleme": probleme,
            "cause": cause,
            "solution": solution,
            "pieces_utilisees": pieces_used,
            "cout": cout,
            "duree_minutes": duree,
            "code_erreur": code_erreur,
            "statut": statut,
            "notes": f"[{equip['client']}]",
            "type_erreur": type_erreur,
            "priorite": priorite,
        })
    
    return interventions


def generate_planning(equipements, techniciens, n=150):
    """Génère n entrées de planning de maintenance préventive."""
    plannings = []
    
    for i in range(n):
        equip = random.choice(equipements)
        tech = random.choice(techniciens)
        tech_name = f"{tech['prenom']} {tech['nom']}"
        
        # Dates : passé, présent, futur
        days_offset = random.randint(-90, 180)
        date_prevue = (datetime.now() + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        
        if days_offset < -7:
            statut = random.choices(["Terminée", "En retard"], weights=[80, 20])[0]
            date_realisee = (datetime.now() + timedelta(days=days_offset + random.randint(0, 5))).strftime("%Y-%m-%d") if statut == "Terminée" else None
        elif days_offset < 0:
            statut = random.choices(["En cours", "En retard"], weights=[60, 40])[0]
            date_realisee = None
        else:
            statut = "Planifiée"
            date_realisee = None
        
        descriptions = [
            f"MP trimestrielle — {equip['type']}",
            f"Contrôle qualité annuel — {equip['fabricant']} {equip['modele']}",
            f"Inspection sécurité — {equip['type']}",
            f"Calibration périodique — {equip['nom']}",
            f"Vérification dosimétrique — {equip['type']}",
            f"Nettoyage et maintenance préventive — {equip['nom']}",
        ]
        
        recurrence = random.choice(["Mensuelle", "Trimestrielle", "Semestrielle", "Annuelle", ""])
        
        plannings.append({
            "machine": equip["nom"],
            "client": equip["client"],
            "type_maintenance": "Préventive",
            "description": random.choice(descriptions),
            "date_prevue": date_prevue,
            "date_realisee": date_realisee,
            "technicien_assigne": tech_name,
            "statut": statut,
            "recurrence": recurrence,
            "notes": "",
        })
    
    return plannings


def generate_pieces():
    """Génère toutes les pièces de rechange avec stocks réalistes."""
    pieces = []
    for eq_type, parts in PIECES_PAR_TYPE.items():
        for ref, designation, stock, stock_min, fournisseur, prix in parts:
            # Varier le stock réaliste
            stock_actuel = max(0, stock + random.randint(-2, 3))
            pieces.append({
                "reference": ref,
                "designation": designation,
                "equipement_type": eq_type,
                "stock_actuel": stock_actuel,
                "stock_minimum": stock_min,
                "fournisseur": fournisseur,
                "prix_unitaire": prix,
                "derniere_commande": (datetime.now() - timedelta(days=random.randint(0, 180))).strftime("%Y-%m-%d"),
                "notes": "",
            })
    return pieces


# ============================================================
# 💾 INSERTION EN BASE
# ============================================================

def insert_data():
    """Insère toutes les données dans la base."""
    print("🏗️  Génération des données réalistes SAVIA SIC Radiologie")
    print("=" * 60)
    
    # Initialiser la base
    init_db()
    
    # Générer les données
    print("\n📊 Génération des données...")
    clients = generate_clients(50)
    print(f"  ✅ {len(clients)} clients générés")
    
    techniciens = generate_techniciens(10)
    print(f"  ✅ {len(techniciens)} techniciens générés")
    
    equipements = generate_equipements(clients, 100)
    print(f"  ✅ {len(equipements)} équipements générés")
    
    interventions = generate_interventions(equipements, techniciens, 500)
    print(f"  ✅ {len(interventions)} interventions générées")
    
    plannings = generate_planning(equipements, techniciens, 150)
    print(f"  ✅ {len(plannings)} plannings générés")
    
    pieces = generate_pieces()
    print(f"  ✅ {len(pieces)} pièces de rechange générées")
    
    # Insérer en base
    print("\n💾 Insertion en base de données...")
    
    with get_db() as conn:
        # Techniciens
        for t in techniciens:
            try:
                conn.execute("""
                    INSERT INTO techniciens (nom, prenom, specialite, qualification, telephone, email, username)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (t["nom"], t["prenom"], t["specialite"], t["qualification"],
                      t["telephone"], t["email"], t["username"]))
            except Exception:
                pass
        print(f"  ✅ Techniciens insérés")
        
        # Équipements
        for e in equipements:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO equipements (nom, type, fabricant, modele, num_serie,
                        date_installation, derniere_maintenance, statut, notes, client)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (e["nom"], e["type"], e["fabricant"], e["modele"], e["num_serie"],
                      e["date_installation"], e["derniere_maintenance"], e["statut"],
                      e["notes"], e["client"]))
            except Exception:
                pass
        print(f"  ✅ Équipements insérés")
        
        # Interventions
        for interv in interventions:
            try:
                conn.execute("""
                    INSERT INTO interventions (date, machine, technicien, type_intervention,
                        description, probleme, cause, solution, pieces_utilisees,
                        cout, duree_minutes, code_erreur, statut, notes, type_erreur, priorite)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (interv["date"], interv["machine"], interv["technicien"],
                      interv["type_intervention"], interv["description"],
                      interv["probleme"], interv["cause"], interv["solution"],
                      interv["pieces_utilisees"], interv["cout"],
                      interv["duree_minutes"], interv["code_erreur"],
                      interv["statut"], interv["notes"],
                      interv["type_erreur"], interv["priorite"]))
            except Exception:
                pass
        print(f"  ✅ Interventions insérées")
        
        # Planning
        for p in plannings:
            try:
                conn.execute("""
                    INSERT INTO planning_maintenance (machine, client, type_maintenance,
                        description, date_prevue, date_realisee, technicien_assigne,
                        statut, recurrence, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (p["machine"], p["client"], p["type_maintenance"],
                      p["description"], p["date_prevue"], p["date_realisee"],
                      p["technicien_assigne"], p["statut"], p["recurrence"],
                      p["notes"]))
            except Exception:
                pass
        print(f"  ✅ Planning insérés")
        
        # Pièces de rechange
        for pc in pieces:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO pieces_rechange (reference, designation, equipement_type,
                        stock_actuel, stock_minimum, fournisseur, prix_unitaire,
                        derniere_commande, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (pc["reference"], pc["designation"], pc["equipement_type"],
                      pc["stock_actuel"], pc["stock_minimum"], pc["fournisseur"],
                      pc["prix_unitaire"], pc["derniere_commande"], pc["notes"]))
            except Exception:
                pass
        print(f"  ✅ Pièces de rechange insérées")
    
    print("\n" + "=" * 60)
    print("🎉 Données réalistes générées avec succès !")
    print(f"""
📈 Résumé :
   • {len(clients)} clients (cliniques, hôpitaux, cabinets)
   • {len(techniciens)} techniciens spécialisés
   • {len(equipements)} équipements de radiologie
   • {len(interventions)} interventions (correctives + préventives)
   • {len(plannings)} maintenances planifiées
   • {len(pieces)} références de pièces de rechange
""")


if __name__ == "__main__":
    insert_data()
