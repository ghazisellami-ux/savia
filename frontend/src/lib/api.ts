// ==========================================
// 🌐 API Client — Savia Frontend
// ==========================================

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ApiOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : null;
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: options.method || 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({ error: 'Erreur réseau' }));
    throw new ApiError(data.error || `HTTP ${res.status}`, res.status);
  }

  return res.json();
}

// --- Auth ---
export const auth = {
  login: (username: string, password: string) =>
    request<{ token: string; user: { username: string; nom: string; role: string } }>(
      '/api/auth/login', { method: 'POST', body: { username, password } }
    ),
  me: () => request<{ user: { sub: string; role: string; nom: string } }>('/api/auth/me'),
};

// --- Dashboard ---
export const dashboard = {
  kpis: (params?: { date_start?: string; date_end?: string; client?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Record<string, number>>(`/api/dashboard/kpis?${qs}`);
  },
  healthScores: (client?: string) => {
    const qs = client ? `?client=${client}` : '';
    return request<Array<{ machine: string; score: number; tendance: string; pannes: number }>>(
      `/api/dashboard/health-scores${qs}`
    );
  },
};

// --- Interventions ---
export const interventions = {
  list: (params?: { machine?: string; technicien?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Array<Record<string, unknown>>>(`/api/interventions?${qs}`);
  },
  create: (data: Record<string, unknown>) =>
    request<{ ok: boolean; message: string }>('/api/interventions', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) =>
    request<{ ok: boolean; message: string }>(`/api/interventions/${id}`, { method: 'PUT', body: data }),
};

// --- Équipements ---
export const equipements = {
  list: () => request<Array<Record<string, unknown>>>('/api/equipements'),
};

// --- Techniciens ---
export const techniciens = {
  list: () => request<Array<Record<string, unknown>>>('/api/techniciens'),
};

// --- Pièces ---
export const pieces = {
  list: () => request<Array<Record<string, unknown>>>('/api/pieces'),
};

// --- Demandes ---
export const demandes = {
  list: (statuts?: string) => {
    const qs = statuts ? `?statuts=${statuts}` : '';
    return request<Array<Record<string, unknown>>>(`/api/demandes${qs}`);
  },
};

export { ApiError };
export default { auth, dashboard, interventions, equipements, techniciens, pieces, demandes };
