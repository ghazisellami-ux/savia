# ==========================================
# 📊 PAGE DASHBOARD — v3.0
# ==========================================
import streamlit as st

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from styles import kpi_card, health_badge, plotly_dark_layout, apply_plotly_defaults, CHART_COLORS
from database import lire_interventions, lire_equipements
from db_engine import get_config, lire_demandes_intervention
from predictive_engine import (
    calculer_score_sante, calculer_tendances,
    repartition_erreurs_par_type, generer_recommandations,
    predire_prochaine_panne
)
from anomaly_detector import analyser_anomalies, calculer_kpis
from i18n import t


def afficher_dashboard():
    """Affiche la page Dashboard avec KPIs, graphiques et alertes."""

    # Base unique PostgreSQL — plus besoin de sync entre SIC Terrain et SIC Radiologie

    st.title(t("dashboard"))

    # Filtre par client (verrouillé pour les Lecteurs)
    from auth import get_user_client
    lecteur_client = get_user_client()

    df_equip_filter = lire_equipements()
    if lecteur_client:
        # Lecteur: filtre verrouillé sur son client
        client_filtre = lecteur_client
        st.info(f"🏥 **Portail Client** — {lecteur_client}")
    else:
        # Admin/Technicien: filtre en haut de page
        clients_list = ["Tous les clients"]
        if not df_equip_filter.empty and "Client" in df_equip_filter.columns:
            clients_list += sorted(df_equip_filter["Client"].fillna("Non spécifié").unique().tolist())
        client_filtre = st.selectbox("🏥 Filtrer par client", clients_list, key="dash_client_filter")

    st.markdown("---")

    # ============ FILTRE PÉRIODE ============
    from datetime import datetime, timedelta
    import calendar

    now = datetime.now()
    fp1, fp2, fp3 = st.columns([2, 1, 1])
    with fp1:
        periode_mode = st.radio("📅 Période", ["Mensuel", "Annuel"], horizontal=True, key="dash_periode_mode")
    with fp2:
        if periode_mode == "Mensuel":
            sel_mois = st.number_input("Mois", min_value=1, max_value=12, value=now.month, key="dash_mois")
        else:
            sel_mois = None
    with fp3:
        if periode_mode == "Mensuel":
            sel_annee = st.number_input("Année", min_value=2020, max_value=2030, value=now.year, key="dash_annee")
        else:
            sel_annee = st.number_input("Année", min_value=2020, max_value=2030, value=now.year, key="dash_annee_a")

    if periode_mode == "Mensuel":
        date_start = datetime(sel_annee, sel_mois, 1)
        last_day = calendar.monthrange(sel_annee, sel_mois)[1]
        date_end = datetime(sel_annee, sel_mois, last_day, 23, 59, 59)
        jours_periode = last_day
        label_periode = f"{sel_mois:02d}/{sel_annee}"
    else:
        date_start = datetime(sel_annee, 1, 1)
        date_end = datetime(sel_annee, 12, 31, 23, 59, 59)
        jours_periode = 366 if calendar.isleap(sel_annee) else 365
        label_periode = f"{sel_annee}"

    st.markdown(f"""
<div style="background: rgba(59,130,246,0.08); border-left: 3px solid #3b82f6;
     border-radius: 6px; padding: 10px 14px; margin-top: 4px;">
    <span style="color: #3b82f6; font-weight: 600;">📊 Période : {label_periode}</span>
    <span style="color: #94a3b8; font-size: 0.85rem;"> | {date_start.strftime('%d/%m/%Y')} → {date_end.strftime('%d/%m/%Y')} ({jours_periode}j)</span>
</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Charger les données depuis les interventions uniquement
    df_interv = lire_interventions()
    df_equip = lire_equipements()

    # Préparer le DataFrame historique à partir des interventions
    common_cols = ["Date", "Machine", "Code", "Type", "Severite"]
    if not df_interv.empty:
        df_hist = df_interv.rename(columns={
            "date": "Date", "machine": "Machine",
            "code_erreur": "Code", "statut": "Severite"
        }).copy()
        df_hist["Date"] = pd.to_datetime(df_hist["Date"], errors="coerce")
        # Utiliser type_erreur (Hardware, Software, etc.) pour le camembert
        df_hist["Type"] = df_hist.get("type_erreur", pd.Series(dtype=str)).fillna("")
        for c in common_cols:
            if c not in df_hist.columns:
                df_hist[c] = ""
        # Filtrer par période sélectionnée
        df_hist = df_hist[(df_hist["Date"] >= pd.Timestamp(date_start)) & (df_hist["Date"] <= pd.Timestamp(date_end))]
    else:
        df_hist = pd.DataFrame(columns=common_cols)

    # Ne garder que les machines qui correspondent aux vrais équipements
    if not df_hist.empty and not df_equip.empty and "Nom" in df_equip.columns:
        noms_equip = set(df_equip["Nom"].astype(str).tolist())
        df_hist = df_hist[df_hist["Machine"].astype(str).isin(noms_equip)]

    # Appliquer le filtre client
    if client_filtre != "Tous les clients" and not df_equip.empty:
        df_equip = df_equip[df_equip["Client"] == client_filtre]

    # Filtrer historique par machines du client
    machines_client = df_equip["Nom"].tolist() if not df_equip.empty else []
    if client_filtre != "Tous les clients":
        if not df_hist.empty and "Machine" in df_hist.columns:
            df_hist = df_hist[df_hist["Machine"].isin(machines_client)]

    # ============ KPIs AVANCÉS (filtrés par période) ============
    kpis = calculer_kpis(date_start=date_start, date_end=date_end)

    # Recalculer TOUS les KPIs par client si filtré
    if client_filtre != "Tous les clients":
        df_inter_dash = lire_interventions()
        nb_eq_client = len(machines_client)
        if not df_inter_dash.empty:
            import pandas as _pd
            df_inter_dash["date_dt"] = _pd.to_datetime(df_inter_dash["date"], errors="coerce")
            df_recent = df_inter_dash[
                (df_inter_dash["machine"].isin(machines_client)) &
                (df_inter_dash["date_dt"] >= _pd.Timestamp(date_start)) &
                (df_inter_dash["date_dt"] <= _pd.Timestamp(date_end))
            ]
            nb_inter = len(df_recent)
            try:
                taux_h = int(float(get_config("taux_horaire_technicien", "50") or "50"))
            except (ValueError, TypeError):
                taux_h = 50
            duree_tot = df_recent["duree_minutes"].sum() if "duree_minutes" in df_recent.columns else 0

            # Filtrer par type pour MTTR et coûts
            if "type_intervention" in df_recent.columns:
                mask_repair = df_recent["type_intervention"].fillna("").str.contains("Corrective|ventive", case=False, na=False)
                duree_repairs = df_recent.loc[mask_repair, "duree_minutes"].sum() if mask_repair.any() else 0
                nb_repairs = int(mask_repair.sum())
                mttr = (df_recent.loc[mask_repair, "duree_minutes"].mean() / 60) if nb_repairs > 0 else 0
            else:
                duree_repairs = duree_tot
                nb_repairs = nb_inter
                mttr = (duree_tot / nb_inter / 60) if nb_inter > 0 else 0

            # Coût maintenance = réparations uniquement
            cout_maintenance = round((duree_repairs / 60) * taux_h, 2)

            # MTBF & Disponibilité basés sur réparations uniquement
            heures_totales = nb_eq_client * jours_periode * 24 if nb_eq_client > 0 else 1
            mtbf = heures_totales / max(nb_repairs, 1)
            heures_panne = duree_repairs / 60
            disponibilite = ((heures_totales - heures_panne) / heures_totales * 100) if heures_totales > 0 else 100
            kpis["cout_total"] = cout_maintenance
            kpis["mttr"] = round(mttr, 1)
            kpis["mtbf"] = round(mtbf, 1)
            kpis["disponibilite"] = round(min(100, max(0, disponibilite)), 1)
            kpis["nb_interventions"] = nb_inter
        else:
            # Pas d'interventions pour ce client
            kpis["cout_total"] = 0
            kpis["mttr"] = 0
            kpis["mtbf"] = nb_eq_client * jours_periode * 24 if nb_eq_client > 0 else 0
            kpis["disponibilite"] = 100.0
            kpis["nb_interventions"] = 0

    nb_machines = len(df_equip) if not df_equip.empty else 0
    # Compter les alertes critiques + interventions priorité Haute + demandes urgentes
    nb_critiques = 0
    nb_haute = 0
    if not df_hist.empty:
        if "Severite" in df_hist.columns:
            nb_critiques += int(df_hist["Severite"].astype(str).str.upper().str.contains("CRITIQUE").sum())
    # Priorité Haute : compter depuis df_interv — exclure les clôturées
    if not df_interv.empty:
        df_interv_active = df_interv[~df_interv["statut"].astype(str).str.contains("Clotur", case=False, na=False)]
        if "priorite" in df_interv_active.columns:
            nb_haute = int(df_interv_active["priorite"].astype(str).str.contains("Haute", case=False, na=False).sum())
        elif "Priorite" in df_interv_active.columns:
            nb_haute = int(df_interv_active["Priorite"].astype(str).str.contains("Haute", case=False, na=False).sum())
    nb_critiques += nb_haute

    # Demandes d'intervention en attente ("Nouvelle" uniquement — les acceptées/planifiées deviennent des interventions)
    try:
        if lecteur_client:
            df_demandes = lire_demandes_intervention(client=lecteur_client)
        elif client_filtre != "Tous les clients":
            df_demandes = lire_demandes_intervention(client=client_filtre)
        else:
            df_demandes = lire_demandes_intervention()
        # Afficher TOUTES les demandes "Nouvelle" (pas encore prises en charge)
        df_demandes_nouvelles = df_demandes[
            df_demandes["statut"].astype(str).str.strip() == "Nouvelle"
        ] if not df_demandes.empty and "statut" in df_demandes.columns else pd.DataFrame()
        # Compter les demandes urgentes (Haute) pour le KPI alertes
        df_demandes_haute = df_demandes_nouvelles[
            df_demandes_nouvelles["urgence"].astype(str).str.contains("Haute", case=False, na=False)
        ] if not df_demandes_nouvelles.empty and "urgence" in df_demandes_nouvelles.columns else pd.DataFrame()
        nb_critiques += len(df_demandes_haute)
    except Exception:
        df_demandes_nouvelles = pd.DataFrame()
        df_demandes_haute = pd.DataFrame()


    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

    with col1:
        st.markdown(kpi_card("🖥️", str(nb_machines), t("total_equipment")),
                    unsafe_allow_html=True)
    with col2:
        css = "danger" if nb_critiques > 0 else ""
        st.markdown(kpi_card("🔴", str(nb_critiques), t("critical_alerts"), css),
                    unsafe_allow_html=True)
    with col3:
        dispo = kpis.get("disponibilite", 99.9)
        st.markdown(kpi_card("✅", f"{dispo}%", t("availability_rate")),
                    unsafe_allow_html=True)
    with col4:
        _mtbf_h = kpis.get('mtbf', 0)
        _mtbf_str = f"{int(_mtbf_h // 24)}j {int(_mtbf_h % 24)}h" if _mtbf_h >= 24 else f"{_mtbf_h:.0f}h"
        st.markdown(kpi_card("⏱️", _mtbf_str, t("mtbf"),
                    tooltip="MTBF = Mean Time Between Failures (Temps moyen entre pannes). Plus la valeur est élevée, plus la machine est fiable."),
                    unsafe_allow_html=True)
    with col5:
        st.markdown(kpi_card("🔧", f"{kpis.get('mttr', 0):.1f}h", "MTTR (Réparations)",
                    tooltip="MTTR = Mean Time To Repair. Temps moyen de réparation (Corrective + Préventive uniquement)."),
                    unsafe_allow_html=True)
    with col6:
        user_role = st.session_state.get("user", {}).get("role", "")
        if user_role not in ("Lecteur", "Technicien"):
            devise = get_config("devise", "EUR")
            st.markdown(kpi_card("💰", f"{kpis.get('cout_total', 0):,.0f}".replace(",", " ") + f" {devise}",
                                 t("maintenance_cost")), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============ SCORE SANTÉ JOURNALIER + GAMIFICATION ============
    _score_col, _gamif_col = st.columns(2)

    with _score_col:
        # --- Score Santé du Jour ---
        from datetime import datetime, timedelta
        today_str = datetime.now().strftime("%Y-%m-%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Calculer le score basé sur disponibilité, MTBF, et alertes
        dispo_val = kpis.get("disponibilite", 100)
        mttr_val = kpis.get("mttr", 0)
        score_today = max(0, min(100, round(
            dispo_val * 0.5 +                              # 50% basé sur disponibilité
            max(0, 50 - nb_critiques * 10) +                # -10 pts par alerte critique
            max(0, min(20, 20 - mttr_val * 2))              # Bonus si MTTR bas
        )))

        # Historique des scores (session_state)
        if "_health_scores" not in st.session_state:
            st.session_state["_health_scores"] = {}
        st.session_state["_health_scores"][today_str] = score_today
        score_yesterday = st.session_state["_health_scores"].get(yesterday_str, score_today)
        delta = score_today - score_yesterday
        delta_str = f"↑{delta}%" if delta > 0 else f"↓{abs(delta)}%" if delta < 0 else "→ stable"
        delta_color = "#22c55e" if delta >= 0 else "#ef4444"

        # Couleur du score
        if score_today >= 85:
            score_color, score_bg, score_emoji = "#22c55e", "rgba(34,197,94,0.1)", "🟢"
        elif score_today >= 60:
            score_color, score_bg, score_emoji = "#eab308", "rgba(234,179,8,0.1)", "🟡"
        else:
            score_color, score_bg, score_emoji = "#ef4444", "rgba(239,68,68,0.1)", "🔴"

        st.markdown(f"""
        <div style="background:{score_bg}; border:1px solid {score_color}33; border-radius:12px; padding:16px; text-align:center;">
            <div style="font-size:0.75rem; color:#94a3b8; margin-bottom:4px;">📊 SCORE SANTÉ DU JOUR</div>
            <div style="font-size:2.2rem; font-weight:800; color:{score_color}; line-height:1;">{score_emoji} {score_today}%</div>
            <div style="font-size:0.85rem; color:{delta_color}; font-weight:600; margin-top:4px;">{delta_str}</div>
            <div style="background:rgba(255,255,255,0.08); border-radius:6px; height:8px; margin-top:8px; overflow:hidden;">
                <div style="width:{score_today}%; height:100%; background:{score_color}; border-radius:6px; transition:width 0.5s;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with _gamif_col:
        # --- Gamification Technicien ---
        from auth import get_current_user
        current_user = get_current_user()
        tech_name = current_user.get("nom", "") if current_user else ""
        current_month = datetime.now().strftime("%Y-%m")

        # Compter les interventions du mois pour ce technicien
        nb_mois = 0
        if not df_interv.empty and tech_name:
            df_interv["date_dt"] = pd.to_datetime(df_interv["date"], errors="coerce")
            df_tech_mois = df_interv[
                (df_interv["technicien"].astype(str).str.contains(tech_name, case=False, na=False)) &
                (df_interv["date_dt"].dt.strftime("%Y-%m") == current_month)
            ]
            nb_mois = len(df_tech_mois)
        elif not df_interv.empty:
            df_interv["date_dt"] = pd.to_datetime(df_interv["date"], errors="coerce")
            df_tech_mois = df_interv[df_interv["date_dt"].dt.strftime("%Y-%m") == current_month]
            nb_mois = len(df_tech_mois)

        # Record mensuel (session_state)
        record_key = "_gamif_record"
        if record_key not in st.session_state:
            st.session_state[record_key] = 0
        is_record = nb_mois > st.session_state[record_key]
        if is_record:
            st.session_state[record_key] = nb_mois
        record_val = st.session_state[record_key]

        # Badges et niveaux
        if nb_mois >= 30:
            badge, badge_name, badge_color = "🏆", "Expert", "#f59e0b"
        elif nb_mois >= 20:
            badge, badge_name, badge_color = "🥇", "Pro", "#eab308"
        elif nb_mois >= 10:
            badge, badge_name, badge_color = "🥈", "Confirmé", "#94a3b8"
        elif nb_mois >= 5:
            badge, badge_name, badge_color = "🥉", "En progression", "#cd7f32"
        else:
            badge, badge_name, badge_color = "⭐", "Débutant", "#64748b"

        # Message motivationnel
        if is_record and nb_mois > 1:
            motiv = f"🎉 <b>Nouveau record !</b>"
        elif nb_mois >= 20:
            motiv = "🔥 Performance exceptionnelle !"
        elif nb_mois >= 10:
            motiv = "💪 Excellent travail ce mois !"
        elif nb_mois >= 5:
            motiv = "👍 Bon rythme, continuez !"
        else:
            motiv = "🚀 C'est parti !"

        display_name = tech_name if tech_name else "Équipe"

        st.markdown(f"""
        <div style="background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.2); border-radius:12px; padding:16px; text-align:center;">
            <div style="font-size:0.75rem; color:#94a3b8; margin-bottom:4px;">🏆 GAMIFICATION — {display_name}</div>
            <div style="font-size:2.2rem; font-weight:800; color:#f59e0b; line-height:1;">{nb_mois} <span style="font-size:0.9rem;">interventions</span></div>
            <div style="font-size:0.8rem; color:{badge_color}; font-weight:600; margin-top:4px;">{badge} Niveau : {badge_name}</div>
            <div style="font-size:0.8rem; color:#64748b; margin-top:2px;">📊 Record mensuel : {record_val} | {motiv}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============ ANOMALIES DÉTECTÉES ============
    anomalies = analyser_anomalies(jours_lookback=30)
    if client_filtre != "Tous les clients" and anomalies:
        anomalies = [a for a in anomalies if a.get("machine", "") in machines_client]

    # Interventions à priorité Haute
    alertes_haute = []
    if not df_interv.empty and "priorite" in df_interv.columns:
        df_haute = df_interv[
            (df_interv["priorite"].astype(str).str.contains("Haute", case=False, na=False)) &
            (~df_interv["statut"].astype(str).str.contains("Clotur", case=False, na=False))
        ]
        if client_filtre != "Tous les clients":
            # Filtrer par client (extrait des notes [Client])
            def _get_client(notes):
                n = str(notes or "")
                if n.startswith("[") and "]" in n:
                    return n[1:n.index("]")]
                return ""
            df_haute = df_haute[df_haute["notes"].apply(_get_client).isin(machines_client) | df_haute["machine"].isin(machines_client)]
        for _, row in df_haute.iterrows():
            notes_str = str(row.get("notes", ""))
            client_name = notes_str[1:notes_str.index("]")] if notes_str.startswith("[") and "]" in notes_str else "—"
            alertes_haute.append({
                "machine": row.get("machine", "?"),
                "client": client_name,
                "type_erreur": row.get("type_erreur", "") if "type_erreur" in df_interv.columns else "",
                "code_erreur": row.get("code_erreur", ""),
                "description": str(row.get("description", ""))[:120],
                "technicien": row.get("technicien", ""),
                "statut": row.get("statut", ""),
                "date": str(row.get("date", ""))[:16],
                "type_intervention": row.get("type_intervention", ""),
            })

    # Demandes d'intervention en attente ("Nouvelle")
    alertes_demandes = []
    if not df_demandes_nouvelles.empty:
        for _, row in df_demandes_nouvelles.iterrows():
            alertes_demandes.append({
                "client": row.get("client", "?"),
                "equipement": row.get("equipement", "?"),
                "urgence": row.get("urgence", "Moyenne"),
                "description": str(row.get("description", ""))[:120],
                "demandeur": row.get("demandeur", ""),
                "date_demande": str(row.get("date_demande", ""))[:16],
                "statut": row.get("statut", "Nouvelle"),
            })

    has_alerts = bool(anomalies) or bool(alertes_haute) or bool(alertes_demandes)
    if has_alerts:
        st.markdown("---")
        nb_haute = len(alertes_haute) + len([a for a in (anomalies or []) if a.get("severite") == "HAUTE"]) + len([d for d in alertes_demandes if d.get("urgence") == "Haute"])
        nb_moyenne = len([a for a in (anomalies or []) if a.get("severite") == "MOYENNE"]) + len([d for d in alertes_demandes if d.get("urgence") == "Moyenne"])
        nb_total = len(anomalies or []) + len(alertes_haute) + len(alertes_demandes)
        label_parts = []
        if nb_haute > 0:
            label_parts.append(f"{nb_haute} priorité haute")
        if nb_moyenne > 0:
            label_parts.append(f"{nb_moyenne} priorité moyenne")
        label_detail = f" ({', '.join(label_parts)})" if label_parts else ""
        with st.expander(f"🚨 {nb_total} Anomalie(s) Détectée(s){label_detail}", expanded=False):

            # Afficher les interventions priorité Haute en premier
            for ah in alertes_haute:
                type_err = f" — 📌 {ah['type_erreur']}" if ah['type_erreur'] else ""
                code_err = f" | Code: `{ah['code_erreur']}`" if ah['code_erreur'] else ""
                st.markdown(f"""
<div style="border-left: 4px solid #ef4444; padding: 12px 16px; margin: 6px 0;
    background: rgba(239, 68, 68, 0.08); border-radius: 0 10px 10px 0;
    backdrop-filter: blur(8px); border: 1px solid rgba(239, 68, 68, 0.2);
    border-left: 4px solid #ef4444;">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <b>🔴 {ah['machine']}</b>
        <span style="background:#ef4444; color:white; padding:2px 10px; border-radius:10px; font-size:0.75rem; font-weight:700;">🚨 PRIORITÉ HAUTE</span>
    </div>
    <div style="color:#cbd5e1; font-size:0.85rem; margin-top:6px;">
        🏢 <b>{ah['client']}</b> — 🔧 {ah['type_intervention']}{type_err}{code_err}
    </div>
    <div style="color:#94a3b8; font-size:0.85rem; margin-top:4px;">
        📄 {ah['description']}
    </div>
    <div style="color:#64748b; font-size:0.8rem; margin-top:4px;">
        👷 {ah['technicien']} | 📅 {ah['date']} | 📋 {ah['statut']}
    </div>
</div>""", unsafe_allow_html=True)

            # Afficher les demandes d'intervention en attente
            for ad in alertes_demandes:
                urg_color = "#ef4444" if ad['urgence'] == "Haute" else "#f97316" if ad['urgence'] == "Moyenne" else "#eab308"
                urg_label = "🚨 URGENTE" if ad['urgence'] == "Haute" else "⚠️ MOYENNE" if ad['urgence'] == "Moyenne" else "📋 BASSE"
                st.markdown(f"""
<div style="border-left: 4px solid {urg_color}; padding: 12px 16px; margin: 6px 0;
    background: rgba(249, 115, 22, 0.08); border-radius: 0 10px 10px 0;
    backdrop-filter: blur(8px); border: 1px solid rgba(249, 115, 22, 0.2);
    border-left: 4px solid {urg_color};">
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <b>📋 {ad['equipement']}</b>
        <span style="background:{urg_color}; color:white; padding:2px 10px; border-radius:10px; font-size:0.75rem; font-weight:700;">📋 DEMANDE {urg_label}</span>
    </div>
    <div style="color:#cbd5e1; font-size:0.85rem; margin-top:6px;">
        🏢 <b>{ad['client']}</b> — 🚨 Urgence: {ad['urgence']}
    </div>
    <div style="color:#94a3b8; font-size:0.85rem; margin-top:4px;">
        📄 {ad['description']}
    </div>
    <div style="color:#64748b; font-size:0.8rem; margin-top:4px;">
        👤 {ad['demandeur']} | 📅 {ad['date_demande']} | 📋 En attente de prise en charge
    </div>
</div>""", unsafe_allow_html=True)

            # Afficher les anomalies classiques ensuite
            for a in (anomalies or [])[:5]:
                sev_icon = "🔴" if a["severite"] == "HAUTE" else "🟡"
                sev_color = "#ef4444" if a["severite"] == "HAUTE" else "#eab308"
                type_label = {"frequence": "📈 Fréquence", "nouveau": "🆕 Nouveau",
                              "diversite": "🎯 Diversité"}.get(a["type"], "❓")
                st.markdown(f"""
<div style="border-left: 4px solid {sev_color}; padding: 10px 16px; margin: 6px 0;
    background: rgba(30, 41, 59, 0.7); border-radius: 0 10px 10px 0;
    backdrop-filter: blur(8px); border: 1px solid rgba(148, 163, 184, 0.1);
    border-left: 4px solid {sev_color};">
    <b>{sev_icon} {a['machine']}</b> — {type_label}
    <br/><span style="color: #94a3b8; font-size: 0.9rem;">{a['details']}</span>
</div>""", unsafe_allow_html=True)

    # ============ TIMELINE DES INTERVENTIONS RÉCENTES ============
    st.markdown("---")
    st.subheader("📅 Timeline des Interventions Récentes")
    try:
        from streamlit_timeline import timeline as st_timeline
        # Construire les événements pour la timeline (max 15 dernières)
        if not df_interv.empty:
            df_tl = df_interv.copy()
            df_tl["date_dt"] = pd.to_datetime(df_tl["date"], errors="coerce")
            if client_filtre != "Tous les clients":
                df_tl = df_tl[df_tl["machine"].isin(machines_client)]
            df_tl = df_tl.dropna(subset=["date_dt"]).sort_values("date_dt", ascending=False).head(15)

            if not df_tl.empty:
                events = []
                for _, row in df_tl.iterrows():
                    dt = row["date_dt"]
                    statut = str(row.get("statut", ""))
                    is_cloture = "clotur" in statut.lower()
                    color = "#22c55e" if is_cloture else "#3b82f6" if "cours" in statut.lower() else "#f59e0b"

                    # Couleurs sombres pour les backgrounds des événements
                    bg_color = "#1a2332" if is_cloture else "#1a2940" if "cours" in statut.lower() else "#2a2520"
                    text_color = "#22c55e" if is_cloture else "#3b82f6" if "cours" in statut.lower() else "#f59e0b"

                    events.append({
                        "start_date": {"year": dt.year, "month": dt.month, "day": dt.day},
                        "text": {
                            "headline": f"<span style='color:{text_color}'>{'✅' if is_cloture else '🔄'} {row.get('machine', '?')}</span>",
                            "text": f"<span style='color:#e2e8f0'><b>{row.get('type_intervention', '')}</b><br>"
                                    f"👷 {row.get('technicien', '-')}<br>"
                                    f"📊 {statut}</span>"
                        },
                        "background": {"color": bg_color},
                    })

                tl_data = {
                    "title": {
                        "text": {
                            "headline": "<span style='color:#2dd4bf'>📅 Interventions</span>",
                            "text": "<span style='color:#94a3b8'>Historique récent</span>",
                        },
                        "background": {"color": "#0f172a"},
                    },
                    "events": events,
                }
                # CSS sombre pour TimelineJS
                st.markdown("""
                <style>
                /* Force dark mode sur l'iframe TimelineJS */
                iframe[title="streamlit_timeline.timeline"] {
                    border-radius: 12px;
                    border: 1px solid rgba(45,212,191,0.15) !important;
                }
                </style>
                """, unsafe_allow_html=True)
                st_timeline(tl_data, height=350)

                # Injecter JS pour forcer le dark mode dans le timenav (intérieur iframe)
                import streamlit.components.v1 as components
                components.html("""
                <script>
                function darkTimeline() {
                    var iframes = parent.document.querySelectorAll('iframe[title="streamlit_timeline.timeline"]');
                    for (var i = 0; i < iframes.length; i++) {
                        try {
                            var doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                            if (!doc) continue;
                            if (doc.getElementById('tl-dark-injected')) continue;
                            var style = doc.createElement('style');
                            style.id = 'tl-dark-injected';
                            style.textContent = `
                                body, .tl-timeline { background: #0f172a !important; }
                                .tl-timenav { background: #0f172a !important; border-top: 1px solid rgba(45,212,191,0.15) !important; }
                                .tl-timenav-slider { background: #0f172a !important; }
                                .tl-timeaxis-background { background: #1e293b !important; fill: #1e293b !important; }
                                .tl-timeaxis { background: #1e293b !important; }
                                .tl-timeaxis-tick, .tl-timeaxis-tick-text { color: #94a3b8 !important; }
                                .tl-timeaxis-tick line { stroke: #334155 !important; }
                                .tl-timemarker .tl-timemarker-content-container .tl-timemarker-content .tl-timemarker-text h2.tl-headline,
                                .tl-timemarker .tl-timemarker-content-container .tl-timemarker-content .tl-timemarker-text h2.tl-headline span {
                                    color: #e2e8f0 !important;
                                }
                                .tl-timemarker-content-container { background: #1e293b !important; border: 1px solid #334155 !important; }
                                .tl-timemarker-timespan { background: #334155 !important; }
                                .tl-timemarker .tl-timemarker-line-left, .tl-timemarker .tl-timemarker-line-right { border-color: #475569 !important; }
                                .tl-attribution { background: #0f172a !important; color: #64748b !important; }
                                .tl-attribution a { color: #64748b !important; }
                                .tl-slidenav-previous, .tl-slidenav-next { color: #94a3b8 !important; }
                                .tl-slidenav-previous .tl-slidenav-title, .tl-slidenav-next .tl-slidenav-title { color: #94a3b8 !important; }
                                .tl-slidenav-previous .tl-slidenav-description, .tl-slidenav-next .tl-slidenav-description { color: #64748b !important; }
                                .tl-slide { background: #0f172a !important; }
                                .tl-slide .tl-text .tl-text-content-container .tl-text-content h2.tl-headline { color: #e2e8f0 !important; }
                                .tl-slide .tl-text .tl-text-content-container .tl-text-content p { color: #94a3b8 !important; }
                                .tl-menubar { background: #0f172a !important; }
                                .tl-menubar-button { color: #94a3b8 !important; }
                                rect.tl-timeaxis-background { fill: #1e293b !important; }
                                text.tl-timeaxis-tick-text { fill: #94a3b8 !important; }
                                line.tl-timeaxis-tick { stroke: #334155 !important; }
                                .tl-timemarker.tl-timemarker-active .tl-timemarker-content-container { background: #334155 !important; }
                            `;
                            doc.head.appendChild(style);
                        } catch(e) {}
                    }
                }
                setTimeout(darkTimeline, 500);
                setTimeout(darkTimeline, 1500);
                setTimeout(darkTimeline, 3000);
                </script>
                """, height=0)
            else:
                st.info("Aucune intervention récente à afficher.")
        else:
            st.info("Aucune intervention enregistrée.")
    except ImportError:
        # Fallback si streamlit-timeline pas disponible
        if not df_interv.empty:
            df_recent = df_interv.sort_values("date", ascending=False).head(10)
            for _, row in df_recent.iterrows():
                statut = str(row.get("statut", ""))
                icon = "✅" if "clotur" in statut.lower() else "🔄" if "cours" in statut.lower() else "⏳"
                st.markdown(f"**{icon} {str(row.get('date', ''))[:10]}** — {row.get('machine', '?')} | "
                           f"👷 {row.get('technicien', '-')} | 📊 {statut}")
    except Exception:
        pass

    # ============ ANIMATION SANTÉ (CSS pur — aucune dépendance) ============
    st.markdown("""
    <style>
    @keyframes pulse-health {
        0% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.3); opacity: 0.5; }
        100% { transform: scale(1); opacity: 1; }
    }
    @keyframes pulse-ring {
        0% { transform: scale(1); opacity: 0.6; }
        100% { transform: scale(2.2); opacity: 0; }
    }
    .health-anim-container {
        display: flex; align-items: center; gap: 20px;
        padding: 16px 24px; margin: 8px 0;
        background: linear-gradient(135deg, rgba(45,212,191,0.06), rgba(59,130,246,0.06));
        border: 1px solid rgba(45,212,191,0.15); border-radius: 16px;
    }
    .health-pulse-wrapper { position: relative; width: 60px; height: 60px; }
    .health-pulse-dot {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
        width: 24px; height: 24px; border-radius: 50%;
        background: linear-gradient(135deg, #2dd4bf, #22c55e);
        animation: pulse-health 1.5s ease-in-out infinite;
        box-shadow: 0 0 20px rgba(45,212,191,0.4);
    }
    .health-pulse-ring {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
        width: 24px; height: 24px; border-radius: 50%;
        border: 2px solid #2dd4bf;
        animation: pulse-ring 1.5s ease-out infinite;
    }
    .health-title {
        font-size: 1.3rem; font-weight: 800;
        background: linear-gradient(135deg, #2dd4bf, #3b82f6);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .health-subtitle { color: #94a3b8; font-size: 0.85rem; margin-top: 2px; }
    </style>
    <div class="health-anim-container">
        <div class="health-pulse-wrapper">
            <div class="health-pulse-ring"></div>
            <div class="health-pulse-dot"></div>
        </div>
        <div>
            <div class="health-title">🫀 Santé du Parc d'Équipements</div>
            <div class="health-subtitle">📡 Monitoring en temps réel — Analyse prédictive active</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ============ SANTÉ DU PARC & ALERTES (FUSIONNÉ) ============
    col_gauche, col_droite = st.columns([3, 2])

    # Calculer les scores et prédictions par ÉQUIPEMENT (une seule fois, partagés)
    scores_machines = {}
    predictions = {}
    scores_data = []
    # Utiliser la liste d'équipements de la base (pas les logs)
    if not df_equip.empty:
        machines_equip = list(dict.fromkeys(df_equip["Nom"].tolist()))  # dédupliquer
    elif not df_hist.empty:
        machines_equip = df_hist["Machine"].unique().tolist()
    else:
        machines_equip = []

    for m in machines_equip:
        score, details = calculer_score_sante(df_hist, m)
        scores_machines[m] = (score, details)
        predictions[m] = predire_prochaine_panne(df_hist, m)
        scores_data.append({
            "Machine": m,
            "Score": score,
            "Tendance": details.get("tendance", "?"),
            "Pannes": details.get("pannes_periode", 0),
        })

    with col_gauche:
        st.subheader("🫀 " + t("health_score"))

        if scores_data:
            df_scores = pd.DataFrame(scores_data).sort_values("Score")

            # --- 1. KPI résumé compact (3 cartes) ---
            nb_critique = len(df_scores[df_scores["Score"] < 30])
            nb_attention = len(df_scores[(df_scores["Score"] >= 30) & (df_scores["Score"] < 60)])
            nb_bon = len(df_scores[df_scores["Score"] >= 60])
            total = len(df_scores)

            kpi_html = f"""
            <div style="display:flex;gap:10px;margin-bottom:14px;">
                <div style="flex:1;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);
                    border-radius:10px;padding:10px 14px;text-align:center;">
                    <div style="font-size:1.8rem;font-weight:800;color:#ef4444;">{nb_critique}</div>
                    <div style="font-size:0.75rem;color:#fca5a5;">🔴 Critique</div>
                </div>
                <div style="flex:1;background:rgba(245,158,11,0.15);border:1px solid rgba(245,158,11,0.3);
                    border-radius:10px;padding:10px 14px;text-align:center;">
                    <div style="font-size:1.8rem;font-weight:800;color:#f59e0b;">{nb_attention}</div>
                    <div style="font-size:0.75rem;color:#fcd34d;">🟡 Attention</div>
                </div>
                <div style="flex:1;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.3);
                    border-radius:10px;padding:10px 14px;text-align:center;">
                    <div style="font-size:1.8rem;font-weight:800;color:#10b981;">{nb_bon}</div>
                    <div style="font-size:0.75rem;color:#6ee7b7;">🟢 Bon</div>
                </div>
            </div>
            """
            st.markdown(kpi_html, unsafe_allow_html=True)

            # --- 2. Tableau compact trié (coloré) ---
            def _color_score(val):
                """Coloration conditionnelle du score."""
                try:
                    v = int(val)
                except (ValueError, TypeError):
                    return ""
                if v < 30:
                    return "background-color: rgba(239,68,68,0.25); color: #fca5a5; font-weight: 700;"
                elif v < 60:
                    return "background-color: rgba(245,158,11,0.25); color: #fcd34d; font-weight: 700;"
                else:
                    return "background-color: rgba(16,185,129,0.25); color: #6ee7b7; font-weight: 700;"

            def _tendance_emoji(val):
                """Remplace les tendances par des emojis visuels."""
                mapping = {"hausse": "📈 Hausse", "baisse": "📉 Baisse", "stable": "➡️ Stable"}
                return mapping.get(str(val).lower(), str(val))

            df_display = df_scores.copy()
            df_display["Tendance"] = df_display["Tendance"].apply(_tendance_emoji)
            df_display = df_display.rename(columns={
                "Machine": "Équipement", "Score": "Santé %", "Pannes": "Pannes (période)"
            })

            styled = (
                df_display.style
                .applymap(_color_score, subset=["Santé %"])
                .set_properties(**{
                    "text-align": "center",
                    "font-size": "0.85rem",
                })
                .set_properties(subset=["Équipement"], **{"text-align": "left"})
                .hide(axis="index")
            )
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                height=min(38 * total + 40, 400),  # Hauteur dynamique, max 400px
                column_config={
                    "Santé %": st.column_config.ProgressColumn(
                        "Santé %",
                        min_value=0,
                        max_value=100,
                        format="%d%%",
                    ),
                    "Pannes (période)": st.column_config.NumberColumn(
                        "Pannes",
                        format="%d",
                    ),
                },
            )


        else:
            st.info(t("no_data"))

    with col_droite:
        st.subheader("🎯 Jauge Santé Globale")

        if scores_machines:
            all_scores = [s for s, _ in scores_machines.values()]
            score_global = int(sum(all_scores) / len(all_scores)) if all_scores else 100

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score_global,
                number={"suffix": "%", "font": {"size": 48, "color": "#f1f5f9"}},
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": "#64748b"},
                    "bar": {"color": "#00d4aa" if score_global >= 60 else "#f59e0b" if score_global >= 30 else "#ef4444"},
                    "bgcolor": "#1e293b",
                    "borderwidth": 0,
                    "steps": [
                        {"range": [0, 30], "color": "rgba(239,68,68,0.1)"},
                        {"range": [30, 60], "color": "rgba(245,158,11,0.1)"},
                        {"range": [60, 100], "color": "rgba(16,185,129,0.1)"},
                    ],
                    "threshold": {
                        "line": {"color": "#f1f5f9", "width": 3},
                        "thickness": 0.8,
                        "value": score_global,
                    },
                },
            ))
            fig_gauge.update_layout(
                **plotly_dark_layout(),
                height=280,
                margin=dict(l=30, r=30, t=30, b=10),
            )
            apply_plotly_defaults(fig_gauge)
            st.plotly_chart(fig_gauge, use_container_width=True)
        else:
            st.info(t("no_data"))

        # Répartition par type
        st.subheader("📁 Répartition par Type")
        # Utiliser df_interv directement pour éviter le filtre par nom d'équipement
        df_pie_src = df_interv.copy() if not df_interv.empty else pd.DataFrame()
        if not df_pie_src.empty and "type_erreur" in df_pie_src.columns:
            df_pie_src = df_pie_src[df_pie_src["type_erreur"].astype(str).str.strip() != ""]
            if not df_pie_src.empty:
                df_rep = df_pie_src.groupby("type_erreur").size().reset_index(name="Count")
                df_rep = df_rep.rename(columns={"type_erreur": "Type"})
                fig_pie = px.pie(
                    df_rep, names="Type", values="Count",
                    color_discrete_sequence=CHART_COLORS,
                    hole=0.4,
                )
                fig_pie.update_layout(
                    **plotly_dark_layout(),
                    height=280,
                    showlegend=True,
                    legend=dict(font=dict(size=11)),
                    margin=dict(l=10, r=10, t=10, b=10),
                )
                apply_plotly_defaults(fig_pie)
                fig_pie.update_traces(
                    textinfo="percent+label",
                    textfont=dict(size=11),
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Aucune intervention avec un type d'erreur défini.")
        else:
            st.info("Aucune intervention avec un type d'erreur défini.")

    # ============ TENDANCES ============
    st.markdown("---")
    st.subheader("📈 Tendance des Pannes (90 jours)")

    if not df_hist.empty:
        df_tendances = calculer_tendances(df_hist, jours=90)
        if not df_tendances.empty:
            fig_trend = px.line(
                df_tendances, x="Date", y="NbPannes", color="Machine",
                color_discrete_sequence=CHART_COLORS,
                markers=True,
            )
            fig_trend.update_layout(
                **plotly_dark_layout(),
                height=350,
                xaxis_title=t("date"),
                yaxis_title="Nombre de pannes",
                legend_title=t("machine"),
            )
            apply_plotly_defaults(fig_trend)
            fig_trend.update_traces(line=dict(width=2.5))
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info(t("no_data"))
    else:
        st.info(t("no_data"))

    # ============ RECOMMANDATIONS & ACTIONS ============
    st.markdown("---")
    st.subheader("🚨 Alertes & Recommandations")

    if scores_machines:
        recs = generer_recommandations(scores_machines, predictions)
        if recs:
            for i, rec in enumerate(recs):
                urgence = rec.get("Urgence", "")
                machine = rec.get("Machine", "")
                score = rec.get("Score", "")
                action = rec.get("Action", "")
                deadline = rec.get("Deadline", "")

                # Couleur selon urgence
                if "CRITIQUE" in str(urgence).upper():
                    color = "#ef4444"
                    icon = "🔴"
                elif "HAUTE" in str(urgence).upper() or "HIGH" in str(urgence).upper():
                    color = "#f97316"
                    icon = "🟠"
                else:
                    color = "#eab308"
                    icon = "🟡"

                col_alert, col_btn = st.columns([5, 1])
                with col_alert:
                    st.markdown(
                        f"""<div style="border-left: 4px solid {color}; padding: 8px 12px; margin: 4px 0;
                            background: rgba(255,255,255,0.03); border-radius: 0 8px 8px 0;">
                            <b>{icon} {urgence}</b> — <b>{machine}</b> (Score: {score})<br/>
                            📋 {action}<br/>
                            <small>⏰ Deadline : {deadline}</small>
                        </div>""",
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("📅 Planifier", key=f"plan_alert_{i}", use_container_width=True):
                        st.session_state["prefill_planning"] = {
                            "machine": machine,
                            "description": f"[Auto] {action}",
                            "type": "Préventive",
                            "notes": f"Urgence: {urgence} | Score: {score} | Deadline: {deadline}",
                        }
                        st.session_state["nav_target"] = "planning"
                        st.rerun()
        else:
            st.success("✅ Aucune recommandation urgente — Parc en bonne santé !")
    else:
        st.info(t("no_data"))
