'use client';
// ==========================================
// 📌 Sidebar Navigation — Savia (avec contrôle d'accès par rôle + collapse)
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
  ChevronLeft, ChevronRight, DollarSign, MapPin, ShieldCheck,
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
  { key: 'contrats',           label: 'Contrats',               href: '/contrats',    icon: ClipboardCheck },
  { key: 'finances',           label: 'Finances',               href: '/finances',    icon: DollarSign     },
  { key: 'carte',              label: 'Carte Géographique',     href: '/carte',       icon: MapPin         },
  { key: 'sla',                label: 'Suivi SLA',              href: '/sla',         icon: ShieldCheck    },
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
const SIDEBAR_COLLAPSED_KEY = 'savia_sidebar_collapsed';

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
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
      const res = await fetch(`/api/demandes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data: any[] = await res.json();

      const PENDING = ['En attente', 'Nouvelle', ''];
      const ACTIVE  = ['En attente', 'Nouvelle', 'Assignée', 'En cours'];

      const isTechnicien = user?.role === 'Technicien';

      const count = data.filter((d: any) => {
        const s = d.statut || '';
        if (isTechnicien) return ACTIVE.includes(s);
        return PENDING.includes(s);
      }).length;

      setNewDemandesCount(count);
    } catch {
      // silencieux
    }
  }, [canSeeNotif, user?.role]);

  // ─── Badge pièces ───
  const fetchPiecesCount = useCallback(async () => {
    if (!canSeePiecesNotif) return;
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : null;
      if (!token) return;
      const res = await fetch(`/api/notifications/count`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data: { count: number } = await res.json();
      setPiecesNotifCount(data.count || 0);
    } catch {
      // silencieux
    }
  }, [canSeePiecesNotif]);

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

  useEffect(() => {
    if (pathname === '/demandes') setTimeout(fetchNewCount, 1000);
  }, [pathname, fetchNewCount]);

  useEffect(() => {
    if (pathname === '/pieces') setTimeout(fetchPiecesCount, 1500);
  }, [pathname, fetchPiecesCount]);

  if (!user) return null;

  const visibleItems = NAV_ITEMS.filter(item => hasPermission(item.key));

  return (
    <aside
      className={clsx(
        'fixed left-0 top-0 bottom-0 bg-savia-surface border-r border-savia-border flex flex-col z-40',
        'transition-all duration-300 ease-in-out',
        isCollapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo + toggle */}
      <div className={clsx(
        'border-b border-savia-border flex items-center',
        isCollapsed ? 'p-4 justify-center' : 'p-6'
      )}>
        {!isCollapsed && (
          <div className="flex-1 flex flex-col items-center">
            <Image
              src="/logo-savia.png"
              alt="SAVIA"
              width={98}
              height={32}
              priority
              unoptimized
              className="object-contain"
            />
            <div className="text-xs mt-5 font-semibold text-savia-text-muted">
              {user.nom} · <span className={ROLE_COLOR[user.role] || 'text-savia-text-muted'}>{user.role}</span>
            </div>
          </div>
        )}

        {/* Bouton collapse */}
        <button
          onClick={onToggle}
          title={isCollapsed ? 'Ouvrir le menu' : 'Réduire le menu'}
          className={clsx(
            'flex items-center justify-center w-7 h-7 rounded-lg',
            'bg-savia-surface-hover hover:bg-savia-accent/20 hover:text-savia-accent',
            'text-savia-text-muted transition-all duration-200 border border-savia-border',
            isCollapsed ? '' : 'ml-2 flex-shrink-0'
          )}
        >
          {isCollapsed
            ? <ChevronRight className="w-4 h-4" />
            : <ChevronLeft className="w-4 h-4" />
          }
        </button>
      </div>

      {/* Navigation */}
      <nav className={clsx(
        'flex-1 overflow-y-auto py-2 space-y-0.5',
        isCollapsed ? 'px-1' : 'px-2'
      )}>
        {visibleItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
          const Icon = item.icon;
          const showBadge = item.key === 'demandes' && canSeeNotif && newDemandesCount > 0;
          const showPiecesBadge = item.key === 'pieces' && canSeePiecesNotif && piecesNotifCount > 0;
          const badgeCount = showBadge ? newDemandesCount : showPiecesBadge ? piecesNotifCount : 0;
          const hasBadge = showBadge || showPiecesBadge;
          const badgeColor = showBadge ? 'bg-red-500 shadow-red-500/40' : 'bg-orange-500 shadow-orange-500/40';

          return (
            <Link
              key={item.key}
              href={item.href}
              title={isCollapsed ? item.label : undefined}
              className={clsx(
                'relative flex items-center rounded-lg text-sm font-medium transition-all duration-200',
                isCollapsed ? 'justify-center px-2 py-2.5' : 'gap-3 px-3 py-2.5',
                isActive
                  ? 'bg-gradient-to-r from-savia-accent/15 to-savia-accent-blue/10 text-savia-accent font-bold'
                  : 'text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover'
              )}
            >
              <Icon className={clsx('w-4 h-4 flex-shrink-0', isActive ? 'text-savia-accent' : '')} />

              {/* Label (masqué si collapsed) */}
              {!isCollapsed && (
                <span className="truncate flex-1">{item.label}</span>
              )}

              {/* Badge en mode étendu */}
              {!isCollapsed && hasBadge && (
                <span className={clsx(
                  'min-w-[20px] h-5 px-1.5 rounded-full text-white text-xs font-bold flex items-center justify-center animate-pulse shadow-lg',
                  badgeColor
                )}>
                  {badgeCount > 99 ? '99+' : badgeCount}
                </span>
              )}

              {/* Petit point rouge en mode collapsed */}
              {isCollapsed && hasBadge && (
                <span className={clsx(
                  'absolute top-1 right-1 w-2.5 h-2.5 rounded-full border border-savia-surface animate-pulse',
                  showBadge ? 'bg-red-500' : 'bg-orange-500'
                )} />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className={clsx('border-t border-savia-border', isCollapsed ? 'p-2' : 'p-3')}>
        <button
          onClick={() => {
            localStorage.removeItem('savia_token');
            localStorage.removeItem('savia_user');
            window.location.href = '/login';
          }}
          title={isCollapsed ? 'Déconnexion' : undefined}
          className={clsx(
            'w-full flex items-center rounded-lg text-sm text-savia-text-muted hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer',
            isCollapsed ? 'justify-center p-2' : 'gap-2 px-3 py-2'
          )}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!isCollapsed && 'Déconnexion'}
        </button>
      </div>
    </aside>
  );
}
