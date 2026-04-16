'use client';
import { useState, useEffect, useMemo } from 'react';
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

type PiecesQty = Record<number, number>;

export default function InterventionDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = Number(params?.id);

  const [intervention, setIntervention] = useState<any>(null);
  const [allPieces, setAllPieces]       = useState<any[]>([]);
  const [equipement, setEquipement]     = useState<any>(null);
  const [loading, setLoading]           = useState(true);
  const [saving, setSaving]             = useState(false);
  const [error, setError]               = useState('');
  const [success, setSuccess]           = useState('');
  const [photoFile, setPhotoFile]       = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState('');
  const [piecesQty, setPiecesQty]       = useState<PiecesQty>({});

  const [form, setForm] = useState({
    statut: '', probleme: '', cause: '', solution: '',
    description: '', notes: '', type_erreur: '', priorite: '',
    duree_minutes: 0,
  });

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    loadAll();
  }, [id]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [all, pieces, equips] = await Promise.all([
        api.interventions.list(),
        api.pieces.list(),
        api.equipements.list(),
      ]);

      const found = (all as any[]).find(i => Number(i.id) === id);
      if (!found) { setError('Intervention introuvable.'); setLoading(false); return; }

      setIntervention(found);
      setAllPieces(pieces as any[]);
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

      // Trouver l'équipement correspondant à la machine de l'intervention
      const machineName = (found.machine || '').toLowerCase();
      const eq = (equips as any[]).find(e =>
        (e.nom || '').toLowerCase() === machineName ||
        machineName.includes((e.nom || '').toLowerCase())
      );
      setEquipement(eq || null);

    } catch {
      setError('Erreur lors du chargement.');
    } finally {
      setLoading(false);
    }
  };

  // Filtrer les pièces par type d'équipement (correspondance partielle insensible à la casse)
  const filteredPieces = useMemo(() => {
    if (allPieces.length === 0) return [];
    if (!equipement) return allPieces;
    const eqType = (equipement.type || '').toLowerCase().trim();
    if (!eqType) return allPieces;
    return allPieces.filter(p => {
      const pt = (p.equipement_type || '').toLowerCase().trim();
      return pt === eqType || pt.includes(eqType) || eqType.includes(pt);
    });
  }, [allPieces, equipement]);

  const handleQty = (pieceId: number, qty: number) => {
    setPiecesQty(prev => {
      if (qty <= 0) { const next = { ...prev }; delete next[pieceId]; return next; }
      return { ...prev, [pieceId]: qty };
    });
  };

  const selectedCount = Object.keys(piecesQty).length;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSuccess(''); setSaving(true);
    try {
      const pieces_a_deduire = Object.entries(piecesQty).map(([pieceId, qty]) => {
        const p = allPieces.find(x => x.id === Number(pieceId));
        return { id: Number(pieceId), reference: p?.reference || '', quantite: qty };
      });
      await api.interventions.update(id, { ...form, pieces_a_deduire });
      if (photoFile) await api.interventions.uploadPhoto(id, photoFile).catch(() => {});
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

        {/* Header carte */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: 'var(--teal)', fontSize: '1.1rem', cursor: 'pointer', padding: '4px' }}>←</button>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--navy)', margin: 0 }}>
              {intervention?.machine} — {intervention?.client}
            </h1>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              #{id} · {intervention?.date ? new Date(intervention.date).toLocaleDateString('fr-FR') : ''}
              {equipement?.type && <> · <strong>{equipement.type}</strong></>}
            </p>
          </div>
          <span style={{ ...statutStyle, fontSize: '0.7rem', fontWeight: 700, padding: '4px 12px', borderRadius: '20px', textTransform: 'uppercase' }}>
            {form.statut}
          </span>
        </div>

        {success && (
          <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid #22C55E', borderRadius: '10px', padding: '14px', textAlign: 'center', color: '#15803D', fontWeight: 700, marginBottom: '16px' }}>
            {success}
          </div>
        )}

        <form onSubmit={handleSave}>
          {/* Sélecteur statut */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>⚙️ Statut</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
              {['En cours', 'En attente de piece', 'Cloturee'].map(s => {
                const st = STATUT_STYLES[s] || { bg: 'rgba(47,65,86,0.08)', color: 'var(--navy)' };
                return (
                  <button key={s} type="button" onClick={() => set('statut', s)}
                    style={{
                      padding: '10px 4px', border: `2px solid ${form.statut === s ? st.color : 'var(--border)'}`,
                      borderRadius: '10px', background: form.statut === s ? st.bg : '#fff',
                      color: form.statut === s ? st.color : 'var(--text-muted)',
                      fontWeight: form.statut === s ? 800 : 500, fontSize: '0.72rem',
                      cursor: 'pointer', transition: 'all 0.2s', textAlign: 'center',
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
              { key: 'probleme', label: 'Problème constaté', ph: 'Symptômes observés...' },
              { key: 'cause',    label: 'Cause racine',      ph: 'Analyse de la cause...' },
              { key: 'solution', label: 'Solution appliquée',ph: 'Actions correctives...' },
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
                <label style={LABEL}>⏱ Durée (heures)</label>
                <input
                  type="number" style={INPUT} min={0} step={0.5}
                  value={form.duree_minutes > 0 ? +(form.duree_minutes / 60).toFixed(2) : 0}
                  onChange={e => set('duree_minutes', Math.round((parseFloat(e.target.value) || 0) * 60))}
                />
              </div>
            </div>
          </div>

          {/* 🔩 Pièces de rechange — masqué si aucune pièce pour ce type */}
          {filteredPieces.length > 0 && (
          <div style={SECTION}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                🔩 Pièces de rechange
              </h3>
              {selectedCount > 0 && (
                <span style={{ background: 'var(--teal)', color: '#fff', fontSize: '0.68rem', fontWeight: 700, padding: '3px 10px', borderRadius: '10px' }}>
                  {selectedCount} sélectionnée{selectedCount > 1 ? 's' : ''}
                </span>
              )}
            </div>

            {equipement?.type && (
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '10px', background: 'rgba(86,124,141,0.07)', padding: '6px 10px', borderRadius: '8px' }}>
                🏷 Filtre : <strong>{equipement.type}</strong> · {filteredPieces.length} pièce{filteredPieces.length > 1 ? 's' : ''}
              </p>
            )}

            {/* Liste avec défilement — 3 pièces visibles (~72px chacune) */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '244px', overflowY: 'auto', paddingRight: '2px' }}>
              {filteredPieces.map((p: any) => {
                const qty = piecesQty[p.id] || 0;
                const enStock = Number(p.stock_actuel ?? p.stock ?? 0);
                const rupture = enStock === 0;
                return (
                  <div key={p.id} style={{
                    background: qty > 0 ? 'rgba(86,124,141,0.06)' : '#fafafa',
                    border: `1px solid ${qty > 0 ? 'var(--teal)' : 'var(--border)'}`,
                    borderRadius: '10px', padding: '10px 12px',
                    display: 'flex', alignItems: 'center', gap: '10px',
                    opacity: rupture && qty === 0 ? 0.55 : 1,
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--navy)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {p.designation || p.nom}
                      </p>
                      <div style={{ display: 'flex', gap: '6px', marginTop: '3px', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>🏷 {p.reference}</span>
                        <span style={{
                          fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                          background: rupture ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                          color: rupture ? 'var(--danger)' : '#15803D',
                        }}>
                          {rupture ? '⚠ Rupture' : `✅ ${enStock} en stock`}
                        </span>
                      </div>
                    </div>

                    {/* Compteur +/- */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                      <button type="button" onClick={() => handleQty(p.id, qty - 1)} disabled={qty === 0}
                        style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: qty === 0 ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: qty === 0 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        −
                      </button>
                      <span style={{ minWidth: '26px', textAlign: 'center', fontWeight: 800, color: qty > 0 ? 'var(--teal)' : 'var(--text-dim)', fontSize: '1.05rem' }}>
                        {qty}
                      </span>
                      <button type="button" onClick={() => handleQty(p.id, qty + 1)}
                        style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: rupture ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: rupture ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        +
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          )}

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
                <img src={photoPreview} alt="Aperçu" style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: '10px', border: '2px solid var(--teal)', objectFit: 'contain', marginTop: '10px' }} />
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
            {saving ? '⏳ Enregistrement...' : `💾 Mettre à jour${selectedCount > 0 ? ` · ${selectedCount} pièce${selectedCount > 1 ? 's' : ''}` : ''}`}
          </button>
        </form>
      </main>
      <BottomNav />
    </div>
  );
}
