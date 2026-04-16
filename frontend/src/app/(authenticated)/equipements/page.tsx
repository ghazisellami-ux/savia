'use client';
// ==========================================
// PAGE PARC ÉQUIPEMENTS — SAVIA Next.js
// ==========================================
import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { SectionCard } from '@/components/ui/cards';
import {
  Plus, Search, Edit2, Trash2, Loader2, Save, X, Server, Building2,
  FileText, Hash, Calendar, Settings, ClipboardList, StickyNote, Factory,
  Microscope, Activity, CheckCircle2, AlertTriangle, Upload, BadgeCheck,
  Download, Filter, FolderOpen
} from 'lucide-react';
import { equipements, documentsTechniques } from '@/lib/api';

interface Equipment {
  id: string;
  nom: string;
  type: string;
  marque: string;
  modele: string;
  numSerie: string;
  client: string;
  matriculeFiscale: string;
  localisation: string;
  dateInstallation: string;
  derniereMaintenance: string;
  prochaineMaintenance: string;
  healthScore: number;
  statut: string;
  documentTechnique: string;
}

interface DocTechnique {
  id: number;
  nom_fichier: string;
  date_ajout: string;
  equipement_id: number;
  equipement_nom: string;
  fabricant: string;
  modele: string;
  equipement_type: string;
  client: string;
}

const INPUT_CLS = "w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 focus:border-savia-accent/40 outline-none transition-all";

function getStatutBadge(statut: string) {
  const s = statut.toLowerCase();
  if (s.includes('opérationnel') || s.includes('actif')) return 'bg-green-500/10 text-green-400 border-green-500/20';
  if (s.includes('maintenance')) return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
  if (s.includes('hors service') || s.includes('critique')) return 'bg-red-500/10 text-red-400 border-red-500/20';
  return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
}

export default function EquipementsPage() {
  const [activeTab, setActiveTab] = useState<'equipements' | 'documents'>('equipements');
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('Tous');
  const [filterClient, setFilterClient] = useState('Tous');
  const [showAddForm, setShowAddForm] = useState(false);
  const [data, setData] = useState<Equipment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [docFiles, setDocFiles] = useState<File[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<Equipment | null>(null);
  const [editingEquip, setEditingEquip] = useState<Equipment | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLDivElement>(null);

  // Documents state
  const [docs, setDocs] = useState<DocTechnique[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docFilterEquip, setDocFilterEquip] = useState('Tous');
  const [docFilterClient, setDocFilterClient] = useState('Tous');
  const [docSearch, setDocSearch] = useState('');

  // Form state
  const emptyForm = {
    Nom: '', Type: 'Scanner CT', Fabricant: '', Modele: '', NumSerie: '',
    Client: '', MatriculeFiscale: '', Notes: '', Statut: 'Opérationnel',
    DateInstallation: new Date().toISOString().split('T')[0],
    DernieresMaintenance: new Date().toISOString().split('T')[0],
  };
  const [form, setForm] = useState(emptyForm);

  const dynamicClients = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.client).filter(Boolean)))], [data]);
  const dynamicTypes = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.type).filter(Boolean)))], [data]);

  // Lookup: matricule fiscale -> client name (for auto-fill)
  const matriculeClientMap = useMemo(() => {
    const map = new Map<string, string>();
    data.forEach(eq => {
      if (eq.matriculeFiscale && eq.client) {
        map.set(eq.matriculeFiscale.trim().toLowerCase(), eq.client);
      }
    });
    return map;
  }, [data]);

  // Documents filter options (derived from docs data)
  const docEquipOptions = useMemo(() => ['Tous', ...Array.from(new Set(docs.map(d => d.equipement_nom).filter(Boolean)))], [docs]);
  const docClientOptions = useMemo(() => ['Tous', ...Array.from(new Set(docs.map(d => d.client).filter(Boolean)))], [docs]);

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
        matriculeFiscale: item.MatriculeFiscale || '',
        localisation: item.Notes || '',
        dateInstallation: item.DateInstallation || 'N/A',
        derniereMaintenance: item.DernieresMaintenance || 'N/A',
        prochaineMaintenance: 'N/A',
        healthScore: item.Score_Sante || (item.Statut && (item.Statut === 'Actif' || item.Statut === 'Opérationnel') ? 95 : 50),
        statut: item.Statut || 'Actif',
        documentTechnique: item.DocumentTechnique || '',
      }));
      setData(mapped);
    } catch (err) {
      console.error("Failed to fetch equipements", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadDocs = useCallback(async () => {
    setDocsLoading(true);
    try {
      const res = await documentsTechniques.listAll();
      setDocs(res as unknown as DocTechnique[]);
    } catch (err) {
      console.error("Failed to fetch documents", err);
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => { if (activeTab === 'documents') loadDocs(); }, [activeTab, loadDocs]);

  const startEdit = (eq: Equipment) => {
    setEditingEquip(eq);
    setForm({
      Nom: eq.nom,
      Type: eq.type || 'Scanner CT',
      Fabricant: eq.marque,
      Modele: eq.modele,
      NumSerie: eq.numSerie,
      Client: eq.client,
      MatriculeFiscale: eq.matriculeFiscale || '',
      Notes: eq.localisation,
      Statut: eq.statut || 'Opérationnel',
      DateInstallation: eq.dateInstallation !== 'N/A' ? eq.dateInstallation : new Date().toISOString().split('T')[0],
      DernieresMaintenance: eq.derniereMaintenance !== 'N/A' ? eq.derniereMaintenance : new Date().toISOString().split('T')[0],
    });
    setShowAddForm(true);
    // Scroll to form after state update
    setTimeout(() => {
      formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  const cancelForm = () => {
    setShowAddForm(false);
    setEditingEquip(null);
    setForm(emptyForm);
    setDocFiles([]);
  };

  // Helper: convert File to base64 string
  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // Remove the "data:...;base64," prefix
        const base64 = result.split(',')[1] || result;
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const handleSave = async () => {
    if (!form.Nom.trim() || !form.Client.trim()) return;
    setIsSaving(true);
    try {
      const payload = { ...form };
      if (docFiles.length > 0) {
        (payload as any).DocumentTechnique = docFiles.map(f => f.name).join(', ');
      }

      let targetEquipId: number | null = null;

      if (editingEquip) {
        await equipements.update(Number(editingEquip.id), payload);
        targetEquipId = Number(editingEquip.id);
      } else {
        const result = await equipements.create(payload);
        targetEquipId = result.id;
      }

      // Upload each document file to the backend
      if (targetEquipId && docFiles.length > 0) {
        for (const file of docFiles) {
          try {
            const base64Content = await fileToBase64(file);
            await documentsTechniques.upload(targetEquipId, file.name, base64Content);
          } catch (uploadErr) {
            console.error(`Failed to upload ${file.name}:`, uploadErr);
          }
        }
      }

      setForm(emptyForm);
      setDocFiles([]);
      setShowAddForm(false);
      setEditingEquip(null);
      await loadData();
    } catch (err) {
      console.error("Save failed", err);
    } finally {
      setIsSaving(false);
    }
  };

  const executeDelete = async (eq: Equipment) => {
    setConfirmDelete(null);
    try {
      await equipements.delete(Number(eq.id));
      await loadData();
    } catch (err) {
      console.error("Delete failed", err);
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    setDocFiles(prev => [...prev, ...files]);
  };

  const handleDownloadDoc = async (doc: DocTechnique) => {
    try {
      const result = await documentsTechniques.download(doc.id);
      // Create download link from base64
      const link = document.createElement('a');
      link.href = `data:application/octet-stream;base64,${result.contenu_base64}`;
      link.download = result.nom_fichier || doc.nom_fichier;
      link.click();
    } catch (err) {
      console.error("Download failed", err);
    }
  };

  const handleDeleteDoc = async (doc: DocTechnique) => {
    try {
      await documentsTechniques.delete(doc.id);
      await loadDocs();
    } catch (err) {
      console.error("Delete doc failed", err);
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

  const filteredDocs = useMemo(() => {
    return docs.filter(doc => {
      if (docFilterEquip !== 'Tous' && doc.equipement_nom !== docFilterEquip) return false;
      if (docFilterClient !== 'Tous' && doc.client !== docFilterClient) return false;
      if (docSearch && !doc.nom_fichier.toLowerCase().includes(docSearch.toLowerCase()) &&
          !doc.equipement_nom?.toLowerCase().includes(docSearch.toLowerCase())) return false;
      return true;
    });
  }, [docs, docFilterEquip, docFilterClient, docSearch]);

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
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
          <Server className="w-7 h-7" /> Parc Équipements — Radiologie
        </h1>
        <p className="text-savia-text-muted text-sm mt-1">Gestion du parc d&apos;équipements de radiologie</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Équipements', value: totalEquip, color: 'text-savia-accent', icon: <Server className="w-5 h-5" /> },
          { label: 'Opérationnels', value: operationnel, color: 'text-green-400', icon: <CheckCircle2 className="w-5 h-5" /> },
          { label: 'En arrêt/Panne', value: maintenance, color: 'text-red-400', icon: <AlertTriangle className="w-5 h-5" /> },
          { label: 'Santé Moy.', value: `${avgHealth}%`, color: avgHealth >= 80 ? 'text-green-400' : 'text-yellow-400', icon: <Activity className="w-5 h-5" /> },
        ].map(kpi => (
          <div key={kpi.label} className="glass rounded-xl p-4 text-center">
            <div className={`flex justify-center mb-2 ${kpi.color}`}>{kpi.icon}</div>
            <div className={`text-3xl font-black ${kpi.color}`}>{kpi.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 glass rounded-xl p-1">
        <button
          onClick={() => setActiveTab('equipements')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer ${
            activeTab === 'equipements'
              ? 'bg-gradient-to-r from-savia-accent to-savia-accent-blue text-white shadow-md'
              : 'text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover'
          }`}
        >
          <Server className="w-4 h-4" /> Équipements
        </button>
        <button
          onClick={() => setActiveTab('documents')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer ${
            activeTab === 'documents'
              ? 'bg-gradient-to-r from-savia-accent to-savia-accent-blue text-white shadow-md'
              : 'text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover'
          }`}
        >
          <FileText className="w-4 h-4" /> Documents Techniques
        </button>
      </div>

      {/* ========== TAB: ÉQUIPEMENTS ========== */}
      {activeTab === 'equipements' && (
        <>
          {/* Add/Edit Equipment Form (Collapsible) */}
          <div ref={formRef} className="glass rounded-xl overflow-hidden">
            <button
              onClick={() => { if (showAddForm) { cancelForm(); } else { setEditingEquip(null); setForm(emptyForm); setShowAddForm(true); } }}
              className="w-full flex items-center justify-between p-4 hover:bg-savia-surface-hover/30 transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-3">
                {editingEquip ? <Edit2 className="w-5 h-5 text-blue-400" /> : <Plus className="w-5 h-5 text-savia-accent" />}
                <span className="font-semibold">{editingEquip ? `Modifier — ${editingEquip.nom}` : 'Ajouter un nouvel équipement'}</span>
              </div>
              {showAddForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            </button>

            {showAddForm && (
              <div className="p-5 pt-0 border-t border-savia-border/50 space-y-6">
                {/* Client Identification */}
                <div className="mt-4">
                  <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                    <BadgeCheck className="w-4 h-4 text-savia-accent" /> Identification du Client
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Hash className="w-3.5 h-3.5" /> Matricule Fiscale du client *
                      </label>
                      <div className="relative">
                        <input
                          className={INPUT_CLS}
                          placeholder="Ex: 1234567/A/P/M/000"
                          value={form.MatriculeFiscale}
                          onChange={e => {
                            const val = e.target.value;
                            const matched = matriculeClientMap.get(val.trim().toLowerCase());
                            if (matched) {
                              setForm({...form, MatriculeFiscale: val, Client: matched});
                            } else {
                              setForm({...form, MatriculeFiscale: val});
                            }
                          }}
                        />
                        {form.MatriculeFiscale && matriculeClientMap.has(form.MatriculeFiscale.trim().toLowerCase()) && (
                          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 text-green-400">
                            <CheckCircle2 className="w-4 h-4" />
                            <span className="text-xs font-semibold">Client trouvé</span>
                          </div>
                        )}
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Building2 className="w-3.5 h-3.5" /> Client / Site *
                        {form.MatriculeFiscale && matriculeClientMap.has(form.MatriculeFiscale.trim().toLowerCase()) && (
                          <span className="text-green-400 text-[10px] font-normal ml-1">(auto-rempli)</span>
                        )}
                      </label>
                      <input
                        className={INPUT_CLS}
                        placeholder="Ex: Clinique du Parc"
                        value={form.Client}
                        onChange={e => setForm({...form, Client: e.target.value})}
                      />
                    </div>
                  </div>
                </div>

                {/* Equipment Details */}
                <div>
                  <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                    <Server className="w-4 h-4 text-savia-accent" /> Détails de l&apos;Équipement
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Server className="w-3.5 h-3.5" /> Nom de l&apos;équipement *
                      </label>
                      <input
                        className={INPUT_CLS}
                        placeholder="Ex: Scanner CT - Salle 3"
                        value={form.Nom}
                        onChange={e => setForm({...form, Nom: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Microscope className="w-3.5 h-3.5" /> Type d&apos;équipement *
                      </label>
                      <select className={INPUT_CLS} value={form.Type} onChange={e => setForm({...form, Type: e.target.value})}>
                        {['Scanner CT', 'IRM', 'Radiographie', 'Mammographie', 'Échographie', 'Fluoroscopie', 'Angiographie'].map(t => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Factory className="w-3.5 h-3.5" /> Fabricant
                      </label>
                      <input
                        className={INPUT_CLS}
                        placeholder="Ex: Siemens, GE, Philips..."
                        value={form.Fabricant}
                        onChange={e => setForm({...form, Fabricant: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <ClipboardList className="w-3.5 h-3.5" /> Modèle
                      </label>
                      <input
                        className={INPUT_CLS}
                        placeholder="Ex: SOMATOM go.Up"
                        value={form.Modele}
                        onChange={e => setForm({...form, Modele: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Hash className="w-3.5 h-3.5" /> N° de série
                      </label>
                      <input
                        className={INPUT_CLS}
                        placeholder="Ex: SN-2024-001"
                        value={form.NumSerie}
                        onChange={e => setForm({...form, NumSerie: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Calendar className="w-3.5 h-3.5" /> Date d&apos;installation
                      </label>
                      <input
                        type="date"
                        className={INPUT_CLS}
                        value={form.DateInstallation}
                        onChange={e => setForm({...form, DateInstallation: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Settings className="w-3.5 h-3.5" /> Dernière maintenance
                      </label>
                      <input
                        type="date"
                        className={INPUT_CLS}
                        value={form.DernieresMaintenance}
                        onChange={e => setForm({...form, DernieresMaintenance: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Activity className="w-3.5 h-3.5" /> Statut
                      </label>
                      <select className={INPUT_CLS} value={form.Statut} onChange={e => setForm({...form, Statut: e.target.value})}>
                        {['Opérationnel', 'En maintenance', 'Hors Service', 'En attente'].map(s => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <StickyNote className="w-3.5 h-3.5" /> Notes
                      </label>
                      <textarea
                        className={`${INPUT_CLS} resize-none`}
                        rows={2}
                        placeholder="Informations complémentaires..."
                        value={form.Notes}
                        onChange={e => setForm({...form, Notes: e.target.value})}
                      />
                    </div>
                  </div>
                </div>

                {/* Document Upload */}
                <div>
                  <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-savia-accent" /> Documents techniques (PDF, manuels, schémas...)
                  </h3>
                  <div
                    className="border-2 border-dashed border-savia-border rounded-xl p-6 text-center hover:border-savia-accent/40 transition-colors cursor-pointer"
                    onDragOver={e => e.preventDefault()}
                    onDrop={handleFileDrop}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xlsx"
                      className="hidden"
                      onChange={e => {
                        if (e.target.files) setDocFiles(prev => [...prev, ...Array.from(e.target.files!)]);
                      }}
                    />
                    <Upload className="w-8 h-8 mx-auto mb-2 text-savia-text-dim" />
                    {docFiles.length === 0 ? (
                      <>
                        <p className="text-sm text-savia-text-muted">Aucun fichier choisi</p>
                        <p className="text-xs text-savia-text-dim mt-1">Drag and drop files here</p>
                        <p className="text-xs text-savia-text-dim">Limit 200MB per file • PDF, PNG, JPG, JPEG, DOC, DOCX, XLSX</p>
                      </>
                    ) : (
                      <div className="space-y-1 text-sm text-savia-text">
                        {docFiles.map((f, i) => (
                          <div key={i} className="flex items-center justify-center gap-2">
                            <FileText className="w-3 h-3 text-savia-accent" />
                            <span>{f.name}</span>
                            <button onClick={(e) => { e.stopPropagation(); setDocFiles(prev => prev.filter((_, idx) => idx !== i)); }}
                              className="text-red-400 hover:text-red-300 cursor-pointer">
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Save / Cancel buttons */}
                <div className="flex justify-end gap-3 pt-4 border-t border-savia-border/50">
                  <button
                    onClick={cancelForm}
                    className="px-4 py-2.5 rounded-lg text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-colors cursor-pointer"
                  >
                    Annuler
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={isSaving || !form.Nom.trim() || !form.Client.trim()}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer"
                  >
                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    {editingEquip ? 'Mettre à jour' : 'Sauvegarder'}
                  </button>
                </div>
              </div>
            )}
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
              {dynamicTypes.map(t => <option key={t} value={t}>{t === 'Tous' ? 'Tous les types' : t}</option>)}
            </select>
            <select value={filterClient} onChange={e => setFilterClient(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {dynamicClients.map(c => <option key={c} value={c}>{c === 'Tous' ? 'Tous les clients' : c}</option>)}
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
                  <div className="flex items-center gap-2">
                    <Building2 className="w-3.5 h-3.5 text-savia-text-dim" /> {eq.client}
                  </div>
                  <div className="flex items-center gap-2">
                    <StickyNote className="w-3.5 h-3.5 text-savia-text-dim" /> {eq.localisation || 'N/A'}
                  </div>
                  <div className="flex items-center gap-2">
                    <Hash className="w-3.5 h-3.5 text-savia-text-dim" /> <code className="text-xs">{eq.numSerie || 'N/A'}</code>
                  </div>
                  <div className="flex items-center gap-2">
                    <Calendar className="w-3.5 h-3.5 text-savia-text-dim" /> Maint: {eq.derniereMaintenance}
                  </div>
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
                    <button onClick={() => startEdit(eq)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer"><Edit2 className="w-3.5 h-3.5" /></button>
                    <button onClick={() => setConfirmDelete(eq)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {filtered.length === 0 && (
            <div className="glass rounded-xl p-8 text-center">
              <Server className="w-10 h-10 mx-auto mb-3 text-savia-text-dim" />
              <p className="text-savia-text-muted">Aucun équipement trouvé pour ces filtres.</p>
            </div>
          )}
        </>
      )}

      {/* ========== TAB: DOCUMENTS TECHNIQUES ========== */}
      {activeTab === 'documents' && (
        <>
          {/* Documents Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
              <input
                type="text"
                placeholder="Rechercher un document..."
                value={docSearch}
                onChange={e => setDocSearch(e.target.value)}
                className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim"
              />
            </div>
            <select value={docFilterEquip} onChange={e => setDocFilterEquip(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {docEquipOptions.map(e => <option key={e} value={e}>{e === 'Tous' ? '🔧 Tous les équipements' : e}</option>)}
            </select>
            <select value={docFilterClient} onChange={e => setDocFilterClient(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {docClientOptions.map(c => <option key={c} value={c}>{c === 'Tous' ? '🏢 Tous les clients' : c}</option>)}
            </select>
          </div>

          {/* Documents Table */}
          <div className="glass rounded-xl overflow-hidden">
            {docsLoading ? (
              <div className="flex justify-center items-center h-32">
                <Loader2 className="w-6 h-6 animate-spin text-savia-accent" />
              </div>
            ) : filteredDocs.length === 0 ? (
              <div className="p-8 text-center">
                <FolderOpen className="w-10 h-10 mx-auto mb-3 text-savia-text-dim" />
                <p className="text-savia-text-muted">Aucun document technique trouvé.</p>
                <p className="text-xs text-savia-text-dim mt-1">Les documents sont ajoutés via le formulaire d&apos;équipement.</p>
              </div>
            ) : (
              <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-10">
                    <tr className="bg-savia-surface-hover/50">
                      <th className="text-left px-4 py-3 font-semibold text-savia-text-muted">
                        <div className="flex items-center gap-2"><FileText className="w-3.5 h-3.5" /> Document</div>
                      </th>
                      <th className="text-left px-4 py-3 font-semibold text-savia-text-muted">
                        <div className="flex items-center gap-2"><Server className="w-3.5 h-3.5" /> Équipement</div>
                      </th>
                      <th className="text-left px-4 py-3 font-semibold text-savia-text-muted">
                        <div className="flex items-center gap-2"><Building2 className="w-3.5 h-3.5" /> Client</div>
                      </th>
                      <th className="text-left px-4 py-3 font-semibold text-savia-text-muted">
                        <div className="flex items-center gap-2"><Microscope className="w-3.5 h-3.5" /> Type</div>
                      </th>
                      <th className="text-left px-4 py-3 font-semibold text-savia-text-muted">
                        <div className="flex items-center gap-2"><Calendar className="w-3.5 h-3.5" /> Date</div>
                      </th>
                      <th className="text-right px-4 py-3 font-semibold text-savia-text-muted">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-savia-border/30">
                    {filteredDocs.map(doc => (
                      <tr key={doc.id} className="hover:bg-savia-surface-hover/30 transition-colors">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-savia-accent flex-shrink-0" />
                            <span className="font-medium truncate max-w-[200px]">{doc.nom_fichier}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-savia-text">{doc.equipement_nom}</span>
                          {doc.fabricant && <span className="text-savia-text-dim text-xs ml-1">({doc.fabricant})</span>}
                        </td>
                        <td className="px-4 py-3 text-savia-text-muted">{doc.client}</td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded-full text-xs bg-savia-accent/10 text-savia-accent border border-savia-accent/20">
                            {doc.equipement_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-savia-text-dim text-xs">
                          {doc.date_ajout ? new Date(doc.date_ajout).toLocaleDateString('fr-FR') : 'N/A'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleDownloadDoc(doc)}
                              className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors cursor-pointer"
                              title="Télécharger"
                            >
                              <Download className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleDeleteDoc(doc)}
                              className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer"
                              title="Supprimer"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!docsLoading && filteredDocs.length > 0 && (
              <div className="px-4 py-2 border-t border-savia-border/30 text-xs text-savia-text-dim text-right">
                {filteredDocs.length} document{filteredDocs.length > 1 ? 's' : ''} trouvé{filteredDocs.length > 1 ? 's' : ''}
              </div>
            )}
          </div>
        </>
      )}

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-savia-surface border border-savia-border rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-full bg-red-500/10">
                <Trash2 className="w-6 h-6 text-red-400" />
              </div>
              <h3 className="text-lg font-bold text-savia-text">Supprimer l&apos;équipement</h3>
            </div>
            <p className="text-savia-text-muted text-sm mb-2">
              Voulez-vous supprimer définitivement :
            </p>
            <p className="text-savia-text font-bold text-base mb-4 bg-savia-bg rounded-lg px-3 py-2">
              <Server className="w-4 h-4 inline mr-2 -mt-0.5 text-savia-accent" />
              {confirmDelete.nom}
            </p>
            <p className="text-red-400/80 text-xs mb-6 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> Cette action est irréversible.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="flex-1 py-2.5 rounded-lg font-semibold text-savia-text bg-savia-bg border border-savia-border hover:bg-savia-surface-hover transition-all cursor-pointer"
              >
                Annuler
              </button>
              <button
                onClick={() => executeDelete(confirmDelete)}
                className="flex-1 py-2.5 rounded-lg font-semibold text-white bg-red-600 hover:bg-red-500 transition-all cursor-pointer flex items-center justify-center gap-2"
              >
                <Trash2 className="w-4 h-4" /> Supprimer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
