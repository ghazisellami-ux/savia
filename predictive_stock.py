# ==========================================
# 🧠 MOTEUR PRÉDICTIF STOCK & ACHATS
# ==========================================
import pandas as pd
from datetime import datetime, timedelta
import re
from db_engine import lire_interventions, lire_pieces
from ai_engine import _call_ia, AI_AVAILABLE

def analyser_conso_pieces():
    """Calculates part consumption from interventions."""
    df_inter = lire_interventions()
    if df_inter.empty or "pieces_utilisees" not in df_inter.columns:
        return pd.DataFrame()

    usage_data = []

    for _, row in df_inter.iterrows():
        raw_str = row.get("pieces_utilisees", "")
        if not raw_str or len(raw_str) < 2:
            continue
        
        # Format: " | Designation (xQty)"
        parts = raw_str.split(" | ")
        date_inter = pd.to_datetime(row["date"])
        
        for part_entry in parts:
            if not part_entry.strip():
                continue
            
            # Extract quantity
            match = re.search(r"\(x(\d+)\)", part_entry)
            qty = int(match.group(1)) if match else 1
            
            # Nettoyer le nom (minuscules, espaces)
            name_clean = re.sub(r"\(x\d+\)", "", part_entry).strip().lower()
            
            usage_data.append({
                "Date": date_inter,
                "Piece": name_clean,
                "Qty": qty,
                "Machine": row["machine"]
            })

    if not usage_data:
        return pd.DataFrame()

    df_usage = pd.DataFrame(usage_data)
    df_usage["Date"] = pd.to_datetime(df_usage["Date"])
    df_usage = df_usage.sort_values("Date")
    
    stats = []
    # Group by piece name
    for piece, group in df_usage.groupby("Piece"):
        group = group.sort_values("Date")
        last_date = group["Date"].max()
        total_used = group["Qty"].sum()
        
        # MTBR (Mean Time Between Replacements)
        if len(group) > 1:
            diffs = group["Date"].diff().dt.days.dropna()
            mtbr = diffs.mean() if not diffs.empty else 365
        else:
            mtbr = 365 

        stats.append({
            "Piece": piece,
            "DerniereConso": last_date,
            "TotalConso": total_used,
            "MTBR_Jours": int(mtbr)
        })

    return pd.DataFrame(stats)

def predire_besoins_stock():
    """Generates purchase recommendations."""
    df_stats = analyser_conso_pieces()
    
    # Needs stock info
    df_stock = lire_pieces() 
    # Rendre le dictionnaire de stock insensible à la casse
    stock_map = {}
    if not df_stock.empty:
        stock_map = {str(row["designation"]).lower().strip(): row["stock_actuel"] for _, row in df_stock.iterrows()}

    predictions = []
    today = datetime.now()

    if df_stats.empty:
        return pd.DataFrame()

    for _, row in df_stats.iterrows():
        piece = row["Piece"]
        mtbr = row["MTBR_Jours"]
        last_date = row["DerniereConso"]
        
        # Next need calculation
        next_need_date = last_date + timedelta(days=mtbr)
        days_remaining = (next_need_date - today).days
        
        # Match stock (Robuste, insensible à la casse)
        current_stock = 0
        piece_lower = piece.lower()
        
        # Chercher une correspondance exacte ou partielle
        if piece_lower in stock_map:
            current_stock = stock_map[piece_lower]
        else:
            for design, stk in stock_map.items():
                if design in piece_lower or piece_lower in design:
                    current_stock = stk
                    break
        
        # Purchase Logic
        action = "✅ Pas d'action"
        lead_time = 45 # Délai d'approvisionnement standard en jours
        
        if current_stock == 0:
            recommended_date_str = today.strftime("%Y-%m-%d") # Acheter maintenant (rupture)
            action = "🛒 Achat Urgent (Rupture)"
        elif days_remaining < lead_time:
            # On va avoir besoin de la pièce avant qu'elle n'arrive si on la commande plus tard
            recommended_date_str = today.strftime("%Y-%m-%d")
            action = "🛒 Achat Recommandé"
        else:
            buy_date = next_need_date - timedelta(days=lead_time) 
            if buy_date < today: buy_date = today
            recommended_date_str = buy_date.strftime("%Y-%m-%d")

        predictions.append({
            "Pièce": piece.title(), # Remettre une majuscule pour l'affichage
            "Stock Est.": current_stock,
            "Dernier Rempl.": last_date.strftime("%Y-%m-%d"),
            "MTBR (jours)": mtbr,
            "Prochain Besoin": next_need_date.strftime("%Y-%m-%d"),
            "Date Achat Conseillée": recommended_date_str,
            "Action": action,
            "Justification IA": "Analyse en attente..." # Filled later if needed
        })
        
    return pd.DataFrame(predictions)

def generer_conseil_achat_ia(piece_info):
    """Generates AI justification for purchase using Gemini."""
    if not AI_AVAILABLE:
        return "IA non disponible."

    prompt = f"""Agis en tant que Supply Chain Manager stratégique d'un réseau hospitalier (spécialisé en pièces de radiologie médicale).
Analyse les données suivantes pour une seule pièce et fournis une recommandation d'achat structurée.

**Informations de la pièce :**
- Désignation : {piece_info.get('Pièce', 'N/A')}
- Type d'équipement : {piece_info.get('Équipement', 'Non spécifié')}
- Référence : {piece_info.get('Référence', 'N/A')}
- Stock actuel : {piece_info.get('Stock actuel', piece_info.get('Stock Est.', 'N/A'))} unité(s)
- Stock minimum requis : {piece_info.get('Stock minimum', 'N/A')} unité(s)
- Fournisseur : {piece_info.get('Fournisseur', 'Non spécifié')}
- Prix unitaire : {piece_info.get('Prix unitaire', 'N/A')}

**Données prédictives :**
- Fréquence de remplacement (MTBR) : {piece_info.get('MTBR (jours)', 'N/A')} jours
- Dernier remplacement : {piece_info.get('Dernier Rempl.', 'Aucun')}
- Prochain besoin estimé : {piece_info.get('Prochain Besoin', 'À évaluer')}

**Instructions :** Réponds en français, de manière implacable, concise et structurée :
1. **🔍 Analyse du risque** : Évalue le risque clinique (arrêt des soins causé par la rupture de cette pièce) et le risque de sur-stockage financier.
2. **🛒 Recommandation** : Indique s'il faut "Acheter maintenant", "Planifier pour plus tard" ou "Ne PAS acheter" - avec une justification très précise.
3. **📅 Timing** : Quand déclencher concrètement la commande pour pallier aux délais logistiques.
4. **💰 Impact budget** : Impact exact pour la clinique et la rentabilité du contrat.
"""

    try:
        resp = _call_ia(prompt)
        return resp.strip() if resp else "IA muette."
    except:
        return "Erreur IA."

