"""Equipment attestation PDF route."""

from api.runtime import (
    Depends,
    HTTPException,
    app,
    datetime,
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
    assert_resource_client_access,
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

@app.post("/api/equipements/{equip_id}/attestation-pdf")
def generate_attestation_pdf(equip_id: int, body: dict = {}, user: dict = Depends(_verify_token)):
    """Generate an 'Attestation de Bon Fonctionnement' PDF for an operational equipment."""
    with get_db() as conn:
        assert_resource_client_access(conn, "equipement", equip_id, user)
    from io import BytesIO
    from fastapi.responses import Response

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        df_equip = lire_equipements()
        equip = None
        if not df_equip.empty:
            match = df_equip[df_equip["id"] == equip_id]
            if not match.empty:
                equip = match.iloc[0].to_dict()
        if not equip:
            raise HTTPException(status_code=404, detail="Equipement non trouve")

        nom = str(equip.get("Nom", "") or equip.get("nom", "") or "-")
        client_name = str(equip.get("Client", "") or equip.get("client", "") or "-")
        num_serie = str(equip.get("NumSerie", "") or equip.get("num_serie", "") or "-")
        marque = str(equip.get("Marque", "") or equip.get("marque", "") or "-")
        modele = str(equip.get("Modele", "") or equip.get("modele", "") or "-")
        equip_type = str(equip.get("Type", "") or equip.get("type", "") or "-")
        localisation = str(equip.get("Localisation", "") or equip.get("localisation", "") or "-")
        date_installation = str(equip.get("DateInstallation", "") or equip.get("date_installation", "") or "")[:10]
        statut = str(equip.get("Statut", "") or equip.get("statut", "") or "-")

        # Fetch client info
        client_region = ""
        client_ville = ""
        client_adresse = ""
        client_telephone = ""
        if client_name and client_name != "-":
            try:
                with get_db() as conn:
                    cl_row = conn.execute("SELECT region, ville, adresse, telephone FROM clients WHERE nom = %s LIMIT 1", (client_name,)).fetchone()
                    if cl_row:
                        d = dict(cl_row)
                        client_region = d.get("region", "") or ""
                        client_ville = d.get("ville", "") or ""
                        client_adresse = d.get("adresse", "") or ""
                        client_telephone = d.get("telephone", "") or ""
            except Exception:
                pass

        # Warranty check
        sous_garantie = False
        garantie_fin_str = ""
        g_debut = equip.get("garantie_debut", "")
        g_duree = int(equip.get("garantie_duree", 0) or 0)
        if g_debut and g_duree:
            try:
                fin = datetime.strptime(str(g_debut)[:10], "%Y-%m-%d")
                fin = fin.replace(year=fin.year + g_duree)
                sous_garantie = fin > datetime.now()
                garantie_fin_str = fin.strftime("%d/%m/%Y")
            except Exception:
                pass

        # Contract check
        sous_contrat = False
        if client_name and client_name != "-":
            df_contrats = lire_contrats()
            if not df_contrats.empty:
                ccol = "client" if "client" in df_contrats.columns else "Client"
                if ccol in df_contrats.columns:
                    cc = df_contrats[df_contrats[ccol].str.strip().str.lower() == client_name.lower()]
                    if not cc.empty:
                        for _, c in cc.iterrows():
                            fin_str = c.get("date_fin", c.get("DateFin", ""))
                            if not fin_str:
                                sous_contrat = True
                                break
                            try:
                                if datetime.strptime(str(fin_str)[:10], "%Y-%m-%d") > datetime.now():
                                    sous_contrat = True
                                    break
                            except Exception:
                                sous_contrat = True
                                break

        # Company info from admin settings
        company_name = body.get("company_name", "SAVIA")
        company_logo = body.get("company_logo", "")
        import base64 as _b64
        import urllib.request as _ur
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

        # Build PDF
        pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
        pdf.set_header_data(
            SAVIA_LOGO, _client_logo_io,
            company_name if company_name != "SAVIA" else "",
            "",
            report_title="ATTESTATION DE BON FONCTIONNEMENT"
        )
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_top_margin(pdf.HEADER_H + 10)
        pdf.add_page()
        W = pdf.w - 20

        today_str = datetime.now().strftime("%d/%m/%Y")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 120, 140)
        pdf.cell(W, 5, _sanitize(f"Date : {today_str}    |    R\u00e9f : ATT-{equip_id}-{datetime.now().strftime('%Y%m%d')}"), align="C")
        pdf.ln(10)

        # Introduction
        display_name = company_name if company_name and company_name != "SAVIA" else "SAVIA"
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 40, 60)
        pdf.multi_cell(W, 6, _sanitize(
            f"La soci\u00e9t\u00e9 {display_name} atteste par la pr\u00e9sente que l'\u00e9quipement ci-dessous, "
            f"install\u00e9 chez le client {client_name}, est en parfait \u00e9tat de fonctionnement "
            f"\u00e0 la date du {today_str}."
        ), align="L")
        pdf.ln(6)

        # ── SECTION: EQUIPEMENT ──
        y0 = pdf.get_y()
        pdf.set_fill_color(242, 252, 250)
        pdf.set_draw_color(180, 220, 215)
        pdf.set_line_width(0.3)
        box_h = 52
        pdf.rect(10, y0, W, box_h, style="FD")
        pdf.set_xy(14, y0 + 2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W - 8, 6, _sanitize("INFORMATIONS \u00c9QUIPEMENT"))
        pdf.set_text_color(30, 40, 60)
        left_x = 14
        right_x = pdf.w / 2 + 5
        row_h = 7

        for i, (label, value) in enumerate([
            ("\u00c9quipement", _sanitize(nom)),
            ("Type", _sanitize(equip_type)),
            ("Marque / Mod\u00e8le", _sanitize(f"{marque} {modele}".strip())),
            ("N\u00b0 de s\u00e9rie", _sanitize(num_serie)),
            ("Localisation", _sanitize(localisation)),
        ]):
            pdf.set_xy(left_x, y0 + 9 + i * row_h)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(30, row_h, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(55, row_h, value[:40])

        for i, (label, value, color) in enumerate([
            ("Date installation", date_installation or "-", (30, 40, 60)),
            ("Statut", _sanitize(statut), (22, 163, 74)),
            ("Sous garantie", "Oui" if sous_garantie else "Non", (22, 163, 74) if sous_garantie else (200, 50, 50)),
            ("Sous contrat", "Oui" if sous_contrat else "Non", (22, 163, 74) if sous_contrat else (200, 50, 50)),
        ]):
            pdf.set_xy(right_x, y0 + 9 + i * row_h)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(30, 40, 60)
            pdf.cell(28, row_h, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(*color)
            pdf.cell(40, row_h, value[:35])
        pdf.set_text_color(30, 40, 60)

        # ── SECTION: CLIENT ──
        pdf.set_y(y0 + box_h + 6)
        y1 = pdf.get_y()
        pdf.set_fill_color(240, 245, 255)
        pdf.set_draw_color(180, 200, 230)
        client_box_h = 38
        pdf.rect(10, y1, W, client_box_h, style="FD")
        pdf.set_xy(14, y1 + 2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(30, 80, 170)
        pdf.cell(W - 8, 6, "INFORMATIONS CLIENT")
        pdf.set_text_color(30, 40, 60)

        for i, (label, value) in enumerate([
            ("Client", _sanitize(client_name)),
            ("R\u00e9gion / Ville", _sanitize(f"{client_region} - {client_ville}".strip(" -") or "-")),
            ("Adresse", _sanitize(client_adresse or "-")),
            ("T\u00e9l\u00e9phone", _sanitize(client_telephone or "-")),
        ]):
            pdf.set_xy(left_x, y1 + 9 + i * row_h)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(30, row_h, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(130, row_h, value[:70])

        # ── DECLARATION ──
        pdf.set_y(y1 + client_box_h + 8)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 40, 60)
        pdf.multi_cell(W, 6, _sanitize(
            "Nous attestons que l'\u00e9quipement susmentionn\u00e9 a \u00e9t\u00e9 v\u00e9rifi\u00e9 et test\u00e9 par nos techniciens qualifi\u00e9s. "
            "Tous les param\u00e8tres de fonctionnement sont conformes aux sp\u00e9cifications du fabricant. "
            "L'\u00e9quipement est apte \u00e0 une utilisation normale dans le cadre de ses fonctions d\u00e9sign\u00e9es."
        ), align="L")
        pdf.ln(4)

        if sous_garantie and garantie_fin_str:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(22, 163, 74)
            pdf.cell(W, 6, _sanitize(f"Cet \u00e9quipement est sous garantie jusqu'au {garantie_fin_str}."), align="L")
            pdf.ln(8)
            pdf.set_text_color(30, 40, 60)

        # ── SIGNATURES ──
        pdf.ln(6)
        y_sig = pdf.get_y()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(80, 90, 110)
        pdf.set_xy(14, y_sig)
        pdf.cell(80, 6, _sanitize(f"Pour {display_name} :"))
        pdf.set_xy(14, y_sig + 8)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(80, 5, "Nom et signature :")
        pdf.set_draw_color(180, 180, 200)
        pdf.line(14, y_sig + 30, 90, y_sig + 30)

        pdf.set_xy(right_x, y_sig)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(80, 6, _sanitize(f"Pour le client ({client_name[:30]}) :"))
        pdf.set_xy(right_x, y_sig + 8)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(80, 5, "Nom, signature et cachet :")
        pdf.line(right_x, y_sig + 30, right_x + 76, y_sig + 30)

        # Footer
        pdf.set_y(-30)
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(140, 150, 165)
        pdf.cell(W, 4, _sanitize(f"Ce document est g\u00e9n\u00e9r\u00e9 automatiquement par {display_name} - {today_str}"), align="C")

        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=attestation_bon_fonctionnement_{equip_id}.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Attestation PDF error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# ==========================================
# PDF CONTRAT DE MAINTENANCE (document juridique)
# ==========================================

__all__ = [
    "generate_attestation_pdf",
]
