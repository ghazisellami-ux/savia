# ==========================================
# 🌐 INTERNATIONALISATION (FR / EN)
# ==========================================
"""
Module de traduction Français / Anglais.
Usage: from i18n import t
       t("dashboard")  → "Tableau de Bord" ou "Dashboard"
"""
import streamlit as st


TRANSLATIONS = {
    # ============ NAVIGATION ============
    "app_title": {"fr": "SIC Radiologie", "en": "SIC Radiology"},
    "dashboard": {"fr": "📊 Tableau de Bord", "en": "📊 Dashboard"},
    "supervision": {"fr": "🔧 Supervision", "en": "🔧 Supervision"},
    "predictions": {"fr": "📈 Prédictions", "en": "📈 Predictions"},
    "knowledge_base": {"fr": "📚 Base de Connaissances", "en": "📚 Knowledge Base"},
    "fleet": {"fr": "🏥 Parc d'Équipements", "en": "🏥 Equipment Fleet"},
    "interventions": {"fr": "🔩 Interventions", "en": "🔩 Interventions"},
    "planning": {"fr": "📅 Planning Maintenance", "en": "📅 Maintenance Planning"},
    "spare_parts": {"fr": "🔧 Pièces de Rechange", "en": "🔧 Spare Parts"},
    "reports": {"fr": "📄 Rapports PDF", "en": "📄 PDF Reports"},
    "admin": {"fr": "⚙️ Administration", "en": "⚙️ Administration"},
    "settings": {"fr": "🎨 Paramètres", "en": "🎨 Settings"},
    "logout": {"fr": "🚪 Déconnexion", "en": "🚪 Logout"},

    # ============ LOGIN ============
    "login_title": {"fr": "Connexion", "en": "Login"},
    "username": {"fr": "Nom d'utilisateur", "en": "Username"},
    "password": {"fr": "Mot de passe", "en": "Password"},
    "login_btn": {"fr": "🔐 Se connecter", "en": "🔐 Log in"},
    "login_error": {"fr": "❌ Nom d'utilisateur ou mot de passe incorrect", "en": "❌ Invalid username or password"},
    "welcome": {"fr": "Bienvenue", "en": "Welcome"},
    "role": {"fr": "Rôle", "en": "Role"},

    # ============ DASHBOARD ============
    "total_equipment": {"fr": "Équipements Total", "en": "Total Equipment"},
    "critical_alerts": {"fr": "Alertes Critiques", "en": "Critical Alerts"},
    "health_score": {"fr": "Score de Santé", "en": "Health Score"},
    "last_24h": {"fr": "Dernières 24h", "en": "Last 24h"},
    "availability_rate": {"fr": "Taux de Disponibilité", "en": "Availability Rate"},
    "mtbf": {"fr": "MTBF (heures)", "en": "MTBF (hours)"},
    "mttr": {"fr": "MTTR (heures)", "en": "MTTR (hours)"},
    "maintenance_cost": {"fr": "Coût Maintenance", "en": "Maintenance Cost"},

    # ============ SUPERVISION ============
    "fleet_overview": {"fr": "🏥 Vue d'ensemble du Parc", "en": "🏥 Fleet Overview"},
    "machine": {"fr": "Machine", "en": "Machine"},
    "errors_detected": {"fr": "Erreurs Détectées", "en": "Errors Detected"},
    "state": {"fr": "État", "en": "Status"},
    "select_error": {"fr": "🎯 Sélectionnez l'erreur à analyser", "en": "🎯 Select error to analyze"},
    "known_error": {"fr": "✅ Erreur CONNUE — Solution existante", "en": "✅ KNOWN Error — Solution exists"},
    "unknown_error": {"fr": "⚠️ Erreur INCONNUE — Aucune solution", "en": "⚠️ UNKNOWN Error — No solution found"},
    "cause": {"fr": "Cause", "en": "Cause"},
    "solution": {"fr": "Solution", "en": "Solution"},
    "priority": {"fr": "Priorité", "en": "Priority"},
    "type": {"fr": "Type", "en": "Type"},
    "send_alert": {"fr": "🔔 Envoyer une alerte au responsable", "en": "🔔 Send alert to manager"},
    "alert_sent": {"fr": "✅ Alerte envoyée", "en": "✅ Alert sent"},

    # ============ AI DIAGNOSTICS ============
    "ai_diagnostic": {"fr": "🧠 Diagnostic IA", "en": "🧠 AI Diagnostic"},
    "ai_analyzing": {"fr": "Analyse en cours...", "en": "Analyzing..."},
    "problem": {"fr": "Problème", "en": "Problem"},
    "recommended_solution": {"fr": "Solution recommandée", "en": "Recommended Solution"},

    # ============ KNOWLEDGE BASE ============
    "save_to_kb": {"fr": "💾 Enregistrer dans la Base de Connaissances", "en": "💾 Save to Knowledge Base"},
    "confirmed_cause": {"fr": "🔧 Cause confirmée", "en": "🔧 Confirmed Cause"},
    "applied_solution": {"fr": "💡 Solution appliquée", "en": "💡 Applied Solution"},
    "error_type": {"fr": "📁 Type d'erreur", "en": "📁 Error Type"},
    "save_btn": {"fr": "💾 Enregistrer dans la base", "en": "💾 Save to database"},
    "save_success": {"fr": "✅ Enregistré avec succès !", "en": "✅ Successfully saved!"},
    "save_error": {"fr": "❌ Erreur lors de la sauvegarde", "en": "❌ Error while saving"},
    "fill_fields": {"fr": "❌ Veuillez remplir la cause ET la solution", "en": "❌ Please fill in both cause AND solution"},

    # ============ INTERVENTIONS ============
    "new_intervention": {"fr": "➕ Nouvelle Intervention", "en": "➕ New Intervention"},
    "technician": {"fr": "Technicien", "en": "Technician"},
    "duration_min": {"fr": "Durée (minutes)", "en": "Duration (minutes)"},
    "cost": {"fr": "Coût", "en": "Cost"},
    "parts_used": {"fr": "Pièces utilisées", "en": "Parts Used"},
    "description": {"fr": "Description", "en": "Description"},
    "corrective": {"fr": "Corrective", "en": "Corrective"},
    "preventive": {"fr": "Préventive", "en": "Preventive"},
    "intervention_history": {"fr": "📋 Historique des Interventions", "en": "📋 Intervention History"},

    # ============ PLANNING ============
    "planned": {"fr": "Planifiée", "en": "Planned"},
    "in_progress": {"fr": "En cours", "en": "In Progress"},
    "completed": {"fr": "Terminée", "en": "Completed"},
    "overdue": {"fr": "En retard", "en": "Overdue"},
    "add_maintenance": {"fr": "➕ Planifier une maintenance", "en": "➕ Schedule maintenance"},
    "planned_date": {"fr": "Date prévue", "en": "Planned Date"},
    "assigned_tech": {"fr": "Technicien assigné", "en": "Assigned Technician"},
    "recurrence": {"fr": "Récurrence", "en": "Recurrence"},

    # ============ SPARE PARTS ============
    "reference": {"fr": "Référence", "en": "Reference"},
    "designation": {"fr": "Désignation", "en": "Designation"},
    "current_stock": {"fr": "Stock Actuel", "en": "Current Stock"},
    "min_stock": {"fr": "Stock Minimum", "en": "Minimum Stock"},
    "supplier": {"fr": "Fournisseur", "en": "Supplier"},
    "unit_price": {"fr": "Prix unitaire", "en": "Unit Price"},
    "low_stock_alert": {"fr": "⚠️ Stock bas !", "en": "⚠️ Low stock!"},
    "add_part": {"fr": "➕ Ajouter une pièce", "en": "➕ Add part"},

    # ============ REPORTS ============
    "generate_report": {"fr": "📄 Générer le rapport", "en": "📄 Generate report"},
    "monthly_report": {"fr": "Rapport Mensuel", "en": "Monthly Report"},
    "download_pdf": {"fr": "⬇️ Télécharger le PDF", "en": "⬇️ Download PDF"},
    "report_period": {"fr": "Période", "en": "Period"},

    # ============ ADMIN ============
    "user_management": {"fr": "👥 Gestion des Utilisateurs", "en": "👥 User Management"},
    "add_user": {"fr": "➕ Ajouter un utilisateur", "en": "➕ Add User"},
    "audit_log": {"fr": "📋 Journal d'Audit", "en": "📋 Audit Log"},
    "backup_management": {"fr": "💾 Sauvegardes", "en": "💾 Backups"},
    "create_backup": {"fr": "Créer une sauvegarde", "en": "Create backup"},
    "restore_backup": {"fr": "Restaurer", "en": "Restore"},
    "full_name": {"fr": "Nom complet", "en": "Full Name"},
    "email": {"fr": "Email", "en": "Email"},
    "active": {"fr": "Actif", "en": "Active"},
    "actions": {"fr": "Actions", "en": "Actions"},
    "change_password": {"fr": "Changer le mot de passe", "en": "Change password"},
    "delete": {"fr": "Supprimer", "en": "Delete"},
    "confirm_delete": {"fr": "Confirmer la suppression ?", "en": "Confirm deletion?"},

    # ============ SETTINGS ============
    "organization_name": {"fr": "Nom de l'organisation", "en": "Organization Name"},
    "upload_logo": {"fr": "📷 Télécharger le logo", "en": "📷 Upload Logo"},
    "language": {"fr": "🌐 Langue", "en": "🌐 Language"},
    "save_settings": {"fr": "💾 Sauvegarder les paramètres", "en": "💾 Save Settings"},

    # ============ GENERAL ============
    "loading": {"fr": "Chargement...", "en": "Loading..."},
    "no_data": {"fr": "Aucune donnée disponible", "en": "No data available"},
    "cancel": {"fr": "Annuler", "en": "Cancel"},
    "save": {"fr": "Enregistrer", "en": "Save"},
    "edit": {"fr": "Modifier", "en": "Edit"},
    "search": {"fr": "Rechercher...", "en": "Search..."},
    "filter": {"fr": "Filtrer", "en": "Filter"},
    "export": {"fr": "Exporter", "en": "Export"},
    "refresh": {"fr": "🔄 Actualiser", "en": "🔄 Refresh"},
    "notes": {"fr": "Notes", "en": "Notes"},
    "status": {"fr": "Statut", "en": "Status"},
    "date": {"fr": "Date", "en": "Date"},
    "frequency": {"fr": "Fréquence", "en": "Frequency"},
    "total": {"fr": "Total", "en": "Total"},
    "high": {"fr": "HAUTE", "en": "HIGH"},
    "medium": {"fr": "MOYENNE", "en": "MEDIUM"},
    "low": {"fr": "BASSE", "en": "LOW"},
}


def get_lang():
    """Retourne la langue actuelle (fr ou en)."""
    return st.session_state.get("lang", "fr")


def set_lang(lang):
    """Change la langue."""
    st.session_state["lang"] = lang


def t(key: str) -> str:
    """Traduit une clé dans la langue actuelle."""
    lang = get_lang()
    entry = TRANSLATIONS.get(key)
    if entry:
        return entry.get(lang, entry.get("fr", key))
    return key


def langue_selector():
    """Affiche un sélecteur de langue dans la sidebar."""
    current = get_lang()
    langs = {"fr": "🇫🇷 Français", "en": "🇬🇧 English"}
    selected = st.sidebar.selectbox(
        "🌐",
        options=list(langs.keys()),
        format_func=lambda x: langs[x],
        index=0 if current == "fr" else 1,
        key="lang_selector",
    )
    if selected != current:
        set_lang(selected)
        st.rerun()
