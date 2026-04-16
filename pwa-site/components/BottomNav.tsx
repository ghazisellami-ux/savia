'use client';
import { useRouter, usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { href: '/interventions', icon: '📋', label: 'Interventions' },
  { href: '/notifications', icon: '🔔', label: 'Alertes' },
  { href: '/nouvelle',      icon: '➕', label: 'Nouvelle' },
];

interface BottomNavProps {
  notifCount?: number;
}

export default function BottomNav({ notifCount = 0 }: BottomNavProps) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      height: 'var(--nav-h)', background: '#fff',
      borderTop: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-around',
      zIndex: 900, paddingBottom: 'env(safe-area-inset-bottom, 0)',
      boxShadow: '0 -4px 20px rgba(47,65,86,0.08)',
    }}>
      {NAV_ITEMS.map(item => {
        const active = pathname?.startsWith(item.href);
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
            <span style={{ fontSize: '1.3rem', position: 'relative' }}>
              {item.icon}
              {item.href === '/notifications' && notifCount > 0 && (
                <span style={{
                  position: 'absolute', top: '-4px', right: '-8px',
                  background: 'var(--danger)', color: '#fff',
                  fontSize: '0.55rem', fontWeight: 800,
                  minWidth: '16px', height: '16px', borderRadius: '8px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 3px',
                }}>{notifCount}</span>
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
