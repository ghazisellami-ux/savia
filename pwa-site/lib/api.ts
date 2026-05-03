// ==========================================
// 🔌 API Client — SAVIA Site
// All /api/* calls go through Next.js proxy → backend
// ==========================================
const API_BASE = '/site'; // Must match basePath for Next.js rewrites to work

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('savia_site_token') : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts.headers,
    },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }

  return res.json();
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    req<{ token: string; user: { username: string; nom: string; nom_complet?: string; role: string } }>(
      '/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }
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
    uploadPhoto: async (id: number, file: File) => {
      const token = localStorage.getItem('savia_site_token') || '';
      const fd = new FormData();
      fd.append('file', file);
      // Upload directly to backend — Next.js rewrites don't reliably proxy
      // multipart/form-data in standalone mode. Use relative /api/ path which
      // Nginx reverse-proxies directly to the backend container.
      const res = await fetch(`/api/interventions/${id}/photo`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => '');
        throw new Error(`Upload photo failed: ${res.status} ${detail}`);
      }
      return res.json();
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

  // Pièces
  pieces: {
    list: () => req<any[]>('/api/pieces'),
  },

  // Notifications
  notifications: {
    list: () => req<any[]>('/api/notifications'),
    markRead: (id: number) => req<any>(`/api/notifications/${id}/read`, { method: 'PUT' }),
  },
};
