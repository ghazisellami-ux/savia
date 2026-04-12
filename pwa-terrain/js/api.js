// ==========================================
// 🌐 API — Appels REST avec gestion offline
// ==========================================

const API_BASE = (localStorage.getItem('SIC_API_URL') || window.location.origin) + '/api';

function getToken() {
    return localStorage.getItem('sic_token');
}

function authHeaders() {
    const token = getToken();
    return {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };
}

async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url, {
        headers: authHeaders(),
        ...options,
    });
    if (res.status === 401) {
        // Token expiré → déconnecter
        localStorage.removeItem('sic_token');
        localStorage.removeItem('sic_user');
        window.location.reload();
        throw new Error('Session expirée');
    }
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Erreur ${res.status}`);
    }
    return res.json();
}

// --- Auth ---
async function apiLogin(username, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Erreur de connexion');
    }
    return res.json();
}

// --- Interventions ---
async function apiGetInterventions(machine, technicien) {
    const params = new URLSearchParams();
    if (machine) params.set('machine', machine);
    if (technicien) params.set('technicien', technicien);
    const qs = params.toString();
    return apiFetch(`/interventions${qs ? '?' + qs : ''}`);
}

async function apiCreateIntervention(data) {
    return apiFetch('/interventions', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

async function apiUpdateIntervention(id, data) {
    return apiFetch(`/interventions/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

// --- Équipements ---
async function apiGetEquipements() {
    return apiFetch('/equipements');
}

// --- Techniciens ---
async function apiGetTechniciens() {
    return apiFetch('/techniciens');
}

// --- Pièces ---
async function apiGetPieces() {
    return apiFetch('/pieces');
}

// --- Demandes d'intervention ---
async function apiGetDemandes(statuts) {
    const params = statuts ? `?statuts=${encodeURIComponent(statuts)}` : '';
    return apiFetch(`/demandes${params}`);
}

// --- Sync ---
async function apiSync(operations) {
    return apiFetch('/sync', {
        method: 'POST',
        body: JSON.stringify({ operations }),
    });
}

// --- Notifications pièces ---
async function apiGetNotifications(destination = 'terrain') {
    return apiFetch(`/notifications?destination=${destination}`);
}

async function apiGetNotificationCount(destination = 'terrain') {
    return apiFetch(`/notifications/count?destination=${destination}`);
}

async function apiMarkNotificationRead(notifId) {
    return apiFetch(`/notifications/${notifId}/read`, { method: 'POST' });
}

async function apiMarkNotificationTreated(notifId) {
    return apiFetch(`/notifications/${notifId}/treat`, { method: 'POST' });
}

// --- Upload photo fiche intervention ---
async function apiUploadPhoto(interventionId, photoFile) {
    const formData = new FormData();
    formData.append('photo', photoFile);
    const url = `${API_BASE}/interventions/${interventionId}/photo`;
    const token = getToken();
    const res = await fetch(url, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Erreur upload ${res.status}`);
    }
    return res.json();
}
