# ==========================================
# RAPPORTS PDF & EXPORTS
# ==========================================
import streamlit as st
from datetime import datetime, date
from reports import generer_rapport_mensuel
from auth import get_current_user, require_role
from db_engine import log_audit, lire_interventions, lire_equipements, get_config, lire_pieces, lire_contrats
from i18n import t
import os
import pandas as pd
import io
import plotly.express as px


def page_reports():
    st.title(t("reports"))

    user = get_current_user()
    username = user.get("username", "?") if user else "?"
    devise = get_config("devise", "EUR")

    tab_mensuel, tab_client, tab_ia, tab_compare, tab_fiab = st.tabs([
        "📄 Rapport Mensuel",
        "🏢 Rapport Client",
        "🤖 Rapport IA",
        "📊 Comparaison",
        "⭐ Fiabilité",
    ])

    # ========== TAB 1 : RAPPORT MENSUEL GLOBAL ==========
    with tab_mensuel:
        st.subheader(t("monthly_report"))

        col1, col2 = st.columns(2)
        now = datetime.now()
        mois = col1.number_input("Mois", min_value=1, max_value=12, value=now.month)
        annee = col2.number_input("Ann\u00e9e", min_value=2020, max_value=2030, value=now.year)

        if st.button(t("generate_report"), use_container_width=True):
            with st.spinner(t("loading")):
                try:
                    filepath = generer_rapport_mensuel(mois=mois, annee=annee)
                    if filepath and os.path.exists(filepath):
                        log_audit(username, "REPORT_GENERATED",
                                  f"Rapport {mois}/{annee}", "Rapports")
                        st.success(f"Rapport g\u00e9n\u00e9r\u00e9 !")

                        with open(filepath, "rb") as f:
                            st.download_button(
                                label=t("download_pdf"),
                                data=f.read(),
                                file_name=os.path.basename(filepath),
                                mime="application/pdf",
                                use_container_width=True,
                            )
                    else:
                        st.error("Erreur lors de la g\u00e9n\u00e9ration")
                except Exception as e:
                    st.error(f"Erreur : {e}")

        # Rapports existants
        st.markdown("---")
        st.subheader("Rapports existants")
        reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
        if os.path.exists(reports_dir):
            files = sorted(
                [f for f in os.listdir(reports_dir) if f.endswith(".pdf")],
                reverse=True
            )
            if files:
                for f in files:
                    col1, col2 = st.columns([4, 1])
                    fpath = os.path.join(reports_dir, f)
                    size_kb = os.path.getsize(fpath) / 1024
                    col1.markdown(f"`{f}` \u2014 {size_kb:.0f} KB")
                    with open(fpath, "rb") as fp:
                        col2.download_button("\u2b07\ufe0f", fp.read(), file_name=f, mime="application/pdf",
                                             key=f"dl_{f}")
            else:
                st.info(t("no_data"))
        else:
            st.info(t("no_data"))

    # ========== TAB 2 : RAPPORT CLIENT ==========
    with tab_client:
        st.subheader("Rapport Client Mensuel")
        st.markdown("G\u00e9n\u00e9rez un rapport PDF par client avec interventions, co\u00fbts, pi\u00e8ces et disponibilit\u00e9.")

        df_equip = lire_equipements()
        clients = sorted(df_equip["Client"].fillna("Non sp\u00e9cifi\u00e9").unique().tolist()) if not df_equip.empty else []

        if not clients:
            st.info("Aucun client trouv\u00e9. Ajoutez des \u00e9quipements avec un client.")
        else:
            rc1, rc2, rc3 = st.columns(3)
            sel_client = rc1.selectbox("Client", clients, key="rapport_client")
            sel_mois = rc2.number_input("Mois", min_value=1, max_value=12, value=datetime.now().month, key="rc_mois")
            sel_annee = rc3.number_input("Ann\u00e9e", min_value=2020, max_value=2030, value=datetime.now().year, key="rc_annee")

            if st.button("Générer Rapport Client", use_container_width=True):
                df_inter = lire_interventions()
                if not df_inter.empty:
                    df_inter["date_dt"] = pd.to_datetime(df_inter["date"], errors="coerce")
                    # Filter by machine belonging to client
                    machines_client = df_equip[df_equip["Client"] == sel_client]["Nom"].tolist() if not df_equip.empty else []
                    df_client = df_inter[
                        (df_inter["machine"].isin(machines_client)) &
                        (df_inter["date_dt"].dt.month == sel_mois) &
                        (df_inter["date_dt"].dt.year == sel_annee)
                    ].copy()
                else:
                    df_client = pd.DataFrame()

                if df_client.empty:
                    st.warning(f"Aucune intervention pour {sel_client} en {sel_mois}/{sel_annee}.")
                else:
                    # Assurer que cout_pieces existe
                    if "cout_pieces" not in df_client.columns:
                        df_client["cout_pieces"] = 0.0
                    df_client["cout_pieces"] = df_client["cout_pieces"].fillna(0)

                    # Calculer les totaux
                    nb_inter = len(df_client)
                    cout_interventions = df_client["cout"].sum()
                    cout_pieces = df_client["cout_pieces"].sum()
                    cout_total_depenses = cout_interventions + cout_pieces

                    # Récupérer le revenu contrat du client
                    df_contrats = lire_contrats(client=sel_client)
                    revenu_contrat = 0.0
                    if not df_contrats.empty:
                        # Sommer les contrats actifs
                        actifs = df_contrats[df_contrats["statut"] == "Actif"]
                        revenu_contrat = actifs["montant"].sum() if not actifs.empty else 0.0

                    marge = revenu_contrat - cout_total_depenses

                    # ===== SYNTHÈSE FINANCIÈRE =====
                    st.markdown("---")
                    st.markdown("### 💰 Synthèse Financière")
                    m1, m2, m3 = st.columns(3)
                    m1.metric("📥 Revenu Contrat", f"{revenu_contrat:,.0f}".replace(",", " ") + f" {devise}",
                              help="Montant annuel du contrat de maintenance actif")
                    m2.metric("📤 Dépenses Totales", f"{cout_total_depenses:,.0f}".replace(",", " ") + f" {devise}",
                              delta=f"-{cout_total_depenses:,.0f}", delta_color="inverse",
                              help="Coût interventions + coût pièces de rechange")
                    m3.metric("📊 Marge Nette", f"{marge:,.0f}".replace(",", " ") + f" {devise}",
                              delta=f"{marge:+,.0f}", delta_color="normal",
                              help="Revenu contrat - dépenses totales")

                    # Détail dépenses
                    d1, d2, d3 = st.columns(3)
                    d1.metric("🔧 Interventions", nb_inter)
                    d2.metric("Coût Interventions", f"{cout_interventions:,.0f}".replace(",", " ") + f" {devise}")
                    d3.metric("Durée totale", f"{(df_client['duree_minutes'].sum() or 0) / 60:.1f}h")

                    # Breakdown
                    st.markdown("### Détail des interventions")
                    # Ajouter colonne Durée en heures
                    if "duree_minutes" in df_client.columns:
                        df_client["duree_heures"] = (df_client["duree_minutes"].fillna(0) / 60).round(1)
                    cols_show = ["date", "machine", "type_intervention", "technicien", "description",
                                 "statut", "cout", "cout_pieces", "pieces_utilisees", "duree_heures"]
                    available = [c for c in cols_show if c in df_client.columns]
                    st.dataframe(df_client[available].sort_values("date", ascending=False), use_container_width=True, hide_index=True)

                    # Type breakdown
                    if "type_intervention" in df_client.columns:
                        st.markdown("### Répartition par type")
                        type_counts = df_client["type_intervention"].value_counts()
                        st.bar_chart(type_counts)

                    # Pre-generate PDF
                    pdf_client_bytes = None
                    pdf_client_error = None
                    try:
                        from pdf_generator import generer_pdf_rapport_client
                        pdf_client_bytes = generer_pdf_rapport_client(
                            client=sel_client,
                            mois=sel_mois,
                            annee=sel_annee,
                            df_interventions=df_client,
                            revenu_contrat=revenu_contrat,
                            cout_interventions=cout_interventions,
                            cout_pieces=cout_pieces,
                            marge=marge,
                            devise=devise,
                        )
                    except Exception as e:
                        pdf_client_error = str(e)

                    if pdf_client_error:
                        st.error(f"⚠️ Erreur generation PDF : {pdf_client_error}")

                    # CSV download of client report
                    csv_buf = io.StringIO()
                    df_client[available].to_csv(csv_buf, index=False, sep=";")

                    dl_c1, dl_c2 = st.columns(2)
                    with dl_c1:
                        st.download_button(
                            "📋 Télécharger CSV",
                            data=csv_buf.getvalue(),
                            file_name=f"rapport_{sel_client}_{sel_mois}_{sel_annee}.csv",
                            mime="text/csv",
                            use_container_width=True,
                        )
                    with dl_c2:
                        if pdf_client_bytes:
                            st.download_button(
                                "📄 Télécharger PDF",
                                data=pdf_client_bytes,
                                file_name=f"rapport_{sel_client}_{sel_mois}_{sel_annee}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                            )

    # ========== TAB 3 : RAPPORT IA ==========
    with tab_ia:
        st.subheader("🤖 Rapport IA")
        st.caption("Gemini analyse vos données et génère un rapport avec tendances, risques et recommandations.")

        # ===== FILTRES =====
        fi1, fi2, fi3 = st.columns(3)
        ia_periode = fi1.selectbox("📆 Période", ["Mensuel", "Annuel"], key="ia_periode")
        ia_annee = fi2.number_input("Année", 2020, 2030, datetime.now().year, key="ia_annee")
        if ia_periode == "Mensuel":
            ia_mois = fi3.number_input("Mois", 1, 12, datetime.now().month, key="ia_mois")
        else:
            ia_mois = None

        # Client filter
        df_equip_ia = lire_equipements()
        clients_ia = sorted(df_equip_ia["Client"].fillna("Non spécifié").unique().tolist()) if not df_equip_ia.empty else []
        ia_client = st.selectbox("🏢 Client", ["Tous les clients"] + clients_ia, key="ia_client")

        if st.button("🧠 Générer le Rapport IA", use_container_width=True, key="btn_rapport_ia"):
            df_inter = lire_interventions()

            if df_inter.empty:
                st.warning("Aucune donnée d'intervention disponible.")
            else:
                df_inter["date_dt"] = pd.to_datetime(df_inter["date"], errors="coerce")

                # Filter by period
                if ia_periode == "Mensuel":
                    df_periode = df_inter[
                        (df_inter["date_dt"].dt.month == ia_mois) &
                        (df_inter["date_dt"].dt.year == ia_annee)
                    ]
                    periode_label = f"{ia_mois:02d}/{ia_annee}"
                else:
                    df_periode = df_inter[df_inter["date_dt"].dt.year == ia_annee]
                    periode_label = f"Année {ia_annee}"

                # Filter by client
                if ia_client != "Tous les clients":
                    machines_client_ia = df_equip_ia[df_equip_ia["Client"] == ia_client]["Nom"].tolist() if not df_equip_ia.empty else []
                    df_periode = df_periode[df_periode["machine"].isin(machines_client_ia)]
                    client_label = ia_client
                else:
                    client_label = "Tous les clients"

                if df_periode.empty:
                    st.warning(f"Aucune intervention pour {client_label} en {periode_label}.")
                else:
                    # Préparer les statistiques
                    nb = len(df_periode)
                    nb_cloturees = len(df_periode[df_periode["statut"].fillna("").str.contains("lotur", case=False)])
                    types = df_periode["type_intervention"].value_counts().to_dict() if "type_intervention" in df_periode.columns else {}
                    machines_top = df_periode["machine"].value_counts().head(5).to_dict()
                    duree_moy = df_periode["duree_minutes"].fillna(0).mean()
                    duree_totale = df_periode["duree_minutes"].fillna(0).sum()
                    codes_erreur = df_periode["code_erreur"].value_counts().head(10).to_dict() if "code_erreur" in df_periode.columns else {}
                    cout_total = df_periode["cout"].fillna(0).sum()
                    cout_pieces = df_periode["cout_pieces"].fillna(0).sum() if "cout_pieces" in df_periode.columns else 0

                    # Taux horaire
                    try:
                        taux_h = int(float(get_config("taux_horaire_technicien", "90") or "90"))
                    except Exception:
                        taux_h = 90

                    # Techniciens stats
                    tech_stats = df_periode["technicien"].value_counts().head(5).to_dict() if "technicien" in df_periode.columns else {}

                    # Previous period for comparison
                    if ia_periode == "Mensuel":
                        prev_m = ia_mois - 1 if ia_mois > 1 else 12
                        prev_y = ia_annee if ia_mois > 1 else ia_annee - 1
                        df_prev = df_inter[
                            (df_inter["date_dt"].dt.month == prev_m) &
                            (df_inter["date_dt"].dt.year == prev_y)
                        ]
                        if ia_client != "Tous les clients":
                            df_prev = df_prev[df_prev["machine"].isin(machines_client_ia)]
                        prev_label = f"{prev_m:02d}/{prev_y}"
                    else:
                        df_prev = df_inter[df_inter["date_dt"].dt.year == ia_annee - 1]
                        if ia_client != "Tous les clients":
                            df_prev = df_prev[df_prev["machine"].isin(machines_client_ia)]
                        prev_label = f"Année {ia_annee - 1}"
                    nb_prev = len(df_prev)

                    # Mapping Machine → Client
                    machine_client_map = {}
                    if not df_equip_ia.empty and "Nom" in df_equip_ia.columns and "Client" in df_equip_ia.columns:
                        for _, eq_row in df_equip_ia.iterrows():
                            machine_client_map[eq_row["Nom"]] = eq_row.get("Client", "Non spécifié")

                    # Top 5 machines avec client
                    machines_top_raw = df_periode["machine"].value_counts().head(5).to_dict()
                    machines_top_with_client = {
                        f"{m} ({machine_client_map.get(m, '?')})": count
                        for m, count in machines_top_raw.items()
                    }

                    stats_text = f"""Données pour {client_label} — Période : {periode_label}
- {nb} interventions ({nb_cloturees} clôturées)
- Période précédente ({prev_label}) : {nb_prev} interventions
- Variation : {'+' if nb > nb_prev else ''}{nb - nb_prev} interventions
- Types : {types}
- Top 5 machines en panne (avec client) : {machines_top_with_client}
- Durée moyenne : {duree_moy:.0f} minutes
- Durée totale : {duree_totale:.0f} minutes ({duree_totale/60:.1f}h)
- Coût total (charge technique) : {f'{cout_total:,.0f}'.replace(',', ' ')} {devise}
- Coût pièces : {f'{cout_pieces:,.0f}'.replace(',', ' ')} {devise}
- Taux horaire : {taux_h} {devise}/h
- Codes erreur fréquents : {codes_erreur}
- Techniciens : {tech_stats}
- Nb équipements total : {len(df_equip_ia) if not df_equip_ia.empty else 0}
- Mapping complet Équipement → Client : {machine_client_map}"""

                    prompt = f"""Agis en tant qu'Auditeur Qualité Sénior (ISO 13485) et Directeur des Opérations pour un grand réseau de maintenance d'imagerie médicale.
Analyse ces données {'mensuelles' if ia_periode == 'Mensuel' else 'annuelles'} à la loupe et génère un rapport qualitatif, sans concession.

{stats_text}

⚠️ RÈGLE ABSOLUE : Chaque fois que tu mentionnes un équipement, tu DOIS préciser le client entre parenthèses.
Exemple : "Le Scanner CT (Clinique El Manar)" et NON "Le Scanner CT".
Utilise le mapping Équipement → Client explicite.

Génère un rapport structuré avec ces sections EXACTES (utilise des emojis) :

📊 RÉSUMÉ EXÉCUTIF
Synthèse impitoyable des performances de la période (succès et échecs). Inclure les chiffres clés (interventions, évolution, MTTR/coûts).

📈 TENDANCES & PANNES FRÉQUENTES
Identification chirurgicale des causes de pannes répétitives. Un composant lâche-t-il trop souvent chez un client précis ?

⚠️ POINTS DE VULNÉRABILITÉ (RISQUE CLINIQUE)
Quelles machines risquent une panne totale le mois prochain ? Y a-t-il un risque d'arrêt des soins pour un client précis ?

✅ PLAN D'ACTION (RECOMMANDATIONS)
Des actions de maintenance prédictive ou curative immédiates, numérotées par ordre de priorité opérationnelle absolue (avec niveau d'urgence).

💰 RENTABILITÉ & ANALYSE FINANCIÈRE
Analyse stricte des coûts de maintenance réels par rapport à la charge technique. Où perd-on de l'argent ? (Tous montants format: xxx xxx {devise}).

📋 SCORE DE PERFORMANCE
Note globale d'efficacité qualité (0-100) avec justification claire et sans complaisance."""

                    with st.spinner("🧠 Gemini analyse vos données..."):
                        try:
                            from ai_engine import _call_ia
                            result = _call_ia(prompt, timeout=120)
                            if result:
                                st.markdown("---")

                                # Store report in session for PDF download
                                st.session_state["ia_report_text"] = result
                                st.session_state["ia_report_meta"] = {
                                    "client": client_label,
                                    "periode": periode_label,
                                    "nb": nb,
                                    "cout": cout_total,
                                    "devise": devise,
                                }

                                # Display in styled cards
                                sections = {
                                    "RÉSUMÉ": ("#3b82f6", "📊"),
                                    "TENDANCES": ("#8b5cf6", "📈"),
                                    "POINTS": ("#ef4444", "⚠️"),
                                    "RECOMMANDATIONS": ("#10b981", "✅"),
                                    "ANALYSE": ("#f59e0b", "💰"),
                                    "SCORE": ("#06b6d4", "📋"),
                                }

                                current_section = ""
                                section_content = {}

                                def _is_section_header(line_text, keyword):
                                    """Only match if the line looks like a header (short, keyword-heavy)."""
                                    stripped = line_text.strip()
                                    # Remove markdown and emojis for cleaner matching
                                    clean = stripped.replace("**", "").replace("*", "").replace("#", "").strip()
                                    # Must be short line (< 60 chars) to be a header
                                    if len(clean) > 60:
                                        return False
                                    return keyword.lower() in clean.lower()

                                for line in result.split("\n"):
                                    matched = False
                                    for key in sections:
                                        if _is_section_header(line, key):
                                            current_section = key
                                            section_content[key] = ""
                                            matched = True
                                            break
                                    if not matched and current_section:
                                        section_content[current_section] = section_content.get(current_section, "") + line + "\n"

                                if section_content:
                                    for key, (color, icon) in sections.items():
                                        content = section_content.get(key, "").strip()
                                        if content:
                                            st.markdown(
                                                f"""<div style="background: linear-gradient(135deg, {color}15, {color}08);
                                                border-left: 4px solid {color}; border-radius: 8px;
                                                padding: 16px; margin: 10px 0;">
                                                <h4 style="color: {color}; margin: 0 0 8px 0;">{icon} {key}</h4>
                                                <div style="color: #e2e8f0;">{content.replace(chr(10), '<br>')}</div>
                                                </div>""",
                                                unsafe_allow_html=True,
                                            )
                                else:
                                    st.markdown(result)

                                log_audit(username, "AI_REPORT", f"Rapport IA {client_label} {periode_label}", "Rapports")
                            else:
                                st.error("❌ L'IA n'a pas pu générer le rapport. Vérifiez les clés API.")
                        except Exception as e:
                            st.error(f"Erreur IA : {e}")

        # ===== PDF DOWNLOAD (outside the button to persist) =====
        if "ia_report_text" in st.session_state and st.session_state["ia_report_text"]:
            meta = st.session_state.get("ia_report_meta", {})
            report_text = st.session_state["ia_report_text"]

            # Generate PDF from the AI report text
            try:
                from fpdf import FPDF

                class RapportIA_PDF(FPDF):
                    def __init__(self, devise="TND"):
                        super().__init__()
                        self.devise = devise
                        import os
                        from config import BASE_DIR
                        from db_engine import get_config as _gc
                        self.org_name = _gc("nom_organisation", "SIC Radiologie")
                        self.savia_logo = os.path.join(BASE_DIR, "assets", "logo_savia.png")
                        self.client_logo = _gc("logo_path", "")

                    def header(self):
                        import os
                        if os.path.exists(self.savia_logo):
                            try: self.image(self.savia_logo, 10, 8, 35)
                            except: pass
                        if self.client_logo and os.path.exists(self.client_logo):
                            try: self.image(self.client_logo, 170, 8, 25)
                            except: pass
                        self.set_font("Helvetica", "B", 16)
                        self.set_text_color(30, 58, 138)
                        self.cell(0, 10, self.org_name, align="C")
                        self.ln(10)
                        self.set_font("Helvetica", "", 10)
                        self.set_text_color(100, 100, 100)
                        self.cell(0, 6, "Systeme Intelligent de Controle - Imagerie Medicale", align="C")
                        self.ln(6)
                        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
                        self.ln(6)

                    def footer(self):
                        self.set_y(-15)
                        self.set_font("Helvetica", "I", 8)
                        self.set_text_color(150, 150, 150)
                        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} - Rapport IA - {datetime.now().strftime('%d/%m/%Y')}", align="C")

                pdf = RapportIA_PDF(devise=devise)
                pdf.alias_nb_pages()
                pdf.add_page()

                # Title
                pdf.set_font("Helvetica", "B", 14)
                pdf.set_text_color(30, 58, 138)
                pdf.cell(0, 10, "RAPPORT IA - ANALYSE DE MAINTENANCE", align="C")
                pdf.ln(10)
                pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(80, 80, 80)
                safe_client = str(meta.get('client', 'Tous')).encode('latin-1', 'replace').decode('latin-1')
                pdf.cell(0, 7, f"{safe_client} - {meta.get('periode', '')}", align="C")
                pdf.ln(10)

                # Content - rich formatting
                import re
                def _safe(text):
                    """Keep only latin-1 safe characters."""
                    return re.sub(r'[^\x20-\x7E\xA0-\xFF]', '', text).strip()

                ew = pdf.w - pdf.l_margin - pdf.r_margin
                indent = 6  # indent for bullet points

                # Section colors mapping (use accent-free keys for matching)
                section_colors = {
                    "RESUME": (30, 58, 138),       # blue
                    "TENDANCES": (139, 92, 246),    # purple
                    "PANNES": (139, 92, 246),       # purple (alias)
                    "FORCES": (16, 185, 129),       # green - points forts
                    "FORTS": (16, 185, 129),        # green - points forts
                    "FAIBLESSES": (239, 68, 68),    # red - points faibles
                    "FAIBLES": (239, 68, 68),       # red - points faibles
                    "VULNERABILITE": (239, 68, 68), # red
                    "POINTS": (239, 68, 68),        # red - generic fallback
                    "RECOMMANDATIONS": (16, 185, 129),  # green
                    "PLAN D'ACTION": (16, 185, 129),    # green alias
                    "ANALYSE": (245, 158, 11),      # amber
                    "RENTABILITE": (245, 158, 11),  # amber alias
                    "SCORE": (6, 182, 212),          # cyan
                }

                def _normalize_accents(text):
                    """Remove accents for keyword matching."""
                    replacements = {
                        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
                        'À': 'A', 'Â': 'A', 'Ä': 'A',
                        'Î': 'I', 'Ï': 'I',
                        'Ô': 'O', 'Ö': 'O',
                        'Ù': 'U', 'Û': 'U', 'Ü': 'U',
                        'Ç': 'C',
                        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
                        'à': 'a', 'â': 'a', 'ä': 'a',
                        'î': 'i', 'ï': 'i',
                        'ô': 'o', 'ö': 'o',
                        'ù': 'u', 'û': 'u', 'ü': 'u',
                        'ç': 'c',
                    }
                    for orig, repl in replacements.items():
                        text = text.replace(orig, repl)
                    return text

                # Priority colors for bullet points
                priority_colors = {
                    "haute": (220, 38, 38),    # red
                    "high": (220, 38, 38),
                    "critique": (220, 38, 38),
                    "urgent": (220, 38, 38),
                    "moyenne": (234, 179, 8),  # orange
                    "medium": (234, 179, 8),
                    "basse": (34, 197, 94),    # green
                    "low": (34, 197, 94),
                    "faible": (34, 197, 94),
                }

                current_section_color = (30, 58, 138)

                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(0, 0, 0)

                for line in report_text.split("\n"):
                    raw = line
                    clean = _safe(line)
                    # Remove markdown bold/italic markers but track bold
                    is_bold_line = "**" in raw
                    clean = clean.replace("**", "").replace("*", "").strip()
                    # Remove heading markers
                    while clean.startswith("#"):
                        clean = clean[1:]
                    clean = clean.strip()
                    # Remove leftover ?
                    while clean.startswith("?"):
                        clean = clean[1:].strip()
                    if not clean or clean in ("?", "-", "---"):
                        pdf.ln(2)
                        continue

                    # Page break check
                    if pdf.get_y() > 265:
                        pdf.add_page()
                    pdf.set_x(pdf.l_margin)

                    # === SECTION HEADERS (short lines with keywords) ===
                    is_section = False
                    if len(clean) < 80:
                        clean_normalized = _normalize_accents(clean.upper())
                        for marker, color in section_colors.items():
                            if marker in clean_normalized:
                                pdf.ln(4)
                                pdf.set_font("Helvetica", "B", 11)
                                pdf.set_fill_color(*color)
                                pdf.set_text_color(255, 255, 255)
                                pdf.cell(ew, 8, f"  {clean}", fill=True, new_x="LMARGIN", new_y="NEXT")
                                pdf.set_text_color(0, 0, 0)
                                pdf.ln(3)
                                current_section_color = color
                                is_section = True
                                break
                    if is_section:
                        continue

                    # === BULLET POINTS (- or *) ===
                    bullet_match = re.match(r'^[\-\*]\s+(.*)', clean)
                    if bullet_match:
                        text = bullet_match.group(1)
                        pdf.set_x(pdf.l_margin + indent)

                        # Check for priority coloring
                        priority_set = False
                        for pkey, pcolor in priority_colors.items():
                            if pkey in text.lower():
                                # Draw colored bullet
                                pdf.set_fill_color(*pcolor)
                                bx = pdf.get_x()
                                by = pdf.get_y() + 2
                                pdf.circle(bx, by, 1.5, style="F")
                                pdf.set_x(bx + 4)
                                # Bold the priority keyword part
                                if ":" in text:
                                    parts = text.split(":", 1)
                                    pdf.set_font("Helvetica", "B", 9)
                                    pdf.set_text_color(*pcolor)
                                    pdf.cell(pdf.get_string_width(parts[0] + " :") + 2, 5, parts[0] + " :")
                                    pdf.set_font("Helvetica", "", 9)
                                    pdf.set_text_color(40, 40, 40)
                                    pdf.multi_cell(ew - indent - pdf.get_string_width(parts[0] + " :") - 6, 5, parts[1].strip())
                                else:
                                    pdf.set_font("Helvetica", "", 9)
                                    pdf.set_text_color(*pcolor)
                                    pdf.multi_cell(ew - indent - 4, 5, text)
                                pdf.set_text_color(0, 0, 0)
                                priority_set = True
                                break

                        if not priority_set:
                            # Standard bullet
                            pdf.set_fill_color(*current_section_color)
                            bx = pdf.get_x()
                            by = pdf.get_y() + 2
                            pdf.circle(bx, by, 1, style="F")
                            pdf.set_x(bx + 4)
                            if is_bold_line and ":" in text:
                                parts = text.split(":", 1)
                                pdf.set_font("Helvetica", "B", 9)
                                pdf.set_text_color(40, 40, 40)
                                pdf.cell(pdf.get_string_width(parts[0] + " :") + 2, 5, parts[0] + " :")
                                pdf.set_font("Helvetica", "", 9)
                                remaining_w = ew - indent - pdf.get_string_width(parts[0] + " :") - 6
                                if remaining_w > 20:
                                    pdf.multi_cell(remaining_w, 5, parts[1].strip())
                                else:
                                    pdf.ln(5)
                                    pdf.set_x(pdf.l_margin + indent + 4)
                                    pdf.multi_cell(ew - indent - 4, 5, parts[1].strip())
                            else:
                                pdf.set_font("Helvetica", "", 9)
                                pdf.set_text_color(40, 40, 40)
                                pdf.multi_cell(ew - indent - 4, 5, text)
                            pdf.set_text_color(0, 0, 0)
                        pdf.ln(1)
                        continue

                    # === NUMBERED LISTS (1. 2. 3. or a. b. c.) ===
                    num_match = re.match(r'^(\d+[\.\)]\s+|[a-z][\.\)]\s+)(.*)', clean)
                    if num_match:
                        num = num_match.group(1).strip()
                        text = num_match.group(2)
                        pdf.set_x(pdf.l_margin + indent)
                        pdf.set_font("Helvetica", "B", 9)
                        pdf.set_text_color(*current_section_color)
                        pdf.cell(8, 5, num)
                        pdf.set_font("Helvetica", "", 9)
                        pdf.set_text_color(40, 40, 40)
                        pdf.multi_cell(ew - indent - 8, 5, text)
                        pdf.set_text_color(0, 0, 0)
                        pdf.ln(1)
                        continue

                    # === SUB-HEADERS (bold short lines) ===
                    if is_bold_line and len(clean) < 80:
                        pdf.ln(2)
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.set_text_color(*current_section_color)
                        pdf.multi_cell(ew, 6, clean)
                        pdf.set_text_color(0, 0, 0)
                        pdf.ln(1)
                        continue

                    # === SCORE LINE (e.g. "65/100") ===
                    score_match = re.match(r'^(\d+)\s*/\s*100', clean)
                    if score_match:
                        score_val = int(score_match.group(1))
                        if score_val >= 70:
                            sc = (34, 197, 94)  # green
                        elif score_val >= 50:
                            sc = (234, 179, 8)  # orange
                        else:
                            sc = (220, 38, 38)  # red
                        pdf.ln(2)
                        pdf.set_font("Helvetica", "B", 24)
                        pdf.set_text_color(*sc)
                        pdf.cell(ew, 14, f"{score_val} / 100", align="C", new_x="LMARGIN", new_y="NEXT")
                        pdf.set_text_color(0, 0, 0)
                        pdf.set_font("Helvetica", "", 10)
                        pdf.ln(2)
                        continue

                    # === REGULAR PARAGRAPH ===
                    if len(clean) > 1:
                        pdf.set_font("Helvetica", "", 10)
                        pdf.set_text_color(40, 40, 40)
                        pdf.multi_cell(ew, 5, clean)
                        pdf.set_text_color(0, 0, 0)

                pdf_bytes = bytes(pdf.output())

                safe_filename = meta.get('client', 'tous').replace(' ', '_')
                st.download_button(
                    "📄 Télécharger le Rapport IA en PDF",
                    data=pdf_bytes,
                    file_name=f"rapport_ia_{safe_filename}_{meta.get('periode', '').replace('/', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_ia_pdf",
                )
            except Exception as e:
                st.error(f"Erreur génération PDF : {e}")

    # ========== TAB 5 : COMPARAISON ==========
    with tab_compare:
        st.subheader("📊 Comparaison Inter-Clients / Inter-Équipements")

        df_inter = lire_interventions()
        df_equip = lire_equipements()

        if df_inter.empty:
            st.info("Aucune donnée d'intervention.")
        else:
            # Mapper machines → clients
            client_map = {}
            if not df_equip.empty:
                client_map = dict(zip(df_equip["Nom"], df_equip["Client"].fillna("Non spécifié")))
            df_inter["client"] = df_inter["machine"].map(client_map).fillna("Non spécifié")

            compare_mode = st.radio("Comparer par :", ["Client", "Équipement"], horizontal=True, key="cmp_mode")

            if compare_mode == "Client":
                group_col = "client"
            else:
                group_col = "machine"

            # Calculs par groupe
            grp = df_inter.groupby(group_col).agg(
                nb_interventions=("id", "count"),
                duree_totale=("duree_minutes", "sum"),
                nb_corrective=("type_intervention", lambda x: (x.fillna("").str.contains("Corrective", case=False)).sum()),
            ).reset_index()
            grp["duree_h"] = (grp["duree_totale"].fillna(0) / 60).round(1)
            grp = grp.sort_values("nb_interventions", ascending=False)

            # Graphique barres
            fig1 = px.bar(
                grp, x=group_col, y="nb_interventions",
                color="nb_corrective",
                labels={group_col: compare_mode, "nb_interventions": "Interventions", "nb_corrective": "Correctives"},
                title=f"Nombre d'interventions par {compare_mode.lower()}",
                color_continuous_scale="RdYlGn_r",
            )
            fig1.update_layout(
                plot_bgcolor="rgba(15,23,42,1)", paper_bgcolor="rgba(15,23,42,1)",
                font=dict(color="#e2e8f0"), margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig1, use_container_width=True)

            # Graphique durée
            fig2 = px.bar(
                grp, x=group_col, y="duree_h",
                labels={group_col: compare_mode, "duree_h": "Heures"},
                title=f"Durée totale d'intervention par {compare_mode.lower()} (heures)",
                color="duree_h", color_continuous_scale="Blues",
            )
            fig2.update_layout(
                plot_bgcolor="rgba(15,23,42,1)", paper_bgcolor="rgba(15,23,42,1)",
                font=dict(color="#e2e8f0"), margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig2, use_container_width=True)

            # Tableau détaillé
            st.dataframe(
                grp.rename(columns={
                    group_col: compare_mode,
                    "nb_interventions": "🔧 Interventions",
                    "nb_corrective": "⚠️ Correctives",
                    "duree_h": "⏱️ Heures",
                }).drop(columns=["duree_totale"], errors="ignore"),
                use_container_width=True, hide_index=True,
            )

    # ========== TAB 6 : FIABILITÉ ==========
    with tab_fiab:
        st.subheader("⭐ Score de Fiabilité par Équipement")
        st.caption("Score calculé à partir du nombre de pannes, du MTTR et du ratio correctif/préventif.")

        df_inter = lire_interventions()
        df_equip = lire_equipements()

        if df_inter.empty or df_equip.empty:
            st.info("Données insuffisantes pour calculer les scores.")
        else:
            # Grouper par type d'équipement
            type_col = "Type" if "Type" in df_equip.columns else "Nom"
            equip_type_map = dict(zip(df_equip["Nom"], df_equip[type_col].fillna("Autre")))
            df_inter["type_equip"] = df_inter["machine"].map(equip_type_map).fillna("Autre")

            fiab_rows = []
            for equip_type in df_inter["type_equip"].unique():
                df_t = df_inter[df_inter["type_equip"] == equip_type]
                nb_inter = len(df_t)
                nb_machines = df_t["machine"].nunique()

                # Classifier par type d'intervention
                mask_corr = df_t["type_intervention"].fillna("").str.contains("Corrective", case=False)
                mask_prev = df_t["type_intervention"].fillna("").str.contains("ventive", case=False)
                mask_repair = mask_corr | mask_prev

                nb_corrective = int(mask_corr.sum())
                nb_preventive = int(mask_prev.sum())
                nb_repairs = int(mask_repair.sum())

                ratio_corr = (nb_corrective / nb_repairs * 100) if nb_repairs > 0 else 0

                # MTTR = réparations uniquement
                mttr = df_t.loc[mask_repair, "duree_minutes"].fillna(0).mean() / 60 if nb_repairs > 0 else 0

                # Score de fiabilité basé sur réparations (0-100)
                pannes_par_machine = nb_repairs / max(nb_machines, 1)
                score = 100
                score -= min(40, pannes_par_machine * 5)  # pénalité pannes
                score -= min(30, mttr * 5)                # pénalité MTTR
                score -= min(30, ratio_corr * 0.3)        # pénalité correctif
                score = max(0, min(100, score))

                fiab_rows.append({
                    "Type": equip_type,
                    "Machines": nb_machines,
                    "Réparations": nb_repairs,
                    "Correctives": nb_corrective,
                    "Ratio Corr. %": round(ratio_corr, 1),
                    "MTTR (h)": round(mttr, 1),
                    "Score": round(score, 0),
                })

            df_fiab = pd.DataFrame(fiab_rows).sort_values("Score", ascending=False)

            # Score visuel
            for _, row in df_fiab.iterrows():
                score = row["Score"]
                if score >= 80:
                    color, emoji = "#34d399", "🟢"
                elif score >= 50:
                    color, emoji = "#fbbf24", "🟡"
                else:
                    color, emoji = "#f87171", "🔴"

                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:12px; padding:12px; "
                    f"margin:6px 0; background:rgba(30,41,59,0.8); border-radius:10px; "
                    f"border-left:4px solid {color};'>"
                    f"<span style='font-size:2rem;'>{emoji}</span>"
                    f"<div style='flex:1;'>"
                    f"<b style='font-size:1.1rem;'>{row['Type']}</b><br/>"
                    f"<span style='color:#94a3b8;'>{int(row['Machines'])} machine(s) • "
                    f"🔧 {int(row['Réparations'])} rép. (MTTR {row['MTTR (h)']}h) • "
                    f"{row['Ratio Corr. %']}% correctif</span></div>"
                    f"<span style='font-size:2rem; font-weight:800; color:{color};'>"
                    f"{int(score)}</span>"
                    f"<span style='color:#94a3b8; font-size:0.8rem;'>/100</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )

            # Graphique radar/bar
            st.markdown("---")
            fig_fiab = px.bar(
                df_fiab, x="Type", y="Score",
                color="Score", color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                title="Score de Fiabilité par Type d'Équipement",
                labels={"Type": "Type d'équipement", "Score": "Score /100"},
            )
            fig_fiab.update_layout(
                plot_bgcolor="rgba(15,23,42,1)", paper_bgcolor="rgba(15,23,42,1)",
                font=dict(color="#e2e8f0"), margin=dict(l=10, r=10, t=40, b=10),
                yaxis=dict(range=[0, 100]),
            )
            st.plotly_chart(fig_fiab, use_container_width=True)

            # Tableau détaillé
            st.dataframe(df_fiab, use_container_width=True, hide_index=True)
