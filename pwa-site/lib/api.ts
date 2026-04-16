// ==========================================
// 🔌 API Client — SAVIA Site
// ==========================================
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

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
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    req<{ access_token: string; role: string; nom: string; id: number }>(
      '/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }
    ),

  // Interventions (SAV)
  interventions: {
    list: (params?: { technicien?: string }) => {
      const qs = params?.technicien ? `?technicien=${encodeURIComponent(params.technicien)}` : '';
      return req<any[]>(`/api/sav${qs}`);
    },
    get: (id: number) => req<any>(`/api/sav/${id}`),
    create: (data: any) => req<any>('/api/sav', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: any) => req<any>(`/api/sav/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    uploadPhoto: async (id: number, file: File) => {
      const token = localStorage.getItem('savia_site_token') || '';
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`${API_BASE}/api/sav/${id}/photo`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) throw new Error('Upload photo failed');
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
