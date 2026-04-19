'use client';
import { useState, useEffect, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import {
  Plus, Search, FileText, Calendar, DollarSign, Clock, Wrench,
  X, ChevronDown, Package, Bell, RefreshCcw, CheckSquare, StickyNote,
  Loader2, AlertTriangle, CheckCircle2, ShieldCheck, Building2
} from 'lucide-react';
import { contrats, equipements, pieces as piecesApi } from '@/lib/api';

const INPUT = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-2 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all text-sm";
const LABEL = "block text-xs font-semibold text-savia-text-muted mb-1 uppercase tracking-wider";
const SECTION_TITLE = "flex items-center gap-2 text-sm font-bold text-savia-text mb-3 pb-2 border-b border-savia-border";

const TYPES_CONTRAT = ['Maintenance Préventive', 'Maintenance Corrective', 'Full Service', 'Standard', 'Premium', 'Pièces incluses', 'Main d\'œuvre uniquement'];
const RECURRENCES = ['Mensuelle', 'Trimestrielle', 'Semestrielle', 'Annuelle', 'Hebdomadaire'];

interface Contrat {
  id: string;
  client: string;
  equipement: string;
  type_contrat: string;
  date_debut: string;
  date_fin: string;
  sla_temps_reponse_h: number;
  montant: number;
  statut: string;
  conditions: string;
  notes: string;
}

const emptyForm = () => ({
  client: '',
  equipement: '',
  type_contrat: TYPES_CONTRAT[0],
  date_debut: new Date().toISOString().substring(0, 10),
  date_fin: new Date(Date.now() + 365 * 86400000).toISOString().substring(0, 10),
  sla_temps_reponse_h: 4,
  montant: 0,
  avec_pieces: false,
  pieces_selectionnees: [] as { ref: string; designation: string; quota: number }[],
  rappel_avant: 30,
  rappel_unite: 'jours' as 'jours' | 'mois',
  recurrence_maintenance: RECURRENCES[2],
  date_premiere_maintenance: new Date().toISOString().substring(0, 10),
  conditions: '',
  notes: '',
  statut: 'Actif',
});

export default function ContratsPage() {
  const [search, setSearch] = useState('');
  const [data, setData] = useState<Contrat[]>([]);
  const [equips, setEquips] = useState<any[]>([]);
  const [stockPieces, setStockPieces] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [form, setForm] = useState(emptyForm());

  const load = useCallback(async () => {
    try {
      const [ctrs, eqs, pcs] = await Promise.all([contrats.list(), equipements.list(), piecesApi.list()]);
      setData((ctrs as any[]).map((item: any) => ({
        id: String(item.id || ''),
        client: item.client || item.Client || '',
        equipement: item.equipement || '',
        type_contrat: item.type_contrat || 'Standard',
        date_debut: (item.date_debut || '').substring(0, 10),
        date_fin: (item.date_fin || '').substring(0, 10),
        sla_temps_reponse_h: item.sla_temps_reponse_h || 4,
        montant: item.montant || item.Montant_Annuel || 0,
        statut: item.statut || 'Actif',
        conditions: item.conditions || '',
        notes: item.notes || '',
      })));
      setEquips(eqs as any[]);
      setStockPieces(pcs as any[]);
    } catch (err) { console.error(err); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Derived lists
  const clients = [...new Set(equips.map((e: any) => e.Client).filter(Boolean))].sort();
  const equipsByClient = form.client
    ? equips.filter((e: any) => e.Client === form.client)
    : [];

  // Filter pieces — use designation + equipement_type (correct DB fields)
  const filteredPieces = form.equipement
    ? stockPieces.filter((p: any) => {
        const eq = equips.find((e: any) => e.Nom === form.equipement);
        const eqType = (eq?.Type_Equipement || eq?.type || '').toLowerCase().split(' ')[0];
        if (!eqType) return true;
        return (p.designation || '').toLowerCase().includes(eqType) ||
               (p.equipement_type || '').toLowerCase().includes(eqType);
      })
    : stockPieces;

  const handleSave = async () => {
    if (!form.client) { setSaveMsg('Veuillez sélectionner un client.'); return; }
    setIsSaving(true);
    setSaveMsg('');
    try {
      const payload = {
        client: form.client,
        equipement: form.equipement,
        type_contrat: form.type_contrat,
        date_debut: form.date_debut,
        date_fin: form.date_fin,
        sla_temps_reponse_h: Number(form.sla_temps_reponse_h),
        montant: Number(form.montant),
        avec_pieces: form.avec_pieces,
        pieces_incluses: form.avec_pieces ? JSON.stringify(form.pieces_selectionnees) : '',
        rappel_avant_jours: form.rappel_unite === 'jours' ? form.rappel_avant : form.rappel_avant * 30,
        recurrence_maintenance: form.recurrence_maintenance,
        date_premiere_maintenance: form.date_premiere_maintenance,
        conditions: form.conditions,
        notes: form.notes,
        statut: form.statut,
      };
      await (contrats as any).create(payload);
      setSaveMsg('✅ Contrat créé avec succès !');
      setForm(emptyForm());
      await load();
      setTimeout(() => { setShowModal(false); setSaveMsg(''); }, 1500);
    } catch (err: any) {
      setSaveMsg(`❌ Erreur: ${err?.message || 'Indisponible'}`);
    } finally { setIsSaving(false); }
  };

  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }));

  // Toggle a piece in/out of selection (identified by unique reference)
  const togglePiece = (ref: string, designation: string) => setForm(f => {
    const exists = f.pieces_selectionnees.find(s => s.ref === ref);
    return {
      ...f,
      pieces_selectionnees: exists
        ? f.pieces_selectionnees.filter(s => s.ref !== ref)
        : [...f.pieces_selectionnees, { ref, designation, quota: 1 }],
    };
  });

  const setPieceQuota = (ref: string, quota: number) => setForm(f => ({
    ...f,
    pieces_selectionnees: f.pieces_selectionnees.map(s => s.ref === ref ? { ...s, quota: Math.max(1, quota) } : s),
  }));

  const filtered = data.filter(c =>
    !search || c.client.toLowerCase().includes(search.toLowerCase()) ||
    c.id.toLowerCase().includes(search.toLowerCase()) ||
    (c.type_contrat || '').toLowerCase().includes(search.toLowerCase())
  );

  const actifs = data.filter(c => (c.statut || '').toLowerCase().includes('actif')).length;
  const expires = data.filter(c => {
    const fin = new Date(c.date_fin);
    const diff = (fin.getTime() - Date.now()) / 86400000;
    return diff >= 0 && diff <= 60;
  }).length;
  const totalRevenu = data.reduce((a, b) => a + (b.montant || 0), 0);

  if (isLoading) return (
    <div className="flex justify-center items-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
    </div>
  );

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-2">
            <FileText className="w-7 h-7 text-savia-accent" /> Contrats de Maintenance
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des contrats SAV et maintenance préventive</p>
        </div>
        <button onClick={() => { setForm(emptyForm()); setSaveMsg(''); setShowModal(true); }}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20">
          <Plus className="w-4 h-4" /> Nouveau contrat
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total contrats', value: data.length, color: 'text-savia-accent', icon: <FileText className="w-5 h-5" /> },
          { label: 'Actifs', value: actifs, color: 'text-green-400', icon: <CheckCircle2 className="w-5 h-5" /> },
          { label: 'Expirent dans 60j', value: expires, color: 'text-yellow-400', icon: <AlertTriangle className="w-5 h-5" /> },
          { label: 'Revenu annuel', value: `${(totalRevenu / 1000).toFixed(0)}K TND`, color: 'text-savia-accent', icon: <DollarSign className="w-5 h-5" /> },
        ].map(k => (
          <div key={k.label} className="glass rounded-xl p-4 text-center">
            <div className={`${k.color} mx-auto mb-1 flex justify-center`}>{k.icon}</div>
            <div className={`text-3xl font-black ${k.color}`}>{k.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {/* ===== BANNER : contrats expirant dans 30j ===== */}
      {(() => {
        const expiring30 = data.filter(c => {
          const diff = (new Date(c.date_fin).getTime() - Date.now()) / 86400000;
          return diff >= 0 && diff <= 30 && (c.statut || '').toLowerCase() === 'actif';
        });
        if (expiring30.length === 0) return null;
        return (
          <div className="rounded-xl border-l-4 border-amber-500 bg-amber-50 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
              <span className="font-bold text-amber-800">
                ⚠️ {expiring30.length} contrat(s) expire(nt) dans moins de 30 jours
              </span>
            </div>
            <div className="space-y-1 pl-7">
              {expiring30.map(c => {
                const daysLeft = Math.round((new Date(c.date_fin).getTime() - Date.now()) / 86400000);
                return (
                  <div key={c.id} className="flex items-center gap-2 text-sm text-amber-700">
                    <span className="font-mono text-xs bg-amber-100 px-1.5 py-0.5 rounded">#{c.id}</span>
                    <span className="font-semibold">{c.client}</span>
                    {c.equipement && <span className="text-amber-500">— {c.equipement}</span>}
                    <span className="ml-auto font-bold">{daysLeft}j restant(s)</span>
                    <span className="text-amber-500">• {c.date_fin}</span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
        <input type="text" placeholder="Rechercher par client, type, référence..." value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim outline-none" />
      </div>

      {/* Contract list */}
      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="glass rounded-xl p-8 text-center text-savia-text-muted">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            Aucun contrat trouvé
          </div>
        )}
        {filtered.map(c => {
          const fin = new Date(c.date_fin);
          const daysLeft = Math.round((fin.getTime() - Date.now()) / 86400000);
          const isExpiring = daysLeft >= 0 && daysLeft <= 60;
          const isExpired = daysLeft < 0;
          return (
            <div key={c.id} className="glass rounded-xl p-4 hover:border-savia-accent/30 transition-all">
              <div className="flex items-start justify-between mb-2">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <FileText className="w-4 h-4 text-savia-accent shrink-0" />
                    <span className="font-mono text-savia-accent font-bold text-sm">#{c.id}</span>
                    <span className="font-bold">{c.client}</span>
                    {c.equipement && <span className="text-xs text-savia-text-muted">— {c.equipement}</span>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-savia-text-muted flex-wrap">
                    <span className="flex items-center gap-1"><Wrench className="w-3 h-3" /> {c.type_contrat}</span>
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> SLA: {c.sla_temps_reponse_h}h</span>
                    <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> {c.date_debut} → {c.date_fin}</span>
                    {c.montant > 0 && <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" /> {c.montant.toLocaleString('fr')} TND/an</span>}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${
                    isExpired ? 'bg-red-500/10 text-red-400' :
                    isExpiring ? 'bg-yellow-500/10 text-yellow-400' :
                    'bg-green-500/10 text-green-400'
                  }`}>
                    {isExpired ? 'Expiré' : isExpiring ? `Expire dans ${daysLeft}j` : c.statut}
                  </span>
                </div>
              </div>
              {c.conditions && (
                <p className="text-xs text-savia-text-muted mt-2 italic border-l-2 border-savia-border pl-2 line-clamp-2">{c.conditions}</p>
              )}
            </div>
          );
        })}
      </div>

      {/* ===================== MODAL ===================== */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-6 px-4">
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-2xl shadow-2xl">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border">
              <h2 className="text-lg font-black gradient-text flex items-center gap-2">
                <Plus className="w-5 h-5 text-savia-accent" /> Nouveau Contrat
              </h2>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted hover:text-savia-text transition-all cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="px-6 py-5 space-y-6 max-h-[80vh] overflow-y-auto">

              {/* === SECTION: Client & Équipement === */}
              <div>
                <div className={SECTION_TITLE}>
                  <Building2 className="w-4 h-4 text-savia-accent" /> Client &amp; Équipement
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className={LABEL}>Client *</label>
                    <select className={INPUT} value={form.client} onChange={e => { set('client', e.target.value); set('equipement', ''); }}>
                      <option value="">— Sélectionner un client —</option>
                      {clients.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={LABEL}>Équipement</label>
                    <select className={INPUT} value={form.equipement} onChange={e => set('equipement', e.target.value)} disabled={!form.client}>
                      <option value="">— Tous les équipements —</option>
                      {equipsByClient.map((e: any) => <option key={e.id} value={e.Nom}>{e.Nom}</option>)}
                    </select>
                    {!form.client && <p className="text-xs text-savia-text-muted mt-1">Sélectionnez d'abord un client</p>}
                  </div>
                </div>
              </div>

              {/* === SECTION: Contrat === */}
              <div>
                <div className={SECTION_TITLE}>
                  <FileText className="w-4 h-4 text-savia-accent" /> Détails du Contrat
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className={LABEL}>Type de contrat</label>
                    <select className={INPUT} value={form.type_contrat} onChange={e => set('type_contrat', e.target.value)}>
                      {TYPES_CONTRAT.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={LABEL}>Statut</label>
                    <select className={INPUT} value={form.statut} onChange={e => set('statut', e.target.value)}>
                      {['Actif', 'Suspendu', 'Expiré', 'En attente'].map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={LABEL}>Date début</label>
                    <input type="date" className={INPUT} value={form.date_debut} onChange={e => set('date_debut', e.target.value)} />
                  </div>
                  <div>
                    <label className={LABEL}>Date fin</label>
                    <input type="date" className={INPUT} value={form.date_fin} onChange={e => set('date_fin', e.target.value)} />
                  </div>
                  <div>
                    <label className={LABEL}>SLA Réponse (heures)</label>
                    <input type="number" className={INPUT} value={form.sla_temps_reponse_h} min={1} max={240}
                      onChange={e => set('sla_temps_reponse_h', Number(e.target.value))} />
                    <p className="text-xs text-savia-text-muted mt-1">Délai max de réponse garantie</p>
                  </div>
                  <div>
                    <label className={LABEL}>Montant annuel (TND)</label>
                    <input type="number" className={INPUT} value={form.montant} min={0}
                      onChange={e => set('montant', Number(e.target.value))} />
                  </div>
                </div>
              </div>

              {/* === SECTION: Pièces === */}
              <div>
                <div className={SECTION_TITLE}>
                  <Package className="w-4 h-4 text-savia-accent" /> Pièces de Rechange
                </div>
                <label className="flex items-center gap-3 cursor-pointer group mb-3">
                  <div onClick={() => set('avec_pieces', !form.avec_pieces)}
                    className={`w-5 h-5 rounded flex items-center justify-center border-2 transition-all ${form.avec_pieces ? 'bg-savia-accent border-savia-accent' : 'border-savia-border group-hover:border-savia-accent/60'}`}>
                    {form.avec_pieces && <CheckSquare className="w-3 h-3 text-white" />}
                  </div>
                  <span className="text-sm font-semibold">Contrat avec pièces incluses</span>
                </label>
                {form.avec_pieces && (
                  <div className="space-y-3 mt-2">
                    <p className="text-xs text-savia-text-muted">Cochez les pièces incluses et définissez un quota pour la durée du contrat :</p>
                    <div className="border border-savia-border rounded-xl overflow-hidden">
                      <div className="max-h-64 overflow-y-auto divide-y divide-savia-border">
                        {filteredPieces.length === 0 ? (
                          <p className="text-xs text-savia-text-muted p-3">Aucune pièce disponible.</p>
                        ) : filteredPieces.map((p: any) => {
                          const ref = p.reference || String(p.id || Math.random());
                          const dsg = p.designation || p.reference || '—';
                          const sel = form.pieces_selectionnees.find(s => s.ref === ref);
                          return (
                            <div key={ref} className={`transition-colors ${sel ? 'bg-savia-accent/5' : 'bg-white'}`}>
                              <label className="flex items-center gap-3 cursor-pointer px-3 py-2.5 hover:bg-savia-surface-hover">
                                <input type="checkbox" className="accent-cyan-400 w-4 h-4 shrink-0"
                                  checked={!!sel}
                                  onChange={() => togglePiece(ref, dsg)} />
                                <div className="flex-1 min-w-0">
                                  <div className="text-sm font-bold text-[#2F4156] truncate">{dsg}</div>
                                  <div className="text-[10px] font-mono text-savia-text-muted">{ref}</div>
                                </div>
                                <div className="text-right shrink-0">
                                  <div className="text-sm font-bold text-[#2F4156]">{p.stock_actuel}</div>
                                  <div className="text-[10px] text-savia-text-dim">en stock</div>
                                </div>
                              </label>
                              {sel && (
                                <div className="flex items-center gap-2 px-10 pb-2.5">
                                  <span className="text-xs text-savia-text-muted shrink-0">Quota contrat :</span>
                                  <input type="number" min={1} value={sel.quota}
                                    className="w-20 text-sm font-bold border-2 border-savia-accent/40 rounded-lg px-2 py-1.5 bg-white text-[#2F4156] outline-none focus:border-savia-accent"
                                    style={{ appearance: 'textfield' }}
                                    onChange={e => setPieceQuota(ref, Number(e.target.value))} />
                                  <span className="text-xs text-savia-text-muted">unités sur la durée du contrat</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    {form.pieces_selectionnees.length > 0 && (
                      <p className="text-xs font-semibold text-savia-accent">
                        {form.pieces_selectionnees.length} pièce(s) sélectionnée(s) — quota total : {form.pieces_selectionnees.reduce((a, b) => a + b.quota, 0)} unités
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* === SECTION: Rappel & Maintenance === */}
              <div>
                <div className={SECTION_TITLE}>
                  <Bell className="w-4 h-4 text-savia-accent" /> Rappels &amp; Maintenance
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className={LABEL}>Rappel avant expiration</label>
                    <div className="grid grid-cols-2 gap-2">
                      <input type="number" min={1} max={365}
                        className="w-full border-2 border-savia-accent/40 rounded-lg px-3 py-2 bg-white text-[#2F4156] font-bold outline-none focus:border-savia-accent"
                        style={{ appearance: 'textfield' }}
                        value={form.rappel_avant}
                        onChange={e => set('rappel_avant', Number(e.target.value))} />
                      <select className={INPUT} value={form.rappel_unite} onChange={e => set('rappel_unite', e.target.value)}>
                        <option value="jours">jours</option>
                        <option value="mois">mois</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className={LABEL}>Récurrence maintenance</label>
                    <select className={INPUT} value={form.recurrence_maintenance} onChange={e => set('recurrence_maintenance', e.target.value)}>
                      {RECURRENCES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                  <div className="md:col-span-2">
                    <label className={LABEL}>Date première maintenance</label>
                    <input type="date" className={INPUT} value={form.date_premiere_maintenance}
                      onChange={e => set('date_premiere_maintenance', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* === SECTION: Conditions & Notes === */}
              <div>
                <div className={SECTION_TITLE}>
                  <StickyNote className="w-4 h-4 text-savia-accent" /> Conditions &amp; Notes
                </div>
                <div className="space-y-3">
                  <div>
                    <label className={LABEL}>Conditions du contrat</label>
                    <textarea className={`${INPUT} resize-none`} rows={3} placeholder="Pénalités, exclusions, engagements..."
                      value={form.conditions} onChange={e => set('conditions', e.target.value)} />
                  </div>
                  <div>
                    <label className={LABEL}>Notes internes</label>
                    <textarea className={`${INPUT} resize-none`} rows={3} placeholder="Remarques, contacts, informations complémentaires..."
                      value={form.notes} onChange={e => set('notes', e.target.value)} />
                  </div>
                </div>
              </div>

              {/* Save message */}
              {saveMsg && (
                <div className={`p-3 rounded-lg text-sm font-semibold ${saveMsg.includes('✅') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {saveMsg}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-savia-border">
              <button onClick={() => setShowModal(false)} disabled={isSaving}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-all cursor-pointer">
                Annuler
              </button>
              <button onClick={handleSave} disabled={isSaving || !form.client}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20 disabled:opacity-50">
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                {isSaving ? 'Enregistrement...' : 'Créer le contrat'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
