// ==========================================
// 🔌 API Client — SAVIA Site
// All /api/* calls go through Next.js proxy → backend
// ==========================================
import { cacheResponse, readCachedResponse } from './offline-db';
import { isTransientNetworkError, newOperationId, queueJsonMutation, queuePhoto, reportOfflineState } from './offline-sync';

const API_BASE = ''; // PWA has its own domain, no basePath needed
const NETWORK_TIMEOUT_MS = 12000;

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('savia_site_token') : null;
  const lang = typeof window !== 'undefined'
    ? (localStorage.getItem('savia_site_lang') || localStorage.getItem('savia_lang') || 'fr')
    : 'fr';
  const method = (opts.method || 'GET').toUpperCase();
  const queueable = ['PUT', 'PATCH', 'DELETE'].includes(method);
  const operationId = queueable ? newOperationId() : '';
  const headers = {
    'Content-Type': 'application/json',
    'X-SAVIA-Lang': lang,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(operationId ? { 'X-SAVIA-Operation-Id': operationId } : {}),
    ...opts.headers,
  };

  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), NETWORK_TIMEOUT_MS);
    const res = await fetch(`${API_BASE}${path}`, { ...opts, headers, signal: controller.signal });
    window.clearTimeout(timeout);
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body?.detail || body?.error) detail = body.detail || body.error;
      } catch {}
      const apiError = new Error(detail) as Error & { status?: number };
      apiError.status = res.status;
      throw apiError;
    }

    const data = await res.json();
    if (method === 'GET') await cacheResponse(path, data).catch(() => undefined);
    return data;
  } catch (error) {
    const networkError = typeof window !== 'undefined' && isTransientNetworkError(error);
    if (!networkError) throw error;
    reportOfflineState(true);

    if (method === 'GET') {
      const cached = await readCachedResponse(path).catch(() => null);
      if (cached !== null) return cached as T;
      throw new Error('Données indisponibles hors connexion. Ouvrez cette page une première fois avec une connexion.');
    }

    // A new intervention needs a server-generated ID for its detail page and
    // its signed fiche. Keep creation explicit until a full draft workflow is
    // introduced; updates and closures remain safely queueable.
    if (!queueable) throw new Error('Cette action nécessite une connexion internet.');

    const body = typeof opts.body === 'string' ? opts.body : '{}';
    let parsedBody: any = {};
    try { parsedBody = JSON.parse(body); } catch { /* keep empty patch */ }
    const patch: Record<string, unknown> = {};
    if (typeof parsedBody?.statut === 'string') patch.statut = parsedBody.statut;
    const queued = await queueJsonMutation(path, method, body, patch, operationId);
    return queued as T;
  }
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    req<{ token: string; user: { username: string; nom: string; nom_complet?: string; role: string } }>(
      '/api/auth/login', {
        method: 'POST',
        headers: { 'X-SAVIA-Client': 'pwa' },
        body: JSON.stringify({ username, password }),
      }
    ),

  // Interventions
  interventions: {
    list: (params?: { technicien?: string; machine?: string }) => {
      const p = new URLSearchParams();
      if (params?.technicien) p.set('technicien', params.technicien);
      if (params?.machine) p.set('machine', params.machine);
      const qs = p.toString();
      return req<any[]>(`/api/interventions${qs ? '?' + qs : ''}`);
    },
    get:    (id: number) => req<any>(`/api/interventions/${id}`),
    create: (data: any) => req<any>('/api/interventions', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: any) => req<any>(`/api/interventions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    accept: (id: number) => req<any>(`/api/interventions/${id}/accept`, { method: 'PUT' }),
    refuse: (id: number, raison: string) => req<any>(`/api/interventions/${id}/refuse`, { method: 'PUT', body: JSON.stringify({ raison }) }),
    updateTechnicianData: (id: number, data: any) => req<any>(`/api/interventions/${id}/technicien-data`, { method: 'PUT', body: JSON.stringify(data) }),
    getTechnicianData: (id: number) => req<any[]>(`/api/interventions/${id}/techniciens`, { method: 'GET' }),
    getWorkSessions: (id: number) => req<any[]>(`/api/interventions/${id}/work-sessions`, { method: 'GET' }),
    saveWorkSessions: (id: number, sessions: any[]) => req<any>(`/api/interventions/${id}/work-sessions`, { method: 'PUT', body: JSON.stringify({ sessions }) }),
    uploadPhoto: async (id: number, file: File) => {
      const token = localStorage.getItem('savia_site_token') || '';
      const lang = localStorage.getItem('savia_site_lang') || localStorage.getItem('savia_lang') || 'fr';
      const fd = new FormData();
      fd.append('file', file);
      // Upload directly to backend — Next.js rewrites don't reliably proxy
      // multipart/form-data in standalone mode. Use relative /api/ path which
      // Nginx reverse-proxies directly to the backend container.
      const operationId = newOperationId();
      try {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), NETWORK_TIMEOUT_MS);
        const res = await fetch(`/api/interventions/${id}/photo`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'X-SAVIA-Lang': lang,
            'X-SAVIA-Operation-Id': operationId,
          },
          body: fd,
          signal: controller.signal,
        });
        window.clearTimeout(timeout);
        if (!res.ok) {
          const detail = await res.text().catch(() => '');
          const uploadError = new Error(`Upload photo failed: ${res.status} ${detail}`) as Error & { status?: number };
          uploadError.status = res.status;
          throw uploadError;
        }
        return res.json();
      } catch (error) {
        const networkError = isTransientNetworkError(error);
        if (!networkError) throw error;
        return queuePhoto(`/api/interventions/${id}/photo`, file, operationId);
      }
    },
  },

  // Clients
  clients: {
    list: () => req<any[]>('/api/clients'),
  },

  // Équipements
  equipements: {
    list: () => req<any[]>('/api/equipements'),
  },

  // Techniciens
  techniciens: {
    list: () => req<any[]>('/api/techniciens'),
  },

  typesIntervention: {
    list: () => req<Array<{ id: number; nom: string }>>('/api/types-intervention-custom'),
  },

  // Pièces
  pieces: {
    list: () => req<any[]>('/api/pieces'),
  },

  // Notifications
  notifications: {
    list: () => req<any[]>('/api/notifications', { cache: 'no-store' }),
    count: () => req<{ count: number }>('/api/notifications/count', { cache: 'no-store' }),
    markRead: (id: number) => req<any>(`/api/notifications/${id}/read`, { method: 'PATCH' }),
  },
};
