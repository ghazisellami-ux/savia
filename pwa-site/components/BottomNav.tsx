'use client';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { ClipboardList, Bell, PlusCircle } from 'lucide-react';
import { canCreateIntervention } from '@/lib/auth';
import { api } from '@/lib/api';

const NAV_ITEMS = [
  { href: '/interventions', icon: ClipboardList, label: 'Interventions' },
  { href: '/notifications', icon: Bell,          label: 'Alertes' },
  { href: '/nouvelle',      icon: PlusCircle,    label: 'Nouvelle' },
];

interface BottomNavProps {
  notifCount?: number;
}

function subscribeToSession(callback: () => void) {
  window.addEventListener('savia_site_session_changed', callback);
  window.addEventListener('storage', callback);
  return () => {
    window.removeEventListener('savia_site_session_changed', callback);
    window.removeEventListener('storage', callback);
  };
}

export default function BottomNav({ notifCount }: BottomNavProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [remoteNotifCount, setRemoteNotifCount] = useState(0);
  const canCreate = useSyncExternalStore(
    subscribeToSession,
    () => canCreateIntervention(),
    () => false,
  );

  useEffect(() => {
    if (notifCount !== undefined) return;

    let active = true;
    const refreshCount = () => {
      api.notifications.count()
        .then(({ count }) => {
          if (active) setRemoteNotifCount(Math.max(0, Number(count) || 0));
        })
        .catch(() => undefined);
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') refreshCount();
    };

    refreshCount();
    const interval = window.setInterval(refreshCount, 15_000);
    window.addEventListener('focus', refreshCount);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshCount);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [notifCount]);

  const displayedNotifCount = notifCount ?? remoteNotifCount;

  const visibleItems = canCreate
    ? NAV_ITEMS
    : NAV_ITEMS.filter(item => item.href !== '/nouvelle');

  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      height: 'var(--nav-h)', background: '#fff',
      borderTop: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-around',
      zIndex: 900, paddingBottom: 'env(safe-area-inset-bottom, 0)',
      boxShadow: '0 -4px 20px rgba(47,65,86,0.08)',
    }}>
      {visibleItems.map(item => {
        const active = pathname?.startsWith(item.href);
        const IconComp = item.icon;
        return (
          <button
            key={item.href}
            onClick={() => router.push(item.href)}
            style={{
              background: 'none', border: 'none', display: 'flex', flexDirection: 'column',
              alignItems: 'center', gap: '2px', cursor: 'pointer', padding: '8px 16px',
              borderRadius: '10px', color: active ? 'var(--teal)' : 'var(--text-dim)',
              position: 'relative', transition: 'color 0.2s',
            }}
          >
            <span style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <IconComp style={{ width: 22, height: 22 }} />
              {item.href === '/notifications' && displayedNotifCount > 0 && (
                <span className="animate-pulse-dot" style={{
                  position: 'absolute', top: '-4px', right: '-8px',
                  background: 'var(--danger)', color: '#fff',
                  fontSize: '0.55rem', fontWeight: 800,
                  minWidth: '16px', height: '16px', borderRadius: '8px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 3px',
                }}>{displayedNotifCount > 99 ? '99+' : displayedNotifCount}</span>
              )}
            </span>
            <span style={{ fontSize: '0.62rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.3px' }}>
              {item.label}
            </span>
            {active && (
              <span style={{ position: 'absolute', bottom: 0, left: '50%', transform: 'translateX(-50%)', width: '20px', height: '3px', background: 'var(--teal)', borderRadius: '3px' }} />
            )}
          </button>
        );
      })}
    </nav>
  );
}
