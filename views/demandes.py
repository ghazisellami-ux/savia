# ==========================================
# 📋 PAGE DEMANDES D'INTERVENTION
# ==========================================
import streamlit as st
import pandas as pd
from datetime import datetime
from db_engine import (
    lire_demandes_intervention, ajouter_demande_intervention,
    traiter_demande_intervention, modifier_demande_intervention,
    supprimer_demande_intervention, lire_equipements, lire_techniciens,
    log_audit, get_db
)
from auth import get_current_user, require_role
from styles import kpi_card
from notifications import get_notifier

URGENCES = ["Haute", "Moyenne", "Basse"]
STATUTS_DEMANDE = ["Nouvelle", "Acceptée", "Planifiée", "Rejetée", "Clôturée"]


def page_demandes():
    st.markdown("## 📋 Demandes d'Intervention")

    user = get_current_user()
    username = user.get("username", "?") if user else "?"
    user_role = user.get("role", "Lecteur") if user else "Lecteur"
    user_client = user.get("client", "") if user else ""

    tab_new, tab_suivi = st.tabs(["📝 Nouvelle Demande", "📋 Suivi des Demandes"])

    # ==========================================
    # ONGLET 1 : NOUVELLE DEMANDE
    # ==========================================
    with tab_new:
        st.markdown("### ✏️ Soumettre une demande d'intervention")
        st.caption("Remplissez le formulaire ci-dessous pour soumettre une demande d'intervention technique.")

        # --- Prefill depuis bouton "Intervention rapide" (equipements.py) ---
        _prefill = st.session_state.get("prefill_intervention", {})
        if _prefill:
            st.success(f"⚡ **Intervention rapide** — Machine : **{_prefill.get('machine', '')}** ({_prefill.get('client', '')})")

        df_equip = lire_equipements()

        # --- Sélection du client ---
        if user_role == "Lecteur" and user_client:
            # Lecteur : client fixé automatiquement
            selected_client = user_client
            st.info(f"🏢 Client : **{selected_client}**")
        else:
            if not df_equip.empty and "Client" in df_equip.columns:
                clients_uniques = sorted(df_equip["Client"].fillna("Non spécifié").unique().tolist())
            else:
                clients_uniques = ["Centre Principal"]
            _pf_client = _prefill.get("client", "")
            _pf_client_idx = clients_uniques.index(_pf_client) if _pf_client in clients_uniques else 0
            selected_client = st.selectbox(
                "🏢 Client",
                clients_uniques,
                index=_pf_client_idx,
                key="demande_client_select"
            )

        # --- Filtrage équipements par client ---
        if not df_equip.empty:
            df_client_machines = df_equip[df_equip["Client"] == selected_client]
            machines_client = df_client_machines["Nom"].tolist()
        else:
            machines_client = []

        if not machines_client:
            machines_client = ["Autre / Non listé"]

        # --- Formulaire ---
        with st.form("form_demande_intervention"):
            col1, col2 = st.columns(2)
            with col1:
                _pf_machine = _prefill.get("machine", "")
                _pf_mach_idx = machines_client.index(_pf_machine) if _pf_machine in machines_client else 0
                equipement = st.selectbox(
                    "🏥 Équipement concerné",
                    machines_client,
                    index=_pf_mach_idx,
                    key="demande_equipement"
                )
                _pf_urgence_idx = 0 if _prefill else 1  # Haute si prefill, Moyenne sinon
                urgence = st.selectbox(
                    "🚨 Niveau d'urgence",
                    URGENCES,
                    index=_pf_urgence_idx,
                    key="demande_urgence"
                )
                code_erreur = st.text_input(
                    "🔢 Code erreur (optionnel)",
                    placeholder="Ex: 4B02",
                    key="demande_code_erreur"
                )
            with col2:
                contact_nom = st.text_input(
                    "👤 Contact sur site",
                    value=user.get("nom_complet", username) if user else username,
                    key="demande_contact_nom"
                )
                contact_tel = st.text_input(
                    "📞 Téléphone du contact",
                    placeholder="Ex: +216 XX XXX XXX",
                    key="demande_contact_tel"
                )

            description = st.text_area(
                "📝 Description du problème *",
                height=120,
                placeholder="Décrivez le problème rencontré, les symptômes observés, les messages d'erreur...",
                key="demande_description"
            )

            submitted = st.form_submit_button("📤 Soumettre la demande", use_container_width=True, type="primary")

            if submitted:
                if not description.strip():
                    st.error("❌ La description du problème est obligatoire.")
                else:
                    ajouter_demande_intervention({
                        "date_demande": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "demandeur": username,
                        "client": selected_client,
                        "equipement": equipement,
                        "urgence": urgence,
                        "description": description.strip(),
                        "code_erreur": code_erreur.strip(),
                        "contact_nom": contact_nom.strip(),
                        "contact_tel": contact_tel.strip(),
                    })
                    log_audit(username, "DEMANDE_CREATED",
                              f"{selected_client} - {equipement} - {urgence}", "Demandes")

                    # --- Notification Telegram ---
                    try:
                        notifier = get_notifier()
                        tg_ok = notifier.notifier_nouvelle_demande(
                            client=selected_client,
                            equipement=equipement,
                            urgence=urgence,
                            description=description.strip(),
                            date_demande=datetime.now().strftime("%d/%m/%Y %H:%M"),
                            demandeur=username,
                        )
                        if tg_ok:
                            st.toast("📨 Notification Telegram envoyée", icon="✅")
                        else:
                            st.toast("⚠️ Telegram non configuré ou erreur d'envoi", icon="⚠️")
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Notification Telegram échouée: {e}")
                        st.toast(f"❌ Erreur Telegram: {e}", icon="❌")

                    st.success(f"✅ Demande soumise avec succès pour **{equipement}** ({selected_client})")
                    # Effacer le prefill
                    st.session_state.pop("prefill_intervention", None)
                    import time; time.sleep(1.5)
                    st.rerun()

    # ==========================================
    # ONGLET 2 : SUIVI DES DEMANDES
    # ==========================================
    with tab_suivi:
        st.markdown("### 📊 Suivi des demandes")

        # Charger les demandes selon le rôle
        if user_role == "Lecteur" and user_client:
            df_demandes = lire_demandes_intervention(client=user_client)
        else:
            df_demandes = lire_demandes_intervention()

        if df_demandes.empty:
            st.info("📭 Aucune demande d'intervention enregistrée.")
            return

        # --- KPI Cards ---
        nb_total = len(df_demandes)
        nb_nouvelle = len(df_demandes[df_demandes["statut"] == "Nouvelle"])
        nb_acceptee = len(df_demandes[df_demandes["statut"] == "Acceptée"])
        nb_planifiee = len(df_demandes[df_demandes["statut"] == "Planifiée"])
        nb_rejetee = len(df_demandes[df_demandes["statut"] == "Rejetée"])

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(kpi_card("🆕", str(nb_nouvelle), "Nouvelles"), unsafe_allow_html=True)
        k2.markdown(kpi_card("✅", str(nb_acceptee), "Acceptées"), unsafe_allow_html=True)
        k3.markdown(kpi_card("📅", str(nb_planifiee), "Planifiées"), unsafe_allow_html=True)
        k4.markdown(kpi_card("❌", str(nb_rejetee), "Rejetées"), unsafe_allow_html=True)

        st.markdown("---")

        # --- Filtres ---
        fc1, fc2, fc3 = st.columns(3)
        statut_filter = fc1.multiselect(
            "📊 Statut", options=STATUTS_DEMANDE, key="demande_filtre_statut"
        )
        all_clients = sorted(df_demandes["client"].unique().tolist()) if "client" in df_demandes.columns else []
        client_filter = fc2.multiselect(
            "🏢 Client", options=all_clients, key="demande_filtre_client"
        )
        urgence_filter = fc3.multiselect(
            "🚨 Urgence", options=URGENCES, key="demande_filtre_urgence"
        )

        df_filtered = df_demandes.copy()
        if statut_filter:
            df_filtered = df_filtered[df_filtered["statut"].isin(statut_filter)]
        if client_filter:
            df_filtered = df_filtered[df_filtered["client"].isin(client_filter)]
        if urgence_filter:
            df_filtered = df_filtered[df_filtered["urgence"].isin(urgence_filter)]

        # --- Tableau ---
        display_cols = {
            "date_demande": "📅 Date",
            "client": "🏢 Client",
            "equipement": "🏥 Équipement",
            "urgence": "🚨 Urgence",
            "description": "📝 Description",
            "statut": "📊 Statut",
            "demandeur": "👤 Demandeur",
            "technicien_assigne": "🔧 Technicien",
            "date_planifiee": "📅 Date planifiée",
        }
        cols_present = [c for c in display_cols if c in df_filtered.columns]
        df_display = df_filtered[cols_present].rename(columns=display_cols)
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 * len(df_display) + 38),
        )

        # --- Détails & Actions par demande ---
        st.markdown("---")
        st.subheader("🔍 Détails & Actions")

        for _, row in df_filtered.iterrows():
            demande = row.to_dict()
            demande_id = demande.get("id", 0)
            date_str = str(demande.get("date_demande", ""))[:16]
            client = demande.get("client", "?")
            equip = demande.get("equipement", "?")
            urgence_val = demande.get("urgence", "?")
            statut = demande.get("statut", "?")

            # Icône par statut
            icon_map = {"Nouvelle": "🆕", "Acceptée": "✅", "Planifiée": "📅", "Rejetée": "❌", "Clôturée": "🏁"}
            icon = icon_map.get(statut, "📋")

            # Icône urgence
            urgence_icon = "🔴" if urgence_val == "Haute" else "🟡" if urgence_val == "Moyenne" else "🟢"

            with st.expander(f"{icon} {date_str} — {client} — {equip} — {urgence_icon} {urgence_val} — {statut}"):
                c1, c2 = st.columns(2)
                c1.markdown(f"**Demandeur :** {demande.get('demandeur', '-')}")
                c1.markdown(f"**Contact :** {demande.get('contact_nom', '-')}")
                c1.markdown(f"**Téléphone :** {demande.get('contact_tel', '-')}")
                # Badge statut coloré
                statut_colors = {
                    "Nouvelle": "#3b82f6",     # bleu
                    "Acceptée": "#10b981",     # vert
                    "Planifiée": "#f59e0b",    # orange
                    "Rejetée": "#ef4444",      # rouge
                    "Clôturée": "#6b7280",     # gris
                }
                s_color = statut_colors.get(statut, "#94a3b8")
                # Badge urgence coloré
                urgence_colors = {"Haute": "#ef4444", "Moyenne": "#f59e0b", "Basse": "#10b981"}
                u_color = urgence_colors.get(urgence_val, "#94a3b8")
                c2.markdown(f"""
<div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;">
  <div style="display:inline-block; background:{s_color}; color:white; padding:4px 14px;
    border-radius:14px; font-size:0.85rem; font-weight:700;">📊 {statut}</div>
  <div style="display:inline-block; background:{u_color}; color:white; padding:4px 14px;
    border-radius:14px; font-size:0.85rem; font-weight:700;">🚨 {urgence_val}</div>
</div>
                """, unsafe_allow_html=True)
                code_err = demande.get("code_erreur", "")
                if code_err:
                    c2.markdown(f"**Code erreur :** `{code_err}`")
                tech = demande.get("technicien_assigne", "")
                if tech:
                    c2.markdown(f"**Technicien assigné :** {tech}")

                st.markdown(f"**Description :** {demande.get('description', '-')}")

                notes_trait = demande.get("notes_traitement", "")
                if notes_trait:
                    st.markdown(f"**Notes de traitement :** {notes_trait}")

                date_trait = demande.get("date_traitement", "")
                if date_trait:
                    st.markdown(f"**Date de traitement :** {str(date_trait)[:16]}")

                date_plan = demande.get("date_planifiee", "")
                if date_plan:
                    st.markdown(f"📅 **Date planifiée :** {str(date_plan)[:10]}")

                # --- Actions Admin / Technicien ---
                if require_role("Admin", "Manager", "Technicien") and statut not in ["Rejetée"]:
                    st.markdown("---")
                    st.caption("⚙️ Actions de traitement")

                    df_techs = lire_techniciens()
                    if not df_techs.empty:
                        tech_list = [""] + [f"{r.prenom} {r.nom}".strip() for r in df_techs.itertuples()]
                    else:
                        tech_list = ["", username]

                    ac1, ac2 = st.columns(2)
                    new_statut = ac1.selectbox(
                        "Nouveau statut",
                        STATUTS_DEMANDE,
                        index=STATUTS_DEMANDE.index(statut) if statut in STATUTS_DEMANDE else 0,
                        key=f"dem_statut_{demande_id}"
                    )
                    current_tech = demande.get("technicien_assigne", "")
                    tech_idx = tech_list.index(current_tech) if current_tech in tech_list else 0
                    new_tech = ac2.selectbox(
                        "Technicien assigné",
                        tech_list,
                        index=tech_idx,
                        key=f"dem_tech_{demande_id}"
                    )

                    # Date planifiée (visible quand statut = Planifiée)
                    from datetime import timedelta
                    existing_date_plan = demande.get("date_planifiee", None)
                    try:
                        default_date = pd.to_datetime(existing_date_plan).date() if existing_date_plan else datetime.now().date() + timedelta(days=3)
                    except Exception:
                        default_date = datetime.now().date() + timedelta(days=3)
                    new_date_planifiee = st.date_input(
                        "📅 Date d'intervention planifiée",
                        value=default_date,
                        key=f"dem_date_plan_{demande_id}"
                    )

                    new_notes = st.text_area(
                        "Notes de traitement",
                        value=notes_trait,
                        height=60,
                        key=f"dem_notes_{demande_id}"
                    )

                    if st.button("💾 Mettre à jour", key=f"dem_update_{demande_id}", use_container_width=True):
                        traiter_demande_intervention(
                            demande_id, new_statut, new_tech, new_notes,
                            date_planifiee=new_date_planifiee if new_statut == "Planifiée" else None
                        )
                        log_audit(username, "DEMANDE_UPDATED",
                                  f"#{demande_id} → {new_statut} (tech: {new_tech})", "Demandes")

                        # --- Notification Telegram changement de statut (seulement Planifiée/Rejetée) ---
                        if new_statut in ["Planifiée", "Rejetée"]:
                            try:
                                notifier = get_notifier()
                                notifier.notifier_traitement_demande(
                                    client=client,
                                    equipement=equip,
                                    urgence=urgence_val,
                                    description=str(demande.get("description", ""))[:200],
                                    nouveau_statut=new_statut,
                                    technicien=new_tech,
                                    notes=new_notes,
                                    demandeur=demande.get("demandeur", ""),
                                    date_planifiee=str(new_date_planifiee) if new_statut == "Planifiée" else "",
                                )
                            except Exception:
                                pass

                        # --- Auto-créer une intervention si Planifiée avec technicien ---
                        if new_statut == "Planifiée" and new_tech:
                            interv_data = {
                                "machine": equip,
                                "technicien": new_tech,
                                "type_intervention": "Corrective",
                                "description": str(demande.get("description", "")),
                                "probleme": str(demande.get("description", "")),
                                "code_erreur": str(demande.get("code_erreur", "")),
                                "statut": "En cours",
                                "priorite": urgence_val,
                                "notes": f"[{client}] Demande #{demande_id} — Planifiée le {new_date_planifiee} — {new_notes}".strip(),
                            }
                            # Créer localement
                            try:
                                from db_engine import ajouter_intervention
                                ajouter_intervention(interv_data)
                            except Exception as e:
                                import logging
                                logging.getLogger(__name__).warning(f"Auto-création intervention locale échouée: {e}")
                            else:
                                st.toast(f"🔧 Intervention créée pour {new_tech}", icon="✅")

                        st.success(f"✅ Demande #{demande_id} mise à jour → **{new_statut}**")
                        import time; time.sleep(0.5)
                        st.rerun()

                # --- Actions Admin uniquement : Modifier / Supprimer ---
                if require_role("Admin"):
                    st.markdown("---")
                    st.caption("🔒 Actions Administrateur")

                    col_edit, col_del = st.columns(2)

                    with col_edit:
                        if st.button("✏️ Modifier", key=f"dem_edit_toggle_{demande_id}", use_container_width=True):
                            st.session_state[f"editing_demande_{demande_id}"] = True

                    with col_del:
                        if st.button("🗑️ Supprimer", key=f"dem_del_toggle_{demande_id}", use_container_width=True, type="primary"):
                            st.session_state[f"confirm_delete_demande_{demande_id}"] = True

                    # --- Formulaire de modification ---
                    if st.session_state.get(f"editing_demande_{demande_id}", False):
                        st.markdown("#### ✏️ Modifier la demande")
                        df_equip_edit = lire_equipements()
                        all_clients_edit = sorted(df_equip_edit["Client"].fillna("Non spécifié").unique().tolist()) if not df_equip_edit.empty and "Client" in df_equip_edit.columns else [client]
                        
                        me1, me2 = st.columns(2)
                        edit_client = me1.selectbox(
                            "🏢 Client", all_clients_edit,
                            index=all_clients_edit.index(client) if client in all_clients_edit else 0,
                            key=f"dem_edit_client_{demande_id}"
                        )
                        # Machines filtrées par client sélectionné
                        if not df_equip_edit.empty:
                            machines_edit = df_equip_edit[df_equip_edit["Client"] == edit_client]["Nom"].tolist()
                        else:
                            machines_edit = [equip]
                        if not machines_edit:
                            machines_edit = [equip] if equip else ["Autre"]
                        edit_equip = me2.selectbox(
                            "🏥 Équipement", machines_edit,
                            index=machines_edit.index(equip) if equip in machines_edit else 0,
                            key=f"dem_edit_equip_{demande_id}"
                        )
                        me3, me4 = st.columns(2)
                        edit_urgence = me3.selectbox(
                            "🚨 Urgence", URGENCES,
                            index=URGENCES.index(urgence_val) if urgence_val in URGENCES else 1,
                            key=f"dem_edit_urgence_{demande_id}"
                        )
                        edit_code = me4.text_input(
                            "🔢 Code erreur", value=demande.get("code_erreur", ""),
                            key=f"dem_edit_code_{demande_id}"
                        )
                        edit_desc = st.text_area(
                            "📝 Description", value=demande.get("description", ""),
                            height=80, key=f"dem_edit_desc_{demande_id}"
                        )
                        me5, me6 = st.columns(2)
                        edit_contact = me5.text_input(
                            "👤 Contact", value=demande.get("contact_nom", ""),
                            key=f"dem_edit_contact_{demande_id}"
                        )
                        edit_tel = me6.text_input(
                            "📞 Téléphone", value=demande.get("contact_tel", ""),
                            key=f"dem_edit_tel_{demande_id}"
                        )

                        bc1, bc2 = st.columns(2)
                        if bc1.button("💾 Enregistrer", key=f"dem_save_edit_{demande_id}", use_container_width=True, type="primary"):
                            modifier_demande_intervention(demande_id, {
                                "client": edit_client,
                                "equipement": edit_equip,
                                "urgence": edit_urgence,
                                "description": edit_desc.strip(),
                                "code_erreur": edit_code.strip(),
                                "contact_nom": edit_contact.strip(),
                                "contact_tel": edit_tel.strip(),
                            })
                            log_audit(username, "DEMANDE_MODIFIED",
                                      f"#{demande_id} modifiée", "Demandes")
                            st.success(f"✅ Demande #{demande_id} modifiée avec succès")
                            st.session_state[f"editing_demande_{demande_id}"] = False
                            import time; time.sleep(0.5)
                            st.rerun()
                        if bc2.button("❌ Annuler", key=f"dem_cancel_edit_{demande_id}", use_container_width=True):
                            st.session_state[f"editing_demande_{demande_id}"] = False
                            st.rerun()

                    # --- Confirmation de suppression ---
                    if st.session_state.get(f"confirm_delete_demande_{demande_id}", False):
                        st.warning(f"⚠️ Êtes-vous sûr de vouloir supprimer la demande **#{demande_id}** ?")
                        dc1, dc2 = st.columns(2)
                        if dc1.button("🗑️ Confirmer la suppression", key=f"dem_confirm_del_{demande_id}", use_container_width=True, type="primary"):
                            supprimer_demande_intervention(demande_id)
                            log_audit(username, "DEMANDE_DELETED",
                                      f"#{demande_id} — {client} — {equip}", "Demandes")
                            st.success(f"✅ Demande #{demande_id} supprimée")
                            st.session_state[f"confirm_delete_demande_{demande_id}"] = False
                            import time; time.sleep(0.5)
                            st.rerun()
                        if dc2.button("❌ Annuler", key=f"dem_cancel_del_{demande_id}", use_container_width=True):
                            st.session_state[f"confirm_delete_demande_{demande_id}"] = False
                            st.rerun()
