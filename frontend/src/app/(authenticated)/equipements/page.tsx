'use client';
// ==========================================
// PAGE PARC ÉQUIPEMENTS — SAVIA Next.js
// ==========================================
import { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
  Plus, Search, Edit2, Trash2, Loader2, Save, X, Server, Building2,
  FileText, Hash, Calendar, Settings, ClipboardList, StickyNote, Factory,
  Microscope, Activity, CheckCircle2, AlertTriangle, Upload, BadgeCheck,
  Download, FolderOpen, Scan, Package, Wind,
} from 'lucide-react';
import { equipements, documentsTechniques } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

interface Equipment {
  id: string;
  nom: string;
  type: string;
  domaine: string;
  estAnnexe: boolean;
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

// ======================= CATALOGUE DOMAINES & TYPES =======================

const DOMAINES = ['Radiologie', 'POC / Soins Intensifs', 'Laboratoire', 'Anesthésie / Bloc Op.'] as const;
type Domaine = typeof DOMAINES[number];

const DOMAINE_ICONS: Record<string, React.ReactNode> = {
  'Radiologie':             <Scan       className="w-4 h-4" />,
  'POC / Soins Intensifs':  <Activity   className="w-4 h-4" />,
  'Laboratoire':            <Microscope className="w-4 h-4" />,
  'Anesthésie / Bloc Op.':  <Wind       className="w-4 h-4" />,
};

const DOMAINE_COLORS: Record<string, string> = {
  'Radiologie':             'text-blue-400   bg-blue-500/10   border-blue-500/20',
  'POC / Soins Intensifs':  'text-orange-400 bg-orange-500/10 border-orange-500/20',
  'Laboratoire':            'text-purple-400 bg-purple-500/10 border-purple-500/20',
  'Anesthésie / Bloc Op.':  'text-teal-400   bg-teal-500/10   border-teal-500/20',
};

const DOMAINE_ACTIVE: Record<string, string> = {
  'Radiologie':             'bg-blue-500/20   border-blue-500/50   text-blue-200',
  'POC / Soins Intensifs':  'bg-orange-500/20 border-orange-500/50 text-orange-200',
  'Laboratoire':            'bg-purple-500/20 border-purple-500/50 text-purple-200',
  'Anesthésie / Bloc Op.':  'bg-teal-500/20   border-teal-500/50   text-teal-200',
};

const TYPES_PAR_DOMAINE: Record<string, string[]> = {
  'Radiologie': [
    'Scanner CT', 'IRM', 'Radiographie numérique', 'Mammographie',
    'Fluoroscopie', 'Angiographie', 'Radiographie conventionnelle',
    'CBCT (Cone Beam CT)', 'Ostéodensitométrie (DXA)', 'Amplificateur de brillance',
  ],
  'POC / Soins Intensifs': [
    'Moniteur patient', 'Défibrillateur', 'Ventilateur',
    'Pompe à infusion', 'Échographe portable', 'Analyseur gaz du sang (ABG)',
    'Électrocardiographe (ECG)', 'Oxymètre de pouls', 'Glucomètre', 'Tensiomètre',
  ],
  'Laboratoire': [
    "Automate d'hématologie", "Automate de biochimie", 'Centrifugeuse',
    'Microscope', "Automate d'immunologie", 'Spectrophotomètre',
    'PCR (thermocycleur)', 'Automate de coagulation', 'Chambre froide', 'Incubateur',
  ],
  'Anesthésie / Bloc Op.': [
    'Machine d\'anesthésie', 'Respirateur (bloc opératoire)',
    'Moniteur multiparamétrique (bloc)', 'Bistouri électrique (diathermie)',
    'Lampe scialytique', 'Table d\'opération',
    'Pousse-seringue électrique', 'Aspirateur chirurgical',
    'Réchauffeur de perfusion', 'Scope anesthésie (capnographe)',
  ],
};

/** Équipements annexes — uniquement pour le domaine Radiologie */
const TYPES_ANNEXES_RADIOLOGIE = [
  'Générateur haute tension (HT)', 'Capteur plan (FPD)',
  'Onduleur / Alimentation', 'Table télécommandée',
  'Bucky mural', 'Collimateur', 'Console opérateur',
  'Imprimante DICOM', 'Injecteur produit de contraste',
  'Tube radiogène', 'Détecteur CR (cassette numérique)',
];
// =========================================================================

function getStatutBadge(statut: string) {
  const s = statut.toLowerCase();
  if (s.includes('opérationnel') || s.includes('actif')) return 'bg-green-500/10 text-green-400 border-green-500/20';
  if (s.includes('maintenance')) return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
  if (s.includes('hors service') || s.includes('critique')) return 'bg-red-500/10 text-red-400 border-red-500/20';
  return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
}

export default function EquipementsPage() {
  const { user } = useAuth();
  const isLecteur = user?.role === 'Lecteur';
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
    Nom: '', Type: 'Scanner CT', Domaine: 'Radiologie' as string, EstAnnexe: false,
    Fabricant: '', Modele: '', NumSerie: '',
    Client: '', MatriculeFiscale: '', Notes: '', Statut: 'Opérationnel',
    DateInstallation: new Date().toISOString().split('T')[0],
    DernieresMaintenance: new Date().toISOString().split('T')[0],
  };
  const [form, setForm] = useState(emptyForm);

  // Types list based on domain + annexe state
  const availableTypes = useMemo(() => {
    if (form.Domaine === 'Radiologie' && form.EstAnnexe) return TYPES_ANNEXES_RADIOLOGIE;
    return TYPES_PAR_DOMAINE[form.Domaine] || TYPES_PAR_DOMAINE['Radiologie'];
  }, [form.Domaine, form.EstAnnexe]);

  const dynamicClients = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.client).filter(Boolean)))], [data]);
  const dynamicTypes = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.type).filter(Boolean)))], [data]);

  const matriculeClientMap = useMemo(() => {
    const map = new Map<string, string>();
    data.forEach(eq => {
      if (eq.matriculeFiscale && eq.client) map.set(eq.matriculeFiscale.trim().toLowerCase(), eq.client);
    });
    return map;
  }, [data]);

  // Reverse map: client name → matricule (for auto-fill when selecting client)
  const clientMatriculeMap = useMemo(() => {
    const map = new Map<string, string>();
    data.forEach(eq => {
      if (eq.client && eq.matriculeFiscale && !map.has(eq.client)) {
        map.set(eq.client, eq.matriculeFiscale);
      }
    });
    return map;
  }, [data]);

  const allMatricules = useMemo(() => Array.from(matriculeClientMap.keys()), [matriculeClientMap]);
  const allClientNames = useMemo(() => Array.from(clientMatriculeMap.keys()), [clientMatriculeMap]);

  const docEquipOptions = useMemo(() => ['Tous', ...Array.from(new Set(docs.map(d => d.equipement_nom).filter(Boolean)))], [docs]);
  const docClientOptions = useMemo(() => ['Tous', ...Array.from(new Set(docs.map(d => d.client).filter(Boolean)))], [docs]);

  const loadData = useCallback(async () => {
    try {
      const res = await equipements.list();
      const mapped = res.map((item: any) => ({
        id: String(item.id || item.Nom),
        nom: item.Nom || '',
        type: item.Type || '',
        domaine: item.domaine || item.Domaine || 'Radiologie',
        estAnnexe: item.est_annexe === true || item.est_annexe === 'true' || item.est_annexe === 1,
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
      Domaine: eq.domaine || 'Radiologie',
      EstAnnexe: eq.estAnnexe || false,
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
    setTimeout(() => { formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100);
  };

  const cancelForm = () => { setShowAddForm(false); setEditingEquip(null); setForm(emptyForm); setDocFiles([]); };

  const fileToBase64 = (file: File): Promise<string> => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(',')[1] || reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

  const handleSave = async () => {
    if (!form.Nom.trim() || !form.Client.trim()) return;
    setIsSaving(true);
    try {
      const payload: any = { ...form };
      if (docFiles.length > 0) payload.DocumentTechnique = docFiles.map(f => f.name).join(', ');

      let targetEquipId: number | null = null;
      if (editingEquip) {
        await equipements.update(Number(editingEquip.id), payload);
        targetEquipId = Number(editingEquip.id);
      } else {
        const result = await equipements.create(payload);
        targetEquipId = result.id;
      }

      if (targetEquipId && docFiles.length > 0) {
        for (const file of docFiles) {
          try {
            const base64Content = await fileToBase64(file);
            await documentsTechniques.upload(targetEquipId, file.name, base64Content);
          } catch (uploadErr) { console.error(`Failed to upload ${file.name}:`, uploadErr); }
        }
      }

      setForm(emptyForm); setDocFiles([]); setShowAddForm(false); setEditingEquip(null);
      await loadData();
    } catch (err) {
      console.error("Save failed", err);
    } finally {
      setIsSaving(false);
    }
  };

  const executeDelete = async (eq: Equipment) => {
    setConfirmDelete(null);
    try { await equipements.delete(Number(eq.id)); await loadData(); }
    catch (err) { console.error("Delete failed", err); }
  };

  const handleFileDrop = (e: React.DragEvent) => { e.preventDefault(); setDocFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)]); };

  const handleDownloadDoc = async (doc: DocTechnique) => {
    try {
      const result = await documentsTechniques.download(doc.id);
      const link = document.createElement('a');
      link.href = `data:application/octet-stream;base64,${result.contenu_base64}`;
      link.download = result.nom_fichier || doc.nom_fichier;
      link.click();
    } catch (err) { console.error("Download failed", err); }
  };

  const handleDeleteDoc = async (doc: DocTechnique) => {
    try { await documentsTechniques.delete(doc.id); await loadDocs(); }
    catch (err) { console.error("Delete doc failed", err); }
  };

  const filtered = useMemo(() => data.filter(eq => {
    if (filterType !== 'Tous' && eq.type !== filterType) return false;
    if (filterClient !== 'Tous' && eq.client !== filterClient) return false;
    if (search && !eq.nom.toLowerCase().includes(search.toLowerCase()) &&
        !eq.numSerie.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }), [search, filterType, filterClient, data]);

  const filteredDocs = useMemo(() => docs.filter(doc => {
    if (docFilterEquip !== 'Tous' && doc.equipement_nom !== docFilterEquip) return false;
    if (docFilterClient !== 'Tous' && doc.client !== docFilterClient) return false;
    if (docSearch && !doc.nom_fichier.toLowerCase().includes(docSearch.toLowerCase()) &&
        !doc.equipement_nom?.toLowerCase().includes(docSearch.toLowerCase())) return false;
    return true;
  }), [docs, docFilterEquip, docFilterClient, docSearch]);

  const totalEquip = data.length;
  const operationnel = data.filter(e => e.statut.toLowerCase().includes('actif') || e.statut.toLowerCase().includes('opérationnel')).length;
  const maintenance = totalEquip - operationnel;
  const avgHealth = totalEquip > 0 ? Math.round(data.reduce((a, b) => a + b.healthScore, 0) / totalEquip) : 0;

  if (isLoading) return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
          <Server className="w-7 h-7" /> Parc Équipements Médicaux
        </h1>
        <p className="text-savia-text-muted text-sm mt-1">Gestion multi-domaines : Radiologie · POC · Laboratoire · Anesthésie</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Équipements', value: totalEquip,      color: 'text-savia-accent', icon: <Server className="w-5 h-5" /> },
          { label: 'Opérationnels',     value: operationnel,    color: 'text-green-400',    icon: <CheckCircle2 className="w-5 h-5" /> },
          { label: 'En arrêt/Panne',   value: maintenance,     color: 'text-red-400',      icon: <AlertTriangle className="w-5 h-5" /> },
          { label: 'Santé Moy.',        value: `${avgHealth}%`, color: avgHealth >= 80 ? 'text-green-400' : 'text-yellow-400', icon: <Activity className="w-5 h-5" /> },
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
        <button onClick={() => setActiveTab('equipements')}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer ${activeTab === 'equipements' ? 'bg-gradient-to-r from-savia-accent to-savia-accent-blue text-white shadow-md' : 'text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover'}`}>
          <Server className="w-4 h-4" /> Équipements
        </button>
        {!isLecteur && (
          <button onClick={() => setActiveTab('documents')}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer ${activeTab === 'documents' ? 'bg-gradient-to-r from-savia-accent to-savia-accent-blue text-white shadow-md' : 'text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover'}`}>
            <FileText className="w-4 h-4" /> Documents Techniques
          </button>
        )}
      </div>

      {/* ========== TAB: ÉQUIPEMENTS ========== */}
      {activeTab === 'equipements' && (
        <>
          {/* Add/Edit Form */}
          {!isLecteur && (
            <div ref={formRef} className="glass rounded-xl overflow-hidden">
              <button
                onClick={() => { if (showAddForm) cancelForm(); else { setEditingEquip(null); setForm(emptyForm); setShowAddForm(true); } }}
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

                  {/* ── 1. Client ── */}
                  <div className="mt-4">
                    <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                      <BadgeCheck className="w-4 h-4 text-savia-accent" /> Identification du Client
                    </h3>
                    {/* Datalists for auto-complete */}
                    <datalist id="matricule-suggestions">
                      {allMatricules.map(m => <option key={m} value={m} />)}
                    </datalist>
                    <datalist id="client-suggestions">
                      {allClientNames.map(c => <option key={c} value={c} />)}
                    </datalist>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Hash className="w-3.5 h-3.5" /> Matricule Fiscale *
                        </label>
                        <div className="relative">
                          <input
                            list="matricule-suggestions"
                            className={INPUT_CLS}
                            placeholder="Ex: 1234567/A/P/M/000"
                            value={form.MatriculeFiscale}
                            onChange={e => {
                              const val = e.target.value;
                              const matched = matriculeClientMap.get(val.trim().toLowerCase());
                              setForm(matched ? { ...form, MatriculeFiscale: val, Client: matched } : { ...form, MatriculeFiscale: val });
                            }}
                          />
                          {form.MatriculeFiscale && matriculeClientMap.has(form.MatriculeFiscale.trim().toLowerCase()) && (
                            <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 text-green-400 pointer-events-none">
                              <CheckCircle2 className="w-4 h-4" /><span className="text-xs font-semibold">Client trouvé</span>
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Building2 className="w-3.5 h-3.5" /> Client / Site *
                          {form.MatriculeFiscale && matriculeClientMap.has(form.MatriculeFiscale.trim().toLowerCase()) && (
                            <span className="text-green-400 text-[10px] font-normal">(auto-rempli)</span>
                          )}
                        </label>
                        <input
                          list="client-suggestions"
                          className={INPUT_CLS}
                          placeholder="Ex: Clinique du Parc"
                          value={form.Client}
                          onChange={e => {
                            const val = e.target.value;
                            const mat = clientMatriculeMap.get(val);
                            setForm(mat ? { ...form, Client: val, MatriculeFiscale: mat } : { ...form, Client: val });
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* ── 2. Domaine & Type ── */}
                  <div>
                    <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
                      <Server className="w-4 h-4 text-savia-accent" /> Domaine & Classification
                    </h3>

                    {/* Domaine selector */}
                    <div className="mb-4">
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                        Domaine médical *
                      </label>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {DOMAINES.map(d => (
                          <button key={d} type="button"
                            onClick={() => setForm({ ...form, Domaine: d, EstAnnexe: false, Type: TYPES_PAR_DOMAINE[d][0] })}
                            className={`flex flex-col items-center gap-2 py-4 px-2 rounded-xl text-sm font-semibold transition-all cursor-pointer border ${
                              form.Domaine === d ? DOMAINE_ACTIVE[d] : 'bg-savia-bg/50 border-savia-border text-savia-text-muted hover:bg-savia-surface-hover'
                            }`}
                          >
                            <div className="scale-125">{DOMAINE_ICONS[d]}</div>
                            <span className="text-xs text-center leading-tight">
                              {d === 'POC / Soins Intensifs' ? (<><span className="hidden md:inline">POC / Soins</span><span className="md:hidden">POC</span></>) : d}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Annexe checkbox — uniquement Radiologie */}
                    {form.Domaine === 'Radiologie' && (
                      <div className="mb-4">
                        <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${
                          form.EstAnnexe
                            ? 'bg-amber-500/10 border-amber-500/40 text-amber-200'
                            : 'border-savia-border hover:border-savia-accent/30 text-savia-text-muted'
                        }`}>
                          <input
                            type="checkbox"
                            checked={form.EstAnnexe}
                            onChange={e => setForm({
                              ...form,
                              EstAnnexe: e.target.checked,
                              Type: e.target.checked ? TYPES_ANNEXES_RADIOLOGIE[0] : TYPES_PAR_DOMAINE['Radiologie'][0],
                            })}
                            className="w-4 h-4 mt-0.5 accent-amber-500 cursor-pointer flex-shrink-0"
                          />
                          <div>
                            <div className="flex items-center gap-2 font-semibold text-sm">
                              <Package className="w-4 h-4" /> Équipement annexe (vendu en complément de l&apos;équipement principal)
                            </div>
                            <p className="text-xs mt-1 opacity-70 leading-relaxed">
                              Ex : Générateur HT, Capteur plan (FPD), Tube radiogène, Bucky mural, Injecteur de contraste...
                            </p>
                          </div>
                        </label>
                      </div>
                    )}

                    {/* Type d'équipement (filtré par domaine + état annexe) */}
                    <div>
                      <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Microscope className="w-3.5 h-3.5" />
                        {form.EstAnnexe ? 'Type d\'équipement annexe *' : 'Type d\'équipement *'}
                      </label>
                      <select className={INPUT_CLS} value={form.Type} onChange={e => setForm({ ...form, Type: e.target.value })}>
                        {availableTypes.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                      {form.EstAnnexe && (
                        <p className="text-xs text-amber-400/70 mt-1.5 pl-1">
                          ⚠️ Pensez à indiquer l&apos;équipement principal dans les Notes ci-dessous.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* ── 3. Détails techniques ── */}
                  <div>
                    <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                      <ClipboardList className="w-4 h-4 text-savia-accent" /> Détails Techniques
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Server className="w-3.5 h-3.5" /> Nom de l&apos;équipement *
                        </label>
                        <input className={INPUT_CLS}
                          placeholder={form.EstAnnexe ? 'Ex: Générateur HT — Scanner Salle 3' : 'Ex: Scanner CT — Salle 3'}
                          value={form.Nom} onChange={e => setForm({ ...form, Nom: e.target.value })} />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Factory className="w-3.5 h-3.5" /> Fabricant
                        </label>
                        <input className={INPUT_CLS} placeholder="Ex: Siemens, GE, Philips..." value={form.Fabricant}
                          onChange={e => setForm({ ...form, Fabricant: e.target.value })} />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <ClipboardList className="w-3.5 h-3.5" /> Modèle
                        </label>
                        <input className={INPUT_CLS} placeholder="Ex: SOMATOM go.Up" value={form.Modele}
                          onChange={e => setForm({ ...form, Modele: e.target.value })} />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Hash className="w-3.5 h-3.5" /> N° de série
                        </label>
                        <input className={INPUT_CLS} placeholder="Ex: SN-2024-001" value={form.NumSerie}
                          onChange={e => setForm({ ...form, NumSerie: e.target.value })} />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Calendar className="w-3.5 h-3.5" /> Date d&apos;installation
                        </label>
                        <input type="date" className={INPUT_CLS} value={form.DateInstallation}
                          onChange={e => setForm({ ...form, DateInstallation: e.target.value })} />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Settings className="w-3.5 h-3.5" /> Dernière maintenance
                        </label>
                        <input type="date" className={INPUT_CLS} value={form.DernieresMaintenance}
                          onChange={e => setForm({ ...form, DernieresMaintenance: e.target.value })} />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Activity className="w-3.5 h-3.5" /> Statut
                        </label>
                        <select className={INPUT_CLS} value={form.Statut} onChange={e => setForm({ ...form, Statut: e.target.value })}>
                          {['Opérationnel', 'En maintenance', 'Hors Service', 'En attente'].map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </div>
                      <div className="md:col-span-2">
                        <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                          <StickyNote className="w-3.5 h-3.5" /> Notes
                        </label>
                        <textarea className={`${INPUT_CLS} resize-none`} rows={2}
                          placeholder={form.EstAnnexe ? "Indiquer l'équipement principal auquel cet équipement est rattaché, localisation..." : "Localisation, remarques..."}
                          value={form.Notes} onChange={e => setForm({ ...form, Notes: e.target.value })} />
                      </div>
                    </div>
                  </div>

                  {/* ── 4. Documents ── */}
                  <div>
                    <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-savia-accent" /> Documents techniques
                    </h3>
                    <div className="border-2 border-dashed border-savia-border rounded-xl p-6 text-center hover:border-savia-accent/40 transition-colors cursor-pointer"
                      onDragOver={e => e.preventDefault()} onDrop={handleFileDrop} onClick={() => fileInputRef.current?.click()}>
                      <input ref={fileInputRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xlsx" className="hidden"
                        onChange={e => { if (e.target.files) setDocFiles(prev => [...prev, ...Array.from(e.target.files!)]); }} />
                      <Upload className="w-8 h-8 mx-auto mb-2 text-savia-text-dim" />
                      {docFiles.length === 0 ? (
                        <>
                          <p className="text-sm text-savia-text-muted">Aucun fichier choisi — drag & drop ici</p>
                          <p className="text-xs text-savia-text-dim mt-1">PDF, PNG, JPG, DOC, XLSX · max 200MB</p>
                        </>
                      ) : (
                        <div className="space-y-1 text-sm text-savia-text">
                          {docFiles.map((f, i) => (
                            <div key={i} className="flex items-center justify-center gap-2">
                              <FileText className="w-3 h-3 text-savia-accent" /><span>{f.name}</span>
                              <button onClick={e => { e.stopPropagation(); setDocFiles(prev => prev.filter((_, idx) => idx !== i)); }}
                                className="text-red-400 hover:text-red-300 cursor-pointer"><X className="w-3 h-3" /></button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* ── Save/Cancel ── */}
                  <div className="flex justify-end gap-3 pt-4 border-t border-savia-border/50">
                    <button onClick={cancelForm}
                      className="px-4 py-2.5 rounded-lg text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-colors cursor-pointer">
                      Annuler
                    </button>
                    <button onClick={handleSave} disabled={isSaving || !form.Nom.trim() || !form.Client.trim()}
                      className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
                      {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                      {editingEquip ? 'Mettre à jour' : 'Sauvegarder'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
              <input type="text" placeholder="Rechercher par nom ou N° série..." value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
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
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      <h3 className="font-bold text-lg leading-tight">{eq.nom}</h3>
                      {eq.estAnnexe && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30 flex items-center gap-1 flex-shrink-0">
                          <Package className="w-2.5 h-2.5" /> Annexe
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border flex items-center gap-1 ${DOMAINE_COLORS[eq.domaine] || 'text-gray-400 bg-gray-500/10 border-gray-500/20'}`}>
                        {DOMAINE_ICONS[eq.domaine]}{eq.domaine}
                      </span>
                      <p className="text-savia-text-muted text-sm">{eq.marque} — {eq.modele}</p>
                    </div>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-xs font-bold border ml-2 flex-shrink-0 ${getStatutBadge(eq.statut)}`}>{eq.statut}</span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                  <div className="flex items-center gap-2"><Building2 className="w-3.5 h-3.5 text-savia-text-dim" /> {eq.client}</div>
                  <div className="flex items-center gap-2"><StickyNote className="w-3.5 h-3.5 text-savia-text-dim" /> {eq.localisation || 'N/A'}</div>
                  <div className="flex items-center gap-2"><Hash className="w-3.5 h-3.5 text-savia-text-dim" /> <code className="text-xs">{eq.numSerie || 'N/A'}</code></div>
                  <div className="flex items-center gap-2"><Calendar className="w-3.5 h-3.5 text-savia-text-dim" /> {eq.derniereMaintenance}</div>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-savia-text-dim">Santé:</span>
                    <div className="w-24 h-2 bg-savia-bg rounded-full overflow-hidden">
                      <div className={`h-full rounded-full transition-all ${eq.healthScore >= 85 ? 'bg-green-500' : eq.healthScore >= 65 ? 'bg-yellow-500' : 'bg-red-500'}`}
                        style={{ width: `${eq.healthScore}%` }} />
                    </div>
                    <span className={`text-sm font-bold ${eq.healthScore >= 85 ? 'text-green-400' : eq.healthScore >= 65 ? 'text-yellow-400' : 'text-red-400'}`}>{eq.healthScore}%</span>
                  </div>
                  <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    {!isLecteur && (
                      <>
                        <button onClick={() => startEdit(eq)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer"><Edit2 className="w-3.5 h-3.5" /></button>
                        <button onClick={() => setConfirmDelete(eq)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
                      </>
                    )}
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
              <input type="text" placeholder="Rechercher un document..." value={docSearch} onChange={e => setDocSearch(e.target.value)}
                className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
            </div>
            <select value={docFilterEquip} onChange={e => setDocFilterEquip(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {docEquipOptions.map(e => <option key={e} value={e}>{e === 'Tous' ? '🔧 Tous les équipements' : e}</option>)}
            </select>
            <select value={docFilterClient} onChange={e => setDocFilterClient(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {docClientOptions.map(c => <option key={c} value={c}>{c === 'Tous' ? '🏢 Tous les clients' : c}</option>)}
            </select>
          </div>

          <div className="glass rounded-xl overflow-hidden">
            {docsLoading ? (
              <div className="flex justify-center items-center h-32"><Loader2 className="w-6 h-6 animate-spin text-savia-accent" /></div>
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
                      {['Document', 'Équipement', 'Client', 'Type', 'Date', 'Actions'].map((h, i) => (
                        <th key={h} className={`px-4 py-3 font-semibold text-savia-text-muted ${i === 5 ? 'text-right' : 'text-left'}`}>{h}</th>
                      ))}
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
                          <span className="px-2 py-0.5 rounded-full text-xs bg-savia-accent/10 text-savia-accent border border-savia-accent/20">{doc.equipement_type}</span>
                        </td>
                        <td className="px-4 py-3 text-savia-text-dim text-xs">
                          {doc.date_ajout ? new Date(doc.date_ajout).toLocaleDateString('fr-FR') : 'N/A'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <button onClick={() => handleDownloadDoc(doc)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer" title="Télécharger">
                              <Download className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => handleDeleteDoc(doc)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer" title="Supprimer">
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-savia-surface border border-savia-border rounded-2xl p-6 w-full max-w-sm shadow-2xl">
            <h3 className="text-lg font-bold mb-2 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400" /> Confirmer la suppression
            </h3>
            <p className="text-savia-text-muted text-sm mb-4">
              Voulez-vous supprimer <strong className="text-savia-text">{confirmDelete.nom}</strong> ? Cette action est irréversible.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmDelete(null)}
                className="px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">Annuler</button>
              <button onClick={() => executeDelete(confirmDelete)}
                className="px-4 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 font-semibold cursor-pointer transition-colors">Supprimer</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
