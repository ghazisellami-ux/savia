# ==========================================
# 🔍 DÉTECTION D'ANOMALIES
# ==========================================
"""
Analyse statistique des patterns d'erreurs.
Détecte les anomalies : fréquence inhabituelle, nouveaux types d'erreurs.
"""
import pandas as pd
from datetime import datetime, timedelta
from db_engine import get_db
from collections import Counter


def analyser_anomalies(jours_lookback=30, seuil_ratio=2.0):
    """
    Analyse les anomalies dans l'historique récent.
    
    Compare la fréquence des erreurs des N derniers jours
    par rapport à la période précédente.
    
    Retourne une liste de dict anomalies :
    [{"machine": ..., "code": ..., "type": "frequence"|"nouveau", 
      "ratio": ..., "details": ..., "severite": "HAUTE"|"MOYENNE"}]
    """
    from database import lire_interventions, lire_base
    hex_db, _ = lire_base()
    df = lire_interventions()
    if not df.empty:
        df = df.rename(columns={
            "date": "Date", 
            "machine": "Machine", 
            "code_erreur": "Code", 
            "statut": "Severite"
        })
        # Résoudre le Type d'erreur via codes_erreurs
        code_to_type = {code: info.get("Type", "Autre") for code, info in hex_db.items()} if hex_db else {}
        df["Type"] = df["Code"].map(code_to_type).fillna("Autre")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        
    if df.empty or "Date" not in df.columns:
        return []

    now = datetime.now()
    debut_recent = now - timedelta(days=jours_lookback)
    debut_precedent = debut_recent - timedelta(days=jours_lookback)

    df_recent = df[df["Date"] >= debut_recent]
    df_precedent = df[(df["Date"] >= debut_precedent) & (df["Date"] < debut_recent)]

    anomalies = []

    # ---- 1) Anomalie de fréquence par machine ----
    machines_col = "machine" if "machine" in df_recent.columns else "Machine"
    code_col = "code" if "code" in df_recent.columns else "Code"

    if not df_recent.empty:
        freq_recent = Counter()
        for _, row in df_recent.iterrows():
            key = (str(row.get(machines_col, "")), str(row.get(code_col, "")))
            freq_recent[key] += 1

        freq_precedent = Counter()
        for _, row in df_precedent.iterrows():
            key = (str(row.get(machines_col, "")), str(row.get(code_col, "")))
            freq_precedent[key] += 1

        for key, count_recent in freq_recent.items():
            machine, code = key
            count_prec = freq_precedent.get(key, 0)

            # Nouvelle erreur jamais vue
            if count_prec == 0 and count_recent >= 2:
                anomalies.append({
                    "machine": machine,
                    "code": code,
                    "type": "nouveau",
                    "count_recent": count_recent,
                    "count_precedent": 0,
                    "ratio": float("inf"),
                    "details": f"Nouveau pattern : {count_recent} occurrences en {jours_lookback}j, jamais vu avant",
                    "severite": "HAUTE",
                })
            # Augmentation significative
            elif count_prec > 0:
                ratio = count_recent / count_prec
                if ratio >= seuil_ratio and count_recent >= 3:
                    anomalies.append({
                        "machine": machine,
                        "code": code,
                        "type": "frequence",
                        "count_recent": count_recent,
                        "count_precedent": count_prec,
                        "ratio": round(ratio, 1),
                        "details": f"Fréquence x{ratio:.1f} : {count_recent} vs {count_prec} ({jours_lookback}j glissants)",
                        "severite": "HAUTE" if ratio >= 3.0 else "MOYENNE",
                    })

    # ---- 2) Machine avec trop d'erreurs distinctes ----
    if not df_recent.empty:
        machine_codes = df_recent.groupby(machines_col)[code_col].nunique()
        for machine, nb_codes in machine_codes.items():
            if nb_codes >= 5:
                anomalies.append({
                    "machine": str(machine),
                    "code": "MULTI",
                    "type": "diversite",
                    "count_recent": nb_codes,
                    "count_precedent": 0,
                    "ratio": nb_codes,
                    "details": f"{nb_codes} codes d'erreur distincts en {jours_lookback}j — problème systémique possible",
                    "severite": "HAUTE",
                })

    # Trier par sévérité puis ratio
    anomalies.sort(key=lambda x: (0 if x["severite"] == "HAUTE" else 1, -x.get("ratio", 0)))

    return anomalies


def get_machine_health_score(machine_name, jours=30):
    """
    Calcule un score de santé 0-100 pour une machine.
    100 = parfait, 0 = critique.
    """
    from database import lire_interventions, lire_base
    hex_db, _ = lire_base()
    df = lire_interventions()
    if not df.empty:
        df = df.rename(columns={
            "date": "Date", 
            "machine": "Machine", 
            "code_erreur": "Code", 
            "statut": "Severite"
        })
        code_to_type = {code: info.get("Type", "Autre") for code, info in hex_db.items()} if hex_db else {}
        df["Type"] = df["Code"].map(code_to_type).fillna("Autre")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        
    if df.empty or "Date" not in df.columns:
        return 100

    machines_col = "machine" if "machine" in df.columns else "Machine"
    sev_col = "severite" if "severite" in df.columns else "Severite"

    now = datetime.now()
    debut = now - timedelta(days=jours)
    df_machine = df[(df[machines_col] == machine_name) & (df["Date"] >= debut)]

    if df_machine.empty:
        return 95  # Pas d'erreur = bon score

    score = 100

    # Pénalités par sévérité
    for _, row in df_machine.iterrows():
        sev = str(row.get(sev_col, "")).upper()
        if sev == "CRITIQUE":
            score -= 15
        elif sev == "ERREUR" or sev == "HAUTE":
            score -= 8
        elif sev == "ATTENTION" or sev == "MOYENNE":
            score -= 3
        else:
            score -= 1

    return max(0, min(100, score))


def calculer_kpis(jours=30, date_start=None, date_end=None):
    """
    Calcule les KPIs du parc complet.
    Si date_start/date_end fournis, utilise cette plage.
    Sinon, utilise les N derniers jours.
    Retourne un dict avec : disponibilite, mtbf, mttr, mtti, cout_total, nb_interventions
    """
    from database import lire_interventions, lire_equipements

    df_equip = lire_equipements()
    nb_equip = len(df_equip)

    df_interv = lire_interventions()

    # Déterminer la plage de dates
    if date_start and date_end:
        debut = pd.to_datetime(date_start)
        fin = pd.to_datetime(date_end)
        jours_periode = max((fin - debut).days, 1)
    else:
        now = datetime.now()
        debut = now - timedelta(days=jours)
        fin = now
        jours_periode = jours

    # Filtrer interventions par période
    if not df_interv.empty and "date" in df_interv.columns:
        df_interv["date_dt"] = pd.to_datetime(df_interv["date"], errors="coerce")
        df_recent = df_interv[(df_interv["date_dt"] >= debut) & (df_interv["date_dt"] <= fin)]
    else:
        df_recent = pd.DataFrame()

    nb_interv = len(df_recent)
    # Coût total = charge technique (heures × taux horaire)
    from db_engine import get_config
    taux_horaire = 50
    try:
        taux_horaire = int(float(get_config("taux_horaire_technicien", "50") or "50"))
    except (ValueError, TypeError):
        pass
    duree_totale = df_recent["duree_minutes"].sum() if not df_recent.empty and "duree_minutes" in df_recent.columns else 0

    # Classifier les interventions (réparations uniquement)
    if not df_recent.empty and "type_intervention" in df_recent.columns:
        mask_repair = df_recent["type_intervention"].fillna("").str.contains("Corrective|ventive", case=False, na=False)
        df_repairs = df_recent[mask_repair]
    else:
        df_repairs = df_recent

    nb_repairs = len(df_repairs)

    # Coût maintenance = réparations uniquement (Corrective + Préventive)
    duree_repairs_tot = df_repairs["duree_minutes"].sum() if nb_repairs > 0 else 0
    cout_maintenance = round((duree_repairs_tot / 60) * taux_horaire, 2)
    cout_total_global = round((duree_totale / 60) * taux_horaire, 2)

    # MTTR = durée moyenne de réparation (Corrective + Préventive uniquement)
    duree_repairs = df_repairs["duree_minutes"].fillna(0).mean() if nb_repairs > 0 else 0
    mttr = duree_repairs / 60

    # MTBF = (heures totales) / nombre de pannes (réparations uniquement)
    heures_totales = nb_equip * jours_periode * 24 if nb_equip > 0 else 1
    mtbf = heures_totales / max(nb_repairs, 1)

    # Disponibilité basée sur les réparations uniquement
    heures_panne = df_repairs["duree_minutes"].sum() / 60 if nb_repairs > 0 else 0
    disponibilite = ((heures_totales - heures_panne) / heures_totales * 100) if heures_totales > 0 else 100

    return {
        "disponibilite": round(min(100, max(0, disponibilite)), 1),
        "mtbf": round(mtbf, 1),
        "mttr": round(mttr, 1),
        "cout_total": cout_maintenance,
        "cout_global": cout_total_global,
        "nb_interventions": nb_interv,
        "nb_repairs": nb_repairs,
        "nb_equipements": nb_equip,
        "duree_totale_h": round(duree_totale / 60, 1),
    }


def analyser_tendance_telemetrie(machine, sensor="TEMP", jours_lookback=7):
    """
    Analyse la tendance d'un capteur (ex: Température) pour prédire une surchauffe.
    Retourne un dict ou None si RAS.
    """
    from database import lire_telemetry
    
    # 1. Période récente (24h)
    df_recent = lire_telemetry(machine, sensor, hours=24)
    if df_recent.empty:
        return None
    avg_recent = df_recent["value"].mean()

    # 2. Période de référence (7 jours avant)
    # On récupère tout et on filtre manuellement car lire_telemetry est simple
    df_long = lire_telemetry(machine, sensor, hours=jours_lookback*24)
    if df_long.empty:
        return None
        
    start_ref = datetime.now() - timedelta(days=jours_lookback)
    end_ref = datetime.now() - timedelta(days=1)
    
    df_ref = df_long[(df_long["timestamp"] >= start_ref) & (df_long["timestamp"] < end_ref)]
    if df_ref.empty:
        return None
        
    avg_ref = df_ref["value"].mean()
    
    # Détection hausse significative (> 15%)
    if avg_ref > 0:
        ratio = avg_recent / avg_ref
        if ratio > 1.15:
            return {
                "machine": machine,
                "sensor": sensor,
                "type": "tendance_iot",
                "ratio": round(ratio, 2),
                "avg_recent": round(avg_recent, 1),
                "avg_ref": round(avg_ref, 1),
                "severite": "HAUTE" if ratio > 1.3 else "MOYENNE",
                "details": f"Hausse {sensor} (+{int((ratio-1)*100)}%) : {avg_recent:.1f} vs {avg_ref:.1f} (moy. 7j)"
            }
            
    return None
