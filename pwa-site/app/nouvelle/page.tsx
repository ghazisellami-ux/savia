'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { canCreateIntervention, isLoggedIn } from '@/lib/auth';
import { INTERVENTION_TYPES_BASE, mergeInterventionTypes } from '@/lib/intervention-types';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';
import TimeScrollPicker from '@/components/TimeScrollPicker';
import {
  ChevronLeft, CheckCircle, Building2, Settings, FileText, Search,
  Timer, Car, Wrench, ClipboardList, Camera, Trash2, Loader2, Save,
  Clock, Tag, AlertTriangle
} from 'lucide-react';

const ICON_INLINE = { width: '14px', height: '14px', display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' } as const;

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
  'Assignée':                 { bg: 'rgba(168,85,247,0.12)', color: '#7C3AED' },
  'En cours':                { bg: 'rgba(86,124,141,0.12)', color: 'var(--teal)' },
  "Transfert vers l'atelier": { bg: 'rgba(37,99,235,0.12)', color: '#2563EB' },
  'En attente de piece':     { bg: 'rgba(245,158,11,0.12)', color: '#B45309' },
  'Cloturee':                { bg: 'rgba(34,197,94,0.12)', color: '#15803D' },
};

type PiecesQty = Record<number, number>;

function calculateDuration(startTime: string, endTime: string): number {
  const [startH, startM] = startTime.split(':').map(Number);
  const [endH, endM] = endTime.split(':').map(Number);
  let duration = (endH * 60 + endM) - (startH * 60 + startM);
  if (duration <= 0) duration += 24 * 60;
  return Math.max(60, duration);
}

export default function NouvelleInterventionPage() {
  const router = useRouter();

  const [clients, setClients]     = useState<any[]>([]);
  const [equips, setEquips]       = useState<any[]>([]);
  const [techs, setTechs]         = useState<any[]>([]);
  const [pieces, setPieces]       = useState<any[]>([]);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');
  const [success, setSuccess]     = useState(false);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState('');
  const [interventionTypes, setInterventionTypes] = useState<string[]>([...INTERVENTION_TYPES_BASE]);
  const [customTypeMode, setCustomTypeMode] = useState(false);
  const [customTypeValue, setCustomTypeValue] = useState('');
  const [piecesQty, setPiecesQty] = useState<PiecesQty>({});

  const [form, setForm] = useState({
    client: '', machine: '', technicien_assigne: '', type_intervention: 'Corrective',
    statut: 'Assignée', description: '', probleme: '', cause: '', solution: '',
    duree_minutes: 60, deplacement: 0, code_erreur: '', type_erreur: '',
    notes: '', fiche_validation: 'En attente', start_time: '08:00', end_time: '09:00',
  });

  const filteredEquips = useMemo(() =>
    form.client ? equips.filter(e => (e.Client || e.client) === form.client) : equips,
    [equips, form.client]
  );

  const filteredPieces = useMemo(() => {
    const equipment = equips.find((item: any) => (item.Nom || item.nom) === form.machine);
    const equipmentType = String(equipment?.Type || equipment?.type || '').toLowerCase().trim();
    if (!equipmentType) return [];
    return pieces.filter((piece: any) =>
      String(piece.equipement_type || '').toLowerCase().trim() === equipmentType,
    );
  }, [equips, form.machine, pieces]);

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    if (!canCreateIntervention()) { router.replace('/interventions'); return; }
    Promise.all([
      api.clients.list().catch(() => []),
      api.equipements.list().catch(() => []),
      api.techniciens.list().catch(() => []),
      api.pieces.list().catch(() => []),
      api.typesIntervention.list().catch(() => []),
    ]).then(([c, e, t, p, types]) => {
      setClients(c as any[]);
      setEquips(e as any[]);
      setTechs(t as any[]);
      setPieces(p as any[]);
      setInterventionTypes(mergeInterventionTypes(
        INTERVENTION_TYPES_BASE,
        (types as any[]).map((type: any) => type.nom).filter(Boolean),
      ));
    });
  }, [router]);

  const handlePhoto = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPhotoFile(f);
    setPhotoPreview(URL.createObjectURL(f));
  };

  const handleQty = (pieceId: number, qty: number) => {
    setPiecesQty(current => {
      const next = { ...current };
      if (qty <= 0) delete next[pieceId];
      else next[pieceId] = qty;
      return next;
    });
  };

  const handleStartTimeChange = useCallback((time: string) => {
    setForm(current => ({
      ...current,
      start_time: time,
      duree_minutes: calculateDuration(time, current.end_time),
    }));
  }, []);

  const handleEndTimeChange = useCallback((time: string) => {
    setForm(current => ({
      ...current,
      end_time: time,
      duree_minutes: calculateDuration(current.start_time, time),
    }));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (form.statut === 'Cloturee' && !form.solution.trim()) {
      setError('La "Solution appliquée" est obligatoire pour clôturer l\'intervention.');
      document.getElementById('field-solution')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setSaving(true);
    try {
      const selectedPieces = Object.entries(piecesQty).map(([pieceId, qty]) => {
        const piece = pieces.find((item: any) => item.id === Number(pieceId));
        return {
          id: Number(pieceId),
          ref: piece?.reference || '',
          reference: piece?.reference || '',
          qty,
          quantite: qty,
          designation: piece?.designation || piece?.nom || '',
          prix_unitaire: piece?.prix_unitaire || 0,
        };
      });
      const payload = {
        ...form,
        technicien: form.technicien_assigne,
        duree_minutes: calculateDuration(form.start_time, form.end_time),
        duree_deplacement: Math.round(form.deplacement * 60),
        pieces_utilisees: selectedPieces
          .map(piece => `${piece.designation} (${piece.reference}) × ${piece.qty}`)
          .join(', '),
        pieces_a_deduire: selectedPieces,
      };
      const created = await api.interventions.create(payload);
      if (photoFile && created.id) {
        await api.interventions.uploadPhoto(created.id, photoFile).catch(() => {});
      }
      setSuccess(true);
      setTimeout(() => router.replace('/interventions'), 1500);
    } catch {
      setError('Erreur lors de l\'enregistrement.');
    } finally {
      setSaving(false);
    }
  };

  const set = (k: keyof typeof form, v: any) => setForm(f => ({ ...f, [k]: v }));

  const isClotured = form.statut === 'Cloturee';
  const selectedCount = Object.keys(piecesQty).length;

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)' }}>
      <Header />
      <main style={{ paddingTop: 'calc(var(--header-h) + 16px)', paddingBottom: 'calc(var(--nav-h) + 24px)', padding: 'calc(var(--header-h) + 16px) 16px calc(var(--nav-h) + 24px)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: 'var(--teal)', fontSize: '1.1rem', cursor: 'pointer', padding: '4px 8px', display: 'flex', alignItems: 'center' }}><ChevronLeft style={{ width: 20, height: 20 }} /> Retour</button>
          <h1 style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--navy)' }}>Nouvelle Intervention</h1>
        </div>

        {success && (
          <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid var(--success)', borderRadius: '10px', padding: '14px', textAlign: 'center', color: '#15803D', fontWeight: 700, marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
            <CheckCircle style={{ width: 18, height: 18 }} /> Intervention enregistrée !
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {/* Client & Équipement */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Building2 style={{ width: 16, height: 16 }} /> Identification</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={LABEL}>Client *</label>
                <select style={INPUT} value={form.client} onChange={e => { set('client', e.target.value); set('machine', ''); setPiecesQty({}); }} required>
                  <option value="">— Choisir —</option>
                  {clients.map((c: any) => <option key={c.id || c.nom || c.Nom} value={c.nom || c.Nom}>{c.nom || c.Nom}</option>)}
                </select>
              </div>
              <div>
                <label style={LABEL}>Équipement *</label>
                <select style={INPUT} value={form.machine} onChange={e => { set('machine', e.target.value); setPiecesQty({}); }} required>
                  <option value="">— Choisir —</option>
                  {filteredEquips.map((e: any) => <option key={e.id || e.Nom || e.nom} value={e.Nom || e.nom}>{e.Nom || e.nom}</option>)}
                </select>
              </div>
            </div>
            <div style={{ marginTop: '12px' }}>
              <div>
                <label style={LABEL}>Type d&apos;intervention</label>
                {customTypeMode ? (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <input style={INPUT} autoFocus placeholder="Saisir le type..." value={customTypeValue} onChange={e => setCustomTypeValue(e.target.value)} />
                    <button type="button" style={{ ...INPUT, width: 'auto', background: 'var(--teal)', color: '#fff', cursor: 'pointer' }} onClick={() => {
                      const value = customTypeValue.trim();
                      if (!value) return;
                      setInterventionTypes(prev => mergeInterventionTypes(prev, [value]));
                      set('type_intervention', value);
                      setCustomTypeMode(false);
                      setCustomTypeValue('');
                    }}>✓</button>
                    <button type="button" style={{ ...INPUT, width: 'auto', cursor: 'pointer' }} onClick={() => { setCustomTypeMode(false); setCustomTypeValue(''); }}>×</button>
                  </div>
                ) : (
                  <select style={INPUT} value={form.type_intervention} onChange={e => {
                    if (e.target.value === '__autre__') {
                      setCustomTypeMode(true);
                      return;
                    }
                    set('type_intervention', e.target.value);
                  }}>
                    {interventionTypes.map(type => <option key={type}>{type}</option>)}
                    <option value="__autre__">✏️ Autre (saisie manuelle)</option>
                  </select>
                )}
              </div>
              <div style={{ marginTop: '12px' }}>
                <label style={LABEL}>Technicien *</label>
                <select style={INPUT} value={form.technicien_assigne} onChange={e => set('technicien_assigne', e.target.value)} required>
                  <option value="">— Choisir —</option>
                  {techs.map((technician: any) => (
                    <option key={technician.id || technician.nom} value={technician.username || technician.nom || technician.id}>
                      {technician.nom_complet || technician.nom || technician.username}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* ① Diagnostic — même ordre que la fiche d'intervention */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Search style={{ width: 16, height: 16 }} /> Diagnostic</h3>
            {[
              { key: 'probleme', label: 'Problème constaté', ph: 'Symptômes observés...' },
              { key: 'cause', label: 'Cause racine', ph: 'Analyse de la cause...' },
              { key: 'solution', label: 'Solution appliquée', ph: 'Actions correctives...' },
            ].map(({ key, label, ph }) => (
              <div key={key} id={key === 'solution' ? 'field-solution' : undefined} style={{ marginBottom: '12px' }}>
                <label style={LABEL}>
                  {label}
                  {key === 'solution' && isClotured && <span style={{ color: '#ef4444', marginLeft: '4px' }}>*</span>}
                </label>
                <textarea
                  style={{ ...INPUT, resize: 'vertical', borderColor: key === 'solution' && isClotured && !(form as any)[key] ? '#ef4444' : undefined }}
                  rows={2}
                  placeholder={ph}
                  value={(form as any)[key]}
                  onChange={e => set(key as any, e.target.value)}
                />
              </div>
            ))}

            <div style={{ marginBottom: '12px' }}>
              <label style={LABEL}>Type d&apos;erreur</label>
              <select style={INPUT} value={form.type_erreur} onChange={e => set('type_erreur', e.target.value)}>
                <option value="">— Aucun —</option>
                {['Hardware','Software','Réseau','Calibration','Mécanique','Électrique','Autre'].map(type => <option key={type}>{type}</option>)}
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
              <TimeScrollPicker label="Heure de début" value={form.start_time} defaultValue="08:00" onChange={handleStartTimeChange} />
              <TimeScrollPicker label="Heure de fin" value={form.end_time} defaultValue="09:00" onChange={handleEndTimeChange} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 14px', marginTop: '12px', borderRadius: '8px', background: 'rgba(86,124,141,0.12)', border: '1px solid var(--border)' }}>
              <Timer style={{ width: 18, height: 18, color: 'var(--teal)' }} />
              <div>
                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Durée de l&apos;intervention</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--teal)', marginTop: '2px' }}>
                  {(form.duree_minutes / 60).toFixed(1)}h
                </div>
              </div>
              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginLeft: 'auto', background: '#fff', padding: '4px 8px', borderRadius: '4px' }}>Min 1h</span>
            </div>

            <div style={{ marginTop: '12px' }}>
              <label style={LABEL}><Car style={ICON_INLINE} /> Déplacement (heures)</label>
              <input type="number" style={INPUT} min={0} step={0.5} value={form.deplacement} onChange={e => set('deplacement', parseFloat(e.target.value) || 0)} />
            </div>
          </div>

          {/* ② Pièces de rechange */}
          <div style={SECTION}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                  <Wrench style={ICON_INLINE} /> Pièces de rechange
                </h3>
                {selectedCount > 0 && (
                  <span style={{ background: 'var(--teal)', color: '#fff', fontSize: '0.68rem', fontWeight: 700, padding: '3px 10px', borderRadius: '10px' }}>
                    {selectedCount} sélectionnée{selectedCount > 1 ? 's' : ''}
                  </span>
                )}
              </div>
              {form.machine && filteredPieces.length > 0 && (
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '10px', background: 'rgba(86,124,141,0.07)', padding: '6px 10px', borderRadius: '8px' }}>
                  <Tag style={{ width: 12, height: 12, display: 'inline-block', verticalAlign: '-1px', marginRight: '4px' }} /> {form.machine} · {filteredPieces.length} pièce{filteredPieces.length > 1 ? 's' : ''} compatible{filteredPieces.length > 1 ? 's' : ''}
                </p>
              )}
              {!form.machine && (
                <p style={{ margin: 0, padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem', background: '#fafafa', borderRadius: '8px' }}>
                  Choisissez un équipement pour afficher ses pièces compatibles.
                </p>
              )}
              {form.machine && filteredPieces.length === 0 && (
                <p style={{ margin: 0, padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem', background: '#fafafa', borderRadius: '8px' }}>
                  Aucune pièce de rechange compatible avec cet équipement.
                </p>
              )}
              {filteredPieces.length > 0 && <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '244px', overflowY: 'auto', paddingRight: '2px' }}>
                {filteredPieces.map((piece: any) => {
                  const qty = piecesQty[piece.id] || 0;
                  const stock = Number(piece.stock_actuel ?? piece.stock ?? 0);
                  const unavailable = stock === 0;
                  return (
                    <div key={piece.id} style={{ background: qty > 0 ? 'rgba(86,124,141,0.06)' : '#fafafa', border: `1px solid ${qty > 0 ? 'var(--teal)' : 'var(--border)'}`, borderRadius: '10px', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: '10px', opacity: unavailable && qty === 0 ? 0.55 : 1 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--navy)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{piece.designation || piece.nom}</p>
                        <div style={{ display: 'flex', gap: '6px', marginTop: '3px', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '2px' }}><Tag style={{ width: 10, height: 10 }} /> {piece.reference}</span>
                          <span style={{ fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '6px', background: unavailable ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)', color: unavailable ? 'var(--danger)' : '#15803D' }}>
                            {unavailable ? <><AlertTriangle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> Rupture</> : <><CheckCircle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> {stock} en stock</>}
                          </span>
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                        <button type="button" onClick={() => handleQty(piece.id, qty - 1)} disabled={qty === 0} style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: qty === 0 ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: qty === 0 ? 'not-allowed' : 'pointer' }}>−</button>
                        <span style={{ minWidth: '26px', textAlign: 'center', fontWeight: 800, color: qty > 0 ? 'var(--teal)' : 'var(--text-dim)', fontSize: '1.05rem' }}>{qty}</span>
                        <button type="button" onClick={() => handleQty(piece.id, qty + 1)} disabled={unavailable || qty >= stock} style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: unavailable || qty >= stock ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: unavailable || qty >= stock ? 'not-allowed' : 'pointer' }}>+</button>
                      </div>
                    </div>
                  );
                })}
              </div>}
            </div>

          {/* ③ Description & Notes */}
          <div style={SECTION}>
            <div style={{ marginBottom: '12px' }}>
              <label style={LABEL}><FileText style={ICON_INLINE} /> Description</label>
              <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2} value={form.description} onChange={e => set('description', e.target.value)} />
            </div>
            <div>
              <label style={LABEL}><ClipboardList style={ICON_INLINE} /> Notes</label>
              <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2} value={form.notes} onChange={e => set('notes', e.target.value)} />
            </div>
          </div>

          {/* ④ Statut — en bas, comme dans la fiche d'intervention */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Settings style={{ width: 16, height: 16 }} /> Statut de l&apos;intervention</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              {['Assignée', 'En cours', "Transfert vers l'atelier", 'En attente de piece', 'Cloturee'].map(status => {
                const style = STATUT_STYLES[status];
                return (
                  <button key={status} type="button" onClick={() => set('statut', status)} style={{ padding: '10px 4px', border: `2px solid ${form.statut === status ? style.color : 'var(--border)'}`, borderRadius: '10px', background: form.statut === status ? style.bg : '#fff', color: form.statut === status ? style.color : 'var(--text-muted)', fontWeight: form.statut === status ? 800 : 500, fontSize: '0.72rem', cursor: 'pointer', transition: 'all 0.2s', textAlign: 'center' }}>
                    {status}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Photo (clôture) */}
          {isClotured && (
            <div style={{ ...SECTION, border: '2px dashed var(--teal)' }}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Camera style={{ width: 16, height: 16 }} /> Fiche d&apos;intervention signée</h3>
              <input type="file" id="photo-input" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={handlePhoto} />
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <button type="button" onClick={() => document.getElementById('photo-input')?.click()}
                  style={{ flex: 1, background: 'var(--teal)', color: '#fff', border: 'none', padding: '14px', borderRadius: '10px', fontWeight: 700, cursor: 'pointer', fontSize: '0.95rem' }}>
                  <Camera style={{ width: 16, height: 16, display: 'inline-block', verticalAlign: '-3px', marginRight: '6px' }} /> {photoFile ? 'Changer la photo' : 'Prendre / Importer photo'}
                </button>
                {photoFile && (
                  <button type="button" onClick={() => { setPhotoFile(null); setPhotoPreview(''); }}
                    style={{ background: 'var(--danger)', color: '#fff', border: 'none', padding: '14px 16px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700, display: 'flex', alignItems: 'center' }}><Trash2 style={{ width: 18, height: 18 }} /></button>
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

              <div style={{ marginTop: '4px' }}>
                <label style={LABEL}>Statut de la fiche signée</label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '6px' }}>
                  {[
                    { val: 'En attente', icon: <Clock style={{ width: 14, height: 14 }} />, bg: 'rgba(245,158,11,0.1)', color: '#B45309' },
                    { val: 'Validée', icon: <CheckCircle style={{ width: 14, height: 14 }} />, bg: 'rgba(34,197,94,0.1)', color: '#15803D' },
                  ].map(({ val, icon, bg, color }) => (
                    <button key={val} type="button" onClick={() => set('fiche_validation', val)} style={{ padding: '12px 8px', border: `2px solid ${form.fiche_validation === val ? color : 'var(--border)'}`, borderRadius: '10px', background: form.fiche_validation === val ? bg : '#fff', color: form.fiche_validation === val ? color : 'var(--text-muted)', fontWeight: form.fiche_validation === val ? 800 : 500, fontSize: '0.82rem', cursor: 'pointer', transition: 'all 0.2s', textAlign: 'center' }}>
                      {icon} {val}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Error */}
          {error && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px' }}>{error}</p>}

          {/* Submit */}
          <button type="submit" disabled={saving}
            style={{ width: '100%', padding: '16px', background: 'linear-gradient(135deg, var(--teal), var(--navy))', color: '#fff', border: 'none', borderRadius: '12px', fontSize: '1rem', fontWeight: 800, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            {saving ? <><Loader2 style={{ width: 18, height: 18, animation: 'spin 1s linear infinite' }} /> Enregistrement...</> : <><Save style={{ width: 18, height: 18 }} /> Enregistrer l&apos;intervention{selectedCount > 0 ? ` · ${selectedCount} pièce${selectedCount > 1 ? 's' : ''}` : ''}</>}
          </button>
        </form>
      </main>
      <BottomNav />
    </div>
  );
}
