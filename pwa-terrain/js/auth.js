// ==========================================
// 🔐 Auth — Gestion du login + JWT + OFFLINE
// ==========================================

function isLoggedIn() {
    return !!getToken();
}

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('sic_user') || 'null');
    } catch {
        return null;
    }
}

function setSession(token, user) {
    localStorage.setItem('sic_token', token);
    localStorage.setItem('sic_user', JSON.stringify(user));
}

function clearSession() {
    localStorage.removeItem('sic_token');
    localStorage.removeItem('sic_user');
}

// --- Hash simple pour stocker le mot de passe offline ---
async function hashPassword(password) {
    const encoder = new TextEncoder();
    const data = encoder.encode(password + '_sic_salt_2026');
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

// --- Cacher les identifiants pour login offline ---
async function cacheCredentials(username, password, user) {
    const hash = await hashPassword(password);
    const cached = JSON.parse(localStorage.getItem('sic_cached_creds') || '{}');
    cached[username.toLowerCase()] = { hash, user };
    localStorage.setItem('sic_cached_creds', JSON.stringify(cached));
}

// --- Vérifier les identifiants en mode offline ---
async function verifyOfflineCredentials(username, password) {
    const cached = JSON.parse(localStorage.getItem('sic_cached_creds') || '{}');
    const entry = cached[username.toLowerCase()];
    if (!entry) return null;
    const hash = await hashPassword(password);
    if (hash === entry.hash) {
        return entry.user;
    }
    return null;
}

async function handleLogin(username, password) {
    // 1. Essayer le login en ligne
    try {
        const result = await apiLogin(username, password);
        setSession(result.token, result.user);
        // Cacher les identifiants pour le mode offline
        await cacheCredentials(username, password, result.user);
        return result.user;
    } catch (onlineErr) {
        console.warn('[Auth] Login en ligne échoué:', onlineErr.message);
        // 2. Si erreur réseau ou serveur inaccessible → essayer offline
        const user = await verifyOfflineCredentials(username, password);
        if (user) {
            console.log('[Auth] Login OFFLINE réussi pour', username);
            setSession('offline_token_' + Date.now(), user);
            return user;
        }
        // 3. Si pas de credentials cachées, afficher l'erreur appropriée
        if (!navigator.onLine) {
            throw new Error('Hors ligne — Connectez-vous d\'abord en ligne');
        }
        throw onlineErr; // Erreur d'authentification réelle (mauvais mot de passe, etc.)
    }
}

function handleLogout() {
    clearSession();
    // Vider les data locales
    dbClear(STORES.interventions);
    dbClear(STORES.equipements);
    dbClear(STORES.techniciens);
    // Ne PAS vider la sync queue ni les credentials cachées
    window.location.reload();
}
