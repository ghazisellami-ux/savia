# ==========================================
# 🔩 PAGE INTERVENTIONS
# ==========================================
import streamlit as st
import pandas as pd
from datetime import datetime
from database import lire_interventions, ajouter_intervention, lire_equipements
from db_engine import log_audit, get_config, lire_base, lire_techniciens, get_db
from auth import get_current_user, require_role
from pdf_generator import generer_pdf_intervention
from i18n import t

TYPES_ERREUR = ["Hardware", "Software", "Réseau", "Calibration", "Mécanique", "Électrique", "Autre"]
PRIORITES = ["Haute", "Moyenne", "Basse"]


def page_interventions():
    st.title(t("interventions"))

    user = get_current_user()
    username = user.get("username", "?") if user else "?"
    _hide_costs = user.get("role", "") in ("Technicien", "Lecteur") if user else False

    # ============ NOUVELLE INTERVENTION ============
    if require_role("Admin", "Manager", "Technicien"):
        with st.expander(t("new_intervention"), expanded=False):
            df_equip = lire_equipements()

            if not df_equip.empty:
                if "Client" not in df_equip.columns:
                    df_equip["Client"] = "Centre Principal"

                # --- Étape 1 : Choisir le client (hors formulaire pour réactivité) ---
                clients_uniques = sorted(df_equip["Client"].fillna("Non spécifié").unique().tolist())
                selected_client = st.selectbox(
                    "🏢 Client",
                    clients_uniques,
                    key="interv_client_select"
                )

                # --- Étape 2 : Filtrer les machines du client ---
                df_client_machines = df_equip[df_equip["Client"] == selected_client]
                machines_client = df_client_machines["Nom"].tolist()

                if not machines_client:
                    st.warning(f"⚠️ Aucun équipement enregistré pour **{selected_client}**.")
                    machines_client = ["Aucun équipement"]

                st.info(f"🏥 **{selected_client}** — {len(machines_client)} équipement(s) disponible(s)")
            else:
                selected_client = "Non spécifié"
                machines_client = ["Machine 1"]

            # --- Upload fichier log (HORS formulaire) ---
            st.markdown("**Fichier Log (optionnel)**")
            uploaded_log = st.file_uploader(
                "Uploader le fichier log de la machine",
                type=["log", "csv", "txt"],
                key="interv_log_upload",
                label_visibility="collapsed"
            )

            log_desc_prefill = ""
            log_code_prefill = ""
            if uploaded_log:
                try:
                    from log_analyzer import analyser_log
                    contenu = uploaded_log.read().decode("utf-8", errors="replace")
                    hex_db, sol_db = lire_base()
                    df_log = analyser_log(contenu, hex_db, sol_db)

                    if not df_log.empty:
                        df_errors = df_log[df_log["Severite"].isin(["ERREUR", "CRITIQUE", "ATTENTION"])]
                        nb_connues = len(df_errors[df_errors["Statut"] == "Connue"]) if not df_errors.empty else 0
                        nb_inconnues = len(df_errors[df_errors["Statut"] != "Connue"]) if not df_errors.empty else 0

                        st.success(f"Analyse : **{len(df_errors)}** erreur(s) — {nb_connues} connue(s), {nb_inconnues} inconnue(s)")

                        if not df_errors.empty:
                            st.dataframe(
                                df_errors[["Code", "Message", "Severite", "Statut", "Type"]].drop_duplicates(),
                                use_container_width=True, hide_index=True
                            )

                            # Solutions connues
                            codes_trouves = df_errors[df_errors["Statut"] == "Connue"]["Code"].unique()
                            if len(codes_trouves) > 0:
                                st.markdown("**Solutions connues :**")
                                for code in codes_trouves:
                                    sol_info = sol_db.get(code)
                                    hex_info = hex_db.get(code)
                                    if sol_info:
                                        st.info(
                                            f"**{code}** — {hex_info['Msg'] if hex_info else ''}\n\n"
                                            f"**Cause :** {sol_info.get('Cause', 'N/A')}\n\n"
                                            f"**Solution :** {sol_info.get('Solution', 'N/A')}"
                                        )

                            # Pre-remplir
                            erreurs_resume = df_errors[["Code", "Message"]].drop_duplicates().head(5)
                            log_desc_prefill = "\n".join(
                                [f"[{r.Code}] {r.Message}" for r in erreurs_resume.itertuples()]
                            )
                            critiques = df_errors[df_errors["Severite"] == "CRITIQUE"]
                            if not critiques.empty:
                                log_code_prefill = str(critiques.iloc[0]["Code"])
                            else:
                                log_code_prefill = str(df_errors.iloc[0]["Code"])
                    else:
                        st.info("Aucune erreur detectee dans ce fichier log.")
                except Exception as e:
                    st.warning(f"Impossible d'analyser le fichier : {e}")

            # --- Formulaire (les données sont soumises ensemble) ---
            with st.form("form_intervention"):
                col1, col2 = st.columns(2)
                with col1:
                    machine = st.selectbox(
                        "🔬 " + t("machine"),
                        machines_client,
                        key="interv_machine_select"
                    )
                    # Liste des techniciens depuis la DB
                    df_techs = lire_techniciens()
                    if not df_techs.empty:
                        tech_list = [f"{r.nom} {r.prenom}" for r in df_techs.itertuples()]
                    else:
                        tech_list = [username]
                    techniciens = st.multiselect(
                        t("technician") + "(s)",
                        tech_list,
                        default=[username] if username in tech_list else [],
                        key="interv_techniciens"
                    )
                    type_interv = st.selectbox(
                        t("type"),
                        [t("corrective"), t("preventive")]
                    )
                with col2:
                    duree = st.number_input(t("duration_min"), min_value=0, value=60)
                    devise_form = get_config("devise", "EUR")
                    if not _hide_costs:
                        cout = st.number_input(f"{t('cost')} ({devise_form})", min_value=0.0, value=0.0, step=10.0)
                    else:
                        cout = 0.0
                    code_err = st.text_input("Code erreur", value=log_code_prefill, placeholder="Ex: 4B02")

                description = st.text_area(t("description"), value=log_desc_prefill, height=100)
                pieces = st.text_input(t("parts_used"), placeholder="Ex: Tube RX, Filtre")
                type_erreur = st.selectbox("📌 Type d'erreur", [""] + TYPES_ERREUR, help="Type d'erreur pour le tableau de bord")
                priorite = st.selectbox("🚨 Priorité", [""] + PRIORITES)
                notes = st.text_area(t("notes"), height=60)

                if st.form_submit_button(t("save"), use_container_width=True):
                    if not description.strip():
                        st.error("❌ La description est obligatoire")
                    elif machine == "Aucun équipement":
                        st.error("❌ Veuillez d'abord ajouter un équipement pour ce client.")
                    else:
                        display_name = f"{machine} ({selected_client})"
                        ajouter_intervention({
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "machine": machine,
                            "technicien": ", ".join(techniciens) if techniciens else username,
                            "type_intervention": type_interv,
                            "description": description.strip(),
                            "pieces_utilisees": pieces.strip(),
                            "cout": cout,
                            "duree_minutes": duree,
                            "code_erreur": code_err.strip(),
                            "statut": "Terminée",
                            "notes": f"[{selected_client}] {notes.strip()}",
                            "type_erreur": type_erreur,
                            "priorite": priorite,
                        })
                        log_audit(username, "INTERVENTION_ADDED",
                                  f"{display_name} - {type_interv}", "Interventions")
                        st.success(f"✅ Intervention enregistrée pour **{display_name}**")
                        st.rerun()

    # ============ HISTORIQUE ============
    st.markdown("---")
    st.subheader(t("intervention_history"))

    df = lire_interventions()
    if df.empty:
        st.info(t("no_data"))
        return

    # Filtres
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        machines_uniques = df["machine"].unique().tolist()
        filtre_machine = st.selectbox(
            t("filter") + " " + t("machine"),
            ["Toutes"] + machines_uniques
        )
    with col_f2:
        types_uniques = df["type_intervention"].unique().tolist()
        filtre_type = st.selectbox(
            t("filter") + " " + t("type"),
            ["Tous"] + types_uniques
        )

    df_filtered = df.copy()
    if filtre_machine != "Toutes":
        df_filtered = df_filtered[df_filtered["machine"] == filtre_machine]
    if filtre_type != "Tous":
        df_filtered = df_filtered[df_filtered["type_intervention"] == filtre_type]

    # KPIs
    devise = get_config("devise", "EUR")
    sym_map = {
        "EUR": "EUR", "USD": "USD", "GBP": "GBP", "TND": "TND",
        "MAD": "MAD", "DZD": "DZD", "XOF": "XOF", "CHF": "CHF",
        "CAD": "CAD", "SAR": "SAR", "AED": "AED", "QAR": "QAR",
    }
    sym = sym_map.get(devise, devise)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(t("total"), len(df_filtered))

    # Calculer le coût via charge technique (taux_horaire × heures)
    try:
        taux_h = int(float(get_config("taux_horaire_technicien", "50") or "50"))
    except (ValueError, TypeError):
        taux_h = 50
    duree_tot = df_filtered["duree_minutes"].sum() if not df_filtered.empty else 0
    cout_total = round((duree_tot / 60) * taux_h, 2)
    cout_moyen = round(cout_total / len(df_filtered), 2) if len(df_filtered) > 0 else 0

    if not _hide_costs:
        col2.metric("💰 " + t("cost") + " Total", f"{cout_total:.0f} {sym}")
    avg_duree = df_filtered["duree_minutes"].mean() if not df_filtered.empty else 0
    col3.metric(t("duration_min") + " Moy.", f"{avg_duree:.0f} min")
    if not _hide_costs:
        col4.metric("💰 Coût Moyen", f"{cout_moyen:.0f} {sym}")

    # Liste des interventions avec bouton PDF
    st.markdown("---")
    for idx, row in df_filtered.iterrows():
        interv = row.to_dict()
        date_str = str(interv.get('date', ''))[:16]
        machine = interv.get('machine', '?')
        type_i = interv.get('type_intervention', '?')
        cout_val = interv.get('cout', 0)
        icon = "[C]" if "orrect" in str(type_i) else "[P]"
        interv_id = interv.get('id', idx)

        col_info, col_pdf = st.columns([6, 1])
        with col_info:
            _exp_lbl = f"{icon} {date_str} - {machine} - {type_i}" if _hide_costs else f"{icon} {date_str} - {machine} - {type_i} - {cout_val:.0f} {sym}"
            with st.expander(_exp_lbl):
                c1, c2 = st.columns(2)
                c1.markdown(f"**Technicien :** {interv.get('technicien', '-')}")
                c1.markdown(f"**Dur\u00e9e :** {interv.get('duree_minutes', 0)} min")
                if not _hide_costs:
                    c2.markdown(f"**Co\u00fbt :** {cout_val:.2f} {sym}")
                c2.markdown(f"**Code erreur :** `{interv.get('code_erreur', '-')}`")
                type_err_val = interv.get('type_erreur', '')
                if type_err_val:
                    c2.markdown(f"**Type erreur :** {type_err_val}")
                priorite_val = interv.get('priorite', '')
                if priorite_val:
                    c2.markdown(f"**Priorité :** {priorite_val}")
                st.markdown(f"**Description :** {interv.get('description', '-')}")
                pieces = interv.get('pieces_utilisees', '')
                if pieces:
                    st.markdown(f"**Pi\u00e8ces :** {pieces}")
                notes = interv.get('notes', '')
                if notes:
                    st.markdown(f"**Notes :** {notes}")

                # --- Modifier / Clôturer ---
                if require_role("Admin", "Manager", "Technicien"):
                    st.markdown("---")
                    with st.form(f"form_edit_interv_{interv_id}"):
                        st.caption("✏️ Modifier / Clôturer")
                        ec1, ec2 = st.columns(2)
                        new_statut = ec1.selectbox("Statut", ["En cours", "Terminée", "Cloturee", "En attente de pièce"],
                            index=["En cours", "Terminée", "Cloturee", "En attente de pièce"].index(
                                interv.get('statut', 'En cours')) if interv.get('statut', 'En cours') in ["En cours", "Terminée", "Cloturee", "En attente de pièce"] else 0,
                            key=f"statut_{interv_id}")
                        current_te = interv.get('type_erreur', '')
                        te_options = [""] + TYPES_ERREUR
                        te_idx = te_options.index(current_te) if current_te in te_options else 0
                        new_type_erreur = ec2.selectbox("📌 Type d'erreur", te_options, index=te_idx, key=f"te_{interv_id}")
                        ec3, ec4 = st.columns(2)
                        current_pr = interv.get('priorite', '')
                        pr_options = [""] + PRIORITES
                        pr_idx = pr_options.index(current_pr) if current_pr in pr_options else 0
                        new_priorite = ec3.selectbox("🚨 Priorité", pr_options, index=pr_idx, key=f"pr_{interv_id}")

                        if st.form_submit_button("💾 Sauvegarder", use_container_width=True):
                            with get_db() as conn:
                                conn.execute(
                                    "UPDATE interventions SET statut=?, type_erreur=?, priorite=? WHERE id=?",
                                    (new_statut, new_type_erreur, new_priorite, interv_id)
                                )
                            log_audit(username, "INTERVENTION_UPDATED",
                                      f"{machine} - statut={new_statut}, type_erreur={new_type_erreur}, priorite={new_priorite}", "Interventions")
                            st.success(f"✅ Intervention #{interv_id} mise à jour")
                            import time; time.sleep(0.5); st.rerun()

        with col_pdf:
            st.markdown("<br>", unsafe_allow_html=True)
            pdf_bytes = generer_pdf_intervention(interv, devise)
            safe_machine = str(machine).replace(' ', '_')[:20]
            filename = f"rapport_{safe_machine}_{date_str[:10]}.pdf"
            st.download_button(
                "PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                key=f"pdf_{idx}",
            )
