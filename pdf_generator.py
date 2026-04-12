# ==========================================
# 📄 GENERATEUR DE RAPPORTS PDF
# ==========================================
"""
Génère des rapports d'intervention en PDF avec fpdf2.
"""
from fpdf import FPDF
from datetime import datetime
from io import BytesIO


class RapportInterventionPDF(FPDF):
    """PDF personnalisé pour les rapports d'intervention SIC Radiologie."""

    def __init__(self, devise="EUR"):
        super().__init__()
        self.devise = devise
        self.symboles = {
            "EUR": "EUR", "USD": "USD", "GBP": "GBP", "TND": "TND",
            "MAD": "MAD", "DZD": "DZD", "XOF": "XOF", "CHF": "CHF",
            "CAD": "CAD", "SAR": "SAR", "AED": "AED",
        }
        # Logos
        import os
        from config import BASE_DIR
        from db_engine import get_config
        self.org_name = get_config("nom_organisation", "SIC Radiologie")
        self.savia_logo = os.path.join(BASE_DIR, "assets", "logo_savia.png")
        self.client_logo = get_config("logo_path", "")

    def header(self):
        import os
        # Logo SAVIA en haut à gauche
        if os.path.exists(self.savia_logo):
            try:
                self.image(self.savia_logo, 10, 8, 35)
            except Exception:
                pass
        # Logo client en haut à droite
        if self.client_logo and os.path.exists(self.client_logo):
            try:
                self.image(self.client_logo, 170, 8, 25)
            except Exception:
                pass
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
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} - SIC Radiologie - {datetime.now().strftime('%d/%m/%Y')}",
                  align="C")

    def _section_title(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(30, 58, 138)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, f"  {title}", fill=True)
        self.ln(8)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def _row(self, label, value):
        self.set_font("Helvetica", "B", 10)
        self.cell(55, 7, label, border=0)
        self.set_font("Helvetica", "", 10)
        # Sanitize value
        safe_val = str(value).encode('latin-1', 'replace').decode('latin-1')
        self.cell(0, 7, safe_val, border=0)
        self.ln(7)

    def _format_devise(self, montant):
        sym = self.symboles.get(self.devise, self.devise)
        try:
            val = float(montant)
            return f"{val:,.0f}".replace(",", " ") + f" {sym}"
        except (ValueError, TypeError):
            return f"0 {sym}"


def generer_pdf_intervention(intervention: dict, devise: str = "EUR") -> bytes:
    """
    Genere un rapport PDF pour une intervention.

    Args:
        intervention: dict avec les champs de l'intervention
        devise: code devise (EUR, USD, TND, etc.)

    Returns:
        bytes du PDF
    """
    pdf = RapportInterventionPDF(devise=devise)
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- Titre ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 10, "RAPPORT D'INTERVENTION", align="C")
    pdf.ln(10)
    pdf.ln(4)

    # --- Informations generales ---
    pdf._section_title("Informations Generales")
    pdf._row("Date :", intervention.get("date", "N/A"))
    pdf._row("Machine :", intervention.get("machine", "N/A"))
    pdf._row("Technicien :", intervention.get("technicien", "N/A"))
    pdf._row("Type :", intervention.get("type_intervention", "N/A"))
    pdf._row("Statut :", intervention.get("statut", "N/A"))
    pdf._row("Code erreur :", intervention.get("code_erreur", "-"))
    pdf.ln(4)

    # --- Client (extrait des notes) ---
    notes = str(intervention.get("notes", ""))
    client = ""
    if notes.startswith("[") and "]" in notes:
        client = notes[1:notes.index("]")]
    if client:
        pdf._section_title("Client")
        pdf._row("Etablissement :", client)
        pdf.ln(4)

    # --- Description ---
    pdf._section_title("Description de l'intervention")
    pdf.set_font("Helvetica", "", 10)
    desc = str(intervention.get("description", "Aucune description"))
    safe_desc = desc.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 6, safe_desc)
    pdf.ln(4)

    # --- Diagnostic ---
    probleme = intervention.get("probleme", "")
    cause = intervention.get("cause", "")
    solution = intervention.get("solution", "")
    if any([probleme, cause, solution]):
        pdf._section_title("Diagnostic")
        if probleme:
            pdf._row("Probleme :", probleme)
        if cause:
            pdf._row("Cause :", cause)
        if solution:
            pdf._row("Solution :", solution)
        pdf.ln(4)

    # --- Durees & Pieces ---
    pdf._section_title("Durees & Pieces")
    pdf._row("Duree intervention :", f"{(intervention.get('duree_minutes', 0) or 0) / 60:.1f} heures")
    pdf._row("Duree deplacement :", f"{(intervention.get('deplacement_minutes', 0) or 0) / 60:.1f} heures")
    pieces = intervention.get("pieces_utilisees", "")
    if pieces:
        pdf._row("Pieces utilisees :", pieces)
    pdf.ln(4)

    # Notes supprimees du rapport (informations internes)

    # --- Signature ---
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 7, "Signature Technicien :", border=0)
    pdf.cell(95, 7, "Signature Responsable :", border=0)
    pdf.ln(22)
    pdf.cell(95, 0, "", border="T")
    pdf.cell(95, 0, "", border="T")
    pdf.ln(5)

    return bytes(pdf.output())


def _safe(text):
    """Encode text for PDF (latin-1 safe)."""
    return str(text).encode('latin-1', 'replace').decode('latin-1')


def _table_header(pdf, cols, widths):
    """Draw a table header row."""
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(30, 58, 138)
    for i, col in enumerate(cols):
        pdf.cell(widths[i], 7, _safe(col), border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_text_color(0, 0, 0)


def _table_row(pdf, values, widths, fill=False):
    """Draw a table data row."""
    pdf.set_font("Helvetica", "", 7)
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(0, 0, 0)
    for i, val in enumerate(values):
        pdf.cell(widths[i], 6, _safe(val), border=1, fill=True, align="C")
    pdf.ln()


def generer_pdf_rapport_client(client, mois, annee, df_interventions,
                                revenu_contrat, cout_interventions,
                                cout_pieces, marge, devise="EUR"):
    """
    Genere un rapport PDF client mensuel avec entete SAVIA.

    Returns: bytes du PDF
    """
    pdf = RapportInterventionPDF(devise=devise)
    pdf.alias_nb_pages()
    pdf.add_page()

    # --- Titre ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 10, "RAPPORT CLIENT MENSUEL", align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, f"{_safe(client)} - {mois:02d}/{annee}", align="C")
    pdf.ln(7)
    pdf.ln(4)

    # --- Synthese Financiere ---
    pdf._section_title("Synthese Financiere")
    cout_total = cout_interventions + cout_pieces
    pdf._row("Revenu Contrat :", pdf._format_devise(revenu_contrat))
    pdf._row("Cout Interventions :", pdf._format_devise(cout_interventions))
    pdf._row("Cout Pieces :", pdf._format_devise(cout_pieces))
    pdf._row("Depenses Totales :", pdf._format_devise(cout_total))
    pdf._row("Marge Nette :", pdf._format_devise(marge))
    pdf.ln(4)

    # --- Resume ---
    pdf._section_title("Resume des Interventions")
    nb_inter = len(df_interventions)
    duree_totale = df_interventions["duree_minutes"].sum() if "duree_minutes" in df_interventions.columns else 0
    pdf._row("Nombre d'interventions :", str(nb_inter))
    pdf._row("Duree totale :", f"{(duree_totale or 0) / 60:.1f} heures")
    pdf.ln(4)

    # --- Tableau des interventions ---
    if not df_interventions.empty:
        pdf._section_title("Detail des Interventions")

        cols = ["Date", "Machine", "Type", "Technicien", "Cout", "Pieces", "Statut"]
        widths = [22, 35, 28, 30, 22, 22, 22]

        _table_header(pdf, cols, widths)

        for i, (_, row) in enumerate(df_interventions.iterrows()):
            # Check page break
            if pdf.get_y() > 265:
                pdf.add_page()
                _table_header(pdf, cols, widths)

            values = [
                str(row.get("date", ""))[:10],
                str(row.get("machine", ""))[:20],
                str(row.get("type_intervention", ""))[:16],
                str(row.get("technicien", ""))[:18],
                pdf._format_devise(row.get("cout", 0)),
                pdf._format_devise(row.get("cout_pieces", 0)),
                str(row.get("statut", "")),
            ]
            _table_row(pdf, values, widths, fill=(i % 2 == 1))

        # Ligne total
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(220, 220, 240)
        pdf.cell(widths[0] + widths[1] + widths[2] + widths[3], 7,
                 f"TOTAL ({nb_inter} interventions)", border=1, fill=True, align="R")
        pdf.cell(widths[4], 7, _safe(pdf._format_devise(cout_interventions)), border=1, fill=True, align="C")
        pdf.cell(widths[5], 7, _safe(pdf._format_devise(cout_pieces)), border=1, fill=True, align="C")
        pdf.cell(widths[6], 7, "", border=1, fill=True)
        pdf.ln()

    # --- Repartition par type ---
    if not df_interventions.empty and "type_intervention" in df_interventions.columns:
        pdf.ln(4)
        pdf._section_title("Repartition par Type")
        type_counts = df_interventions["type_intervention"].value_counts()
        for type_name, count in type_counts.items():
            pdf._row(f"  {type_name} :", f"{count} intervention(s)")

    # --- Signature ---
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 7, "Signature Client :", border=0)
    pdf.cell(95, 7, "Signature Responsable :", border=0)
    pdf.ln(22)
    pdf.cell(95, 0, "", border="T")
    pdf.cell(95, 0, "", border="T")
    pdf.ln(5)

    return bytes(pdf.output())


def generer_pdf_export_comptable(date_debut, date_fin, client, df_export, devise="EUR"):
    """
    Genere un export comptable en PDF avec entete SAVIA.

    Returns: bytes du PDF
    """
    pdf = RapportInterventionPDF(devise=devise)
    pdf.alias_nb_pages()
    pdf.add_page("L")  # Paysage pour plus de colonnes

    # --- Titre ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 10, "EXPORT COMPTABLE", align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    titre_client = f"Client : {_safe(client)}" if client and client != "Tous" else "Tous les clients"
    pdf.cell(0, 7, f"{titre_client} | Periode : {date_debut} a {date_fin}", align="C")
    pdf.ln(7)
    pdf.ln(4)

    # --- Resume ---
    pdf._section_title("Resume")
    nb_inter = len(df_export)
    cout_total = df_export["cout"].sum() if "cout" in df_export.columns else 0
    cout_pieces = df_export["cout_pieces"].sum() if "cout_pieces" in df_export.columns else 0
    duree_total = df_export["duree_minutes"].sum() if "duree_minutes" in df_export.columns else 0
    pdf._row("Nombre d'interventions :", str(nb_inter))
    pdf._row("Cout total interventions :", pdf._format_devise(cout_total))
    pdf._row("Cout total pieces :", pdf._format_devise(cout_pieces))
    pdf._row("Cout global :", pdf._format_devise(cout_total + cout_pieces))
    pdf._row("Duree totale :", f"{(duree_total or 0) / 60:.1f} heures")
    pdf.ln(4)

    # --- Tableau ---
    if not df_export.empty:
        pdf._section_title("Detail des Ecritures")

        cols = ["Date", "Machine", "Type", "Technicien", "Description", "Cout", "Pieces", "Duree(h)", "Statut"]
        widths = [22, 35, 25, 28, 55, 22, 22, 18, 22]

        _table_header(pdf, cols, widths)

        for i, (_, row) in enumerate(df_export.iterrows()):
            if pdf.get_y() > 180:  # Paysage = moins de hauteur
                pdf.add_page("L")
                _table_header(pdf, cols, widths)

            duree_h = f"{(row.get('duree_minutes', 0) or 0) / 60:.1f}"
            values = [
                str(row.get("date", ""))[:10],
                str(row.get("machine", ""))[:20],
                str(row.get("type_intervention", ""))[:14],
                str(row.get("technicien", ""))[:16],
                str(row.get("description", ""))[:32],
                pdf._format_devise(row.get("cout", 0)),
                pdf._format_devise(row.get("cout_pieces", 0)),
                duree_h,
                str(row.get("statut", "")),
            ]
            _table_row(pdf, values, widths, fill=(i % 2 == 1))

        # Ligne total
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(220, 220, 240)
        total_w = widths[0] + widths[1] + widths[2] + widths[3] + widths[4]
        pdf.cell(total_w, 7, f"TOTAL ({nb_inter} interventions)", border=1, fill=True, align="R")
        pdf.cell(widths[5], 7, _safe(pdf._format_devise(cout_total)), border=1, fill=True, align="C")
        pdf.cell(widths[6], 7, _safe(pdf._format_devise(cout_pieces)), border=1, fill=True, align="C")
        pdf.cell(widths[7], 7, _safe(f"{(duree_total or 0) / 60:.1f}"), border=1, fill=True, align="C")
        pdf.cell(widths[8], 7, "", border=1, fill=True)
        pdf.ln()

    # --- Pied ---
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Document genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')} - Usage interne",
             align="C")
    pdf.ln(6)

    return bytes(pdf.output())


def draw_reportlab_header_footer(canvas, doc):
    """Callback pour dessiner l'entête SAVIA et le pied de page sur les PDF ReportLab"""
    canvas.saveState()
    import os
    from config import BASE_DIR
    from db_engine import get_config
    from datetime import datetime
    
    org_name = get_config("nom_organisation", "SIC Radiologie")
    savia_logo = os.path.join(BASE_DIR, "assets", "logo_savia.png")
    client_logo = get_config("logo_path", "")
    
    width, height = doc.pagesize
    
    # === HEADER ===
    # Logo SAVIA (gauche)
    if os.path.exists(savia_logo):
        try:
            # We use bottom-left y=height-60 and draw upward, with preserveAspectRatio
            canvas.drawImage(savia_logo, 30, height - 55, width=90, height=40, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
            
    # Centrale: Nom Organisation et sous-titre
    canvas.setFont('Helvetica-Bold', 16)
    canvas.setFillColorRGB(30/255.0, 58/255.0, 138/255.0)  # #1e3a8a
    canvas.drawCentredString(width / 2.0, height - 25, org_name)
    
    canvas.setFont('Helvetica', 10)
    canvas.setFillColorRGB(100/255.0, 100/255.0, 100/255.0)
    canvas.drawCentredString(width / 2.0, height - 40, "Systeme Intelligent de Controle - Imagerie Medicale")
    
    # Logo Client (droite)
    if client_logo and os.path.exists(client_logo):
        try:
            canvas.drawImage(client_logo, width - 120, height - 55, width=90, height=40, preserveAspectRatio=True, mask='auto', anchor='ne')
        except Exception:
            pass
            
    # Ligne de séparation
    canvas.setStrokeColorRGB(0.8, 0.8, 0.8)
    canvas.line(30, height - 60, width - 30, height - 60)
    
    # === FOOTER ===
    canvas.setFont('Helvetica-Oblique', 8)
    canvas.setFillColorRGB(150/255.0, 150/255.0, 150/255.0)
    
    page_num = canvas.getPageNumber()
    footer_text = f"Page {page_num} - SIC Radiologie - {datetime.now().strftime('%d/%m/%Y')}"
    canvas.drawCentredString(width / 2.0, 20, footer_text)
    
    canvas.restoreState()
