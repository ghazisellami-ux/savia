'use client';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { getUser, isLoggedIn } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';
import InterventionCard from '@/components/InterventionCard';

const STATUTS = ['', 'En cours', 'En attente de piece', 'Cloturee'];

export default function InterventionsPage() {
  const router = useRouter();
  const user = getUser();
  const [data, setData] = useState<any[]>([]);
  const [filtered, setFiltered] = useState<any[]>([]);
  const [statut, setStatut] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true); setError('');
    try {
      const res = await api.interventions.list();
      // Filter only interventions assigned to this technician
      const mine = res.filter((i: any) => {
        const tech = (i.technicien_assigne || i.technicien || '').toLowerCase();
        return tech.includes((user?.nom || '').toLowerCase()) || tech.includes((user?.username || '').toLowerCase());
      });
      setData(mine);
      setFiltered(mine);
    } catch (e) {
      setError('Impossible de charger les interventions.');
    } finally {
      setLoading(false);
    }
  };

  const applyFilter = (s: string) => {
    setStatut(s);
    setFiltered(s ? data.filter(i => i.statut === s) : data);
  };

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)' }}>
      <Header />

      <main style={{ paddingTop: 'calc(var(--header-h) + 16px)', paddingBottom: 'calc(var(--nav-h) + 24px)', padding: 'calc(var(--header-h) + 16px) 16px calc(var(--nav-h) + 24px)' }}>
        {/* Page title */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h1 style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--navy)' }}>📋 Mes Interventions</h1>
          <button onClick={() => router.push('/nouvelle')}
            style={{ background: 'linear-gradient(135deg, var(--teal), var(--navy))', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: '10px', fontWeight: 700, fontSize: '0.85rem', cursor: 'pointer' }}>
            + Nouvelle
          </button>
        </div>

        {/* Filter */}
        <div style={{ marginBottom: '16px' }}>
          <select value={statut} onChange={e => applyFilter(e.target.value)}
            style={{ width: '100%', background: '#fff', border: '1px solid var(--border)', borderRadius: '10px', color: 'var(--text)', padding: '10px 14px', fontSize: '0.9rem', outline: 'none' }}>
            {STATUTS.map(s => <option key={s} value={s}>{s || 'Tous les statuts'}</option>)}
          </select>
        </div>

        {/* Content */}
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: '48px' }}>
            <div className="animate-pulse-dot" style={{ fontSize: '2rem' }}>⏳</div>
          </div>
        )}
        {error && <p style={{ color: 'var(--danger)', textAlign: 'center', padding: '32px' }}>{error}</p>}
        {!loading && !error && filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-dim)' }}>
            <div style={{ fontSize: '3rem', marginBottom: '12px' }}>📭</div>
            <p>Aucune intervention trouvée</p>
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filtered.map(i => (
            <InterventionCard
              key={i.id}
              id={i.id}
              machine={i.machine || ''}
              client={i.client || ''}
              statut={i.statut || 'En cours'}
              type={i.type_intervention || i.type || ''}
              date={i.date_intervention || i.created_at || ''}
              technicien={i.technicien_assigne || i.technicien || ''}
              priorite={i.priorite || ''}
            />
          ))}
        </div>
      </main>

      <BottomNav />
    </div>
  );
}
