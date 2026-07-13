"""Maintenance contract PDF route."""

from api.runtime import (
    Depends,
    HTTPException,
    app,
    datetime,
    get_config,
    get_db,
    lire_contrats,
    lire_equipements,
    logger,
    logging,
)
from api.security import (
    Depends,
    HTTPException,
    _verify_token,
    get_db,
)
from services.scheduled_jobs import (
    get_db,
    lire_contrats,
    lire_equipements,
    logger,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    _verify_token,
    app,
    datetime,
    get_db,
    lire_equipements,
    logger,
)
from controllers.report_helpers import (
    SaviaPDF,
    _sanitize,
)

@app.post("/api/contrats/{contrat_id}/contrat-pdf")
def generate_contrat_pdf(contrat_id: int, body: dict = {}, user: dict = Depends(_verify_token)):
    """Genere un PDF de contrat de maintenance reel (parties, articles, signatures)."""
    from io import BytesIO
    from fastapi.responses import Response
    import base64 as _b64
    import urllib.request as _ur

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        # ── Fetch contract ──
        df_contrats = lire_contrats()
        contrat = None
        if not df_contrats.empty:
            match = df_contrats[df_contrats["id"] == contrat_id]
            if not match.empty:
                contrat = match.iloc[0].to_dict()
        if not contrat:
            raise HTTPException(status_code=404, detail="Contrat non trouve")

        # ── Extract fields ──
        client_name = str(contrat.get("client", "") or "-")
        equipement = str(contrat.get("equipement", "") or "")
        type_contrat = str(contrat.get("type_contrat", "") or "Standard")
        date_debut = str(contrat.get("date_debut", "") or "")[:10]
        date_fin = str(contrat.get("date_fin", "") or "")[:10]
        sla_h = int(contrat.get("sla_temps_reponse_h", 24) or 24)
        montant = float(contrat.get("montant", 0) or 0)
        currency = str(body.get("sym") or body.get("devise") or get_config("devise", "TND") or "TND").strip().upper()
        statut = str(contrat.get("statut", "Actif") or "Actif")
        conditions = str(contrat.get("conditions", "") or "").strip()
        notes = str(contrat.get("notes", "") or "").strip()
        recurrence = str(contrat.get("recurrence_maintenance", "") or "").strip()
        date_premiere_mp = str(contrat.get("date_premiere_maintenance", "") or "")[:10]

        def _fmt_date(s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y") if s else "-"
            except Exception:
                return s or "-"

        date_debut_fr = _fmt_date(date_debut)
        date_fin_fr = _fmt_date(date_fin)
        date_premiere_mp_fr = _fmt_date(date_premiere_mp)

        # Duration in months / years
        duree_str = "-"
        try:
            if date_debut and date_fin:
                d1 = datetime.strptime(date_debut, "%Y-%m-%d")
                d2 = datetime.strptime(date_fin, "%Y-%m-%d")
                months = (d2.year - d1.year) * 12 + (d2.month - d1.month)
                if months >= 12 and months % 12 == 0:
                    yrs = months // 12
                    duree_str = f"{yrs} an{'s' if yrs > 1 else ''}"
                else:
                    duree_str = f"{months} mois"
        except Exception:
            pass

        # ── Client info ──
        client_adresse = ""
        client_ville = ""
        client_telephone = ""
        client_contact = ""
        client_mf = ""
        if client_name and client_name != "-":
            try:
                with get_db() as conn:
                    cl_row = conn.execute(
                        "SELECT ville, adresse, telephone, contact, matricule_fiscale FROM clients WHERE nom = ? LIMIT 1",
                        (client_name,)
                    ).fetchone()
                    if cl_row:
                        d = dict(cl_row)
                        client_ville = d.get("ville", "") or ""
                        client_adresse = d.get("adresse", "") or ""
                        client_telephone = d.get("telephone", "") or ""
                        client_contact = d.get("contact", "") or ""
                        client_mf = d.get("matricule_fiscale", "") or ""
            except Exception as e:
                logger.debug(f"Client lookup failed: {e}")

        # ── Equipment details (optional) ──
        equip_marque = ""
        equip_modele = ""
        equip_serie = ""
        equip_type = ""
        if equipement:
            try:
                df_equip = lire_equipements()
                if not df_equip.empty and "Nom" in df_equip.columns:
                    eq_match = df_equip[df_equip["Nom"].str.strip() == equipement.strip()]
                    if not eq_match.empty:
                        eq = eq_match.iloc[0].to_dict()
                        equip_marque = str(eq.get("Marque", "") or eq.get("marque", "") or "")
                        equip_modele = str(eq.get("Modele", "") or eq.get("modele", "") or "")
                        equip_serie = str(eq.get("NumSerie", "") or eq.get("num_serie", "") or "")
                        equip_type = str(eq.get("Type", "") or eq.get("type", "") or "")
            except Exception as e:
                logger.debug(f"Equipment lookup failed: {e}")

        # ── Company / prestataire info ──
        company_name = body.get("company_name", "SAVIA") or "SAVIA"
        company_logo = body.get("company_logo", "")
        prestataire = company_name if company_name and company_name != "SAVIA" else "SAVIA"

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
            except Exception as _e:
                logger.warning(f"Client logo error: {_e}")

        # ── Build PDF (Portrait A4) ──
        pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
        pdf.set_header_data(
            SAVIA_LOGO, _client_logo_io,
            company_name if company_name != "SAVIA" else "",
            "",
            report_title=f"CONTRAT DE MAINTENANCE N. {contrat_id}"
        )
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.set_top_margin(pdf.HEADER_H + 8)
        pdf.add_page()
        W = pdf.w - 20
        LM = 10

        today_str = datetime.now().strftime("%d/%m/%Y")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 115, 135)
        pdf.cell(W, 5, _sanitize(f"R\u00e9f. : CTR-{contrat_id}-{datetime.now().strftime('%Y')}    |    \u00c9tabli le : {today_str}    |    Statut : {statut}"), align="C")
        pdf.ln(8)

        def section_title(num, label, color=(15, 118, 110)):
            if pdf.get_y() > pdf.h - 35:
                pdf.add_page()
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(*color)
            pdf.cell(W, 6, _sanitize(f"ARTICLE {num} \u2014 {label.upper()}"))
            pdf.ln(6)
            pdf.set_draw_color(*color)
            pdf.set_line_width(0.4)
            pdf.line(LM, pdf.get_y(), pdf.w - LM, pdf.get_y())
            pdf.ln(3)
            pdf.set_text_color(30, 40, 60)
            pdf.set_font("Helvetica", "", 9.5)

        def body_text(txt, indent=0):
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(35, 45, 65)
            pdf.set_x(LM + indent)
            pdf.multi_cell(W - indent, 5.2, _sanitize(txt))
            pdf.ln(1)

        def kv_line(label, value, label_w=55):
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(80, 95, 115)
            pdf.set_x(LM + 4)
            pdf.cell(label_w, 5.5, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(25, 35, 55)
            pdf.multi_cell(W - label_w - 4, 5.5, _sanitize(str(value)))

        # ─── ENTRE LES SOUSSIGNES ───
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W, 7, "ENTRE LES SOUSSIGN\u00c9S", align="C")
        pdf.ln(9)

        # Prestataire box
        y_p = pdf.get_y()
        pdf.set_fill_color(242, 252, 250)
        pdf.set_draw_color(180, 220, 215)
        pdf.set_line_width(0.3)
        prest_h = 26
        pdf.rect(LM, y_p, W, prest_h, style="FD")
        pdf.set_xy(LM + 4, y_p + 2)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W - 8, 5, _sanitize("LE PRESTATAIRE"))
        pdf.set_xy(LM + 4, y_p + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(25, 35, 55)
        pdf.cell(W - 8, 5, _sanitize(prestataire))
        pdf.set_xy(LM + 4, y_p + 14)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(70, 85, 105)
        pdf.multi_cell(W - 8, 4.5, _sanitize(
            "Soci\u00e9t\u00e9 sp\u00e9cialis\u00e9e dans la maintenance d'\u00e9quipements techniques, "
            "agissant en qualit\u00e9 de prestataire de services. Ci-apr\u00e8s d\u00e9nomm\u00e9e \u00ab le Prestataire \u00bb."
        ))

        # Client box
        pdf.set_y(y_p + prest_h + 4)
        y_c = pdf.get_y()
        pdf.set_fill_color(240, 245, 255)
        pdf.set_draw_color(180, 200, 230)
        cli_h = 32
        pdf.rect(LM, y_c, W, cli_h, style="FD")
        pdf.set_xy(LM + 4, y_c + 2)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(30, 80, 170)
        pdf.cell(W - 8, 5, _sanitize("LE CLIENT"))
        pdf.set_xy(LM + 4, y_c + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(25, 35, 55)
        pdf.cell(W - 8, 5, _sanitize(client_name))

        col_left_x = LM + 4
        col_right_x = pdf.w / 2 + 2
        info_y = y_c + 14
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(60, 75, 95)

        left_pairs = [
            ("Adresse", client_adresse or "-"),
            ("Ville", client_ville or "-"),
        ]
        right_pairs = [
            ("T\u00e9l\u00e9phone", client_telephone or "-"),
            ("Contact", client_contact or "-"),
        ]
        for i, (lbl, val) in enumerate(left_pairs):
            pdf.set_xy(col_left_x, info_y + i * 5)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(20, 4.5, _sanitize(lbl + " :"))
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(70, 4.5, _sanitize(str(val))[:50])
        for i, (lbl, val) in enumerate(right_pairs):
            pdf.set_xy(col_right_x, info_y + i * 5)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(20, 4.5, _sanitize(lbl + " :"))
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(70, 4.5, _sanitize(str(val))[:50])

        if client_mf:
            pdf.set_xy(col_left_x, info_y + 10)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(35, 4.5, _sanitize("Matricule fiscale :"))
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(80, 4.5, _sanitize(client_mf)[:50])

        pdf.set_y(y_c + cli_h + 4)
        pdf.set_x(LM)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(70, 85, 105)
        pdf.multi_cell(W, 4.5, _sanitize("Ci-apr\u00e8s d\u00e9nomm\u00e9 \u00ab le Client \u00bb."), align="R")
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W, 6, "IL A \u00c9T\u00c9 CONVENU CE QUI SUIT :", align="C")
        pdf.ln(8)

        # ARTICLE 1 - OBJET
        section_title(1, "Objet du contrat")
        intro_obj = (
            f"Le pr\u00e9sent contrat a pour objet de d\u00e9finir les conditions et modalit\u00e9s dans lesquelles "
            f"le Prestataire assure, au profit du Client, la maintenance de type \u00ab {type_contrat} \u00bb"
        )
        if equipement:
            intro_obj += " portant sur l'\u00e9quipement d\u00e9sign\u00e9 ci-dessous."
        else:
            intro_obj += " sur l'ensemble des \u00e9quipements d\u00e9clar\u00e9s par le Client."
        body_text(intro_obj)

        if equipement:
            pdf.ln(1)
            kv_line("D\u00e9signation", equipement)
            if equip_type:
                kv_line("Type", equip_type)
            if equip_marque or equip_modele:
                kv_line("Marque / Mod\u00e8le", f"{equip_marque} {equip_modele}".strip() or "-")
            if equip_serie:
                kv_line("N\u00b0 de s\u00e9rie", equip_serie)
        pdf.ln(3)

        # ARTICLE 2 - DUREE
        section_title(2, "Dur\u00e9e du contrat")
        body_text(
            f"Le pr\u00e9sent contrat est conclu pour une dur\u00e9e de {duree_str}, "
            f"prenant effet le {date_debut_fr} et expirant le {date_fin_fr}. "
            f"Au-del\u00e0 de ce terme, toute reconduction fera l'objet d'un avenant \u00e9crit entre les parties."
        )

        # ARTICLE 3 - PRESTATIONS
        section_title(3, "Nature des prestations")
        type_lower = type_contrat.lower()
        prest_desc = []
        if "pr\u00e9ventive" in type_lower or "preventive" in type_lower:
            prest_desc = [
                "Visites de maintenance pr\u00e9ventive planifi\u00e9es selon le calendrier convenu.",
                "Contr\u00f4le visuel et fonctionnel des composants critiques.",
                "Nettoyage, lubrification et r\u00e9glages selon recommandations du constructeur.",
                "R\u00e9daction d'un rapport d'intervention apr\u00e8s chaque visite.",
            ]
        elif "corrective" in type_lower:
            prest_desc = [
                "Intervention sur site en cas de panne ou dysfonctionnement signal\u00e9 par le Client.",
                "Diagnostic, r\u00e9paration et remise en service de l'\u00e9quipement.",
                "Fourniture et remplacement des pi\u00e8ces d\u00e9fectueuses (selon Article 6).",
                "Remise d'un rapport d'intervention d\u00e9taill\u00e9 apr\u00e8s chaque op\u00e9ration.",
            ]
        elif "full" in type_lower:
            prest_desc = [
                "Maintenance pr\u00e9ventive p\u00e9riodique programm\u00e9e.",
                "Maintenance corrective illimit\u00e9e (interventions sur panne).",
                "Fourniture et remplacement des pi\u00e8ces d\u00e9tach\u00e9es selon Article 6.",
                "Main d'\u0153uvre et frais de d\u00e9placement inclus.",
                "Support technique distance disponible aux heures ouvr\u00e9es.",
            ]
        elif "premium" in type_lower:
            prest_desc = [
                "Maintenance pr\u00e9ventive et corrective illimit\u00e9e.",
                "Pi\u00e8ces d\u00e9tach\u00e9es et main d'\u0153uvre incluses.",
                "Support technique prioritaire 24h/24, 7j/7.",
                "Reporting mensuel d\u00e9taill\u00e9 sur l'\u00e9tat du parc.",
                "Acc\u00e8s prioritaire aux mises \u00e0 jour techniques.",
            ]
        elif "main" in type_lower and "uvre" in type_lower:
            prest_desc = [
                "Main d'\u0153uvre des techniciens lors des interventions.",
                "D\u00e9placements sur site dans la zone de couverture.",
                "Diagnostic et r\u00e9parations (hors fourniture de pi\u00e8ces).",
                "Les pi\u00e8ces d\u00e9tach\u00e9es restent \u00e0 la charge du Client.",
            ]
        else:
            prest_desc = [
                "Maintenance pr\u00e9ventive et corrective de l'\u00e9quipement d\u00e9sign\u00e9.",
                "Diagnostic, r\u00e9paration et remise en service en cas de panne.",
                "R\u00e9daction d'un rapport apr\u00e8s chaque intervention.",
                "Conseil et support technique pendant les heures ouvr\u00e9es.",
            ]
        for it in prest_desc:
            pdf.set_x(LM + 4)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(35, 45, 65)
            pdf.cell(4, 5.2, "-")
            pdf.multi_cell(W - 8, 5.2, _sanitize(it))
        pdf.ln(2)

        # ARTICLE 4 - SLA
        section_title(4, "Engagements de service (SLA)")
        body_text(
            f"Le Prestataire s'engage \u00e0 intervenir dans un d\u00e9lai maximum de {sla_h} heure(s) "
            f"\u00e0 compter de la r\u00e9ception de la demande d'intervention par le Client, durant les heures "
            f"ouvr\u00e9es (du lundi au vendredi, 8h\u201318h). Pour les interventions hors plages ouvr\u00e9es, "
            f"un d\u00e9lai compl\u00e9mentaire pourra s'appliquer."
        )

        # ARTICLE 5 - PLANNING (optionnel)
        if recurrence:
            section_title(5, "Planning des maintenances pr\u00e9ventives")
            body_text(
                f"Les visites de maintenance pr\u00e9ventive sont planifi\u00e9es selon une fr\u00e9quence "
                f"{recurrence.lower()}. La premi\u00e8re visite est pr\u00e9vue le {date_premiere_mp_fr}. "
                f"Les visites suivantes seront communiqu\u00e9es au Client au moins deux (2) semaines \u00e0 l'avance "
                f"par notification \u00e9crite (e-mail ou SMS)."
            )
            article_n = 6
        else:
            article_n = 5

        # ARTICLE - MONTANT
        section_title(article_n, "Montant et modalit\u00e9s de paiement")
        body_text(
            "En contrepartie des prestations d\u00e9finies au pr\u00e9sent contrat, le Client s'engage "
            "\u00e0 verser au Prestataire la somme annuelle de "
        )
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 118, 110)
        pdf.set_x(LM + 4)
        pdf.cell(W - 4, 7, _sanitize(f"{montant:,.3f} {currency}".replace(",", " ")))
        pdf.ln(8)
        pdf.set_text_color(35, 45, 65)
        body_text(
            "hors taxes, payable selon les modalit\u00e9s convenues entre les parties (annuelle, "
            "trimestrielle ou mensuelle). Tout retard de paiement sup\u00e9rieur \u00e0 trente (30) jours "
            "pourra entra\u00eener la suspension des prestations apr\u00e8s mise en demeure rest\u00e9e infructueuse."
        )
        article_n += 1

        # ARTICLE - CONDITIONS PARTICULIERES
        if conditions:
            section_title(article_n, "Conditions particuli\u00e8res")
            body_text(conditions)
            article_n += 1

        # ARTICLE - OBLIGATIONS DU CLIENT
        section_title(article_n, "Obligations du Client")
        for it in [
            "Permettre l'acc\u00e8s libre aux \u00e9quipements lors des interventions programm\u00e9es.",
            "Signaler dans les meilleurs d\u00e9lais tout dysfonctionnement constat\u00e9.",
            "Ne pas faire intervenir de tiers non agr\u00e9\u00e9 sur les \u00e9quipements couverts.",
            "Utiliser les \u00e9quipements conform\u00e9ment aux pr\u00e9conisations du constructeur.",
            "R\u00e9gler les sommes dues aux \u00e9ch\u00e9ances convenues.",
        ]:
            pdf.set_x(LM + 4)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(35, 45, 65)
            pdf.cell(4, 5.2, "-")
            pdf.multi_cell(W - 8, 5.2, _sanitize(it))
        pdf.ln(2)
        article_n += 1

        # ARTICLE - RESILIATION
        section_title(article_n, "R\u00e9siliation")
        body_text(
            "Le pr\u00e9sent contrat pourra \u00eatre r\u00e9sili\u00e9 par l'une ou l'autre des parties, "
            "moyennant un pr\u00e9avis \u00e9crit de soixante (60) jours adress\u00e9 par lettre recommand\u00e9e "
            "avec accus\u00e9 de r\u00e9ception. En cas de manquement grave et persistant aux obligations "
            "contractuelles, la r\u00e9siliation pourra intervenir de plein droit apr\u00e8s mise en demeure "
            "rest\u00e9e sans effet pendant trente (30) jours."
        )
        article_n += 1

        # ARTICLE - LITIGES
        section_title(article_n, "Loi applicable et juridiction comp\u00e9tente")
        body_text(
            "Le pr\u00e9sent contrat est soumis au droit tunisien. Tout litige relatif \u00e0 son interpr\u00e9tation "
            "ou \u00e0 son ex\u00e9cution sera soumis, \u00e0 d\u00e9faut de r\u00e8glement amiable, aux tribunaux "
            "comp\u00e9tents du si\u00e8ge social du Prestataire."
        )

        # NOTES (optionnel)
        if notes:
            pdf.ln(2)
            pdf.set_font("Helvetica", "BI", 9)
            pdf.set_text_color(110, 95, 30)
            pdf.set_x(LM)
            pdf.cell(W, 5, _sanitize("Notes compl\u00e9mentaires :"))
            pdf.ln(5)
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(80, 90, 110)
            pdf.set_x(LM + 4)
            pdf.multi_cell(W - 4, 4.8, _sanitize(notes))
            pdf.ln(2)

        # ─── SIGNATURES ───
        if pdf.get_y() > pdf.h - 70:
            pdf.add_page()
        else:
            pdf.ln(6)

        pdf.set_draw_color(15, 118, 110)
        pdf.set_line_width(0.5)
        pdf.line(LM, pdf.get_y(), pdf.w - LM, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W, 6, _sanitize(f"Fait \u00e0 {client_ville or '-'}, le {today_str}, en deux exemplaires originaux."))
        pdf.ln(8)

        sig_y = pdf.get_y()
        col1_x = LM + 4
        col2_x = pdf.w / 2 + 5
        box_w = (pdf.w / 2) - 14
        box_h = 38

        pdf.set_xy(col1_x, sig_y)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(box_w, 5, _sanitize(f"Pour le Prestataire ({prestataire})"))
        pdf.set_xy(col1_x, sig_y + 6)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(80, 95, 115)
        pdf.cell(box_w, 4.5, "Nom, qualit\u00e9, signature et cachet :")
        pdf.set_draw_color(180, 195, 215)
        pdf.set_line_width(0.3)
        pdf.rect(col1_x, sig_y + 11, box_w, box_h - 11, style="D")

        client_short = client_name[:35] + ("..." if len(client_name) > 35 else "")
        pdf.set_xy(col2_x, sig_y)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(30, 80, 170)
        pdf.cell(box_w, 5, _sanitize(f"Pour le Client ({client_short})"))
        pdf.set_xy(col2_x, sig_y + 6)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(80, 95, 115)
        pdf.cell(box_w, 4.5, "Nom, qualit\u00e9, signature et cachet :")
        pdf.rect(col2_x, sig_y + 11, box_w, box_h - 11, style="D")

        # ─── FOOTER ───
        pdf.set_auto_page_break(auto=False)
        total_pages = len(pdf.pages)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        for pg in range(1, total_pages + 1):
            pdf.page = pg
            pdf.set_xy(LM, pdf.h - 11)
            pdf.set_draw_color(200, 205, 220)
            pdf.set_line_width(0.3)
            pdf.line(LM, pdf.h - 11, pdf.w - LM, pdf.h - 11)
            pdf.set_xy(LM, pdf.h - 9)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(160, 170, 190)
            pdf.cell(pdf.w - 40, 5, _sanitize(f"Contrat #{contrat_id} - G\u00e9n\u00e9r\u00e9 par {prestataire} le {now_str}"), align="L")
            pdf.cell(30, 5, f"Page {pg} / {total_pages}", align="R")

        pdf_bytes = bytes(pdf.output())
        import urllib.parse as _up, unicodedata as _ud
        _fn = f"contrat_maintenance_{contrat_id}_{client_name.replace(' ', '_')}"
        _ascii = _ud.normalize("NFKD", _fn).encode("ascii", "ignore").decode()
        _ascii = "".join(c if c.isalnum() or c in "._-" else "_" for c in _ascii).strip("_") or f"contrat_{contrat_id}"
        _utf8 = _up.quote(_fn + ".pdf", safe="")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={_ascii}.pdf; filename*=UTF-8''{_utf8}",
                "Content-Length": str(len(pdf_bytes)),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Contrat PDF error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# ==========================================
# FINANCES — Rentabilite & TCO
# ==========================================

__all__ = [
    "generate_contrat_pdf",
]

