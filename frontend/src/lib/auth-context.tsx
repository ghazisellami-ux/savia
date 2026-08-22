'use client';
// ==========================================
// 🔐 Auth Context — Savia (avec permissions par rôle)
// ==========================================
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { auth as authApi, SESSION_EXPIRED_EVENT } from './api';

export type PermissionsMap = Record<string, boolean>;

interface User {
  username: string;
  nom: string;
  role: string;
  client?: string;  // présent pour Lecteur
  password_change_required?: boolean;
}

interface AuthContextType {
  user: User | null;
  permissions: PermissionsMap;
  isLoading: boolean;
  isAuthenticated: boolean;
  hasPermission: (page: string) => boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const DEFAULT_PERMS: PermissionsMap = {};

const AuthContext = createContext<AuthContextType>({
  user: null,
  permissions: DEFAULT_PERMS,
  isLoading: true,
  isAuthenticated: false,
  hasPermission: () => true,
  login: async () => {},
  logout: () => {},
});

// Permissions par défaut selon le rôle (fallback si l'API échoue)
const DEFAULT_ROLE_PERMS: Record<string, PermissionsMap> = {
  Admin: {
    dashboard: true, supervision: true, equipements: true, predictions: true,
    base_connaissances: true, sav: true, planning: true, pieces: true,
    reports: true, contrats: true, admin: true, settings: true, demandes: true,
    finances: true, carte: true, sla: true,
  },
  Manager: {
    dashboard: true, supervision: true, equipements: true, predictions: true,
    base_connaissances: true, sav: true, planning: true, pieces: true,
    reports: true, contrats: true, admin: true, settings: true, demandes: true,
    finances: true, carte: true, sla: true,
  },
  'Responsable Technique': {
    dashboard: true, supervision: true, equipements: true, predictions: true,
    base_connaissances: true, sav: true, planning: true, pieces: false,
    reports: true, contrats: false, admin: false, settings: true, demandes: true,
    finances: false, carte: true, sla: true,
  },
  Technicien: {
    dashboard: true, supervision: true, equipements: true, predictions: true,
    base_connaissances: true, sav: true, planning: true, pieces: true,
    reports: true, contrats: true, admin: false, settings: true, demandes: true,
    finances: false, carte: true, sla: true,
  },
  Gestionnaire: {
    dashboard: true, supervision: false, equipements: true, predictions: true,
    base_connaissances: false, sav: false, planning: false, pieces: true,
    reports: true, contrats: true, admin: false, settings: true, demandes: false,
    finances: true, carte: true, sla: true,
  },
  'Gestionnaire de stock': {
    dashboard: true, supervision: false, equipements: true, predictions: true,
    base_connaissances: false, sav: false, planning: false, pieces: true,
    reports: true, contrats: true, admin: false, settings: true, demandes: false,
    finances: true, carte: true, sla: true,
  },
  Lecteur: {
    dashboard: true, supervision: true, equipements: true, predictions: false,
    base_connaissances: false, sav: false, planning: false, pieces: false,
    reports: true, contrats: false, admin: false, settings: true, demandes: false,
    finances: false, carte: true, sla: false,
  },
};

async function loadRolePermissions(role: string, token: string): Promise<PermissionsMap> {
  try {
    const res = await fetch('/api/settings/public', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('settings failed');
    const data = await res.json();
    const lang = data.langue === 'en' ? 'en' : 'fr';
    localStorage.setItem('savia_lang', lang);
    window.dispatchEvent(new CustomEvent('savia_language_changed', { detail: { lang } }));
    const allRolePerms = JSON.parse(data.role_permissions || '{}');
    if (allRolePerms[role]) return allRolePerms[role];
  } catch {}
  return DEFAULT_ROLE_PERMS[role] || DEFAULT_PERMS;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser]               = useState<User | null>(null);
  const [permissions, setPermissions] = useState<PermissionsMap>(DEFAULT_PERMS);
  const [isLoading, setIsLoading]     = useState(true);

  // Vérifier le token au chargement
  useEffect(() => {
    let active = true;

    const restoreSession = async () => {
      const token     = localStorage.getItem('savia_token');
      const savedUser = localStorage.getItem('savia_user');
      if (!token || !savedUser) {
        if (active) setIsLoading(false);
        return;
      }

      try {
        const u = JSON.parse(savedUser) as User;
        const session = await authApi.me();
        if (!active) return;
        const restoredUser = {
          ...u,
          password_change_required: Boolean(session.user.password_change_required),
        };
        setUser(restoredUser);
        localStorage.setItem('savia_user', JSON.stringify(restoredUser));
        if (!restoredUser.password_change_required) {
          // Wait for the persisted role permissions before marking the auth
          // state as ready. Otherwise a guarded page can briefly see the
          // fallback permissions and redirect a user who was granted access.
          const restoredPermissions = await loadRolePermissions(restoredUser.role, token);
          if (!active) return;
          setPermissions(restoredPermissions);
        }
      } catch {
        localStorage.removeItem('savia_token');
        localStorage.removeItem('savia_user');
      } finally {
        if (active) setIsLoading(false);
      }
    };

    restoreSession();
    return () => { active = false; };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await authApi.login(username, password);
    localStorage.setItem('savia_token', res.token);
    localStorage.setItem('savia_user', JSON.stringify(res.user));
    setUser(res.user);
    if (!res.user.password_change_required) {
      const perms = await loadRolePermissions(res.user.role, res.token);
      setPermissions(perms);
    } else {
      setPermissions(DEFAULT_PERMS);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('savia_token');
    localStorage.removeItem('savia_user');
    setUser(null);
    setPermissions(DEFAULT_PERMS);
  }, []);

  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, logout);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, logout);
  }, [logout]);

  const hasPermission = useCallback((page: string): boolean => {
    if (!user) return false;
    // Si les permissions sont vides → fallback sur les défauts du rôle
    const perms = Object.keys(permissions).length > 0
      ? permissions
      : (DEFAULT_ROLE_PERMS[user.role] || {});
    // Deny by default: la page doit être EXPLICITEMENT à true
    return perms[page] === true;
  }, [user, permissions]);

  return (
    <AuthContext.Provider value={{
      user, permissions, isLoading, isAuthenticated: !!user, hasPermission, login, logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export default AuthContext;
