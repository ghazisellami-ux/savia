// ==========================================
// 🌐 API Client — Savia Frontend
// ==========================================

// Browser requests stay same-origin and are forwarded by Next.js to the backend.
// This avoids exposing a build-time localhost URL that breaks Docker and CORS.
const API_BASE = '';
export const SESSION_EXPIRED_EVENT = 'savia_session_expired';

export function expireSession(): void {
  if (typeof window === 'undefined') return;
  // Remove the pre-cookie credential if an older deployment left it behind.
  localStorage.removeItem('savia_token');
  localStorage.removeItem('savia_user');
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

interface ApiOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
  const lang = typeof window !== 'undefined' ? (localStorage.getItem('savia_lang') || 'fr') : 'fr';
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-SAVIA-Lang': lang,
    ...options.headers,
  };
  
  const isAiEndpoint = endpoint.includes('/ai/');
  // Certaines analyses IA SAV prennent plus de 30 secondes (notamment avec
  // un modèle de raisonnement). Le backend peut déjà avoir terminé avec 200
  // alors qu'un ancien délai client provoque à tort une erreur réseau.
  const timeoutMs = options.timeoutMs ?? (isAiEndpoint ? 300000 : 30000);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
      method: options.method || 'GET',
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: 'same-origin',
      signal: controller.signal,
    });
  } catch(fetchErr: any) {
    clearTimeout(timer);
    if (fetchErr.name === 'AbortError') {
      throw new ApiError(
        isAiEndpoint ? "Timeout : l'IA met trop de temps. Réessayez." : 'La requête a expiré. Réessayez.',
        408,
      );
    }
    throw new ApiError('Erreur reseau: ' + (fetchErr.message || 'indisponible'), 0);
  }
  clearTimeout(timer);

  if (!res.ok) {
    if (res.status === 401 && endpoint !== '/api/auth/login' && endpoint !== '/api/auth/change-password') {
      expireSession();
    }
    const data = await res.json().catch(() => ({ error: 'Erreur réseau' }));
    if (res.status === 428 && isAiEndpoint && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('savia_ai_consent_required'));
    }
    throw new ApiError(data.error || data.detail || `HTTP ${res.status}`, res.status);
  }

  return res.json();
}

// --- Auth ---
export const auth = {
  login: (username: string, password: string) =>
    request<{ token?: string; password_change_required: boolean; user: { username: string; nom: string; role: string; client?: string; pages_autorisees?: string; password_change_required?: boolean } }>(
      '/api/auth/login', { method: 'POST', body: { username, password } }
    ),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  me: () => request<{ user: { sub: string; role: string; nom: string; client?: string; pages_autorisees?: string; password_change_required?: boolean } }>('/api/auth/me'),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ token?: string; password_change_required: boolean; user: { username: string; nom: string; role: string; client?: string; pages_autorisees?: string; password_change_required?: boolean } }>(
      '/api/auth/change-password', { method: 'POST', body: { current_password: currentPassword, new_password: newPassword } }
    ),
};

// --- Dashboard ---
export const dashboard = {
  regions: () => request<string[]>('/api/dashboard/regions'),
  villes: (region: string) =>
    request<string[]>(`/api/dashboard/villes?region=${encodeURIComponent(region)}`),
  clientsByRegion: (region?: string) =>
    request<string[]>(`/api/dashboard/clients-by-region${region ? `?region=${encodeURIComponent(region)}` : ''}`),
  equipmentTypes: (params?: { client?: string; region?: string; ville?: string }) => {
    const p = new URLSearchParams();
    if (params?.client) p.set('client', params.client);
    if (params?.region) p.set('region', params.region);
    if (params?.ville) p.set('ville', params.ville);
    const qs = p.toString();
    return request<string[]>(`/api/dashboard/equipment-types${qs ? '?' + qs : ''}`);
  },
  kpis: (params?: { date_start?: string; date_end?: string; client?: string; region?: string; ville?: string; equipment_type?: string }) => {
    const p = new URLSearchParams();
    if (params?.client) p.set('client', params.client);
    if (params?.region) p.set('region', params.region);
    if (params?.ville) p.set('ville', params.ville);
    if (params?.equipment_type) p.set('equipment_type', params.equipment_type);
    if (params?.date_start) p.set('date_start', params.date_start);
    if (params?.date_end) p.set('date_end', params.date_end);
    const qs = p.toString();
    return request<Record<string, number>>(`/api/dashboard/kpis${qs ? '?' + qs : ''}`);
  },
  healthScores: (params?: { client?: string; region?: string; ville?: string; equipment_type?: string; date_start?: string; date_end?: string }) => {
    const p = new URLSearchParams();
    if (params?.client) p.set('client', params.client);
    if (params?.region) p.set('region', params.region);
    if (params?.ville) p.set('ville', params.ville);
    if (params?.equipment_type) p.set('equipment_type', params.equipment_type);
    if (params?.date_start) p.set('date_start', params.date_start);
    if (params?.date_end) p.set('date_end', params.date_end);
    const qs = p.toString();
    return request<Array<{ machine: string; score: number; tendance: string; pannes: number; client?: string }>>(
      `/api/dashboard/health-scores${qs ? '?' + qs : ''}`
    );
  },
  predictions: (params?: { client?: string; equipment_type?: string; horizon_days?: number }) => {
    const p = new URLSearchParams();
    if (params?.client) p.set('client', params.client);
    if (params?.equipment_type) p.set('equipment_type', params.equipment_type);
    if (params?.horizon_days) p.set('horizon_days', String(params.horizon_days));
    const qs = p.toString();
    return request<{
      items: Array<Record<string, unknown>>;
      meta: Record<string, unknown>;
    }>(`/api/dashboard/predictions${qs ? '?' + qs : ''}`);
  },
};

export const predictionFeedback = {
  create: (data: Record<string, unknown>) =>
    request<{ ok: boolean }>('/api/predictions/feedback', { method: 'POST', body: data }),
  list: (limit = 100) =>
    request<Array<Record<string, unknown>>>(`/api/predictions/feedback?limit=${limit}`),
};

// --- Interventions ---
export const interventions = {
  list: (params?: { machine?: string; technicien?: string; offset?: number; limit?: number }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Array<Record<string, unknown>>>(`/api/interventions?${qs}`);
  },
  filterOptions: (params?: { year?: number; month?: number; client?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params || {}).reduce<Record<string, string>>((acc, [key, value]) => {
        if (value !== undefined && value !== null && value !== '') acc[key] = String(value);
        return acc;
      }, {}),
    ).toString();
    return request<{ types: string[]; equipements: string[]; clients: string[]; statuts: string[]; annees: number[] }>(
      `/api/interventions/filter-options${qs ? `?${qs}` : ''}`,
    );
  },
  create: (data: Record<string, unknown>) =>
    request<{ ok: boolean; message: string }>('/api/interventions', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) =>
    request<{ ok: boolean; message: string }>(`/api/interventions/${id}`, { method: 'PUT', body: data }),

  // Fiche signée
  uploadFiche: async (id: number, file: File): Promise<{ ok: boolean; filename: string }> => {
    const lang = typeof window !== 'undefined' ? (localStorage.getItem('savia_lang') || 'fr') : 'fr';
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/interventions/${id}/fiche`, {
      method: 'POST',
      headers: { 'X-SAVIA-Lang': lang },
      credentials: 'same-origin',
      body: form,
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  },
  downloadFiche: async (id: number): Promise<Blob> => {
    const res = await fetch(`${API_BASE}/api/interventions/${id}/fiche`, {
      credentials: 'same-origin',
    });
    if (!res.ok) throw new ApiError(`Impossible de télécharger la fiche (${res.status})`, res.status);
    return res.blob();
  },
  listFiches: () =>
    request<Array<Record<string, unknown>>>('/api/interventions/fiches'),
  updateFicheValidation: (id: number, validation: string) =>
    request<{ ok: boolean; validation: string }>(`/api/interventions/${id}/fiche-validation`, {
      method: 'PATCH',
      body: { validation },
    }),
  delete: (id: number) =>
    request<{ ok: boolean }>(`/api/interventions/${id}`, { method: 'DELETE' }),
};

// --- Équipements ---
export const equipements = {
  list: (client?: string) => {
    const qs = client ? `?client=${encodeURIComponent(client)}` : '';
    return request<Array<Record<string, unknown>>>(`/api/equipements${qs}`);
  },
  create: (data: Record<string, unknown>) => request<{ok: boolean; id: number | null}>('/api/equipements', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) => request<{ok: boolean}>(`/api/equipements/${id}`, { method: 'PUT', body: data }),
  history: (id: number) => request<Array<Record<string, unknown>>>(`/api/equipements/${id}/historique-statuts`),
  reactivate: (id: number, raison?: string) => request<{ok: boolean; statut: string}>(`/api/equipements/${id}/remise-en-service`, { method: 'PUT', body: { raison } }),
  delete: (id: number) => request<{ok: boolean}>(`/api/equipements/${id}`, { method: 'DELETE' }),
};

// --- Documents Techniques ---
export const documentsTechniques = {
  listAll: () => request<Array<Record<string, unknown>>>('/api/documents-techniques'),
  listByEquipment: (equipId: number) => request<Array<Record<string, unknown>>>(`/api/documents-techniques/${equipId}`),
  upload: (data: { nomFichier: string; contenuBase64: string; domaine: string; typeEquipement: string; fabricant: string; modele?: string }) =>
    request<{ok: boolean}>('/api/documents-techniques/upload', {
      method: 'POST',
      body: {
        nom_fichier: data.nomFichier,
        contenu_base64: data.contenuBase64,
        domaine: data.domaine,
        type_equipement: data.typeEquipement,
        fabricant: data.fabricant,
        modele: data.modele || '',
      },
      timeoutMs: 120000,
    }),
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
  exchangeRates: () => request<{ base_code: string; rates: Record<string, number>; updated_at?: string; cached?: boolean }>('/api/currency-rates'),
  create: (data: Record<string, unknown>) => request<{ok: boolean}>('/api/pieces', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) => request<{ok: boolean}>(`/api/pieces/${id}`, { method: 'PUT', body: data }),
  delete: (id: number) => request<{ok: boolean}>(`/api/pieces/${id}`, { method: 'DELETE' }),
  prediction: (id: number) => request<Record<string, unknown>>(`/api/pieces/${id}/prediction`, { method: 'POST' }),
  predictionFeedback: (data: Record<string, unknown>) =>
    request<{ ok: boolean }>('/api/pieces/prediction-feedback', { method: 'POST', body: data }),
  predictionFeedbackList: (limit = 100) =>
    request<Array<Record<string, unknown>>>(`/api/pieces/prediction-feedback?limit=${limit}`),
};

export const fournisseurs = {
  list: () => request<Array<{ id: number; nom: string }>>('/api/fournisseurs'),
  create: (nom: string) => request<{ ok: boolean }>('/api/fournisseurs', { method: 'POST', body: { nom } }),
};

export const piecesDemandees = {
  list: (statut?: string) => request<Array<Record<string, unknown>>>(`/api/pieces-demandees${statut ? `?statut=${statut}` : ''}`),
  resoudre: (id: number) => request<{ok: boolean}>(`/api/pieces-demandees/${id}/resoudre`, { method: 'POST' }),
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
    request<{ success: boolean; demande_id: number; intervention_id: number; billing_case_id?: number | null }>('/api/demandes', { method: 'POST', body }),
  updateStatut: (id: number, body: Record<string, unknown>) =>
    request<{ success: boolean }>(`/api/demandes/${id}/statut`, { method: 'PUT', body }),
  delete: (id: number) =>
    request<{ success: boolean }>(`/api/demandes/${id}`, { method: 'DELETE' }),
};

// --- Autres modules ---
export const contrats = {
  list: (client?: string) => {
    const qs = client ? `?client=${client}` : '';
    return request<Array<Record<string, unknown>>>(`/api/contrats${qs}`);
  },
  create: (data: Record<string, unknown>) =>
    request<{ ok: boolean; contrat_id?: number; nb_plannings?: number }>('/api/contrats', { method: 'POST', body: data }),
  uploadFile: async (id: string | number, file: File) => {
    const lang = typeof window !== 'undefined' ? (localStorage.getItem('savia_lang') || 'fr') : 'fr';
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = { 'X-SAVIA-Lang': lang };
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60000);
    let res: Response;
    try {
      res = await fetch(`/api/contrats/${id}/fichiers`, {
        method: 'POST',
        headers,
        credentials: 'same-origin',
        body: formData,
        signal: controller.signal,
      });
    } catch (error: any) {
      if (error?.name === 'AbortError') throw new Error('Délai dépassé pendant l’envoi de la pièce jointe');
      throw new Error(`Erreur réseau pendant l’envoi : ${error?.message || 'indisponible'}`);
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: 'Erreur réseau' }));
      throw new Error(data.error || data.detail || `HTTP ${res.status}`);
    }
    return res.json() as Promise<{ ok: boolean; id: number; filename: string; content_type: string; size_bytes: number; already_attached?: boolean }>;
  },
  downloadFile: async (id: string | number, fileId: number) => {
    const res = await fetch(`/api/contrats/${id}/fichiers/${fileId}`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('Pièce jointe indisponible');
    return res.blob();
  },
  deleteFile: (id: string | number, fileId: number) =>
    request<{ ok: boolean; contrat_id: string | number; fichier_id: number }>(`/api/contrats/${id}/fichiers/${fileId}`, { method: 'DELETE' }),
  update: (id: number, data: Record<string, unknown>) =>
    request<{ ok: boolean; planning?: { removed: number; created: number } | null }>(`/api/contrats/${id}`, { method: 'PUT', body: data }),
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
  reschedule: (id: number, body: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/planning/${id}/reschedule`, { method: 'PUT', body }),
  comparateur: (id: number) =>
    request<Record<string, unknown>>(`/api/planning/${id}/comparateur`),
  comparateurPeriode: (dateDebut: string, dateFin: string) =>
    request<Record<string, unknown>>(`/api/planning/comparateur-periode?date_debut=${dateDebut}&date_fin=${dateFin}`),
  delete: (id: number) =>
    request<{ ok: boolean; deleted_planning: number; deleted_interventions: number; recurring: boolean }>(`/api/planning/${id}`, { method: 'DELETE' }),
};
export const knowledge = {
  list: () => request<Array<Record<string, unknown>>>('/api/knowledge'),
};

export const clients = {
  list: () => request<Array<Record<string, unknown>>>('/api/clients'),
  create: (data: Record<string, unknown>) => request<{ ok: boolean }>('/api/clients', { method: 'POST', body: data }),
  update: (id: number, data: Record<string, unknown>) => request<{ ok: boolean }>(`/api/clients/${id}`, { method: 'PUT', body: data }),
  delete: (id: number) => request<{ ok: boolean }>(`/api/clients/${id}`, { method: 'DELETE' }),
  importExcel: async (file: File): Promise<Record<string, unknown>> => {
    const fd = new FormData();
    fd.append('file', file);
    const lang = typeof window !== 'undefined' ? (localStorage.getItem('savia_lang') || 'fr') : 'fr';
    const res = await fetch('/api/clients/import-excel', {
      method: 'POST',
      headers: { 'X-SAVIA-Lang': lang },
      credentials: 'same-origin',
      body: fd,
    });
    if (!res.ok) throw new Error('Erreur import: ' + res.status);
    return res.json() as Promise<Record<string, unknown>>;
  },
};

export const fabricants = {
  list: () => request<Array<{ id: number; nom: string }>>('/api/fabricants'),
  create: (nom: string) => request<{ ok: boolean }>('/api/fabricants', { method: 'POST', body: { nom } }),
};

export const modelesEquipement = {
  list: (filters?: { domaine?: string; type?: string; fabricant?: string }) => {
    const params = new URLSearchParams();
    if (filters?.domaine) params.set('domaine', filters.domaine);
    if (filters?.type) params.set('type', filters.type);
    if (filters?.fabricant) params.set('fabricant', filters.fabricant);
    const qs = params.toString();
    return request<Array<{ id: number; nom: string; domaine: string; type_equipement: string; fabricant: string }>>(`/api/modeles-equipement${qs ? `?${qs}` : ''}`);
  },
  create: (data: { nom: string; domaine: string; type: string; fabricant: string }) =>
    request<{ ok: boolean; created: boolean; id: number; nom: string }>('/api/modeles-equipement', { method: 'POST', body: data }),
};

export const servicesEquipement = {
  list: () => request<Array<{ id: number; nom: string }>>('/api/services-equipement'),
  create: (nom: string) => request<{ ok: boolean }>('/api/services-equipement', { method: 'POST', body: { nom } }),
};

export const typesEquipement = {
  list: (domaine: string) => request<Array<{ id: number; nom: string; domaine: string }>>(`/api/types-equipement-custom?domaine=${encodeURIComponent(domaine)}`),
  create: (nom: string, domaine: string) => request<{ ok: boolean }>('/api/types-equipement-custom', { method: 'POST', body: { nom, domaine } }),
  delete: (id: number) => request<{ ok: boolean }>(`/api/types-equipement-custom/${id}`, { method: 'DELETE' }),
};

export const typesIntervention = {
  list: () => request<Array<{ id: number; nom: string }>>('/api/types-intervention-custom'),
  create: (nom: string) => request<{ ok: boolean }>('/api/types-intervention-custom', { method: 'POST', body: { nom } }),
};

export const typesClient = {
  list: () => request<Array<{ id: number; nom: string }>>('/api/types-client-custom'),
  create: (nom: string) => request<{ ok: boolean }>('/api/types-client-custom', { method: 'POST', body: { nom } }),
};

export const villesCustom = {
  list: (countryCode: string) => request<Array<{ id: number; country_code: string; nom: string; latitude?: number | null; longitude?: number | null }>>(`/api/villes-custom?country=${encodeURIComponent(countryCode)}`),
  create: (countryCode: string, nom: string, coordinates?: [number, number] | null) => request<{ ok: boolean; city?: { country_code: string; nom: string; latitude?: number | null; longitude?: number | null } }>('/api/villes-custom', { method: 'POST', body: { country_code: countryCode, nom, latitude: coordinates?.[0], longitude: coordinates?.[1] } }),
  update: (countryCode: string, nom: string, nouveauNom: string) => request<{ ok: boolean; city?: { country_code: string; nom: string; latitude?: number | null; longitude?: number | null } }>(`/api/villes-custom/${encodeURIComponent(countryCode)}/${encodeURIComponent(nom)}`, { method: 'PUT', body: { nom: nouveauNom } }),
  delete: (countryCode: string, nom: string) => request<{ ok: boolean }>(`/api/villes-custom/${encodeURIComponent(countryCode)}/${encodeURIComponent(nom)}`, { method: 'DELETE' }),
};

export const paysCustom = {
  list: () => request<Array<{ id: number; code: string; nom: string; flag?: string; latitude?: number | null; longitude?: number | null }>>('/api/pays-custom'),
  create: (nom: string, flag = '🌍') => request<{ ok: boolean; country?: { id: number; code: string; nom: string; flag?: string; latitude?: number | null; longitude?: number | null } }>('/api/pays-custom', { method: 'POST', body: { nom, flag } }),
  delete: (code: string) => request<{ ok: boolean }>(`/api/pays-custom/${encodeURIComponent(code)}`, { method: 'DELETE' }),
};

export const admin = {
  users: () => request<Array<Record<string, unknown>>>('/api/admin/users'),
  createUser: (data: Record<string, unknown>) =>
    request<{ ok: boolean }>('/api/admin/users', { method: 'POST', body: data }),
  updateUser: (id: number, data: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/admin/users/${id}`, { method: 'PUT', body: data }),
  deleteUser: (id: number) =>
    request<{ ok: boolean }>(`/api/admin/users/${id}`, { method: 'DELETE' }),
  aiGovernance: () => request<any>('/api/admin/ai-governance'),
  updateAiOffer: (code: string, data: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/admin/ai-governance/offers/${code}`, { method: 'PUT', body: data }),
  updateActiveAiOffer: (offer_code: string) =>
    request<{ ok: boolean }>('/api/admin/ai-governance/active-offer', { method: 'PUT', body: { offer_code } }),
  updateAiUser: (id: number, data: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/admin/ai-governance/users/${id}`, { method: 'PUT', body: data }),
  updateAiDataLocation: (data_location: string) =>
    request<{ ok: boolean }>('/api/admin/ai-governance/data-location', { method: 'PUT', body: { data_location } }),
};

// --- AI Engine ---
export const ai = {
  analyzePerformance: (kpis: Record<string, unknown>, sym: string = "EUR") => 
    request<{ok: boolean, result: Record<string, unknown>}>('/api/ai/analyze-performance', { method: 'POST', body: {kpis, sym} }),
  analyzeDiagnostic: (machine: string, code_erreur: string, message_erreur: string, log_context: string = "", equipment_type: string = "") =>
    request<{ok: boolean, result: Record<string, unknown>}>('/api/ai/analyze-diagnostic', { method: 'POST', body: { machine, code_erreur, message_erreur, log_context, equipment_type } }),
  analyzeSav: (sav_data: Record<string, unknown>, sym: string = "TND") =>
    request<{ok: boolean, result: Record<string, unknown>}>('/api/ai/analyze-sav', { method: 'POST', body: { sav_data, sym } }),
  analyzePieces: (pieces: Array<Record<string, unknown>>, sym: string = "USD", domain: string = "", equipment_type: string = "") =>
    request<{ok: boolean, result: Record<string, unknown>}>('/api/ai/analyze-pieces', { method: 'POST', body: { pieces, sym, domain, equipment_type } }),
  chat: (message: string, history: Array<{role: string, content: string}> = []) =>
    request<{response: string, suggestions: string[]}>('/api/ai/chat', { method: 'POST', body: { message, history } }),
  analyzeCosts: (clients: Array<Record<string, unknown>>, kpis: Record<string, unknown>, sym: string = "TND") =>
    request<{ok: boolean, result: Record<string, unknown>}>('/api/ai/analyze-costs', { method: 'POST', body: { clients, kpis, sym } }),
  analyzeCostsPdf: async (result: Record<string, unknown>, kpis: Record<string, unknown>, sym: string = "TND") => {
    const lang = localStorage.getItem('savia_lang') || 'fr';
    const cn = localStorage.getItem('savia_company') || 'SAVIA';
    const cl = localStorage.getItem('savia_logo') || '';
    const res = await fetch('/api/ai/analyze-costs/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-SAVIA-Lang': lang },
      credentials: 'same-origin',
      body: JSON.stringify({ result, kpis, sym, company_name: cn, company_logo: cl }),
    });
    if (!res.ok) throw new Error('Erreur PDF');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'SAVIA_Analyse_Couts_IA.pdf';
    a.click();
    URL.revokeObjectURL(url);
  },
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
  sites: (country?: string) => request<Array<Record<string, unknown>>>(`/api/map/sites${country ? `?country=${encodeURIComponent(country)}` : ''}`),
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

// --- Settings ---
export const settings = {
  get: () => request<Record<string, string>>('/api/settings'),
  public: () => request<Record<string, string>>('/api/settings/public'),
};

// --- Custom Domains ---
export const domaines_custom = {
  list: () => request<Array<Record<string, unknown>>>('/api/domaines-custom'),
  create: (nom: string) => request<{ ok: boolean; domaine?: { id: number; nom: string } }>('/api/domaines-custom', { method: 'POST', body: { nom } }),
  delete: (nom: string) => request<{ ok: boolean }>(`/api/domaines-custom/${encodeURIComponent(nom)}`, { method: 'DELETE' }),
};

// --- Suivi facturation ---
export const billing = {
  responsibles: () => request<Array<Record<string, unknown>>>('/api/billing/responsibles'),
  list: (filters?: { status?: string; client?: string; search?: string }) => {
    const params = new URLSearchParams();
    if (filters?.status) params.set('status', filters.status);
    if (filters?.client) params.set('client', filters.client);
    if (filters?.search) params.set('search', filters.search);
    const qs = params.toString();
    return request<Array<Record<string, unknown>>>(`/api/billing/cases${qs ? `?${qs}` : ''}`);
  },
  get: (caseId: number) => request<Record<string, unknown>>(`/api/billing/cases/${caseId}`),
  delete: (caseId: number) => request<{ ok: boolean; case_id: number; replacement_case_id?: number | null }>(`/api/billing/cases/${caseId}`, { method: 'DELETE' }),
  reassessCoverage: (caseId: number) =>
    request<Record<string, unknown>>(`/api/billing/cases/${caseId}/reassess-coverage`, { method: 'POST' }),
  create: (data: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/billing/cases', { method: 'POST', body: data }),
  updateCase: (caseId: number, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/billing/cases/${caseId}`, { method: 'PATCH', body: data }),
  resolveDuplicate: (data: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/billing/cases/resolve-duplicate', { method: 'POST', body: data }),
  saveStep: (caseId: number, stepType: string, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/billing/cases/${caseId}/steps/${encodeURIComponent(stepType)}`, { method: 'PUT', body: data }),
  saveDeliveryNotes: (caseId: number, deliveryNotes: Array<Record<string, unknown>>) =>
    request<Record<string, unknown>>(`/api/billing/cases/${caseId}/delivery-notes`, { method: 'PUT', body: { delivery_notes: deliveryNotes } }),
  saveInvoices: (caseId: number, invoices: Array<Record<string, unknown>>) =>
    request<Record<string, unknown>>(`/api/billing/cases/${caseId}/invoices`, { method: 'PUT', body: { invoices } }),
  addPayment: (caseId: number, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/billing/cases/${caseId}/payments`, { method: 'POST', body: data }),
  updatePayment: (caseId: number, paymentId: number, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/billing/cases/${caseId}/payments/${paymentId}`, { method: 'PUT', body: data }),
  history: (caseId: number) =>
    request<Array<Record<string, unknown>>>(`/api/billing/cases/${caseId}/history`),
};

// --- Suivi des marchés publics ---
export const publicMarkets = {
  responsibles: () => request<Array<Record<string, unknown>>>('/api/public-markets/responsibles'),
  list: (filters?: { status?: string; client?: string; search?: string }) => {
    const params = new URLSearchParams();
    if (filters?.status) params.set('status', filters.status);
    if (filters?.client) params.set('client', filters.client);
    if (filters?.search) params.set('search', filters.search);
    const qs = params.toString();
    return request<Array<Record<string, unknown>>>(`/api/public-markets/cases${qs ? `?${qs}` : ''}`);
  },
  get: (caseId: number) => request<Record<string, unknown>>(`/api/public-markets/cases/${caseId}`),
  create: (data: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/public-markets/cases', { method: 'POST', body: data }),
  update: (caseId: number, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/public-markets/cases/${caseId}`, { method: 'PATCH', body: data }),
  history: (caseId: number) =>
    request<Array<Record<string, unknown>>>(`/api/public-markets/cases/${caseId}/history`),
};

export { ApiError };

// Default export for backward compatibility
const apiClient = { auth, dashboard, interventions, equipements, documentsTechniques, techniciens, pieces, piecesDemandees, notifications, demandes, contrats, conformite, planning, knowledge, clients, admin, ai, logs, finances, billing, publicMarkets, mapApi, sla, typesIntervention, typesClient, villesCustom, paysCustom, settings };
export default apiClient;
