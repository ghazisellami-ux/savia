"""Shared PDF sanitization, fonts, number formatting, and request models."""

from api.runtime import (
    BaseModel,
    FPDF,
    _LANG_CONTEXT,
    _normalize_lang,
    _translate_text_for_lang,
    os,
)
from api.security import (
    BaseModel,
)

def _sanitize(text):
    if not text:
        return ""
    text = str(text)
    text = _translate_text_for_lang(text)
    # Replace specific chars with ASCII equivalents
    text = text.replace(chr(0x2014), " - ")  # em dash
    text = text.replace(chr(0x2013), " - ")  # en dash
    text = text.replace(chr(0x202F), " ")     # narrow no-break space
    text = text.replace(chr(0x00A0), " ")     # no-break space
    text = text.replace(chr(0x2022), "-")     # bullet
    text = text.replace(chr(0x2019), "'")    # right single quote
    text = text.replace(chr(0x2018), "'")    # left single quote
    text = text.replace(chr(0x201C), '"')    # left double quote
    text = text.replace(chr(0x201D), '"')    # right double quote
    text = text.replace(chr(0x2026), "...")   # ellipsis
    text = text.replace(chr(0x20AC), "EUR")   # euro sign
    # Final fallback: encode to Latin-1, unknown chars become ?
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _patch_pdf_text_translation():
    if getattr(FPDF, "_savia_i18n_patched", False):
        return

    original_cell = FPDF.cell
    original_multi_cell = FPDF.multi_cell

    def _translate_pdf_args(args, kwargs):
        if _normalize_lang(_LANG_CONTEXT.get()) != "en":
            return args, kwargs
        args = list(args)
        kwargs = dict(kwargs)

        def safe_pdf_text(value):
            if not isinstance(value, str):
                return value
            if len(value) == 1 and ord(value) > 255:
                return value
            return _sanitize(value)

        if "text" in kwargs:
            kwargs["text"] = safe_pdf_text(kwargs["text"])
        if "txt" in kwargs:
            kwargs["txt"] = safe_pdf_text(kwargs["txt"])
        if "text" not in kwargs and "txt" not in kwargs and len(args) >= 3:
            args[2] = safe_pdf_text(args[2])
        return tuple(args), kwargs

    def translated_cell(self, *args, **kwargs):
        args, kwargs = _translate_pdf_args(args, kwargs)
        return original_cell(self, *args, **kwargs)

    def translated_multi_cell(self, *args, **kwargs):
        args, kwargs = _translate_pdf_args(args, kwargs)
        return original_multi_cell(self, *args, **kwargs)

    FPDF.cell = translated_cell
    FPDF.multi_cell = translated_multi_cell
    FPDF._savia_i18n_patched = True


_patch_pdf_text_translation()


def _fmt_number(n):
    try:
        val = int(round(float(n)))
        s = str(abs(val))
        result = ""
        for i, c in enumerate(reversed(s)):
            if i > 0 and i % 3 == 0:
                result = " " + result
            result = c + result
        return ("-" if val < 0 else "") + result
    except Exception:
        return str(n)


class SaviaPDF(FPDF):
    """FPDF subclass with auto-repeated compact header on every page."""
    _savia_logo   = None    # path
    _client_logo  = None    # BytesIO (seekable)
    _company_name = ''
    _company_sub  = ''
    _report_title = ''     # centered between logos
    HEADER_H = 26           # header height mm

    def header(self):
        from io import BytesIO
        H = self.HEADER_H
        y0 = 5
        W  = self.w - 16   # 8mm each side

        # ── SAVIA logo (left) ──────────────────────────────────────
        savia_w = 0
        if self._savia_logo and os.path.exists(self._savia_logo):
            try:
                logo_h = (H - 4) * 0.28
                self.image(self._savia_logo, x=8, y=y0 + (H - 4 - logo_h) / 2, h=logo_h)
                savia_w = 8
            except Exception:
                savia_w = 0

        # ── Client logo (right) ───────────────────────────────────
        client_w = 0
        if self._client_logo:
            try:
                self._client_logo.seek(0)
                self.image(self._client_logo, x=self.w - 8 - 28, y=y0, h=H - 4)
                client_w = 30
            except Exception:
                client_w = 0

        # ── Center zone: report title + company name ───────────────
        cx = 8 + savia_w + 2
        cw = W - savia_w - client_w - 4

        # Report title (top, bold, centered between logos)
        if self._report_title:
            self.set_xy(cx, y0 + 1)
            self.set_font('Helvetica', 'B', 11)
            self.set_text_color(30, 40, 55)
            self.cell(cw, 7, _sanitize(self._report_title[:70]), align='C')

        # Company name (below title, smaller)
        if self._company_name:
            y_cn = y0 + 9 if self._report_title else y0 + 4
            self.set_xy(cx, y_cn)
            self.set_font('Helvetica', 'B', 9)
            self.set_text_color(1, 180, 188)
            self.cell(cw, 6, _sanitize(self._company_name[:55]), align='C')
            if self._company_sub:
                self.set_xy(cx, y_cn + 6)
                self.set_font('Helvetica', '', 7)
                self.set_text_color(130, 145, 160)
                self.cell(cw, 4.5, _sanitize(self._company_sub[:90]), align='C')

        # ── Separator line ─────────────────────────────────────────
        sep = y0 + H
        self.set_fill_color(1, 180, 188)
        self.rect(8, sep, self.w - 16, 0.8, style='F')
        self.set_y(sep + 3)
        self.set_text_color(40, 50, 65)

    def set_header_data(self, savia_logo, client_logo_bytes, company_name, company_sub, report_title=""):
        self._savia_logo   = savia_logo
        self._client_logo  = client_logo_bytes
        self._company_name = company_name
        self._company_sub  = company_sub
        self._report_title = report_title



class PdfRequest(BaseModel):
    title: str = "Rapport SAVIA"
    subtitle: str = ""
    filename: str = "rapport"
    company_name: str = "SAVIA"
    company_logo: str = ""
    kpis: list = []
    head: list = []
    rows: list = []
    tables: list = []  # List of {title, head, rows} dicts
    type_data: list = []
    table_title: str = ""
    is_ai_report: bool = False
    ai_content: str = ""

__all__ = [
    "_sanitize",
    "_patch_pdf_text_translation",
    "_fmt_number",
    "SaviaPDF",
    "PdfRequest",
]

