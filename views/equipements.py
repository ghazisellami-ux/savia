# ==========================================
# 🏥 PAGE ÉQUIPEMENTS
# ==========================================
import streamlit as st
import pandas as pd
import os
import base64
import time
from db_engine import (
    lire_equipements, ajouter_equipement, supprimer_equipement,
    modifier_equipement, lire_equipement_par_id,
    lire_interventions,
    ajouter_document_technique, lire_documents_techniques,
    lire_document_technique_contenu, supprimer_document_technique,
    lire_tous_documents_techniques,
)
from predictive_engine import calculer_score_sante
from db_engine import get_config, get_db
from styles import health_badge
from config import EXCEL_PATH, TYPES_EQUIPEMENTS
from datetime import datetime


def afficher_equipements():
    """Page de gestion du parc d'équipements de radiologie."""

    st.title("🏥 Parc Équipements — Radiologie")
    st.markdown("---")

    from auth import get_user_client, get_current_user
    lecteur_client = get_user_client()
    user = get_current_user()
    is_lecteur = user.get("role") == "Lecteur" if user else False

    if is_lecteur:
        tab_parc = st.tabs(["🏥 Parc Équipements"])[0]
        tab_docs = None
    else:
        tab_parc, tab_docs = st.tabs(["🏥 Parc Équipements", "📄 Documentation Technique"])

    with tab_parc:

        df_equip = lire_equipements()
        df_hist = lire_interventions()
        if not df_hist.empty:
            # Mapper les colonnes d'interventions pour correspondre à l'ancien format historique
            from database import lire_base
            hex_db, _ = lire_base()
            df_hist = df_hist.rename(columns={
                "date": "Date", 
                "machine": "Machine", 
                "code_erreur": "Code", 
                "statut": "Severite", 
                "resolu": "Resolu"
            })
            # Résoudre le Type d'erreur via la table codes_erreurs
            code_to_type = {code: info.get("Type", "Autre") for code, info in hex_db.items()} if hex_db else {}
            df_hist["Type"] = df_hist["Code"].map(code_to_type).fillna("Autre")

        # Filtrer par client pour les Lecteurs
        if lecteur_client and not df_equip.empty and "Client" in df_equip.columns:
            df_equip = df_equip[df_equip["Client"] == lecteur_client]
            st.info(f"🏥 **Portail Client** — {lecteur_client}")
            machines_client = df_equip["Nom"].tolist()
            if not df_hist.empty and "Machine" in df_hist.columns:
                df_hist = df_hist[df_hist["Machine"].isin(machines_client)]

        # ============ AJOUTER UN ÉQUIPEMENT (masqué pour Lecteurs) ============
        if not is_lecteur:
            with st.expander("➕ Ajouter un nouvel équipement", expanded=not len(df_equip)):
                from db_engine import chercher_client_par_matricule

                # --- Étape 1 : Matricule Fiscale en premier ---
                st.markdown("**🆔 Identification du Client**")
                matricule = st.text_input(
                    "🆔 Matricule Fiscale du client *",
                    placeholder="Ex: 1234567/A/P/M/000",
                    key="ajout_matricule",
                    help="Saisissez la matricule fiscale pour identifier le client automatiquement"
                )

                # Auto-lookup du client par matricule
                client_auto = ""
                client_disabled = False
                if matricule and matricule.strip():
                    client_existant = chercher_client_par_matricule(matricule.strip())
                    if client_existant:
                        client_auto = client_existant
                        client_disabled = True
                        st.success(f"✅ Client trouvé : **{client_existant}** (matricule : {matricule})")
                    else:
                        st.info("🆕 Nouvelle matricule — veuillez saisir le nom du client ci-dessous.")

                client = st.text_input(
                    "🏢 Client / Site *",
                    value=client_auto,
                    placeholder="Ex: Clinique du Parc",
                    disabled=client_disabled,
                    key="ajout_client",
                )
                if client_disabled:
                    client = client_auto  # Forcer la valeur même si disabled

                st.markdown("---")
                st.markdown("**🏥 Détails de l'Équipement**")

                with st.form("form_ajout_equip"):
                    col1, col2 = st.columns(2)

                    nom = col1.text_input("📛 Nom de l'équipement *", placeholder="Ex: Scanner CT - Salle 3")
                    type_eq = col2.selectbox("🔬 Type d'équipement *", TYPES_EQUIPEMENTS)

                    col3, col4 = st.columns(2)
                    fabricant = col3.text_input("🏭 Fabricant", placeholder="Ex: Siemens, GE, Philips...")
                    modele = col4.text_input("📋 Modèle", placeholder="Ex: SOMATOM go.Up")

                    col5, col6 = st.columns(2)
                    num_serie = col5.text_input("🔢 N° de série", placeholder="Ex: SN-2024-001")
                    date_install = col6.date_input("📅 Date d'installation", value=datetime.now())

                    col7, col8 = st.columns(2)
                    derniere_maint = col7.date_input("🔧 Dernière maintenance", value=datetime.now())
                    statut = col8.selectbox("📊 Statut", ["Opérationnel", "En maintenance", "Hors service", "En attente pièce"])

                    notes = st.text_area("📝 Notes", placeholder="Informations complémentaires...")

                    # Upload documents techniques (multi-fichiers)
                    docs_technique = st.file_uploader(
                        "📄 Documents techniques (PDF, manuels, schémas...)",
                        type=["pdf", "png", "jpg", "jpeg", "doc", "docx", "xlsx"],
                        key="doc_technique_upload",
                        accept_multiple_files=True,
                        help="Sélectionnez un ou plusieurs fichiers. Ils seront stockés dans la base et utilisés par l'IA."
                    )

                    if st.form_submit_button("💾 Enregistrer l'équipement", use_container_width=True):
                        if not nom:
                            st.error("Le nom est obligatoire.")
                        elif not matricule or not matricule.strip():
                            st.error("La matricule fiscale est obligatoire.")
                        elif not client:
                            st.error("Le nom du client est obligatoire.")
                        else:
                            equip_dict = {
                                "Nom": nom,
                                "Type": type_eq,
                                "Fabricant": fabricant,
                                "Modele": modele,
                                "NumSerie": num_serie,
                                "DateInstallation": date_install.strftime("%Y-%m-%d"),
                                "DernieresMaintenance": derniere_maint.strftime("%Y-%m-%d"),
                                "Statut": statut,
                                "Notes": notes,
                                "Client": client if client else "Centre Principal",
                                "MatriculeFiscale": matricule.strip(),
                            }
                            if ajouter_equipement(equip_dict):
                                # Sauvegarder les documents un par un dans la table dédiée
                                if docs_technique:
                                    # Récupérer l'ID de l'équipement créé
                                    with get_db() as conn:
                                        row = conn.execute(
                                            "SELECT id FROM equipements WHERE nom = ? AND client = ?",
                                            (nom, client if client else "Centre Principal")
                                        ).fetchone()
                                    if row:
                                        eq_id = row["id"] if isinstance(row, dict) else row[0]
                                        for doc_file in docs_technique:
                                            b64 = base64.b64encode(doc_file.getvalue()).decode("utf-8")
                                            ajouter_document_technique(eq_id, doc_file.name, b64)
                                msg = f"✅ **{nom}** ajouté au parc pour le client **{client}** !"
                                if docs_technique:
                                    msg += f" 📄 {len(docs_technique)} document(s) technique(s) joint(s)."
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Erreur de sauvegarde.")

        # ============ LISTE PAR CLIENT (HIERARCHIQUE) ============
        if df_equip.empty:
            st.info("📭 Aucun équipement enregistré.")
            return

        st.subheader(f"📋 Parc Client — {len(df_equip)} Équipement(s)")

        # --- Préparation des données hiérarchiques ---
        if "Client" not in df_equip.columns:
            df_equip["Client"] = "Centre Principal"

        clients_uniques = sorted(df_equip["Client"].fillna("Non spécifié").unique())

        # --- Filtres Globaux ---
        col_search, col_filter_type, col_filter_statut = st.columns([3, 1, 1])
        recherche = col_search.text_input("🔍 Rechercher (Client, Machine, Série...)", placeholder="Tapez un mot-clé...")
        filtre_type = col_filter_type.selectbox("Type", ["Tous"] + df_equip["Type"].unique().tolist())

        # Collecter les statuts uniques (normalisés)
        statuts_possibles = ["Opérationnel", "En maintenance", "Hors service", "En attente pièce"]
        filtre_statut = col_filter_statut.selectbox("📊 Statut", ["Tous"] + statuts_possibles, key="filtre_statut_equip")

        # --- Affichage Hiérarchique ---
        for client_name in clients_uniques:
            df_client = df_equip[df_equip["Client"] == client_name]

            if filtre_type != "Tous":
                df_client = df_client[df_client["Type"] == filtre_type]

            if filtre_statut != "Tous":
                # Filtrer par statut (normalisation par préfixe)
                prefix_map = {"Opérationnel": "Op", "En maintenance": "En m", "Hors service": "Hors", "En attente pièce": "En a"}
                prefix = prefix_map.get(filtre_statut, "")
                df_client = df_client[df_client["Statut"].fillna("").astype(str).str.startswith(prefix)]

            if recherche:
                mask = df_client.apply(lambda row: recherche.lower() in " ".join(row.astype(str)).lower(), axis=1)
                df_client = df_client[mask]

            if df_client.empty:
                continue

            # --- Calcul Statut Client ---
            statuts = df_client["Statut"].tolist()
            if "Hors service" in statuts:
                client_status_icon = "🔴"
            elif "En maintenance" in statuts or "En attente pièce" in statuts:
                client_status_icon = "🟠"
            else:
                client_status_icon = "🟢"

            label_client = f"{client_status_icon} {client_name} ({len(df_client)} éq.)"

            with st.expander(label_client, expanded=True if recherche else False):
                for idx, row in df_client.iterrows():
                    nom_eq = row.get("Nom", "?")
                    client_eq = row.get("Client", "")
                    equip_id = row.get("id", "")

                    # Affichage : Nom (Client)
                    display_name = f"{nom_eq} ({client_eq})" if client_eq else nom_eq

                    # --- Icons ---
                    type_icons = {
                        "Scanner CT": "🔄", "IRM": "🧲", "Radiographie Numérique (DR)": "📷",
                        "Mammographe": "🩺", "Échographe": "🔊", "Fluoroscopie": "📺",
                        "Panoramique Dentaire": "🦷", "Ostéodensitomètre": "🦴",
                        "Angiographe": "❤️", "Cone Beam (CBCT)": "🎯",
                    }
                    icon = type_icons.get(row.get("Type", ""), "🔬")

                    statut_raw = row.get("Statut", "?")
                    # Normaliser le statut par préfixe (robuste face aux problèmes d'encodage DB)
                    if str(statut_raw).startswith("Op"):
                        statut_eq = "Opérationnel"
                    elif str(statut_raw).startswith("En m"):
                        statut_eq = "En maintenance"
                    elif str(statut_raw).startswith("Hors"):
                        statut_eq = "Hors service"
                    elif str(statut_raw).startswith("En a"):
                        statut_eq = "En attente pièce"
                    else:
                        statut_eq = str(statut_raw)

                    statut_colors = {"Opérationnel": "🟢", "En maintenance": "🟠", "Hors service": "🔴", "En attente pièce": "🟡"}
                    statut_icon = statut_colors.get(statut_eq, "⚪")

                    # Score santé
                    score_html = ""
                    if not df_hist.empty:
                        score, _ = calculer_score_sante(df_hist, nom_eq)
                        score_html = health_badge(score)

                    def _h(text):
                        """Convert accented chars to HTML entities."""
                        return str(text).encode('ascii', 'xmlcharrefreplace').decode('ascii')

                    _display = _h(display_name)
                    _type = _h(row.get('Type', '-'))
                    _ns = _h(row.get('NumSerie', '-'))
                    _fab = _h(row.get('Fabricant', '-'))
                    _statut = _h(statut_eq)

                    st.markdown(
                        f"""<div class="equip-card" style="margin-bottom: 8px; border-left: 4px solid {'#ef4444' if statut_eq=='Hors service' else '#22c55e'};">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div style="flex: 3;">
                                    <div style="font-weight:bold; font-size:1.1rem;">{icon} {_display}</div>
                                    <div style="color:#aaa; font-size:0.85rem;">
                                        {_type} | 🔢 {_ns} | 🏭 {_fab}
                                    </div>
                                </div>
                                <div style="flex: 2; text-align:right;">
                                    <span style="font-size:0.9rem;">{statut_icon} {_statut}</span>
                                    <div style="margin-top:4px;">{score_html}</div>
                                </div>
                            </div>
                        </div>""",
                        unsafe_allow_html=True
                    )

                    # Bouton Intervention rapide → dialog modal
                    if not is_lecteur:
                        if st.button("🔧 Intervention rapide", key=f"quick_interv_{equip_id}", type="secondary"):
                            st.session_state[f"_quick_interv_{equip_id}"] = {
                                "machine": nom_eq,
                                "client": client_eq,
                                "equip_id": equip_id,
                            }
                            st.rerun()

                        # Ouvrir le dialog si déclenché
                        if st.session_state.get(f"_quick_interv_{equip_id}"):
                            _qi = st.session_state[f"_quick_interv_{equip_id}"]

                            @st.dialog(f"⚡ Intervention Rapide — {_qi['machine']}", width="large")
                            def _dialog_quick_interv(qi_data, eq_id):
                                from db_engine import lire_techniciens, ajouter_intervention
                                st.success(f"🏥 **{qi_data['machine']}** — Client : **{qi_data['client']}**")

                                techs_df = lire_techniciens()
                                tech_list = [f"{r.nom} {r.prenom}" for r in techs_df.itertuples()] if not techs_df.empty else []
                                tech_telegram_map = {}
                                if not techs_df.empty:
                                    for r in techs_df.itertuples():
                                        tech_telegram_map[f"{r.nom} {r.prenom}"] = r.telegram_id if hasattr(r, 'telegram_id') else ""

                                sel_techs = st.multiselect("👷 Technicien(s)", tech_list, default=tech_list[:1] if tech_list else [], key=f"qi_tech_{eq_id}")
                                c1, c2 = st.columns(2)
                                type_opts = ["Corrective", "Préventive"]
                                sel_type = c1.selectbox("🔧 Type", type_opts, key=f"qi_type_{eq_id}")
                                priorite_opts = ["Haute", "Moyenne", "Basse"]
                                sel_priorite = c2.selectbox("🚨 Priorité", priorite_opts, index=0, key=f"qi_prio_{eq_id}")
                                sel_desc = st.text_area("📝 Description du problème", key=f"qi_desc_{eq_id}")

                                bc1, bc2 = st.columns(2)
                                if bc1.button("✅ Créer l'intervention", type="primary", use_container_width=True, key=f"qi_ok_{eq_id}"):
                                    if not sel_techs:
                                        st.error("Veuillez sélectionner au moins un technicien.")
                                        return

                                    tech_str = ", ".join(sel_techs)
                                    interv_data = {
                                        "machine": qi_data["machine"],
                                        "technicien": tech_str,
                                        "type_intervention": sel_type,
                                        "description": sel_desc,
                                        "statut": "En cours",
                                        "notes": f"[{qi_data['client']}]",
                                        "code_erreur": "",
                                        "type_erreur": "",
                                        "priorite": sel_priorite,
                                    }

                                    # 1. Créer l'intervention localement
                                    ajouter_intervention(interv_data)

                                    # 2. Marquer l'équipement comme "En maintenance"
                                    try:
                                        with get_db() as conn:
                                            conn.execute(
                                                "UPDATE equipements SET statut = ? WHERE id = ?",
                                                ("En maintenance", eq_id)
                                            )
                                    except Exception:
                                        pass

                                    # 3. Notification Telegram
                                    tg_msg = ""
                                    try:
                                        from notifications import get_notifier
                                        notifier = get_notifier()
                                        if notifier.telegram_ok:
                                            tech_tags = [(t, tech_telegram_map.get(t, "")) for t in sel_techs]
                                            notifier.notifier_nouvelle_intervention(
                                                qi_data["machine"], tech_tags, sel_desc, sel_type, client=qi_data["client"]
                                            )
                                            tg_msg = "📨 Notification Telegram envoyée"
                                        else:
                                            tg_msg = "⚠️ Telegram non configuré"
                                    except Exception as tg_err:
                                        tg_msg = f"❌ Telegram: {tg_err}"

                                    st.success(f"✅ Intervention créée pour **{qi_data['machine']}** — {tech_str}")
                                    if tg_msg:
                                        st.info(tg_msg)
                                    st.info("🔧 Visible sur SIC Terrain (base partagée)")

                                    # Nettoyage
                                    del st.session_state[f"_quick_interv_{eq_id}"]
                                    time.sleep(3)
                                    st.rerun()

                                if bc2.button("❌ Annuler", use_container_width=True, key=f"qi_cancel_{eq_id}"):
                                    del st.session_state[f"_quick_interv_{eq_id}"]
                                    st.rerun()

                            _dialog_quick_interv(_qi, equip_id)

                    # Documents techniques (depuis la table dédiée) — masqué pour Lecteurs
                    if not is_lecteur:
                        docs_db = lire_documents_techniques(equip_id)
                        if docs_db:
                            st.markdown(f"📄 **{len(docs_db)} document(s) technique(s) :**")
                            for doc_row in docs_db:
                                dc1, dc2, dc3 = st.columns([3, 1, 1])
                                dc1.caption(f"📎 {doc_row['nom_fichier']}")
                                # Téléchargement : charger le contenu à la demande
                                doc_content = lire_document_technique_contenu(doc_row['id'])
                                if doc_content:
                                    dc2.download_button(
                                        "📥",
                                        data=base64.b64decode(doc_content['contenu_base64']),
                                        file_name=doc_row['nom_fichier'],
                                        key=f"dl_doc_{equip_id}_{doc_row['id']}",
                                    )
                                if dc3.button("🗑️", key=f"del_doc_{equip_id}_{doc_row['id']}"):
                                    supprimer_document_technique(doc_row['id'])
                                    st.success(f"✅ Document **{doc_row['nom_fichier']}** supprimé.")
                                    time.sleep(0.5)
                                    st.rerun()

                    # --- Historique complet de la machine ---
                    with st.expander(f"Historique de {nom_eq}"):
                        df_inter_all = lire_interventions(machine=nom_eq)
                        devise = get_config("devise", "EUR")
                        if not df_inter_all.empty:
                            cout_total = df_inter_all["cout"].sum()
                            nb_inter = len(df_inter_all)
                            hide_costs = is_lecteur or (user and user.get("role") == "Technicien")
                            if hide_costs:
                                st.markdown(f"**{nb_inter}** interventions")
                            else:
                                st.markdown(f"**{nb_inter}** interventions | **Co\u00fbt cumul\u00e9 : {f'{cout_total:,.0f}'.replace(',', ' ')} {devise}**")
                            if "duree_minutes" in df_inter_all.columns:
                                df_inter_all["duree_heures"] = (df_inter_all["duree_minutes"].fillna(0) / 60).round(1)
                            cols_display = ["date", "type_intervention", "technicien", "statut", "description", "cout", "duree_heures"]
                            if hide_costs:
                                cols_display = [c for c in cols_display if c != "cout"]
                            available_cols = [c for c in cols_display if c in df_inter_all.columns]
                            st.dataframe(df_inter_all[available_cols].sort_values("date", ascending=False), use_container_width=True, hide_index=True)
                        else:
                            st.info("Aucune intervention pour cet \u00e9quipement.")


                    # --- Actions : Historique / Modifier / Supprimer ---
                    col_actions = st.columns([1, 1, 1, 2])

                    show_logs = col_actions[0].toggle("📜 Logs", key=f"toggle_{equip_id}")
                    if not is_lecteur:
                        show_edit = col_actions[1].toggle("✏️ Modifier", key=f"edit_{equip_id}")
                        do_delete = col_actions[2].button("🗑️ Supprimer", key=f"del_{equip_id}", type="secondary")
                    else:
                        show_edit = False
                        do_delete = False

                    # --- SUPPRIMER ---
                    if do_delete:
                        supprimer_equipement(equip_id)
                        st.success(f"✅ **{display_name}** supprimé.")
                        time.sleep(1)
                        st.rerun()

                    # --- MODIFIER ---
                    if show_edit:
                        with st.form(f"form_edit_{equip_id}"):
                            st.caption(f"✏️ Modifier : **{display_name}**")

                            e_matricule = st.text_input("🆔 Matricule Fiscale", value=row.get("matricule_fiscale", "") or "", key=f"emat_{equip_id}")

                            ec1, ec2 = st.columns(2)
                            e_nom = ec1.text_input("📛 Nom", value=nom_eq, key=f"en_{equip_id}")
                            e_client = ec2.text_input("🏢 Client", value=client_eq, key=f"ec_{equip_id}")

                            ec3, ec4 = st.columns(2)
                            e_type = ec3.selectbox("🔬 Type", TYPES_EQUIPEMENTS,
                                                   index=TYPES_EQUIPEMENTS.index(row.get("Type", "Autre")) if row.get("Type", "Autre") in TYPES_EQUIPEMENTS else 0,
                                                   key=f"et_{equip_id}")
                            e_fabricant = ec4.text_input("🏭 Fabricant", value=row.get("Fabricant", ""), key=f"ef_{equip_id}")

                            ec5, ec6 = st.columns(2)
                            e_modele = ec5.text_input("📋 Modèle", value=row.get("Modele", ""), key=f"em_{equip_id}")
                            e_serie = ec6.text_input("🔢 N° Série", value=row.get("NumSerie", ""), key=f"es_{equip_id}")

                            ec7, ec8 = st.columns(2)
                            e_statut = ec7.selectbox("📊 Statut",
                                                     ["Opérationnel", "En maintenance", "Hors service", "En attente pièce"],
                                                     index=["Opérationnel", "En maintenance", "Hors service", "En attente pièce"].index(statut_eq) if statut_eq in ["Opérationnel", "En maintenance", "Hors service", "En attente pièce"] else 0,
                                                     key=f"est_{equip_id}")
                            e_notes = ec8.text_input("📝 Notes", value=row.get("Notes", ""), key=f"eno_{equip_id}")

                            # Documents existants
                            existing_docs_edit = lire_documents_techniques(equip_id)
                            if existing_docs_edit:
                                st.caption(f"📄 {len(existing_docs_edit)} document(s) existant(s) : {', '.join(d['nom_fichier'] for d in existing_docs_edit)}")

                            # Upload nouveaux documents
                            e_docs = st.file_uploader(
                                "📄 Ajouter des documents techniques",
                                type=["pdf", "png", "jpg", "jpeg", "doc", "docx", "xlsx"],
                                key=f"doc_edit_{equip_id}",
                                accept_multiple_files=True,
                                help="Les nouveaux documents s'ajoutent aux existants"
                            )

                            if st.form_submit_button("💾 Sauvegarder les modifications", use_container_width=True):
                                edit_dict = {
                                    "Nom": e_nom,
                                    "Type": e_type,
                                    "Fabricant": e_fabricant,
                                    "Modele": e_modele,
                                    "NumSerie": e_serie,
                                    "DateInstallation": row.get("DateInstallation", ""),
                                    "DernieresMaintenance": row.get("DernieresMaintenance", ""),
                                    "Statut": e_statut,
                                    "Notes": e_notes,
                                    "Client": e_client if e_client else "Centre Principal",
                                    "MatriculeFiscale": e_matricule.strip() if e_matricule else "",
                                }
                                try:
                                    modifier_equipement(equip_id, edit_dict)
                                    # Sauvegarder les nouveaux docs un par un
                                    nb_new = 0
                                    for doc_file in (e_docs or []):
                                        b64 = base64.b64encode(doc_file.getvalue()).decode("utf-8")
                                        ajouter_document_technique(equip_id, doc_file.name, b64)
                                        nb_new += 1
                                    msg = f"✅ **{e_nom} ({e_client})** modifié !"
                                    if nb_new:
                                        msg += f" 📄 {nb_new} nouveau(x) document(s) ajouté(s)."
                                    st.success(msg)
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ ERREUR DB: {type(e).__name__}: {e}")

                    # --- HISTORIQUE / LOGS ---
                    if show_logs:
                        st.info(f"Détails pour {display_name}")
                        t_inter, t_event = st.tabs(["🔧 Interventions", "⚠️ Événements Système"])

                        with t_inter:
                            df_i = lire_interventions(machine=nom_eq)
                            if not df_i.empty:
                                st.dataframe(
                                    df_i[["date", "technicien", "type_intervention", "statut", "pieces_utilisees"]],
                                    use_container_width=True,
                                    hide_index=True
                                )
                            else:
                                st.caption("Aucune intervention enregistrée.")

                        with t_event:
                            if not df_hist.empty:
                                df_h_machine = df_hist[df_hist["Machine"] == nom_eq]
                                if not df_h_machine.empty:
                                    display_cols = [c for c in ["Date", "Code", "Type", "Severite", "Resolu"] if c in df_h_machine.columns]
                                    st.dataframe(
                                        df_h_machine[display_cols],
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                else:
                                    st.caption("Aucun événement système.")
                            else:
                                st.caption("Historique vide.")

                st.markdown("---")

    # ============ ONGLET DOCUMENTATION TECHNIQUE (masqué pour Lecteurs) ============
    if tab_docs is not None:
      with tab_docs:
        st.subheader("📄 Documentation Technique")
        st.caption("Consultez et recherchez tous les documents techniques du parc d'équipements.")

        all_docs = lire_tous_documents_techniques()

        if not all_docs:
            st.info("📭 Aucun document technique n'a été uploadé pour le moment.")
            st.markdown("**Pour ajouter un document :** sélectionnez un équipement dans l'onglet *Parc Équipements* → *✏️ Modifier* → uploadez un fichier.")
        else:
            # Extraire les valeurs uniques pour les filtres
            fabricants = sorted(set(d.get("fabricant", "") or "" for d in all_docs if d.get("fabricant")))
            modeles = sorted(set(d.get("modele", "") or "" for d in all_docs if d.get("modele")))
            clients_list = sorted(set(d.get("client", "") or "" for d in all_docs if d.get("client")))
            equipements_noms = sorted(set(d.get("equipement_nom", "") or "" for d in all_docs if d.get("equipement_nom")))

            # Filtres
            fc1, fc2, fc3, fc4 = st.columns(4)
            filtre_fabricant = fc1.selectbox("🏭 Fabricant", ["Tous"] + fabricants, key="doc_filtre_fab")
            filtre_modele = fc2.selectbox("📋 Modèle", ["Tous"] + modeles, key="doc_filtre_mod")
            filtre_client = fc3.selectbox("🏢 Client", ["Tous"] + clients_list, key="doc_filtre_cli")
            filtre_equip = fc4.selectbox("🏥 Équipement", ["Tous"] + equipements_noms, key="doc_filtre_eq")

            recherche = st.text_input("🔎 Rechercher par nom de fichier", key="doc_recherche",
                                      placeholder="Ex: Manuel, Schema, guide...")

            # Appliquer les filtres
            filtered = all_docs
            if filtre_fabricant != "Tous":
                filtered = [d for d in filtered if d.get("fabricant") == filtre_fabricant]
            if filtre_modele != "Tous":
                filtered = [d for d in filtered if d.get("modele") == filtre_modele]
            if filtre_client != "Tous":
                filtered = [d for d in filtered if d.get("client") == filtre_client]
            if filtre_equip != "Tous":
                filtered = [d for d in filtered if d.get("equipement_nom") == filtre_equip]
            if recherche:
                recherche_lower = recherche.lower()
                filtered = [d for d in filtered if recherche_lower in (d.get("nom_fichier", "") or "").lower()]

            st.markdown("---")
            st.markdown(f"### 📄 {len(filtered)} document(s) trouvé(s)")

            if not filtered:
                st.warning("Aucun document ne correspond aux filtres sélectionnés.")
            else:
                for doc in filtered:
                    nom_fichier = doc.get("nom_fichier", "?")
                    equipement = doc.get("equipement_nom", "?")
                    fabricant_v = doc.get("fabricant", "—")
                    modele_v = doc.get("modele", "—")
                    client_v = doc.get("client", "—")
                    date_ajout = str(doc.get("date_ajout", ""))[:10]
                    doc_id = doc.get("id")

                    ext = nom_fichier.rsplit(".", 1)[-1].lower() if "." in nom_fichier else ""
                    icon_map = {"pdf": "📕", "doc": "📘", "docx": "📘", "xlsx": "📗", "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️"}
                    icon = icon_map.get(ext, "📄")

                    c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
                    c1.markdown(f"**{icon} {nom_fichier}**")
                    c2.caption(f"🏥 {equipement} — {fabricant_v} {modele_v}")
                    c3.caption(f"🏢 {client_v} | 📅 {date_ajout}")

                    doc_content = lire_document_technique_contenu(doc_id)
                    if doc_content:
                        c4.download_button(
                            "📥",
                            data=base64.b64decode(doc_content["contenu_base64"]),
                            file_name=nom_fichier,
                            key=f"dl_doctech_{doc_id}",
                        )

                    if not is_lecteur:
                        if c5.button("🗑️", key=f"del_doctech_{doc_id}"):
                            supprimer_document_technique(doc_id)
                            st.success(f"✅ Document **{nom_fichier}** supprimé.")
                            time.sleep(0.5)
                            st.rerun()

                    st.markdown("<hr style='margin:2px 0; border-color:rgba(148,163,184,0.1)'>", unsafe_allow_html=True)
