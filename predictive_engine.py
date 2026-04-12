# ==========================================
# 📊 MOTEUR DE MAINTENANCE PRÉDICTIVE
# ==========================================
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import SEUIL_SANTE_CRITIQUE, SEUIL_SANTE_ATTENTION, SEUIL_TENDANCE_ALERTE


def calculer_score_sante(df_historique, machine, jours_analyse=90):
    """
    Calcule un score de santé (0-100) pour une machine.
    
    Facteurs :
    - Fréquence des pannes (poids 40%)
    - Sévérité moyenne (poids 30%)
    - Temps depuis dernière panne (poids 20%)
    - Tendance récente vs historique (poids 10%)
    
    Retourne : score (int 0-100), détails (dict)
    """
    if df_historique.empty or "Date" not in df_historique.columns:
        return 100, {"status": "Aucune donnée", "pannes_total": 0}

    df_machine = df_historique[df_historique["Machine"] == machine].copy()
    if df_machine.empty:
        return 100, {"status": "Aucune panne enregistrée", "pannes_total": 0}

    df_machine["Date"] = pd.to_datetime(df_machine["Date"], errors="coerce")
    df_machine = df_machine.dropna(subset=["Date"])
    if df_machine.empty:
        return 100, {"status": "Dates invalides", "pannes_total": 0}

    now = datetime.now()
    date_limite = now - timedelta(days=jours_analyse)
    df_recent = df_machine[df_machine["Date"] >= date_limite]

    # --- 1. Fréquence des pannes (40%) ---
    nb_pannes = len(df_recent)
    # Score fréquence : 0 pannes = 100, 25+ pannes = 0
    score_freq = max(0, 100 - (nb_pannes * 4))

    # --- 2. Sévérité moyenne (30%) ---
    map_sev = {"CRITIQUE": 40, "HAUTE": 55, "ERREUR": 65, "ATTENTION": 80, "MOYENNE": 85, "BASSE": 95}
    if "Severite" in df_recent.columns and not df_recent.empty:
        severites = df_recent["Severite"].map(
            lambda x: map_sev.get(str(x).upper().strip(), 70)
        )
        score_sev = severites.mean()
    else:
        score_sev = 70

    # --- 3. Temps depuis dernière panne (20%) ---
    derniere_panne = df_machine["Date"].max()
    jours_depuis = (now - derniere_panne).days
    
    # Adoucissement de la pénalité (Racine carrée) :
    # 0j = 30 points, 14j = ~70 points, 30j = ~90 points, 60j = 100 points
    # La formule racine permet d'éviter la rigidité de la soustraction linaire abrupte
    import math
    if jours_depuis == 0:
        score_temps = 30
    else:
        # Pousser asymptotiquement vers 100 en fonction des jours (max cap = 100)
        score_temps = min(100, 30 + (math.sqrt(jours_depuis) * 12))

    # --- 4. Tendance (10%) ---
    moitie = jours_analyse // 2
    df_ancien = df_recent[df_recent["Date"] < (now - timedelta(days=moitie))]
    df_recemment = df_recent[df_recent["Date"] >= (now - timedelta(days=moitie))]
    nb_ancien = max(len(df_ancien), 1)
    nb_recent_half = len(df_recemment)
    ratio = nb_recent_half / nb_ancien
    if ratio > SEUIL_TENDANCE_ALERTE:
        score_tendance = max(0, 50 - (ratio - 1) * 30)
        tendance_txt = "📈 En hausse"
    elif ratio < 0.7:
        score_tendance = 100
        tendance_txt = "📉 En baisse"
    else:
        score_tendance = 75
        tendance_txt = "➡️ Stable"

    # --- Score composite ---
    score_final = int(
        score_freq * 0.40
        + score_sev * 0.30
        + score_temps * 0.20
        + score_tendance * 0.10
    )
    score_final = max(0, min(100, score_final))

    details = {
        "pannes_total": nb_pannes,
        "pannes_periode": len(df_recent),
        "derniere_panne": derniere_panne.strftime("%Y-%m-%d %H:%M"),
        "jours_depuis_derniere": jours_depuis,
        "tendance": tendance_txt,
        "ratio_tendance": round(ratio, 2),
        "score_frequence": round(score_freq, 1),
        "score_severite": round(score_sev, 1),
        "score_temps": round(score_temps, 1),
        "score_tendance": round(score_tendance, 1),
    }

    return score_final, details


def calculer_tendances(df_historique, machine=None, jours=90, granularite="semaine"):
    """
    Calcule les tendances de pannes pour le graphique temporel.
    
    Retourne un DataFrame : {Date, NbPannes, Machine}
    regroupé par semaine ou jour.
    """
    if df_historique.empty:
        return pd.DataFrame(columns=["Date", "NbPannes", "Machine"])

    df = df_historique.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    now = datetime.now()
    df = df[df["Date"] >= (now - timedelta(days=jours))]

    if machine:
        df = df[df["Machine"] == machine]

    if df.empty:
        return pd.DataFrame(columns=["Date", "NbPannes", "Machine"])

    # Regroupement temporel
    if granularite == "jour":
        df["Periode"] = df["Date"].dt.date
    else:  # semaine
        df["Periode"] = df["Date"].dt.to_period("W").dt.start_time.dt.date

    result = (
        df.groupby(["Periode", "Machine"])
        .size()
        .reset_index(name="NbPannes")
    )
    result = result.rename(columns={"Periode": "Date"})
    result["Date"] = pd.to_datetime(result["Date"])

    return result.sort_values("Date")


def predire_prochaine_panne(df_historique, machine, min_points=2):
    """
    Prédit la date probable de la prochaine panne en utilisant un modèle
    probabiliste basé sur le MTBF (Mean Time Between Failures) et la loi
    exponentielle de fiabilité.
    
    Retourne : {date_predite, confiance, intervalle_moyen_jours, nb_points}
    ou None si données insuffisantes.
    """
    if df_historique.empty:
        return None

    df = df_historique[df_historique["Machine"] == machine].copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")

    if len(df) < min_points:
        return None

    # Calculer les intervalles entre pannes
    dates = df["Date"].values
    intervalles = []
    for i in range(1, len(dates)):
        delta = (pd.Timestamp(dates[i]) - pd.Timestamp(dates[i - 1])).days
        if delta > 0:
            intervalles.append(delta)

    if not intervalles:
        return None

    import math
    moyenne = np.mean(intervalles)
    mtbf = max(1.0, float(moyenne)) 
    
    # Loi exponentielle de fiabilité: R(t) = e^(-lambda * t), où lambda = 1/MTBF
    # On cherche le moment "t" où la probabilité de défaillance CDF(t) atteint 50% ou plus 
    # (c-a-d Fiabilité tombe à 50%) -> t = -ln(0.5) * MTBF
    # Si le nombre de points est élevé on peut baisser le seuil d'alerte (prévenir plus tôt)
    
    prob_seuil = 0.50 # 50% de probabilité d'avoir déjà eu une panne
    if len(intervalles) > 5:
        prob_seuil = 0.60 # Modèle plus agressif si beaucoup d'historique (alerte plus tôt)

    # ln(1 - F(t)) = -t / MTBF => t = -MTBF * ln(1 - F(t))
    jours_prediction = -mtbf * math.log(1 - prob_seuil)
    
    # Déterminer la date prédite à partir de la dernière panne
    derniere_panne = pd.Timestamp(dates[-1])
    date_predite = derniere_panne + timedelta(days=int(jours_prediction))
    
    # Si la date prédite est déjà passée et qu'il n'y a pas eu de panne
    # On ajuste la prédiction au "prochain MTBF glissant" ou on garde à aujourd'hui max
    now = datetime.now()
    if date_predite < now:
        # L'équipement a "survécu" plus longtemps que le seuil de probabilité,
        # la probabilité conditionnelle indique qu'une panne est imminente
        date_predite = now + timedelta(days=2) 
        
    jours_restants = max(0, (date_predite - pd.Timestamp(now)).days)
    
    # Mettre à jour la logique de confiance: 
    # Beaucoup d'intervalles très réguliers (faible coefficient de variation CV) = forte confiance
    variance = np.var(intervalles)
    cv = (np.sqrt(variance) / mtbf) if mtbf > 0 else 1
    
    # Bonus de confiance si beaucoup d'historique
    bonus_points = min(20, len(intervalles) * 2) 
    confiance = min(95, max(10, int((1 - cv) * 80) + bonus_points))

    # Tendance des pannes (sont-elles de plus en plus rapprochées ?)
    x = np.arange(len(intervalles))
    y = np.array(intervalles, dtype=float)
    tendance_txt = "Stable ➡️"
    if len(intervalles) > 2:
        coeffs = np.polyfit(x, y, 1)
        if coeffs[0] < -1.0:
            tendance_txt = "Décroissant ⚠️"
        elif coeffs[0] > 1.0:
            tendance_txt = "Croissant ✅"

    return {
        "date_predite": date_predite.strftime("%Y-%m-%d"),
        "jours_restants": jours_restants,
        "confiance": max(10, confiance),
        "intervalle_moyen_jours": round(mtbf, 1),
        "tendance_intervalles": tendance_txt,
        "nb_points": len(intervalles),
    }


def generer_heatmap_data(df_historique, jours=90):
    """
    Génère les données pour une heatmap Machine × Semaine.
    Retourne un DataFrame pivoted.
    """
    if df_historique.empty:
        return pd.DataFrame()

    df = df_historique.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    now = datetime.now()
    df = df[df["Date"] >= (now - timedelta(days=jours))]

    if df.empty:
        return pd.DataFrame()

    df["Semaine"] = df["Date"].dt.isocalendar().week.astype(str)

    pivot = df.pivot_table(
        values="Code",
        index="Machine",
        columns="Semaine",
        aggfunc="count",
        fill_value=0,
    )

    return pivot


def repartition_erreurs_par_type(df_historique):
    """Calcule la répartition des erreurs par type pour un pie chart."""
    if df_historique.empty or "Type" not in df_historique.columns:
        return pd.DataFrame(columns=["Type", "Count"])

    result = (
        df_historique.groupby("Type")
        .size()
        .reset_index(name="Count")
        .sort_values("Count", ascending=False)
    )
    return result


def generer_recommandations(scores_machines, predictions):
    """
    Génère des recommandations de maintenance préventive.
    
    scores_machines : dict {machine: (score, details)}
    predictions : dict {machine: prediction_dict ou None}
    
    Retourne une liste de recommandations triées par urgence.
    """
    recommandations = []

    for machine, (score, details) in scores_machines.items():
        urgence = "HAUTE" if score < SEUIL_SANTE_CRITIQUE else (
            "MOYENNE" if score < SEUIL_SANTE_ATTENTION else "BASSE"
        )

        pred = predictions.get(machine)

        if score < SEUIL_SANTE_CRITIQUE:
            recommandations.append({
                "Machine": machine,
                "Urgence": "🔴 HAUTE",
                "Score": score,
                "Action": f"Inspection immédiate requise. Score santé critique ({score}%). "
                          f"Tendance: {details.get('tendance', '?')}",
                "Deadline": pred["date_predite"] if pred else "Dès que possible",
            })
        elif score < SEUIL_SANTE_ATTENTION:
            recommandations.append({
                "Machine": machine,
                "Urgence": "🟠 MOYENNE",
                "Score": score,
                "Action": f"Planifier maintenance préventive. Score: {score}%. "
                          f"{details.get('pannes_periode', 0)} pannes récentes.",
                "Deadline": pred["date_predite"] if pred else "Sous 2 semaines",
            })
        elif pred and pred.get("jours_restants", 999) < 14:
            recommandations.append({
                "Machine": machine,
                "Urgence": "🟡 PRÉVENTIVE",
                "Score": score,
                "Action": f"Panne prédite dans {pred['jours_restants']} jours "
                          f"(confiance: {pred['confiance']}%)",
                "Deadline": pred["date_predite"],
            })

    # Tri par urgence
    ordre = {"🔴 HAUTE": 0, "🟠 MOYENNE": 1, "🟡 PRÉVENTIVE": 2}
    recommandations.sort(key=lambda x: ordre.get(x["Urgence"], 3))

    return recommandations
