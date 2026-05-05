'use client';
import { Search, Building2, Users, Wrench, Loader2, Plus, Upload, X, Globe, MapPin, FileSpreadsheet, CheckCircle } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { clients as clientsApi } from '@/lib/api';

const REGIONS: Record<string, string[]> = {
  'Nord': ['Tunis','Ariana','Ben Arous','Manouba','Bizerte','Béja','Jendouba','Le Kef','Siliana','Nabeul','Zaghouan'],
  'Centre': ['Sousse','Monastir','Mahdia','Sfax','Kairouan','Kasserine','Sidi Bouzid'],
  'Sud': ['Gabès','Médenine','Tataouine','Tozeur','Gafsa','Kébili'],
};

interface Client {
  id?: number; nom: string; code_client: string; ville: string; region: string;
  contact: string; telephone: string; adresse: string; matricule_fiscale: string;
  type_client: string; international: boolean;
  nb_equipements: number; nb_interventions: number; score_sante: number;
}

const emptyForm = (): Record<string, any> => ({
  nom:'', code_client:'', matricule_fiscale:'', ville:'', region:'', contact:'',
  telephone:'', adresse:'', type_client:'Privé', international: false,
});

export default function ClientsPage() {
  const [search, setSearch] = useState('');
  const [regionFilter, setRegionFilter] = useState('');
  const [data, setData] = useState<Client[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editId, setEditId] = useState<number|null>(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = async () => {
    try {
      const res = await clientsApi.list();
      setData(res.map((item: any) => ({
        id: item.id, nom: item.nom||'', code_client: item.code_client||'',
        ville: item.ville||'', region: item.region||'',
        contact: item.contact||'', telephone: item.telephone||'',
        adresse: item.adresse||'', matricule_fiscale: item.matricule_fiscale||'',
        type_client: item.type_client||'', international: !!item.international,
        nb_equipements: item.nb_equipements||0, nb_interventions: item.nb_interventions||0,
        score_sante: item.score_sante||80,
      })));
    } catch(e) { console.error(e); } finally { setIsLoading(false); }
  };

  useEffect(() => { loadData(); }, []);

  const filtered = data.filter(c => {
    if (search && !c.nom.toLowerCase().includes(search.toLowerCase())) return false;
    if (regionFilter && c.region !== regionFilter) return false;
    return true;
  });

  const totalMachines = data.reduce((a,c) => a+c.nb_equipements, 0);
  const totalInterv = data.reduce((a,c) => a+c.nb_interventions, 0);
  const avgHealth = data.length > 0 ? Math.round(data.reduce((a,c) => a+c.score_sante, 0)/data.length) : 0;

  const openAdd = () => { setForm(emptyForm()); setEditId(null); setShowModal(true); };
  const openEdit = (c: Client) => {
    setForm({ nom:c.nom, code_client:c.code_client, matricule_fiscale:c.matricule_fiscale,
      ville:c.ville, region:c.region, contact:c.contact, telephone:c.telephone,
      adresse:c.adresse, type_client:c.type_client||'Privé', international:c.international });
    setEditId(c.id||null); setShowModal(true);
  };

  const handleSave = async () => {
    if (!form.nom.trim()) return alert('Le nom est obligatoire');
    setSaving(true);
    try {
      if (editId) await clientsApi.update(editId, form);
      else await clientsApi.create(form);
      setShowModal(false); await loadData();
    } catch(e: any) { alert('Erreur: '+(e.message||'Inconnue')); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Supprimer ce client ?')) return;
    try { await clientsApi.delete(id); await loadData(); } catch(e) { console.error(e); }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true); setImportResult(null);
    try {
      const res = await clientsApi.importExcel(file);
      setImportResult(res); await loadData();
    } catch(err: any) { setImportResult({ ok:false, error: err.message }); }
    finally { setImporting(false); if(fileRef.current) fileRef.current.value=''; }
  };

  const villes = form.region ? (REGIONS[form.region]||[]) : Object.values(REGIONS).flat();

  if (isLoading) return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black gradient-text">🏢 Clients SAVIA</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des établissements clients</p>
        </div>
        <div className="flex gap-2">
          <input type="file" ref={fileRef} accept=".xlsx,.xls" className="hidden" onChange={handleImport} />
          <button onClick={() => fileRef.current?.click()} disabled={importing}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 border border-emerald-500/30 transition-all text-sm font-medium">
            {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            Importer Excel
          </button>
          <button onClick={openAdd}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-savia-accent/20 text-savia-accent hover:bg-savia-accent/30 border border-savia-accent/30 transition-all text-sm font-medium">
            <Plus className="w-4 h-4" /> Ajouter Client
          </button>
        </div>
      </div>

      {/* Import result banner */}
      {importResult && (
        <div className={`glass rounded-xl p-4 flex items-center gap-3 border ${importResult.ok ? 'border-emerald-500/30' : 'border-red-500/30'}`}>
          {importResult.ok ? <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0" /> : <X className="w-5 h-5 text-red-400 shrink-0" />}
          <div className="flex-1">
            {importResult.ok ? (
              <p className="text-sm"><span className="font-bold text-emerald-400">{importResult.imported}</span> clients importés,{' '}
                <span className="text-savia-text-muted">{importResult.skipped} ignorés</span> — Colonnes détectées:{' '}
                <span className="text-savia-accent">{importResult.columns_detected?.join(', ')}</span></p>
            ) : <p className="text-sm text-red-400">{importResult.error}</p>}
          </div>
          <button onClick={() => setImportResult(null)} className="text-savia-text-dim hover:text-white"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{data.length}</div><div className="text-xs text-savia-text-muted mt-1">Clients actifs</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-blue-400">{totalMachines}</div><div className="text-xs text-savia-text-muted mt-1">Machines gérées</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{totalInterv}</div><div className="text-xs text-savia-text-muted mt-1">Interventions totales</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-yellow-400">{avgHealth}%</div><div className="text-xs text-savia-text-muted mt-1">Santé moyenne</div></div>
      </div>

      {/* Search + Region filter */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input type="text" placeholder="Rechercher un client..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
        </div>
        <select value={regionFilter} onChange={e => setRegionFilter(e.target.value)}
          className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40">
          <option value="">Toutes régions</option>
          <option value="Nord">🔵 Nord</option>
          <option value="Centre">🟢 Centre</option>
          <option value="Sud">🟠 Sud</option>
        </select>
      </div>

      {/* Client cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map(c => (
          <div key={c.id||c.nom} className="glass rounded-xl p-5 hover:border-savia-accent/30 transition-all cursor-pointer group" onClick={() => openEdit(c)}>
            <div className="flex items-start gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-savia-accent/10 flex items-center justify-center shrink-0">
                {c.international ? <Globe className="w-5 h-5 text-blue-400" /> : <Building2 className="w-5 h-5 text-savia-accent" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-bold truncate">{c.nom}</h3>
                  {c.code_client && <span className="text-xs bg-savia-accent/10 text-savia-accent px-2 py-0.5 rounded-full font-mono">{c.code_client}</span>}
                </div>
                <p className="text-xs text-savia-text-muted">
                  {c.international ? '🌍 International' : <>📍 {c.ville || 'N/A'}{c.region ? ` — ${c.region}` : ''}</>}
                  {c.telephone ? ` — 📞 ${c.telephone}` : ''}
                </p>
              </div>
              <div className="flex gap-1.5 shrink-0">
                {c.type_client && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.type_client === 'Public' ? 'bg-blue-500/15 text-blue-400' : 'bg-purple-500/15 text-purple-400'}`}>
                    {c.type_client}
                  </span>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm mb-3">
              <div><span className="text-savia-text-dim">👤</span> {c.contact || 'N/A'}</div>
              <div><span className="text-savia-text-dim">📄</span> MF: {c.matricule_fiscale || 'N/A'}</div>
              <div><span className="text-savia-text-dim">🏥</span> {c.nb_equipements} machines</div>
              <div><span className="text-savia-text-dim">🔧</span> {c.nb_interventions} interv.</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-savia-text-dim">Santé parc:</span>
              <div className="flex-1 h-2 bg-savia-bg rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${c.score_sante >= 85 ? 'bg-green-500' : c.score_sante >= 65 ? 'bg-yellow-500' : 'bg-red-500'}`}
                  style={{ width: `${c.score_sante}%` }} />
              </div>
              <span className={`text-sm font-bold ${c.score_sante >= 85 ? 'text-green-400' : c.score_sante >= 65 ? 'text-yellow-400' : 'text-red-400'}`}>{c.score_sante}%</span>
            </div>
            <div className="flex justify-end mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button onClick={e => { e.stopPropagation(); handleDelete(c.id!); }}
                className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-500/10">Supprimer</button>
            </div>
          </div>
        ))}
      </div>
      {filtered.length === 0 && <p className="text-center text-savia-text-muted py-10">Aucun client trouvé</p>}

      {/* Add/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-savia-border">
              <h2 className="text-lg font-bold">{editId ? '✏️ Modifier Client' : '➕ Nouveau Client'}</h2>
              <button onClick={() => setShowModal(false)} className="text-savia-text-dim hover:text-white"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5 space-y-4">
              {/* Code client + Nom */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-savia-text-muted mb-1 block">Code client</label>
                  <input value={form.code_client} onChange={e => setForm({...form, code_client: e.target.value})} placeholder="CL-001"
                    className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
                </div>
                <div className="col-span-2">
                  <label className="text-xs text-savia-text-muted mb-1 block">Nom *</label>
                  <input value={form.nom} onChange={e => setForm({...form, nom: e.target.value})} placeholder="Nom de l'établissement" required
                    className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
                </div>
              </div>

              {/* Type client + International */}
              <div className="flex items-center gap-4 flex-wrap">
                <div className="flex-1 min-w-[140px]">
                  <label className="text-xs text-savia-text-muted mb-1 block">Type client</label>
                  <select value={form.type_client} onChange={e => setForm({...form, type_client: e.target.value})}
                    className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40">
                    <option value="Privé">🏢 Privé</option>
                    <option value="Public">🏛️ Public</option>
                  </select>
                </div>
                <label className="flex items-center gap-2 mt-4 cursor-pointer select-none">
                  <input type="checkbox" checked={form.international}
                    onChange={e => setForm({...form, international: e.target.checked, ...e.target.checked ? {region:'', ville:''} : {}})}
                    className="w-4 h-4 rounded border-savia-border bg-savia-bg text-savia-accent focus:ring-savia-accent/40" />
                  <Globe className="w-4 h-4 text-blue-400" />
                  <span className="text-sm">Client international</span>
                </label>
              </div>

              {/* Region + Ville (hidden if international) */}
              {!form.international && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-savia-text-muted mb-1 block">Région</label>
                    <select value={form.region} onChange={e => setForm({...form, region: e.target.value, ville: ''})}
                      className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40">
                      <option value="">— Sélectionner —</option>
                      <option value="Nord">🔵 Nord</option>
                      <option value="Centre">🟢 Centre</option>
                      <option value="Sud">🟠 Sud</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-savia-text-muted mb-1 block">Ville</label>
                    <select value={form.ville} onChange={e => setForm({...form, ville: e.target.value})}
                      className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40">
                      <option value="">— Sélectionner —</option>
                      {villes.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </div>
                </div>
              )}

              {/* Matricule fiscale */}
              <div>
                <label className="text-xs text-savia-text-muted mb-1 block">Matricule fiscale</label>
                <input value={form.matricule_fiscale} onChange={e => setForm({...form, matricule_fiscale: e.target.value})} placeholder="0000000/A/A/M/000"
                  className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
              </div>

              {/* Contact + Telephone */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-savia-text-muted mb-1 block">Contact</label>
                  <input value={form.contact} onChange={e => setForm({...form, contact: e.target.value})} placeholder="Nom du contact"
                    className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
                </div>
                <div>
                  <label className="text-xs text-savia-text-muted mb-1 block">Téléphone</label>
                  <input value={form.telephone} onChange={e => setForm({...form, telephone: e.target.value})} placeholder="+216 XX XXX XXX"
                    className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
                </div>
              </div>

              {/* Adresse */}
              <div>
                <label className="text-xs text-savia-text-muted mb-1 block">Adresse</label>
                <input value={form.adresse} onChange={e => setForm({...form, adresse: e.target.value})} placeholder="Adresse complète"
                  className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-sm text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
              </div>
            </div>
            <div className="flex justify-end gap-3 p-5 border-t border-savia-border">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 rounded-lg text-sm text-savia-text-muted hover:bg-savia-bg transition-colors">Annuler</button>
              <button onClick={handleSave} disabled={saving}
                className="px-6 py-2 rounded-lg text-sm font-medium bg-savia-accent text-white hover:bg-savia-accent/80 transition-colors disabled:opacity-50 flex items-center gap-2">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {editId ? 'Enregistrer' : 'Ajouter'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
