"""Signed intervention sheet PDF route."""

from api.runtime import (
    Depends,
    HTTPException,
    app,
    datetime,
    get_db,
    lire_contrats,
    lire_equipements,
    lire_interventions,
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
    lire_interventions,
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
    lire_interventions,
    logger,
)
from controllers.report_helpers import (
    SaviaPDF,
    _sanitize,
)


def _collect_technician_names(primary_value, assignment_records, work_sessions):
    """Return every technician name once, preserving the most useful display order."""
    names = []

    def add(raw_name):
        name = str(raw_name or "").strip()
        if name and name.lower() not in {existing.lower() for existing in names}:
            names.append(name)

    for name in str(primary_value or "").split(","):
        add(name)
    for record in assignment_records or []:
        item = dict(record) if hasattr(record, "keys") else record
        add(item.get("technicien_nom", ""))
    for session in work_sessions or []:
        item = dict(session) if hasattr(session, "keys") else session
        add(item.get("technicien_nom", ""))

    return names


def _write_header_field(pdf, x, y, width, label, value, line_height=5, multiline=False):
    """Draw an underlined field label followed by its regular-weight value."""
    pdf.set_xy(x, y)
    pdf.set_font("Helvetica", "BU", 10)
    label_width = pdf.get_string_width(label)
    pdf.cell(label_width, line_height, _sanitize(label))
    pdf.set_font("Helvetica", "B", 10)
    separator = ": "
    separator_width = pdf.get_string_width(separator)
    pdf.cell(separator_width, line_height, separator)
    value_width = width - label_width - separator_width
    pdf.set_font("Helvetica", "", 10)
    if multiline:
        pdf.multi_cell(value_width, line_height, _sanitize(str(value)), max_line_height=line_height)
    else:
        pdf.cell(value_width, line_height, _sanitize(str(value)))


def _fiche_display_date(intervention):
    """Return the actual intervention date without changing the legacy `date` field."""
    for field in ("date_cloture", "date_debut_intervention", "date"):
        value = intervention.get(field)
        if value and str(value).strip() and str(value).strip() != "None":
            return str(value)[:10]
    return "-"


def _fiche_equipment_details(intervention: dict) -> tuple[dict, bool, bool]:
    """Load PDF equipment data and coverage from the immutable equipment ID.

    Equipment names are deliberately never used here: two records may have
    the same label while their serial number, warranty, and contract coverage
    are different.
    """
    try:
        equipment_id = int(intervention.get("equipement_id"))
    except (TypeError, ValueError):
        return {}, False, False

    reference_date = None
    for field in ("date_cloture", "date_debut_intervention", "date"):
        value = intervention.get(field)
        if not value:
            continue
        try:
            reference_date = datetime.strptime(str(value)[:10], "%Y-%m-%d")
            break
        except (TypeError, ValueError):
            continue
    reference_date = reference_date or datetime.now()

    with get_db() as conn:
        row = conn.execute(
            """SELECT id, nom, num_serie, fabricant, modele,
                      garantie_debut, garantie_duree
               FROM equipements WHERE id = %s""",
            (equipment_id,),
        ).fetchone()
        equipment = dict(row) if row else {}
        if not equipment:
            return {}, False, False
        contract = conn.execute(
            """SELECT 1
               FROM contrats c
               JOIN contrats_equipements ce ON ce.contrat_id = c.id
               WHERE ce.equipement_id = %s
                 AND LOWER(BTRIM(COALESCE(c.statut, ''))) IN ('actif', 'active')
                 AND %s BETWEEN c.date_debut AND c.date_fin
               LIMIT 1""",
            (equipment_id, reference_date.date()),
        ).fetchone()

    under_warranty = False
    try:
        start = datetime.strptime(str(equipment.get("garantie_debut") or "")[:10], "%Y-%m-%d")
        duration_years = int(equipment.get("garantie_duree") or 0)
        if duration_years > 0:
            try:
                end = start.replace(year=start.year + duration_years)
            except ValueError:  # 29 February on a non-leap end year
                end = start.replace(year=start.year + duration_years, day=28)
            under_warranty = reference_date < end
    except (TypeError, ValueError):
        pass
    return equipment, under_warranty, bool(contract)


@app.post("/api/interventions/{interv_id}/fiche-pdf")
def generate_fiche_intervention_pdf(interv_id: int, body: dict = {}, user: dict = Depends(_verify_token)):
    """Generate a professional intervention fiche PDF with all details, logos, and signature areas.
    
    For multi-technician interventions, includes a table with one row per technician.
    """
    with get_db() as conn:
        assert_resource_client_access(conn, "intervention", interv_id, user)
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    from io import BytesIO
    from fastapi.responses import Response
    import base64 as _b64
    import urllib.request as _ur
    from db_engine import get_interventions_techniciens, list_work_sessions

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        # Fetch intervention data
        df_interv = lire_interventions()
        interv = None
        if not df_interv.empty:
            match = df_interv[df_interv["id"] == interv_id]
            if not match.empty:
                interv = match.iloc[0].to_dict()
        if not interv:
            raise HTTPException(status_code=404, detail="Intervention non trouvee")

        # Load all technician sources. Some multi-technician interventions retain
        # only the primary technician in the legacy intervention column.
        technicien_str = str(interv.get("technicien", "")).strip()
        tech_records = []
        try:
            tech_records = get_interventions_techniciens(interv_id)
        except Exception as e:
            logger.debug(f"Could not load tech records: {e}")
        try:
            work_sessions = list_work_sessions(interv_id)
        except Exception as e:
            logger.debug(f"Could not load work sessions: {e}")
            work_sessions = []
        technicians = _collect_technician_names(technicien_str, tech_records, work_sessions)
        is_multi_tech = len(technicians) > 1

        # The equipment ID is the sole identity source for every field shown
        # on the PDF. A machine name is only a display label and can repeat.
        matched_equip, sous_garantie, sous_contrat = _fiche_equipment_details(interv)
        client_name = str(interv.get("client", "")).strip()
        num_serie = str(matched_equip.get("num_serie") or "-")
        equip_brand_model = " ".join(
            value for value in (
                str(matched_equip.get("fabricant") or "").strip(),
                str(matched_equip.get("modele") or "").strip(),
            ) if value
        ) or "-"
        duree_min = int(interv.get("duree_minutes", 0) or 0)
        duree_h = round(duree_min / 60, 2) if duree_min else 0
        deplacement_min = int(interv.get("duree_deplacement", 0) or 0)
        deplacement_h = round(deplacement_min / 60, 2) if deplacement_min else 0

        # Fetch client region/ville
        client_region = ""
        client_ville = ""
        if client_name:
            try:
                with get_db() as conn:
                    cl_row = conn.execute("SELECT region, ville FROM clients WHERE nom = %s LIMIT 1", (client_name,)).fetchone()
                    if cl_row:
                        client_region = dict(cl_row).get("region", "") or ""
                        client_ville = dict(cl_row).get("ville", "") or ""
            except Exception:
                pass

        # Client logo
        company_name = body.get("company_name", "SAVIA")
        company_logo = body.get("company_logo", "")
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
            report_title=f"FICHE D'INTERVENTION N. {interv_id}"
        )
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_top_margin(pdf.HEADER_H + 10)
        pdf.add_page()
        W = pdf.w - 20

        # Date line
        pdf.set_font("Helvetica", "", 9)
        # INFORMATION PRINCIPALE - Two columns layout
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        
        date_str = _fiche_display_date(interv)
        intervention_id = str(interv.get("id", ""))
        technicien = ", ".join(technicians) or "-"
        intervention_type = str(interv.get("type_intervention", "") or "-").strip()
        
        # Left column
        left_x = 14
        right_col_x = pdf.w / 2 + 5
        line_h = 5
        y_start = pdf.get_y()
        
        # LEFT COLUMN: Date, Client, Equipement, Marque/Modele, N° Serie
        _write_header_field(pdf, left_x, y_start, 85, "Date", date_str)
        _write_header_field(pdf, left_x, y_start + 5, 85, "Client", client_name or "-")
        _write_header_field(pdf, left_x, y_start + 10, 85, "Equipement", str(interv.get("machine", "-"))[:35])
        _write_header_field(pdf, left_x, y_start + 15, 85, "Marque/Modele", equip_brand_model[:30])
        _write_header_field(pdf, left_x, y_start + 20, 85, "N° Serie", str(num_serie or "-")[:25])
        # RIGHT COLUMN: Technicien(s), Garantie, Contrat, Type d'intervention
        _write_header_field(pdf, right_col_x, y_start, 95, "Technicien(s)", technicien, multiline=True)
        _write_header_field(pdf, right_col_x, y_start + 10, 95, "Garantie", "OUI" if sous_garantie else "NON")
        _write_header_field(pdf, right_col_x, y_start + 15, 95, "Contrat", "OUI" if sous_contrat else "NON")
        _write_header_field(pdf, right_col_x, y_start + 20, 95, "Type d'intervention", intervention_type)
        
        # Move down after info section
        pdf.set_y(y_start + 28)

        # TRAVAUX EFFECTUES - Table with Date, Start, End, Travel
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        if work_sessions:
            pdf.cell(W, 6, "Travaux Effectues")
            col_widths = [28, 42, 24, 24, 26, 30]
            headers = ["Date", "Technicien", "Debut", "Fin", "Duree", "Trajet (h)"]
        elif is_multi_tech:
            pdf.cell(W, 6, "Travaux Effectues (Multi-Technicien)")
        else:
            pdf.cell(W, 6, "Travaux Effectues")
        pdf.ln(7)  # Increased space before table
        
        # Table header - Add Technicien column for multi-tech
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(200, 200, 200)
        pdf.set_text_color(0, 0, 0)
        
        if work_sessions:
            pass
        elif is_multi_tech:
            # Multi-tech table: Technicien, Debut, Fin, Trajet, Solution
            col_widths = [30, 25, 25, 25, 50]
            headers = ["Technicien", "Heure Debut", "Heure Fin", "Trajet (h)", "Solution"]
        else:
            # Single-tech table: Date, Debut, Fin, Trajet, Solution
            col_widths = [35, 30, 30, 30, 50]
            headers = ["Date", "Heure Debut", "Heure Fin", "Trajet (h)", "Solution Appliquee"]
        
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 6, header, border=1, align="C", fill=True)
        pdf.ln(6)
        
        # Table data rows
        pdf.set_font("Helvetica", "", 8)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(0, 0, 0)
        
        if work_sessions:
            for session in work_sessions:
                session_dict = dict(session) if hasattr(session, "keys") else session
                duration = int(session_dict.get("duration_minutes", 0) or 0)
                travel = int(session_dict.get("travel_minutes", 0) or 0)
                values = [
                    str(session_dict.get("work_date", ""))[:10],
                    str(session_dict.get("technicien_nom", ""))[:24],
                    str(session_dict.get("start_time", ""))[:5],
                    str(session_dict.get("end_time", ""))[:5],
                    f"{duration // 60}h{duration % 60:02d}",
                    f"{round(travel / 60, 2)}" if travel else "-",
                ]
                for index, value in enumerate(values):
                    pdf.cell(col_widths[index], 6, _sanitize(value), border=1)
                pdf.ln(6)
        elif is_multi_tech and tech_records:
            # Multi-tech mode: one row per technician from interventions_techniciens
            for tech_record in tech_records:
                rec_dict = dict(tech_record) if hasattr(tech_record, 'keys') else tech_record
                
                tech_nom = str(rec_dict.get('technicien_nom', 'Unknown'))[:20]
                heure_debut = str(rec_dict.get('heure_debut_tech', '-') or '-')[:5]
                heure_fin = str(rec_dict.get('heure_fin_tech', '-') or '-')[:5]
                duree_depl_min = int(rec_dict.get('duree_deplacement_tech', 0) or 0)
                trajet = f"{round(duree_depl_min / 60, 1)}" if duree_depl_min > 0 else "-"
                solution = _sanitize(str(rec_dict.get('solution_tech', ''))[:50])
                
                pdf.cell(col_widths[0], 6, _sanitize(tech_nom), border=1)
                pdf.cell(col_widths[1], 6, _sanitize(heure_debut), border=1)
                pdf.cell(col_widths[2], 6, _sanitize(heure_fin), border=1)
                pdf.cell(col_widths[3], 6, _sanitize(trajet), border=1)
                pdf.cell(col_widths[4], 6, solution, border=1)
                pdf.ln(6)
        else:
            # Single-tech mode: original behavior
            # Extract time data - USE start_time and end_time from database, with fallbacks
            date_val = date_str
            
            # Get start_time and end_time directly from database (TIME type columns)
            start_time = str(interv.get("start_time", "") or "").strip()
            if not start_time or start_time == "None" or start_time == "00:00":
                # Fallback: try to extract from date_debut_intervention
                start_time_fb = str(interv.get("date_debut_intervention", "") or "").strip()
                if start_time_fb and start_time_fb != "None" and len(start_time_fb) >= 16:
                    start_time = start_time_fb[11:16]  # Extract HH:MM (indices 11-16 exclusive)
                else:
                    # Second fallback: use date field
                    start_time_fb2 = str(interv.get("date", "") or "").strip()
                    if start_time_fb2 and start_time_fb2 != "None" and len(start_time_fb2) >= 16:
                        start_time = start_time_fb2[11:16]  # Extract HH:MM
                    else:
                        start_time = "-"
            else:
                # Ensure we only have HH:MM (remove seconds if present)
                if len(start_time) > 5 and start_time[5] == ':':
                    start_time = start_time[:5]  # Remove :SS
            
            end_time = str(interv.get("end_time", "") or "").strip()
            if not end_time or end_time == "None" or end_time == "00:00":
                # Fallback: use date_cloture
                end_time_fb = str(interv.get("date_cloture", "") or "").strip()
                if end_time_fb and end_time_fb != "None" and len(end_time_fb) >= 16:
                    end_time = end_time_fb[11:16]  # Extract HH:MM (indices 11-16 exclusive)
                else:
                    end_time = "-"
            else:
                # Ensure we only have HH:MM (remove seconds if present)
                if len(end_time) > 5 and end_time[5] == ':':
                    end_time = end_time[:5]  # Remove :SS
            
            # Trajet: duree_deplacement is in MINUTES, convert to hours
            trajet = f"{round(deplacement_min / 60, 1)}" if deplacement_min > 0 else "-"
            description = _sanitize(str(interv.get("solution", ""))[:50])  # Solution field
            
            # Row with borders - SANITIZE ALL VALUES
            pdf.cell(col_widths[0], 6, _sanitize(date_val), border=1)
            pdf.cell(col_widths[1], 6, _sanitize(start_time), border=1)
            pdf.cell(col_widths[2], 6, _sanitize(end_time), border=1)
            pdf.cell(col_widths[3], 6, _sanitize(trajet), border=1)
            pdf.cell(col_widths[4], 6, description, border=1)
            pdf.ln(6)
        
        # Add empty rows for manual fill (per model) - only for single-tech
        if not is_multi_tech and not work_sessions:
            for _ in range(2):
                pdf.cell(col_widths[0], 6, "", border=1)
                pdf.cell(col_widths[1], 6, "", border=1)
                pdf.cell(col_widths[2], 6, "", border=1)
                pdf.cell(col_widths[3], 6, "", border=1)
                pdf.cell(col_widths[4], 6, "", border=1)
                pdf.ln(6)
        
        pdf.ln(8)
        
        # STATUT INTERVENTION - MOVED AFTER TABLE, IN BOLD
        pdf.set_font("Helvetica", "B", 10)  # Bold
        pdf.set_text_color(0, 0, 0)
        statut_val = str(interv.get("statut", "-"))
        status_map = {
            "Clôturee": "Clôturee",
            "En cours": "En cours",
            "En attente de piece": "En attente de piece",
        }
        display_status = status_map.get(statut_val, statut_val)
        pdf.cell(W, 5, _sanitize(f"Statut: {display_status}"))
        pdf.ln(8)
        
        # PIECES UTILISEES / REFERENCES TABLE
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(W, 6, "References - Pieces Utilisees")
        pdf.ln(7)  # Increased space before table
        
        # Table header - INCREASED REFERENCE COLUMN WIDTH
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(200, 200, 200)
        pdf.set_text_color(0, 0, 0)
        ref_col_widths = [50, 15, 100]  # Increased reference from 30 to 50
        ref_headers = ["Reference", "Qte", "Designation"]
        for i, header in enumerate(ref_headers):
            pdf.cell(ref_col_widths[i], 6, header, border=1, align="C", fill=True)
        pdf.ln(6)
        
        # Parse pieces data - USE PIPE DELIMITER - SHOW MORE TEXT
        pdf.set_font("Helvetica", "", 7)  # Smaller font for pieces
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(0, 0, 0)
        
        pieces = str(interv.get("pieces_utilisees", "") or "").strip()
        row_count = 0
        if pieces:
            pieces_lines = pieces.split('\n')  # Multiple pieces separated by newlines
            for piece_line in pieces_lines[:8]:  # Max 8 rows
                if piece_line.strip():
                    # Parse format: "Product | Ref: XXX | Fournisseur: YYY | Qty: Z"
                    parts = piece_line.split('|')
                    
                    # Extract each part
                    product_name = _sanitize(parts[0].strip()[:80]) if len(parts) > 0 else "-"
                    
                    # Find reference and quantity
                    ref_val = "-"
                    qty_val = "-"
                    for part in parts[1:]:
                        part_lower = part.lower()
                        if "ref:" in part_lower:
                            ref_val = _sanitize(part.replace("Ref:", "").replace("ref:", "").strip()[:45])  # Increased from 30 to 45
                        if "qty:" in part_lower:
                            qty_val = _sanitize(part.replace("Qty:", "").replace("qty:", "").strip()[:10])
                    
                    # Full designation includes product name
                    desc_val = product_name
                    
                    pdf.cell(ref_col_widths[0], 6, ref_val, border=1)
                    pdf.cell(ref_col_widths[1], 6, qty_val, border=1)
                    pdf.cell(ref_col_widths[2], 6, desc_val, border=1)
                    pdf.ln(6)
                    row_count += 1
        
        # Add empty rows for manual fill
        for _ in range(max(0, 8 - row_count)):
            pdf.cell(ref_col_widths[0], 6, "", border=1)
            pdf.cell(ref_col_widths[1], 6, "", border=1)
            pdf.cell(ref_col_widths[2], 6, "", border=1)
            pdf.ln(6)
        
        pdf.ln(8)
        
        # OBSERVATIONS section
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(W, 5, "Observations:")
        pdf.ln(6)
        
        # Add 2 extended dotted lines for client to write observations
        pdf.set_font("Helvetica", "", 9)
        for _ in range(2):
            # Create a dotted line that extends to the right edge
            # Each dot is about 1.5-2 characters wide, so we need about 130-150 dots for full width
            dots = "." * 150
            pdf.cell(W, 5, dots)
            pdf.ln(5)

        # SIGNATURES SECTION
        pdf.ln(8)
        sig_start_y = pdf.get_y()
        
        if sig_start_y > pdf.h - 60:
            pdf.add_page()
            sig_start_y = pdf.get_y()
        
        # Separator line
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.5)
        pdf.line(10, sig_start_y, pdf.w - 10, sig_start_y)
        
        pdf.set_y(sig_start_y + 3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(W, 5, "Signatures & Approbations")
        pdf.ln(8)
        
        # Three signature labels on ONE line
        col1_x = 18
        col2_x = pdf.w / 3 + 10
        col3_x = (pdf.w / 3) * 2 + 2
        box_w = 45
        box_h = 22
        label_y = pdf.get_y()
        
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        
        # Position labels horizontally
        pdf.set_xy(col1_x, label_y)
        pdf.cell(box_w, 5, "Visa Intervenant", align="C")
        
        pdf.set_xy(col2_x, label_y)
        pdf.cell(box_w, 5, "Visa Client", align="C")
        
        pdf.set_xy(col3_x, label_y)
        pdf.cell(box_w, 5, "Visa Administration", align="C")
        
        # Draw signature boxes below each label
        box_y = label_y + 6
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.3)
        pdf.rect(col1_x, box_y, box_w, box_h, style="D")
        pdf.rect(col2_x, box_y, box_w, box_h, style="D")
        pdf.rect(col3_x, box_y, box_w, box_h, style="D")

        # Footer
        pdf.set_auto_page_break(auto=False)
        total_pages = len(pdf.pages)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        for pg in range(1, total_pages + 1):
            pdf.page = pg
            pdf.set_xy(10, pdf.h - 12)
            pdf.set_draw_color(150, 180, 180)
            pdf.set_line_width(0.5)
            pdf.line(10, pdf.h - 12, pdf.w - 10, pdf.h - 12)
            pdf.set_xy(10, pdf.h - 9)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(120, 140, 150)
            pdf.cell(pdf.w - 40, 5, _sanitize(f"Généré par {company_name} - {now_str}"), align="L")
            pdf.cell(30, 5, f"Page {pg}/{total_pages}", align="R")

        pdf_bytes = bytes(pdf.output())
        _fn = f"fiche_intervention_{interv_id}"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={_fn}.pdf",
                "Content-Length": str(len(pdf_bytes)),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Fiche PDF generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

__all__ = [
    "generate_fiche_intervention_pdf",
]
