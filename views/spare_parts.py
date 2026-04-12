# ==========================================
# 🔧 PAGE PIÈCES DE RECHANGE
# ==========================================
import streamlit as st
import pandas as pd
from db_engine import (
    lire_pieces, ajouter_piece, update_stock_piece, modifier_piece,
    supprimer_piece, log_audit, get_config, get_db,
    ajouter_notification_piece, notifications_rupture_pour_piece,
    marquer_notification_traitee,
)
from database import lire_interventions
from auth import get_current_user, require_role
from i18n import t
from predictive_stock import predire_besoins_stock, generer_conseil_achat_ia


def page_pieces():
    st.title(t("spare_parts"))

    user = get_current_user()
    username = user.get("username", "?") if user else "?"
    devise = get_config("devise", "EUR")
    is_admin = require_role("Admin")

    # ============ AJOUTER PIÈCE ============
    if require_role("Admin", "Manager", "Technicien"):
        with st.expander(t("add_part"), expanded=False):
            with st.form("form_piece"):
                col1, col2 = st.columns(2)
                with col1:
                    ref = st.text_input(t("reference"), placeholder="Ex: TUBE-RX-001")
                    designation = st.text_input(t("designation"), placeholder="Ex: Tube radiogène")
                    from config import TYPES_EQUIPEMENTS
                    equip_type_sel = st.selectbox(t("type"), options=TYPES_EQUIPEMENTS, index=0)
                    if equip_type_sel == "Autre":
                        equip_type = st.text_input("Préciser le type", placeholder="Type personnalisé...")
                    else:
                        equip_type = equip_type_sel
                with col2:
                    stock = st.number_input(t("current_stock"), min_value=0, value=1)
                    stock_min = st.number_input(t("min_stock"), min_value=0, value=1)
                    prix = st.number_input(f"{t('unit_price')} ({devise})", min_value=0.0, value=0.0, step=10.0)

                fournisseur = st.text_input(t("supplier"), placeholder="Ex: Siemens Healthineers")
                notes = st.text_input(t("notes"))

                if st.form_submit_button(t("save"), use_container_width=True):
                    if not ref.strip() or not designation.strip():
                        st.error("\u274c Référence et désignation obligatoires")
                    else:
                        ajouter_piece({
                            "reference": ref.strip().upper(),
                            "designation": designation.strip(),
                            "equipement_type": equip_type.strip(),
                            "stock_actuel": stock,
                            "stock_minimum": stock_min,
                            "fournisseur": fournisseur.strip(),
                            "prix_unitaire": prix,
                            "notes": notes.strip(),
                        })
                        log_audit(username, "PIECE_ADDED", f"{ref} - {designation}", "Pièces")
                        st.success(t("save_success"))
                        # Sync vers SIC Terrain
                        try:
                            from sync_terrain import sync_pieces_to_terrain
                            _sync = sync_pieces_to_terrain()
                            if _sync.get("pieces_pushed", 0) > 0:
                                st.toast(f"🔄 {_sync['pieces_pushed']} pièce(s) synchronisée(s) vers Terrain")
                        except Exception:
                            pass
                        st.rerun()

    # ============ STOCK ============
    st.markdown("---")
    df = lire_pieces()

    if df.empty:
        st.info(t("no_data"))
        return

    # Alertes stock bas
    if "stock_actuel" in df.columns and "stock_minimum" in df.columns:
        df["stock_actuel"] = pd.to_numeric(df["stock_actuel"], errors="coerce").fillna(0)
        df["stock_minimum"] = pd.to_numeric(df["stock_minimum"], errors="coerce").fillna(0)
        low_stock = df[df["stock_actuel"] <= df["stock_minimum"]]
        if not low_stock.empty:
            nb_rupture = len(low_stock[low_stock["stock_actuel"] == 0])
            nb_bas = len(low_stock) - nb_rupture
            label_parts = []
            if nb_rupture > 0:
                label_parts.append(f"{nb_rupture} en rupture")
            if nb_bas > 0:
                label_parts.append(f"{nb_bas} stock bas")
            expander_label = f"\U0001f6a8 {len(low_stock)} pièce(s) en stock critique ! ({', '.join(label_parts)})"

            with st.expander(expander_label, expanded=False):
                for _, row in low_stock.iterrows():
                    rupture = int(row['stock_actuel']) == 0
                    if rupture:
                        badge_color = "#dc2626"
                        badge_bg = "rgba(220,38,38,0.15)"
                        badge_label = "\U0001f6a8 RUPTURE"
                    else:
                        badge_color = "#f97316"
                        badge_bg = "rgba(249,115,22,0.15)"
                        badge_label = "\U0001f534 Stock bas"

                    stock_val = int(row['stock_actuel'])
                    stock_min = int(row['stock_minimum'])
                    fournisseur = row.get('fournisseur', '') or ''
                    prix = row.get('prix_unitaire', 0) or 0

                    st.markdown(f"""
<div style="border-left:4px solid {badge_color}; background:{badge_bg};
    padding:10px 16px; margin:6px 0; border-radius:0 8px 8px 0;">
  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
    <div>
      <span style="font-weight:700; font-size:0.95rem;">{row['designation']}</span>
      <span style="color:#94a3b8; font-size:0.82rem;"> — {row['reference']}</span>
    </div>
    <div style="background:{badge_color}; color:white; padding:2px 12px;
        border-radius:12px; font-size:0.75rem; font-weight:700;">{badge_label}</div>
  </div>
  <div style="color:#cbd5e1; font-size:0.82rem; margin-top:4px;">
    📦 Stock : <b>{stock_val}</b> / Min : {stock_min}
    &nbsp;|&nbsp; 🏭 {fournisseur}
    &nbsp;|&nbsp; 💰 {f"{prix:,.0f}".replace(",", " ")} {devise}
  </div>
</div>
                    """, unsafe_allow_html=True)

    # KPIs
    col1, col2, col3, col4 = st.columns([1, 1, 2.5, 1])
    col1.metric(t("total"), len(df))
    col2.metric(t("low_stock_alert"), len(low_stock) if 'low_stock' in dir() else 0)
    total_val = (df["stock_actuel"] * pd.to_numeric(df["prix_unitaire"], errors="coerce").fillna(0)).sum()
    total_val_fmt = f"{total_val:,.0f}".replace(",", " ")
    col3.metric("Valeur Stock", f"{total_val_fmt} {devise}")
    fournisseurs = df["fournisseur"].nunique() if "fournisseur" in df.columns else 0
    col4.metric("\U0001f3ed " + t("supplier") + "s", fournisseurs)

    # ============ FILTRES ============
    st.markdown("---")
    fc1, fc2 = st.columns(2)
    with fc1:
        search_text = st.text_input(
            "\U0001f50d Rechercher une pièce",
            placeholder="Référence, désignation ou fournisseur...",
            key="piece_search"
        ).strip().lower()
    with fc2:
        types_dispos = ["Tous"] + sorted(df["equipement_type"].fillna("").unique().tolist())
        filtre_type = st.selectbox(
            "\U0001f527 Filtrer par type d'équipement",
            types_dispos,
            key="piece_type_filter"
        )

    # Appliquer filtres
    df_filtered = df.copy()
    if search_text:
        mask = (
            df_filtered["reference"].fillna("").str.lower().str.contains(search_text, na=False) |
            df_filtered["designation"].fillna("").str.lower().str.contains(search_text, na=False) |
            df_filtered["fournisseur"].fillna("").str.lower().str.contains(search_text, na=False)
        )
        df_filtered = df_filtered[mask]
    if filtre_type != "Tous":
        df_filtered = df_filtered[df_filtered["equipement_type"] == filtre_type]

    st.caption(f"\U0001f4e6 {len(df_filtered)} pièce(s) affichée(s)")

    # Onglets
    tab_stock, tab_trace, tab_actions, tab_pred = st.tabs([
        "\U0001f4e6 Stock", "\U0001f50d Traçabilité",
        "\u270f\ufe0f Modifier / \U0001f5d1\ufe0f Supprimer", "\U0001f9e0 Prédictions & Achats IA"
    ])

    # ============ TAB STOCK ============
    with tab_stock:
        st.dataframe(
            df_filtered[["reference", "designation", "equipement_type", "stock_actuel",
                "stock_minimum", "fournisseur", "prix_unitaire"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "reference": t("reference"),
                "designation": t("designation"),
                "equipement_type": t("type"),
                "stock_actuel": st.column_config.NumberColumn(t("current_stock")),
                "stock_minimum": st.column_config.NumberColumn(t("min_stock")),
                "fournisseur": t("supplier"),
                "prix_unitaire": st.column_config.NumberColumn(f"{t('unit_price')} ({devise})", format=f"%,.0f {devise}"),
            }
        )

        # Bouton de synchronisation manuelle vers SIC Terrain
        if require_role("Admin", "Manager", "Technicien"):
            if st.button("🔄 Synchroniser stock → SIC Terrain", key="sync_stock_terrain", type="secondary"):
                with st.spinner("Synchronisation en cours..."):
                    try:
                        from sync_terrain import sync_pieces_to_terrain
                        _sync = sync_pieces_to_terrain()
                        nb = _sync.get("pieces_pushed", 0)
                        if nb > 0:
                            st.success(f"✅ {nb} pièce(s) synchronisée(s) vers SIC Terrain !")
                        elif "error" in _sync:
                            st.error(f"❌ Erreur sync : {_sync['error']}")
                        else:
                            st.info("✅ Stock déjà à jour sur SIC Terrain.")
                    except Exception as e:
                        st.error(f"❌ Erreur : {e}")

    # ============ TAB TRAÇABILITÉ ============
    with tab_trace:
        st.subheader("\U0001f50d Traçabilité des Pièces")
        st.caption("Historique complet : quelle pièce a été utilisée sur quel équipement.")

        df_interv = lire_interventions()
        if df_interv.empty or "pieces_utilisees" not in df_interv.columns:
            st.info("Aucune donnée d'intervention avec des pièces utilisées.")
        else:
            df_with_parts = df_interv[df_interv["pieces_utilisees"].fillna("").str.strip().str.len() > 0].copy()

            if df_with_parts.empty:
                st.info("Aucune intervention n'a de pièces utilisées enregistrées.")
            else:
                trace_rows = []
                for _, interv in df_with_parts.iterrows():
                    pieces_str = str(interv.get("pieces_utilisees", ""))
                    parts = [p.strip() for p in pieces_str.replace(";", ",").split(",") if p.strip()]
                    notes = str(interv.get("notes", "") or "")
                    client = ""
                    if notes.startswith("[") and "]" in notes:
                        client = notes[1:notes.index("]")]
                    for part_name in parts:
                        trace_rows.append({
                            "Date": str(interv.get("date", ""))[:10],
                            "Pièce": part_name,
                            "Équipement": interv.get("machine", ""),
                            "Client": client,
                            "Technicien": interv.get("technicien", ""),
                            "Statut": interv.get("statut", ""),
                            "Description": str(interv.get("description", ""))[:60],
                        })

                if trace_rows:
                    df_trace = pd.DataFrame(trace_rows)

                    tc1, tc2 = st.columns(2)
                    with tc1:
                        pieces_uniques = sorted(df_trace["Pièce"].unique().tolist())
                        piece_filter = st.multiselect("\U0001f527 Filtrer par pièce", pieces_uniques, key="trace_piece")
                    with tc2:
                        equip_uniques = sorted(df_trace["Équipement"].unique().tolist())
                        equip_filter = st.multiselect("\U0001f3e5 Filtrer par équipement", equip_uniques, key="trace_equip")

                    df_trace_f = df_trace.copy()
                    if piece_filter:
                        df_trace_f = df_trace_f[df_trace_f["Pièce"].isin(piece_filter)]
                    if equip_filter:
                        df_trace_f = df_trace_f[df_trace_f["Équipement"].isin(equip_filter)]

                    tk1, tk2, tk3 = st.columns(3)
                    tk1.metric("\U0001f527 Pièces différentes", df_trace_f["Pièce"].nunique())
                    tk2.metric("\U0001f3e5 Équipements concernés", df_trace_f["Équipement"].nunique())
                    tk3.metric("\U0001f4e6 Utilisations totales", len(df_trace_f))

                    st.dataframe(
                        df_trace_f.sort_values("Date", ascending=False),
                        use_container_width=True,
                        hide_index=True,
                        height=min(600, 35 * len(df_trace_f) + 38),
                    )

                    csv_data = df_trace_f.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "\U0001f4e5 Exporter en CSV",
                        data=csv_data,
                        file_name="tracabilite_pieces.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
                else:
                    st.info("Aucune pièce identifiée dans les interventions.")

    with tab_actions:
        if not is_admin:
            st.info("\U0001f510 Section réservée aux administrateurs.")
        elif df_filtered.empty:
            st.info("Aucune pièce à afficher avec les filtres actuels.")
        else:
            from config import TYPES_EQUIPEMENTS

            for _, row in df_filtered.iterrows():
                pid = row["id"]
                ref_val = row.get("reference", "?")
                desig_val = row.get("designation", "?")
                stock_val = int(row.get("stock_actuel", 0))
                stock_min_val = int(row.get("stock_minimum", 0))
                prix_val = float(row.get("prix_unitaire", 0) or 0)
                four_val = row.get("fournisseur", "")
                type_val = row.get("equipement_type", "")
                notes_val = row.get("notes", "")

                # Icone stock
                stock_icon = "\U0001f534" if stock_val <= stock_min_val else "\U0001f7e2"

                with st.expander(
                    f"{stock_icon} **{ref_val}** \u2014 {desig_val} \u2014 "
                    f"Stock: {stock_val} \u2014 {f'{prix_val:,.0f}'.replace(',', ' ')} {devise}"
                ):
                    act1, act2 = st.columns(2)

                    # ===== MODIFIER =====
                    with act1:
                        with st.popover("\u270f\ufe0f Modifier", use_container_width=True):
                            with st.form(key=f"edit_piece_{pid}"):
                                e_ref = st.text_input("Référence", value=ref_val, key=f"ep_ref_{pid}")
                                e_desig = st.text_input("Désignation", value=desig_val, key=f"ep_des_{pid}")
                                e_type = st.selectbox(
                                    "Type équipement", TYPES_EQUIPEMENTS,
                                    index=TYPES_EQUIPEMENTS.index(type_val) if type_val in TYPES_EQUIPEMENTS else 0,
                                    key=f"ep_ty_{pid}"
                                )
                                ep1, ep2 = st.columns(2)
                                e_stock = ep1.number_input("Stock", min_value=0, value=stock_val, key=f"ep_st_{pid}")
                                e_min = ep2.number_input("Stock min", min_value=0, value=stock_min_val, key=f"ep_mn_{pid}")
                                e_prix = st.number_input(
                                    f"Prix ({devise})", min_value=0.0, value=prix_val, step=10.0,
                                    key=f"ep_px_{pid}"
                                )
                                e_four = st.text_input("Fournisseur", value=four_val or "", key=f"ep_fr_{pid}")
                                e_notes = st.text_input("Notes", value=notes_val or "", key=f"ep_no_{pid}")

                                if st.form_submit_button("💾 Enregistrer"):
                                    # Check old stock before modifying (for restock detection)
                                    old_stock = stock_val
                                    new_stock = e_stock

                                    modifier_piece(pid, {
                                        "reference": e_ref.strip().upper(),
                                        "designation": e_desig.strip(),
                                        "equipement_type": e_type,
                                        "stock_actuel": e_stock,
                                        "stock_minimum": e_min,
                                        "fournisseur": e_four.strip(),
                                        "prix_unitaire": e_prix,
                                        "notes": e_notes.strip(),
                                    })
                                    log_audit(username, "PIECE_MODIFIED", f"{e_ref} - {e_desig}", "Pièces")

                                    # === NOTIFICATION PIÈCE ARRIVÉE ===
                                    # Si le stock passe de 0 à >0, notifier SIC Terrain
                                    if old_stock == 0 and new_stock > 0:
                                        ref_upper = e_ref.strip().upper()
                                        df_ruptures = notifications_rupture_pour_piece(ref_upper)
                                        if not df_ruptures.empty:
                                            for _, notif_row in df_ruptures.iterrows():
                                                # Créer notification "pièce arrivée" → terrain
                                                msg_arrivee = (
                                                    f"🟢 Pièce '{e_desig.strip()}' ({ref_upper}) "
                                                    f"réapprovisionnée (stock: {new_stock}). "
                                                    f"Intervention {notif_row.get('intervention_ref', '')} "
                                                    f"peut être planifiée."
                                                )
                                                ajouter_notification_piece({
                                                    "type": "piece_arrivee",
                                                    "intervention_id": notif_row.get("intervention_id"),
                                                    "piece_reference": ref_upper,
                                                    "piece_nom": e_desig.strip(),
                                                    "intervention_ref": notif_row.get("intervention_ref", ""),
                                                    "equipement": notif_row.get("equipement", ""),
                                                    "client": notif_row.get("client", ""),
                                                    "technicien": notif_row.get("technicien", ""),
                                                    "message": msg_arrivee,
                                                    "source": "radiologie",
                                                    "destination": "terrain",
                                                })
                                                # Marquer la notification de rupture comme traitée
                                                marquer_notification_traitee(notif_row["id"])

                                            # Envoyer Telegram
                                            try:
                                                from notifications import get_notifier
                                                notifier = get_notifier()
                                                if notifier.telegram_ok:
                                                    tg_msg = (
                                                        f"🟢 *PIÈCE DISPONIBLE (SIC Radiologie)*\n\n"
                                                        f"📦 Pièce : *{e_desig.strip()}* ({ref_upper})\n"
                                                        f"📊 Nouveau stock : *{new_stock}*\n\n"
                                                    )
                                                    interventions_refs = df_ruptures["intervention_ref"].tolist()
                                                    tg_msg += f"🔧 Interventions concernées : {', '.join(str(r) for r in interventions_refs)}\n"
                                                    tg_msg += f"👉 Planifier les interventions sur *SIC Terrain*"
                                                    notifier.envoyer_telegram(tg_msg)
                                            except Exception:
                                                pass

                                            st.success(
                                                f"✅ Pièce #{pid} modifiée ! "
                                                f"🔔 {len(df_ruptures)} notification(s) envoyée(s) à SIC Terrain"
                                            )
                                        else:
                                            st.success(f"✅ Pièce #{pid} modifiée !")
                                    else:
                                        st.success(f"✅ Pièce #{pid} modifiée !")
                                    # Sync automatique vers SIC Terrain
                                    try:
                                        from sync_terrain import sync_pieces_to_terrain
                                        _sync = sync_pieces_to_terrain()
                                        if _sync.get("pieces_pushed", 0) > 0:
                                            st.toast(f"🔄 Stock synchronisé vers SIC Terrain")
                                    except Exception:
                                        pass
                                    st.rerun()

                    # ===== SUPPRIMER =====
                    with act2:
                        confirm = st.checkbox("Confirmer suppression", key=f"del_p_{pid}")
                        if confirm:
                            if st.button(
                                "\U0001f5d1\ufe0f Supprimer",
                                type="primary",
                                key=f"btn_del_p_{pid}",
                                use_container_width=True,
                            ):
                                supprimer_piece(pid)
                                log_audit(username, "PIECE_DELETED", f"{ref_val} - {desig_val}", "Pièces")
                                st.success(f"\u2705 Pièce #{pid} supprimée.")
                                st.rerun()

    # ============ TAB PREDICTIONS ============
    with tab_pred:
        st.subheader("\U0001f916 Assistant d'Achat Prédictif")
        st.info("L'IA analyse vos cycles de remplacement et niveaux de stock pour anticiper les ruptures.")

        df_pred = predire_besoins_stock()

        if not df_pred.empty:
            st.dataframe(
                df_pred,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Date Achat Conseillée": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    "Prochain Besoin": st.column_config.DateColumn(format="DD/MM/YYYY"),
                    "MTBR (jours)": st.column_config.NumberColumn("Fréquence Rempl. (jours)"),
                }
            )

            # Analyse IA à la demande
            st.markdown("---")
            st.markdown("#### \U0001f9e0 Analyse Qualitative")
            # Construire liste : Désignation — Type Équipement (pour distinguer Tube RX Mammo vs Scanner)
            if not df.empty:
                df_sel = df[["designation", "equipement_type", "stock_actuel", "stock_minimum",
                             "fournisseur", "prix_unitaire", "reference"]].drop_duplicates(subset=["designation", "equipement_type"])
                pieces_labels = []
                pieces_data = {}
                for _, r in df_sel.iterrows():
                    label = f"{r['designation']} — {r['equipement_type']}" if r.get("equipement_type") else str(r["designation"])
                    pieces_labels.append(label)
                    pieces_data[label] = r.to_dict()
                pieces_labels.sort()
            else:
                pieces_labels = []
                pieces_data = {}

            # Récupérer le contexte feedback pour l'IA
            feedback_context_sp = ""
            try:
                from db_engine import get_prediction_accuracy
                acc_all = get_prediction_accuracy()
                if acc_all and pieces_labels:
                    fb_lines = []
                    for pn in pieces_labels:
                        if pn in acc_all:
                            fb_lines.append(f"  - {pn}: {acc_all[pn]['precision']}% précision sur {acc_all[pn]['total']} feedbacks")
                    if fb_lines:
                        feedback_context_sp = "HISTORIQUE PRÉCISION PRÉDICTIONS PIÈCES (feedbacks techniciens):\n" + "\n".join(fb_lines) + "\n"
            except Exception:
                pass

            if pieces_labels:
                options_list = ["📦 Toutes les pièces"] + pieces_labels
                selected_p = st.selectbox("Choisir une pièce à analyser :", options_list, index=0, key="qual_piece_sel")
            else:
                selected_p = None
                st.info("Aucune pièce disponible.")

            if selected_p and st.button("✨ Demander l'avis de l'IA", key="btn_ia_qual"):
                if selected_p == "📦 Toutes les pièces":
                    # Analyse globale de toutes les pièces
                    with st.spinner("Analyse globale de toutes les pièces par Gemini..."):
                        all_pieces_info = []
                        for label in pieces_labels:
                            p_info = pieces_data.get(label, {})
                            designation = p_info.get("designation", label)
                            equip_type = p_info.get("equipement_type", "")
                            stock_val = int(p_info.get("stock_actuel", 0) or 0)
                            stock_min = int(p_info.get("stock_minimum", 0) or 0)
                            fournisseur = p_info.get("fournisseur", "")
                            prix = float(p_info.get("prix_unitaire", 0) or 0)
                            ref = p_info.get("reference", "")

                            # Chercher prédictions
                            match_pred = df_pred[df_pred["Pièce"].str.lower().str.contains(
                                designation.lower()[:15], na=False
                            )] if not df_pred.empty else pd.DataFrame()
                            mtbr = match_pred.iloc[0]["MTBR (jours)"] if not match_pred.empty else "N/A"

                            status_txt = "🚨 RUPTURE" if stock_val == 0 else ("⚠️ Stock bas" if stock_val <= stock_min else "✅ OK")
                            prix_fmt = f"{prix:,.0f}".replace(",", " ")
                            all_pieces_info.append(
                                f"- {designation} ({ref}) [{equip_type}] | Stock: {stock_val}/{stock_min} ({status_txt}) | "
                                f"Fournisseur: {fournisseur} | Prix: {prix_fmt} {devise} | MTBR: {mtbr} jours"
                            )

                        # Calculer valeur totale du stock
                        total_stock_val = sum(
                            int(pieces_data.get(l, {}).get("stock_actuel", 0) or 0) *
                            float(pieces_data.get(l, {}).get("prix_unitaire", 0) or 0)
                            for l in pieces_labels
                        )
                        total_fmt = f"{total_stock_val:,.0f}".replace(",", " ")

                        global_prompt = (
                            f"Agis en tant que Supply Chain Manager stratégique d'un réseau hospitalier (spécialisé en pièces de radiologie).\n"
                            f"Valeur actuelle du stock : {total_fmt} {devise}.\n\n"
                            "Analyse la liste des pièces de rechange, leurs niveaux de stock minimum et leurs comportements historiques :\n" + "\n".join(all_pieces_info) + "\n\n"
                            f"{feedback_context_sp}\n"
                            f"{'Ajuste tes recommandations en fonction de la précision passée des prédictions.' if feedback_context_sp else ''}\n"
                            f"Utilise UNIQUEMENT la devise {devise} dans ta réponse.\n"
                            "Exigence de réponse : Fournis une stratégie rigoureuse structurée de cette façon précise :\n"
                            "🔍 Analyse du risque — identifie le capital immobilisé inutilement (pièces qui dorment) et les pièces critiques prêtes à casser.\n"
                            "🛒 Recommandation — indique quelles ruptures actuelles impactent la continuité des soins, justifie pourquoi.\n"
                            "📅 Timing d'achat — plan de commande clair (quoi acheter aujourd'hui vs mois prochain).\n"
                            f"💰 Impact budget — impact financier exact ({devise}) et comment optimiser la trésorerie sans prendre de risque.\n"
                        )
                        from ai_engine import _call_ia
                        analyse = _call_ia(global_prompt, timeout=60) or "Aucune réponse de l'IA. Veuillez réessayer."

                    # Afficher résultat global
                    st.markdown("#### 📋 Analyse IA Globale — Toutes les pièces")

                    # Résumé badges
                    nb_rupture = len([l for l in all_pieces_info if "RUPTURE" in l])
                    nb_bas = len([l for l in all_pieces_info if "Stock bas" in l])
                    nb_ok = len(all_pieces_info) - nb_rupture - nb_bas
                    st.markdown(f"""
<div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px;">
    <span style="background: rgba(239,68,68,0.15); color: #ef4444; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">🚨 {nb_rupture} en rupture</span>
    <span style="background: rgba(249,115,22,0.15); color: #f97316; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">⚠️ {nb_bas} stock bas</span>
    <span style="background: rgba(16,185,129,0.15); color: #10b981; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">✅ {nb_ok} OK</span>
    <span style="background: rgba(59,130,246,0.15); color: #3b82f6; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">📦 {len(all_pieces_info)} pièces total</span>
    <span style="background: rgba(168,85,247,0.15); color: #a855f7; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">💰 Valeur: {total_fmt} {devise}</span>
</div>""", unsafe_allow_html=True)

                    # Parser et afficher la réponse IA par sections
                    sections = {
                        "risque": {"text": "", "icon": "🔍", "title": "Analyse du risque", "color": "#ef4444"},
                        "recommandation": {"text": "", "icon": "🛒", "title": "Recommandation", "color": "#f59e0b"},
                        "timing": {"text": "", "icon": "📅", "title": "Timing d'achat", "color": "#10b981"},
                        "budget": {"text": "", "icon": "💰", "title": "Impact budget", "color": "#3b82f6"},
                    }
                    current_section = None
                    for line in analyse.split("\n"):
                        line_lower = line.lower().strip()
                        if "risque" in line_lower and ("analyse" in line_lower or "🔍" in line):
                            current_section = "risque"
                            continue
                        elif "recommandation" in line_lower or "🛒" in line:
                            current_section = "recommandation"
                            continue
                        elif "timing" in line_lower or "📅" in line:
                            current_section = "timing"
                            continue
                        elif "budget" in line_lower or "impact" in line_lower or "💰" in line:
                            current_section = "budget"
                            continue
                        if current_section and line.strip():
                            sections[current_section]["text"] += line.strip() + "<br>"

                    # Si le parsing n'a pas trouvé de sections, mettre tout dans "risque"
                    has_sections = any(s["text"] for s in sections.values())
                    if not has_sections:
                        sections["risque"]["text"] = analyse.replace("\n", "<br>")

                    # Afficher en cards pleine largeur (vertical)
                    for key, sec in sections.items():
                        if not sec["text"]:
                            continue
                        st.markdown(f"""
<div style="background: rgba({int(sec['color'][1:3], 16)},{int(sec['color'][3:5], 16)},{int(sec['color'][5:7], 16)},0.08);
     border-left: 4px solid {sec['color']};
     border-radius: 8px; padding: 16px; margin-bottom: 10px;">
    <div style="color: {sec['color']}; font-weight: 700; font-size: 0.9rem;
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        {sec['icon']} {sec['title']}</div>
    <div style="color: #f1f5f9; font-size: 0.92rem; line-height: 1.5;">{sec['text']}</div>
</div>""", unsafe_allow_html=True)

                else:
                    # Analyse d'une seule pièce
                    with st.spinner("Analyse des tendances et risques par Gemini..."):
                        piece_info = pieces_data.get(selected_p, {})
                        designation = piece_info.get("designation", selected_p)
                        equip_type = piece_info.get("equipement_type", "")
                        stock_val = int(piece_info.get("stock_actuel", 0) or 0)
                        stock_min = int(piece_info.get("stock_minimum", 0) or 0)
                        fournisseur = piece_info.get("fournisseur", "")
                        prix = float(piece_info.get("prix_unitaire", 0) or 0)
                        ref = piece_info.get("reference", "")

                        match_pred = df_pred[df_pred["Pièce"].str.lower().str.contains(
                            designation.lower()[:15], na=False
                        )] if not df_pred.empty else pd.DataFrame()

                        mtbr = match_pred.iloc[0]["MTBR (jours)"] if not match_pred.empty else "Pas de données"
                        dernier_rempl = match_pred.iloc[0]["Dernier Rempl."] if not match_pred.empty else "Aucun"
                        prochain = match_pred.iloc[0]["Prochain Besoin"] if not match_pred.empty else "À évaluer"

                        info = {
                            "Pièce": designation,
                            "Équipement": equip_type,
                            "Référence": ref,
                            "Stock actuel": stock_val,
                            "Stock minimum": stock_min,
                            "Fournisseur": fournisseur,
                            "Prix unitaire": prix,
                            "MTBR (jours)": mtbr,
                            "Dernier Rempl.": dernier_rempl,
                            "Prochain Besoin": prochain,
                        }
                        analyse = generer_conseil_achat_ia(info)

                    st.markdown("#### 📋 Résultat de l'Analyse IA")

                    stock_color = "#ef4444" if stock_val <= stock_min else "#10b981"
                    st.markdown(f"""
<div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px;">
    <span style="background: rgba(59,130,246,0.15); color: #3b82f6; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">🔧 {designation}</span>
    <span style="background: rgba(168,85,247,0.15); color: #a855f7; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">🏥 {equip_type}</span>
    <span style="background: rgba(45,212,191,0.15); color: #2dd4bf; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">📦 Ref: {ref}</span>
    <span style="background: rgba({239 if stock_val <= stock_min else 16},{68 if stock_val <= stock_min else 185},{68 if stock_val <= stock_min else 129},0.15);
         color: {stock_color}; padding: 4px 14px;
         border-radius: 20px; font-size: 0.8rem; font-weight: 600;">📊 Stock: {stock_val}/{stock_min}</span>
</div>""", unsafe_allow_html=True)

                    sections = {
                        "risque": {"text": "", "icon": "🔍", "title": "Analyse du risque", "color": "#ef4444"},
                        "recommandation": {"text": "", "icon": "🛒", "title": "Recommandation", "color": "#f59e0b"},
                        "timing": {"text": "", "icon": "📅", "title": "Timing d'achat", "color": "#10b981"},
                        "budget": {"text": "", "icon": "💰", "title": "Impact budget", "color": "#3b82f6"},
                    }

                    current_section = None
                    for line in analyse.split("\n"):
                        line_lower = line.lower().strip()
                        if "risque" in line_lower and ("analyse" in line_lower or "🔍" in line):
                            current_section = "risque"
                            continue
                        elif "recommandation" in line_lower or "🛒" in line:
                            current_section = "recommandation"
                            continue
                        elif "timing" in line_lower or "📅" in line:
                            current_section = "timing"
                            continue
                        elif "budget" in line_lower or "impact" in line_lower or "💰" in line:
                            current_section = "budget"
                            continue
                        if current_section and line.strip():
                            sections[current_section]["text"] += line.strip() + "<br>"

                    has_sections = any(s["text"] for s in sections.values())
                    if not has_sections:
                        sections["risque"]["text"] = analyse.replace("\n", "<br>")

                    col1, col2 = st.columns(2)
                    for i, (key, sec) in enumerate(sections.items()):
                        if not sec["text"]:
                            continue
                        col = col1 if i % 2 == 0 else col2
                        with col:
                            st.markdown(f"""
<div style="background: rgba({int(sec['color'][1:3], 16)},{int(sec['color'][3:5], 16)},{int(sec['color'][5:7], 16)},0.08);
     border-left: 4px solid {sec['color']};
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: {sec['color']}; font-weight: 700; font-size: 0.85rem;
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        {sec['icon']} {sec['title']}</div>
    <div style="color: #f1f5f9; font-size: 0.95rem;">{sec['text']}</div>
</div>""", unsafe_allow_html=True)

            # ============ FEEDBACK PRÉDICTIONS PIÈCES (HITL) ============
            st.markdown("---")
            st.subheader("🔄 Feedback — Validez les Prédictions Pièces")
            st.caption("Sélectionnez une pièce pour donner votre feedback. L'IA utilisera vos retours pour affiner ses prochaines recommandations.")

            try:
                from db_engine import save_prediction_feedback, get_prediction_accuracy, lire_prediction_feedback

                # Précision globale par pièce (cards compactes)
                accuracy_data = get_prediction_accuracy()
                piece_names_set = set(df_pred["Pièce"].tolist()) if not df_pred.empty and "Pièce" in df_pred.columns else set()
                piece_accuracy = {k: v for k, v in accuracy_data.items() if k in piece_names_set} if accuracy_data else {}

                if piece_accuracy:
                    st.markdown("##### 🎯 Précision des Prédictions")
                    n_cols = min(len(piece_accuracy), 5)
                    acc_cols = st.columns(n_cols)
                    for i, (p_name, stats) in enumerate(piece_accuracy.items()):
                        col = acc_cols[i % n_cols]
                        prec = stats["precision"]
                        color = "#10b981" if prec >= 70 else "#f59e0b" if prec >= 40 else "#ef4444"
                        col.markdown(f"""
<div style="background: rgba(30,41,59,0.7); border: 1px solid {color}40; border-radius: 10px; padding: 8px; text-align: center;">
    <div style="font-size: 1.4rem; font-weight: 700; color: {color};">{prec}%</div>
    <div style="font-size: 0.7rem; color: #94a3b8;">{p_name[:20]}</div>
    <div style="font-size: 0.65rem; color: #64748b;">{stats['total']} fb</div>
</div>""", unsafe_allow_html=True)

                # Selectbox compact pour choisir la pièce
                fb_options = []
                fb_map = {}
                for _, pr in df_pred.iterrows():
                    p_n = pr.get("Pièce", "?")
                    p_d = str(pr.get("Prochain Besoin", "?"))
                    label = f"{p_n} — Besoin: {p_d}"
                    fb_options.append(label)
                    fb_map[label] = (p_n, p_d)

                if fb_options:
                    sel_fb = st.selectbox("📋 Sélectionner une pièce :", fb_options, key="sp_fb_select")
                    sel_piece, sel_date = fb_map[sel_fb]
                    fk = f"fb2_{sel_piece}_{sel_date}".replace(" ", "_").replace("/", "-").replace(":", "")

                    # Boutons inline
                    fb_c = st.columns([1, 1, 1, 1])
                    if fb_c[0].button("✅ Correct", key=f"ok2_{fk}", use_container_width=True):
                        user = st.session_state.get("username", "system")
                        save_prediction_feedback(sel_piece, sel_date, "correct", username=user)
                        st.success(f"✅ Feedback enregistré pour {sel_piece}")
                        import time; time.sleep(1); st.rerun()

                    if fb_c[1].button("❌ Pas nécessaire", key=f"fp2_{fk}", use_container_width=True):
                        user = st.session_state.get("username", "system")
                        save_prediction_feedback(sel_piece, sel_date, "faux_positif", username=user)
                        st.success(f"✅ Faux positif noté pour {sel_piece}")
                        import time; time.sleep(1); st.rerun()

                    if fb_c[2].button("⏰ Décalé", key=f"dec2_{fk}", use_container_width=True):
                        st.session_state[f"show_dec2_{fk}"] = True

                    if fb_c[3].button("📜 Historique", key=f"hist2_{fk}", use_container_width=True):
                        st.session_state[f"show_hist2_{fk}"] = not st.session_state.get(f"show_hist2_{fk}", False)

                    # Décalé form
                    if st.session_state.get(f"show_dec2_{fk}"):
                        dc1, dc2 = st.columns(2)
                        dr = dc1.date_input("📅 Date réelle", key=f"dr2_{fk}")
                        nt = dc2.text_input("📝 Note", key=f"nt2_{fk}")
                        if st.button("💾 Enregistrer", key=f"sv2_{fk}"):
                            user = st.session_state.get("username", "system")
                            save_prediction_feedback(sel_piece, sel_date, "decale", date_reelle=str(dr), note=nt, username=user)
                            st.success("✅ Feedback enregistré.")
                            st.session_state.pop(f"show_dec2_{fk}", None)
                            import time; time.sleep(1); st.rerun()

                    # Historique
                    if st.session_state.get(f"show_hist2_{fk}"):
                        df_fb = lire_prediction_feedback(sel_piece, limit=10)
                        if not df_fb.empty:
                            for _, fb in df_fb.iterrows():
                                icon = "✅" if fb["resultat"] == "correct" else "❌" if fb["resultat"] == "faux_positif" else "⏰"
                                dr_t = f" → Réel: {fb['date_reelle']}" if fb.get("date_reelle") else ""
                                nt_t = f" — {fb['note_technicien']}" if fb.get("note_technicien") else ""
                                st.caption(f"{icon} {fb['timestamp'][:16]} | Prédit: {fb['date_predite']}{dr_t}{nt_t}")
                        else:
                            st.caption("Aucun feedback pour cette pièce.")

            except Exception as e:
                st.caption(f"⚠️ Feedback non disponible ({e})")

        else:
            st.info("Pas assez de données d'interventions pour générer des prédictions fiables.")

