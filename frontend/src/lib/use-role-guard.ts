// ==========================================
// 🔐 Hook: useRoleGuard — Redirection si pas la permission
// ==========================================
'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from './auth-context';

/**
 * Redirige vers /dashboard si l'utilisateur n'a pas la permission pour `page`.
 * Usage: useRoleGuard('sav') dans le composant de la page SAV.
 */
export function useRoleGuard(page: string) {
  const { hasPermission, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !hasPermission(page)) {
      router.replace('/dashboard');
    }
  }, [isLoading, hasPermission, page, router]);
}

/**
 * Retourne true si l'utilisateur peut voir les coûts (non-Lecteur).
 */
export function useCanSeeCosts(): boolean {
  const { user } = useAuth();
  return user?.role !== 'Lecteur';
}
