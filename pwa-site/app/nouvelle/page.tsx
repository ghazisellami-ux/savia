'use client';
import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { getUser, isLoggedIn } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';
import {
  ChevronLeft, CheckCircle, Building2, Settings, FileText, Search,
  Timer, Car, Wrench, ClipboardList, Camera, Trash2, Loader2, Save,
  Clock
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

export default function NouvelleInterventionPage() {
  const router = useRouter();
  const user = getUser();

  const [clients, setClients]     = useState<any[]>([]);
  const [equips, setEquips]       = useState<any[]>([]);
  const [techs, setTechs]         = useState<any[]>([]);
  const [pieces, setPieces]       = useState<any[]>([]);
  const [loading, setLoading]     = useState(false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');
  const [success, setSuccess]     = useState(false);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState('');

  const [form, setForm] = useState({
    client: '', machine: '', technicien_assigne: '', type_intervention: 'Corrective',
    statut: 'En cours', description: '', probleme: '', cause: '', solution: '',
    duree: 0, deplacement: 0, code_erreur: '', type_erreur: '', priorite: '',
    pieces_utilisees: [] as number[], notes: '', validation_client: 'En attente',
  });

  const filteredEquips = useMemo(() =>
    form.client ? equips.filter(e => (e.Client || e.client) === form.client) : equips,
    [equips, form.client]
  );

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    Promise.all([
      api.clients.list().catch(() => []),
      api.equipements.list().catch(() => []),
      api.techniciens.list().catch(() => []),
      api.pieces.list().catch(() => []),
    ]).then(([c, e, t, p]) => {
      setClients(c as any[]);
      setEquips(e as any[]);
      setTechs(t as any[]);
      setPieces(p as any[]);
      // Pre-fill technician
      const me = (t as any[]).find((x: any) => x.nom?.toLowerCase().includes(user?.nom?.toLowerCase() || ''));
      if (me) setForm(f => ({ ...f, technicien_assigne: String(me.id || me.nom) }));
    });
  }, []);

  const handlePhoto = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setPhotoFile(f);
    setPhotoPreview(URL.createObjectURL(f));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSaving(true);
    try {
      const payload = {
        ...form,
        technicien: form.technicien_assigne,
        duree_minutes: Math.round((form.duree || 0) * 60),
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
          {/* Client & Machine */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Building2 style={{ width: 16, height: 16 }} /> Identification</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={LABEL}>Client *</label>
                <select style={INPUT} value={form.client} onChange={e => set('client', e.target.value)} required>
                  <option value="">— Choisir —</option>
                  {clients.map((c: any) => <option key={c.id || c.nom || c.Nom} value={c.nom || c.Nom}>{c.nom || c.Nom}</option>)}
                </select>
              </div>
              <div>
                <label style={LABEL}>Machine *</label>
                <select style={INPUT} value={form.machine} onChange={e => set('machine', e.target.value)} required>
                  <option value="">— Choisir —</option>
                  {filteredEquips.map((e: any) => <option key={e.id || e.Nom || e.nom} value={e.Nom || e.nom}>{e.Nom || e.nom}</option>)}
                </select>
              </div>
            </div>
            <div style={{ marginTop: '12px' }}>
              <label style={LABEL}>Technicien(s)</label>
              <select style={INPUT} value={form.technicien_assigne} onChange={e => set('technicien_assigne', e.target.value)}>
                <option value="">— Choisir —</option>
                {techs.map((t: any) => <option key={t.id || t.nom} value={t.nom || t.id}>{t.nom}</option>)}
              </select>
            </div>
          </div>

          {/* Type & Statut */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Settings style={{ width: 16, height: 16 }} /> Classification</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={LABEL}>Type</label>
                <select style={INPUT} value={form.type_intervention} onChange={e => set('type_intervention', e.target.value)}>
                  <option>Corrective</option>
                  <option>Préventive</option>
                </select>
              </div>
              <div>
                <label style={LABEL}>Statut</label>
                <select style={INPUT} value={form.statut} onChange={e => set('statut', e.target.value)}>
                  <option>En cours</option>
                  <option>En attente de piece</option>
                  <option>Cloturee</option>
                </select>
              </div>
            </div>
            <div style={{ marginTop: '12px' }}>
              <label style={LABEL}>Priorité</label>
              <select style={INPUT} value={form.priorite} onChange={e => set('priorite', e.target.value)}>
                <option value="">— Aucune —</option>
                <option>Haute</option>
                <option>Moyenne</option>
                <option>Basse</option>
              </select>
            </div>
          </div>

          {/* Description */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><FileText style={{ width: 16, height: 16 }} /> Description</h3>
            <textarea style={{ ...INPUT, resize: 'vertical', minHeight: '80px' }} rows={3}
              placeholder="Décrivez le problème..." value={form.description}
              onChange={e => set('description', e.target.value)} />
          </div>

          {/* Diagnostic (Corrective only) */}
          {form.type_intervention === 'Corrective' && (
            <div style={SECTION}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Search style={{ width: 16, height: 16 }} /> Diagnostic</h3>
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
                  <label style={LABEL}>Code Erreur</label>
                  <input style={INPUT} placeholder="Ex: E102, 0x3F..." value={form.code_erreur} onChange={e => set('code_erreur', e.target.value)} />
                </div>
                <div>
                  <label style={LABEL}>Type d&apos;erreur</label>
                  <select style={INPUT} value={form.type_erreur} onChange={e => set('type_erreur', e.target.value)}>
                    <option value="">— Aucun —</option>
                    {['Hardware','Software','Réseau','Calibration','Mécanique','Électrique','Autre'].map(t => <option key={t}>{t}</option>)}
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Durées */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Timer style={{ width: 16, height: 16 }} /> Temps</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={LABEL}>Durée (heures)</label>
                <input type="number" style={INPUT} min={0} step={0.5} value={form.duree} onChange={e => set('duree', parseFloat(e.target.value) || 0)} />
              </div>
              <div>
                <label style={LABEL}><Car style={ICON_INLINE} /> Déplacement (h)</label>
                <input type="number" style={INPUT} min={0} step={0.5} value={form.deplacement} onChange={e => set('deplacement', parseFloat(e.target.value) || 0)} />
              </div>
            </div>
          </div>

          {/* Pièces */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Wrench style={{ width: 16, height: 16 }} /> Pièces utilisées</h3>
            <select style={{ ...INPUT, height: '100px' }} multiple
              value={form.pieces_utilisees.map(String)}
              onChange={e => set('pieces_utilisees', Array.from(e.target.selectedOptions).map(o => Number(o.value)))}>
              {pieces.map((p: any) => <option key={p.id} value={p.id}>{p.nom} — {p.reference}</option>)}
            </select>
            <small style={{ color: 'var(--text-dim)', fontSize: '0.72rem' }}>Tap long pour sélectionner plusieurs pièces</small>
          </div>

          {/* Notes */}
          <div style={SECTION}>
            <label style={LABEL}><ClipboardList style={ICON_INLINE} /> Notes</label>
            <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2} placeholder="Observations complémentaires..."
              value={form.notes} onChange={e => set('notes', e.target.value)} />
          </div>

          {/* Photo (clôture) */}
          {isClotured && (
            <div style={SECTION}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Camera style={{ width: 16, height: 16 }} /> Fiche Signée</h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '10px' }}>Photographiez la fiche d&apos;intervention avec la signature du client.</p>
              <input type="file" id="photo-input" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={handlePhoto} />
              <div style={{ display: 'flex', gap: '8px' }}>
                <button type="button" onClick={() => document.getElementById('photo-input')?.click()}
                  style={{ flex: 1, background: 'var(--teal)', color: '#fff', border: 'none', padding: '12px', borderRadius: '10px', fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                  <Camera style={{ width: 16, height: 16 }} /> Prendre photo
                </button>
                {photoFile && (
                  <button type="button" onClick={() => { setPhotoFile(null); setPhotoPreview(''); }}
                    style={{ background: 'var(--danger)', color: '#fff', border: 'none', padding: '12px 16px', borderRadius: '10px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}><Trash2 style={{ width: 18, height: 18 }} /></button>
                )}
              </div>
              {photoPreview && (
                <div style={{ marginTop: '10px' }}>
                  <img src={photoPreview} alt="Aperçu" style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: '10px', border: '2px solid var(--teal)', objectFit: 'contain' }} />
                  <p style={{ color: 'var(--success)', fontSize: '0.8rem', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}><CheckCircle style={{ width: 14, height: 14 }} /> Photo jointe</p>
                </div>
              )}

              {/* Validation client */}
              <div style={{ marginTop: '16px' }}>
                <label style={LABEL}><CheckCircle style={ICON_INLINE} /> Validation Client</label>
                <select style={INPUT} value={form.validation_client} onChange={e => set('validation_client', e.target.value)}>
                  <option value="En attente">En attente</option>
                  <option value="Validée">Validée</option>
                </select>
              </div>
            </div>
          )}

          {/* Error */}
          {error && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px' }}>{error}</p>}

          {/* Submit */}
          <button type="submit" disabled={saving}
            style={{ width: '100%', padding: '16px', background: 'linear-gradient(135deg, var(--teal), var(--navy))', color: '#fff', border: 'none', borderRadius: '12px', fontSize: '1rem', fontWeight: 800, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            {saving ? <><Loader2 style={{ width: 18, height: 18, animation: 'spin 1s linear infinite' }} /> Enregistrement...</> : <><Save style={{ width: 18, height: 18 }} /> Enregistrer l&apos;intervention</>}
          </button>
        </form>
      </main>
      <BottomNav />
    </div>
  );
}
