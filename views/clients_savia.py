# ==========================================
# 🏢 GESTION DES CLIENTS SAVIA
# ==========================================
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from db_engine import get_db, log_audit
from auth import get_current_user, require_role


def _init_clients_table():
    """Créer la table clients_savia si elle n'existe pas."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients_savia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                contact_nom TEXT DEFAULT '',
                contact_email TEXT DEFAULT '',
                contact_tel TEXT DEFAULT '',
                adresse TEXT DEFAULT '',
                secteur TEXT DEFAULT '',
                paiement_mensuel REAL DEFAULT 0,
                paiement_annuel REAL DEFAULT 0,
                date_debut_contrat TEXT DEFAULT '',
                date_fin_contrat TEXT DEFAULT '',
                type_contrat TEXT DEFAULT 'Mensuel',
                statut_contrat TEXT DEFAULT 'Actif',
                statut_paiement TEXT DEFAULT 'À jour',
                notes TEXT DEFAULT '',
                date_creation TEXT DEFAULT '',
                derniere_modification TEXT DEFAULT '',
                url_savia TEXT DEFAULT '',
                url_terrain TEXT DEFAULT ''
            )
        """)
        
        # Ajouter les colonnes si la table existait déjà
        try:
            conn.execute("ALTER TABLE clients_savia ADD COLUMN url_savia TEXT DEFAULT ''")
        except:
            pass
        try:
            conn.execute("ALTER TABLE clients_savia ADD COLUMN url_terrain TEXT DEFAULT ''")
        except:
            pass
        try:
            conn.execute("ALTER TABLE clients_savia ADD COLUMN ip_vps TEXT DEFAULT ''")
        except:
            pass


def _lire_clients():
    """Lire tous les clients."""
    _init_clients_table()
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM clients_savia ORDER BY nom").fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def _ajouter_client(data):
    """Ajouter un nouveau client."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO clients_savia 
            (nom, contact_nom, contact_email, contact_tel, adresse, secteur,
             paiement_mensuel, paiement_annuel, date_debut_contrat, date_fin_contrat,
             type_contrat, statut_contrat, statut_paiement, notes, date_creation, derniere_modification, url_savia, url_terrain, ip_vps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["nom"], data.get("contact_nom", ""), data.get("contact_email", ""),
            data.get("contact_tel", ""), data.get("adresse", ""), data.get("secteur", ""),
            data.get("paiement_mensuel", 0), data.get("paiement_annuel", 0),
            data.get("date_debut_contrat", ""), data.get("date_fin_contrat", ""),
            data.get("type_contrat", "Mensuel"), data.get("statut_contrat", "Actif"),
            data.get("statut_paiement", "À jour"), data.get("notes", ""),
            now, now, data.get("url_savia", ""), data.get("url_terrain", ""), data.get("ip_vps", "")
        ))


def _modifier_client(client_id, data):
    """Modifier un client existant."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("""
            UPDATE clients_savia SET
                nom=?, contact_nom=?, contact_email=?, contact_tel=?, adresse=?, secteur=?,
                paiement_mensuel=?, paiement_annuel=?, date_debut_contrat=?, date_fin_contrat=?,
                type_contrat=?, statut_contrat=?, statut_paiement=?, notes=?, derniere_modification=?,
                url_savia=?, url_terrain=?, ip_vps=?
            WHERE id=?
        """, (
            data["nom"], data.get("contact_nom", ""), data.get("contact_email", ""),
            data.get("contact_tel", ""), data.get("adresse", ""), data.get("secteur", ""),
            data.get("paiement_mensuel", 0), data.get("paiement_annuel", 0),
            data.get("date_debut_contrat", ""), data.get("date_fin_contrat", ""),
            data.get("type_contrat", "Mensuel"), data.get("statut_contrat", "Actif"),
            data.get("statut_paiement", "À jour"), data.get("notes", ""),
            now, data.get("url_savia", ""), data.get("url_terrain", ""), data.get("ip_vps", ""), client_id
        ))


def _supprimer_client(client_id):
    """Supprimer un client."""
    with get_db() as conn:
        conn.execute("DELETE FROM clients_savia WHERE id=?", (client_id,))


def page_clients_savia():
    """Page de gestion des clients SAVIA."""
    if not require_role("Admin"):
        st.error("🚫 Accès réservé aux administrateurs")
        return

    st.title("🏢 Gestion des Clients SAVIA")
    user = get_current_user()
    username = user.get("username", "?") if user else "?"

    _init_clients_table()
    df_clients = _lire_clients()

    from db_engine import get_config
    devise = get_config("devise", "EUR")

    # ============ KPIs ============
    nb_clients = len(df_clients)
    nb_actifs = len(df_clients[df_clients["statut_contrat"] == "Actif"]) if not df_clients.empty else 0
    nb_expires = 0
    revenu_mensuel = 0
    revenu_annuel = 0

    if not df_clients.empty:
        revenu_mensuel = df_clients["paiement_mensuel"].sum()
        revenu_annuel = df_clients["paiement_annuel"].sum()
        # Contrats expirés ou expirant bientôt
        today = date.today()
        for _, row in df_clients.iterrows():
            try:
                fin = datetime.strptime(str(row["date_fin_contrat"]), "%Y-%m-%d").date()
                if fin < today:
                    nb_expires += 1
            except Exception:
                pass

    k1, k2, k3, k4, k5 = st.columns([1, 1, 1, 2.5, 2.5])
    k1.metric("👥 Clients Total", nb_clients)
    k2.metric("✅ Actifs", nb_actifs)
    k3.metric("⚠️ Expirés", nb_expires)
    k4.metric(f"💰 Revenu Mensuel", f"{revenu_mensuel:,.0f} {devise}")
    k5.metric(f"📊 Revenu Annuel", f"{revenu_annuel:,.0f} {devise}")

    st.markdown("---")

    # ============ ONGLETS ============
    tab_list, tab_add = st.tabs(["📋 Liste des Clients", "➕ Nouveau Client"])

    # ============ LISTE ============
    with tab_list:
        if df_clients.empty:
            st.info("📭 Aucun client enregistré. Ajoutez votre premier client !")
        else:
            # Filtres
            fc1, fc2, fc3 = st.columns(3)
            filtre_statut = fc1.selectbox("📊 Statut contrat", ["Tous", "Actif", "Expiré", "Suspendu", "Résilié"], key="cl_filtre_statut")
            filtre_paiement = fc2.selectbox("💰 Paiement", ["Tous", "À jour", "En retard", "Impayé"], key="cl_filtre_paiement")
            filtre_search = fc3.text_input("🔍 Rechercher", key="cl_search", placeholder="Nom du client...")

            df_f = df_clients.copy()
            if filtre_statut != "Tous":
                df_f = df_f[df_f["statut_contrat"] == filtre_statut]
            if filtre_paiement != "Tous":
                df_f = df_f[df_f["statut_paiement"] == filtre_paiement]
            if filtre_search:
                df_f = df_f[df_f["nom"].str.contains(filtre_search, case=False, na=False)]

            st.markdown(f"**{len(df_f)} client(s)**")

            # Tableau récapitulatif
            for _, client in df_f.iterrows():
                cid = client["id"]
                nom = client["nom"]
                statut = client["statut_contrat"]
                paiement = client["statut_paiement"]
                fin_contrat = client.get("date_fin_contrat", "")

                # Couleurs statut
                s_color = {"Actif": "#22c55e", "Expiré": "#ef4444", "Suspendu": "#f59e0b", "Résilié": "#6b7280"}.get(statut, "#64748b")
                p_color = {"À jour": "#22c55e", "En retard": "#f59e0b", "Impayé": "#ef4444"}.get(paiement, "#64748b")
                s_emoji = {"Actif": "✅", "Expiré": "❌", "Suspendu": "⏸️", "Résilié": "🚫"}.get(statut, "❓")
                p_emoji = {"À jour": "💚", "En retard": "🟡", "Impayé": "🔴"}.get(paiement, "⚪")

                # Vérifier si contrat expire bientôt
                alerte_expiration = ""
                try:
                    fin_d = datetime.strptime(str(fin_contrat), "%Y-%m-%d").date()
                    jours_restants = (fin_d - date.today()).days
                    if jours_restants < 0:
                        alerte_expiration = f" — ⚠️ **Expiré depuis {abs(jours_restants)}j**"
                    elif jours_restants <= 30:
                        alerte_expiration = f" — 🔔 **Expire dans {jours_restants}j**"
                except Exception:
                    pass

                with st.expander(f"{s_emoji} **{nom}** | {p_emoji} {paiement} | 📅 Fin: {fin_contrat}{alerte_expiration}"):
                    # Infos client
                    ic1, ic2, ic3 = st.columns(3)
                    ic1.markdown(f"**🏢 Nom :** {nom}")
                    ic1.markdown(f"**👤 Contact :** {client.get('contact_nom', '-')}")
                    ic1.markdown(f"**📧 Email :** {client.get('contact_email', '-')}")
                    ic1.markdown(f"**📞 Tél :** {client.get('contact_tel', '-')}")

                    ic2.markdown(f"**📍 Adresse :** {client.get('adresse', '-')}")
                    ic2.markdown(f"**🏷️ Secteur :** {client.get('secteur', '-')}")
                    ic2.markdown(f"**📋 Type contrat :** {client.get('type_contrat', '-')}")
                    ic2.markdown(f"**📊 Statut :** <span style='color:{s_color};font-weight:700;'>{statut}</span>", unsafe_allow_html=True)

                    ic3.markdown(f"**💰 Mensuel :** {client.get('paiement_mensuel', 0):,.0f} {devise}")
                    ic3.markdown(f"**📊 Annuel :** {client.get('paiement_annuel', 0):,.0f} {devise}")
                    ic3.markdown(f"**📅 Début :** {client.get('date_debut_contrat', '-')}")
                    ic3.markdown(f"**📅 Fin :** {fin_contrat}")

                    # Liens
                    st.markdown("---")
                    l1, l2, l3 = st.columns([1,1,2])
                    
                    url_sav = client.get("url_savia", "")
                    url_ter = client.get("url_terrain", "")
                    
                    if url_sav:
                        url_sav = url_sav if url_sav.startswith("http") else "https://" + url_sav
                        l1.markdown(f'<a href="{url_sav}" target="_blank" style="display:block; text-align:center; background:#1e293b; border:1px solid #3b82f6; color:#3b82f6; padding:8px; border-radius:6px; text-decoration:none; font-weight:600;">💻 Ouvrir SAVIA</a>', unsafe_allow_html=True)
                    else:
                        l1.markdown("*(Aucun lien SAVIA)*")
                        
                    if url_ter:
                        url_ter = url_ter if url_ter.startswith("http") else "https://" + url_ter
                        l2.markdown(f'<a href="{url_ter}" target="_blank" style="display:block; text-align:center; background:#1e293b; border:1px solid #10b981; color:#10b981; padding:8px; border-radius:6px; text-decoration:none; font-weight:600;">📱 Ouvrir SIC Terrain</a>', unsafe_allow_html=True)
                    else:
                        l2.markdown("*(Aucun lien Terrain)*")

                    if client.get("notes"):
                        st.markdown(f"**📝 Notes :** {client['notes']}")
                    
                    if client.get("ip_vps"):
                        st.markdown(f"**🖥️ Adresse IP VPS :** `{client['ip_vps']}`")

                    # Formulaire de modification
                    st.markdown("---")
                    with st.form(f"edit_client_{cid}"):
                        st.caption("✏️ Modifier ce client")
                        e1, e2 = st.columns(2)
                        new_nom = e1.text_input("Nom", value=nom, key=f"en_{cid}")
                        new_contact = e2.text_input("Contact", value=client.get("contact_nom", ""), key=f"ec_{cid}")
                        new_email = e1.text_input("Email", value=client.get("contact_email", ""), key=f"ee_{cid}")
                        new_tel = e2.text_input("Téléphone", value=client.get("contact_tel", ""), key=f"et_{cid}")
                        new_adresse = e1.text_input("Adresse", value=client.get("adresse", ""), key=f"ea_{cid}")
                        new_secteur = e2.text_input("Secteur", value=client.get("secteur", ""), key=f"es_{cid}")

                        e3, e4 = st.columns(2)
                        new_mensuel = e3.number_input(f"Paiement Mensuel ({devise})", value=float(client.get("paiement_mensuel", 0)), key=f"em_{cid}")
                        new_annuel = e4.number_input(f"Paiement Annuel ({devise})", value=float(client.get("paiement_annuel", 0)), key=f"ey_{cid}")

                        e5, e6 = st.columns(2)
                        types_contrat = ["Mensuel", "Annuel", "Trimestriel", "Personnalisé"]
                        tc_idx = types_contrat.index(client.get("type_contrat", "Mensuel")) if client.get("type_contrat", "Mensuel") in types_contrat else 0
                        new_type = e5.selectbox("Type contrat", types_contrat, index=tc_idx, key=f"etp_{cid}")

                        statuts_contrat = ["Actif", "Expiré", "Suspendu", "Résilié"]
                        sc_idx = statuts_contrat.index(statut) if statut in statuts_contrat else 0
                        new_statut = e6.selectbox("Statut contrat", statuts_contrat, index=sc_idx, key=f"esc_{cid}")

                        e7, e8 = st.columns(2)
                        statuts_paiement = ["À jour", "En retard", "Impayé"]
                        sp_idx = statuts_paiement.index(paiement) if paiement in statuts_paiement else 0
                        new_paiement_st = e7.selectbox("Statut paiement", statuts_paiement, index=sp_idx, key=f"esp_{cid}")

                        new_debut = e8.text_input("Date début (YYYY-MM-DD)", value=client.get("date_debut_contrat", ""), key=f"ed_{cid}")
                        new_fin = e7.text_input("Date fin (YYYY-MM-DD)", value=fin_contrat, key=f"ef_{cid}")
                        
                        u1, u2 = st.columns(2)
                        new_url_savia = u1.text_input("Lien SAVIA (ex: sav.clinique.com)", value=client.get("url_savia", ""), key=f"usav_{cid}")
                        new_url_terrain = u2.text_input("Lien SIC Terrain (ex: sav.clinique.com/terrain)", value=client.get("url_terrain", ""), key=f"uter_{cid}")
                        
                        new_ip_vps = st.text_input("🖥️ Adresse IP (VPS)", value=client.get("ip_vps", ""), key=f"eip_{cid}")
                        
                        new_notes = st.text_area("Notes", value=client.get("notes", ""), key=f"eno_{cid}")

                        bc1, bc2 = st.columns(2)
                        if bc1.form_submit_button("💾 Sauvegarder", use_container_width=True):
                            _modifier_client(cid, {
                                "nom": new_nom, "contact_nom": new_contact,
                                "contact_email": new_email, "contact_tel": new_tel,
                                "adresse": new_adresse, "secteur": new_secteur,
                                "paiement_mensuel": new_mensuel, "paiement_annuel": new_annuel,
                                "date_debut_contrat": new_debut, "date_fin_contrat": new_fin,
                                "type_contrat": new_type, "statut_contrat": new_statut,
                                "statut_paiement": new_paiement_st, "notes": new_notes,
                                "url_savia": new_url_savia, "url_terrain": new_url_terrain,
                                "ip_vps": new_ip_vps
                            })
                            log_audit(username, "CLIENT_UPDATED", f"Client #{cid}: {new_nom}", "Clients")
                            st.success(f"✅ Client **{new_nom}** mis à jour")
                            st.rerun()

                    # Bouton supprimer (hors formulaire)
                    if st.button(f"🗑️ Supprimer {nom}", key=f"del_{cid}", type="secondary"):
                        _supprimer_client(cid)
                        log_audit(username, "CLIENT_DELETED", f"Client #{cid}: {nom}", "Clients")
                        st.success(f"Client **{nom}** supprimé")
                        st.rerun()

            # Export CSV
            st.markdown("---")
            import io
            csv_buf = io.StringIO()
            df_f.to_csv(csv_buf, index=False, sep=";")
            st.download_button(
                "📊 Exporter en CSV",
                data=csv_buf.getvalue(),
                file_name=f"clients_savia_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    # ============ AJOUTER ============
    with tab_add:
        st.subheader("➕ Nouveau Client")

        with st.form("form_new_client"):
            a1, a2 = st.columns(2)
            nom = a1.text_input("🏢 Nom du client *", key="nc_nom")
            contact = a2.text_input("👤 Nom du contact", key="nc_contact")
            email = a1.text_input("📧 Email", key="nc_email")
            tel = a2.text_input("📞 Téléphone", key="nc_tel")
            adresse = a1.text_input("📍 Adresse", key="nc_adresse")
            secteur = a2.selectbox("🏷️ Secteur", ["", "Radiologie", "Imagerie Médicale", "Hôpital", "Clinique", "Laboratoire", "Autre"], key="nc_secteur")

            a3, a4 = st.columns(2)
            mensuel = a3.number_input(f"💰 Paiement Mensuel ({devise})", min_value=0.0, value=0.0, step=100.0, key="nc_mensuel")
            annuel = a4.number_input(f"📊 Paiement Annuel ({devise})", min_value=0.0, value=0.0, step=500.0, key="nc_annuel")

            a5, a6 = st.columns(2)
            type_contrat = a5.selectbox("📋 Type de contrat", ["Mensuel", "Annuel", "Trimestriel", "Personnalisé"], key="nc_type")
            debut = a6.date_input("📅 Date début contrat", value=date.today(), key="nc_debut")
            fin = a5.date_input("📅 Date fin contrat", value=date.today() + timedelta(days=365), key="nc_fin")

            a7, a8 = st.columns(2)
            url_savia = a7.text_input("💻 Lien SAVIA (ex: sav.client.com)", key="nc_url_sav")
            url_terrain = a8.text_input("📱 Lien SIC Terrain (ex: sav.client.com/terrain)", key="nc_url_ter")

            ip_vps = st.text_input("🖥️ Adresse IP du Serveur (VPS)", placeholder="1.2.3.4", key="nc_ip_vps")

            notes = st.text_area("📝 Notes", key="nc_notes")

            if st.form_submit_button("✅ Créer le client", use_container_width=True, type="primary"):
                if not nom.strip():
                    st.error("❌ Le nom du client est obligatoire")
                else:
                    _ajouter_client({
                        "nom": nom.strip(),
                        "contact_nom": contact.strip(),
                        "contact_email": email.strip(),
                        "contact_tel": tel.strip(),
                        "adresse": adresse.strip(),
                        "secteur": secteur,
                        "paiement_mensuel": mensuel,
                        "paiement_annuel": annuel,
                        "date_debut_contrat": debut.strftime("%Y-%m-%d"),
                        "date_fin_contrat": fin.strftime("%Y-%m-%d"),
                        "type_contrat": type_contrat,
                        "statut_contrat": "Actif",
                        "statut_paiement": "À jour",
                        "notes": notes.strip(),
                        "url_savia": url_savia.strip(),
                        "url_terrain": url_terrain.strip(),
                        "ip_vps": ip_vps.strip()
                    })
                    log_audit(username, "CLIENT_CREATED", f"Nouveau client: {nom}", "Clients")
                    st.success(f"✅ Client **{nom}** créé avec succès !")
                    st.balloons()
                    st.rerun()
