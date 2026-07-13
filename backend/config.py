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

# --- Création des dossiers nécessaires ---
os.makedirs(LOGS_DIR, exist_ok=True)

