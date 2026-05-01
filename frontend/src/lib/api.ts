// ==========================================
// 🌐 API Client — Savia Frontend
// ==========================================

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

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
  
  if (token && token !== 'undefined' && token !== 'null') {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const isAiEndpoint = endpoint.includes('/ai/');
  const timeoutMs = isAiEndpoint ? 180000 : 30000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
      method: options.method || 'GET',
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch(fetchErr: any) {
    clearTimeout(timer);
    if (fetchErr.name === 'AbortError') throw new ApiError('Timeout: L\'IA mettra trop de temps. Reessayez.', 408);
    throw new ApiError('Erreur reseau: ' + (fetchErr.message || 'indisponible'), 0);
  }
  clearTimeout(timer);

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
    const p = new URLSearchParams();
    if (params?.client) p.set('client', params.client);
    if (params?.date_start) p.set('date_start', params.date_start);
    if (params?.date_end) p.set('date_end', params.date_end);
    const qs = p.toString();
    return request<Record<string, number>>(`/api/dashboard/kpis${qs ? '?' + qs : ''}`);
  },
  healthScores: (params?: { client?: string; date_start?: string; date_end?: string }) => {
    const p = new URLSearchParams();
    if (params?.client) p.set('client', params.client);
    if (params?.date_start) p.set('date_start', params.date_start);
    if (params?.date_end) p.set('date_end', params.date_end);
    const qs = p.toString();
    return request<Array<{ machine: string; score: number; tendance: string; pannes: number; client?: string }>>(
      `/api/dashboard/health-scores${qs ? '?' + qs : ''}`
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

  // Fiche signée
  uploadFiche: async (id: number, file: File): Promise<{ ok: boolean; filename: string }> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : null;
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/interventions/${id}/fiche`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },
  downloadFicheUrl: (id: number): string => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : '';
    return `${API_BASE}/api/interventions/${id}/fiche?token=${token}`;
  },
  listFiches: () =>
    request<Array<Record<string, unknown>>>('/api/interventions/fiches'),
  updateFicheValidation: (id: number, validation: string) =>
    request<{ ok: boolean; validation: string }>(`/api/interventions/${id}/fiche-validation`, {
      method: 'PATCH',
      body: { validation },
    }),
};

// --- Équipements ---
export const equipements = {
  list: (client?: string) => {
    const qs = client ? `?client=${encodeURIComponent(client)}` : '';
    return request<Array<Record<string, unknown>>>(`/api/equipements${qs}`);
  },
  create: (data: Record<string, unknown>) => request<{ok: boolean; id: number | null}>('/api/equipements', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) => request<{ok: boolean}>(`/api/equipements/${id}`, { method: 'PUT', body: data }),
  delete: (id: number) => request<{ok: boolean}>(`/api/equipements/${id}`, { method: 'DELETE' }),
};

// --- Documents Techniques ---
export const documentsTechniques = {
  listAll: () => request<Array<Record<string, unknown>>>('/api/documents-techniques'),
  listByEquipment: (equipId: number) => request<Array<Record<string, unknown>>>(`/api/documents-techniques/${equipId}`),
  upload: (equipementId: number, nomFichier: string, contenuBase64: string) =>
    request<{ok: boolean}>('/api/documents-techniques/upload', {
      method: 'POST',
      body: { equipement_id: equipementId, nom_fichier: nomFichier, contenu_base64: contenuBase64 }
    }),
  download: (docId: number) => request<{ contenu_base64: string; nom_fichier: string }>(`/api/documents-techniques/download/${docId}`),
  delete: (docId: number) => request<{ok: boolean}>(`/api/documents-techniques/${docId}`, { method: 'DELETE' }),
};

// --- Techniciens ---
export const techniciens = {
  list: () => request<Array<Record<string, unknown>>>('/api/techniciens'),
  create: (data: Record<string, unknown>) => request<{ok: boolean}>('/api/techniciens', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) => request<{ok: boolean}>(`/api/techniciens/${id}`, { method: 'PUT', body: data }),
  delete: (id: number) => request<{ok: boolean}>(`/api/techniciens/${id}`, { method: 'DELETE' }),
};

// --- Pièces ---
export const pieces = {
  list: () => request<Array<Record<string, unknown>>>('/api/pieces'),
  create: (data: Record<string, unknown>) => request<{ok: boolean}>('/api/pieces', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) => request<{ok: boolean}>(`/api/pieces/${id}`, { method: 'PUT', body: data }),
  delete: (id: number) => request<{ok: boolean}>(`/api/pieces/${id}`, { method: 'DELETE' }),
};

// --- Notifications ---
export const notifications = {
  list: () => request<Array<Record<string, unknown>>>('/api/notifications'),
  count: () => request<{ count: number }>('/api/notifications/count'),
  markRead: (id: number) => request<{ ok: boolean }>(`/api/notifications/${id}/read`, { method: 'PATCH' }),
  markDone: (id: number) => request<{ ok: boolean }>(`/api/notifications/${id}/done`, { method: 'PATCH' }),
};

// --- Demandes ---
export const demandes = {
  list: (statuts?: string) => {
    const qs = statuts ? `?statuts=${statuts}` : '';
    return request<Array<Record<string, unknown>>>(`/api/demandes${qs}`);
  },
  create: (body: Record<string, unknown>) =>
    request<{ success: boolean }>('/api/demandes', { method: 'POST', body }),
  updateStatut: (id: number, body: Record<string, unknown>) =>
    request<{ success: boolean }>(`/api/demandes/${id}/statut`, { method: 'PUT', body }),
};

// --- Autres modules ---
export const contrats = {
  list: (client?: string) => {
    const qs = client ? `?client=${client}` : '';
    return request<Array<Record<string, unknown>>>(`/api/contrats${qs}`);
  },
  create: (data: Record<string, unknown>) =>
    request<{ ok: boolean }>('/api/contrats', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/contrats/${id}`, { method: 'PUT', body: data }),
  delete: (id: number) =>
    request<{ ok: boolean }>(`/api/contrats/${id}`, { method: 'DELETE' }),
};

export const conformite = {
  list: (client?: string) => {
    const qs = client ? `?client=${client}` : '';
    return request<Array<Record<string, unknown>>>(`/api/conformite${qs}`);
  },
};

export const planning = {
  list: (params?: { machine?: string; statut?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Array<Record<string, unknown>>>(`/api/planning?${qs}`);
  },
  create: (body: Record<string, unknown>) =>
    request<{ ok: boolean }>('/api/planning', { method: 'POST', body }),
  updateStatut: (id: number, body: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/planning/${id}`, { method: 'PUT', body }),
  delete: (id: number) =>
    request<{ ok: boolean }>(`/api/planning/${id}`, { method: 'DELETE' }),
};
export const knowledge = {
  list: () => request<Array<Record<string, unknown>>>('/api/knowledge'),
};

export const clients = {
  list: () => request<Array<Record<string, unknown>>>('/api/clients'),
  create: (data: Record<string, unknown>) => request<{ ok: boolean }>('/api/clients', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Record<string, unknown>) => request<{ ok: boolean }>(`/api/clients/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: number) => request<{ ok: boolean }>(`/api/clients/${id}`, { method: 'DELETE' }),
};

export const admin = {
  users: () => request<Array<Record<string, unknown>>>('/api/admin/users'),
  createUser: (data: Record<string, unknown>) =>
    request<{ ok: boolean }>('/api/admin/users', { method: 'POST', body: data }),
  updateUser: (id: number, data: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/admin/users/${id}`, { method: 'PUT', body: data }),
  deleteUser: (id: number) =>
    request<{ ok: boolean }>(`/api/admin/users/${id}`, { method: 'DELETE' }),
};

// --- AI Engine ---
export const ai = {
  analyzePerformance: (kpis: Record<string, unknown>, sym: string = "EUR") => 
    request<{ok: boolean, result: Record<string, unknown>}>('/api/ai/analyze-performance', { method: 'POST', body: {kpis, sym} }),
  analyzeDiagnostic: (machine: string, code_erreur: string, message_erreur: string, log_context: string = "") =>
    request<{ok: boolean, result: any}>('/api/ai/analyze-diagnostic', { method: 'POST', body: { machine, code_erreur, message_erreur, log_context } }),
  analyzeSav: (sav_data: Record<string, unknown>, sym: string = "TND") =>
    request<{ok: boolean, result: any}>('/api/ai/analyze-sav', { method: 'POST', body: { sav_data, sym } }),
  analyzePieces: (pieces: any[], sym: string = "TND") =>
    request<{ok: boolean, result: any}>('/api/ai/analyze-pieces', { method: 'POST', body: { pieces, sym } }),
};

// --- Logs / S3 ---
export const logs = {
  list: (machine?: string) => {
    const qs = machine ? `?machine=${encodeURIComponent(machine)}` : '';
    return request<Array<{ key: string; size: number; last_modified: string }>>(`/api/logs${qs}`);
  },
  delete: (key: string) =>
    request<{ ok: boolean; message: string }>(`/api/logs?key=${encodeURIComponent(key)}`, { method: 'DELETE' }),
  deleteMachine: (machineName: string) =>
    request<{ ok: boolean; deleted: number; message: string }>(`/api/logs/machine/${encodeURIComponent(machineName)}`, { method: 'DELETE' }),
};

// --- Finances ---
export const finances = {
  dashboard: (client?: string) => {
    const qs = client ? `?client=${encodeURIComponent(client)}` : '';
    return request<{ kpis: Record<string, number>; clients: Array<Record<string, unknown>> }>(`/api/finances/dashboard${qs}`);
  },
  tco: (client?: string) => {
    const qs = client ? `?client=${encodeURIComponent(client)}` : '';
    return request<Array<Record<string, unknown>>>(`/api/finances/tco${qs}`);
  },
};

// --- Map ---
export const mapApi = {
  sites: () => request<Array<Record<string, unknown>>>('/api/map/sites'),
  updateCoordinates: (clientName: string, data: { latitude: number; longitude: number; adresse?: string }) =>
    request<{ ok: boolean }>(`/api/map/sites/${encodeURIComponent(clientName)}/coordinates`, { method: 'PUT', body: data }),
};

// --- SLA ---
export const sla = {
  status: (client?: string) => {
    const qs = client ? `?client=${encodeURIComponent(client)}` : '';
    return request<{ kpis: Record<string, number>; items: Array<Record<string, unknown>> }>(`/api/sla/status${qs}`);
  },
};

export { ApiError };
export default { auth, dashboard, interventions, equipements, documentsTechniques, techniciens, pieces, notifications, demandes, contrats, conformite, planning, knowledge, clients, admin, ai, logs, finances, mapApi, sla };
