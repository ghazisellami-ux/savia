'use client';
// ==========================================
// 📌 Sidebar Navigation — Savia (avec contrôle d'accès par rôle)
// ==========================================
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/lib/auth-context';
import { useEffect, useState, useCallback } from 'react';
import {
  BarChart3, Monitor, Hospital, TrendingUp, BookOpen,
  Wrench, ClipboardList, CalendarDays, Cog, FileText,
  ClipboardCheck, Settings, LogOut, SlidersHorizontal,
} from 'lucide-react';
import { clsx } from 'clsx';

// key doit correspondre aux clés dans role_permissions
const NAV_ITEMS = [
  { key: 'dashboard',          label: 'Dashboard',               href: '/dashboard',  icon: BarChart3      },
  { key: 'supervision',        label: 'Supervision',             href: '/supervision', icon: Monitor        },
  { key: 'equipements',        label: 'Équipements',             href: '/equipements', icon: Hospital       },
  { key: 'predictions',        label: 'Prédictions',             href: '/predictions', icon: TrendingUp     },
  { key: 'base_connaissances', label: 'Base de Connaissances',  href: '/knowledge',   icon: BookOpen       },
  { key: 'sav',                label: 'SAV & Interventions',    href: '/sav',         icon: Wrench         },
  { key: 'demandes',           label: "Demandes d'Intervention", href: '/demandes',   icon: ClipboardList  },
  { key: 'planning',           label: 'Planning',               href: '/planning',    icon: CalendarDays   },
  { key: 'pieces',             label: 'Pièces de Rechange',     href: '/pieces',      icon: Cog            },
  { key: 'reports',            label: 'Rapports & Exports',     href: '/reports',     icon: FileText       },
  { key: 'contrats',           label: 'Contrats & SLA',         href: '/contrats',    icon: ClipboardCheck },
  { key: 'admin',              label: 'Administration',         href: '/admin',       icon: Settings       },
  { key: 'settings',           label: 'Paramètres',             href: '/settings',    icon: SlidersHorizontal },
];

const ROLE_COLOR: Record<string, string> = {
  Admin: 'text-purple-400', Manager: 'text-purple-400',
  'Responsable Technique': 'text-blue-400', Technicien: 'text-cyan-400',
  Gestionnaire: 'text-amber-400', Lecteur: 'text-green-400',
};

// Rôles qui reçoivent les notifications de nouvelles demandes
const NOTIF_ROLES = ['Admin', 'Manager', 'Responsable Technique', 'Gestionnaire', 'Lecteur', 'Technicien'];
// Rôles qui voient le badge pièces (rupture pour gestionnaires, dispo pour techniciens)
const PIECES_NOTIF_ROLES = ['Admin', 'Manager', 'Responsable Technique', 'Gestionnaire', 'Technicien'];
const LAST_SEEN_KEY = 'demandes_last_seen';
const LAST_SEEN_PIECES_KEY = 'pieces_notif_last_seen';
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Sidebar() {
  const pathname = usePathname();
  const { user, hasPermission } = useAuth();
  const [newDemandesCount, setNewDemandesCount] = useState(0);
  const [piecesNotifCount, setPiecesNotifCount] = useState(0);

  const canSeeNotif = !!(user && NOTIF_ROLES.includes(user.role));
  const canSeePiecesNotif = !!(user && PIECES_NOTIF_ROLES.includes(user.role));

  // ─── Badge demandes : compte les demandes non traitées ───
  const fetchNewCount = useCallback(async () => {
    if (!canSeeNotif) return;
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : null;
      if (!token) return;
      const res = await fetch(`${API_BASE}/api/demandes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data: any[] = await res.json();

      const PENDING = ['En attente', 'Nouvelle', ''];
      const ACTIVE  = ['En attente', 'Nouvelle', 'Assignée', 'En cours'];

      const isTechnicien = user?.role === 'Technicien';

      const count = data.filter((d: any) => {
        const s = d.statut || '';
        // Technicien : voit les demandes qui le concernent et sont actives
        if (isTechnicien) return ACTIVE.includes(s);
        // Autres (Admin, Lecteur, Gestionnaire…) : demandes en attente non résolues
        return PENDING.includes(s);
      }).length;

      setNewDemandesCount(count);
    } catch {
      // silencieux
    }
  }, [canSeeNotif, user?.role]);

  // ─── Badge pièces (rupture pour gestionnaires / dispo pour techniciens) ───
  const fetchPiecesCount = useCallback(async () => {
    if (!canSeePiecesNotif) return;
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : null;
      if (!token) return;
      const res = await fetch(`${API_BASE}/api/notifications/count`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data: { count: number } = await res.json();
      setPiecesNotifCount(data.count || 0);
    } catch {
      // silencieux
    }
  }, [canSeePiecesNotif]);

  // Poll toutes les 30 secondes
  useEffect(() => {
    fetchNewCount();
    const interval = setInterval(fetchNewCount, 30_000);
    return () => clearInterval(interval);
  }, [fetchNewCount]);

  useEffect(() => {
    fetchPiecesCount();
    const interval = setInterval(fetchPiecesCount, 30_000);
    return () => clearInterval(interval);
  }, [fetchPiecesCount]);

  // Quand on arrive sur /demandes, rafraîchir le compteur
  useEffect(() => {
    if (pathname === '/demandes') {
      setTimeout(fetchNewCount, 1000); // rafraîchir après que la page a chargé
    }
  }, [pathname, fetchNewCount]);

  // Quand on arrive sur /pieces, rafraîchir le count (les notifs sont marquées lues depuis la page)
  useEffect(() => {
    if (pathname === '/pieces') {
      // Petit délai pour laisser la page marquer les notifs comme lues
      setTimeout(fetchPiecesCount, 1500);
    }
  }, [pathname, fetchPiecesCount]);

  if (!user) return null;

  const visibleItems = NAV_ITEMS.filter(item => hasPermission(item.key));

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 bg-savia-surface border-r border-savia-border flex flex-col z-40">
      {/* Logo */}
      <div className="p-3 text-center border-b border-savia-border">
        <div className="flex items-center justify-center">
          <Image
            src="/logo-savia.png"
            alt="SAVIA"
            width={300}
            height={190}
            priority
            className="object-contain w-full"
          />
        </div>
        <div className="text-xs mt-0.5 font-semibold text-savia-text-muted">
          {user.nom} · {user.role}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
          const Icon = item.icon;
          const showBadge = item.key === 'demandes' && canSeeNotif && newDemandesCount > 0;
          const showPiecesBadge = item.key === 'pieces' && canSeePiecesNotif && piecesNotifCount > 0;
          return (
            <Link
              key={item.key}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-gradient-to-r from-savia-accent/15 to-savia-accent-blue/10 text-savia-accent font-bold'
                  : 'text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover'
              )}
            >
              <Icon className={clsx('w-4 h-4 flex-shrink-0', isActive ? 'text-savia-accent' : '')} />
              <span className="truncate flex-1">{item.label}</span>
              {showBadge && (
                <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-red-500 text-white text-xs font-bold flex items-center justify-center animate-pulse shadow-lg shadow-red-500/40">
                  {newDemandesCount > 99 ? '99+' : newDemandesCount}
                </span>
              )}
              {showPiecesBadge && (
                <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-orange-500 text-white text-xs font-bold flex items-center justify-center animate-pulse shadow-lg shadow-orange-500/40">
                  {piecesNotifCount > 99 ? '99+' : piecesNotifCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-savia-border">
        <button
          onClick={() => {
            localStorage.removeItem('savia_token');
            localStorage.removeItem('savia_user');
            window.location.href = '/login';
          }}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-savia-text-muted hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
          Déconnexion
        </button>
      </div>
    </aside>
  );
}
