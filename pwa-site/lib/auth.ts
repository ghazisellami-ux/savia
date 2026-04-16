// ==========================================
// 🔐 Auth — SAVIA Site
// ==========================================
export interface SaviaUser {
  id: number;
  nom: string;
  role: string;
  username: string;
}

const TOKEN_KEY = 'savia_site_token';
const USER_KEY  = 'savia_site_user';

export function getToken(): string | null {
  return typeof window !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null;
}

export function getUser(): SaviaUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function saveSession(token: string, user: SaviaUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isLoggedIn(): boolean {
  return !!getToken() && !!getUser();
}
