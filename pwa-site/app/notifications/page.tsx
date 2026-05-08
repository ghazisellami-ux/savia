'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isLoggedIn } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';
import { Bell, BellOff, Loader2, Check, Package, AlertTriangle, Wrench, User, Building2, Hash } from 'lucide-react';

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
    setNotifs(n => n.map(x => x.id === id ? { ...x, statut: 'lu' } : x));
  };

  const isRead = (n: any) => n.statut === 'lu' || n.statut === 'traite';
  const unread = notifs.filter(n => !isRead(n)).length;

  const isRupture = (n: any) => n.type === 'piece_rupture';
  const isDispo = (n: any) => n.type === 'piece_dispo';

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

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {notifs.map(n => {
            const rupture = isRupture(n);
            const dispo = isDispo(n);
            const accentColor = rupture ? '#e67e22' : dispo ? '#27ae60' : 'var(--teal)';
            const bgColor = rupture ? 'rgba(230,126,34,0.06)' : dispo ? 'rgba(39,174,96,0.06)' : '#fff';

            return (
              <div key={n.id} className="animate-fade-up"
                style={{
                  background: isRead(n) ? '#fff' : bgColor,
                  border: '1px solid var(--border)',
                  borderLeft: `4px solid ${isRead(n) ? 'var(--border)' : accentColor}`,
                  borderRadius: 'var(--radius)', padding: '14px 16px',
                  opacity: isRead(n) ? 0.6 : 1,
                }}>

                {/* Header: badge type + date */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: '4px',
                    fontSize: '0.7rem', fontWeight: 700, padding: '2px 8px', borderRadius: '12px',
                    background: rupture ? 'rgba(230,126,34,0.15)' : 'rgba(39,174,96,0.15)',
                    color: accentColor,
                  }}>
                    {rupture ? <><AlertTriangle style={{ width: 11, height: 11 }} /> Rupture de stock</> : <><Package style={{ width: 11, height: 11 }} /> Pièce disponible</>}
                  </span>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                    {n.date_creation ? new Date(n.date_creation).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </div>

                {/* Piece info */}
                {(n.piece_nom || n.piece_reference) && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                    <Package style={{ width: 14, height: 14, color: accentColor, flexShrink: 0 }} />
                    <span style={{ fontWeight: 700, color: 'var(--navy)', fontSize: '0.9rem' }}>{n.piece_nom || n.piece_reference}</span>
                    {n.piece_reference && n.piece_nom && (
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', fontFamily: 'monospace', background: 'rgba(0,0,0,0.04)', padding: '1px 6px', borderRadius: '4px' }}>{n.piece_reference}</span>
                    )}
                  </div>
                )}

                {/* Detail grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', fontSize: '0.78rem', color: 'var(--navy)' }}>
                  {n.intervention_id && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Hash style={{ width: 12, height: 12, color: 'var(--teal)' }} />
                      <span style={{ color: 'var(--text-dim)' }}>Intervention</span>
                      <span style={{ fontWeight: 600 }}>#{n.intervention_id}</span>
                    </div>
                  )}
                  {n.equipement && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Wrench style={{ width: 12, height: 12, color: 'var(--teal)' }} />
                      <span style={{ color: 'var(--text-dim)' }}>Équip.</span>
                      <span style={{ fontWeight: 600 }}>{n.equipement}</span>
                    </div>
                  )}
                  {n.client && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Building2 style={{ width: 12, height: 12, color: 'var(--teal)' }} />
                      <span style={{ color: 'var(--text-dim)' }}>Client</span>
                      <span style={{ fontWeight: 600 }}>{n.client}</span>
                    </div>
                  )}
                  {n.technicien && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <User style={{ width: 12, height: 12, color: 'var(--teal)' }} />
                      <span style={{ color: 'var(--text-dim)' }}>Tech.</span>
                      <span style={{ fontWeight: 600 }}>{n.technicien}</span>
                    </div>
                  )}
                </div>

                {/* Message (optional fallback) */}
                {n.message && !(n.piece_nom || n.piece_reference) && (
                  <p style={{ fontWeight: isRead(n) ? 400 : 600, color: 'var(--navy)', fontSize: '0.85rem', marginTop: '6px' }}>
                    {n.message}
                  </p>
                )}

                {/* Mark as read button */}
                {!isRead(n) && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
                    <button onClick={() => markRead(n.id)}
                      style={{ background: `${accentColor}15`, color: accentColor, border: `1px solid ${accentColor}30`, padding: '4px 14px', borderRadius: '8px', fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Check style={{ width: 12, height: 12 }} /> Marquer comme lu
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </main>
      <BottomNav notifCount={unread} />
    </div>
  );
}
