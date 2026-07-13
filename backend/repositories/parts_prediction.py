"""Spare-part parameter calculation and order prediction persistence."""

from database.core import _trigger_backup, get_db, logger, read_sql

__all__ = [
    "get_data_collection_period",
    "calculate_piece_parameters",
    "update_piece_parameters_batch",
    "predict_commande_date",
    "predict_pieces_a_commander",
    "get_ai_pieces_context",
]

# ============================================================================
# 🚀 ADVANCED SPARE PARTS PREDICTION ENGINE
# ============================================================================
# Predicts optimal purchase date using multi-factor analysis:
# - Consumption frequency (actual usage patterns)
# - Supplier lead time
# - Part criticality (system impact)
# - Equipment count dependency
# - Financial optimization
# ============================================================================

from datetime import datetime, timedelta
import json

def get_data_collection_period(piece_reference: str) -> tuple:
    """
    Détermine la période d'historique à utiliser pour le calcul.
    
    Logique :
    - Si pièce < 12 mois d'historique → utiliser 6 mois
    - Si pièce >= 12 mois d'historique → utiliser 12 mois
    
    Returns:
        tuple: (months_to_use, first_usage_date, age_in_months)
    """
    try:
        with get_db() as conn:
            # Chercher la première utilisation de cette pièce
            result = conn.execute("""
                SELECT MIN(date) as first_date
                FROM interventions
                WHERE pieces_utilisees LIKE %s
                    OR pieces_utilisees LIKE %s
            """, (f'%"{piece_reference}"%', f'%{piece_reference}%')).fetchone()
            
            first_usage = result['first_date'] if result and result['first_date'] else None
            
            if not first_usage:
                # Pièce jamais utilisée
                return (6, None, 0)
            
            # Convertir en date si c'est une string
            if isinstance(first_usage, str):
                first_usage = datetime.fromisoformat(first_usage.replace('Z', '+00:00')).date()
            elif isinstance(first_usage, datetime):
                first_usage = first_usage.date()
            
            today = datetime.now().date()
            age_days = (today - first_usage).days
            age_months = age_days / 30.0
            
            # Décision : 6 ou 12 mois
            months_to_use = 12 if age_months >= 12 else 6
            
            return (months_to_use, first_usage, age_months)
    except Exception as e:
        logger.error(f"Erreur get_data_collection_period pour {piece_reference}: {e}")
        return (6, None, 0)


def calculate_piece_parameters(piece_reference: str, equipement_type: str = "") -> dict:
    """
    Calcule automatiquement les paramètres de prédiction basés sur l'historique.
    
    Returns:
        dict: {
            'consommation_moyenne_mois': float,
            'nombre_equipements_relies': int,
            'utilisation_recente_30j': int,
            'data_confidence': str ('HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT'),
            'details': dict
        }
    """
    try:
        with get_db() as conn:
            # Déterminer la période d'historique
            months, first_usage, age_months = get_data_collection_period(piece_reference)
            cutoff_date = datetime.now().date() - timedelta(days=months*30)
            
            # --- CALCUL 1: Consommation moyenne mensuelle ---
            result = conn.execute("""
                SELECT COUNT(*) as total_utilisations
                FROM interventions
                WHERE (pieces_utilisees LIKE %s OR pieces_utilisees LIKE %s)
                    AND date >= %s
            """, (f'%"{piece_reference}"%', f'%{piece_reference}%', cutoff_date)).fetchone()
            
            total_uses = result['total_utilisations'] if result else 0
            consommation_moyenne_mois = (total_uses / months) if months > 0 else 0
            
            # --- CALCUL 2: Utilisation récente 30 jours ---
            cutoff_30j = datetime.now().date() - timedelta(days=30)
            result = conn.execute("""
                SELECT COUNT(*) as recent_uses
                FROM interventions
                WHERE (pieces_utilisees LIKE %s OR pieces_utilisees LIKE %s)
                    AND date >= %s
            """, (f'%"{piece_reference}"%', f'%{piece_reference}%', cutoff_30j)).fetchone()
            
            utilisation_recente_30j = result['recent_uses'] if result else 0
            
            # --- CALCUL 3: Nombre d'équipements reliés ---
            nombre_equipements = 0
            if equipement_type:
                result = conn.execute("""
                    SELECT COUNT(DISTINCT id) as count
                    FROM equipements
                    WHERE type = %s
                """, (equipement_type,)).fetchone()
                nombre_equipements = result['count'] if result else 0
            
            # --- CALCUL 4: Déterminer le niveau de confiance ---
            if total_uses == 0 or age_months < 3:
                data_confidence = 'INSUFFICIENT'
            elif age_months < 6:
                data_confidence = 'LOW'
            elif age_months < 12:
                data_confidence = 'MEDIUM'
            else:
                data_confidence = 'HIGH'
            
            return {
                'consommation_moyenne_mois': round(consommation_moyenne_mois, 2),
                'nombre_equipements_relies': max(1, nombre_equipements),
                'utilisation_recente_30j': utilisation_recente_30j,
                'data_confidence': data_confidence,
                'details': {
                    'historique_mois': months,
                    'premiere_utilisation': str(first_usage) if first_usage else None,
                    'age_mois': round(age_months, 1),
                    'total_utilisations': total_uses,
                    'cutoff_date': str(cutoff_date)
                }
            }
    except Exception as e:
        logger.error(f"Erreur calculate_piece_parameters pour {piece_reference}: {e}")
        return {
            'consommation_moyenne_mois': 1.0,
            'nombre_equipements_relies': 1,
            'utilisation_recente_30j': 0,
            'data_confidence': 'INSUFFICIENT',
            'details': {'error': str(e)}
        }


def update_piece_parameters_batch() -> dict:
    """
    Met à jour automatiquement les paramètres de toutes les pièces.
    À exécuter chaque nuit par un daemon.
    
    Returns:
        dict: Statistiques de mise à jour
    """
    try:
        with get_db() as conn:
            pieces = conn.execute("""
                SELECT id, reference, equipement_type
                FROM pieces_rechange
                ORDER BY designation
            """).fetchall()
            
            updated = 0
            failed = 0
            
            for piece in pieces:
                try:
                    params = calculate_piece_parameters(
                        piece['reference'],
                        piece['equipement_type']
                    )
                    
                    conn.execute("""
                        UPDATE pieces_rechange
                        SET consommation_moyenne_mois = %s,
                            nombre_equipements_relies = %s,
                            utilisation_recente_30j = %s,
                            data_confidence = %s
                        WHERE id = %s
                    """, (
                        params['consommation_moyenne_mois'],
                        params['nombre_equipements_relies'],
                        params['utilisation_recente_30j'],
                        params['data_confidence'],
                        piece['id']
                    ))
                    updated += 1
                except Exception as e:
                    logger.error(f"Erreur mise à jour pièce {piece['reference']}: {e}")
                    failed += 1
            
            conn.commit()
            _trigger_backup()
            
            return {
                'success': True,
                'updated': updated,
                'failed': failed,
                'total': len(pieces)
            }
    except Exception as e:
        logger.error(f"Erreur update_piece_parameters_batch: {e}")
        return {
            'success': False,
            'error': str(e)
        }


    consomm_mois = max(0.1, piece_data.get('consommation_moyenne_mois', 1))
    lead_time_jours = max(7, min(30, piece_data.get('delai_fournisseur_jours', 14)))
    criticite = piece_data.get('criticite', 'NORMAL').upper()
    cout = piece_data.get('prix_unitaire', 0)
    nb_equipements = max(1, piece_data.get('nombre_equipements_relies', 1))
    utilisation_recente = max(0, piece_data.get('utilisation_recente_30j', 0))
    
    # --- VALIDATION DES PARAMÈTRES ---
    if criticite not in ('CRITIQUE', 'NORMAL', 'BAS'):
        criticite = 'NORMAL'
    
    # ─────────────────────────────────────────────────────────────
    # CALCUL 1: PRÉDICTION DE RUPTURE BASÉE SUR LA CONSOMMATION
    # ─────────────────────────────────────────────────────────────
    
    if stock == 0:
        # Stock épuisé = COMMANDER MAINTENANT
        jours_avant_rupture = 0
        date_rupture = today
        urgence = 'CRITIQUE'
        raison = '🔴 Stock = 0'
    elif stock <= mini:
        # Stock ≤ minimum = Commander dans 3 jours
        jours_avant_rupture = 3
        date_rupture = today + timedelta(days=3)
        urgence = 'CRITIQUE'
        raison = f'🟠 Stock ≤ minimum ({stock} ≤ {mini})'
    else:
        # Stock > minimum: Calculer basé sur consommation
        if consomm_mois > 0:
            # jours_avant_rupture = (stock - mini) / (consomm_mois / 30)
            jours_avant_rupture = ((stock - mini) / consomm_mois) * 30
            date_rupture = today + timedelta(days=jours_avant_rupture)
        else:
            # Pas de consommation historique: utiliser l'ancienne logique
            marge = stock - mini
            if marge <= 2:
                jours_avant_rupture = 14
                urgence = 'HAUTE'
            elif marge <= 5:
                jours_avant_rupture = 30
                urgence = 'NORMALE'
            else:
                jours_avant_rupture = 60
                urgence = 'BASSE'
            date_rupture = today + timedelta(days=jours_avant_rupture)
            raison = f'📊 Marge stock: {marge} unités'
    
    # ─────────────────────────────────────────────────────────────
    # CALCUL 2: CALCUL DE LA DATE DE COMMANDE (avec lead time)
    # ─────────────────────────────────────────────────────────────
    
    # Commander AVANT rupture: rupture_date - lead_time
    date_commande = date_rupture - timedelta(days=lead_time_jours)
    
    # ─────────────────────────────────────────────────────────────
    # CALCUL 3: AJUSTEMENT CRITICITÉ (±30%)
    # ─────────────────────────────────────────────────────────────
    
    coefficient_criticite = 1.0
    if criticite == 'CRITIQUE':
        # Pièces critiques: commande 30% plus tôt (augmente lead time)
        coefficient_criticite = 1.3
        date_commande -= timedelta(days=lead_time_jours * 0.3)
    elif criticite == 'BAS':
        # Pièces non-critiques: peut attendre 20% plus longtemps
        coefficient_criticite = 0.8
        date_commande += timedelta(days=lead_time_jours * 0.2)
    
    # ─────────────────────────────────────────────────────────────
    # CALCUL 4: AJUSTEMENT NOMBRE D'ÉQUIPEMENTS RELIÉS
    # ─────────────────────────────────────────────────────────────
    # Plus il y a d'équipements dépendants, plus on commande tôt
    
    facteur_equipements = 1.0
    if nb_equipements >= 3:
        # Beaucoup d'équipements dépendants: commande 15% plus tôt
        facteur_equipements = 1.15
        date_commande -= timedelta(days=lead_time_jours * 0.15)
    elif nb_equipements >= 2:
        facteur_equipements = 1.1
        date_commande -= timedelta(days=lead_time_jours * 0.1)
    
    # ─────────────────────────────────────────────────────────────
    # CALCUL 5: OPTIMISATION FINANCIÈRE (Stock buffer)
    # ─────────────────────────────────────────────────────────────
    # Pièces chères: garder plus de stock (risque si rupture)
    # Pièces bon marché: moins de stock (coût de stockage réduit)
    
    if cout > 5000:  # Pièces très chères (>5000 TND)
        buffer_jours = lead_time_jours * 1.5
        date_commande -= timedelta(days=buffer_jours)
        raison = f"💰 Pièce très chère ({cout:.0f} TND): stock élevé requis"
    elif cout > 1000:  # Pièces chères (>1000 TND)
        buffer_jours = lead_time_jours * 1.2
        date_commande -= timedelta(days=buffer_jours)
        raison = f"💵 Pièce chère ({cout:.0f} TND): stock augmenté"
    elif cout < 100:  # Pièces bon marché (<100 TND)
        buffer_jours = lead_time_jours * 0.5
        date_commande += timedelta(days=buffer_jours)
        raison = f"💲 Pièce bon marché ({cout:.0f} TND): délai flexible"
    
    # ─────────────────────────────────────────────────────────────
    # CALCUL 6: UTILISATION RÉCENTE (Early warning)
    # ─────────────────────────────────────────────────────────────
    # Si beaucoup d'utilisations récentes: pièce en hausse
    
    if utilisation_recente >= 5:
        # Consommation élevée ces 30 derniers jours
        tendance_coeff = 1.2
        date_commande -= timedelta(days=lead_time_jours * 0.2)
        raison = f"📈 Consommation haute ces 30j: {utilisation_recente} utilisations"
    elif utilisation_recente >= 3:
        tendance_coeff = 1.1
        date_commande -= timedelta(days=lead_time_jours * 0.1)
    else:
        tendance_coeff = 1.0
    
    # ─────────────────────────────────────────────────────────────
    # CALCUL 7: SÉCURITÉ - Ne pas commander dans le passé
    # ─────────────────────────────────────────────────────────────
    
    if date_commande < today:
        date_commande = today
        raison = '🚨 COMMANDE IMMÉDIATE NÉCESSAIRE'
        if urgence != 'CRITIQUE':
            urgence = 'CRITIQUE'
    
    # ─────────────────────────────────────────────────────────────
    # DÉFINITION DE L'URGENCE (si pas déjà définie)
    # ─────────────────────────────────────────────────────────────
    
    jours_jusqua_commande = (date_commande - today).days
    
    if urgence is None:
        if jours_jusqua_commande <= 3:
            urgence = 'CRITIQUE'
        elif jours_jusqua_commande <= 14:
            urgence = 'HAUTE'
        elif jours_jusqua_commande <= 30:
            urgence = 'NORMALE'
        else:
            urgence = 'BASSE'
    
    # ─────────────────────────────────────────────────────────────
    # RÉSUMÉ ET RETOUR
    # ─────────────────────────────────────────────────────────────
    
    return {
        'date_commande': date_commande,
        'date_rupture_prevue': date_rupture,
        'raison': raison or f"Consommation: {consomm_mois:.1f} pcs/mois",
        'urgence': urgence,
        'jours_avant_rupture': round(jours_avant_rupture, 1),
        'jours_jusqua_commande': jours_jusqua_commande,
        'stock_previsionnel_jours': round(((stock - mini) / consomm_mois) * 30, 1) if consomm_mois > 0 else 0,
        'facteur_equipements': round(facteur_equipements, 2),
        'coefficient_criticite': round(coefficient_criticite, 2),
        'tendance_consommation': 'HAUSSE' if utilisation_recente >= 3 else 'NORMALE' if utilisation_recente >= 1 else 'BASSE',
        'details': {
            'stock_actuel': stock,
            'stock_minimum': mini,
            'consommation_mois': round(consomm_mois, 2),
            'lead_time_jours': lead_time_jours,
            'criticite': criticite,
            'nombre_equipements': nb_equipements,
            'utilisation_30j': utilisation_recente,
            'prix_unitaire': round(cout, 2)
        }
    }


def predict_commande_date(piece_data: dict) -> dict:
    """
    Advanced prediction with automatic data sufficiency check.
    Returns prediction ONLY if data is reliable.
    
    ⚠️ Returns date_commande=None if data INSUFFICIENT!
    """
    today = datetime.now().date()
    
    # Extract parameters
    stock = max(0, piece_data.get('stock_actuel', 0))
    mini = max(1, piece_data.get('stock_minimum', 1))
    consomm_mois = max(0.1, piece_data.get('consommation_moyenne_mois', 1))
    lead_time_jours = max(7, min(30, piece_data.get('delai_fournisseur_jours', 14)))
    criticite = piece_data.get('criticite', 'NORMAL').upper()
    cout = piece_data.get('prix_unitaire', 0)
    nb_equipements = max(1, piece_data.get('nombre_equipements_relies', 1))
    utilisation_recente = max(0, piece_data.get('utilisation_recente_30j', 0))
    data_confidence = piece_data.get('data_confidence', 'INSUFFICIENT')
    
    # Validate
    if criticite not in ('CRITIQUE', 'NORMAL', 'BAS'):
        criticite = 'NORMAL'
    
    # === SAFETY CHECK: INSUFFICIENT DATA ===
    if data_confidence in ('INSUFFICIENT', 'LOW'):
        return {
            'date_commande': None,
            'urgence': 'UNKNOWN',
            'raison': 'Donnees insuffisantes - Historique requis: minimum 3 mois',
            'prediction_available': False,
            'conseil': 'Attendre accumulation donnees avant prediction',
            'details': {
                'stock_actuel': stock,
                'data_confidence': data_confidence
            }
        }
    
    if utilisation_recente == 0 and consomm_mois < 0.01:
        return {
            'date_commande': None,
            'urgence': 'UNKNOWN',
            'raison': 'Piece jamais utilisee dans historique',
            'prediction_available': False,
            'conseil': 'Aucun historique d\'utilisation trouve',
            'details': {'utilisation_recente_30j': utilisation_recente}
        }
    
    # === CALCULATION PHASE ===
    urgence = None
    raison = None
    
    if stock == 0:
        jours_avant_rupture = 0
        date_rupture = today
        urgence = 'CRITIQUE'
        raison = 'Stock = 0'
    elif stock <= mini:
        jours_avant_rupture = 3
        date_rupture = today + timedelta(days=3)
        urgence = 'CRITIQUE'
        raison = f'Stock <= minimum ({stock} <= {mini})'
    else:
        if consomm_mois > 0:
            jours_avant_rupture = ((stock - mini) / consomm_mois) * 30
            date_rupture = today + timedelta(days=jours_avant_rupture)
        else:
            marge = stock - mini
            if marge <= 2:
                jours_avant_rupture = 14
                urgence = 'HAUTE'
            elif marge <= 5:
                jours_avant_rupture = 30
                urgence = 'NORMALE'
            else:
                jours_avant_rupture = 60
                urgence = 'BASSE'
            date_rupture = today + timedelta(days=jours_avant_rupture)
            raison = f'Marge stock: {marge} unites'
    
    date_commande = date_rupture - timedelta(days=lead_time_jours)
    
    # Adjustments
    coefficient_criticite = 1.0
    if criticite == 'CRITIQUE':
        coefficient_criticite = 1.3
        date_commande -= timedelta(days=lead_time_jours * 0.3)
    elif criticite == 'BAS':
        coefficient_criticite = 0.8
        date_commande += timedelta(days=lead_time_jours * 0.2)
    
    facteur_equipements = 1.0
    if nb_equipements >= 3:
        facteur_equipements = 1.15
        date_commande -= timedelta(days=lead_time_jours * 0.15)
    elif nb_equipements >= 2:
        facteur_equipements = 1.1
        date_commande -= timedelta(days=lead_time_jours * 0.1)
    
    if cout > 5000:
        buffer_jours = lead_time_jours * 1.5
        date_commande -= timedelta(days=buffer_jours)
    elif cout > 1000:
        buffer_jours = lead_time_jours * 1.2
        date_commande -= timedelta(days=buffer_jours)
    elif cout < 100:
        buffer_jours = lead_time_jours * 0.5
        date_commande += timedelta(days=buffer_jours)
    
    if utilisation_recente >= 5:
        date_commande -= timedelta(days=lead_time_jours * 0.2)
    elif utilisation_recente >= 3:
        date_commande -= timedelta(days=lead_time_jours * 0.1)
    
    # Safety: never order in the past
    if date_commande < today:
        date_commande = today
        raison = 'COMMANDE IMMEDIATE NECESSAIRE'
        if urgence != 'CRITIQUE':
            urgence = 'CRITIQUE'
    
    jours_jusqua_commande = (date_commande - today).days
    
    if urgence is None:
        if jours_jusqua_commande <= 3:
            urgence = 'CRITIQUE'
        elif jours_jusqua_commande <= 14:
            urgence = 'HAUTE'
        elif jours_jusqua_commande <= 30:
            urgence = 'NORMALE'
        else:
            urgence = 'BASSE'
    
    return {
        'date_commande': str(date_commande),
        'urgence': urgence,
        'raison': raison or f'Consommation: {consomm_mois:.1f} pcs/mois',
        'prediction_available': True,
        'jours_avant_rupture': round(jours_avant_rupture, 1),
        'jours_jusqua_commande': jours_jusqua_commande,
        'details': {
            'stock_actuel': stock,
            'data_confidence': data_confidence,
            'consommation_mois': round(consomm_mois, 2)
        }
    }


def predict_pieces_a_commander(nb_to_return: int = 10) -> list:
    """
    Get top N pieces to order - only includes pieces with reliable predictions.
    """
    try:
        with get_db() as conn:
            pieces_df = read_sql("""
                SELECT id, reference, designation, stock_actuel, stock_minimum,
                       consommation_moyenne_mois, delai_fournisseur_jours, criticite,
                       prix_unitaire, nombre_equipements_relies, utilisation_recente_30j,
                       data_confidence
                FROM pieces_rechange
                ORDER BY stock_actuel ASC, designation
            """, conn)
            
            if pieces_df.empty:
                return []
            
            predictions = []
            urgence_priority = {'CRITIQUE': 0, 'HAUTE': 1, 'NORMALE': 2, 'BASSE': 3, 'UNKNOWN': 99}
            
            for _, row in pieces_df.iterrows():
                pred = predict_commande_date(dict(row))
                
                # Only include if prediction is available
                if pred.get('prediction_available') is True:
                    predictions.append({
                        'id': int(row['id']),
                        'reference': row['reference'],
                        'designation': row['designation'],
                        'stock_actuel': int(row['stock_actuel']),
                        'stock_minimum': int(row['stock_minimum']),
                        **pred
                    })
            
            # Sort by urgence then date
            predictions.sort(key=lambda x: (
                urgence_priority.get(x['urgence'], 99),
                x.get('jours_jusqua_commande', 999)
            ))
            
            return predictions[:nb_to_return]
    except Exception as e:
        logger.error(f"Erreur predict_pieces_a_commander: {e}")
        return []


# ==========================================
# IA CONTEXT BUILDER: Assemble data for AI analysis
# ==========================================

def get_ai_pieces_context(domaine: str = "", equipment_type: str = ""):
    """
    Assemble comprehensive context for AI analysis of spare parts.
    Includes historical usage, predictions, and equipment metadata.
    
    Args:
        domaine: Equipment domain/facility type (e.g., "Radiologie", "Soins Intensifs")
        equipment_type: Specific equipment type (e.g., "Scanner CT", "IRM")
    
    Returns:
        dict with complete context for AI prompt
    """
    try:
        with get_db() as conn:
            # Fetch all pieces with predictions
            pieces_df = read_sql("""
                SELECT 
                    id, reference, designation, equipement_type, domaine,
                    stock_actuel, stock_minimum, prix_unitaire, fournisseur,
                    consommation_moyenne_mois, delai_fournisseur_jours,
                    criticite, nombre_equipements_relies, utilisation_recente_30j,
                    data_confidence
                FROM pieces_rechange
                ORDER BY reference
            """, conn)
            
            if pieces_df.empty:
                return {'pieces': [], 'interventions_history': []}
            
            pieces_list = []
            for _, row in pieces_df.iterrows():
                piece_id = int(row['id'])
                
                # Get intervention history for this piece (last 90 days)
                history_df = read_sql("""
                    SELECT 
                        date, machine, client, technicien, statut,
                        pieces_utilisees
                    FROM interventions
                    WHERE pieces_utilisees LIKE %s
                        AND date >= NOW() - INTERVAL '90 days'
                    ORDER BY date DESC
                    LIMIT 20
                """, conn, params=(f'%{row["reference"]}%',))
                
                history = []
                for _, h in history_df.iterrows():
                    history.append({
                        'date': str(h['date']),
                        'equipment': h['machine'],
                        'facility': h['client'],
                        'technician': h['technicien'],
                        'status': h['statut']
                    })
                
                # Calculate when rupture will occur
                consumption = float(row['consommation_moyenne_mois'] or 0)
                stock = int(row['stock_actuel'] or 0)
                mini = int(row['stock_minimum'] or 1)
                
                if consumption > 0:
                    days_until_rupture = ((stock - mini) / consumption) * 30 if stock > mini else 0
                else:
                    days_until_rupture = None
                
                piece = {
                    'id': piece_id,
                    'reference': row['reference'],
                    'designation': row['designation'],
                    'equipment_type': row['equipement_type'],
                    'domain': row['domaine'],
                    'current_stock': stock,
                    'minimum_stock': mini,
                    'unit_price': float(row['prix_unitaire'] or 0),
                    'supplier': row['fournisseur'],
                    'supplier_lead_time_days': int(row['delai_fournisseur_jours'] or 14),
                    'criticality': row['criticite'],
                    'monthly_consumption': round(float(row['consommation_moyenne_mois'] or 0), 2),
                    'dependent_equipment_count': int(row['nombre_equipements_relies'] or 1),
                    'recent_usage_30d': int(row['utilisation_recente_30j'] or 0),
                    'data_confidence': row['data_confidence'],
                    'days_until_rupture': round(days_until_rupture, 1) if days_until_rupture is not None else None,
                    'recent_usage_history': history
                }
                
                # Calculate urgency
                if stock == 0:
                    piece['urgency'] = 'CRITICAL - OUT_OF_STOCK'
                elif stock <= mini:
                    piece['urgency'] = 'CRITICAL - LOW_STOCK'
                elif days_until_rupture is not None and days_until_rupture <= 7:
                    piece['urgency'] = 'HIGH - RUPTURE_IN_7_DAYS'
                elif days_until_rupture is not None and days_until_rupture <= 14:
                    piece['urgency'] = 'NORMAL - RUPTURE_IN_14_DAYS'
                else:
                    piece['urgency'] = 'LOW - ADEQUATE_STOCK'
                
                pieces_list.append(piece)
            
            # Global statistics
            total_stock_value = sum(p['current_stock'] * p['unit_price'] for p in pieces_list)
            critical_count = sum(1 for p in pieces_list if 'CRITICAL' in p['urgency'])
            high_count = sum(1 for p in pieces_list if p['urgency'].startswith('HIGH'))
            
            return {
                'pieces': pieces_list,
                'statistics': {
                    'total_pieces': len(pieces_list),
                    'critical_urgency_count': critical_count,
                    'high_urgency_count': high_count,
                    'total_stock_value': round(total_stock_value, 2),
                    'requested_domain': domaine,
                    'requested_equipment_type': equipment_type
                }
            }
    
    except Exception as e:
        logger.error(f"Erreur get_ai_pieces_context: {e}")
        return {'pieces': [], 'statistics': {}, 'error': str(e)}

