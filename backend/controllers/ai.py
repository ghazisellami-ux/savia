"""AI analysis and chat routes."""

from api.runtime import (
    Depends,
    HTTPException,
    Header,
    Optional,
    _ai_language_instruction,
    _fallback_translate_payload_for_lang,
    _force_ai_payload_language,
    _get_app_language,
    _normalize_lang,
    app,
    datetime,
    get_db,
    lire_contrats,
    lire_equipements,
    lire_interventions,
    lire_pieces,
    lire_planning,
    log_audit,
    logger,
)
from api.security import (
    _verify_token,
    require_roles,
)

@app.post("/api/ai/analyze-diagnostic")
def analyze_diagnostic(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
    """Calls Gemini to diagnose a machine error code and log contexts."""
    try:
        from ai_engine import get_ai_suggestion, _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible. (Vérifiez GOOGLE_API_KEY).")

    machine = body.get("machine", "Équipement inconnu")
    code_erreur = body.get("code_erreur", "")
    message_erreur = body.get("message_erreur", "")
    log_context = body.get("log_context", "")
    equipment_type = body.get("equipment_type", "")
    lang = _get_app_language(x_savia_lang, body)
    try:
        result = get_ai_suggestion(code_erreur, message_erreur, machine, log_context=log_context, equipment_type=equipment_type, response_language=lang)
        import json
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except:
                return {"ok": True, "result": _force_ai_payload_language(result, lang, _call_ia, clean_json_response)}
        
        if result and isinstance(result, dict):
            result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
            # Map uppercase keys from ai_engine to lowercase keys expected by frontend
            return {"ok": True, "result": {
                "probleme": result.get("Probleme", result.get("probleme", "Non identifié")),
                "cause": result.get("Cause", result.get("cause", "À déterminer")),
                "solution": result.get("Solution", result.get("solution", "Analyse manuelle requise")),
                "prevention": result.get("Prevention", result.get("prevention", "Maintenance préventive recommandée")),
                "urgence": result.get("Urgence", result.get("urgence", "À évaluer")),
                "type": result.get("Type", result.get("type", "?")),
                "priorite": result.get("Priorite", result.get("priorite", "MOYENNE")),
                "confidence": result.get("Confidence_Score", result.get("confidence", 0)),
            }}
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostic IA échoué: {e}")

@app.post("/api/ai/analyze-performance")
def analyze_performance(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """Calls Gemini to produce a detailed predictive maintenance report (v2)."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    kpis = body.get("kpis", {})
    sym = body.get("sym", "TND")
    lang = _get_app_language(x_savia_lang, body)

    # --- Fetch real per-machine data from DB ---
    machine_details = ""
    equip_detail = ""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT machine, COUNT(*) as nb, "
                "SUM(CASE WHEN type_intervention='Corrective' THEN 1 ELSE 0 END) as corr, "
                "SUM(CASE WHEN type_intervention ILIKE '%%r\u00e9ventive%%' THEN 1 ELSE 0 END) as prev, "
                "ROUND(AVG(duree_minutes)::numeric,1) as mttr_m, "
                "ROUND(SUM(cout)::numeric,0) as cout "
                "FROM interventions GROUP BY machine ORDER BY nb DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                machine_details += f"  - {r['machine']}: {r['nb']} int ({r['corr']} corr, {r['prev']} prev), MTTR={r['mttr_m']}min, co\u00fbt={r['cout']} {sym}\n"
            eqs = conn.execute('SELECT "Nom","Client","Type","Statut","DateInstallation" FROM equipements ORDER BY "Nom" LIMIT 25').fetchall()
            for eq in eqs:
                equip_detail += f"  - {eq['Nom']} ({eq.get('Type','?')}) — {eq.get('Client','?')}, install\u00e9: {eq.get('DateInstallation','?')}, statut: {eq.get('Statut','?')}\n"
    except Exception as db_err:
        logger.warning(f"DB fetch for AI failed: {db_err}")

    risk_detail = ""
    for r in kpis.get("top_risques", []):
        risk_detail += f"  - {r.get('machine','?')}: risque={r.get('risque_panne_pct',0)}%, pi\u00e8ce={r.get('composant_a_risque','?')}, panne_dans={r.get('jours_avant_panne','?')}j, sant\u00e9={r.get('score_sante',0)}%\n"

    import datetime
    today = datetime.date.today()

    prompt = f"""{_ai_language_instruction(lang)}
Tu es Directeur du Service Technique d'une entreprise de maintenance d'\u00e9quipements d'imagerie m\u00e9dicale en Tunisie.
Analyse ces donn\u00e9es R\u00c9ELLES et produis un rapport pr\u00e9dictif d\u00e9taill\u00e9.

=== CHIFFRES DU PARC ===
- \u00c9quipements : {kpis.get('nb_equipements', 0)} | Interventions : {kpis.get('nb_interventions', 0)}
- Correctives : {kpis.get('interventions_correctives', 0)} | Pr\u00e9ventives : {kpis.get('interventions_preventives', 0)} | Calibrations : {kpis.get('interventions_calibration', 0)}
- Disponibilit\u00e9 : {kpis.get('disponibilite', 0)}% | MTBF : {kpis.get('mtbf', 0)}h | MTTR : {kpis.get('mttr', 0)}h
- Co\u00fbt total : {kpis.get('cout_total', 0)} {sym}

=== HISTORIQUE PAR MACHINE ===
{machine_details if machine_details else 'Non disponible'}

=== PR\u00c9DICTIONS IA ===
{risk_detail if risk_detail else 'Aucune'}

=== \u00c9QUIPEMENTS ===
{equip_detail if equip_detail else 'Non disponible'}

PRODUIS un rapport JSON STRICT :
{{{{
  "alertes_critiques": [
    {{{{
      "machine": "Nom (Client)",
      "score_sante": 41,
      "jours_avant_panne": 2,
      "nb_interventions": 19,
      "risque": "Risque concret",
      "action_immediate": "Action + pi\u00e8ces"
    }}}}
  ],
  "machines_stables": [
    {{{{
      "machine": "Nom (Client)",
      "score_sante": 84,
      "commentaire": "Pourquoi fiable"
    }}}}
  ],
  "plan_maintenance": [
    {{{{
      "jour": "Lundi {today.strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}},
    {{{{
      "jour": "Mardi {(today + datetime.timedelta(days=1)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}},
    {{{{
      "jour": "Mercredi {(today + datetime.timedelta(days=2)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}}
  ],
  "estimation_couts": {{{{
    "cout_curatif_historique": {int(kpis.get('cout_total', 0))},
    "cout_preventif_propose": 0,
    "detail_preventif": "D\u00e9tail calcul",
    "gain_potentiel": 0,
    "ratio": "Pour 1 {sym} investi, X {sym} \u00e9conomis\u00e9s"
  }}}},
  "tendances": ["Tendance 1", "Tendance 2", "Tendance 3"],
  "conclusion": "Priorit\u00e9 absolue \u00e0..."
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas r\u00e9pondu.")
    result = clean_json_response(raw)
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-pieces")
def analyze_pieces(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Gestionnaire", "Gestionnaire de stock")
    """
    Advanced AI analysis of spare parts with historical usage and predictions.
    Uses calculated consumption, data confidence, and intervention history.
    Generates buying recommendations and purchase planning.
    """
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        from db_engine import get_ai_pieces_context
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI engine is not available.")

    # Get domain and equipment type from request (or use defaults)
    domaine = body.get("domain", "")
    equipment_type = body.get("equipment_type", "")
    sym = body.get("sym", "USD")  # Default to USD for universality
    lang = _get_app_language(x_savia_lang, body)

    # Get comprehensive context from database
    context = get_ai_pieces_context(domaine, equipment_type)
    pieces_data = context.get('pieces', [])
    stats = context.get('statistics', {})
    
    if not pieces_data:
        raise HTTPException(status_code=400, detail="No spare parts data available for analysis.")

    import datetime
    today = datetime.date.today()
    def fmt(d): return d.strftime("%d/%m/%Y")

    # Build detailed inventory report with predictions
    inventory_lines = ""
    critical_pieces = []
    for p in pieces_data:
        ref = p['reference']
        nom = p['designation']
        stock = p['current_stock']
        mini = p['minimum_stock']
        prix = p['unit_price']
        four = p['supplier']
        consomm = p['monthly_consumption']
        confiance = p['data_confidence']
        urgency = p['urgency']
        jours_rupture = p['days_until_rupture']
        recent_use = p['recent_usage_30d']
        
        # Format stock status with prediction (in French)
        if stock == 0:
            status = "EN RUPTURE - CRITIQUE"
        elif stock <= mini:
            status = f"STOCK BAS (besoin {mini - stock + 1})"
        elif jours_rupture is not None and jours_rupture <= 7:
            status = f"CORRECT mais RUPTURE en {jours_rupture:.0f} jours"
        else:
            status = f"ADAPTÉ (marge {stock - mini})"
        
        # Consumption info (in French)
        consump_info = f"Consommation: {consomm:.2f}/mois | Usage récent (30j): {recent_use}x | Confiance: {confiance}"
        
        line = f"  • {nom} ({ref}) | Équip: {p['equipment_type']} | Stock: {stock}/{mini} [{status}] | {consump_info} | Fournisseur: {four} | Prix: {prix:.2f} {sym}\n"
        inventory_lines += line
        
        # Track critical items
        if 'CRITICAL' in urgency:
            critical_pieces.append((ref, nom, urgency))
    
    # Timeline weeks
    s1 = f"{fmt(today)} - {fmt(today+datetime.timedelta(days=6))}"
    s2 = f"{fmt(today+datetime.timedelta(days=7))} - {fmt(today+datetime.timedelta(days=13))}"
    s3 = f"{fmt(today+datetime.timedelta(days=14))} - {fmt(today+datetime.timedelta(days=20))}"
    d0 = fmt(today)
    d3 = fmt(today+datetime.timedelta(days=3))
    d7 = fmt(today+datetime.timedelta(days=7))
    d14 = fmt(today+datetime.timedelta(days=14))
    
    # Contextualize for domain if provided (in French)
    domain_context = ""
    if domaine:
        domain_context = f"\nDomaine: {domaine}"
        if equipment_type:
            domain_context += f" | Équipement principal: {equipment_type}"
    
    prompt = f"""{_ai_language_instruction(lang)}
Tu es un expert en gestion de stock et approvisionnement pour équipements médicaux critiques.
Analyse cet inventaire de pièces de rechange avec prédictions et génère un plan d'achat stratégique.

=== CONTEXTE INSTALLATION ===
Aujourd'hui: {fmt(today)}{domain_context}
Total pièces: {stats['total_pieces']} références
Valeur stock: {stats['total_stock_value']:,.0f} {sym}
Articles urgence CRITIQUE: {stats['critical_urgency_count']}
Articles urgence HAUTE: {stats['high_urgency_count']}

=== INVENTAIRE PIÈCES AVEC PRÉDICTIONS ===
{inventory_lines}

=== DIRECTIVES D'ANALYSE ===
1. Utiliser les données de consommation mensuelle et usage récent pour générer des prédictions fiables
2. Data_confidence indique la fiabilité (INSUFFICIENT/LOW/MEDIUM/HIGH) - prioriser MEDIUM+
3. days_until_rupture = jours avant rupture de stock
4. Patterns usage 30j = indicatif de la tendance réelle
5. Générer quantités commandées basées sur consommation + délai fournisseur
6. Prioriser urgence CRITIQUE + haute confiance données

=== FORMAT RÉPONSE ===
RÉPONDS UNIQUEMENT en JSON valide (pas de markdown, texte avant/après):
{{
  "analyse_risque": "Résumé exécutif (3-4 phrases): identifier pièces critiques, impact opérationnel, capital à risque",
  "recommandations": [
    {{"piece": "Nom pièce", "reference": "REF", "raison": "Impact opérationnel si non commandé (ex: arrêt équipement = X patients)", "action": "Commander immédiatement", "quantite": 2, "date_achat": "{d0}", "urgence": "critique", "cout_estime": 500, "delai_fournisseur": 14}},
    {{"piece": "Nom pièce 2", "reference": "REF2", "raison": "Raison opérationnelle basée pattern consommation", "action": "Commander rapidement", "quantite": 1, "date_achat": "{d7}", "urgence": "haute", "cout_estime": 300, "delai_fournisseur": 14}}
  ],
  "plan_achat": [
    {{"semaine": "Semaine 1 ({s1})", "pieces": ["reference_1"], "budget": 1200, "priorite": "Critique", "raison": "Besoins immédiats"}},
    {{"semaine": "Semaine 2 ({s2})", "pieces": ["reference_2"], "budget": 800, "priorite": "Haute", "raison": "Prévenir rupture"}},
    {{"semaine": "Semaine 3 ({s3})", "pieces": ["reference_3"], "budget": 500, "priorite": "Normale", "raison": "Maintenir stock minimum"}}
  ],
  "impact_budget": {{
    "cout_total_commande": 2500,
    "gain_potentiel": 8000,
    "ratio": "Pour chaque 1 {sym} investi, X {sym} d'économie sur indisponibilité",
    "cout_indisponibilite_estime": 3000,
    "calcul_methode": "Basé sur nombre équipements critiques et consommation mensuelle"
  }},
  "tendances": ["Tendance 1 avec données concrètes", "Tendance 2", "Tendance 3"]
}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="AI did not respond.")
    result = clean_json_response(raw)
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    
    # Log the analysis
    username = user.get("sub", "unknown")
    log_audit(username, "AI_ANALYZE_PIECES", f"Analyzed {len(pieces_data)} spare parts", "pieces")
    
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-sav")
def analyze_sav(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique")
    """Comprehensive SAV/Interventions analysis using Gemini."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    sav_data = body.get("sav_data", {})
    sym = body.get("sym", "TND")
    lang = _get_app_language(x_savia_lang, body)

    prompt = f"""{_ai_language_instruction(lang)}
Tu es un expert en gestion de maintenance SAV pour équipements d'imagerie médicale en Tunisie.
Analyse ces données SAV RÉELLES et produis un rapport COMPLET et DÉTAILLÉ.

=== STATISTIQUES GLOBALES ===
- Total interventions : {sav_data.get('nb_total', 0)}
- Clôturées : {sav_data.get('nb_cloturees', 0)}
- En cours : {sav_data.get('nb_en_cours', 0)}
- Taux résolution : {sav_data.get('taux_resolution', 0)}%
- MTTR moyen : {sav_data.get('mttr_h', 0)}h
- Durée totale : {sav_data.get('duree_totale_h', 0)}h

=== RÉPARTITION PAR TYPE ===
- Correctives : {sav_data.get('nb_correctives', 0)}
- Préventives : {sav_data.get('nb_preventives', 0)}  
- Installations : {sav_data.get('nb_installations', 0)}
- Ratio correctif : {sav_data.get('ratio_correctif_pct', 0)}%

=== COÛTS ===
- Coût total interventions : {sav_data.get('cout_interventions', 0)} {sym}
- Coût pièces : {sav_data.get('cout_pieces', 0)} {sym}
- Coût total : {sav_data.get('cout_total', 0)} {sym}
- Coût moyen/intervention : {sav_data.get('cout_moyen', 0)} {sym}

=== PERFORMANCE ÉQUIPE (par technicien) ===
{sav_data.get('tech_details', 'Non disponible')}

=== DÉTAIL DES INTERVENTIONS RÉCENTES ===
{sav_data.get('interventions_detail', 'Non disponible')}

=== MACHINES LES PLUS INTERVENUES ===
{sav_data.get('machines_detail', 'Non disponible')}

=== CLIENTS ===
{sav_data.get('clients_detail', 'Non disponible')}

IMPORTANT: Analyse en profondeur et produis un JSON STRICT avec cette structure exacte :
{{{{
  "analyse": "Résumé exécutif complet de la situation SAV (3-5 phrases détaillées)",
  "score_global": 75,
  "points_forts": [
    "Point fort 1 détaillé avec chiffres",
    "Point fort 2 détaillé avec chiffres",
    "Point fort 3 détaillé avec chiffres"
  ],
  "points_faibles": [
    "Point faible 1 détaillé avec chiffres",
    "Point faible 2 détaillé avec chiffres", 
    "Point faible 3 détaillé avec chiffres"
  ],
  "recommandations": [
    {{{{
      "titre": "Titre recommandation",
      "description": "Description détaillée de l'action à entreprendre",
      "impact": "HAUT"
    }}}},
    {{{{
      "titre": "Titre recommandation 2",
      "description": "Description détaillée",
      "impact": "MOYEN"
    }}}},
    {{{{
      "titre": "Titre recommandation 3",
      "description": "Description détaillée",
      "impact": "BAS"
    }}}}
  ],
  "performance_equipe": [
    {{{{
      "technicien": "Nom",
      "evaluation": "Excellent/Bon/À améliorer",
      "commentaire": "Commentaire détaillé sur ses performances"
    }}}}
  ],
  "analyse_couts": {{{{
    "verdict": "Maîtrisés/Élevés/Critiques",
    "detail": "Analyse détaillée des coûts",
    "economie_possible": "Estimation d'économie possible et comment"
  }}}},
  "tendances": [
    "Tendance 1 observée",
    "Tendance 2 observée",
    "Tendance 3 observée"
  ],
  "priorites_immediates": [
    "Action prioritaire 1",
    "Action prioritaire 2"
  ]
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
    result = clean_json_response(raw)
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    return {"ok": True, "result": result}


# ==========================================
# AI — Analyse des coûts (cartes structurées)
# ==========================================

@app.post("/api/ai/analyze-costs")
def ai_analyze_costs(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager")
    """Analyse IA structurée des coûts clients — retourne des cartes comme le diagnostic IA."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    clients_data = body.get("clients", [])
    kpis = body.get("kpis", {})
    lang = _get_app_language(x_savia_lang, body)
    sym = str(body.get("sym") or "TND").strip() or "TND"
    if not clients_data:
        raise HTTPException(status_code=400, detail="Aucune donnée client.")

    # ── Fetch TCO data server-side ──
    tco_data = []
    try:
        tco_data = finances_tco(client=None, user=user)
    except Exception:
        pass

    # Build compact summary
    avg_cout = sum(c.get('cout_total', 0) for c in clients_data) / max(len(clients_data), 1)
    client_lines = []
    for c in clients_data:
        ecart = round(((c.get('cout_total', 0) - avg_cout) / avg_cout * 100)) if avg_cout > 0 else 0
        nb_interv = c.get('nb_interventions', 0)
        nb_equip = c.get('nb_equipements', 0)
        ratio_interv = round(nb_interv / nb_equip, 1) if nb_equip > 0 else 0
        client_lines.append(
            f"{c.get('client','?')}: "
            f"revenu={c.get('revenu_contrats',0)} {sym}, "
            f"coûts_total={c.get('cout_total',0)} {sym}, "
            f"coût_interventions={c.get('cout_interventions',0)} {sym}, "
            f"coût_pièces={c.get('cout_pieces',0)} {sym}, "
            f"coût_main_oeuvre={c.get('cout_main_oeuvre',0)} {sym}, "
            f"marge={c.get('marge_pct',0)}%, "
            f"interventions={nb_interv} (correctives={c.get('nb_correctives',0)}, préventives={c.get('nb_preventives',0)}), "
            f"equipements={nb_equip}, "
            f"ratio_interv/equip={ratio_interv}, "
            f"ratio_préventif={round(c.get('nb_preventives',0)/nb_interv*100) if nb_interv>0 else 0}%, "
            f"écart_vs_moy={'+' if ecart>0 else ''}{ecart}%"
        )
    summary = "\n".join(client_lines)

    # ── TCO summary (top 15 by cost) ──
    tco_summary = ""
    if tco_data:
        top_tco = sorted(tco_data, key=lambda x: x.get('tco_total', 0), reverse=True)[:15]
        tco_total_global = sum(t.get('tco_total', 0) for t in tco_data)
        tco_lines = []
        for t in top_tco:
            age_ans = round(t.get('age_jours', 0) / 365, 1)
            tco_lines.append(
                f"  {t.get('equipement','?')} ({t.get('client','')}): "
                f"TCO={t.get('tco_total',0)} {sym}, "
                f"pièces={t.get('cout_pieces',0)} {sym}, MO={t.get('cout_main_oeuvre',0)} {sym}, interv={t.get('cout_interventions',0)} {sym}, "
                f"nb_interv={t.get('nb_interventions',0)} (corr={t.get('nb_correctives',0)}/prev={t.get('nb_preventives',0)}), "
                f"âge={age_ans}ans, TCO/mois={t.get('tco_mensuel',0)} {sym}"
            )
        tco_summary = f"""
═══ TCO — TOTAL COST OF OWNERSHIP (Top 15 équipements) ═══
TCO global parc: {round(tco_total_global)} {sym} | Nb équipements: {len(tco_data)} | TCO moyen/équipement: {round(tco_total_global/max(len(tco_data),1))} {sym}
{chr(10).join(tco_lines)}"""

    output_guidance = ""
    if _normalize_lang(lang) == "en":
        output_guidance = f"""
ENGLISH OUTPUT REQUIREMENTS:
- Write every value in natural professional English only.
- Do not use French words or mixed expressions such as Couteux, Coûteux, Identifiees, Identifiées, Proposees, Proposées, Cout, Coût, de Possession, preventif, préventif, pieces, pièces, main d'oeuvre, main d'œuvre, rentables, recommandations, Analyse From, Risk de, Action immédiate, Curatif historique, Préventif proposé, or Cibles.
- Use these English section concepts in the generated text: High-cost clients, Identified causes, Proposed optimizations, TCO analysis - Total Cost of Ownership, High-performing clients, Strategic recommendations.
- Use {sym} as the currency everywhere. Do not write TND unless {sym} is TND.
"""

    prompt = f"""{_ai_language_instruction(lang)}
Tu es un expert en gestion financière de maintenance biomédicale (GMAO). Analyse ces données financières SAVIA en profondeur.

═══ INDICATEURS GLOBAUX ═══
• Coût moyen par client: {round(avg_cout)} {sym}
• Marge globale: {kpis.get('marge_pct',0)}%
• Marge brute: {kpis.get('marge_globale',0)} {sym}
• Revenu total contrats: {kpis.get('revenu_total',0)} {sym}
• Coût total: {kpis.get('cout_total',0)} {sym}
• Clients rentables: {kpis.get('nb_rentables',0)} / {kpis.get('nb_clients',0)}
• Clients déficitaires: {kpis.get('nb_deficitaires',0)}

═══ DONNÉES DÉTAILLÉES PAR CLIENT ═══
{summary}
{tco_summary}
{output_guidance}

═══ CONSIGNES D'ANALYSE ═══
Retourne UNIQUEMENT un JSON valide avec cette structure exacte:
{{
  "clients_couteux": "Pour chaque client dont le coût dépasse la moyenne: nomme-le, donne son écart en % et en {sym} vs la moyenne, son ratio interventions/équipement, la répartition de ses coûts (pièces vs MO vs interventions). Indique le coût par équipement. Utilise • pour chaque client. Sois PRÉCIS avec tous les chiffres.",

  "causes": "Analyse technique des causes racines: taux de maintenance corrective vs préventive par client (un ratio préventif <30% est problématique), coût moyen par intervention, concentration des coûts pièces ou main d'œuvre, équipements vieillissants potentiels, fréquence d'interventions anormale (>4 interv/équipement/an = critique). Utilise • pour chaque cause identifiée avec les chiffres.",

  "optimisations": "Propositions concrètes avec estimation d'impact financier: ex. 'Augmenter le préventif de X à Y% pour [client] → économie estimée de Z {sym}/an', 'Négocier un contrat pièces forfaitaire pour [client]', 'Former les techniciens sur [type d'équipement] pour réduire le taux de rappel'. Chiffre chaque recommandation. Utilise • pour chaque proposition.",

  "clients_performants": "Pour chaque client rentable: nomme-le, donne sa marge en % et {sym}, son ratio préventif/correctif, son coût par équipement. Explique POURQUOI il performe (bon ratio préventif, peu de pannes, contrat bien dimensionné...). Identifie les bonnes pratiques réplicables. Utilise • pour chaque client.",

  "tco_analyse": "Analyse TCO du parc équipement: identifie les 3-5 équipements avec le TCO le plus élevé, calcule le TCO/mois et compare-le à la moyenne du parc. Pour chaque équipement critique: donne le TCO total, la ventilation pièces/MO/interventions, l'âge, le ratio correctif/préventif. Indique si le TCO justifie un remplacement (seuil: TCO > 60% du prix neuf estimé ou TCO/mois en hausse). Propose un plan de renouvellement priorisé. Utilise • pour chaque équipement.",

  "recommandations": "Actions stratégiques prioritaires classées par impact: renégociation tarifaire avec montants suggérés, plan de transition corrective→préventive avec calendrier, optimisation stock pièces de rechange (quelles pièces, quel fournisseur), seuils d'alerte à mettre en place (coût/équipement max, ratio correctif max), KPIs de suivi mensuel à implémenter. Utilise • pour chaque recommandation.",

  "tags": ["3-5 tags pertinents parmi: Surcoût Pièces, Ratio Correctif Élevé, Marge Négative, Contrat Sous-dimensionné, Maintenance Préventive Insuffisante, Optimisation Stock, Renégociation Contrat, Performance Élevée, Équipements Critiques, TCO Élevé, Renouvellement Requis"],
  "confiance": 85
}}

IMPORTANT: Sois un consultant expert. Chaque section doit faire 4-8 lignes avec des données chiffrées précises. Retourne UNIQUEMENT le JSON, rien d'autre."""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
    result = clean_json_response(raw)
    result = _force_ai_payload_language(result, lang, _call_ia, clean_json_response)
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-costs/pdf")
def ai_analyze_costs_pdf(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager")
    """Genere un PDF a partir du resultat d'analyse IA des couts."""
    from io import BytesIO
    from starlette.responses import StreamingResponse
    import base64 as _b64
    import urllib.request as _ur

    data = body.get("result", {})
    kpis = body.get("kpis", {})
    lang = _get_app_language(x_savia_lang, body)
    sym = str(body.get("sym") or "TND").strip() or "TND"
    is_en = _normalize_lang(lang) == "en"
    try:
        from ai_engine import _call_ia, clean_json_response
        data = _force_ai_payload_language(data, lang, _call_ia, clean_json_response)
    except Exception:
        data = _fallback_translate_payload_for_lang(data, lang)
    company_name = body.get("company_name", "")
    company_logo = body.get("company_logo", "")
    if not data:
        raise HTTPException(status_code=400, detail="Aucune donnee d'analyse.")

    SAVIA_LOGO = "/app/logo-savia.png"

    # Client logo
    _client_logo_io = None
    if company_logo:
        try:
            clogo = company_logo.strip()
            if clogo.startswith("data:"):
                _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                _client_logo_io = BytesIO(_b64.b64decode(_b64_part))
            elif clogo.startswith("http"):
                req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                with _ur.urlopen(req_, timeout=6) as _r:
                    _client_logo_io = BytesIO(_r.read())
        except Exception:
            pass

    pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
    pdf.set_header_data(
        SAVIA_LOGO, _client_logo_io,
        company_name if company_name and company_name != "SAVIA" else "",
        "",
        report_title="AI FINANCIAL ANALYSIS" if is_en else "ANALYSE FINANCIERE IA"
    )
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_top_margin(pdf.HEADER_H + 10)
    pdf.add_page()

    # KPIs summary bar
    ky = pdf.get_y() + 2
    pdf.set_fill_color(238, 243, 246)
    pdf.rect(8, ky, pdf.w - 16, 12, 'F')
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(47, 65, 86)
    if is_en:
        kpi_items = [
            f"Revenue: {_fmt_number(kpis.get('revenu_total', 0))} {sym}",
            f"Costs: {_fmt_number(kpis.get('cout_total', 0))} {sym}",
            f"Margin: {kpis.get('marge_pct', 0)}%",
            f"Profitable: {kpis.get('nb_rentables', 0)}/{kpis.get('nb_clients', 0)}",
        ]
    else:
        kpi_items = [
            f"Revenu: {_fmt_number(kpis.get('revenu_total', 0))} {sym}",
            f"Couts: {_fmt_number(kpis.get('cout_total', 0))} {sym}",
            f"Marge: {kpis.get('marge_pct', 0)}%",
            f"Rentables: {kpis.get('nb_rentables', 0)}/{kpis.get('nb_clients', 0)}",
        ]
    pdf.set_xy(10, ky + 2)
    pdf.cell(pdf.w - 20, 8, _sanitize("   |   ".join(kpi_items)), align="C")
    pdf.ln(16)

    # Section card renderer with bullet support
    def render_card(title, content, color_rgb):
        r, g, b = color_rgb
        W = pdf.w - 20  # usable width

        if pdf.get_y() > 250:
            pdf.add_page()

        # Colored section header
        pdf.set_fill_color(r, g, b)
        pdf.rect(10, pdf.get_y(), W, 7, 'F')
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_x(12)
        pdf.cell(W - 4, 7, _sanitize(title.upper()), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(1)

        # Content: split by bullet markers
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(50, 50, 50)
        raw = content or "-"
        bullets = [b.strip() for b in raw.replace('\n', ' ').split(chr(0x2022)) if b.strip()]
        if not bullets:
            bullets = [b.strip() for b in raw.split('\n') if b.strip()]

        for bullet in bullets:
            if not bullet:
                continue
            if pdf.get_y() > 270:
                pdf.add_page()
            cy = pdf.get_y()
            # Small black bullet dot
            pdf.set_fill_color(50, 50, 50)
            pdf.ellipse(12, cy + 1.2, 2, 2, 'F')
            pdf.set_x(16)
            pdf.multi_cell(pdf.w - 28, 4.2, _sanitize(bullet))
            pdf.ln(0.8)

        pdf.ln(3)

    # Render all cards
    cards = [
        (("High-cost Clients" if is_en else "Clients Couteux"), data.get("clients_couteux", ""), (220, 53, 53)),
        (("Identified Causes" if is_en else "Causes Identifiees"), data.get("causes", ""), (234, 88, 12)),
        (("Proposed Optimizations" if is_en else "Optimisations Proposees"), data.get("optimisations", ""), (22, 163, 74)),
        (("TCO Analysis - Total Cost of Ownership" if is_en else "Analyse TCO - Cout Total de Possession"), data.get("tco_analyse", ""), (13, 148, 136)),
        (("High-performing Clients" if is_en else "Clients Performants"), data.get("clients_performants", ""), (37, 99, 235)),
        (("Strategic Recommendations" if is_en else "Recommandations Strategiques"), data.get("recommandations", ""), (124, 58, 237)),
    ]
    for title, content, color in cards:
        render_card(title, content, color)

    # Footer info
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(150, 150, 150)
    generated_at = datetime.now().strftime('%d/%m/%Y a %H:%M')
    footer = (
        f"Generated on {generated_at} | SAVIA Maintenance - Confidential"
        if is_en
        else f"Genere le {generated_at} | SAVIA Maintenance - Confidentiel"
    )
    pdf.cell(0, 4, _sanitize(footer), align="C")

    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=SAVIA_Analyse_Couts_IA.pdf"}
    )


# ==========================================
# AI CHATBOT — Assistant conversationnel
# ==========================================

@app.post("/api/ai/chat")
def ai_chat(body: dict, user: dict = Depends(_verify_token), x_savia_lang: Optional[str] = Header(None)):
    require_roles(user, "Admin", "Manager", "Responsable Technique", "Technicien")
    """Assistant IA conversationnel — répond aux questions en langage naturel sur les données SAVIA."""
    from datetime import date, timedelta
    try:
        from ai_engine import _call_ia, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    message = body.get("message", "").strip()
    history = body.get("history", [])
    lang = _get_app_language(x_savia_lang, body)
    if not message:
        raise HTTPException(status_code=400, detail="Message vide.")

    # ── Aggregate compact data context ──
    today = date.today()
    ctx_parts = []
    try:
        df_interv = lire_interventions()
        if not df_interv.empty:
            total = len(df_interv)
            by_statut = df_interv['statut'].value_counts().to_dict() if 'statut' in df_interv.columns else {}
            by_type = df_interv['type_intervention'].value_counts().head(5).to_dict() if 'type_intervention' in df_interv.columns else {}
            by_tech = df_interv['technicien'].value_counts().head(5).to_dict() if 'technicien' in df_interv.columns else {}
            by_machine = df_interv['machine'].value_counts().head(5).to_dict() if 'machine' in df_interv.columns else {}
            by_client = df_interv['client'].value_counts().head(5).to_dict() if 'client' in df_interv.columns else {}
            # This month
            mois = 0
            if 'date' in df_interv.columns:
                month_str = today.strftime('%Y-%m')
                mois = int(df_interv['date'].astype(str).str[:7].eq(month_str).sum())
            ctx_parts.append(f"INTERVENTIONS: {total} total, {mois} ce mois. Statuts: {by_statut}. Types(top5): {by_type}. Techniciens(top5): {by_tech}. Machines(top5): {by_machine}. Clients(top5): {by_client}.")
    except Exception:
        pass
    try:
        df_equip = lire_equipements()
        if not df_equip.empty:
            n = len(df_equip)
            by_dom = df_equip['domaine'].value_counts().to_dict() if 'domaine' in df_equip.columns else {}
            by_st = df_equip['Statut'].value_counts().to_dict() if 'Statut' in df_equip.columns else {}
            by_cl = df_equip['Client'].value_counts().head(5).to_dict() if 'Client' in df_equip.columns else {}
            ctx_parts.append(f"EQUIPEMENTS: {n} total. Domaines: {by_dom}. Statuts: {by_st}. Clients(top5): {by_cl}.")
    except Exception:
        pass
    try:
        df_pieces = lire_pieces()
        if not df_pieces.empty:
            n = len(df_pieces)
            rupture = []
            if 'stock_actuel' in df_pieces.columns and 'stock_minimum' in df_pieces.columns:
                low = df_pieces[df_pieces['stock_actuel'] <= df_pieces['stock_minimum']]
                rupture = low['nom'].head(5).tolist() if 'nom' in low.columns else []
            ctx_parts.append(f"PIECES: {n} références. En rupture/stock bas: {rupture if rupture else 'aucune'}.")
    except Exception:
        pass
    try:
        df_plan = lire_planning()
        if not df_plan.empty:
            upcoming = df_plan[df_plan['date_prevue'].astype(str).str[:10] >= str(today)]
            n_upcoming = len(upcoming) if not upcoming.empty else 0
            ctx_parts.append(f"PLANNING: {n_upcoming} maintenances à venir.")
    except Exception:
        pass
    try:
        df_contrats = lire_contrats()
        if not df_contrats.empty:
            n = len(df_contrats)
            ctx_parts.append(f"CONTRATS: {n} contrats.")
    except Exception:
        pass

    data_context = "\n".join(ctx_parts) if ctx_parts else "Données non disponibles."

    # ── Build conversation ──
    hist_text = ""
    for h in history[-6:]:
        role = "Utilisateur" if h.get("role") == "user" else "Assistant"
        hist_text += f"{role}: {h.get('content','')}\n"

    prompt = f"""{_ai_language_instruction(lang)}
Tu es SAVIA Assistant, l'assistant IA intelligent de la plateforme SAVIA de gestion de maintenance d'équipements médicaux.

RÔLE: Tu aides les responsables techniques, managers et techniciens à comprendre leurs données, prendre des décisions et obtenir des insights sur leur parc d'équipements.

DONNÉES EN TEMPS RÉEL DE LA PLATEFORME:
{data_context}

DATE DU JOUR: {today.strftime('%d/%m/%Y')}

RÈGLES:
- {"Answer in English, concisely and professionally" if lang == "en" else "Réponds en français, de manière concise et professionnelle"}
- Utilise les données ci-dessus pour répondre avec des chiffres précis
- Si la question ne concerne pas les données, réponds quand même de manière utile (conseils maintenance, bonnes pratiques...)
- Formate ta réponse en texte simple (pas de markdown complexe), utilise des puces • pour les listes
- À la fin de ta réponse, sur une ligne séparée commençant par SUGGESTIONS:, propose 2-3 questions de suivi pertinentes séparées par |

{f"HISTORIQUE DE CONVERSATION:{chr(10)}{hist_text}" if hist_text else ""}

QUESTION DE L'UTILISATEUR: {message}"""

    raw = _call_ia(prompt, timeout=60)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")

    # Parse suggestions from response
    response_text = raw.strip()
    suggestions = []
    if "SUGGESTIONS:" in response_text:
        parts = response_text.split("SUGGESTIONS:")
        response_text = parts[0].strip()
        if len(parts) > 1:
            suggestions = [s.strip() for s in parts[1].strip().split("|") if s.strip()]

    chat_payload = _force_ai_payload_language(
        {"response": response_text, "suggestions": suggestions[:3]},
        lang,
        _call_ia,
        clean_json_response,
    )
    chat_response = chat_payload.get("response", response_text) if isinstance(chat_payload, dict) else response_text
    chat_suggestions = chat_payload.get("suggestions", suggestions[:3]) if isinstance(chat_payload, dict) else suggestions[:3]
    if not isinstance(chat_suggestions, list):
        chat_suggestions = suggestions[:3]
    return {
        "response": chat_response,
        "suggestions": chat_suggestions[:3],
    }


# ==========================================
# ADMIN — Utilisateurs
# ==========================================

__all__ = [
    "analyze_diagnostic",
    "analyze_performance",
    "analyze_pieces",
    "analyze_sav",
    "ai_analyze_costs",
    "ai_analyze_costs_pdf",
    "ai_chat",
]
