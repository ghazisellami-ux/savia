import re

with open(r'c:\Users\ACER\.gemini\antigravity\scratch\sic_radiology\sic_radiology\main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the function to replace
old_func_start = '@app.post("/api/ai/analyze-performance")\ndef analyze_performance'
old_func_end = '    return {"ok": True, "result": result}\n'

# Find start position
start_idx = content.find(old_func_start)
if start_idx == -1:
    # Try with \r\n
    old_func_start = old_func_start.replace('\n', '\r\n')
    start_idx = content.find(old_func_start)

if start_idx == -1:
    print("ERROR: Could not find function start")
    exit(1)

# Find end position (the return statement after the function)
end_pattern = '    return {"ok": True, "result": result}'
end_idx = content.find(end_pattern, start_idx)
if end_idx == -1:
    print("ERROR: Could not find function end")
    exit(1)

# Include the return line and the newline after it
end_idx = content.find('\n', end_idx) + 1

print(f"Found function at positions {start_idx}-{end_idx}")
print(f"Replacing {end_idx - start_idx} characters")

new_func = '''@app.post("/api/ai/analyze-performance")
def analyze_performance(body: dict, user: dict = Depends(_verify_token)):
    """Calls Gemini to produce a detailed predictive maintenance report (v2)."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    kpis = body.get("kpis", {})
    sym = body.get("sym", "TND")

    # --- Fetch real per-machine data from DB ---
    machine_details = ""
    equip_detail = ""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT machine, COUNT(*) as nb, "
                "SUM(CASE WHEN type_intervention='Corrective' THEN 1 ELSE 0 END) as corr, "
                "SUM(CASE WHEN type_intervention ILIKE '%%r\\u00e9ventive%%' THEN 1 ELSE 0 END) as prev, "
                "ROUND(AVG(duree_minutes)::numeric,1) as mttr_m, "
                "ROUND(SUM(cout)::numeric,0) as cout "
                "FROM interventions GROUP BY machine ORDER BY nb DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                machine_details += f"  - {r['machine']}: {r['nb']} int ({r['corr']} corr, {r['prev']} prev), MTTR={r['mttr_m']}min, co\\u00fbt={r['cout']} {sym}\\n"
            eqs = conn.execute('SELECT "Nom","Client","Type","Statut","DateInstallation" FROM equipements ORDER BY "Nom" LIMIT 25').fetchall()
            for eq in eqs:
                equip_detail += f"  - {eq['Nom']} ({eq.get('Type','?')}) — {eq.get('Client','?')}, install\\u00e9: {eq.get('DateInstallation','?')}, statut: {eq.get('Statut','?')}\\n"
    except Exception as db_err:
        logger.warning(f"DB fetch for AI failed: {db_err}")

    risk_detail = ""
    for r in kpis.get("top_risques", []):
        risk_detail += f"  - {r.get('machine','?')}: risque={r.get('risque_panne_pct',0)}%, pi\\u00e8ce={r.get('composant_a_risque','?')}, panne_dans={r.get('jours_avant_panne','?')}j, sant\\u00e9={r.get('score_sante',0)}%\\n"

    import datetime
    today = datetime.date.today()

    prompt = f"""Tu es Directeur du Service Technique d'une entreprise de maintenance d'\\u00e9quipements d'imagerie m\\u00e9dicale en Tunisie.
Analyse ces donn\\u00e9es R\\u00c9ELLES et produis un rapport pr\\u00e9dictif d\\u00e9taill\\u00e9.

=== CHIFFRES DU PARC ===
- \\u00c9quipements : {kpis.get('nb_equipements', 0)} | Interventions : {kpis.get('nb_interventions', 0)}
- Correctives : {kpis.get('interventions_correctives', 0)} | Pr\\u00e9ventives : {kpis.get('interventions_preventives', 0)} | Calibrations : {kpis.get('interventions_calibration', 0)}
- Disponibilit\\u00e9 : {kpis.get('disponibilite', 0)}% | MTBF : {kpis.get('mtbf', 0)}h | MTTR : {kpis.get('mttr', 0)}h
- Co\\u00fbt total : {kpis.get('cout_total', 0)} {sym}

=== HISTORIQUE PAR MACHINE ===
{machine_details if machine_details else 'Non disponible'}

=== PR\\u00c9DICTIONS IA ===
{risk_detail if risk_detail else 'Aucune'}

=== \\u00c9QUIPEMENTS ===
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
      "action_immediate": "Action + pi\\u00e8ces"
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
    "detail_preventif": "D\\u00e9tail calcul",
    "gain_potentiel": 0,
    "ratio": "Pour 1 TND investi, X TND \\u00e9conomis\\u00e9s"
  }}}},
  "tendances": ["Tendance 1", "Tendance 2", "Tendance 3"],
  "conclusion": "Priorit\\u00e9 absolue \\u00e0..."
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas r\\u00e9pondu.")
    result = clean_json_response(raw)
    return {"ok": True, "result": result}
'''

content = content[:start_idx] + new_func + content[end_idx:]

with open(r'c:\Users\ACER\.gemini\antigravity\scratch\sic_radiology\sic_radiology\main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("SUCCESS: Function replaced!")
