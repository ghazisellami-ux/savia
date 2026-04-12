# ==========================================
# ⚙️ CONFIGURATION CENTRALISÉE
# ==========================================
import os
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key, default=""):
    """Lit une variable depuis .env (local) ou st.secrets (Streamlit Cloud)."""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


# --- Clés et sécurité ---
GOOGLE_API_KEY = _get_secret("GOOGLE_API_KEY")

# Support multi-clés pour rotation automatique (séparées par des virgules)
_raw_keys = _get_secret("GOOGLE_API_KEYS")
GOOGLE_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
# Fallback : si pas de multi-clés, utiliser la clé unique
if not GOOGLE_API_KEYS and GOOGLE_API_KEY:
    GOOGLE_API_KEYS = [GOOGLE_API_KEY]

_mk = _get_secret("MASTER_KEY")
MASTER_KEY = _mk.encode() if _mk else b""
ACCESS_CODE = _get_secret("ACCESS_CODE", "SIC2026")

# --- Chemins ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
EXCEL_PATH = os.path.join(BASE_DIR, "knowledge_base.xlsx")

# --- Création des dossiers nécessaires ---
os.makedirs(LOGS_DIR, exist_ok=True)

# --- Types d'équipements radiologie ---
TYPES_EQUIPEMENTS = [
    "Scanner CT",
    "IRM",
    "Radiographie Numérique (DR)",
    "Table Télécommandée",
    "Échographe",
    "Mammographe",
    "Panoramique Dentaire",
    "Cone Beam (CBCT)",
    "Arceau Chirurgical (C-Arm)",
    "Ostéodensitomètre",
    "Angiographe",
    "PET-Scan",
    "Gamma Caméra",
    "Accélérateur Linéaire",
    "Lithotripteur",
    "Fluoroscopie",
    "Développeuse",
    "Imprimante DICOM",
    "Station PACS/RIS",
    "Injecteur de Contraste",
    "Générateur HT",
    "Tube Radiogène",
    "Capteur Plan",
    "Autre",
]

# --- Types d'erreurs ---
TYPES_ERREURS = [
    "Hardware",
    "Software",
    "Power",
    "Rotation",
    "Thermal",
    "Network",
    "Calibration",
    "Tube RX",
    "Détecteur",
    "Autre",
]

# --- Seuils prédictifs ---
SEUIL_SANTE_CRITIQUE = 30      # Score < 30 = critique
SEUIL_SANTE_ATTENTION = 60     # Score < 60 = attention
SEUIL_TENDANCE_ALERTE = 1.5    # Ratio > 1.5 = tendance haussière dangereuse

# --- Feuilles Excel ---
SHEET_CODES = "CODES_HEXA"
SHEET_SOLUTIONS = "SOLUTIONS_TEXTE"
SHEET_HISTORIQUE = "HISTORIQUE"
SHEET_EQUIPEMENTS = "EQUIPEMENTS"

# --- Colonnes feuille HISTORIQUE ---
COLS_HISTORIQUE = ["Date", "Machine", "Code", "Type", "Severite", "Resolu"]

# --- Colonnes feuille EQUIPEMENTS ---
COLS_EQUIPEMENTS = [
    "DateInstallation", "DernieresMaintenance", "Statut", "Notes"
]

# --- MQTT IoT Configuration (désactivé pour le moment) ---
# MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.hivemq.com")
# MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
# MQTT_TOPIC = os.getenv("MQTT_TOPIC", "sic/telemetry/#")

