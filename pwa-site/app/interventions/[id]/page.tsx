'use client';
import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { isLoggedIn } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';

const INPUT = {
  width: '100%', background: '#fff', border: '1px solid var(--border)',
  borderRadius: '10px', color: 'var(--text)', padding: '12px 14px',
  fontSize: '1rem', outline: 'none', fontFamily: 'inherit',
} as const;

const LABEL = {
  display: 'block', fontSize: '0.75rem', fontWeight: 700,
  color: 'var(--text-muted)', textTransform: 'uppercase' as const,
  letterSpacing: '0.5px', marginBottom: '6px',
};

const SECTION = {
  background: '#fff', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
  padding: '16px', marginBottom: '16px',
} as const;

const STATUT_STYLES: Record<string, { bg: string; color: string }> = {
  'En cours':            { bg: 'rgba(86,124,141,0.12)',  color: 'var(--teal)'  },
  'En attente de piece': { bg: 'rgba(245,158,11,0.12)',  color: '#B45309'      },
  'Cloturee':            { bg: 'rgba(34,197,94,0.12)',   color: '#15803D'      },
  'Assignée':            { bg: 'rgba(168,85,247,0.12)',  color: '#7C3AED'      },
};

export default function InterventionDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = Number(params?.id);

  const [intervention, setIntervention] = useState<any>(null);
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState('');
  const [success, setSuccess]   = useState('');
  const [photoFile, setPhotoFile]   = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState('');

  const [form, setForm] = useState({
    statut: '', probleme: '', cause: '', solution: '',
    description: '', notes: '', type_erreur: '', priorite: '',
    duree_minutes: 0,
  });

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    loadIntervention();
  }, [id]);

  const loadIntervention = async () => {
    setLoading(true);
    try {
      // Charger depuis la liste car pas de GET /id
      const all = await api.interventions.list();
      const found = (all as any[]).find(i => Number(i.id) === id);
      if (!found) { setError('Intervention introuvable.'); setLoading(false); return; }
      setIntervention(found);
      setForm({
        statut:        found.statut || 'En cours',
        probleme:      found.probleme || '',
        cause:         found.cause || '',
        solution:      found.solution || '',
        description:   found.description || '',
        notes:         found.notes || '',
        type_erreur:   found.type_erreur || '',
        priorite:      found.priorite || '',
        duree_minutes: found.duree_minutes || 0,
      });
    } catch {
      setError('Erreur lors du chargement.');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSuccess(''); setSaving(true);
    try {
      await api.interventions.update(id, form);
      if (photoFile) {
        await api.interventions.uploadPhoto(id, photoFile).catch(() => {});
      }
      setSuccess('✅ Intervention mise à jour !');
      setTimeout(() => router.replace('/interventions'), 1500);
    } catch {
      setError('Erreur lors de la mise à jour.');
    } finally {
      setSaving(false);
    }
  };

  const set = (k: keyof typeof form, v: any) => setForm(f => ({ ...f, [k]: v }));

  const statutStyle = STATUT_STYLES[form.statut] || { bg: 'rgba(47,65,86,0.08)', color: 'var(--navy)' };
  const isClotured = form.statut === 'Cloturee';

  if (loading) return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center' }}>
        <div className="animate-pulse-dot" style={{ fontSize: '3rem' }}>⏳</div>
        <p style={{ color: 'var(--text-muted)', marginTop: '12px' }}>Chargement...</p>
      </div>
    </div>
  );

  if (error && !intervention) return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', padding: '32px' }}>
        <div style={{ fontSize: '3rem', marginBottom: '12px' }}>❌</div>
        <p style={{ color: 'var(--danger)' }}>{error}</p>
        <button onClick={() => router.back()} style={{ marginTop: '16px', background: 'var(--teal)', color: '#fff', border: 'none', padding: '10px 20px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700 }}>← Retour</button>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)' }}>
      <Header />
      <main style={{ padding: 'calc(var(--header-h) + 16px) 16px calc(var(--nav-h) + 24px)' }}>

        {/* Titre + statut badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: 'var(--teal)', fontSize: '1.1rem', cursor: 'pointer', padding: '4px' }}>←</button>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--navy)', margin: 0 }}>
              {intervention?.machine} — {intervention?.client}
            </h1>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              #{id} · {intervention?.date ? new Date(intervention.date).toLocaleDateString('fr-FR') : ''}
            </p>
          </div>
          <span style={{ ...statutStyle, fontSize: '0.7rem', fontWeight: 700, padding: '4px 12px', borderRadius: '20px', textTransform: 'uppercase' }}>
            {form.statut}
          </span>
        </div>

        {success && (
          <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid var(--success)', borderRadius: '10px', padding: '14px', textAlign: 'center', color: '#15803D', fontWeight: 700, marginBottom: '16px' }}>
            {success}
          </div>
        )}

        <form onSubmit={handleSave}>
          {/* Statut */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>⚙️ Statut</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              {['En cours', 'En attente de piece', 'Cloturee'].map(s => {
                const st = STATUT_STYLES[s] || { bg: 'rgba(47,65,86,0.08)', color: 'var(--navy)' };
                return (
                  <button key={s} type="button" onClick={() => set('statut', s)}
                    style={{
                      padding: '10px', border: `2px solid ${form.statut === s ? st.color : 'var(--border)'}`,
                      borderRadius: '10px', background: form.statut === s ? st.bg : '#fff',
                      color: form.statut === s ? st.color : 'var(--text-muted)',
                      fontWeight: form.statut === s ? 800 : 500, fontSize: '0.8rem',
                      cursor: 'pointer', transition: 'all 0.2s',
                    }}>
                    {s}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Diagnostic */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>🔍 Diagnostic</h3>
            {[
              { key: 'probleme', label: 'Problème constaté',   ph: 'Symptômes observés...' },
              { key: 'cause',    label: 'Cause racine',        ph: 'Analyse de la cause...' },
              { key: 'solution', label: 'Solution appliquée',  ph: 'Actions correctives...' },
            ].map(({ key, label, ph }) => (
              <div key={key} style={{ marginBottom: '12px' }}>
                <label style={LABEL}>{label}</label>
                <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2} placeholder={ph}
                  value={(form as any)[key]} onChange={e => set(key as any, e.target.value)} />
              </div>
            ))}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={LABEL}>Type d&apos;erreur</label>
                <select style={INPUT} value={form.type_erreur} onChange={e => set('type_erreur', e.target.value)}>
                  <option value="">— Aucun —</option>
                  {['Hardware','Software','Réseau','Calibration','Mécanique','Électrique','Autre'].map(t => <option key={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label style={LABEL}>⏱ Durée (min)</label>
                <input type="number" style={INPUT} min={0} value={form.duree_minutes} onChange={e => set('duree_minutes', parseInt(e.target.value) || 0)} />
              </div>
            </div>
          </div>

          {/* Description & Notes */}
          <div style={SECTION}>
            <div style={{ marginBottom: '12px' }}>
              <label style={LABEL}>📝 Description</label>
              <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2}
                value={form.description} onChange={e => set('description', e.target.value)} />
            </div>
            <div>
              <label style={LABEL}>📋 Notes</label>
              <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2}
                value={form.notes} onChange={e => set('notes', e.target.value)} />
            </div>
          </div>

          {/* Photo si clôture */}
          {isClotured && (
            <div style={SECTION}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>📸 Fiche Signée</h3>
              <input type="file" id="photo-input" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={e => {
                const f = e.target.files?.[0];
                if (!f) return;
                setPhotoFile(f);
                setPhotoPreview(URL.createObjectURL(f));
              }} />
              <div style={{ display: 'flex', gap: '8px' }}>
                <button type="button" onClick={() => document.getElementById('photo-input')?.click()}
                  style={{ flex: 1, background: 'var(--teal)', color: '#fff', border: 'none', padding: '12px', borderRadius: '10px', fontWeight: 700, cursor: 'pointer' }}>
                  📷 Prendre photo
                </button>
                {photoFile && (
                  <button type="button" onClick={() => { setPhotoFile(null); setPhotoPreview(''); }}
                    style={{ background: 'var(--danger)', color: '#fff', border: 'none', padding: '12px 16px', borderRadius: '10px', cursor: 'pointer' }}>🗑</button>
                )}
              </div>
              {photoPreview && (
                <div style={{ marginTop: '10px' }}>
                  <img src={photoPreview} alt="Aperçu" style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: '10px', border: '2px solid var(--teal)', objectFit: 'contain' }} />
                </div>
              )}
            </div>
          )}

          {/* Priorité */}
          <div style={SECTION}>
            <label style={LABEL}>🚨 Priorité</label>
            <select style={INPUT} value={form.priorite} onChange={e => set('priorite', e.target.value)}>
              <option value="">— Aucune —</option>
              <option>Haute</option>
              <option>Moyenne</option>
              <option>Basse</option>
            </select>
          </div>

          {error && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px' }}>{error}</p>}

          <button type="submit" disabled={saving}
            style={{ width: '100%', padding: '16px', background: 'linear-gradient(135deg, var(--teal), var(--navy))', color: '#fff', border: 'none', borderRadius: '12px', fontSize: '1rem', fontWeight: 800, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            {saving ? '⏳ Enregistrement...' : '💾 Mettre à jour'}
          </button>
        </form>
      </main>
      <BottomNav />
    </div>
  );
}
