# ==========================================
# 📡 SIC — SUPERVISEUR INTELLIGENT CLINIQUE
# Maintenance Prédictive - Radiologie v3.0
# ==========================================
import streamlit as st
from streamlit_option_menu import option_menu

# --- MUST be first Streamlit command ---
st.set_page_config(
    page_title="SIC Radiologie — Maintenance Prédictive",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)
import os
import sys
import uuid
import hashlib
from datetime import datetime, timedelta

# Ajouter le répertoire courant au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from styles import get_custom_css
from db_engine import get_config, init_db
from auth import authentifier, authentifier_par_username, deconnecter, get_current_user, creer_admin_defaut, require_role
from i18n import t, langue_selector, get_lang, set_lang

# --- Initialisation unique (cachée, ne tourne qu'une seule fois) ---
@st.cache_resource
def _one_time_init():
    init_db()
    from db_engine import verifier_et_migrer_schema
    verifier_et_migrer_schema()
    creer_admin_defaut()
    # Auto-restore depuis GitHub si DB vide (Streamlit Cloud)
    try:
        from data_sync import auto_restore_si_vide
        auto_restore_si_vide()
    except Exception:
        pass
    # Auto-seed demo si historique vide
    try:
        from db_engine import get_db
        with get_db() as _conn:
            row = _conn.execute("SELECT COUNT(*) as cnt FROM interventions").fetchone()
            _count = row["cnt"] if row else 0
        if _count == 0:
            from generer_demo_sqlite import generer_demo_sqlite
            generer_demo_sqlite()
    except Exception:
        pass
    # Backup quotidien en arrière-plan (ne bloque pas le chargement)
    import threading
    def _bg_backup():
        try:
            from backup import backup_quotidien
            backup_quotidien()
        except Exception:
            pass
    threading.Thread(target=_bg_backup, daemon=True).start()
    # Démarrage du bot Telegram bidirectionnel — DÉPLACÉ hors du cache
    return True

_one_time_init()

# Lancer le bot Telegram (hors cache pour qu'il redémarre à chaque déploiement)
if "_bot_started" not in st.session_state:
    try:
        from telegram_bot import start_bot_thread
        start_bot_thread()
    except Exception:
        pass
    st.session_state["_bot_started"] = True

# --- Nom de l'organisation (utilisé dans login et header) ---
org_name = get_config("nom_organisation", "SIC Radiologie")



# --- Injection CSS thème sombre médical ---
# st.html() est nécessaire car les nouvelles versions de Streamlit
# strippent les balises <style> de st.markdown(unsafe_allow_html=True)
try:
    st.html(get_custom_css())
except AttributeError:
    # Fallback pour anciennes versions de Streamlit
    st.markdown(get_custom_css(), unsafe_allow_html=True)

# --- Keep-alive WebSocket pour éviter la déconnexion après inactivité ---
st.markdown("""
<script>
    // Heartbeat toutes les 30s pour garder le WebSocket actif
    if (!window._sicKeepAlive) {
        window._sicKeepAlive = setInterval(() => {
            try {
                // Simuler une micro-activité pour empêcher le sleep du WebSocket
                window.dispatchEvent(new Event('streamlit:componentReady'));
            } catch(e) {}
        }, 30000);
    }

    // Auto-reload si la connexion WebSocket est perdue
    if (!window._sicConnCheck) {
        window._sicConnCheck = setInterval(() => {
            const widgets = document.querySelectorAll('[data-testid="stStatusWidget"]');
            widgets.forEach(w => {
                if (w && (w.textContent.includes('Connecting') || w.textContent.includes('Error'))) {
                    clearInterval(window._sicConnCheck);
                    window._sicConnCheck = null;
                    setTimeout(() => window.location.reload(), 5000);
                }
            });
        }, 10000);
    }
</script>
""", unsafe_allow_html=True)

# --- Charger la langue sauvegardée ---
if "lang_loaded" not in st.session_state:
    saved_lang = get_config("langue", "fr")
    set_lang(saved_lang)
    st.session_state["lang_loaded"] = True


# ==========================================
# 🔒 PERSISTANCE DE SESSION (anti-déconnexion)
# ==========================================
_SESSION_MAX_AGE_HOURS = 24

def _create_session_token(username):
    """Crée un token de session persisté en DB."""
    token = str(uuid.uuid4())
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    from db_engine import set_config as _set_cfg
    _set_cfg(f"session_{token_hash}", f"{username}|{datetime.now().isoformat()}")
    return token

def _restore_session(token):
    """Restaure une session à partir d'un token. Retourne le username ou None."""
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    from db_engine import get_config as _get_cfg
    data = _get_cfg(f"session_{token_hash}", "")
    if data and "|" in data:
        parts = data.split("|", 1)
        username = parts[0]
        try:
            ts = datetime.fromisoformat(parts[1])
            if datetime.now() - ts < timedelta(hours=_SESSION_MAX_AGE_HOURS):
                return username
        except Exception:
            pass
    return None

def _invalidate_session(token):
    """Invalide un token de session."""
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    from db_engine import set_config as _set_cfg
    _set_cfg(f"session_{token_hash}", "")


# ==========================================
# VERIFICATION LICENCE
# ==========================================
def check_license():
    """
    Verifie la licence.
    - Si expiree/absente : affiche un ecran d'activation (saisie cle).
    - Si valide : retourne (nom_client, jours_restants).
    """
    from license_manager import verifier_licence, enregistrer_cle_licence

    statut = verifier_licence()

    # --- Licence expiree ou absente : ecran d'activation ---
    if statut["expiree"] or not statut["valide"]:
        st.markdown("<div style='height: 2vh;'></div>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            st.markdown(
                """
                <div class="section-card" style="text-align:center; padding:24px;">
                    <div style="font-size:2rem; margin-bottom:8px;">&#x1F512;</div>
                    <h2 style="margin:0 0 8px 0;">Licence requise</h2>
                    <p style="color:#94a3b8; font-size:0.85rem;">
                        Votre licence a expire ou n'est pas encore activee.<br>
                        Collez la cle d'acces fournie par votre administrateur.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if statut["date_expiration"]:
                st.error(f"Licence expiree le {statut['date_expiration']}")
            else:
                st.warning("Aucune licence active detectee.")

            cle_input = st.text_area(
                "Cle d'acces",
                height=100,
                placeholder="Collez votre cle d'acces ici...",
                key="license_activation_key",
            )
            if st.button("Activer la licence", use_container_width=True, type="primary"):
                ok, msg = enregistrer_cle_licence(cle_input)
                if ok:
                    st.success(msg)
                    st.balloons()
                    st.rerun()
                else:
                    st.error(msg)

            st.markdown("---")
            st.caption("Contactez votre fournisseur SIC Radiologie pour obtenir une cle.")

        st.stop()

    return statut["client"], statut["jours_restants"]


# ==========================================
# 🔑 PAGE DE CONNEXION MULTI-UTILISATEURS
# ==========================================
def page_login():
    """Page de connexion avec username/password — design premium."""
    # Mesh gradient background
    st.markdown('<div class="login-mesh"></div>', unsafe_allow_html=True)

    # Centrer verticalement le contenu (supprime le scroll)
    st.markdown("""
    <style>
        /* Masquer header et footer Streamlit sur la page login */
        header[data-testid="stHeader"] { display: none !important; }
        footer { display: none !important; }
        #MainMenu { display: none !important; }
        /* Centrer le contenu principal verticalement */
        .stMainBlockContainer, [data-testid="stAppViewBlockContainer"] {
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            min-height: 100vh !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        /* Réduire les marges sur le block content */
        .block-container {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        /* Masquer le footer de déploiement */
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        # Logo client
        logo_path = get_config("logo_path", "")
        if logo_path and os.path.exists(logo_path):
            st.image(logo_path, width=100, use_container_width=False)

        st.markdown(
            f"""
            <div class="login-container">
                <div style="text-align:center; margin-bottom:8px;">
                    <span style="font-size:2.5rem;">\U0001f4e1\U0001f3e5</span>
                </div>
                <div class="login-title">{org_name}</div>
                <div class="login-subtitle">
                    {t("login_title")} — Superviseur Intelligent Clinique
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.text_input(t("username"), placeholder="admin")
            password = st.text_input(t("password"), type="password", placeholder="••••••••")

            if st.form_submit_button(t("login_btn"), use_container_width=True, type="primary"):
                user = authentifier(username, password)
                if user:
                    st.session_state["user"] = user
                    st.session_state["authenticated"] = True
                    # Créer un token persistant pour survivre aux déconnexions
                    token = _create_session_token(user["username"])
                    st.session_state["session_token"] = token
                    # Stocker le token dans un cookie via JavaScript
                    st.markdown(f"""
                    <script>
                        document.cookie = "sic_session={token}; path=/; max-age={_SESSION_MAX_AGE_HOURS * 3600}; SameSite=Lax";
                    </script>
                    """, unsafe_allow_html=True)
                    st.rerun()
                else:
                    st.error(t("login_error"))




# ==========================================
# 🚀 APPLICATION PRINCIPALE
# ==========================================

# --- Verification licence (AVANT login) ---
nom_client, jours_restants = check_license()

# --- Verification authentification ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# --- Tentative de restauration de session via cookie (après déconnexion WebSocket) ---
if not st.session_state["authenticated"]:
    # Lire le cookie de session via query params ou header (fallback: JS injection)
    _restored = False
    _token_from_state = st.session_state.get("session_token", "")
    if _token_from_state:
        _username = _restore_session(_token_from_state)
        if _username:
            _user = authentifier_par_username(_username)
            if _user:
                st.session_state["user"] = _user
                st.session_state["authenticated"] = True
                _restored = True

    if not _restored:
        # Injecter un script qui lit le cookie et le passe via query param
        # pour la prochaine exécution du script
        _cookie_js = """
        <script>
            const cookies = document.cookie.split(';');
            let sicToken = '';
            cookies.forEach(c => {
                const [k, v] = c.trim().split('=');
                if (k === 'sic_session') sicToken = v;
            });
            if (sicToken && !window._sicSessionRestored) {
                window._sicSessionRestored = true;
                // Stocker dans sessionStorage pour que Streamlit puisse le lire
                window.sessionStorage.setItem('sic_session_token', sicToken);
                // Forcer un rerun en changeant l'URL avec le token
                const url = new URL(window.location);
                if (!url.searchParams.has('sic_token')) {
                    url.searchParams.set('sic_token', sicToken);
                    window.location.replace(url.toString());
                }
            }
        </script>
        """
        st.markdown(_cookie_js, unsafe_allow_html=True)

        # Vérifier si le token arrive via query params
        _params = st.query_params
        _qp_token = _params.get("sic_token", "")
        if _qp_token:
            _username = _restore_session(_qp_token)
            if _username:
                _user = authentifier_par_username(_username)
                if _user:
                    st.session_state["user"] = _user
                    st.session_state["authenticated"] = True
                    st.session_state["session_token"] = _qp_token
                    # Nettoyer l'URL
                    del _params["sic_token"]
                    _restored = True

if not st.session_state["authenticated"]:
    page_login()
    st.stop()

# --- Alerte 15 jours avant expiration (apres login) ---
if jours_restants <= 15:
    st.warning(
        f"Votre licence expire dans **{jours_restants} jour(s)** ! "
        f"Contactez votre administrateur pour renouveler votre cle d'acces."
    )

# --- Utilisateur connecté ---
user = get_current_user()
username = user.get("username", "?") if user else "?"
user_role = user.get("role", "Lecteur") if user else "Lecteur"
user_nom = user.get("nom_complet", username) if user else username

# ==========================================
# 📌 SIDEBAR NAVIGATION
# ==========================================

# Logo SAVIA en haut de la sidebar (centré)
import base64 as _b64
_savia_logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo_savia.png")
if os.path.exists(_savia_logo):
    with open(_savia_logo, "rb") as _f:
        _logo_b64 = _b64.b64encode(_f.read()).decode()
    st.sidebar.markdown(
        f'<div style="text-align:center;padding:0;margin-top:-30px;"><img src="data:image/png;base64,{_logo_b64}" width="130"></div>',
        unsafe_allow_html=True,
    )

role_emoji = {"Admin": "👑", "Manager": "💼", "Responsable Technique": "🎯", "Gestionnaire de stock": "📦", "Technicien": "🔧", "Lecteur": "👁️"}.get(user_role, "❓")
st.sidebar.markdown(
    f"""
    <div style="text-align:center; padding:0; margin-top:-10px; margin-bottom: -15px;">
        <div style="font-size:0.9rem; font-weight:800;
            background: linear-gradient(135deg, #00d4aa, #3b82f6);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            📡 {org_name}
        </div>
        <div style="color:#64748b; font-size:0.55rem;">
            {role_emoji} {user_nom} · {user_role}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("---")

# --- Pages filtrées par permissions ---
from auth import has_page_access

# --- Compter les demandes en attente (badge notification) ---
_nb_demandes_nouvelles = 0
try:
    from db_engine import lire_demandes_intervention
    _df_dem = lire_demandes_intervention()
    if not _df_dem.empty and "statut" in _df_dem.columns:
        _nb_demandes_nouvelles = int((_df_dem["statut"].astype(str).str.strip() == "Nouvelle").sum())
except Exception:
    pass

# Définition des pages : (clé, label sans emoji, icône Bootstrap)
_demandes_label = "Demandes d'Intervention"
_PAGE_DEFS = [
    ("dashboard",          t("dashboard").lstrip("📊 "),          "bar-chart-line"),
    ("supervision",        t("supervision").lstrip("🔧 "),        "display"),
    ("equipements",        t("fleet").lstrip("🏥 "),              "hospital"),
    ("predictions",        t("predictions").lstrip("📈 "),        "graph-up-arrow"),
    ("base_connaissances", t("knowledge_base").lstrip("📚 "),     "book"),
    ("sav",                "SAV & Interventions",                 "tools"),
    ("demandes",           _demandes_label,                       "clipboard-plus"),
    ("planning",           t("planning").lstrip("📅 "),           "calendar-event"),
    ("pieces",             t("spare_parts").lstrip("🔧 "),        "gear"),
    ("reports",            t("reports").lstrip("📄 "),            "file-earmark-pdf"),
    ("contrats",           "Contrats & SLA",                      "clipboard-check"),
    ("conformite",         "QHSE Conformité",                     "shield-check"),
    ("admin",              t("admin").lstrip("⚙️ "),             "sliders"),
    ("clients_savia",      "Clients SAVIA",                       "building"),
    ("settings",           t("settings").lstrip("🎨 "),           "palette"),
]

# Filtrer les pages selon les permissions du rôle
_filtered = [(k, lbl, ico) for k, lbl, ico in _PAGE_DEFS if has_page_access(k)]
_page_keys   = [k for k, _, _ in _filtered]
_page_labels = [lbl for _, lbl, _ in _filtered]
_page_icons  = [ico for _, _, ico in _filtered]

# Déterminer l'index par défaut (redirection depuis une autre page)
_nav_target = st.session_state.pop("nav_target", None)
_default_idx = 0
if _nav_target and _nav_target in _page_keys:
    _default_idx = _page_keys.index(_nav_target)
    # Forcer le menu à se re-rendre avec le nouvel index
    st.session_state.pop("nav_option_menu", None)

with st.sidebar:
    page_sel = option_menu(
        menu_title=None,
        options=_page_labels,
        icons=_page_icons,
        default_index=_default_idx,
        key="nav_option_menu",
        styles={
            "container": {
                "padding": "4px 0",
                "background-color": "#1e293b",
                "border-radius": "0px",
            },
            "icon": {"color": "#2dd4bf", "font-size": "16px"},
            "nav-link": {
                "font-size": "14px",
                "text-align": "left",
                "margin": "2px 0",
                "padding": "8px 12px",
                "border-radius": "8px",
                "color": "#94a3b8",
                "background-color": "transparent",
                "--hover-color": "rgba(45,212,191,0.08)",
            },
            "nav-link-selected": {
                "background": "linear-gradient(135deg, rgba(45,212,191,0.15), rgba(59,130,246,0.10))",
                "color": "#2dd4bf",
                "font-weight": "700",
            },
            "menu-title": {"display": "none"},
        },
    )

# --- Forcer le fond sombre des iframes option-menu dans la sidebar ---
st.sidebar.markdown("""
<style>
section[data-testid="stSidebar"] iframe {
    background-color: #1e293b !important;
}
</style>
""", unsafe_allow_html=True)

# --- Badge notification rouge sur "Demandes d'Intervention" ---
if _nb_demandes_nouvelles > 0:
    import streamlit.components.v1 as _components
    _badge_label = _demandes_label
    _badge_html = f"""
    <script>
    (function() {{
        function addBadge() {{
            var doc = window.parent.document;
            // Chercher dans les iframes du sidebar (option_menu)
            var iframes = doc.querySelectorAll('section[data-testid="stSidebar"] iframe');
            iframes.forEach(function(iframe) {{
                try {{
                    var idoc = iframe.contentDocument || iframe.contentWindow.document;
                    if (!idoc) return;
                    var links = idoc.querySelectorAll('a.nav-link, a');
                    links.forEach(function(link) {{
                        if (link.textContent && link.textContent.includes("{_badge_label}") && !link.querySelector('.sic-badge')) {{
                            link.style.position = 'relative';
                            var style = idoc.getElementById('sic-badge-style');
                            if (!style) {{
                                style = idoc.createElement('style');
                                style.id = 'sic-badge-style';
                                style.textContent = '.sic-badge {{ display:inline-flex; align-items:center; justify-content:center; min-width:20px; height:20px; padding:0 6px; background:#ef4444; color:white !important; border-radius:10px; font-size:0.7rem; font-weight:800; position:absolute; top:50%; right:8px; transform:translateY(-50%); box-shadow:0 2px 6px rgba(239,68,68,0.5); animation:badge-pulse 2s ease-in-out infinite; }} @keyframes badge-pulse {{ 0%,100% {{ transform:translateY(-50%) scale(1); }} 50% {{ transform:translateY(-50%) scale(1.15); }} }}';
                                idoc.head.appendChild(style);
                            }}
                            var badge = idoc.createElement('span');
                            badge.className = 'sic-badge';
                            badge.textContent = '{_nb_demandes_nouvelles}';
                            link.appendChild(badge);
                        }}
                    }});
                }} catch(e) {{}}
            }});
        }}
        setTimeout(addBadge, 800);
        setTimeout(addBadge, 2000);
        setTimeout(addBadge, 4000);
    }})();
    </script>
    """
    with st.sidebar:
        _components.html(_badge_html, height=0)

st.sidebar.markdown("---")

# --- Indicateur statut IA (lazy-load pour ne pas ralentir le démarrage) ---
if "ia_status" not in st.session_state:
    # Pas d'import lourd ici, juste un check rapide de la config
    from config import GOOGLE_API_KEYS
    if not GOOGLE_API_KEYS:
        st.session_state["ia_status"] = (False, "Clé API non configurée")
    else:
        st.session_state["ia_status"] = (True, "IA disponible (non testée)")

ia_ok, ia_msg = st.session_state["ia_status"]
ia_color = "#10b981" if ia_ok else "#ef4444"
ia_dot = "🟢" if ia_ok else "🔴"

col_ia, col_test = st.sidebar.columns([3, 1])
col_ia.markdown(
    f"""<div style="display:flex; align-items:center; gap:6px; padding:4px 0;">
    <span style="font-size:0.7rem;">{ia_dot}</span>
    <span style="color:{ia_color}; font-size:0.7rem; font-weight:600;">IA: {ia_msg}</span>
</div>""",
    unsafe_allow_html=True,
)
if col_test.button("🔄", help="Tester la connexion IA", key="test_ia"):
    with st.spinner("Test IA..."):
        from ai_engine import verifier_ia
        result = verifier_ia()
        st.session_state["ia_status"] = result
        st.rerun()

# Statut Bot Telegram
try:
    from telegram_bot import is_bot_running, get_bot_error
    bot_ok = is_bot_running()
    bot_err = get_bot_error()
    if bot_ok:
        bot_dot, bot_msg, bot_color = "🟢", "Bot Telegram actif", "#10b981"
    elif bot_err:
        bot_dot, bot_msg, bot_color = "🔴", f"Bot: {bot_err[:50]}", "#ef4444"
    else:
        bot_dot, bot_msg, bot_color = "⚪", "Bot Telegram inactif", "#64748b"
    st.sidebar.markdown(
        f"""<div style="display:flex; align-items:center; gap:6px; padding:2px 0;">
        <span style="font-size:0.7rem;">{bot_dot}</span>
        <span style="color:{bot_color}; font-size:0.7rem;">{bot_msg}</span>
    </div>""", unsafe_allow_html=True)
except Exception:
    pass

# --- Notifications pièces (alertes cross-app) ---
try:
    from db_engine import compter_notifications_non_lues, lire_notifications_pieces, marquer_notification_lue
    notif_count = compter_notifications_non_lues("radiologie")
    if notif_count > 0:
        st.sidebar.markdown(
            f"""
            <div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);
                 border-radius: 8px; padding: 8px 12px; margin: 4px 0;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-size:1.1rem;">🔔</span>
                    <span style="color:#ef4444; font-size:0.8rem; font-weight:700;">
                        {notif_count} alerte(s) pièce(s)
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.sidebar.expander(f"📦 Voir {notif_count} notification(s)", expanded=False):
            df_notifs = lire_notifications_pieces(destination="radiologie", statut="non_lu")
            if not df_notifs.empty:
                for _, nrow in df_notifs.iterrows():
                    n_icon = "🚨" if nrow.get("type") == "piece_rupture" else "🟢"
                    n_type = "Rupture" if nrow.get("type") == "piece_rupture" else "Disponible"
                    st.markdown(
                        f"{n_icon} **{n_type}** — {nrow.get('piece_nom', '')} ({nrow.get('piece_reference', '')})\n\n"
                        f"🏥 {nrow.get('equipement', '')} | 🏢 {nrow.get('client', '')} | 👨‍🔧 {nrow.get('technicien', '')}",
                    )
                    if st.button(f"✅ Marquer lu", key=f"notif_lu_{nrow['id']}"):
                        marquer_notification_lue(nrow["id"])
                        st.rerun()
                    st.markdown("---")
            if st.button("📦 Voir les pièces", use_container_width=True, key="go_pieces_notif"):
                st.session_state["nav_target"] = "pieces"
                st.rerun()
except Exception:
    pass

# Bouton déconnexion + licence compact
col_logout, col_info = st.sidebar.columns([2, 1])
if col_logout.button(t("logout"), use_container_width=True):
    # Invalider le token de session persistant
    _invalidate_session(st.session_state.get("session_token", ""))
    # Supprimer le cookie côté navigateur
    st.markdown('<script>document.cookie = "sic_session=; path=/; max-age=0";</script>', unsafe_allow_html=True)
    deconnecter()
    st.session_state["authenticated"] = False
    st.session_state.pop("session_token", None)
    st.rerun()
col_info.markdown(f"<div style='color:#64748b;font-size:0.6rem;text-align:center;padding-top:8px;'>{jours_restants}j</div>", unsafe_allow_html=True,
)

# Logo client en bas de la sidebar
logo_client_path = get_config("logo_path", "")
if logo_client_path and os.path.exists(logo_client_path):
    st.sidebar.markdown("---")
    st.sidebar.image(logo_client_path, width=120)

# ==========================================
# 📍 ROUTING DES PAGES
# ==========================================
# Retrouver la clé de page à partir du label sélectionné
_sel_idx = _page_labels.index(page_sel) if page_sel in _page_labels else 0
page_key = _page_keys[_sel_idx]

if page_key == "dashboard":
    from views.dashboard import afficher_dashboard
    afficher_dashboard()

elif page_key == "supervision":
    from views.supervision import afficher_supervision
    afficher_supervision()

elif page_key == "equipements":
    from views.equipements import afficher_equipements
    afficher_equipements()

elif page_key == "predictions":
    from views.predictions import afficher_predictions
    afficher_predictions()

elif page_key == "base_connaissances":
    from views.base_connaissances import afficher_base_connaissances
    afficher_base_connaissances()

elif page_key == "sav":
    from views.sav import show_sav_page
    show_sav_page()

elif page_key == "demandes":
    from views.demandes import page_demandes
    page_demandes()

elif page_key == "planning":
    from views.planning import page_planning
    page_planning()

elif page_key == "pieces":
    from views.spare_parts import page_pieces
    page_pieces()

elif page_key == "reports":
    from views.reports import page_reports
    page_reports()

elif page_key == "admin":
    from views.admin import page_admin
    page_admin()

elif page_key == "contrats":
    from views.contrats import page_contrats
    page_contrats()

elif page_key == "conformite":
    from views.conformite import page_conformite
    page_conformite()

elif page_key == "settings":
    from views.settings import page_settings
    page_settings()

elif page_key == "clients_savia":
    from views.clients_savia import page_clients_savia
    page_clients_savia()

# --- Footer Branding Premium ---
st.markdown("""
<div style="margin-top: 3rem; padding: 1.5rem 0; border-top: 1px solid rgba(148,163,184,0.08); text-align: center;">
    <span class="savia-footer-brand">SAVIA</span>
    <span style="color: #475569; font-size: 0.8rem; margin-left: 8px;">
        Powered by SIC Radiologie &bull; Maintenance Pr\u00e9dictive
    </span>
</div>
""", unsafe_allow_html=True)
