'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isLoggedIn } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';

export default function NotificationsPage() {
  const router = useRouter();
  const [notifs, setNotifs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    api.notifications.list().then(setNotifs).catch(() => setNotifs([])).finally(() => setLoading(false));
  }, []);

  const markRead = async (id: number) => {
    await api.notifications.markRead(id).catch(() => {});
    setNotifs(n => n.map(x => x.id === id ? { ...x, lue: true } : x));
  };

  const unread = notifs.filter(n => !n.lue).length;

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)' }}>
      <Header notifCount={unread} />
      <main style={{ padding: 'calc(var(--header-h) + 16px) 16px calc(var(--nav-h) + 24px)' }}>
        <h1 style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--navy)', marginBottom: '16px' }}>🔔 Notifications</h1>

        {loading && <div style={{ textAlign: 'center', paddingTop: '48px', fontSize: '2rem' }} className="animate-pulse-dot">⏳</div>}

        {!loading && notifs.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-dim)' }}>
            <div style={{ fontSize: '3rem', marginBottom: '12px' }}>🔕</div>
            <p>Aucune notification</p>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {notifs.map(n => (
            <div key={n.id} className="animate-fade-up"
              style={{
                background: '#fff', border: '1px solid var(--border)',
                borderLeft: n.lue ? '4px solid var(--border)' : '4px solid var(--teal)',
                borderRadius: 'var(--radius)', padding: '14px 16px',
                opacity: n.lue ? 0.65 : 1,
              }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <p style={{ fontWeight: n.lue ? 400 : 700, color: 'var(--navy)', fontSize: '0.9rem', marginBottom: '4px' }}>
                    {n.message || n.titre || n.contenu}
                  </p>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                    {n.date_envoi ? new Date(n.date_envoi).toLocaleString('fr-FR') : ''}
                  </p>
                </div>
                {!n.lue && (
                  <button onClick={() => markRead(n.id)}
                    style={{ marginLeft: '12px', background: 'rgba(86,124,141,0.12)', color: 'var(--teal)', border: 'none', padding: '4px 12px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                    ✓ Lu
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </main>
      <BottomNav notifCount={unread} />
    </div>
  );
}
