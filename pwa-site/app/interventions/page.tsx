'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { getUser, isLoggedIn } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';
import InterventionCard from '@/components/InterventionCard';
import { ClipboardList, Loader2, Inbox } from 'lucide-react';

const STATUTS = ['', 'En cours', 'En attente de piece', 'Cloturee'];

export default function InterventionsPage() {
  const router = useRouter();
  const user = getUser();
  const [data, setData]         = useState<any[]>([]);
  const [filtered, setFiltered] = useState<any[]>([]);
  const [statut, setStatut]     = useState('En cours'); // Par défaut: En cours
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true); setError('');
    try {
      // Passer le nom du technicien en query param pour filtre côté serveur
      const techName = user?.nom || user?.username || '';
      const res = await api.interventions.list({ technicien: techName });

      // Trier par date décroissante (plus récentes en premier)
      const sorted = (res as any[]).sort((a, b) => {
        const da = new Date(a.date || a.date_intervention || a.created_at || 0).getTime();
        const db = new Date(b.date || b.date_intervention || b.created_at || 0).getTime();
        return db - da;
      });

      setData(sorted);
      // Appliquer le filtre par défaut "En cours"
      setFiltered(sorted.filter(i =>
        (i.statut || '').toLowerCase().includes('cours')
      ));
    } catch {
      setError('Impossible de charger les interventions.');
    } finally {
      setLoading(false);
    }
  };

  const applyFilter = (s: string) => {
    setStatut(s);
    if (!s) {
      setFiltered(data);
    } else {
      setFiltered(data.filter(i => i.statut === s));
    }
  };

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)' }}>
      <Header />

      <main style={{ paddingTop: 'calc(var(--header-h) + 16px)', paddingBottom: 'calc(var(--nav-h) + 24px)', padding: 'calc(var(--header-h) + 16px) 16px calc(var(--nav-h) + 24px)' }}>
        {/* Page title */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h1 style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--navy)', display: 'flex', alignItems: 'center', gap: '8px' }}><ClipboardList style={{ width: 22, height: 22 }} /> Mes Interventions</h1>
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
            <Loader2 style={{ width: 32, height: 32, color: 'var(--teal)', animation: 'spin 1s linear infinite' }} />
          </div>
        )}
        {error && <p style={{ color: 'var(--danger)', textAlign: 'center', padding: '32px' }}>{error}</p>}
        {!loading && !error && filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--text-dim)' }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '12px' }}><Inbox style={{ width: 48, height: 48, color: 'var(--text-dim)' }} /></div>
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
              date={i.date || i.date_intervention || i.created_at || ''}
              technicien={i.technicien || i.technicien_assigne || ''}
              priorite={i.priorite || ''}
            />
          ))}
        </div>
      </main>

      <BottomNav />
    </div>
  );
}
