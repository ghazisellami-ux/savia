# ==========================================
# 🎨 THÈME MÉDICAL "STITCH" (Slate & Teal)
# ==========================================
from functools import lru_cache

@lru_cache(maxsize=1)
def get_custom_css():
    """Retourne le CSS complet du thème médical propre et moderne."""
    return """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" media="print" onload="this.media='all'">
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap" media="print" onload="this.media='all'">
    <style>

    /* === VARIABLES GLOBALES === */
    :root {
        /* Palette "Medical Slate" */
        --bg-primary: #0f172a;       /* Slate 900 */
        --bg-secondary: #1e293b;     /* Slate 800 */
        --bg-card: rgba(30, 41, 59, 0.7);
        --bg-card-hover: rgba(51, 65, 85, 0.8); /* Slate 700 */
        
        --border-color: rgba(148, 163, 184, 0.15); /* Slate 400 alpha */
        --border-scent: rgba(45, 212, 191, 0.3);   /* Teal scent */
        
        --text-primary: #f8fafc;     /* Slate 50 */
        --text-secondary: #94a3b8;   /* Slate 400 */
        --text-muted: #64748b;       /* Slate 500 */
        
        /* Accents */
        --accent-medical: #2dd4bf;   /* Teal 400 - Main Brand */
        --accent-info: #38bdf8;      /* Sky 400 */
        --accent-warn: #fbbf24;      /* Amber 400 */
        --accent-danger: #f87171;    /* Red 400 */
        --accent-success: #34d399;   /* Emerald 400 */
        
        /* Gradients */
        --gradient-primary: linear-gradient(135deg, #2dd4bf 0%, #06b6d4 100%);
        --gradient-card: linear-gradient(145deg, rgba(30,41,59,0.6) 0%, rgba(15,23,42,0.8) 100%);
        
        /* Effects */
        --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        --shadow-glow: 0 0 20px rgba(45, 212, 191, 0.15);
        
        --radius-pill: 9999px;
        --radius-lg: 16px;
        --radius-md: 12px;
    }

    /* === GLOBAL RESET === */
    .stApp {
        background: var(--bg-primary) !important;
        font-family: 'Inter', system-ui, sans-serif !important;
        color: var(--text-primary) !important;
    }
    
    /* Header invisible mais présent layout */
    .stApp > header { background: transparent !important; }
    
    /* Remonter tout le contenu principal (supprimer l'espace vide en haut) */
    .stApp .block-container {
        padding-top: 2rem !important; /* Au lieu des 6rem par défaut */
    }

    /* === SIDEBAR MODERNE === */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%) !important;
        border-right: 1px solid var(--border-color) !important;
        box-shadow: 4px 0 24px rgba(0,0,0,0.2);
    }
    
    /* Réduire le padding par défaut en haut de la sidebar pour tout remonter */
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem !important;
    }

    /* Option-menu dans la sidebar : fond transparent pour cohérence dark */
    section[data-testid="stSidebar"] iframe {
        background-color: transparent !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stCustomComponentV1"] {
        background-color: transparent !important;
    }
    /* Override fond blanc interne du composant option-menu */
    section[data-testid="stSidebar"] .nav-link {
        color: #94a3b8 !important;
    }
    section[data-testid="stSidebar"] .nav-link.active,
    section[data-testid="stSidebar"] .nav-link:hover {
        color: #2dd4bf !important;
    }
    
    section[data-testid="stSidebar"] .stMarkdown h1 {
        font-size: 1.5rem !important;
        background: var(--gradient-primary);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800 !important;
        padding-bottom: 1rem;
        border-bottom: 1px solid var(--border-color);
        margin-bottom: 1rem;
    }

    /* === TYPOGRAPHY === */
    h1, h2, h3 {
        color: var(--text-primary) !important;
        font-weight: 700 !important;
        letter-spacing: -0.025em !important;
    }
    h1 { font-size: 2.25rem !important; }
    h2 { font-size: 1.5rem !important; margin-top: 1.5rem !important; }
    h3 { font-size: 1.125rem !important; color: var(--accent-medical) !important; }
    
    code {
        font-family: 'JetBrains Mono', monospace !important;
        background: rgba(0,0,0,0.3) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 4px !important;
    }

    /* === CARDS & CONTAINERS === */
    /* Métriques (KPI) */
    div[data-testid="stMetric"] {
        background: var(--bg-card) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius-lg) !important;
        padding: 24px !important;
        box-shadow: var(--shadow-md) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease !important;
        text-align: center !important;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: var(--shadow-lg), var(--shadow-glow) !important;
        border-color: var(--border-scent) !important;
    }
    div[data-testid="stMetric"] label {
        color: var(--text-secondary) !important;
        font-weight: 600 !important;
        font-size: 0.875rem !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: var(--main_white) !important;
        font-size: 1.875rem !important;
        font-weight: 800 !important;
    }

    /* === BOUTONS (PILL SHAPE - Stitch Style) === */
    .stButton > button {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius-pill) !important;
        padding: 0.5rem 1.5rem !important;
        font-weight: 500 !important;
        font-size: 0.9375rem !important;
        transition: all 0.2s ease !important;
        box-shadow: var(--shadow-sm) !important;
    }
    .stButton > button:hover {
        background: var(--bg-card-hover) !important;
        border-color: var(--accent-medical) !important;
        color: var(--accent-medical) !important;
        transform: translateY(-1px) !important;
        box-shadow: var(--shadow-md) !important;
    }
    /* Bouton Primaire (Submit) - Souvent le dernier d'un form */
    div[data-testid="stForm"] .stButton > button {
        background: var(--gradient-primary) !important;
        color: #0f172a !important;
        border: none !important;
        font-weight: 600 !important;
    }
    div[data-testid="stForm"] .stButton > button:hover {
        opacity: 0.9 !important;
        box-shadow: 0 0 15px rgba(45, 212, 191, 0.4) !important;
    }

    /* === INPUTS & FORMS === */
    .stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stNumberInput input, .stTextArea textarea {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius-md) !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: var(--accent-medical) !important;
        box-shadow: 0 0 0 2px rgba(45, 212, 191, 0.2) !important;
    }

    /* === DATAFRAMES & TABLES === */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius-lg) !important;
        overflow: hidden !important;
    }
    /* Forcer le fond sombre des iframes de dataframes */
    div[data-testid="stDataFrame"] iframe {
        background-color: #0f172a !important;
    }
    /* Glide Data Grid (composant interne des dataframes Streamlit) */
    div[data-testid="stDataFrame"] > div {
        background-color: #0f172a !important;
    }
    /* Tables HTML classiques dans st.markdown */
    .stMarkdown table {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border-collapse: collapse !important;
        width: 100% !important;
        border-radius: var(--radius-md) !important;
        overflow: hidden !important;
    }
    .stMarkdown table th {
        background-color: #0f172a !important;
        color: #2dd4bf !important;
        padding: 12px 16px !important;
        border-bottom: 2px solid rgba(45, 212, 191, 0.3) !important;
        font-weight: 700 !important;
        text-align: left !important;
    }
    .stMarkdown table td {
        padding: 10px 16px !important;
        border-bottom: 1px solid rgba(148, 163, 184, 0.1) !important;
        color: #e2e8f0 !important;
    }
    .stMarkdown table tr:hover td {
        background-color: rgba(45, 212, 191, 0.05) !important;
    }
    /* st.table() spécifique */
    div[data-testid="stTable"] table {
        background-color: #1e293b !important;
        color: #f8fafc !important;
    }
    div[data-testid="stTable"] th {
        background-color: #0f172a !important;
        color: #2dd4bf !important;
        border-bottom: 2px solid rgba(45, 212, 191, 0.3) !important;
    }
    div[data-testid="stTable"] td {
        border-bottom: 1px solid rgba(148, 163, 184, 0.1) !important;
        color: #e2e8f0 !important;
    }
    
    /* === TABS (Navigation Onglets) === */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem !important;
        border-bottom: 2px solid var(--border-color) !important;
        margin-bottom: 1.5rem !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: auto !important;
        padding: 0.5rem 0 !important;
        background: transparent !important;
        border: none !important;
        color: var(--text-secondary) !important;
        font-weight: 500 !important;
    }
    .stTabs [aria-selected="true"] {
        color: var(--accent-medical) !important;
        border-bottom: 2px solid var(--accent-medical) !important;
    }
    .stTabs [data-baseweb="tab-highlight"] { display: none !important; }

    /* === ALERTS (Toast styles) === */
    div[data-testid="stAlert"] {
        border-radius: var(--radius-md) !important;
        border: 1px solid transparent !important;
    }
    .stSuccess { background: rgba(52, 211, 153, 0.1) !important; border-color: rgba(52, 211, 153, 0.2) !important; color: #34d399 !important; }
    .stInfo { background: rgba(56, 189, 248, 0.1) !important; border-color: rgba(56, 189, 248, 0.2) !important; color: #38bdf8 !important; }
    .stWarning { background: rgba(251, 191, 36, 0.1) !important; border-color: rgba(251, 191, 36, 0.2) !important; color: #fbbf24 !important; }
    .stError { background: rgba(248, 113, 113, 0.1) !important; border-color: rgba(248, 113, 113, 0.2) !important; color: #f87171 !important; }

    /* === EXPANDER === */
    .streamlit-expanderHeader {
        background: var(--bg-secondary) !important;
        border-radius: var(--radius-md) !important;
        border: 1px solid var(--border-color) !important;
    }
    .streamlit-expanderContent {
        border: 1px solid var(--border-color) !important;
        border-top: none !important;
        border-bottom-left-radius: var(--radius-md) !important;
        border-bottom-right-radius: var(--radius-md) !important;
        background: rgba(30, 41, 59, 0.3) !important;
    }
    
    /* === SCROLLBAR FINES === */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #475569; }

    /* === ANIMATIONS PREMIUM === */
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes pulseGlow {
        0%, 100% { box-shadow: 0 0 8px rgba(45, 212, 191, 0.2); }
        50% { box-shadow: 0 0 20px rgba(45, 212, 191, 0.4); }
    }
    @keyframes shimmer {
        0% { background-position: -200% 0; }
        100% { background-position: 200% 0; }
    }
    @keyframes floatUp {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-6px); }
    }
    @keyframes gradientFlow {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    @keyframes borderGlow {
        0%, 100% { border-color: rgba(45, 212, 191, 0.2); }
        50% { border-color: rgba(45, 212, 191, 0.5); }
    }

    /* Titres de page avec animation */
    .stApp h1 {
        animation: fadeInUp 0.5s ease-out;
    }

    /* KPI cards — fade in animation */
    div[data-testid="stMetric"] {
        animation: fadeInUp 0.4s ease-out;
        border-top: 3px solid transparent !important;
        border-image: linear-gradient(135deg, #2dd4bf, #38bdf8) 1 !important;
    }

    /* Sidebar active nav glow bar */
    section[data-testid="stSidebar"] .nav-link-selected {
        position: relative;
    }
    section[data-testid="stSidebar"] .nav-link-selected::before {
        content: '';
        position: absolute;
        left: 0;
        top: 50%;
        transform: translateY(-50%);
        width: 3px;
        height: 60%;
        background: linear-gradient(180deg, #2dd4bf, #38bdf8);
        border-radius: 0 4px 4px 0;
        box-shadow: 0 0 12px rgba(45, 212, 191, 0.5);
    }

    /* Form inputs — focus animation */
    .stTextInput input:focus, .stTextArea textarea:focus {
        animation: borderGlow 2s ease-in-out infinite !important;
    }

    /* Download buttons — gradient hover */
    .stDownloadButton > button {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: var(--radius-pill) !important;
        color: var(--text-primary) !important;
        transition: all 0.3s ease !important;
    }
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, rgba(45,212,191,0.15), rgba(59,130,246,0.10)) !important;
        border-color: var(--accent-medical) !important;
        transform: translateY(-1px) !important;
    }

    /* Premium Login Page */
    .login-container {
        background: linear-gradient(145deg, rgba(30,41,59,0.9) 0%, rgba(15,23,42,0.95) 100%);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(45, 212, 191, 0.15);
        border-radius: 24px;
        padding: 40px 36px;
        box-shadow: 0 24px 48px rgba(0,0,0,0.4), 0 0 40px rgba(45, 212, 191, 0.08);
        animation: fadeInUp 0.6s ease-out;
    }
    .login-title {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #2dd4bf, #38bdf8, #818cf8);
        background-size: 200% 200%;
        animation: gradientFlow 4s ease infinite;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 4px;
    }
    .login-subtitle {
        color: #64748b;
        text-align: center;
        font-size: 0.85rem;
        margin-bottom: 24px;
    }
    .login-mesh {
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        z-index: -1;
        background:
            radial-gradient(ellipse at 20% 50%, rgba(45,212,191,0.08) 0%, transparent 50%),
            radial-gradient(ellipse at 80% 20%, rgba(56,189,248,0.06) 0%, transparent 50%),
            radial-gradient(ellipse at 50% 80%, rgba(129,140,248,0.05) 0%, transparent 50%);
        pointer-events: none;
    }

    /* Footer SAVIA shimmer */
    .savia-footer-brand {
        background: linear-gradient(90deg, #2dd4bf, #38bdf8, #818cf8, #2dd4bf);
        background-size: 200% 100%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: shimmer 3s linear infinite;
        font-weight: 800;
        font-size: 1.1rem;
        letter-spacing: 2px;
    }

    /* Plotly charts — fade in */
    div[data-testid="stPlotlyChart"] {
        animation: fadeInUp 0.5s ease-out;
    }

    /* Tabs — animated underline */
    .stTabs [aria-selected="true"] {
        transition: all 0.3s ease !important;
    }

    /* Alert pulse for errors */
    .stError {
        animation: fadeInUp 0.3s ease-out;
    }
    .stWarning {
        animation: fadeInUp 0.3s ease-out;
    }

    </style>
    """

def kpi_card(icon, value, label, css_class="", tooltip="", accent_color="#2dd4bf"):
    """Génère le HTML d'une carte KPI stylisée premium — glassmorphisme + gradient top."""
    title_attr = f'title="{tooltip}"' if tooltip else ""
    return f"""
    <div {title_attr} style="
        background: linear-gradient(145deg, rgba(30,41,59,0.7) 0%, rgba(15,23,42,0.8) 100%);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-top: 3px solid {accent_color};
        border-radius: 16px;
        padding: 20px 16px;
        min-height: 140px;
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.15), 0 0 12px rgba(45,212,191,0.04);
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        text-align: center;
        transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
        cursor: {('help' if tooltip else 'default')};
        animation: fadeInUp 0.5s ease-out;
    " onmouseover="this.style.transform='translateY(-4px)';this.style.boxShadow='0 12px 24px rgba(0,0,0,0.25), 0 0 20px rgba(45,212,191,0.12)';this.style.borderColor='{accent_color}50'"
       onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='0 4px 6px -1px rgba(0,0,0,0.15), 0 0 12px rgba(45,212,191,0.04)';this.style.borderColor='rgba(148,163,184,0.12)'">
        <div style="font-size: 1.6rem; margin-bottom: 6px; line-height: 1;">{icon}</div>
        <div style="font-size: 1.7rem; font-weight: 800; color: #f8fafc; line-height: 1.2; margin-bottom: 6px;
            letter-spacing: -0.02em;">{value}</div>
        <div style="color: #94a3b8; font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
            letter-spacing: 0.8px; line-height: 1.3;">{label}</div>
    </div>
    """

def health_badge(score):
    """Badge de santé coloré."""
    color = "#34d399" # Success
    bg = "rgba(52, 211, 153, 0.1)"
    if score < 70: 
        color = "#fbbf24" # Warning
        bg = "rgba(251, 191, 36, 0.1)"
    if score < 40: 
        color = "#f87171" # Danger
        bg = "rgba(248, 113, 113, 0.1)"
        
    return f"""
    <span style="
        background-color: {bg};
        color: {color};
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        border: 1px solid {color}40;
    ">{score}%</span>
    """

def status_dot(level):
    """Point de statut."""
    color = "#34d399"
    if level == "warning": color = "#fbbf24"
    if level == "critical": color = "#f87171"
    
    return f"""
    <div style="
        width: 10px; height: 10px; 
        background-color: {color}; 
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 8px {color}80;
    "></div>
    """

def section_card(title, content_html):
    """Wrapper pour section."""
    return f"""
    <div style="
        background: #1e293b;
        border: 1px solid rgba(148, 163, 184, 0.1);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
    ">
        <h3 style="margin-top: 0; color: #2dd4bf;">{title}</h3>
        {content_html}
    </div>
    """

def plotly_dark_layout():
    """Layout Plotly assorti au thème Slate."""
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, Helvetica, sans-serif", color="#94a3b8", size=12),
        hoverlabel=dict(
            bgcolor="#1e293b",
            font_size=13,
            font_family="Arial, Helvetica, sans-serif",
            bordercolor="#2dd4bf",
        ),
    )

def apply_plotly_defaults(fig):
    """Applique les défauts de grille Plotly."""
    grid_color = "rgba(148, 163, 184, 0.05)"
    fig.update_xaxes(gridcolor=grid_color, zerolinecolor=grid_color)
    fig.update_yaxes(gridcolor=grid_color, zerolinecolor=grid_color)
    fig.update_layout(
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8")),
        margin=dict(l=40, r=20, t=40, b=40),
    )
    return fig

# Palette Graphiques "Material Stitch"
CHART_COLORS = [
    "#2dd4bf", # Teal
    "#38bdf8", # Sky
    "#818cf8", # Indigo
    "#a78bfa", # Violet
    "#fbbf24", # Amber
    "#f87171", # Red
    "#34d399", # Emerald
    "#e879f9", # Fuchsia
]


def status_pill(statut):
    """Génère un badge pill coloré pour les statuts d'intervention."""
    colors = {
        "Clôturée":  ("#34d399", "rgba(52, 211, 153, 0.12)"),
        "Clôturée":  ("#34d399", "rgba(52, 211, 153, 0.12)"),
        "En cours":  ("#38bdf8", "rgba(56, 189, 248, 0.12)"),
        "Ouverte":   ("#fbbf24", "rgba(251, 191, 36, 0.12)"),
        "En retard": ("#f87171", "rgba(248, 113, 113, 0.12)"),
        "Planifiée": ("#818cf8", "rgba(129, 140, 248, 0.12)"),
        "Terminée":  ("#34d399", "rgba(52, 211, 153, 0.12)"),
        "Actif":     ("#34d399", "rgba(52, 211, 153, 0.12)"),
        "Expiré":    ("#f87171", "rgba(248, 113, 113, 0.12)"),
    }
    color, bg = colors.get(statut, ("#94a3b8", "rgba(148, 163, 184, 0.12)"))
    return (
        f'<span style="'
        f'background:{bg}; color:{color}; padding:4px 14px; border-radius:9999px; '
        f'font-size:0.75rem; font-weight:700; border:1px solid {color}30; '
        f'white-space:nowrap; display:inline-block;'
        f'">{statut}</span>'
    )


def avatar_initials(name, size=32):
    """Génère un avatar circulaire avec les initiales d'un technicien."""
    if not name or not name.strip():
        initials = "?"
    else:
        parts = name.strip().split()
        initials = "".join([p[0].upper() for p in parts[:2]])

    # Couleur déterministe basée sur le nom
    palette = ["#2dd4bf", "#38bdf8", "#818cf8", "#a78bfa", "#fbbf24", "#f87171", "#34d399", "#e879f9"]
    idx = sum(ord(c) for c in (name or "?")) % len(palette)
    color = palette[idx]

    return (
        f'<span style="'
        f'width:{size}px; height:{size}px; border-radius:50%; '
        f'background:linear-gradient(135deg, {color}, {color}99); '
        f'color:#0f172a; font-weight:800; font-size:{size//2.5:.0f}px; '
        f'display:inline-flex; align-items:center; justify-content:center; '
        f'box-shadow: 0 0 8px {color}40; flex-shrink:0;'
        f'" title="{name}">{initials}</span>'
    )

def get_tablet_css():
    """CSS additionnel pour le mode Tablette (Android-friendly, tactile).
    Surcouche aggressive pour une différence très visible par rapport au desktop."""
    return """
    <style>
    /* ============================================ */
    /* 📱 MODE TABLETTE — SURCOUCHE ANDROID-FRIENDLY */
    /* ============================================ */

    /* === SIDEBAR RÉDUITE PAR DÉFAUT === */
    section[data-testid="stSidebar"] {
        width: 240px !important;
        min-width: 240px !important;
    }
    /* Masquer la sidebar sur écrans < 768px (mobiles) */
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            transform: translateX(-100%) !important;
        }
        section[data-testid="stSidebar"][aria-expanded="true"] {
            transform: translateX(0) !important;
        }
    }

    /* === ZONE PRINCIPALE PLEINE LARGEUR === */
    .stMainBlockContainer, .block-container {
        max-width: 100% !important;
        padding: 1rem 1.2rem !important;
    }

    /* === POLICE PLUS GRANDE === */
    .stApp {
        font-size: 20px !important;
    }
    .stMarkdown p, .stMarkdown li {
        font-size: 1.1rem !important;
        line-height: 1.7 !important;
    }

    /* === TITRES PLUS GROS ET ESPACÉS === */
    h1 {
        font-size: 2rem !important;
        margin-bottom: 1.5rem !important;
        padding-bottom: 0.8rem !important;
        border-bottom: 2px solid rgba(45, 212, 191, 0.3) !important;
    }
    h2 {
        font-size: 1.5rem !important;
        margin-top: 2rem !important;
        margin-bottom: 1rem !important;
    }
    h3 {
        font-size: 1.2rem !important;
        margin-top: 1.5rem !important;
    }

    /* ==================================================== */
    /* ===      BOUTONS TACTILES TRÈS GRANDS (60px)      === */
    /* ==================================================== */
    .stButton > button {
        min-height: 60px !important;
        padding: 1rem 2.5rem !important;
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        border-radius: 16px !important;
        touch-action: manipulation !important;
        letter-spacing: 0.3px !important;
    }
    .stButton > button:active {
        transform: scale(0.97) !important;
        transition: transform 0.1s !important;
    }
    div[data-testid="stForm"] .stButton > button {
        min-height: 64px !important;
        font-size: 1.2rem !important;
    }
    .stDownloadButton > button {
        min-height: 60px !important;
        padding: 1rem 2.5rem !important;
        font-size: 1.15rem !important;
        border-radius: 16px !important;
        touch-action: manipulation !important;
    }

    /* ==================================================== */
    /* ===      INPUTS TRÈS GRANDS (56px)                === */
    /* ==================================================== */
    .stTextInput input,
    .stNumberInput input {
        min-height: 56px !important;
        font-size: 1.15rem !important;
        padding: 0.8rem 1.2rem !important;
        border-radius: 14px !important;
        touch-action: manipulation !important;
    }
    .stTextArea textarea {
        min-height: 120px !important;
        font-size: 1.1rem !important;
        padding: 0.8rem 1.2rem !important;
        border-radius: 14px !important;
        line-height: 1.6 !important;
    }

    /* Selectbox & Multiselect */
    .stSelectbox div[data-baseweb="select"] > div,
    .stMultiSelect div[data-baseweb="select"] > div {
        min-height: 56px !important;
        font-size: 1.15rem !important;
        border-radius: 14px !important;
    }

    /* DateInput */
    .stDateInput input {
        min-height: 56px !important;
        font-size: 1.15rem !important;
        border-radius: 14px !important;
    }

    /* Labels au-dessus des inputs */
    .stTextInput label, .stTextArea label, .stSelectbox label,
    .stMultiSelect label, .stNumberInput label, .stDateInput label {
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        margin-bottom: 6px !important;
    }

    /* Radio buttons — grands et espacés */
    .stRadio > div {
        gap: 6px !important;
    }
    .stRadio label {
        min-height: 52px !important;
        display: flex !important;
        align-items: center !important;
        padding: 10px 16px !important;
        font-size: 1.1rem !important;
        background: rgba(30, 41, 59, 0.5) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(148, 163, 184, 0.1) !important;
        margin-bottom: 4px !important;
    }
    .stRadio label:active {
        background: rgba(45, 212, 191, 0.15) !important;
    }

    /* Checkbox — plus grand */
    .stCheckbox label {
        min-height: 52px !important;
        display: flex !important;
        align-items: center !important;
        font-size: 1.1rem !important;
        padding: 8px 0 !important;
    }

    /* File uploader */
    .stFileUploader section {
        min-height: 90px !important;
        padding: 1.2rem !important;
        border-radius: 16px !important;
        font-size: 1.1rem !important;
    }

    /* ==================================================== */
    /* ===      METRICS / KPI CARDS PLUS GROS            === */
    /* ==================================================== */
    div[data-testid="stMetric"] {
        padding: 24px 20px !important;
        border-radius: 20px !important;
        margin-bottom: 12px !important;
    }
    div[data-testid="stMetric"] label {
        font-size: 1rem !important;
        font-weight: 700 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 900 !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        font-size: 0.95rem !important;
    }

    /* ==================================================== */
    /* ===      TABS TACTILES SCROLLABLES                === */
    /* ==================================================== */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px !important;
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
        -webkit-overflow-scrolling: touch !important;
        padding-bottom: 4px !important;
    }
    .stTabs [data-baseweb="tab"] {
        min-height: 54px !important;
        padding: 0.7rem 1.2rem !important;
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
        border-radius: 12px 12px 0 0 !important;
        touch-action: manipulation !important;
    }

    /* ==================================================== */
    /* ===      EXPANDER TACTILE                         === */
    /* ==================================================== */
    details summary {
        min-height: 56px !important;
        padding: 14px 18px !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        display: flex !important;
        align-items: center !important;
        border-radius: 14px !important;
    }
    .streamlit-expanderHeader {
        min-height: 56px !important;
        padding: 14px 18px !important;
        font-size: 1.1rem !important;
    }

    /* ==================================================== */
    /* ===      COLONNES → EMPILÉES SUR MOBILE          === */
    /* ==================================================== */
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
        }
        div[data-testid="stHorizontalBlock"] > div {
            width: 100% !important;
            flex: 1 1 100% !important;
        }
    }

    /* Espacement entre colonnes plus grand */
    div[data-testid="stHorizontalBlock"] {
        gap: 1rem !important;
    }

    /* ==================================================== */
    /* ===      SIDEBAR NAVIGATION TACTILE               === */
    /* ==================================================== */
    section[data-testid="stSidebar"] .stRadio label {
        min-height: 54px !important;
        font-size: 1.1rem !important;
        padding: 10px 12px !important;
        border-radius: 12px !important;
        margin-bottom: 4px !important;
    }

    /* ==================================================== */
    /* ===      DATAFRAMES RESPONSIVE                    === */
    /* ==================================================== */
    div[data-testid="stDataFrame"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        border-radius: 16px !important;
    }

    /* ==================================================== */
    /* ===      SCROLLBARS TACTILES (ÉPAISSES)           === */
    /* ==================================================== */
    ::-webkit-scrollbar { width: 16px !important; height: 16px !important; }
    ::-webkit-scrollbar-track { background: rgba(15, 23, 42, 0.5) !important; border-radius: 8px !important; }
    ::-webkit-scrollbar-thumb {
        min-height: 50px !important;
        border-radius: 8px !important;
        background: #475569 !important;
        border: 3px solid transparent !important;
        background-clip: content-box !important;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #64748b !important;
        background-clip: content-box !important;
    }

    /* ==================================================== */
    /* ===      BANNIÈRE MODE TABLETTE                   === */
    /* ==================================================== */
    .tablet-mode-badge {
        background: linear-gradient(135deg, #06b6d4, #3b82f6);
        color: white;
        padding: 5px 16px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 800;
        display: inline-block;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        box-shadow: 0 2px 8px rgba(6, 182, 212, 0.3);
    }

    /* ==================================================== */
    /* ===      TOUCH GÉNÉRAL + ANTI-DOUBLE TAP          === */
    /* ==================================================== */
    * {
        -webkit-tap-highlight-color: rgba(45, 212, 191, 0.2) !important;
    }
    html {
        touch-action: manipulation !important;
    }
    a, button, [role="button"], label, summary, input, select, textarea {
        touch-action: manipulation !important;
    }

    /* ==================================================== */
    /* ===      ESPACEMENT GÉNÉRAL PLUS AÉRÉ             === */
    /* ==================================================== */
    .stMarkdown hr {
        margin: 1.5rem 0 !important;
    }
    div[data-testid="stVerticalBlock"] > div {
        margin-bottom: 4px !important;
    }

    /* === ALERTES PLUS VISIBLES === */
    div[data-testid="stAlert"] {
        padding: 1.2rem 1.5rem !important;
        border-radius: 16px !important;
        font-size: 1.05rem !important;
        margin: 0.8rem 0 !important;
    }

    /* === FORMULAIRES PLUS ESPACÉS === */
    div[data-testid="stForm"] {
        padding: 1.5rem !important;
        border-radius: 20px !important;
        border: 2px solid rgba(148, 163, 184, 0.15) !important;
    }

    /* === POPOVER / DIALOG PLUS GRAND === */
    div[data-testid="stPopover"] button {
        min-height: 56px !important;
        font-size: 1.1rem !important;
    }

    </style>
    """

