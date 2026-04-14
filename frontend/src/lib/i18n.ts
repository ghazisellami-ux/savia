// ==========================================
// 🌍 Internationalisation — Savia
// ==========================================

const translations: Record<string, Record<string, string>> = {
  fr: {
    dashboard: '📊 Dashboard',
    supervision: '🔧 Supervision',
    fleet: '🏥 Équipements',
    predictions: '📈 Prédictions',
    knowledge_base: '📚 Base de Connaissances',
    sav: '🔧 SAV & Interventions',
    demandes: '📋 Demandes',
    planning: '📅 Planning',
    spare_parts: '🔧 Pièces de Rechange',
    reports: '📄 Rapports',
    contrats: '📋 Contrats & SLA',
    conformite: '🛡️ QHSE Conformité',
    admin: '⚙️ Administration',
    settings: '🎨 Paramètres',
    clients: '🏢 Clients SAVIA',
    login_title: 'Connexion',
    login_subtitle: 'Superviseur Intelligent Clinique',
    username: 'Identifiant',
    password: 'Mot de passe',
    login_btn: 'Se connecter',
    login_error: 'Identifiants incorrects',
    logout: 'Déconnexion',
    total_equipment: 'Équipements',
    critical_alerts: 'Alertes Critiques',
    availability_rate: 'Disponibilité',
    mtbf: 'MTBF',
    mttr: 'MTTR',
    maintenance_cost: 'Coût Maintenance',
    health_score: 'Score de Santé',
    no_data: 'Aucune donnée disponible',
  },
  en: {
    dashboard: '📊 Dashboard',
    supervision: '🔧 Supervision',
    fleet: '🏥 Equipment',
    predictions: '📈 Predictions',
    knowledge_base: '📚 Knowledge Base',
    sav: '🔧 Maintenance',
    demandes: '📋 Requests',
    planning: '📅 Planning',
    spare_parts: '🔧 Spare Parts',
    reports: '📄 Reports',
    contrats: '📋 Contracts & SLA',
    conformite: '🛡️ QHSE Compliance',
    admin: '⚙️ Administration',
    settings: '🎨 Settings',
    clients: '🏢 SAVIA Clients',
    login_title: 'Sign In',
    login_subtitle: 'Intelligent Clinical Supervisor',
    username: 'Username',
    password: 'Password',
    login_btn: 'Sign In',
    login_error: 'Invalid credentials',
    logout: 'Sign Out',
    total_equipment: 'Equipment',
    critical_alerts: 'Critical Alerts',
    availability_rate: 'Availability',
    mtbf: 'MTBF',
    mttr: 'MTTR',
    maintenance_cost: 'Maintenance Cost',
    health_score: 'Health Score',
    no_data: 'No data available',
  },
};

let currentLang = 'fr';

export function setLang(lang: string) {
  currentLang = lang;
}

export function getLang() {
  return currentLang;
}

export function t(key: string): string {
  return translations[currentLang]?.[key] || translations['fr']?.[key] || key;
}

export default { t, getLang, setLang };
