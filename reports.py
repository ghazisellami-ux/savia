# ==========================================
# GÉNÉRATEUR DE RAPPORTS PDF
# ==========================================
"""
Génère des rapports PDF mensuels avec :
- État du parc, KPIs, interventions, alertes, recommandations
- Mise en page professionnelle avec en-tête SAVIA
"""
import os
from datetime import datetime, timedelta
from fpdf import FPDF
from config import BASE_DIR
from db_engine import get_config
import pandas as pd

REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def _safe(text):
    """Sanitize text for PDF: replace Unicode chars not supported by Helvetica."""
    s = str(text)
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2026", "...").replace("\u00a0", " ")
    return s.encode('latin-1', 'replace').decode('latin-1')


def _fmt_cost(value, devise="TND"):
    """Format cost with space-separated thousands."""
    try:
        v = float(value)
        return f"{v:,.0f}".replace(",", " ") + f" {devise}"
    except (ValueError, TypeError):
        return f"0 {devise}"


# Section colors (matches IA report style)
SECTION_COLORS = {
    1: (30, 58, 138),      # blue - Parc
    2: (139, 92, 246),     # purple - KPIs
    3: (6, 182, 212),      # cyan - Interventions
    4: (239, 68, 68),      # red - Critiques
    5: (16, 185, 129),     # green - Recommandations
}


class RapportPDF(FPDF):
    """PDF professionnel avec en-tête SAVIA."""

    def __init__(self, org_name="SIC Radiologie", logo_path=""):
        super().__init__()
        self.org_name = org_name
        self.logo_path = logo_path
        self.savia_logo = os.path.join(BASE_DIR, "assets", "logo_savia.png")
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        # Logo SAVIA (gauche)
        if os.path.exists(self.savia_logo):
            try:
                self.image(self.savia_logo, 10, 8, 35)
            except Exception:
                pass
        # Logo client (droite)
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                self.image(self.logo_path, 170, 8, 25)
            except Exception:
                pass
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(30, 58, 138)
        self.cell(0, 10, _safe(self.org_name), align="C")
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
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}} - {_safe(self.org_name)} - {datetime.now().strftime('%d/%m/%Y')}",
                  align="C")

    @property
    def ew(self):
        """Effective width respecting margins."""
        return self.w - self.l_margin - self.r_margin

    def section_title(self, titre, color=(30, 58, 138)):
        """Colored section header like IA report."""
        self.ln(4)
        self.set_font("Helvetica", "B", 11)
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.cell(self.ew, 8, f"  {_safe(titre)}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def kpi_card(self, label, value, color=(30, 58, 138)):
        """KPI row with colored value."""
        self.set_x(self.l_margin + 4)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(60, 60, 60)
        lw = self.get_string_width(_safe(label)) + 4
        self.cell(lw, 7, _safe(label))
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*color)
        self.cell(0, 7, _safe(str(value)), ln=True)
        self.set_text_color(0, 0, 0)

    def bullet(self, text, color=(30, 58, 138)):
        """Bullet point with colored dot."""
        self.set_x(self.l_margin + 6)
        self.set_fill_color(*color)
        bx = self.get_x()
        by = self.get_y() + 2
        self.circle(bx, by, 1.2, style="F")
        self.set_x(bx + 4)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        self.multi_cell(self.ew - 10, 5, _safe(text))
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def bullet_bold(self, label, value, color=(30, 58, 138)):
        """Bullet with bold label and normal value."""
        self.set_x(self.l_margin + 6)
        self.set_fill_color(*color)
        bx = self.get_x()
        by = self.get_y() + 2
        self.circle(bx, by, 1.2, style="F")
        self.set_x(bx + 4)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*color)
        lw = self.get_string_width(_safe(label) + " : ") + 2
        self.cell(lw, 5, _safe(label) + " : ")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        remaining = self.ew - 10 - lw
        if remaining > 20:
            self.multi_cell(remaining, 5, _safe(str(value)))
        else:
            self.ln(5)
            self.set_x(self.l_margin + 10)
            self.multi_cell(self.ew - 10, 5, _safe(str(value)))
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def priority_bullet(self, text, level="normal"):
        """Colored bullet based on priority level."""
        colors = {
            "haute": (220, 38, 38),
            "moyenne": (234, 179, 8),
            "basse": (34, 197, 94),
            "normal": (30, 58, 138),
        }
        color = colors.get(level, colors["normal"])
        self.set_x(self.l_margin + 6)
        self.set_fill_color(*color)
        bx = self.get_x()
        by = self.get_y() + 2
        self.circle(bx, by, 1.5, style="F")
        self.set_x(bx + 4)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*color)
        # Extract label if colon exists
        if ":" in text:
            parts = text.split(":", 1)
            lw = self.get_string_width(_safe(parts[0]) + " : ") + 2
            self.cell(lw, 5, _safe(parts[0]) + " : ")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(40, 40, 40)
            remaining = self.ew - 10 - lw
            if remaining > 20:
                self.multi_cell(remaining, 5, _safe(parts[1].strip()))
            else:
                self.ln(5)
                self.set_x(self.l_margin + 10)
                self.multi_cell(self.ew - 10, 5, _safe(parts[1].strip()))
        else:
            self.multi_cell(self.ew - 10, 5, _safe(text))
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def table_header(self, colonnes, widths):
        """Table header with white background and blue text."""
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(255, 255, 255)
        self.set_text_color(30, 58, 138)
        for i, col in enumerate(colonnes):
            self.cell(widths[i], 7, _safe(col), border=1, fill=True, align="C")
        self.ln()
        self.set_text_color(0, 0, 0)

    def table_row(self, values, widths, fill=False):
        """Table data row with white background and black text."""
        self.set_font("Helvetica", "", 7)
        self.set_fill_color(255, 255, 255)
        self.set_text_color(0, 0, 0)
        for i, val in enumerate(values):
            text = _safe(val)[:30]
            self.cell(widths[i], 6, text, border=1, fill=True, align="C")
        self.ln()


def generer_rapport_mensuel(mois=None, annee=None):
    """Génère le rapport PDF mensuel complet avec mise en page professionnelle."""
    from db_engine import lire_equipements, get_db
    from database import lire_interventions

    now = datetime.now()
    mois = mois or now.month
    annee = annee or now.year

    org_name = get_config("nom_organisation", "SIC Radiologie")
    logo_path = get_config("logo_path", "")
    devise = get_config("devise", "EUR")

    pdf = RapportPDF(org_name=org_name, logo_path=logo_path)
    pdf.alias_nb_pages()
    pdf.add_page()

    # === TITRE ===
    mois_noms = ["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre"]
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 12, f"RAPPORT MENSUEL - {mois_noms[mois - 1].upper()} {annee}", align="C")
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, f"Periode : 01/{mois:02d}/{annee} - {mois_noms[mois - 1]} {annee}", align="C")
    pdf.ln(10)

    # === SECTION 1: NOUVEAUX ÉQUIPEMENTS & CLIENTS ===
    pdf.section_title("1. NOUVEAUX EQUIPEMENTS & CLIENTS", SECTION_COLORS[1])

    df_equip = lire_equipements()
    prefix_mois = f"{annee}-{mois:02d}"

    # Filter equipments added during this month (by date_installation)
    df_new_equip = pd.DataFrame()
    if not df_equip.empty and "DateInstallation" in df_equip.columns:
        df_equip["_date_inst"] = pd.to_datetime(df_equip["DateInstallation"], errors="coerce")
        df_new_equip = df_equip[
            (df_equip["_date_inst"].dt.month == mois) &
            (df_equip["_date_inst"].dt.year == annee)
        ]

    # Show total park as context
    pdf.kpi_card("Parc total actuel", f"{len(df_equip)} equipement(s)", SECTION_COLORS[1])
    pdf.kpi_card("Nouveaux ce mois", f"{len(df_new_equip)} equipement(s)", (16, 185, 129) if len(df_new_equip) > 0 else (100, 100, 100))
    pdf.ln(3)

    # New equipments table
    if not df_new_equip.empty:
        ew_cols = ["Nom", "Type", "Client", "Fabricant"]
        available_cols = [c for c in ew_cols if c in df_new_equip.columns]
        if available_cols:
            col_widths = {
                "Nom": 50, "Type": 35, "Client": 50, "Fabricant": 40,
            }
            widths = [col_widths.get(c, 40) for c in available_cols]
            # Adjust last column to fill
            total_w = sum(widths)
            if total_w < pdf.ew:
                widths[-1] += pdf.ew - total_w
            pdf.table_header(available_cols, widths)
            for i, (_, row) in enumerate(df_new_equip.iterrows()):
                pdf.table_row(
                    [str(row.get(c, ""))[:25] for c in available_cols],
                    widths, fill=(i % 2 == 1)
                )
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 7, "Pas de nouvel equipement ajoute pendant ce mois.", ln=True)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(3)

    # New clients (clients that appear in new equipments but not in older ones)
    if not df_equip.empty and "Client" in df_equip.columns:
        if not df_new_equip.empty:
            new_clients_set = set(df_new_equip["Client"].fillna("Non specifie").unique())
            old_equip = df_equip[~df_equip.index.isin(df_new_equip.index)]
            old_clients_set = set(old_equip["Client"].fillna("Non specifie").unique()) if not old_equip.empty else set()
            truly_new_clients = new_clients_set - old_clients_set

            if truly_new_clients:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(*SECTION_COLORS[1])
                pdf.cell(0, 6, f"  Nouveaux clients ({len(truly_new_clients)}) :", ln=True)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(1)
                cw = [70, pdf.ew - 70]
                pdf.table_header(["Client", "Equipements ajoutes"], cw)
                for i, client in enumerate(sorted(truly_new_clients)):
                    nb = len(df_new_equip[df_new_equip["Client"] == client])
                    pdf.table_row([str(client), str(nb)], cw, fill=(i % 2 == 1))
            else:
                pdf.set_font("Helvetica", "I", 10)
                pdf.set_text_color(100, 100, 100)
                pdf.cell(0, 7, "Pas de nouveau client ajoute pendant ce mois.", ln=True)
                pdf.set_text_color(0, 0, 0)
        else:
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 7, "Pas de nouveau client ajoute pendant ce mois.", ln=True)
            pdf.set_text_color(0, 0, 0)

    # === SECTION 2: KPIs ===
    pdf.section_title("2. INDICATEURS CLES (KPIs)", SECTION_COLORS[2])

    df_interv = lire_interventions()
    if not df_interv.empty and "date" in df_interv.columns:
        df_interv["Date_dt"] = pd.to_datetime(df_interv["date"], errors="coerce")
        debut = datetime(annee, mois, 1)
        fin = datetime(annee, mois + 1, 1) if mois < 12 else datetime(annee + 1, 1, 1)
        mask = (df_interv["Date_dt"] >= debut) & (df_interv["Date_dt"] < fin)
        df_mois = df_interv[mask]
    else:
        df_mois = df_interv.head(0)

    nb_interv = len(df_mois)
    cout_total = df_mois["cout"].fillna(0).sum() if not df_mois.empty and "cout" in df_mois.columns else 0
    cout_pieces = df_mois["cout_pieces"].fillna(0).sum() if not df_mois.empty and "cout_pieces" in df_mois.columns else 0
    duree_totale = df_mois["duree_minutes"].fillna(0).sum() if not df_mois.empty and "duree_minutes" in df_mois.columns else 0
    duree_moy = df_mois["duree_minutes"].fillna(0).mean() if not df_mois.empty and "duree_minutes" in df_mois.columns else 0

    critiques = 0
    if not df_mois.empty and "statut" in df_mois.columns:
        critiques = len(df_mois[df_mois["statut"].astype(str).str.upper().isin(["A TRAITER", "URGENT", "CRITIQUE"])])

    nb_cloturees = 0
    if not df_mois.empty and "statut" in df_mois.columns:
        nb_cloturees = len(df_mois[df_mois["statut"].fillna("").str.contains("lotur", case=False)])

    pdf.kpi_card("Interventions realisees", nb_interv, SECTION_COLORS[2])
    pdf.kpi_card("Interventions cloturees", nb_cloturees, (16, 185, 129))
    pdf.kpi_card("Alertes critiques", critiques, (239, 68, 68) if critiques > 0 else (16, 185, 129))
    pdf.ln(2)
    pdf.kpi_card("Cout total maintenance", _fmt_cost(cout_total, devise), SECTION_COLORS[2])
    pdf.kpi_card("Cout pieces detachees", _fmt_cost(cout_pieces, devise), SECTION_COLORS[2])
    pdf.kpi_card("Cout global", _fmt_cost(cout_total + cout_pieces, devise), (30, 58, 138))
    pdf.ln(2)
    pdf.kpi_card("Duree totale", f"{duree_totale / 60:.1f} heures", SECTION_COLORS[2])
    pdf.kpi_card("Duree moyenne / intervention", f"{duree_moy / 60:.1f} heures", SECTION_COLORS[2])

    # Types d'interventions
    if not df_mois.empty and "type_intervention" in df_mois.columns:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*SECTION_COLORS[2])
        pdf.cell(0, 6, "  Repartition par type :", ln=True)
        pdf.set_text_color(0, 0, 0)
        type_counts = df_mois["type_intervention"].value_counts()
        for type_name, count in type_counts.items():
            pct = count / nb_interv * 100 if nb_interv > 0 else 0
            pdf.bullet(f"{type_name} : {count} ({pct:.0f}%)", SECTION_COLORS[2])

    # === SECTION 3: DÉTAIL DES INTERVENTIONS ===
    if nb_interv > 0:
        pdf.section_title("3. DETAIL DES INTERVENTIONS", SECTION_COLORS[3])

        widths = [22, 35, 28, 25, 50, 22]
        pdf.table_header(["Date", "Machine", "Technicien", f"Cout ({devise})", "Description", "Statut"], widths)
        for i, (_, row) in enumerate(df_mois.sort_values("date", ascending=False).head(30).iterrows()):
            if pdf.get_y() > 255:
                pdf.add_page()
                pdf.table_header(["Date", "Machine", "Technicien", f"Cout ({devise})", "Description", "Statut"], widths)
            cout_val = row.get("cout", 0) or 0
            pdf.table_row([
                str(row.get("date", ""))[:10],
                str(row.get("machine", ""))[:20],
                str(row.get("technicien", ""))[:16],
                _fmt_cost(cout_val, devise),
                str(row.get("description", ""))[:28],
                str(row.get("statut", "")),
            ], widths, fill=(i % 2 == 1))

        # Total row
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(widths[0] + widths[1] + widths[2], 7,
                 f"TOTAL ({nb_interv} interventions)", border=1, fill=True, align="R")
        pdf.cell(widths[3], 7, _safe(_fmt_cost(cout_total, devise)), border=1, fill=True, align="C")
        pdf.cell(widths[4] + widths[5], 7, "", border=1, fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)

    # === SECTION 4: ÉVÉNEMENTS CRITIQUES ===
    if critiques > 0:
        pdf.section_title("4. EVENEMENTS CRITIQUES", SECTION_COLORS[4])
        df_crit = df_mois[df_mois["statut"].astype(str).str.upper().isin(["A TRAITER", "URGENT", "CRITIQUE"])]
        for _, row in df_crit.head(10).iterrows():
            machine = str(row.get("machine", "?"))
            desc = str(row.get("description", ""))[:60]
            date_str = str(row.get("date", ""))[:10]
            pdf.priority_bullet(f"{machine} ({date_str}) : {desc}", "haute")

    # === SECTION 5: RECOMMANDATIONS ===
    pdf.section_title("5. RECOMMANDATIONS", SECTION_COLORS[5])

    if critiques > 3:
        pdf.priority_bullet(
            "URGENT : Nombre eleve d'incidents critiques. Inspection approfondie recommandee.", "haute")
    if cout_total + cout_pieces > 5000:
        pdf.priority_bullet(
            f"Budget : Le cout de maintenance ({_fmt_cost(cout_total + cout_pieces, devise)}) "
            "est significatif. Evaluer le remplacement des equipements ages.", "moyenne")
    if nb_interv == 0:
        pdf.priority_bullet(
            "Donnees : Aucune intervention enregistree. Verifier la saisie des donnees.", "moyenne")

    pdf.bullet("Maintenir le calendrier de maintenance preventive a jour.", SECTION_COLORS[5])
    pdf.bullet("Verifier les stocks de pieces de rechange critiques.", SECTION_COLORS[5])
    pdf.bullet("Former les techniciens sur les nouvelles procedures.", SECTION_COLORS[5])

    # === SIGNATURE ===
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 7, "Signature Responsable :", border=0)
    pdf.cell(95, 7, "Signature Direction :", border=0)
    pdf.ln(22)
    pdf.cell(95, 0, "", border="T")
    pdf.cell(95, 0, "", border="T")

    # Sauvegarder
    filename = f"rapport_{annee}_{mois:02d}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)
    pdf.output(filepath)

    return filepath
