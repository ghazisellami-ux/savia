import streamlit as st
import pandas as pd
from datetime import datetime
from db_engine import (
    lire_interventions, lire_techniciens, lire_equipements, lire_base,
    ajouter_technicien, update_technicien, supprimer_technicien,
    cloturer_intervention, ajouter_intervention, lire_pieces,
    update_intervention_statut, get_config, set_config, get_db
)
from auth import require_role, get_current_user
from styles import kpi_card

TYPES_ERREUR = ["Hardware", "Software", "Réseau", "Calibration", "Mécanique", "Électrique", "Autre"]
PRIORITES = ["Haute", "Moyenne", "Basse"]

def _calculer_kpis_equipe(df, sym="EUR"):
    """Calcule les KPIs de performance de l'equipe a partir d'un DataFrame d'interventions."""
    kpis = {}
    if df.empty:
        return kpis

    nb_total = len(df)
    kpis["nb_total"] = nb_total

    # Taux de resolution
    mask_cloture = df["statut"].fillna("").str.contains("tur", case=False, na=False)
    nb_cloture = int(mask_cloture.sum())
    nb_en_cours = nb_total - nb_cloture
    kpis["nb_cloture"] = nb_cloture
    kpis["nb_en_cours"] = nb_en_cours
    kpis["taux_resolution"] = round((nb_cloture / nb_total) * 100, 1) if nb_total > 0 else 0

    durees = df["duree_minutes"].fillna(0)
    mask_repair = df["type_intervention"].fillna("").str.contains("Corrective|ventive", case=False, na=False)

    durees_repairs = durees[mask_cloture & mask_repair]
    kpis["mttr_h"] = round(durees_repairs.mean() / 60, 1) if len(durees_repairs) > 0 and durees_repairs.mean() > 0 else 0

    kpis["duree_totale_h"] = round(durees.sum() / 60, 1)

    # Cout moyen par intervention (charge technique = taux_horaire × heures)
    try:
        taux_h = int(float(get_config("taux_horaire_technicien", "50") or "50"))
    except (ValueError, TypeError):
        taux_h = 50
    kpis["cout_total"] = round((durees.sum() / 60) * taux_h, 2)
    kpis["cout_moyen"] = round(kpis["cout_total"] / nb_total, 2) if nb_total > 0 else 0

    # Ratio correctif / preventif
    nb_corrective = len(df[df["type_intervention"].fillna("").str.contains("Corrective", case=False, na=False)])
    nb_preventive = len(df[df["type_intervention"].fillna("").str.contains("ventive", case=False, na=False)])
    kpis["nb_corrective"] = nb_corrective
    kpis["nb_preventive"] = nb_preventive
    kpis["ratio_correctif_pct"] = round((nb_corrective / nb_total) * 100, 1) if nb_total > 0 else 0

    # Performance par technicien
    tech_stats = []
    if "technicien" in df.columns:
        for tech_name in df["technicien"].fillna("Inconnu").unique():
            df_tech = df[df["technicien"] == tech_name]
            tech_cloture = df_tech["statut"].fillna("").str.contains("tur", case=False, na=False)
            tech_durees = df_tech["duree_minutes"].fillna(0)
            tech_durees_clot = tech_durees[tech_cloture]
            tech_mttr = round(tech_durees_clot.mean() / 60, 1) if len(tech_durees_clot) > 0 and tech_durees_clot.mean() > 0 else 0
            tech_stats.append({
                "nom": tech_name,
                "nb_interventions": len(df_tech),
                "nb_cloturees": int(tech_cloture.sum()),
                "taux_resolution": round((tech_cloture.sum() / len(df_tech)) * 100, 1) if len(df_tech) > 0 else 0,
                "mttr_h": tech_mttr,
                "cout_total": round((tech_durees.sum() / 60) * taux_h, 2),
            })
    kpis["tech_stats"] = sorted(tech_stats, key=lambda x: x["taux_resolution"], reverse=True)

    # Score de performance global (0-100)
    score = 0
    # Taux resolution contribue 40 points
    score += min(40, kpis["taux_resolution"] * 0.4)
    # MTTR < 2h = 30 points, jusqu'a 8h = lineaire
    if kpis["mttr_h"] > 0:
        mttr_score = max(0, 30 - (kpis["mttr_h"] - 2) * 5)
        score += min(30, mttr_score)
    else:
        score += 15  # pas de donnees = neutre
    # Ratio preventif > correctif = 30 points
    preventif_ratio = (100 - kpis["ratio_correctif_pct"])
    score += min(30, preventif_ratio * 0.3)
    kpis["score_global"] = round(min(100, max(0, score)), 0)

    return kpis


def _get_ai_recommendations(kpis, sym="EUR"):
    """Appelle Gemini pour generer des recommandations de performance."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        if not AI_AVAILABLE:
            return None

        tech_detail = ""
        for ts in kpis.get("tech_stats", []):
            tech_detail += (
                f"  - {ts['nom']}: {ts['nb_interventions']} interventions, "
                f"{ts['taux_resolution']}% resolues, MTTR={ts['mttr_h']}h, "
                f"cout total={ts['cout_total']} {sym}\n"
            )

        prompt = f"""Agis en tant que Directeur du Service Technique pour une entreprise d'équipements d'imagerie médicale.
Ton rôle est d'analyser ces métriques d'équipe (taux de résolution, MTTR temps moyen de réparation, ratio préventif/curatif, coûts) pour le mois en cours.

KPIs de l'equipe :
- Interventions totales : {kpis.get('nb_total', 0)}
- Taux de resolution : {kpis.get('taux_resolution', 0)}%
- MTTR (temps moyen de reparation) : {kpis.get('mttr_h', 0)}h
- Cout moyen par intervention : {kpis.get('cout_moyen', 0)} {sym}
- Cout total : {kpis.get('cout_total', 0)} {sym}
- Ratio correctif : {kpis.get('ratio_correctif_pct', 0)}% ({kpis.get('nb_corrective', 0)} correctives / {kpis.get('nb_preventive', 0)} preventives)
- Score global : {kpis.get('score_global', 0)}/100

Performance par technicien :
{tech_detail if tech_detail else '  Aucune donnee par technicien'}

Donne-moi un rapport exécutif exigeant et constructif. Identifie les points de tension qui plombent la rentabilité, et propose des actions fortes pour réduire le MTTR.
Reponds en JSON avec cette structure EXACTE :
{{
  "analyse": "Résumé exécutif de la situation actuelle (2 phrases max)",
  "points_forts": ["point fort 1", "point fort 2"],
  "points_faibles": ["point faible 1", "point faible 2"],
  "recommandations": [
    {{
      "titre": "Directives stratégiques",
      "description": "Action précise pour baisser le MTTR ou optimiser l'équipe",
      "impact": "HAUT" ou "MOYEN" ou "BAS",
      "priorite": 1
    }}
  ],
  "objectifs": [
    "Objectif KPI mesurable pour le mois prochain",
    "Objectif opérationnel pour les techniciens"
  ]
}}"""

        raw = _call_ia(prompt, timeout=45)
        if not raw:
            return None
        result = clean_json_response(raw)
        return result
    except Exception:
        return None


def show_sav_page():
    st.markdown("## 🛠️ Service Après-Vente & Interventions")

    # Détection rôle pour masquer les coûts
    from auth import get_current_user
    _sav_user = get_current_user()
    _sav_role = _sav_user.get("role", "") if _sav_user else ""
    _hide_costs = _sav_role in ("Technicien", "Lecteur")

    # Si on vient d'un "Intervention Rapide", auto-cliquer sur l'onglet Mode Tablette via JS
    _has_prefill = st.session_state.get("prefill_intervention") is not None
    if _has_prefill:
        import streamlit.components.v1 as components
        components.html("""
        <script>
        setTimeout(function() {
            const tabs = parent.document.querySelectorAll('button[data-baseweb="tab"]');
            if (tabs.length >= 3) { tabs[2].click(); }
        }, 500);
        </script>
        """, height=0)

    # Tabs : masquer l'onglet Charge Technique pour Technicien/Lecteur
    if _hide_costs:
        tab_dash, tab_team, tab_tablet, tab_photos = st.tabs(["📊 Tableau de Bord", "👥 Équipe Technique", "📱 Mode Tablette (Terrain)", "📸 Fiches Signées"])
        tab_charge = None
    else:
        tab_dash, tab_team, tab_tablet, tab_charge, tab_photos = st.tabs(["📊 Tableau de Bord", "👥 Équipe Technique", "📱 Mode Tablette (Terrain)", "💰 Charge Technique", "📸 Fiches Signées"])

    # ==========================================
    # ONGLET 1 : TABLEAU DE BORD (MANAGER)
    # ==========================================
    with tab_dash:
        # ============ FILTRE PÉRIODE (MOIS / ANNÉE) ============
        import calendar
        now = datetime.now()
        fp1, fp2, fp3 = st.columns([2, 1, 1])
        with fp1:
            sav_periode_mode = st.radio("📅 Période", ["Mensuel", "Annuel"], horizontal=True, key="sav_periode_mode")
        with fp2:
            if sav_periode_mode == "Mensuel":
                sav_sel_mois = st.number_input("Mois", min_value=1, max_value=12, value=now.month, key="sav_mois")
            else:
                sav_sel_mois = None
        with fp3:
            if sav_periode_mode == "Mensuel":
                sav_sel_annee = st.number_input("Année", min_value=2020, max_value=2030, value=now.year, key="sav_annee")
            else:
                sav_sel_annee = st.number_input("Année", min_value=2020, max_value=2030, value=now.year, key="sav_annee_a")

        if sav_periode_mode == "Mensuel":
            sav_date_start = datetime(sav_sel_annee, sav_sel_mois, 1)
            sav_last_day = calendar.monthrange(sav_sel_annee, sav_sel_mois)[1]
            sav_date_end = datetime(sav_sel_annee, sav_sel_mois, sav_last_day, 23, 59, 59)
            sav_label_periode = f"{sav_sel_mois:02d}/{sav_sel_annee}"
        else:
            sav_date_start = datetime(sav_sel_annee, 1, 1)
            sav_date_end = datetime(sav_sel_annee, 12, 31, 23, 59, 59)
            sav_label_periode = f"{sav_sel_annee}"

        st.markdown(f"""
<div style="background: rgba(59,130,246,0.08); border-left: 3px solid #3b82f6;
     border-radius: 6px; padding: 10px 14px; margin-top: 4px; margin-bottom: 12px;">
    <span style="color: #3b82f6; font-weight: 600;">📊 Période : {sav_label_periode}</span>
</div>
""", unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)
        df_inter = lire_interventions()

        # Appliquer le filtre période
        if not df_inter.empty and "date" in df_inter.columns:
            df_inter["date_dt"] = pd.to_datetime(df_inter["date"], errors="coerce")
            df_inter = df_inter[
                (df_inter["date_dt"] >= sav_date_start) &
                (df_inter["date_dt"] <= sav_date_end)
            ]
        
        # Métriques rapides (KPI cards stylisées)
        if not df_inter.empty:
            nb_total = len(df_inter)
            # Comparaison ultra-robuste : 'lotur' est present dans Cloturee, Clôturée, Cl├┴tur├®e
            # 'tur' est present dans TOUTE variante : Cloturee, Clôturée, ClÃ´turÃ©e
            _mask_cloture = df_inter["statut"].fillna("").str.contains("tur", case=False, na=False)
            _mask_assignee = df_inter["statut"].fillna("").str.contains("ssign", case=False, na=False)
            _mask_attente = df_inter["statut"].fillna("").str.contains("attente", case=False, na=False)
            nb_cloture = int(_mask_cloture.sum())
            nb_assignee = int(_mask_assignee.sum())
            nb_attente = int(_mask_attente.sum())
            nb_en_cours = nb_total - nb_cloture - nb_attente
            col1.markdown(kpi_card("📋", str(nb_total), "Interventions Totales"), unsafe_allow_html=True)
            col2.markdown(kpi_card("🔄", str(nb_en_cours), "En Cours"), unsafe_allow_html=True)
            col3.markdown(kpi_card("✅", str(nb_cloture), "Clôturées"), unsafe_allow_html=True)
            col4.markdown(kpi_card("⏳", str(nb_attente), "Attente de pièce"), unsafe_allow_html=True)

        st.markdown("---")

        # Fonction de normalisation des statuts (gère TOUTE corruption d'encodage)
        def _normalize_statut(s):
            s_lower = str(s).lower()
            if "clotur" in s_lower or "tur" in s_lower:
                return "Clôturée"
            if "ssign" in s_lower:
                return "En cours"
            if "attente" in s_lower:
                return "En attente de pièce"
            return "En cours"

        # Ajouter une colonne statut normalisé pour filtrage et affichage
        if not df_inter.empty:
            df_inter["statut_clean"] = df_inter["statut"].apply(_normalize_statut)

        # Extraire le client depuis les notes [Client] ou via la table équipements
        if not df_inter.empty:
            def _extract_client(notes):
                n = str(notes or "")
                if n.startswith("[") and "]" in n:
                    return n[1:n.index("]")]
                return ""
            df_inter["client"] = df_inter["notes"].apply(_extract_client)
            # Compléter avec les équipements si le client est vide
            df_equip = lire_equipements()
            if not df_equip.empty:
                equip_client_map = {}
                for _, eq in df_equip.iterrows():
                    nom = eq.get("Nom") or eq.get("nom") or ""
                    client = eq.get("Client") or eq.get("client") or "Centre Principal"
                    equip_client_map[nom] = client
                mask_empty = df_inter["client"] == ""
                df_inter.loc[mask_empty, "client"] = df_inter.loc[mask_empty, "machine"].map(equip_client_map).fillna("Centre Principal")

        # Filtres cascading : Client → Équipement → Statut
        fc1, fc2, fc3 = st.columns(3)
        all_clients = sorted(df_inter["client"].unique()) if not df_inter.empty and "client" in df_inter.columns else []
        client_filter = fc1.multiselect("🏢 Filtrer par Client", options=all_clients)

        # Équipements filtrés par client sélectionné
        if client_filter:
            machines_for_client = df_inter[df_inter["client"].isin(client_filter)]["machine"].unique()
        else:
            machines_for_client = df_inter["machine"].unique() if not df_inter.empty else []
        machine_filter = fc2.multiselect("🏥 Filtrer par Équipement", options=sorted(machines_for_client))

        statut_options = ["En cours", "En attente de pièce", "Clôturée"]
        statut_filter = fc3.multiselect("📊 Filtrer par Statut", options=statut_options)

        df_filtered = df_inter.copy()
        if client_filter:
            df_filtered = df_filtered[df_filtered["client"].isin(client_filter)]
        if machine_filter:
            df_filtered = df_filtered[df_filtered["machine"].isin(machine_filter)]
        if statut_filter:
            df_filtered = df_filtered[df_filtered["statut_clean"].isin(statut_filter)]

        # ============ TABLEAU DÉTAILLÉ DES INTERVENTIONS ============
        from db_engine import get_config
        from pdf_generator import generer_pdf_intervention
        from datetime import timedelta
        devise = get_config("devise", "EUR")
        sym_map = {
            "EUR": "EUR", "USD": "USD", "GBP": "GBP", "TND": "TND",
            "MAD": "MAD", "DZD": "DZD", "XOF": "XOF", "CHF": "CHF",
            "CAD": "CAD", "SAR": "SAR", "AED": "AED", "QAR": "QAR",
        }
        sym = sym_map.get(devise, devise)

        if not df_filtered.empty:
            st.markdown("---")
            # Préparer le DataFrame pour affichage tableau
            df_table = df_filtered.copy()
            df_table["duree_h"] = df_table["duree_minutes"].fillna(0).apply(lambda x: f"{x / 60:.1f}h")
            try:
                _taux = int(float(get_config("taux_horaire_technicien", "50") or "50"))
            except (ValueError, TypeError):
                _taux = 50
            df_table["cout_fmt"] = df_table["duree_minutes"].fillna(0).apply(lambda x: f"{(x / 60) * _taux:.0f} {sym}")

            # Colonnes à afficher dans le tableau
            display_cols = {
                "date": "📅 Date",
                "client": "🏢 Client",
                "machine": "🏥 Équipement",
                "technicien": "👤 Technicien",
                "type_intervention": "🔧 Type",
                "statut_clean": "📊 Statut",
                "code_erreur": "🔢 Code Erreur",
                "description": "📝 Description",
                **({"cout_fmt": f"💰 Coût ({sym})"} if not _hide_costs else {}),
                "duree_h": "⏱️ Durée",
                "pieces_utilisees": "🔩 Pièces",
            }
            # Ne garder que les colonnes qui existent
            cols_present = [c for c in display_cols if c in df_table.columns]
            df_display = df_table[cols_present].rename(columns=display_cols)

            st.subheader(f"📋 Tableau des Interventions ({len(df_display)} résultats)")
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                height=min(400, 35 * len(df_display) + 38),
            )

            # ============ PERFORMANCE EQUIPE (en haut, bien visible) ============
            kpis_page = _calculer_kpis_equipe(df_filtered, sym)
            if kpis_page:
                score_val = kpis_page.get("score_global", 0)
                score_color = "#10b981" if score_val >= 70 else "#f59e0b" if score_val >= 40 else "#ef4444"
                score_label = "Excellente" if score_val >= 80 else "Bonne" if score_val >= 60 else "À améliorer" if score_val >= 40 else "Insuffisante"

                # Score global en grand
                st.markdown(f"""
                <div style="text-align:center; padding:16px; background: rgba({','.join(str(int(score_color.lstrip('#')[i:i+2], 16)) for i in (0,2,4))}, 0.1);
                     border: 2px solid {score_color}; border-radius:16px; margin-bottom:16px;">
                    <div style="font-size:2.5rem; font-weight:900; color:{score_color};">{score_val}/100</div>
                    <div style="font-size:1rem; color:{score_color}; font-weight:600;">{score_label}</div>
                    <div style="font-size:0.75rem; color:#94a3b8; margin-top:4px;">Score de Performance Global</div>
                </div>
                """, unsafe_allow_html=True)

                # KPIs en cartes
                k1, k2, k3, k4 = st.columns(4)
                if _hide_costs:
                    k1, k2, k3 = st.columns(3)
                    k1.metric("✅ Taux Résolution", f"{kpis_page.get('taux_resolution', 0)}%")
                    k2.metric("⏱️ MTTR (Réparations)", f"{kpis_page.get('mttr_h', 0)}h")
                    k3.metric("🔧 Correctif", f"{kpis_page.get('ratio_correctif_pct', 0)}%")
                else:
                    k1.metric("✅ Taux Résolution", f"{kpis_page.get('taux_resolution', 0)}%")
                    k2.metric("⏱️ MTTR (Réparations)", f"{kpis_page.get('mttr_h', 0)}h")
                    k3.metric("💰 Coût Moyen", f"{kpis_page.get('cout_moyen', 0):.0f} {sym}")
                    k4.metric("🔧 Correctif", f"{kpis_page.get('ratio_correctif_pct', 0)}%")

                # Tableau par technicien
                tech_stats_page = kpis_page.get("tech_stats", [])
                if tech_stats_page:
                    st.markdown("##### 👥 Performance par Technicien")
                    df_tech_perf = pd.DataFrame(tech_stats_page)
                    df_tech_perf = df_tech_perf.rename(columns={
                        "nom": "👤 Technicien",
                        "nb_interventions": "📋 Interventions",
                        "nb_cloturees": "✅ Résolues",
                        "taux_resolution": "📊 Taux (%)",
                        "mttr_h": "⏱️ MTTR (h)",
                        **({"cout_total": f"💰 Coût ({sym})"} if not _hide_costs else {}),
                    })
                    st.dataframe(df_tech_perf, use_container_width=True, hide_index=True)

                # Bouton recommandations IA
                st.markdown("---")
                st.subheader("🧠 Recommandations IA (Gemini)")

                from ai_engine import AI_AVAILABLE
                if AI_AVAILABLE:
                    if st.button("✨ Analyser la performance avec l'IA", type="primary", use_container_width=True, key="sav_ai_btn"):
                        with st.spinner("🧠 L'IA analyse les performances de l'équipe..."):
                            ai_result = _get_ai_recommendations(kpis_page, sym)
                            if ai_result:
                                st.session_state["sav_ai_reco"] = ai_result
                            else:
                                st.warning("⚠️ L'IA n'a pas pu générer de recommandations. Quota API épuisé ?")

                    # Afficher les recommandations si disponibles
                    if st.session_state.get("sav_ai_reco"):
                        ai_reco = st.session_state["sav_ai_reco"]

                        # Analyse
                        analyse = ai_reco.get("analyse", "")
                        if analyse:
                            st.info(f"📋 **Analyse :** {analyse}")

                        # Points forts / faibles
                        pf_col, pw_col = st.columns(2)
                        with pf_col:
                            points_forts = ai_reco.get("points_forts", [])
                            if points_forts:
                                st.markdown("**✅ Points forts :**")
                                for pf in points_forts:
                                    st.markdown(f"- 🟢 {pf}")
                        with pw_col:
                            points_faibles = ai_reco.get("points_faibles", [])
                            if points_faibles:
                                st.markdown("**⚠️ Points à améliorer :**")
                                for pw in points_faibles:
                                    st.markdown(f"- 🟡 {pw}")

                        # Recommandations
                        recos = ai_reco.get("recommandations", [])
                        if recos:
                            st.markdown("**🎯 Recommandations :**")
                            for reco in recos:
                                impact = reco.get("impact", "")
                                impact_color = "#ef4444" if impact == "HAUT" else "#f59e0b" if impact == "MOYEN" else "#10b981"
                                st.markdown(f"""
                                <div style="background: rgba(45,212,191,0.05); border-left: 3px solid {impact_color};
                                     border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;">
                                    <div style="font-weight:700; color:#f1f5f9; font-size:0.9rem;">
                                        {reco.get('titre', '')}
                                        <span style="background:{impact_color}; color:white; padding:2px 8px;
                                               border-radius:10px; font-size:0.7rem; margin-left:8px;">Impact {impact}</span>
                                    </div>
                                    <div style="color:#94a3b8; font-size:0.85rem; margin-top:4px;">{reco.get('description', '')}</div>
                                </div>
                                """, unsafe_allow_html=True)

                        # Objectifs
                        objectifs = ai_reco.get("objectifs", [])
                        if objectifs:
                            st.markdown("**🎯 Objectifs mesurables :**")
                            for obj in objectifs:
                                st.markdown(f"- 📌 {obj}")

                        st.caption("💡 Cliquez sur 'Générer PDF' pour inclure ces recommandations dans le rapport.")
                else:
                    st.info("🔑 Configurez `GOOGLE_API_KEY` dans `.env` pour activer les recommandations IA.")


            # ============ RAPPORT PDF PAR PÉRIODE ============
            st.markdown("---")
            st.subheader("📄 Rapport PDF des Interventions")

            col_d1, col_d2, col_d3 = st.columns([2, 2, 1])
            with col_d1:
                date_debut_pdf = st.date_input(
                    "📅 Du", value=datetime.now().date() - timedelta(days=30),
                    key="sav_pdf_date_debut"
                )
            with col_d2:
                date_fin_pdf = st.date_input(
                    "📅 Au", value=datetime.now().date(),
                    key="sav_pdf_date_fin"
                )
            with col_d3:
                st.write("")  # spacer
                gen_pdf_btn = st.button("📥 Générer PDF", use_container_width=True, key="sav_gen_pdf")

            if gen_pdf_btn:
                # Filtrer par période
                df_rapport = df_filtered.copy()
                df_rapport["date_dt"] = pd.to_datetime(df_rapport["date"], errors="coerce")
                mask = (df_rapport["date_dt"] >= pd.Timestamp(date_debut_pdf)) & \
                       (df_rapport["date_dt"] <= pd.Timestamp(date_fin_pdf) + pd.Timedelta(days=1))
                df_rapport = df_rapport[mask].sort_values("date_dt")

                if df_rapport.empty:
                    st.warning("Aucune intervention trouvée pour cette période.")
                else:
                    try:
                        from io import BytesIO
                        from reportlab.lib import colors
                        from reportlab.lib.pagesizes import A4, landscape
                        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                        from reportlab.lib.units import cm
                        from pdf_generator import draw_reportlab_header_footer

                        buffer = BytesIO()
                        doc = SimpleDocTemplate(
                            buffer, pagesize=landscape(A4),
                            topMargin=3*cm, bottomMargin=1.5*cm,
                            leftMargin=1*cm, rightMargin=1*cm,
                        )

                        styles = getSampleStyleSheet()
                        title_style = ParagraphStyle(
                            'Title2', parent=styles['Title'],
                            fontSize=16, spaceAfter=20
                        )
                        subtitle_style = ParagraphStyle(
                            'Subtitle2', parent=styles['Normal'],
                            fontSize=10, textColor=colors.grey,
                            spaceAfter=15
                        )
                        cell_style = ParagraphStyle(
                            'CellStyle', parent=styles['Normal'],
                            fontSize=7, textColor=colors.black,
                            leading=9,
                        )
                        cell_header_style = ParagraphStyle(
                            'CellHeader', parent=styles['Normal'],
                            fontSize=8, textColor=colors.HexColor('#1e3a8a'),
                            leading=10, fontName='Helvetica-Bold',
                        )

                        elements = []
                        elements.append(Paragraph(
                            "Rapport des Interventions SAV", title_style
                        ))
                        elements.append(Paragraph(
                            f"Periode : {date_debut_pdf.strftime('%d/%m/%Y')} - "
                            f"{date_fin_pdf.strftime('%d/%m/%Y')}  |  "
                            f"Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}",
                            subtitle_style
                        ))
                        elements.append(Spacer(1, 10))

                        # En-tête du tableau
                        header = [
                            Paragraph("Date", cell_header_style),
                            Paragraph("Client", cell_header_style),
                            Paragraph("Equipement", cell_header_style),
                            Paragraph("Technicien", cell_header_style),
                            Paragraph("Type", cell_header_style),
                            Paragraph("Statut", cell_header_style),
                            Paragraph("Code Err.", cell_header_style),
                            Paragraph("Description", cell_header_style),
                            Paragraph(f"Cout ({sym})", cell_header_style),
                            Paragraph("Duree", cell_header_style),
                            Paragraph("Pieces", cell_header_style),
                        ]
                        data_rows = [header]

                        for _, r in df_rapport.iterrows():
                            date_val = r["date_dt"].strftime("%d/%m/%Y") if pd.notna(r["date_dt"]) else "?"
                            cout_val = r.get("cout", 0) or 0
                            duree_val = r.get("duree_minutes", 0) or 0
                            desc_text = str(r.get("description", ""))[:80]
                            pieces_text = str(r.get("pieces_utilisees", "") or "")[:40]
                            client_val = str(r.get("client", "") or "")

                            data_rows.append([
                                Paragraph(date_val, cell_style),
                                Paragraph(client_val, cell_style),
                                Paragraph(str(r.get("machine", "")), cell_style),
                                Paragraph(str(r.get("technicien", "")), cell_style),
                                Paragraph(str(r.get("type_intervention", "")), cell_style),
                                Paragraph(str(r.get("statut_clean", r.get("statut", ""))), cell_style),
                                Paragraph(str(r.get("code_erreur", "") or ""), cell_style),
                                Paragraph(desc_text, cell_style),
                                Paragraph(f"{cout_val:.2f}", cell_style),
                                Paragraph(f"{duree_val / 60:.1f}h", cell_style),
                                Paragraph(pieces_text, cell_style),
                            ])

                        col_widths = [1.8*cm, 2.2*cm, 2.5*cm, 2.5*cm, 2*cm, 1.8*cm, 1.8*cm, 5.5*cm, 1.8*cm, 1.5*cm, 2.5*cm]
                        table = Table(data_rows, colWidths=col_widths, repeatRows=1)
                        table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 8),
                            ('FONTSIZE', (0, 1), (-1, -1), 7),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                            ('TOPPADDING', (0, 0), (-1, -1), 3),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                            ('LEFTPADDING', (0, 0), (-1, -1), 4),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                        ]))
                        elements.append(table)

                        # ============ PERFORMANCE EQUIPE (dans le PDF) ============
                        elements.append(Spacer(1, 15))

                        # Calculer les KPIs
                        kpis_pdf = _calculer_kpis_equipe(df_rapport, sym)

                        # Resume general
                        nb_total_pdf = kpis_pdf.get("nb_total", len(df_rapport))
                        nb_en_cours_pdf = kpis_pdf.get("nb_en_cours", 0)
                        nb_cloture_pdf = kpis_pdf.get("nb_cloture", 0)
                        total_cout = kpis_pdf.get("cout_total", 0)
                        total_duree = kpis_pdf.get("duree_totale_h", 0)

                        elements.append(Paragraph(
                            f"<b>Resume :</b> {nb_total_pdf} intervention(s) - "
                            f"{nb_en_cours_pdf} en cours, "
                            f"{nb_cloture_pdf} cloturee(s) | "
                            f"Cout total : {total_cout:.2f} {sym} | "
                            f"Duree totale : {total_duree:.1f}h",
                            styles['Normal']
                        ))

                        # Section Performance Equipe
                        elements.append(Spacer(1, 20))
                        perf_title = ParagraphStyle(
                            'PerfTitle', parent=styles['Heading2'],
                            fontSize=13, spaceAfter=10,
                        )
                        elements.append(Paragraph("Performance de l'equipe", perf_title))

                        # Tableau KPIs
                        kpi_header = [
                            Paragraph("Indicateur", cell_header_style),
                            Paragraph("Valeur", cell_header_style),
                            Paragraph("Interpretation", cell_header_style),
                        ]

                        score = kpis_pdf.get("score_global", 0)
                        score_label = "Excellente" if score >= 80 else "Bonne" if score >= 60 else "A ameliorer" if score >= 40 else "Insuffisante"
                        mttr_val = kpis_pdf.get("mttr_h", 0)
                        mttr_label = "Excellent" if mttr_val <= 1 else "Bon" if mttr_val <= 3 else "A ameliorer" if mttr_val <= 6 else "Critique"
                        taux_res = kpis_pdf.get("taux_resolution", 0)
                        taux_label = "Excellent" if taux_res >= 90 else "Bon" if taux_res >= 70 else "A ameliorer" if taux_res >= 50 else "Critique"
                        ratio_corr = kpis_pdf.get("ratio_correctif_pct", 0)
                        ratio_label = "Ideal" if ratio_corr <= 30 else "Bon" if ratio_corr <= 50 else "Trop de correctif" if ratio_corr <= 70 else "Excessif"

                        kpi_rows = [kpi_header]
                        kpi_data = [
                            ("Score Global", f"{score}/100", score_label),
                            ("Taux de Resolution", f"{taux_res}%", taux_label),
                            ("MTTR (Temps Moyen Reparation)", f"{mttr_val}h", mttr_label),
                            ("Cout Moyen / Intervention", f"{kpis_pdf.get('cout_moyen', 0):.2f} {sym}", ""),
                            ("Ratio Correctif / Total", f"{ratio_corr}% ({kpis_pdf.get('nb_corrective', 0)}C / {kpis_pdf.get('nb_preventive', 0)}P)", ratio_label),
                            ("Duree Totale", f"{total_duree:.1f}h", ""),
                        ]
                        for label, val, interp in kpi_data:
                            kpi_rows.append([
                                Paragraph(label, cell_style),
                                Paragraph(str(val), cell_style),
                                Paragraph(interp, cell_style),
                            ])

                        kpi_table = Table(kpi_rows, colWidths=[8*cm, 6*cm, 6*cm], repeatRows=1)
                        kpi_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 8),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('TOPPADDING', (0, 0), (-1, -1), 4),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ]))
                        elements.append(kpi_table)

                        # Tableau performance par technicien
                        tech_stats = kpis_pdf.get("tech_stats", [])
                        if tech_stats:
                            elements.append(Spacer(1, 15))
                            elements.append(Paragraph("Performance par Technicien", perf_title))

                            tech_header = [
                                Paragraph("Technicien", cell_header_style),
                                Paragraph("Interventions", cell_header_style),
                                Paragraph("Resolues", cell_header_style),
                                Paragraph("Taux (%)", cell_header_style),
                                Paragraph("MTTR (h)", cell_header_style),
                                Paragraph(f"Cout ({sym})", cell_header_style),
                            ]
                            tech_rows = [tech_header]
                            for ts in tech_stats:
                                tech_rows.append([
                                    Paragraph(ts["nom"], cell_style),
                                    Paragraph(str(ts["nb_interventions"]), cell_style),
                                    Paragraph(str(ts["nb_cloturees"]), cell_style),
                                    Paragraph(f"{ts['taux_resolution']}%", cell_style),
                                    Paragraph(f"{ts['mttr_h']}h", cell_style),
                                    Paragraph(f"{ts['cout_total']:.2f}", cell_style),
                                ])
                            tech_table = Table(tech_rows, colWidths=[5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 3*cm], repeatRows=1)
                            tech_table.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.white),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 8),
                                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                ('TOPPADDING', (0, 0), (-1, -1), 4),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                            ]))
                            elements.append(tech_table)

                        # Recommandations IA
                        ai_reco = st.session_state.get("sav_ai_reco")
                        if ai_reco:
                            elements.append(Spacer(1, 20))
                            elements.append(Paragraph("Recommandations IA (Gemini)", perf_title))

                            reco_style = ParagraphStyle(
                                'RecoStyle', parent=styles['Normal'],
                                fontSize=8, textColor=colors.black,
                                leading=11,
                            )

                            # Analyse
                            analyse = ai_reco.get("analyse", "")
                            if analyse:
                                elements.append(Paragraph(f"<b>Analyse :</b> {analyse}", reco_style))
                                elements.append(Spacer(1, 6))

                            # Points forts
                            points_forts = ai_reco.get("points_forts", [])
                            if points_forts:
                                elements.append(Paragraph("<b>Points forts :</b>", reco_style))
                                elements.append(Spacer(1, 3))
                                for pf in points_forts:
                                    elements.append(Paragraph(f"  + {pf}", reco_style))
                                elements.append(Spacer(1, 6))

                            # Points faibles
                            points_faibles = ai_reco.get("points_faibles", [])
                            if points_faibles:
                                elements.append(Paragraph("<b>Points a ameliorer :</b>", reco_style))
                                elements.append(Spacer(1, 3))
                                for pw in points_faibles:
                                    elements.append(Paragraph(f"  - {pw}", reco_style))
                                elements.append(Spacer(1, 6))

                            # Recommandations
                            recos = ai_reco.get("recommandations", [])
                            for i, reco in enumerate(recos, 1):
                                titre = reco.get("titre", "")
                                desc = reco.get("description", "")
                                impact = reco.get("impact", "")
                                elements.append(Paragraph(
                                    f"<b>{i}. {titre}</b> [Impact: {impact}] - {desc}",
                                    reco_style
                                ))
                                elements.append(Spacer(1, 4))

                            # Objectifs
                            objectifs = ai_reco.get("objectifs", [])
                            if objectifs:
                                elements.append(Spacer(1, 6))
                                obj_text = "  |  ".join(objectifs)
                                elements.append(Paragraph(f"<b>Objectifs :</b> {obj_text}", reco_style))

                        doc.build(
                            elements, 
                            onFirstPage=draw_reportlab_header_footer, 
                            onLaterPages=draw_reportlab_header_footer
                        )
                        pdf_bytes = buffer.getvalue()

                        st.download_button(
                            "📥 Télécharger le rapport PDF",
                            data=pdf_bytes,
                            file_name=f"rapport_interventions_{date_debut_pdf}_{date_fin_pdf}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                        st.success(
                            f"✅ Rapport généré : **{nb_total_pdf}** intervention(s) — "
                            f"Coût total : **{total_cout:.2f} {sym}** — Score performance : **{score}/100**"
                        )
                    except ImportError:
                        st.error("❌ Module `reportlab` manquant. Ajoutez-le dans requirements.txt")
                    except Exception as e:
                        st.error(f"❌ Erreur génération PDF : {e}")

            # ============ TABLEAU INTERACTIF AgGrid ============
            st.markdown("---")
            st.subheader("📊 Tableau Interactif des Interventions")
            try:
                from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
                _ag_cols = ["date", "machine", "technicien", "type_intervention", "statut_clean", "code_erreur", "type_erreur", "priorite"]
                _ag_cols_present = [c for c in _ag_cols if c in df_filtered.columns]
                df_ag = df_filtered[_ag_cols_present].copy()
                df_ag.columns = [{"date": "📅 Date", "machine": "🖥️ Machine", "technicien": "👷 Technicien",
                                 "type_intervention": "🔧 Type", "statut_clean": "📊 Statut",
                                 "code_erreur": "🔴 Code", "type_erreur": "📌 Type Erreur",
                                 "priorite": "🚨 Priorité"}.get(c, c) for c in _ag_cols_present]
                gb = GridOptionsBuilder.from_dataframe(df_ag)
                gb.configure_pagination(paginationAutoPageSize=True)
                gb.configure_default_column(filterable=True, sortable=True, resizable=True)
                gb.configure_selection(selection_mode="single", use_checkbox=False)
                grid_opts = gb.build()
                AgGrid(df_ag, gridOptions=grid_opts, update_mode=GridUpdateMode.SELECTION_CHANGED,
                       theme="streamlit", height=350, fit_columns_on_grid_load=True)
            except Exception:
                # Fallback si AgGrid pas disponible
                if not df_filtered.empty:
                    st.dataframe(df_filtered[["date", "machine", "technicien", "type_intervention", "statut_clean"]].head(50),
                                use_container_width=True, hide_index=True)

            # ============ DÉTAILS & ACTIONS PAR INTERVENTION ============
            st.markdown("---")
            st.subheader("🔍 Détails & Actions par Intervention")

            # Pagination pour éviter de surcharger la page
            PAGE_SIZE = 20
            total_items = len(df_filtered)
            total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
            current_page_num = st.number_input(
                f"Page (1-{total_pages}) — {total_items} interventions",
                min_value=1, max_value=total_pages, value=1, step=1,
                key="sav_detail_page"
            )
            start_idx = (current_page_num - 1) * PAGE_SIZE
            end_idx = min(start_idx + PAGE_SIZE, total_items)
            df_page = df_filtered.iloc[start_idx:end_idx]
            st.caption(f"Affichage {start_idx+1}–{end_idx} sur {total_items}")

            for idx, row in df_page.iterrows():
                interv = row.to_dict()
                date_str = str(interv.get('date', ''))[:16]
                machine = interv.get('machine', '?')
                type_i = interv.get('type_intervention', '?')
                statut = interv.get('statut_clean', '?')
                cout_val = interv.get('cout', 0) or 0
                # Si coût = 0 mais durée > 0, calculer depuis taux_horaire
                if cout_val == 0:
                    _d = (interv.get('duree_minutes', 0) or 0)
                    if _d > 0:
                        cout_val = round((_d / 60) * _taux, 2)
                icon = "✅" if statut == "Clôturée" else "⏳" if statut == "En attente de pièce" else "🔄" if statut == "En cours" else "📋"

                _exp_label = f"{icon} {date_str} - {machine} - {type_i}" if _hide_costs else f"{icon} {date_str} - {machine} - {type_i} - {cout_val:.0f} {sym}"
                with st.expander(_exp_label):
                    # En-tête : détails + bouton PDF alignés
                    h1, h2, h3 = st.columns([3, 3, 1])
                    h1.markdown(f"**Technicien :** {interv.get('technicien', '-')}")
                    h1.markdown(f"**Durée :** {(interv.get('duree_minutes', 0) or 0) / 60:.1f}h")
                    h1.markdown(f"**Statut :** {statut}")
                    if not _hide_costs:
                        h2.markdown(f"**Coût :** {cout_val:.2f} {sym}")
                    h2.markdown(f"**Code erreur :** `{interv.get('code_erreur', '-')}`")
                    type_err_val = interv.get('type_erreur', '')
                    if type_err_val:
                        h2.markdown(f"**Type erreur :** {type_err_val}")
                    priorite_val = interv.get('priorite', '')
                    if priorite_val:
                        h2.markdown(f"**Priorité :** {priorite_val}")
                    # PDF en haut à droite de l'expander
                    pdf_bytes_ind = generer_pdf_intervention(interv, devise)
                    safe_machine = str(machine).replace(' ', '_')[:20]
                    filename = f"rapport_{safe_machine}_{date_str[:10]}.pdf"
                    h3.download_button(
                        "📄 PDF",
                        data=pdf_bytes_ind,
                        file_name=filename,
                        mime="application/pdf",
                        key=f"pdf_sav_{idx}",
                        use_container_width=True,
                    )
                    st.markdown(f"**Description :** {interv.get('description', '-')}")
                    pieces = str(interv.get('pieces_utilisees', '') or '').strip()
                    # Nettoyer les entrées vides comme "| (x1 @ 0)"
                    if pieces:
                        clean_parts = [p.strip() for p in pieces.split("|") if p.strip() and "(x" in p and "@ 0)" not in p]
                        pieces = " | ".join(clean_parts)
                    if pieces:
                        st.markdown(f"**Pièces :** {pieces}")
                    notes = interv.get('notes', '')
                    if notes:
                        st.markdown(f"**Notes :** {notes}")

                    # Changement de statut rapide
                    if statut != "Clôturée" and require_role("Admin", "Manager", "Technicien"):
                        sc1, sc2 = st.columns(2)
                        statut_opts = ["En cours", "En attente de pièce", "Clôturée"]
                        current_idx = statut_opts.index(statut) if statut in statut_opts else 0
                        new_st = sc1.selectbox("Statut", statut_opts, index=current_idx, key=f"st_sel_{idx}")
                        current_te = interv.get('type_erreur', '')
                        te_opts = [""] + TYPES_ERREUR
                        te_idx = te_opts.index(current_te) if current_te in te_opts else 0
                        new_te = sc2.selectbox("📌 Type d'erreur", te_opts, index=te_idx, key=f"te_sel_{idx}")
                        sc3, sc4 = st.columns(2)
                        current_pr = interv.get('priorite', '')
                        pr_opts = [""] + PRIORITES
                        pr_idx = pr_opts.index(current_pr) if current_pr in pr_opts else 0
                        new_pr = sc3.selectbox("🚨 Priorité", pr_opts, index=pr_idx, key=f"pr_sel_{idx}")
                        changed = (new_st != statut) or (new_te != current_te) or (new_pr != current_pr)
                        if changed:
                            if st.button("Mettre à jour", key=f"upd_st_{idx}"):
                                if new_st != statut:
                                    update_intervention_statut(interv.get("id"), new_st)
                                with get_db() as conn:
                                    conn.execute("UPDATE interventions SET type_erreur=?, priorite=? WHERE id=?", (new_te, new_pr, interv.get("id")))
                                st.success(f"Mis à jour: statut={new_st}, type_erreur={new_te}, priorité={new_pr}")
                                st.rerun()

                    # Boutons d'action
                    btn_cols = st.columns([2, 2, 1] if require_role("Admin", "Manager") else [2, 2])
                    
                    # Bouton clôturer → ouvre une modale st.dialog
                    if statut != "Clôturée" and require_role("Admin", "Manager", "Technicien"):
                        if btn_cols[0].button("📋 Clôturer", key=f"btn_open_clot_{idx}", type="primary", use_container_width=True):
                            st.session_state[f"_clot_interv_{idx}"] = interv

                    # Bouton supprimer (Admin/Manager uniquement)
                    if require_role("Admin", "Manager"):
                        if btn_cols[-1].button("🗑️ Supprimer", key=f"btn_del_interv_{idx}", type="secondary", use_container_width=True):
                            st.session_state[f"_confirm_del_{idx}"] = True

                        if st.session_state.get(f"_confirm_del_{idx}"):
                            st.warning(f"⚠️ Supprimer l'intervention **{machine}** ({date_str}) ?")
                            dc1, dc2 = st.columns(2)
                            if dc1.button("✅ Confirmer", key=f"confirm_del_{idx}", type="primary"):
                                interv_id = interv.get("id")
                                with get_db() as conn:
                                    conn.execute("DELETE FROM interventions WHERE id = ?", (interv_id,))
                                # Si plus aucune intervention En cours pour cet équipement → Opérationnel
                                with get_db() as conn:
                                    remaining = conn.execute(
                                        "SELECT COUNT(*) as cnt FROM interventions WHERE machine = ? AND statut = 'En cours'",
                                        (machine,)
                                    ).fetchone()
                                    if remaining and remaining["cnt"] == 0:
                                        conn.execute("UPDATE equipements SET statut = ? WHERE nom = ?", ("Opérationnel", machine))
                                st.success("✅ Intervention supprimée !")
                                del st.session_state[f"_confirm_del_{idx}"]
                                st.rerun()
                            if dc2.button("❌ Annuler", key=f"cancel_del_{idx}"):
                                del st.session_state[f"_confirm_del_{idx}"]
                                st.rerun()

                    # Modale de clôture
                    if f"_clot_interv_{idx}" in st.session_state:
                        @st.dialog(f"Clôturer — {machine}", width="large")
                        def _dialog_cloturer(interv_data, dialog_idx):
                            is_corr = (interv_data.get("type_intervention") == "Corrective")
                            if is_corr:
                                d_prob = st.text_area("Problème constaté *", key=f"d_qp_{dialog_idx}")
                                d_cause = st.text_area("Cause racine *", key=f"d_qc_{dialog_idx}")
                                d_sol = st.text_area("Solution appliquée *", key=f"d_qs_{dialog_idx}")
                            else:
                                d_prob = "RAS"
                                d_cause = "N/A"
                                d_sol = st.text_area("Actions réalisées *", key=f"d_qs_{dialog_idx}")

                            c1, c2 = st.columns(2)
                            d_te_opts = [""] + TYPES_ERREUR
                            d_te_current = interv_data.get('type_erreur', '')
                            d_te_idx = d_te_opts.index(d_te_current) if d_te_current in d_te_opts else 0
                            d_type_erreur = c1.selectbox("📌 Type d'erreur", d_te_opts, index=d_te_idx, key=f"d_te_{dialog_idx}")
                            d_pr_opts = [""] + PRIORITES
                            d_pr_current = interv_data.get('priorite', '')
                            d_pr_idx = d_pr_opts.index(d_pr_current) if d_pr_current in d_pr_opts else 0
                            d_priorite = c2.selectbox("🚨 Priorité", d_pr_opts, index=d_pr_idx, key=f"d_pr_{dialog_idx}")

                            st.markdown("**📦 Pièces de Rechange**")
                            df_pcs = lire_pieces()
                            d_pieces = []
                            if not df_pcs.empty:
                                pcs_map = {f"{p.reference} - {p.designation} (Stock: {p.stock_actuel})": p for p in df_pcs.itertuples()}
                                sel_pcs = st.multiselect("Sélectionner pièces", options=list(pcs_map.keys()), key=f"d_pc_{dialog_idx}")
                                for pk in sel_pcs:
                                    part = pcs_map[pk]
                                    qq = st.number_input(f"Qté {part.reference}", min_value=1, value=1, key=f"d_qty_{part.reference}_{dialog_idx}")
                                    d_pieces.append({"ref": part.reference, "qty": qq, "designation": part.designation, "prix_unitaire": part.prix_unitaire if hasattr(part, "prix_unitaire") else 0})
                            else:
                                st.info("Aucune pièce en stock.")

                            d_duree_h = st.number_input("⏱️ Durée (heures)", min_value=0.0, value=(interv_data.get("duree_minutes", 0) or 0) / 60, step=0.5, key=f"d_dur_{dialog_idx}")
                            d_duree = int(d_duree_h * 60)

                            st.markdown("---")
                            bc1, bc2 = st.columns(2)
                            if bc1.button("✅ Valider la clôture", type="primary", use_container_width=True, key=f"d_val_{dialog_idx}"):
                                if not d_sol:
                                    st.error("La solution/actions est obligatoire.")
                                else:
                                    ok, msg = cloturer_intervention(interv_data.get("id"), d_prob, d_cause, d_sol, pieces_a_deduire=d_pieces, duree_minutes=d_duree)
                                    if ok:
                                        if d_type_erreur or d_priorite:
                                            with get_db() as conn:
                                                conn.execute("UPDATE interventions SET type_erreur=?, priorite=? WHERE id=?", (d_type_erreur, d_priorite, interv_data.get("id")))
                                        st.success("✅ Intervention clôturée !")
                                        try:
                                            from notifications import get_notifier
                                            notifier = get_notifier()
                                            _tech_nom = interv_data.get("technicien", "")
                                            _notes = str(interv_data.get("notes", ""))
                                            _client = ""
                                            if _notes.startswith("[") and "]" in _notes:
                                                _client = _notes[1:_notes.index("]")]
                                            notifier.notifier_cloture_intervention(
                                                machine=str(interv_data.get("machine", "")),
                                                techniciens_tags=[(_tech_nom, "")],
                                                probleme=d_prob,
                                                solution=d_sol,
                                                client=_client,
                                            )
                                        except Exception:
                                            pass
                                        # Remettre l'équipement en Opérationnel si plus aucune intervention En cours
                                        try:
                                            _machine_name = str(interv_data.get("machine", ""))
                                            with get_db() as conn:
                                                remaining = conn.execute(
                                                    "SELECT COUNT(*) as cnt FROM interventions WHERE machine = ? AND statut = 'En cours'",
                                                    (_machine_name,)
                                                ).fetchone()
                                                if remaining and remaining["cnt"] == 0:
                                                    conn.execute("UPDATE equipements SET statut = ? WHERE nom = ?", ("Opérationnel", _machine_name))
                                        except Exception:
                                            pass
                                        # Fermer la modale
                                        del st.session_state[f"_clot_interv_{dialog_idx}"]
                                        st.rerun()
                                    else:
                                        st.error(msg)
                            if bc2.button("❌ Annuler", use_container_width=True, key=f"d_cancel_{dialog_idx}"):
                                del st.session_state[f"_clot_interv_{dialog_idx}"]
                                st.rerun()

                        _dialog_cloturer(st.session_state[f"_clot_interv_{idx}"], idx)

            # ============ EXPORTS ============
            st.markdown("---")
            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                from io import BytesIO
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_filtered.to_excel(writer, sheet_name='Interventions', index=False)
                st.download_button(
                    "📊 Exporter tout en Excel",
                    data=output.getvalue(),
                    file_name="sav_export.xlsx",
                    use_container_width=True,
                )
        else:
            st.info("Aucune intervention trouvée pour les filtres sélectionnés.")

    # ==========================================
    # ONGLET 2 : GESTION ÉQUIPE (MANAGER)
    # ==========================================
    with tab_team:
        if require_role("Admin"):
            c1, c2 = st.columns([1, 3])
            
            with c1:
                st.subheader("Ajouter un Technicien")
                with st.form("add_tech_form"):
                    new_nom = st.text_input("Nom")
                    new_prenom = st.text_input("Prénom")
                    new_qualif = st.selectbox("Qualification", ["Niveau 1", "Niveau 2", "Expert", "Stagiaire"])
                    new_spec = st.text_input("Spécialité", "Généraliste")
                    new_tel = st.text_input("Téléphone")
                    new_telegram = st.text_input("Telegram (@username)", help="Pour les notifications et tags")
                    submitted = st.form_submit_button("Ajouter")
                    if submitted and new_nom and new_prenom:
                        ajouter_technicien({
                            "nom": new_nom, "prenom": new_prenom, "qualification": new_qualif,
                            "specialite": new_spec, "telephone": new_tel, "telegram_id": new_telegram
                        })
                        st.success("Technicien ajouté !")
                        st.rerun()

            with c2:
                st.subheader("Liste des Techniciens")
                df_tech = lire_techniciens()
                if not df_tech.empty:
                    st.dataframe(df_tech, use_container_width=True, hide_index=True)
                    
                    # Suppression
                    tech_opts = {f"{r.nom} {r.prenom}": r.id for r in df_tech.itertuples()}
                    
                    st.markdown("---")
                    st.subheader("Modifier / Supprimer")
                    
                    tech_to_edit_key = st.selectbox("Sélectionner un technicien", [""] + list(tech_opts.keys()))
                    
                    if tech_to_edit_key:
                        tech_id = tech_opts[tech_to_edit_key]
                        tech_data = df_tech[df_tech["id"] == tech_id].iloc[0]
                        
                        with st.popover("✏️ Modifier"):
                            with st.form("edit_tech_form"):
                                e_nom = st.text_input("Nom", value=tech_data["nom"])
                                e_prenom = st.text_input("Prénom", value=tech_data["prenom"])
                                e_qualif = st.selectbox("Qualification", ["Niveau 1", "Niveau 2", "Expert", "Stagiaire"], index=["Niveau 1", "Niveau 2", "Expert", "Stagiaire"].index(tech_data["qualification"]) if tech_data["qualification"] in ["Niveau 1", "Niveau 2", "Expert", "Stagiaire"] else 0)
                                e_spec = st.text_input("Spécialité", value=tech_data["specialite"])
                                e_tel = st.text_input("Téléphone", value=tech_data["telephone"])
                                e_telegram = st.text_input("Telegram", value=tech_data["telegram_id"] if pd.notna(tech_data["telegram_id"]) else "")
                                
                                if st.form_submit_button("Enregistrer modifications"):
                                    update_technicien(tech_id, {
                                        "nom": e_nom, "prenom": e_prenom, "qualification": e_qualif,
                                        "specialite": e_spec, "telephone": e_tel, "telegram_id": e_telegram
                                    })
                                    st.success("Modifications enregistrées !")
                                    st.rerun()

                        st.write("")
                        if st.button("🗑️ Supprimer ce technicien", type="primary", key=f"del_tech_btn_{tech_id}"):
                            st.session_state[f"confirm_del_tech_{tech_id}"] = True

                        if st.session_state.get(f"confirm_del_tech_{tech_id}", False):
                            st.warning(f"⚠️ Confirmer la suppression de {tech_data['nom']} {tech_data['prenom']} ?")
                            c_yes, c_no = st.columns(2)
                            if c_yes.button("✅ Oui", key=f"del_tech_yes_{tech_id}", type="primary", use_container_width=True):
                                from db_engine import log_audit
                                username = get_current_user().get("username", "admin")
                                supprimer_technicien(tech_id)
                                log_audit(username, "TECH_DELETED", f"{tech_data['nom']} {tech_data['prenom']}", "SAV")
                                del st.session_state[f"confirm_del_tech_{tech_id}"]
                                st.success("Technicien supprimé !")
                                st.rerun()
                            if c_no.button("❌ Non", key=f"del_tech_no_{tech_id}", use_container_width=True):
                                del st.session_state[f"confirm_del_tech_{tech_id}"]
                                st.rerun()
                else:
                    st.info("Aucun technicien enregistré.")
        else:
            st.warning("🔒 Section réservée aux administrateurs.")

    # ==========================================
    # ONGLET 3 : MODE TABLETTE (TECHNICIEN)
    # ==========================================
    with tab_tablet:
        st.markdown("### 📱 Fiche d'Intervention Terrain")
        
        machines = lire_equipements()
        techs = lire_techniciens()
        tech_opts = [f"{r.nom} {r.prenom}" for r in techs.itertuples()] if not techs.empty else []
        
        # Map pour retrouver le telegram_id
        tech_telegram_map = {}
        if not techs.empty:
            for r in techs.itertuples():
                key = f"{r.nom} {r.prenom}"
                tech_telegram_map[key] = r.telegram_id if hasattr(r, 'telegram_id') else ""

        # --- SECTION NOUVELLE INTERVENTION (visible uniquement si prefill) ---
        _prefill = st.session_state.get("prefill_intervention", {})
        if _prefill:
            st.markdown("---")
            st.markdown("#### ⚡ Nouvelle Intervention Rapide")
            st.success(f"⚡ **Intervention rapide** — Machine : **{_prefill.get('machine', '')}** ({_prefill.get('client', '')})")

            # --- Sélection Client → Machine ---
            if not machines.empty:
                if "Client" not in machines.columns:
                    machines["Client"] = "Centre Principal"

                clients_uniques = sorted(machines["Client"].fillna("Non spécifié").unique().tolist())
                _pf_client = _prefill.get("client", "")
                _pf_client_idx = clients_uniques.index(_pf_client) if _pf_client in clients_uniques else 0
                selected_client = st.selectbox(
                    "🏢 Client",
                    clients_uniques,
                    index=_pf_client_idx,
                    key="tablet_client_select"
                )

                df_client_machines = machines[machines["Client"] == selected_client]
                machine_opts = df_client_machines["Nom"].tolist()

                if not machine_opts:
                    st.warning(f"⚠️ Aucun équipement pour **{selected_client}**.")
                    machine_opts = ["Aucun équipement"]

                st.info(f"🏥 **{selected_client}** — {len(machine_opts)} équipement(s)")
            else:
                selected_client = "Non spécifié"
                machine_opts = ["Machine 1"]

            # Pré-sélection machine et type
            _pf_machine = _prefill.get("machine", "")
            _pf_mach_idx = machine_opts.index(_pf_machine) if _pf_machine in machine_opts else 0
            _type_opts = ["Corrective", "Préventive"]
            _pf_type = _prefill.get("type", "Corrective")
            _pf_type_idx = _type_opts.index(_pf_type) if _pf_type in _type_opts else 0

            with st.form("new_interv_tablet"):
                c1, c2 = st.columns(2)
                f_mach = c1.selectbox("Machine", machine_opts, index=_pf_mach_idx)
                f_techs = c2.multiselect("Technicien(s)", tech_opts, default=tech_opts[:1] if tech_opts else [])
                f_type = st.selectbox("Type", _type_opts, index=_pf_type_idx)
                fc1, fc2 = st.columns(2)
                f_type_erreur = fc1.selectbox("📌 Type d'erreur", [""] + TYPES_ERREUR, key="tablet_type_erreur")
                f_priorite = fc2.selectbox("🚨 Priorité", PRIORITES, index=0, key="tablet_priorite")  # Haute par défaut
                f_desc = st.text_area("Description du problème")
                
                if st.form_submit_button("⚡ Démarrer Intervention", type="primary", use_container_width=True):
                    if f_mach == "Aucun équipement":
                        st.error("Veuillez d'abord ajouter un équipement pour ce client.")
                    elif not f_techs:
                        st.error("Veuillez sélectionner au moins un technicien.")
                    else:
                        display_name = f"{f_mach} ({selected_client})"
                        tech_str = ", ".join(f_techs)
                        interv_data = {
                            "machine": f_mach, "technicien": tech_str,
                            "type_intervention": f_type, "description": f_desc,
                            "statut": "En cours",
                            "notes": f"[{selected_client}]",
                            "code_erreur": "",
                            "type_erreur": f_type_erreur,
                            "priorite": f_priorite,
                        }
                        ajouter_intervention(interv_data)
                        st.success(f"✅ Intervention créée pour **{display_name}** !")
                        
                        # Notification Telegram
                        try:
                            from notifications import get_notifier
                            notifier = get_notifier()
                            st.info(f"🔍 Debug Telegram: telegram_ok={notifier.telegram_ok}, token={bool(notifier.telegram_token)}, chat_id={bool(notifier.telegram_chat_id)}")
                            if notifier.telegram_ok:
                                tech_tags = [(t, tech_telegram_map.get(t, "")) for t in f_techs]
                                notifier.notifier_nouvelle_intervention(
                                    f_mach, tech_tags, f_desc, f_type, client=selected_client
                                )
                                st.success("📨 Notification Telegram envoyée !")
                            else:
                                st.warning("⚠️ Telegram non configuré (telegram_ok=False)")
                        except Exception as tg_err:
                            st.error(f"❌ Erreur Telegram : {tg_err}")
                        
                        # Sync vers SIC Terrain
                        try:
                            import os, urllib.request, json as json_mod
                            from dotenv import load_dotenv
                            load_dotenv()
                            terrain_url = os.environ.get("SIC_TERRAIN_URL", "").strip().rstrip("/")
                            admin_pwd = os.environ.get("SIC_TERRAIN_ADMIN_PWD", "admin")
                            st.info(f"🔍 Debug SIC Terrain: URL={terrain_url}, pwd={bool(admin_pwd)}")
                            if terrain_url:
                                login_data = json_mod.dumps({
                                    "username": "admin",
                                    "password": admin_pwd,
                                }).encode("utf-8")
                                login_req = urllib.request.Request(
                                    f"{terrain_url}/api/auth/login",
                                    data=login_data,
                                    headers={"Content-Type": "application/json"},
                                )
                                with urllib.request.urlopen(login_req, timeout=10) as resp:
                                    token = json_mod.loads(resp.read()).get("token", "")

                                if token:
                                    interv_json = json_mod.dumps(interv_data).encode("utf-8")
                                    create_req = urllib.request.Request(
                                        f"{terrain_url}/api/interventions",
                                        data=interv_json,
                                        headers={
                                            "Content-Type": "application/json",
                                            "Authorization": f"Bearer {token}",
                                        },
                                        method="POST",
                                    )
                                    with urllib.request.urlopen(create_req, timeout=10) as resp:
                                        pass
                                    st.success("🔧 Intervention synchronisée avec SIC Terrain !")
                                else:
                                    st.warning("⚠️ Token SIC Terrain manquant")
                            else:
                                st.warning("⚠️ SIC_TERRAIN_URL non configuré dans .env")
                        except Exception as sync_err:
                            st.error(f"❌ Sync SIC Terrain échouée : {sync_err}")
                        
                        # Effacer le prefill + délai pour voir les messages
                        st.session_state.pop("prefill_intervention", None)
                        import time; time.sleep(5)
                        st.rerun()

            st.markdown("---")

        # --- SECTION MODIFIER / CLÔTURER ---
        st.markdown("#### 📋 Modifier / Clôturer une intervention")
        # Toujours recharger les données les plus récentes
        df_pending = lire_interventions()
        # Filtrer celles non clôturées
        if not df_pending.empty:
            # Garder uniquement les interventions non clôturées
            df_pending = df_pending[df_pending["statut"] != "Cloturee"]
            
            if df_pending.empty:
                st.info("Aucune intervention en cours.")
            else:
                # Extraire les clients depuis les notes [Client]
                def _extract_client(notes):
                    n = str(notes or "")
                    if n.startswith("[") and "]" in n:
                        return n[1:n.index("]")]
                    return "—"
                df_pending = df_pending.copy()
                df_pending["_client"] = df_pending["notes"].apply(_extract_client)
                clients_actifs = sorted(df_pending["_client"].unique().tolist())
                
                # Filtre client
                client_options = ["Tous les clients"] + clients_actifs
                sel_client_tablet = st.selectbox("🏢 Filtrer par Client", client_options, key="tablet_client_filter")
                
                if sel_client_tablet != "Tous les clients":
                    df_pending = df_pending[df_pending["_client"] == sel_client_tablet]
                
                interv_opts = {f"{r.date} - {r.machine} ({r.description[:30]}...)": r for r in df_pending.itertuples()}
                sel_interv_key = st.selectbox("Sélectionner l'intervention à traiter", list(interv_opts.keys()))
                
                if sel_interv_key:
                    interv = interv_opts[sel_interv_key]
                    
                    st.markdown(f"#### 🔧 Intervention #{interv.id} sur **{interv.machine}**")
                    
                    # Détails complets de l'intervention
                    d1, d2 = st.columns(2)
                    d1.markdown(f"**📅 Date :** {interv.date}")
                    d1.markdown(f"**👷 Technicien :** {interv.technicien}")
                    d1.markdown(f"**🔧 Type :** {interv.type_intervention}")
                    d1.markdown(f"**📋 Statut :** {interv.statut}")
                    d2.markdown(f"**🔢 Code erreur :** `{interv.code_erreur if interv.code_erreur else '-'}`")
                    if not _hide_costs:
                        d2.markdown(f"**💰 Coût :** {(interv.cout or 0):.2f}")
                    d2.markdown(f"**⌚️ Durée :** {((interv.duree_minutes or 0) / 60):.1f}h")
                    type_err_disp = getattr(interv, 'type_erreur', '') or ''
                    priorite_disp = getattr(interv, 'priorite', '') or ''
                    if type_err_disp:
                        d2.markdown(f"**📌 Type erreur :** {type_err_disp}")
                    if priorite_disp:
                        d2.markdown(f"**🚨 Priorité :** {priorite_disp}")
                    notes_val = interv.notes if hasattr(interv, 'notes') and interv.notes else "-"
                    d2.markdown(f"**📝 Notes :** {notes_val}")
                    desc_val = interv.description if interv.description else "-"
                    st.markdown(f"**📄 Description :** {desc_val}")

                    # Changement de statut + Rapport technique dans un seul formulaire
                    st.markdown("---")
                    with st.form(f"form_modifier_cloture_{interv.id}"):
                        statut_opts = ["En cours", "En attente de pièce", "Clôturée"]
                        current_statut = interv.statut or "En cours"
                        current_idx = statut_opts.index(current_statut) if current_statut in statut_opts else 0
                        new_statut = st.selectbox("📋 Statut de l'intervention", statut_opts, index=current_idx, key="edit_statut_tablet")
                        # Type d'erreur et Priorité
                        te_col, pr_col = st.columns(2)
                        current_te_tab = getattr(interv, 'type_erreur', '') or ''
                        te_opts_tab = [""] + TYPES_ERREUR
                        te_idx_tab = te_opts_tab.index(current_te_tab) if current_te_tab in te_opts_tab else 0
                        new_te_tab = te_col.selectbox("📌 Type d'erreur", te_opts_tab, index=te_idx_tab, key="edit_te_tablet")
                        current_pr_tab = getattr(interv, 'priorite', '') or ''
                        pr_opts_tab = [""] + PRIORITES
                        pr_idx_tab = pr_opts_tab.index(current_pr_tab) if current_pr_tab in pr_opts_tab else 0
                        new_pr_tab = pr_col.selectbox("🚨 Priorité", pr_opts_tab, index=pr_idx_tab, key="edit_pr_tablet")

                        st.markdown("---")
                        st.markdown("**Rapport Technique**")
                        
                        # LOGIQUE CONDITIONNELLE SELON TYPE
                        is_corrective = (interv.type_intervention == "Corrective")
                        
                        if is_corrective:
                            st.caption("Maintenance Corrective : Le diagnostic complet est requis.")
                            
                            # Auto-remplir cause/solution depuis la base de connaissances
                            prefill_cause = interv.cause if interv.cause else ""
                            prefill_solution = interv.solution if interv.solution else ""
                            if hasattr(interv, "code_erreur") and interv.code_erreur and (not prefill_cause or not prefill_solution):
                                _, sol_db_cloture = lire_base()
                                sol_match = sol_db_cloture.get(interv.code_erreur)
                                if sol_match:
                                    if not prefill_cause:
                                        prefill_cause = sol_match.get("Cause", "")
                                    if not prefill_solution:
                                        prefill_solution = sol_match.get("Solution", "")
                                    st.success(f"Base de connaissances : solution trouvee pour le code **{interv.code_erreur}**")
                            
                            prob = st.text_area("Problème constaté *", value=interv.probleme if interv.probleme else "")
                            res_cause = st.text_area("Cause racine *", value=prefill_cause, help="Sera ajoute a la base de connaissances")
                            res_solution = st.text_area("Solution appliquée *", value=prefill_solution, help="Sera ajoute a la base de connaissances")
                        else:
                            st.caption(f"ℹ️ {interv.type_intervention} : Décrivez les actions effectuées.")
                            prob = "RAS" # Valeur par défaut pour DB
                            res_cause = "N/A" # Valeur par défaut pour DB
                            res_solution = st.text_area("✅ Actions réalisées / Travaux effectués *", value=interv.solution if interv.solution else "", height=150)
                        
                        c1, c2 = st.columns(2)
                        duree_h = c1.number_input("Durée (heures)", min_value=0.0, value=(interv.duree_minutes if interv.duree_minutes else 0) / 60, step=0.5)
                        duree = int(duree_h * 60)  # conversion en minutes pour la DB

                        # Boutons du formulaire
                        fc1, fc2 = st.columns([1, 1])
                        save_draft = fc1.form_submit_button("🔄 Mettre à jour")
                        close_final = fc2.form_submit_button("✅ Clôturer & Archiver")

                    # Pièces de rechange — HORS du formulaire car multiselect dynamique 
                    st.markdown("**Pièces de Rechange (Et Stock)**")
                    df_pieces = lire_pieces()
                    pieces_a_deduire = []
                    if not df_pieces.empty:
                        parts_map = {f"{p.reference} - {p.designation} (Stock: {p.stock_actuel})": p for p in df_pieces.itertuples()}
                        sel_parts = st.multiselect("Sélectionner pièces utilisées", options=list(parts_map.keys()), key=f"parts_{interv.id}")
                        
                        for p_key in sel_parts:
                            part = parts_map[p_key]
                            q_val = st.number_input(f"Quantité pour {part.reference}", min_value=1, value=1, key=f"qty_{part.reference}_{interv.id}")
                            pieces_a_deduire.append({
                                "ref": part.reference,
                                "qty": q_val,
                                "designation": part.designation,
                                "prix_unitaire": part.prix_unitaire if hasattr(part, "prix_unitaire") else 0
                            })
                    else:
                        st.info("Aucune pièce en stock. Ajoutez-les dans l'onglet Stock.")
                    
                    if save_draft:
                        # Mise à jour partielle (statut, type_erreur, priorite, champs rapport)
                        update_intervention_statut(interv.id, new_statut)
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE interventions SET type_erreur=?, priorite=?, probleme=?, cause=?, solution=?, duree_minutes=? WHERE id=?",
                                (new_te_tab, new_pr_tab, prob, res_cause, res_solution, duree, interv.id)
                            )
                        st.success(f"✅ Intervention #{interv.id} mise à jour (statut={new_statut}, priorité={new_pr_tab})")
                        st.rerun()
                    
                    if close_final:
                        # Validation selon le contexte
                        is_corrective = (interv.type_intervention == "Corrective")
                        valid = True
                        if is_corrective:
                            if not prob or not res_cause or not res_solution:
                                st.error("❌ Problème, Cause et Solution sont OBLIGATOIRES pour une maintenance corrective.")
                                valid = False
                        else:
                            if not res_solution: # Actions réalisées
                                st.error("❌ Veuillez décrire les actions réalisées.")
                                valid = False
                                
                        if valid:
                            if pieces_a_deduire:
                                st.info(f"📦 Pièces à déduire du stock : {pieces_a_deduire}")
                            else:
                                st.warning("⚠️ Aucune pièce sélectionnée pour déduction du stock.")
                            ok, msg = cloturer_intervention(interv.id, prob, res_cause, res_solution, pieces_a_deduire, duree_minutes=duree)
                            if ok:
                                # Sauvegarder type_erreur et priorite
                                with get_db() as conn:
                                    conn.execute("UPDATE interventions SET type_erreur=?, priorite=? WHERE id=?", (new_te_tab, new_pr_tab, interv.id))
                                # Notification Telegram Cloture
                                from notifications import get_notifier
                                notifier = get_notifier()
                                if notifier.telegram_ok:
                                    # Construire tags pour tous les techniciens
                                    tech_names = [n.strip() for n in interv.technicien.split(",")]
                                    tech_tags = [(n, tech_telegram_map.get(n, "")) for n in tech_names]
                                    # Extraire le client depuis les notes [ClientName]
                                    client_name = ""
                                    if hasattr(interv, "notes") and interv.notes:
                                        import re
                                        m = re.match(r"\[(.+?)\]", interv.notes)
                                        if m:
                                            client_name = m.group(1)
                                    notifier.notifier_cloture_intervention(
                                        interv.machine, tech_tags, prob, res_solution, client=client_name
                                    )
                                    st.toast("Notification de cloture envoyee !")

                                st.success(f"🎉 {msg}")
                                # Remettre l'équipement en Opérationnel si plus aucune En cours
                                try:
                                    with get_db() as conn:
                                        remaining = conn.execute(
                                            "SELECT COUNT(*) as cnt FROM interventions WHERE machine = ? AND statut = 'En cours'",
                                            (interv.machine,)
                                        ).fetchone()
                                        if remaining and remaining["cnt"] == 0:
                                            conn.execute("UPDATE equipements SET statut = ? WHERE nom = ?", ("Opérationnel", interv.machine))
                                except Exception:
                                    pass
                                st.balloons()
                                st.rerun()
                            else:
                                st.error(f"Erreur: {msg}")

    # ==========================================
    # ONGLET 4 : CHARGE TECHNIQUE
    # ==========================================
    if tab_charge is not None:
      with tab_charge:
        st.subheader("💰 Charge Technique — Coût des Interventions")

        devise = get_config("devise", "EUR")

        # --- Configuration du taux horaire ---
        st.markdown("### ⚙️ Taux Horaire")
        taux_actuel = int(float(get_config("taux_horaire_technicien", "50")))
        col_taux1, col_taux2 = st.columns([3, 1])
        nouveau_taux = col_taux1.number_input(
            f"💶 Prix de l'heure de travail ({devise})",
            min_value=0, value=taux_actuel, step=5,
            key="charge_taux_horaire"
        )
        col_taux2.markdown("<br>", unsafe_allow_html=True)
        if col_taux2.button("💾 Enregistrer le taux", key="btn_save_taux"):
            set_config("taux_horaire_technicien", str(nouveau_taux))
            st.success(f"✅ Taux horaire mis à jour : {nouveau_taux} {devise}/h")
            st.rerun()

        st.markdown("---")

        # --- Charger les données ---
        df_inter = lire_interventions()
        df_equip = lire_equipements()

        if df_inter.empty:
            st.info("Aucune intervention enregistrée.")
        else:
            # Préparer les données
            df_charge = df_inter.copy()
            df_charge["duree_heures"] = (df_charge["duree_minutes"].fillna(0) / 60).round(2)
            df_charge["cout_heures"] = (df_charge["duree_heures"] * nouveau_taux).round(2)

            # Résoudre le client via les notes ou la table équipements
            def _resolve_client_charge(row):
                notes = str(row.get("notes", "") or "")
                if notes.startswith("[") and "]" in notes:
                    return notes[1:notes.index("]")]
                machine = row.get("machine", "")
                if not df_equip.empty and machine:
                    match = df_equip[df_equip["Nom"] == machine]
                    if not match.empty:
                        return str(match.iloc[0].get("Client", ""))
                return "Non spécifié"

            df_charge["client"] = df_charge.apply(_resolve_client_charge, axis=1)

            # --- Filtres ---
            st.markdown("### 🔍 Filtres")
            fc1, fc2, fc3 = st.columns(3)
            clients = sorted(df_charge["client"].unique().tolist())
            client_filter = fc1.multiselect("🏢 Client", options=clients, key="charge_client")

            machines = sorted(df_charge["machine"].fillna("?").unique().tolist())
            machine_filter = fc2.multiselect("🏥 Équipement", options=machines, key="charge_machine")

            techniciens = sorted(df_charge["technicien"].fillna("?").unique().tolist())
            tech_filter = fc3.multiselect("👨‍🔧 Technicien", options=techniciens, key="charge_tech")

            # Appliquer les filtres
            df_f = df_charge.copy()
            if client_filter:
                df_f = df_f[df_f["client"].isin(client_filter)]
            if machine_filter:
                df_f = df_f[df_f["machine"].isin(machine_filter)]
            if tech_filter:
                df_f = df_f[df_f["technicien"].isin(tech_filter)]

            if df_f.empty:
                st.warning("Aucune intervention pour ces filtres.")
            else:
                # --- KPIs ---
                st.markdown("### 📊 Synthèse")
                total_heures = df_f["duree_heures"].sum()
                total_cout = df_f["cout_heures"].sum()
                nb_inter = len(df_f)

                k1, k2, k3 = st.columns(3)
                k1.metric("🔧 Interventions", nb_inter)
                k2.metric("⏱️ Heures totales", f"{total_heures:.1f}h")
                k3.metric(f"💰 Coût total ({devise})", f"{total_cout:,.0f}".replace(",", " ") + f" {devise}")

                d1, d2 = st.columns(2)
                d1.metric("📈 Taux appliqué", f"{nouveau_taux} {devise}/h")
                d2.metric("📊 Coût moyen/intervention", f"{total_cout / nb_inter:,.0f}".replace(",", " ") + f" {devise}")

                st.markdown("---")

                # --- Tableau détaillé ---
                st.markdown("### 📋 Détail par Intervention")
                cols_display = [
                    "date", "client", "machine", "technicien", "type_intervention",
                    "statut", "duree_heures", "cout_heures"
                ]
                available = [c for c in cols_display if c in df_f.columns]
                df_display = df_f[available].copy()
                df_display = df_display.rename(columns={
                    "date": "📅 Date",
                    "client": "🏢 Client",
                    "machine": "🏥 Équipement",
                    "technicien": "👨‍🔧 Technicien",
                    "type_intervention": "🔧 Type",
                    "statut": "📊 Statut",
                    "duree_heures": "⏱️ Heures",
                    "cout_heures": f"💰 Coût ({devise})",
                })
                st.dataframe(
                    df_display.sort_values("📅 Date", ascending=False),
                    use_container_width=True, hide_index=True,
                    height=min(600, 35 * len(df_display) + 38),
                )

                # --- Résumé par technicien ---
                st.markdown("### 👥 Coût par Technicien")
                df_tech = df_f.groupby("technicien").agg(
                    nb_interventions=("id", "count"),
                    heures_totales=("duree_heures", "sum"),
                    cout_total=("cout_heures", "sum"),
                ).reset_index()
                df_tech = df_tech.rename(columns={
                    "technicien": "👨‍🔧 Technicien",
                    "nb_interventions": "🔧 Interventions",
                    "heures_totales": "⏱️ Heures",
                    "cout_total": f"💰 Coût ({devise})",
                })
                st.dataframe(df_tech.sort_values(f"💰 Coût ({devise})", ascending=False),
                             use_container_width=True, hide_index=True)

                # --- Résumé par client ---
                st.markdown("### 🏢 Coût par Client")
                df_client = df_f.groupby("client").agg(
                    nb_interventions=("id", "count"),
                    heures_totales=("duree_heures", "sum"),
                    cout_total=("cout_heures", "sum"),
                ).reset_index()
                df_client = df_client.rename(columns={
                    "client": "🏢 Client",
                    "nb_interventions": "🔧 Interventions",
                    "heures_totales": "⏱️ Heures",
                    "cout_total": f"💰 Coût ({devise})",
                })
                st.dataframe(df_client.sort_values(f"💰 Coût ({devise})", ascending=False),
                             use_container_width=True, hide_index=True)

                # --- Export CSV ---
                st.markdown("---")
                import io
                csv_buf = io.StringIO()
                df_f[available].to_csv(csv_buf, index=False, sep=";")
                st.download_button(
                    "📊 Exporter en CSV",
                    data=csv_buf.getvalue(),
                    file_name=f"charge_technique_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # ==========================================
    # ONGLET 5 : FICHES D'INTERVENTION SIGNÉES
    # ==========================================
    with tab_photos:
        st.subheader("📸 Fiches d'intervention signées")
        st.caption("Photos des fiches d'intervention avec signature client, envoyées depuis SIC Terrain.")

        df_all_interv = lire_interventions()
        if df_all_interv.empty:
            st.info("Aucune intervention disponible.")
        else:
            has_photo_col = "photo_fiche" in df_all_interv.columns
            has_valid_col = "validation_client" in df_all_interv.columns

            if not has_photo_col:
                st.warning("⚠️ La colonne `photo_fiche` n'existe pas encore.")
            else:
                df_with_photo = df_all_interv[df_all_interv["photo_fiche"].fillna("").str.len() > 0].copy()

                if df_with_photo.empty:
                    st.info("📭 Aucune fiche signée n'a encore été envoyée par les techniciens.")
                else:
                    import os as _os

                    # Extraire client depuis notes
                    def _extract_client_photo(notes):
                        n = str(notes or "")
                        if n.startswith("[") and "]" in n:
                            return n[1:n.index("]")]
                        return "Non spécifié"
                    df_with_photo["client_extract"] = df_with_photo["notes"].apply(_extract_client_photo)

                    # --- Filtres ---
                    fc1, fc2 = st.columns(2)
                    clients_photo = sorted(df_with_photo["client_extract"].unique())
                    client_f = fc1.selectbox("🏢 Client", ["Tous"] + clients_photo, key="photo_client_f")

                    if has_valid_col:
                        valid_f = fc2.selectbox("✅ Validation", ["Tous", "Validée", "En attente"], key="photo_valid_f")
                    else:
                        valid_f = "Tous"

                    df_display = df_with_photo.copy()
                    if client_f != "Tous":
                        df_display = df_display[df_display["client_extract"] == client_f]
                    if valid_f != "Tous" and has_valid_col:
                        df_display = df_display[df_display["validation_client"].fillna("En attente") == valid_f]

                    st.markdown(f"**{len(df_display)} fiche(s) trouvée(s)**")
                    st.markdown("---")

                    # Chemin du dossier photos
                    photos_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "photos")

                    for _, row in df_display.sort_values("date", ascending=False).iterrows():
                        interv_id = row.get("id", "?")
                        technicien = row.get("technicien", "?")
                        client = row.get("client_extract", "?")
                        machine = row.get("machine", "?")
                        date_str = str(row.get("date", ""))[:16]
                        validation = row.get("validation_client", "En attente") if has_valid_col else "En attente"
                        photo_file = row.get("photo_fiche", "")
                        photo_path = _os.path.join(photos_dir, photo_file) if photo_file else ""

                        # Badge
                        v_emoji = "✅" if validation == "Validée" else "⏳"
                        v_color = "#22c55e" if validation == "Validée" else "#f59e0b"

                        c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 1.5, 1.5])
                        c1.markdown(f"**#{interv_id}**")
                        c2.markdown(f"👨‍🔧 {technicien}")
                        c3.markdown(f"🏢 {client}")
                        c4.markdown(f"📅 {date_str}")

                        # Bouton télécharger la photo
                        if photo_path and _os.path.exists(photo_path):
                            with open(photo_path, "rb") as f:
                                photo_bytes = f.read()
                            c5.download_button(
                                "📥 Photo",
                                data=photo_bytes,
                                file_name=f"fiche_intervention_{interv_id}.jpg",
                                mime="image/jpeg",
                                key=f"dl_photo_{interv_id}",
                            )
                        else:
                            c5.caption("📁 Fichier manquant")

                        # Validation modifiable + aperçu photo en expander
                        with st.expander(f"📋 Détails intervention #{interv_id}", expanded=False):
                            d1, d2 = st.columns([1, 1])
                            with d1:
                                st.markdown(f"🏥 **Machine :** {machine}")
                                st.markdown(f"**Validation :** :{v_emoji}: `{validation}`")
                                if has_valid_col:
                                    if validation == "Validée":
                                        st.success("✅ Fiche validée")
                                    else:
                                        new_val = st.selectbox(
                                            "Modifier validation",
                                            ["En attente", "Validée"],
                                            index=0,
                                            key=f"val_edit_{interv_id}",
                                        )
                                        if new_val != validation:
                                            with get_db() as conn:
                                                conn.execute(
                                                    "UPDATE interventions SET validation_client = ? WHERE id = ?",
                                                    (new_val, interv_id)
                                                )
                                            st.success(f"✅ Validation → {new_val}")
                                            st.rerun()
                            with d2:
                                if photo_path and _os.path.exists(photo_path):
                                    st.image(photo_path, caption="Fiche signée", use_container_width=True)

                        st.markdown("---")

