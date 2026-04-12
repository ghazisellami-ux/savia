# ==========================================
# 🛠️ PAGE SUPERVISION
# ==========================================
import streamlit as st
import pandas as pd
import os
import time
from database import lire_base, ajouter_code, enregistrer_evenement
from log_analyzer import scanner_dossier_logs
from ai_engine import AI_AVAILABLE, get_ai_suggestion
from auth import require_role
from notifications import get_notifier
from config import EXCEL_PATH, LOGS_DIR, TYPES_ERREURS


def afficher_supervision():
    """Page de supervision : scan des logs, erreurs, diagnostic IA, validation manuelle."""

    st.title("🛠️ Supervision — Monitoring Machines")
    st.markdown("---")

    # ============ IMPORT DE FICHIERS LOG ============
    with st.expander("📥 Importer un fichier Log", expanded=False):
        st.markdown("Uploadez un fichier de log machine et associez-le à un équipement du parc.")

        from db_engine import lire_equipements
        df_eq = lire_equipements()

        if df_eq.empty:
            st.warning("⚠️ Aucun équipement dans le parc. Ajoutez d'abord un équipement dans **🏥 Parc Équipements**.")
        else:
            # Construire la liste Nom (Client) pour le selectbox
            if "Client" not in df_eq.columns:
                df_eq["Client"] = "Centre Principal"

            options = []
            for _, row in df_eq.iterrows():
                nom = row.get("Nom", "?")
                client = row.get("Client", "")
                label = f"{nom} ({client})" if client else nom
                options.append({"label": label, "nom": nom, "id": row.get("id", "")})

            selected_label = st.selectbox(
                "🏥 Associer à l'équipement",
                [o["label"] for o in options]
            )
            selected = next(o for o in options if o["label"] == selected_label)

            uploaded_log = st.file_uploader(
                "📄 Fichier Log",
                type=["log", "txt", "csv", "elg2"],
                key="upload_log_file"
            )

            if uploaded_log:
                st.info(f"📎 **{uploaded_log.name}** ({uploaded_log.size / 1024:.1f} KB) → **{selected_label}**")

                if st.button("💾 Enregistrer et analyser", key="btn_save_log", type="primary"):
                    # Nom du fichier = nom de l'équipement + extension originale
                    ext = os.path.splitext(uploaded_log.name)[1] or ".log"
                    safe_name = selected["nom"].replace(" ", "_").replace("/", "-")
                    dest_path = os.path.join(LOGS_DIR, f"{safe_name}{ext}")

                    # Si un fichier existe déjà, on peut ajouter ou remplacer
                    mode = "ab" if os.path.exists(dest_path) else "wb"
                    with open(dest_path, mode) as f:
                        if mode == "ab":
                            f.write(b"\n\n# === IMPORT ADDITIONNEL ===\n")
                        f.write(uploaded_log.getbuffer())

                    st.success(f"✅ Log enregistré : `{safe_name}{ext}` — Rafraîchissement de l'analyse...")
                    # Sauvegarder le nom de la machine pour auto-sélection (persistant)
                    st.session_state["uploaded_log_machine"] = selected["nom"]
                    st.session_state["_log_just_uploaded"] = True
                    time.sleep(1)
                    st.rerun()

    # ============ SCAN DES LOGS ============
    hex_db, sol_db = lire_base()
    fleet = scanner_dossier_logs(LOGS_DIR, hex_db, sol_db)

    # Construire un mapping filename → (nom réel, client)
    from db_engine import lire_equipements as _lire_eq_map
    _df_eq_all = _lire_eq_map()
    _filename_to_equip = {}
    _equip_list = []  # pour fuzzy matching
    if not _df_eq_all.empty:
        for _, _row in _df_eq_all.iterrows():
            _nom = str(_row.get("Nom", ""))
            _cli = str(_row.get("Client", ""))
            _equip_list.append((_nom, _cli))
            # Méthode 1: reproduire la logique d'upload
            _safe = _nom.replace(" ", "_").replace("/", "-")
            for _ext in [".log", ".txt", ".csv", ".elg2", ""]:
                _filename_to_equip[f"{_safe}{_ext}"] = (_nom, _cli)

    def _resolve_machine(filename):
        """Résout un nom de fichier log en (nom_machine, client)."""
        # 1. Match exact (fichiers uploadés via l'app)
        if filename in _filename_to_equip:
            return _filename_to_equip[filename]
        # 2. Fuzzy: normaliser le filename et chercher dans les noms d'équipements
        _base = os.path.splitext(filename)[0].lower().replace("_", "").replace("-", "").replace(" ", "")
        best_match = None
        best_len = 0
        for _nom, _cli in _equip_list:
            _norm = _nom.lower().replace(" ", "").replace("_", "").replace("-", "")
            # Vérifier si le nom d'équipement est contenu dans le filename ou inversement
            if _norm in _base or _base in _norm:
                if len(_norm) > best_len:
                    best_match = (_nom, _cli)
                    best_len = len(_norm)
            # Vérifier aussi chaque mot du nom
            else:
                _words = [w.lower() for w in _nom.split() if len(w) >= 3]
                matches = sum(1 for w in _words if w in _base)
                if matches >= len(_words) * 0.6 and matches > 0 and len(_nom) > best_len:
                    best_match = (_nom, _cli)
                    best_len = len(_nom)
        if best_match:
            return best_match
        # 3. Fallback: retourner le filename nettoyé
        _clean = os.path.splitext(filename)[0].replace("_", " ")
        return (_clean, "")

    if not fleet:
        st.warning("📭 **Aucun fichier log trouvé** dans le dossier `logs/`")
        st.info(
            "Utilisez le bouton **📥 Importer un fichier Log** ci-dessus "
            "pour charger vos fichiers de log machine."
        )
        return

    # Liste des fichiers log (pour le selectbox plus bas)
    log_files = [f for f in os.listdir(LOGS_DIR) if os.path.isfile(os.path.join(LOGS_DIR, f))]

    st.markdown("---")

    mach_opts = {m["Machine"]: m for m in fleet}

    # Mapping équipement → client depuis la base
    _machine_client_map = {}
    if not _df_eq_all.empty:
        for _, _r in _df_eq_all.iterrows():
            _machine_client_map[str(_r.get("Nom", ""))] = str(_r.get("Client", ""))

    # ============ CHOISIR FICHIER LOG (avec filtres) ============
    # 1. Clients : directement depuis la base équipements
    clients_from_db = []
    machine_client_db = {}
    if not _df_eq_all.empty:
        for _, _r in _df_eq_all.iterrows():
            nom = str(_r.get("Nom", ""))
            cli = str(_r.get("Client", ""))
            if cli and cli != "nan":
                clients_from_db.append(cli)
                machine_client_db[nom] = cli
    clients_from_db = sorted(set(clients_from_db))

    # 2. Construire la liste des logs avec machine et client
    log_entries = []
    for m in fleet:
        machine_name = m["Machine"]
        log_file = os.path.basename(m.get("Chemin", ""))
        # Résoudre le nom d'équipement réel (DB) et le client
        resolved_name, resolved_client = _resolve_machine(log_file)
        # Enrichir le client depuis la base si nécessaire
        client = machine_client_db.get(resolved_name, "")
        if not client:
            client = resolved_client or ""
        if not client:
            client = machine_client_db.get(machine_name, "")
        log_entries.append({
            "file": log_file,
            "machine": machine_name,
            "equip_name": resolved_name,
            "client": client,
        })

    # Auto-sélection si log uploadé (garder en session_state pour persistance)
    just_uploaded = "uploaded_log_machine" in st.session_state and st.session_state.get("_log_just_uploaded", False)
    uploaded_mach = st.session_state.get("uploaded_log_machine", None)
    # Réinitialiser le flag "just uploaded" après le premier affichage
    st.session_state["_log_just_uploaded"] = False

    # Filtres
    col_fc, col_fm = st.columns(2)
    with col_fc:
        client_opts = ["Tous"] + clients_from_db
        sel_client = st.selectbox("🏢 Filtrer par Client", client_opts, key="sup_filter_client")
    with col_fm:
        # Liste équipements depuis la base, PAS depuis les logs
        if not _df_eq_all.empty:
            if sel_client != "Tous":
                equip_names = sorted(_df_eq_all[_df_eq_all["Client"] == sel_client]["Nom"].tolist())
            else:
                equip_names = sorted(_df_eq_all["Nom"].tolist())
        else:
            equip_names = sorted(set(e["machine"] for e in log_entries))
        equip_opts = ["Tous"] + equip_names
        sel_equip = st.selectbox("🏥 Filtrer par Équipement", equip_opts, key="sup_filter_equip")

    # Filtrer les logs selon client ET équipement sélectionnés
    filtered = []
    for e in log_entries:
        if sel_client != "Tous" and e["client"] != sel_client:
            continue
        if sel_equip != "Tous" and e["equip_name"] != sel_equip and e["machine"] != sel_equip:
            continue
        filtered.append(e)
    if not filtered:
        filtered = log_entries

    # Selectbox fichier log — nom de fichier uniquement, sans doublons
    seen = set()
    unique_filtered = []
    for e in filtered:
        if e["file"] not in seen:
            seen.add(e["file"])
            unique_filtered.append(e)

    file_names = [e["file"] for e in unique_filtered]
    file_to_machine = {e["file"]: e["machine"] for e in unique_filtered}

    default_idx = 0
    if uploaded_mach:
        for i, fn in enumerate(file_names):
            if uploaded_mach.replace(" ", "_") in fn or uploaded_mach in fn:
                default_idx = i
                break

    sel_file = st.selectbox("📂 Choisir fichier log", file_names, index=default_idx)
    sel_mach = file_to_machine.get(sel_file, list(mach_opts.keys())[0] if mach_opts else "")

    if not sel_mach:
        return

    machine_info = mach_opts[sel_mach]
    df_details = machine_info["df_erreurs"]

    # Message après upload
    if just_uploaded:
        st.info(f"📂 Log chargé : **{uploaded_mach}** — Erreurs ci-dessous ⬇️")

    if df_details.empty:
        st.success(f"✅ **{sel_mach}** — Système sain, aucune erreur détectée.")

        with st.expander("📄 Voir les logs bruts"):
            with open(machine_info["Chemin"], "r", encoding="utf-8", errors="replace") as f:
                st.text(f.read()[:5000])
        return

    # ============ TABLEAU ERREURS ============
    st.subheader(f"🔎 Erreurs détectées sur **{sel_mach}**")

    df_grouped = (
        df_details.groupby(["Code", "Message", "Statut", "Type"])
        .size()
        .reset_index(name="Fréquence")
        .sort_values("Fréquence", ascending=False)
    )

    st.dataframe(df_grouped, use_container_width=True, hide_index=True)

    # ============ SÉLECTION ERREUR ============
    st.markdown("---")

    code_opts = [
        f"{row.Code} — {row.Message[:60]}" for row in df_grouped.itertuples()
    ]
    sel_err_txt = st.selectbox("🎯 Sélectionnez l'erreur à analyser :", code_opts)

    if not sel_err_txt:
        return

    sel_code = sel_err_txt.split(" — ")[0]
    sel_msg = sel_err_txt.split(" — ")[1] if " — " in sel_err_txt else sel_err_txt

    # Clé unique combinant code + message pour éviter les conflits
    # (ex: plusieurs erreurs avec code "TXT" mais messages différents)
    sol_key = f"{sel_code}::{sel_msg[:60]}".upper()
    sol = sol_db.get(sol_key) or sol_db.get(sel_code.upper())

    # Recherche fuzzy : chercher les mots-clés de sol_db dans le message/texte brut
    if not sol:
        sel_msg_upper = sel_msg.upper()
        # Chercher aussi dans le texte brut (Raw) de la première occurrence
        raw_line = ""
        if not df_details.empty and "Raw" in df_details.columns:
            matching_rows = df_details[df_details["Code"] == sel_code]
            if not matching_rows.empty:
                raw_line = str(matching_rows.iloc[0].get("Raw", "")).upper()
        search_text = sel_msg_upper + " " + raw_line

        best_match = None
        best_len = 0
        for mot_cle, sol_info in sol_db.items():
            mk = mot_cle.upper()
            if len(mk) >= 3 and mk in search_text and len(mk) > best_len:
                best_match = sol_info
                best_len = len(mk)
        if best_match:
            sol = best_match

    # ============ INFO CONNUE ============
    st.markdown(f"### 🆔 Code : `{sel_code}` — {sel_msg}")

    if sol:
        st.success("✅ **Erreur CONNUE** — Solution existante dans la base")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**🔧 Cause :** {sol['Cause']}")
        c2.markdown(f"**💡 Solution :** {sol['Solution']}")
        c3.markdown(f"**📁 Type :** {sol['Type']} | **⚡ Priorité :** {sol['Priorité']}")
    else:
        st.error("⚠️ **Erreur INCONNUE** — Aucune solution dans la base")

    # Bouton d'envoi d'alerte manuelle
    notifier = get_notifier()
    if notifier.telegram_ok or notifier.email_ok:
        # Résoudre le vrai nom de machine depuis le fichier log sélectionné
        _real_machine = sel_mach
        _alert_client = ""
        # Chercher dans le mapping log → machine le fichier actuel
        for lf in log_files if log_files else []:
            m_name, m_client = _resolve_machine(lf)
            if m_name == sel_mach or sel_mach in m_name or m_name in sel_mach:
                _real_machine = m_name
                _alert_client = m_client
                break
        # Fallback: chercher dans les équipements par nom partiel
        if not _alert_client and not _df_eq_all.empty:
            for _, _row in _df_eq_all.iterrows():
                _nom = str(_row.get("Nom", ""))
                if _nom == sel_mach or sel_mach.replace("_", " ") in _nom or _nom in sel_mach:
                    _real_machine = _nom
                    _alert_client = str(_row.get("Client", ""))
                    break

        if st.button("\U0001f6a8 Envoyer alerte", use_container_width=True):
            result = notifier.notifier_panne_critique(_real_machine, sel_code, sel_msg, client=_alert_client)
            if result["telegram"] or result["email"]:
                canaux = []
                if result["telegram"]: canaux.append("Telegram")
                if result["email"]: canaux.append("Email")
                st.success(f"\u2705 Alerte envoyée via : {', '.join(canaux)}")
            else:
                st.error("\u274c Impossible d'envoyer l'alerte. Vérifiez la config .env")

    # ============ DIAGNOSTIC IA (Admin uniquement) ============
    st.markdown("---")

    # Gestion état session
    if "last_code" not in st.session_state or st.session_state["last_code"] != sel_code:
        st.session_state["last_code"] = sel_code
        st.session_state["ai_sugg"] = None

    # L'IA est accessible aux Admin et Techniciens
    if require_role("Admin", "Technicien"):
        st.subheader("🧠 Diagnostic IA avancé")
        st.caption(
            "⚠️ Les données du log seront "
            "envoyées à l'API Gemini pour analyse approfondie."
        )

        if AI_AVAILABLE:
            if st.button("✨ Analyser avec l'IA", type="primary", use_container_width=True):
                with st.spinner("🧠 Analyse experte en cours (peut prendre 30s si le quota est limité)..."):
                    # Extraire le contexte log (20 lignes avant l'erreur)
                    log_context = ""
                    try:
                        log_path = machine_info.get("Chemin", "")
                        if log_path:
                            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                                all_lines = f.readlines()
                            # Trouver la ligne contenant le code/message de l'erreur sélectionnée
                            error_line_idx = None
                            for i, line in enumerate(all_lines):
                                if sel_code in line or (sel_msg and sel_msg[:30] in line):
                                    error_line_idx = i
                                    break
                            if error_line_idx is not None:
                                start = max(0, error_line_idx - 20)
                                context_lines = all_lines[start:error_line_idx + 1]
                                log_context = "".join(context_lines).strip()
                    except Exception:
                        pass

                    try:
                        sugg = get_ai_suggestion(sel_code, sel_msg, sel_mach, log_context=log_context)
                        if sugg:
                            # Vérifier si c'est un vrai résultat IA ou un fallback local
                            if sugg.get("_source") == "local":
                                st.warning(
                                    "⚠️ **L'IA Gemini n'est pas disponible** (quota API épuisé ou erreur réseau). "
                                    "Le résultat ci-dessous provient de la **base locale** uniquement.\n\n"
                                    "💡 Le quota se réinitialise chaque jour. Réessayez plus tard ou "
                                    "vérifiez votre clé API dans `.env`."
                                )
                                # Mettre à jour l'indicateur sidebar
                                st.session_state["ia_status"] = (False, "Quota API épuisé")
                            st.session_state["ai_sugg"] = sugg
                        else:
                            st.warning("⚠️ L'IA n'a pas pu fournir de diagnostic. Le quota API est peut-être épuisé. Réessayez plus tard.")
                            st.session_state["ia_status"] = (False, "Aucune réponse")
                    except Exception as e:
                        st.error(f"❌ Erreur lors de l'appel IA : {e}")
                        st.session_state["ia_status"] = (False, f"Erreur: {str(e)[:50]}")
        else:
            st.info("🔑 Configurez `GOOGLE_API_KEY` dans `.env` pour activer l'IA.")
    else:
        # Lecteurs : uniquement le diagnostic Regex local
        st.info(
            "💡 L'analyse Regex locale est affichée ci-dessus. "
            "Pour une **analyse IA approfondie**, connectez-vous avec un compte Technicien ou Admin."
        )

    # Afficher la réponse IA de façon claire et structurée
    if st.session_state.get("ai_sugg"):
        s = st.session_state["ai_sugg"]

        st.markdown("#### 📋 Résultat du Diagnostic IA")

        # Affichage structuré : Problème, Cause, Solution
        col_prob, col_cause = st.columns(2)

        with col_prob:
            probleme = s.get("Probleme", s.get("Message", "Non spécifié"))
            st.markdown(f"""
<div style="background: rgba(239,68,68,0.08); border-left: 4px solid #ef4444; 
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: #ef4444; font-weight: 700; font-size: 0.85rem; 
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        🔴 Problème identifié</div>
    <div style="color: #f1f5f9; font-size: 0.95rem;">{probleme}</div>
</div>""", unsafe_allow_html=True)

        with col_cause:
            cause = s.get("Cause", "Non spécifiée")
            st.markdown(f"""
<div style="background: rgba(245,158,11,0.08); border-left: 4px solid #f59e0b; 
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: #f59e0b; font-weight: 700; font-size: 0.85rem; 
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        🟠 Cause probable</div>
    <div style="color: #f1f5f9; font-size: 0.95rem;">{cause}</div>
</div>""", unsafe_allow_html=True)

        # Solution en pleine largeur
        solution = s.get("Solution", "Non spécifiée")
        st.markdown(f"""
<div style="background: rgba(16,185,129,0.08); border-left: 4px solid #10b981; 
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: #10b981; font-weight: 700; font-size: 0.85rem; 
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        🟢 Procédure d'investigation</div>
    <div style="color: #f1f5f9; font-size: 0.95rem;">{solution}</div>
</div>""", unsafe_allow_html=True)

        # Prévention et Urgence côte à côte
        prevention = s.get("Prevention", "")
        urgence = s.get("Urgence", "")

        if prevention or urgence:
            col_prev, col_urg = st.columns(2)

            if prevention:
                with col_prev:
                    st.markdown(f"""
<div style="background: rgba(59,130,246,0.08); border-left: 4px solid #3b82f6; 
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: #3b82f6; font-weight: 700; font-size: 0.85rem; 
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        🛡️ Maintenance préventive</div>
    <div style="color: #f1f5f9; font-size: 0.95rem;">{prevention}</div>
</div>""", unsafe_allow_html=True)

            if urgence:
                with col_urg:
                    st.markdown(f"""
<div style="background: rgba(168,85,247,0.08); border-left: 4px solid #a855f7; 
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: #a855f7; font-weight: 700; font-size: 0.85rem; 
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        ⏱️ Évaluation d'urgence</div>
    <div style="color: #f1f5f9; font-size: 0.95rem;">{urgence}</div>
</div>""", unsafe_allow_html=True)

        # Type, Priorité et Score de Confiance en badges
        type_ia = s.get("Type", "?")
        prio_ia = s.get("Priorite", "?")
        conf_score = s.get("Confidence_Score", "?")
        prio_color = "#ef4444" if prio_ia == "HAUTE" else "#f59e0b" if prio_ia == "MOYENNE" else "#10b981"
        conf_color = "#10b981" if isinstance(conf_score, int) and conf_score >= 80 else "#f59e0b" if isinstance(conf_score, int) and conf_score >= 50 else "#ef4444"
        st.markdown(f"""
<div style="display: flex; gap: 12px; margin-top: 4px;">
    <span style="background: rgba(59,130,246,0.15); color: #3b82f6; padding: 4px 14px; 
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">📁 {type_ia}</span>
    <span style="background: rgba(239,68,68,0.1); color: {prio_color}; padding: 4px 14px; 
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">⚡ {prio_ia}</span>
    <span style="background: rgba(16,185,129,0.1); color: {conf_color}; padding: 4px 14px; 
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">🎯 Confiance: {conf_score}%</span>
</div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

    # ============ FORMULAIRE DE VALIDATION MANUELLE ============
    st.markdown("---")
    st.subheader("💾 Enregistrer dans la Base de Connaissances")
    st.markdown(
        "_Remplissez ce formulaire avec la solution qui a **réellement fonctionné** "
        "sur le terrain, puis enregistrez-la dans la base._"
    )

    # Recharger la base pour avoir les données à jour pour CE code
    _, sol_db_fresh = lire_base()
    sol_fresh = sol_db_fresh.get(sol_key) or sol_db_fresh.get(sel_code.upper())

    # Valeurs par défaut : base existante > IA > vide
    def_cause = ""
    def_sol = ""
    def_type = "Hardware"
    def_prio = "MOYENNE"

    if sol_fresh:
        def_cause = sol_fresh.get("Cause", "")
        def_sol = sol_fresh.get("Solution", "")
        def_type = sol_fresh.get("Type", "Hardware")
        def_prio = sol_fresh.get("Priorité", "MOYENNE")

    # Clé de formulaire unique par code erreur pour éviter le cache croisé
    form_key = f"form_validation_{sol_key}"

    with st.form(form_key):
        new_cause = st.text_input("🔧 Cause confirmée", value=def_cause,
                                  placeholder="Décrivez la cause réelle du problème")
        new_sol = st.text_area(
            "💡 Solution appliquée", value=def_sol, height=100,
            placeholder="Décrivez les étapes de la solution qui a fonctionné"
        )
        c_t, c_p = st.columns(2)

        type_index = 0
        if def_type in TYPES_ERREURS:
            type_index = TYPES_ERREURS.index(def_type)

        new_type = c_t.selectbox("📁 Type d'erreur", TYPES_ERREURS, index=type_index)

        prio_list = ["HAUTE", "MOYENNE", "BASSE"]
        prio_index = prio_list.index(def_prio) if def_prio in prio_list else 1
        new_prio = c_p.selectbox("⚡ Priorité", prio_list, index=prio_index)

        submitted = st.form_submit_button(
            "💾 Enregistrer dans la base",
            use_container_width=True,
        )

        if submitted:
            if not new_cause.strip() or not new_sol.strip():
                st.error("❌ Veuillez remplir la cause ET la solution avant d'enregistrer.")
            else:
                success = ajouter_code(
                    EXCEL_PATH, sol_key, sel_msg,
                    new_cause.strip(), new_sol.strip(), new_type, new_prio
                )
                if success:
                    enregistrer_evenement(EXCEL_PATH, sel_mach, sel_code, new_type, new_prio)
                    st.success(f"✅ Code **{sel_code}** enregistré avec succès !")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Erreur lors de la sauvegarde. Le fichier Excel est-il ouvert ?")

    # ============ LOGS BRUTS ============
    with st.expander("📄 Voir les logs bruts"):
        with open(machine_info["Chemin"], "r", encoding="utf-8", errors="replace") as f:
            st.text(f.read()[:5000])

    # ============ TABLEAU ÉTAT DU PARC (en bas de page) ============
    st.markdown("---")
    st.subheader("📋 État du Parc")

    # En-tête
    h1, h2, h3, h4, h5, h6, h7 = st.columns([0.5, 1.5, 1.5, 1.5, 0.8, 0.8, 0.5])
    h1.markdown("**État**")
    h2.markdown("**🏥 Équipement**")
    h3.markdown("**🏢 Client**")
    h4.markdown("**📄 Fichier**")
    h5.markdown("**⚠️ Err.**")
    h6.markdown("**🔴 Crit.**")
    h7.markdown("**🗑️**")
    st.markdown("<hr style='margin:2px 0;border-color:rgba(45,212,191,0.3)'>", unsafe_allow_html=True)

    for m in fleet:
        log_path = m.get("Chemin", "")
        log_file = os.path.basename(log_path)
        equip_name, equip_client = _resolve_machine(log_file)
        client = _machine_client_map.get(equip_name, equip_client or "—")
        etat = m["État"]
        etat_emoji = "🟢" if etat == "OK" else ("🔴" if "CRITIQUE" in etat else "🟡")

        confirm_key = f"confirm_del_log_{log_file}"
        if st.session_state.get(confirm_key):
            # Ligne de confirmation
            st.warning(f"⚠️ Supprimer **{log_file}** ({equip_name}) ?")
            cy, cn = st.columns(2)
            if cy.button("✅ Oui", key=f"yes_{log_file}", use_container_width=True):
                try:
                    os.remove(log_path)
                    st.success(f"🗑️ {log_file} supprimé")
                except Exception as ex:
                    st.error(f"Erreur : {ex}")
                st.session_state.pop(confirm_key, None)
                st.rerun()
            if cn.button("❌ Non", key=f"no_{log_file}", use_container_width=True):
                st.session_state.pop(confirm_key, None)
                st.rerun()
        else:
            c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 1.5, 1.5, 1.5, 0.8, 0.8, 0.5])
            c1.markdown(f"{etat_emoji}")
            c2.markdown(f"**{equip_name}**")
            c3.markdown(f"{client}")
            c4.markdown(f"`{log_file}`")
            c5.markdown(f"{m['Erreurs']}")
            c6.markdown(f"{m['Critiques']}")
            if c7.button("🗑️", key=f"del_{log_file}", help="Supprimer"):
                st.session_state[confirm_key] = True
                st.rerun()

    # Alertes critiques
    crit_machines = [m for m in fleet if "CRITIQUE" in m["État"]]
    if crit_machines:
        st.error(f"🚨 **{len(crit_machines)} machine(s) en état CRITIQUE**")
        for m in crit_machines:
            df_crit = m["df_erreurs"]
            if not df_crit.empty:
                first_err = df_crit.iloc[0]
                st.warning(f"⚠️ **{m['Machine']}** — Code `{first_err.get('Code', '?')}` : {first_err.get('Message', '')}")
