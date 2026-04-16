'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import { Plus, Search, Package, AlertTriangle, Loader2, Save, Trash2, Edit, Sparkles,
  Filter, Wrench, Building2, TrendingDown, DollarSign, ShoppingCart, Clock,
  CheckCircle2, XCircle, History, Brain, BarChart3, Boxes, Factory, StickyNote } from 'lucide-react';
import { pieces, interventions, ai } from '@/lib/api';

interface Piece {
  id: number;
  reference: string;
  designation: string;
  equipement_type: string;
  stock_actuel: number;
  stock_minimum: number;
  prix_unitaire: number;
  fournisseur: string;
  notes: string;
}

const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";
const TAB_CLS = "px-4 py-2.5 text-sm font-semibold rounded-t-lg transition-all cursor-pointer border-b-2";
const TAB_ACTIVE = "border-cyan-400 text-cyan-400 bg-cyan-400/5";
const TAB_INACTIVE = "border-transparent text-savia-text-muted hover:text-savia-text hover:border-slate-500";
const TYPES_EQUIPEMENTS = ["Scanner CT", "IRM", "Radiographie", "Mammographie", "Échographie", "Fluoroscopie", "Angiographie", "Autre"];

export default function PiecesPage() {
  const [activeTab, setActiveTab] = useState(0);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('Tous');
  const [data, setData] = useState<Piece[]>([]);
  const [interventionData, setInterventionData] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedPiece, setSelectedPiece] = useState<Piece | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState<string>('');
  const [aiSelectedPiece, setAiSelectedPiece] = useState<string>('all');

  const emptyForm = { reference: '', designation: '', equipement_type: 'Scanner CT', stock_actuel: '1', stock_minimum: '1', prix_unitaire: '0', fournisseur: '', notes: '' };
  const [form, setForm] = useState(emptyForm);

  const loadData = useCallback(async () => {
    try {
      const [piecesRes, intervRes] = await Promise.all([pieces.list(), interventions.list()]);
      const mapped = piecesRes.map((item: any) => ({
        id: item.id || 0,
        reference: item.reference || item.Reference || '',
        designation: item.designation || item.Nom || '',
        equipement_type: item.equipement_type || item.Compatibilite || '',
        stock_actuel: Number(item.stock_actuel || item.Stock_Actuel || 0),
        stock_minimum: Number(item.stock_minimum || item.Seuil_Critique || 1),
        prix_unitaire: Number(item.prix_unitaire || item.Cout_Unitaire || 0),
        fournisseur: item.fournisseur || item.Fournisseur || '',
        notes: item.notes || '',
      }));
      setData(mapped);
      setInterventionData(intervRes);
    } catch (err) {
      console.error("Failed to fetch pieces", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSave = async () => {
    if (!form.designation.trim()) return;
    setIsSaving(true);
    try {
      await pieces.create({
        reference: form.reference.trim().toUpperCase(),
        designation: form.designation.trim(),
        equipement_type: form.equipement_type,
        stock_actuel: Number(form.stock_actuel),
        stock_minimum: Number(form.stock_minimum),
        prix_unitaire: Number(form.prix_unitaire),
        fournisseur: form.fournisseur.trim(),
        notes: form.notes.trim(),
      });
      setForm(emptyForm);
      setShowAddModal(false);
      await loadData();
    } catch (err) { console.error("Save failed", err); }
    finally { setIsSaving(false); }
  };

  const handleEdit = async () => {
    if (!selectedPiece) return;
    setIsSaving(true);
    try {
      await pieces.update(selectedPiece.id, {
        reference: form.reference.trim().toUpperCase(),
        designation: form.designation.trim(),
        equipement_type: form.equipement_type,
        stock_actuel: Number(form.stock_actuel),
        stock_minimum: Number(form.stock_minimum),
        prix_unitaire: Number(form.prix_unitaire),
        fournisseur: form.fournisseur.trim(),
        notes: form.notes.trim(),
      });
      setShowEditModal(false);
      setSelectedPiece(null);
      await loadData();
    } catch (err) { console.error("Edit failed", err); }
    finally { setIsSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Supprimer cette pièce ?")) return;
    try { await pieces.delete(id); await loadData(); }
    catch (err) { console.error("Delete failed", err); }
  };

  const handleAiAnalyze = async () => {
    setIsAnalyzing(true);
    setAiResult('');
    try {
      const piecesInfo = filtered.map(p => {
        const status = p.stock_actuel === 0 ? '🚨 RUPTURE' : p.stock_actuel <= p.stock_minimum ? '⚠️ Stock bas' : '✅ OK';
        return `- ${p.designation} (${p.reference}) [${p.equipement_type}] | Stock: ${p.stock_actuel}/${p.stock_minimum} (${status}) | Fournisseur: ${p.fournisseur} | Prix: ${p.prix_unitaire.toLocaleString('fr')} TND`;
      }).join('\n');

      const totalVal = filtered.reduce((a, p) => a + p.stock_actuel * p.prix_unitaire, 0);
      const prompt = `Agis en tant que Supply Chain Manager pour un réseau hospitalier spécialisé en imagerie médicale.
Valeur actuelle du stock : ${totalVal.toLocaleString('fr')} TND.

Analyse ces pièces de rechange :
${piecesInfo}

Fournis une analyse structurée en 4 sections :
🔍 Analyse du risque — identifie le capital immobilisé et les pièces critiques
🛒 Recommandation — ruptures impactant la continuité des soins
📅 Timing d'achat — plan de commande (immédiat vs mois prochain)
💰 Impact budget — impact financier en TND et optimisation`;

      const res = await ai.analyzePerformance({ prompt_override: prompt } as any, 'TND');
      if (res.ok && res.result) {
        setAiResult(typeof res.result === 'string' ? res.result : JSON.stringify(res.result, null, 2));
      } else {
        setAiResult("L'IA n'a pas pu générer de réponse.");
      }
    } catch (err: any) {
      setAiResult(`Erreur: ${err?.message || "Analyse indisponible"}`);
    } finally { setIsAnalyzing(false); }
  };

  // Filters
  const types = useMemo(() => ['Tous', ...new Set(data.map(p => p.equipement_type).filter(Boolean))], [data]);
  const filtered = data.filter(p => {
    if (filterType !== 'Tous' && p.equipement_type !== filterType) return false;
    if (search) {
      const s = search.toLowerCase();
      return p.reference.toLowerCase().includes(s) || p.designation.toLowerCase().includes(s) || p.fournisseur.toLowerCase().includes(s);
    }
    return true;
  });

  // KPIs
  const lowStock = data.filter(p => p.stock_actuel <= p.stock_minimum);
  const ruptures = data.filter(p => p.stock_actuel === 0).length;
  const totalValeur = data.reduce((a, p) => a + p.stock_actuel * p.prix_unitaire, 0);
  const fournisseurs = new Set(data.map(p => p.fournisseur).filter(Boolean)).size;

  // Traceability data
  const traceData = useMemo(() => {
    const rows: any[] = [];
    interventionData.forEach((inter: any) => {
      const piecesStr = inter.pieces_utilisees || '';
      if (!piecesStr.trim()) return;
      const parts = piecesStr.replace(/;/g, ',').split(',').map((p: string) => p.trim()).filter(Boolean);
      parts.forEach((partName: string) => {
        rows.push({
          date: (inter.date || '').substring(0, 10),
          piece: partName,
          equipement: inter.machine || '',
          technicien: inter.technicien || '',
          statut: inter.statut || '',
        });
      });
    });
    return rows.sort((a, b) => b.date.localeCompare(a.date));
  }, [interventionData]);

  const tabs = [
    { icon: <Package className="w-4 h-4" />, label: 'Stock' },
    { icon: <History className="w-4 h-4" />, label: 'Traçabilité' },
    { icon: <Edit className="w-4 h-4" />, label: 'Modifier / Supprimer' },
    { icon: <Brain className="w-4 h-4" />, label: 'Prédictions & Achats IA' },
  ];

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <Wrench className="w-7 h-7" /> Pièces de Rechange
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion du stock, traçabilité et prédictions IA</p>
        </div>
        <button onClick={() => { setForm(emptyForm); setShowAddModal(true); }} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg">
          <Plus className="w-4 h-4" /> Nouvelle Pièce
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-savia-accent"><Package className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-savia-accent">{data.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">Total pièces</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-red-400"><TrendingDown className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-red-400">{lowStock.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">Stock critique</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-green-400"><DollarSign className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-green-400">{(totalValeur / 1000).toFixed(0)}K</div>
          <div className="text-xs text-savia-text-muted mt-1">Valeur stock (TND)</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-purple-400"><Factory className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-purple-400">{fournisseurs}</div>
          <div className="text-xs text-savia-text-muted mt-1">Fournisseurs</div>
        </div>
      </div>

      {/* Alerte stock critique */}
      {lowStock.length > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span className="font-bold text-red-400">{lowStock.length} pièce(s) en stock critique !</span>
            <span className="text-xs text-savia-text-muted ml-2">({ruptures} en rupture, {lowStock.length - ruptures} stock bas)</span>
          </div>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {lowStock.map(p => (
              <div key={p.id} className={`flex items-center justify-between p-2 rounded-lg ${p.stock_actuel === 0 ? 'bg-red-500/10 border-l-4 border-red-500' : 'bg-yellow-500/5 border-l-4 border-yellow-500'}`}>
                <div>
                  <span className="font-bold text-sm">{p.designation}</span>
                  <span className="text-xs text-savia-text-muted ml-2">{p.reference}</span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1"><Boxes className="w-3 h-3" /> {p.stock_actuel} / Min: {p.stock_minimum}</span>
                  <span className="flex items-center gap-1"><Factory className="w-3 h-3" /> {p.fournisseur}</span>
                  <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full font-bold ${p.stock_actuel === 0 ? 'bg-red-500 text-white' : 'bg-yellow-500 text-black'}`}>
                    {p.stock_actuel === 0 ? <><XCircle className="w-3 h-3" /> RUPTURE</> : <><AlertTriangle className="w-3 h-3" /> Bas</>}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input type="text" placeholder="🔍 Rechercher par référence, désignation ou fournisseur..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          {types.map(t => <option key={t} value={t}>{t === 'Tous' ? '🔧 Tous les types' : t}</option>)}
        </select>
      </div>

      <div className="text-xs text-savia-text-muted flex items-center gap-1">
        <Package className="w-3.5 h-3.5" /> {filtered.length} pièce(s) affichée(s)
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-savia-border overflow-x-auto">
        {tabs.map((tab, i) => (
          <button key={i} onClick={() => setActiveTab(i)} className={`${TAB_CLS} ${activeTab === i ? TAB_ACTIVE : TAB_INACTIVE} whitespace-nowrap flex items-center gap-2`}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 0: STOCK */}
      {activeTab === 0 && (
        <SectionCard title="Inventaire Stock">
          <div className="overflow-x-auto">
            <div className="overflow-y-auto" style={{maxHeight: '380px'}}>
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-savia-surface z-10">
                  <tr className="border-b border-savia-border">
                    {['Référence', 'Désignation', 'Type Équip.', 'Stock', 'Min', 'Fournisseur', 'Prix Unit.'].map(h => (
                      <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(p => (
                    <tr key={p.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                      <td className="py-2.5 px-3 font-mono text-savia-accent font-bold text-xs">{p.reference}</td>
                      <td className="py-2.5 px-3 font-semibold">{p.designation}</td>
                      <td className="py-2.5 px-3 text-xs text-savia-text-muted">{p.equipement_type}</td>
                      <td className="py-2.5 px-3 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${p.stock_actuel === 0 ? 'bg-red-500/10 text-red-400' : p.stock_actuel <= p.stock_minimum ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'}`}>
                          {p.stock_actuel}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-center text-xs text-savia-text-muted">{p.stock_minimum}</td>
                      <td className="py-2.5 px-3 text-sm">{p.fournisseur}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-sm">{p.prix_unitaire.toLocaleString('fr')} TND</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </SectionCard>
      )}

      {/* TAB 1: TRAÇABILITÉ */}
      {activeTab === 1 && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-savia-accent"><Wrench className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-savia-accent">{new Set(traceData.map(t => t.piece)).size}</div>
              <div className="text-xs text-savia-text-muted mt-1">Pièces différentes</div>
            </div>
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-blue-400"><Building2 className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-blue-400">{new Set(traceData.map(t => t.equipement)).size}</div>
              <div className="text-xs text-savia-text-muted mt-1">Équipements</div>
            </div>
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-purple-400"><Boxes className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-purple-400">{traceData.length}</div>
              <div className="text-xs text-savia-text-muted mt-1">Utilisations totales</div>
            </div>
          </div>

          <SectionCard title="Historique d'utilisation des pièces">
            {traceData.length === 0 ? (
              <div className="text-center text-savia-text-muted py-8">Aucune donnée de traçabilité disponible.</div>
            ) : (
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-savia-bg">
                    <tr className="border-b border-savia-border">
                      {['Date', 'Pièce', 'Équipement', 'Technicien', 'Statut'].map(h => (
                        <th key={h} className="text-left py-2 px-3 text-savia-text-muted">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {traceData.map((t, i) => (
                      <tr key={i} className="border-b border-savia-border/30">
                        <td className="py-2 px-3 text-xs">{t.date}</td>
                        <td className="py-2 px-3 font-semibold text-savia-accent">{t.piece}</td>
                        <td className="py-2 px-3">{t.equipement}</td>
                        <td className="py-2 px-3">{t.technicien}</td>
                        <td className="py-2 px-3"><span className={`px-2 py-0.5 rounded-full text-xs font-bold ${t.statut?.toLowerCase().includes('tur') ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>{t.statut}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </div>
      )}

      {/* TAB 2: MODIFIER / SUPPRIMER */}
      {activeTab === 2 && (
        <div className="space-y-3">
          {filtered.map(p => {
            const isLow = p.stock_actuel <= p.stock_minimum;
            return (
              <div key={p.id} className={`glass rounded-xl p-4 border ${isLow ? 'border-red-500/20' : 'border-savia-border/30'}`}>
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <span className={`text-lg flex items-center ${
                        p.stock_actuel === 0 ? 'text-red-400' : isLow ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                      {p.stock_actuel === 0
                        ? <XCircle className="w-4 h-4" />
                        : isLow
                        ? <AlertTriangle className="w-4 h-4" />
                        : <CheckCircle2 className="w-4 h-4" />}
                    </span>
                    <div>
                      <div className="font-bold">{p.reference} — {p.designation}</div>
                      <div className="text-xs text-savia-text-muted">{p.equipement_type} | Stock: {p.stock_actuel} | Min: {p.stock_minimum} | {p.prix_unitaire.toLocaleString('fr')} TND</div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => {
                      setSelectedPiece(p);
                      setForm({
                        reference: p.reference, designation: p.designation, equipement_type: p.equipement_type,
                        stock_actuel: String(p.stock_actuel), stock_minimum: String(p.stock_minimum),
                        prix_unitaire: String(p.prix_unitaire), fournisseur: p.fournisseur, notes: p.notes,
                      });
                      setShowEditModal(true);
                    }} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 text-sm font-semibold cursor-pointer">
                      <Edit className="w-3.5 h-3.5" /> Modifier
                    </button>
                    <button onClick={() => handleDelete(p.id)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 text-sm font-semibold cursor-pointer">
                      <Trash2 className="w-3.5 h-3.5" /> Supprimer
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* TAB 3: PRÉDICTIONS IA */}
      {activeTab === 3 && (
        <div className="space-y-6">
          <SectionCard title="Assistant d'Achat Prédictif">
            <div className="text-center space-y-4">
              <p className="text-sm text-savia-text-muted">L&apos;IA analyse vos cycles de remplacement et niveaux de stock pour anticiper les ruptures.</p>
              <div className="flex gap-4 justify-center flex-wrap">
                <div className="flex gap-2 flex-wrap">
                  <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-red-500/10 text-red-400">
                    <XCircle className="w-3 h-3" /> {ruptures} en rupture
                  </span>
                  <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-yellow-500/10 text-yellow-400">
                    <AlertTriangle className="w-3 h-3" /> {lowStock.length - ruptures} stock bas
                  </span>
                  <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-green-500/10 text-green-400">
                    <CheckCircle2 className="w-3 h-3" /> {data.length - lowStock.length} OK
                  </span>
                  <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-purple-500/10 text-purple-400">
                    <DollarSign className="w-3 h-3" /> Valeur: {(totalValeur / 1000).toFixed(0)}K TND
                  </span>
                </div>
              </div>
              <button onClick={handleAiAnalyze} disabled={isAnalyzing} className="flex items-center gap-2 px-6 py-3 rounded-lg font-bold text-savia-text bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 mx-auto disabled:opacity-50">
                {isAnalyzing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
                {isAnalyzing ? 'Analyse en cours...' : '🚀 Lancer l\'Analyse IA'}
              </button>
            </div>
          </SectionCard>

          {aiResult && (
            <SectionCard title="Résultat de l'Analyse IA">
              <div className="space-y-3">
                {/* Parse sections */}
                {(() => {
                  const sections = [
                    { key: 'risque', icon: '🔍', title: 'Analyse du risque', color: '#ef4444' },
                    { key: 'recommandation', icon: '🛒', title: 'Recommandation', color: '#f59e0b' },
                    { key: 'timing', icon: '📅', title: "Timing d'achat", color: '#10b981' },
                    { key: 'budget', icon: '💰', title: 'Impact budget', color: '#3b82f6' },
                  ];
                  // Simple display
                  return (
                    <div className="prose prose-invert max-w-none">
                      {sections.map(sec => {
                        const regex = new RegExp(`${sec.icon}[^\\n]*`, 'i');
                        return (
                          <div key={sec.key} className="mb-4 p-4 rounded-lg" style={{ background: `${sec.color}10`, borderLeft: `4px solid ${sec.color}` }}>
                            <div className="font-bold text-sm uppercase tracking-wider mb-2" style={{ color: sec.color }}>
                              {sec.icon} {sec.title}
                            </div>
                          </div>
                        );
                      })}
                      <div className="bg-savia-surface-hover/50 rounded-lg p-4 whitespace-pre-wrap text-sm text-savia-text leading-relaxed">
                        {typeof aiResult === 'string' ? aiResult : JSON.stringify(aiResult, null, 2)}
                      </div>
                    </div>
                  );
                })()}
              </div>
            </SectionCard>
          )}
        </div>
      )}

      {/* Add Modal */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="➕ Nouvelle Pièce" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-sm text-savia-text-muted mb-1">Référence</label><input className={INPUT_CLS} placeholder="TUBE-RX-001" value={form.reference} onChange={e => setForm({...form, reference: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Désignation *</label><input className={INPUT_CLS} placeholder="Tube radiogène" value={form.designation} onChange={e => setForm({...form, designation: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Type équipement</label>
            <select className={INPUT_CLS} value={form.equipement_type} onChange={e => setForm({...form, equipement_type: e.target.value})}>
              {TYPES_EQUIPEMENTS.map(t => <option key={t}>{t}</option>)}
            </select></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock actuel</label><input type="number" className={INPUT_CLS} value={form.stock_actuel} onChange={e => setForm({...form, stock_actuel: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock minimum</label><input type="number" className={INPUT_CLS} value={form.stock_minimum} onChange={e => setForm({...form, stock_minimum: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Prix unitaire (TND)</label><input type="number" className={INPUT_CLS} value={form.prix_unitaire} onChange={e => setForm({...form, prix_unitaire: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Fournisseur</label><input className={INPUT_CLS} placeholder="Siemens" value={form.fournisseur} onChange={e => setForm({...form, fournisseur: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Notes</label><input className={INPUT_CLS} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowAddModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text cursor-pointer">Annuler</button>
          <button onClick={handleSave} disabled={isSaving} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Sauvegarder
          </button>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal isOpen={showEditModal} onClose={() => setShowEditModal(false)} title={`✏️ Modifier — ${selectedPiece?.designation || ''}`} size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-sm text-savia-text-muted mb-1">Référence</label><input className={INPUT_CLS} value={form.reference} onChange={e => setForm({...form, reference: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Désignation</label><input className={INPUT_CLS} value={form.designation} onChange={e => setForm({...form, designation: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Type équipement</label>
            <select className={INPUT_CLS} value={form.equipement_type} onChange={e => setForm({...form, equipement_type: e.target.value})}>
              {TYPES_EQUIPEMENTS.map(t => <option key={t}>{t}</option>)}
            </select></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock actuel</label><input type="number" className={INPUT_CLS} value={form.stock_actuel} onChange={e => setForm({...form, stock_actuel: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock minimum</label><input type="number" className={INPUT_CLS} value={form.stock_minimum} onChange={e => setForm({...form, stock_minimum: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Prix unitaire (TND)</label><input type="number" className={INPUT_CLS} value={form.prix_unitaire} onChange={e => setForm({...form, prix_unitaire: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Fournisseur</label><input className={INPUT_CLS} value={form.fournisseur} onChange={e => setForm({...form, fournisseur: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Notes</label><input className={INPUT_CLS} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowEditModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text cursor-pointer">Annuler</button>
          <button onClick={handleEdit} disabled={isSaving} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Enregistrer
          </button>
        </div>
      </Modal>
    </div>
  );
}
