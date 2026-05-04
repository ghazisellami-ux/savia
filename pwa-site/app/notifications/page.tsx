'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isLoggedIn } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';
import { Bell, BellOff, Loader2, Check } from 'lucide-react';

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
        <h1 style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--navy)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}><Bell style={{ width: 22, height: 22 }} /> Notifications</h1>

        {loading && <div style={{ display: 'flex', justifyContent: 'center', paddingTop: '48px' }}><Loader2 style={{ width: 32, height: 32, color: 'var(--teal)', animation: 'spin 1s linear infinite' }} /></div>}

        {!loading && notifs.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-dim)' }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '12px' }}><BellOff style={{ width: 48, height: 48, color: 'var(--text-dim)' }} /></div>
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
                    style={{ marginLeft: '12px', background: 'rgba(86,124,141,0.12)', color: 'var(--teal)', border: 'none', padding: '4px 12px', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Check style={{ width: 12, height: 12 }} /> Lu
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
