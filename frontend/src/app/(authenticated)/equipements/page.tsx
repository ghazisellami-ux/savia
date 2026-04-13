'use client';
// ==========================================
// 🏥 PAGE PARC ÉQUIPEMENTS — SAVIA
// ==========================================
import { useState, useMemo, useEffect, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import { Plus, Search, Edit2, Trash2, ChevronDown, ChevronUp, Filter, Loader2, Save, X } from 'lucide-react';
import { equipements } from '@/lib/api';

interface Equipment {
  id: string;
  nom: string;
  type: string;
  marque: string;
  modele: string;
  numSerie: string;
  client: string;
  localisation: string;
  dateMiseEnService: string;
  derniereMaintenance: string;
  prochaineMaintenance: string;
  healthScore: number;
  statut: string;
}

const INPUT_CLS = "w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white placeholder:text-slate-500 focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500/40 outline-none transition-all";

function getStatutBadge(statut: string) {
  const s = statut.toLowerCase();
  if (s.includes('opérationnel') || s.includes('actif')) return 'bg-green-500/10 text-green-400 border-green-500/20';
  if (s.includes('maintenance')) return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
  if (s.includes('hors service') || s.includes('critique')) return 'bg-red-500/10 text-red-400 border-red-500/20';
  return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
}

export default function EquipementsPage() {
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('Tous');
  const [filterClient, setFilterClient] = useState('Tous');
  const [showAddModal, setShowAddModal] = useState(false);
  const [data, setData] = useState<Equipment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Form state
  const emptyForm = { Nom: '', Type: '', Fabricant: '', Modele: '', NumSerie: '', Client: '', Notes: '', Statut: 'Actif' };
  const [form, setForm] = useState(emptyForm);

  const dynamicClients = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.client).filter(Boolean)))], [data]);
  const dynamicTypes = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.type).filter(Boolean)))], [data]);

  const loadData = useCallback(async () => {
    try {
      const res = await equipements.list();
      const mapped = res.map((item: any) => ({
        id: String(item.id || item.Nom),
        nom: item.Nom || '',
        type: item.Type || '',
        marque: item.Fabricant || '',
        modele: item.Modele || '',
        numSerie: item.NumSerie || '',
        client: item.Client || 'Centre Principal',
        localisation: item.Notes || 'S/O',
        dateMiseEnService: item.DateInstallation || 'N/A',
        derniereMaintenance: item.DernieresMaintenance || 'N/A',
        prochaineMaintenance: 'N/A',
        healthScore: item.Statut && (item.Statut === 'Actif' || item.Statut === 'Opérationnel') ? 95 : 50,
        statut: item.Statut || 'Actif',
      }));
      setData(mapped);
    } catch (err) {
      console.error("Failed to fetch equipements", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSave = async () => {
    if (!form.Nom.trim()) return;
    setIsSaving(true);
    try {
      await equipements.create(form);
      setForm(emptyForm);
      setShowAddModal(false);
      await loadData();
    } catch (err) {
      console.error("Save failed", err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Supprimer cet équipement ?")) return;
    try {
      await equipements.delete(Number(id));
      await loadData();
    } catch (err) {
      console.error("Delete failed", err);
    }
  };

  const filtered = useMemo(() => {
    return data.filter(eq => {
      if (filterType !== 'Tous' && eq.type !== filterType) return false;
      if (filterClient !== 'Tous' && eq.client !== filterClient) return false;
      if (search && !eq.nom.toLowerCase().includes(search.toLowerCase()) &&
          !eq.numSerie.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [search, filterType, filterClient, data]);

  const totalEquip = data.length;
  const operationnel = data.filter(e => e.statut.toLowerCase().includes('actif') || e.statut.toLowerCase().includes('opérationnel')).length;
  const maintenance = totalEquip - operationnel;
  const avgHealth = totalEquip > 0 ? Math.round(data.reduce((a, b) => a + b.healthScore, 0) / totalEquip) : 0;

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">🏥 Parc Équipements</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion du parc d&apos;équipements de radiologie</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer"
        >
          <Plus className="w-4 h-4" /> Nouvel Équipement
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Équipements', value: totalEquip, color: 'text-savia-accent' },
          { label: 'Opérationnels', value: operationnel, color: 'text-green-400' },
          { label: 'En arrêt/Panne', value: maintenance, color: 'text-red-400' },
          { label: 'Santé Moy.', value: `${avgHealth}%`, color: avgHealth >= 80 ? 'text-green-400' : 'text-yellow-400' },
        ].map(kpi => (
          <div key={kpi.label} className="glass rounded-xl p-4 text-center">
            <div className={`text-3xl font-black ${kpi.color}`}>{kpi.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input
            type="text"
            placeholder="Rechercher par nom ou N° série..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim"
          />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          {dynamicTypes.map(t => <option key={t} value={t}>{t === 'Tous' ? '📁 Tous les types' : t}</option>)}
        </select>
        <select value={filterClient} onChange={e => setFilterClient(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          {dynamicClients.map(c => <option key={c} value={c}>{c === 'Tous' ? '🏢 Tous les clients' : c}</option>)}
        </select>
      </div>

      {/* Equipment Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map(eq => (
          <div key={eq.id} className="glass rounded-xl p-5 hover:border-savia-accent/30 transition-all group">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-bold text-lg">{eq.nom}</h3>
                <p className="text-savia-text-muted text-sm">{eq.marque} — {eq.modele}</p>
              </div>
              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getStatutBadge(eq.statut)}`}>
                {eq.statut}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm mb-3">
              <div><span className="text-savia-text-dim">🏢</span> {eq.client}</div>
              <div><span className="text-savia-text-dim">📍</span> {eq.localisation}</div>
              <div><span className="text-savia-text-dim">🔢</span> <code className="text-xs">{eq.numSerie}</code></div>
              <div><span className="text-savia-text-dim">📅</span> Maint: {eq.derniereMaintenance}</div>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs text-savia-text-dim">Santé:</span>
                <div className="w-24 h-2 bg-savia-bg rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${eq.healthScore >= 85 ? 'bg-green-500' : eq.healthScore >= 65 ? 'bg-yellow-500' : 'bg-red-500'}`}
                    style={{ width: `${eq.healthScore}%` }}
                  />
                </div>
                <span className={`text-sm font-bold ${eq.healthScore >= 85 ? 'text-green-400' : eq.healthScore >= 65 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {eq.healthScore}%
                </span>
              </div>
              <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer"><Edit2 className="w-3.5 h-3.5" /></button>
                <button onClick={() => handleDelete(eq.id)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="glass rounded-xl p-8 text-center">
          <p className="text-savia-text-muted">Aucun équipement trouvé pour ces filtres.</p>
        </div>
      )}

      {/* Add Equipment Modal */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="➕ Nouvel Équipement" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Nom *</label>
            <input className={INPUT_CLS} placeholder="Ex: Scanner GE Revolution" value={form.Nom} onChange={e => setForm({...form, Nom: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Type</label>
            <select className={INPUT_CLS} value={form.Type} onChange={e => setForm({...form, Type: e.target.value})}>
              <option value="">— Sélectionner —</option>
              {['Scanner CT', 'IRM', 'Radiographie', 'Mammographie', 'Échographie', 'Fluoroscopie', 'Angiographie'].map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Fabricant</label>
            <input className={INPUT_CLS} placeholder="Ex: GE Healthcare" value={form.Fabricant} onChange={e => setForm({...form, Fabricant: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Modèle</label>
            <input className={INPUT_CLS} placeholder="Ex: Revolution CT" value={form.Modele} onChange={e => setForm({...form, Modele: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">N° Série</label>
            <input className={INPUT_CLS} placeholder="Ex: SN-2024-0042" value={form.NumSerie} onChange={e => setForm({...form, NumSerie: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Client</label>
            <input className={INPUT_CLS} placeholder="Ex: Clinique El Manar" value={form.Client} onChange={e => setForm({...form, Client: e.target.value})} />
          </div>
          <div className="md:col-span-2">
            <label className="block text-sm text-slate-400 mb-1">Notes / Localisation</label>
            <input className={INPUT_CLS} placeholder="Ex: Salle 3, RDC" value={form.Notes} onChange={e => setForm({...form, Notes: e.target.value})} />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowAddModal(false)} className="px-4 py-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer">Annuler</button>
          <button onClick={handleSave} disabled={isSaving || !form.Nom.trim()} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Sauvegarder
          </button>
        </div>
      </Modal>
    </div>
  );
}
