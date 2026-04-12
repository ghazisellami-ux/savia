# ==========================================
# Contrats & SLA
# ==========================================
import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
from db_engine import (
    lire_contrats, ajouter_contrat, modifier_contrat, supprimer_contrat,
    lire_interventions, lire_equipements, get_config
)
from auth import require_role
from config import BASE_DIR

CONTRATS_FILES_DIR = os.path.join(BASE_DIR, "contrats_files")
os.makedirs(CONTRATS_FILES_DIR, exist_ok=True)


def page_contrats():
    st.title("Contrats & SLA")

    devise = get_config("devise", "EUR")
    df_equip = lire_equipements()
    clients = sorted(df_equip["Client"].fillna("Non spécifié").unique().tolist()) if not df_equip.empty else []

    # ========== ONGLETS ==========
    tab_dash, tab_gestion = st.tabs(["Dashboard SLA", "Ajouter un Contrat"])

    # ========== TAB 1 : DASHBOARD SLA ==========
    with tab_dash:
        df_contrats = lire_contrats()
        if df_contrats.empty:
            st.info("Aucun contrat enregistré. Ajoutez-en dans l'onglet 'Ajouter un Contrat'.")
        else:
            today = date.today()
            is_admin = require_role("Admin")

            # KPIs
            c1, c2, c3 = st.columns(3)
            nb_actifs = len(df_contrats[df_contrats["statut"] == "Actif"])
            c1.metric("Contrats actifs", nb_actifs)

            # Contrats expirant dans 30 jours
            df_contrats["date_fin_dt"] = pd.to_datetime(df_contrats["date_fin"], errors="coerce")
            expirant = df_contrats[
                (df_contrats["date_fin_dt"].notna()) &
                (df_contrats["date_fin_dt"] <= pd.Timestamp(today) + pd.Timedelta(days=30)) &
                (df_contrats["date_fin_dt"] >= pd.Timestamp(today)) &
                (df_contrats["statut"] == "Actif")
            ]
            c2.metric("Expirent sous 30j", len(expirant))

            # Valeur totale
            val_total = df_contrats[df_contrats["statut"] == "Actif"]["montant"].sum()
            c3.metric("Valeur totale", f"{val_total:,.0f}".replace(",", " ") + f" {devise}")

            st.markdown("---")

            # Alertes
            if not expirant.empty:
                for _, row in expirant.iterrows():
                    jours = (row["date_fin_dt"].date() - today).days
                    st.warning(f"**{row['client']}** \u2014 Contrat expire dans **{jours} jour(s)** ({row['date_fin']})")

            # ========== TABLEAU DES CONTRATS ==========
            st.subheader("\U0001f4cb Contrats Existants")

            df_show = df_contrats.copy()
            if "montant" in df_show.columns:
                df_show["montant_fmt"] = df_show["montant"].fillna(0).apply(lambda x: f"{x:,.0f}".replace(",", " ") + f" {devise}")
            if "sla_temps_reponse_h" in df_show.columns:
                df_show["sla_fmt"] = df_show["sla_temps_reponse_h"].apply(lambda x: f"{x}h")
            if "interventions_incluses" in df_show.columns:
                df_show["interv_fmt"] = df_show["interventions_incluses"].apply(
                    lambda x: "Illimité" if x == -1 else str(x)
                )
            col_map = {
                "id": "\U0001f194 ID", "client": "\U0001f3e2 Client", "type_contrat": "\U0001f4c4 Type",
                "date_debut": "\U0001f4c5 Début", "date_fin": "\U0001f4c5 Fin", "sla_fmt": "\u23f1\ufe0f SLA",
                "interv_fmt": "\U0001f527 Interventions", "montant_fmt": f"\U0001f4b0 Montant ({devise})",
                "statut": "\U0001f4ca Statut",
            }
            cols_present = [c for c in col_map if c in df_show.columns]
            st.dataframe(
                df_show[cols_present].rename(columns=col_map),
                use_container_width=True, hide_index=True,
                height=min(400, 35 * len(df_show) + 38),
            )

            # Total des montants
            total_montants = df_contrats["montant"].fillna(0).sum()
            st.markdown(
                f'<div style="text-align:right; padding:8px 16px; background:rgba(45,212,191,0.08); '
                f'border-radius:8px; font-size:1.1rem;">'
                f'<b>\U0001f4b0 Total des contrats : {f"{total_montants:,.0f}".replace(",", " ")} {devise}</b></div>',
                unsafe_allow_html=True
            )

            # ========== MODIFIER / SUPPRIMER PAR CONTRAT ==========
            st.markdown("---")
            st.subheader("\u270f\ufe0f Modifier / \U0001f5d1\ufe0f Supprimer")

            # Barre de recherche
            search_client = st.text_input(
                "\U0001f50d Rechercher un client", placeholder="Tapez le nom du client...",
                key="contrat_search_client"
            ).strip().lower()

            # Filtrer les contrats
            df_filtered = df_contrats.copy()
            if search_client:
                df_filtered = df_filtered[df_filtered["client"].fillna("").str.lower().str.contains(search_client, na=False)]

            if df_filtered.empty and search_client:
                st.info(f"Aucun contrat trouvé pour '{search_client}'.")

            for idx, row in df_filtered.iterrows():
                cid = row["id"]
                client_name = row.get("client", "?")
                type_c = row.get("type_contrat", "?")
                dt_debut = row.get("date_debut", "")
                dt_fin = row.get("date_fin", "")
                sla_h = row.get("sla_temps_reponse_h", 0)
                interv_incl = row.get("interventions_incluses", -1)
                montant = row.get("montant", 0) or 0
                statut_c = row.get("statut", "?")
                conditions_c = row.get("conditions", "")
                notes_c = row.get("notes", "")
                interv_label = "Illimité" if interv_incl == -1 else str(interv_incl)

                # Couleur du statut
                statut_icon = "\U0001f7e2" if statut_c == "Actif" else "\U0001f534" if statut_c == "Expiré" else "\U0001f7e1"

                with st.expander(
                    f"{statut_icon} **{client_name}** \u2014 {type_c} \u2014 "
                    f"{dt_debut} \u2192 {dt_fin} \u2014 {f'{montant:,.0f}'.replace(',', ' ')} {devise}"
                ):
                    # Détails en colonnes
                    d1, d2, d3, d4 = st.columns(4)
                    d1.markdown(f"**\U0001f3e2 Client :** {client_name}")
                    d1.markdown(f"**\U0001f4c4 Type :** {type_c}")
                    equip_name = row.get("equipement", "") or ""
                    if equip_name:
                        d1.markdown(f"**🖥️ Équipement :** {equip_name}")
                    d2.markdown(f"**\U0001f4c5 Début :** {dt_debut}")
                    d2.markdown(f"**\U0001f4c5 Fin :** {dt_fin}")
                    d3.markdown(f"**\u23f1\ufe0f SLA :** {sla_h}h")
                    d3.markdown(f"**\U0001f527 Interventions :** {interv_label}")
                    d4.markdown(f"**\U0001f4b0 Montant :** {f'{montant:,.0f}'.replace(',', ' ')} {devise}")
                    d4.markdown(f"**\U0001f4ca Statut :** {statut_c}")

                    # ===== CHARGES TECHNIQUES liées à l'équipement du contrat =====
                    equip_contrat = row.get("equipement", "") or ""
                    if equip_contrat:
                        df_interv = lire_interventions()
                        if not df_interv.empty:
                            # Filtrer les interventions sur cet équipement
                            df_eq_interv = df_interv[df_interv["machine"].str.strip() == equip_contrat.strip()]
                            # Filtrer par période du contrat
                            if dt_debut and dt_fin:
                                df_eq_interv["date_dt"] = pd.to_datetime(df_eq_interv["date"], errors="coerce")
                                df_eq_interv = df_eq_interv[
                                    (df_eq_interv["date_dt"] >= pd.to_datetime(dt_debut, errors="coerce")) &
                                    (df_eq_interv["date_dt"] <= pd.to_datetime(dt_fin, errors="coerce"))
                                ]
                            if not df_eq_interv.empty:
                                taux_h = float(get_config("taux_horaire_technicien", "50") or "50")
                                df_eq_interv["heures"] = (df_eq_interv["duree_minutes"].fillna(0).astype(float) / 60).round(2)
                                df_eq_interv["charge_technique"] = (df_eq_interv["heures"] * taux_h).round(2)
                                df_eq_interv["cout_pieces_val"] = df_eq_interv["cout_pieces"].fillna(0).astype(float).round(2)
                                df_eq_interv["total_ligne"] = (df_eq_interv["charge_technique"] + df_eq_interv["cout_pieces_val"]).round(2)
                                total_charge = df_eq_interv["charge_technique"].sum()
                                total_pieces = df_eq_interv["cout_pieces_val"].sum()
                                total_global = total_charge + total_pieces
                                nb_interv = len(df_eq_interv)

                                st.markdown("---")
                                st.markdown(f"**💰 Dépenses liées au contrat — {equip_contrat}**")

                                # Résumé KPIs
                                cc1, cc2, cc3, cc4 = st.columns(4)
                                cc1.metric("Interventions", nb_interv)
                                cc2.metric("Main d'œuvre", f"{total_charge:,.0f}".replace(",", " ") + f" {devise}")
                                cc3.metric("Pièces installées", f"{total_pieces:,.0f}".replace(",", " ") + f" {devise}")
                                # Rentabilité : contrat vs dépenses
                                benefice = montant - total_global
                                delta_color = "normal" if benefice >= 0 else "inverse"
                                cc4.metric("💰 Solde contrat", f"{benefice:,.0f}".replace(",", " ") + f" {devise}",
                                          delta=f"{f'{total_global:,.0f}'.replace(',', ' ')} dépensé", delta_color=delta_color)

                                # Barre de progression budget
                                if montant > 0:
                                    pct_used = min(total_global / montant * 100, 100)
                                    bar_color = "#22c55e" if pct_used < 70 else "#eab308" if pct_used < 90 else "#ef4444"
                                    st.markdown(
                                        f'<div style="background:rgba(255,255,255,0.05); border-radius:8px; overflow:hidden; height:20px; margin:8px 0;">'
                                        f'<div style="width:{pct_used:.0f}%; background:{bar_color}; height:100%; border-radius:8px; '
                                        f'display:flex; align-items:center; justify-content:center; font-size:0.7rem; font-weight:bold; color:#fff;">'
                                        f'{pct_used:.0f}% du budget utilisé</div></div>',
                                        unsafe_allow_html=True
                                    )

                                # Tableau détaillé des interventions + pièces
                                cols_display = ["date", "technicien", "type_intervention", "statut",
                                               "heures", "charge_technique", "cout_pieces_val", "total_ligne", "pieces_utilisees"]
                                cols_available = [c for c in cols_display if c in df_eq_interv.columns]
                                df_display = df_eq_interv[cols_available].copy()
                                col_rename = {
                                    "date": "📅 Date", "technicien": "👷 Technicien",
                                    "type_intervention": "🔧 Type", "statut": "📊 Statut",
                                    "heures": "⏱️ Heures", "charge_technique": f"💰 Main d'œuvre ({devise})",
                                    "cout_pieces_val": f"🔩 Pièces ({devise})",
                                    "total_ligne": f"📊 Total ({devise})",
                                    "pieces_utilisees": "📦 Détail pièces installées"
                                }
                                df_display = df_display.rename(columns={k: v for k, v in col_rename.items() if k in df_display.columns})
                                st.dataframe(df_display, use_container_width=True, hide_index=True)

                                # Résumé total
                                st.markdown(
                                    f'<div style="text-align:right; padding:8px 16px; background:rgba(239,68,68,0.08); '
                                    f'border-radius:8px; font-size:1rem; margin-top:8px;">'
                                    f'<b>🔴 Total dépenses : {f"{total_global:,.0f}".replace(",", " ")} {devise}</b> '
                                    f'(Main d\'œuvre: {f"{total_charge:,.0f}".replace(",", " ")} + Pièces: {f"{total_pieces:,.0f}".replace(",", " ")})'
                                    f'</div>', unsafe_allow_html=True
                                )
                            else:
                                st.caption(f"ℹ️ Aucune intervention trouvée pour **{equip_contrat}** durant la période du contrat.")

                    if conditions_c:
                        st.markdown(f"**\U0001f4cb Conditions :** {conditions_c}")
                    if notes_c:
                        st.markdown(f"**\U0001f4dd Notes :** {notes_c}")

                    # Fichier contrat attaché
                    fichier_c = row.get("fichier_contrat", "") or ""
                    if fichier_c and os.path.exists(fichier_c):
                        st.markdown("**📎 Fichier contrat joint :**")
                        with open(fichier_c, "rb") as fp:
                            st.download_button(
                                f"📥 Télécharger {os.path.basename(fichier_c)}",
                                data=fp.read(),
                                file_name=os.path.basename(fichier_c),
                                key=f"dl_contrat_file_{cid}",
                            )
                    elif fichier_c:
                        st.caption("📎 Fichier joint introuvable sur le serveur.")

                    # Actions admin : Modifier / Supprimer
                    if is_admin:
                        st.markdown("---")
                        act1, act2 = st.columns(2)

                        # ===== MODIFIER =====
                        with act1:
                            with st.popover("\u270f\ufe0f Modifier ce contrat", use_container_width=True):
                                with st.form(key=f"edit_contrat_{cid}"):
                                    e_client = st.selectbox(
                                        "Client", clients if clients else [client_name],
                                        index=clients.index(client_name) if client_name in clients else 0,
                                        key=f"ec_cl_{cid}"
                                    )
                                    e_type = st.selectbox(
                                        "Type", ["Standard", "Premium", "Full-Risk", "Garantie", "Sur mesure"],
                                        index=["Standard", "Premium", "Full-Risk", "Garantie", "Sur mesure"].index(type_c) if type_c in ["Standard", "Premium", "Full-Risk", "Garantie", "Sur mesure"] else 0,
                                        key=f"ec_ty_{cid}"
                                    )
                                    ec1, ec2 = st.columns(2)
                                    e_debut = ec1.date_input(
                                        "Début",
                                        value=pd.to_datetime(dt_debut, errors="coerce") or today,
                                        key=f"ec_dd_{cid}"
                                    )
                                    e_fin = ec2.date_input(
                                        "Fin",
                                        value=pd.to_datetime(dt_fin, errors="coerce") or today,
                                        key=f"ec_df_{cid}"
                                    )
                                    ec3, ec4 = st.columns(2)
                                    e_sla = ec3.number_input(
                                        "SLA (h)", min_value=1, value=int(sla_h),
                                        key=f"ec_sla_{cid}"
                                    )
                                    e_max = ec4.number_input(
                                        "Interventions (-1=illimité)", min_value=-1,
                                        value=int(interv_incl), key=f"ec_mx_{cid}"
                                    )
                                    e_montant = st.number_input(
                                        f"Montant ({devise})", min_value=0.0,
                                        value=float(montant), step=100.0,
                                        key=f"ec_mt_{cid}"
                                    )
                                    e_statut = st.selectbox(
                                        "Statut", ["Actif", "Expiré", "Suspendu", "Résilié"],
                                        index=["Actif", "Expiré", "Suspendu", "Résilié"].index(statut_c) if statut_c in ["Actif", "Expiré", "Suspendu", "Résilié"] else 0,
                                        key=f"ec_st_{cid}"
                                    )
                                    e_cond = st.text_area(
                                        "Conditions", value=conditions_c or "",
                                        key=f"ec_co_{cid}"
                                    )
                                    e_notes = st.text_area(
                                        "Notes", value=notes_c or "",
                                        key=f"ec_no_{cid}"
                                    )

                                    if st.form_submit_button("\U0001f4be Enregistrer"):
                                        # Conserver le fichier existant
                                        fichier_existant = row.get("fichier_contrat", "") or ""
                                        modifier_contrat(cid, {
                                            "client": e_client,
                                            "type_contrat": e_type,
                                            "equipement": row.get("equipement", "") or "",
                                            "date_debut": e_debut.isoformat(),
                                            "date_fin": e_fin.isoformat(),
                                            "sla_temps_reponse_h": e_sla,
                                            "interventions_incluses": e_max,
                                            "montant": e_montant,
                                            "statut": e_statut,
                                            "conditions": e_cond,
                                            "notes": e_notes,
                                            "fichier_contrat": fichier_existant,
                                        })
                                        st.success(f"\u2705 Contrat #{cid} modifié !")
                                        st.rerun()

                        # ===== SUPPRIMER =====
                        with act2:
                            confirm_key = f"confirm_del_c_{cid}"
                            confirm = st.checkbox(
                                "Confirmer la suppression",
                                key=confirm_key
                            )
                            if confirm:
                                if st.button(
                                    "\U0001f5d1\ufe0f Supprimer",
                                    type="primary",
                                    key=f"btn_del_c_{cid}",
                                    use_container_width=True,
                                ):
                                    supprimer_contrat(cid)
                                    st.success(f"\u2705 Contrat #{cid} supprimé.")
                                    st.rerun()

    # ========== TAB 2 : AJOUTER UN CONTRAT ==========
    with tab_gestion:
        if not require_role("Admin", "Manager", "Technicien"):
            st.warning("Accès réservé aux admins et techniciens.")
            return

        today = date.today()

        st.subheader("Ajouter un contrat")

        # Client et Équipement HORS du form (pour que l'équipement se filtre dynamiquement)
        fc_top1, fc_top2 = st.columns(2)
        f_client = fc_top1.selectbox("🏢 Client", clients if clients else ["Aucun client"], key="contrat_client_sel")
        # Filtrer les équipements en fonction du client sélectionné
        if not df_equip.empty and f_client != "Aucun client":
            equip_client = sorted(df_equip[df_equip["Client"] == f_client]["Nom"].tolist())
        else:
            equip_client = []
        f_equipement = fc_top2.selectbox(
            "🖥️ Équipement",
            [""] + equip_client if equip_client else ["Aucun équipement"],
            key="contrat_equip_sel"
        )

        # File uploader outside the form (Streamlit limitation)
        f_fichier = st.file_uploader(
            "📎 Joindre le fichier du contrat (PDF, image...)",
            type=["pdf", "png", "jpg", "jpeg", "doc", "docx"],
            key="contrat_file_upload",
        )

        with st.form("form_contrat"):
            f_type = st.selectbox("Type", ["Standard", "Premium", "Full-Risk", "Garantie", "Sur mesure"])
            fc3, fc4 = st.columns(2)
            f_debut = fc3.date_input("Date début", value=today)
            f_fin = fc4.date_input("Date fin", value=date(today.year + 1, today.month, today.day))
            fc5, fc6 = st.columns(2)
            f_sla = fc5.number_input("SLA Réponse (heures)", min_value=1, value=24)
            f_max = fc6.number_input("Interventions incluses (-1 = illimité)", min_value=-1, value=-1)
            f_montant = st.number_input(f"Montant annuel ({devise})", min_value=0.0, value=0.0, step=100.0)

            # === SECTION MAINTENANCE PRÉVENTIVE RÉCURRENTE ===
            st.markdown("---")
            st.markdown("**🔄 Maintenance Préventive Récurrente**")
            st.caption("Si une récurrence est choisie, les maintenances seront automatiquement planifiées dans le calendrier.")

            rc1, rc2 = st.columns(2)
            f_recurrence = rc1.selectbox("📅 Récurrence maintenance", [
                "", "Mensuelle", "Trimestrielle", "Semestrielle", "Annuelle"
            ])
            f_date_maint = rc2.date_input(
                "📅 Date 1ère maintenance",
                value=today + timedelta(days=30),
            )

            # Technicien assigné pour les maintenances récurrentes
            from db_engine import lire_techniciens
            df_techs = lire_techniciens()
            tech_opts = [""] + [f"{r.nom} {r.prenom}" for r in df_techs.itertuples()] if not df_techs.empty else [""]
            f_tech_maint = st.selectbox("👤 Technicien assigné (maintenance)", tech_opts)

            f_conditions = st.text_area("Conditions", placeholder="Ex: Pièces incluses, support 24/7...")
            f_notes = st.text_area("Notes", height=60)

            if st.form_submit_button("Enregistrer le contrat"):
                if f_client == "Aucun client":
                    st.error("Ajoutez d'abord des clients dans la section Équipements.")
                else:
                    # Sauvegarder le fichier joint s'il existe
                    fichier_path = ""
                    if f_fichier is not None:
                        safe_client = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in f_client)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        ext = os.path.splitext(f_fichier.name)[1]
                        filename = f"contrat_{safe_client}_{timestamp}{ext}"
                        fichier_path = os.path.join(CONTRATS_FILES_DIR, filename)
                        with open(fichier_path, "wb") as out_f:
                            out_f.write(f_fichier.getbuffer())

                    ajouter_contrat({
                        "client": f_client,
                        "type_contrat": f_type,
                        "equipement": f_equipement if f_equipement != "Aucun équipement" else "",
                        "date_debut": f_debut.isoformat(),
                        "date_fin": f_fin.isoformat(),
                        "sla_temps_reponse_h": f_sla,
                        "interventions_incluses": f_max,
                        "montant": f_montant,
                        "conditions": f_conditions,
                        "notes": f_notes,
                        "fichier_contrat": fichier_path,
                    })
                    st.success("✅ Contrat enregistré !")
                    if fichier_path:
                        st.info(f"📎 Fichier joint : {os.path.basename(fichier_path)}")

                    # === GÉNÉRATION AUTOMATIQUE DES MAINTENANCES RÉCURRENTES ===
                    if f_recurrence and f_date_maint:
                        from dateutil.relativedelta import relativedelta
                        from db_engine import ajouter_planning

                        delta_map = {
                            "Mensuelle": 1,
                            "Trimestrielle": 3,
                            "Semestrielle": 6,
                            "Annuelle": 12,
                        }
                        delta_months = delta_map.get(f_recurrence, 0)
                        equip_name = f_equipement if f_equipement and f_equipement != "Aucun équipement" else "Équipement général"

                        if delta_months > 0:
                            # Calculer la durée du contrat en jours
                            duree_contrat = (f_fin - f_debut).days
                            dates_planifiees = []
                            current = f_date_maint

                            while current <= f_fin:
                                dates_planifiees.append(current)
                                current = current + relativedelta(months=delta_months)

                            for d in dates_planifiees:
                                ajouter_planning({
                                    "machine": equip_name,
                                    "client": f_client,
                                    "type_maintenance": "Préventive",
                                    "date_prevue": d.strftime("%Y-%m-%d"),
                                    "technicien_assigne": f_tech_maint or "À assigner",
                                    "recurrence": f_recurrence,
                                    "description": f"Maintenance préventive {f_recurrence.lower()} — Contrat {f_type}",
                                    "notes": f"Généré automatiquement depuis le contrat {f_client}",
                                })

                            st.success(
                                f"🔄 **{len(dates_planifiees)} maintenances préventives** ({f_recurrence.lower()}) "
                                f"planifiées du {dates_planifiees[0].strftime('%d/%m/%Y')} "
                                f"au {dates_planifiees[-1].strftime('%d/%m/%Y')}"
                            )

                            # Notification Telegram
                            try:
                                from notifications import get_notifier
                                notifier = get_notifier()
                                if notifier.telegram_ok:
                                    dates_str = ", ".join(d.strftime("%d/%m/%Y") for d in dates_planifiees[:6])
                                    if len(dates_planifiees) > 6:
                                        dates_str += f"... (+{len(dates_planifiees)-6})"
                                    notifier.envoyer_telegram(
                                        f"📋 *Nouveau Contrat + Planning Préventif*\n\n"
                                        f"🏢 Client : *{f_client}*\n"
                                        f"🏥 Équipement : *{equip_name}*\n"
                                        f"📄 Type : {f_type}\n"
                                        f"🔄 Récurrence : {f_recurrence}\n"
                                        f"👤 Technicien : {f_tech_maint or 'À assigner'}\n\n"
                                        f"📅 {len(dates_planifiees)} dates planifiées :\n{dates_str}"
                                    )
                            except Exception:
                                pass

                    st.rerun()

