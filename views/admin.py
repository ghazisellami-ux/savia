# ==========================================
# ⚙️ PAGE ADMINISTRATION
# ==========================================
import streamlit as st
import pandas as pd
from auth import (
    lister_utilisateurs, creer_utilisateur, modifier_utilisateur,
    changer_mot_de_passe, supprimer_utilisateur,
    get_current_user, require_role,
    get_permissions, save_permissions, DEFAULT_PERMISSIONS
)
from db_engine import lire_audit, log_audit, get_config, set_config
from backup import creer_backup, lister_backups, restaurer_backup
from i18n import t


def page_admin():
    user = get_current_user()
    user_role = user.get("role", "") if user else ""
    
    if user_role not in ("Admin", "Manager"):
        st.error("🚫 Accès réservé aux administrateurs et managers")
        return
    
    is_admin = (user_role == "Admin")

    st.title(t("admin") if is_admin else "👥 Gestion des Utilisateurs")
    username = user.get("username", "?") if user else "?"

    if is_admin:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            t("user_management"), t("audit_log"), t("backup_management"),
            "📝 Journal Système", "⚙️ Paramètres", "🔐 Permissions par rôle"
        ])
    else:
        # Manager: seulement gestion des utilisateurs
        tab1 = st.container()

    # ============ UTILISATEURS ============
    with tab1:
        st.subheader(t("user_management"))

        # Ajouter utilisateur (Admin uniquement)
        if not is_admin:
            st.info("💼 En tant que Manager, vous pouvez modifier ou supprimer des comptes existants, mais pas en créer de nouveaux.")
        if is_admin:
          with st.expander(t("add_user"), expanded=False):
            # Rôle et client/technicien HORS formulaire pour réactivité
            col_role, col_extra = st.columns(2)
            with col_role:
                new_role = st.selectbox(t("role"), ["Manager", "Responsable Technique", "Gestionnaire de stock", "Technicien", "Lecteur", "Admin"], key="new_user_role")

            # Sélecteur de client pour Lecteur
            new_client = ""
            selected_tech_name = ""
            if new_role == "Lecteur":
                with col_extra:
                    from db_engine import lire_equipements
                    df_eq = lire_equipements()
                    clients_list = sorted(df_eq["Client"].dropna().unique().tolist()) if not df_eq.empty and "Client" in df_eq.columns else []
                    if clients_list:
                        new_client = st.selectbox(
                            "🏢 Client associé *",
                            clients_list,
                            key="new_user_client",
                            help="Ce lecteur ne verra que les données de ce client"
                        )
                    else:
                        st.warning("⚠️ Aucun client trouvé. Ajoutez des équipements d'abord.")

            # Sélecteur de technicien pour Technicien
            if new_role == "Technicien":
                with col_extra:
                    from db_engine import lire_techniciens
                    df_tech = lire_techniciens()
                    if not df_tech.empty and "nom" in df_tech.columns:
                        tech_names = sorted([f"{r.nom} {r.prenom}" for r in df_tech.itertuples() if r.nom])
                    else:
                        tech_names = []
                    if tech_names:
                        selected_tech_name = st.selectbox(
                            "🔧 Technicien associé *",
                            tech_names,
                            key="new_user_tech",
                            help="Le nom complet sera pré-rempli et servira à filtrer les interventions dans SIC Terrain"
                        )
                    else:
                        st.warning("⚠️ Aucun technicien dans l'équipe. Ajoutez-en dans SAV → Équipe Technique.")

            with st.form("form_new_user"):
                col1, col2 = st.columns(2)
                with col1:
                    new_username = st.text_input(t("username"))
                    new_password = st.text_input(t("password"), type="password")
                with col2:
                    default_nom = selected_tech_name if new_role == "Technicien" and selected_tech_name else ""
                    new_nom = st.text_input(t("full_name"), value=default_nom)
                    new_email = st.text_input(t("email"))

                if new_role == "Lecteur" and new_client:
                    st.info(f"🏢 Ce lecteur sera associé au client : **{new_client}**")
                if new_role == "Technicien" and selected_tech_name:
                    st.info(f"🔧 Ce compte sera lié au technicien : **{selected_tech_name}**")

                if st.form_submit_button(t("save"), use_container_width=True):
                    if not new_username or not new_password:
                        st.error("❌ Nom d'utilisateur et mot de passe requis")
                    elif new_role == "Lecteur" and not new_client:
                        st.error("❌ Un Lecteur doit être associé à un client")
                    elif creer_utilisateur(new_username, new_password, new_nom, new_role, new_email, new_client):
                        log_audit(username, "USER_CREATED",
                                  f"{new_username} ({new_role}) → Client: {new_client}" if new_client else f"{new_username} ({new_role})", "Admin")

                        # --- Sync automatique vers SIC Terrain ---
                        try:
                            import os, urllib.request, json as json_mod
                            terrain_url = os.environ.get("SIC_TERRAIN_URL", "").strip().rstrip("/")
                            if terrain_url:
                                sync_data = json_mod.dumps({
                                    "username": new_username,
                                    "password": new_password,
                                    "nom_complet": new_nom,
                                    "role": new_role,
                                    "email": new_email,
                                    "client": new_client,
                                }).encode("utf-8")
                                req = urllib.request.Request(
                                    f"{terrain_url}/api/admin/users",
                                    data=sync_data,
                                    headers={"Content-Type": "application/json"},
                                    method="POST",
                                )
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    result = json_mod.loads(resp.read())
                                    st.toast(f"🔄 Sync SIC Terrain : {result.get('message', 'OK')}", icon="✅")
                            else:
                                st.toast("⚠️ SIC_TERRAIN_URL non configuré — compte non synchronisé", icon="⚠️")
                        except Exception as sync_err:
                            st.toast(f"⚠️ Sync Terrain: {sync_err}", icon="⚠️")

                        st.success(f"✅ Utilisateur **{new_username}** créé !")
                        st.rerun()
                    else:
                        st.error("❌ Ce nom d'utilisateur existe déjà")


        if is_admin:
            pass  # Fermeture du bloc expander ci-dessus

        # Liste utilisateurs
        users = lister_utilisateurs()
        if users:
            for u in users:
                role_emoji = {"Admin": "👑", "Manager": "💼", "Responsable Technique": "🎯", "Gestionnaire de stock": "📦", "Technicien": "🔧", "Lecteur": "👁️"}.get(u["role"], "❓")
                active_txt = "✅" if u["actif"] else "❌"

                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
                    client_info = f" → 🏥 {u.get('client', '')}" if u.get("client") else ""
                    col1.markdown(f"**{role_emoji} {u['username']}** — {u['nom_complet']}{client_info}")
                    col2.markdown(f"📧 {u.get('email', '')}")
                    col3.markdown(f"{active_txt} {u['role']}")

                    # Bouton modifier
                    if col4.button("✏️", key=f"edit_user_{u['id']}", help="Modifier"):
                        st.session_state[f"editing_user_{u['id']}"] = True

                    # Bouton supprimer (HITL Pillier 4: Confirmation explicite)
                    if u["username"] != "admin":
                        if col5.button("🗑️", key=f"del_user_{u['id']}", help=t("delete")):
                            st.session_state[f"confirm_del_user_{u['id']}"] = True

                    # Dialogue de confirmation (HITL)
                    if st.session_state.get(f"confirm_del_user_{u['id']}", False):
                        st.warning(f"⚠️ Êtes-vous sûr de vouloir supprimer l'utilisateur **{u['username']}** ?")
                        c_yes, c_no = st.columns(2)
                        if c_yes.button("✅ Oui, Supprimer", key=f"del_user_yes_{u['id']}", type="primary", use_container_width=True):
                            supprimer_utilisateur(u["id"])
                            log_audit(username, "USER_DELETED", u["username"], "Admin")
                            del st.session_state[f"confirm_del_user_{u['id']}"]
                            st.success(f"Utilisateur {u['username']} supprimé")
                            st.rerun()
                        if c_no.button("❌ Annuler", key=f"del_user_no_{u['id']}", use_container_width=True):
                            del st.session_state[f"confirm_del_user_{u['id']}"]
                            st.rerun()

                    # Formulaire de modification inline
                    if st.session_state.get(f"editing_user_{u['id']}", False):
                        with st.form(f"form_edit_user_{u['id']}"):
                            st.markdown(f"**✏️ Modifier : {u['username']}**")
                            ec1, ec2 = st.columns(2)
                            with ec1:
                                edit_nom = st.text_input("Nom complet", value=u.get("nom_complet", ""), key=f"edit_nom_{u['id']}")
                                edit_email = st.text_input("Email", value=u.get("email", ""), key=f"edit_email_{u['id']}")
                            with ec2:
                                all_roles = ["Manager", "Responsable Technique", "Gestionnaire de stock", "Technicien", "Lecteur", "Admin"]
                                edit_role = st.selectbox("Rôle", all_roles,
                                    index=all_roles.index(u["role"]) if u["role"] in all_roles else 0,
                                    key=f"edit_role_{u['id']}")
                                edit_password = st.text_input("Nouveau mot de passe (laisser vide = inchangé)", type="password", key=f"edit_pwd_{u['id']}")
                            edit_actif = st.checkbox("Compte actif", value=bool(u.get("actif", 1)), key=f"edit_actif_{u['id']}")

                            bc1, bc2 = st.columns(2)
                            save_clicked = bc1.form_submit_button("💾 Sauvegarder", use_container_width=True)
                            cancel_clicked = bc2.form_submit_button("❌ Annuler", use_container_width=True)

                            if save_clicked:
                                modifier_utilisateur(u["id"], edit_nom, edit_role, edit_email, int(edit_actif))
                                if edit_password:
                                    changer_mot_de_passe(u["id"], edit_password)
                                log_audit(username, "USER_MODIFIED", f"{u['username']} → {edit_role}, actif={edit_actif}", "Admin")

                                # Sync vers SIC Terrain
                                try:
                                    import os, urllib.request, json as json_mod
                                    terrain_url = os.environ.get("SIC_TERRAIN_URL", "").strip().rstrip("/")
                                    if terrain_url and edit_password:
                                        sync_data = json_mod.dumps({
                                            "username": u["username"],
                                            "password": edit_password,
                                            "nom_complet": edit_nom,
                                            "role": edit_role,
                                            "email": edit_email,
                                        }).encode("utf-8")
                                        req = urllib.request.Request(
                                            f"{terrain_url}/api/admin/users",
                                            data=sync_data,
                                            headers={"Content-Type": "application/json"},
                                            method="POST",
                                        )
                                        with urllib.request.urlopen(req, timeout=10) as resp:
                                            pass
                                except Exception:
                                    pass

                                st.session_state[f"editing_user_{u['id']}"] = False
                                st.success(f"✅ Utilisateur **{u['username']}** modifié")
                                st.rerun()

                            if cancel_clicked:
                                st.session_state[f"editing_user_{u['id']}"] = False
                                st.rerun()

                    st.markdown("---")

    # ============ JOURNAL D'AUDIT ============ (Admin uniquement)
    if not is_admin:
        return
    with tab2:
        st.subheader(t("audit_log"))

        col_limit, col_filter = st.columns(2)
        limit = col_limit.number_input("Dernières entrées", min_value=10, max_value=500, value=50)
        df_audit = lire_audit(limit=limit)

        if df_audit.empty:
            st.info(t("no_data"))
        else:
            action_filter = col_filter.selectbox(
                t("filter"),
                ["Toutes"] + df_audit["action"].unique().tolist()
            )
            if action_filter != "Toutes":
                df_audit = df_audit[df_audit["action"] == action_filter]

            st.dataframe(df_audit, use_container_width=True, hide_index=True)

    # ============ SAUVEGARDES ============
    with tab3:
        st.subheader(t("backup_management"))

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 " + t("create_backup"), use_container_width=True):
                result = creer_backup()
                if result:
                    log_audit(username, "BACKUP_CREATED", result, "Admin")
                    st.success(f"✅ Sauvegarde créée : {result}")
                    st.rerun()
                else:
                    st.error("❌ Erreur lors de la sauvegarde")

        backups = lister_backups()
        if not backups:
            st.info("Aucune sauvegarde disponible")
        else:
            st.markdown(f"**{len(backups)} sauvegarde(s) disponible(s)**")
            for b in backups:
                col1, col2, col3 = st.columns([4, 2, 1])
                col1.markdown(f"📦 `{b['nom']}`")
                col2.markdown(f"📅 {b['date']} — {b['taille']}")
                if col3.button("↩️", key=f"restore_{b['nom']}", help=t("restore_backup")):
                    if restaurer_backup(b["path"]):
                        log_audit(username, "BACKUP_RESTORED", b["nom"], "Admin")
                        st.success(f"✅ Base restaurée depuis {b['nom']}")
                        st.rerun()
                    else:
                        st.error("❌ Erreur lors de la restauration")

        # ============ TÉLÉCHARGER LA BASE ============
        st.markdown("---")
        st.subheader("📥 Télécharger la base de données")

        col_dl1, col_dl2 = st.columns(2)

        # Télécharger le fichier SQLite brut
        with col_dl1:
            import os
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sic_radiologie.db")
            if os.path.exists(db_path):
                with open(db_path, "rb") as f:
                    db_bytes = f.read()
                st.download_button(
                    "💾 Télécharger (.db)",
                    data=db_bytes,
                    file_name="sic_radiologie.db",
                    mime="application/octet-stream",
                    use_container_width=True,
                )
            else:
                st.warning("Fichier de base de données introuvable")

        # Télécharger en JSON
        with col_dl2:
            try:
                from data_sync import exporter_toutes_tables
                import json as json_mod
                backup_json = exporter_toutes_tables()
                json_str = json_mod.dumps(backup_json, ensure_ascii=False, indent=2, default=str)
                st.download_button(
                    "📋 Télécharger (.json)",
                    data=json_str,
                    file_name="sic_radiologie_export.json",
                    mime="application/json",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Erreur export JSON : {e}")

    # ============ JOURNAL SYSTÈME (LOGS & ERREURS) ============
    with tab4:
        st.subheader("📝 Journal Système — SAVIA")
        st.caption("Historique complet des actions, modifications et erreurs de l'application.")

        from datetime import datetime, timedelta

        # --- Filtres ---
        fc1, fc2, fc3 = st.columns(3)
        log_period = fc1.selectbox("📅 Période", ["Aujourd'hui", "7 derniers jours", "30 derniers jours", "Tout"], key="log_period")
        log_type = fc2.selectbox("📋 Type", ["Tous", "Modifications", "Connexions", "Erreurs", "Interventions", "Sécurité"], key="log_type")

        # Charger les logs d'audit
        audit_logs = lire_audit()
        if not audit_logs.empty:
            # Filtrer par période
            if "date" in audit_logs.columns:
                audit_logs["date"] = pd.to_datetime(audit_logs["date"], errors="coerce")
                now = datetime.now()
                if log_period == "Aujourd'hui":
                    audit_logs = audit_logs[audit_logs["date"].dt.date == now.date()]
                elif log_period == "7 derniers jours":
                    audit_logs = audit_logs[audit_logs["date"] >= now - timedelta(days=7)]
                elif log_period == "30 derniers jours":
                    audit_logs = audit_logs[audit_logs["date"] >= now - timedelta(days=30)]

            # Filtrer par type
            if log_type != "Tous" and "action" in audit_logs.columns:
                type_map = {
                    "Modifications": ["UPDATED", "CREATED", "DELETED", "CHANGED", "MODIFIED", "ADDED"],
                    "Connexions": ["LOGIN", "LOGOUT", "SESSION"],
                    "Erreurs": ["ERROR", "FAIL", "ERREUR"],
                    "Interventions": ["INTERVENTION", "INTERV"],
                    "Sécurité": ["LOGIN", "PASSWORD", "PERMISSION", "LICENSE", "BACKUP", "RESTORE"],
                }
                keywords = type_map.get(log_type, [])
                if keywords:
                    mask = audit_logs["action"].str.upper().apply(
                        lambda x: any(k in str(x) for k in keywords)
                    )
                    audit_logs = audit_logs[mask]

            # Recherche texte
            search_q = fc3.text_input("🔍 Rechercher", key="log_search", placeholder="mot-clé...")
            if search_q:
                search_lower = search_q.lower()
                mask = audit_logs.apply(lambda row: search_lower in " ".join(row.astype(str)).lower(), axis=1)
                audit_logs = audit_logs[mask]

            # Résumé
            st.markdown(f"**{len(audit_logs)} entrée(s) trouvée(s)**")

            # KPIs rapides
            k1, k2, k3, k4 = st.columns(4)
            total_today = 0
            total_errors = 0
            total_logins = 0
            total_interv = 0
            if "action" in audit_logs.columns:
                actions_upper = audit_logs["action"].str.upper()
                total_errors = actions_upper.str.contains("ERROR|FAIL|ERREUR", na=False).sum()
                total_logins = actions_upper.str.contains("LOGIN", na=False).sum()
                total_interv = actions_upper.str.contains("INTERVENTION|INTERV", na=False).sum()
            if "date" in audit_logs.columns:
                total_today = len(audit_logs[audit_logs["date"].dt.date == datetime.now().date()])

            k1.metric("📊 Total", len(audit_logs))
            k2.metric("⚠️ Erreurs", total_errors)
            k3.metric("🔑 Connexions", total_logins)
            k4.metric("🔧 Interventions", total_interv)

            st.markdown("---")

            # Affichage du tableau
            display_cols = [c for c in ["date", "utilisateur", "action", "details", "module"] if c in audit_logs.columns]
            rename_map = {
                "date": "📅 Date",
                "utilisateur": "👤 Utilisateur",
                "action": "📋 Action",
                "details": "📝 Détails",
                "module": "📦 Module",
            }
            df_display = audit_logs[display_cols].sort_values(display_cols[0], ascending=False).rename(columns=rename_map)
            st.dataframe(df_display, use_container_width=True, hide_index=True, height=500)

            # Export CSV
            st.markdown("---")
            import io
            csv_buf = io.StringIO()
            df_display.to_csv(csv_buf, index=False, sep=";")
            st.download_button(
                "📄 Exporter les logs (CSV)",
                data=csv_buf.getvalue(),
                file_name=f"savia_logs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("📭 Aucun log enregistré pour le moment.")
    # ============ PARAMÈTRES ============
    with tab5:
        st.subheader("⚙️ Paramètres de l'application")

        # --- Devise ---
        st.markdown("#### 💱 Devise")
        devises = [
            "EUR - Euro",
            "USD - Dollar américain",
            "GBP - Livre sterling",
            "TND - Dinar tunisien",
            "MAD - Dirham marocain",
            "DZD - Dinar algérien",
            "XOF - Franc CFA",
            "CHF - Franc suisse",
            "CAD - Dollar canadien",
            "SAR - Riyal saoudien",
            "AED - Dirham émirati",
            "QAR - Riyal qatari",
        ]
        devise_actuelle = get_config("devise", "EUR")
        # Trouver l'index de la devise actuelle
        codes = [d.split(" - ")[0] for d in devises]
        idx = codes.index(devise_actuelle) if devise_actuelle in codes else 0

        choix = st.selectbox("Devise utilisée dans l'application", devises, index=idx)
        code_devise = choix.split(" - ")[0]

        if code_devise != devise_actuelle:
            set_config("devise", code_devise)
            log_audit(username, "CONFIG_CHANGED", f"devise: {devise_actuelle} -> {code_devise}", "Admin")
            st.success(f"Devise changee : **{choix}**")
            st.rerun()

        st.info(f"Devise actuelle : **{devise_actuelle}**")

        # --- Licence ---
        st.markdown("---")
        st.markdown("#### Licence")

        from license_manager import verifier_licence, enregistrer_cle_licence

        lic_statut = verifier_licence()
        if lic_statut["valide"]:
            jrs = lic_statut["jours_restants"]
            couleur = "green" if jrs > 30 else "orange" if jrs > 15 else "red"
            st.markdown(
                f"**Client :** {lic_statut['client']}  \n"
                f"**Expiration :** {lic_statut['date_expiration']}  \n"
                f"**Jours restants :** :{couleur}[**{jrs}**]"
            )
            if lic_statut["alerte_15j"]:
                st.warning(
                    f"Licence expire dans {jrs} jour(s) ! "
                    "Demandez une nouvelle cle a votre fournisseur."
                )
        else:
            st.error(f"Licence invalide : {lic_statut.get('erreur', 'inconnue')}")

        st.markdown("**Mettre a jour la cle d'acces :**")
        nouvelle_cle = st.text_area(
            "Cle d'acces",
            height=80,
            placeholder="Collez la nouvelle cle ici...",
            key="admin_license_key",
        )
        if st.button("Activer / Renouveler", key="btn_activate_license"):
            ok, msg = enregistrer_cle_licence(nouvelle_cle)
            if ok:
                log_audit(username, "LICENSE_UPDATED", msg, "Admin")
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # ============ PERMISSIONS PAR RÔLE ============
    with tab6:
        st.subheader("🔐 Permissions par rôle")
        st.caption("Activez ou désactivez l'accès aux pages pour chaque rôle.")

        perms = get_permissions()

        # Noms lisibles des pages
        PAGE_LABELS = {
            "dashboard": "📊 Dashboard",
            "supervision": "📡 Supervision",
            "equipements": "🏥 Équipements",
            "predictions": "🔮 Prédictions",
            "base_connaissances": "📚 Base Connaissances",
            "sav": "🛠️ SAV & Interventions",
            "demandes": "📋 Demandes d'Intervention",
            "planning": "📅 Planning",
            "pieces": "🔩 Pièces détachées",
            "reports": "📈 Rapports",
            "contrats": "📋 Contrats & SLA",
            "conformite": "🛡️ QHSE Conformité",
            "admin": "⚙️ Administration",
            "settings": "⚙️ Paramètres",
        }

        # Matrice de permissions
        roles = ["Admin", "Manager", "Responsable Technique", "Gestionnaire de stock", "Technicien", "Lecteur"]
        all_pages = list(DEFAULT_PERMISSIONS["Admin"].keys())

        # Header
        cols = st.columns([3] + [1] * len(roles))
        cols[0].markdown("**Page**")
        for i, role in enumerate(roles):
            cols[i + 1].markdown(f"**{role}**")

        st.markdown("---")

        changed = False
        for page_key in all_pages:
            cols = st.columns([3] + [1] * len(roles))
            label = PAGE_LABELS.get(page_key, page_key)
            cols[0].markdown(label)

            for i, role in enumerate(roles):
                current = perms.get(role, {}).get(page_key, False)
                # Admin garde toujours accès à admin et settings
                disabled = (role == "Admin" and page_key in ("admin", "settings", "dashboard"))
                new_val = cols[i + 1].checkbox(
                    f"{role}_{page_key}",
                    value=current,
                    key=f"perm_{role}_{page_key}",
                    label_visibility="collapsed",
                    disabled=disabled,
                )
                if new_val != current and not disabled:
                    perms[role][page_key] = new_val
                    changed = True

        if changed:
            save_permissions(perms)
            log_audit(username, "PERMISSIONS_UPDATED", "Matrice de permissions modifiée", "Admin")
            st.success("✅ Permissions mises à jour !")
            st.rerun()

