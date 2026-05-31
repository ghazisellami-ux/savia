'use client';
// ==========================================
// 🔒 Layout Authentifié — avec Sidebar collapsible
// ==========================================
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { AuthProvider, useAuth } from '@/lib/auth-context';
import Sidebar from '@/components/layout/sidebar';
import { clsx } from 'clsx';

const SIDEBAR_COLLAPSED_KEY = 'savia_sidebar_collapsed';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Lire la préférence sauvegardée (après montage pour éviter hydration mismatch)
  useEffect(() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (saved === 'true') setIsCollapsed(true);
    setMounted(true);
  }, []);

  const handleToggle = useCallback(() => {
    setIsCollapsed(prev => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
  }, []);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-savia-bg">
        <div className="text-center animate-fade-in">
          <div className="animate-pulse-glow w-8 h-8 rounded-full bg-savia-accent mx-auto mb-4" />
          <p className="text-savia-text-muted text-sm">Chargement de SAVIA...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="flex min-h-screen">
      <Sidebar isCollapsed={isCollapsed} onToggle={handleToggle} />
      <main
        className={clsx(
          'flex-1 p-6 overflow-auto transition-all duration-300 ease-in-out',
          // Utiliser ml fixe seulement après montage (évite flash)
          mounted
            ? isCollapsed ? 'ml-16' : 'ml-64'
            : 'ml-64'
        )}
      >
        {children}
      </main>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthGuard>{children}</AuthGuard>
    </AuthProvider>
  );
}
