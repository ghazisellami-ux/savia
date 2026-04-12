# ==========================================
# 🛡️ PAGE QHSE — CONFORMITÉ RADIOLOGIE
# ==========================================
import streamlit as st
import pandas as pd
from datetime import datetime, date
from db_engine import (
    lire_conformite, ajouter_conformite, supprimer_conformite,
    lire_fichier_conformite, lire_equipements, log_audit
)
from auth import get_current_user, require_role, get_user_client
from i18n import t

TYPES_CONTROLE = [
    "Contrôle Qualité Interne",
    "Contrôle Qualité Externe",
    "Inspection ASN",
    "Radioprotection",
    "Maintenance Réglementaire",
    "Contrôle Technique (Électrique/Clim)",
    "ANSM — Matériovigilance",
    "Dosimétrie Personnel",
    "Autre",
]


def page_conformite():
    """Page QHSE — Suivi de la conformité réglementaire."""

    st.title("🛡️ QHSE — Conformité Radiologie")

    user = get_current_user()
    username = user.get("username", "?") if user else "?"
    user_role = user.get("role", "Lecteur") if user else "Lecteur"
    is_lecteur = user_role == "Lecteur"
    lecteur_client = get_user_client()

    # Charger les équipements pour le formulaire
    df_equip = lire_equipements()

    # Filtrer par client pour les Lecteurs
    filtre_client = None
    if lecteur_client:
        filtre_client = lecteur_client
        st.info(f"🏥 **Portail Client** — {lecteur_client}")
    elif not df_equip.empty and "Client" in df_equip.columns:
        clients_list = ["Tous les clients"] + sorted(df_equip["Client"].dropna().unique().tolist())
        choix_client = st.selectbox("Filtrer par client", clients_list, key="qhse_client")
        if choix_client != "Tous les clients":
            filtre_client = choix_client

    st.markdown("---")

    # ============ AJOUTER UN CONTRÔLE (Admin/Technicien) ============
    if not is_lecteur:
        with st.expander("➕ Ajouter un contrôle de conformité", expanded=False):
            with st.form("form_conformite"):
                col1, col2 = st.columns(2)

                with col1:
                    # Sélection client → machines filtrées
                    if not df_equip.empty and "Client" in df_equip.columns:
                        clients = sorted(df_equip["Client"].dropna().unique().tolist())
                        sel_client = st.selectbox("🏢 Client", clients, key="conf_client")
                        machines_client = df_equip[df_equip["Client"] == sel_client]["Nom"].tolist()
                    else:
                        sel_client = "Centre Principal"
                        machines_client = df_equip["Nom"].tolist() if not df_equip.empty else ["—"]

                    sel_equip = st.selectbox("🔬 Équipement", machines_client, key="conf_equip")
                    type_ctrl = st.selectbox("📋 Type de contrôle", TYPES_CONTROLE)

                with col2:
                    date_ctrl = st.date_input("📅 Date du contrôle", value=date.today())
                    date_exp = st.date_input("⏰ Date d'expiration", value=date.today())
                    description = st.text_input("📝 Description", placeholder="Ex: CQ mammographe fantôme CDMAM")

                notes = st.text_area("📋 Notes / Observations", height=80, placeholder="Résultats, non-conformités...")

                # Upload fichier PDF
                uploaded = st.file_uploader(
                    "📎 Joindre le PV (PDF)",
                    type=["pdf"],
                    key="conf_upload"
                )

                if st.form_submit_button("💾 Enregistrer le contrôle", use_container_width=True):
                    if not sel_equip or sel_equip == "—":
                        st.error("❌ Sélectionnez un équipement")
                    elif date_exp <= date_ctrl:
                        st.error("❌ La date d'expiration doit être postérieure à la date de contrôle")
                    else:
                        fichier_bytes = uploaded.read() if uploaded else None
                        fichier_nom = uploaded.name if uploaded else ""

                        # Calcul du statut
                        jours_restants = (date_exp - date.today()).days
                        if jours_restants < 0:
                            statut = "Expiré"
                        elif jours_restants <= 30:
                            statut = "Bientôt expiré"
                        else:
                            statut = "Conforme"

                        data = {
                            "equipement": sel_equip,
                            "client": sel_client,
                            "type_controle": type_ctrl,
                            "description": description,
                            "date_controle": date_ctrl.strftime("%Y-%m-%d"),
                            "date_expiration": date_exp.strftime("%Y-%m-%d"),
                            "fichier_nom": fichier_nom,
                            "statut": statut,
                            "notes": notes,
                            "created_by": username,
                        }

                        if ajouter_conformite(data, fichier_bytes):
                            log_audit(username, "CONFORMITE_ADDED",
                                      f"{sel_equip} — {type_ctrl} (exp: {date_exp})", "QHSE")
                            st.success(f"✅ Contrôle **{type_ctrl}** enregistré pour **{sel_equip}** !")

                            # Notification Telegram si bientôt expiré
                            if statut in ("Bientôt expiré", "Expiré"):
                                try:
                                    from notifications import Notifier
                                    notifier = Notifier()
                                    if notifier.telegram_ok:
                                        msg = (
                                            f"⚠️ *ALERTE CONFORMITÉ*\n\n"
                                            f"🔬 {sel_equip} ({sel_client})\n"
                                            f"📋 {type_ctrl}\n"
                                            f"⏰ Expiration: {date_exp}\n"
                                            f"{'🔴 EXPIRÉ !' if statut == 'Expiré' else '🟠 Expire dans ' + str(jours_restants) + ' jours'}"
                                        )
                                        notifier.envoyer_telegram(msg)
                                except Exception:
                                    pass

                            st.rerun()

    # ============ TABLEAU DE CONFORMITÉ ============
    df_conf = lire_conformite(client=filtre_client)

    if df_conf.empty:
        st.info("📭 Aucun contrôle de conformité enregistré.")
        return

    # Mettre à jour les statuts dynamiquement
    today = date.today()
    statuts = []
    for _, row in df_conf.iterrows():
        try:
            exp = pd.to_datetime(row["date_expiration"]).date()
            jours = (exp - today).days
            if jours < 0:
                statuts.append("Expiré")
            elif jours <= 30:
                statuts.append("Bientôt expiré")
            else:
                statuts.append("Conforme")
        except Exception:
            statuts.append("Inconnu")
    df_conf["statut_calc"] = statuts

    # ============ KPIs ============
    nb_total = len(df_conf)
    nb_conforme = len(df_conf[df_conf["statut_calc"] == "Conforme"])
    nb_bientot = len(df_conf[df_conf["statut_calc"] == "Bientôt expiré"])
    nb_expire = len(df_conf[df_conf["statut_calc"] == "Expiré"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📋 Total", nb_total)
    col2.metric("🟢 Conformes", nb_conforme)
    col3.metric("🟠 Bientôt expirés", nb_bientot)
    col4.metric("🔴 Expirés", nb_expire)

    if nb_expire > 0:
        st.error(f"⚠️ **{nb_expire} contrôle(s) expiré(s) !** Action requise immédiatement.")
    elif nb_bientot > 0:
        st.warning(f"🔔 **{nb_bientot} contrôle(s) expirent dans les 30 prochains jours.**")
    else:
        st.success("✅ Tous les contrôles sont à jour !")

    st.markdown("---")

    # ============ LISTE DES CONTRÔLES ============
    for _, row in df_conf.iterrows():
        statut = row["statut_calc"]
        equip = row["equipement"]
        client = row.get("client", "")
        type_c = row["type_controle"]
        date_exp_str = str(row["date_expiration"])[:10]
        conf_id = row["id"]

        # Badge couleur
        if statut == "Expiré":
            badge = "🔴"
            border_color = "#ef4444"
        elif statut == "Bientôt expiré":
            badge = "🟠"
            border_color = "#f59e0b"
        else:
            badge = "🟢"
            border_color = "#22c55e"

        try:
            exp_date = pd.to_datetime(row["date_expiration"]).date()
            jours_rest = (exp_date - today).days
            jours_txt = f"{jours_rest}j" if jours_rest >= 0 else f"Expiré depuis {abs(jours_rest)}j"
        except Exception:
            jours_txt = "?"

        st.markdown(
            f"""<div style="border-left: 4px solid {border_color}; padding: 8px 12px; margin-bottom: 8px;
                 background: rgba(255,255,255,0.03); border-radius: 6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-weight:bold;">{badge} {equip}</span>
                        <span style="color:#94a3b8; font-size:0.85rem;"> — {client}</span><br>
                        <span style="color:#94a3b8; font-size:0.85rem;">
                            📋 {type_c} | ⏰ Exp: {date_exp_str} ({jours_txt})
                        </span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.85rem; color:{border_color}; font-weight:bold;">{statut}</span>
                    </div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # Actions : Télécharger PDF + Supprimer
        col_dl, col_del = st.columns([5, 1])

        if row.get("fichier_nom"):
            with col_dl:
                nom_f, data_f = lire_fichier_conformite(conf_id)
                if data_f:
                    st.download_button(
                        f"📥 {nom_f}",
                        data=data_f,
                        file_name=nom_f,
                        mime="application/pdf",
                        key=f"dl_conf_{conf_id}",
                    )

        if not is_lecteur:
            with col_del:
                if st.button("🗑️", key=f"del_conf_{conf_id}", help="Supprimer"):
                    supprimer_conformite(conf_id)
                    log_audit(username, "CONFORMITE_DELETED",
                              f"{equip} — {type_c}", "QHSE")
                    st.rerun()
