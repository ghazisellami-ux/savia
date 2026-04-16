'use client';
// ==========================================
// 📌 Sidebar Navigation — Savia (avec contrôle d'accès par rôle)
// ==========================================
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/lib/auth-context';
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

export default function Sidebar() {
  const pathname = usePathname();
  const { user, hasPermission } = useAuth();

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
            width={150}
            height={95}
            priority
            className="object-contain"
          />
        </div>
        <div className={`text-xs mt-0.5 font-semibold ${ROLE_COLOR[user.role] || 'text-savia-text-muted'}`}>
          {user.nom} · {user.role}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
          const Icon = item.icon;
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
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-savia-border">
        <button
          onClick={() => { localStorage.removeItem('savia_token'); localStorage.removeItem('savia_user'); window.location.href = '/login'; }}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-savia-text-muted
                     hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
          Déconnexion
        </button>
      </div>
    </aside>
  );
}
