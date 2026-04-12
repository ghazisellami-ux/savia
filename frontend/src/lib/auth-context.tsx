'use client';
// ==========================================
// 🔐 Auth Context — Savia
// ==========================================
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { auth as authApi } from './api';

interface User {
  username: string;
  nom: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Vérifier le token au chargement
  useEffect(() => {
    const token = localStorage.getItem('savia_token');
    const savedUser = localStorage.getItem('savia_user');
    if (token && savedUser) {
      try {
        setUser(JSON.parse(savedUser));
      } catch {
        localStorage.removeItem('savia_token');
        localStorage.removeItem('savia_user');
      }
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await authApi.login(username, password);
    localStorage.setItem('savia_token', res.token);
    localStorage.setItem('savia_user', JSON.stringify(res.user));
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('savia_token');
    localStorage.removeItem('savia_user');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export default AuthContext;
