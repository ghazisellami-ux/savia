# ==========================================
# 🎨 PAGE PARAMÈTRES CLIENT
# ==========================================
import streamlit as st
import os
from db_engine import get_config, set_config, log_audit
from auth import get_current_user, require_role
from i18n import t, set_lang, get_lang
from config import BASE_DIR


LOGO_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(LOGO_DIR, exist_ok=True)


def page_settings():
    if not require_role("Admin"):
        st.error("🚫 Accès réservé aux administrateurs")
        return

    st.title(t("settings"))
    user = get_current_user()
    username = user.get("username", "?") if user else "?"

    col1, col2 = st.columns(2)

    # ============ BRANDING ============
    with col1:
        st.subheader("🏥 " + t("organization_name"))

        current_name = get_config("nom_organisation", "SIC Radiologie")
        new_name = st.text_input(t("organization_name"), value=current_name)

        # Logo upload
        st.subheader(t("upload_logo"))
        current_logo = get_config("logo_path", "")
        if current_logo and os.path.exists(current_logo):
            st.image(current_logo, width=150)
            if st.button("🗑️ " + t("remove_logo")):
                set_config("logo_path", "")
                st.success("Logo supprimé !")
                st.rerun()

        uploaded = st.file_uploader("📷 Logo (PNG, JPG)", type=["png", "jpg", "jpeg"])
        if uploaded:
            logo_path = os.path.join(LOGO_DIR, "logo_client.png")
            with open(logo_path, "wb") as f:
                f.write(uploaded.getbuffer())
            set_config("logo_path", logo_path)
            st.success("✅ Logo enregistré !")
            st.image(logo_path, width=150)

    # ============ LANGUE ============
    with col2:
        st.subheader(t("language"))
        lang_options = {"fr": "🇫🇷 Français", "en": "🇬🇧 English"}
        current_lang = get_lang()
        selected_lang = st.radio(
            t("language"),
            options=list(lang_options.keys()),
            format_func=lambda x: lang_options[x],
            index=0 if current_lang == "fr" else 1,
            label_visibility="collapsed",
        )

        # Changer le mot de passe de l'utilisateur connecté
        st.markdown("---")
        st.subheader("🔑 " + t("change_password"))
        with st.form("form_change_pwd"):
            new_pwd = st.text_input(t("password"), type="password")
            confirm_pwd = st.text_input("Confirmer", type="password")
            if st.form_submit_button(t("save")):
                if not new_pwd:
                    st.error("❌ Mot de passe vide")
                elif new_pwd != confirm_pwd:
                    st.error("❌ Les mots de passe ne correspondent pas")
                else:
                    from auth import changer_mot_de_passe
                    changer_mot_de_passe(user["id"], new_pwd)
                    st.success("✅ Mot de passe changé !")

    # ============ DEVISE ============
    st.markdown("---")
    col_dev, _ = st.columns([1, 1])
    with col_dev:
        st.subheader("💰 Devise")
        current_devise = get_config("devise", "EUR")
        new_devise = st.text_input("Devise", value=current_devise, help="EUR, USD, TND, etc.")

    # ============ SAUVEGARDER ============
    st.markdown("---")
    if st.button(t("save_settings"), use_container_width=True):
        set_config("nom_organisation", new_name.strip())
        set_config("devise", new_devise.strip())
        if selected_lang != current_lang:
            set_lang(selected_lang)
            set_config("langue", selected_lang)
        log_audit(username, "SETTINGS_CHANGED",
                  f"Org: {new_name}, Lang: {selected_lang}", "Paramètres")
        st.success(t("save_success"))
        st.rerun()
