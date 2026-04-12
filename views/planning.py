# ==========================================
# 📅 PAGE PLANNING MAINTENANCE PRÉVENTIVE
# ==========================================
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database import lire_equipements
from db_engine import lire_planning, ajouter_planning, update_planning_statut, supprimer_planning, reprogrammer_planning, log_audit, get_db, lire_techniciens
import plotly.express as px
from styles import plotly_dark_layout
from auth import get_current_user, require_role
from i18n import t


def _fix_encoding(text):
    """Répare le texte UTF-8 mal décodé (ex: Pr├®ventive → Préventive)."""
    if not isinstance(text, str):
        return text
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _fix_df_encoding(df):
    """Applique la correction d'encodage à toutes les colonnes texte du DataFrame."""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(_fix_encoding)
    return df


def page_planning():
    st.title(t("planning"))

    user = get_current_user()
    username = user.get("username", "?") if user else "?"

    # ============ AJOUTER MAINTENANCE ============
    if require_role("Admin", "Manager", "Technicien"):
        # Gérer le pré-remplissage : garder en session_state jusqu'à soumission
        if "prefill_planning" in st.session_state:
            prefill = st.session_state["prefill_planning"]
        else:
            prefill = {}
        prefill_machine = prefill.get("machine", "")
        prefill_type = prefill.get("type", "")
        prefill_desc = prefill.get("description", "")
        prefill_notes = prefill.get("notes", "")
        auto_open = bool(prefill_machine)

        # Si pré-remplissage depuis le dashboard → formulaire direct (pas d'expander)
        # Utiliser expander fermé par défaut (demandé par l'utilisateur)
        form_container = st.container() if auto_open else st.expander(t("add_maintenance"), expanded=False)

        with form_container:
            df_equip = lire_equipements()

            # Construire la liste des clients et équipements
            if not df_equip.empty:
                if "Client" not in df_equip.columns:
                    df_equip["Client"] = "Centre Principal"
            else:
                df_equip = pd.DataFrame([{"Nom": "Machine 1", "Client": ""}])

            with st.form("form_planning"):
                if prefill_machine:
                    st.info(f"📋 Formulaire pré-rempli depuis l'alerte : **{prefill_machine}**")

                col1, col2 = st.columns(2)
                with col1:
                    # 1. Sélection Client
                    clients_list = sorted(df_equip["Client"].fillna("").unique().tolist())
                    # Trouver le client de la machine pré-remplie
                    prefill_client = ""
                    if prefill_machine:
                        match = df_equip[df_equip["Nom"] == prefill_machine]
                        if not match.empty:
                            prefill_client = match.iloc[0].get("Client", "")
                    client_idx = 0
                    if prefill_client and prefill_client in clients_list:
                        client_idx = clients_list.index(prefill_client)

                    selected_client = st.selectbox("🏢 Client", clients_list, index=client_idx)

                    # 2. Sélection Équipement (filtré par client)
                    equip_du_client = df_equip[df_equip["Client"] == selected_client]
                    equip_noms = equip_du_client["Nom"].tolist() if not equip_du_client.empty else ["Machine 1"]
                    equip_idx = 0
                    if prefill_machine and prefill_machine in equip_noms:
                        equip_idx = equip_noms.index(prefill_machine)

                    selected_machine = st.selectbox("🏥 Équipement", equip_noms, index=equip_idx)

                    date_prevue = st.date_input(t("planned_date"),
                                                value=datetime.now() + timedelta(days=30))

                    # Sélection Technicien
                    df_techs = lire_techniciens()
                    tech_opts = [f"{r.nom} {r.prenom}" for r in df_techs.itertuples()] if not df_techs.empty else [username]
                    tech_telegram_map = {f"{r.nom} {r.prenom}": r.telegram_id for r in df_techs.itertuples()} if not df_techs.empty else {}

                    technicien = st.selectbox(t("assigned_tech"), tech_opts)
                with col2:
                    type_options = [
                        "Préventive", "Calibration", "Inspection",
                        "Remplacement planifié", "Mise à jour logiciel"
                    ]
                    type_idx = 0
                    if prefill_type and prefill_type in type_options:
                        type_idx = type_options.index(prefill_type)
                    type_maint = st.selectbox(t("type"), type_options, index=type_idx)
                    recurrence = st.selectbox(t("recurrence"), [
                        "", "Mensuelle", "Trimestrielle", "Semestrielle", "Annuelle"
                    ])

                description = st.text_area(t("description"), value=prefill_desc, height=80)
                notes = st.text_area(t("notes"), value=prefill_notes, height=60)

                if st.form_submit_button(t("save"), use_container_width=True):
                    # Calculer les dates récurrentes
                    dates_a_creer = [date_prevue]
                    
                    if recurrence:
                        # Intervalles selon la récurrence
                        if recurrence == "Mensuelle":
                            delta_months = 1
                        elif recurrence == "Trimestrielle":
                            delta_months = 3
                        elif recurrence == "Semestrielle":
                            delta_months = 6
                        elif recurrence == "Annuelle":
                            delta_months = 12
                        else:
                            delta_months = 0
                        
                        if delta_months > 0:
                            # Générer les dates sur 12 mois à partir de la date choisie
                            from dateutil.relativedelta import relativedelta
                            current_date = date_prevue
                            for _ in range(12):
                                current_date = current_date + relativedelta(months=delta_months)
                                if (current_date - date_prevue).days > 365:
                                    break
                                dates_a_creer.append(current_date)
                    
                    # Créer toutes les entrées
                    nb_created = 0
                    for d in dates_a_creer:
                        ajouter_planning({
                            "machine": selected_machine,
                            "client": selected_client,
                            "type_maintenance": type_maint,
                            "date_prevue": d.strftime("%Y-%m-%d"),
                            "technicien_assigne": technicien,
                            "recurrence": recurrence,
                            "description": description,
                            "notes": notes.strip(),
                        })
                        nb_created += 1

                    # Notification Telegram (uniquement pour la 1ère date)
                    from notifications import get_notifier
                    notifier = get_notifier()
                    if notifier.telegram_ok:
                        tg_id = tech_telegram_map.get(technicien, "")
                        msg_recurrence = f" (récurrence {recurrence})" if recurrence else ""
                        notifier.notifier_nouvelle_maintenance(
                            f"{selected_machine} ({selected_client})", technicien, tg_id, date_prevue.strftime("%d/%m/%Y"), type_maint
                        )
                        if nb_created > 1:
                            dates_str = ", ".join(d.strftime("%d/%m/%Y") for d in dates_a_creer)
                            notifier.envoyer_telegram(
                                f"📅 *{nb_created} maintenances préventives planifiées*{msg_recurrence}\n\n"
                                f"🏥 Machine : *{selected_machine}*\n"
                                f"🏢 Client : {selected_client}\n"
                                f"👤 Technicien : {technicien}\n\n"
                                f"📆 Dates : {dates_str}"
                            )
                        st.toast("🔔 Notification Telegram envoyée !")

                    log_audit(username, "PLANNING_ADDED",
                              f"{selected_machine} - {type_maint} - {date_prevue} ({nb_created} entrées)", "Planning")
                    
                    if nb_created > 1:
                        st.success(f"✅ {nb_created} maintenances préventives planifiées ({recurrence}) à partir du {date_prevue.strftime('%d/%m/%Y')} !")
                    else:
                        st.success(t("save_success"))
                    # Nettoyer le prefill seulement APRÈS soumission réussie
                    st.session_state.pop("prefill_planning", None)
                    st.rerun()

        # Si mode pré-remplissage, ne pas afficher la liste en dessous
        if auto_open:
            st.caption("💡 Remplissez le formulaire ci-dessus puis cliquez sur Enregistrer.")
            return

    # ============ VUE PLANNING ============
    st.markdown("---")
    df = _fix_df_encoding(lire_planning())

    # Mettre à jour les statuts en retard (seulement si données)
    if not df.empty:
        today = datetime.now().strftime("%Y-%m-%d")
        with get_db() as conn:
            conn.execute("""
                UPDATE planning_maintenance
                SET statut = 'En retard'
                WHERE date_prevue < ? AND statut = 'Planifiée'
            """, (today,))
        df = _fix_df_encoding(lire_planning())

    # ============ ALERTES MAINTENANCES EN RETARD ============
    if not df.empty:
        df_retard = df[df["statut"] == "En retard"]
        if not df_retard.empty:
            with st.expander(f"🔴 {len(df_retard)} maintenance(s) en retard !", expanded=False):
                for _, r in df_retard.iterrows():
                    client_txt = r.get('client', '') or ''
                    machine_txt = r.get('machine', '?')
                    type_txt = r.get('type_maintenance', '')
                    tech_txt = r.get('technicien_assigne', '')
                    date_prevue = str(r.get('date_prevue', ''))[:10]
                    # Calculer jours de retard
                    try:
                        days_late = (datetime.now() - pd.to_datetime(date_prevue)).days
                        retard_label = f"{days_late} jour(s) de retard"
                    except Exception:
                        retard_label = "En retard"
                    
                    # Badge couleur selon gravité du retard
                    if days_late > 30:
                        badge_color = "#dc2626"  # rouge vif
                        badge_bg = "rgba(220,38,38,0.15)"
                    elif days_late > 14:
                        badge_color = "#f97316"  # orange
                        badge_bg = "rgba(249,115,22,0.15)"
                    else:
                        badge_color = "#eab308"  # jaune
                        badge_bg = "rgba(234,179,8,0.15)"
                    
                    st.markdown(f"""
<div style="border-left:4px solid {badge_color}; background:{badge_bg};
    padding:10px 16px; margin:6px 0; border-radius:0 8px 8px 0;">
  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
    <div>
      <span style="font-weight:700; font-size:0.95rem;">🏥 {machine_txt}</span>
      <span style="color:#94a3b8; font-size:0.85rem;"> — {client_txt}</span>
    </div>
    <div style="background:{badge_color}; color:white; padding:2px 12px;
        border-radius:12px; font-size:0.75rem; font-weight:700;">⏰ {retard_label}</div>
  </div>
  <div style="color:#cbd5e1; font-size:0.82rem; margin-top:4px;">
    🔧 {type_txt} &nbsp;|&nbsp; 📅 Prévue le <b>{date_prevue}</b> &nbsp;|&nbsp; 👤 {tech_txt}
  </div>
</div>
                    """, unsafe_allow_html=True)
            # Notification Telegram pour les nouvelles alertes (une seule fois)
            try:
                df_non_notified = df_retard[df_retard["rappel_envoye"] == 0]
                if not df_non_notified.empty:
                    from notifications import get_notifier
                    notifier = get_notifier()
                    if notifier.telegram_ok:
                        for _, r in df_non_notified.iterrows():
                            msg = (
                                f"⚠️ <b>MAINTENANCE EN RETARD</b>\n\n"
                                f"🏥 Machine : <b>{r['machine']}</b>\n"
                                f"🏢 Client : {r.get('client', '')}\n"
                                f"🔧 Type : {r.get('type_maintenance', '')}\n"
                                f"📅 Prévue le : <b>{r['date_prevue']}</b>\n"
                                f"👤 Technicien : {r.get('technicien_assigne', '')}\n\n"
                                f"👉 Action requise sur <b>SAVIA</b>"
                            )
                            notifier.envoyer_telegram(msg)
                            with get_db() as conn:
                                conn.execute(
                                    "UPDATE planning_maintenance SET rappel_envoye = 1 WHERE id = ?",
                                    (r["id"],)
                                )
                        st.toast(f"🔔 {len(df_non_notified)} alerte(s) Telegram envoyée(s)")
            except Exception:
                pass

    # ============ CALENDRIER VISUEL (Style Google Agenda) ============
    st.subheader("📅 Calendrier des Maintenances")

    import calendar as cal_module

    # Navigation mois
    if "cal_month" not in st.session_state:
        st.session_state["cal_month"] = datetime.now().month
    if "cal_year" not in st.session_state:
        st.session_state["cal_year"] = datetime.now().year

    nav1, nav2, nav3 = st.columns([1, 3, 1])
    with nav1:
        if st.button("◀ Mois précédent", key="prev_month", use_container_width=True):
            m = st.session_state["cal_month"] - 1
            if m < 1:
                m = 12
                st.session_state["cal_year"] -= 1
            st.session_state["cal_month"] = m
            st.rerun()
    with nav2:
        mois_noms = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                     "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        st.markdown(
            f"<h3 style='text-align:center; margin:0; color:#2dd4bf;'>"
            f"{mois_noms[st.session_state['cal_month']]} {st.session_state['cal_year']}</h3>",
            unsafe_allow_html=True
        )
    with nav3:
        if st.button("Mois suivant ▶", key="next_month", use_container_width=True):
            m = st.session_state["cal_month"] + 1
            if m > 12:
                m = 1
                st.session_state["cal_year"] += 1
            st.session_state["cal_month"] = m
            st.rerun()

    # Préparer les événements du mois
    df_cal = df.copy()
    df_cal["date_prevue"] = pd.to_datetime(df_cal["date_prevue"], errors="coerce")
    df_cal = df_cal.dropna(subset=["date_prevue"])

    cal_year = st.session_state["cal_year"]
    cal_month = st.session_state["cal_month"]

    events_by_day = {}
    for _, row in df_cal.iterrows():
        d = row["date_prevue"]
        if d.year == cal_year and d.month == cal_month:
            day = d.day
            if day not in events_by_day:
                events_by_day[day] = []
            client_txt = f" ({row.get('client', '')})" if row.get('client') else ""
            events_by_day[day].append({
                "machine": row["machine"] + client_txt,
                "type": row.get("type_maintenance", ""),
                "tech": row.get("technicien_assigne", ""),
                "statut": row.get("statut", ""),
            })

    # Couleurs
    status_colors = {
        "Planifiée": "#38bdf8",
        "En cours": "#fbbf24",
        "Terminée": "#34d399",
        "En retard": "#f87171",
    }

    # Construire le calendrier HTML
    cal_obj = cal_module.Calendar(firstweekday=0)  # Lundi
    month_days = cal_obj.monthdayscalendar(cal_year, cal_month)
    today_day = datetime.now().day if datetime.now().month == cal_month and datetime.now().year == cal_year else -1

    jours_semaine = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    html = """<style>
    .gcal-table { width:100%; border-collapse:collapse; font-family:'Inter',sans-serif; }
    .gcal-th { background:#0f172a; color:#94a3b8; font-size:0.75rem; padding:8px 4px;
               text-align:center; font-weight:600; text-transform:uppercase; letter-spacing:1px; }
    .gcal-td { border:1px solid rgba(148,163,184,0.1); vertical-align:top; height:90px;
               padding:4px; background:#1e293b; width:14.28%; }
    .gcal-td:hover { background:rgba(45,212,191,0.05); }
    .gcal-td.today { border:2px solid #2dd4bf; }
    .gcal-td.empty { background:#0f172a; }
    .gcal-day { color:#94a3b8; font-size:0.7rem; font-weight:600; margin-bottom:3px; }
    .gcal-day.today { color:#2dd4bf; font-weight:800; }
    .gcal-event { font-size:0.65rem; padding:2px 5px; margin:1px 0; border-radius:4px;
                  color:#fff; overflow:hidden; white-space:nowrap; text-overflow:ellipsis;
                  cursor:default; line-height:1.4; }
    .gcal-event:hover { opacity:0.85; }
    .gcal-legend { display:flex; gap:16px; justify-content:center; margin-top:8px; }
    .gcal-legend-item { display:flex; align-items:center; gap:4px; font-size:0.75rem; color:#94a3b8; }
    .gcal-legend-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
    </style>
    <table class="gcal-table"><thead><tr>"""

    for j in jours_semaine:
        html += f'<th class="gcal-th">{j}</th>'
    html += "</tr></thead><tbody>"

    for week in month_days:
        html += "<tr>"
        for day in week:
            if day == 0:
                html += '<td class="gcal-td empty"></td>'
            else:
                is_today = " today" if day == today_day else ""
                html += f'<td class="gcal-td{is_today}">'
                html += f'<div class="gcal-day{is_today}">{day}</div>'
                if day in events_by_day:
                    for ev in events_by_day[day][:3]:  # Max 3 events per day
                        color = status_colors.get(ev["statut"], "#64748b")
                        html += f'<div class="gcal-event" style="background:{color};" title="{ev["machine"]} — {ev["type"]} — {ev["tech"]}">'
                        html += f'🔧 {ev["machine"][:25]}'
                        html += '</div>'
                    if len(events_by_day[day]) > 3:
                        html += f'<div style="font-size:0.6rem;color:#94a3b8;">+{len(events_by_day[day])-3} de plus</div>'
                html += '</td>'
        html += "</tr>"

    html += "</tbody></table>"

    # Légende
    html += '<div class="gcal-legend">'
    for label, color in status_colors.items():
        html += f'<span class="gcal-legend-item"><span class="gcal-legend-dot" style="background:{color};"></span>{label}</span>'
    html += '</div>'

    try:
        st.html(html)
    except AttributeError:
        st.markdown(html, unsafe_allow_html=True)

    # ============ VUE GANTT TECHNICIENS ============
    if not df.empty:
        st.subheader("📊 Planning Techniciens (Gantt)")

        df_gantt = df.copy()
        df_gantt["date_prevue"] = pd.to_datetime(df_gantt["date_prevue"], errors="coerce")
        df_gantt = df_gantt.dropna(subset=["date_prevue"])

        if not df_gantt.empty:
            # Calculer date_fin = date_prevue + 1 jour (durée estimée par défaut)
            df_gantt["date_fin"] = df_gantt["date_prevue"] + pd.Timedelta(days=1)
            df_gantt["label"] = df_gantt.apply(
                lambda r: f"{r.get('machine', '?')} ({r.get('client', '')})", axis=1
            )

            gantt_colors = {
                "Planifiée": "#38bdf8",
                "En cours": "#fbbf24",
                "Terminée": "#34d399",
                "En retard": "#f87171",
            }

            # Filtre par technicien
            techs_gantt = sorted(df_gantt["technicien_assigne"].fillna("?").unique().tolist())
            g1, g2 = st.columns([3, 1])
            with g2:
                tech_gantt_filter = st.multiselect(
                    "👨‍🔧 Filtrer techniciens", techs_gantt, key="gantt_tech_filter"
                )
            df_gantt_f = df_gantt.copy()
            if tech_gantt_filter:
                df_gantt_f = df_gantt_f[df_gantt_f["technicien_assigne"].isin(tech_gantt_filter)]

            if not df_gantt_f.empty:
                fig_gantt = px.timeline(
                    df_gantt_f,
                    x_start="date_prevue",
                    x_end="date_fin",
                    y="technicien_assigne",
                    color="statut",
                    hover_data=["machine", "client", "type_maintenance", "description"],
                    color_discrete_map=gantt_colors,
                    labels={
                        "technicien_assigne": "Technicien",
                        "statut": "Statut",
                        "date_prevue": "Début",
                        "date_fin": "Fin",
                    },
                )
                fig_gantt.update_layout(
                    height=max(250, len(df_gantt_f["technicien_assigne"].unique()) * 80),
                    xaxis_title="",
                    yaxis_title="",
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                    plot_bgcolor="rgba(15,23,42,1)",
                    paper_bgcolor="rgba(15,23,42,1)",
                    font=dict(color="#e2e8f0"),
                    xaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
                    yaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
                    margin=dict(l=10, r=10, t=40, b=10),
                )
                fig_gantt.update_traces(
                    marker_line_color="rgba(0,0,0,0.3)",
                    marker_line_width=1,
                    opacity=0.9,
                )
                st.plotly_chart(fig_gantt, use_container_width=True)
            else:
                st.info("Aucune maintenance trouvée pour ces techniciens.")

    # ============ DÉTAILS DU JOUR SÉLECTIONNÉ ============
    if not df.empty:
        st.subheader("📋 Détails par Jour")
        selected_date = st.date_input(
            "📅 Sélectionnez une date",
            value=datetime.now().date(),
            key="planning_day_picker",
        )

        # Trouver les maintenances pour ce jour
        df_day = df_cal[
            (df_cal["date_prevue"].dt.year == selected_date.year) &
            (df_cal["date_prevue"].dt.month == selected_date.month) &
            (df_cal["date_prevue"].dt.day == selected_date.day)
        ] if not df_cal.empty else pd.DataFrame()

        if not df_day.empty:
            for _, row in df_day.iterrows():
                status_emoji = {"Planifiée": "📅", "En cours": "🔄",
                                "Terminée": "✅", "En retard": "⚠️"}.get(row["statut"], "❓")
                status_color = status_colors.get(row["statut"], "#64748b")
                row_id = row["id"]
                client_txt = f" ({row.get('client', '')})" if row.get('client') else ""

                st.markdown(
                    f"<div style='border-left:4px solid {status_color}; padding:8px 16px; "
                    f"margin:8px 0; background:rgba(30,41,59,0.8); border-radius:0 8px 8px 0;'>"
                    f"<b>{status_emoji} {row['machine']}{client_txt}</b> — {row.get('type_maintenance', '')}<br/>"
                    f"<span style='color:#94a3b8;'>👤 {row.get('technicien_assigne', '')} • "
                    f"{row.get('description', '')[:80]}</span></div>",
                    unsafe_allow_html=True
                )

                # Actions rapides (Admin/Technicien)
                if require_role("Admin", "Manager", "Technicien") and row["statut"] not in ["Terminée"]:
                    act1, act2, act3 = st.columns([1, 1, 2])
                    with act1:
                        if row["statut"] == "Planifiée" and st.button(
                            "▶ Démarrer", key=f"start_{row_id}", use_container_width=True
                        ):
                            update_planning_statut(row_id, "En cours")
                            log_audit(username, "PLANNING_STARTED", f"{row['machine']}", "Planning")
                            st.rerun()
                    with act2:
                        if st.button("✅ Terminer", key=f"finish_{row_id}", use_container_width=True):
                            update_planning_statut(
                                row_id, "Terminée", datetime.now().strftime("%Y-%m-%d")
                            )
                            log_audit(username, "PLANNING_COMPLETED", f"{row['machine']}", "Planning")
                            st.rerun()
                    with act3:
                        new_date = st.date_input(
                            "📅 Reprogrammer",
                            value=datetime.now() + timedelta(days=7),
                            key=f"reprogram_{row_id}",
                        )
                        if st.button("📅 Reprogrammer", key=f"reprg_btn_{row_id}", use_container_width=True):
                            reprogrammer_planning(row_id, new_date.strftime("%Y-%m-%d"))
                            log_audit(username, "PLANNING_RESCHEDULED",
                                      f"{row['machine']} → {new_date}", "Planning")
                            st.success(f"📅 Reprogrammé au {new_date.strftime('%d/%m/%Y')}")
                            st.rerun()
        else:
            st.info("Aucune maintenance prévue pour cette date.")

    st.markdown("---")

    # ============ RAPPORT PDF ============
    st.subheader("📄 Rapport PDF des Maintenances")

    col_d1, col_d2, col_d3 = st.columns([2, 2, 1])
    with col_d1:
        date_debut = st.date_input("📅 Du", value=datetime.now().date(), key="pdf_date_debut")
    with col_d2:
        date_fin_pdf = st.date_input("📅 Au", value=datetime.now().date() + timedelta(days=90), key="pdf_date_fin")
    with col_d3:
        st.write("")  # spacer
        gen_pdf = st.button("📥 Générer PDF", use_container_width=True)

    if gen_pdf:
        df_rapport = df.copy()
        df_rapport["date_prevue"] = pd.to_datetime(df_rapport["date_prevue"], errors="coerce")
        mask = (df_rapport["date_prevue"] >= pd.Timestamp(date_debut)) & \
               (df_rapport["date_prevue"] <= pd.Timestamp(date_fin_pdf))
        df_rapport = df_rapport[mask].sort_values("date_prevue")

        if df_rapport.empty:
            st.warning("Aucune maintenance trouvée pour cette période.")
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
                doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                        topMargin=3*cm, bottomMargin=1.5*cm,
                                        leftMargin=1.5*cm, rightMargin=1.5*cm)

                styles = getSampleStyleSheet()
                title_style = ParagraphStyle('Title2', parent=styles['Title'],
                                             fontSize=16, spaceAfter=20)
                subtitle_style = ParagraphStyle('Subtitle2', parent=styles['Normal'],
                                                fontSize=10, textColor=colors.grey,
                                                spaceAfter=15)

                elements = []
                elements.append(Paragraph("📅 Rapport Planning Maintenances", title_style))
                elements.append(Paragraph(
                    f"Période : {date_debut.strftime('%d/%m/%Y')} — {date_fin_pdf.strftime('%d/%m/%Y')}  |  "
                    f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
                    subtitle_style
                ))
                elements.append(Spacer(1, 10))

                # Styles pour les cellules (permet le retour à la ligne)
                cell_header_style = ParagraphStyle(
                    'CellHeader', parent=styles['Normal'],
                    fontSize=9, fontName='Helvetica-Bold',
                    textColor=colors.white, leading=11,
                    alignment=1,  # CENTER
                )
                cell_style = ParagraphStyle(
                    'CellBody', parent=styles['Normal'],
                    fontSize=8, textColor=colors.HexColor('#1e293b'),
                    leading=10, wordWrap='CJK',
                )
                cell_style_center = ParagraphStyle(
                    'CellBodyCenter', parent=cell_style,
                    alignment=1,  # CENTER
                )

                # Tableau avec Paragraphs pour le retour à la ligne
                header = [
                    Paragraph("Date", cell_header_style),
                    Paragraph("Machine", cell_header_style),
                    Paragraph("Client", cell_header_style),
                    Paragraph("Type", cell_header_style),
                    Paragraph("Technicien", cell_header_style),
                    Paragraph("Statut", cell_header_style),
                    Paragraph("Description", cell_header_style),
                ]
                data_rows = [header]
                for _, r in df_rapport.iterrows():
                    # Couleur du statut
                    statut_val = str(r.get("statut", ""))
                    statut_color = {"Planifiée": "#2563eb", "En cours": "#d97706", "Terminée": "#16a34a", "En retard": "#dc2626"}.get(statut_val, "#475569")
                    statut_p = Paragraph(f'<font color="{statut_color}"><b>{statut_val}</b></font>', cell_style_center)

                    data_rows.append([
                        Paragraph(r["date_prevue"].strftime("%d/%m/%Y") if pd.notna(r["date_prevue"]) else "?", cell_style_center),
                        Paragraph(str(r.get("machine", "")), cell_style),
                        Paragraph(str(r.get("client", "")), cell_style),
                        Paragraph(str(r.get("type_maintenance", "")), cell_style_center),
                        Paragraph(str(r.get("technicien_assigne", "")), cell_style),
                        statut_p,
                        Paragraph(str(r.get("description", ""))[:120], cell_style),
                    ])

                col_widths = [2.2*cm, 4*cm, 3.5*cm, 2.8*cm, 3.5*cm, 2.5*cm, 7.5*cm]
                table = Table(data_rows, colWidths=col_widths, repeatRows=1)
                table.setStyle(TableStyle([
                    # En-tête : fond bleu foncé professionnel
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    # Corps : fond blanc avec alternance gris clair
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1e293b')),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    # Grille fine
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#1e3a5f')),
                    # Alignement et padding
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]))
                elements.append(table)

                # Résumé
                elements.append(Spacer(1, 20))
                planifiees = len(df_rapport[df_rapport["statut"] == "Planifiée"])
                en_cours = len(df_rapport[df_rapport["statut"] == "En cours"])
                terminees = len(df_rapport[df_rapport["statut"] == "Terminée"])
                en_retard = len(df_rapport[df_rapport["statut"] == "En retard"])
                elements.append(Paragraph(
                    f"<b>Résumé :</b> {len(df_rapport)} maintenance(s) — "
                    f"📅 {planifiees} planifiée(s), 🔄 {en_cours} en cours, "
                    f"✅ {terminees} terminée(s), ⚠️ {en_retard} en retard",
                    styles['Normal']
                ))

                doc.build(
                    elements,
                    onFirstPage=draw_reportlab_header_footer,
                    onLaterPages=draw_reportlab_header_footer
                )
                pdf_bytes = buffer.getvalue()

                st.download_button(
                    "📥 Télécharger le rapport PDF",
                    data=pdf_bytes,
                    file_name=f"planning_maintenance_{date_debut}_{date_fin_pdf}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
                st.success(f"✅ Rapport généré : **{len(df_rapport)}** maintenance(s) trouvée(s)")
            except ImportError:
                st.error("❌ Module `reportlab` manquant. Ajoutez-le dans requirements.txt")
            except Exception as e:
                st.error(f"❌ Erreur génération PDF : {e}")

    st.markdown("---")

    if df.empty:
        st.info(t("no_data"))
    else:
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📅 " + t("planned"), len(df[df["statut"] == "Planifiée"]))
        col2.metric("🔄 " + t("in_progress"), len(df[df["statut"] == "En cours"]))
        col3.metric("✅ " + t("completed"), len(df[df["statut"] == "Terminée"]))

        retard_count = len(df[df["statut"] == "En retard"])
        col4.metric("⚠️ " + t("overdue"), retard_count,
                    delta=f"-{retard_count}" if retard_count > 0 else None,
                    delta_color="inverse")

        # Filtres
        col_f1, col_f2 = st.columns(2)
        statut_filter = col_f1.selectbox(
            t("filter") + " " + t("status"),
            ["Tous", "Planifiée", "En cours", "En retard", "Terminée"]
        )

        # Filtre par client
        if "client" in df.columns:
            clients_uniques = ["Tous"] + sorted(df["client"].fillna("").unique().tolist())
            client_filter = col_f2.selectbox("🏢 Client", clients_uniques)
        else:
            client_filter = "Tous"

        df_show = df if statut_filter == "Tous" else df[df["statut"] == statut_filter]
        if client_filter != "Tous" and "client" in df_show.columns:
            df_show = df_show[df_show["client"] == client_filter]

        # Tableau avec actions
        for _, row in df_show.iterrows():
            status_emoji = {"Planifiée": "📅", "En cours": "🔄",
                            "Terminée": "✅", "En retard": "⚠️"}.get(row["statut"], "❓")

            client_info = row.get("client", "") if "client" in row.index else ""
            display_machine = f"{row['machine']} ({client_info})" if client_info else row["machine"]
            row_id = row["id"]

            with st.container():
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
                c1.markdown(f"**{status_emoji} {display_machine}** — {row['type_maintenance']}")
                c2.markdown(f"📅 {row['date_prevue']}")
                c3.markdown(f"👤 {row['technicien_assigne']}")

                if require_role("Admin", "Manager", "Technicien") and row["statut"] != "Terminée":
                    if c4.button("✅", key=f"done_{row_id}", help=t("completed")):
                        update_planning_statut(
                            row_id, "Terminée",
                            datetime.now().strftime("%Y-%m-%d"))
                        log_audit(username, "PLANNING_COMPLETED",
                                  f"{display_machine}", "Planning")
                        try:
                            from notifications import get_notifier
                            notifier = get_notifier()
                            msg = (
                                f"✅ <b>MAINTENANCE TERMINÉE</b>\n\n"
                                f"👤 Tech : <b>{row.get('technicien_assigne', '')}</b>\n"
                                f"🏥 Machine : <b>{display_machine}</b>\n"
                                f"🔧 Type : {row.get('type_maintenance', '')}\n"
                                f"📅 Terminée le : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                                f"👉 Voir sur <b>SAVIA</b>"
                            )
                            notifier.envoyer_telegram(msg)
                        except Exception:
                            pass
                        st.rerun()

                # Bouton supprimer avec confirmation
                if require_role("Admin"):
                    confirm_key = f"confirm_del_{row_id}"
                    if st.session_state.get(confirm_key):
                        # Mode confirmation
                        c5.markdown("**⚠️ Sûr ?**")
                        col_yes, col_no = st.columns(2)
                        if col_yes.button("✅ Oui", key=f"yes_del_{row_id}", use_container_width=True):
                            supprimer_planning(row_id)
                            log_audit(username, "PLANNING_DELETED", f"{display_machine}", "Planning")
                            st.session_state.pop(confirm_key, None)
                            st.success(f"🗑️ Maintenance supprimée : {display_machine}")
                            st.rerun()
                        if col_no.button("❌ Non", key=f"no_del_{row_id}", use_container_width=True):
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                    else:
                        if c5.button("🗑️", key=f"del_{row_id}", help="Supprimer"):
                            st.session_state[confirm_key] = True
                            st.rerun()

                if row["description"]:
                    st.caption(f"   📝 {row['description']}")

                st.markdown("---")
