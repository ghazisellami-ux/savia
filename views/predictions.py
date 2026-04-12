# ==========================================
# 🔮 PAGE PRÉDICTIONS
# ==========================================
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from styles import plotly_dark_layout, apply_plotly_defaults, CHART_COLORS, health_badge
from database import lire_interventions
from predictive_engine import (
    calculer_score_sante, calculer_tendances,
    predire_prochaine_panne, generer_heatmap_data,
    generer_recommandations
)
from config import EXCEL_PATH


def afficher_predictions():
    """
    Interface de maintenance prédictive (Pilliers 4 & 5).
    
    Logic:
        1. Calcule l'indice de santé (Health Score) basé sur l'âge et le MTTR.
        2. Visualise les scores via Graphiques Plotly.
        3. Appelle l'IA Gemini (Moteur ai_engine) pour analyse experte.
        4. Optimise les prompts (Pillier 5) pour économie de tokens.
    
    Inputs:
        Données de db_engine (interventions, équipements).
    """
    st.title("🔮 Prédictions — Maintenance Prédictive")
    st.markdown("---")

    from database import lire_base
    hex_db, sol_db = lire_base()

    df_hist = lire_interventions()
    if not df_hist.empty:
        # Mapper les colonnes d'interventions pour correspondre à l'ancien format historique
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

    if df_hist.empty:
        st.warning("📭 **Aucune donnée d'historique disponible.**")
        st.info(
            "L'historique est alimenté automatiquement quand vous validez des erreurs "
            "dans la page **Supervision**. Vous pouvez aussi ajouter des données manuellement."
        )

        # Formulaire d'ajout manuel rapide
        with st.expander("➕ Ajouter un événement manuellement"):
            with st.form("form_event_manual"):
                col1, col2 = st.columns(2)
                machine = col1.text_input("Machine", placeholder="Ex: Scanner_CT_01.log")
                code = col2.text_input("Code erreur", placeholder="Ex: 4A01")
                col3, col4 = st.columns(2)
                type_err = col3.text_input("Type", value="Hardware")
                severite = col4.selectbox("Sévérité", ["HAUTE", "MOYENNE", "BASSE"])

                if st.form_submit_button("💾 Enregistrer"):
                    if machine and code:
                        from database import enregistrer_evenement
                        enregistrer_evenement(EXCEL_PATH, machine, code, type_err, severite)
                        st.success("✅ Événement enregistré !")
                        import time; time.sleep(1); st.rerun()
        return

    # ============ FILTRES ============
    st.subheader("⚙️ Filtres")
    col_f1, col_f2 = st.columns(2)

    machines = df_hist["Machine"].unique().tolist()
    filtre_machine = col_f1.selectbox("Machine", ["Toutes"] + machines)
    filtre_jours = col_f2.selectbox("Période", [30, 60, 90, 180, 365], index=2)

    machine_sel = None if filtre_machine == "Toutes" else filtre_machine

    # ============ PRÉDICTIONS PAR MACHINE ============
    st.markdown("---")
    st.subheader("🎯 Prédictions de Pannes")

    predictions_data = []

    for m in machines:
        score, details = calculer_score_sante(df_hist, m, jours_analyse=filtre_jours)
        pred = predire_prochaine_panne(df_hist, m)

        pred_row = {
            "Machine": m,
            "Score Santé": f"{score}%",
            "Tendance": details.get("tendance", "?"),
            "Dernière Panne": details.get("derniere_panne", "Aucune"),
        }

        if pred:
            pred_row["Prochaine Panne (estimée)"] = pred["date_predite"]
            pred_row["Jours Restants"] = pred["jours_restants"]
            pred_row["Confiance"] = f"{pred['confiance']}%"
            pred_row["Intervalle Moyen (j)"] = pred["intervalle_moyen_jours"]
        else:
            pred_row["Prochaine Panne (estimée)"] = "Données insuffisantes"
            pred_row["Jours Restants"] = "-"
            pred_row["Confiance"] = "-"
            pred_row["Intervalle Moyen (j)"] = "-"

        predictions_data.append(pred_row)

    if predictions_data:
        df_pred = pd.DataFrame(predictions_data)
        st.dataframe(df_pred, use_container_width=True, hide_index=True)

    # ============ ANALYSE IA PRÉDICTIVE ============
    st.markdown("---")
    st.subheader("🤖 Analyse IA Prédictive")
    st.caption("Gemini analyse les scores de santé, tendances et prédictions pour générer un diagnostic et un plan de maintenance.")

    if st.button("✨ Analyser avec l'IA", type="primary", use_container_width=True, key="pred_ai_btn"):
        try:
            from ai_engine import _call_ia, AI_AVAILABLE
            if not AI_AVAILABLE:
                st.warning("⚠️ L'IA Gemini n'est pas disponible (clé API non configurée).")
            else:
                # Préparer les données enrichies pour le prompt
                machines_detail = ""

                # Récupérer les données brutes d'interventions
                from database import lire_interventions as _lire_interv
                df_raw = _lire_interv()

                # Récupérer les équipements pour l'âge
                from database import lire_equipements as _lire_equip
                df_equip = _lire_equip()
                age_map = {}
                if not df_equip.empty and "Nom" in df_equip.columns:
                    for _, eq in df_equip.iterrows():
                        nom = eq.get("Nom", "")
                        date_install = eq.get("DateInstallation", "")
                        if nom and date_install:
                            try:
                                from datetime import datetime as dt
                                d = pd.to_datetime(date_install)
                                age_ans = round((dt.now() - d).days / 365, 1)
                                age_map[nom] = age_ans
                            except Exception:
                                pass

                # Build machine → client mapping
                client_map = {}
                if not df_equip.empty and "Nom" in df_equip.columns and "Client" in df_equip.columns:
                    for _, eq in df_equip.iterrows():
                        client_map[eq.get("Nom", "")] = eq.get("Client", "Non spécifié")

                # Récupérer les feedbacks de précision pour le contexte IA
                feedback_context = ""
                try:
                    from db_engine import get_prediction_accuracy
                    acc = get_prediction_accuracy()
                    if acc:
                        feedback_lines = []
                        for m, stats in acc.items():
                            feedback_lines.append(
                                f"  - {m}: {stats['precision']}% de précision sur {stats['total']} feedbacks"
                            )
                        feedback_context = "HISTORIQUE DE PRÉCISION DES PRÉDICTIONS (feedbacks techniciens):\n" + "\n".join(feedback_lines) + "\n"
                except Exception:
                    pass

                for row in predictions_data:
                    m_name = row["Machine"]
                    m_client = client_map.get(m_name, "?")
                    detail = (
                        f"  - {m_name} (Client: {m_client}): Score={row['Score Santé']}, "
                        f"Tendance={row['Tendance']}, "
                        f"Dernière Panne={row['Dernière Panne']}, "
                        f"Prochaine Panne={row.get('Prochaine Panne (estimée)', '?')}, "
                        f"Jours Restants={row.get('Jours Restants', '?')}, "
                        f"Confiance={row.get('Confiance', '?')}"
                    )

                    # Ajouter l'âge de la machine
                    if m_name in age_map:
                        detail += f", Âge={age_map[m_name]} ans"

                    # Ajouter les stats d'interventions pour cette machine
                    if not df_raw.empty and "machine" in df_raw.columns:
                        df_m = df_raw[df_raw["machine"] == m_name]
                        nb_interv = len(df_m)
                        if nb_interv > 0:
                            if "duree_minutes" in df_m.columns:
                                duree_moy = df_m["duree_minutes"].fillna(0).mean()
                                detail += f", MTTR={round(duree_moy / 60, 1)}h"
                            detail += f", Nb interventions={nb_interv}"
                            if "type_erreur" in df_m.columns:
                                types = df_m["type_erreur"].fillna("Inconnu").value_counts().head(3)
                                types_str = ", ".join([f"{t}({c})" for t, c in types.items()])
                                detail += f", Erreurs fréquentes=[{types_str}]"
                            if "cause" in df_m.columns:
                                causes = df_m["cause"].fillna("").replace("", pd.NA).dropna().value_counts().head(2)
                                if not causes.empty:
                                    causes_str = ", ".join([f"{c}({n})" for c, n in causes.items()])
                                    detail += f", Causes fréquentes=[{causes_str}]"

                    machines_detail += detail + "\n"

                # Récupérer le taux horaire et la devise
                try:
                    from db_engine import get_config
                    taux_h = int(float(get_config("taux_horaire_technicien", "90") or "90"))
                    devise = get_config("devise", "EUR")
                except Exception:
                    taux_h = 90
                    devise = "EUR"

                # Coût total global
                cout_total = 0
                if not df_raw.empty and "duree_minutes" in df_raw.columns:
                    cout_total = round((df_raw["duree_minutes"].fillna(0).sum() / 60) * taux_h)

                prompt = f"""Agis en tant qu'Ingénieur Fiabiliste (Reliability Engineer) spécialisé en équipements d'imagerie médicale.
Analyse les scores de santé et les probabilités de pannes de ce parc.

Données de santé et prédictions :
{machines_detail}
Paramètres financiers actuels : {taux_h} {devise}/h, Coût historique de casse : {cout_total} {devise}.

{feedback_context}
⚠️ RÈGLE ABSOLUE : Chaque fois que tu mentionnes un équipement, tu DOIS préciser le client entre parenthèses.
Exemple : "Le Scanner GE (Clinique Pasteur)" et NON "Le Scanner GE".

{"Prends impérativement en compte l'historique de précision (Feedback techniciens) ci-dessus. Modère tes alertes si la précision précédente est faible." if feedback_context else ""}

Génère un diagnostic prédictif strict avec ces sections :
🔴 ⚠️ ALERTES PRIORITAIRES (DANGER CLINIQUE)
Identifie les machines dont la probabilité de panne est imminente et précise le risque de rupture de soins (Toujours inclure le nom du client). Quelles pièces commander immédiatement ?

🟢 ✅ MACHINES STABLES (ZONES SÉCURISÉES)
Liste les machines fiables et justifie pourquoi (MTTR bas, peu de pannes récentes).

📋 PLAN DE MAINTENANCE PRÉDICTIVE
Propose un calendrier technique d'interventions préventives (Qui / Quand / Quoi faire), basé sur l'âge et la MTBF (Mean Time Between Failures).

💰 ESTIMATION DU ROI PRÉVENTIF
Prouve financièrement que le plan préventif proposé coûtera beaucoup moins cher qu'une casse curative ({devise}).

📊 TENDANCES & RISQUES LONG TERME (3-6 MOIS)
Anticipation de l'usure asymétrique, problèmes de réseau de refroidissement ou usure tube RX par exemple."""

                with st.spinner("🧠 Gemini analyse les prédictions..."):
                    analyse = _call_ia(prompt, timeout=90)

                if analyse:
                    st.markdown("#### 📋 Résultat de l'Analyse IA Prédictive")

                    # Nettoyer les astérisques de la réponse IA
                    import re as _re
                    def _clean_md(text):
                        """Remplace les astérisques markdown par des puces et du HTML bold."""
                        # **texte** → <b>texte</b>
                        text = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
                        # Lignes commençant par * ou - → puce •
                        lines = []
                        for line in text.split('\n'):
                            stripped = line.strip()
                            if stripped.startswith('* ') or stripped.startswith('- '):
                                lines.append('• ' + stripped[2:])
                            elif stripped.startswith('*') and len(stripped) > 1 and stripped[1] != '*':
                                lines.append('• ' + stripped[1:].strip())
                            else:
                                # Remplacer les * isolés restants
                                lines.append(stripped)
                        return '\n'.join(lines)

                    analyse = _clean_md(analyse)

                    # Découper l'analyse en sections
                    sections_config = [
                        ("⚠️ ALERTES", "#ef4444", "🔴 Alertes critiques"),
                        ("✅ MACHINES STABLES", "#10b981", "🟢 Machines stables"),
                        ("📋 PLAN DE MAINTENANCE", "#3b82f6", "📅 Plan de maintenance recommandé"),
                        ("💰 ESTIMATION", "#f59e0b", "💰 Estimation des coûts"),
                        ("📊 TENDANCES", "#8b5cf6", "📊 Tendances observées"),
                    ]
                    section_keys = [s[0] for s in sections_config]

                    current_section = ""
                    section_content = {}

                    for line in analyse.split("\n"):
                        matched = False
                        for key in section_keys:
                            if key.lower() in line.lower() or key.split(" ", 1)[-1].lower() in line.lower():
                                current_section = key
                                section_content[key] = ""
                                matched = True
                                break
                        if not matched and current_section:
                            section_content[current_section] = section_content.get(current_section, "") + line + "\n"

                    if section_content:
                        # Afficher toutes les cartes empilées verticalement
                        for key, color, label in sections_config:
                            content = section_content.get(key, "").strip()
                            if content:
                                st.markdown(f"""
<div style="background: rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08); border-left: 4px solid {color}; 
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: {color}; font-weight: 700; font-size: 0.85rem; 
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        {label}</div>
    <div style="color: #f1f5f9; font-size: 0.95rem; line-height: 1.6;">{content.replace(chr(10), '<br>')}</div>
</div>""", unsafe_allow_html=True)

                    else:
                        # Fallback : afficher l'analyse brute dans une card
                        st.markdown(f"""
<div style="background: rgba(59,130,246,0.08); border-left: 4px solid #3b82f6; 
     border-radius: 8px; padding: 16px; margin-bottom: 12px;">
    <div style="color: #3b82f6; font-weight: 700; font-size: 0.85rem; 
         text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        🤖 Analyse IA</div>
    <div style="color: #f1f5f9; font-size: 0.95rem; line-height: 1.6;">{analyse.replace(chr(10), '<br>')}</div>
</div>""", unsafe_allow_html=True)
                else:
                    st.warning("⚠️ Aucune réponse de l'IA. Veuillez réessayer.")
        except ImportError:
            st.error("❌ Module AI non disponible.")
        except Exception as e:
            st.error(f"❌ Erreur : {e}")

    # ============ FEEDBACK PRÉDICTIONS (HITL) ============
    st.markdown("---")
    st.subheader("🔄 Feedback — Validez les Prédictions")
    st.caption("Sélectionnez une machine pour donner votre feedback. L'IA utilisera vos retours pour affiner ses prochaines prédictions.")

    try:
        from db_engine import save_prediction_feedback, get_prediction_accuracy, lire_prediction_feedback

        # Cards de précision compactes
        accuracy_data = get_prediction_accuracy()
        machine_names = set(r["Machine"] for r in predictions_data)
        machine_accuracy = {k: v for k, v in accuracy_data.items() if k in machine_names} if accuracy_data else {}

        if machine_accuracy:
            st.markdown("##### 🎯 Précision des Prédictions")
            n_cols = min(len(machine_accuracy), 5)
            acc_cols = st.columns(n_cols)
            for i, (m_name, stats) in enumerate(machine_accuracy.items()):
                col = acc_cols[i % n_cols]
                prec = stats["precision"]
                color = "#10b981" if prec >= 70 else "#f59e0b" if prec >= 40 else "#ef4444"
                col.markdown(f"""
<div style="background: rgba(30,41,59,0.7); border: 1px solid {color}40; border-radius: 10px; padding: 8px; text-align: center;">
    <div style="font-size: 1.4rem; font-weight: 700; color: {color};">{prec}%</div>
    <div style="font-size: 0.7rem; color: #94a3b8;">{m_name[:20]}</div>
    <div style="font-size: 0.65rem; color: #64748b;">{stats['total']} fb</div>
</div>""", unsafe_allow_html=True)

        # Selectbox compact
        fb_options = []
        fb_map = {}
        for row in predictions_data:
            m_n = row["Machine"]
            p_d = row.get("Prochaine Panne (estimée)", "?")
            if p_d == "Données insuffisantes":
                continue
            label = f"{m_n} — Prédit: {p_d}"
            fb_options.append(label)
            fb_map[label] = (m_n, str(p_d))

        if fb_options:
            sel_fb = st.selectbox("📋 Sélectionner une machine :", fb_options, key="pred_fb_select")
            sel_machine, sel_date = fb_map[sel_fb]
            fk = f"pfb_{sel_machine}_{sel_date}".replace(" ", "_").replace("/", "-")

            # Boutons inline
            fb_c = st.columns([1, 1, 1, 1])
            if fb_c[0].button("✅ Correct", key=f"pok_{fk}", use_container_width=True):
                user = st.session_state.get("username", "system")
                save_prediction_feedback(sel_machine, sel_date, "correct", username=user)
                st.success(f"✅ Feedback enregistré pour {sel_machine}")
                import time; time.sleep(1); st.rerun()

            if fb_c[1].button("❌ Faux positif", key=f"pfp_{fk}", use_container_width=True):
                user = st.session_state.get("username", "system")
                save_prediction_feedback(sel_machine, sel_date, "faux_positif", username=user)
                st.success(f"✅ Faux positif noté pour {sel_machine}")
                import time; time.sleep(1); st.rerun()

            if fb_c[2].button("⏰ Décalé", key=f"pdec_{fk}", use_container_width=True):
                st.session_state[f"show_pdec_{fk}"] = True

            if fb_c[3].button("📜 Historique", key=f"phist_{fk}", use_container_width=True):
                st.session_state[f"show_phist_{fk}"] = not st.session_state.get(f"show_phist_{fk}", False)

            # Décalé form
            if st.session_state.get(f"show_pdec_{fk}"):
                dc1, dc2 = st.columns(2)
                dr = dc1.date_input("📅 Date réelle de la panne", key=f"pdr_{fk}")
                nt = dc2.text_input("📝 Note", key=f"pnt_{fk}")
                if st.button("💾 Enregistrer", key=f"psv_{fk}"):
                    user = st.session_state.get("username", "system")
                    save_prediction_feedback(sel_machine, sel_date, "decale", date_reelle=str(dr), note=nt, username=user)
                    st.success("✅ Feedback enregistré.")
                    st.session_state.pop(f"show_pdec_{fk}", None)
                    import time; time.sleep(1); st.rerun()

            # Historique
            if st.session_state.get(f"show_phist_{fk}"):
                df_fb = lire_prediction_feedback(sel_machine, limit=10)
                if not df_fb.empty:
                    for _, fb in df_fb.iterrows():
                        icon = "✅" if fb["resultat"] == "correct" else "❌" if fb["resultat"] == "faux_positif" else "⏰"
                        dr_t = f" → Réel: {fb['date_reelle']}" if fb.get("date_reelle") else ""
                        nt_t = f" — {fb['note_technicien']}" if fb.get("note_technicien") else ""
                        st.caption(f"{icon} {fb['timestamp'][:16]} | Prédit: {fb['date_predite']}{dr_t}{nt_t}")
                else:
                    st.caption("Aucun feedback pour cette machine.")

    except Exception as e:
        st.caption(f"⚠️ Feedback non disponible ({e})")

