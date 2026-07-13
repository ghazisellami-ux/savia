"""General intervention report PDF route."""

from api.runtime import (
    Depends,
    HTTPException,
    _fallback_translate_payload_for_lang,
    _force_ai_payload_language,
    _get_app_language,
    app,
    datetime,
    logger,
    logging,
    os,
)
from api.security import (
    Depends,
    HTTPException,
    _verify_token,
)
from services.scheduled_jobs import (
    logger,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    _verify_token,
    app,
    datetime,
    logger,
)
from controllers.report_helpers import (
    PdfRequest,
    SaviaPDF,
    _fmt_number,
    _sanitize,
)

@app.post("/api/reports/generate-pdf")
def generate_pdf_report(data: PdfRequest, user: dict = Depends(_verify_token)):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    from io import BytesIO
    from fastapi.responses import Response
    import json

    SAVIA_LOGO = "/app/logo-savia.png"
    try:
        from io import BytesIO as _BytesIO
        import base64 as _b64
        import urllib.request as _ur

        orientation = "P" if data.is_ai_report else "L"
        pdf = SaviaPDF(orientation=orientation, unit="mm", format="A4")

        # ── Resolve client logo (URL or base64) ──────────────
        _client_logo_io = None
        if data.company_logo:
            try:
                clogo = data.company_logo.strip()
                if clogo.startswith("data:"):
                    _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                    _client_logo_io = _BytesIO(_b64.b64decode(_b64_part))
                elif clogo.startswith("http"):
                    req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                    with _ur.urlopen(req_, timeout=6) as _r:
                        _client_logo_io = _BytesIO(_r.read())
            except Exception as _e:
                logger.warning(f"Client logo error: {_e}")

        pdf.set_header_data(
            SAVIA_LOGO, _client_logo_io,
            data.company_name if data.company_name != "SAVIA" else "",
            "Systeme Intelligent de Controle et de Gestion",  # Always fixed - footer has date/name
            report_title=data.title if data.title and data.title != "Rapport SAVIA" else ""
        )
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_top_margin(pdf.HEADER_H + 10)  # content starts below header
        pdf.add_page()
        page_w = pdf.w

        # Title is now shown in header (between logos)


        # KPIs
        if data.kpis:
            box_w, box_h, margin_ = 64, 16, 5
            kpi_y = pdf.get_y()
            # Centrer les KPIs au milieu de la page
            num_kpis = len(data.kpis[:4])
            total_width = num_kpis * box_w + (num_kpis - 1) * margin_
            start_x = (pdf.w - total_width) / 2  # Centrer horizontalement
            
            for i, kpi in enumerate(data.kpis[:4]):
                kx = start_x + i * (box_w + margin_)
                color = kpi.get("color", [15, 118, 110])
                # Support both hex string "#RRGGBB" and [r,g,b] list
                if isinstance(color, str) and color.startswith("#") and len(color) >= 7:
                    h = color.lstrip("#")
                    r1,g1,b1 = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
                elif isinstance(color, (list,tuple)) and len(color) >= 3:
                    r1,g1,b1 = int(color[0]),int(color[1]),int(color[2])
                else:
                    r1,g1,b1 = 15,118,110
                lc = [min(r1+215,255), min(g1+215,255), min(b1+215,255)]
                pdf.set_fill_color(*lc)
                pdf.set_draw_color(r1,g1,b1)
                pdf.set_line_width(0.4)
                pdf.rect(kx, kpi_y, box_w, box_h, style="FD")
                # Top accent bar (Dopely palette solid)
                pdf.set_fill_color(r1,g1,b1)
                pdf.rect(kx, kpi_y, box_w, 3, style="F")
                # Small white round dot on top bar
                pdf.set_fill_color(255, 255, 255)
                pdf.ellipse(kx + box_w/2 - 1.5, kpi_y + 0.3, 3, 2.4, style="F")
                # Value
                pdf.set_xy(kx, kpi_y + 3)
                pdf.set_font("Helvetica", "B", 13)
                vr = max(30, min(r1-30, 180)); vg = max(30, min(g1-20, 120)); vb = max(30, min(b1-20, 150))
                pdf.set_text_color(vr, vg, vb)
                pdf.cell(box_w, 8, _sanitize(str(kpi.get("val", ""))), align="C")
                # Label
                pdf.set_xy(kx, kpi_y + 11)
                pdf.set_font("Helvetica", "", 6.5)
                pdf.set_text_color(90, 100, 115)
                pdf.cell(box_w, 4, _sanitize(str(kpi.get("label", ""))), align="C")
            pdf.set_y(kpi_y + box_h + 6)
            pdf.set_text_color(0, 0, 0)

        # Type distribution table
        if data.type_data:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(50, 70, 90)
            pdf.cell(0, 6, "Repartition par type", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_draw_color(1, 180, 188)
            pdf.set_fill_color(1, 180, 188)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(100, 7, "Type", border=1, fill=True)
            pdf.cell(30, 7, "Nombre", border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 8)
            for idx, row in enumerate(data.type_data):
                fill = idx % 2 == 0
                if fill: pdf.set_fill_color(225, 250, 251)
                else: pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(30, 40, 60)
                pdf.cell(100, 6, _sanitize(str(row[0])) if row else "", border=1, fill=fill)
                pdf.cell(30, 6, str(row[1]) if len(row) > 1 else "", border=1, fill=fill, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

        # AI Report mode - WEB UI STYLE (colored text headers + Unicode symbols)
        if data.is_ai_report and data.ai_content:
            try: ai = json.loads(data.ai_content)
            except Exception: ai = {'summary': data.ai_content}
            lang = _get_app_language(body=data.model_dump() if hasattr(data, "model_dump") else data.dict())
            try:
                from ai_engine import _call_ia, clean_json_response
                ai = _force_ai_payload_language(ai, lang, _call_ia, clean_json_response)
            except Exception:
                ai = _fallback_translate_payload_for_lang(ai, lang)

            W = page_w - 20

            # Load DejaVu for Unicode bullet symbols
            _DJVU = '/app/DejaVuSans.ttf'
            _has_djvu = os.path.exists(_DJVU)
            if _has_djvu:
                try: pdf.add_font('DejaVu', fname=_DJVU)
                except Exception: _has_djvu = False

            # Font Awesome icons (requires fonttools space-glyph fix)
            _FA = '/app/fa-solid-900.ttf'
            # NOTE: FA TTF converted from WOFF2 lacks 'space' glyph
            # fpdf2 crashes on output() -> disabled, using test + fallback
            _has_fa = False
            if os.path.exists(_FA):
                try:
                    pdf.add_font('FA', fname=_FA)
                    from fpdf import FPDF as _FPDF_TEST
                    _pt = _FPDF_TEST(); _pt.add_page()
                    _pt.add_font('FA', fname=_FA); _pt.set_font('FA', size=10)
                    _pt.cell(10, 10, chr(0xF164))
                    bytes(_pt.output())  # test that it works
                    _has_fa = True
                except Exception as _efa:
                    _has_fa = False
                    logger.debug(f"FA font disabled: {_efa}")

            def _sym(size=8):
                if _has_djvu:
                    try: pdf.set_font('DejaVu', size=size); return True
                    except: pass
                pdf.set_font('Helvetica', size=size); return False

            def _hel(style='', size=8.5):
                pdf.set_font('Helvetica', style, size)

            # FA section icon codes (matches Lucide React)
            FA = {
                'resume':   chr(0xf080),  # bar-chart (BarChart3)
                'strong':   chr(0xf164),  # thumbs-up (ThumbsUp)
                'weak':     chr(0xf165),  # thumbs-down (ThumbsDown)
                'reco':     chr(0xf0eb),  # lightbulb (Lightbulb)
                'alert':    chr(0xf071),  # triangle-exclamation (AlertTriangle)
                'trend':    chr(0xf201),  # chart-line (TrendingUp)
                'team':     chr(0xf0c0),  # users (Users)
                'cost':     chr(0xf155),  # dollar-sign (DollarSign)
                'priority': chr(0xf0e7),  # bolt (Zap)
                'done':     chr(0xf058),  # circle-check (CheckCircle2)
                'score':    chr(0xf201),  # chart-line (BarChart2)
            }

            def sec_hdr(lbl, bg, fa_key=None):
                # Web-style: white bg, FA icon + colored bold title, thin underline
                if pdf.get_y() > pdf.h - 45: pdf.add_page()
                yh = pdf.get_y() + 2
                R_, G_, B_ = bg
                # Font Awesome icon before title
                if fa_key and _has_fa and fa_key in FA:
                    pdf.set_xy(10, yh - 0.5)
                    pdf.set_font('FA', size=9)
                    pdf.set_text_color(R_, G_, B_)
                    pdf.cell(7, 6, FA[fa_key])
                    pdf.set_xy(18, yh)
                else:
                    # Fallback: colored rect
                    pdf.set_fill_color(R_, G_, B_)
                    pdf.rect(10, yh, 3, 5.5, style='F')
                    pdf.set_xy(15, yh)
                # Colored bold title
                _hel('B', 10)
                pdf.set_text_color(R_, G_, B_)
                pdf.cell(W - 8, 5.5, _sanitize(lbl))
                # Thin underline
                pdf.set_draw_color(R_, G_, B_)
                pdf.set_line_width(0.4)
                pdf.line(10, yh + 7, page_w - 10, yh + 7)
                pdf.set_y(yh + 10)
                pdf.set_text_color(40, 50, 65)

            def body_item(txt, bg, sym='\u25cf'):
                if not txt: return
                if pdf.get_y() > pdf.h - 20: pdf.add_page()
                yi = pdf.get_y()
                R_, G_, B_ = bg
                if _has_djvu:
                    _sym(8)
                    pdf.set_text_color(R_, G_, B_)
                    pdf.set_xy(13, yi)
                    pdf.cell(5, 4.8, sym)
                else:
                    pdf.set_fill_color(R_, G_, B_)
                    pdf.ellipse(13.5, yi + 2.0, 2.5, 2.5, style='F')
                _hel('', 8.5)
                pdf.set_text_color(40, 50, 65)
                pdf.set_xy(19, yi)
                pdf.multi_cell(W - 10, 4.8, _sanitize(str(txt)[:300]))
                pdf.ln(0.5)

            def add_sec(lbl, items, bg, sym='\u25cf', fa_key=None):
                if not items: return
                sec_hdr(lbl, bg, fa_key)
                _hel('', 8.5)
                for it in items:
                    txt = it if isinstance(it, str) else it.get('action', it.get('machine', str(it))) if isinstance(it, dict) else str(it)
                    body_item(txt, bg, sym)
                pdf.ln(4)

            # Score global
            score = ai.get('score_global')
            if score is not None:
                sc = int(score)
                if sc >= 70:   s_bg = [95,165,90]
                elif sc >= 40: s_bg = [250,137,37]
                else:          s_bg = [250,84,87]
                y_sc = pdf.get_y()
                pdf.set_fill_color(255, 255, 255)
                pdf.set_draw_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.set_line_width(0.8)
                pdf.rect(10, y_sc, W, 16, style='FD')
                pdf.set_fill_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.rect(10, y_sc, 5, 16, style='F')
                pdf.set_xy(18, y_sc + 1.5)
                _hel('B', 15)
                pdf.set_text_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.cell(25, 9, str(sc))
                pdf.set_xy(36, y_sc + 2)
                _hel('B', 9)
                slabel = 'Excellent' if sc>=70 else 'Satisfaisant' if sc>=40 else 'A ameliorer'
                pdf.set_text_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.cell(50, 5.5, slabel)
                pdf.set_xy(36, y_sc + 8.5)
                _hel('', 7)
                pdf.set_text_color(130, 145, 160)
                pdf.cell(W - 28, 4, '/100 - Score global de performance')
                pdf.set_y(y_sc + 19)

            # Resume Executif - ORANGE #FA8925
            analyse = ai.get('analyse') or ai.get('summary')
            if analyse:
                sec_hdr('RESUME EXECUTIF', [250,137,37], 'resume')
                _hel('', 8.5)
                pdf.set_text_color(40, 50, 65)
                pdf.set_x(13)
                pdf.multi_cell(W - 3, 5, _sanitize(str(analyse)[:2500]))
                pdf.ln(5)

            # Points Forts - GREEN + CHECK
            add_sec('POINTS FORTS',     ai.get('points_forts', []),    [95,165,90],  '\u2713', 'strong')
            # Points Faibles - CORAL + TRIANGLE
            add_sec('POINTS FAIBLES',   ai.get('points_faibles', []),  [250,84,87],  '\u25b3', 'weak')
            # Recommandations - TEAL + ARROW
            recs = ai.get('recommandations', [])
            recs_c = [r if isinstance(r, str) else r.get('action', str(r)) for r in recs]
            add_sec('RECOMMANDATIONS',  recs_c,                        [1,180,188],  '\u2192', 'reco')
            # Alertes - CORAL + WARNING
            add_sec('ALERTES CRITIQUES',ai.get('alertes_critiques',[]),[250,84,87],  '\u26a0', 'alert')
            # Tendances - TEAL + UP-ARROW
            add_sec('TENDANCES',        ai.get('tendances', []),       [1,180,188],  '\u2197', 'trend')

            # Performance Equipe - AMBER
            perf = ai.get('performance_equipe', [])
            if perf:
                sec_hdr('EVALUATION DE L\'EQUIPE', [155,110,5], 'team')
                _hel('', 8.5)
                for pe in perf:
                    if isinstance(pe, dict):
                        nm_ = pe.get('technicien', pe.get('nom', ''))
                        sc_ = pe.get('score', pe.get('note', ''))
                        dt_ = pe.get('detail', pe.get('commentaire', ''))
                        body_item(_sanitize(str(nm_))+' : '+str(sc_)+(' - '+str(dt_) if dt_ else ''), [155,110,5], '\u25cf')
                    else: body_item(str(pe), [155,110,5], '\u25cf')
                pdf.ln(4)

            # Analyse Financiere - ORANGE
            couts = ai.get('analyse_couts')
            if couts and isinstance(couts, dict):
                sec_hdr('ANALYSE DES COUTS', [250,137,37], 'cost')
                _hel('', 8.5)
                for k_, v_ in couts.items():
                    if v_: body_item(str(k_)+' : '+str(v_), [250,137,37], '\u25cf')
                pdf.ln(4)

            # Priorites - ORANGE + LIGHTNING
            add_sec('PRIORITES IMMEDIATES', ai.get('priorites_immediates',[]),[250,137,37],'\u26a1', 'priority')

            # Conclusion - TEAL
            conclusion = ai.get('conclusion')
            if conclusion:
                sec_hdr('CONCLUSION', [1,180,188], 'done')
                _hel('', 9)
                pdf.set_text_color(50, 62, 78)
                pdf.set_x(13)
                pdf.multi_cell(W - 3, 5, _sanitize(str(conclusion)[:2500]))

        # ── Multi-table support (tables: [{title, head, rows}]) ──────
        if data.tables:
            def _render_table(tbl_head, tbl_rows, tbl_title=""):
                if not tbl_head: return
                if pdf.get_y() > pdf.h - 45: pdf.add_page()
                if tbl_title:
                    pdf.ln(3)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(1, 180, 188)
                    pdf.cell(0, 7, _sanitize(str(tbl_title)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                n_cols = len(tbl_head)
                total_w = page_w - 20
                # Smart column width distribution
                if n_cols == 2:
                    col_w = [total_w * 0.38, total_w * 0.62]
                elif n_cols == 7:
                    # Optimized for SAV: Date(12%), Machine(18%), Client(18%), Technicien(18%), Type(12%), Statut(12%), Durée(10%)
                    col_w = [total_w * p for p in [0.12, 0.18, 0.18, 0.18, 0.12, 0.12, 0.10]]
                else:
                    col_w = [total_w / n_cols] * n_cols
                # Header row
                pdf.set_font("Helvetica", "B", 7.5)
                pdf.set_draw_color(1, 180, 188)
                pdf.set_fill_color(1, 180, 188)
                pdf.set_text_color(255, 255, 255)
                for i, h in enumerate(tbl_head):
                    pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
                pdf.ln()
                # Data rows
                pdf.set_font("Helvetica", "", 7.5)
                for row_idx, row in enumerate(tbl_rows):
                    if pdf.get_y() > pdf.h - 15:
                        pdf.add_page()
                        pdf.set_font("Helvetica", "B", 7.5)
                        pdf.set_fill_color(1, 180, 188)
                        pdf.set_text_color(255, 255, 255)
                        for i, h in enumerate(tbl_head):
                            pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
                        pdf.ln()
                        pdf.set_font("Helvetica", "", 7.5)
                    fill = row_idx % 2 == 0
                    pdf.set_fill_color(244, 252, 251) if fill else pdf.set_fill_color(255, 255, 255)
                    pdf.set_text_color(25, 35, 55)
                    for i, cell in enumerate(row[:n_cols]):
                        # Dynamically truncate based on column width (~2.5mm per char at 7.5pt)
                        max_chars = max(5, int(col_w[i] / 2.3))
                        raw = str(cell) if cell is not None else "-"
                        val_s = _sanitize(raw[:max_chars])
                        align = "C" if i >= n_cols - 3 else "L"
                        pdf.cell(col_w[i], 6.5, val_s, border=1, fill=fill, align=align)
                    pdf.ln()
                pdf.ln(4)

            for tbl in data.tables:
                if isinstance(tbl, dict):
                    _render_table(tbl.get("head",[]), tbl.get("rows",[]), tbl.get("title",""))

        # Standard table (legacy: head + rows directly on request)
        elif data.head and data.rows:
            if pdf.get_y() > pdf.h - 45: pdf.add_page()
            if data.table_title:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(50, 70, 90)
                pdf.cell(0, 7, _sanitize(data.table_title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            n_cols = len(data.head)
            total_w = page_w - 20
            # Equal distribution: each column gets the same width
            # Exception: 2-col tables use 38%/62% (label/value)
            if n_cols == 2:
                col_w = [total_w * 0.38, total_w * 0.62]
            else:
                col_w = [total_w / n_cols] * n_cols
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_draw_color(1, 180, 188)
            pdf.set_fill_color(1, 180, 188)
            pdf.set_text_color(255, 255, 255)
            for i, h in enumerate(data.head):
                pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_font("Helvetica", "", 7.5)
            for row_idx, row in enumerate(data.rows):
                if pdf.get_y() > pdf.h - 15:
                    pdf.add_page()
                    pdf.set_font("Helvetica", "B", 8)
                    pdf.set_fill_color(15, 118, 110)
                    pdf.set_text_color(255, 255, 255)
                    for i, h in enumerate(data.head):
                        pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
                    pdf.ln()
                    pdf.set_font("Helvetica", "", 7.5)
                fill = row_idx % 2 == 0
                if fill: pdf.set_fill_color(244, 252, 251)
                else: pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(25, 35, 55)
                for i, cell in enumerate(row[:n_cols]):
                    val = _sanitize(_fmt_number(cell)) if i == n_cols - 1 else _sanitize(str(cell)[:25]) if cell else "-"
                    align = "R" if i == n_cols - 1 else "L"
                    pdf.cell(col_w[i], 6.5, val, border=1, fill=fill, align=align)
                pdf.ln()

        # ── CRITICAL: disable auto-page-break before footer loop ──────────────
        # cell() at y=h-10=287mm exceeds auto-break threshold (h-15=282mm)
        # → triggers unwanted new page with "Genere par" at top
        pdf.set_auto_page_break(auto=False)

        # Also remove last page if only header drawn (extra safety)
        try:
            _EMPTY_THRESHOLD = 46
            _last_y = pdf.get_y()
            _n_pages = len(pdf.pages)
            logger.info(f"PDF: {_n_pages} pages, last_y={_last_y:.1f}mm")
            if _last_y <= _EMPTY_THRESHOLD and _n_pages > 1:
                _last_pg = max(pdf.pages.keys())
                del pdf.pages[_last_pg]
                pdf.page = _last_pg - 1
                logger.info(f"Removed empty last page #{_last_pg}")
        except Exception as _ep:
            logger.warning(f"Empty page removal: {_ep}")

        # Footer on all pages (auto-break already disabled above)
        total_pages = len(pdf.pages)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        for pg in range(1, total_pages + 1):
            pdf.page = pg
            pdf.set_xy(10, pdf.h - 11)
            pdf.set_draw_color(200, 205, 220)
            pdf.set_line_width(0.3)
            pdf.line(10, pdf.h - 11, page_w - 10, pdf.h - 11)
            pdf.set_xy(10, pdf.h - 9)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(160, 170, 190)
            pdf.cell(page_w - 40, 5, _sanitize(f"Genere par {data.company_name} - {now_str}"), align="L")
            pdf.cell(30, 5, f"Page {pg} / {total_pages}", align="R")

        pdf_bytes = bytes(pdf.output()
        )
        # Sanitize filename for HTTP headers (latin-1 only)
        import urllib.parse as _up, unicodedata as _ud
        _fn = str(data.filename or "rapport")
        _ascii = _ud.normalize("NFKD", _fn).encode("ascii","ignore").decode()
        _ascii = "".join(c if c.isalnum() or c in "._-" else "_" for c in _ascii).strip("_") or "rapport"
        _utf8  = _up.quote(_fn + ".pdf", safe="")
        _cd = "attachment; filename=" + _ascii + ".pdf; filename*=UTF-8''" + _utf8
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": _cd,
                "Content-Length": str(len(pdf_bytes)),
            }
        )
    except Exception as e:
        logging.error(f"PDF generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

# ==========================================
# PDF FICHE INTERVENTION (server-side fpdf2)
# ==========================================

__all__ = [
    "generate_pdf_report",
]

