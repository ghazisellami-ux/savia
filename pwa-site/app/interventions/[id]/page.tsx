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

// Extrait les mots significatifs d'une chaîne (ignore parenthèses, tirets, etc.)
function coreWords(s: string): string[] {
  return s.toLowerCase().replace(/[()\-_/]/g, ' ').split(/\s+/).filter(w => w.length > 1);
}

// Vérifie si le type de pièce correspond à la machine de l'intervention
// Machine format: "Type Fabricant" (ex: "IRM GE", "Arceau Chirurgical Hologic")
// Piece equipement_type: "Type (détail)" (ex: "IRM", "Arceau Chirurgical (C-Arm)")
function matchesMachine(machineName: string, pieceType: string): boolean {
  if (!machineName || !pieceType) return false;
  const machineWords = coreWords(machineName);
  // Remove parenthesized parts from piece type (e.g. "(C-Arm)", "(CBCT)", "(DR)")
  const pieceClean = pieceType.replace(/\([^)]*\)/g, '').trim();
  const pieceCore = coreWords(pieceClean);
  if (pieceCore.length === 0) return false;
  const matchCount = pieceCore.filter(pw => machineWords.some(mw => mw.includes(pw) || pw.includes(mw))).length;
  return matchCount >= pieceCore.length;
}

export default function InterventionDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = Number(params?.id);

  const [intervention, setIntervention] = useState<any>(null);
  const [allPieces, setAllPieces]       = useState<any[]>([]);
  const [loading, setLoading]           = useState(true);
  const [saving, setSaving]             = useState(false);
  const [error, setError]               = useState('');
  const [success, setSuccess]           = useState('');
  const [photoFile, setPhotoFile]       = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState('');
  const [piecesQty, setPiecesQty]       = useState<PiecesQty>({});
  const [piecesRupture, setPiecesRupture] = useState<any[]>([]); // pièces demandées (rupture)
  const [searchRupture, setSearchRupture] = useState('');

  const [form, setForm] = useState({
    statut: '', probleme: '', cause: '', solution: '',
    description: '', notes: '', type_erreur: '', priorite: '',
    duree_minutes: 0, fiche_validation: 'En attente',
  });

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    loadAll();
  }, [id]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [all, pieces] = await Promise.all([
        api.interventions.list(),
        api.pieces.list(),
      ]);

      const found = (all as any[]).find(i => Number(i.id) === id);
      if (!found) { setError('Intervention introuvable.'); setLoading(false); return; }

      setIntervention(found);
      setAllPieces(pieces as any[]);
      setForm({
        statut:           found.statut || 'En cours',
        probleme:         found.probleme || '',
        cause:            found.cause || '',
        solution:         found.solution || '',
        description:      found.description || '',
        notes:            found.notes || '',
        type_erreur:      found.type_erreur || '',
        priorite:         found.priorite || '',
        duree_minutes:    found.duree_minutes || 0,
        fiche_validation: found.fiche_validation || 'En attente',
      });
    } catch {
      setError('Erreur lors du chargement.');
    } finally {
      setLoading(false);
    }
  };

  // Filtrer les pièces : l'equipement_type de la pièce doit correspondre
  // au nom de la machine de l'intervention (matching intelligent multi-mots)
  const filteredPieces = useMemo(() => {
    if (!intervention?.machine || allPieces.length === 0) return [];
    return allPieces.filter(p => matchesMachine(intervention.machine, p.equipement_type || ''));
  }, [allPieces, intervention]);

  const handleQty = (pieceId: number, qty: number) => {
    setPiecesQty(prev => {
      if (qty <= 0) { const next = { ...prev }; delete next[pieceId]; return next; }
      return { ...prev, [pieceId]: qty };
    });
  };

  const selectedCount = Object.keys(piecesQty).length;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSuccess('');

    // Validation frontend : solution obligatoire pour clôturer
    if (form.statut === 'Cloturee' && !form.solution.trim()) {
      setError('⚠️ La "Solution appliquée" est obligatoire pour clôturer l\'intervention.');
      document.getElementById('field-solution')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    setSaving(true);
    try {
      const pieces_a_deduire = Object.entries(piecesQty).map(([pieceId, qty]) => {
        const p = allPieces.find(x => x.id === Number(pieceId));
        return { id: Number(pieceId), reference: p?.reference || '', quantite: qty };
      });
      const pieces_rupture = piecesRupture.map(p => ({
        id: p.id,
        reference: p.reference || '',
        designation: p.designation || p.nom || '',
      }));
      await api.interventions.update(id, { ...form, pieces_a_deduire, pieces_rupture });
      if (photoFile) await api.interventions.uploadPhoto(id, photoFile).catch(() => {});
      setSuccess('✅ Intervention mise à jour !');
      setTimeout(() => router.replace('/interventions'), 1500);
    } catch (err: any) {
      setError(err?.message || 'Erreur lors de la mise à jour.');
    } finally {
      setSaving(false);
    }
  };

  const set = (k: keyof typeof form, v: any) => setForm(f => ({ ...f, [k]: v }));
  const statutStyle = STATUT_STYLES[form.statut] || { bg: 'rgba(47,65,86,0.08)', color: 'var(--navy)' };
  const isClotured    = form.statut === 'Cloturee';
  const isAttenteP    = form.statut === 'En attente de piece';

  const toggleRupture = (p: any) => {
    setPiecesRupture(prev =>
      prev.find(x => x.id === p.id) ? prev.filter(x => x.id !== p.id) : [...prev, p]
    );
  };

  // Pour la section "en attente de pièce", filtrer d'abord par type d'équipement puis par recherche
  const searchedPieces = useMemo(() => {
    const base = intervention?.machine
      ? allPieces.filter(p => matchesMachine(intervention.machine, p.equipement_type || ''))
      : allPieces;
    if (!searchRupture) return base;
    const q = searchRupture.toLowerCase();
    return base.filter(p =>
      (p.designation || p.nom || '').toLowerCase().includes(q)
      || (p.reference || '').toLowerCase().includes(q)
    );
  }, [allPieces, intervention, searchRupture]);

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

        {/* Header */}
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
          <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid #22C55E', borderRadius: '10px', padding: '14px', textAlign: 'center', color: '#15803D', fontWeight: 700, marginBottom: '16px' }}>
            {success}
          </div>
        )}

        <form onSubmit={handleSave}>

          {/* ① Diagnostic */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>🔍 Diagnostic</h3>
            {[
              { key: 'probleme', label: 'Problème constaté', ph: 'Symptômes observés...' },
              { key: 'cause',    label: 'Cause racine',      ph: 'Analyse de la cause...' },
              { key: 'solution', label: 'Solution appliquée', ph: 'Actions correctives...' },
            ].map(({ key, label, ph }) => (
              <div key={key} id={key === 'solution' ? 'field-solution' : undefined} style={{ marginBottom: '12px' }}>
                <label style={LABEL}>
                  {label}
                  {key === 'solution' && isClotured && (
                    <span style={{ color: '#ef4444', marginLeft: '4px' }}>*</span>
                  )}
                </label>
                <textarea
                  style={{
                    ...INPUT, resize: 'vertical',
                    borderColor: key === 'solution' && isClotured && !(form as any)[key] ? '#ef4444' : undefined,
                  }}
                  rows={2} placeholder={ph}
                  value={(form as any)[key]}
                  onChange={e => set(key as any, e.target.value)}
                />
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

          {/* ② Pièces de rechange — masqué si aucune correspondance */}
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

              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '10px', background: 'rgba(86,124,141,0.07)', padding: '6px 10px', borderRadius: '8px' }}>
                🏷 {intervention?.machine} · {filteredPieces.length} pièce{filteredPieces.length > 1 ? 's' : ''} compatible{filteredPieces.length > 1 ? 's' : ''}
              </p>

              {/* 3 pièces visibles, défilement pour le reste */}
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

          {/* ③ Description & Notes */}
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

          {/* ④ Priorité */}
          <div style={SECTION}>
            <label style={LABEL}>🚨 Priorité</label>
            <select style={INPUT} value={form.priorite} onChange={e => set('priorite', e.target.value)}>
              <option value="">— Aucune —</option>
              <option>Haute</option>
              <option>Moyenne</option>
              <option>Basse</option>
            </select>
          </div>

          {/* ⑤ Statut — EN BAS */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>⚙️ Statut de l&apos;intervention</h3>
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

          {/* □ Pièces requises — visible uniquement quand statut = En attente de piece */}
          {isAttenteP && (
            <div style={{ ...SECTION, border: '2px dashed #B45309', background: 'rgba(245,158,11,0.03)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#B45309', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                  ⚠️ Pièces requises (rupture)
                </h3>
                {piecesRupture.length > 0 && (
                  <span style={{ background: '#ef4444', color: '#fff', fontSize: '0.68rem', fontWeight: 700, padding: '3px 10px', borderRadius: '10px', animation: 'pulse 2s infinite' }}>
                    {piecesRupture.length} sélectionnée{piecesRupture.length > 1 ? 's' : ''}
                  </span>
                )}
              </div>
              <p style={{ fontSize: '0.72rem', color: '#B45309', background: 'rgba(245,158,11,0.08)', padding: '6px 10px', borderRadius: '8px', marginBottom: '10px' }}>
                Sélectionnez les pièces nécessaires — un badge rouge sera créé dans Pièces de rechange
              </p>

              {/* Recherche */}
              <input
                type="search"
                placeholder="🔍 Rechercher une pièce..."
                value={searchRupture}
                onChange={e => setSearchRupture(e.target.value)}
                style={{ ...INPUT, marginBottom: '10px' }}
              />

              {/* Liste des pièces */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '7px', maxHeight: '280px', overflowY: 'auto' }}>
                {searchedPieces.length === 0 && (
                  <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem', padding: '12px' }}>Aucune pièce trouvée</p>
                )}
                {searchedPieces.map((p: any) => {
                  const enStock = Number(p.stock_actuel ?? p.stock ?? 0);
                  const rupture = enStock === 0;
                  const selected = !!piecesRupture.find(x => x.id === p.id);
                  return (
                    <button key={p.id} type="button" onClick={() => toggleRupture(p)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '10px 12px', borderRadius: '10px', border: 'none',
                        background: selected ? (rupture ? 'rgba(239,68,68,0.08)' : 'rgba(86,124,141,0.08)') : '#fafafa',
                        outline: selected ? `2px solid ${rupture ? '#ef4444' : 'var(--teal)'}` : '2px solid transparent',
                        cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                      }}>
                      <span style={{ fontSize: '1.1rem' }}>{selected ? '✅' : (rupture ? '⚠️' : '○')}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--navy)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {p.designation || p.nom}
                        </p>
                        <div style={{ display: 'flex', gap: '6px', marginTop: '2px' }}>
                          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>🏷 {p.reference}</span>
                          <span style={{
                            fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                            background: rupture ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                            color: rupture ? '#ef4444' : '#15803D',
                          }}>
                            {rupture ? '🔴 Rupture' : `✅ ${enStock} en stock`}
                          </span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Résumé sélection */}
              {piecesRupture.length > 0 && (
                <div style={{ marginTop: '10px', padding: '8px 12px', background: 'rgba(239,68,68,0.06)', borderRadius: '8px', border: '1px solid rgba(239,68,68,0.2)' }}>
                  <p style={{ fontSize: '0.72rem', fontWeight: 700, color: '#ef4444', marginBottom: '4px' }}>📣 Pièces qui seront notifiées :</p>
                  {piecesRupture.map(p => (
                    <p key={p.id} style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: '1px 0' }}>
                      • {p.designation || p.nom} ({p.reference})
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {isClotured && (
            <div style={{ ...SECTION, border: '2px dashed var(--teal)' }}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>📸 Fiche d&apos;intervention signée</h3>

              {/* Prise de photo */}
              <input type="file" id="photo-input" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={e => {
                const f = e.target.files?.[0];
                if (!f) return;
                setPhotoFile(f);
                setPhotoPreview(URL.createObjectURL(f));
              }} />
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <button type="button" onClick={() => document.getElementById('photo-input')?.click()}
                  style={{ flex: 1, background: 'var(--teal)', color: '#fff', border: 'none', padding: '14px', borderRadius: '10px', fontWeight: 700, cursor: 'pointer', fontSize: '0.95rem' }}>
                  📷 {photoFile ? 'Changer la photo' : 'Prendre / Importer photo'}
                </button>
                {photoFile && (
                  <button type="button" onClick={() => { setPhotoFile(null); setPhotoPreview(''); }}
                    style={{ background: 'var(--danger)', color: '#fff', border: 'none', padding: '14px 16px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700 }}>🗑</button>
                )}
              </div>
              {photoPreview && (
                <img src={photoPreview} alt="Aperçu fiche" style={{ maxWidth: '100%', maxHeight: '220px', borderRadius: '10px', border: '2px solid var(--teal)', objectFit: 'contain', marginBottom: '12px', display: 'block' }} />
              )}
              {!photoFile && (
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', marginBottom: '12px' }}>
                  Joignez une photo de la fiche d&apos;intervention signée par le client
                </p>
              )}

              {/* Statut de la fiche */}
              <div style={{ marginTop: '4px' }}>
                <label style={LABEL}>Statut de la fiche signée</label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '6px' }}>
                  {[
                    { val: 'En attente', icon: '⏳', bg: 'rgba(245,158,11,0.1)', color: '#B45309' },
                    { val: 'Validée',    icon: '✅', bg: 'rgba(34,197,94,0.1)',  color: '#15803D' },
                  ].map(({ val, icon, bg, color }) => (
                    <button key={val} type="button"
                      onClick={() => set('fiche_validation', val)}
                      style={{
                        padding: '12px 8px',
                        border: `2px solid ${form.fiche_validation === val ? color : 'var(--border)'}`,
                        borderRadius: '10px',
                        background: form.fiche_validation === val ? bg : '#fff',
                        color: form.fiche_validation === val ? color : 'var(--text-muted)',
                        fontWeight: form.fiche_validation === val ? 800 : 500,
                        fontSize: '0.82rem',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        textAlign: 'center',
                      }}>
                      {icon} {val}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px' }}>{error}</p>}

          {/* ⑦ Bouton mise à jour */}
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
